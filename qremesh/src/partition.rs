//! The layout as a partition of the surface into patches that each hold at
//! most one singularity, cut along field lines between them.
//!
//! This is the structure of QuadWild (Pietroni et al., "Reliable
//! Feature-Line Driven Quad-Remeshing", 2021), from the paper. The earlier
//! layout (`trace.rs`) traced every separatrix, which made every singularity
//! a patch corner: on an organic shape with seventy singularities, many
//! closer than a quad, that gives two- and seven-sided patches and arcs a
//! fraction of a quad long, which the quantizer can only round up. Here a
//! singularity is never on a cut. A patch is valid when it is a disk, has no
//! corner pointing in, and holds at most one singularity (two for a
//! six-sided one); the field's own index then makes it three-, four- or
//! five-sided, which is exactly what the fill's patterns are for: a quad
//! with no singularity is a grid, a triangle and a pentagon get a valence-3
//! or -5 vertex in the middle.
//!
//! Cuts run along mesh edges. A candidate is a field line traced exactly
//! through the triangles (as the old tracer did) and laid onto the mesh by
//! taking, wherever it crosses an edge, the nearer end of that edge: two
//! consecutive picks are corners of one triangle, so the picks are an edge
//! path, and it stays within half an edge of the exact line instead of
//! drifting, which a Dijkstra over edges with a per-step angle cost does
//! (every step can lean the same way for the same price as zigzagging).
//!
//! Every cut edge carries, at each end, which arm of the field it runs
//! along in that vertex's frame. A patch's corners are then read off
//! combinatorially: walking its outline, the arm turns by a quarter to the
//! left at a corner, not at all along a side, and to the right at a corner
//! that points in. Measuring angles on a zigzag of mesh edges would not
//! tell these apart.
//!
//! Paths are added while some patch is invalid, the one that most reduces
//! a count of what is wrong; then every path is taken out again, last
//! first, wherever the patches it separated merge into a valid one with
//! sides that still fit together. That second pass is what keeps the layout
//! coarse.

use crate::cplx::C;
use crate::cross::{Singularity, Surface};
use crate::math::V3;
use crate::patches;
use crate::trace::{field_dir, Topology};
use std::collections::{HashMap, HashSet, VecDeque};

fn key(a: u32, b: u32) -> (u32, u32) {
    (a.min(b), a.max(b))
}

pub struct Path {
    pub chain: Vec<u32>,
    /// Per chain vertex: the arm (0..4, in that vertex's frame) the path
    /// runs along there, in the direction of the chain.
    pub labels: Vec<u8>,
    pub kind: &'static str,
}

pub struct Partition {
    /// Every cut edge, features and boundary included.
    pub cut: HashSet<(u32, u32)>,
    pub feature: HashSet<(u32, u32)>,
    /// For the key (a, b), a < b: the arms at a and at b when going a → b.
    pub label: HashMap<(u32, u32), (u8, u8)>,
    pub paths: Vec<Path>,
    /// Patches still invalid when no candidate helped them.
    pub invalid: usize,
    pub added: usize,
    pub removed: usize,
}

/// The arms at `a` and `b` for travel a → b.
fn directed(label: &HashMap<(u32, u32), (u8, u8)>, a: u32, b: u32) -> Option<(u8, u8)> {
    if a < b {
        label.get(&(a, b)).copied()
    } else {
        label.get(&(b, a)).map(|&(lb, la)| ((la + 2) % 4, (lb + 2) % 4))
    }
}

/// Quarter turns to the left at `v` going u → v → w: 1 a corner, 0 none,
/// −1 a corner pointing in, 2 a turn back (the tip of a slit).
fn turn_of(label: &HashMap<(u32, u32), (u8, u8)>, u: u32, v: u32, w: u32) -> i64 {
    let (Some((_, arrive)), Some((leave, _))) = (directed(label, u, v), directed(label, v, w)) else { return 0 };
    match (leave as i64 - arrive as i64).rem_euclid(4) {
        3 => -1,
        t => t,
    }
}

/// A path's edges as keys, each with its arms stored for the key's own
/// direction (low → high vertex).
fn path_edges(path: &Path) -> impl Iterator<Item = ((u32, u32), (u8, u8))> + '_ {
    (0..path.chain.len() - 1).map(move |i| {
        let (a, b) = (path.chain[i], path.chain[i + 1]);
        let (la, lb) = (path.labels[i], path.labels[i + 1]);
        (key(a, b), if a < b { (la, lb) } else { ((lb + 2) % 4, (la + 2) % 4) })
    })
}

impl Partition {
    pub fn turn(&self, u: u32, v: u32, w: u32) -> i64 {
        turn_of(&self.label, u, v, w)
    }
}

struct Ctx<'a> {
    s: &'a Surface,
    mesh: crate::mesh::TriMesh,
    z: &'a [C],
    topo: Topology,
    /// Each vertex's four arms as surface vectors.
    arms: Vec<[V3; 4]>,
    vert_tris: Vec<Vec<u32>>,
    edge_tris: HashMap<(u32, u32), Vec<u32>>,
    /// Vertices of singular triangles: no cut may touch them.
    blocked: Vec<bool>,
    sing_tri: Vec<usize>,
    /// Angle defect (2π minus the angles round it) of each vertex off the
    /// boundary: the Gaussian curvature it carries.
    defect: Vec<f64>,
    /// The quad side at each vertex (`sizing`): every distance below that
    /// is "half a quad" or "three quads" is so in the local quad.
    h: &'a [f64],
    max_length: f64,
    /// Rules switched off by name in QREMESH_OFF, to measure each alone.
    off: Vec<String>,
}

enum End {
    Cut,
    Own,
    Closed,
}

struct Walk {
    chain: Vec<u32>,
    labels: Vec<u8>,
    end: End,
}

impl<'a> Ctx<'a> {
    fn is_off(&self, rule: &str) -> bool {
        self.off.iter().any(|x| x == rule)
    }

    fn label_at(&self, v: u32, d: V3) -> u8 {
        let a = &self.arms[v as usize];
        (0..4).max_by(|&i, &j| a[i].dot(d).total_cmp(&a[j].dot(d))).unwrap() as u8
    }

    /// Where the ray x + λd leaves triangle `t`, not through `skip` and not
    /// through an edge at `from` if given: (edge ends, point, fraction
    /// along the edge).
    fn exit(&self, t: usize, x: V3, d: V3, skip: Option<(u32, u32)>, from: Option<u32>) -> Option<((u32, u32), V3, f64)> {
        let tri = self.s.tris[t];
        let p = |i: u32| self.s.p[i as usize];
        let n = (p(tri[1]) - p(tri[0])).cross(p(tri[2]) - p(tri[0])).normalized();
        let d = d.project_tangent(n);
        let mut best: Option<(f64, (u32, u32), V3, f64)> = None;
        for k in 0..3 {
            let (a, b) = (tri[k], tri[(k + 1) % 3]);
            if skip == Some(key(a, b)) || from.is_some_and(|f| f == a || f == b) {
                continue;
            }
            // x + λd = a + μ(b − a), in the plane: cross with n.
            let e = p(b) - p(a);
            let den = d.cross(e).dot(n);
            if den.abs() < 1e-300 {
                continue;
            }
            let w = p(a) - x;
            let lambda = w.cross(e).dot(n) / den;
            let mu = w.cross(d).dot(n) / den;
            if lambda > 1e-12 && (-1e-9..=1.0 + 1e-9).contains(&mu) && best.map_or(true, |b| lambda < b.0) {
                best = Some((lambda, (a, b), x + d * lambda, mu.clamp(0.0, 1.0)));
            }
        }
        best.map(|(_, e, y, mu)| (e, y, mu))
    }

    /// A field line from vertex `start` along `dir`, laid onto mesh edges,
    /// until it reaches a vertex for which `stop` holds, its own chain or
    /// `other` (the other half of the same path), or comes back round to
    /// `start` (only if `close`). None if it meets a singularity, leaves
    /// the surface or runs too long.
    fn walk(&self, start: u32, dir: V3, other: &[u32], stop: &dyn Fn(u32) -> bool, close: bool) -> Option<Walk> {
        let w = self.walk_inner(start, dir, other, stop, close);
        if std::env::var("QREMESH_WALKS").is_ok() {
            eprintln!("    walk from {start}: {}", match &w { Err(why) => why.to_string(), Ok(w) => format!("{} edges, {}", w.chain.len() - 1, match w.end { End::Cut => "cut", End::Own => "own", End::Closed => "closed" }) });
        }
        w.ok()
    }

    fn walk_inner(&self, start: u32, dir: V3, other: &[u32], stop: &dyn Fn(u32) -> bool, close: bool) -> Result<Walk, &'static str> {
        let mut x = self.s.p[start as usize];
        // The first triangle: the one of `start`'s fan the direction points into.
        let mut first: Option<(usize, (u32, u32), V3, f64)> = None;
        for &t in &self.vert_tris[start as usize] {
            let d = dir.project_tangent(self.s.n[start as usize]);
            if let Some((e, y, mu)) = self.exit(t as usize, x, d, None, Some(start)) {
                first = Some((t as usize, e, y, mu));
                break;
            }
        }
        let (mut t, _, _, _) = first.ok_or("no first triangle")?;
        let mut d = dir;
        let mut chain = vec![start];
        let mut labels = vec![self.label_at(start, dir)];
        let mut entry: Option<(u32, u32)> = None;
        let mut length = 0.0;
        let other: HashSet<u32> = other.iter().copied().collect();
        let mut own: HashMap<u32, usize> = HashMap::from([(start, 0)]);
        for _ in 0..200_000 {
            d = field_dir(self.s, self.z, t, x, d);
            let from = if chain.len() == 1 && entry.is_none() { Some(start) } else { None };
            let ((a, b), y, mu) = self.exit(t, x, d, entry, from).ok_or("no exit")?;
            length += (y - x).norm();
            if length > self.max_length {
                return Err("too long");
            }
            // The nearer end of the crossed edge, or the other one if the
            // nearer is a singularity's: the path skirts it by half an edge.
            let (near, far) = if mu < 0.5 { (a, b) } else { (b, a) };
            let c = if self.blocked[near as usize] && !self.blocked[far as usize] { far } else { near };
            // Leaving a corner of the cuts, its neighbours on them are no
            // place to stop: the far end, if free, carries the line in.
            let c = if chain.len() == 1 && stop(c) && c != far && !stop(far) && !self.blocked[far as usize] { far } else { c };
            let last = *chain.last().unwrap();
            if c != last {
                if chain.len() >= 2 && c == chain[chain.len() - 2] {
                    // Back over the edge it just took: the line runs along it.
                    own.remove(&last);
                    chain.pop();
                    labels.pop();
                } else {
                    if self.blocked[c as usize] {
                        return Err("through a singularity");
                    }
                    let label = self.label_at(c, d);
                    if stop(c) || other.contains(&c) {
                        chain.push(c);
                        labels.push(label);
                        return Ok(Walk { chain, labels, end: if stop(c) { End::Cut } else { End::Own } });
                    }
                    if let Some(&i) = own.get(&c) {
                        if close && i == 0 {
                            chain.push(c);
                            labels.push(label);
                            return Ok(Walk { chain, labels, end: End::Closed });
                        }
                        chain.push(c);
                        labels.push(label);
                        return Ok(Walk { chain, labels, end: End::Own });
                    }
                    // Back near the start going the same way: close the loop
                    // with a short hop rather than spiral past it.
                    if close && length > 3.0 * self.h[start as usize] && d.dot(dir) > 0.7 && (self.s.p[c as usize] - self.s.p[start as usize]).norm() < 0.7 * self.h[start as usize] {
                        if let Some(hop) = self.hop(c, start, &own, stop) {
                            chain.push(c);
                            labels.push(label);
                            for &h in &hop[1..] {
                                chain.push(h);
                                labels.push(self.label_at(h, d));
                            }
                            return Ok(Walk { chain, labels, end: End::Closed });
                        }
                    }
                    own.insert(c, chain.len());
                    chain.push(c);
                    labels.push(label);
                }
            }
            let next = self.topo.across(t as u32, a, b).ok_or("off the surface")?;
            entry = Some(key(a, b));
            t = next as usize;
            x = y;
        }
        Err("ran out of steps")
    }

    /// The path with its end moved onto a junction of the cuts within half
    /// a quad of where it landed, if there is one it can reach: two paths
    /// crossing a line from either side should cross it at one point, not
    /// leave a sliver of an arc between their two T-junctions.
    fn snap_end(&self, path: &Path, cut_adj: &HashMap<u32, Vec<u32>>, is_cut: &dyn Fn(u32) -> bool) -> Option<Path> {
        let n = path.chain.len();
        if n < 3 {
            return None;
        }
        let c = path.chain[n - 1];
        // Junctions along the cuts from the landing point, nearest first.
        let mut best: Option<(f64, u32)> = None;
        let mut seen: HashMap<u32, f64> = HashMap::from([(c, 0.0)]);
        let mut stack = vec![c];
        while let Some(v) = stack.pop() {
            let d = seen[&v];
            if v != c && cut_adj.get(&v).map_or(0, Vec::len) >= 3 && best.map_or(true, |(bd, _)| d < bd) {
                best = Some((d, v));
            }
            for &w in cut_adj.get(&v).map_or(&[][..], |x| &x[..]) {
                let nd = d + (self.s.p[w as usize] - self.s.p[v as usize]).norm();
                if nd < 0.5 * self.h[c as usize] && seen.get(&w).map_or(true, |&o| nd < o) {
                    seen.insert(w, nd);
                    stack.push(w);
                }
            }
        }
        let (_, x) = best?;
        if cut_adj.get(&c).map_or(0, Vec::len) >= 3 {
            return None;
        }
        let own: HashMap<u32, usize> = path.chain[..n - 1].iter().enumerate().map(|(i, &v)| (v, i)).collect();
        let hop = self.hop(path.chain[n - 2], x, &own, is_cut)?;
        let d = self.arms[c as usize][path.labels[n - 1] as usize];
        let mut chain = path.chain[..n - 1].to_vec();
        let mut labels = path.labels[..n - 1].to_vec();
        for &h in &hop[1..] {
            chain.push(h);
            labels.push(self.label_at(h, d));
        }
        Some(Path { chain, labels, kind: path.kind })
    }

    /// The fewest edges from `a` to `b` through vertices that are free.
    fn hop(&self, a: u32, b: u32, own: &HashMap<u32, usize>, stop: &dyn Fn(u32) -> bool) -> Option<Vec<u32>> {
        let mut from: HashMap<u32, u32> = HashMap::from([(a, a)]);
        let mut queue = VecDeque::from([(a, 0)]);
        while let Some((v, depth)) = queue.pop_front() {
            if v == b {
                let mut path = vec![b];
                let mut v = b;
                while v != a {
                    v = from[&v];
                    path.push(v);
                }
                path.reverse();
                return Some(path);
            }
            if depth >= 4 {
                continue;
            }
            for &w in &self.s.adj[v as usize] {
                let free = w == b || (!own.contains_key(&w) && !stop(w) && !self.blocked[w as usize]);
                if free && !from.contains_key(&w) {
                    from.insert(w, v);
                    queue.push_back((w, depth + 1));
                }
            }
        }
        None
    }
}

fn add_path(path: &Path, cut: &mut HashSet<(u32, u32)>, label: &mut HashMap<(u32, u32), (u8, u8)>, on_cut: &mut [u32]) {
    for (e, stored) in path_edges(path) {
        if cut.insert(e) {
            on_cut[e.0 as usize] += 1;
            on_cut[e.1 as usize] += 1;
        }
        label.insert(e, stored);
    }
}

/// The cuts so far.
struct Cuts<'a> {
    cut: &'a HashSet<(u32, u32)>,
    label: &'a HashMap<(u32, u32), (u8, u8)>,
    on_cut: &'a [u32],
}

impl Cuts<'_> {
    /// The candidate that most lowers patch `r`'s badness with its gain (on
    /// equal gain: one snapped to a junction, then the shorter), and the
    /// candidates that leave it as it is.
    fn best(&self, ctx: &Ctx, regions: &Regions, r: usize, eval: &(patches::Patch, usize)) -> (Option<(usize, Path)>, Vec<Path>) {
        let before = eval.1;
        let mut cut_adj: HashMap<u32, Vec<u32>> = HashMap::new();
        for &(a, b) in self.cut {
            cut_adj.entry(a).or_default().push(b);
            cut_adj.entry(b).or_default().push(a);
        }
        let is_cut = |v: u32| self.on_cut[v as usize] > 0;
        let mut best: Option<(usize, f64, Path)> = None;
        let mut level = Vec::new();
        for cand in candidates(ctx, regions, r, &eval.0, &cut_adj, self.label, &is_cut) {
            let after = regions.split_badness(ctx, r, self.cut, self.label, &cand);
            if std::env::var("QREMESH_WALKS").is_ok() {
                eprintln!("    candidate {} of {} edges: badness {before} -> {after}", cand.kind, cand.chain.len() - 1);
            }
            if after == before {
                level.push(cand);
                continue;
            }
            if after > before {
                continue;
            }
            let gain = before - after;
            let len = cand.chain.len() as f64 + if cand.kind.ends_with("snapped") { 0.0 } else { 1e6 };
            if best.as_ref().map_or(true, |(g, l, _)| gain > *g || (gain == *g && len < *l)) {
                best = Some((gain, len, cand));
            }
        }
        (best.map(|(g, _, p)| (g, p)), level)
    }
}

/// What is wrong with a patch, counted: 0 for a valid one. Weighted so that
/// every step toward valid counts even when it leaves the pieces invalid:
/// a non-disk by the cuts still needed to open it into a disk (a sphere
/// one, a torus two, an annulus one), a singularity too many twice (four
/// split two and two is progress even though each half is a digon).
fn badness(p: &patches::Patch, singular: usize, paired: bool, bending: f64) -> usize {
    let mut b = p.concave + overbent(bending);
    if !p.is_disk() {
        let holes = p.loops as i64;
        let genus = ((2 - p.euler - holes) / 2).max(0);
        let cuts = if holes == 0 { if genus == 0 { 1 } else { 2 * genus } } else { 2 * genus + holes - 1 };
        b += 3 * cuts.max(1) as usize;
    }
    let allowed = if p.corners.len() == 6 && paired { 2 } else { 1 };
    b += 2 * singular.saturating_sub(allowed);
    if p.is_disk() && p.concave == 0 && !(3..=6).contains(&p.corners.len()) {
        b += 1;
    }
    b
}

/// Quarter turns of curvature beyond one full turn: a patch bending more
/// than that holds a limb or a lobe, which flattens onto a polygon so
/// badly that the grid misses its tip. Good patches of a blob or a cow hold
/// up to about five; a leg left in the body's patch, fifteen.
fn overbent(bending: f64) -> usize {
    (bending - 4.0).max(0.0).round() as usize
}

/// How many times over a disk holds more surface than its outline can
/// carry. A patch is filled from its sides alone, and the most quads an
/// outline of a given length can hold is a square's, (perimeter / 4)². A
/// horn or an ear cut off at its base is a bag: a short outline round a
/// long surface, which a fill stretches into a few huge quads. A flat
/// square is 1, a cube's face blown onto a sphere 1.4, half a sphere 2.5;
/// from 3.5 on the patch needs a ring cut round it.
fn bagged(p: &patches::Patch, area: f64, perimeter: f64) -> usize {
    if !p.is_disk() || perimeter <= 0.0 {
        return 0;
    }
    let side = perimeter / 4.0;
    ((area / (side * side) / 3.5).floor() as usize).min(4)
}

/// The quads a patch's sides can carry, from their lengths in quads: a
/// grid's for four sides, and for three or five the midpoint pattern's,
/// whose spokes t solve side_i = t_(i−1) + t_(i+1) and whose corner quads
/// are t_(i−1) × t_i. None for other counts (a hexagon's spokes are not
/// determined by its sides).
fn capacity(e: &[f64]) -> Option<f64> {
    let n = e.len();
    match n {
        4 => Some(0.25 * (e[0] + e[2]) * (e[1] + e[3])),
        3 | 5 => {
            // With c_j = side_(2j+1) the system is c_j = u_j + u_(j+1) round
            // an odd cycle, u_j = t_(2j): u_0 is half the alternating sum.
            let c = |j: usize| e[(2 * j + 1) % n];
            let mut u = vec![0.0; n];
            u[0] = 0.5 * (0..n).map(|j| if j % 2 == 0 { c(j) } else { -c(j) }).sum::<f64>();
            for j in 0..n - 1 {
                u[j + 1] = c(j) - u[j];
            }
            let t = |i: usize| -> f64 { (0..n).find(|&j| (2 * j) % n == i % n).map(|j| u[j].max(0.0)).unwrap() };
            Some((0..n).map(|i| t(i) * t(i + 1)).sum())
        }
        _ => None,
    }
}

/// Side lengths of a patch in local quads, walked along its outline from
/// corner to corner.
fn side_lengths(ctx: &Ctx, p: &patches::Patch) -> Vec<f64> {
    let s = ctx.s;
    let n = p.outline.len();
    let k = p.corners.len();
    (0..k)
        .map(|c| {
            let (mut i, end) = (p.corners[c], p.corners[(c + 1) % k]);
            let mut len = 0.0;
            loop {
                let j = (i + 1) % n;
                let (a, b) = (p.verts[p.outline[i] as usize] as usize, p.verts[p.outline[j] as usize] as usize);
                len += (s.p[b] - s.p[a]).norm() / (0.5 * (ctx.h[a] + ctx.h[b]));
                i = j;
                if i == end {
                    break;
                }
            }
            len
        })
        .collect()
}

/// Whether a patch's sides can be filled without a strip being squeezed:
/// the conditions under which the midpoint patterns exist (QuadWild's
/// equation 1, after Takayama), with a quad's worth of slack.
fn sides_fit(e: &[f64]) -> bool {
    let n = e.len();
    let at = |i: usize| e[i % n];
    match n {
        3 => (0..3).all(|i| at(i) <= at(i + 1) + at(i + 2)),
        4 => (0..2).all(|i| (at(i) - at(i + 2)).abs() <= 1.0 + 0.3 * at(i).max(at(i + 2))),
        5 => (0..5).all(|i| at(i) + at(i + 1) + at(i + 4) + 1.0 >= at(i + 2) + at(i + 3)),
        6 => (0..6).all(|i| at(i) <= at(i + 2) + at(i + 4) + 1.0),
        _ => false,
    }
}

pub fn layout(s: &Surface, z: &[C], sings: &[Singularity], features: &[(u32, u32)], h: &[f64], max_length: f64) -> Partition {
    let nv = s.p.len();
    let topo = Topology::new(&s.tris);
    let arms: Vec<[V3; 4]> = (0..nv)
        .map(|i| {
            let a = s.arm(i, z[i]);
            let b = s.n[i].cross(a);
            [a, b, -a, -b]
        })
        .collect();
    let mut vert_tris: Vec<Vec<u32>> = vec![Vec::new(); nv];
    let mut edge_tris: HashMap<(u32, u32), Vec<u32>> = HashMap::new();
    for (t, tri) in s.tris.iter().enumerate() {
        for k in 0..3 {
            vert_tris[tri[k] as usize].push(t as u32);
            edge_tris.entry(key(tri[k], tri[(k + 1) % 3])).or_default().push(t as u32);
        }
    }
    // A singularity touching a feature or the boundary is where the feature
    // turns (a cube's corner): it is a corner of the patches there, not
    // something inside one, and the feature is already a cut through it.
    let on_feature: HashSet<u32> = features.iter().flat_map(|&(a, b)| [a, b]).collect();
    let sings: Vec<&Singularity> = sings.iter().filter(|sg| !s.tris[sg.tri].iter().any(|v| on_feature.contains(v))).collect();
    let mut blocked = vec![false; nv];
    for sg in &sings {
        for &v in &s.tris[sg.tri] {
            blocked[v as usize] = true;
        }
    }
    let mut defect = vec![std::f64::consts::TAU; nv];
    for tri in &s.tris {
        for k in 0..3 {
            let (v, a, b) = (tri[k] as usize, tri[(k + 1) % 3] as usize, tri[(k + 2) % 3] as usize);
            defect[v] -= (s.p[a] - s.p[v]).normalized().dot((s.p[b] - s.p[v]).normalized()).clamp(-1.0, 1.0).acos();
        }
    }
    for (e, ts) in &edge_tris {
        if ts.len() == 1 {
            defect[e.0 as usize] = 0.0;
            defect[e.1 as usize] = 0.0;
        }
    }
    let ctx = Ctx { s, mesh: crate::mesh::TriMesh { v: s.p.clone(), f: s.tris.clone() }, z, topo, arms, vert_tris, edge_tris, blocked, sing_tri: sings.iter().map(|x| x.tri).collect(), defect, h, max_length, off: std::env::var("QREMESH_OFF").map(|s| s.split(',').map(str::to_string).collect()).unwrap_or_default() };

    // Feature lines that end in the open bound nothing; the field still
    // follows them, but as cuts they would only be slits, which the final
    // graph prunes too.
    let mut kept: HashSet<(u32, u32)> = features.iter().map(|&(a, b)| key(a, b)).collect();
    patches::prune(&mut kept, nv);
    let mut kept: Vec<(u32, u32)> = kept.into_iter().collect();
    kept.sort_unstable();
    let mut cut: HashSet<(u32, u32)> = HashSet::new();
    let mut label: HashMap<(u32, u32), (u8, u8)> = HashMap::new();
    for &(a, b) in &kept {
        let d = s.p[b as usize] - s.p[a as usize];
        cut.insert((a, b));
        label.insert((a, b), (ctx.label_at(a, d), ctx.label_at(b, d)));
    }
    let feature: HashSet<(u32, u32)> = cut.clone();
    let mut paths: Vec<Path> = Vec::new();
    let mut on_cut = vec![0u32; nv];
    for &(a, b) in &cut {
        on_cut[a as usize] += 1;
        on_cut[b as usize] += 1;
    }

    let debug = std::env::var("QREMESH_DEBUG").is_ok();
    let mut added = 0;
    let mut round = 0;
    loop {
        round += 1;
        let regions = Regions::new(&ctx, &cut);
        let evals: Vec<(patches::Patch, usize)> = (0..regions.tris.len()).map(|r| regions.eval(&ctx, r, &cut, &label)).collect();
        let bad: Vec<usize> = (0..evals.len()).filter(|&r| evals[r].1 > 0).collect();
        if debug {
            eprintln!("partition round {round}: {} patches, {} invalid, badness {}", evals.len(), bad.len(), evals.iter().map(|e| e.1).sum::<usize>());
        }
        if bad.is_empty() || round > 400 {
            break;
        }
        let mut progress = false;
        for &r in &bad {
            let before = evals[r].1;
            let cuts = Cuts { cut: &cut, label: &label, on_cut: &on_cut };
            let (best, level) = cuts.best(&ctx, &regions, r, &evals[r]);
            let mut chosen: Vec<Path> = Vec::new();
            if let Some((gain, path)) = best {
                if debug {
                    eprintln!("  patch {r} (badness {before}): {} path of {} edges, gain {gain}", path.kind, path.chain.len() - 1);
                }
                chosen.push(path);
            } else {
                // No one path helps. Some patches need two before they are
                // any better: a band round the body is first opened into a
                // disk with corners pointing in, then those are carried on.
                // Try each path that at least does no harm, and take the
                // one after which its pieces can be mended most.
                let mut pair: Option<(usize, Vec<Path>)> = None;
                for first in level.into_iter().take(if ctx.is_off("look") { 0 } else { 6 }) {
                    let (mut cut2, mut label2, mut on_cut2) = (cut.clone(), label.clone(), on_cut.clone());
                    add_path(&first, &mut cut2, &mut label2, &mut on_cut2);
                    let regions2 = Regions::new(&ctx, &cut2);
                    let mut pieces: Vec<u32> = regions.tris[r].iter().map(|&t| regions2.of[t as usize]).collect();
                    pieces.sort_unstable();
                    pieces.dedup();
                    let cuts2 = Cuts { cut: &cut2, label: &label2, on_cut: &on_cut2 };
                    let mut gain = 0;
                    let mut both = vec![first];
                    for &q in &pieces {
                        let eval = regions2.eval(&ctx, q as usize, &cut2, &label2);
                        if eval.1 == 0 {
                            continue;
                        }
                        if let (Some((g, second)), _) = cuts2.best(&ctx, &regions2, q as usize, &eval) {
                            gain += g;
                            both.push(second);
                        }
                    }
                    if gain > 0 && pair.as_ref().map_or(true, |(g, _)| gain > *g) {
                        pair = Some((gain, both));
                    }
                }
                match pair {
                    Some((gain, both)) => {
                        if debug {
                            eprintln!("  patch {r} (badness {before}): {} paths together, gain {gain}", both.len());
                        }
                        chosen = both;
                    }
                    None => {
                        if debug {
                            eprintln!("  patch {r} (badness {before}): no candidate helps");
                        }
                        continue;
                    }
                }
            }
            for path in chosen {
                add_path(&path, &mut cut, &mut label, &mut on_cut);
                paths.push(path);
                added += 1;
            }
            progress = true;
        }
        if !progress {
            break;
        }
    }

    // Take paths out again, last first, wherever the patches they separated
    // merge into something no worse (QuadWild's removal). Most layouts of an
    // organic shape keep some invalid patches, so "no worse" rather than
    // "valid" is what lets this pass coarsen them at all.
    let mut removed = 0;
    for i in (0..paths.len()).rev() {
        let edges: Vec<(u32, u32)> = paths[i].chain.windows(2).map(|w| key(w[0], w[1])).collect();
        let touched = |regions: &Regions| -> Vec<u32> {
            let mut t: Vec<u32> = edges.iter().flat_map(|e| ctx.edge_tris[e].iter().map(|&t| regions.of[t as usize])).collect();
            t.sort_unstable();
            t.dedup();
            t
        };
        let before = {
            let regions = Regions::new(&ctx, &cut);
            let evals = scored(&ctx, &regions, &touched(&regions), &cut, &label);
            score(&ctx, &evals)
        };
        let saved: Vec<((u32, u32), (u8, u8))> = edges.iter().map(|e| (*e, label[e])).collect();
        for e in &edges {
            cut.remove(e);
            label.remove(e);
        }
        let regions = Regions::new(&ctx, &cut);
        let evals = scored(&ctx, &regions, &touched(&regions), &cut, &label);
        if score(&ctx, &evals) <= before {
            paths.remove(i);
            removed += 1;
        } else {
            for (e, l) in saved {
                cut.insert(e);
                label.insert(e, l);
            }
        }
    }
    let regions = Regions::new(&ctx, &cut);
    let invalid = (0..regions.tris.len()).filter(|&r| regions.eval(&ctx, r, &cut, &label).1 > 0).count();
    if debug {
        eprintln!("partition: {added} paths added, {removed} removed, {invalid} patches left invalid");
        for r in 0..regions.tris.len() {
            let (p, b) = regions.eval(&ctx, r, &cut, &label);
            if p.concave > 0 || !p.is_disk() {
                eprintln!("  final patch {r}: {} triangles, concave {}, loops {}, euler {}, corners {}, badness {b}", regions.tris[r].len(), p.concave, p.loops, p.euler, p.corners.len());
            }
        }
        let mut b: Vec<String> = (0..regions.tris.len()).map(|r| {
            let p = regions.eval(&ctx, r, &cut, &label).0;
            let (area, perimeter) = regions.girth(&ctx, r, &p);
            let sides = side_lengths(&ctx, &p);
            format!("{:.1}/{}/{:.1}/k{} area {:.0} holds {:.0}", regions.bending(&ctx, r, &cut), regions.singular(&ctx, r), 16.0 * area / (perimeter * perimeter).max(1e-300), p.corners.len(), area, capacity(&sides).unwrap_or(-1.0))
        }).collect();
        b.sort();
        eprintln!("bending/singularities/bag per patch: {}", b.join("\n  "));
    }
    Partition { cut, feature, label, paths, invalid, added, removed }
}

/// What `score` reads of each of the patches `rs`.
fn scored(ctx: &Ctx, regions: &Regions, rs: &[u32], cut: &HashSet<(u32, u32)>, label: &HashMap<(u32, u32), (u8, u8)>) -> Vec<(patches::Patch, usize, f64, usize)> {
    rs.iter()
        .map(|&r| {
            let r = r as usize;
            let p = regions.eval(ctx, r, cut, label).0;
            let (area, perimeter) = regions.girth(ctx, r, &p);
            let bag = if ctx.is_off("bag") { 0 } else { bagged(&p, area, perimeter) };
            (p, regions.singular(ctx, r), regions.bending(ctx, r, cut), bag)
        })
        .collect()
}

/// How bad a set of patches is, compared lexicographically, worst first:
/// non-disks, corners pointing in, corner counts out of range, curvature
/// beyond a full turn (`overbent`) and bags (`bagged`), the most
/// singularities in one patch (one is fine), fewer patches holding exactly
/// one singularity, and sides that do not fit together. QuadWild's order
/// for deciding whether a removal makes things worse.
fn score(ctx: &Ctx, evals: &[(patches::Patch, usize, f64, usize)]) -> [i64; 7] {
    let mut out = [0i64; 7];
    for (p, singular, bending, bag) in evals {
        let disk = p.is_disk();
        let convex = disk && p.concave == 0;
        out[0] += !disk as i64;
        out[1] += p.concave as i64;
        out[2] += (convex && !(3..=6).contains(&p.corners.len())) as i64;
        out[3] += (overbent(*bending) + bag) as i64;
        out[4] = out[4].max((*singular).max(1) as i64);
        out[5] -= (*singular == 1) as i64;
        out[6] += (convex && (3..=6).contains(&p.corners.len()) && !sides_fit(&side_lengths(ctx, p))) as i64;
    }
    out
}

/// Triangles flooded across uncut edges.
struct Regions {
    of: Vec<u32>,
    tris: Vec<Vec<u32>>,
}

impl Regions {
    fn new(ctx: &Ctx, cut: &HashSet<(u32, u32)>) -> Regions {
        Self::flood(ctx, cut, None, (0..ctx.s.tris.len() as u32).collect())
    }

    fn flood(ctx: &Ctx, cut: &HashSet<(u32, u32)>, extra: Option<&HashSet<(u32, u32)>>, within: Vec<u32>) -> Regions {
        let inside: HashSet<u32> = within.iter().copied().collect();
        let mut of = vec![u32::MAX; ctx.s.tris.len()];
        let mut tris: Vec<Vec<u32>> = Vec::new();
        for &start in &within {
            if of[start as usize] != u32::MAX {
                continue;
            }
            let r = tris.len() as u32;
            let mut list = vec![start];
            of[start as usize] = r;
            let mut i = 0;
            while i < list.len() {
                let t = list[i];
                i += 1;
                let tri = ctx.s.tris[t as usize];
                for k in 0..3 {
                    let e = key(tri[k], tri[(k + 1) % 3]);
                    if cut.contains(&e) || extra.is_some_and(|x| x.contains(&e)) {
                        continue;
                    }
                    for &o in &ctx.edge_tris[&e] {
                        if of[o as usize] == u32::MAX && inside.contains(&o) {
                            of[o as usize] = r;
                            list.push(o);
                        }
                    }
                }
            }
            tris.push(list);
        }
        Regions { of, tris }
    }

    /// Curvature inside patch `r` with its sign ignored, in quarter turns:
    /// a limb is a cap and a saddle whose curvatures cancel in sum, but
    /// not in this. Vertices on cuts are left out.
    fn bending(&self, ctx: &Ctx, r: usize, cut: &HashSet<(u32, u32)>) -> f64 {
        let mut verts: Vec<u32> = self.tris[r].iter().flat_map(|&t| ctx.s.tris[t as usize]).collect();
        verts.sort_unstable();
        verts.dedup();
        let on_cut = |v: u32| ctx.s.adj[v as usize].iter().any(|&w| cut.contains(&key(v, w)));
        verts.iter().filter(|&&v| !on_cut(v)).map(|&v| ctx.defect[v as usize].abs()).sum::<f64>() / std::f64::consts::FRAC_PI_2
    }

    fn singular(&self, ctx: &Ctx, r: usize) -> usize {
        ctx.sing_tri.iter().filter(|&&t| self.of[t] == r as u32).count()
    }

    /// Patch `r`'s area and the length of its outline, in local quads.
    fn girth(&self, ctx: &Ctx, r: usize, p: &patches::Patch) -> (f64, f64) {
        let area: f64 = self.tris[r].iter().map(|&t| {
            let tri = ctx.s.tris[t as usize];
            let [a, b, c] = tri.map(|v| ctx.s.p[v as usize]);
            let h = tri.iter().map(|&v| ctx.h[v as usize]).sum::<f64>() / 3.0;
            (b - a).cross(c - a).norm() / 2.0 / (h * h)
        }).sum();
        let n = p.outline.len();
        let perimeter: f64 = (0..n).map(|i| {
            let (a, b) = (p.verts[p.outline[i] as usize] as usize, p.verts[p.outline[(i + 1) % n] as usize] as usize);
            (ctx.s.p[b] - ctx.s.p[a]).norm() / (0.5 * (ctx.h[a] + ctx.h[b]))
        }).sum();
        (area, perimeter)
    }

    /// Whether patch `r` holds exactly two singularities within two quads
    /// of each other. Such a pair may share a six-sided patch: no line fits
    /// between them. Two far apart may not: the patterns put a hexagon's
    /// two irregular vertices where its side counts say, not where the
    /// surface bulges, and a long hexagon with one at each end came out
    /// three quads wide across a rump ten quads wide.
    fn paired(&self, ctx: &Ctx, r: usize) -> bool {
        let at: Vec<(V3, f64)> = ctx.sing_tri.iter().filter(|&&t| self.of[t] == r as u32).map(|&t| {
            let tri = ctx.s.tris[t];
            ((ctx.s.p[tri[0] as usize] + ctx.s.p[tri[1] as usize] + ctx.s.p[tri[2] as usize]) / 3.0, ctx.h[tri[0] as usize])
        }).collect();
        at.len() == 2 && (ctx.is_off("paired") || (at[0].0 - at[1].0).norm() < 2.0 * 0.5 * (at[0].1 + at[1].1))
    }

    /// The patch and its badness.
    fn eval(&self, ctx: &Ctx, r: usize, cut: &HashSet<(u32, u32)>, label: &HashMap<(u32, u32), (u8, u8)>) -> (patches::Patch, usize) {
        let turn = |u: u32, v: u32, w: u32| turn_of(label, u, v, w);
        let p = patches::patch(&ctx.mesh, &self.tris[r], cut, &ctx.edge_tris, &HashSet::new(), &HashMap::new(), Some(&turn));
        let mut b = badness(&p, self.singular(ctx, r), self.paired(ctx, r), self.bending(ctx, r, cut));
        let (area, perimeter) = self.girth(ctx, r, &p);
        if !ctx.is_off("bag") {
            b += bagged(&p, area, perimeter);
        }
        // Sides no pattern can join evenly (a "triangle" round the whole
        // body, a quad three times longer on one side than the other): the
        // fill squeezes dozens of rows into a band. Another cut is needed.
        if !ctx.is_off("unfit") && p.is_disk() && p.concave == 0 && (3..=6).contains(&p.corners.len()) && !sides_fit(&side_lengths(ctx, &p)) {
            b += 1;
        }
        // A sliver between two cuts running side by side: nothing can
        // mend it (a line across it is an edge long), so a path that would
        // make one must never be taken. Width ≈ twice the area over the
        // perimeter.
        // The same for a strip that is wide enough but many times longer
        // (16 · area / perimeter² is 4 · width / length for one): two lines
        // a quad and a half apart for fifty quads, joined at a snapped end.
        // Its corners come out wrong and the quantizer inflates it.
        if perimeter > 0.0 && (2.0 * area / perimeter < 0.3 || (!ctx.is_off("thin") && 16.0 * area / (perimeter * perimeter) < 0.15)) {
            b += 10;
        }
        (p, b)
    }

    /// Total badness of the pieces patch `r` falls into with `path` cut too.
    fn split_badness(&self, ctx: &Ctx, r: usize, cut: &HashSet<(u32, u32)>, label: &HashMap<(u32, u32), (u8, u8)>, path: &Path) -> usize {
        let mut cut2 = cut.clone();
        let mut label2 = label.clone();
        for (e, stored) in path_edges(path) {
            cut2.insert(e);
            label2.insert(e, stored);
        }
        let pieces = Regions::flood(ctx, &cut2, None, self.tris[r].clone());
        (0..pieces.tris.len()).map(|q| pieces.eval(ctx, q, &cut2, &label2).1).sum()
    }
}

/// Paths that might mend patch `r`: straight on from every corner that
/// points in, and through seeds spread over the patch, a field line each
/// way in each of the two directions.
fn candidates(ctx: &Ctx, regions: &Regions, r: usize, p: &patches::Patch, cut_adj: &HashMap<u32, Vec<u32>>, label: &HashMap<(u32, u32), (u8, u8)>, is_cut: &dyn Fn(u32) -> bool) -> Vec<Path> {
    let s = ctx.s;
    let mut out = Vec::new();
    // Corners pointing in, and slit tips: carry the arriving line on.
    let n = p.outline.len();
    for i in 0..n {
        let (u, v, w) = (p.verts[p.outline[(i + n - 1) % n] as usize], p.verts[p.outline[i] as usize], p.verts[p.outline[(i + 1) % n] as usize]);
        let t = turn_of(label, u, v, w);
        if t != -1 && t != 2 {
            continue;
        }
        let (Some((_, arrive)), Some((leave, _))) = (directed(label, u, v), directed(label, v, w)) else { continue };
        let mut dirs = vec![ctx.arms[v as usize][arrive as usize]];
        if t == -1 {
            dirs.push(ctx.arms[v as usize][((leave + 2) % 4) as usize]);
        }
        for d in dirs {
            let stop = |x: u32| x != v && is_cut(x);
            if let Some(wk) = ctx.walk(v, d, &[], &stop, false) {
                if wk.chain.len() >= 2 && matches!(wk.end, End::Cut) {
                    out.push(Path { chain: wk.chain, labels: wk.labels, kind: "corner" });
                }
            }
        }
    }

    // Seeds: farthest-point samples of the patch's free vertices, away from
    // its cuts and its singularities.
    let tris = &regions.tris[r];
    let mut verts: Vec<u32> = tris.iter().flat_map(|&t| s.tris[t as usize]).collect();
    verts.sort_unstable();
    verts.dedup();
    let in_patch: HashSet<u32> = verts.iter().copied().collect();
    let mut dist: HashMap<u32, f64> = HashMap::new();
    let mut sources: Vec<u32> = verts.iter().copied().filter(|&v| is_cut(v)).collect();
    if sources.is_empty() {
        sources.push(verts[0]);
    }
    let spread = |dist: &mut HashMap<u32, f64>, from: &[u32]| {
        let mut heap = std::collections::BinaryHeap::new();
        for &v in from {
            dist.insert(v, 0.0);
            heap.push((std::cmp::Reverse(0u64), v));
        }
        while let Some((std::cmp::Reverse(dq), v)) = heap.pop() {
            let d = f64::from_bits(dq);
            if d > dist[&v] {
                continue;
            }
            for &w in &s.adj[v as usize] {
                if !in_patch.contains(&w) {
                    continue;
                }
                let nd = d + (s.p[w as usize] - s.p[v as usize]).norm();
                if dist.get(&w).map_or(true, |&o| nd < o) {
                    dist.insert(w, nd);
                    heap.push((std::cmp::Reverse(nd.to_bits()), w));
                }
            }
        }
    };
    spread(&mut dist, &sources);
    let mut seeds = Vec::new();
    for _ in 0..8 {
        let Some((&v, &d)) = dist.iter().filter(|(&v, _)| !is_cut(v) && !ctx.blocked[v as usize]).max_by(|a, b| a.1.total_cmp(b.1).then(b.0.cmp(a.0))) else { break };
        if d < 0.5 * ctx.h[v as usize] {
            break;
        }
        seeds.push(v);
        spread(&mut dist, &[v]);
    }
    // Beside every singularity in the patch, on its four diagonals: the
    // lines through these run past it on each side, which is what
    // separates it from its neighbours. Lines through seeds far from
    // everything only cut off empty pieces.
    let free: Vec<u32> = verts.iter().copied().filter(|&v| !is_cut(v) && !ctx.blocked[v as usize]).collect();
    for &t in ctx.sing_tri.iter().filter(|&&t| regions.of[t] == r as u32).take(24) {
        let tri = s.tris[t];
        let c = (s.p[tri[0] as usize] + s.p[tri[1] as usize] + s.p[tri[2] as usize]) / 3.0;
        let arm = &ctx.arms[tri[0] as usize];
        let quad = ctx.h[tri[0] as usize];
        for k in 0..4 {
            let goal = c + (arm[k] + arm[(k + 1) % 4]).normalized() * (0.65 * quad);
            if let Some(&v) = free.iter().min_by(|&&a, &&b| (s.p[a as usize] - goal).norm2().total_cmp(&(s.p[b as usize] - goal).norm2())) {
                if (s.p[v as usize] - goal).norm() < 0.4 * quad && !seeds.contains(&v) {
                    seeds.push(v);
                }
            }
        }
    }
    // Midway between each singularity and its two nearest in the patch: two
    // close together need a line between them, and the diagonal seeds of
    // either may land beyond the other.
    let mine: Vec<V3> = ctx.sing_tri.iter().filter(|&&t| regions.of[t] == r as u32).map(|&t| {
        let tri = s.tris[t];
        (s.p[tri[0] as usize] + s.p[tri[1] as usize] + s.p[tri[2] as usize]) / 3.0
    }).collect();
    for (i, &a) in mine.iter().enumerate().take(24) {
        let mut near: Vec<(f64, V3)> = mine.iter().enumerate().filter(|&(j, _)| j != i).map(|(_, &b)| ((b - a).norm(), b)).collect();
        near.sort_by(|x, y| x.0.total_cmp(&y.0));
        for &(_, b) in near.iter().take(2) {
            let goal = (a + b) / 2.0;
            if let Some(&v) = free.iter().min_by(|&&x, &&y| (s.p[x as usize] - goal).norm2().total_cmp(&(s.p[y as usize] - goal).norm2())) {
                if !seeds.contains(&v) {
                    seeds.push(v);
                }
            }
        }
    }
    for &seed in &seeds {
        for family in 0..2 {
            let d = ctx.arms[seed as usize][family];
            let Some(a) = ctx.walk(seed, d, &[], is_cut, true) else { continue };
            if matches!(a.end, End::Closed) {
                out.push(Path { chain: a.chain, labels: a.labels, kind: "loop" });
                continue;
            }
            let Some(b) = ctx.walk(seed, -d, &a.chain, is_cut, false) else { continue };
            let mut chain: Vec<u32> = b.chain.iter().rev().copied().collect();
            let mut labels: Vec<u8> = b.labels.iter().rev().map(|&l| (l + 2) % 4).collect();
            chain.extend_from_slice(&a.chain[1..]);
            labels.extend_from_slice(&a.labels[1..]);
            out.push(Path { chain, labels, kind: "seed" });
        }
    }
    // Each path also with its ends moved onto nearby junctions.
    let reverse = |p: &Path| Path { chain: p.chain.iter().rev().copied().collect(), labels: p.labels.iter().rev().map(|&l| (l + 2) % 4).collect(), kind: p.kind };
    let mut snapped = Vec::new();
    for p in &out {
        if p.kind == "loop" {
            continue;
        }
        let tail = ctx.snap_end(p, cut_adj, is_cut);
        let both = tail.as_ref().unwrap_or(p);
        let head = if p.kind == "seed" { ctx.snap_end(&reverse(both), cut_adj, is_cut).map(|q| reverse(&q)) } else { None };
        if let Some(h) = head {
            snapped.push(h);
        } else if let Some(t) = tail {
            snapped.push(t);
        }
    }
    for p in snapped.iter_mut() {
        p.kind = match p.kind { "seed" => "seed, snapped", "corner" => "corner, snapped", k => k };
    }
    // Snapped ones first: on a tie they win.
    snapped.extend(out);
    snapped
}

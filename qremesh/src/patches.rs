//! The layout as a graph on the refined mesh: nodes where cut chains meet,
//! arcs between them, and patches — the regions the cuts bound — with their
//! corners and sides read off exactly.
//!
//! A patch is kept as its own little mesh, cut open along the cuts: a vertex
//! the patch touches from both sides of a cut (a torus cut open into one
//! patch has every vertex of its two loops on its outline twice) is two
//! local vertices. That makes outline walking and the Euler characteristic
//! plain mesh operations, and it is the mesh the patch is parametrized on.

use crate::math::V3;
use crate::mesh::TriMesh;
use std::collections::{HashMap, HashSet};
use std::f64::consts::PI;

pub struct Arc {
    /// Node vertices (refined mesh) at each end, and the chain between
    /// them, ends included.
    pub a: u32,
    pub b: u32,
    pub chain: Vec<u32>,
    pub length: f64,
    /// A sharp feature or the surface's boundary rather than a trace: its
    /// vertices stay put when the result is smoothed.
    pub feature: bool,
}

pub struct Patch {
    /// Local vertex → refined vertex.
    pub verts: Vec<u32>,
    pub tris: Vec<[u32; 3]>,
    /// The outline as local vertices, in the winding of the triangles.
    /// Only the first loop if there are several; `loops` says.
    pub outline: Vec<u32>,
    pub loops: usize,
    pub euler: i64,
    /// Indices into `outline` where the corners are.
    pub corners: Vec<usize>,
    /// Each side's arcs from one corner to the next: (arc, runs forward).
    pub sides: Vec<Vec<(usize, bool)>>,
    /// Nodes on the outline whose interior angle is about three quarters
    /// of a turn or more: a corner that points in, which no grid fits.
    pub concave: usize,
}

impl Patch {
    pub fn is_disk(&self) -> bool {
        self.loops == 1 && self.euler == 1
    }
}

pub struct Graph {
    pub arcs: Vec<Arc>,
    pub patches: Vec<Patch>,
    /// Region of each refined triangle.
    pub region: Vec<u32>,
    pub nodes: HashSet<u32>,
    /// Dangling chains pruned away (a trace that ended on nothing).
    pub pruned: usize,
}

/// A chain's length with its zigzag smoothed out first: a cut laid on mesh
/// edges swings up to half an edge either side of the line it stands for,
/// and its raw length overstates that line's by a tenth or more.
pub fn chain_length(m: &TriMesh, chain: &[u32]) -> f64 {
    let mut p: Vec<V3> = chain.iter().map(|&v| m.v[v as usize]).collect();
    for _ in 0..3 {
        let q = p.clone();
        for i in 1..p.len().saturating_sub(1) {
            p[i] = (q[i - 1] + q[i] * 2.0 + q[i + 1]) / 4.0;
        }
    }
    p.windows(2).map(|w| (w[1] - w[0]).norm()).sum()
}

fn key(a: u32, b: u32) -> (u32, u32) {
    (a.min(b), a.max(b))
}

/// Cuts that end in a vertex with no other cut: a slit, which bounds
/// nothing. They are walked back to the first real node and dropped.
pub fn prune(cut: &mut HashSet<(u32, u32)>, nv: usize) -> usize {
    let mut pruned = 0;
    loop {
        let mut at: Vec<Vec<u32>> = vec![Vec::new(); nv];
        for &(a, b) in cut.iter() {
            at[a as usize].push(b);
            at[b as usize].push(a);
        }
        let Some(mut v) = (0..nv as u32).find(|&v| at[v as usize].len() == 1) else { return pruned };
        pruned += 1;
        let mut prev = u32::MAX;
        loop {
            let Some(&next) = at[v as usize].iter().find(|&&w| w != prev) else { break };
            cut.remove(&key(v, next));
            at[v as usize].retain(|&w| w != next);
            at[next as usize].retain(|&w| w != v);
            if at[next as usize].len() != 1 {
                break;
            }
            prev = v;
            v = next;
        }
    }
}

/// `features`: cut edges that are features or boundary rather than traces.
/// `window`: how far along a feature chain to look each way when judging
/// whether it turns a corner at a vertex (a jagged rim of mesh edges turns
/// at every vertex and is no corner at all).
///
/// `turn`, when given, says how many quarter turns to the left the cuts make
/// at a vertex going u → v → w (from the field's arms the cuts follow); it
/// decides nodes and corners instead of measured angles.
pub fn build(m: &TriMesh, cut_in: &HashSet<(u32, u32)>, features: &HashSet<(u32, u32)>, window: f64, turn: Option<&Turn>) -> Graph {
    let nv = m.v.len();
    let mut cut = cut_in.clone();
    let pruned = prune(&mut cut, nv);

    let mut edge_tris: HashMap<(u32, u32), Vec<u32>> = HashMap::new();
    for (t, tri) in m.f.iter().enumerate() {
        for k in 0..3 {
            edge_tris.entry(key(tri[k], tri[(k + 1) % 3])).or_default().push(t as u32);
        }
    }
    let mut at: Vec<Vec<u32>> = vec![Vec::new(); nv];
    for &(a, b) in &cut {
        at[a as usize].push(b);
        at[b as usize].push(a);
    }

    // Nodes: where chains meet or end, and where a feature chain turns a
    // corner (a square hole's corners are nodes with two cut edges).
    let mut nodes: HashSet<u32> = HashSet::new();
    for v in 0..nv as u32 {
        let n = at[v as usize].len();
        if n == 0 {
            continue;
        }
        if n != 2 {
            nodes.insert(v);
            continue;
        }
        let (p, q) = (at[v as usize][0], at[v as usize][1]);
        if let Some(turn) = turn {
            if turn(p, v, q) != 0 {
                nodes.insert(v);
            }
            continue;
        }
        if !(features.contains(&key(v, p)) && features.contains(&key(v, q))) {
            continue;
        }
        // Along the chain `window` each way, the far points.
        let far = |mut prev: u32, mut cur: u32| -> V3 {
            let mut gone = 0.0;
            while gone < window && at[cur as usize].len() == 2 {
                gone += (m.v[cur as usize] - m.v[prev as usize]).norm();
                let next = if at[cur as usize][0] == prev { at[cur as usize][1] } else { at[cur as usize][0] };
                prev = cur;
                cur = next;
                if cur == v {
                    break;
                }
            }
            m.v[cur as usize]
        };
        let (pf, qf) = (far(v, p), far(v, q));
        let d1 = (m.v[v as usize] - pf).normalized();
        let d2 = (qf - m.v[v as usize]).normalized();
        if d1.dot(d2) < 45f64.to_radians().cos() {
            nodes.insert(v);
        }
    }

    // Arcs: chains walked from each node, each cut edge taken once. A loop
    // with no node on it gets one, so it is an arc from a vertex to itself.
    let mut arcs: Vec<Arc> = Vec::new();
    let mut taken: HashSet<(u32, u32)> = HashSet::new();
    let mut arc_at: HashMap<(u32, u32), (usize, bool)> = HashMap::new();
    let walk = |start: u32, first: u32, nodes: &HashSet<u32>, taken: &mut HashSet<(u32, u32)>, arcs: &mut Vec<Arc>, arc_at: &mut HashMap<(u32, u32), (usize, bool)>| {
        let mut chain = vec![start, first];
        taken.insert(key(start, first));
        let (mut prev, mut v) = (start, first);
        while !nodes.contains(&v) {
            let Some(&next) = at[v as usize].iter().find(|&&w| w != prev) else { break };
            if taken.contains(&key(v, next)) {
                break;
            }
            taken.insert(key(v, next));
            chain.push(next);
            prev = v;
            v = next;
        }
        let length = chain_length(m, &chain);
        let feature = chain.windows(2).all(|w| features.contains(&key(w[0], w[1])));
        let id = arcs.len();
        arc_at.insert((chain[0], chain[1]), (id, true));
        arc_at.insert((chain[chain.len() - 1], chain[chain.len() - 2]), (id, false));
        arcs.push(Arc { a: chain[0], b: chain[chain.len() - 1], chain, length, feature });
    };
    let mut node_list: Vec<u32> = nodes.iter().copied().collect();
    node_list.sort_unstable();
    for &v in &node_list {
        for &w in &at[v as usize] {
            if !taken.contains(&key(v, w)) {
                walk(v, w, &nodes, &mut taken, &mut arcs, &mut arc_at);
            }
        }
    }
    let mut cut_list: Vec<(u32, u32)> = cut.iter().copied().collect();
    cut_list.sort_unstable();
    for &(a, b) in &cut_list {
        if !taken.contains(&(a, b)) {
            nodes.insert(a);
            walk(a, b, &nodes, &mut taken, &mut arcs, &mut arc_at);
        }
    }

    // Regions: triangles flooded across uncut edges.
    let mut region = vec![u32::MAX; m.f.len()];
    let mut regions = 0u32;
    for start in 0..m.f.len() {
        if region[start] != u32::MAX {
            continue;
        }
        let mut stack = vec![start as u32];
        region[start] = regions;
        while let Some(t) = stack.pop() {
            let tri = m.f[t as usize];
            for k in 0..3 {
                let e = key(tri[k], tri[(k + 1) % 3]);
                if cut.contains(&e) {
                    continue;
                }
                for &o in &edge_tris[&e] {
                    if region[o as usize] == u32::MAX {
                        region[o as usize] = regions;
                        stack.push(o);
                    }
                }
            }
        }
        regions += 1;
    }

    let mut tris_of: Vec<Vec<u32>> = vec![Vec::new(); regions as usize];
    for (t, &r) in region.iter().enumerate() {
        tris_of[r as usize].push(t as u32);
    }
    let patches = tris_of.iter().map(|tris| patch(m, tris, &cut, &edge_tris, &nodes, &arc_at, turn)).collect();
    Graph { arcs, patches, region, nodes, pruned }
}

pub type Turn<'a> = dyn Fn(u32, u32, u32) -> i64 + 'a;

pub fn patch(m: &TriMesh, tris: &[u32], cut: &HashSet<(u32, u32)>, edge_tris: &HashMap<(u32, u32), Vec<u32>>, nodes: &HashSet<u32>, arc_at: &HashMap<(u32, u32), (usize, bool)>, turn: Option<&Turn>) -> Patch {
    // Local vertices: each triangle corner, joined to the same corner of
    // the neighbour across every uncut edge.
    let index: HashMap<u32, usize> = tris.iter().enumerate().map(|(i, &t)| (t, i)).collect();
    let mut parent: Vec<usize> = (0..tris.len() * 3).collect();
    fn root(parent: &mut [usize], mut i: usize) -> usize {
        while parent[i] != i {
            parent[i] = parent[parent[i]];
            i = parent[i];
        }
        i
    }
    let corner = |i: usize, v: u32| -> usize {
        let tri = m.f[tris[i] as usize];
        i * 3 + (0..3).find(|&k| tri[k] == v).unwrap()
    };
    for (i, &t) in tris.iter().enumerate() {
        let tri = m.f[t as usize];
        for k in 0..3 {
            let (a, b) = (tri[k], tri[(k + 1) % 3]);
            let e = key(a, b);
            if cut.contains(&e) {
                continue;
            }
            for &o in &edge_tris[&e] {
                if let Some(&j) = index.get(&o) {
                    if j != i {
                        for v in [a, b] {
                            let (ra, rb) = (root(&mut parent, corner(i, v)), root(&mut parent, corner(j, v)));
                            parent[ra] = rb;
                        }
                    }
                }
            }
        }
    }
    let mut local_of: HashMap<usize, u32> = HashMap::new();
    let mut verts: Vec<u32> = Vec::new();
    let mut ltris: Vec<[u32; 3]> = Vec::with_capacity(tris.len());
    for (i, &t) in tris.iter().enumerate() {
        let tri = m.f[t as usize];
        let mut lt = [0u32; 3];
        for k in 0..3 {
            let r = root(&mut parent, i * 3 + k);
            lt[k] = *local_of.entry(r).or_insert_with(|| {
                verts.push(tri[k]);
                (verts.len() - 1) as u32
            });
        }
        ltris.push(lt);
    }

    // Outline: half-edges with no twin, chained.
    let mut half: HashSet<(u32, u32)> = HashSet::new();
    for lt in &ltris {
        for k in 0..3 {
            half.insert((lt[k], lt[(k + 1) % 3]));
        }
    }
    let mut next: HashMap<u32, u32> = HashMap::new();
    let mut edges = 0usize;
    for &(a, b) in &half {
        if a < b || !half.contains(&(b, a)) {
            edges += 1;
        }
        if !half.contains(&(b, a)) {
            next.insert(a, b);
        }
    }
    let euler = verts.len() as i64 - edges as i64 + ltris.len() as i64;
    let mut seen: HashSet<u32> = HashSet::new();
    let mut outline: Vec<u32> = Vec::new();
    let mut loops = 0;
    let mut starts: Vec<u32> = next.keys().copied().collect();
    starts.sort_unstable();
    for &s in &starts {
        if seen.contains(&s) {
            continue;
        }
        loops += 1;
        let mut lp = Vec::new();
        let mut v = s;
        while seen.insert(v) {
            lp.push(v);
            v = next[&v];
        }
        if outline.is_empty() {
            outline = lp;
        }
    }

    // Interior angle at each outline vertex: the angles of the patch's
    // triangles at it, summed.
    let mut angle: HashMap<u32, f64> = HashMap::new();
    for lt in &ltris {
        for k in 0..3 {
            let (v, p, q) = (lt[k], lt[(k + 1) % 3], lt[(k + 2) % 3]);
            let (pv, pp, pq) = (m.v[verts[v as usize] as usize], m.v[verts[p as usize] as usize], m.v[verts[q as usize] as usize]);
            let a = (pp - pv).normalized().dot((pq - pv).normalized()).clamp(-1.0, 1.0).acos();
            *angle.entry(v).or_default() += a;
        }
    }
    let mut corners = Vec::new();
    let mut concave = 0;
    if let Some(turn) = turn {
        // A slit's tip turns back on itself: as wrong as two corners in.
        let n = outline.len();
        for i in 0..n {
            let at = |k: usize| verts[outline[k % n] as usize];
            match turn(at(i + n - 1), at(i), at(i + 1)) {
                1 => corners.push(i),
                -1 => concave += 1,
                2 => concave += 2,
                _ => {}
            }
        }
    }
    for (i, &lv) in outline.iter().enumerate() {
        if turn.is_some() {
            break;
        }
        if !nodes.contains(&verts[lv as usize]) {
            continue;
        }
        let quarters = (angle[&lv] / (PI / 2.0)).round() as i64;
        if quarters <= 1 {
            corners.push(i);
        } else if quarters >= 3 {
            concave += 1;
        }
    }

    // Sides: from each corner to the next along the outline, the arcs met
    // at each node on the way.
    let mut sides = Vec::new();
    let n = outline.len();
    for (c, &start) in corners.iter().enumerate() {
        let end = corners[(c + 1) % corners.len()];
        let mut arcs = Vec::new();
        let mut i = start;
        loop {
            let v = verts[outline[i] as usize];
            let w = verts[outline[(i + 1) % n] as usize];
            if nodes.contains(&v) {
                if let Some(&a) = arc_at.get(&(v, w)) {
                    arcs.push(a);
                }
            }
            i = (i + 1) % n;
            if i == end {
                break;
            }
        }
        sides.push(arcs);
    }
    Patch { verts, tris: ltris, outline, loops, euler, corners, sides, concave }
}

impl Graph {
    /// Split arc `a` at its chain vertex `at`, which becomes a node: the
    /// first part keeps the id, the second is new, and every patch side
    /// holding the arc holds both. -> the new arc.
    pub fn split_arc(&mut self, m: &TriMesh, a: usize, at: usize) -> usize {
        let chain = self.arcs[a].chain.split_off(at);
        self.arcs[a].chain.push(chain[0]);
        let node = chain[0];
        self.nodes.insert(node);
        let len = |c: &[u32]| chain_length(m, c);
        self.arcs[a].length = len(&self.arcs[a].chain);
        self.arcs[a].b = node;
        let feature = self.arcs[a].feature;
        let b = *chain.last().unwrap();
        let length = len(&chain);
        self.arcs.push(Arc { a: node, b, chain, length, feature });
        let new = self.arcs.len() - 1;
        for p in self.patches.iter_mut() {
            for side in p.sides.iter_mut() {
                let mut i = 0;
                while i < side.len() {
                    if side[i].0 == a {
                        let fwd = side[i].1;
                        if fwd {
                            side.insert(i + 1, (new, true));
                        } else {
                            side.insert(i, (new, false));
                        }
                        i += 1;
                    }
                    i += 1;
                }
            }
        }
        new
    }
}

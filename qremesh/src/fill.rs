//! From the layout to quads: every patch mapped to a flat domain, cut into
//! quads there, its sides quantized to whole numbers of edges, and a grid
//! laid into each quad and pulled back onto the surface.
//!
//! A patch with four corners is one quad. Any other patch is first made into
//! quads in its domain: three- and five-sided patches from their centre
//! (the midpoint subdivision: a vertex of valence three or five in the
//! middle, the pattern Takayama's catalogue uses), two-sided and six-or-more
//! sided ones split first by a line between two side midpoints. The quads
//! so made are "kites", and every kite's opposite sides must quantize equal:
//! that is the whole constraint set the quantizer sees.
//!
//! The domain map is a Tutte embedding of the patch's own triangles: with
//! positive weights and a convex boundary it cannot fold, so every grid
//! point has one place on the surface. The map's shape is poor (it is not
//! conformal), which the smoothing afterwards repairs.

use crate::math::V3;
use crate::mesh::TriMesh;
use crate::patches::Graph;
use crate::quantize;
use std::collections::HashMap;
use std::f64::consts::TAU;

/// A point the quads are built between: a vertex of the refined mesh, or a
/// point that exists only in a patch's domain.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
enum Node {
    Vertex(u32),
    Domain(usize),
}

enum DPoint {
    /// The centroid of a piece's corners.
    Center { corners: Vec<Node> },
    /// Between two nodes, where arcs `first` and `second` meet, at the
    /// fraction their quantized lengths give.
    Mid { a: Node, b: Node, first: usize, second: usize },
}

enum Kind {
    Surface(usize),
    Domain(usize),
}

struct FArc {
    from: Node,
    to: Node,
    kind: Kind,
    target: f64,
}

/// A polygon in a patch's domain, its sides as arcs (arc, runs forward).
struct Piece {
    patch: usize,
    corners: Vec<Node>,
    sides: Vec<Vec<(usize, bool)>>,
    /// A four-sided piece whose sides could not be quantized equal: it is
    /// cut at a corner into a three- and a five-sided piece (a valence-3
    /// and a valence-5 vertex), which gives the quantizer room.
    force: bool,
}

struct Kite {
    patch: usize,
    corners: [Node; 4],
    sides: [Vec<(usize, bool)>; 4],
    /// The kite is the whole patch, whose domain is the integer rectangle:
    /// its corners are the rectangle's. (Looked up by vertex they could not
    /// be told apart on a patch that touches itself, like a torus cut open
    /// into one patch, whose four corners are one vertex.)
    whole: bool,
}

/// A patch's domain: its local vertices placed in the plane, with a bucket
/// grid of its triangles for finding which one holds a point.
struct Domain {
    uv: Vec<(f64, f64)>,
    tris: Vec<[u32; 3]>,
    cell: f64,
    lo: (f64, f64),
    grid: HashMap<(i64, i64), Vec<u32>>,
}

impl Domain {
    fn new(uv: Vec<(f64, f64)>, tris: Vec<[u32; 3]>) -> Domain {
        let lo = uv.iter().fold((f64::MAX, f64::MAX), |a, p| (a.0.min(p.0), a.1.min(p.1)));
        let hi = uv.iter().fold((f64::MIN, f64::MIN), |a, p| (a.0.max(p.0), a.1.max(p.1)));
        let extent = (hi.0 - lo.0).max(hi.1 - lo.1).max(1e-9);
        let cell = ((hi.0 - lo.0) * (hi.1 - lo.1) / tris.len().max(1) as f64).sqrt().max(extent / 200.0) * 2.0;
        let mut grid: HashMap<(i64, i64), Vec<u32>> = HashMap::new();
        for (t, tri) in tris.iter().enumerate() {
            let ps = tri.map(|i| uv[i as usize]);
            let a = (((ps[0].0.min(ps[1].0).min(ps[2].0) - lo.0) / cell).floor() as i64, ((ps[0].1.min(ps[1].1).min(ps[2].1) - lo.1) / cell).floor() as i64);
            let b = (((ps[0].0.max(ps[1].0).max(ps[2].0) - lo.0) / cell).floor() as i64, ((ps[0].1.max(ps[1].1).max(ps[2].1) - lo.1) / cell).floor() as i64);
            for x in a.0..=b.0 {
                for y in a.1..=b.1 {
                    grid.entry((x, y)).or_default().push(t as u32);
                }
            }
        }
        Domain { uv, tris, cell, lo, grid }
    }

    fn bary(&self, t: usize, p: (f64, f64)) -> [f64; 3] {
        let c = self.tris[t].map(|i| self.uv[i as usize]);
        let cross = |a: (f64, f64), b: (f64, f64)| a.0 * b.1 - a.1 * b.0;
        let sub = |a: (f64, f64), b: (f64, f64)| (a.0 - b.0, a.1 - b.1);
        let area = cross(sub(c[1], c[0]), sub(c[2], c[0]));
        if area.abs() < 1e-300 {
            return [1.0 / 3.0; 3];
        }
        let w0 = cross(sub(c[1], p), sub(c[2], p)) / area;
        let w1 = cross(sub(c[2], p), sub(c[0], p)) / area;
        [w0, w1, 1.0 - w0 - w1]
    }

    /// The triangle holding `p`, or the one it is least outside of.
    fn locate(&self, p: (f64, f64)) -> (usize, [f64; 3]) {
        let c = (((p.0 - self.lo.0) / self.cell).floor() as i64, ((p.1 - self.lo.1) / self.cell).floor() as i64);
        let mut best: Option<(f64, usize, [f64; 3])> = None;
        for ring in 0..3i64 {
            for x in c.0 - ring..=c.0 + ring {
                for y in c.1 - ring..=c.1 + ring {
                    let Some(ts) = self.grid.get(&(x, y)) else { continue };
                    for &t in ts {
                        let w = self.bary(t as usize, p);
                        let worst = w[0].min(w[1]).min(w[2]);
                        if best.map_or(true, |(b, _, _)| worst > b) {
                            best = Some((worst, t as usize, w));
                        }
                    }
                }
            }
            if let Some((worst, _, _)) = best {
                if worst >= -1e-9 {
                    break;
                }
            }
        }
        if best.is_none() {
            for t in 0..self.tris.len() {
                let w = self.bary(t, p);
                let worst = w[0].min(w[1]).min(w[2]);
                if best.map_or(true, |(b, _, _)| worst > b) {
                    best = Some((worst, t, w));
                }
            }
        }
        let (_, t, mut w) = best.expect("a domain has triangles");
        // Clamp a point just outside back onto the triangle.
        for x in w.iter_mut() {
            *x = x.max(0.0);
        }
        let sum = w[0] + w[1] + w[2];
        for x in w.iter_mut() {
            *x /= sum.max(1e-300);
        }
        (t, w)
    }
}

pub struct Output {
    pub v: Vec<V3>,
    pub faces: Vec<Vec<u32>>,
    /// Vertices held still when smoothing: on features and the boundary.
    pub fixed: Vec<bool>,
    /// Vertices on the layout's arcs, the borders of its patches.
    pub border: Vec<bool>,
    pub unfilled: usize,
    pub quantize_violations: usize,
    pub kites: usize,
    pub arcs: usize,
}

pub struct Filler<'a> {
    m: &'a TriMesh,
    graph: &'a mut Graph,
    h: f64,
    /// The quad side at each vertex of `m`.
    size: &'a [f64],
    farcs: Vec<FArc>,
    /// Fill arc of each graph arc: the two numberings part once domain
    /// arcs are made.
    farc_of: Vec<usize>,
    dpoints: Vec<DPoint>,
    kites: Vec<Kite>,
    /// Every piece waiting to be cut into kites.
    pending: Vec<Piece>,
    unfilled: usize,
    /// Each patch's preliminary domain, for measuring synthetic arcs.
    prelim: HashMap<usize, (Domain, HashMap<u32, (f64, f64)>)>,
    /// Integer length of each fill arc, when the arcs are quantized before
    /// the patches are cut (`build_patches`).
    pub int: Vec<i64>,
    /// Patches filled whole from a pattern (`build_patches`): the patch,
    /// its sides as fill arcs, and the pattern.
    templates: Vec<(usize, Vec<Vec<(usize, bool)>>, crate::pattern::Template)>,
}

fn fillable(p: &crate::patches::Patch) -> bool {
    p.is_disk() && p.concave == 0 && p.corners.len() >= 2 && !p.sides.iter().any(|s| s.is_empty())
}

/// Where the corners of an `n`-gon domain sit: the integer rectangle for a
/// quad, a regular polygon otherwise, and for a two-sided patch the two
/// ends of a circle's diameter — its sides are the two half circles, since
/// the boundary must be convex for the embedding to be one-to-one.
fn polygon(n: usize, sides: &[f64]) -> Vec<(f64, f64)> {
    if n == 4 {
        let (a, b) = (sides[0], sides[1]);
        vec![(0.0, 0.0), (a, 0.0), (a, b), (0.0, b)]
    } else {
        let scale = sides.iter().sum::<f64>() / n as f64;
        (0..n).map(|k| {
            let t = TAU * k as f64 / n as f64;
            (scale * t.cos(), scale * t.sin())
        }).collect()
    }
}

/// The point `f` of the way along side `c` of the domain polygon.
fn on_side(n: usize, poly: &[(f64, f64)], c: usize, f: f64) -> (f64, f64) {
    if n == 2 {
        let r = poly[0].0.abs();
        let t = std::f64::consts::PI * (c as f64 + f);
        return (r * t.cos(), r * t.sin());
    }
    let (q0, q1) = (poly[c], poly[(c + 1) % n]);
    (q0.0 + (q1.0 - q0.0) * f, q0.1 + (q1.1 - q0.1) * f)
}

impl<'a> Filler<'a> {
    pub fn new(m: &'a TriMesh, graph: &'a mut Graph, h: f64, size: &'a [f64]) -> Filler<'a> {
        let farcs = graph
            .arcs
            .iter()
            .enumerate()
            .map(|(i, a)| FArc { from: Node::Vertex(a.a), to: Node::Vertex(a.b), kind: Kind::Surface(i), target: a.length / h })
            .collect();
        let farc_of = (0..graph.arcs.len()).collect();
        Filler { m, graph, h, size, farcs, farc_of, dpoints: Vec::new(), kites: Vec::new(), pending: Vec::new(), unfilled: 0, prelim: HashMap::new(), int: Vec::new(), templates: Vec::new() }
    }

    /// The outline vertex of patch `p` that is refined vertex `v`. A node
    /// off the outline is a fault upstream; the nearest outline vertex
    /// stands in and the fault is reported.
    fn outline_local(&self, p: usize, v: u32) -> u32 {
        let patch = &self.graph.patches[p];
        if let Some(&l) = patch.outline.iter().find(|&&l| patch.verts[l as usize] == v) {
            return l;
        }
        let q = self.m.v[v as usize];
        let l = *patch.outline.iter().min_by(|&&a, &&b| (self.m.v[patch.verts[a as usize] as usize] - q).norm2().total_cmp(&(self.m.v[patch.verts[b as usize] as usize] - q).norm2())).unwrap();
        eprintln!("fill: node {v} is not on the outline of patch {p} (in the patch: {}); using the nearest outline vertex", patch.verts.contains(&v));
        l
    }

    fn node_vertex(&self, p: usize, c: usize) -> Node {
        let patch = &self.graph.patches[p];
        Node::Vertex(patch.verts[patch.outline[patch.corners[c]] as usize])
    }

    /// Cut every patch into kites and quantize; kites the quantizer cannot
    /// satisfy are cut further and the whole quantized again, a few times.
    pub fn build(&mut self) -> quantize::Solution {
        self.cut_patches();
        let mut sol = self.quantize();
        for _round in 0..12 {
            if sol.violated == 0 {
                break;
            }
            // One infeasible patch leaves several kites unsatisfied at once;
            // cutting them all would fill the patch with pleats, so only the
            // few worst go, and the rest get another chance.
            let mut bad = self.violated_kites(&sol.x);
            bad.sort_by(|&a, &b| self.mismatch(b, &sol.x).cmp(&self.mismatch(a, &sol.x)));
            bad.truncate(2);
            bad.sort_unstable();
            if std::env::var("QREMESH_DEBUG").is_ok() {
                eprintln!("    {} kites could not be quantized; cutting {}", sol.violated, bad.len());
            }
            for &k in bad.iter().rev() {
                let kite = self.kites.remove(k);
                self.pending.push(Piece { patch: kite.patch, corners: kite.corners.to_vec(), sides: kite.sides.to_vec(), force: true });
            }
            while let Some(piece) = self.pending.pop() {
                self.cut(piece);
            }
            sol = self.quantize();
        }
        sol
    }

    /// The layout's own arcs quantized first, then every patch filled whole
    /// from a pattern for its side counts (`pattern.rs`). Quads want their
    /// opposite sides equal; triangles and pentagons an even total with
    /// every midpoint-pattern spoke at least one (S_i = t_{i−1} + t_{i+1});
    /// that is QuadWild's quantization, with no kite-level constraints for
    /// the solver to get stuck on.
    pub fn build_patches(&mut self) -> quantize::Solution {
        let na = self.graph.arcs.len();
        // An arc's edges: its length in local quads, the integral of 1/size
        // along it (here the length times the mean of 1/size on its chain).
        let size = self.size;
        let target: Vec<f64> = self.graph.arcs.iter().map(|a| (a.length * a.chain.iter().map(|&v| 1.0 / size[v as usize]).sum::<f64>() / a.chain.len() as f64).max(0.05)).collect();
        let weight: Vec<f64> = target.iter().map(|t| 1.0 / t.max(1.0)).collect();
        let ok: Vec<bool> = self.graph.patches.iter().map(|p| fillable(p) && (3..=6).contains(&p.corners.len())).collect();
        let side_arcs = |p: &crate::patches::Patch| -> Vec<Vec<usize>> { p.sides.iter().map(|s| s.iter().map(|&(a, _)| a).collect()).collect() };
        // A quad is held to equal opposite sides only where its sides'
        // lengths allow it: within a quad or a quarter of each other.
        // Otherwise equality squeezes one side (an arc 11.5 quads long came
        // out 4 on Spot); QuadWild makes regularity a cost for this reason,
        // and the patterns fill an unequal quad with a 3/5 pair.
        let side_len = |patch: &crate::patches::Patch, i: usize| patch.sides[i].iter().map(|&(a, _)| target[a]).sum::<f64>();
        let grid: Vec<bool> = self.graph.patches.iter().enumerate().map(|(p, patch)| {
            ok[p] && patch.corners.len() == 4 && (0..2).all(|i| {
                let (a, b) = (side_len(patch, i), side_len(patch, i + 2));
                (a - b).abs() <= 1.0f64.max(0.25 * a.max(b))
            })
        }).collect();
        let mut constraints = Vec::new();
        for (p, patch) in self.graph.patches.iter().enumerate() {
            if grid[p] {
                for (i, j) in [(0, 2), (1, 3)] {
                    let mut c: Vec<(usize, i64)> = patch.sides[i].iter().map(|&(a, _)| (a, 1)).collect();
                    c.extend(patch.sides[j].iter().map(|&(a, _)| (a, -1)));
                    constraints.push(c);
                }
            }
        }
        let mut sol = quantize::solve(&quantize::Problem { target: target.clone(), weight: weight.clone(), constraints });
        let sides: Vec<quantize::Sides> = self.graph.patches.iter().enumerate().filter(|&(p, _)| ok[p]).map(|(p, patch)| quantize::Sides { sides: side_arcs(patch), grid: grid[p] }).collect();
        let odd = quantize::parity(&mut sol.x, &target, &weight, &sides);
        if std::env::var("QREMESH_DEBUG").is_ok() {
            eprintln!("    quantized {na} arcs: {} quads unequal, {odd} patches odd", sol.violated);
        }
        // Fill arcs are the graph arcs so far.
        self.int = (0..na).map(|a| sol.x[a]).collect();
        for p in 0..self.graph.patches.len() {
            if !ok[p] {
                self.unfilled += 1;
                continue;
            }
            let patch = &self.graph.patches[p];
            let sides: Vec<Vec<(usize, bool)>> = patch.sides.iter().map(|s| s.iter().map(|&(a, f)| (self.farc_of[a], f)).collect()).collect();
            let l: Vec<usize> = sides.iter().map(|s| s.iter().map(|&(a, _)| self.int[a].max(0) as usize).sum()).collect();
            let corners = polygon(l.len(), &l.iter().map(|&x| x as f64).collect::<Vec<_>>());
            match crate::pattern::build(&corners, &l) {
                Some(t) => {
                    if std::env::var("QREMESH_DEBUG").is_ok() {
                        let want: Vec<String> = patch.sides.iter().map(|s| format!("{:.1}", s.iter().map(|&(a, _)| target[a]).sum::<f64>())).collect();
                        eprintln!("    patch {p}: sides {l:?} (wanted {}) -> {} quads", want.join(" "), t.faces.len());
                    }
                    self.templates.push((p, sides, t))
                }
                None => {
                    if std::env::var("QREMESH_DEBUG").is_ok() {
                        eprintln!("    patch {p}: no pattern for sides {l:?}");
                    }
                    self.unfilled += 1;
                }
            }
        }
        sol.violated += odd;
        sol.x = self.int.clone();
        sol
    }

    /// How far a kite's opposite sides are from equal.
    fn mismatch(&self, k: usize, x: &[i64]) -> i64 {
        let sum = |side: &[(usize, bool)]| side.iter().map(|&(a, _)| x[a]).sum::<i64>();
        let s = &self.kites[k].sides;
        (sum(&s[0]) - sum(&s[2])).abs() + (sum(&s[1]) - sum(&s[3])).abs()
    }

    /// Kites whose opposite sides came out unequal, ascending.
    fn violated_kites(&self, x: &[i64]) -> Vec<usize> {
        let sum = |side: &[(usize, bool)]| side.iter().map(|&(a, _)| x[a]).sum::<i64>();
        (0..self.kites.len()).filter(|&k| { let s = &self.kites[k].sides; !s.iter().any(|s| s.is_empty()) && (sum(&s[0]) != sum(&s[2]) || sum(&s[1]) != sum(&s[3])) }).collect()
    }

    fn cut_patches(&mut self) {
        for p in 0..self.graph.patches.len() {
            let patch = &self.graph.patches[p];
            if !fillable(patch) {
                self.unfilled += 1;
                continue;
            }
            let n = patch.corners.len();
            let corners: Vec<Node> = (0..n).map(|c| self.node_vertex(p, c)).collect();
            let sides: Vec<Vec<(usize, bool)>> = patch.sides.iter().map(|s| s.iter().map(|&(a, f)| (self.farc_of[a], f)).collect()).collect();
            if n == 4 {
                self.kites.push(Kite { patch: p, corners: [corners[0], corners[1], corners[2], corners[3]], sides: [sides[0].clone(), sides[1].clone(), sides[2].clone(), sides[3].clone()], whole: true });
                continue;
            }
            self.pending.push(Piece { patch: p, corners, sides, force: false });
            let mut guard = 0;
            while let Some(piece) = self.pending.pop() {
                if std::env::var("QREMESH_DEBUG").is_ok() {
                    eprintln!("  cutting a {}-gon piece of patch {p}", piece.corners.len());
                }
                guard += 1;
                if guard > 64 {
                    eprintln!("fill: patch {p} would not stop splitting");
                    self.unfilled += 1;
                    break;
                }
                self.cut(piece);
            }
        }
    }

    /// The preliminary domain of patch `p`: boundary placed by geometric
    /// length, for measuring arcs that exist only in the domain.
    fn preliminary(&mut self, p: usize) {
        if self.prelim.contains_key(&p) {
            return;
        }
        let patch = &self.graph.patches[p];
        let n = patch.corners.len();
        let side_len: Vec<f64> = patch.sides.iter().map(|s| s.iter().map(|&(a, _)| self.graph.arcs[a].length).sum()).collect();
        let poly = polygon(n, &side_len);
        let mut boundary: HashMap<u32, (f64, f64)> = HashMap::new();
        let outline = &patch.outline;
        for c in 0..n {
            let total = side_len[c].max(1e-300);
            let mut i = patch.corners[c];
            let end = patch.corners[(c + 1) % n];
            let mut along = 0.0;
            loop {
                let f = along / total;
                boundary.insert(outline[i], on_side(n, &poly, c, f));
                let j = (i + 1) % outline.len();
                along += (self.m.v[patch.verts[outline[j] as usize] as usize] - self.m.v[patch.verts[outline[i] as usize] as usize]).norm();
                i = j;
                if i == end {
                    break;
                }
            }
        }
        if std::env::var("QREMESH_DEBUG").is_ok() { eprintln!("    boundary placed ({} of {} outline vertices)", boundary.len(), patch.outline.len()); }
        let dom = tutte(self.m, patch, &boundary);
        if std::env::var("QREMESH_DEBUG").is_ok() { eprintln!("    preliminary domain of patch {p} done"); }
        self.prelim.insert(p, (dom, boundary));
    }

    /// Domain position of a node in patch `p`'s preliminary domain.
    fn prelim_pos(&self, p: usize, node: Node) -> (f64, f64) {
        match node {
            Node::Vertex(v) => {
                let (_, boundary) = &self.prelim[&p];
                boundary[&self.outline_local(p, v)]
            }
            Node::Domain(d) => match &self.dpoints[d] {
                DPoint::Center { corners, .. } => {
                    let ps: Vec<(f64, f64)> = corners.iter().map(|&c| self.prelim_pos(p, c)).collect();
                    let n = ps.len() as f64;
                    (ps.iter().map(|q| q.0).sum::<f64>() / n, ps.iter().map(|q| q.1).sum::<f64>() / n)
                }
                DPoint::Mid { a, b, .. } => {
                    let (pa, pb) = (self.prelim_pos(p, *a), self.prelim_pos(p, *b));
                    ((pa.0 + pb.0) * 0.5, (pa.1 + pb.1) * 0.5)
                }
            },
        }
    }

    /// The surface length of the straight domain segment a→b in patch `p`.
    fn measure(&self, p: usize, a: Node, b: Node) -> f64 {
        let (dom, _) = &self.prelim[&p];
        let patch = &self.graph.patches[p];
        let (pa, pb) = (self.prelim_pos(p, a), self.prelim_pos(p, b));
        let steps = 24;
        let mut prev: Option<V3> = None;
        let mut total = 0.0;
        for k in 0..=steps {
            let f = k as f64 / steps as f64;
            let q = (pa.0 + (pb.0 - pa.0) * f, pa.1 + (pb.1 - pa.1) * f);
            let (t, w) = dom.locate(q);
            let tri = patch.tris[t];
            let x = (0..3).fold(V3::ZERO, |acc, k| acc + self.m.v[patch.verts[tri[k] as usize] as usize] * w[k]);
            if let Some(pr) = prev {
                total += (x - pr).norm();
            }
            prev = Some(x);
        }
        total
    }

    fn domain_arc(&mut self, p: usize, a: Node, b: Node) -> usize {
        let target = self.measure(p, a, b) / self.h;
        self.farcs.push(FArc { from: a, to: b, kind: Kind::Domain(p), target });
        self.farcs.len() - 1
    }

    /// Replace arc `old` by the two arcs it was split into, everywhere.
    fn replace(&mut self, old: usize, new: usize) {
        let fix = |side: &mut Vec<(usize, bool)>| {
            let mut i = 0;
            while i < side.len() {
                if side[i].0 == old {
                    if side[i].1 {
                        side.insert(i + 1, (new, true));
                    } else {
                        side.insert(i, (new, false));
                    }
                    i += 1;
                }
                i += 1;
            }
        };
        for k in self.kites.iter_mut() {
            for s in k.sides.iter_mut() {
                fix(s);
            }
        }
        for pc in self.pending.iter_mut() {
            for s in pc.sides.iter_mut() {
                fix(s);
            }
        }
    }

    /// A node halfway along a side: an existing node near the middle, or
    /// the arc there split (a surface arc at its chain vertex nearest the
    /// middle, a domain arc at its midpoint). -> (node, first half, second
    /// half).
    fn midpoint(&mut self, p: usize, side: &[(usize, bool)]) -> (Node, Vec<(usize, bool)>, Vec<(usize, bool)>) {
        self.split_side(p, side, 0.5)
    }

    /// A node `f` of the way along a side; see `midpoint`.
    fn split_side(&mut self, p: usize, side: &[(usize, bool)], f: f64) -> (Node, Vec<(usize, bool)>, Vec<(usize, bool)>) {
        assert!(!side.is_empty(), "a side with no arcs cannot be split");
        let lens: Vec<f64> = side.iter().map(|&(a, _)| self.farcs[a].target).collect();
        let total: f64 = lens.iter().sum();
        let goal = total * f;
        let mut cum = 0.0;
        let mut best: Option<(f64, usize)> = None;
        for j in 0..side.len() - 1 {
            cum += lens[j];
            let off = (cum - goal).abs();
            if off <= 0.15 * total && best.map_or(true, |(b, _)| off < b) {
                best = Some((off, j));
            }
        }
        if let Some((_, j)) = best {
            let (a, fwd) = side[j];
            let node = if fwd { self.farcs[a].to } else { self.farcs[a].from };
            return (node, side[..=j].to_vec(), side[j + 1..].to_vec());
        }
        // Split the arc holding the point.
        let mut cum = 0.0;
        let mut j = 0;
        while j + 1 < side.len() && cum + lens[j] < goal {
            cum += lens[j];
            j += 1;
        }
        let (a, fwd) = side[j];
        let want = (goal - cum) / lens[j].max(1e-300);
        let want = if fwd { want } else { 1.0 - want };
        let want = want.clamp(0.0, 1.0);
        // An arc of a single mesh edge has nowhere to split; the node at
        // its end stands in, or if the side is that one edge, the side is
        // left whole with an empty other half (a degenerate kite, skipped).
        if let Kind::Surface(ga) = self.farcs[a].kind {
            if self.graph.arcs[ga].chain.len() < 3 {
                let (first, second, node) = if j + 1 < side.len() {
                    (side[..=j].to_vec(), side[j + 1..].to_vec(), if fwd { self.farcs[a].to } else { self.farcs[a].from })
                } else if j > 0 {
                    (side[..j].to_vec(), side[j..].to_vec(), if fwd { self.farcs[a].from } else { self.farcs[a].to })
                } else {
                    (side.to_vec(), Vec::new(), if fwd { self.farcs[a].to } else { self.farcs[a].from })
                };
                return (node, first, second);
            }
        }
        let new = match self.farcs[a].kind {
            Kind::Surface(ga) => {
                let chain = &self.graph.arcs[ga].chain;
                let mut cum = vec![0.0];
                for w in chain.windows(2) {
                    cum.push(cum.last().unwrap() + (self.m.v[w[1] as usize] - self.m.v[w[0] as usize]).norm());
                }
                let goal = want * cum.last().unwrap();
                let mut at = (1..chain.len() - 1).min_by(|&i, &k| (cum[i] - goal).abs().total_cmp(&(cum[k] - goal).abs())).unwrap_or(1);
                at = at.clamp(1, chain.len() - 2);
                let gnew = self.graph.split_arc(self.m, ga, at);
                let node = Node::Vertex(self.graph.arcs[ga].b);
                self.farcs[a].to = node;
                self.farcs[a].target = self.graph.arcs[ga].length / self.h;
                let to = Node::Vertex(self.graph.arcs[gnew].b);
                self.farcs.push(FArc { from: node, to, kind: Kind::Surface(gnew), target: self.graph.arcs[gnew].length / self.h });
                self.farc_of.push(self.farcs.len() - 1);
                self.farcs.len() - 1
            }
            Kind::Domain(pp) => {
                let (from, to) = (self.farcs[a].from, self.farcs[a].to);
                let id = self.farcs.len();
                self.dpoints.push(DPoint::Mid { a: from, b: to, first: a, second: id });
                let node = Node::Domain(self.dpoints.len() - 1);
                let t = self.farcs[a].target;
                self.farcs[a].to = node;
                self.farcs[a].target = t * want;
                self.farcs.push(FArc { from: node, to, kind: Kind::Domain(pp), target: t * (1.0 - want) });
                id
            }
        };
        self.replace(a, new);
        // The side itself, as it now reads.
        let mut side: Vec<(usize, bool)> = side.to_vec();
        {
            let mut i = 0;
            while i < side.len() {
                if side[i].0 == a {
                    if side[i].1 {
                        side.insert(i + 1, (new, true));
                    } else {
                        side.insert(i, (new, false));
                    }
                    i += 1;
                }
                i += 1;
            }
        }
        let cut = side.iter().position(|&(x, f)| (x == a && f) || (x == new && !f)).unwrap() + 1;
        // Either way round, the new node is where the first part now ends.
        let _ = (p, fwd);
        (self.farcs[a].to, side[..cut].to_vec(), side[cut..].to_vec())
    }

    fn cut(&mut self, piece: Piece) {
        let p = piece.patch;
        let n = piece.corners.len();
        if piece.sides.iter().any(|s| s.is_empty()) {
            // A side of nothing: an arc of one mesh edge that could not be
            // split. The piece is left out rather than torn.
            self.unfilled += 1;
            return;
        }
        if n == 4 && piece.force {
            self.preliminary(p);
            let lens: Vec<f64> = piece.sides.iter().map(|s| s.iter().map(|&(a, _)| self.farcs[a].target).sum()).collect();
            let i = (0..4).max_by(|&a, &b| lens[a].total_cmp(&lens[b])).unwrap();
            let j = (i + 1) % 4;
            let (mi, first_i, second_i) = self.midpoint(p, &piece.sides[i].clone());
            let (mj, first_j, second_j) = self.midpoint(p, &piece.sides[j].clone());
            let x = self.domain_arc(p, mi, mj);
            let c = piece.corners.clone();
            self.pending.push(Piece { patch: p, corners: vec![mi, c[j], mj], sides: vec![second_i, first_j, vec![(x, false)]], force: false });
            self.pending.push(Piece { patch: p, corners: vec![c[i], mi, mj, c[(i + 2) % 4], c[(i + 3) % 4]], sides: vec![first_i, vec![(x, true)], second_j, piece.sides[(i + 2) % 4].clone(), piece.sides[(i + 3) % 4].clone()], force: false });
            return;
        }
        if n == 4 {
            self.kites.push(Kite { patch: p, corners: [piece.corners[0], piece.corners[1], piece.corners[2], piece.corners[3]], sides: [piece.sides[0].clone(), piece.sides[1].clone(), piece.sides[2].clone(), piece.sides[3].clone()], whole: false });
            return;
        }
        self.preliminary(p);
        // A three-sided patch whose longest side is at least the other two
        // together cannot be filled from its centre: with one corner's worth
        // of turning inside, the three kites are rectangles in the grid's
        // own metric, and a triangle of rectangles obeys the triangle
        // inequality. Such a patch gets its two ends cut off instead — two
        // lines from the long side to the middles of the short sides — and
        // is three, five and three sided: a valence-3, a valence-5 and a
        // valence-3 vertex, the pleat such a shape needs.
        if n == 3 {
            let lens: Vec<f64> = piece.sides.iter().map(|s| s.iter().map(|&(a, _)| self.farcs[a].target).sum()).collect();
            let i = (0..3).max_by(|&a, &b| lens[a].total_cmp(&lens[b])).unwrap();
            let (j, k) = ((i + 1) % 3, (i + 2) % 3);
            // Only a patch big enough for its three pieces to be a few
            // quads across is cut; a small thin one the quantizer stretches
            // by a quad or two instead.
            if lens[i] >= lens[j] + lens[k] - 2.0 && lens[j].min(lens[k]) >= 3.0 && lens[i] >= 6.0 {
                if std::env::var("QREMESH_DEBUG").is_ok() {
                    eprintln!("    thin triangle {:.1} {:.1} {:.1}: cutting both ends off", lens[i], lens[j], lens[k]);
                }
                let (nj, firstj, secondj) = self.midpoint(p, &piece.sides[j].clone());
                let (nk, firstk, secondk) = self.midpoint(p, &piece.sides[k].clone());
                // Cuts at thirds of the long side: the end triangles then
                // have a long diagonal, which keeps them fat, and the
                // five-sided middle has no side longer than its others.
                let (m, first_i, rest) = self.split_side(p, &piece.sides[i].clone(), 1.0 / 3.0);
                let (m2, middle_i, last_i) = self.split_side(p, &rest, 0.5);
                let x1 = self.domain_arc(p, m, nk);
                let x2 = self.domain_arc(p, nj, m2);
                let (ci, cj, ck) = (piece.corners[i], piece.corners[j], piece.corners[k]);
                self.pending.push(Piece { patch: p, corners: vec![ci, m, nk], sides: vec![first_i, vec![(x1, true)], secondk], force: false });
                self.pending.push(Piece { patch: p, corners: vec![m2, cj, nj], sides: vec![last_i, firstj, vec![(x2, true)]], force: false });
                self.pending.push(Piece { patch: p, corners: vec![m, m2, nj, ck, nk], sides: vec![middle_i, vec![(x2, false)], secondj, firstk, vec![(x1, false)]], force: false });
                return;
            }
        }
        if n == 3 || n == 5 {
            let mut mids = Vec::new();
            for i in 0..n {
                mids.push(self.midpoint(p, &piece.sides[i].clone()));
            }
            // Earlier splits may have changed later sides' arcs; re-read.
            self.dpoints.push(DPoint::Center { corners: piece.corners.clone() });
            let center = Node::Domain(self.dpoints.len() - 1);
            let spokes: Vec<usize> = (0..n).map(|i| self.domain_arc(p, mids[i].0, center)).collect();
            for i in 0..n {
                let prev = (i + n - 1) % n;
                self.kites.push(Kite {
                    patch: p,
                    corners: [piece.corners[i], mids[i].0, center, mids[prev].0],
                    sides: [mids[i].1.clone(), vec![(spokes[i], true)], vec![(spokes[prev], false)], mids[prev].2.clone()],
                    whole: false,
                });
            }
            return;
        }
        if n < 2 {
            self.unfilled += 1;
            return;
        }
        // Two sides, or six or more: a line between two side midpoints.
        let h = if n == 2 { 1 } else { n / 2 };
        let (m0, first0, second0) = self.midpoint(p, &piece.sides[0].clone());
        if std::env::var("QREMESH_DEBUG").is_ok() { eprintln!("    mid 0 done"); }
        let (mh, firsth, secondh) = self.midpoint(p, &piece.sides[h].clone());
        if std::env::var("QREMESH_DEBUG").is_ok() { eprintln!("    mid h done"); }
        let x = self.domain_arc(p, m0, mh);
        if std::env::var("QREMESH_DEBUG").is_ok() { eprintln!("    split arc measured {:.2}", self.farcs[x].target); }
        let reverse = |s: &[(usize, bool)]| -> Vec<(usize, bool)> { s.iter().rev().map(|&(a, f)| (a, !f)).collect() };
        let _ = reverse;
        // Piece A: c0, m0, mh, c_{h+1}, …, c_{n-1}.
        let mut ca = vec![piece.corners[0], m0, mh];
        let mut sa = vec![first0, vec![(x, true)], secondh];
        for i in h + 1..n {
            ca.push(piece.corners[i]);
            sa.push(piece.sides[i].clone());
        }
        // Piece B: m0, c1, …, ch, mh.
        let mut cb = vec![m0];
        let mut sb = vec![second0];
        for i in 1..=h {
            cb.push(piece.corners[i]);
            if i < h {
                sb.push(piece.sides[i].clone());
            }
        }
        cb.push(mh);
        sb.push(firsth);
        sb.push(vec![(x, false)]);
        // Sides split since the pieces were read: `replace` touches only
        // what is stored, so these go in before any further split.
        self.pending.push(Piece { patch: p, corners: ca, sides: sa, force: false });
        self.pending.push(Piece { patch: p, corners: cb, sides: sb, force: false });
    }

    /// Integer lengths for every arc.
    fn quantize(&self) -> quantize::Solution {
        let target: Vec<f64> = self.farcs.iter().map(|a| a.target.max(0.05)).collect();
        let weight: Vec<f64> = target.iter().map(|t| 1.0 / t.max(1.0)).collect();
        let mut constraints = Vec::new();
        for k in &self.kites {
            if k.sides.iter().any(|s| s.is_empty()) {
                continue;
            }
            for (s0, s2) in [(0, 2), (1, 3)] {
                let mut c: Vec<(usize, i64)> = k.sides[s0].iter().map(|&(a, _)| (a, 1)).collect();
                c.extend(k.sides[s2].iter().map(|&(a, _)| (a, -1)));
                constraints.push(c);
            }
        }
        if std::env::var("QREMESH_DEBUG").is_ok() {
            for (i, a) in self.farcs.iter().enumerate() {
                let kind = match a.kind { Kind::Surface(g) => format!("surface {g} chain {}..{}", self.graph.arcs[g].a, self.graph.arcs[g].b), Kind::Domain(p) => format!("domain of patch {p}") };
                eprintln!("    arc {i}: {:?} -> {:?} target {:.2} {kind}", a.from, a.to, a.target);
            }
            for (i, k) in self.kites.iter().enumerate() {
                let sides: Vec<String> = k.sides.iter().map(|s| s.iter().map(|&(a, f)| format!("{}{a}", if f { "" } else { "-" })).collect::<Vec<_>>().join("+")).collect();
                eprintln!("    kite {i} of patch {} whole {}: corners {:?} sides [{}]", k.patch, k.whole, k.corners, sides.join(" | "));
            }
        }
        let sol = quantize::solve(&quantize::Problem { target: target.clone(), weight, constraints: constraints.clone() });
        if std::env::var("QREMESH_DEBUG").is_ok() {
            for (i, c) in constraints.iter().enumerate() {
                let r: i64 = c.iter().map(|&(a, k)| k * sol.x[a]).sum();
                let show: Vec<String> = c.iter().map(|&(a, k)| format!("{}{}:{:.2}->{}", if k > 0 { "+" } else { "-" }, a, target[a], sol.x[a])).collect();
                eprintln!("    kite {} side pair {}: residual {r}  {}", i / 2, i % 2, show.join(" "));
            }
        }
        sol
    }

    /// The quad mesh.
    pub fn place(&self, lengths: &[i64]) -> Output {
        let mut v: Vec<V3> = Vec::new();
        let mut fixed: Vec<bool> = Vec::new();
        let mut on_arcs: Vec<u32> = Vec::new();
        let mut faces: Vec<Vec<u32>> = Vec::new();
        let mut node_out: HashMap<Node, u32> = HashMap::new();
        let mut arc_out: HashMap<usize, Vec<u32>> = HashMap::new();

        // Final domains: boundary placed in proportion to integer lengths.
        let mut domains: HashMap<usize, (Domain, HashMap<u32, (f64, f64)>)> = HashMap::new();
        let patches_used: std::collections::BTreeSet<usize> = self.kites.iter().map(|k| k.patch).chain(self.templates.iter().map(|t| t.0)).collect();
        for &p in &patches_used {
            let patch = &self.graph.patches[p];
            let n = patch.corners.len();
            let side_int: Vec<f64> = patch.sides.iter().map(|s| s.iter().map(|&(a, _)| lengths[self.farc_of[a]] as f64).sum()).collect();
            let poly = polygon(n, &side_int);
            let mut boundary: HashMap<u32, (f64, f64)> = HashMap::new();
            let outline = &patch.outline;
            for c in 0..n {
                let total = side_int[c].max(1e-300);
                let mut i = patch.corners[c];
                let mut units = 0.0;
                for &(ga, fwd) in &patch.sides[c] {
                    let a = self.farc_of[ga];
                    let arc = &self.graph.arcs[ga];
                    let chain: Vec<u32> = if fwd { arc.chain.clone() } else { arc.chain.iter().rev().copied().collect() };
                    let mut cum = vec![0.0];
                    for w in chain.windows(2) {
                        cum.push(cum.last().unwrap() + self.step(w[0], w[1]));
                    }
                    let len = *cum.last().unwrap();
                    for (k, _) in chain.iter().enumerate() {
                        let f = (units + lengths[a] as f64 * cum[k] / len.max(1e-300)) / total;
                        boundary.insert(outline[i], on_side(n, &poly, c, f));
                        if k + 1 < chain.len() {
                            i = (i + 1) % outline.len();
                        }
                    }
                    units += lengths[a] as f64;
                }
            }
            let dom = tutte(self.m, patch, &boundary);
            domains.insert(p, (dom, boundary));
        }

        let domain_pos = |p: usize, node: Node, dpoints: &[DPoint], boundary: &HashMap<u32, (f64, f64)>| -> (f64, f64) {
            fn go(p: usize, node: Node, me: &Filler, dpoints: &[DPoint], boundary: &HashMap<u32, (f64, f64)>, lengths: &[i64]) -> (f64, f64) {
                match node {
                    Node::Vertex(v) => boundary[&me.outline_local(p, v)],
                    Node::Domain(d) => match &dpoints[d] {
                        DPoint::Center { corners, .. } => {
                            let ps: Vec<(f64, f64)> = corners.iter().map(|&c| go(p, c, me, dpoints, boundary, lengths)).collect();
                            let n = ps.len() as f64;
                            (ps.iter().map(|q| q.0).sum::<f64>() / n, ps.iter().map(|q| q.1).sum::<f64>() / n)
                        }
                        DPoint::Mid { a, b, first, second } => {
                            let (pa, pb) = (go(p, *a, me, dpoints, boundary, lengths), go(p, *b, me, dpoints, boundary, lengths));
                            let f = lengths[*first] as f64 / (lengths[*first] + lengths[*second]).max(1) as f64;
                            (pa.0 + (pb.0 - pa.0) * f, pa.1 + (pb.1 - pa.1) * f)
                        }
                    },
                }
            }
            go(p, node, self, dpoints, boundary, lengths)
        };
        let to_surface = |p: usize, q: (f64, f64), dom: &Domain| -> V3 {
            let patch = &self.graph.patches[p];
            let (t, w) = dom.locate(q);
            let tri = patch.tris[t];
            (0..3).fold(V3::ZERO, |acc, k| acc + self.m.v[patch.verts[tri[k] as usize] as usize] * w[k])
        };

        // Nodes and arcs first, shared by every kite that touches them. A
        // node on a side between two arcs (a T-junction) is no kite's
        // corner, so arc ends make nodes too.
        let template_corners: Vec<Vec<Node>> = self.templates.iter().map(|(p, sides, _)| (0..sides.len()).map(|c| self.node_vertex(*p, c)).collect()).collect();
        let uses: Vec<(usize, &[Node], &[Vec<(usize, bool)>])> = self
            .kites
            .iter()
            .map(|k| (k.patch, &k.corners[..], &k.sides[..]))
            .chain(self.templates.iter().zip(&template_corners).map(|((p, sides, _), c)| (*p, &c[..], &sides[..])))
            .collect();
        for &(patch, corners, sides) in &uses {
            let (dom, boundary) = &domains[&patch];
            let ends: Vec<Node> = corners.iter().copied().chain(sides.iter().flatten().flat_map(|&(a, _)| [self.farcs[a].from, self.farcs[a].to])).collect();
            for c in ends {
                if !node_out.contains_key(&c) {
                    let (pos, fix) = match c {
                        Node::Vertex(x) => (self.m.v[x as usize], self.vertex_fixed(x)),
                        Node::Domain(_) => (to_surface(patch, domain_pos(patch, c, &self.dpoints, boundary), dom), false),
                    };
                    v.push(pos);
                    fixed.push(fix);
                    if matches!(c, Node::Vertex(_)) {
                        on_arcs.push((v.len() - 1) as u32);
                    }
                    node_out.insert(c, (v.len() - 1) as u32);
                }
            }
            for side in sides {
                for &(a, _) in side {
                    if arc_out.contains_key(&a) {
                        continue;
                    }
                    let arc = &self.farcs[a];
                    let n = lengths[a].max(1) as usize;
                    let mut ids = vec![node_out[&arc.from]];
                    match arc.kind {
                        Kind::Surface(ga) => {
                            let g = &self.graph.arcs[ga];
                            // Even steps in local quads, not in length.
                            let mut cum = vec![0.0];
                            for w in g.chain.windows(2) {
                                cum.push(cum.last().unwrap() + self.step(w[0], w[1]));
                            }
                            let len = *cum.last().unwrap();
                            for s in 1..n {
                                let goal = len * s as f64 / n as f64;
                                let j = cum.partition_point(|&c| c < goal).clamp(1, cum.len() - 1);
                                let f = ((goal - cum[j - 1]) / (cum[j] - cum[j - 1]).max(1e-300)).clamp(0.0, 1.0);
                                let (pa, pb) = (self.m.v[g.chain[j - 1] as usize], self.m.v[g.chain[j] as usize]);
                                v.push(pa + (pb - pa) * f);
                                fixed.push(g.feature);
                                on_arcs.push((v.len() - 1) as u32);
                                ids.push((v.len() - 1) as u32);
                            }
                        }
                        Kind::Domain(p) => {
                            let (dom, boundary) = &domains[&p];
                            let (qa, qb) = (domain_pos(p, arc.from, &self.dpoints, boundary), domain_pos(p, arc.to, &self.dpoints, boundary));
                            for s in 1..n {
                                let f = s as f64 / n as f64;
                                v.push(to_surface(p, (qa.0 + (qb.0 - qa.0) * f, qa.1 + (qb.1 - qa.1) * f), dom));
                                fixed.push(false);
                                ids.push((v.len() - 1) as u32);
                            }
                        }
                    }
                    ids.push(node_out[&arc.to]);
                    arc_out.insert(a, ids);
                }
            }
        }

        // The grids.
        for k in &self.kites {
            if k.sides.iter().any(|s| s.is_empty()) {
                continue;
            }
            let (dom, boundary) = &domains[&k.patch];
            let side_ids = |s: usize| -> Vec<u32> {
                let mut ids = Vec::new();
                for (i, &(a, fwd)) in k.sides[s].iter().enumerate() {
                    let arc = &arc_out[&a];
                    let seq: Vec<u32> = if fwd { arc.clone() } else { arc.iter().rev().copied().collect() };
                    ids.extend(if i == 0 { seq } else { seq[1..].to_vec() });
                }
                ids
            };
            let (s0, s1, s2, s3) = (side_ids(0), side_ids(1), side_ids(2), side_ids(3));
            let (a, b) = (s0.len() - 1, s1.len() - 1);
            if s2.len() - 1 != a || s3.len() - 1 != b {
                // The quantizer could not make this kite's sides agree; it
                // stays a hole rather than a torn grid.
                continue;
            }
            let q: [(f64, f64); 4] = if k.whole {
                let poly = polygon(4, &[a as f64, b as f64]);
                [poly[0], poly[1], poly[2], poly[3]]
            } else {
                k.corners.map(|c| domain_pos(k.patch, c, &self.dpoints, boundary))
            };
            let mut grid = vec![vec![u32::MAX; b + 1]; a + 1];
            for i in 0..=a {
                for j in 0..=b {
                    let id = if j == 0 {
                        s0[i]
                    } else if i == a {
                        s1[j]
                    } else if j == b {
                        s2[a - i]
                    } else if i == 0 {
                        s3[b - j]
                    } else {
                        let (u, w) = (i as f64 / a as f64, j as f64 / b as f64);
                        let x = q[0].0 * (1.0 - u) * (1.0 - w) + q[1].0 * u * (1.0 - w) + q[2].0 * u * w + q[3].0 * (1.0 - u) * w;
                        let y = q[0].1 * (1.0 - u) * (1.0 - w) + q[1].1 * u * (1.0 - w) + q[2].1 * u * w + q[3].1 * (1.0 - u) * w;
                        v.push(to_surface(k.patch, (x, y), dom));
                        fixed.push(false);
                        (v.len() - 1) as u32
                    };
                    grid[i][j] = id;
                }
            }
            for i in 0..a {
                for j in 0..b {
                    let f = vec![grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]];
                    if f[0] == f[1] || f[1] == f[2] || f[2] == f[3] || f[3] == f[0] || f[0] == f[2] || f[1] == f[3] {
                        continue;
                    }
                    faces.push(f);
                }
            }
        }
        // Patterns: boundary vertices are the arcs' own, the rest lifted
        // from the domain.
        for (p, sides, t) in &self.templates {
            let (dom, _) = &domains[p];
            let mut out: Vec<u32> = vec![u32::MAX; t.pos.len()];
            for (i, side) in sides.iter().enumerate() {
                let mut ids: Vec<u32> = Vec::new();
                for (j, &(a, fwd)) in side.iter().enumerate() {
                    let arc = &arc_out[&a];
                    let seq: Vec<u32> = if fwd { arc.clone() } else { arc.iter().rev().copied().collect() };
                    ids.extend(if j == 0 { seq } else { seq[1..].to_vec() });
                }
                for (k, &tv) in t.sides[i].iter().enumerate() {
                    out[tv] = ids[k];
                }
            }
            for (tv, id) in out.iter_mut().enumerate() {
                if *id == u32::MAX {
                    v.push(to_surface(*p, t.pos[tv], dom));
                    fixed.push(false);
                    *id = (v.len() - 1) as u32;
                }
            }
            for f in &t.faces {
                faces.push(f.iter().map(|&x| out[x]).collect());
            }
        }
        let mut border = vec![false; v.len()];
        for i in on_arcs {
            border[i as usize] = true;
        }
        Output { v, faces, fixed, border, unfilled: self.unfilled, quantize_violations: 0, kites: self.kites.len() + self.templates.len(), arcs: self.farcs.len() }
    }

    /// Whether a refined vertex lies on a feature or boundary arc.
    /// The mesh edge a → b in local quads.
    fn step(&self, a: u32, b: u32) -> f64 {
        (self.m.v[b as usize] - self.m.v[a as usize]).norm() / (0.5 * (self.size[a as usize] + self.size[b as usize]))
    }

    fn vertex_fixed(&self, x: u32) -> bool {
        self.graph.arcs.iter().any(|a| a.feature && (a.a == x || a.b == x))
    }
}

/// The patch's triangles laid flat: boundary as given, interior by the
/// weighted average of neighbours (cotangent weights, clamped positive so
/// the embedding stays one-to-one), solved by conjugate gradients.
fn tutte(m: &TriMesh, patch: &crate::patches::Patch, boundary: &HashMap<u32, (f64, f64)>) -> Domain {
    let n = patch.verts.len();
    let pos = |l: u32| m.v[patch.verts[l as usize] as usize];
    let mut w: Vec<HashMap<u32, f64>> = vec![HashMap::new(); n];
    for tri in &patch.tris {
        for k in 0..3 {
            let (a, b, c) = (tri[k], tri[(k + 1) % 3], tri[(k + 2) % 3]);
            // Edge a–b, opposite corner c.
            let (pa, pb, pc) = (pos(a), pos(b), pos(c));
            let (u, vv) = (pa - pc, pb - pc);
            let cot = u.dot(vv) / u.cross(vv).norm().max(1e-12);
            let cot = cot.clamp(-0.9, 20.0);
            *w[a as usize].entry(b).or_default() += cot;
            *w[b as usize].entry(a).or_default() += cot;
        }
    }
    for row in w.iter_mut() {
        for x in row.values_mut() {
            *x = x.max(0.05);
        }
    }
    let is_fixed: Vec<bool> = (0..n as u32).map(|l| boundary.contains_key(&l)).collect();
    let mut uv: Vec<(f64, f64)> = (0..n as u32).map(|l| boundary.get(&l).copied().unwrap_or((0.0, 0.0))).collect();
    // Start the interior at the boundary's centre.
    let (cx, cy) = {
        let (mut sx, mut sy, mut k): (f64, f64, f64) = (0.0, 0.0, 0.0);
        for q in boundary.values() {
            sx += q.0;
            sy += q.1;
            k += 1.0;
        }
        (sx / k.max(1.0), sy / k.max(1.0))
    };
    for l in 0..n {
        if !is_fixed[l] {
            uv[l] = (cx, cy);
        }
    }
    for axis in 0..2 {
        let get = |q: (f64, f64)| if axis == 0 { q.0 } else { q.1 };
        let mut x: Vec<f64> = uv.iter().map(|&q| get(q)).collect();
        // (L x)_i = Σ w_ij (x_i − x_j) over free i; fixed j go to the rhs.
        let apply = |x: &[f64], y: &mut [f64]| {
            for i in 0..n {
                if is_fixed[i] {
                    y[i] = 0.0;
                    continue;
                }
                let mut acc = 0.0;
                for (&j, &wij) in &w[i] {
                    acc += wij * (x[i] - if is_fixed[j as usize] { 0.0 } else { x[j as usize] });
                }
                y[i] = acc;
            }
        };
        let mut b = vec![0.0; n];
        for i in 0..n {
            if is_fixed[i] {
                continue;
            }
            for (&j, &wij) in &w[i] {
                if is_fixed[j as usize] {
                    b[i] += wij * x[j as usize];
                }
            }
        }
        for i in 0..n {
            if is_fixed[i] {
                x[i] = 0.0;
            }
        }
        let diag: Vec<f64> = (0..n).map(|i| w[i].values().sum::<f64>().max(1e-12)).collect();
        let mut ax = vec![0.0; n];
        apply(&x, &mut ax);
        let mut r: Vec<f64> = (0..n).map(|i| b[i] - ax[i]).collect();
        let mut z: Vec<f64> = (0..n).map(|i| r[i] / diag[i]).collect();
        let mut p = z.clone();
        let mut rz: f64 = r.iter().zip(&z).map(|(a, b)| a * b).sum();
        let bn = b.iter().map(|v| v * v).sum::<f64>().sqrt().max(1e-300);
        let mut ap = vec![0.0; n];
        let mut its = 0;
        for _ in 0..4000 {
            its += 1;
            if r.iter().map(|v| v * v).sum::<f64>().sqrt() < 1e-10 * bn {
                break;
            }
            apply(&p, &mut ap);
            let pap: f64 = p.iter().zip(&ap).map(|(a, b)| a * b).sum();
            if pap.abs() < 1e-300 {
                break;
            }
            let alpha = rz / pap;
            for i in 0..n {
                x[i] += alpha * p[i];
                r[i] -= alpha * ap[i];
                z[i] = r[i] / diag[i];
            }
            let rz2: f64 = r.iter().zip(&z).map(|(a, b)| a * b).sum();
            let beta = rz2 / rz;
            rz = rz2;
            for i in 0..n {
                p[i] = z[i] + beta * p[i];
            }
        }
        if std::env::var("QREMESH_DEBUG").is_ok() {
            let big = x.iter().fold(0.0f64, |a, v| a.max(v.abs()));
            eprintln!("    tutte axis {axis}: {its} iterations, residual {:.2e}, max {big:.3}", r.iter().map(|v| v * v).sum::<f64>().sqrt() / bn);
        }
        for i in 0..n {
            if !is_fixed[i] {
                if axis == 0 {
                    uv[i].0 = x[i];
                } else {
                    uv[i].1 = x[i];
                }
            }
        }
    }
    Domain::new(uv, patch.tris.clone())
}

/// Laplacian smoothing along the surface, with reprojection onto the
/// input, features and the boundary held still. Only the tangential part of
/// each move is taken: the plain Laplacian also pulls every vertex toward
/// the inside of the curve it sits on, which on a limb a few quads round
/// collapses the limb, and the closest point of the input then lies on the
/// body instead.
pub fn smooth(out: &mut Output, sizing: &crate::sizing::Sizing, rounds: usize) {
    let n = out.v.len();
    let mut adj: Vec<Vec<u32>> = vec![Vec::new(); n];
    for f in &out.faces {
        for k in 0..f.len() {
            let (a, b) = (f[k], f[(k + 1) % f.len()]);
            adj[a as usize].push(b);
            adj[b as usize].push(a);
        }
    }
    for list in adj.iter_mut() {
        list.sort_unstable();
        list.dedup();
    }
    // Vertex normals from the faces round each vertex.
    let normals = |out: &Output| -> Vec<V3> {
        let mut normal = vec![V3::ZERO; n];
        for f in &out.faces {
            for k in 0..f.len() {
                let (a, b, c) = (f[(k + f.len() - 1) % f.len()] as usize, f[k] as usize, f[(k + 1) % f.len()] as usize);
                normal[b] += (out.v[c] - out.v[b]).cross(out.v[a] - out.v[b]);
            }
        }
        normal
    };
    // Where vertex `i` goes: toward its neighbours' mean, along the surface
    // only. Neighbours pull by one over the wanted edge between them: at
    // rest every edge is then as long as the quad size there asks, where
    // plain averaging would even a graded mesh out.
    let pull = |out: &Output, normal: &[V3], size: &[f64], i: usize| -> V3 {
        let (mut sum, mut weight) = (V3::ZERO, 0.0);
        for &j in &adj[i] {
            let w = 1.0 / (size[i] + size[j as usize]);
            sum += out.v[j as usize] * w;
            weight += w;
        }
        (sum / weight - out.v[i]).project_tangent(normal[i].normalized())
    };

    // First each patch's inside, its border held where the layout put it,
    // until it is at rest. A patch comes off its flat domain badly spread:
    // a strip thirty quads long with two singularities is laid out through
    // a hexagon, rows crushed into a band, and the gentle rounds below
    // never even that out. With the border held this has one answer (the
    // patch's quads spread between its sides), so it can be run to the end,
    // each vertex moving at once and the next seeing it there, each move
    // taken 1.7 times over (successive over-relaxation: rounds by a patch's
    // length in quads, not by its square).
    //
    // Not where the quads are too coarse for the surface (a tail one quad
    // round): averaging there is not along the surface any more, the ring
    // shrinks, and run to the end the tail is gone. Those vertices stay.
    if rounds > 0 {
        let held: Vec<bool> = (0..n).map(|i| out.fixed[i] || out.border[i] || adj[i].is_empty() || sizing.coarse(out.v[i])).collect();
        let mut size: Vec<f64> = Vec::new();
        for round in 0..400 {
            let normal = normals(out);
            if round % 10 == 0 {
                size = out.v.iter().map(|&p| sizing.at(p)).collect();
            }
            let mut moved: f64 = 0.0;
            for i in 0..n {
                if held[i] {
                    continue;
                }
                let step = pull(out, &normal, &size, i);
                moved = moved.max(step.norm() / size[i]);
                out.v[i] = sizing.closest(out.v[i] + step * 1.7).0;
            }
            if moved < 0.01 {
                break;
            }
        }
    }
    // Then everything but features, a set number of gentle rounds: enough
    // to ease the borders' zigzag and the kinks across them, not enough
    // for anything to travel.
    for _ in 0..rounds {
        let normal = normals(out);
        let size: Vec<f64> = out.v.iter().map(|&p| sizing.at(p)).collect();
        let mut next = out.v.clone();
        for i in 0..n {
            if out.fixed[i] || adj[i].is_empty() {
                continue;
            }
            next[i] = sizing.closest(out.v[i] + pull(out, &normal, &size, i) * 0.5).0;
        }
        out.v = next;
    }
}

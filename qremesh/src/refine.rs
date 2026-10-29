//! Cutting the traces into the mesh.
//!
//! A trace is a polyline across triangles. For everything after the layout
//! — regions, their corners, their sides, their parametrization — it is far
//! simpler if each trace is a chain of mesh edges, so that a region is
//! exactly a set of triangles and its outline exactly a trace. So every
//! trace point becomes a vertex (splitting the edge or triangle it sits on)
//! and every segment between consecutive points becomes a chain of edges
//! (splitting whatever edges it crosses). Points close to an existing
//! vertex or edge snap to it, so nothing degenerate is made.
//!
//! All the work is done in each original triangle's own plane: the pieces
//! of a triangle stay in that plane, so the geometry is two-dimensional and
//! points on a shared edge agree from both sides by construction.

use crate::math::V3;
use crate::mesh::TriMesh;
use crate::trace::Stop;
use std::collections::{HashMap, HashSet};

/// What a refined vertex is, in terms of the original mesh.
#[derive(Clone, Copy, Debug)]
pub enum Where {
    Original,
    /// On the original edge `a`→`b` (a < b), `t` of the way along it.
    OnEdge { a: u32, b: u32, t: f64 },
    /// Inside original triangle `tri`, at these barycentric coordinates.
    InTri { tri: u32, bary: [f64; 3] },
}

pub struct Refined {
    pub m: TriMesh,
    /// Edges of `m` that are cuts: trace chains, sharp features, the
    /// surface's own boundary.
    pub cut: HashSet<(u32, u32)>,
    /// The cuts that are features or boundary rather than traces.
    pub feature: HashSet<(u32, u32)>,
    /// The original triangle each refined triangle is a piece of.
    pub origin: Vec<u32>,
    pub whence: Vec<Where>,
    /// Trace segments that crossed an existing cut: a layout fault, counted
    /// rather than hidden (the crossing becomes a four-way node).
    pub crossings: usize,
}

/// A triangle's plane, as a 2D frame.
struct Frame {
    o: V3,
    u: V3,
    v: V3,
}

impl Frame {
    fn flat(&self, p: V3) -> (f64, f64) {
        let d = p - self.o;
        (d.dot(self.u), d.dot(self.v))
    }
}

struct Builder<'a> {
    m: &'a TriMesh,
    frames: Vec<Frame>,
    /// Per original triangle, its pieces (global vertex ids, same winding).
    subs: Vec<Vec<[u32; 3]>>,
    edge_tris: HashMap<(u32, u32), Vec<u32>>,
    /// Vertices on each original edge, (t, vertex), sorted by t, with the
    /// endpoints at 0 and 1.
    edge_pts: HashMap<(u32, u32), Vec<(f64, u32)>>,
    pos: Vec<V3>,
    whence: Vec<Where>,
    cut: HashSet<(u32, u32)>,
    feature: HashSet<(u32, u32)>,
    /// Snapping distance.
    eps: f64,
    crossings: usize,
}

fn key(a: u32, b: u32) -> (u32, u32) {
    (a.min(b), a.max(b))
}

fn cross2(a: (f64, f64), b: (f64, f64)) -> f64 {
    a.0 * b.1 - a.1 * b.0
}

fn sub2(a: (f64, f64), b: (f64, f64)) -> (f64, f64) {
    (a.0 - b.0, a.1 - b.1)
}

fn len2(a: (f64, f64)) -> f64 {
    (a.0 * a.0 + a.1 * a.1).sqrt()
}

impl<'a> Builder<'a> {
    /// Where vertex `v` sits in original triangle `t`'s frame. Only asked
    /// for vertices that are on or in `t`.
    fn local(&self, t: usize, v: u32) -> (f64, f64) {
        let tri = self.m.f[t];
        let corner = |i: u32| self.frames[t].flat(self.m.v[i as usize]);
        match self.whence[v as usize] {
            Where::Original => corner(v),
            Where::OnEdge { a, b, t: s } => {
                let (pa, pb) = (corner(a), corner(b));
                (pa.0 + (pb.0 - pa.0) * s, pa.1 + (pb.1 - pa.1) * s)
            }
            Where::InTri { tri: owner, bary } => {
                debug_assert_eq!(owner as usize, t);
                let c = tri.map(corner);
                (
                    c[0].0 * bary[0] + c[1].0 * bary[1] + c[2].0 * bary[2],
                    c[0].1 * bary[0] + c[1].1 * bary[1] + c[2].1 * bary[2],
                )
            }
        }
    }

    fn bary(&self, t: usize, p: (f64, f64)) -> [f64; 3] {
        let c = self.m.f[t].map(|i| self.frames[t].flat(self.m.v[i as usize]));
        let area = cross2(sub2(c[1], c[0]), sub2(c[2], c[0]));
        let w0 = cross2(sub2(c[1], p), sub2(c[2], p)) / area;
        let w1 = cross2(sub2(c[2], p), sub2(c[0], p)) / area;
        [w0, w1, 1.0 - w0 - w1]
    }

    fn new_vertex(&mut self, p: V3, w: Where) -> u32 {
        self.pos.push(p);
        self.whence.push(w);
        (self.pos.len() - 1) as u32
    }

    /// Split edge `p`–`q` of the pieces of original triangle `t` at the
    /// existing vertex `x`. A cut edge stays cut in both halves.
    fn split_edge_in(&mut self, t: usize, p: u32, q: u32, x: u32) {
        let mut found = false;
        let n = self.subs[t].len();
        for i in 0..n {
            let tri = self.subs[t][i];
            for k in 0..3 {
                let (a, b) = (tri[k], tri[(k + 1) % 3]);
                if key(a, b) == key(p, q) {
                    let c = tri[(k + 2) % 3];
                    self.subs[t][i] = [a, x, c];
                    self.subs[t].push([x, b, c]);
                    found = true;
                    break;
                }
            }
        }
        debug_assert!(found, "edge to split not found");
        if self.cut.remove(&key(p, q)) {
            self.cut.insert(key(p, x));
            self.cut.insert(key(x, q));
        }
        if self.feature.remove(&key(p, q)) {
            self.feature.insert(key(p, x));
            self.feature.insert(key(x, q));
        }
    }

    /// The vertex on original edge `a`–`b` at `t`, made if there is none
    /// close enough.
    fn on_edge(&mut self, a: u32, b: u32, t: f64) -> u32 {
        let (a, b) = (a.min(b), a.max(b));
        let length = (self.m.v[b as usize] - self.m.v[a as usize]).norm();
        let tol = self.eps / length.max(1e-300);
        let pts = self.edge_pts.get(&(a, b)).expect("edge").clone();
        if let Some(&(_, v)) = pts.iter().find(|&&(s, _)| (s - t).abs() < tol) {
            return v;
        }
        let k = pts.partition_point(|&(s, _)| s < t);
        let (p, q) = (pts[k - 1].1, pts[k].1);
        let pos = self.m.v[a as usize] + (self.m.v[b as usize] - self.m.v[a as usize]) * t;
        let x = self.new_vertex(pos, Where::OnEdge { a, b, t });
        for tri in self.edge_tris[&(a, b)].clone() {
            self.split_edge_in(tri as usize, p, q, x);
        }
        self.edge_pts.get_mut(&(a, b)).unwrap().insert(k, (t, x));
        x
    }

    /// A vertex at the point `p` (in `t`'s frame) inside original triangle
    /// `t`: an existing one close enough, else made by splitting the edge
    /// it is close to, else the piece it is in.
    fn inside(&mut self, t: usize, p: (f64, f64)) -> u32 {
        let eps = self.eps;
        // The nearest vertex, the nearest cut edge and the nearest edge of
        // any kind. A point meant to sit on a trace (where another trace
        // ended on it) must land on that chain, so a cut edge within reach
        // wins over a mesh vertex that happens to be as close.
        let mut vertex: Option<(f64, u32)> = None;
        let mut seen: HashSet<u32> = HashSet::new();
        let mut edge: Option<(f64, u32, u32, f64)> = None;
        let mut cut_edge: Option<(f64, u32, u32, f64)> = None;
        for tri in &self.subs[t] {
            for k in 0..3 {
                let (a, b) = (tri[k], tri[(k + 1) % 3]);
                let (pa, pb) = (self.local(t, a), self.local(t, b));
                if seen.insert(a) {
                    let d = len2(sub2(pa, p));
                    if vertex.map_or(true, |(bd, _)| d < bd) {
                        vertex = Some((d, a));
                    }
                }
                let ab = sub2(pb, pa);
                let s = ((p.0 - pa.0) * ab.0 + (p.1 - pa.1) * ab.1) / (ab.0 * ab.0 + ab.1 * ab.1).max(1e-300);
                let s = s.clamp(0.0, 1.0);
                let foot = (pa.0 + ab.0 * s, pa.1 + ab.1 * s);
                let d = len2(sub2(foot, p));
                if edge.map_or(true, |(nd, _, _, _)| d < nd) {
                    edge = Some((d, a, b, s));
                }
                if self.cut.contains(&key(a, b)) && cut_edge.map_or(true, |(nd, _, _, _)| d < nd) {
                    cut_edge = Some((d, a, b, s));
                }
            }
        }
        let on_edge = match (cut_edge, vertex, edge) {
            (Some(c), _, _) if c.0 < eps => Some(c),
            (_, Some((d, v)), _) if d < eps => return v,
            (_, _, Some(e)) if e.0 < eps => Some(e),
            _ => None,
        };
        if let Some((_, a, b, s)) = on_edge {
            let (pa, pb) = (self.local(t, a), self.local(t, b));
            let e = sub2(pb, pa);
            let tol = eps / len2(e).max(1e-300);
            if s < tol {
                return a;
            }
            if s > 1.0 - tol {
                return b;
            }
            // On the triangle's own boundary: a point of the original
            // edge, shared with the neighbour.
            if let Some(((ea, eb), ta, tb)) = self.original_edge_of(t, a, b) {
                return self.on_edge(ea, eb, ta + (tb - ta) * s);
            }
            let foot = (pa.0 + e.0 * s, pa.1 + e.1 * s);
            let bary = self.bary(t, foot);
            let pos = self.unflat(t, bary);
            let x = self.new_vertex(pos, Where::InTri { tri: t as u32, bary });
            self.split_edge_in(t, a, b, x);
            return x;
        }
        // Inside a piece.
        let mut which: Option<(f64, usize)> = None;
        for (i, tri) in self.subs[t].iter().enumerate() {
            let c = tri.map(|v| self.local(t, v));
            let area = cross2(sub2(c[1], c[0]), sub2(c[2], c[0])).max(1e-300);
            let w = [
                cross2(sub2(c[1], p), sub2(c[2], p)) / area,
                cross2(sub2(c[2], p), sub2(c[0], p)) / area,
                cross2(sub2(c[0], p), sub2(c[1], p)) / area,
            ];
            let worst = w[0].min(w[1]).min(w[2]);
            if which.map_or(true, |(bw, _)| worst > bw) {
                which = Some((worst, i));
            }
        }
        let (_, i) = which.expect("a triangle has pieces");
        let bary = self.bary(t, p);
        let pos = self.unflat(t, bary);
        let x = self.new_vertex(pos, Where::InTri { tri: t as u32, bary });
        let [a, b, c] = self.subs[t][i];
        self.subs[t][i] = [a, b, x];
        self.subs[t].push([b, c, x]);
        self.subs[t].push([c, a, x]);
        x
    }

    fn unflat(&self, t: usize, bary: [f64; 3]) -> V3 {
        let c = self.m.f[t].map(|i| self.m.v[i as usize]);
        c[0] * bary[0] + c[1] * bary[1] + c[2] * bary[2]
    }

    /// If piece edge `a`–`b` of triangle `t` lies on one of `t`'s original
    /// edges: that edge and where along it `a` and `b` sit.
    fn original_edge_of(&self, t: usize, a: u32, b: u32) -> Option<((u32, u32), f64, f64)> {
        let along = |v: u32, ea: u32, eb: u32| -> Option<f64> {
            match self.whence[v as usize] {
                Where::Original if v == ea => Some(0.0),
                Where::Original if v == eb => Some(1.0),
                Where::OnEdge { a: x, b: y, t: s } if (x, y) == (ea, eb) => Some(s),
                _ => None,
            }
        };
        let tri = self.m.f[t];
        for k in 0..3 {
            let (ea, eb) = key(tri[k], tri[(k + 1) % 3]);
            if let (Some(ta), Some(tb)) = (along(a, ea, eb), along(b, ea, eb)) {
                return Some(((ea, eb), ta, tb));
            }
        }
        None
    }

    /// Join vertices `a` and `b`, both on or in original triangle `t`, by a
    /// straight chain of cut edges, splitting the piece edges it crosses.
    fn walk(&mut self, t: usize, mut a: u32, b: u32) {
        let pb = self.local(t, b);
        let mut guard = 0;
        while a != b {
            guard += 1;
            if guard > 10_000 {
                eprintln!("refine: walk did not converge");
                return;
            }
            let pa = self.local(t, a);
            let dir = sub2(pb, pa);
            // The piece around `a` whose wedge holds the direction to `b`.
            let mut best: Option<(f64, u32, u32)> = None;
            for tri in &self.subs[t] {
                let Some(k) = (0..3).find(|&k| tri[k] == a) else { continue };
                let (p, q) = (tri[(k + 1) % 3], tri[(k + 2) % 3]);
                let (pp, pq) = (self.local(t, p), self.local(t, q));
                let left = cross2(sub2(pp, pa), dir) / (len2(sub2(pp, pa)) * len2(dir)).max(1e-300);
                let right = cross2(dir, sub2(pq, pa)) / (len2(sub2(pq, pa)) * len2(dir)).max(1e-300);
                let score = left.min(right);
                if best.map_or(true, |(s, _, _)| score > s) {
                    best = Some((score, p, q));
                }
            }
            let Some((_, p, q)) = best else {
                eprintln!("refine: vertex without pieces");
                return;
            };
            if p == b || q == b {
                self.cut.insert(key(a, b));
                a = b;
                continue;
            }
            // Where the ray leaves the piece through p–q.
            let (pp, pq) = (self.local(t, p), self.local(t, q));
            let e = sub2(pq, pp);
            let den = cross2(dir, e);
            let w = sub2(pp, pa);
            let u = if den.abs() < 1e-300 { 0.5 } else { cross2(w, dir) / den };
            let s = if den.abs() < 1e-300 { 1.0 } else { cross2(w, e) / den };
            let tol = self.eps / len2(e).max(1e-300);
            // `b` closer than the crossing: `b` is in this piece after all
            // (it would have split it, so this is a rounding case).
            if s >= 1.0 - 1e-9 {
                let x = self.inside(t, pb);
                if x != b {
                    self.cut.insert(key(a, x));
                    a = x;
                    continue;
                }
                self.cut.insert(key(a, b));
                a = b;
                continue;
            }
            let next = if u < tol {
                p
            } else if u > 1.0 - tol {
                q
            } else {
                if self.cut.contains(&key(p, q)) {
                    self.crossings += 1;
                }
                let foot = (pp.0 + e.0 * u, pp.1 + e.1 * u);
                let x = if let Some(((ea, eb), ta, tb)) = self.original_edge_of(t, p, q) {
                    self.on_edge(ea, eb, ta + (tb - ta) * u)
                } else {
                    let bary = self.bary(t, foot);
                    let pos = self.unflat(t, bary);
                    let x = self.new_vertex(pos, Where::InTri { tri: t as u32, bary });
                    self.split_edge_in(t, p, q, x);
                    x
                };
                x
            };
            self.cut.insert(key(a, next));
            a = next;
        }
    }
}

/// Cut `traces` (each a polyline with a stop per point) and `features`
/// into `m`. `eps` is the snapping distance, a small fraction of an edge.
pub fn insert(m: &TriMesh, features: &[(u32, u32)], traces: &[(&[V3], &[Stop])], eps: f64) -> Refined {
    let frames: Vec<Frame> = m
        .f
        .iter()
        .map(|t| {
            let (p0, p1, p2) = (m.v[t[0] as usize], m.v[t[1] as usize], m.v[t[2] as usize]);
            let u = (p1 - p0).normalized();
            let n = (p1 - p0).cross(p2 - p0).normalized();
            Frame { o: p0, u, v: n.cross(u) }
        })
        .collect();
    let mut edge_tris: HashMap<(u32, u32), Vec<u32>> = HashMap::new();
    for (t, tri) in m.f.iter().enumerate() {
        for k in 0..3 {
            edge_tris.entry(key(tri[k], tri[(k + 1) % 3])).or_default().push(t as u32);
        }
    }
    let edge_pts = edge_tris.keys().map(|&(a, b)| ((a, b), vec![(0.0, a), (1.0, b)])).collect();
    let mut cut: HashSet<(u32, u32)> = features.iter().map(|&(a, b)| key(a, b)).collect();
    // The surface's own boundary is a cut like any feature.
    cut.extend(edge_tris.iter().filter(|(_, ts)| ts.len() == 1).map(|(&e, _)| e));
    let mut b = Builder {
        m,
        frames,
        subs: m.f.iter().map(|&t| vec![t]).collect(),
        edge_tris,
        edge_pts,
        pos: m.v.clone(),
        whence: vec![Where::Original; m.v.len()],
        feature: cut.clone(),
        cut,
        eps,
        crossings: 0,
    };

    for &(points, stops) in traces {
        // Every point first becomes a vertex, so that where traces meet,
        // the meeting point is already there to be walked into.
        let verts: Vec<u32> = points
            .iter()
            .zip(stops)
            .map(|(&p, stop)| match stop.edge {
                Some((ea, eb)) => {
                    let (pa, pb) = (m.v[ea as usize], m.v[eb as usize]);
                    let t = ((p - pa).dot(pb - pa) / (pb - pa).norm2().max(1e-300)).clamp(0.0, 1.0);
                    b.on_edge(ea, eb, t)
                }
                None => {
                    let t = stop.tri as usize;
                    let flat = b.frames[t].flat(p);
                    b.inside(t, flat)
                }
            })
            .collect();
        for i in 0..verts.len().saturating_sub(1) {
            if verts[i] == verts[i + 1] {
                continue;
            }
            // Both points sit on or in the triangle the second was made in.
            b.walk(stops[i + 1].tri as usize, verts[i], verts[i + 1]);
        }
    }

    let mut f = Vec::new();
    let mut origin = Vec::new();
    for (t, pieces) in b.subs.iter().enumerate() {
        for &piece in pieces {
            f.push(piece);
            origin.push(t as u32);
        }
    }
    Refined { m: TriMesh { v: b.pos, f }, cut: b.cut, feature: b.feature, origin, whence: b.whence, crossings: b.crossings }
}

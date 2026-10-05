//! From singularities to patches: separatrices traced across the surface
//! along the cross field, grown together until they hit each other, a
//! singularity or a sharp edge — a motorcycle graph — and the surface cut
//! along them into regions.
//!
//! In QuadWild this is the stage that turns a field into a layout; here it
//! is the simplest version that can be measured: no choice among candidate
//! traces, no repair of regions that are not disks. The report says how
//! many regions came out and how many of them are disks.

use crate::cplx::C;
use crate::cross::{Singularity, Surface};
use crate::math::V3;
use std::collections::{HashMap, HashSet};
use std::f64::consts::TAU;

pub struct Topology {
    /// Triangles across each edge, keyed by (low, high) vertex.
    pub edge_tris: HashMap<(u32, u32), Vec<u32>>,
}

impl Topology {
    pub fn new(tris: &[[u32; 3]]) -> Topology {
        let mut edge_tris: HashMap<(u32, u32), Vec<u32>> = HashMap::new();
        for (t, tri) in tris.iter().enumerate() {
            for k in 0..3 {
                let (a, b) = (tri[k], tri[(k + 1) % 3]);
                edge_tris.entry((a.min(b), a.max(b))).or_default().push(t as u32);
            }
        }
        Topology { edge_tris }
    }

    fn across(&self, t: u32, a: u32, b: u32) -> Option<u32> {
        self.edge_tris.get(&(a.min(b), a.max(b)))?.iter().copied().find(|&x| x != t)
    }
}

fn tri_normal(s: &Surface, t: usize) -> V3 {
    let [a, b, c] = s.tris[t].map(|x| x as usize);
    (s.p[b] - s.p[a]).cross(s.p[c] - s.p[a]).normalized()
}

/// The field at a point inside triangle `t`, as the arm closest to `d`:
/// each corner's four arms, the one nearest `d` from each, blended by
/// barycentric weight and laid into the triangle's plane.
fn field_dir(s: &Surface, z: &[C], t: usize, x: V3, d: V3) -> V3 {
    let tri = s.tris[t].map(|v| v as usize);
    let nt = tri_normal(s, t);
    let w = barycentric(s, t, x);
    let mut sum = V3::ZERO;
    for (k, &v) in tri.iter().enumerate() {
        let arm = s.arm(v, z[v]);
        let other = s.n[v].cross(arm);
        let mut best = (f64::MIN, arm);
        for c in [arm, other, -arm, -other] {
            let score = c.dot(d);
            if score > best.0 {
                best = (score, c);
            }
        }
        sum += best.1 * w[k].max(0.0);
    }
    let dir = sum.project_tangent(nt).normalized();
    if dir == V3::ZERO { d } else { dir }
}

fn barycentric(s: &Surface, t: usize, x: V3) -> [f64; 3] {
    let [a, b, c] = s.tris[t].map(|v| s.p[v as usize]);
    let (v0, v1, v2) = (b - a, c - a, x - a);
    let (d00, d01, d11, d20, d21) = (v0.dot(v0), v0.dot(v1), v1.dot(v1), v2.dot(v0), v2.dot(v1));
    let den = d00 * d11 - d01 * d01;
    let v = (d11 * d20 - d01 * d21) / den;
    let w = (d00 * d21 - d01 * d20) / den;
    [1.0 - v - w, v, w]
}

pub struct Trace {
    pub points: Vec<V3>,
    tri: u32,
    dir: V3,
    /// Its singularity's index, or `usize::MAX` for a repair trace.
    pub from: usize,
    pub alive: bool,
    /// How it ended: "trace", "self", "singularity", "feature", "boundary", "length".
    pub ended: &'static str,
    travelled: f64,
    /// Distance walked straight before following the field — near a
    /// singularity the field has no direction worth following.
    free: f64,
}

struct Segment {
    trace: usize,
    a: V3,
    b: V3,
    /// How far along its trace the segment starts.
    at: f64,
}

pub struct Layout {
    pub traces: Vec<Trace>,
    /// Region id per triangle.
    pub region: Vec<u32>,
    pub regions: usize,
    pub disks: usize,
    pub region_euler: Vec<i64>,
    /// Rounds of repair traces it took to make every region a disk.
    pub repairs: usize,
}

/// Directions in which an arm of the field points straight away from the
/// singularity — its separatrices.
///
/// Around a singularity of index s (±¼), an arm's angle α in the
/// singularity's plane turns at s times the rate of the angle β around it:
/// α(β) ≈ α₀ + sβ, modulo a quarter turn. So α₀ is fitted once from a ring
/// of samples (a circular mean of 4(α − sβ), which averages the noise near
/// the singularity away), and the separatrices are where the arm and the
/// radius agree: β(1 − s) ≡ α₀ (mod ¼ turn) — three directions 120° apart
/// for +¼, five 72° apart for −¼.
fn separatrix_dirs(s: &Surface, z: &[C], sing: &Singularity, radius: f64, near: &[usize]) -> Vec<V3> {
    let nt = tri_normal(s, sing.tri);
    let u = V3::tangent_of(nt);
    let v = nt.cross(u);
    let index = 0.25 * sing.index.signum() as f64;
    let samples = 120;
    let mut sum = C::ZERO;
    for k in 0..samples {
        let beta = TAU * k as f64 / samples as f64;
        let point = sing.at + (u * beta.cos() + v * beta.sin()) * radius;
        let nearest = *near
            .iter()
            .min_by(|&&a, &&b| (s.p[a] - point).norm2().total_cmp(&(s.p[b] - point).norm2()))
            .unwrap();
        let arm = s.arm(nearest, z[nearest]).project_tangent(nt);
        let alpha = arm.dot(v).atan2(arm.dot(u));
        sum += C::polar(1.0, 4.0 * (alpha - index * beta));
    }
    let alpha0 = sum.arg() / 4.0;
    let count = if index > 0.0 { 3 } else { 5 };
    (0..count)
        .map(|k| {
            let beta = (alpha0 + k as f64 * TAU / 4.0) / (1.0 - index);
            u * beta.cos() + v * beta.sin()
        })
        .collect()
}

struct Tracer<'a> {
    s: &'a Surface,
    z: &'a [C],
    topo: Topology,
    features: HashSet<(u32, u32)>,
    cut: HashSet<(u32, u32)>,
    segments: HashMap<u32, Vec<Segment>>,
    sings: &'a [Singularity],
    traces: Vec<Trace>,
    step: f64,
    max_length: f64,
}

pub fn layout(s: &Surface, z: &[C], sings: &[Singularity], features: &[(u32, u32)], step: f64, max_length: f64) -> Layout {
    let feature_set: HashSet<(u32, u32)> = features.iter().copied().collect();
    let mut tr = Tracer {
        s,
        z,
        topo: Topology::new(&s.tris),
        cut: feature_set.clone(),
        features: feature_set,
        segments: HashMap::new(),
        sings,
        traces: Vec::new(),
        step,
        max_length,
    };

    let ring = |t: usize, depth: usize| -> Vec<usize> {
        let mut seen: HashSet<usize> = s.tris[t].iter().map(|&v| v as usize).collect();
        let mut frontier: Vec<usize> = seen.iter().copied().collect();
        for _ in 0..depth {
            let mut next = Vec::new();
            for &v in &frontier {
                for &j in &s.adj[v] {
                    if seen.insert(j as usize) {
                        next.push(j as usize);
                    }
                }
            }
            frontier = next;
        }
        let mut out: Vec<usize> = seen.into_iter().collect();
        out.sort_unstable();
        out
    };

    let free = step * 6.0;
    for (k, sing) in sings.iter().enumerate() {
        let near = ring(sing.tri, 8);
        for dir in separatrix_dirs(s, z, sing, free, &near) {
            // Separatrices that run along a sharp edge are that edge.
            let along_feature = s.tris[sing.tri].iter().any(|&a| {
                s.adj[a as usize].iter().any(|&b| {
                    tr.features.contains(&(a.min(b), a.max(b)))
                        && (s.p[b as usize] - s.p[a as usize]).normalized().dot(dir) > 0.9
                })
            });
            if !along_feature {
                tr.start(sing.at, sing.tri as u32, dir, k, free);
            }
        }
    }
    tr.run();

    // Regions that are not disks — a torus has no singularities at all, so
    // no separatrices — get a cross of field lines from their middle, the
    // way QuadWild adds traces until every patch is a disk.
    let mut repairs = 0;
    let (mut region, mut regions, mut euler) = tr.regions();
    while repairs < 12 {
        let bad: Vec<u32> = (0..regions as u32).filter(|&r| euler[r as usize] != 1).collect();
        if bad.is_empty() {
            break;
        }
        for r in bad {
            if let Some(t) = tr.deepest(&region, r) {
                let [a, b, c] = s.tris[t].map(|v| s.p[v as usize]);
                let centre = (a + b + c) / 3.0;
                let v0 = s.tris[t][0] as usize;
                let arm = s.arm(v0, z[v0]);
                let other = s.n[v0].cross(arm);
                for d in [arm, other, -arm, -other] {
                    tr.start(centre, t as u32, d, usize::MAX, 0.0);
                }
            }
        }
        tr.run();
        (region, regions, euler) = tr.regions();
        repairs += 1;
    }

    let disks = euler.iter().filter(|&&e| e == 1).count();
    Layout { traces: tr.traces, region, regions, disks, region_euler: euler, repairs }
}

impl<'a> Tracer<'a> {
    fn start(&mut self, at: V3, tri: u32, dir: V3, from: usize, free: f64) {
        self.traces.push(Trace {
            points: vec![at],
            tri,
            dir,
            from,
            alive: true,
            ended: "",
            travelled: 0.0,
            free,
        });
    }

    /// Grow every live trace a step at a time, all together, so who stops
    /// whom does not depend on the order they were started in.
    fn run(&mut self) {
        loop {
            let live: Vec<usize> = (0..self.traces.len()).filter(|&i| self.traces[i].alive).collect();
            if live.is_empty() {
                break;
            }
            for id in live {
                self.advance(id);
            }
        }
    }

    fn stop(&mut self, id: usize, why: &'static str) {
        self.traces[id].alive = false;
        self.traces[id].ended = why;
    }

    fn advance(&mut self, id: usize) {
        let s = self.s;
        let mut remaining = self.step;
        while remaining > 1e-12 {
            let t = self.traces[id].tri as usize;
            let x = *self.traces[id].points.last().unwrap();
            let nt = tri_normal(s, t);
            let mut d = self.traces[id].dir.project_tangent(nt).normalized();
            if self.traces[id].travelled >= self.traces[id].free {
                d = field_dir(s, self.z, t, x, d);
            }
            self.traces[id].dir = d;

            // Where the ray leaves the triangle.
            let tri = s.tris[t];
            let mut exit: Option<(f64, u32, u32)> = None;
            for k in 0..3 {
                let (a, b) = (tri[k], tri[(k + 1) % 3]);
                let (pa, pb) = (s.p[a as usize], s.p[b as usize]);
                let e = pb - pa;
                let m = d.cross(e).dot(nt);
                if m.abs() < 1e-14 {
                    continue;
                }
                let w = pa - x;
                let sd = w.cross(e).dot(nt) / m;
                let u = w.cross(d).dot(nt) / m;
                if sd > 1e-10 && (-1e-9..=1.0 + 1e-9).contains(&u) && exit.map_or(true, |(best, _, _)| sd < best) {
                    exit = Some((sd, a, b));
                }
            }
            let Some((to_edge, a, b)) = exit else {
                self.stop(id, "boundary");
                return;
            };
            let length = to_edge.min(remaining);
            let next = x + d * length;
            let travelled = self.traces[id].travelled;

            if let Some((hit, own)) = self.crossing(t as u32, id, x, next, nt) {
                self.traces[id].points.push(hit);
                self.stop(id, if own { "self" } else { "trace" });
                return;
            }
            let segment = Segment { trace: id, a: x, b: next, at: travelled };
            // A singularity other than our own start, close by: end on it.
            let from = self.traces[id].from;
            let snap = self.sings.iter().enumerate().find(|(k, sing)| {
                (*k != from || travelled > self.traces[id].free * 2.0) && (sing.at - next).norm() < self.step * 1.5
            });
            if let Some((_, sing)) = snap {
                let at = sing.at;
                self.segments.entry(t as u32).or_default().push(segment);
                self.traces[id].points.push(at);
                self.stop(id, "singularity");
                return;
            }
            self.segments.entry(t as u32).or_default().push(segment);
            self.traces[id].points.push(next);
            self.traces[id].travelled += length;
            remaining -= length;
            if self.traces[id].travelled > self.max_length {
                self.stop(id, "length");
                return;
            }
            if length < to_edge {
                continue;
            }
            // Over the edge, into the next triangle.
            let key = (a.min(b), a.max(b));
            self.cut.insert(key);
            if self.features.contains(&key) {
                self.stop(id, "feature");
                return;
            }
            let Some(other) = self.topo.across(t as u32, a, b) else {
                self.stop(id, "boundary");
                return;
            };
            // Keep the component along the edge; the component across it
            // turns from "out of t" into "into the new triangle", toward its
            // third corner.
            let e = (s.p[b as usize] - s.p[a as usize]).normalized();
            let out_old = e.cross(nt);
            let third = s.tris[other as usize].iter().copied().find(|&c| c != a && c != b).unwrap();
            let toward = s.p[third as usize] - s.p[a as usize];
            let in_new = (toward - e * toward.dot(e)).normalized();
            let along = d.dot(e);
            let across = d.dot(out_old).abs();
            self.traces[id].dir = (e * along + in_new * across).normalized();
            self.traces[id].tri = other;
            let nudge = self.traces[id].dir * 1e-9;
            *self.traces[id].points.last_mut().unwrap() += nudge;
        }
    }

    /// Where segment x→y crosses a segment already drawn in this triangle.
    /// Its own earlier segments count once it is far enough from them (a
    /// loop closing); siblings from the same singularity do not count near
    /// the start they share. -> (point, whether it was our own trace).
    fn crossing(&self, t: u32, id: usize, x: V3, y: V3, nt: V3) -> Option<(V3, bool)> {
        let existing = self.segments.get(&t)?;
        let me = &self.traces[id];
        let u = V3::tangent_of(nt);
        let v = nt.cross(u);
        let flat = |p: V3| (p.dot(u), p.dot(v));
        let (p, r) = (flat(x), flat(y));
        let r = (r.0 - p.0, r.1 - p.1);
        let mut best: Option<(f64, V3, bool)> = None;
        for seg in existing {
            let own = seg.trace == id;
            if own && me.travelled - seg.at < self.step * 8.0 {
                continue;
            }
            let sibling = !own && self.traces[seg.trace].from == me.from && me.from != usize::MAX;
            if sibling && (me.travelled < me.free * 1.5 || seg.at < me.free * 1.5) {
                continue;
            }
            let q = flat(seg.a);
            let s2 = flat(seg.b);
            let sv = (s2.0 - q.0, s2.1 - q.1);
            let den = r.0 * sv.1 - r.1 * sv.0;
            if den.abs() < 1e-18 {
                continue;
            }
            let qp = (q.0 - p.0, q.1 - p.1);
            let tt = (qp.0 * sv.1 - qp.1 * sv.0) / den;
            let w = (qp.0 * r.1 - qp.1 * r.0) / den;
            if (1e-9..=1.0).contains(&tt) && (0.0..=1.0).contains(&w) && best.map_or(true, |(bt, _, _)| tt < bt) {
                best = Some((tt, x + (y - x) * tt, own));
            }
        }
        best.map(|(_, at, own)| (at, own))
    }

    /// Triangles flooded across every edge no trace or feature cut, and
    /// each region's Euler characteristic (1 for a disk).
    fn regions(&self) -> (Vec<u32>, usize, Vec<i64>) {
        let s = self.s;
        let mut region = vec![u32::MAX; s.tris.len()];
        let mut regions = 0u32;
        for start in 0..s.tris.len() {
            if region[start] != u32::MAX {
                continue;
            }
            let mut stack = vec![start as u32];
            region[start] = regions;
            while let Some(t) = stack.pop() {
                let tri = s.tris[t as usize];
                for k in 0..3 {
                    let (a, b) = (tri[k], tri[(k + 1) % 3]);
                    if self.cut.contains(&(a.min(b), a.max(b))) {
                        continue;
                    }
                    if let Some(o) = self.topo.across(t, a, b) {
                        if region[o as usize] == u32::MAX {
                            region[o as usize] = regions;
                            stack.push(o);
                        }
                    }
                }
            }
            regions += 1;
        }
        let n = regions as usize;
        let mut verts: Vec<HashSet<u32>> = vec![HashSet::new(); n];
        let mut edges: Vec<HashSet<(u32, u32)>> = vec![HashSet::new(); n];
        let mut faces = vec![0i64; n];
        for (t, tri) in s.tris.iter().enumerate() {
            let r = region[t] as usize;
            faces[r] += 1;
            for k in 0..3 {
                let (a, b) = (tri[k], tri[(k + 1) % 3]);
                verts[r].insert(a);
                edges[r].insert((a.min(b), a.max(b)));
            }
        }
        let euler = (0..n).map(|r| verts[r].len() as i64 - edges[r].len() as i64 + faces[r]).collect();
        (region, n, euler)
    }

    /// The triangle of region `r` farthest (in triangle steps) from the
    /// region's edge — where a repair trace has the most room.
    fn deepest(&self, region: &[u32], r: u32) -> Option<usize> {
        let s = self.s;
        let mut depth = vec![usize::MAX; s.tris.len()];
        let mut queue = std::collections::VecDeque::new();
        for (t, tri) in s.tris.iter().enumerate() {
            if region[t] != r {
                continue;
            }
            let on_edge = (0..3).any(|k| {
                let (a, b) = (tri[k], tri[(k + 1) % 3]);
                self.cut.contains(&(a.min(b), a.max(b)))
                    || self.topo.across(t as u32, a, b).map_or(true, |o| region[o as usize] != r)
            });
            if on_edge {
                depth[t] = 0;
                queue.push_back(t);
            }
        }
        if queue.is_empty() {
            // No edge at all (a closed surface with nothing cut yet): any
            // triangle will do.
            return (0..s.tris.len()).find(|&t| region[t] == r);
        }
        while let Some(t) = queue.pop_front() {
            let tri = s.tris[t];
            for k in 0..3 {
                if let Some(o) = self.topo.across(t as u32, tri[k], tri[(k + 1) % 3]) {
                    let o = o as usize;
                    if region[o] == r && depth[o] == usize::MAX {
                        depth[o] = depth[t] + 1;
                        queue.push_back(o);
                    }
                }
            }
        }
        (0..s.tris.len()).filter(|&t| region[t] == r).max_by_key(|&t| depth[t])
    }
}

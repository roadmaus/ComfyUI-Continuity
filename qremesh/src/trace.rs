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

#[derive(Clone)]
pub struct Trace {
    pub points: Vec<V3>,
    tri: u32,
    dir: V3,
    /// Its singularity's index, or `usize::MAX` for a repair trace.
    pub from: usize,
    /// Which of its singularity's separatrices it is.
    pub slot: usize,
    pub alive: bool,
    /// How it ended: "trace", "self", "singularity", "feature", "boundary", "length".
    pub ended: &'static str,
    /// The singularity and separatrix it arrived along, when it ended on one.
    pub to: Option<(usize, usize)>,
    /// "edge" (singularity to singularity, chosen from the candidates),
    /// "separatrix" (grown until it hits the layout) or "repair".
    pub kind: &'static str,
    /// A constant turn away from the field, in radians: a candidate bent
    /// toward a singularity the field's own line would just miss.
    pub bend: f64,
    travelled: f64,
    /// Distance walked straight before following the field — near a
    /// singularity the field has no direction worth following.
    free: f64,
    /// Close to a singularity it will end on: walk straight in. (Which one,
    /// its separatrix, how far the trace had come when it turned.)
    aim: Option<(usize, usize, f64)>,
    /// Mesh edges it crossed: the cut it makes in the surface.
    crossed: Vec<(u32, u32)>,
    segs: Vec<Segment>,
}

#[derive(Clone, Copy)]
struct Segment {
    tri: u32,
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
    /// Candidates traced, and how many of them ran singularity to
    /// singularity along a separatrix at both ends.
    pub candidates: Vec<Trace>,
    pub candidate_edges: usize,
    /// Corners per region: where its outline turns by more than 45°.
    pub corners: Vec<usize>,
}

/// Directions in which an arm of the field points straight away from the
/// singularity, measured: g(β) = (arm angle − β) wrapped to ±45°, sampled around
/// the ring; a separatrix is where g crosses zero (the wraps at ±45° are
/// jumps, not crossings).
fn measured_dirs(s: &Surface, z: &[C], sing: &Singularity, radius: f64, near: &[usize]) -> Vec<V3> {
    let nt = tri_normal(s, sing.tri);
    let u = V3::tangent_of(nt);
    let v = nt.cross(u);
    let samples = 360;
    let quarter = TAU / 4.0;
    let g: Vec<(f64, f64)> = (0..samples)
        .map(|k| {
            let beta = TAU * k as f64 / samples as f64;
            let point = sing.at + (u * beta.cos() + v * beta.sin()) * radius;
            // Inverse-distance blend of the nearest few vertices' crosses.
            let mut ranked: Vec<(f64, usize)> = near.iter().map(|&i| ((s.p[i] - point).norm2(), i)).collect();
            ranked.sort_by(|a, b| a.0.total_cmp(&b.0));
            let mut sum = C::ZERO;
            for &(d2, i) in ranked.iter().take(4) {
                let arm = s.arm(i, z[i]).project_tangent(nt);
                let alpha = arm.dot(v).atan2(arm.dot(u));
                sum += C::polar(1.0 / (d2.sqrt() + 1e-9), 4.0 * alpha);
            }
            let alpha = sum.arg() / 4.0;
            let mut w = (alpha - beta) % quarter;
            if w > quarter / 2.0 { w -= quarter; }
            if w < -quarter / 2.0 { w += quarter; }
            (beta, w)
        })
        .collect();
    let mut out = Vec::new();
    for k in 0..samples {
        let (b0, g0) = g[k];
        let (_, g1) = g[(k + 1) % samples];
        if g0 * g1 <= 0.0 && (g0 - g1).abs() < quarter / 2.0 {
            let t = g0 / (g0 - g1);
            let beta = b0 + t * TAU / samples as f64;
            out.push(u * beta.cos() + v * beta.sin());
        }
    }
    out
}

struct Tracer<'a> {
    s: &'a Surface,
    z: &'a [C],
    topo: &'a Topology,
    features: &'a HashSet<(u32, u32)>,
    sings: &'a [Singularity],
    /// Each singularity's separatrix directions, in its triangle's plane.
    seps: &'a [Vec<V3>],
    /// Segments drawn so far, by triangle.
    segments: HashMap<u32, Vec<Segment>>,
    traces: Vec<Trace>,
    /// Candidates: every trace runs as if it were alone on the surface.
    independent: bool,
    step: f64,
    max_length: f64,
    /// How close a trace heading for a singularity must come to end on it.
    snap: f64,
    /// Closest two lines may run side by side; also the grid's cell size.
    gap: f64,
    /// Segments drawn so far, by cell of side `gap`, for finding lines that
    /// run close beside each other.
    grid: HashMap<(i64, i64, i64), Vec<Segment>>,
}

/// Bends tried each way, `BEND_STEP` degrees apart.
const BENDS: i32 = 20;
const BEND_STEP: f64 = 1.0;

fn rotate(d: V3, n: V3, angle: f64) -> V3 {
    d * angle.cos() + n.cross(d) * angle.sin()
}

/// `gap`: the size of a quad, below which two lines side by side make a
/// strip too thin to fill.
pub fn layout(s: &Surface, z: &[C], sings: &[Singularity], features: &[(u32, u32)], step: f64, max_length: f64, gap: f64) -> Layout {
    let feature_set: HashSet<(u32, u32)> = features.iter().copied().collect();
    let topo = Topology::new(&s.tris);

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
    // Measured where the field allows it: the fitted model is a few degrees
    // off wherever the singularity is not alone (up to 14° on a lumpy
    // surface). A ring whose crossings do not come out as three or five is
    // too noisy to trust, and gets the model.
    let seps: Vec<Vec<V3>> = sings
        .iter()
        .map(|sing| {
            let near = ring(sing.tri, 8);
            let measured = measured_dirs(s, z, sing, free, &near);
            let expected = if sing.index > 0 { 3 } else { 5 };
            if measured.len() == expected { measured } else { separatrix_dirs(s, z, sing, free, &near) }
        })
        .collect();
    // Separatrices that run along a sharp edge are that edge: nothing to trace.
    let along_feature = |k: usize, dir: V3| {
        s.tris[sings[k].tri].iter().any(|&a| {
            s.adj[a as usize].iter().any(|&b| {
                feature_set.contains(&(a.min(b), a.max(b))) && (s.p[b as usize] - s.p[a as usize]).normalized().dot(dir) > 0.9
            })
        })
    };
    let slots: Vec<(usize, usize)> = (0..sings.len())
        .flat_map(|k| (0..seps[k].len()).map(move |j| (k, j)))
        .filter(|&(k, j)| !along_feature(k, seps[k][j]))
        .collect();

    let tracer = |independent: bool| Tracer {
        s,
        z,
        topo: &topo,
        features: &feature_set,
        sings,
        seps: &seps,
        segments: HashMap::new(),
        traces: Vec::new(),
        independent,
        step,
        max_length,
        snap: free,
        gap: f64::INFINITY,
        grid: HashMap::new(),
    };

    // Candidates: every separatrix traced on its own, through whatever other
    // traces would have stopped it, to where the field takes it. Most of a
    // good layout's lines run singularity to singularity — a cube's edges on
    // a sphere — and a separatrix stopped by the first trace it meets never
    // gets the chance to find its far end.
    //
    // A field line from one singularity rarely runs exactly into another,
    // even where the layout plainly wants it to: a sphere's field lines
    // spiral past their neighbours by a few degrees. So each separatrix is
    // shot again at a sweep of small constant bends off the field, and
    // wherever a bent shot lands on a singularity, that is a candidate edge
    // whose cost grows with the bend. (QuadWild gets the same freedom from
    // shortest paths in a graph that charges for leaving the field.)
    let mut cand = tracer(true);
    cand.max_length = max_length * 0.5;
    for &(k, j) in &slots {
        let nt = tri_normal(s, sings[k].tri);
        for b in -BENDS..=BENDS {
            let bend = (b as f64 * BEND_STEP).to_radians();
            let id = cand.traces.len();
            cand.start(sings[k].at, sings[k].tri as u32, rotate(seps[k][j], nt, bend), k, j, free);
            cand.traces[id].bend = bend;
        }
    }
    cand.run();
    // A separatrix whose straight shot meets a sharp edge within a few
    // triangles of its singularity runs along that edge too; the edge is
    // already in the layout. (A cube's corners: all three are its edges.)
    let slots: Vec<(usize, usize)> = slots
        .into_iter()
        .filter(|&(k, j)| !cand.traces.iter().any(|t| t.from == k && t.slot == j && t.bend == 0.0 && t.ended == "feature" && t.travelled < free * 2.0))
        .collect();

    // The layout, one line at a time, each checked against the lines
    // already in it. First the singularity-to-singularity edges, cheapest
    // first. A line between singularities A and B is usually found twice,
    // once from each end, and each separatrix may be used once, so the
    // second copy falls away. No edge may cross one already chosen — that
    // would put a corner in the middle of two patch sides — or run beside
    // one closer than a quad, which would make a strip too thin to fill.
    let mut tr = tracer(false);
    tr.gap = gap;
    let mut used: HashSet<(usize, usize)> = HashSet::new();
    for (_, c) in edge_options(&cand) {
        let t = &cand.traces[c];
        let (from, to) = ((t.from, t.slot), t.to.unwrap());
        if used.contains(&from) || used.contains(&to) {
            continue;
        }
        if tr.first_crossing(t).is_some() || tr.runs_along(t, t.travelled) {
            continue;
        }
        used.insert(from);
        used.insert(to);
        if std::env::var("QREMESH_DEBUG").is_ok() {
            eprintln!("edge {from:?} -> {to:?} length {:.2} bend {:.0}", t.travelled, t.bend.to_degrees());
        }
        tr.adopt(t.clone(), "edge");
    }

    // Then every separatrix left over must still end somewhere: on a line of
    // the layout, at close to a right angle (a T-junction), or on a sharp
    // edge. Of all its bent shots, the cheapest that does so without running
    // along a line is taken; the cheapest over all leftover separatrices
    // goes in first, since each line added changes where the rest end.
    let mut open: Vec<(usize, usize)> = slots.iter().copied().filter(|x| !used.contains(x)).collect();
    while !open.is_empty() {
        let mut best: Option<(f64, usize)> = None;
        for (i, t) in cand.traces.iter().enumerate() {
            if !open.contains(&(t.from, t.slot)) {
                continue;
            }
            let end = match tr.first_crossing(t) {
                Some((at, angle)) if angle > 50f64.to_radians() => at,
                Some(_) => continue,
                None if matches!(t.ended, "feature" | "boundary") => t.travelled,
                None => continue,
            };
            if tr.runs_along(t, end) {
                continue;
            }
            let bend = t.bend.to_degrees() / 10.0;
            let cost = end * (1.0 + bend * bend);
            if best.map_or(true, |(c, _)| cost < c) {
                best = Some((cost, i));
            }
        }
        let Some((cost, i)) = best else { break };
        let t = &cand.traces[i];
        if std::env::var("QREMESH_DEBUG").is_ok() {
            eprintln!("separatrix {:?} bend {:.0} cost {cost:.2}", (t.from, t.slot), t.bend.to_degrees());
        }
        open.retain(|&x| x != (t.from, t.slot));
        // Shot again, this time into the layout, which stops it where the
        // candidate first crossed it.
        let id = tr.traces.len();
        tr.start(t.points[0], sings[t.from].tri as u32, rotate(seps[t.from][t.slot], tri_normal(s, sings[t.from].tri), t.bend), t.from, t.slot, free);
        tr.traces[id].bend = t.bend;
        tr.run();
    }
    // Whatever found no clean end grows along the field until it meets
    // something, as every separatrix did in the first layouts.
    for &(k, j) in &open {
        if std::env::var("QREMESH_DEBUG").is_ok() {
            eprintln!("fallback {:?}", (k, j));
        }
        tr.start(sings[k].at, sings[k].tri as u32, seps[k][j], k, j, free);
    }
    tr.run();

    // Regions that are not disks — a torus has no singularities at all, so
    // no separatrices — get a field line through their middle, grown both
    // ways until it closes on itself or meets the layout, the way QuadWild
    // adds traces until every patch is a disk. One line a round, the two
    // directions of the cross taking turns: a torus needs one loop each way
    // round it, and a cross of four arms at once leaves half-loops that
    // stop on each other.
    let defect = |euler: &[i64]| euler.iter().map(|&e| (e - 1).abs()).sum::<i64>();
    let mut repairs = 0;
    let (mut region, mut regions, mut euler) = tr.regions();
    while repairs < 24 {
        let Some(r) = (0..regions as u32).find(|&r| euler[r as usize] != 1) else { break };
        let Some(t) = tr.deepest(&region, r) else { break };
        let [a, b, c] = s.tris[t].map(|v| s.p[v as usize]);
        let centre = (a + b + c) / 3.0;
        let v0 = s.tris[t][0] as usize;
        let arm = s.arm(v0, z[v0]);
        // Which way round is the one that cuts the region open is not known
        // in advance (a second loop parallel to the first cuts an annulus in
        // two annuli): both are tried, and the better kept.
        let before = tr.traces.len();
        let mut best: Option<(i64, V3)> = None;
        for d in [arm, s.n[v0].cross(arm)] {
            tr.start(centre, t as u32, d, usize::MAX, 0, 0.0);
            tr.start(centre, t as u32, -d, usize::MAX, 0, 0.0);
            tr.run();
            let score = defect(&tr.regions().2);
            if std::env::var("QREMESH_DEBUG").is_ok() {
                let ends: Vec<String> = tr.traces[before..].iter().map(|t| format!("{} {:.2}", t.ended, t.travelled)).collect();
                eprintln!("repair at {t}: defect {score} {ends:?}");
                let (rg, n, eu) = tr.regions();
                let mut size = vec![0; n];
                for &r in &rg { size[r as usize] += 1; }
                eprintln!("   {:?}", (0..n).filter(|&r| eu[r] != 1).map(|r| (eu[r], size[r])).collect::<Vec<_>>());
            }
            if best.map_or(true, |(b, _)| score < b) {
                best = Some((score, d));
            }
            tr.retract(before);
        }
        let d = best.unwrap().1;
        tr.start(centre, t as u32, d, usize::MAX, 0, 0.0);
        tr.start(centre, t as u32, -d, usize::MAX, 0, 0.0);
        tr.run();
        (region, regions, euler) = tr.regions();
        repairs += 1;
    }

    let disks = euler.iter().filter(|&&e| e == 1).count();
    let candidate_edges = cand.traces.iter().filter(|t| t.to.is_some()).count();
    let corners = corners(s, &topo, &region, regions, &tr.cut(), free * 2.0);
    Layout { traces: tr.traces, region, regions, disks, region_euler: euler, repairs, candidates: cand.traces, candidate_edges, corners }
}

/// Corners of each region, counted on its outline: the chain of mesh edges
/// between it and its neighbours or along a cut, walked around, turning by
/// more than 45° between the stretch `window` behind a point and the
/// stretch `window` ahead. The outline zigzags along triangle edges, so the
/// window must span a few triangles to see the trace it follows rather than
/// the teeth. A region can border itself (a torus cut open into one patch
/// has its two loops on its outline twice each), so the walk goes by
/// half-edge, pivoting around each vertex through the region's triangles to
/// the next edge on the outline. Triangles must wind consistently.
fn corners(s: &Surface, topo: &Topology, region: &[u32], regions: usize, cut: &HashSet<(u32, u32)>, window: f64) -> Vec<usize> {
    let outline = |t: usize, k: usize| -> bool {
        let tri = s.tris[t];
        let (a, b) = (tri[k], tri[(k + 1) % 3]);
        cut.contains(&(a.min(b), a.max(b))) || topo.across(t as u32, a, b).map_or(true, |o| region[o as usize] != region[t])
    };
    let mut seen: HashSet<(usize, usize)> = HashSet::new();
    let mut out = vec![0; regions];
    for t0 in 0..s.tris.len() {
        for k0 in 0..3 {
            if !outline(t0, k0) || seen.contains(&(t0, k0)) {
                continue;
            }
            let mut lp: Vec<u32> = Vec::new();
            let (mut t, mut k) = (t0, k0);
            while seen.insert((t, k)) {
                lp.push(s.tris[t][k]);
                // From the end of edge k, pivot to the next outline edge.
                let mut kk = (k + 1) % 3;
                let mut tt = t;
                let mut turns = 0;
                while !outline(tt, kk) && turns < 64 {
                    let (p, q) = (s.tris[tt][kk], s.tris[tt][(kk + 1) % 3]);
                    let Some(o) = topo.across(tt as u32, p, q) else { break };
                    let o = o as usize;
                    let Some(m) = (0..3).find(|&m| s.tris[o][m] == q && s.tris[o][(m + 1) % 3] == p) else { break };
                    tt = o;
                    kk = (m + 1) % 3;
                    turns += 1;
                }
                t = tt;
                k = kk;
            }
            // A cut that ends inside the region (a slit) is walked in and
            // straight back out: …, a, b, a, … Fold those away, or every
            // slit would count as three corners.
            let mut folded: Vec<u32> = Vec::with_capacity(lp.len());
            for v in lp {
                if folded.len() >= 2 && folded[folded.len() - 2] == v {
                    folded.pop();
                } else {
                    folded.push(v);
                }
            }
            while folded.len() >= 3 && (folded[1] == folded[folded.len() - 1] || folded[0] == folded[folded.len() - 2]) {
                if folded[1] == folded[folded.len() - 1] {
                    folded.remove(0);
                    folded.pop();
                } else {
                    let last = folded.pop().unwrap();
                    folded.pop();
                    folded.insert(0, last);
                    folded.remove(1);
                }
            }
            let points: Vec<V3> = folded.iter().map(|&v| s.p[v as usize]).collect();
            out[region[t0] as usize] += loop_corners(&points, window);
        }
    }
    out
}

fn loop_corners(p: &[V3], window: f64) -> usize {
    let n = p.len();
    if n < 3 {
        return 0;
    }
    let mut cum = vec![0.0; n + 1];
    for i in 0..n {
        cum[i + 1] = cum[i] + (p[(i + 1) % n] - p[i]).norm();
    }
    let total = cum[n];
    if total < 4.0 * window {
        return 0;
    }
    // The point `d` along the loop from point i (either way round).
    let along = |i: usize, d: f64| -> V3 {
        let mut target = (cum[i] + d).rem_euclid(total);
        let mut k = cum.partition_point(|&c| c <= target).saturating_sub(1).min(n - 1);
        if cum[k + 1] - cum[k] < 1e-300 {
            target = cum[k];
        }
        let t = (target - cum[k]) / (cum[k + 1] - cum[k]).max(1e-300);
        k %= n;
        p[k] + (p[(k + 1) % n] - p[k]) * t
    };
    let turn: Vec<f64> = (0..n)
        .map(|i| {
            let back = (p[i] - along(i, -window)).normalized();
            let ahead = (along(i, window) - p[i]).normalized();
            back.dot(ahead).clamp(-1.0, 1.0).acos()
        })
        .collect();
    // Peaks above 45°, at least a window apart.
    let mut count = 0;
    for i in 0..n {
        if turn[i] < 45f64.to_radians() {
            continue;
        }
        let peak = (0..n).all(|j| {
            let d = (cum[j] - cum[i]).abs();
            let d = d.min(total - d);
            d > window || turn[j] < turn[i] || (turn[j] == turn[i] && j >= i)
        });
        if peak {
            count += 1;
        }
    }
    count
}

/// Singularity-to-singularity candidates as (cost, candidate), cheapest
/// first, keeping per pair of separatrices only the cheapest shot from
/// either end. Cost is length, raised by how far the shot bent.
fn edge_options(cand: &Tracer) -> Vec<(f64, usize)> {
    let mut best: HashMap<((usize, usize), (usize, usize)), (f64, usize)> = HashMap::new();
    for (i, t) in cand.traces.iter().enumerate() {
        let Some(to) = t.to else { continue };
        let from = (t.from, t.slot);
        if from == to {
            continue;
        }
        let key = (from.min(to), from.max(to));
        let bend = t.bend.to_degrees() / 10.0;
        let cost = t.travelled * (1.0 + bend * bend);
        if best.get(&key).map_or(true, |&(c, _)| cost < c) {
            best.insert(key, (cost, i));
        }
    }
    let mut options: Vec<(f64, usize)> = best.into_values().collect();
    options.sort_by(|a, b| a.0.total_cmp(&b.0));
    options
}

/// Where segment x→y crosses segment a→b, both in the plane with normal
/// `nt`. -> (fraction along x→y, point).
fn intersect_at(nt: V3, x: V3, y: V3, a: V3, b: V3) -> Option<(f64, V3)> {
    let u = V3::tangent_of(nt);
    let v = nt.cross(u);
    let flat = |p: V3| (p.dot(u), p.dot(v));
    let (p, r) = (flat(x), flat(y));
    let r = (r.0 - p.0, r.1 - p.1);
    let (q, s2) = (flat(a), flat(b));
    let sv = (s2.0 - q.0, s2.1 - q.1);
    let den = r.0 * sv.1 - r.1 * sv.0;
    if den.abs() < 1e-18 {
        return None;
    }
    let qp = (q.0 - p.0, q.1 - p.1);
    let tt = (qp.0 * sv.1 - qp.1 * sv.0) / den;
    let w = (qp.0 * r.1 - qp.1 * r.0) / den;
    ((1e-9..=1.0).contains(&tt) && (0.0..=1.0).contains(&w)).then(|| (tt, x + (y - x) * tt))
}

fn point_segment(x: V3, a: V3, b: V3) -> f64 {
    let ab = b - a;
    let t = ((x - a).dot(ab) / ab.norm2().max(1e-300)).clamp(0.0, 1.0);
    (a + ab * t - x).norm()
}

impl<'a> Tracer<'a> {
    fn start(&mut self, at: V3, tri: u32, dir: V3, from: usize, slot: usize, free: f64) {
        self.traces.push(Trace {
            points: vec![at],
            tri,
            dir,
            from,
            slot,
            alive: true,
            ended: "",
            to: None,
            kind: if from == usize::MAX { "repair" } else { "separatrix" },
            bend: 0.0,
            travelled: 0.0,
            free,
            aim: None,
            crossed: Vec::new(),
            segs: Vec::new(),
        });
    }

    /// Take over a finished candidate as a layout edge.
    fn adopt(&mut self, mut t: Trace, kind: &'static str) {
        let id = self.traces.len();
        t.kind = kind;
        let segs = std::mem::take(&mut t.segs);
        self.traces.push(t);
        for mut seg in segs {
            seg.trace = id;
            self.draw(seg);
        }
    }

    /// Take back every trace from `from` on.
    fn retract(&mut self, from: usize) {
        for list in self.segments.values_mut().chain(self.grid.values_mut()) {
            list.retain(|seg| seg.trace < from);
        }
        self.traces.truncate(from);
    }

    fn cell(&self, x: V3) -> (i64, i64, i64) {
        ((x.x / self.gap).floor() as i64, (x.y / self.gap).floor() as i64, (x.z / self.gap).floor() as i64)
    }

    /// Where candidate `t` first crosses a line already in the layout, away
    /// from the singularities it starts and ends on (every line from those
    /// starts there). -> (how far along `t`, the angle between the two).
    fn first_crossing(&self, t: &Trace) -> Option<(f64, f64)> {
        let zone = t.free * 1.5;
        let ends: Vec<V3> = [Some(t.from), t.to.map(|(k, _)| k)].into_iter().flatten().filter(|&k| k != usize::MAX).map(|k| self.sings[k].at).collect();
        for seg in &t.segs {
            let Some(others) = self.segments.get(&seg.tri) else { continue };
            let nt = tri_normal(self.s, seg.tri as usize);
            let mut first: Option<(f64, f64)> = None;
            for o in others {
                let Some((tt, x)) = intersect_at(nt, seg.a, seg.b, o.a, o.b) else { continue };
                if ends.iter().any(|&e| (x - e).norm() < zone) {
                    continue;
                }
                let cos = (seg.b - seg.a).normalized().dot((o.b - o.a).normalized()).abs();
                if first.map_or(true, |(f, _)| tt < f) {
                    first = Some((tt, cos.min(1.0).acos()));
                }
            }
            if let Some((tt, angle)) = first {
                return Some((seg.at + (seg.b - seg.a).norm() * tt, angle));
            }
        }
        None
    }

    /// Whether the first `until` of candidate `t` runs beside a line of the
    /// layout, nearly parallel and closer than `gap`, for more than two gaps
    /// of its length. Near singularities lines converge anyway; that does
    /// not count.
    fn runs_along(&self, t: &Trace, until: f64) -> bool {
        let zone = t.free * 1.5;
        let mut alongside = 0.0;
        for seg in &t.segs {
            if seg.at >= until {
                break;
            }
            let mid = (seg.a + seg.b) * 0.5;
            if self.sings.iter().any(|sing| (sing.at - mid).norm() < zone) {
                continue;
            }
            let dir = (seg.b - seg.a).normalized();
            let (cx, cy, cz) = self.cell(mid);
            let close = (-1..=1).any(|dx| {
                (-1..=1).any(|dy| {
                    (-1..=1).any(|dz| {
                        self.grid.get(&(cx + dx, cy + dy, cz + dz)).map_or(false, |cell| {
                            cell.iter().any(|o| {
                                (o.b - o.a).normalized().dot(dir).abs() > 0.9
                                    && point_segment(mid, o.a, o.b) < self.gap
                            })
                        })
                    })
                })
            });
            if close {
                alongside += (seg.b - seg.a).norm();
                if alongside > 2.0 * self.gap {
                    return true;
                }
            }
        }
        false
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

    fn draw(&mut self, seg: Segment) {
        self.segments.entry(seg.tri).or_default().push(seg);
        if self.gap.is_finite() {
            let c = self.cell((seg.a + seg.b) * 0.5);
            self.grid.entry(c).or_default().push(seg);
        }
        self.traces[seg.trace].segs.push(seg);
    }

    /// A singularity this trace, now at `x` heading `d`, should end on: close
    /// and ahead, and reached along one of its own separatrices (a field
    /// line through a singularity leaves along another of them). Its own
    /// singularity counts only once the trace has gone well away from it.
    fn target(&self, id: usize, x: V3, d: V3) -> Option<(usize, usize)> {
        let me = &self.traces[id];
        for (k, sing) in self.sings.iter().enumerate() {
            if k == me.from && me.travelled < me.free * 3.0 {
                continue;
            }
            let off = x - sing.at;
            let dist = off.norm();
            if dist > self.snap {
                continue;
            }
            let ahead = d.dot(-off) / dist.max(1e-300);
            if dist > self.step * 1.5 && ahead < 15f64.to_radians().cos() {
                continue;
            }
            let nt = tri_normal(self.s, sing.tri);
            let back = off.project_tangent(nt).normalized();
            let (best, score) = self.seps[k]
                .iter()
                .enumerate()
                .map(|(j, &sd)| (j, sd.dot(back)))
                .max_by(|a, b| a.1.total_cmp(&b.1))?;
            let tolerance = if self.seps[k].len() == 3 { 35f64 } else { 25f64 };
            if score >= tolerance.to_radians().cos() || dist < self.step * 1.5 {
                return Some((k, best));
            }
        }
        None
    }

    fn advance(&mut self, id: usize) {
        let s = self.s;
        let mut remaining = self.step;
        while remaining > 1e-12 {
            let t = self.traces[id].tri as usize;
            let x = *self.traces[id].points.last().unwrap();
            if let Some((k, j, since)) = self.traces[id].aim {
                if t == self.sings[k].tri || self.traces[id].travelled - since > self.snap * 3.0 {
                    self.traces[id].points.push(self.sings[k].at);
                    self.traces[id].to = Some((k, j));
                    self.stop(id, "singularity");
                    return;
                }
            }
            let nt = tri_normal(s, t);
            let mut d = self.traces[id].dir.project_tangent(nt).normalized();
            if let Some((k, _, _)) = self.traces[id].aim {
                let toward = (self.sings[k].at - x).project_tangent(nt).normalized();
                if toward != V3::ZERO {
                    d = toward;
                }
            } else if self.traces[id].travelled >= self.traces[id].free {
                let bend = self.traces[id].bend;
                // Undo the bend before asking the field which arm we are on.
                d = rotate(field_dir(s, self.z, t, x, rotate(d, nt, -bend)), nt, bend);
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
            self.draw(Segment { tri: t as u32, trace: id, a: x, b: next, at: travelled });
            if self.traces[id].aim.is_none() {
                if let Some((k, j)) = self.target(id, next, d) {
                    self.traces[id].aim = Some((k, j, travelled + length));
                }
            }
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
            self.traces[id].crossed.push(key);
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
    /// loop closing). Near its own start, where every trace of that
    /// singularity begins, and near the singularity it is walking into,
    /// where every trace of that one begins, nothing stops it. A candidate
    /// is stopped by nothing but itself. -> (point, whether it was our own
    /// trace).
    fn crossing(&self, t: u32, id: usize, x: V3, y: V3, nt: V3) -> Option<(V3, bool)> {
        let existing = self.segments.get(&t)?;
        let me = &self.traces[id];
        let zone = (me.free * 1.5).max(self.step * 4.0);
        // Where it started: its singularity, or a repair line's middle,
        // where its other half starts too.
        let home = (me.travelled < zone).then(|| me.points[0]);
        let goal = me.aim.map(|(k, _, _)| self.sings[k].at);
        let mut best: Option<(f64, V3, bool)> = None;
        for seg in existing {
            let own = seg.trace == id;
            if own && me.travelled - seg.at < self.step * 8.0 {
                continue;
            }
            if !own && self.independent {
                continue;
            }
            if !own && [home, goal].into_iter().flatten().any(|c| (seg.a - c).norm() < zone || (seg.b - c).norm() < zone) {
                continue;
            }
            if let Some((tt, at)) = intersect_at(nt, x, y, seg.a, seg.b) {
                if best.map_or(true, |(bt, _, _)| tt < bt) {
                    best = Some((tt, at, own));
                }
                continue;
            }
            // Lines that meet head on, or a loop coming back round beside
            // its own start, run alongside instead of crossing and would
            // never stop: close enough and parallel enough is a meeting.
            let along = (seg.b - seg.a).normalized().dot((y - x).normalized()).abs();
            if along > 0.95 && point_segment(y, seg.a, seg.b) < self.step * 1.5 {
                let ab = seg.b - seg.a;
                let at = seg.a + ab * ((y - seg.a).dot(ab) / ab.norm2().max(1e-300)).clamp(0.0, 1.0);
                if best.map_or(true, |(bt, _, _)| 1.0 < bt) {
                    best = Some((1.0, at, own));
                }
            }
        }
        best.map(|(_, at, own)| (at, own))
    }

    /// Every mesh edge a trace or a sharp edge cuts.
    fn cut(&self) -> HashSet<(u32, u32)> {
        let mut cut: HashSet<(u32, u32)> = self.features.clone();
        for t in &self.traces {
            cut.extend(t.crossed.iter().copied());
        }
        cut
    }

    /// Triangles flooded across every edge no trace or feature cut, and
    /// each region's Euler characteristic (1 for a disk).
    fn regions(&self) -> (Vec<u32>, usize, Vec<i64>) {
        let s = self.s;
        let cut = self.cut();
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
                    if cut.contains(&(a.min(b), a.max(b))) {
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
        // χ of each region as the cuts leave it, not of its triangles: a
        // torus cut open along one loop each way is a disk, though its
        // triangles are still all of the torus. So a cut edge inside a
        // region counts once per side, and a vertex once per fan of its
        // triangles that no cut edge splits.
        let mut chi = vec![0i64; n];
        for &r in &region {
            chi[r as usize] += 1;
        }
        for (&(a, b), tris) in &self.topo.edge_tris {
            if cut.contains(&(a, b)) {
                for &t in tris {
                    chi[region[t as usize] as usize] -= 1;
                }
            } else {
                chi[region[tris[0] as usize] as usize] -= 1;
            }
        }
        let mut around: Vec<Vec<u32>> = vec![Vec::new(); s.p.len()];
        for (t, tri) in s.tris.iter().enumerate() {
            for &v in tri {
                around[v as usize].push(t as u32);
            }
        }
        for (v, fan) in around.iter().enumerate() {
            // Union the triangles at v across the uncut edges they share.
            let mut parent: Vec<usize> = (0..fan.len()).collect();
            fn root(parent: &mut [usize], mut i: usize) -> usize {
                while parent[i] != i {
                    parent[i] = parent[parent[i]];
                    i = parent[i];
                }
                i
            }
            for i in 0..fan.len() {
                for j in i + 1..fan.len() {
                    let (ti, tj) = (s.tris[fan[i] as usize], s.tris[fan[j] as usize]);
                    let shared = ti.iter().find(|&&w| w as usize != v && tj.contains(&w));
                    if let Some(&w) = shared {
                        let v = v as u32;
                        if !cut.contains(&(v.min(w), v.max(w))) {
                            let (ri, rj) = (root(&mut parent, i), root(&mut parent, j));
                            parent[ri] = rj;
                        }
                    }
                }
            }
            for i in 0..fan.len() {
                if root(&mut parent, i) == i {
                    chi[region[fan[i] as usize] as usize] += 1;
                }
            }
        }
        (region, n, chi)
    }

    /// The triangle of region `r` farthest (in triangle steps) from the
    /// region's edge — where a repair trace has the most room.
    fn deepest(&self, region: &[u32], r: u32) -> Option<usize> {
        let s = self.s;
        let cut = self.cut();
        let mut depth = vec![usize::MAX; s.tris.len()];
        let mut queue = std::collections::VecDeque::new();
        for (t, tri) in s.tris.iter().enumerate() {
            if region[t] != r {
                continue;
            }
            let on_edge = (0..3).any(|k| {
                let (a, b) = (tri[k], tri[(k + 1) % 3]);
                cut.contains(&(a.min(b), a.max(b))) || self.topo.across(t as u32, a, b).map_or(true, |o| region[o as usize] != r)
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
                let (a, b) = (tri[k], tri[(k + 1) % 3]);
                if cut.contains(&(a.min(b), a.max(b))) {
                    continue;
                }
                if let Some(o) = self.topo.across(t as u32, a, b) {
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

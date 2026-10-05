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

/// Where a trace point sits: inside triangle `tri`, or on mesh edge `edge`
/// (shared by `tri` and the triangle it moved into).
#[derive(Clone, Copy, Debug)]
pub struct Stop {
    pub tri: u32,
    pub edge: Option<(u32, u32)>,
}

#[derive(Clone)]
pub struct Trace {
    pub points: Vec<V3>,
    /// One per point.
    pub stops: Vec<Stop>,
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
    /// Waypoints to walk through (a candidate found as a cheapest path),
    /// and the next one to head for.
    route: Vec<V3>,
    route_at: usize,
    /// The separatrix the route ends on, which it aims for when close
    /// instead of judging the slot by its heading.
    route_to: Option<(usize, usize)>,
    /// Its own segments by triangle, for a candidate that checks only
    /// against itself.
    own: HashMap<u32, Vec<Segment>>,
    /// What the candidate costs in the selection, when it was not a bent
    /// shot (whose cost comes from its length and bend).
    pub cost: Option<f64>,
    travelled: f64,
    /// Distance walked straight before following the field — near a
    /// singularity the field has no direction worth following.
    free: f64,
    /// Close to a point it will end on: walk straight in.
    aim: Option<Aim>,
    /// The trace it ended on, when it ended on one.
    pub on: Option<usize>,
    /// Mesh edges it crossed: the cut it makes in the surface.
    crossed: Vec<(u32, u32)>,
    /// The edge it entered its current triangle through, which the ray
    /// out of the triangle must not pick again from a point sitting on it.
    entered: Option<(u32, u32)>,
    segs: Vec<Segment>,
}

/// Where a trace is walking straight to: a singularity (which one, along
/// which separatrix) or a node where another trace ended on the line this
/// one is about to end on. `since`: how far the trace had come when it
/// turned, so a walk that never arrives can be given up.
#[derive(Clone, Copy)]
enum Aim {
    /// `gate`: still heading for the point on the separatrix ray half a
    /// `free` out, so that every line into a singularity comes in along
    /// its own ray and two of them cannot cross on the way in.
    Sing { k: usize, j: usize, since: f64, gate: bool },
    Node { at: V3, tri: u32, on: usize, since: f64 },
}

impl Aim {
    fn since(&self) -> f64 {
        match *self {
            Aim::Sing { since, .. } | Aim::Node { since, .. } => since,
        }
    }
}

impl Trace {
    /// What choosing this candidate costs: its own cost from the path
    /// search, or its length raised by its bend.
    pub fn cost(&self) -> f64 {
        self.cost.unwrap_or_else(|| {
            let bend = self.bend.to_degrees() / 10.0;
            self.travelled * (1.0 + bend * bend)
        })
    }
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
const BENDS: i32 = 8;
const BEND_STEP: f64 = 2.0;

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
    let clock_shots = std::time::Instant::now();
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
    if std::env::var("QREMESH_DEBUG").is_ok() {
        eprintln!("shots: {} traced in {:.2}s", cand.traces.len(), clock_shots.elapsed().as_secs_f64());
    }
    // Bent shots only reach a singularity the field's line nearly hits.
    // Cheapest paths in a graph over the mesh's edges, charged for every
    // degree they leave the field, reach any singularity there is a
    // reasonable line to; each is walked through the mesh as a candidate
    // like the shots, so the selection treats them alike.
    let clock = std::time::Instant::now();
    let routes = field_routes(s, z, &topo, sings, &seps, &feature_set, &slots, free);
    let t_search = clock.elapsed().as_secs_f64();
    for r in &routes {
        let id = cand.traces.len();
        cand.start_route(sings[r.from.0].tri as u32, r.from.0, r.from.1, r.to, free, r.points.clone(), r.cost);
        let _ = id;
    }
    cand.run();
    if std::env::var("QREMESH_DEBUG").is_ok() {
        let landed = cand.traces.iter().filter(|t| t.cost.is_some() && t.to.is_some()).count();
        let mut why: std::collections::BTreeMap<&str, usize> = Default::default();
        for t in cand.traces.iter().filter(|t| t.cost.is_some()) {
            *why.entry(t.ended).or_default() += 1;
        }
        eprintln!("routes: {} kept, {landed} walked to their singularity ({why:?}); search {t_search:.2}s, walk {:.2}s", routes.len(), clock.elapsed().as_secs_f64() - t_search);
        for (r, t) in routes.iter().zip(cand.traces.iter().filter(|t| t.cost.is_some())) {
            if std::env::var("QREMESH_ROUTES").is_ok() {
                eprintln!("  route {:?} -> {:?} cost {:.2} ({} points): ended {} at {:?}", r.from, r.to, r.cost, r.points.len(), t.ended, t.to);
            }
        }
    }
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
        // One line first; it closes on itself if the field lets it (a
        // torus's loops do), and its stub before the closing point is a
        // slit the graph prunes. Two halves going opposite ways would
        // spiral past each other with a lateral offset and cross twice,
        // leaving a lens between the crossings. Only a line that ended on
        // the layout needs its other half, to reach the layout the other
        // way too.
        let both_ways = |tr: &mut Tracer, d: V3| {
            let first = tr.traces.len();
            tr.start(centre, t as u32, d, usize::MAX, 0, 0.0);
            tr.run();
            if tr.traces[first].ended != "self" {
                tr.start(centre, t as u32, -d, usize::MAX, 0, 0.0);
                tr.run();
            }
        };
        let before = tr.traces.len();
        let mut best: Option<(i64, V3)> = None;
        for d in [arm, s.n[v0].cross(arm)] {
            both_ways(&mut tr, d);
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
        both_ways(&mut tr, d);
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
        let cost = t.cost();
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
            stops: vec![Stop { tri, edge: None }],
            tri,
            dir,
            from,
            slot,
            alive: true,
            ended: "",
            to: None,
            kind: if from == usize::MAX { "repair" } else { "separatrix" },
            bend: 0.0,
            route: Vec::new(),
            route_at: 0,
            route_to: None,
            own: HashMap::new(),
            cost: None,
            travelled: 0.0,
            free,
            aim: None,
            on: None,
            crossed: Vec::new(),
            entered: None,
            segs: Vec::new(),
        });
    }

    /// A trace that walks through `route` (ending at a singularity, which
    /// `target` then catches as usual) instead of following the field.
    fn start_route(&mut self, tri: u32, from: usize, slot: usize, to: (usize, usize), free: f64, route: Vec<V3>, cost: f64) {
        let dir = (route[1] - route[0]).normalized();
        self.start(route[0], tri, dir, from, slot, free);
        let id = self.traces.len() - 1;
        self.traces[id].route = route;
        self.traces[id].route_at = 1;
        self.traces[id].route_to = Some(to);
        self.traces[id].cost = Some(cost);
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
        let zone = t.free * 0.5 + self.step * 1.5;
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
        // Candidates run alone: nothing but the trace itself ever looks at
        // its segments, so the shared index is not kept for them.
        if !self.independent {
            self.segments.entry(seg.tri).or_default().push(seg);
        } else {
            self.traces[seg.trace].own.entry(seg.tri).or_default().push(seg);
        }
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
            if dist > self.step * 1.5 && ahead < 30f64.to_radians().cos() {
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
        // A step is half an edge, so it crosses a handful of triangles. A
        // trace that needs hundreds of moves for one step is pinned at a
        // vertex or an edge, bouncing between two triangles by nothing —
        // and every bounce adds a segment its own crossing test has to scan
        // again, which is how one stuck candidate took minutes. Stop it.
        let mut moves = 0;
        while remaining > 1e-12 {
            moves += 1;
            if moves > 64 {
                self.stop(id, "stuck");
                return;
            }
            let t = self.traces[id].tri as usize;
            let x = *self.traces[id].points.last().unwrap();
            if let Some(aim) = self.traces[id].aim {
                match aim {
                    Aim::Sing { k, j, since, gate: true } => {
                        let gate = self.aim_point(aim);
                        if (gate - x).norm() < self.step * 1.5 || (self.sings[k].at - x).norm() < (gate - self.sings[k].at).norm() {
                            self.traces[id].aim = Some(Aim::Sing { k, j, since, gate: false });
                        }
                    }
                    Aim::Sing { k, j, gate: false, .. } if t == self.sings[k].tri => {
                        self.traces[id].points.push(self.sings[k].at);
                        self.traces[id].stops.push(Stop { tri: t as u32, edge: None });
                        self.traces[id].to = Some((k, j));
                        self.stop(id, "singularity");
                        return;
                    }
                    Aim::Node { at, tri, on, .. } if t == tri as usize => {
                        self.traces[id].points.push(at);
                        self.traces[id].stops.push(Stop { tri: t as u32, edge: None });
                        self.traces[id].on = Some(on);
                        self.stop(id, if on == id { "self" } else { "trace" });
                        return;
                    }
                    _ => {}
                }
                // Walking straight at it and still not there: something is
                // in the way (a fold, a feature). Give up on the aim rather
                // than teleport the trace to a point outside its triangle.
                if self.traces[id].travelled - aim.since() > self.snap * 3.0 {
                    self.stop(id, "lost");
                    return;
                }
            }
            let nt = tri_normal(s, t);
            let mut d = self.traces[id].dir.project_tangent(nt).normalized();
            if let Some(goal) = self.traces[id].aim.map(|a| self.aim_point(a)) {
                let toward = (goal - x).project_tangent(nt).normalized();
                if toward != V3::ZERO {
                    d = toward;
                }
            } else if !self.traces[id].route.is_empty() {
                // Heading for the next waypoint, each one passed when
                // reached within a step.
                // Passed when reached within a step, or when the trace is
                // already beyond it along the route (a waypoint just over
                // an edge sits off this triangle's plane and may never come
                // within a step).
                let tr = &mut self.traces[id];
                while tr.route_at < tr.route.len() {
                    let w = tr.route[tr.route_at];
                    let near = (w - x).norm() < self.step * 1.5;
                    let beyond = tr.route_at + 1 < tr.route.len() && (tr.route[tr.route_at + 1] - w).dot(w - x) <= 0.0 && (w - x).norm() < self.step * 4.0;
                    if near || beyond {
                        tr.route_at += 1;
                    } else {
                        break;
                    }
                }
                if tr.route_at >= tr.route.len() {
                    self.stop(id, "lost");
                    return;
                }
                let toward = (tr.route[tr.route_at] - x).project_tangent(nt).normalized();
                if toward != V3::ZERO {
                    d = toward;
                }
                if std::env::var("QREMESH_ROUTE_STEPS").map_or(false, |v| v == id.to_string()) {
                    eprintln!("    step: at ({:.3},{:.3},{:.3}) tri {t} waypoint {}/{} dist {:.4} travelled {:.3}", x.x, x.y, x.z, tr.route_at, tr.route.len(), (tr.route[tr.route_at] - x).norm(), tr.travelled);
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
                if self.traces[id].entered == Some((a.min(b), a.max(b))) {
                    continue;
                }
                let (pa, pb) = (s.p[a as usize], s.p[b as usize]);
                let e = pb - pa;
                let m = d.cross(e).dot(nt);
                if m.abs() < 1e-14 {
                    continue;
                }
                let w = pa - x;
                let sd = w.cross(e).dot(nt) / m;
                let u = w.cross(d).dot(nt) / m;
                if sd > 0.0 && (-1e-9..=1.0 + 1e-9).contains(&u) && exit.map_or(true, |(best, _, _)| sd < best) {
                    exit = Some((sd, a, b));
                }
            }
            // The field can turn the ray back toward the edge it came in
            // through; then that edge is the way out after all.
            if exit.is_none() {
                if let Some(back) = self.traces[id].entered {
                    self.traces[id].entered = None;
                    let _ = back;
                    continue;
                }
            }
            let Some((to_edge, a, b)) = exit else {
                self.stop(id, "boundary");
                return;
            };
            let length = to_edge.min(remaining);
            let next = x + d * length;
            let travelled = self.traces[id].travelled;

            if let Some((hit, other)) = self.crossing(t as u32, id, x, next, nt) {
                // Ending within a quad of a node already on that line, it
                // ends at the node instead: two lines landing a little apart
                // would bound a sliver no grid can fill.
                if self.traces[id].aim.is_none() {
                    if let Some((at, tri)) = self.node_near(other, hit) {
                        if std::env::var("QREMESH_DEBUG").is_ok() {
                            eprintln!("trace {id} ends at a node {:.2} quads from its hit on {other}", (at - hit).norm() / self.gap);
                        }
                        self.traces[id].aim = Some(Aim::Node { at, tri, on: other, since: travelled });
                        continue;
                    }
                }
                // The last piece is drawn too, so a trace still coming the
                // other way meets this one here and not a quad further on.
                self.draw(Segment { tri: t as u32, trace: id, a: x, b: hit, at: travelled });
                self.traces[id].points.push(hit);
                self.traces[id].stops.push(Stop { tri: t as u32, edge: None });
                self.traces[id].on = Some(other);
                self.stop(id, if other == id { "self" } else { "trace" });
                return;
            }
            self.draw(Segment { tri: t as u32, trace: id, a: x, b: next, at: travelled });
            if self.traces[id].aim.is_none() {
                let goal = match self.traces[id].route_to {
                    Some((k, j)) if (self.sings[k].at - next).norm() < self.snap => Some((k, j)),
                    Some(_) => None,
                    None => self.target(id, next, d),
                };
                if let Some((k, j)) = goal {
                    let gate = (self.sings[k].at - next).norm() > self.snap * 0.5;
                    self.traces[id].aim = Some(Aim::Sing { k, j, since: travelled + length, gate });
                }
            }
            self.traces[id].points.push(next);
            let on_edge = (length >= to_edge).then(|| (a.min(b), a.max(b)));
            self.traces[id].stops.push(Stop { tri: t as u32, edge: on_edge });
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
            self.traces[id].entered = Some(key);
        }
    }

    /// Where segment x→y crosses a segment already drawn in this triangle.
    /// Its own earlier segments count once it is far enough from them (a
    /// loop closing). Near its own start, where every trace of that
    /// singularity begins, and near the singularity it is walking into,
    /// where every trace of that one begins, nothing stops it. A candidate
    /// is stopped by nothing but itself. -> (point, whether it was our own
    /// trace).
    fn crossing(&self, t: u32, id: usize, x: V3, y: V3, nt: V3) -> Option<(V3, usize)> {
        let me = &self.traces[id];
        let existing: &Vec<Segment> = if self.independent { me.own.get(&t)? } else { self.segments.get(&t)? };
        let zone = (me.free * 1.5).max(self.step * 4.0);
        // Where it started: its singularity, or a repair line's middle,
        // where its other half starts too.
        let home = (me.travelled < zone).then(|| me.points[0]);
        // Walking into a singularity, every line of that singularity is
        // in the way near it; walking into a node, the lines through the
        // node are. Neither counts. Any other line crossed on the way in
        // stops the trace as usual.
        let (goal, goal_zone) = match me.aim {
            Some(Aim::Sing { k, .. }) => (Some(self.sings[k].at), self.snap * 0.5 + self.step * 1.5),
            Some(Aim::Node { at, .. }) => (Some(at), self.step * 1.5),
            None => (None, zone),
        };
        let mut best: Option<(f64, V3, usize)> = None;
        for seg in existing {
            let own = seg.trace == id;
            if own && me.travelled - seg.at < self.step * 8.0 {
                continue;
            }
            if !own && self.independent {
                continue;
            }
            if !own && home.map_or(false, |c| (seg.a - c).norm() < zone || (seg.b - c).norm() < zone) {
                continue;
            }
            if let Some(g) = goal {
                if point_segment(g, seg.a, seg.b) < goal_zone || (seg.a - g).norm() < goal_zone || (seg.b - g).norm() < goal_zone {
                    continue;
                }
            }
            if let Some((tt, at)) = intersect_at(nt, x, y, seg.a, seg.b) {
                if best.map_or(true, |(bt, _, _)| tt < bt) {
                    best = Some((tt, at, seg.trace));
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
                    best = Some((1.0, at, seg.trace));
                }
            }
        }
        best.map(|(_, at, other)| (at, other))
    }

    fn aim_point(&self, a: Aim) -> V3 {
        match a {
            Aim::Sing { k, j, gate: true, .. } => self.sings[k].at + self.seps[k][j] * (self.snap * 0.5),
            Aim::Sing { k, gate: false, .. } => self.sings[k].at,
            Aim::Node { at, .. } => at,
        }
    }

    /// A node within a quad of `hit`: where some trace ended on another.
    /// -> (point, its triangle).
    fn node_near(&self, _other: usize, hit: V3) -> Option<(V3, u32)> {
        if !self.gap.is_finite() {
            return None;
        }
        let mut best: Option<(f64, V3, u32)> = None;
        for tr in self.traces.iter() {
            if tr.alive || !matches!(tr.ended, "trace" | "self") {
                continue;
            }
            let at = *tr.points.last().unwrap();
            let d = (at - hit).norm();
            if d < self.gap && best.map_or(true, |(bd, _, _)| d < bd) {
                best = Some((d, at, tr.stops.last().unwrap().tri));
            }
        }
        best.map(|(_, at, tri)| (at, tri))
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

/// A cheapest field-following path from one separatrix to another.
struct Route {
    from: (usize, usize),
    to: (usize, usize),
    cost: f64,
    /// From the first singularity to the second, waypoints between.
    points: Vec<V3>,
}

/// Paths between separatrices through a graph over the mesh's edges: a
/// state is an edge being crossed into a triangle while following one arm
/// of the field, a step goes on to one of that triangle's other edges and
/// costs its length, raised by how far it turns from the arm (QuadWild's
/// graph charges for leaving the field the same way). The arm is carried
/// across each edge by choosing the nearest arm in the next triangle, so
/// a path cannot slip onto the other family of lines. From every
/// separatrix, Dijkstra; then for every other separatrix the cheapest
/// arrival within reach of its singularity along its ray. The paths zigzag
/// across edge midpoints and are smoothed before use.
fn field_routes(s: &Surface, z: &[C], topo: &Topology, sings: &[Singularity], seps: &[Vec<V3>], features: &HashSet<(u32, u32)>, slots: &[(usize, usize)], free: f64) -> Vec<Route> {
    use std::collections::BinaryHeap;
    let mut edges: Vec<(u32, u32)> = topo.edge_tris.keys().copied().collect();
    edges.sort_unstable();
    let index: HashMap<(u32, u32), usize> = edges.iter().enumerate().map(|(i, &e)| (e, i)).collect();
    let mid: Vec<V3> = edges.iter().map(|&(a, b)| (s.p[a as usize] + s.p[b as usize]) * 0.5).collect();
    let tri_edges: Vec<[usize; 3]> = s.tris.iter().map(|t| [index[&key(t[0], t[1])], index[&key(t[1], t[2])], index[&key(t[2], t[0])]]).collect();
    let singular: HashSet<usize> = sings.iter().map(|x| x.tri).collect();
    let edge_tris: Vec<Vec<u32>> = edges.iter().map(|e| topo.edge_tris[e].clone()).collect();
    // The four arms at each edge's midpoint, read in each of its triangles.
    let arm_table: Vec<[V3; 4]> = (0..edges.len() * 2)
        .map(|i| {
            let (e, side) = (i / 2, i % 2);
            let Some(&t) = edge_tris[e].get(side) else { return [V3::ZERO; 4] };
            let t = t as usize;
            let nt = tri_normal(s, t);
            let a0 = field_dir(s, z, t, mid[e], V3::tangent_of(nt));
            let a1 = nt.cross(a0);
            [a0, a1, -a0, -a1]
        })
        .collect();
    let side_of = |e: usize, t: usize| -> usize { if edge_tris[e][0] as usize == t { 0 } else { 1 } };
    let arms = |e: usize, t: usize| -> [V3; 4] { arm_table[e * 2 + side_of(e, t)] };
    let state = |e: usize, t: usize, k: usize| -> usize { (e * 2 + side_of(e, t)) * 4 + k };
    let unstate = |st: usize| -> (usize, usize, usize) {
        let (es, k) = (st / 4, st % 4);
        let (e, side) = (es / 2, es % 2);
        (e, edge_tris[e][side] as usize, k)
    };
    let step_cost = |len: f64, cos: f64| -> f64 {
        let theta = cos.clamp(-1.0, 1.0).acos();
        len * (1.0 + 2.0 * (theta / 45f64.to_radians()).powi(2))
    };
    let ring = |t: usize, depth: usize| -> Vec<usize> {
        let mut seen: HashSet<usize> = [t].into();
        let mut frontier = vec![t];
        for _ in 0..depth {
            let mut next = Vec::new();
            for &x in &frontier {
                for &e in &tri_edges[x] {
                    for &o in &edge_tris[e] {
                        if seen.insert(o as usize) {
                            next.push(o as usize);
                        }
                    }
                }
            }
            frontier = next;
        }
        // In a fixed order, so that ties in cost resolve the same way on
        // every run.
        let mut out: Vec<usize> = seen.into_iter().collect();
        out.sort_unstable();
        out
    };

    #[derive(PartialEq)]
    struct Item(f64, usize);
    impl Eq for Item {}
    impl PartialOrd for Item {
        fn partial_cmp(&self, o: &Self) -> Option<std::cmp::Ordering> {
            Some(self.cmp(o))
        }
    }
    impl Ord for Item {
        fn cmp(&self, o: &Self) -> std::cmp::Ordering {
            o.0.total_cmp(&self.0)
        }
    }

    let n_states = edges.len() * 8;
    let mut routes = Vec::new();
    for &(k, j) in slots {
        let at = sings[k].at;
        let dir = seps[k][j];
        let mut dist = vec![f64::INFINITY; n_states];
        let mut prev = vec![usize::MAX; n_states];
        let mut heap = BinaryHeap::new();
        // Leave along the separatrix: any nearby edge the ray roughly
        // points at, entered away from the singularity.
        for t in ring(sings[k].tri, 3) {
            for &e in &tri_edges[t] {
                let d0 = mid[e] - at;
                let len = d0.norm();
                if len < 1e-9 || len > free * 1.5 {
                    continue;
                }
                let cos = d0.dot(dir) / len;
                if cos < 40f64.to_radians().cos() {
                    continue;
                }
                let tris = &edge_tris[e];
                let far = *tris
                    .iter()
                    .max_by(|&&a, &&b| {
                        let c = |t: u32| { let tr = s.tris[t as usize]; ((s.p[tr[0] as usize] + s.p[tr[1] as usize] + s.p[tr[2] as usize]) / 3.0 - at).norm2() };
                        c(a).total_cmp(&c(b))
                    })
                    .unwrap() as usize;
                let arm = arms(e, far);
                let kk = (0..4).max_by(|&a, &b| arm[a].dot(d0).total_cmp(&arm[b].dot(d0))).unwrap();
                let st = state(e, far, kk);
                let c = step_cost(len, cos);
                if c < dist[st] {
                    dist[st] = c;
                    heap.push(Item(c, st));
                }
            }
        }
        while let Some(Item(d, st)) = heap.pop() {
            if d > dist[st] {
                continue;
            }
            let (e, t, kk) = unstate(st);
            let a = arms(e, t)[kk];
            for &e2 in &tri_edges[t] {
                if e2 == e || features.contains(&edges[e2]) {
                    continue;
                }
                let dd = mid[e2] - mid[e];
                let len = dd.norm();
                if len < 1e-12 {
                    continue;
                }
                let cos = dd.dot(a) / len;
                if cos < 50f64.to_radians().cos() {
                    continue;
                }
                let Some(&t2) = edge_tris[e2].iter().find(|&&o| o as usize != t) else { continue };
                let t2 = t2 as usize;
                // Through another singularity's triangle is no way to go.
                let mut c = step_cost(len, cos);
                if singular.contains(&t2) && t2 != sings[k].tri {
                    c *= 8.0;
                }
                let next_arms = arms(e2, t2);
                let k2 = (0..4).max_by(|&x, &y| next_arms[x].dot(a).total_cmp(&next_arms[y].dot(a))).unwrap();
                let st2 = state(e2, t2, k2);
                let nd = d + c;
                if nd < dist[st2] {
                    dist[st2] = nd;
                    prev[st2] = st;
                    heap.push(Item(nd, st2));
                }
            }
        }
        // Arrivals.
        for &(k2, j2) in slots {
            if k2 == k {
                continue;
            }
            let at2 = sings[k2].at;
            let ray = seps[k2][j2];
            let mut best: Option<(f64, usize)> = None;
            // Any state on an edge near the ray will do: the last stretch
            // is walked straight in through the gate, whatever the path's
            // own heading was.
            for t in ring(sings[k2].tri, 4) {
                for &e in &tri_edges[t] {
                    let off = mid[e] - at2;
                    let len = off.norm();
                    if len < 1e-9 || len > free * 2.0 || off.dot(ray) / len < 35f64.to_radians().cos() {
                        continue;
                    }
                    for side in 0..2 {
                        let Some(&tt) = edge_tris[e].get(side) else { continue };
                        let arm = &arm_table[e * 2 + side];
                        for kk in 0..4 {
                            // Arriving means coming in along the ray, the
                            // arm pointing at the singularity; a path that
                            // merely passes near the ray would hook round.
                            if arm[kk].dot(-off) / len < 60f64.to_radians().cos() {
                                continue;
                            }
                            let st = state(e, tt as usize, kk);
                            if dist[st].is_finite() {
                                let total = dist[st] + len;
                                if best.map_or(true, |(b, _)| total < b) {
                                    best = Some((total, st));
                                }
                            }
                        }
                    }
                }
            }
            let Some((cost, end)) = best else { continue };
            let mut points = vec![at2];
            let mut st = end;
            while st != usize::MAX {
                points.push(mid[unstate(st).0]);
                st = prev[st];
            }
            points.push(at);
            points.reverse();
            routes.push(Route { from: (k, j), to: (k2, j2), cost, points });
        }
    }
    // A path far longer than the straight distance goes the long way
    // round; it would never be chosen, and smoothing it costs time.
    routes.retain(|r| r.cost < 2.5 * (sings[r.from.0].at - sings[r.to.0].at).norm() + free);
    // Smoothed off the edge midpoints, back onto the surface.
    let mesh = crate::mesh::TriMesh { v: s.p.clone(), f: s.tris.clone() };
    let proj = crate::proj::Projector::new(&mesh, free / 1.5);
    for r in routes.iter_mut() {
        let n = r.points.len();
        for _ in 0..12 {
            let old = r.points.clone();
            for i in 1..n - 1 {
                let p = old[i] * 0.5 + (old[i - 1] + old[i + 1]) * 0.25;
                r.points[i] = proj.closest(p).0;
            }
        }
    }
    routes
}

fn key(a: u32, b: u32) -> (u32, u32) {
    (a.min(b), a.max(b))
}

//! The two fields a quad mesh is read off: which way the edges run at every
//! vertex (the orientation field), and where the quad corners sit (the
//! position field).
//!
//! This is the method of Instant Meshes (Jakob, Tarini, Panozzo,
//! Sorkine-Hornung, 2015), written again from the paper: both fields are
//! smoothed by repeatedly averaging each vertex with its neighbours, where
//! "averaging" first picks, of the four rotations (or the lattice
//! translations) a neighbour's value could mean, the one closest to ours.
//! Smoothing alone converges far too slowly on a dense mesh, so both fields
//! are solved first on a coarse copy of the surface and handed down level by
//! level.

use crate::math::{Rng, V3};
use std::collections::HashMap;
use std::f64::consts::PI;

pub struct Level {
    pub p: Vec<V3>,
    pub n: Vec<V3>,
    pub adj: Vec<Vec<u32>>,
    /// Each vertex's cluster in the next coarser level; empty on the coarsest.
    pub parent: Vec<u32>,
}

/// The surface at successively coarser resolutions, finest first.
///
/// Coarsening clusters vertices on a voxel grid whose cell doubles at every
/// level. That is crude next to the edge-collapse matching of the paper — a
/// cell can catch both sides of a thin part — but a sphere has no thin parts,
/// and the question this prototype answers is whether the rest works.
pub fn hierarchy(
    p: Vec<V3>,
    n: Vec<V3>,
    area: Vec<f64>,
    adj: Vec<Vec<u32>>,
    first_cell: f64,
    min_vertices: usize,
) -> Vec<Level> {
    let mut levels = vec![Level { p, n, adj, parent: Vec::new() }];
    let mut areas = vec![area];
    let mut cell = first_cell;
    while levels.last().unwrap().p.len() > min_vertices && levels.len() < 20 {
        let (coarse, coarse_area, parent) = {
            let fine = levels.last().unwrap();
            let fine_area = areas.last().unwrap();
            let mut ids: HashMap<(i64, i64, i64), u32> = HashMap::new();
            let mut parent = vec![0u32; fine.p.len()];
            let (mut ps, mut ns, mut ws) = (Vec::new(), Vec::new(), Vec::new());
            // Ids are handed out in vertex order, so the result does not
            // depend on the map's iteration order.
            for i in 0..fine.p.len() {
                let p = fine.p[i];
                let key = (
                    (p.x / cell).floor() as i64,
                    (p.y / cell).floor() as i64,
                    (p.z / cell).floor() as i64,
                );
                let id = *ids.entry(key).or_insert_with(|| {
                    ps.push(V3::ZERO);
                    ns.push(V3::ZERO);
                    ws.push(0.0);
                    (ps.len() - 1) as u32
                });
                parent[i] = id;
                let w = fine_area[i] + 1e-12;
                ps[id as usize] += p * w;
                ns[id as usize] += fine.n[i] * w;
                ws[id as usize] += w;
            }
            let count = ps.len();
            let mut adj = vec![Vec::new(); count];
            for i in 0..fine.p.len() {
                for &j in &fine.adj[i] {
                    let (a, b) = (parent[i], parent[j as usize]);
                    if a != b {
                        adj[a as usize].push(b);
                    }
                }
            }
            for list in adj.iter_mut() {
                list.sort_unstable();
                list.dedup();
            }
            let p = (0..count).map(|c| ps[c] / ws[c]).collect();
            let n = ns.iter().map(|n| n.normalized()).collect();
            (Level { p, n, adj, parent: Vec::new() }, ws, parent)
        };
        cell *= 2.0;
        if coarse.p.len() as f64 > 0.8 * levels.last().unwrap().p.len() as f64 {
            // The cell is still finer than the spacing here; grow it and try
            // again rather than adding a level that is not coarser.
            continue;
        }
        levels.last_mut().unwrap().parent = parent;
        levels.push(coarse);
        areas.push(coarse_area);
    }
    levels
}

// ---------------------------------------------------------------- orientation

/// Of the four directions `q0` stands for (q, n×q and their negatives) and
/// the four `q1` stands for, the closest pair. -> (ours, theirs).
pub fn compat_orientation(q0: V3, n0: V3, q1: V3, n1: V3) -> (V3, V3) {
    let a = [q0, n0.cross(q0)];
    let b = [q1, n1.cross(q1)];
    let (mut best, mut pick) = (-1.0, (0, 0));
    for (i, ai) in a.iter().enumerate() {
        for (j, bj) in b.iter().enumerate() {
            let score = ai.dot(*bj).abs();
            if score > best {
                best = score;
                pick = (i, j);
            }
        }
    }
    let d = a[pick.0].dot(b[pick.1]);
    (a[pick.0], b[pick.1] * if d < 0.0 { -1.0 } else { 1.0 })
}

/// Which quarter turn of `q0` about `n0` lands closest to `q1`: 0, 1, 2 or 3.
pub fn rotation_index(q0: V3, n0: V3, q1: V3) -> i32 {
    let t0 = n0.cross(q0);
    let turns = [q0, t0, -q0, -t0];
    let mut best = (f64::MIN, 0);
    for (k, t) in turns.iter().enumerate() {
        let d = t.dot(q1);
        if d > best.0 {
            best = (d, k as i32);
        }
    }
    best.1
}

fn smooth_orientation(level: &Level, q: &mut [V3], iterations: usize) {
    for _ in 0..iterations {
        for i in 0..level.p.len() {
            let ni = level.n[i];
            if ni == V3::ZERO {
                continue;
            }
            let mut qi = q[i];
            let mut weight = 0.0;
            for &j in &level.adj[i] {
                let j = j as usize;
                let (ours, theirs) = compat_orientation(qi, ni, q[j], level.n[j]);
                let next = (ours * weight + theirs).project_tangent(ni).normalized();
                if next != V3::ZERO {
                    qi = next;
                }
                weight += 1.0;
            }
            q[i] = qi;
        }
    }
}

fn random_tangent(n: V3, rng: &mut Rng) -> V3 {
    let t1 = V3::tangent_of(n);
    let t2 = n.cross(t1);
    let angle = rng.unit() * 2.0 * PI;
    t1 * angle.cos() + t2 * angle.sin()
}

/// The orientation field on every level, finest first.
pub fn solve_orientation(levels: &[Level], iterations: usize, rng: &mut Rng) -> Vec<Vec<V3>> {
    let top = levels.len() - 1;
    let mut fields: Vec<Vec<V3>> = vec![Vec::new(); levels.len()];
    let mut q: Vec<V3> = levels[top].n.iter().map(|&n| random_tangent(n, rng)).collect();
    smooth_orientation(&levels[top], &mut q, iterations);
    fields[top] = q;
    for l in (0..top).rev() {
        let level = &levels[l];
        let coarse = &fields[l + 1];
        let mut q: Vec<V3> = (0..level.p.len())
            .map(|i| {
                let n = level.n[i];
                let t = coarse[level.parent[i] as usize].project_tangent(n).normalized();
                if t.norm2() < 0.5 { V3::tangent_of(n) } else { t }
            })
            .collect();
        smooth_orientation(level, &mut q, iterations);
        fields[l] = q;
    }
    fields
}

// ------------------------------------------------------------------- position

/// The corner of `o`'s lattice nearest to `p`, the lattice spanned by `q` and
/// n×q at spacing `h`.
pub fn lattice_round(o: V3, q: V3, n: V3, p: V3, h: f64) -> V3 {
    let t = n.cross(q);
    let d = p - o;
    o + q * ((q.dot(d) / h).round() * h) + t * ((t.dot(d) / h).round() * h)
}

fn lattice_floor(o: V3, q: V3, n: V3, p: V3, h: f64) -> V3 {
    let t = n.cross(q);
    let d = p - o;
    o + q * ((q.dot(d) / h).floor() * h) + t * ((t.dot(d) / h).floor() * h)
}

/// A point between two vertices that lies close to both tangent planes — the
/// place two lattices are compared, so that curvature between the vertices
/// does not bias the comparison toward either.
fn middle_point(p0: V3, n0: V3, p1: V3, n1: V3) -> V3 {
    let (n0p0, n0p1, n1p0, n1p1) = (n0.dot(p0), n0.dot(p1), n1.dot(p0), n1.dot(p1));
    let n0n1 = n0.dot(n1);
    let denom = 1.0 / (1.0 - n0n1 * n0n1 + 1e-4);
    let l0 = 2.0 * (n0p1 - n0p0 - n0n1 * (n1p0 - n1p1)) * denom;
    let l1 = 2.0 * (n1p0 - n1p1 - n0n1 * (n0p1 - n0p0)) * denom;
    (p0 + p1) * 0.5 - (n0 * l0 + n1 * l1) * 0.25
}

/// The pair of lattice corners, one from each vertex's lattice, that are
/// closest to each other near the middle point. -> (ours, theirs).
#[allow(clippy::too_many_arguments)]
pub fn compat_position(
    p0: V3, n0: V3, q0: V3, o0: V3,
    p1: V3, n1: V3, q1: V3, o1: V3,
    h: f64,
) -> (V3, V3) {
    let (t0, t1) = (n0.cross(q0), n1.cross(q1));
    let middle = middle_point(p0, n0, p1, n1);
    let base0 = lattice_floor(o0, q0, n0, middle, h);
    let base1 = lattice_floor(o1, q1, n1, middle, h);
    let mut best = (f64::MAX, (base0, base1));
    for i in 0..4 {
        let a = base0 + (q0 * (i & 1) as f64 + t0 * ((i >> 1) & 1) as f64) * h;
        for j in 0..4 {
            let b = base1 + (q1 * (j & 1) as f64 + t1 * ((j >> 1) & 1) as f64) * h;
            let cost = (a - b).norm2();
            if cost < best.0 {
                best = (cost, (a, b));
            }
        }
    }
    best.1
}

fn smooth_position(level: &Level, q: &[V3], o: &mut [V3], h: f64, iterations: usize) {
    for _ in 0..iterations {
        for i in 0..level.p.len() {
            let (pi, ni, qi) = (level.p[i], level.n[i], q[i]);
            if ni == V3::ZERO {
                continue;
            }
            let mut oi = o[i];
            let mut weight = 0.0;
            for &j in &level.adj[i] {
                let j = j as usize;
                let qj = compat_orientation(qi, ni, q[j], level.n[j]).1;
                let (ours, theirs) =
                    compat_position(pi, ni, qi, oi, level.p[j], level.n[j], qj, o[j], h);
                oi = (ours * weight + theirs) / (weight + 1.0);
                weight += 1.0;
                oi -= ni * ni.dot(oi - pi);
            }
            o[i] = lattice_round(oi, qi, ni, pi, h);
        }
    }
}

/// How much finer than the lattice the first position level must be.
pub const SPACING: f64 = 1.0;

/// Mean distance between neighbours on a level.
pub fn spacing(level: &Level) -> f64 {
    let (mut total, mut count) = (0.0, 0usize);
    for (i, list) in level.adj.iter().enumerate() {
        for &j in list {
            total += (level.p[i] - level.p[j as usize]).norm();
            count += 1;
        }
    }
    total / count.max(1) as f64
}

/// The position field on the finest level: for each vertex, the lattice
/// corner nearest to it.
pub fn solve_position(
    levels: &[Level],
    q: &[Vec<V3>],
    h: f64,
    iterations: usize,
    rng: &mut Rng,
) -> Vec<V3> {
    // A level whose vertices are farther apart than a quad side cannot hold
    // a lattice of that side — it aliases, and the aliasing comes down to
    // the fine levels as dislocations smoothing cannot remove. Start at the
    // coarsest level that is still finer than the lattice.
    let top = (0..levels.len())
        .rev()
        .find(|&l| spacing(&levels[l]) < h * SPACING)
        .unwrap_or(0);
    let level = &levels[top];
    let mut o: Vec<V3> = (0..level.p.len())
        .map(|i| {
            let (p, n) = (level.p[i], level.n[i]);
            let start = p + random_tangent(n, rng) * (rng.unit() * h);
            lattice_round(start, q[top][i], n, p, h)
        })
        .collect();
    smooth_position(level, &q[top], &mut o, h, iterations);
    for l in (0..top).rev() {
        let level = &levels[l];
        let mut fine: Vec<V3> = (0..level.p.len())
            .map(|i| {
                let (p, n) = (level.p[i], level.n[i]);
                let from = o[level.parent[i] as usize];
                let on_plane = from - n * n.dot(from - p);
                lattice_round(on_plane, q[l][i], n, p, h)
            })
            .collect();
        smooth_position(level, &q[l], &mut fine, h, iterations);
        o = fine;
    }
    o
}

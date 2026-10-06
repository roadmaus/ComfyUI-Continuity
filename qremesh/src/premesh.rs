//! The input remesh: any triangle mesh to near-equilateral triangles of
//! one edge length, lying on the original surface.
//!
//! Everything after this assumes edges a few times shorter than a quad and
//! triangles that are not slivers. A sliver's normal is noise, so it makes
//! fake sharp edges, and the field kinks around them into pairs of
//! singularities — a marching-cubes creature gave 186 singularities where it
//! needs 8, and the tracer spent minutes routing between them.
//!
//! The scheme is Botsch and Kobbelt's incremental remeshing (2004), a few
//! rounds of: split edges longer than 4/3 of the target, collapse edges
//! shorter than 4/5 of it, flip edges toward valence six, move every vertex
//! toward the middle of its neighbours along its tangent plane, and put it
//! back on the input. Sharp edges and boundaries are kept: split along
//! themselves, collapsed only along themselves, never flipped, never
//! relaxed off.

use crate::math::V3;
use crate::mesh::TriMesh;
use crate::proj::Projector;
use std::collections::{HashMap, HashSet};

type Edge = (u32, u32);

fn key(a: u32, b: u32) -> Edge {
    (a.min(b), a.max(b))
}

fn min_angle(a: V3, b: V3, c: V3) -> f64 {
    let angle = |p: V3, q: V3, r: V3| {
        let (u, v) = ((q - p).normalized(), (r - p).normalized());
        u.dot(v).clamp(-1.0, 1.0).acos()
    };
    angle(a, b, c).min(angle(b, c, a)).min(angle(c, a, b))
}

fn normal(v: &[V3], t: [u32; 3]) -> V3 {
    let (a, b, c) = (v[t[0] as usize], v[t[1] as usize], v[t[2] as usize]);
    (b - a).cross(c - a)
}

fn edge_tris(f: &[[u32; 3]]) -> HashMap<Edge, Vec<usize>> {
    let mut map: HashMap<Edge, Vec<usize>> = HashMap::new();
    for (t, tri) in f.iter().enumerate() {
        for k in 0..3 {
            map.entry(key(tri[k], tri[(k + 1) % 3])).or_default().push(t);
        }
    }
    map
}

/// Sharp edges worth keeping: a dihedral angle over `degrees` between two
/// triangles that are both well shaped. Slivers are skipped — their normals
/// say nothing about the surface — and every boundary edge is kept.
fn features(m: &TriMesh, degrees: f64) -> HashSet<Edge> {
    let limit = degrees.to_radians().cos();
    let sliver = 12f64.to_radians();
    let mut out = Vec::new();
    let mut boundary = HashSet::new();
    for (e, tris) in edge_tris(&m.f) {
        if tris.len() != 2 {
            out.push(e);
            boundary.insert(e);
            continue;
        }
        let (t0, t1) = (m.f[tris[0]], m.f[tris[1]]);
        let shape = |t: [u32; 3]| min_angle(m.v[t[0] as usize], m.v[t[1] as usize], m.v[t[2] as usize]);
        if shape(t0) < sliver || shape(t1) < sliver {
            continue;
        }
        if normal(&m.v, t0).normalized().dot(normal(&m.v, t1).normalized()) < limit {
            out.push(e);
        }
    }
    prune_features(&m.v, &out, &boundary).into_iter().collect()
}

/// Sharp edges that are part of a real feature line: chains (split where
/// three or more sharp edges meet) at least `MIN_CHAIN` edges long that do
/// not zigzag. A faceted, under-sampled part of a scan or a marching-cubes
/// surface has plenty of edges over the angle threshold, but they come in
/// short or zigzagging runs; a hard surface's edges come in long smooth
/// lines. Boundary edges are not judged — they are always features.
pub fn prune_features(p: &[V3], sharp: &[Edge], boundary: &HashSet<Edge>) -> Vec<Edge> {
    const MIN_CHAIN: usize = 6;
    let max_turn = 25f64.to_radians();
    let interior: Vec<Edge> = sharp.iter().copied().filter(|e| !boundary.contains(e)).collect();
    let mut at: HashMap<u32, Vec<u32>> = HashMap::new();
    for &(a, b) in &interior {
        at.entry(a).or_default().push(b);
        at.entry(b).or_default().push(a);
    }
    for list in at.values_mut() {
        list.sort_unstable();
    }
    let mut used: HashSet<Edge> = HashSet::new();
    let mut keep: Vec<Edge> = sharp.iter().copied().filter(|e| boundary.contains(e)).collect();
    let mut starts: Vec<(u32, u32)> = Vec::new();
    let mut ends: Vec<u32> = at.keys().copied().filter(|v| at[v].len() != 2).collect();
    ends.sort_unstable();
    for &v in &ends {
        for &w in &at[&v] {
            starts.push((v, w));
        }
    }
    // Closed loops have no ends; start them anywhere.
    let mut all: Vec<Edge> = interior.clone();
    all.sort_unstable();
    for &(a, b) in &all {
        starts.push((a, b));
    }
    for (v0, w0) in starts {
        if used.contains(&key(v0, w0)) {
            continue;
        }
        let mut chain = vec![v0, w0];
        used.insert(key(v0, w0));
        loop {
            let last = *chain.last().unwrap();
            let prev = chain[chain.len() - 2];
            let next = &at[&last];
            if next.len() != 2 {
                break;
            }
            let n = if next[0] == prev { next[1] } else { next[0] };
            if used.contains(&key(last, n)) {
                break;
            }
            used.insert(key(last, n));
            chain.push(n);
        }
        let edges = chain.len() - 1;
        let mut turn = 0.0;
        for k in 1..chain.len() - 1 {
            let d0 = (p[chain[k] as usize] - p[chain[k - 1] as usize]).normalized();
            let d1 = (p[chain[k + 1] as usize] - p[chain[k] as usize]).normalized();
            turn += d0.dot(d1).clamp(-1.0, 1.0).acos();
        }
        let mean_turn = if edges > 1 { turn / (edges - 1) as f64 } else { 0.0 };
        if edges >= MIN_CHAIN && mean_turn < max_turn {
            keep.extend(chain.windows(2).map(|w| key(w[0], w[1])));
        }
    }
    keep.sort_unstable();
    keep.dedup();
    keep
}

pub struct Report {
    pub vertices: usize,
    pub triangles: usize,
    pub feature_edges: usize,
    pub slivers_before: f64,
    pub slivers_after: f64,
}

fn sliver_share(v: &[V3], f: &[[u32; 3]]) -> f64 {
    let thin = 10f64.to_radians();
    let n = f.iter().filter(|t| min_angle(v[t[0] as usize], v[t[1] as usize], v[t[2] as usize]) < thin).count();
    n as f64 / f.len().max(1) as f64
}

/// The input remeshed to edges of about `target` (asked per point: the
/// triangles follow the quad size where it varies), keeping edges sharper
/// than `degrees`.
pub fn remesh(input: &TriMesh, target: &dyn Fn(V3) -> f64, degrees: f64, rounds: usize) -> (TriMesh, Report) {
    let projector = Projector::new(input, crate::mesh::mean_edge(input) * 2.0);
    let mut v = input.v.clone();
    let mut f = input.f.clone();
    let mut sharp = features(input, degrees);
    let slivers_before = sliver_share(&v, &f);

    for _ in 0..rounds {
        // The wanted edge at every vertex; an edge is judged against the
        // mean of its two ends'.
        let mut size: Vec<f64> = v.iter().map(|&p| target(p)).collect();
        split(&mut v, &mut f, &mut sharp, &mut size, target, &projector);
        collapse(&mut v, &mut f, &mut sharp, &size);
        flip(&v, &mut f, &sharp);
        relax(&mut v, &f, &sharp, &projector);
    }

    // Drop vertices no triangle uses any more.
    let mut map = vec![u32::MAX; v.len()];
    let mut nv = Vec::new();
    for t in f.iter_mut() {
        for i in t.iter_mut() {
            if map[*i as usize] == u32::MAX {
                map[*i as usize] = nv.len() as u32;
                nv.push(v[*i as usize]);
            }
            *i = map[*i as usize];
        }
    }
    let report = Report {
        vertices: nv.len(),
        triangles: f.len(),
        feature_edges: sharp.len(),
        slivers_before,
        slivers_after: sliver_share(&nv, &f),
    };
    (TriMesh { v: nv, f }, report)
}

/// How many feature edges meet at each vertex: 0 free, 2 on a feature line,
/// anything else a corner (or a boundary's end) that never moves.
fn feature_valence(nv: usize, sharp: &HashSet<Edge>) -> Vec<u8> {
    let mut c = vec![0u8; nv];
    for &(a, b) in sharp {
        c[a as usize] = c[a as usize].saturating_add(1);
        c[b as usize] = c[b as usize].saturating_add(1);
    }
    c
}

fn split(v: &mut Vec<V3>, f: &mut Vec<[u32; 3]>, sharp: &mut HashSet<Edge>, size: &mut Vec<f64>, target: &dyn Fn(V3) -> f64, projector: &Projector) {
    for _ in 0..12 {
        let map = edge_tris(f);
        let mut long: Vec<(f64, Edge)> = map
            .keys()
            .map(|&(a, b)| ((v[a as usize] - v[b as usize]).norm() / (0.5 * (size[a as usize] + size[b as usize])), (a, b)))
            .filter(|(l, _)| *l > 4.0 / 3.0)
            .collect();
        if long.is_empty() {
            return;
        }
        long.sort_by(|x, y| y.0.total_cmp(&x.0).then(x.1.cmp(&y.1)));
        let mut touched = vec![false; f.len()];
        let mut added = Vec::new();
        for (_, (a, b)) in long {
            let tris = &map[&(a, b)];
            if tris.iter().any(|&t| touched[t]) {
                continue;
            }
            let mid = (v[a as usize] + v[b as usize]) * 0.5;
            let on_feature = sharp.contains(&(a, b));
            // A point on a straight feature edge is already on the surface;
            // anywhere else the chord is pulled back onto it.
            let m = if on_feature { mid } else { projector.closest(mid).0 };
            v.push(m);
            size.push(target(m));
            let mi = (v.len() - 1) as u32;
            for &t in tris {
                touched[t] = true;
                let tri = f[t];
                // Rotate so the split edge is the triangle's first edge.
                let r = (0..3).find(|&k| key(tri[k], tri[(k + 1) % 3]) == (a, b)).unwrap();
                let (x, y, z) = (tri[r], tri[(r + 1) % 3], tri[(r + 2) % 3]);
                f[t] = [x, mi, z];
                added.push([mi, y, z]);
            }
            if on_feature {
                sharp.remove(&(a, b));
                sharp.insert(key(a, mi));
                sharp.insert(key(mi, b));
            }
        }
        f.extend(added);
    }
}

fn collapse(v: &mut [V3], f: &mut Vec<[u32; 3]>, sharp: &mut HashSet<Edge>, size: &[f64]) {
    for _ in 0..12 {
        let map = edge_tris(f);
        let fv = feature_valence(v.len(), sharp);
        let mut around: Vec<Vec<usize>> = vec![Vec::new(); v.len()];
        for (t, tri) in f.iter().enumerate() {
            for &i in tri {
                around[i as usize].push(t);
            }
        }
        let ring = |i: u32, around: &Vec<Vec<usize>>, f: &Vec<[u32; 3]>| -> HashSet<u32> {
            around[i as usize].iter().flat_map(|&t| f[t]).filter(|&x| x != i).collect()
        };
        let mut short: Vec<(f64, Edge)> = map
            .keys()
            .map(|&(a, b)| ((v[a as usize] - v[b as usize]).norm() / (0.5 * (size[a as usize] + size[b as usize])), (a, b)))
            .filter(|(l, _)| *l < 4.0 / 5.0)
            .collect();
        if short.is_empty() {
            return;
        }
        short.sort_by(|x, y| x.0.total_cmp(&y.0).then(x.1.cmp(&y.1)));
        let mut locked = vec![false; v.len()];
        let mut dead = vec![false; f.len()];
        let mut any = false;
        for (_, (a, b)) in short {
            if locked[a as usize] || locked[b as usize] {
                continue;
            }
            let along = sharp.contains(&(a, b));
            let (ka, kb) = (fv[a as usize], fv[b as usize]);
            // Which vertex goes (r), which stays (s), and where s ends up.
            let free = |k: u8| k == 0;
            let line = |k: u8| k == 2;
            let (r, s, at) = if along {
                // Along a feature line: a line vertex may slide into its
                // neighbour on the line; corners stay.
                if line(ka) && line(kb) {
                    (a, b, (v[a as usize] + v[b as usize]) * 0.5)
                } else if line(ka) {
                    (a, b, v[b as usize])
                } else if line(kb) {
                    (b, a, v[a as usize])
                } else {
                    continue;
                }
            } else if free(ka) && free(kb) {
                (a, b, (v[a as usize] + v[b as usize]) * 0.5)
            } else if free(ka) {
                (a, b, v[b as usize])
            } else if free(kb) {
                (b, a, v[a as usize])
            } else {
                continue;
            };
            let (rr, rs) = (ring(r, &around, f), ring(s, &around, f));
            // Link condition: the two rings may share only the vertices
            // opposite the edge, or the collapse pinches the surface.
            let shared = rr.intersection(&rs).count();
            if shared != map[&(a, b)].len() {
                continue;
            }
            if rr.iter().any(|&x| x != s && (v[x as usize] - at).norm() > 4.0 / 3.0 * 0.5 * (size[x as usize] + size[s as usize])) {
                continue;
            }
            // No triangle that survives may turn over or go flat.
            let ok = around[r as usize].iter().chain(around[s as usize].iter()).all(|&t| {
                let tri = f[t];
                if tri.contains(&r) && tri.contains(&s) {
                    return true;
                }
                let before = normal(v, tri);
                let moved: Vec<V3> = tri.iter().map(|&i| if i == r || i == s { at } else { v[i as usize] }).collect();
                let after = (moved[1] - moved[0]).cross(moved[2] - moved[0]);
                after.norm() > 1e-14 && before.normalized().dot(after.normalized()) > 0.2
            });
            if !ok {
                continue;
            }
            for &t in &around[r as usize] {
                if f[t].contains(&s) {
                    dead[t] = true;
                } else {
                    for i in f[t].iter_mut() {
                        if *i == r {
                            *i = s;
                        }
                    }
                }
            }
            v[s as usize] = at;
            let moved: Vec<Edge> = sharp.iter().copied().filter(|&(x, y)| x == r || y == r).collect();
            for (x, y) in moved {
                sharp.remove(&(x, y));
                let o = if x == r { y } else { x };
                if o != s {
                    sharp.insert(key(o, s));
                }
            }
            for &x in rr.iter().chain(rs.iter()) {
                locked[x as usize] = true;
            }
            locked[r as usize] = true;
            locked[s as usize] = true;
            any = true;
        }
        let mut k = 0;
        f.retain(|_| {
            k += 1;
            !dead[k - 1]
        });
        if !any {
            return;
        }
    }
}

fn flip(v: &[V3], f: &mut [[u32; 3]], sharp: &HashSet<Edge>) {
    let map = edge_tris(f);
    let mut valence = vec![0i32; v.len()];
    let mut boundary = vec![false; v.len()];
    for (&(a, b), tris) in &map {
        valence[a as usize] += 1;
        valence[b as usize] += 1;
        if tris.len() == 1 {
            boundary[a as usize] = true;
            boundary[b as usize] = true;
        }
    }
    let ideal = |i: u32, boundary: &Vec<bool>| if boundary[i as usize] { 4 } else { 6 };
    let mut edges: Vec<Edge> = map.keys().copied().collect();
    edges.sort_unstable();
    let mut existing: HashSet<Edge> = map.keys().copied().collect();
    let mut touched = vec![false; f.len()];
    for (a, b) in edges {
        let tris = &map[&(a, b)];
        if tris.len() != 2 || sharp.contains(&(a, b)) || touched[tris[0]] || touched[tris[1]] {
            continue;
        }
        let (t1, t2) = (tris[0], tris[1]);
        let opposite = |t: usize| f[t].iter().copied().find(|&x| x != a && x != b).unwrap();
        let (c, d) = (opposite(t1), opposite(t2));
        if c == d || existing.contains(&key(c, d)) {
            continue;
        }
        let dev = |i: u32, delta: i32| {
            let x = valence[i as usize] + delta - ideal(i, &boundary);
            x * x
        };
        let before = dev(a, 0) + dev(b, 0) + dev(c, 0) + dev(d, 0);
        let after = dev(a, -1) + dev(b, -1) + dev(c, 1) + dev(d, 1);
        if after >= before {
            continue;
        }
        // Orient: t1 runs x→y with c opposite, so the quad is x, d, y, c.
        let tri = f[t1];
        let r = (0..3).find(|&k| tri[(k + 2) % 3] == c).unwrap();
        let (x, y) = (tri[r], tri[(r + 1) % 3]);
        let n1 = [x, d, c];
        let n2 = [d, y, c];
        let old = (normal(v, f[t1]) + normal(v, f[t2])).normalized();
        let ok = [n1, n2].iter().all(|&t| {
            let n = normal(v, t);
            n.norm() > 1e-14 && n.normalized().dot(old) > 0.3
        });
        if !ok {
            continue;
        }
        f[t1] = n1;
        f[t2] = n2;
        touched[t1] = true;
        touched[t2] = true;
        existing.remove(&(a, b));
        existing.insert(key(c, d));
        valence[a as usize] -= 1;
        valence[b as usize] -= 1;
        valence[c as usize] += 1;
        valence[d as usize] += 1;
    }
}

fn relax(v: &mut [V3], f: &[[u32; 3]], sharp: &HashSet<Edge>, projector: &Projector) {
    let fv = feature_valence(v.len(), sharp);
    let mut neighbours: Vec<Vec<u32>> = vec![Vec::new(); v.len()];
    let mut n = vec![V3::ZERO; v.len()];
    for tri in f {
        let fnorm = normal(v, *tri);
        for k in 0..3 {
            neighbours[tri[k] as usize].push(tri[(k + 1) % 3]);
            n[tri[k] as usize] += fnorm;
        }
    }
    let old = v.to_vec();
    for i in 0..v.len() {
        if fv[i] != 0 || neighbours[i].is_empty() {
            continue;
        }
        let c = neighbours[i].iter().fold(V3::ZERO, |acc, &j| acc + old[j as usize]) / neighbours[i].len() as f64;
        let ni = n[i].normalized();
        let step = c - old[i];
        let moved = old[i] + step - ni * step.dot(ni);
        v[i] = projector.closest(moved).0;
    }
}

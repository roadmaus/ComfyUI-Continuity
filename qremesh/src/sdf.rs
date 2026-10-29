//! Shapes from signed distance fields, triangulated by marching tetrahedra.
//!
//! These stand in for real inputs: limbs, necks, ears and handles, and a
//! triangulation that knows nothing about the surface — slivers and wildly
//! varying edge lengths, as a lifted or scanned mesh has. They are what the
//! input remesh will be measured on.

use crate::math::{v3, V3};
use crate::mesh::TriMesh;
use std::collections::HashMap;

fn sphere(p: V3, c: V3, r: f64) -> f64 {
    (p - c).norm() - r
}

fn capsule(p: V3, a: V3, b: V3, r: f64) -> f64 {
    let (pa, ba) = (p - a, b - a);
    let h = (pa.dot(ba) / ba.dot(ba)).clamp(0.0, 1.0);
    (pa - ba * h).norm() - r
}

/// A bound, not an exact distance, but close enough near the surface.
fn ellipsoid(p: V3, c: V3, r: V3) -> f64 {
    let q = p - c;
    let k = v3(q.x / r.x, q.y / r.y, q.z / r.z).norm();
    (k - 1.0) * r.x.min(r.y).min(r.z)
}

fn torus_xy(p: V3, c: V3, major: f64, minor: f64) -> f64 {
    let q = p - c;
    let ring = (q.x * q.x + q.y * q.y).sqrt() - major;
    (ring * ring + q.z * q.z).sqrt() - minor
}

/// Union with a fillet of about `k`, so joints are smooth necks rather
/// than creases.
fn smooth_min(a: f64, b: f64, k: f64) -> f64 {
    let h = (0.5 + 0.5 * (b - a) / k).clamp(0.0, 1.0);
    b * (1.0 - h) + a * h - k * h * (1.0 - h)
}

/// A four-legged animal: body, head and snout, ears, legs, a tail.
pub fn creature(p: V3) -> f64 {
    let k = 0.12;
    let mut d = ellipsoid(p, v3(0.0, 0.0, 0.6), v3(0.9, 0.45, 0.4));
    d = smooth_min(d, sphere(p, v3(1.05, 0.0, 1.0), 0.33), k);
    d = smooth_min(d, capsule(p, v3(1.2, 0.0, 0.95), v3(1.45, 0.0, 0.86), 0.15), 0.08);
    for side in [-1.0, 1.0] {
        d = smooth_min(d, capsule(p, v3(1.0, 0.17 * side, 1.25), v3(0.93, 0.27 * side, 1.52), 0.07), 0.06);
        for x in [-0.55, 0.55] {
            d = smooth_min(d, capsule(p, v3(x, 0.24 * side, 0.45), v3(x * 1.08, 0.28 * side, -0.3), 0.12), k);
        }
    }
    smooth_min(d, capsule(p, v3(-0.85, 0.0, 0.75), v3(-1.35, 0.0, 1.15), 0.07), 0.08)
}

/// Two tori fused side by side: genus two.
pub fn pretzel(p: V3) -> f64 {
    let a = torus_xy(p, v3(-0.75, 0.0, 0.0), 0.75, 0.28);
    let b = torus_xy(p, v3(0.75, 0.0, 0.0), 0.75, 0.28);
    smooth_min(a, b, 0.15)
}

/// The zero set of `f` inside the box `lo`..`hi`, sampled on a grid of
/// `res` cells along the longest side, outward-facing.
pub fn mesh(f: fn(V3) -> f64, lo: V3, hi: V3, res: usize) -> TriMesh {
    let span = hi - lo;
    let h = span.x.max(span.y).max(span.z) / res as f64;
    let n = [(span.x / h).ceil() as usize + 1, (span.y / h).ceil() as usize + 1, (span.z / h).ceil() as usize + 1];
    let at = |i: usize, j: usize, k: usize| lo + v3(i as f64 * h, j as f64 * h, k as f64 * h);
    let id = |i: usize, j: usize, k: usize| (i * n[1] + j) * n[2] + k;
    let mut value = vec![0.0; n[0] * n[1] * n[2]];
    for i in 0..n[0] {
        for j in 0..n[1] {
            for k in 0..n[2] {
                let v = f(at(i, j, k));
                // A sample exactly on the surface would make zero-area
                // triangles; nudge it to one side.
                value[id(i, j, k)] = if v == 0.0 { 1e-12 } else { v };
            }
        }
    }

    let mut verts: Vec<V3> = Vec::new();
    let mut on_edge: HashMap<(usize, usize), u32> = HashMap::new();
    let mut tris: Vec<[u32; 3]> = Vec::new();
    // The six tetrahedra of a cube along its main diagonal (Kuhn), the same
    // in every cube, so neighbouring cubes agree on shared faces.
    let corner = |c: usize| (c & 1, (c >> 1) & 1, (c >> 2) & 1);
    let orders = [[1, 2, 4], [1, 4, 2], [2, 1, 4], [2, 4, 1], [4, 1, 2], [4, 2, 1]];
    for i in 0..n[0] - 1 {
        for j in 0..n[1] - 1 {
            for k in 0..n[2] - 1 {
                for order in orders {
                    let cs = [0, order[0], order[0] + order[1], 7];
                    let g: Vec<usize> = cs
                        .iter()
                        .map(|&c| {
                            let (a, b, d) = corner(c);
                            id(i + a, j + b, k + d)
                        })
                        .collect();
                    let inside: Vec<usize> = (0..4).filter(|&t| value[g[t]] < 0.0).collect();
                    if inside.is_empty() || inside.len() == 4 {
                        continue;
                    }
                    let outside: Vec<usize> = (0..4).filter(|&t| value[g[t]] >= 0.0).collect();
                    let mut point = |a: usize, b: usize| -> u32 {
                        let (ga, gb) = (g[a], g[b]);
                        let key = (ga.min(gb), ga.max(gb));
                        *on_edge.entry(key).or_insert_with(|| {
                            let pos = |g: usize| {
                                let kk = g % n[2];
                                let jj = (g / n[2]) % n[1];
                                let ii = g / (n[1] * n[2]);
                                at(ii, jj, kk)
                            };
                            let (va, vb) = (value[ga], value[gb]);
                            let t = va / (va - vb);
                            verts.push(pos(ga) + (pos(gb) - pos(ga)) * t);
                            (verts.len() - 1) as u32
                        })
                    };
                    match inside.len() {
                        1 | 3 => {
                            let (lone, rest) = if inside.len() == 1 { (inside[0], outside) } else { (outside[0], inside) };
                            let t = [point(lone, rest[0]), point(lone, rest[1]), point(lone, rest[2])];
                            tris.push(t);
                        }
                        _ => {
                            let (a, b) = (inside[0], inside[1]);
                            let (c, d) = (outside[0], outside[1]);
                            let q = [point(a, c), point(a, d), point(b, d), point(b, c)];
                            tris.push([q[0], q[1], q[2]]);
                            tris.push([q[0], q[2], q[3]]);
                        }
                    }
                }
            }
        }
    }

    // Wind every triangle to face up the field's gradient, i.e. outward.
    let grad = |p: V3| {
        let e = h * 0.25;
        v3(
            f(p + v3(e, 0.0, 0.0)) - f(p - v3(e, 0.0, 0.0)),
            f(p + v3(0.0, e, 0.0)) - f(p - v3(0.0, e, 0.0)),
            f(p + v3(0.0, 0.0, e)) - f(p - v3(0.0, 0.0, e)),
        )
    };
    let mut kept = Vec::with_capacity(tris.len());
    for t in tris {
        let (a, b, c) = (verts[t[0] as usize], verts[t[1] as usize], verts[t[2] as usize]);
        let normal = (b - a).cross(c - a);
        if t[0] == t[1] || t[1] == t[2] || t[0] == t[2] {
            continue;
        }
        kept.push(if normal.dot(grad((a + b + c) / 3.0)) < 0.0 { [t[0], t[2], t[1]] } else { t });
    }
    TriMesh { v: verts, f: kept }
}

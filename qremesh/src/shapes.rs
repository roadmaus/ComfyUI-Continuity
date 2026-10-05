//! Test shapes, each chosen for what it asks of a remesher.
//!
//! - **icosphere**: no features, no preferred direction. The field must find
//!   its eight singularities on its own, and a good layout is a cube.
//! - **cube**: sharp edges everywhere. The field must follow them and the
//!   layout must be the six faces.
//! - **torus**: no singularities at all (its Euler characteristic is zero),
//!   strong curvature directions. Separatrices alone cannot cut it into
//!   disks.
//! - **blob**: a lumpy, stretched, tilted sphere. Curvature directions in
//!   some places, none in others, and nothing lined up with the axes — the
//!   field's singularities land wherever they land, and the layout has to
//!   make do with them.

use crate::math::{v3, Rng, V3};
use crate::mesh::TriMesh;
use std::collections::HashMap;
use std::f64::consts::PI;

pub fn icosphere(subdivisions: usize) -> TriMesh {
    let t = (1.0 + 5f64.sqrt()) / 2.0;
    let mut v: Vec<V3> = [
        (-1.0, t, 0.0), (1.0, t, 0.0), (-1.0, -t, 0.0), (1.0, -t, 0.0),
        (0.0, -1.0, t), (0.0, 1.0, t), (0.0, -1.0, -t), (0.0, 1.0, -t),
        (t, 0.0, -1.0), (t, 0.0, 1.0), (-t, 0.0, -1.0), (-t, 0.0, 1.0),
    ]
    .iter()
    .map(|&(x, y, z)| v3(x, y, z).normalized())
    .collect();
    let mut f: Vec<[u32; 3]> = vec![
        [0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11],
        [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6], [7, 1, 8],
        [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9],
        [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1],
    ];
    for _ in 0..subdivisions {
        let mut middle: HashMap<(u32, u32), u32> = HashMap::new();
        let mut mid = |a: u32, b: u32, v: &mut Vec<V3>| {
            *middle.entry((a.min(b), a.max(b))).or_insert_with(|| {
                v.push(((v[a as usize] + v[b as usize]) * 0.5).normalized());
                (v.len() - 1) as u32
            })
        };
        let mut next = Vec::with_capacity(f.len() * 4);
        for &[a, b, c] in &f {
            let (ab, bc, ca) = (mid(a, b, &mut v), mid(b, c, &mut v), mid(c, a, &mut v));
            next.extend([[a, ab, ca], [b, bc, ab], [c, ca, bc], [ab, bc, ca]]);
        }
        f = next;
    }
    TriMesh { v, f }
}

/// An icosphere pushed in and out by a few slow waves, stretched to
/// 1.4 × 1 × 0.75 and tilted, all from `seed`.
pub fn blob(subdivisions: usize, seed: u64) -> TriMesh {
    let mut m = icosphere(subdivisions);
    let mut rng = Rng::new(seed);
    let random_unit = |rng: &mut Rng| loop {
        let d = v3(rng.unit() - 0.5, rng.unit() - 0.5, rng.unit() - 0.5);
        if d.norm() > 0.1 && d.norm() < 0.5 {
            return d.normalized();
        }
    };
    let waves: Vec<(V3, f64, f64)> =
        (0..4).map(|_| (random_unit(&mut rng), 1.5 + 2.0 * rng.unit(), 2.0 * PI * rng.unit())).collect();
    let tilt = (random_unit(&mut rng), 0.35 + 0.4 * rng.unit());
    let (axis, angle) = tilt;
    for p in m.v.iter_mut() {
        let r = 1.0 + waves.iter().map(|&(d, f, phase)| 0.07 * (f * p.dot(d) + phase).sin()).sum::<f64>();
        let q = *p * r;
        let q = v3(q.x * 1.4, q.y, q.z * 0.75);
        // Rodrigues: turn by `angle` about `axis`.
        *p = q * angle.cos() + axis.cross(q) * angle.sin() + axis * axis.dot(q) * (1.0 - angle.cos());
    }
    m
}

/// The cube [-1, 1]³, each face an `n`×`n` grid, welded along the edges.
pub fn cube(n: usize) -> TriMesh {
    let x = v3(1.0, 0.0, 0.0);
    let y = v3(0.0, 1.0, 0.0);
    let z = v3(0.0, 0.0, 1.0);
    // (normal, u, v) with u × v = normal, so the grid winds outward.
    let faces = [(x, y, z), (-x, z, y), (y, z, x), (-y, x, z), (z, x, y), (-z, y, x)];
    let mut index: HashMap<(i64, i64, i64), u32> = HashMap::new();
    let mut v = Vec::new();
    let mut f = Vec::new();
    for (normal, u, w) in faces {
        let mut id = vec![vec![0u32; n + 1]; n + 1];
        for (i, row) in id.iter_mut().enumerate() {
            for (j, slot) in row.iter_mut().enumerate() {
                let s = 2.0 * i as f64 / n as f64 - 1.0;
                let t = 2.0 * j as f64 / n as f64 - 1.0;
                let p = normal + u * s + w * t;
                let key = ((p.x * 1e6).round() as i64, (p.y * 1e6).round() as i64, (p.z * 1e6).round() as i64);
                *slot = *index.entry(key).or_insert_with(|| {
                    v.push(p);
                    (v.len() - 1) as u32
                });
            }
        }
        for i in 0..n {
            for j in 0..n {
                let (a, b, c, d) = (id[i][j], id[i + 1][j], id[i + 1][j + 1], id[i][j + 1]);
                if (i + j) % 2 == 0 {
                    f.push([a, b, c]);
                    f.push([a, c, d]);
                } else {
                    f.push([a, b, d]);
                    f.push([b, c, d]);
                }
            }
        }
    }
    TriMesh { v, f }
}

pub fn torus(major: f64, minor: f64, nu: usize, nv: usize) -> TriMesh {
    let mut v = Vec::with_capacity(nu * nv);
    for i in 0..nu {
        let a = 2.0 * PI * i as f64 / nu as f64;
        for j in 0..nv {
            let b = 2.0 * PI * j as f64 / nv as f64;
            v.push(v3((major + minor * b.cos()) * a.cos(), (major + minor * b.cos()) * a.sin(), minor * b.sin()));
        }
    }
    let at = |i: usize, j: usize| ((i % nu) * nv + j % nv) as u32;
    let mut f = Vec::new();
    for i in 0..nu {
        for j in 0..nv {
            let (a, b, c, d) = (at(i, j), at(i + 1, j), at(i + 1, j + 1), at(i, j + 1));
            if (i + j) % 2 == 0 {
                f.push([a, b, c]);
                f.push([a, c, d]);
            } else {
                f.push([a, b, d]);
                f.push([b, c, d]);
            }
        }
    }
    TriMesh { v, f }
}

/// Move every vertex along its tangent plane by up to `amount` of the mean
/// edge, so the triangulation stops hinting at any direction. Vertices on
/// sharp edges stay put — moving them would round the feature off.
pub fn jitter(m: &mut TriMesh, amount: f64, seed: u64) {
    let (n, _) = crate::mesh::normals_areas(m);
    let edge = crate::mesh::mean_edge(m);
    let mut faces_at: Vec<Vec<V3>> = vec![Vec::new(); m.v.len()];
    for t in &m.f {
        let (p0, p1, p2) = (m.v[t[0] as usize], m.v[t[1] as usize], m.v[t[2] as usize]);
        let fnorm = (p1 - p0).cross(p2 - p0).normalized();
        for &i in t {
            faces_at[i as usize].push(fnorm);
        }
    }
    let mut rng = Rng::new(seed);
    for i in 0..m.v.len() {
        if faces_at[i].iter().any(|fnorm| fnorm.dot(n[i]) < 0.98) {
            continue;
        }
        let t1 = V3::tangent_of(n[i]);
        let t2 = n[i].cross(t1);
        m.v[i] += (t1 * (rng.unit() - 0.5) + t2 * (rng.unit() - 0.5)) * (amount * edge);
    }
}

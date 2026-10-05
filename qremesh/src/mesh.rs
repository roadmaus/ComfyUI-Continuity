//! Triangle meshes in and polygon meshes out: OBJ reading and writing, vertex
//! normals and areas, adjacency, and the test sphere.

use crate::math::{v3, Rng, V3};
use std::f64::consts::PI;
use std::io::Write;

pub struct TriMesh {
    pub v: Vec<V3>,
    pub f: Vec<[u32; 3]>,
}

/// Positions and faces from an OBJ. Polygons are fanned into triangles;
/// texture and normal indices (`f 1/2/3`) are ignored, negative indices are
/// resolved against the vertices read so far.
pub fn read_obj(path: &str) -> Result<TriMesh, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("{path}: {e}"))?;
    let mut v = Vec::new();
    let mut f = Vec::new();
    for (number, line) in text.lines().enumerate() {
        let at = || format!("{path}:{}", number + 1);
        let mut words = line.split_whitespace();
        match words.next() {
            Some("v") => {
                let c: Vec<f64> = words
                    .take(3)
                    .map(str::parse)
                    .collect::<Result<_, _>>()
                    .map_err(|e| format!("{}: {e}", at()))?;
                if c.len() < 3 {
                    return Err(format!("{}: a vertex needs three coordinates", at()));
                }
                v.push(v3(c[0], c[1], c[2]));
            }
            Some("f") => {
                let mut corners = Vec::new();
                for word in words {
                    let first = word.split('/').next().unwrap_or("");
                    let i: i64 = first.parse().map_err(|e| format!("{}: {e}", at()))?;
                    let k = if i < 0 { v.len() as i64 + i } else { i - 1 };
                    if k < 0 || k >= v.len() as i64 {
                        return Err(format!("{}: vertex {i} does not exist", at()));
                    }
                    corners.push(k as u32);
                }
                for t in 1..corners.len().saturating_sub(1) {
                    f.push([corners[0], corners[t], corners[t + 1]]);
                }
            }
            _ => {}
        }
    }
    if f.is_empty() {
        return Err(format!("{path}: no faces"));
    }
    Ok(TriMesh { v, f })
}

pub fn write_obj(path: &str, v: &[V3], faces: &[Vec<u32>]) -> Result<(), String> {
    let file = std::fs::File::create(path).map_err(|e| format!("{path}: {e}"))?;
    let mut out = std::io::BufWriter::new(file);
    let mut write = || -> std::io::Result<()> {
        writeln!(out, "# qremesh")?;
        for p in v {
            writeln!(out, "v {:.6} {:.6} {:.6}", p.x, p.y, p.z)?;
        }
        for face in faces {
            write!(out, "f")?;
            for &i in face {
                write!(out, " {}", i + 1)?;
            }
            writeln!(out)?;
        }
        out.flush()
    };
    write().map_err(|e| format!("{path}: {e}"))
}

/// Area-weighted vertex normals, and each vertex's share (a third) of the area
/// of the triangles around it.
pub fn normals_areas(m: &TriMesh) -> (Vec<V3>, Vec<f64>) {
    let mut n = vec![V3::ZERO; m.v.len()];
    let mut a = vec![0.0; m.v.len()];
    for t in &m.f {
        let (p0, p1, p2) = (m.v[t[0] as usize], m.v[t[1] as usize], m.v[t[2] as usize]);
        let c = (p1 - p0).cross(p2 - p0);
        let area = 0.5 * c.norm();
        for &i in t {
            n[i as usize] += c;
            a[i as usize] += area / 3.0;
        }
    }
    for x in n.iter_mut() {
        *x = x.normalized();
    }
    (n, a)
}

/// Each vertex's neighbours along triangle edges, sorted and without repeats.
pub fn adjacency(nv: usize, f: &[[u32; 3]]) -> Vec<Vec<u32>> {
    let mut adj = vec![Vec::new(); nv];
    for t in f {
        for k in 0..3 {
            let (a, b) = (t[k], t[(k + 1) % 3]);
            adj[a as usize].push(b);
            adj[b as usize].push(a);
        }
    }
    for list in adj.iter_mut() {
        list.sort_unstable();
        list.dedup();
    }
    adj
}

pub fn surface_area(m: &TriMesh) -> f64 {
    m.f.iter()
        .map(|t| {
            let (p0, p1, p2) = (m.v[t[0] as usize], m.v[t[1] as usize], m.v[t[2] as usize]);
            0.5 * (p1 - p0).cross(p2 - p0).norm()
        })
        .sum()
}

pub fn mean_edge(m: &TriMesh) -> f64 {
    let mut total = 0.0;
    for t in &m.f {
        for k in 0..3 {
            total += (m.v[t[k] as usize] - m.v[t[(k + 1) % 3] as usize]).norm();
        }
    }
    total / (3 * m.f.len()) as f64
}

/// A unit UV sphere, triangulated: fans at the poles, split quads between.
///
/// The worst kind of input a remesher meets on a closed surface — slivers at
/// the poles, a strong grain along the meridians — which is why it is the
/// test. `jitter` (a fraction of the ring spacing) pushes every vertex
/// sideways along the surface to break the grain further, the way a lifted
/// mesh has no grain at all.
pub fn uv_sphere(rings: usize, segments: usize, jitter: f64, seed: u64) -> TriMesh {
    let mut v = vec![v3(0.0, 0.0, 1.0)];
    for k in 1..rings {
        let theta = PI * k as f64 / rings as f64;
        for s in 0..segments {
            let phi = 2.0 * PI * s as f64 / segments as f64;
            v.push(v3(theta.sin() * phi.cos(), theta.sin() * phi.sin(), theta.cos()));
        }
    }
    v.push(v3(0.0, 0.0, -1.0));
    let south = (v.len() - 1) as u32;
    let ring = |k: usize, s: usize| (1 + (k - 1) * segments + s % segments) as u32;

    let mut f = Vec::new();
    for s in 0..segments {
        f.push([0, ring(1, s), ring(1, s + 1)]);
    }
    for k in 1..rings - 1 {
        for s in 0..segments {
            let (a0, a1, b0, b1) = (ring(k, s), ring(k, s + 1), ring(k + 1, s), ring(k + 1, s + 1));
            f.push([a0, b0, b1]);
            f.push([a0, b1, a1]);
        }
    }
    for s in 0..segments {
        f.push([ring(rings - 1, s), south, ring(rings - 1, s + 1)]);
    }

    if jitter > 0.0 {
        let mut rng = Rng::new(seed);
        let step = PI / rings as f64;
        for p in v.iter_mut().take(south as usize).skip(1) {
            let t1 = V3::tangent_of(*p);
            let t2 = p.cross(t1);
            let d = (t1 * (rng.unit() - 0.5) + t2 * (rng.unit() - 0.5)) * (jitter * step);
            *p = (*p + d).normalized();
        }
    }
    TriMesh { v, f }
}

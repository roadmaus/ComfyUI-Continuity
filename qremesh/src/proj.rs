//! Closest points on a triangle mesh, through a grid of its triangles.

use crate::math::{v3, V3};
use crate::mesh::TriMesh;
use std::collections::HashMap;

pub struct Projector<'a> {
    m: &'a TriMesh,
    cell: f64,
    lo: V3,
    grid: HashMap<(i64, i64, i64), Vec<u32>>,
}

/// The point of triangle (a, b, c) closest to p. Ericson, Real-Time
/// Collision Detection, 5.1.5.
pub fn closest_on_triangle(p: V3, a: V3, b: V3, c: V3) -> V3 {
    let (ab, ac, ap) = (b - a, c - a, p - a);
    let (d1, d2) = (ab.dot(ap), ac.dot(ap));
    if d1 <= 0.0 && d2 <= 0.0 {
        return a;
    }
    let bp = p - b;
    let (d3, d4) = (ab.dot(bp), ac.dot(bp));
    if d3 >= 0.0 && d4 <= d3 {
        return b;
    }
    let vc = d1 * d4 - d3 * d2;
    if vc <= 0.0 && d1 >= 0.0 && d3 <= 0.0 {
        return a + ab * (d1 / (d1 - d3));
    }
    let cp = p - c;
    let (d5, d6) = (ab.dot(cp), ac.dot(cp));
    if d6 >= 0.0 && d5 <= d6 {
        return c;
    }
    let vb = d5 * d2 - d1 * d6;
    if vb <= 0.0 && d2 >= 0.0 && d6 <= 0.0 {
        return a + ac * (d2 / (d2 - d6));
    }
    let va = d3 * d6 - d5 * d4;
    if va <= 0.0 && (d4 - d3) >= 0.0 && (d5 - d6) >= 0.0 {
        return b + (c - b) * ((d4 - d3) / ((d4 - d3) + (d5 - d6)));
    }
    let denom = 1.0 / (va + vb + vc);
    a + ab * (vb * denom) + ac * (vc * denom)
}

impl<'a> Projector<'a> {
    pub fn new(m: &'a TriMesh, cell: f64) -> Projector<'a> {
        let lo = m.v.iter().fold(m.v[0], |a, p| v3(a.x.min(p.x), a.y.min(p.y), a.z.min(p.z)));
        let mut grid: HashMap<(i64, i64, i64), Vec<u32>> = HashMap::new();
        let key = |p: V3| (((p.x - lo.x) / cell).floor() as i64, ((p.y - lo.y) / cell).floor() as i64, ((p.z - lo.z) / cell).floor() as i64);
        for (t, tri) in m.f.iter().enumerate() {
            let ps = tri.map(|i| m.v[i as usize]);
            let a = key(v3(ps[0].x.min(ps[1].x).min(ps[2].x), ps[0].y.min(ps[1].y).min(ps[2].y), ps[0].z.min(ps[1].z).min(ps[2].z)));
            let b = key(v3(ps[0].x.max(ps[1].x).max(ps[2].x), ps[0].y.max(ps[1].y).max(ps[2].y), ps[0].z.max(ps[1].z).max(ps[2].z)));
            for x in a.0..=b.0 {
                for y in a.1..=b.1 {
                    for z in a.2..=b.2 {
                        grid.entry((x, y, z)).or_default().push(t as u32);
                    }
                }
            }
        }
        Projector { m, cell, lo, grid }
    }

    /// The closest point of the mesh to `p`, and its distance.
    pub fn closest(&self, p: V3) -> (V3, f64) {
        let (q, d, _) = self.closest_tri(p);
        (q, d)
    }

    /// The closest point, its distance, and the triangle it is on.
    pub fn closest_tri(&self, p: V3) -> (V3, f64, u32) {
        let c = (((p.x - self.lo.x) / self.cell).floor() as i64, ((p.y - self.lo.y) / self.cell).floor() as i64, ((p.z - self.lo.z) / self.cell).floor() as i64);
        let mut best: Option<(f64, V3, u32)> = None;
        // Rings of cells outward, until the nearest point found is closer
        // than anything a further ring could hold.
        for ring in 0..64i64 {
            if let Some((d, _, _)) = best {
                if d <= (ring as f64 - 1.0).max(0.0) * self.cell {
                    break;
                }
            }
            for x in c.0 - ring..=c.0 + ring {
                for y in c.1 - ring..=c.1 + ring {
                    for z in c.2 - ring..=c.2 + ring {
                        let on_ring = (x - c.0).abs() == ring || (y - c.1).abs() == ring || (z - c.2).abs() == ring;
                        if !on_ring {
                            continue;
                        }
                        let Some(tris) = self.grid.get(&(x, y, z)) else { continue };
                        for &t in tris {
                            let [a, b, cc] = self.m.f[t as usize].map(|i| self.m.v[i as usize]);
                            let q = closest_on_triangle(p, a, b, cc);
                            let d = (q - p).norm();
                            if best.map_or(true, |(bd, _, _)| d < bd) {
                                best = Some((d, q, t));
                            }
                        }
                    }
                }
            }
        }
        best.map(|(d, q, t)| (q, d, t)).unwrap_or((p, f64::INFINITY, 0))
    }
}

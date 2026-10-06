//! How large a quad should be at each point of the surface.
//!
//! A uniform quad size spends the budget by area, and a part thinner than
//! one quad (an ear, a horn, a finger) cannot be drawn at all: its whole
//! girth is less than an edge. A sculptor's remesher puts small quads on
//! such parts and pays for them with larger ones on the broad, flat ones.
//! The size here follows the tighter of the two principal curvatures: 0.8
//! of the radius, which is eight quads round a tube. It is kept within
//! `adapt` times of its largest value, kept from changing faster than a
//! third of the distance walked (so sizes grade instead of jumping, and a
//! thin part's small quads reach a little way onto what it grows from),
//! and scaled so the whole surface still holds the quads asked for.
//!
//! Everything downstream reads lengths through it: the premesh keeps its
//! triangles a fixed share of the local quad, the layout judges distances
//! and slivers in local quads, the quantizer counts an arc's edges as the
//! integral of 1/size along it, and the final smoothing keeps the grading.

use crate::cross;
use crate::math::V3;
use crate::mesh::{self, TriMesh};
use crate::proj::Projector;

pub struct Sizing<'a> {
    m: &'a TriMesh,
    proj: Projector<'a>,
    /// The quad side at each vertex of `m`.
    h: Vec<f64>,
    /// The side the curvature there asks for, whatever the budget allows.
    wanted: Vec<f64>,
    /// The side of a quad were they all one size.
    pub uniform: f64,
}

/// Quad sides per radius of curvature: 2π / 0.8 ≈ 8 quads round a tube.
const PER_RADIUS: f64 = 0.8;
/// The most the size may change per unit of distance.
const GRADING: f64 = 0.35;

impl<'a> Sizing<'a> {
    /// Sizes for `quads` quads on `m`, the smallest no less than 1/`adapt`
    /// of the largest. `adapt` ≤ 1 is one size everywhere. Edges sharper
    /// than `degrees` are creases, not curvature.
    pub fn new(m: &'a TriMesh, quads: f64, adapt: f64, degrees: f64) -> Sizing<'a> {
        let area = mesh::surface_area(m);
        let uniform = (area / quads).sqrt();
        let proj = Projector::new(m, mesh::mean_edge(m) * 2.0);
        let s = cross::Surface::new(m);
        // The tighter curvature, averaged with the neighbours' twice: one
        // vertex's fit on a noisy scan is not a part of the shape.
        //
        // A crease has no radius: the fit across a cube's edge reads as a
        // bend as tight as the triangles are small, and would spend the
        // budget along every edge of a machined part. Vertices on feature
        // lines say nothing, and take their size from what is beside them.
        let (_, sharp) = cross::feature_constraints(&s, degrees);
        // Their neighbours neither: those are fitted across the crease too.
        let mut crease = vec![false; m.v.len()];
        for &(a, b) in &sharp {
            for v in [a, b] {
                crease[v as usize] = true;
                for &w in &s.adj[v as usize] {
                    crease[w as usize] = true;
                }
            }
        }
        let mut k: Vec<f64> = (0..m.v.len()).map(|i| if crease[i] { 0.0 } else { cross::principal(&s, i).map_or(0.0, |(k1, k2, _)| k1.abs().max(k2.abs())) }).collect();
        for _ in 0..2 {
            k = (0..k.len())
                .map(|i| {
                    let (mut sum, mut weight) = (0.0, 0.0);
                    for j in std::iter::once(i).chain(s.adj[i].iter().map(|&j| j as usize)) {
                        if !crease[j] {
                            sum += k[j] * s.area[j];
                            weight += s.area[j];
                        }
                    }
                    if weight > 0.0 { sum / weight } else { k[i] }
                })
                .collect();
        }
        let wanted: Vec<f64> = k.iter().map(|&k| PER_RADIUS / k.max(1e-300)).collect();
        if adapt <= 1.0 {
            return Sizing { m, proj, h: vec![uniform; m.v.len()], wanted, uniform };
        }
        // The sizes for a given largest size, and how many quads they hold.
        let sizes = |largest: f64| -> (Vec<f64>, f64) {
            let mut h: Vec<f64> = wanted.iter().map(|&w| w.clamp(largest / adapt, largest)).collect();
            grade(&s, &mut h);
            let count = (0..h.len()).map(|i| s.area[i] / (h[i] * h[i])).sum();
            (h, count)
        };
        // More quads than asked at the uniform size (nothing is larger than
        // it), fewer at `adapt` times it (nothing is smaller): in between.
        let (mut lo, mut hi) = (uniform, uniform * adapt);
        for _ in 0..24 {
            let mid = (lo * hi).sqrt();
            if sizes(mid).1 > quads { lo = mid } else { hi = mid }
        }
        let h = sizes((lo * hi).sqrt()).0;
        Sizing { m, proj, h, wanted, uniform }
    }

    /// Whether the quads at `p` are too coarse for the surface there: more
    /// than twice the side its curvature asks for, fewer than four round a
    /// tube.
    pub fn coarse(&self, p: V3) -> bool {
        let (_, _, t) = self.proj.closest_tri(p);
        self.m.f[t as usize].iter().any(|&i| self.h[i as usize] > 2.0 * self.wanted[i as usize])
    }

    /// The quad side at `p`, read at the closest point of the surface.
    pub fn at(&self, p: V3) -> f64 {
        self.closest(p).1
    }

    /// The closest point of the surface to `p` and the quad side there.
    pub fn closest(&self, p: V3) -> (V3, f64) {
        let (q, _, t) = self.proj.closest_tri(p);
        let tri = self.m.f[t as usize];
        let [a, b, c] = tri.map(|i| self.m.v[i as usize]);
        let [ha, hb, hc] = tri.map(|i| self.h[i as usize]);
        // Barycentric coordinates of q.
        let (e0, e1, e2) = (b - a, c - a, q - a);
        let (d00, d01, d11, d20, d21) = (e0.dot(e0), e0.dot(e1), e1.dot(e1), e2.dot(e0), e2.dot(e1));
        let den = d00 * d11 - d01 * d01;
        if den.abs() < 1e-300 {
            return (q, ha);
        }
        let v = ((d11 * d20 - d01 * d21) / den).clamp(0.0, 1.0);
        let w = ((d00 * d21 - d01 * d20) / den).clamp(0.0, 1.0 - v);
        (q, ha * (1.0 - v - w) + hb * v + hc * w)
    }

    pub fn range(&self) -> (f64, f64) {
        self.h.iter().fold((f64::MAX, f64::MIN), |a, &h| (a.0.min(h), a.1.max(h)))
    }
}

/// Bring every size down to what its neighbours allow: no more than a
/// neighbour's plus `GRADING` times the distance to it. Smallest first, so
/// each vertex is settled once (Dijkstra).
fn grade(s: &cross::Surface, h: &mut [f64]) {
    use std::cmp::Reverse;
    let mut heap: std::collections::BinaryHeap<(Reverse<u64>, u32)> = (0..h.len()).map(|i| (Reverse(h[i].to_bits()), i as u32)).collect();
    while let Some((Reverse(bits), i)) = heap.pop() {
        let hi = f64::from_bits(bits);
        if hi > h[i as usize] {
            continue;
        }
        for &j in &s.adj[i as usize] {
            let limit = hi + GRADING * (s.p[j as usize] - s.p[i as usize]).norm();
            if limit < h[j as usize] {
                h[j as usize] = limit;
                heap.push((Reverse(limit.to_bits()), j));
            }
        }
    }
}

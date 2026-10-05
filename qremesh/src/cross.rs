//! A global cross field: the smoothest field of quad directions over the
//! whole surface, pulled toward the principal curvature directions and held
//! to sharp features.
//!
//! The method is Knöppel, Crane, Pinkall and Schröder, "Globally Optimal
//! Direction Fields" (2013). Each vertex holds one complex number in its own
//! tangent frame (see `cplx`). Smoothness is a quadratic energy over the
//! edges — how far each vertex's cross is from its neighbour's, carried
//! across the edge — so the smoothest field is the solution of one sparse
//! Hermitian linear system rather than thousands of local averaging sweeps.
//! That globality is the difference from Instant Meshes, and it is what keeps
//! singularities few and puts them where the surface wants them.

use crate::cplx::C;
use crate::math::{Rng, V3};
use crate::mesh::TriMesh;

pub struct Surface {
    pub p: Vec<V3>,
    pub n: Vec<V3>,
    /// Each vertex's tangent frame: `e1`, and `n × e1`.
    pub e1: Vec<V3>,
    pub area: Vec<f64>,
    pub adj: Vec<Vec<u32>>,
    /// `transport[i][k]`: what a cross at `adj[i][k]` reads as at `i`.
    pub transport: Vec<Vec<C>>,
    pub tris: Vec<[u32; 3]>,
}

/// Angle of `v` in the tangent frame (`e1`, `n × e1`).
pub fn angle_in(v: V3, n: V3, e1: V3) -> f64 {
    let w = v.project_tangent(n);
    w.dot(n.cross(e1)).atan2(w.dot(e1))
}

impl Surface {
    pub fn new(m: &TriMesh) -> Surface {
        let (n, area) = crate::mesh::normals_areas(m);
        let adj = crate::mesh::adjacency(m.v.len(), &m.f);
        let e1: Vec<V3> = n.iter().map(|&n| V3::tangent_of(n)).collect();
        // An edge's direction, read in both endpoints' frames: the difference
        // is how much the frames turn against each other along it (the
        // discrete Levi-Civita connection), times four for a cross.
        let transport = (0..m.v.len())
            .map(|i| {
                adj[i]
                    .iter()
                    .map(|&j| {
                        let j = j as usize;
                        let d = m.v[j] - m.v[i];
                        let ai = angle_in(d, n[i], e1[i]);
                        let aj = angle_in(d, n[j], e1[j]);
                        C::polar(1.0, 4.0 * (ai - aj))
                    })
                    .collect()
            })
            .collect();
        Surface { p: m.v.clone(), n, e1, area, adj, transport, tris: m.f.clone() }
    }

    /// The unit tangent vector of a cross's first arm at vertex `i`.
    pub fn arm(&self, i: usize, z: C) -> V3 {
        let a = z.arg() / 4.0;
        let e2 = self.n[i].cross(self.e1[i]);
        self.e1[i] * a.cos() + e2 * a.sin()
    }
}

// ------------------------------------------------------------------ inputs

/// Per vertex: the principal curvature direction as a cross, weighted by how
/// different the two curvatures are. Zero where the surface curves the same
/// way in every direction (a sphere, a plane), which is where curvature has
/// nothing to say about quad directions.
pub fn curvature_target(s: &Surface) -> Vec<C> {
    (0..s.p.len())
        .map(|i| {
            let (n, e1) = (s.n[i], s.e1[i]);
            let e2 = n.cross(e1);
            // Fit the shape operator S (symmetric 2×2: a b; b c) so that
            // S · (edge) ≈ (change of normal along the edge), least squares.
            let mut m = [[0.0f64; 3]; 3];
            let mut r = [0.0f64; 3];
            for &j in &s.adj[i] {
                let j = j as usize;
                let de = s.p[j] - s.p[i];
                let dn = s.n[j] - s.n[i];
                let (x, y) = (de.dot(e1), de.dot(e2));
                let (u, w) = (dn.dot(e1), dn.dot(e2));
                // Rows: [x y 0]·(a b c) = u and [0 x y]·(a b c) = w.
                for (row, rhs) in [([x, y, 0.0], u), ([0.0, x, y], w)] {
                    for a in 0..3 {
                        for b in 0..3 {
                            m[a][b] += row[a] * row[b];
                        }
                        r[a] += row[a] * rhs;
                    }
                }
            }
            let Some([a, b, c]) = solve3(m, r) else { return C::ZERO };
            // |k1 − k2|, and how much of the curvature it is. A sphere's
            // difference is pure noise from the triangulation; a cylinder's
            // is all of it. Only a clear difference earns a pull.
            let anisotropy = ((a - c) * (a - c) + 4.0 * b * b).sqrt();
            let k1 = 0.5 * (a + c + anisotropy);
            let k2 = 0.5 * (a + c - anisotropy);
            let share = anisotropy / (k1.abs() + k2.abs() + 1e-12);
            let trust = ((share - 0.25) / 0.35).clamp(0.0, 1.0);
            let trust = trust * trust * (3.0 - 2.0 * trust);
            let direction = 0.5 * (2.0 * b).atan2(a - c);
            C::polar(anisotropy * trust, 4.0 * direction)
        })
        .collect()
}

/// Per vertex: the cross the object's own axes draw on the surface — the
/// world axis closest to the normal is dropped and the other two, laid into
/// the tangent plane, are the cross. Where two axes tie (a normal like
/// (1, 1, 0)) either choice gives the same cross, so this field is smooth
/// everywhere except the eight points whose normals are (±1, ±1, ±1): a
/// sphere comes out with a cube's corners. It is what quads follow where
/// the surface itself has no preferred direction, which is how a sculptor's
/// retopology lines up a blob with the model's axes instead of at random.
pub fn axis_target(s: &Surface) -> Vec<C> {
    let axes = [V3 { x: 1.0, y: 0.0, z: 0.0 }, V3 { x: 0.0, y: 1.0, z: 0.0 }, V3 { x: 0.0, y: 0.0, z: 1.0 }];
    (0..s.p.len())
        .map(|i| {
            let n = s.n[i];
            let drop = (0..3).max_by(|&a, &b| n.dot(axes[a]).abs().total_cmp(&n.dot(axes[b]).abs())).unwrap();
            let keep = axes[(drop + 1) % 3];
            C::polar(1.0, 4.0 * angle_in(keep, n, s.e1[i]))
        })
        .collect()
}

/// Curvature where it is trusted, the axes elsewhere at `axes` of a full
/// pull. Curvature counts in absolute terms against the object's size: a
/// bend of radius an eighth of `diameter` is a full pull, flatter bends
/// proportionally less. (Scaled by its own peak it would turn the noise
/// on a flat surface into a full-strength random target.)
pub fn guide(s: &Surface, axes: f64, diameter: f64) -> Vec<C> {
    let curvature = curvature_target(s);
    let along_axes = axis_target(s);
    let full = 8.0 / diameter.max(1e-300);
    (0..s.p.len())
        .map(|i| {
            let strength = (curvature[i].abs() / full).min(1.0);
            let c = if curvature[i].abs() > 1e-300 { curvature[i].scale(strength / curvature[i].abs()) } else { C::ZERO };
            c + along_axes[i].scale(axes * (1.0 - strength))
        })
        .collect()
}

fn solve3(m: [[f64; 3]; 3], r: [f64; 3]) -> Option<[f64; 3]> {
    let det = |m: [[f64; 3]; 3]| {
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    };
    let d = det(m);
    if d.abs() < 1e-18 {
        return None;
    }
    let mut out = [0.0; 3];
    for (k, slot) in out.iter_mut().enumerate() {
        let mut mk = m;
        for row in 0..3 {
            mk[row][k] = r[row];
        }
        *slot = det(mk) / d;
    }
    Some(out)
}

/// Sharp edges: triangle pairs meeting at more than `degrees`.
/// -> per vertex, the cross its feature edges ask for, if they agree on one.
pub fn feature_constraints(s: &Surface, degrees: f64) -> (Vec<Option<C>>, Vec<(u32, u32)>) {
    let mut faces_of: std::collections::HashMap<(u32, u32), Vec<V3>> = Default::default();
    for t in &s.tris {
        let (p0, p1, p2) = (s.p[t[0] as usize], s.p[t[1] as usize], s.p[t[2] as usize]);
        let fnorm = (p1 - p0).cross(p2 - p0).normalized();
        for k in 0..3 {
            let (a, b) = (t[k], t[(k + 1) % 3]);
            faces_of.entry((a.min(b), a.max(b))).or_default().push(fnorm);
        }
    }
    // The surface's boundary is a feature too: the field runs along it
    // and traces stop on it.
    let limit = degrees.to_radians().cos();
    let mut sharp: Vec<(u32, u32)> = faces_of
        .iter()
        .filter(|(_, f)| f.len() == 1 || (f.len() == 2 && f[0].dot(f[1]) < limit))
        .map(|(&e, _)| e)
        .collect();
    sharp.sort_unstable();
    let mut sum = vec![C::ZERO; s.p.len()];
    let mut count = vec![0usize; s.p.len()];
    for &(a, b) in &sharp {
        for (i, j) in [(a, b), (b, a)] {
            let (i, j) = (i as usize, j as usize);
            let d = s.p[j] - s.p[i];
            sum[i] += C::polar(1.0, 4.0 * angle_in(d, s.n[i], s.e1[i]));
            count[i] += 1;
        }
    }
    // Where the feature edges at a vertex disagree — a cube's corner, where
    // three edges meet at a third of a turn — there is no one cross to ask
    // for; that vertex is left free and becomes a singularity.
    let fixed = (0..s.p.len())
        .map(|i| {
            if count[i] == 0 {
                return None;
            }
            let mean = sum[i].scale(1.0 / count[i] as f64);
            (mean.abs() > 0.8).then(|| mean.scale(1.0 / mean.abs()))
        })
        .collect();
    (fixed, sharp)
}

// ------------------------------------------------------------------- solve

/// (L + σM) x over the free vertices, with fixed vertices held at zero —
/// their contribution is moved to the right-hand side by `rhs_from_fixed`.
fn apply(s: &Surface, sigma: f64, fixed: &[Option<C>], x: &[C], y: &mut [C]) {
    for i in 0..s.p.len() {
        if fixed[i].is_some() {
            y[i] = C::ZERO;
            continue;
        }
        let mut acc = x[i].scale(s.adj[i].len() as f64 + sigma * s.area[i]);
        for (k, &j) in s.adj[i].iter().enumerate() {
            if fixed[j as usize].is_none() {
                acc -= s.transport[i][k] * x[j as usize];
            }
        }
        y[i] = acc;
    }
}

fn rhs_from_fixed(s: &Surface, fixed: &[Option<C>], b: &mut [C]) {
    for i in 0..s.p.len() {
        if fixed[i].is_some() {
            b[i] = C::ZERO;
            continue;
        }
        for (k, &j) in s.adj[i].iter().enumerate() {
            if let Some(z) = fixed[j as usize] {
                b[i] += s.transport[i][k] * z;
            }
        }
    }
}

fn dot(a: &[C], b: &[C]) -> f64 {
    // Re⟨a, b⟩ — enough for CG on a Hermitian system, whose ⟨p, Ap⟩ is real.
    a.iter().zip(b).map(|(x, y)| (x.conj() * *y).re).sum()
}

/// Preconditioned conjugate gradients on the Hermitian system. -> iterations.
fn cg(s: &Surface, sigma: f64, fixed: &[Option<C>], b: &[C], x: &mut [C], tol: f64, max: usize) -> usize {
    let n = x.len();
    let diag: Vec<f64> = (0..n).map(|i| s.adj[i].len() as f64 + sigma * s.area[i]).collect();
    let mut ax = vec![C::ZERO; n];
    apply(s, sigma, fixed, x, &mut ax);
    let mut r: Vec<C> = (0..n).map(|i| if fixed[i].is_some() { C::ZERO } else { b[i] - ax[i] }).collect();
    let mut z: Vec<C> = (0..n).map(|i| r[i].scale(1.0 / diag[i])).collect();
    let mut p = z.clone();
    let mut rz = dot(&r, &z);
    let b_norm = dot(b, b).sqrt().max(1e-300);
    let mut ap = vec![C::ZERO; n];
    for it in 0..max {
        if dot(&r, &r).sqrt() <= tol * b_norm {
            return it;
        }
        apply(s, sigma, fixed, &p, &mut ap);
        let alpha = rz / dot(&p, &ap);
        for i in 0..n {
            x[i] += p[i].scale(alpha);
            r[i] -= ap[i].scale(alpha);
            z[i] = r[i].scale(1.0 / diag[i]);
        }
        let rz_next = dot(&r, &z);
        let beta = rz_next / rz;
        rz = rz_next;
        for i in 0..n {
            p[i] = z[i] + p[i].scale(beta);
        }
    }
    max
}

pub struct Field {
    /// One unit cross per vertex.
    pub z: Vec<C>,
    pub solver_iterations: usize,
    pub how: &'static str,
}

/// The field. With features or curvature to follow: one solve of
/// (L + tM) x = tM q + (what the fixed vertices pull). With neither: the
/// smoothest field, the eigenvector of L with the smallest eigenvalue, by
/// inverse iteration.
///
/// `align` must be small: tM is a mass term, and a mass term screens what
/// the constraints and the field's own smoothness say over a length of
/// about √(1/align) edges. At 0.05 that was five edges — the "global"
/// field was local, a flat ring between two round boundaries grew four
/// pairs of singularities from a whisper of axis guide in its middle. At
/// 0.005 the reach is some fifteen edges, and a sphere, a torus, a ring and
/// a half sphere all come out with exactly the singularities they need.
pub fn solve(s: &Surface, target: &[C], fixed: &[Option<C>], align: f64, rng: &mut Rng) -> Field {
    let n = s.p.len();
    let mean_area = s.area.iter().sum::<f64>() / n as f64;
    let mean_degree = s.adj.iter().map(Vec::len).sum::<usize>() as f64 / n as f64;
    let target_weight = target.iter().map(|q| q.abs()).sum::<f64>() / n as f64;
    let constrained = fixed.iter().any(Option::is_some);
    let mut x = vec![C::ZERO; n];
    let mut total = 0;

    let how = if !constrained && target_weight * mean_area.sqrt() < 1e-3 {
        // No guide: inverse iteration toward the smoothest field.
        for xi in x.iter_mut() {
            *xi = C::polar(1.0, rng.unit() * std::f64::consts::TAU);
        }
        let shift = 1e-6 * mean_degree / mean_area;
        for _ in 0..30 {
            let b: Vec<C> = (0..n).map(|i| x[i].scale(s.area[i])).collect();
            let mut y = x.clone();
            total += cg(s, shift, fixed, &b, &mut y, 1e-6, 5000);
            let norm = y.iter().zip(&s.area).map(|(v, a)| v.abs2() * a).sum::<f64>().sqrt();
            x = y.iter().map(|v| v.scale(1.0 / norm)).collect();
        }
        "smoothest"
    } else {
        // The target's strongest pull is about 1 (`guide` scales it so);
        // it is weighted against smoothness by `align` in units of a
        // vertex's own stiffness. It is not rescaled here: on a flat
        // surface only the weak axis guide is left, and it must stay weak,
        // or it fights the boundary and makes singularities.
        let t = align * mean_degree / mean_area;
        let mut b: Vec<C> = (0..n).map(|i| target[i].scale(t * s.area[i])).collect();
        rhs_from_fixed(s, fixed, &mut b);
        total += cg(s, t, fixed, &b, &mut x, 1e-8, 20000);
        for i in 0..n {
            if let Some(z) = fixed[i] {
                x[i] = z;
            }
        }
        if constrained { "features + curvature" } else { "curvature" }
    };
    let z = x.iter().map(|v| if v.abs() > 1e-300 { v.scale(1.0 / v.abs()) } else { C::polar(1.0, 0.0) }).collect();
    Field { z, solver_iterations: total, how }
}

// ------------------------------------------------------------ singularities

pub struct Singularity {
    pub tri: usize,
    pub at: V3,
    /// Quarter turns the field makes around it: +1 (three separatrices, a
    /// vertex of valence three in the result) or −1 (five).
    pub index: i32,
}

/// Turns of the cross field around each triangle, from how far the field
/// rotates across each edge relative to the frames.
pub fn singularities(s: &Surface, z: &[C]) -> Vec<Singularity> {
    let lookup = |i: usize, j: usize| -> C {
        let k = s.adj[i].iter().position(|&x| x as usize == j).unwrap();
        s.transport[i][k]
    };
    let wrap = |a: f64| {
        let mut a = a % std::f64::consts::TAU;
        if a > std::f64::consts::PI {
            a -= std::f64::consts::TAU;
        }
        if a <= -std::f64::consts::PI {
            a += std::f64::consts::TAU;
        }
        a
    };
    let mut out = Vec::new();
    for (t, tri) in s.tris.iter().enumerate() {
        let [a, b, c] = tri.map(|x| x as usize);
        // Around the loop a→b→c→a: the field's change across each edge
        // (wrapped), plus the frames' own rotation (the connection). For a
        // smooth field the two cancel up to the triangle's curvature; a
        // singularity leaves a whole quarter turn (2π in the ×4 angle).
        let mut field_turn = 0.0;
        let mut frame_turn = 0.0;
        for (i, j) in [(a, b), (b, c), (c, a)] {
            let r = lookup(j, i); // carries a cross at i to j's frame
            field_turn += wrap(z[j].arg() - (r * z[i]).arg());
            frame_turn += wrap(r.arg());
        }
        let _ = frame_turn;
        let index = (field_turn / std::f64::consts::TAU).round() as i32;
        if index != 0 {
            let at = (s.p[a] + s.p[b] + s.p[c]) / 3.0;
            out.push(Singularity { tri: t, at, index });
        }
    }
    out
}

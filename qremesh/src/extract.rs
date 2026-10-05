//! From the two fields to a polygon mesh.
//!
//! Every input edge says how far apart its two vertices' lattice corners are,
//! counted in lattice steps. Zero steps means both vertices belong to the same
//! output vertex, so they are merged; one step means the two output vertices
//! are joined by an edge; anything else is a diagonal or a jump and says
//! nothing. The output faces are then the cycles of that graph, walked by
//! always turning the same way around each vertex.
//!
//! This is the simple version of extraction, without the paper's repairs —
//! no collapsing of near-duplicate vertices, no T-junction or hole fixing.
//! What it leaves broken is counted in the report rather than hidden.

use crate::field::{compat_orientation, compat_position};
use crate::math::V3;
use std::collections::{BTreeSet, HashMap};

pub struct Polygons {
    pub v: Vec<V3>,
    pub faces: Vec<Vec<u32>>,
    /// Edges of the graph the faces were walked on.
    pub edges: usize,
    /// Cycles longer than any face we keep: holes in the result.
    pub open_cycles: usize,
}

struct UnionFind(Vec<u32>);

impl UnionFind {
    fn find(&mut self, mut a: u32) -> u32 {
        while self.0[a as usize] != a {
            let up = self.0[self.0[a as usize] as usize];
            self.0[a as usize] = up;
            a = up;
        }
        a
    }

    fn union(&mut self, a: u32, b: u32) {
        let (ra, rb) = (self.find(a), self.find(b));
        if ra != rb {
            // The smaller root wins, so the result does not depend on order.
            let (lo, hi) = if ra < rb { (ra, rb) } else { (rb, ra) };
            self.0[hi as usize] = lo;
        }
    }
}

/// The longest cycle that is still kept as a face.
const MAX_FACE: usize = 6;

/// Clusters closer than this many quad sides are one vertex.
const MERGE: f64 = 0.5;

/// Union of points within `radius` of each other whose normals agree, found
/// on a hash grid of that cell size. -> a dense new index per point.
fn merge_close(p: &[V3], n: &[V3], weight: &[f64], radius: f64) -> Vec<u32> {
    let _ = weight;
    let key = |x: V3| {
        (
            (x.x / radius).floor() as i64,
            (x.y / radius).floor() as i64,
            (x.z / radius).floor() as i64,
        )
    };
    let mut grid: HashMap<(i64, i64, i64), Vec<u32>> = HashMap::new();
    for (i, &x) in p.iter().enumerate() {
        grid.entry(key(x)).or_default().push(i as u32);
    }
    let mut sets = UnionFind((0..p.len() as u32).collect());
    for (i, &x) in p.iter().enumerate() {
        let (kx, ky, kz) = key(x);
        for dx in -1..=1 {
            for dy in -1..=1 {
                for dz in -1..=1 {
                    let Some(cell) = grid.get(&(kx + dx, ky + dy, kz + dz)) else { continue };
                    for &j in cell {
                        let j = j as usize;
                        if j > i && (p[j] - x).norm() < radius && n[i].dot(n[j]) > 0.5 {
                            sets.union(i as u32, j as u32);
                        }
                    }
                }
            }
        }
    }
    let mut dense = vec![u32::MAX; p.len()];
    let mut out = vec![0u32; p.len()];
    let mut next = 0;
    for i in 0..p.len() {
        let root = sets.find(i as u32) as usize;
        if dense[root] == u32::MAX {
            dense[root] = next;
            next += 1;
        }
        out[i] = dense[root];
    }
    out
}

pub fn extract(p: &[V3], n: &[V3], adj: &[Vec<u32>], q: &[V3], o: &[V3], h: f64) -> Polygons {
    let count = p.len();
    let mut sets = UnionFind((0..count as u32).collect());
    let mut steps = Vec::new();
    for i in 0..count {
        for &j in &adj[i] {
            let j = j as usize;
            if j <= i {
                continue;
            }
            // The offset is counted, not measured: find the lattice corner
            // the two vertices share near their middle, then count how many
            // steps each vertex's own corner is from it, each in its own
            // frame. Measuring o[j] - o[i] in an averaged frame instead
            // rounds wrongly wherever the two lattices disagree slightly,
            // which is everywhere near a singularity.
            let (ti, qj) = (n[i].cross(q[i]), compat_orientation(q[i], n[i], q[j], n[j]).1);
            let tj = n[j].cross(qj);
            let (ours, theirs) = compat_position(p[i], n[i], q[i], o[i], p[j], n[j], qj, o[j], h);
            let steps_i = ((ours - o[i]).dot(q[i]) / h, (ours - o[i]).dot(ti) / h);
            let steps_j = ((theirs - o[j]).dot(qj) / h, (theirs - o[j]).dot(tj) / h);
            let a = (steps_i.0.round() - steps_j.0.round()) as i64;
            let b = (steps_i.1.round() - steps_j.1.round()) as i64;
            match a.abs() + b.abs() {
                0 => sets.union(i as u32, j as u32),
                1 => steps.push((i as u32, j as u32, true)),
                _ => steps.push((i as u32, j as u32, false)),
            }
        }
    }

    // One output vertex per set, numbered in input order.
    let mut id = vec![u32::MAX; count];
    let mut sum: Vec<V3> = Vec::new();
    let mut normal: Vec<V3> = Vec::new();
    let mut members: Vec<f64> = Vec::new();
    for i in 0..count {
        let root = sets.find(i as u32) as usize;
        if id[root] == u32::MAX {
            id[root] = sum.len() as u32;
            sum.push(V3::ZERO);
            normal.push(V3::ZERO);
            members.push(0.0);
        }
        let c = id[root] as usize;
        sum[c] += o[i];
        normal[c] += n[i];
        members[c] += 1.0;
    }
    let cluster_v: Vec<V3> = sum.iter().zip(&members).map(|(s, &m)| *s / m).collect();
    let cluster_n: Vec<V3> = normal.iter().map(|x| x.normalized()).collect();

    // A lattice corner whose vertices are not joined by zero-step edges comes
    // out as two (or more) clusters sitting almost on top of each other —
    // slivers, triangles, and chains of irregular vertices follow. Merge
    // clusters closer than a fraction of the quad size that face the same way.
    let merged = merge_close(&cluster_v, &cluster_n, &members, MERGE * h);
    let finals = merged.iter().copied().max().map_or(0, |m| m as usize + 1);
    let mut fsum = vec![V3::ZERO; finals];
    let mut fnormal = vec![V3::ZERO; finals];
    let mut fcount = vec![0.0; finals];
    for c in 0..cluster_v.len() {
        let f = merged[c] as usize;
        fsum[f] += cluster_v[c] * members[c];
        fnormal[f] += cluster_n[c] * members[c];
        fcount[f] += members[c];
    }
    let v: Vec<V3> = fsum.iter().zip(&fcount).map(|(s, &m)| *s / m).collect();
    let normal: Vec<V3> = fnormal.iter().map(|x| x.normalized()).collect();
    let vertex_of = |i: u32, sets: &mut UnionFind| merged[id[sets.find(i) as usize] as usize];

    // Two output vertices are often joined by several input edges, and near
    // a singularity they do not all agree: some count one lattice step, some
    // a diagonal. One vote for a step used to be enough for an edge, which
    // is how diagonals got in and made triangles. The majority decides.
    let mut votes: HashMap<(u32, u32), (u32, u32)> = HashMap::new();
    for &(i, j, unit) in &steps {
        let (a, b) = (vertex_of(i, &mut sets), vertex_of(j, &mut sets));
        if a != b {
            let tally = votes.entry((a.min(b), a.max(b))).or_default();
            if unit { tally.0 += 1 } else { tally.1 += 1 }
        }
    }
    let edge_set: BTreeSet<(u32, u32)> =
        votes.iter().filter(|(_, t)| t.0 > t.1).map(|(&e, _)| e).collect();
    let mut around: Vec<Vec<u32>> = vec![Vec::new(); v.len()];
    for &(a, b) in &edge_set {
        around[a as usize].push(b);
        around[b as usize].push(a);
    }
    // Neighbours in counter-clockwise order seen from outside.
    for c in 0..v.len() {
        let nc = normal[c];
        let t1 = V3::tangent_of(nc);
        let t2 = nc.cross(t1);
        let angle = |k: u32| {
            let d = v[k as usize] - v[c];
            d.dot(t2).atan2(d.dot(t1))
        };
        around[c].sort_by(|&a, &b| angle(a).total_cmp(&angle(b)));
    }

    // Walk every directed edge once. Arriving at `b` from `a`, the face on
    // our left continues along the neighbour of `b` just before `a` in
    // counter-clockwise order.
    let mut used: Vec<Vec<bool>> = around.iter().map(|l| vec![false; l.len()]).collect();
    let mut faces = Vec::new();
    let mut open_cycles = 0;
    for start in 0..v.len() {
        for k in 0..around[start].len() {
            if used[start][k] {
                continue;
            }
            used[start][k] = true;
            let mut face = vec![start as u32];
            let (mut a, mut b) = (start as u32, around[start][k]);
            let mut closed = false;
            while face.len() <= 2 * MAX_FACE {
                if b == start as u32 {
                    closed = true;
                    break;
                }
                face.push(b);
                let list = &around[b as usize];
                let Some(back) = list.iter().position(|&x| x == a) else { break };
                let next = (back + list.len() - 1) % list.len();
                if used[b as usize][next] {
                    break;
                }
                used[b as usize][next] = true;
                a = b;
                b = list[next];
            }
            if closed && face.len() >= 3 && face.len() <= MAX_FACE {
                faces.push(face);
            } else {
                open_cycles += 1;
            }
        }
    }

    Polygons { v, faces, edges: edge_set.len(), open_cycles }
}

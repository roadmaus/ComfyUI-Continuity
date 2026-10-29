//! Quad meshes of one patch from its side counts: given n corners and how
//! many grid edges each side must hold, a quad mesh of the patch's flat
//! domain (the polygon `fill` maps the patch onto) whose boundary has
//! exactly those edges.
//!
//! The patterns are Takayama, Panozzo and Sorkine-Hornung's ("Pattern-Based
//! Quadrangulation for N-Sided Patches", 2014): a few topologies per side
//! count, each with free integer parameters, padded with strips along its
//! sides, chosen as the first that fits. A template is assembled from grid
//! blocks glued along shared rows of vertices; interior positions are the
//! uniform Laplace average of their neighbours with the boundary fixed,
//! which on a convex polygon cannot fold.

pub struct Template {
    /// Positions in the patch's domain.
    pub pos: Vec<(f64, f64)>,
    /// Per side, the vertices along it from its first corner to the next.
    pub sides: Vec<Vec<usize>>,
    /// Quads, counter-clockwise in the domain.
    pub faces: Vec<[usize; 4]>,
    /// Which vertices were placed and are held while relaxing.
    fixed: Vec<bool>,
}

impl Template {
    /// The boundary of a polygon with corners `corners` and `l[i]` edges on
    /// side i, evenly spaced.
    fn outline(corners: &[(f64, f64)], l: &[usize]) -> Template {
        let n = corners.len();
        let mut t = Template { pos: Vec::new(), sides: Vec::new(), faces: Vec::new(), fixed: Vec::new() };
        let corner_ids: Vec<usize> = corners.iter().map(|&c| t.add(c, true)).collect();
        for i in 0..n {
            let (a, b) = (corners[i], corners[(i + 1) % n]);
            let mut side = vec![corner_ids[i]];
            for k in 1..l[i] {
                let f = k as f64 / l[i] as f64;
                side.push(t.add((a.0 + (b.0 - a.0) * f, a.1 + (b.1 - a.1) * f), true));
            }
            side.push(corner_ids[(i + 1) % n]);
            t.sides.push(side);
        }
        t
    }

    fn add(&mut self, p: (f64, f64), fixed: bool) -> usize {
        self.pos.push(p);
        self.fixed.push(fixed);
        self.pos.len() - 1
    }

    /// A row of new free vertices from `a` to `b` with `k` edges, ends
    /// included as given.
    fn row(&mut self, a: usize, b: usize, k: usize) -> Vec<usize> {
        let (pa, pb) = (self.pos[a], self.pos[b]);
        let mut out = vec![a];
        for j in 1..k {
            let f = j as f64 / k as f64;
            out.push(self.add((pa.0 + (pb.0 - pa.0) * f, pa.1 + (pb.1 - pa.1) * f), false));
        }
        out.push(b);
        out
    }

    /// A grid block bounded by four rows going round it counter-clockwise:
    /// `s0` and `s2` hold the same number of edges, as do `s1` and `s3`;
    /// each row starts where the previous one ends.
    fn grid(&mut self, s0: &[usize], s1: &[usize], s2: &[usize], s3: &[usize]) {
        let (a, b) = (s0.len() - 1, s1.len() - 1);
        debug_assert!(s2.len() - 1 == a && s3.len() - 1 == b);
        let mut g = vec![vec![usize::MAX; b + 1]; a + 1];
        for i in 0..=a {
            g[i][0] = s0[i];
            g[i][b] = s2[a - i];
        }
        for j in 0..=b {
            g[a][j] = s1[j];
            g[0][j] = s3[b - j];
        }
        let c = [self.pos[s0[0]], self.pos[s1[0]], self.pos[s2[0]], self.pos[s3[0]]];
        for i in 1..a {
            for j in 1..b {
                let (u, w) = (i as f64 / a as f64, j as f64 / b as f64);
                let x = c[0].0 * (1.0 - u) * (1.0 - w) + c[1].0 * u * (1.0 - w) + c[2].0 * u * w + c[3].0 * (1.0 - u) * w;
                let y = c[0].1 * (1.0 - u) * (1.0 - w) + c[1].1 * u * (1.0 - w) + c[2].1 * u * w + c[3].1 * (1.0 - u) * w;
                g[i][j] = self.add((x, y), false);
            }
        }
        for i in 0..a {
            for j in 0..b {
                self.faces.push([g[i][j], g[i + 1][j], g[i + 1][j + 1], g[i][j + 1]]);
            }
        }
    }

    /// Every free vertex to the average of its neighbours, until still.
    fn relax(&mut self) {
        let n = self.pos.len();
        let mut adj: Vec<Vec<usize>> = vec![Vec::new(); n];
        for f in &self.faces {
            for k in 0..4 {
                let (a, b) = (f[k], f[(k + 1) % 4]);
                adj[a].push(b);
                adj[b].push(a);
            }
        }
        for list in adj.iter_mut() {
            list.sort_unstable();
            list.dedup();
        }
        for _ in 0..2000 {
            let mut moved = 0.0f64;
            for v in 0..n {
                if self.fixed[v] || adj[v].is_empty() {
                    continue;
                }
                let k = adj[v].len() as f64;
                let p = adj[v].iter().fold((0.0, 0.0), |s, &w| (s.0 + self.pos[w].0, s.1 + self.pos[w].1));
                let p = (p.0 / k, p.1 / k);
                moved = moved.max((p.0 - self.pos[v].0).abs() + (p.1 - self.pos[v].1).abs());
                self.pos[v] = p;
            }
            if moved < 1e-9 {
                break;
            }
        }
    }
}

/// The spokes of the midpoint pattern, if it fits: a centre of valence n,
/// side i meeting spokes i−1 and i+1, so S_i = t_{i−1} + t_{i+1}. Odd n has
/// one solution; even n splits into two cycles (n = 4 leaves one free
/// spoke per cycle, set to the smallest that works). None unless every
/// spoke is a whole number ≥ 1.
fn spokes(l: &[usize]) -> Option<Vec<usize>> {
    let n = l.len();
    let s: Vec<i64> = l.iter().map(|&x| x as i64).collect();
    let mut t = vec![0i64; n];
    // Walk a cycle k, k+2, k+4, …: t_{k+1} sits in S_k and S_{k+2}.
    let cycles: Vec<Vec<usize>> = if n % 2 == 1 { vec![(0..n).map(|j| (2 * j) % n).collect()] } else { (0..2).map(|o| (0..n / 2).map(|j| (o + 2 * j) % n).collect()).collect() };
    for cyc in cycles {
        // Unknowns u_j = t_{cyc[j]+1}; S_{cyc[j+1]} = u_j + u_{j+1}.
        let m = cyc.len();
        let rhs: Vec<i64> = (0..m).map(|j| s[cyc[(j + 1) % m]]).collect();
        let u: Vec<i64> = if m % 2 == 1 {
            (0..m).map(|j| {
                let alt: i64 = (0..m).map(|k| if k % 2 == 0 { rhs[(j + k) % m] } else { -rhs[(j + k) % m] }).sum();
                if alt % 2 != 0 { i64::MIN } else { alt / 2 }
            }).collect()
        } else {
            // Even cycle (only n = 4: m = 2): u_0 + u_1 = rhs_0 = rhs_1.
            if m != 2 || rhs[0] != rhs[1] || rhs[0] < 2 {
                return None;
            }
            vec![1, rhs[0] - 1]
        };
        if u.iter().any(|&x| x < 1) {
            return None;
        }
        for j in 0..m {
            t[(cyc[j] + 1) % n] = u[j];
        }
    }
    // Check, which also catches the odd cycles' parity.
    for i in 0..n {
        if t[(i + n - 1) % n] + t[(i + 1) % n] != s[i] {
            return None;
        }
    }
    Some(t.into_iter().map(|x| x as usize).collect())
}

// ------------------------------------------------------------- Takayama

/// One of Takayama's base patterns: a few quads whose corners `C0…` are the
/// patch corners, with free integer parameters. A padding `p_i` is a strip
/// of quads glued along side i; a chord parameter multiplies a chord (a
/// strip of quads through opposite edges) of the base, seeded by one of its
/// edges; `q_i` is a chord whose effect on the sides equals `p_i`'s.
struct Base {
    n: usize,
    faces: &'static str,
    vars: &'static str,
    /// Chord parameters and an edge of their chord.
    seeds: &'static [(&'static str, &'static str, &'static str)],
    /// The parameter whose range is centred (its singularities kept near
    /// the middle).
    window: Option<&'static str>,
    /// a ≤ b.
    extra: &'static [(&'static str, &'static str)],
    /// Paddings whose sum is maximized.
    objective: &'static str,
}

/// Takayama, Panozzo and Sorkine-Hornung's catalogue (2014, and the
/// three-sided alternative of 2013), in the order they are tried: fewer
/// singularities first. Their side equations are computed from the faces.
const BASES: &[Base] = &[
    Base { n: 2, faces: "C0 V0 V1 C1", vars: "p0 p1 y", seeds: &[("y", "V0", "V1")], window: Some("y"), extra: &[], objective: "p0 p1" },
    Base { n: 2, faces: "C0 V0 C1 V1", vars: "p0 p1 x y", seeds: &[("x", "C0", "V0"), ("y", "C1", "V0")], window: Some("x"), extra: &[], objective: "p0 p1" },
    Base { n: 3, faces: "C0 V0 C1 C2", vars: "p0 p1 p2", seeds: &[], window: None, extra: &[], objective: "p0 p1 p2" },
    Base { n: 3, faces: "C0 V0 V3 C2 | V0 V1 V2 V3 | C2 V3 V2 C1", vars: "p0 p1 p2 q1 q2 x", seeds: &[("x", "C0", "V0"), ("q1", "V0", "V3"), ("q2", "V0", "V1")], window: Some("x"), extra: &[("p1", "q1"), ("p2", "q2")], objective: "p0 p1 p2" },
    Base { n: 3, faces: "C0 V0 V3 C2 | V0 V1 V4 V3 | C1 V2 V4 V1 | C2 V3 V4 V2", vars: "p0 p1 p2 q2 x", seeds: &[("x", "C0", "V0"), ("q2", "V0", "V1")], window: Some("x"), extra: &[("p2", "q2")], objective: "p0 p1 p2" },
    Base { n: 4, faces: "C0 C1 C2 C3", vars: "p0 p1", seeds: &[], window: None, extra: &[], objective: "p0 p1" },
    Base { n: 4, faces: "C0 V0 V2 C3 | V0 C1 V1 V2 | V1 C2 C3 V2", vars: "p0 p1 p2 p3 x", seeds: &[("x", "C0", "V0")], window: None, extra: &[("p0", "p2"), ("p1", "p3")], objective: "p0 p1" },
    Base { n: 4, faces: "C0 V0 C2 C3 | V0 V1 C1 C2", vars: "p0 p1 p2 p3 x y", seeds: &[("x", "V0", "V1"), ("y", "C2", "V0")], window: None, extra: &[("p0", "p2"), ("p1", "p3")], objective: "p0 p1" },
    Base { n: 4, faces: "C0 V0 V3 C3 | V0 V1 V2 V3 | V1 C1 C2 V2 | C2 C3 V3 V2", vars: "p0 p1 p2 p3 q1 x", seeds: &[("x", "C0", "V0"), ("q1", "V0", "V1")], window: None, extra: &[("p0", "p2"), ("p1", "p3"), ("p3", "q1")], objective: "p0 p1" },
    Base { n: 4, faces: "C0 V0 V6 C3 | V0 V1 V5 V6 | V1 V2 V4 V5 | V2 C1 V3 V4 | V3 C2 V5 V4 | C2 C3 V6 V5", vars: "p0 p1 p2 p3 q1 x y", seeds: &[("x", "C0", "V0"), ("q1", "V0", "V1"), ("y", "V1", "V2")], window: None, extra: &[("p0", "p2"), ("p1", "p3"), ("p3", "q1")], objective: "p0 p1" },
    Base { n: 5, faces: "V0 C3 C4 C0 | V0 C1 C2 C3", vars: "p0 p1 p2 p3 p4", seeds: &[], window: None, extra: &[], objective: "p0 p1 p2 p3 p4" },
    Base { n: 5, faces: "C0 V0 C1 C2 | C0 C2 C3 C4", vars: "p0 p1 p2 p3 p4 q4 x", seeds: &[("x", "C0", "V0"), ("q4", "C1", "V0")], window: Some("x"), extra: &[("p4", "q4")], objective: "p0 p1 p2 p3 p4" },
    Base { n: 5, faces: "C0 V0 V3 V4 | C1 V4 V3 V2 | V0 V1 V2 V3 | V4 C3 C4 C0 | V4 C1 C2 C3", vars: "p0 p1 p2 p3 p4 q0 q1 q4 x", seeds: &[("x", "C0", "V0"), ("q4", "V0", "V3"), ("q1", "C1", "V4"), ("q0", "C3", "V4")], window: Some("x"), extra: &[("p0", "q0"), ("p1", "q1"), ("p4", "q4")], objective: "p0 p1 p2 p3 p4" },
    Base { n: 5, faces: "C0 V0 V5 C4 | V0 V1 V6 V5 | V1 V2 V7 V6 | V2 V3 V8 V7 | V3 C1 V4 V8 | V4 C2 V7 V8 | C2 C3 V6 V7 | C3 C4 V5 V6", vars: "p0 p1 p2 p3 p4 q1 q4 x y", seeds: &[("x", "C0", "V0"), ("q4", "V0", "V1"), ("q1", "V1", "V2"), ("y", "V2", "V3")], window: Some("x"), extra: &[("p1", "q1"), ("p4", "q4")], objective: "p0 p1 p2 p3 p4" },
    Base { n: 6, faces: "C0 C1 C2 C5 | C2 C3 C4 C5", vars: "p0 p1 p2 p3 p4 p5 x", seeds: &[("x", "C0", "C1")], window: Some("x"), extra: &[], objective: "p0 p1 p2 p3 p4 p5" },
    Base { n: 6, faces: "C0 V0 V2 V3 | C1 V1 V2 V0 | V1 C2 V3 V2 | C2 C3 C4 V3 | C4 C5 C0 V3", vars: "p0 p1 p2 p3 p4 p5 x y z w", seeds: &[("x", "C0", "V0"), ("y", "V1", "V2"), ("z", "V0", "V2"), ("w", "C2", "C3")], window: Some("x"), extra: &[], objective: "p0 p1 p2 p3 p4 p5" },
    Base { n: 6, faces: "C0 V0 V2 V4 | V0 V1 V3 V2 | V1 C1 V5 V3 | C1 C2 C3 V5 | C3 C4 V4 V5 | C4 C5 C0 V4 | V2 V3 V5 V4", vars: "p0 p1 p2 p3 p4 p5 q0 q3 x y", seeds: &[("x", "C0", "V0"), ("y", "V0", "V1"), ("q0", "C1", "C2"), ("q3", "V0", "V2")], window: Some("x"), extra: &[("p0", "q0"), ("p3", "q3")], objective: "p0 p1 p2 p3 p4 p5" },
    Base { n: 6, faces: "C0 V0 V6 C5 | V0 V1 V5 V6 | V1 V2 V4 V5 | V2 C1 V3 V4 | V3 C2 V5 V4 | C2 C3 V8 V5 | C3 C4 V7 V8 | C4 C5 V6 V7 | V5 V8 V7 V6", vars: "p0 p1 p2 p3 p4 p5 q3 x y z", seeds: &[("x", "C0", "V0"), ("y", "V1", "V2"), ("z", "V0", "V1"), ("q3", "C2", "C3")], window: Some("x"), extra: &[], objective: "p0 p1 p2 p3 p4 p5" },
];

/// A base pattern read into ids: corners are 0..n, other vertices after.
struct Parsed {
    nv: usize,
    faces: Vec<[usize; 4]>,
    names: Vec<&'static str>,
    /// Per variable: its column (effect on each side's edge count).
    cols: Vec<Vec<i64>>,
    /// Per chord parameter (by variable index): an edge of its chord.
    seed: Vec<Option<(usize, usize)>>,
    /// Base side counts.
    c: Vec<i64>,
}

fn parse(b: &Base) -> Parsed {
    let n = b.n;
    let mut ids: std::collections::HashMap<&str, usize> = (0..n).map(|k| (["C0", "C1", "C2", "C3", "C4", "C5"][k], k)).collect();
    let mut faces = Vec::new();
    for f in b.faces.split('|') {
        let mut q = [0usize; 4];
        for (k, name) in f.split_whitespace().enumerate() {
            let next = ids.len();
            q[k] = *ids.entry(name).or_insert(next);
        }
        faces.push(q);
    }
    let nv = ids.len();
    let side_of = boundary_sides(nv, &faces, n);
    let c: Vec<i64> = (0..n).map(|i| side_of.iter().filter(|&&(_, s)| s == i).count() as i64).collect();
    let chord = chords(&faces);
    let names: Vec<&'static str> = b.vars.split_whitespace().collect();
    let mut cols = Vec::new();
    let mut seed = Vec::new();
    for &name in &names {
        let mut col = vec![0i64; n];
        if let Some(i) = name.strip_prefix('p').and_then(|d| d.parse::<usize>().ok()) {
            if n == 2 {
                col[1 - i] += 2;
            } else {
                col[(i + n - 1) % n] += 1;
                col[(i + 1) % n] += 1;
            }
            seed.push(None);
        } else {
            let &(_, a, bb) = b.seeds.iter().find(|s| s.0 == name).expect("a seed for every chord parameter");
            let e = (ids[a], ids[bb]);
            let ch = chord[&(e.0.min(e.1), e.0.max(e.1))];
            for &(edge, s) in &side_of {
                if chord[&edge] == ch {
                    col[s] += 1;
                }
            }
            seed.push(Some(e));
        }
        cols.push(col);
    }
    Parsed { nv, faces, names, cols, seed, c }
}

/// Boundary edges of a quad mesh with their side: walking the outline (the
/// face half-edges with no twin) from corner 0, side i runs from corner i
/// to corner i+1; corners are vertices 0..n.
fn boundary_sides(nv: usize, faces: &[[usize; 4]], n: usize) -> Vec<((usize, usize), usize)> {
    let next = outline(nv, faces);
    let mut out = Vec::new();
    let (mut v, mut side) = (0usize, 0usize);
    loop {
        let w = next[v];
        out.push(((v.min(w), v.max(w)), side));
        v = w;
        if v == 0 {
            break;
        }
        if v < n {
            side += 1;
        }
    }
    out
}

/// The outline as a successor map (usize::MAX off it).
fn outline(nv: usize, faces: &[[usize; 4]]) -> Vec<usize> {
    let mut half: std::collections::HashSet<(usize, usize)> = Default::default();
    for f in faces {
        for k in 0..4 {
            half.insert((f[k], f[(k + 1) % 4]));
        }
    }
    let mut next = vec![usize::MAX; nv];
    for &(a, b) in &half {
        if !half.contains(&(b, a)) {
            next[a] = b;
        }
    }
    next
}

/// Chord of every edge: opposite edges of a quad are one chord.
fn chords(faces: &[[usize; 4]]) -> std::collections::HashMap<(usize, usize), usize> {
    let key = |a: usize, b: usize| (a.min(b), a.max(b));
    let mut index: std::collections::HashMap<(usize, usize), usize> = Default::default();
    for f in faces {
        for k in 0..4 {
            let len = index.len();
            index.entry(key(f[k], f[(k + 1) % 4])).or_insert(len);
        }
    }
    let mut parent: Vec<usize> = (0..index.len()).collect();
    fn root(p: &mut [usize], mut i: usize) -> usize {
        while p[i] != i {
            p[i] = p[p[i]];
            i = p[i];
        }
        i
    }
    for f in faces {
        for k in 0..2 {
            let a = index[&key(f[k], f[k + 1])];
            let b = index[&key(f[k + 2], f[(k + 3) % 4])];
            let (ra, rb) = (root(&mut parent, a), root(&mut parent, b));
            parent[ra] = rb;
        }
    }
    index.iter().map(|(&e, &i)| (e, root(&mut parent, i))).collect()
}

/// The parameters for side counts `l` under pattern `b`, chosen as the
/// reference does: centre the window parameter's range, keep the extra
/// inequalities, maximize the objective paddings, then the
/// lexicographically smallest. Paddings and the q's sharing a padding's
/// column only matter through their sum, so the free parameters are the
/// other chords (at most four), which are enumerated; the sums follow by
/// solving the rest exactly.
fn solve(pp: &Parsed, b: &Base, l: &[usize]) -> Option<Vec<i64>> {
    let n = b.n;
    let rhs: Vec<i64> = (0..n).map(|i| l[i] as i64 - pp.c[i]).collect();
    if rhs.iter().any(|&x| x < 0) {
        return None;
    }
    let nvar = pp.names.len();
    let is_pad = |v: usize| pp.names[v].starts_with('p') || pp.names[v].starts_with('q');
    // Groups of padding-like variables with equal columns.
    let mut groups: Vec<Vec<usize>> = Vec::new();
    for v in (0..nvar).filter(|&v| is_pad(v)) {
        match groups.iter_mut().find(|g| pp.cols[g[0]] == pp.cols[v]) {
            Some(g) => g.push(v),
            None => groups.push(vec![v]),
        }
    }
    let free: Vec<usize> = (0..nvar).filter(|&v| !is_pad(v)).collect();
    // Least squares for the group sums: (GᵀG)⁻¹Gᵀ, checked exactly after.
    let g = groups.len();
    let mut gtg = vec![vec![0.0; g]; g];
    for a in 0..g {
        for c in 0..g {
            gtg[a][c] = (0..n).map(|i| (pp.cols[groups[a][0]][i] * pp.cols[groups[c][0]][i]) as f64).sum();
        }
    }
    let solve_sums = |r: &[i64]| -> Option<Vec<i64>> {
        let gtr: Vec<f64> = (0..g).map(|a| (0..n).map(|i| (pp.cols[groups[a][0]][i] * r[i]) as f64).sum()).collect();
        let x = gauss(gtg.clone(), gtr);
        let xi: Vec<i64> = x.iter().map(|v| v.round() as i64).collect();
        if xi.iter().any(|&v| v < 0) {
            return None;
        }
        for i in 0..n {
            let got: i64 = (0..g).map(|a| pp.cols[groups[a][0]][i] * xi[a]).sum();
            if got != r[i] {
                return None;
            }
        }
        Some(xi)
    };
    let bound: Vec<i64> = free.iter().map(|&v| (0..n).filter(|&i| pp.cols[v][i] > 0).map(|i| rhs[i] / pp.cols[v][i]).min().unwrap_or(0)).collect();
    // Every assignment of the free parameters with feasible sums.
    let mut feasible: Vec<(Vec<i64>, Vec<i64>)> = Vec::new();
    let mut f = vec![0i64; free.len()];
    'outer: loop {
        let r: Vec<i64> = (0..n).map(|i| rhs[i] - free.iter().zip(&f).map(|(&v, &x)| pp.cols[v][i] * x).sum::<i64>()).collect();
        if r.iter().all(|&x| x >= 0) {
            if let Some(sums) = solve_sums(&r) {
                feasible.push((f.clone(), sums));
            }
        }
        for k in 0..f.len() {
            f[k] += 1;
            if f[k] <= bound[k] {
                continue 'outer;
            }
            f[k] = 0;
        }
        break;
    }
    if let Some(w) = b.window {
        let k = free.iter().position(|&v| pp.names[v] == w)?;
        let lo = feasible.iter().map(|x| x.0[k]).min()?;
        let hi = feasible.iter().map(|x| x.0[k]).max()?;
        let mid = (lo + hi) / 2;
        feasible.retain(|x| (mid - 1..=mid + 1).contains(&x.0[k]));
    }
    let objective: Vec<usize> = b.objective.split_whitespace().filter_map(|nm| pp.names.iter().position(|x| x == &nm)).collect();
    let extra: Vec<(usize, usize)> = b.extra.iter().map(|&(a, c)| (pp.names.iter().position(|x| *x == a).unwrap(), pp.names.iter().position(|x| *x == c).unwrap())).collect();
    let mut best: Option<(i64, Vec<i64>)> = None;
    for (fv, sums) in feasible {
        let mut vals = vec![0i64; nvar];
        for (k, &v) in free.iter().enumerate() {
            vals[v] = fv[k];
        }
        // Split each group's sum among its members (at most three).
        let mut ok = true;
        for (gi, grp) in groups.iter().enumerate() {
            let s = sums[gi];
            let mut choice: Option<(i64, Vec<i64>)> = None;
            let mut split = vec![0i64; grp.len()];
            loop {
                let used: i64 = split[..grp.len() - 1].iter().sum();
                if used <= s {
                    *split.last_mut().unwrap() = s - used;
                    let mut trial = vals.clone();
                    for (m, &v) in grp.iter().enumerate() {
                        trial[v] = split[m];
                    }
                    if extra.iter().all(|&(a, c)| !grp.contains(&a) || trial[a] <= trial[c]) {
                        let score: i64 = grp.iter().filter(|v| objective.contains(v)).map(|&v| trial[v]).sum();
                        let cand: Vec<i64> = grp.iter().map(|&v| trial[v]).collect();
                        if choice.as_ref().map_or(true, |(bs, bv)| score > *bs || (score == *bs && cand < *bv)) {
                            choice = Some((score, cand));
                        }
                    }
                }
                // Next split of the first members.
                let mut k = 0;
                while k + 1 < grp.len() {
                    split[k] += 1;
                    if split[k] <= s {
                        break;
                    }
                    split[k] = 0;
                    k += 1;
                }
                if k + 1 >= grp.len() {
                    break;
                }
            }
            match choice {
                Some((_, cand)) => {
                    for (m, &v) in grp.iter().enumerate() {
                        vals[v] = cand[m];
                    }
                }
                None => {
                    ok = false;
                    break;
                }
            }
        }
        if !ok {
            continue;
        }
        let score: i64 = objective.iter().map(|&v| vals[v]).sum();
        if best.as_ref().map_or(true, |(bs, bv)| score > *bs || (score == *bs && vals < *bv)) {
            best = Some((score, vals));
        }
    }
    best.map(|b| b.1)
}

fn gauss(mut a: Vec<Vec<f64>>, mut b: Vec<f64>) -> Vec<f64> {
    let n = b.len();
    for col in 0..n {
        let piv = (col..n).max_by(|&i, &j| a[i][col].abs().total_cmp(&a[j][col].abs())).unwrap();
        a.swap(col, piv);
        b.swap(col, piv);
        let d = a[col][col];
        if d.abs() < 1e-12 {
            continue;
        }
        for r in 0..n {
            if r != col {
                let f = a[r][col] / d;
                for k in col..n {
                    a[r][k] -= f * a[col][k];
                }
                b[r] -= f * b[col];
            }
        }
    }
    (0..n).map(|i| if a[i][i].abs() < 1e-12 { 0.0 } else { b[i] / a[i][i] }).collect()
}

/// The pattern's quad mesh for parameters `vals`: chords multiplied, then
/// padding strips on sides n−1 down to 0. -> (vertex count, faces, outline
/// successor map); corners stay vertices 0..n.
fn assemble(pp: &Parsed, n: usize, vals: &[i64]) -> (usize, Vec<[usize; 4]>, Vec<usize>) {
    let key = |a: usize, b: usize| (a.min(b), a.max(b));
    let chord = chords(&pp.faces);
    let mut mult: std::collections::HashMap<usize, usize> = Default::default();
    for (v, s) in pp.seed.iter().enumerate() {
        if let Some((a, b)) = s {
            *mult.entry(chord[&key(*a, *b)]).or_insert(1) += vals[v] as usize;
        }
    }
    let mut nv = pp.nv;
    // Each base edge's points from its lower to its higher end.
    let mut pts: std::collections::HashMap<(usize, usize), Vec<usize>> = Default::default();
    for (&e, &ch) in &chord {
        let m = *mult.get(&ch).unwrap_or(&1);
        let mut row = vec![e.0];
        for _ in 1..m {
            row.push(nv);
            nv += 1;
        }
        row.push(e.1);
        pts.insert(e, row);
    }
    let along = |a: usize, b: usize| -> Vec<usize> {
        let r = &pts[&key(a, b)];
        if a < b { r.clone() } else { r.iter().rev().copied().collect() }
    };
    let mut faces = Vec::new();
    for f in &pp.faces {
        let (s0, s1, s3) = (along(f[0], f[1]), along(f[1], f[2]), along(f[3], f[0]));
        let s2 = along(f[2], f[3]);
        let (a, bb) = (s0.len() - 1, s1.len() - 1);
        let mut g = vec![vec![usize::MAX; bb + 1]; a + 1];
        for i in 0..=a {
            g[i][0] = s0[i];
            g[i][bb] = s2[a - i];
        }
        for j in 0..=bb {
            g[a][j] = s1[j];
            g[0][j] = s3[bb - j];
        }
        for i in 1..a {
            for j in 1..bb {
                g[i][j] = nv;
                nv += 1;
            }
        }
        for i in 0..a {
            for j in 0..bb {
                faces.push([g[i][j], g[i + 1][j], g[i + 1][j + 1], g[i][j + 1]]);
            }
        }
    }
    // Padding: a strip of quads along the whole of side i, outside.
    let mut next = outline(nv, &faces);
    let mut corner: Vec<usize> = (0..n).collect();
    for i in (0..n).rev() {
        let p = pp.names.iter().position(|x| *x == ["p0", "p1", "p2", "p3", "p4", "p5"][i]).map_or(0, |v| vals[v]);
        for _ in 0..p {
            let mut w = vec![corner[i]];
            while *w.last().unwrap() != corner[(i + 1) % n] {
                w.push(next[*w.last().unwrap()]);
            }
            let u: Vec<usize> = (0..w.len()).map(|k| nv + k).collect();
            nv += w.len();
            next.resize(nv, usize::MAX);
            for k in 0..w.len() - 1 {
                faces.push([w[k + 1], w[k], u[k], u[k + 1]]);
            }
            // New outline: … w_0 → u_0 → … → u_L → w_L …
            next[w[0]] = u[0];
            for k in 0..u.len() - 1 {
                next[u[k]] = u[k + 1];
            }
            next[*u.last().unwrap()] = *w.last().unwrap();
            for &x in &w[1..w.len() - 1] {
                next[x] = usize::MAX;
            }
            corner[i] = u[0];
            corner[(i + 1) % n] = *u.last().unwrap();
        }
    }
    // Corners must be 0..n for the caller: swap ids.
    let mut perm: Vec<usize> = (0..nv).collect();
    for k in 0..n {
        let (a, b) = (perm.iter().position(|&x| x == corner[k]).unwrap(), k);
        perm.swap(a, b);
    }
    // perm[new] = old; map old -> new.
    let mut new_of = vec![0usize; nv];
    for (new, &old) in perm.iter().enumerate() {
        new_of[old] = new;
    }
    let faces: Vec<[usize; 4]> = faces.iter().map(|f| f.map(|x| new_of[x])).collect();
    let next = outline(nv, &faces);
    (nv, faces, next)
}

/// A Takayama pattern for side counts `l`: the first base pattern, under
/// the first of the 2n rotations and reflections, that has parameters.
/// -> (vertex count, faces CCW, per input side its vertices from corner i to
/// corner i+1).
fn takayama(l: &[usize]) -> Option<(usize, Vec<[usize; 4]>, Vec<Vec<usize>>)> {
    let n = l.len();
    for b in BASES.iter().filter(|b| b.n == n) {
        let pp = parse(b);
        for k in 0..2 * n {
            let pi: Vec<usize> = (0..n).map(|i| if k < n { (i + k) % n } else { n - 1 - ((i + k - n) % n) }).collect();
            let lp: Vec<usize> = (0..n).map(|i| l[pi[i]]).collect();
            let Some(vals) = solve(&pp, b, &lp) else { continue };
            let (nv, mut faces, mut next) = assemble(&pp, n, &vals);
            // Pattern corner c is input corner K: π[c], or π[c]+1 reflected.
            let mut input_corner = vec![0usize; n];
            for c in 0..n {
                let kk = if k < n { pi[c] } else { (pi[c] + 1) % n };
                input_corner[kk] = c;
            }
            if k >= n {
                for f in faces.iter_mut() {
                    f.reverse();
                }
                next = outline(nv, &faces);
            }
            let mut sides = Vec::new();
            for i in 0..n {
                let (a, z) = (input_corner[i], input_corner[(i + 1) % n]);
                let mut side = vec![a];
                while *side.last().unwrap() != z {
                    let x = next[*side.last().unwrap()];
                    if x == usize::MAX || side.len() > nv {
                        return None;
                    }
                    side.push(x);
                }
                sides.push(side);
            }
            if (0..n).all(|i| sides[i].len() - 1 == l[i]) {
                return Some((nv, faces, sides));
            }
            return None;
        }
    }
    None
}

impl Template {
    /// A template from a topology: the sides' vertices placed evenly along
    /// the polygon's sides, the rest at the uniform Laplace average.
    fn from_topology(corners: &[(f64, f64)], nv: usize, faces: Vec<[usize; 4]>, sides: Vec<Vec<usize>>) -> Template {
        let n = corners.len();
        let mut pos = vec![(0.0, 0.0); nv];
        let mut fixed = vec![false; nv];
        for i in 0..n {
            let (a, b) = (corners[i], corners[(i + 1) % n]);
            let m = sides[i].len() - 1;
            for (k, &v) in sides[i].iter().enumerate() {
                let f = k as f64 / m as f64;
                pos[v] = (a.0 + (b.0 - a.0) * f, a.1 + (b.1 - a.1) * f);
                fixed[v] = true;
            }
        }
        let c = corners.iter().fold((0.0, 0.0), |s, p| (s.0 + p.0 / n as f64, s.1 + p.1 / n as f64));
        for v in 0..nv {
            if !fixed[v] {
                pos[v] = c;
            }
        }
        let mut t = Template { pos, sides, faces, fixed };
        t.relax();
        t
    }
}

/// A quad mesh for a patch with `corners` (the domain polygon) and `l[i]`
/// edges on side i, or None if no pattern here fits.
pub fn build(corners: &[(f64, f64)], l: &[usize]) -> Option<Template> {
    let n = corners.len();
    if l.len() != n || l.iter().any(|&x| x == 0) || l.iter().sum::<usize>() % 2 != 0 {
        return None;
    }
    let mut t = Template::outline(corners, l);
    if n == 4 && l[0] == l[2] && l[1] == l[3] {
        let s: Vec<Vec<usize>> = t.sides.clone();
        t.grid(&s[0], &s[1], &s[2], &s[3]);
        t.relax();
        return Some(t);
    }
    if matches!(n, 3 | 5 | 6) {
        if let Some(sp) = spokes(l) {
            midpoint(&mut t, l, &sp);
            t.relax();
            return Some(t);
        }
    }
    // Anything else with an even total: Takayama's patterns.
    let (nv, faces, sides) = takayama(l)?;
    Some(Template::from_topology(corners, nv, faces, sides))
}

/// The midpoint pattern: a centre, a spoke to a point on every side, and
/// one grid block per corner.
fn midpoint(t: &mut Template, l: &[usize], sp: &[usize]) {
    let n = l.len();
    let c = t.pos.iter().take(n).fold((0.0, 0.0), |s, p| (s.0 + p.0 / n as f64, s.1 + p.1 / n as f64));
    let center = t.add(c, false);
    // Side i is split t_{i−1} from its first corner.
    let mid: Vec<usize> = (0..n).map(|i| t.sides[i][sp[(i + n - 1) % n]]).collect();
    let spoke: Vec<Vec<usize>> = (0..n).map(|i| t.row(mid[i], center, sp[i])).collect();
    for i in 0..n {
        let prev = (i + n - 1) % n;
        let s0: Vec<usize> = t.sides[i][..=sp[prev]].to_vec();
        let s1 = spoke[i].clone();
        let s2: Vec<usize> = spoke[prev].iter().rev().copied().collect();
        let s3: Vec<usize> = t.sides[prev][sp[(prev + n - 1) % n]..].to_vec();
        t.grid(&s0, &s1, &s2, &s3);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn regular(n: usize) -> Vec<(f64, f64)> {
        (0..n).map(|k| { let a = std::f64::consts::TAU * k as f64 / n as f64; (a.cos(), a.sin()) }).collect()
    }

    /// Every edge inside is shared by two quads, every boundary edge by
    /// one, and the boundary is the sides.
    fn check(t: &Template, l: &[usize]) {
        let mut count: std::collections::HashMap<(usize, usize), i32> = Default::default();
        for f in &t.faces {
            for k in 0..4 {
                let (a, b) = (f[k], f[(k + 1) % 4]);
                *count.entry((a.min(b), a.max(b))).or_default() += 1;
            }
        }
        let mut boundary = 0;
        for (&e, &c) in &count {
            assert!(c == 1 || c == 2, "edge {e:?} in {c} faces");
            if c == 1 {
                boundary += 1;
            }
        }
        assert_eq!(boundary, l.iter().sum::<usize>());
        for (i, s) in t.sides.iter().enumerate() {
            assert_eq!(s.len() - 1, l[i]);
        }
    }

    /// The side equations computed from the faces are the paper's.
    #[test]
    fn equations_from_topology() {
        let eq = |id: usize| { let b = &BASES[id]; let p = parse(b); (p.c.clone(), p.names.iter().zip(&p.cols).map(|(n, c)| (n.to_string(), c.clone())).collect::<Vec<_>>()) };
        // 3-1: l0 = 4 + p1 + p2 + q1 + q2 + 2x, l1 = 1 + p0 + p2 + q2, l2 = 1 + p0 + p1 + q1.
        let (c, cols) = eq(3);
        assert_eq!(c, vec![4, 1, 1]);
        let col = |name: &str| cols.iter().find(|x| x.0 == name).unwrap().1.clone();
        assert_eq!(col("x"), vec![2, 0, 0]);
        assert_eq!(col("q1"), vec![1, 0, 1]);
        assert_eq!(col("q2"), vec![1, 1, 0]);
        // 4-4: c = (4,2,1,1), q1 = (1,0,1,0), x = (2,0,0,0), y = (1,1,0,0).
        let (c, cols) = eq(9);
        assert_eq!(c, vec![4, 2, 1, 1]);
        let col = |name: &str| cols.iter().find(|x| x.0 == name).unwrap().1.clone();
        assert_eq!((col("q1"), col("x"), col("y")), (vec![1, 0, 1, 0], vec![2, 0, 0, 0], vec![1, 1, 0, 0]));
        // 6-2: c = (3,1,1,1,1,1), x = 2 on side 0, y on 0 and 3, q0 on 1 and 5, q3 on 2 and 4.
        let (c, cols) = eq(16);
        assert_eq!(c, vec![3, 1, 1, 1, 1, 1]);
        let col = |name: &str| cols.iter().find(|x| x.0 == name).unwrap().1.clone();
        assert_eq!(col("x"), vec![2, 0, 0, 0, 0, 0]);
        assert_eq!(col("y"), vec![1, 0, 0, 1, 0, 0]);
        assert_eq!(col("q0"), vec![0, 1, 0, 0, 0, 1]);
        assert_eq!(col("q3"), vec![0, 0, 1, 0, 1, 0]);
    }

    #[test]
    fn worked_examples() {
        for (l, faces) in [(vec![2, 2, 4], 4), (vec![10, 2, 12], 20), (vec![5, 3, 7, 3], 18), (vec![1, 1, 1, 1, 2], 2), (vec![6, 2, 1, 1], 10), (vec![3, 3, 3, 3, 3, 3], 14)] {
            let (_, f, _) = takayama(&l).unwrap_or_else(|| panic!("no pattern for {l:?}"));
            assert_eq!(f.len(), faces, "faces for {l:?}");
        }
        assert!(takayama(&[1, 1]).is_none());
    }

    /// Every small input with an even total gets a disk with the sides asked.
    #[test]
    fn exhaustive() {
        let ranges = [(3, 9), (4, 7), (5, 5), (6, 4)];
        for (n, max) in ranges {
            let mut l = vec![1usize; n];
            loop {
                if l.iter().sum::<usize>() % 2 == 0 {
                    let t = build(&regular(n), &l).unwrap_or_else(|| panic!("no pattern for {l:?}"));
                    check(&t, &l);
                    let e = (4 * t.faces.len() + l.iter().sum::<usize>()) / 2;
                    let used: std::collections::HashSet<usize> = t.faces.iter().flatten().copied().collect();
                    assert_eq!(used.len() as i64 - e as i64 + t.faces.len() as i64, 1, "euler for {l:?}");
                }
                let mut k = 0;
                while k < n {
                    l[k] += 1;
                    if l[k] <= max {
                        break;
                    }
                    l[k] = 1;
                    k += 1;
                }
                if k == n {
                    break;
                }
            }
        }
    }

    #[test]
    fn grid_and_midpoint() {
        for l in [vec![3, 2, 3, 2], vec![1, 1, 1, 1]] {
            check(&build(&regular(4), &l).unwrap(), &l);
        }
        for l in [vec![4, 4, 4], vec![2, 2, 2], vec![5, 3, 4]] {
            check(&build(&regular(3), &l).unwrap(), &l);
        }
        for l in [vec![2, 2, 2, 2, 2], vec![3, 4, 3, 4, 2]] {
            check(&build(&regular(5), &l).unwrap(), &l);
        }
    }
}

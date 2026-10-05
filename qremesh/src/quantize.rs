//! Integer lengths for the layout's arcs.
//!
//! Every quad of the layout wants its opposite sides to hold the same number
//! of grid edges, and every arc wants a length close to its geometric
//! length in quads. Each arc lies on at most two quad sides with coefficient
//! ±1 in each, so the constraint matrix is the incidence matrix of a
//! bi-directed graph: the problem Heistermann, Li and Bommes solve as a
//! bi-directed min-deviation flow (SIGGRAPH 2023). This is the simple route
//! to the same answer: the real-valued constrained least squares, rounded,
//! then every remaining violation repaired by the cheapest chain of ±1
//! moves — an augmenting path in that graph — found by Dijkstra.

pub struct Problem {
    /// Per variable: wanted real value and weight.
    pub target: Vec<f64>,
    pub weight: Vec<f64>,
    /// Each constraint: Σ coef · x = 0.
    pub constraints: Vec<Vec<(usize, i64)>>,
}

pub struct Solution {
    pub x: Vec<i64>,
    /// Constraints still violated after repair: parity the graph cannot
    /// fix (an odd cycle of same-sign arcs).
    pub violated: usize,
}

pub fn solve(p: &Problem) -> Solution {
    let n = p.target.len();
    // Constraints with their coefficients merged per variable; an arc on
    // both opposite sides of one quad (a torus cut open into one patch)
    // cancels out.
    let cons: Vec<Vec<(usize, i64)>> = p
        .constraints
        .iter()
        .map(|c| {
            let mut m: std::collections::BTreeMap<usize, i64> = Default::default();
            for &(v, k) in c {
                *m.entry(v).or_default() += k;
            }
            m.into_iter().filter(|&(_, k)| k != 0).collect()
        })
        .filter(|c: &Vec<(usize, i64)>| !c.is_empty())
        .collect();
    let m = cons.len();

    // Real solution with some variables held at integers: x_free =
    // t − W⁻¹Cᵀμ with (C W⁻¹ Cᵀ) μ = C t − d, where d is what the held
    // variables owe each constraint. The matrix is small and may be
    // singular (dependent constraints), so a ridge and Gaussian elimination
    // do.
    let solve_held = |held: &[Option<i64>], target: &[f64], weight: &[f64]| -> Vec<f64> {
        let winv: Vec<f64> = weight.iter().map(|w| 1.0 / w.max(1e-9)).collect();
        let mut x: Vec<f64> = (0..n).map(|v| held[v].map_or(target[v], |h| h as f64)).collect();
        if m == 0 {
            return x;
        }
        let mut a = vec![vec![0.0; m]; m];
        let mut b = vec![0.0; m];
        for i in 0..m {
            for &(v, k) in &cons[i] {
                b[i] += k as f64 * x[v];
            }
            for j in 0..m {
                let mut s = 0.0;
                for &(v, k) in &cons[i] {
                    if held[v].is_some() {
                        continue;
                    }
                    if let Some(&(_, k2)) = cons[j].iter().find(|&&(w, _)| w == v) {
                        s += k as f64 * k2 as f64 * winv[v];
                    }
                }
                a[i][j] = s;
            }
            a[i][i] += 1e-9;
        }
        let mu = gauss(a, b);
        for i in 0..m {
            for &(v, k) in &cons[i] {
                if held[v].is_none() {
                    x[v] -= winv[v] * k as f64 * mu[i];
                }
            }
        }
        x
    };

    // Round one variable at a time, the one nearest an integer first, and
    // solve again for the rest each time (the greedy rounding of mixed-
    // integer quadrangulation). Anything that would go below one is held
    // at one.
    // First a real solution that respects the lower bound of one: a
    // variable that comes out below it is pulled up by a growing penalty
    // and the rest re-solved, until none is below. Rounding starts from
    // there, so the bounds and the equalities can be met together.
    let mut target = p.target.clone();
    let mut weight = p.weight.clone();
    let mut held: Vec<Option<i64>> = vec![None; n];
    let feasible = |held: &[Option<i64>], target: &mut Vec<f64>, weight: &mut Vec<f64>| -> Vec<f64> {
        let mut x = solve_held(held, target, weight);
        for _ in 0..40 {
            let low: Vec<usize> = (0..n).filter(|&v| held[v].is_none() && x[v] < 1.0 - 1e-6).collect();
            if low.is_empty() {
                break;
            }
            for v in low {
                target[v] = 1.25;
                weight[v] *= 4.0;
            }
            x = solve_held(held, target, weight);
        }
        x
    };
    let mut x = feasible(&held, &mut target, &mut weight);
    for _ in 0..n + 1 {
        if held.iter().all(Option::is_some) {
            break;
        }
        let (mut best, mut at) = (f64::INFINITY, usize::MAX);
        for v in 0..n {
            if held[v].is_none() {
                let off = (x[v] - x[v].round()).abs();
                if off < best {
                    best = off;
                    at = v;
                }
            }
        }
        held[at] = Some(x[at].round().max(1.0) as i64);
        // Everything else already within a hair of an integer goes too.
        for v in 0..n {
            if held[v].is_none() && (x[v] - x[v].round()).abs() < 1e-6 && x[v].round() >= 1.0 {
                held[v] = Some(x[v].round() as i64);
            }
        }
        x = feasible(&held, &mut target, &mut weight);
    }
    let mut xi: Vec<i64> = (0..n).map(|v| held[v].unwrap_or(x[v].round().max(1.0) as i64)).collect();
    if let Ok(path) = std::env::var("QREMESH_QUANT_DUMP") {
        let cons_s: Vec<String> = cons.iter().map(|c| format!("[{}]", c.iter().map(|&(v, k)| format!("[{v},{k}]")).collect::<Vec<_>>().join(","))).collect();
        let _ = std::fs::write(path, format!("{{\"target\": {:?}, \"weight\": {:?}, \"cons\": [{}], \"x\": {:?}}}", p.target, p.weight, cons_s.join(","), xi));
    }
    if std::env::var("QREMESH_DEBUG").is_ok() {
        let before: usize = (0..m).filter(|&i| cons[i].iter().map(|&(v, k)| k * xi[v]).sum::<i64>() != 0).count();
        eprintln!("    quantize: {n} arcs, {m} constraints, {before} violated after rounding");
    }

    // Which constraints each variable is in.
    let mut in_cons: Vec<Vec<(usize, i64)>> = vec![Vec::new(); n];
    for (i, c) in cons.iter().enumerate() {
        for &(v, k) in c {
            in_cons[v].push((i, k));
        }
    }
    let residual = |xi: &[i64], i: usize| -> i64 { cons[i].iter().map(|&(v, k)| k * xi[v]).sum() };
    let cost_of = |xi: &[i64], v: usize, d: i64| -> f64 {
        let (t, w) = (p.target[v], p.weight[v]);
        let (a, b) = (xi[v] as f64, (xi[v] + d) as f64);
        w * ((b - t) * (b - t) - (a - t) * (a - t))
    };

    for _round in 0..10 * m + 10 {
        let worst = (0..m).max_by_key(|&i| residual(&xi, i).abs());
        let Some(k0) = worst else { break };
        let r0 = residual(&xi, k0);
        if r0 == 0 {
            break;
        }
        let total = |xi: &[i64]| (0..m).map(|i| residual(xi, i).abs()).sum::<i64>();
        match augment(&xi, k0, -r0.signum(), &cons, &in_cons, &cost_of) {
            Some(path) => {
                if std::env::var("QREMESH_DEBUG").is_ok() {
                    eprintln!("    constraint {k0} residual {r0}: path {path:?}");
                }
                let before = total(&xi);
                let mut next = xi.clone();
                for &(v, d) in &path {
                    next[v] += d;
                }
                if total(&next) >= before || next.iter().any(|&x| x < 1) {
                    if std::env::var("QREMESH_DEBUG").is_ok() {
                        eprintln!("    path made no progress ({before} -> {})", total(&next));
                    }
                    break;
                }
                xi = next;
            }
            None => {
                if std::env::var("QREMESH_DEBUG").is_ok() {
                    eprintln!("    no path for constraint {k0} (residual {r0})");
                }
                break;
            }
        }
    }
    let violated = (0..m).filter(|&i| residual(&xi, i) != 0).count();
    Solution { x: xi, violated }
}

/// The cheapest chain of ±1 moves that changes constraint `k0`'s residual
/// by `s0` and leaves every other residual no worse, by Dijkstra over
/// states (constraint, change still owed to it).
fn augment(
    xi: &[i64],
    k0: usize,
    s0: i64,
    cons: &[Vec<(usize, i64)>],
    in_cons: &[Vec<(usize, i64)>],
    cost_of: &dyn Fn(&[i64], usize, i64) -> f64,
) -> Option<Vec<(usize, i64)>> {
    use std::collections::BinaryHeap;
    #[derive(PartialEq)]
    struct Item(f64, usize, i64);
    impl Eq for Item {}
    impl PartialOrd for Item {
        fn partial_cmp(&self, o: &Self) -> Option<std::cmp::Ordering> {
            Some(self.cmp(o))
        }
    }
    impl Ord for Item {
        fn cmp(&self, o: &Self) -> std::cmp::Ordering {
            o.0.total_cmp(&self.0)
        }
    }
    let residual = |i: usize| -> i64 { cons[i].iter().map(|&(v, k)| k * xi[v]).sum() };
    // A move's cost, shifted so every move costs something: fewer moves
    // first, cheaper moves among chains of the same length.
    let shift = 1.0 + cons.iter().flatten().map(|&(v, _)| cost_of(xi, v, 1).abs().max(cost_of(xi, v, -1).abs())).fold(0.0, f64::max);
    let state = |k: usize, s: i64| k * 2 + if s > 0 { 1 } else { 0 };
    let mut dist: Vec<f64> = vec![f64::INFINITY; cons.len() * 2];
    let mut from: Vec<Option<(usize, i64, usize)>> = vec![None; cons.len() * 2];
    let came_by = |from: &[Option<(usize, i64, usize)>], k: usize, s: i64| -> Option<usize> { from[state(k, s)].map(|(_, _, v)| v) };
    let mut heap = BinaryHeap::new();
    dist[state(k0, s0)] = 0.0;
    heap.push(Item(0.0, k0, s0));
    let mut done: Option<(usize, i64, usize, i64)> = None;
    while let Some(Item(d, k, s)) = heap.pop() {
        if d > dist[state(k, s)] {
            continue;
        }
        let entered = came_by(&from, k, s);
        for &(v, c) in &cons[k] {
            // Change x_v by δ so that c·δ = s. Not the arc the chain came
            // in on: that would only undo the last move.
            if entered == Some(v) {
                continue;
            }
            let delta = s * c;
            if xi[v] + delta < 1 {
                continue;
            }
            let step = cost_of(xi, v, delta) + shift;
            let other = in_cons[v].iter().find(|&&(k2, _)| k2 != k);
            match other {
                None => {
                    done = Some((k, s, v, delta));
                    break;
                }
                Some(&(k2, c2)) => {
                    let r2 = residual(k2);
                    let r2_new = r2 + c2 * delta;
                    if r2_new.abs() < r2.abs() {
                        done = Some((k, s, v, delta));
                        break;
                    }
                    // Owed to k2: undo the change just made to it.
                    let s2 = -c2 * delta;
                    let nd = d + step;
                    if nd < dist[state(k2, s2)] {
                        dist[state(k2, s2)] = nd;
                        from[state(k2, s2)] = Some((k, s, v));
                        let _ = delta;
                        heap.push(Item(nd, k2, s2));
                    }
                }
            }
        }
        if done.is_some() {
            break;
        }
    }
    if std::env::var("QREMESH_DEBUG").is_ok() {
        let reached = dist.iter().filter(|d| d.is_finite()).count();
        eprintln!("    augment from {k0} ({s0}): reached {reached} states, done {:?}", done);
    }
    let (mut k, mut s, v, delta) = done?;
    let mut path = vec![(v, delta)];
    while (k, s) != (k0, s0) {
        let (pk, ps, pv) = from[state(k, s)]?;
        // The move from (pk, ps) through pv changed x_pv by ps·c(pk, pv).
        let c = cons[pk].iter().find(|&&(w, _)| w == pv)?.1;
        path.push((pv, ps * c));
        k = pk;
        s = ps;
    }
    Some(path)
}

pub fn gauss_pub(a: Vec<Vec<f64>>, b: Vec<f64>) -> Vec<f64> {
    gauss(a, b)
}

fn gauss(mut a: Vec<Vec<f64>>, mut b: Vec<f64>) -> Vec<f64> {
    let n = b.len();
    for col in 0..n {
        let pivot = (col..n).max_by(|&i, &j| a[i][col].abs().total_cmp(&a[j][col].abs())).unwrap();
        a.swap(col, pivot);
        b.swap(col, pivot);
        let d = a[col][col];
        if d.abs() < 1e-300 {
            continue;
        }
        for row in col + 1..n {
            let f = a[row][col] / d;
            if f == 0.0 {
                continue;
            }
            for k in col..n {
                a[row][k] -= f * a[col][k];
            }
            b[row] -= f * b[col];
        }
    }
    let mut x = vec![0.0; n];
    for col in (0..n).rev() {
        let mut s = b[col];
        for k in col + 1..n {
            s -= a[col][k] * x[k];
        }
        x[col] = if a[col][col].abs() < 1e-300 { 0.0 } else { s / a[col][col] };
    }
    x
}

/// A patch for `parity`: its sides as lists of variables.
pub struct Sides {
    pub sides: Vec<Vec<usize>>,
}

const NONE: usize = usize::MAX;

#[derive(PartialEq)]
struct Item(f64, usize, usize, i64);
impl Eq for Item {}
impl PartialOrd for Item {
    fn partial_cmp(&self, o: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(o))
    }
}
impl Ord for Item {
    fn cmp(&self, o: &Self) -> std::cmp::Ordering {
        o.0.total_cmp(&self.0)
    }
}

struct Net<'a> {
    target: &'a [f64],
    weight: &'a [f64],
    patches: &'a [Sides],
    /// Patches each variable is on.
    on: Vec<Vec<usize>>,
}

impl<'a> Net<'a> {
    fn odd_kind(&self, p: usize) -> bool {
        matches!(self.patches[p].sides.len(), 3 | 5)
    }
    fn total(&self, x: &[i64], p: usize) -> i64 {
        self.patches[p].sides.iter().flatten().map(|&a| x[a]).sum()
    }
    /// Spokes of an odd polygon's midpoint pattern: S_i = t_{i−1} + t_{i+1}
    /// solved by the alternating sum (n odd), times two.
    fn spokes2(&self, x: &[i64], p: usize) -> Vec<i64> {
        let n = self.patches[p].sides.len();
        let s: Vec<i64> = self.patches[p].sides.iter().map(|side| side.iter().map(|&a| x[a]).sum()).collect();
        // t_k sits in S_{k+1} and S_{k−1}; walking k+1, k+3, … alternately.
        (0..n).map(|k| (0..n).map(|j| if j % 2 == 0 { s[(k + 1 + 2 * j) % n] } else { -s[(k + 1 + 2 * j) % n] }).sum()).collect()
    }

    /// The cheapest chain of ±1 changes starting from `starts` (patch the
    /// chain leaves, variable, sign), carried straight across four-sided
    /// patches, until it reaches a patch `accept` takes; in an odd polygon
    /// that is not accepted it may go on (`branch`). Applied if found.
    fn chain(&self, x: &mut [i64], starts: &[(usize, usize, i64)], accept: &dyn Fn(&[i64], usize) -> bool, branch: bool) -> bool {
        use std::collections::{BinaryHeap, HashMap};
        let delta = |x: &[i64], a: usize, d: i64| {
            let (t, w) = (self.target[a], self.weight[a]);
            let (u, v) = (x[a] as f64, (x[a] + d) as f64);
            w * ((v - t) * (v - t) - (u - t) * (u - t))
        };
        // Every step costs something positive, or Dijkstra goes round a
        // cycle of moves that each bring an arc nearer its target forever:
        // shifted by the largest gain any single move offers.
        let shift = 1.0 + (0..x.len()).flat_map(|a| [-delta(x, a, 1), -delta(x, a, -1)]).fold(0.0, f64::max);
        let cost = |x: &[i64], a: usize, d: i64| delta(x, a, d) + shift;
        let mut dist: HashMap<(usize, usize, i64), f64> = HashMap::new();
        let mut from: HashMap<(usize, usize, i64), Option<(usize, usize, i64)>> = HashMap::new();
        let mut heap = BinaryHeap::new();
        let push = |p: usize, a: usize, d: i64, base: f64, prev: Option<(usize, usize, i64)>, heap: &mut BinaryHeap<Item>, dist: &mut HashMap<(usize, usize, i64), f64>, from: &mut HashMap<(usize, usize, i64), Option<(usize, usize, i64)>>| {
            if x[a] + d < 1 {
                return;
            }
            let q = self.on[a].iter().copied().find(|&q| q != p).unwrap_or(NONE);
            let nd = base + cost(x, a, d);
            let k = (a, q, d);
            if dist.get(&k).map_or(true, |&o| nd < o) {
                dist.insert(k, nd);
                from.insert(k, prev);
                heap.push(Item(nd, a, q, d));
            }
        };
        for &(p, a, d) in starts {
            push(p, a, d, 0.0, None, &mut heap, &mut dist, &mut from);
        }
        let mut done = None;
        let mut pops = 0usize;
        while let Some(Item(dd, a, q, d)) = heap.pop() {
            if dist.get(&(a, q, d)).map_or(false, |&o| dd > o) {
                continue;
            }
            pops += 1;
            if pops > 8 * self.on.len() + 1000 {
                break;
            }
            if q == NONE || accept(x, q) {
                done = Some((a, q, d));
                break;
            }
            let here = Some((a, q, d));
            if self.patches[q].sides.len() == 4 {
                let Some(i) = (0..4).find(|&i| self.patches[q].sides[i].contains(&a)) else { continue };
                for &b in &self.patches[q].sides[(i + 2) % 4] {
                    if b != a {
                        push(q, b, d, dd, here, &mut heap, &mut dist, &mut from);
                    }
                }
            } else if branch && self.odd_kind(q) {
                for &b in self.patches[q].sides.iter().flatten() {
                    if b != a {
                        for d2 in [1, -1] {
                            push(q, b, d2, dd, here, &mut heap, &mut dist, &mut from);
                        }
                    }
                }
            }
        }
        let Some(mut k) = done else { return false };
        loop {
            x[k.0] += k.2;
            match from[&k] {
                Some(prev) => k = prev,
                None => break,
            }
        }
        true
    }
}

/// Make every three- and five-sided patch fillable by the midpoint pattern
/// while every four-sided one keeps its opposite sides equal. The pattern
/// needs an even side total (each spoke meets two half sides) and every
/// spoke at least one (no side as long as the ones either side of it
/// allow). Changing an arc by ±1 flips the parity of both patches on it, so
/// odd patches are paired up by the cheapest chain of changes between them,
/// carried straight across four-sided patches, where an arc of the
/// opposite side must change by the same amount; an arc on the surface's
/// boundary ends a chain by itself. A spoke short of one is raised by
/// lengthening the two sides it meets, each by a chain that ends in any
/// patch that is not a quad, and the parity repaired again. -> patches
/// still unfillable.
pub fn parity(x: &mut [i64], target: &[f64], weight: &[f64], patches: &[Sides]) -> usize {
    let mut on: Vec<Vec<usize>> = vec![Vec::new(); x.len()];
    for (p, ps) in patches.iter().enumerate() {
        for s in &ps.sides {
            for &a in s {
                if !on[a].contains(&p) {
                    on[a].push(p);
                }
            }
        }
    }
    let net = Net { target, weight, patches, on };
    let odd = |x: &[i64]| (0..patches.len()).filter(|&p| net.odd_kind(p) && net.total(x, p) % 2 != 0).collect::<Vec<_>>();
    let thin = |x: &[i64]| (0..patches.len()).filter(|&p| net.odd_kind(p)).flat_map(|p| net.spokes2(x, p).into_iter().enumerate().filter(|&(_, t2)| t2 < 2).map(move |(k, _)| (p, k)).collect::<Vec<_>>()).collect::<Vec<_>>();
    for _round in 0..12 {
        for _ in 0..patches.len() + 1 {
            let Some(&start) = odd(x).first() else { break };
            let starts: Vec<(usize, usize, i64)> = patches[start].sides.iter().flatten().flat_map(|&a| [(start, a, 1), (start, a, -1)]).collect();
            let accept = |x: &[i64], q: usize| q != start && net.odd_kind(q) && net.total(x, q) % 2 != 0;
            if !net.chain(x, &starts, &accept, true) {
                break;
            }
        }
        let short = thin(x);
        if short.is_empty() {
            break;
        }
        for (p, k) in short {
            let n = patches[p].sides.len();
            if net.spokes2(x, p)[k] >= 2 {
                continue;
            }
            for side in [(k + n - 1) % n, (k + 1) % n] {
                let starts: Vec<(usize, usize, i64)> = patches[p].sides[side].iter().map(|&a| (p, a, 1)).collect();
                let accept = |_: &[i64], q: usize| q != p && patches[q].sides.len() != 4;
                net.chain(x, &starts, &accept, false);
            }
        }
    }
    let mut bad: Vec<usize> = odd(x);
    bad.extend(thin(x).into_iter().map(|(p, _)| p));
    bad.sort_unstable();
    bad.dedup();
    bad.len()
}

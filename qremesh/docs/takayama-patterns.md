# Spec: pattern-based quadrangulation of N-sided patches (N = 2..6)

> Implemented in `src/pattern.rs` (n = 3..6; n = 2 is in the table but unused). Written from the
> paper and from reading patchgen, in our own words. The Python harness §10 mentions lived in a
> session scratchpad and is gone; its checks are ported as the Rust tests in `pattern.rs`.

Clean-room specification of Takayama, Panozzo, Sorkine-Hornung, *Pattern-Based
Quadrangulation for N-Sided Patches*, SGP 2014 (CGF 33(5)), as realised by the
reference "patchgen" implementation. It covers everything an implementer needs.
Every pattern table here was machine-checked against the reference topology (§10).

---

## 0. Vocabulary and conventions

* **Patch**: a quad mesh homeomorphic to a disk, with `n` marked boundary vertices
  called **corners** `K_0 … K_{n-1}`.
* **Orientation**: all faces are counter-clockwise (CCW) in the 2D layout. Walking the
  boundary CCW (interior on the left) visits `K_0, K_1, …, K_{n-1}` in that order.
* **Side `i`** is the boundary path from `K_i` CCW to `K_{i+1}` (indices mod n).
  `l_i` is its number of edges. For n = 2, side 0 runs K0→K1 and side 1 runs K1→K0.
* **Chord** (also called an edge flow, or a dual strip): two edges are in the same chord
  when they are opposite edges of a common quad. Close that relation transitively.
  Each edge belongs to exactly one chord. In every base pattern below, every chord is
  an open path that starts and ends on boundary edges. No chord crosses itself, and
  none is a closed loop (all verified).
* **Inserting k edge flows into a chord** means replacing each edge of the chord by
  `k+1` edges, so the strip of quads becomes `k+1` parallel strips. This document
  calls `m = 1 + k` the chord's **multiplicity**. One edge-loop insertion (split
  every edge of the chord at its midpoint and connect the midpoints across each quad)
  raises `m` by 1. The order in which insertions are applied does not change the
  final connectivity.

All variables (paddings `p_i`, internal paddings `q_i`, edge-flow counts `x, y, z, w`)
are **non-negative integers** with no upper bound. No variable has a lower bound of 1.

---

## 1. Problem

**Input.** `n ∈ {2,…,6}` and integers `l_0 … l_{n-1}`, each `l_i ≥ 1`, with
`Σ l_i` even.

* An even sum is necessary: in a quad mesh, `4F = B + 2E_int`, so the boundary edge
  count `B` is even.
* For n = 2 the input `(1,1)` has no solution: it would be two parallel edges and no
  quad. It must be rejected. Every other valid input has a solution (§7).
* `l_i = 0` is outside the method's domain; reject it.

**Output.** A pure quad mesh of a disk with corner vertices `K_0 … K_{n-1}`. Side `i`
(CCW from `K_i` to `K_{i+1}`) has exactly `l_i` edges. Every vertex has a 2D
position (§8).

Sanity identities, true for every output (use them in tests), with `B = Σ l_i`:
`V − E + F = 1`, `E = (4F + B)/2`, so `V = F + 1 + B/2`.

---

## 2. Pipeline

```
choose (pattern P, permutation π, variable vector v)          §6
   l' = l permuted by π   (pattern side i  <->  input side π[i])
build base pattern P (a few quads, corners C0..C_{n-1})       §5
refine chords: multiplicity m = 1 + (its parameter)           §4
add padding strips: p_{n-1} strips on side n-1, then          §3
    p_{n-2} on side n-2, …, then p_0 on side 0
relabel corners back to input indexing; flip faces if π is a reflection   §6.4
place boundary on a regular n-gon; uniform-Laplacian interior            §8
```

The pattern is built for the permuted side counts `l'`. Every constraint row in §5
is written in terms of `l'`, here simply called `l`.

---

## 3. Padding (`p_i`) exactly

### 3.1 Meaning
`p_i` is the number of **padding strips** glued along pattern side `i`. One strip is a
row of quads lying along the whole current side `i`, outside the current mesh.
Equivalently, padding is the inverse of the paper's *trimming*. If side `i` has
neighbours with more than one edge, you can cut a `d × l_i` regular grid off side `i`
and shorten both neighbouring sides by `d`.

**Effect of one strip on side i** (current side `i` length `L`):
* It adds `L` quads and `L + 1` vertices.
* Side `i` keeps length `L`. Its new path is the strip's outer edge.
* Side `i−1` and side `i+1` each gain **one** edge. For n = 2, both neighbours are
  the other side, so the other side gains **2**.
* The two outer end vertices of the strip become the new corners `C_i` and `C_{i+1}`.
  The old corners become ordinary boundary vertices.

So in every pattern's constraint system, the column of `p_i` is
`+1 in rows i−1 and i+1` (for n = 2: `+2` in row `1−i`).

### 3.2 Procedure (must follow this order to reproduce reference connectivity)

```
for i = n-1 down to 0:
    repeat p_i times:
        w_0 … w_L := current boundary vertices of side i, walking CCW from corner C_i to C_{i+1}
        create new vertices u_0 … u_L
        for k = 0 … L-1:  add quad (w_{k+1}, w_k, u_k, u_{k+1})      # CCW, lies outside
        C_i     := u_0
        C_{i+1} := u_L
```

The quad `(w_{k+1}, w_k, u_k, u_{k+1})` uses the boundary edge in the direction
opposite to its existing face, so orientation stays consistent. Because sides are
padded in the order n−1, n−2, …, 0, a strip on side `i` also covers the extension
edges that earlier strips on side `i+1` added to side `i`. This matters only for
reproducing the reference connectivity exactly. Any order gives a valid mesh with the
same side counts, but face counts and layouts can differ.

### 3.3 Internal padding `q_i`
Some patterns have a parameter `q_i`. It is a chord **inside** the base pattern
(refined as in §4) whose boundary effect equals that of `p_i`: +1 on sides `i−1` and
`i+1`. Its column in the constraint matrix equals `p_i`'s column. Trading one unit
between `p_i` and `q_i` "translates a singularity" without changing the boundary. The
default selection breaks this ambiguity with constraints of the form `p_i ≤ q_i`
(§5, §6).

---

## 4. Chord refinement (edge-flow insertion) as grid blocks

Implement refinement directly, without iterated edge-loop insertion:

1. Union-find the base pattern's edges into chords (opposite edges of each quad).
2. Give every chord multiplicity 1. For each parameter `t ∈ {x, y, z, w, q_i}` of the
   pattern, add the parameter's value to the multiplicity of the chord that contains
   its seed edge (the chord tables below list each parameter's chord in full).
3. Subdivide every base edge `(a,b)` into `m(chord)` segments, creating `m−1` new
   vertices. Store them once per undirected edge so that neighbouring quads share
   them. Reverse the list when traversing the edge as `(b,a)`.
4. For a base quad `(a,b,c,d)` (CCW), let `M = m(ab) = m(dc)` and `N = m(bc) = m(ad)`.
   Build an `(M+1) × (N+1)` vertex grid `G[i][j]`:
   * The border comes from the subdivided edges: `G[i][0]` along a→b,
     `G[M][j]` along b→c, `G[i][N]` along d→c, `G[0][j]` along a→d.
   * Interior grid vertices are new.
   * Emit the quads `(G[i][j], G[i+1][j], G[i+1][j+1], G[i][j+1])` for `0≤i<M`,
     `0≤j<N`. These are CCW.
5. The base corner vertices `C_k` stay the corners.

Faces after refinement: `Σ_{base quads} m(ab)·m(bc)`.

Boundary effect: a chord that reaches the boundary on side `s` through `r` of its
boundary edges contributes `r · (m−1)` extra edges to side `s`. That is where the
x/y/z/w/q columns in §5 come from. For example, a chord whose both ends lie on side 0
gives coefficient 2.

---

## 5. Pattern catalogue

Each pattern lists the following.
* **Faces**: base quads as CCW vertex lists. `C_k` are corners; `V_k` are other vertices.
* **Base sides**: the side counts `c = (c_0..c_{n-1})` of the unrefined, unpadded base.
* **Chords**: every chord's edges, with its parameter. "fixed" means `m = 1` always.
* **Variables**: the variable vector `v` in canonical order. This order is used for
  tie-breaking (§6.3).
* **Equations**: `l_i = c_i + …`, i.e. the rows of `A v = l − c`.
* **Window**: the variable whose range is centred in stage 2 of §6.3 ("—" if none).
* **Extra**: extra inequalities applied in the default selection.
* **Objective**: what the default selection maximises.

Default selection tries patterns in this order (§6): n=2: 0,1 · n=3: 0,1,2 ·
n=4: 0,1,2,3,4 · n=5: 0,1,2,3 · n=6: 0,1,2,3. Patterns **3-3** and **5-4** exist in the
reference but are **never** reached by default selection. They are only alternatives
for a user "switch pattern" feature. They are documented for completeness, and you may
omit them.

All patterns: variables ≥ 0, integer. Paddings `p_i` not listed in a pattern's
variable list are 0.

### n = 2

**2-0** (the paper's doublet pattern 0, singularities on the boundary)
* Faces: `C0 V0 V1 C1`. Side 0 = C0→V0→V1→C1 (3 edges); side 1 = C1→C0 (1 edge).
* Base sides c = (3, 1).
* Chords: `y`: {V0-V1, C0-C1}; fixed: {C0-V0, C1-V1}.
* Variables (p0, p1, y).
* `l0 = 3 + 2p1 + y`, `l1 = 1 + 2p0 + y`.
* Window: y. Extra: none. Objective: max p0+p1.

**2-1** (only needed for (2,2))
* Faces: `C0 V0 C1 V1`. Side 0 = C0→V0→C1, side 1 = C1→V1→C0.
* c = (2, 2).
* Chords: `x`: {C0-V0, C1-V1}; `y`: {C1-V0, C0-V1}.
* Variables (p0, p1, x, y).
* `l0 = 2 + 2p1 + x + y`, `l1 = 2 + 2p0 + x + y`.
* Window: x. Extra: none. Objective: max p0+p1.

### n = 3

**3-0** (one quad with a boundary valence-2 vertex)
* Faces: `C0 V0 C1 C2`. Side 0 = C0→V0→C1.
* c = (2, 1, 1). No chord parameters.
* Variables (p0, p1, p2).
* `l0 = 2 + p1 + p2`, `l1 = 1 + p0 + p2`, `l2 = 1 + p0 + p1`.
* The solution is unique when it exists (3×3 system is invertible):
  `p0 = (l1+l2−l0)/2`, `p1 = (l0+l2−l1)/2 − 1`, `p2 = (l0+l1−l2)/2 − 1`; feasible iff all three are ≥ 0.
* Window/extra/objective: none needed.

**3-1** (two singularities, x flows across the triangle)
* Faces: `C0 V0 V3 C2 | V0 V1 V2 V3 | C2 V3 V2 C1`.
  Side 0 = C0→V0→V1→V2→C1 (4 edges). V3 is interior.
* c = (4, 1, 1).
* Chords: `x`: {C0-V0, C2-V3, C1-V2}; `q1`: {V0-V3, C0-C2, V1-V2};
  `q2`: {V0-V1, V2-V3, C1-C2}.
* Variables (p0, p1, p2, q1, q2, x).
* `l0 = 4 + p1 + p2 + q1 + q2 + 2x`, `l1 = 1 + p0 + p2 + q2`, `l2 = 1 + p0 + p1 + q1`.
* Window: x. Extra: p1 ≤ q1, p2 ≤ q2. Objective: max p0+p1+p2.

**3-2** (alternative, from Takayama et al. 2013)
* Faces: `C0 V0 V3 C2 | V0 V1 V4 V3 | C1 V2 V4 V1 | C2 V3 V4 V2`.
  Side 0 = C0→V0→V1→C1, side 1 = C1→V2→C2. V3, V4 interior.
* c = (3, 2, 1).
* Chords: `x`: {C0-V0, C2-V3, V2-V4, C1-V1}; `q2`: {V0-V1, V3-V4, C2-V2};
  fixed: {V0-V3, C0-C2, V1-V4, C1-V2}.
* Variables (p0, p1, p2, q2, x).
* `l0 = 3 + p1 + p2 + q2 + 2x`, `l1 = 2 + p0 + p2 + q2`, `l2 = 1 + p0 + p1` (both ends of the x chord are on side 0).
* Window: x. Extra: p2 ≤ q2. Objective: max p0+p1+p2.

**3-3** (not used by default)
* Faces: `C0 V0 V1 V5 | V1 V2 C1 V5 | C1 V3 V6 V5 | V3 C2 V4 V6 | V4 C0 V5 V6`.
  Side 0 = C0→V0→V1→V2→C1, side 1 = C1→V3→C2, side 2 = C2→V4→C0.
* c = (4, 2, 2).
* Chords: `x`: {C0-V0, V1-V5, C1-V2}; `q2`: {V0-V1, C0-V5, C2-V3, V4-V6};
  `q1`: {V1-V2, C1-V5, V3-V6, C2-V4}; fixed: {C1-V3, V5-V6, C0-V4}.
* Variables (p0, p1, p2, q1, q2, x).
* `l0 = 4 + p1 + p2 + q1 + q2 + 2x`, `l1 = 2 + p0 + p2 + q2`, `l2 = 2 + p0 + p1 + q1`.
* Window: x. Extra: p1 ≤ q1, p2 ≤ q2. Objective: max p0+p1+p2.

### n = 4

**4-0** (regular grid)
* Faces: `C0 C1 C2 C3`. c = (1,1,1,1).
* Variables (p0, p1); p2 = p3 = 0. The reference drops them because their columns
  duplicate p0 and p1.
* `l0 = 1 + p1`, `l1 = 1 + p0`, `l2 = 1 + p1`, `l3 = 1 + p0`. The solution is
  unique; the result is an `l0 × l1` grid.

**4-1**
* Faces: `C0 V0 V2 C3 | V0 C1 V1 V2 | V1 C2 C3 V2`.
  Side 0 = C0→V0→C1, side 1 = C1→V1→C2. V2 interior.
* c = (2, 2, 1, 1).
* Chords: `x`: {C0-V0, C3-V2, C2-V1}; fixed: {V0-V2, C0-C3, C1-V1}; fixed: {C1-V0, V1-V2, C2-C3}.
* Variables (p0, p1, p2, p3, x).
* `l0 = 2 + p1 + p3 + x`, `l1 = 2 + p0 + p2 + x`, `l2 = 1 + p1 + p3`, `l3 = 1 + p0 + p2`.
* Window: — . Extra: p0 ≤ p2, p1 ≤ p3. Objective: max **p0+p1** (only these two).

**4-2**
* Faces: `C0 V0 C2 C3 | V0 V1 C1 C2`. Side 0 = C0→V0→V1→C1.
* c = (3, 1, 1, 1).
* Chords: `x`: {V0-V1, C1-C2}; `y`: {C2-V0, C0-C3, C1-V1}; fixed: {C0-V0, C2-C3}.
* Variables (p0, p1, p2, p3, x, y).
* `l0 = 3 + p1 + p3 + x + y`, `l1 = 1 + p0 + p2 + x`, `l2 = 1 + p1 + p3`, `l3 = 1 + p0 + p2 + y`.
* Window: —. Extra: p0 ≤ p2, p1 ≤ p3. Objective: max p0+p1.

**4-3**
* Faces: `C0 V0 V3 C3 | V0 V1 V2 V3 | V1 C1 C2 V2 | C2 C3 V3 V2`.
  Side 0 = C0→V0→V1→C1. V2, V3 interior.
* c = (3, 1, 1, 1).
* Chords: `x`: {C0-V0, C3-V3, C1-V1, C2-V2}; `q1`: {V0-V1, V2-V3, C2-C3};
  fixed: {V0-V3, C0-C3, V1-V2, C1-C2}.
* Variables (p0, p1, p2, p3, q1, x).
* `l0 = 3 + p1 + p3 + q1 + 2x`, `l1 = 1 + p0 + p2`, `l2 = 1 + p1 + p3 + q1`, `l3 = 1 + p0 + p2`.
* Window: —. Extra: p0 ≤ p2, p1 ≤ p3, p3 ≤ q1. Objective: max p0+p1.

**4-4**
* Faces: `C0 V0 V6 C3 | V0 V1 V5 V6 | V1 V2 V4 V5 | V2 C1 V3 V4 | V3 C2 V5 V4 | C2 C3 V6 V5`.
  Side 0 = C0→V0→V1→V2→C1, side 1 = C1→V3→C2. V4, V5, V6 interior.
* c = (4, 2, 1, 1).
* Chords: `x`: {C0-V0, C3-V6, C1-V2, V3-V4, C2-V5}; `q1`: {V0-V1, V5-V6, C2-C3};
  `y`: {V1-V2, V4-V5, C2-V3}; fixed: {V0-V6, C0-C3, V1-V5, V2-V4, C1-V3}.
* Variables (p0, p1, p2, p3, q1, x, y).
* `l0 = 4 + p1 + p3 + q1 + 2x + y`, `l1 = 2 + p0 + p2 + y`, `l2 = 1 + p1 + p3 + q1`, `l3 = 1 + p0 + p2`.
* Window: —. Extra: p0 ≤ p2, p1 ≤ p3, p3 ≤ q1. Objective: max p0+p1.

### n = 5

**5-0**
* Faces: `V0 C3 C4 C0 | V0 C1 C2 C3`. Side 0 = C0→V0→C1.
* c = (2,1,1,1,1). No chord parameters.
* Variables (p0..p4).
* `l0 = 2 + p1 + p4`, `l1 = 1 + p0 + p2`, `l2 = 1 + p1 + p3`, `l3 = 1 + p2 + p4`, `l4 = 1 + p0 + p3`.
* The 5×5 system is invertible, so the solution is unique when it exists.

**5-1**
* Faces: `C0 V0 C1 C2 | C0 C2 C3 C4`. Side 0 = C0→V0→C1.
* c = (2,1,1,1,1).
* Chords: `x`: {C0-V0, C1-C2}; `q4`: {C1-V0, C0-C2, C3-C4}; fixed: {C2-C3, C0-C4}.
* Variables (p0, p1, p2, p3, p4, q4, x).
* `l0 = 2 + p1 + p4 + q4 + x`, `l1 = 1 + p0 + p2 + x`, `l2 = 1 + p1 + p3`,
  `l3 = 1 + p2 + p4 + q4`, `l4 = 1 + p0 + p3`.
* Window: x. Extra: p4 ≤ q4. Objective: max p0+…+p4.

**5-2**
* Faces: `C0 V0 V3 V4 | C1 V4 V3 V2 | V0 V1 V2 V3 | V4 C3 C4 C0 | V4 C1 C2 C3`.
  Side 0 = C0→V0→V1→V2→C1. V3, V4 interior.
* c = (4,1,1,1,1).
* Chords: `x`: {C0-V0, V3-V4, C1-V2}; `q4`: {V0-V3, C0-V4, V1-V2, C3-C4};
  `q1`: {C1-V4, V2-V3, V0-V1, C2-C3}; `q0`: {C3-V4, C0-C4, C1-C2}.
* Variables (p0, p1, p2, p3, p4, q0, q1, q4, x).
* `l0 = 4 + p1 + p4 + q1 + q4 + 2x`, `l1 = 1 + p0 + p2 + q0`, `l2 = 1 + p1 + p3 + q1`,
  `l3 = 1 + p2 + p4 + q4`, `l4 = 1 + p0 + p3 + q0`.
* Window: x. Extra: p0 ≤ q0, p1 ≤ q1, p4 ≤ q4. Objective: max Σp.

**5-3**
* Faces: `C0 V0 V5 C4 | V0 V1 V6 V5 | V1 V2 V7 V6 | V2 V3 V8 V7 | V3 C1 V4 V8 | V4 C2 V7 V8 | C2 C3 V6 V7 | C3 C4 V5 V6`.
  Side 0 = C0→V0→V1→V2→V3→C1, side 1 = C1→V4→C2. V5..V8 interior.
* c = (5,2,1,1,1).
* Chords: `x`: {C0-V0, C4-V5, C1-V3, V4-V8, C2-V7, C3-V6}; `q4`: {V0-V1, V5-V6, C3-C4};
  `q1`: {V1-V2, V6-V7, C2-C3}; `y`: {V2-V3, V7-V8, C2-V4};
  fixed: {V0-V5, C0-C4, V1-V6, V2-V7, V3-V8, C1-V4}.
* Variables (p0, p1, p2, p3, p4, q1, q4, x, y).
* `l0 = 5 + p1 + p4 + q1 + q4 + 2x + y`, `l1 = 2 + p0 + p2 + y`, `l2 = 1 + p1 + p3 + q1`,
  `l3 = 1 + p2 + p4 + q4`, `l4 = 1 + p0 + p3`.
* Window: x. Extra: p1 ≤ q1, p4 ≤ q4. Objective: max Σp.

**5-4** (not used by default)
* Faces: `C0 V0 V7 V6 | V0 V1 C1 V2 | V2 V3 V7 V0 | V3 C2 V4 V7 | V4 V5 V6 V7 | V5 C3 C4 V6`.
  Side 0 = C0→V0→V1→C1, side 1 = C1→V2→V3→C2, side 2 = C2→V4→V5→C3, side 4 = C4→V6→C0. V7 interior.
* c = (3,3,3,1,2).
* Chords: `x`: {V0-V1, C1-V2}; `q0`: {V0-V7, C0-V6, V2-V3}; `q1`: {C0-V0, V6-V7, V4-V5};
  fixed: {C1-V1, V0-V2, V3-V7, C2-V4}, {C2-V3, V4-V7, V5-V6, C3-C4}, {C3-V5, C4-V6}.
* Variables (p0, p1, p2, p3, p4, q0, q1, x).
* `l0 = 3 + p1 + p4 + q1 + x`, `l1 = 3 + p0 + p2 + q0 + x`, `l2 = 3 + p1 + p3 + q1`,
  `l3 = 1 + p2 + p4`, `l4 = 2 + p0 + p3 + q0`.
* Window: x. Objective: max Σp. Reference extras are p1 ≤ q0 and p4 ≤ q1. Their
  comments say "p1≤q1, p4≤q4", which looks like a reference bug. If you implement this
  pattern, use p0 ≤ q0 and p1 ≤ q1. These are the only q's present, and they are the
  constraints the comments clearly intend.

### n = 6

**6-0**
* Faces: `C0 C1 C2 C5 | C2 C3 C4 C5`.
* c = (1,1,1,1,1,1).
* Chords: `x`: {C0-C1, C2-C5, C3-C4}; fixed: {C1-C2, C0-C5}; fixed: {C2-C3, C4-C5}.
* Variables (p0..p5, x).
* `l0 = 1 + p1 + p5 + x`, `l1 = 1 + p0 + p2`, `l2 = 1 + p1 + p3`, `l3 = 1 + p2 + p4 + x`,
  `l4 = 1 + p3 + p5`, `l5 = 1 + p0 + p4`.
* Window: x. Extra: none. Objective: max Σp.

**6-1**
* Faces: `C0 V0 V2 V3 | C1 V1 V2 V0 | V1 C2 V3 V2 | C2 C3 C4 V3 | C4 C5 C0 V3`.
  Side 0 = C0→V0→C1, side 1 = C1→V1→C2. V2, V3 interior.
* c = (2,2,1,1,1,1).
* Chords: `x`: {C0-V0, V2-V3, C2-V1}; `y`: {V1-V2, C1-V0, C2-V3, C3-C4};
  `z`: {V0-V2, C0-V3, C1-V1, C4-C5}; `w`: {C2-C3, C4-V3, C0-C5}.
* Variables (p0..p5, x, y, z, w).
* `l0 = 2 + p1 + p5 + x + y`, `l1 = 2 + p0 + p2 + x + z`, `l2 = 1 + p1 + p3 + w`,
  `l3 = 1 + p2 + p4 + y`, `l4 = 1 + p3 + p5 + z`, `l5 = 1 + p0 + p4 + w`.
* Window: x. Extra: none. Objective: max Σp.

**6-2**
* Faces: `C0 V0 V2 V4 | V0 V1 V3 V2 | V1 C1 V5 V3 | C1 C2 C3 V5 | C3 C4 V4 V5 | C4 C5 C0 V4 | V2 V3 V5 V4`.
  Side 0 = C0→V0→V1→C1. V2..V5 interior.
* c = (3,1,1,1,1,1).
* Chords: `x`: {C0-V0, V2-V4, C1-V1, V3-V5} (both ends on side 0, so it counts twice);
  `y`: {V0-V1, V2-V3, C3-C4, V4-V5}; `q0`: {C1-C2, C3-V5, C4-V4, C0-C5};
  `q3`: {V0-V2, C0-V4, V1-V3, C1-V5, C2-C3, C4-C5}.
* Variables (p0..p5, q0, q3, x, y).
* `l0 = 3 + p1 + p5 + 2x + y`, `l1 = 1 + p0 + p2 + q0`, `l2 = 1 + p1 + p3 + q3`,
  `l3 = 1 + p2 + p4 + y`, `l4 = 1 + p3 + p5 + q3`, `l5 = 1 + p0 + p4 + q0`.
* Window: x. Extra: p0 ≤ q0, p3 ≤ q3. Objective: max Σp.

**6-3**
* Faces: `C0 V0 V6 C5 | V0 V1 V5 V6 | V1 V2 V4 V5 | V2 C1 V3 V4 | V3 C2 V5 V4 | C2 C3 V8 V5 | C3 C4 V7 V8 | C4 C5 V6 V7 | V5 V8 V7 V6`.
  Side 0 = C0→V0→V1→V2→C1, side 1 = C1→V3→C2. V4..V8 interior.
* c = (4,2,1,1,1,1).
* Chords: `x`: {C0-V0, C5-V6, C1-V2, V3-V4, C2-V5, C3-V8, C4-V7};
  `y`: {V1-V2, V4-V5, C2-V3}; `z`: {V0-V1, V5-V6, C3-C4, V7-V8};
  `q3`: {C2-C3, V5-V8, C4-C5, V6-V7}; fixed: {V0-V6, C0-C5, V1-V5, V2-V4, C1-V3}.
* Variables (p0..p5, q3, x, y, z).
* `l0 = 4 + p1 + p5 + 2x + y + z`, `l1 = 2 + p0 + p2 + y`, `l2 = 1 + p1 + p3 + q3`,
  `l3 = 1 + p2 + p4 + z`, `l4 = 1 + p3 + p5 + q3`, `l5 = 1 + p0 + p4`.
* Window: x. Extra: none. Objective: max Σp.

### Pattern counts
Per n, the reference has 2 / 4 / 5 / 5 / 4 patterns (n = 2..6).

The default procedure uses 2 / 3 / 5 / 4 / 4 of them:
* n=3 uses 0, 1, 2 (pattern 3-2 is never actually chosen, because 3-1 always comes first);
* n=5 uses 0..3.

The paper's Figure 4 shows exactly the "core" set: 3:{0,1}, 4:{0..4}, 5:{0..3}, 6:{0..3},
plus 2:{0,1}.

---

## 6. Selection

### 6.1 Order
```
for pattern id in DEFAULT_ORDER[n]:            # ascending ⇒ fewer singularities first
    for k in 0 .. 2n-1:                         # permutations, in this order
        l' = permute(l, k)
        if solve_default(pattern, l') succeeds: return (pattern, k, v)
fail (only (1,1) for n=2 reaches here)
```

### 6.2 Permutations
For `k < n` (rotations): `π_k[i] = (i + k) mod n`.
For `k ≥ n` (reflections): `π_k[i] = n − 1 − ((i + k − n) mod n)`.
Then `l'_i = l[π_k[i]]`: pattern side `i` is built for input side `π_k[i]`.

### 6.3 `solve_default(pattern, l')` — exact staged procedure
Let `b = l' − c` (if any `b_i < 0`, the pattern is infeasible).
Let `S = { v ∈ ℤ^M, v ≥ 0 : A v = b }`.

1. If `S` is empty, the pattern is infeasible for this permutation.
2. **Window** (if the pattern has a window variable `t`):
   * Compute `t_min = min_S t` and `t_max = max_S t` over the *equality system only*,
     before the extra constraints.
   * Let `t_mid = ⌊(t_min + t_max)/2⌋`.
   * Restrict `S` to `t_mid − 1 ≤ t ≤ t_mid + 1`.
   * This keeps the central edge-flow count moderate, so its singularities sit near
     the middle.
   * Every variable has nonnegative coefficients and appears in some row, so `S` is
     finite and `t_max` exists.
3. **Extra** inequalities: restrict `S` by them.
4. If `S` is now empty, the pattern is infeasible for this permutation; try the next
   one. This really happens, because integrality can make the window miss.
5. Pick `v ∈ S` maximising the objective. This is the paper's "maximise total padding",
   which pushes structure into regular padding strips.
6. **Ties.** The reference returns whatever lp_solve returns, which is not specified.
   Use this deterministic rule: among the optima, take the **lexicographically
   smallest `v`** in the canonical variable order of §5. Ties do occur. For example,
   (2,3,7) → 3-1 with l'=(7,2,3) has optima (0,1,0,1,1,0) and (1,0,0,1,0,1). Any optimum
   gives a valid mesh.

**Solving.** M ≤ 10 and N ≤ M ≤ N+4. Any correct method that enumerates `S`, or
optimises over it, reproduces the procedure. One practical exact approach:
* For n ≠ 4, the padding columns form an invertible matrix (a circulant
  with eigenvalues `2cos(2πk/n) ≠ 0` for n = 3, 5, 6, and `[[0,2],[2,0]]` for n = 2). So
  enumerate the ≤ 4 non-padding variables over `0..max(b)`, solve for `p` exactly
  (integer adjugate / determinant), and keep the nonnegative integer solutions.
* For n = 4, `p0,p2` and `p1,p3` only appear as the sums `p0+p2` and `p1+p3`.
  Enumerate the non-padding variables, derive the two sums `s02 = p0+p2` and
  `s13 = p1+p3`, then enumerate the splits (at most `(s02+1)(s13+1)`), keeping those
  that satisfy the extras (p0 ≤ p2, p1 ≤ p3, and p3 ≤ q1 in 4-3/4-4). Without the
  `p3 ≤ q1` extra, the best split is simply `p0 = ⌊s02/2⌋`, `p1 = ⌊s13/2⌋`.
* Cost is `O(L^k)`, with `k = #non-padding variables ≤ 4` and L the largest side.
  For large L (hundreds), use a small branch-and-bound ILP instead.

### 6.4 Building and relabelling
1. Build pattern + refinement (§4) + padding (§3) for `l'`. The corners are
   `C_0..C_{n−1}`, in pattern indexing.
2. If `k < n`, pattern corner `C_c` is input corner `K_{π[c]}`.
3. If `k ≥ n` (reflection), pattern corner `C_c` is input corner `K_{(π[c] + 1) mod n}`,
   and **every face's vertex order is reversed** to restore CCW orientation.
   The +1 is needed because reversing orientation swaps which end of a side is its
   "start" corner.
4. After this, the CCW boundary walk from `K_0` has exactly `l_0, l_1, …` edges per
   side. This was verified for every case in §10.

---

## 7. Feasibility guarantee

**Theorem (paper, §2.1–2.2).** For 2 ≤ n ≤ 6, every input with all `l_i ≥ 1` and an even
sum (except n=2, (1,1)) is solved by at least one core pattern under some permutation.

**Proof idea.**
* *Trimming*: if both neighbours `l_{k−1}, l_{k+1}` exceed 1, set `d = min(l_{k−1}, l_{k+1}) − 1`.
  Subtract `d` from both neighbours. The trimmed input's quadrangulation plus a
  `d × l_k` grid on side `k` (that is, padding `p_k = d`) solves the original.
* Repeat until every `k` has a neighbour equal to 1 (*maximally reduced*). Up to
  rotation and reflection, with α, β > 1 and an even sum, maximally reduced inputs fall
  into these classes:

| n | reduced input | condition | pattern |
|---|---|---|---|
| 2 | (A, 1) | A = 3 + 2x | 2-0 |
| 2 | (2, 2) | — | 2-1 |
| 3 | (α,1,1) | α = 2 | 3-0 |
| 3 | (α,1,1) | α = 4 + 2x | 3-1 |
| 4 | (1,1,1,1) | — | 4-0 |
| 4 | (α,1,1,1) | α = 3 + 2x | 4-2 (x=0) or 4-3 |
| 4 | (α,β,1,1) | α = β | 4-1 |
| 4 | (α,β,1,1) | α = β + 2 + 2x | 4-4 |
| 5 | (α,1,1,1,1) | α = 2 | 5-0 |
| 5 | (α,1,1,1,1) | α = 4 + 2x | 5-2 |
| 5 | (α,β,1,1,1) | α = β + 1 | 5-1 |
| 5 | (α,β,1,1,1) | α = β + 3 + 2x | 5-3 |
| 6 | (1,1,1,1,1,1) | — | 6-0 (x=0) |
| 6 | (α,1,1,1,1,1) | α = 3 + 2x | 6-2 (y=0) |
| 6 | (α,β,1,1,1,1) | α = β | 6-1 |
| 6 | (α,β,1,1,1,1) | α = β + 2 + 2x | 6-3 |
| 6 | (α,1,1,β,1,1) | α = β | 6-0 |
| 6 | (α,1,1,β,1,1) | α = β + 2 + 2x | 6-2 |

The ILP never performs trimming explicitly. Because the padding variables are free,
it finds those solutions (and often simpler ones) directly.

**Minimum perimeters**:
* n=2: 4, via (3,1) or (2,2).
* n=3: 4, via (2,1,1).
* n=4: 4.
* n=5: 6, via (2,1,1,1,1).
* n=6: 6.

**Empirical confirmation of the full default procedure**, including the window and
extra constraints that the theorem does not cover (§10):
* Exhaustive runs found no failure except (1,1):
  * n=2: all l_i ≤ 40
  * n=3: ≤ 16
  * n=4: ≤ 10
  * n=5: ≤ 7
  * n=6: ≤ 5
* 1500 random inputs with sides up to ~25 also succeeded.

---

## 8. Geometry

1. **Boundary.** Walk the boundary CCW from `K_0`. Vertex `j` (`0 ≤ j < l_i`) of side `i`
   gets parameter `t = i + j/l_i`. Its position is `γ_n(t)`:
   * n ≥ 3: use the regular n-gon with corners
     `P_k = (cos θ_k, sin θ_k)`, `θ_k = 2πk/n − π/2 − π/n`, so `P_0` is bottom-left and
     side 0 is the horizontal bottom edge. Then
     `γ(t) = (1−s)·P_i + s·P_{i+1}` with `i = ⌊t⌋`, `s = t − i`. Vertices are evenly
     spaced along each straight side.
   * n = 2 (lens):
     * For side 0, `t ∈ [0,1)`: `θ = (2t−1)π/3`, `γ = (sin θ, −cos θ + ½)`.
     * For side 1 (`t' = t−1`): `θ = (2t'−1)π/3`, `γ = (−sin θ, cos θ − ½)`.
     * The corners land at `(∓√3/2, 0)`, side 0 bulges down and side 1 bulges up.
2. **Interior.** Use the uniform (umbrella) Laplacian: each interior vertex is the plain
   average of its edge-neighbours. This minimises `Σ_{edges} |v_i − v_j|²` with the
   boundary fixed.
   * Solve the sparse SPD system (Cholesky / CG). Gauss–Seidel also works for small
     patches.
   * All edge weights are 1 (no cotangent weights).
3. **Properties.** The boundary is convex, so the result has no inverted quads.
   * Checked on 400 random cases: the minimum corner cross product was ≥ −1e−16.
   * Quads containing a boundary vertex of valence 2 that lies mid-side (for example
     V0 in 3-0) have a 180° angle there and are **degenerate**, but not flipped. This
     is inherent to the method, which allows singularities on the boundary. In a
     remesher, the 2D layout is normally only a parameter-domain placeholder: map it
     onto the real patch afterwards (the paper maps 2D to 3D through a
     parameterisation).

---

## 9. Worked examples
Variable vectors are in the canonical order of §5. Padding steps are listed in
processing order. "Sides" means the pattern-indexed side counts after each step.

### n=3, l = (2,2,4)
* Pattern 3-0 is tried first. Permutations k=0 and k=1 fail; **k=2** succeeds, with
  `π = [2,0,1]` and `l' = (4,2,2)`.
* Equations: 4 = 2+p1+p2, 2 = 1+p0+p2, 2 = 1+p0+p1. Solution **p = (0,1,1)**, unique.
* Construction:
  * Base: 1 quad, sides (2,1,1).
  * Side 2, one strip (length 1): +1 quad, sides (3,2,1).
  * Side 1, one strip (length 2): +2 quads, sides (4,2,2).
* **F = 4, V = 9.** Corners: C0→K2, C1→K0, C2→K1.

### n=3, l = (10,2,12)
* 3-0 with **k=2**, `π = [2,0,1]`, `l' = (12,10,2)`.
* Equations: 12 = 2+p1+p2, 10 = 1+p0+p2, 2 = 1+p0+p1. Solution **p = (0,1,9)**.
* Construction:
  * Base: 1 quad, sides (2,1,1).
  * Side 2, 9 strips of length 1: +9 quads, sides (11,10,1).
  * Side 1, one strip of length 10: +10 quads, sides (12,10,2).
* **F = 20, V = 33.** This is the paper's Fig. 6 situation: the simpler 3-0 beats the
  pattern that trimming would suggest.

### n=4, l = (5,3,7,3)
* 4-0 fails, since it needs l0 = l2.
* 4-1 fails for all 8 permutations. It needs `l0−l2 = l1−l3 = 1+x`.
* 4-2:
  * k=0 fails: it needs `l2−1 ≤ l0−3`.
  * k=1 fails.
  * **k=2** succeeds, with `π = [2,3,0,1]` and `l' = (7,3,5,3)`.
* Equations: 7 = 3+p1+p3+x+y, 3 = 1+p0+p2+x, 5 = 1+p1+p3, 3 = 1+p0+p2+y.
  They force x = y = 0, p0+p2 = 2, p1+p3 = 4. With p0 ≤ p2, p1 ≤ p3 and max p0+p1:
  **v = (p0,p1,p2,p3,x,y) = (1,2,1,2,0,0)**, unique.
* Construction:
  * Base: 2 quads, sides (3,1,1,1).
  * Side 3 ×2 (length 1): +2 quads, sides (5,1,3,1).
  * Side 2 ×1 (length 3): +3 quads, sides (5,2,3,2).
  * Side 1 ×2 (length 2): +4 quads, sides (7,2,5,2).
  * Side 0 ×1 (length 7): +7 quads, sides (7,3,5,3).
* **F = 18, V = 28.** Corners: C0→K2, C1→K3, C2→K0, C3→K1.

### n=5, l = (1,1,1,1,2)
* 5-0. Permutations k=0..3 fail; **k=4** succeeds, with `π = [4,0,1,2,3]` and
  `l' = (2,1,1,1,1)`.
* All p = 0 (unique).
* Result: the bare base pattern, 2 quads `V0 C3 C4 C0` and `V0 C1 C2 C3`.
  * V0 is the midpoint of pattern side 0, which is input side 4.
  * **F = 2, V = 6.**
* Corners: C0→K4, C1→K0, C2→K1, C3→K2, C4→K3.

### Extra reference outputs (default procedure, lexicographic tie-break)

| input | pattern | k | l' | v | F |
|---|---|---|---|---|---|
| (5,1) | 2-0 | 0 | (5,1) | p=(0,1), y=0 | 2 |
| (2,2) | 2-1 | 0 | (2,2) | all 0 | 1 |
| (4,1,1) | 3-1 | 0 | (4,1,1) | all 0 | 3 |
| (6,1,1) | 3-1 | 0 | (6,1,1) | x=1 | 5 |
| (3,3,2) | 3-0 | 0 | (3,3,2) | p=(1,0,1) | 5 |
| (3,1,1,1) | 4-2 | 0 | (3,1,1,1) | all 0 | 2 |
| (6,2,1,1) | 4-4 | 0 | (6,2,1,1) | x=1, rest 0 | 10 |
| (4,3,1,1,1) | 5-1 | 0 | same | x=2 | 4 |
| (6,1,1,1,1) | 5-2 | 0 | same | x=1 | 7 |
| (1,1,1,1,1,1) | 6-0 | 0 | same | all 0 | 2 |
| (3,3,3,3,3,3) | 6-0 | 0 | same | p=(1,1,1,1,1,1), x=0 | 14 |
| (3,3,1,1,1,1) | 6-1 | 0 | same | x=1 | 7 |
| (5,1,1,1,1,1) | 6-2 | 0 | same | x=1 | 10 |
| (4,2,1,1,1,1) | 6-3 | 0 | same | all 0 | 9 |
| (2,3,7) | 3-1 | 2 | (7,2,3) | (0,1,0,1,1,0) (tie) | 10 |

---

## 10. Verification done for this spec, and tests to port

A Python harness in the scratchpad (`tk/patterns.py`, `tk/verify.py`, `tk/select.py`,
`tk/build.py`, `tk/exhaust.py`, `tk/geom.py`) implements exactly the procedure in this spec.
The pattern tables in §5 were generated from it, and it checked the following.

1. **Matrix check.** For all 20 patterns, it rebuilt the chords from the face lists and
   recomputed every constraint column from the topology.
   * Padding columns: +1 on the neighbouring sides (+2 for n = 2).
   * Chord columns: count of the chord's boundary edges per side.
   * Base-side constants.
   * All of these match the reference matrices exactly. Every q_i column equals the
     p_i column.
   * No chord is self-crossing or closed.
2. **Mesh check.** For every exhaustive and random case, it built the mesh (grid-block
   refinement plus padding plus relabel/flip). Each check passed:
   * each directed half-edge used at most once;
   * a single boundary loop;
   * `V − E + F = 1`;
   * the CCW side counts from `K_0` equal the input `l` exactly.
3. **Feasibility.** The exhaustive ranges of §7 found no failures except (1,1).
4. **Geometry.** No inverted quad corners under the §8 placement.

**Port these as Rust tests:**
* the matrix-vs-topology check;
* the side-count / Euler check over an exhaustive small range per n;
* the worked examples' F, V and v.

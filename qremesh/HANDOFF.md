# Handoff: qremesh

Branch `claude/game-forge-spec`, pushed, no pull request. Last updated 2026-10-05.

qremesh is the pack's own quad remesher: a ZRemesher-like tool written from
scratch in Rust with no dependencies, as a standalone binary the Python side
will run as a subprocess. The pipeline is QuadWild-style and implemented
from the papers only (the QuadWild code is GPL and must not be read or
ported; libSatsuma is MIT). The user writes no code.

The Game Forge context (spec `specs/continuity-game-forge-spec.md`, nothing
of it implemented beyond qremesh) is unchanged from the earlier handoff.

## State in one paragraph
`qremesh remesh in.obj -o out.obj --quads N` goes from a triangle mesh to
a closed all-quad OBJ: field, singularities, traced and chosen layout, the
layout cut into the mesh, exact patches, quantized sides, grids pulled back
through a per-patch parametrization, smoothing onto the input, metrics in a
JSON report. Sphere, cube, torus, open tube and flat annulus come out the
way ZRemesher would (exactly the singularities needed, even quads). The
three blobs come out as a plausible retopology with 8–14 irregular vertices
and visible edge flow, but their layouts still contain two- and three-sided
patches, so they are not yet at ZRemesher's evenness. A half sphere with an
open rim fails (a patch without corners). Real, irregular inputs are not
handled yet: there is no isotropic pre-remesh, and slivers make fake features.

## The pipeline, reviewed stage by stage
This is the step-back review done at the start of this round, with what was
done about each point.

### 1. Input remesh — still missing
Test shapes are uniform. Real inputs (lifted TRELLIS meshes, scans) have
slivers and wildly varying edge lengths; the field and the tracer assume
edges a few times smaller than a quad. `shape sphere --jitter 0.3` (a UV
sphere with polar fans) is the test input for this: today it gives 85 field
singularities and 88 fake feature edges. Needed: split long, collapse
short, flip for valence, tangential smooth, reproject, keeping sharp edges
and boundaries.

### 2. Sharp features and boundaries — done
Dihedral-angle threshold on interior edges, and every boundary edge is a
feature too: the field aligns to it and traces stop on it.

### 3. Cross field — sound, with one important fix
Knöppel 2013: z⁴ per vertex, discrete connection, our own preconditioned
CG. Curvature target where the surface clearly bends (now in absolute
terms against the object's size; scaled by its own peak it turned the noise
on a flat surface into a full-strength random target), the world axes as a
weak guide elsewhere (a sphere gets cube corners), hard constraints on
features and boundaries.

**The alignment weight was far too strong.** `align` multiplies a mass
term, and a mass term screens constraints and smoothness over about
√(1/align) edges. At the old 0.05 that was five edges: the "global" field
was local, and a flat ring between two round boundaries grew four pairs of
singularities from a whisper of axis guide in its middle. At the new
default 0.005 the reach is some fifteen edges, and sphere, torus, ring,
tube and half sphere all get exactly the singularities they need
(8, 0, 0, 0, 4), the blobs get their 8.

### 4. Tracing and selection — extended, still heuristic
Every separatrix is traced independently at a sweep of constant bends
(±16°, 2° apart); shots landing on another singularity are candidate edges.
New: **field routes** (`field_routes`): Dijkstra over a graph whose states
are mesh edges being crossed into a triangle while following one arm of
the field; a step costs its length raised by how far it turns from the arm;
the arm is carried across edges to the nearest arm in the next triangle so
a path cannot slip onto the other family of lines. From every separatrix
to every other, the cheapest arrival on the ray with the arm pointing at
the singularity. Paths are smoothed off the edge midpoints and walked
through the mesh by the tracer as routed candidates, so the selection
treats shots and routes alike (cheapest first, no crossings, no parallel
runs within a quad). Routes found blob1's missing cube edge in principle,
but the field there does not support it arriving on the free slot, so the
layout stays 11 edges + 2 T-junctions.

Other tracer changes: arrivals into a singularity go through a *gate* on
the separatrix ray half a `free` out, so two lines into one singularity
cannot cross on the way in (that made slivers); a trace about to end on a
line within a quad of a node already on it ends at that node; the last
segment of a trace that ends on another is drawn, so a line coming the
other way meets it there; a non-disk region is repaired by one line that
closes on itself before trying its other half (two halves spiral past each
other and cross twice, leaving a lens).

What is still missing against QuadWild: choosing the subset of candidates
as an optimization (they use an ILP) rather than greedily; our blob layouts
end up with 2- and 3-sided patches where a cube-like layout exists.

### 5. Patch representation — restructured, exact
Traces are **inserted into the mesh** (`refine.rs`): every trace point
becomes a vertex, every segment a chain of edges, in each original
triangle's own plane, with snapping (5% of an edge) to vertices and to cut
edges so T-junctions land on the chain they hit. Then (`patches.rs`)
regions are flood fills over uncut edges, nodes are vertices where the
cut graph has valence ≠ 2 (and feature chains that turn more than 45° over
a one-quad window), arcs are the chains between nodes, each patch is kept
as its own cut-open local mesh, corners are nodes where the patch's
interior angle rounds to one quarter turn, sides are the arcs between
corners. Dangling chains are pruned.

### 6. Quantization — built (`quantize.rs`)
Every patch is cut into quads ("kites") in its domain first (see 7). Each
arc gets an integer length ≥ 1; every kite wants its opposite sides equal.
Each arc is on at most two kite sides with coefficient ±1, so this is the
bi-directed flow of Heistermann 2023. We solve it as: real-valued
constrained least squares (KKT, dense), a penalty loop that keeps the real
solution ≥ 1, greedy rounding one variable at a time with re-solves
(MIQ-style), then augmenting-path repair of leftover violations (Dijkstra
over (constraint, owed change) states). Kites the quantizer still cannot
satisfy are cut at a corner into a 3- and a 5-sided piece (a valence-3/5
pair gives the freedom) and the whole quantized again, up to 12 rounds,
two kites per round.

A finding worth keeping: with the midpoint pattern alone, the integer
system of a blob layout had rank 40 of 44 and *no* feasible point in a
24⁴ box — a triangle with three one-quad corners and a single valence-3
inside obeys the triangle inequality in the grid's own metric, so thin
triangles are infeasible by construction. Hence:

### 7. Filling, smoothing, reprojection — built (`fill.rs`)
Each patch's refined triangles are mapped to a flat domain by a Tutte
embedding (cotangent weights clamped positive, CG): a rectangle of the
integer side lengths for a quad, a regular n-gon otherwise, a lens for a
digon; the boundary is placed per arc in proportion to its integer
length. A 4-corner patch is one kite. 3- and 5-sided pieces are cut from
their centre into kites (midpoint pattern: one valence-3 or -5 vertex).
2-sided and ≥6-sided pieces are split by a line between two side
midpoints. A thin triangle (longest side at least the other two together,
and big enough) gets both ends cut off at thirds of its long side, giving
3 + 5 + 3 pieces. Mid-nodes on surface arcs are chain vertices (an
existing junction near the middle is reused). Kites get bilinear grids in
the domain, pulled back to the surface through the map; arc samples are
shared between neighbours. Then 60 rounds of uniform Laplacian smoothing
with reprojection onto the input (grid-accelerated closest point), with
feature and boundary vertices held.

## Measurements (`tools/run_all.sh`, 600 quads asked for)
| shape | field sings | patches (corners) | quads | irregular vertices | edge/h mean±std | dist from input mean/max |
|---|---|---|---|---|---|---|
| ico (sub 4) | +8 | 6 (4,4,4,4,4,4) | 486 | 8 (all val 3) | 1.10±0.13 | 0.0015/0.0026 |
| ico jittered | +8 | 6 | 486 | 8 | 1.10±0.13 | 0.0014/0.0024 |
| cube | +8 | 6 | 600 | 8 | 1.00±0.00 | 0/0 |
| torus | 0 | 1 (4) | 880 | 0 | 0.82±0.24 | 0.0016/0.0040 |
| blob1 | +8 | 7 {2:2,3:2,4:3} | 360 | 10 | 1.20±0.50 | 0.0038/0.030 |
| blob2 | +8 | 7 {2:1,3:3,4:3} | 439 | 8 | 1.15±0.21 | 0.0018/0.018 |
| blob3 | +8 | 8 {2:1,3:6,4:1} | 1029 | 14 | 0.74±0.32 | 0.0009/0.0066 |
| tube | 0 | 1 (4) | 616 | 0 | 0.99±0.00 | 0.0005/0.0027 |
| annulus | 0 | 1 (4) | 495 | 0 | 1.07±0.31 | 0.0000/0.0025 |
| hemi | +4 | 5 {1,2,3,4,5} | 244 | — | broken | 0.11/0.39 |

Distances are a share of the bounding diagonal. Before this round there
was no quad output at all. Pictures: `docs/quads-*.png`, `docs/layout-*.png`.

How far from ZRemesher: sphere, cube, torus, tube, annulus are there.
Blobs have the right singularities and edge flow but uneven quad sizes
(std 0.2–0.5 of a quad) and the quad count is off by up to 70% (the
quantizer stretches sides to make thin patches feasible). Anything with an
open rim or a real scan is not there yet.

## Next steps, in order
1. **Boundaries.** The half sphere: separatrices reach the rim at shallow
   angles, so the big patch has nodes but no corners. End leftover
   separatrices on a boundary only at a steep angle (route them to the
   rim with the arm perpendicular), and add corners to boundary arcs where
   a trace lands.
2. **Selection as an optimization.** Choose the candidate subset to
   maximize 4-sided patches (a small ILP or local search over the
   candidate graph), so blobs get cube-like layouts instead of 2- and
   3-gons. The quantizer and filler already cope with the rest.
3. **Quad count and evenness.** Weight the quantizer toward the target
   count globally; smooth with a quad-aware scheme (or ARAP/LSCM for the
   patch domains, which are plain Tutte now and distort big patches).
4. **Isotropic input remesh**, then the CLI contract and the Python bridge
   (spec §7.6 and §11), CI builds.

## Layout of the crate
| File | What it does |
|---|---|
| `src/cross.rs` | Surface frames, curvature/axis guide, feature and boundary constraints, the field solve, singularities. |
| `src/trace.rs` | Separatrix directions, bent shots, field routes, the tracer (gates, node merging, routes), selection, repairs. |
| `src/refine.rs` | Inserts traces into the triangle mesh as edge chains. |
| `src/patches.rs` | Nodes, arcs, regions as cut-open local meshes, corners, sides; `split_arc`. |
| `src/quantize.rs` | Integer arc lengths. |
| `src/fill.rs` | Domains, kites, thin-triangle and corner cuts, placement, assembly, smoothing. |
| `src/proj.rs` | Closest point on a triangle mesh through a grid. |
| `src/shapes.rs`, `src/mesh.rs` | Test shapes, OBJ in/out, the UV sphere. |
| `tools/run_all.sh` | Every test shape, one line of numbers each. |
| `tools/render_layout.py`, `tools/render.py` | Standard-library renderers for layouts (on the refined mesh) and quad meshes. |

Spike 1 (the Instant-Meshes-style local fields) was deleted; it is in git
history before this round.

## Run it (from `qremesh/`)
```
cargo build --release
./target/release/qremesh shape blob -o out/blob2.obj --seed 2
./target/release/qremesh remesh out/blob2.obj -o out/blob2_q.obj --quads 600 --layout out/blob2.json
python3 tools/render_layout.py out/blob2.json.obj out/blob2.json out/blob2.png [--view x,y,z]
python3 tools/render.py out/blob2_q.obj out/blob2_q.png [--view x,y,z]
sh tools/run_all.sh
```
Options: `--quads N`, `--features DEG` (35), `--align` (0.005), `--axes`
(0.1), `--smooth` (60 rounds), `--seed`. The JSON report goes to stdout.
`out/` is gitignored.

## Gotchas
- `render.py` culls back faces; a flat shape wound toward −z (the annulus)
  needs `--view 0,0,-1`-ish. If a render looks wrong, check the renderer
  before the algorithm.
- Debug output: `QREMESH_DEBUG` (selection, patches, quantizer, cuts),
  `QREMESH_ROUTES` (every route and how its walk ended),
  `QREMESH_ROUTE_STEPS=<trace id>` (a routed trace step by step),
  `QREMESH_CANDIDATES` (draw every candidate), `QREMESH_QUANT_DUMP=<file>`
  (the quantizer's problem and answer as JSON, for analysis in Python).
- Everything is deterministic for a given seed; hash-set iteration is
  sorted wherever it could change a choice.
- Repo conventions: commit messages are full sentences about behaviour
  ending with the session's trailer; code comments explain why; no model
  names in commits or code.

## Update: input remesh and the first organic test (2026-10-05, later)
- **New test shapes** (`src/sdf.rs`): `qremesh shape creature|pretzel --jitter 0 [--res N]`.
  These are SDFs triangulated with marching tetrahedra: a quadruped (genus 0) and two fused tori (genus 2).
  About 13% of their triangles are slivers, like a real lifted mesh.
  Downloads are blocked in the cloud environment (raw.githubusercontent.com, npm and PyPI all return 403).
- **Input remesh** (`src/premesh.rs`): Botsch–Kobbelt split, collapse, flip, relax and reproject, to an edge of 0.4 quad.
  It runs by default in `remesh`; use `--no-premesh` to skip it, and `qremesh premesh in -o out [--edge L]` to run it alone.
  Sharp edges are pruned to real feature lines (`prune_features`: chains of at least 6 edges that do not zigzag), both here and in `cross::feature_constraints`.
  On the creature at `--res 50` (8.9k vertices) it does the following in 0.8 s:
  - slivers go from 12.5% to 0%;
  - "sharp" edges go from 490 to 19;
  - field singularities go from 186 to 62 (+35/−27).

  The cube keeps all 12 of its edges.
  **`tools/run_all.sh` has not been rerun with the premesh on**, so check the test shapes for regressions first.
- **The creature still times out (more than 3 minutes) in the layout stage.** It never reaches quantization.
  Profiling (build with `CARGO_PROFILE_RELEASE_DEBUG=line-tables-only --target-dir target-prof`, then sample with `gdb -p <pid> -batch -ex bt`) puts every sample in `Tracer::crossing`, scanning a candidate's own segments.
  This happens during the first `cand.run()` of bent shots, roughly 250 separatrices × 17 bends.
  The suspected cause is a candidate pinned at a vertex or edge, bouncing between two triangles with near-zero moves and adding a segment each time, which makes the crossing test quadratic.
  A guard is committed but **untested**: `advance` stops a trace after 64 moves in one step, with `ended = "stuck"`.
  Next step: rerun the creature with `QREMESH_DEBUG=1`. Confirm the time drops and count the "stuck" ends; if they are many, find why they get pinned.
  After that, check whether 62 singularities overwhelm the selection, routes and quantizer stages.

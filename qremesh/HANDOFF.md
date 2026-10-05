# Handoff: qremesh

Branch `claude/game-forge-spec`, pushed, no pull request. Last updated 2026-10-05.

qremesh is the pack's own quad remesher: a ZRemesher-like tool written from
scratch in Rust with no dependencies, as a standalone binary the Python side
will run as a subprocess. The pipeline is QuadWild-style and implemented
from the papers only (the QuadWild code is GPL and must not be read or
ported; libSatsuma is MIT). The user writes no code.

The Game Forge context (spec `specs/continuity-game-forge-spec.md`, nothing
of it implemented beyond qremesh) is unchanged from the earlier handoff.

## The pipeline, reviewed stage by stage

This is the step-back review done before the quad output was built. It says
what is sound, what was hacky, and what was restructured.

### 1. Input remesh — missing
Test shapes are already uniform, so nothing is done. Real inputs (lifted
TRELLIS meshes, scans) have slivers and wildly varying edge lengths; the
field and the tracer both assume edges a few times smaller than a quad.
Needed: an isotropic remesher (split long, collapse short, flip for valence,
tangential smooth, reproject) that keeps sharp edges and boundaries.

### 2. Sharp features — sound, boundaries were missing
Dihedral-angle threshold on interior edges. Boundary edges (one face) were
not features, so traces ran off an open mesh and the field ignored its rim.
Boundary edges are now features too: the field aligns to them and traces
stop on them.

### 3. Cross field — sound
Knöppel 2013: one complex z⁴ per vertex, discrete connection, our own
preconditioned CG. Curvature target where it is trusted, the world axes as a
weak guide elsewhere (a sphere gets cube corners), hard constraints on
features. Singularities are read off per triangle. The holonomy term is
ignored in the index; it is small per triangle on the meshes we feed it.

### 4. Tracing and selection — heuristic but keeps working
Every separatrix is traced independently at a sweep of constant bends;
shots landing on another singularity are candidate edges, chosen cheapest
first with no crossings and no parallel runs closer than a quad; leftovers
end on the layout at a T, or on a feature; the rest grow until they hit
something; non-disk regions get repair loops. It is a stack of heuristics
over two spikes but it gives the right layouts on sphere, cube and torus and
usable ones on the blobs. It is kept. What QuadWild does instead (shortest
paths in a graph that charges for leaving the field, then an ILP choosing a
subset) is the next thing to try if layouts on real inputs are poor.

### 5. Patch representation — was the main structural flaw, restructured
Patches were triangle flood fills over "crossed edges", which made outlines
jagged, left slivers where traces met inside a triangle, and let corner
counts be guessed from turning angles of a zigzag. The decision: **traces
are inserted into the mesh** (`refine.rs`). Every trace polyline becomes a
chain of mesh edges, with snapping so that nothing degenerate is made. From
then on everything is exact: regions are edge-bounded, nodes are vertices
where the cut graph has valence ≠ 2, arcs are the chains between nodes,
corners are nodes where the patch's interior angle rounds to a quarter
turn, and sides are the arcs between corners (`patches.rs`).

### 6. Quantization — was missing, built as a signed-graph flow
Every patch is first made a quad: an n-gon is subdivided from its centre
into n quads (the Catmull-Clark/Takayama "midpoint" pattern: a valence-n
vertex in the middle); patches with fewer than 3 or more than 5 corners
are split first by a line between side midpoints in the patch's parameter
domain. Then each arc gets an integer length ≥ 1 with the constraints
"opposite sides of every sub-quad sum equal". Each arc touches at most two
constraints with coefficient ±1, so the constraint matrix is a bi-directed
graph incidence matrix (exactly the structure Heistermann 2023 solves with
Bi-MDF). We solve it simply: real-valued constrained least squares, round,
then repair residuals with augmenting paths (BFS over constraints) — the
same moves a flow solver makes, without the network simplex. Infeasible
parity is reported, not hidden.

### 7. Filling, smoothing, reprojection — was missing, built
Each patch's refined triangles are mapped to a 2D domain (Tutte embedding
with positive weights: a rectangle for quads, a regular n-gon otherwise,
boundary placed per arc in proportion to its integer length). Sub-quads are
kites in the domain; their grids are placed bilinearly in the domain and
pulled back to the surface through the map. Arc samples are shared between
neighbours. Then the quad mesh is smoothed (uniform Laplacian, features and
boundaries held) with reprojection onto the input through a grid of
triangles.

## Layout of the crate
| File | What it does |
|---|---|
| `src/cross.rs` | Surface frames, curvature/axis guide, feature and boundary constraints, the field solve, singularities. |
| `src/trace.rs` | Candidates, selection, repairs; every trace point records which mesh edge it sits on. |
| `src/refine.rs` | Inserts traces into the triangle mesh as edge chains. |
| `src/patches.rs` | Nodes, arcs, regions, corners, sides; domain parametrization; sub-quads. |
| `src/quantize.rs` | Integer arc lengths. |
| `src/fill.rs` | Grid placement, assembly, smoothing, reprojection, metrics. |
| `src/shapes.rs` | Test shapes. |
| `tools/render_layout.py`, `tools/render.py` | Standard-library renderers for layouts and quad meshes. |

Spike 1 (Instant-Meshes-style `field.rs`, `extract.rs`) was deleted; it is
in git history before this handoff.

## Run it (from `qremesh/`)
```
cargo build --release
./target/release/qremesh shape ico -o out/ico.obj --subdivisions 4
./target/release/qremesh remesh out/ico.obj -o out/ico_q.obj --quads 600 --layout out/ico.json
python3 tools/render_layout.py out/ico.obj out/ico.json out/ico.png [--view x,y,z]
python3 tools/render.py out/ico_q.obj out/ico_q.png
```
The JSON report goes to stdout. `out/` is gitignored. `out/run.sh` runs
every test shape.

## Gotchas
- The renderer's depth test is in world units (tolerance `0.02 * radius`).
  If a render looks wrong, check the renderer before the algorithm.
- Debug output: `QREMESH_DEBUG` (trace selection, repairs), `QREMESH_CANDIDATES`
  (draw every candidate), `QREMESH_NO_EDGES`.
- Repo conventions: commit messages are full sentences about behaviour
  ending with the session's trailer; code comments explain why; no model
  names in commits or code.

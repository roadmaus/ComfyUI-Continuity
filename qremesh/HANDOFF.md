# Handoff: qremesh

Branch `claude/game-forge-spec`, not pushed since `61c3e38`, no pull request. Last updated 2026-10-05 (second round, uncommitted).

qremesh is the pack's own quad remesher: a ZRemesher-like tool written from
scratch in Rust with no dependencies, a standalone binary the Python side will
run as a subprocess (spec `specs/continuity-game-forge-spec.md` §7.6/§11; none
of the rest of Game Forge is implemented). The user writes no code.

**Reading other code is allowed now.** QuadWild, quadwild-bimdf, patchgen,
Instant Meshes and QuadriFlow may be read to understand them; nothing is copied
or ported line by line, and qremesh stays MIT. (The earlier rule "QuadWild must
not be read" is gone.) libsatsuma, QuadWild's flow solver, is MIT and could be
ported outright.

**Run one mesh per command, always under `tools/guard.sh`.** A runaway run
once took the user's Mac out of memory (Force Quit dialog). Never batch or
parallelize remesh runs in one tool call; `tools/run_all.sh` guards each shape.

## State in one paragraph
`qremesh remesh in.obj -o out.obj --quads N` turns a triangle mesh into a
closed all-quad mesh. It is now built the QuadWild way: premesh, cross field,
a **partition** of the surface along field lines with singularities *inside*
patches (`partition.rs`), patches with 3–6 corners, the layout's arcs
quantized, every patch filled from its side counts by a **pattern** (grid,
midpoint, or Takayama 2014; `pattern.rs`), then **tangential** smoothing onto
the input. Every test shape and both organic meshes come out closed with
about the asked-for quad count. Edge flow on the organic meshes is acceptable,
but they have many irregular vertices (45–55 on a cow at 600 quads).

## Round of 2026-10-05, not committed (read this first)
Working tree only; nothing below is in a commit. The measurements table further down is
from before this round and no longer matches.

What changed:
- **Adaptive quad size** (`sizing.rs`, `--adapt N`, default 3, 1 = uniform): size follows
  the tighter principal curvature (0.8 of the radius), kept within N× of the largest,
  graded, scaled to the budget. Creases are ignored. The premesh, the partition's
  distances, arc targets, arc vertex spacing and smoothing weights all read it.
- **Count calibration** (`main.rs`): the fill is rerun up to five times with sizes scaled
  by how far the count was off; the closest try is kept. Raw counts were 25–90% over.
- **Partition rules** (`partition.rs`): a patch is also invalid when it is a bag
  (`bagged`), when its sides cannot be joined (`sides_fit`, now in the add phase too),
  when it is a strip many times longer than wide (+10 like a sliver), and when a hexagon
  holds two singularities more than two quads apart (`paired`). When no single path
  helps a patch, pairs of paths are tried (`Cuts::best`, two-step lookahead).
- **Smoothing** (`fill.rs::smooth`): first each patch's inside with its border held, run
  to rest (over-relaxed), skipped where quads are too coarse for the curvature
  (`Sizing::coarse`); then the old gentle rounds, weighted by size.

What was measured (Spot and creature × 600/2500 × adapt 1/3, each rule switched off in
turn through `QREMESH_OFF=bag,unfit,thin,paired,look`, raw counts with `QREMESH_TRIES=1`):
all rules on beats all off on edge evenness in 7 of 8 cases; irregular vertices go up
about 4%. Without the lookahead Spot at 2500/adapt 3 lost a limb.

What works: Spot and the creature at 2500 quads, adapt 3, are clean (renders in
`out/png/now/`): Spot edge/size 1.00 ± 0.32, distance max 0.009; creature 0.98 ± 0.26,
distance max 0.068 (one ear comes out a stub).

What does not:
- **600 quads with adapt 3**: the head's many small patches each need their minimum of
  edges, the calibration pays for them by growing everything else, and body and legs
  get huge quads. Not solved; adapt 2 is milder, and the default may want to be 2.
- **Field singularities are real**, not noise: their count does not move over 250× of
  `--align`. The earlier idea of a scale-aware field to remove them was wrong.
- The creature at 600 uniform loses its tail (thinner than a quad) whatever the smoothing.
- Converged smoothing with nothing held, and rest-length springs, were both tried and
  dropped: the first slides quads off limbs, the second did not even the mesh out.
- hemi is still over-cut (43 patches, 1316 quads for 600).
- The layout takes 15–30 s at 2500 quads; it was 14 s before the extra rules.
- `QREMESH_OFF` and `QREMESH_TRIES` are measuring aids and can go once defaults settle.
- Not started: the flow quantizer (libsatsuma port) and a run on a real lifted mesh (none
  is on this machine; `out/real/armadillo.obj` and `bunny.obj` are untried).

## Measurements (600 quads asked; distances are a share of the bounding diagonal)
| mesh | quads | irregular vertices | distance from input mean / max | closed |
|---|---|---|---|---|
| ico sphere | 608 | 8 (val 3) | 0.0012 / 0.0025 | yes |
| cube | 712 | 8 (corners) | 0 / 0 | yes |
| torus | 528 | 0 | 0.0025 / 0.0067 | yes |
| blob2 | 540 | 8 (val 3) | 0.0014 / 0.0053 | yes |
| Spot (cow) | 632 | 45 (incl. one val 2) | 0.0030 / 0.049 | yes |
| creature (SDF) | 623 | 55 | 0.0028 / 0.040 | yes |

Quad-size spread (edge length / target, std) is ~0.10–0.16 on the simple
shapes and 0.22–0.24 on the organic ones. Not rerun since this round's
changes: blob1, blob3, tube, annulus, **hemi** (open rim; before this round it
over-cut: 43 paths, none removed) and **fandisk** (CAD, many features).

Real meshes live in `out/real/` (gitignored; download again if missing):
Spot `https://www.cs.cmu.edu/~kmcrane/Projects/ModelRepository/spot.zip`
(use `spot/spot_triangulated.obj`), and from
`https://raw.githubusercontent.com/alecjacobson/common-3d-test-models/master/data/`
`stanford-bunny.obj` (has holes), `fandisk.obj`, `armadillo.obj` (not tried).
The creature: `qremesh shape creature -o out/creature.obj --jitter 0 --res 50`.

## The pipeline as it is now (`main.rs::remesh`)
1. **Premesh** (`premesh.rs`): Botsch–Kobbelt isotropic remesh to 0.4 of a quad.
2. **Features** (`cross.rs::feature_constraints`): dihedral > 35° and the boundary, pruned to long
   smooth chains; **if the non-boundary creases add up to < 2·√area they are dropped**
   (organic noise; QuadWild's organic preset turns sharp edges off).
3. **Field** (`cross.rs`): Knöppel 2013 with curvature + weak axis guide. Singularity
   count does not depend on the quad budget (Spot: ~70 at any count); most are real
   (every limb tip needs +4 quarter turns), many closer than a quad.
4. **Partition** (`partition.rs`, new; `--legacy-layout` still runs the old separatrix
   tracer `trace.rs`/`refine.rs` for comparison and should be deleted soon):
   - Cuts are mesh-edge chains. A candidate is an exact field line through the triangles,
     laid on edges by taking the nearer end of each crossed edge (no drift); singular
     triangles' vertices are avoided (the far end is taken, or the line is rejected).
   - Each cut edge stores the field arm it follows at both ends; **corners are read off
     combinatorially** (arm turns +1 at a corner, 0 along a side, −1 pointing in, 2 at a
     slit tip) through the `turn` oracle passed to `patches::build`.
   - Add phase: while some patch is invalid, add the candidate (field lines through seeds
     beside every singularity, midway between neighbouring singularities, far from cuts,
     and straight on from corners pointing in) that most lowers a weighted badness:
     cuts still needed to make a disk ×3, corners pointing in, singularities beyond one
     per patch ×2, corner count outside 3–6, curvature beyond a full turn (absolute
     angle defect in quarter turns minus 4, `overbent`), and +10 for a sliver narrower
     than 0.3 quad. Path ends snap onto junctions within half a quad.
   - Removal phase: paths are removed last-first wherever the merged patches are no
     worse, compared lexicographically (QuadWild's `BetterConfiguration`).
   - Invalid patches are **kept** (QuadWild does too); a limb tip with four
     singularities stays one patch.
5. **Graph** (`patches.rs`): arcs, patches, corners; `fix_corners` forgets corners
   pointing in and brings every disk to 3–6 corners (adds at the sharpest bends, or
   spread out, splitting an arc if needed; drops the flattest).
6. **Quantize** (`fill.rs::build_patches`, `quantize.rs`): an integer per layout arc,
   ≥ 1. Quads whose opposite sides are within 1 quad or 25% are held equal (hard,
   LSQ + greedy rounding + augmenting repair); other quads are free. Then
   `quantize::parity`: every non-grid patch must have an even total (Dijkstra chains of
   ±1 through grid quads straight across), midpoint spokes ≥ 1 for 3-/5-gons where
   cheap, parity repaired last.
7. **Fill** (`pattern.rs`, new): per patch from its side counts: grid if equal, midpoint
   pattern (centre of valence n) if its spokes are whole and ≥ 1, else Takayama's
   catalogue (17 base patterns, chords multiplied, padding strips, every rotation and
   reflection; spec in `docs/takayama-patterns.md`, tests in `pattern.rs` incl. an
   exhaustive check). Domain = convex polygon, interior uniform Laplace; lifted to the
   surface through the patch's Tutte map.
8. **Smooth** (`fill.rs::smooth`): 60 rounds, **tangential part only**, reprojected to
   the closest input point; features held. (The old plain Laplacian collapsed every thin
   limb onto the body: this was the main reason legs vanished.)

## What the reference code taught (read this before changing the layout)
- QuadWild never traces separatrices. Singular vertices are removed from its path graph
  and their 1-ring is split so paths can pass. Paths are Dijkstra over vertex × 4
  directions with arcs to the 2-ring, cost `len·(1 + 100·(angle/45°)²)`; loops are
  shortest cycles; candidates are seeded by Poisson sampling, chosen farthest-first.
- Validity (disk, no emitters, 3–5 corners, CC-ability, ≤ 1 singularity with matching
  valence) only steers tracing and removal; invalid patches survive and get 3–6 corners
  forced. Nothing merges or moves singularities anywhere.
- Quantization is a bi-directed flow (quadwild-bimdf): parity holds by construction
  (inner tail-tail edges per patch between side i and i+2), regularity is soft through
  "emergency" edges, arcs ≥ 1, target = arc length / edge length. Solved with libsatsuma.
- Filling is Takayama's patchgen; any 3–6-gon with an even perimeter works.
- Instant Meshes / QuadriFlow (BSD) absorb singularity clusters into poles of whatever
  valence; robust but worse edge flow. Not a reason to switch.

## Next steps, in order
1. **Fewer irregular vertices on organic meshes.** 45–55 on Spot/creature. Look at where
   they come from (patterns' extra 3/5 pairs vs field singularities vs corners added by
   `fix_corners`); render with `tools/render.py` (blue dots are irregular vertices).
2. **Dijkstra paths (plan step 4).** Replace the streamline candidates with QuadWild's
   graph: vertex × 4 arms, 2-ring arcs, steep angle cost, singular 1-rings split. Should
   cut the many "through a singularity" rejections and give cleaner loops around limbs.
3. **Re-run hemi, tube, annulus, blob1/3, fandisk** one at a time; fix open rims.
4. Delete the legacy tracer (`trace.rs` minus `field_dir`/`Topology`, `refine.rs`, the
   kite code in `fill.rs`) once nothing compares against it.
5. ZRemesher-style density (uniform first, then curvature within ~4×); then the CLI
   contract and Python bridge (spec §7.6, §11), CI builds.

## Run it (from `qremesh/`)
```
cargo build --release
sh tools/guard.sh 120 1500 ./target/release/qremesh remesh out/real/spot/spot_triangulated.obj -o out/real/spot_q.obj --layout out/real/spot.json
python3 tools/render.py out/real/spot_q.obj out/png/spot_q.png --view 1,0.3,1
python3 tools/render_layout.py out/real/spot.json.obj out/real/spot.json out/png/spot_layout.png --view 1,0.3,1
cargo test --release pattern
```
Options: `--quads N`, `--features DEG` (35), `--align` (0.005), `--axes` (0.1),
`--smooth` (60), `--seed`, `--no-premesh`, `--legacy-layout`. The JSON report goes to stdout.

## Debugging
- `QREMESH_DEBUG`: partition rounds, chosen paths, final invalid patches, bending/
  singularities per patch, patch sides, quantizer, patterns that failed.
- `QREMESH_WALKS`: every field-line walk and how it ended, every candidate's badness.
- `QREMESH_QUANT_DUMP=<file>`: targets and integers of the hard-equality solve.
- `render_layout.py` stripes patches grey by the *old* validity rule (2–5 corners);
  six-sided patches show grey though they are fine.
- Everything is deterministic for a given seed.
- Repo conventions: commit messages are full sentences about behaviour, ending with the
  session trailer; comments explain why; no model names in commits or code.

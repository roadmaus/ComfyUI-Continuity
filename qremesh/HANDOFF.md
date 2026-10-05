# Handoff: Game Forge and qremesh

Branch `claude/game-forge-spec`, pushed, no pull request. Last updated 2026-10-05.

## Context
- **Game Forge** is a planned bench in this pack (ComfyUI-Continuity) for making a game's assets inside a project. It covers sprites, tiles, materials, texturing existing UV-mapped models, 3D models, UI and sound. Every bench feature must also work from a CLI, so agents can drive it.
- The full design is in `specs/continuity-game-forge-spec.md`. Nothing from the spec is implemented yet; only the spec and the qremesh prototype exist.
- **qremesh** is the pack's own quad remesher, a ZRemesher-like tool written from scratch in Rust with no dependencies. The user wants it written here, not vendored and not pulled in as a dependency.
- The plan is to ship it as a standalone binary that the Python side runs as a subprocess. CI would build it per platform and the publish step would include the binaries.
- The user writes no code. They expect the agent to write it.

## Decisions so far
- **No Instant Meshes approach.** The first prototype (`src/field.rs`, `src/extract.rs`, the `remesh` command) is Instant-Meshes-style: local fields only. It reached about 89% quads with dislocation chains. Research then showed that local methods can't reach ZRemesher quality: they give extra singularities and spiralling loops. It is kept only for reference.
- **QuadWild-style pipeline instead**, implemented from the papers only. The QuadWild code is GPL, so don't read or port it. libSatsuma is MIT. The stages:
  1. Uniform remesh of the input.
  2. Detect sharp features.
  3. Global cross field: Knöppel 2013, aligned to curvature and features.
  4. Trace separatrices into a patch layout.
  5. Quantize patch side counts with min-cost flow (Bi-MDF, Heistermann 2023, approximate solver).
  6. Fill each patch with a grid or pattern, then smooth and reproject.
- **What we know about ZRemesher:** Maxime Rouca wrote it, and Exoside's Quad Remesher is the same lineage. Nothing about it is published. Its behaviour suggests a global field, then a patch layout, then quantization.

## Current state: the `layout` command (spike 2)
| File | What it does |
|---|---|
| `src/cross.rs` | Global cross field. Complex z⁴ per vertex, discrete connection, our own preconditioned conjugate-gradient solver. Curvature target only where \|k1−k2\| is a clear share of the curvature. Feature constraints from dihedral angle. Singularity index per triangle. |
| `src/trace.rs` | Separatrix directions fitted from the singularity index (3 or 5, exact). All traces grow at once and stop on a trace, a singularity or a feature. Self-loops are allowed after enough distance. Repair traces are added until every region is a disk. Regions come from a flood fill over cut edges. |
| `src/shapes.rs` | Test shapes: icosphere, cube, torus, plus jitter. |
| `tools/render_layout.py` | Renderer using only the Python standard library. Draws the OBJ plus layout JSON to PNG with patches, traces and singularities. Use it to look at results. |

Results so far:
- Cube: 6 patches.
- Torus: 0 singularities, 4 patches after 2 repair rounds.
- Icosphere: exactly 8 singularities with 3 separatrices each, every region a disk, but 15 patches including thin strips. The ideal is 6.
- Images are in `docs/`.

Run it (from `qremesh/`):
```
cargo build --release
./target/release/qremesh shape ico -o out/ico.obj --subdivisions 4
./target/release/qremesh layout out/ico.obj -o out/ico.json
python3 tools/render_layout.py out/ico.obj out/ico.json out/ico.png [--view x,y,z] [--arms]
```
The JSON report goes to stdout. `out/` is gitignored.

## Next steps, in order
1. **Trace selection** (the riskiest step). Trace candidates without stopping at the first hit. Drop near-parallel duplicates. Prefer traces that end on singularities. Then choose a subset so every patch is a disk with 3–6 sides. Goal: the sphere comes out as a cube-like layout.
2. **Count patch sides and corners.** Represent patches explicitly as a graph rather than only as a triangle flood fill.
3. **Quantization** with min-cost flow, written ourselves (network simplex or successive shortest paths).
4. **Patch filling, smoothing and reprojection.** Output a quad OBJ.
5. **Real inputs.** An isotropic remesher for the input, a lifted TRELLIS mesh, then the CLI contract and the Python bridge (spec §7.6 and §11), plus CI builds.

## Gotchas
- The renderer's depth test is in world units (tolerance `0.02 * radius`). An earlier bug let traces on the back show through, so if a render looks wrong, check the renderer before the algorithm.
- `main.rs` still contains the `QREMESH_DEBUG` position-field diagnostics from spike 1. They can be deleted along with spike 1.
- The spec's §3.8 and §7.6 still describe the older plan: an Instant-Meshes-style own implementation, with optional backends as fallback. Update them to the QuadWild plan and to Rust as a standalone binary.
- Repo conventions:
  - Commit messages are full sentences about behaviour, ending with the session's Co-Authored-By trailer.
  - Code comments explain why, in the pack's prose style.
  - No model names go in commits.

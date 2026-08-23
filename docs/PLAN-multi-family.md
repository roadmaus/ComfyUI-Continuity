# Multi-family refactor — H3 first, LTX-AV next

Branch: `multi-family`

## Context

The pack is one model family's pipeline spread across 34 root-level Python modules
(~17.8k lines) and `js/minimax_creator/` (~36k lines). It works, but everything
about MiniMax H3 — two routed checkpoints, the `<Picture N>` ordinal protocol,
the 17n+5 frame grid, `KSampler` + `MiniMaxH3SigmaShift` — is spelled directly
into modules that also hold the parts that have nothing to do with H3: the
picker, the timeline, the trim editor, the cast, LoRA management, the reel, the
mux, the settings page.

The goal is a suite: LTX 2.5 (`LTXAV` in core) next, more later, **without
rewriting the UI each time**. Core has already done part of this work — the
joint AV latent is `comfy.nested_tensor.NestedTensor` and
`LTXVConcatAVLatent`'s own description says "any AV model, e.g. LTXV or MiniMax
H3" — so the reel/spill/mux/decode layer is family-neutral by construction.

Investigation showed the frontend is already ~95% family-neutral: `trim.js`,
`picker.js`, `editor.js`, `timeline.js`, `cast.js` carry almost no H3 knowledge.
The H3 knowledge is concentrated in **`state.js` (101 hits in 3568 lines)**,
which is the blob schema every other file reads. That concentration is the
lever this whole plan turns on.

Two hard constraints found during investigation:

1. **Widget values are restored by position.** `creator_node._schema` declares
   13 sampler widgets, and the `sage` slot is already kept alive solely because
   reclaiming it would silently hand the next widget a `true`. No widget may
   ever be removed or reordered.
2. **The 13 sampler widgets are already hidden by the frontend** and re-drawn
   as pills (`js/minimax_creator.js:247`, `SAMPLING_WIDGETS`). So freezing the
   slots forever costs nothing visually — which is what makes the sampler
   migration safe.

**Scope of this branch: refactor only.** H3 stays the sole video family. No
`ltx25/` implementation here; the design is validated by inspection against
core's `nodes_lt.py` / `nodes_lt_audio.py`, and LTX lands on its own branch.
The pack keeps its published name (`minimax-creator`); the registry rename
happens as its own change when there is a second family to justify it to users.

## End state

```
Minimax_creator/
  __init__.py                      # thin: re-export from the package below
  creator/
    nodes/       creator.py prestage.py graph_nodes.py
    core/        blob.py media.py mux.py spill.py outputs.py settings.py
                 preview.py lorameta.py faces.py latents.py piece.py
                 timeline.py          # seams, feather, clip merge, reel wiring
                 emit.py              # the generic render loop
    families/
      base.py registry.py manifest.py
      h3/        manifest.py canvas.py compile.py encode.py render.py
                 models.py payload.py contextir.py subjects.py accel.py
                 hires.py facepass.py lora.py still.py prompts/
      krea2/     manifest.py compile.py render.py
      ideogram4/ manifest.py compile.py render.py
    refine/      engine.py routes.py local.py skill.py
    routes/      assets.py loras.py settings.py preview.py compiled_prompt.py
                 families.py          # serves the manifests
    h3lora/                            # vendored, untouched
  web/
    creator.js
    creator/
      core/    state.js dom.js api.js i18n.js canvas.js manifest.js
      ui/      timeline.js editor.js cast.js picker.js trim.js prompt.js
               loras.js loradetail.js fullscreen.js stage.js pills.js
               sampling.js prestage.js outputs.js turbo.js waveform.js …
      styles/  presets/  locales/
  tests/ core/ families/h3/ mirror/
  docs/
```

### The family contract

A family is a Python object (`families/base.py`) plus a manifest it serves to
the frontend. The graph-side boundary already exists and is
`MiniMaxH3TimelineSegment` — it takes `segment_data` + loader links and returns
`(model, positive, latent, lead model)`. **That tuple is the contract.** Each
family supplies its own segment node with that signature.

```python
class Family:
    id, label, produces          # "h3", "MiniMax H3", {"video", "still"}
    def manifest(self) -> dict            # what the frontend renders from
    def compile(self, blob, ...) -> Compiled
    def emit_loaders(self, graph, weights, routes) -> Links
    def emit_segment(self, graph, links, payload, compiled, seams) -> Node
    def emit_sampler(self, graph, model, pos, neg, latent, sampling, seed)
    def emit_refine(...) / emit_face(...)     # capability-gated, may be absent
    def patch(self, graph, model, sampling, acceleration, weights)
```

`emit_sampler` is a full subgraph, not a node id: H3 emits `KSampler`, LTX will
emit `LTXVScheduler` → SIGMAS + `LTXVDualCFGGuider` → GUIDER →
`SamplerCustomAdvanced`.

### The manifest describes *controls*, not just values

This is the part that decides whether the UI really survives a new family. LTX
brings concepts H3 has no analogue for — `video_cfg`/`audio_cfg`, `stretch`,
`terminal`, auto-duration from `LTXVDurationPredictor`, per-guide `strength`,
spatial `attention_mask` — so a manifest of H3-derived constants would not have
anticipated them. The manifest therefore carries a small widget vocabulary:

```
{ id, type: slider|toggle|combo|stepper, min, max, step, default,
  label, help, group: sampler|weights|reference }
```

`sampling.js` already draws its row generically from a `widgets` object via
`widgetIO`/`samplingBar` — it renders from a declaration with modest change.

Manifest also declares: **weight slots** (id, label, help, ComfyUI folder key,
folder-name hints, required, gguf-capable, *how many files the loader takes* —
`LTXAVTextEncoderLoader` takes two, and LTX's audio VAE comes from
`checkpoints`, not `vae`); **canvas rules** (snap multiple, frame congruence,
fps and whether fps is fixed or conditioning, native short edge, area cap);
**modes**; **capabilities** (bidirectional — LTX *has* things H3 lacks);
**routes**; **reference vocabularies**; **prompt pipeline**.

## Phases

Each phase ends green and is independently reviewable.

### Phase 0 — Safety net

The mirror tests are what make this refactor survivable: eight suites already
execute the JS and compare it to Python (`test_canvas_mirror`,
`test_scopes_mirror`, `test_piece_mirror`, `test_passes_mirror`,
`test_holds_mirror`, `test_cast_mirror`, `test_outputs_mirror`,
`test_prestage_mirror`). 16 suites spawn `node`; 11 boot ComfyUI.

- Parameterise every mirror suite by family + JS path instead of hardcoding
  `js/minimax_creator/*.js` and H3's values.
- Add **golden-graph snapshots**: extend the existing graph suites
  (`test_creator_graph`, `test_timeline_graph`, `test_face_graph`,
  `test_seam_anchor`, `test_prestage_graph`) to serialise the emitted subgraph
  for a fixed set of representative blobs — text-only, keyframe, reference-heavy,
  3-segment chained with a feathered seam and audio tail, one-pass merge,
  two-pass refine, face pass, supplied clip.

**Every later phase asserts these snapshots are byte-identical.** That is the
whole safety argument; phases 1–3 must not change a single emitted node.

### Phase 1 — Tree move, no logic

Pure `git mv` + import rewrites, so phases 2–5 are written once, in the final
layout. Root `__init__.py` stays (ComfyUI imports the custom_nodes folder as a
package) and re-exports from `creator/`. `WEB_DIRECTORY` → `"./web"`.

Verify: node loads in ComfyUI, all tests green, golden graphs identical.
`.comfyignore` and `pyproject.toml` need no change; the publish workflow only
fires on `pyproject.toml` pushes to `main`, so the branch cannot publish.

### Phase 2 — Sampler settings into the blob

The riskiest change, done early and alone.

- `creator_data.sampling` becomes the source of truth for steps/cfg/sampler/
  scheduler/shifts/accelerators.
- **All 13 widget slots stay declared, in order, forever.** They are already
  hidden, so nothing changes visually. `execute` prefers `blob.sampling` and
  falls back to the widget values when the blob has no `sampling` block — that
  fallback *is* the migration, and it means no saved workflow can break.
- `seed` stays a genuine widget: `control_after_generate` only exists on one.
- `samplingBar` writes the blob; on load, a blob without `sampling` is seeded
  from the widget values once.
- `render.Sampling` stops being a fixed dataclass and becomes family-shaped.

Verify: golden graphs identical for blobs with and without a `sampling` block;
a workflow saved on `main` loads, queues, and emits the same graph.

### Phase 3 — Family contract, H3 extracted

Pure move plus dispatch. Nothing user-visible changes.

- `families/base.py` + `families/h3/` from the current modules.
- `render.emit` splits: the generic loop (routing, progress stamping, the clip
  branch, seam wiring, reel/spill/save, takes) moves to `core/emit.py`; the
  family supplies loaders, segment, sampler, refine, face, patch.
- `Compiled` splits. Shared: prompt, frames, seconds, canvas, assets, seam
  fields, loras, refine. **H3-only** (moves into the family payload): `plan`,
  `labels`, `subject_labels`, `checkpoint`, `checkpoint_pinned` — roughly 60% of
  today's dataclass is H3 protocol.
- `models.py`'s `FOLDERS` / `LABEL` / `DEVICE_FIELDS` / `available()` /
  `check()` / `emit_links()` become slot-driven. `Links` stops being a fixed
  dataclass with `model_fl2va`/`model_ref2va` and becomes a slot dict.
  `available()` already returns `by_folder` for the PreStage — reuse it.
- `contextir.py`, `subjects.py`, `payload.py`, `prompts/modes/*` move into
  `families/h3/` unchanged. They do **not** generalise and must not be forced
  to: LTX takes plain prose through Gemma and has no ordinal protocol.
- `refine/engine.py` keeps transport + VLM loading; template, reply JSON schema
  and compose step become family-owned.

Verify: golden graphs byte-identical. This phase changes no behaviour at all.

### Phase 4 — Manifest, registry, PreStage folded in

- `families/manifest.py` + `routes/families.py` serving `/minimax_creator/families`.
- `krea2` and `ideogram4` become still-only families; `compile_image.py`'s
  per-arch constants (`KREA_RAW`, `IDEOGRAM_QUALITIES`, `IDEOGRAM_CFG_LATE`) and
  `render_image.py`'s `_emit_krea2`/`_emit_ideogram4` split into their own
  packages. One registry, not two — a family declares what it `produces`, and H3
  produces both video and still (`compile_still.py`/`render_still.py` become
  `families/h3/still.py`).
- `canvas.py` parameterised by family; `canvas.js` reads the params.
  `FPS = 24` stops being a module constant — LTX carries frame rate as
  conditioning (`LTXVConditioning`), default 25.

### Phase 5 — `state.js` drained

The frontend reads the manifest instead of holding constants: `MODEL_FIELDS`,
`ROUTES`, `CHECKPOINTS`, `FOLDER_HINTS`, `derivedCheckpoint`, `canPinCheckpoint`,
the take vocabularies, the frame grid.

**Pass condition:**
`grep -riE "fl2va|ref2va|h3|minimax" web/creator/{core,ui,styles}` returns
nothing outside `manifest.js` and the frozen node-id constants in `creator.js`.

Anything the UI branches on that is not in the manifest is a leak, and this grep
is the audit.

## Frozen contracts — do not touch

- **The 20 `MiniMaxH3*` node class ids.** They are named in saved workflows on
  disk. `MiniMaxH3Creator` will render LTX one day under a misleading name;
  accept it. New ids only for genuinely new nodes.
- **Sampler widget slots** — never removed, never reordered (see `sage`).
- **`/minimax_creator/*` routes** — safe to rename later with a one-release
  alias, but not on this branch.
- **`creator_data` blob compatibility** — `compile.as_piece` already reads the
  retired two-node shape; every schema change needs the same treatment.

## Risks

- **`presets/atlas.js` + the 110-image atlas.** Style presets are very likely
  H3-prompt-shaped. Needs checking whether a preset's prose survives being handed
  to another family; if not, presets need a family tag and the library needs
  filtering. Not blocking this branch, but it must be answered before LTX.
- **i18n.** Three dictionaries of ~1250 lines each, keyed by English string, plus
  `locales/*/nodeDefs.json`. Any label that moves into a manifest leaves the
  dictionary — manifests need their own translation path or three languages
  silently lose coverage.
- **`accel.py` does not extend cleanly.** Its model is "optional installed packs,
  free speed". LTX's STG / modality guidance / identity guidance are *core*
  nodes that each cost an extra forward pass and are taste choices, not speed
  choices. Same wiring discipline, different pill semantics — do not put them
  behind the accelerator UI.
- **Phases 0–3 are pure motion.** No feature ships until phase 4, and the payoff
  is entirely in the LTX branch after it. Worth being explicit about before
  starting.

## Verification

Per phase, in order:

1. `for t in tests/test_*.py; do python3 "$t"; done` using the ComfyUI venv —
   graph suites need `~/Documents/ComfyUI/.venv` plus `COMFYUI_PATH`/`BASE`;
   system `python3` silently reports them as skipped.
2. Golden-graph snapshots byte-identical to the phase-0 baseline (phases 1–3).
3. Mirror suites green (they need `node` on PATH).
4. Load ComfyUI, drop a Creator node, confirm the body mounts, the picker lists
   input files, the weights popover lists models, and the sampler row draws.
5. Load a workflow saved from `main` before the branch: it must load, show the
   same values, and queue to the same graph.
6. Since this Mac never samples, an actual render is verified on RunPod from a
   pushed branch — the last check before merge, not per phase.

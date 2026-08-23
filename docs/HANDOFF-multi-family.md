# Handoff — the multi-family refactor

Branch `multi-family`. The plan is `docs/PLAN-multi-family.md`;
read it first, it holds the reasoning this file assumes.

**Where it is: phases 0–4 are done. Phase 5 (`state.js` drained — the
frontend reads the manifest instead of holding constants) has not been
started.**

## Run the suite like this

```sh
export COMFYUI_PATH=~/ComfyUI-Installs/ComfyUI/ComfyUI
export COMFYUI_BASE=~/Documents/ComfyUI
PY=~/Documents/ComfyUI/.venv/bin/python3
for t in tests/test_*.py; do $PY "$t" >/dev/null 2>&1 || echo "FAIL $t"; done
```

**Judge every suite by its exit code.** Not by grepping stdout: a node link error
and a JS stack trace contain neither "Traceback" nor "failure(s)", and a loop
that greps for those reported 43/43 green on a run that contained a hard
failure. That mistake cost a broken commit — see below.

46 suites, all green, no skips (`node` and the venv are both present here).

## What the three finished phases actually bought

**Phase 0 — the net.** `tests/test_golden_graph.py` freezes ten whole emitted
subgraphs in `tests/golden/*.json`, covering every branch in `render.emit` that
changes the *shape* of the graph. Re-record with `UPDATE_GOLDENS=1` and **read
the diff** — an unreviewed re-record throws the net away. Machine settings and
image sizes are pinned inside the suite, or the goldens record whoever ran them.

`tests/layout.py` holds the repo layout — `PY_ROOT`, `WEB_ROOT`, `MODULES` — for
all 25 suites that need a path into the package. **Phase 3 moves modules into
`creator/families/h3/`; that is an edit to `MODULES` in that one file**, which is
the whole reason it exists.

**Phase 1 — the move.** `*.py` → `creator/`, `js/minimax_creator/` → `web/creator/`.
Flat inside `creator/`, deliberately: deciding which module is core and which is
family *is* phase 3's work, and pre-sorting them here would have smuggled those
judgements into a commit that claimed to be a pure rename. `locales/` stayed at
the root — ComfyUI reads it from the custom-node directory, not from a module.

**Phase 2 — the sampler row into the blob.** `creator/sampling.py` (pure, no
ComfyUI import) resolves the row from `creator_data.sampling`, falling back to
the widget values **field by field**. That fallback is the migration. All 13
widget slots stay declared and hidden forever — widget values restore by
position, and this pack has already shipped that bug once (see the `sage` slot).

## Phase 3 — what was actually built

**The contract is `creator/families/base.py`**, and the loop is
`creator/core/emit.py`: routing orchestration, progress stamping, the clip
branch, seam wiring (the loop builds the seam links and hands them to the
family in a dict), reel/spill/save, takes. `creator/families/h3/render.py` is
H3's half — loaders, segment, sampler, refine, face, patch — behind the
segment node's `(model, positive, latent, lead model)` tuple.
`creator/render.py` is now a thin binding of loop to family, kept because
every caller spells `render.emit` and there is one family to bind until the
phase-4 registry; the registry replaces it.

**Moved into `creator/families/h3/`:** `contextir`, `subjects`, `payload`,
`prompts/`, `refine` (the templates/reply-schema/compose half — the plan's
"engine", i.e. `refine_local`/`refine_routes`/`refine_skill`, stays outside).
`tests/layout.py`'s `MODULES` maps the moved names, and a meta-path finder in
`load()` serves them to flat sibling imports, so suites never learn paths.

**`models.py` is slot-driven:** a `SLOTS` table declares each file's folder,
label, loader and routing; `FOLDERS`/`LABEL`/`DEVICE_FIELDS` are derived reads
and `Links` is a slot mapping (attribute spelling kept — `.vae`/`.audio_vae`
are the loop's contract). LTX is different rows, not different code.

**One deliberate deviation:** the plan's "`Compiled` splits" bullet was
resolved by contract instead of by nesting. The loop's read surface (seam
fields, `refine`/`face` truthiness) is documented on `base.Family.compile`;
the H3-only fields stay flat on `Compiled` because all ~90 readers are
H3-owned code. If a second family's compiled type ever needs a shared base,
cut it then, with two implementations to check it against.

`creator/sampling.py` is already the shape a family manifest wants — pure, with
`DEFAULTS` mirrored by `SAMPLING_FIELDS` in `state.js` and a mirror test holding
them together. Extend that pattern; do not invent a second one.

## Phase 4 — what was actually built

Six commits, each green ("The still walks into the family" .. "The canvas
math learns whose numbers it runs"):

- **`families/registry.py` is the one table**: `FAMILIES` order, `PRODUCES`,
  and `STILL_ARCHES` — the pre-stage blob's `"minimax"` stays the frozen
  alias for `h3`. `registry.video()` hands the loop its `Family` singleton;
  `registry.still(arch)` hands the PreStage a family's still module. All
  resolution is lazy, because h3's video half imports ComfyUI.
- **Every still family speaks two verbs** — `compile_still(data,
  image_size_lookup)` and `emit_still(data, plan, sampling, unique_id)` — so
  `prestage.execute` is one registry dispatch, no arch branch.
- **`families/krea2/` and `families/ideogram4/`** own their constants, CLIP
  types, weights fields, core-support probes and sampler branches;
  `compile_image.py`/`render_image.py` are the *shared* image-still flow,
  parameterised by a family module (`family.plan`, `family.emit_graph`,
  `family.FIELDS`…). H3's still is `families/h3/still.py`, compile and graph
  halves in one module (the emit half imports lazily; the compile half stays
  pure).
- **`creator/render.py` is gone.** The nodes call
  `core.emit.emit(registry.video(), ...)` and normalise the turbo `LeadIn`
  at the call site; the row is spelled `sampling.Sampling` everywhere. Two
  node tooltips still say "render.emit" because those strings are i18n keys.
- **The manifests**: `families/manifest.py` defines the widget vocabulary
  (`{id, type: slider|toggle|combo|stepper, min, max, step, default, label,
  help, group}`) and validates; each family's `manifest.py` is built *from*
  `sampling.DEFAULTS`, `models.SLOTS`, `canvas.H3` and the family stills — no
  number exists twice. A combo without `options` means the node schema owns
  the list. `creator/routes/families.py` serves the catalog at
  `/minimax_creator/families` (registered from the root `__init__.py`).
  `tests/test_families.py` holds it all together and has been seen failing.
- **`canvas.py` is parameterised**: family-neutral math over a `Rules`
  dataclass, `canvas.H3` the one instance, historic module constants kept as
  reads off it (`fps_fixed` is part of the declaration). `canvas.js` mirrors
  the shape — `H3_RULES`, every function taking `rules` with H3 defaulted —
  so phase 5 can hand manifest rules in without touching the math.

`tests/layout.py` grew with it: `MODULES` names moved modules by dotted path
and `load()` imports them at their real place in the package (aliased flat),
which is what lets a moved module import upward.

## Phase 5 starts here

`state.js` drained: the frontend reads `/minimax_creator/families` instead of
holding `MODEL_FIELDS`, `ROUTES`, `CHECKPOINTS`, `FOLDER_HINTS`, the take
vocabularies, the frame grid. The pass condition is the plan's grep. Watch
the i18n risk the plan names — labels that move into the manifest need a
translation path — and remember the mirror suites run `state.js` under bare
`node`: whatever fetches the manifest must be injectable the way
`CreatorEditor`'s `samplingStore` is.

## Things that will bite

- **A suite that can skip can swallow a failure, and exit 0 doing it.** The
  ComfyUI-booting suites used to import the *pack* inside the same try/except
  that skips on a machine without ComfyUI — so a pack that failed to import
  printed "skipped: ComfyUI not importable" and exited green. Eight suites,
  goldens included, reported green for a whole afternoon on a branch whose
  node did not load; ComfyUI's own startup log is what said so. The guards now
  import the pack *outside* the skip; keep it that way, and when a run
  matters, confirm the booting suites printed their pass line rather than
  "skipped". A one-line real-load check is opening ComfyUI's newest log under
  the install's `logs/` and searching for `IMPORT FAILED`.
- **`node --check` proves nothing about imports.** It is a parse. ES modules
  resolve named imports at *link* time, so one missing export takes down the
  whole extension and every node falls back to raw widgets. `tests/test_js_links.py`
  is the guard — it imports all 53 frontend modules individually and through the
  entry point, and names the export and the file. Run it after any JS rename.
- **A test that passes before and after the fix is worthless.** Two of the three
  guards written during phase 2 did exactly that on the first draft. Revert the
  fix, watch the test fail, restore. Every guard on this branch has been through
  that and the commit messages say so.
- **The frontend has four faces and they keep the row in three places.** The
  piece as a strip (`TimelineBody` → `timeline.sampling`), the piece as one shot
  (`CreatorEditor` over the piece), and the pre-stage — whose H3 branch mounts a
  `CreatorEditor` over a *nested* creator request while the sampler widgets
  belong to the pre-stage node. That mismatch is why `CreatorEditor` takes an
  injectable `samplingStore`. `tests/test_sampling_persist.py` drives all four.
- **Read values through `value()`, options off the widget.** The combo's option
  list is the node's schema and the blob has no business copying it; the *value*
  moved. One line in `samplingBar` still read `widget.value` and the schedule
  pill silently stopped responding on every face.
- **Frozen, do not touch:** the 15 `MiniMaxH3*` node ids (saved workflows name
  them), the sampler widget slots and their order, the `/minimax_creator/*`
  routes, and `creator_data` back-compat.

## Not done, and known

- **Phase 2 is not verified against a workflow saved before this branch.**
  Deliberate: old-workflow compatibility is not a promise this branch makes and
  the release notes will say so. Old *presets* open fine
  (they go through `parseSampling`, not widget restore). The per-field fallback
  in `sampling.resolve` stays load-bearing regardless — a fresh untuned node and
  a headless API queue both have no `sampling` block.
- ~~Nothing has been rendered.~~ Rendered on RunPod from the pushed branch,
  2026-08-23 — works. Re-verified there after phase 3 (loop split, slot table,
  refine move, the load-failure fix), same day.
- **`presets/atlas.js` is probably H3-prompt-shaped.** Whether a preset's prose
  survives being handed to another family is unanswered and blocks LTX, not
  phase 3.
- **i18n**: three dictionaries keyed by English string. Any label that moves into
  a manifest leaves the dictionary unless a translation path goes with it.

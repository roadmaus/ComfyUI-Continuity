# Handoff — the multi-family refactor

Branch `multi-family`, seven commits off `main`. The plan is `docs/PLAN-multi-family.md`;
read it first, it holds the reasoning this file assumes.

**Where it is: phases 0, 1 and 2 are done. Phase 3 has not been started.**

## Run the suite like this

```sh
export COMFYUI_PATH=/Users/felix/ComfyUI-Installs/ComfyUI/ComfyUI
export COMFYUI_BASE=/Users/felix/Documents/ComfyUI
PY=/Users/felix/Documents/ComfyUI/.venv/bin/python3
for t in tests/test_*.py; do $PY "$t" >/dev/null 2>&1 || echo "FAIL $t"; done
```

**Judge every suite by its exit code.** Not by grepping stdout: a node link error
and a JS stack trace contain neither "Traceback" nor "failure(s)", and a loop
that greps for those reported 43/43 green on a run that contained a hard
failure. That mistake cost a broken commit — see below.

45 suites, all green, no skips (`node` and the venv are both present here).

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

## Phase 3 starts here

The family boundary already exists on the graph side and is
`MiniMaxH3TimelineSegment`: it takes `segment_data` plus loader links and returns
`(model, positive, latent, lead model)`. That tuple is the contract. `render.emit`
splits into the generic loop (routing, progress stamping, the clip branch, seam
wiring, reel/spill/save, takes) and family hooks for loaders, segment, sampler,
refine, face and patch.

`creator/sampling.py` is already the shape a family manifest wants — pure, with
`DEFAULTS` mirrored by `SAMPLING_FIELDS` in `state.js` and a mirror test holding
them together. Extend that pattern; do not invent a second one.

## Things that will bite

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

- **Phase 2 is not verified against a workflow saved before this branch.** The
  fallback path is unit-tested and the goldens cover a blob with no `sampling`
  block, but nobody has opened a real pre-branch `.json` in ComfyUI and queued
  it. Do that before phase 3 stacks on top.
- **Nothing has been rendered.** This machine never samples — verify on RunPod
  from a pushed branch.
- **`presets/atlas.js` is probably H3-prompt-shaped.** Whether a preset's prose
  survives being handed to another family is unanswered and blocks LTX, not
  phase 3.
- **i18n**: three dictionaries keyed by English string. Any label that moves into
  a manifest leaves the dictionary unless a translation path goes with it.

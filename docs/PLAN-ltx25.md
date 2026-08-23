# LTX 2.5 — the second family

Branch: `ltx25`, cut from `multi-family` (phases 0–5 complete, rendered and
UI-tested on RunPod 2026-08-23). Not merged through `main`: this branch is
why the refactor exists, and it starts immediately on top of it.

## The files LTX 2.5 actually ships (the layout the slots must match)

```
models/
  diffusion_models/     ltx-2.5-22b-distilled-transformer-…-int8-convrot
  text_encoders/        gemma4-12b-with-proj-ltx-2.5-…      (the encoder)
                        gemma4_e2b_it_…                      (optional, smaller)
  vae/                  ltx-2.5-video-vae-bf16
                        ltx-2.5-audio-vae-bf16
  latent_upscale_models/ ltx-2.5-latent-spatial-upscaler-x2-…
```

The multi-family plan's warnings about a two-file text encoder and an audio
VAE from `checkpoints` describe the **Gemma-3 recipe**
(`LTXAVTextEncoderLoader` / `LTXVAudioVAELoader`), which LTX 2.5 does not
use. Verified in `comfy/sd.py`: the `-with-proj` file carries
`text_embedding_projection.video_aggregate_embed.weight`, which the
single-file detection recognises and builds the full LTXAV encoder from
(`sd.py:1781`) — so the encoder is one pick from `text_encoders` through the
ordinary `CLIPLoader` type `ltxv`, and the audio VAE is one pick from `vae`
through the ordinary `VAELoader`, whose generic detection knows the
Lightricks `audio_vae.` prefix (`sd.py:932`). **The slot table stays one
file per slot** — the same shape H3's is, two VAEs sharing `vae/` and all.

## What core provides (verified against the running install)

All read from `~/ComfyUI-Installs/.../comfy_extras/nodes_lt.py`,
`nodes_lt_audio.py` and `comfy/sd.py` — the design below binds to these,
not to memory:

- **Text encoder**: one file, `CLIPLoader` type `ltxv` (see above). The
  optional `gemma4_e2b_it` is a smaller E2B variant the same detection
  loads — a second candidate for the slot, not a second slot.
- **Video and audio VAE**: two `VAELoader` picks from `vae/` (see above).
- **Upscaler**: `LTXVLatentUpsampler(samples, upscale_model, vae)` with the
  model from `latent_upscale_models/` — the spatial x2 pass, a natural
  `hires`-like capability for a later phase, not the first render.
- **Latents**: `EmptyLTXVLatentVideo` — width/height step **32**, length step
  8 (default 97), latent T = `(length-1)//8 + 1`, default canvas 768×512.
  The frame grid is **8n+1** (the duration head snaps to it too).
- **AV latent**: `LTXVConcatAVLatent` / `LTXVSeparateAVLatent` /
  `LTXVEmptyLatentAudio` — the packed latent the reel/spill/mux layer already
  speaks (`NestedTensor`; Concat's own description names MiniMax H3).
- **fps**: conditioning, not architecture — `LTXVConditioning(positive,
  negative, frame_rate)`, default **25**. (`LTXVDurationPredictor` defaults
  its own `frame_rate` to 24; the manifest must pin one number and pass it
  everywhere.)
- **Sampler**: `LTXVScheduler(steps, max_shift=2.05, base_shift=0.95,
  stretch, terminal=0.1, latent)` → SIGMAS, `LTXVDualCFGGuider(model, pos,
  neg, video_cfg=3.0, audio_cfg=7.0)` → GUIDER, then `SamplerCustomAdvanced`.
  The shift pair rides the token count, so the scheduler wants the latent
  handed in.
- **Model patch**: `ModelSamplingLTXV(max_shift, base_shift)`.
- **Guides**: `LTXVAddGuide(cond, vae, latent, image, frame_idx, strength,
  attention_mask?, iclora_parameters?)` — per-guide strength, frame_idx on
  the 8-grid, negative indexes from the end; `LTXVCropGuides` after
  sampling. `LTXVImgToVideo(strength)` for the plain first-frame case.
- **Duration**: `LTXVDurationPredictor(model, positive, duration_head,
  frame_rate, min_seconds, max_seconds)` — the head is a separate file
  through `ModelPatchLoader` (`MODEL_PATCH`).
- **Taste guidance, NOT accelerators**: `LTXVSpatioTemporalGuidance`,
  `LTXVModalityGuidance`, `LTXVReferenceAudio`. Each costs a forward pass;
  they do not go behind the accel pill (decided in the multi-family plan).

## What the refactor already bought

The loop (`core/emit.py`) owns routing, progress, seams, reel/spill/save.
The family supplies loaders, segment, sampler, refine/face (absent here),
patch — behind `families/base.py` and the segment tuple `(model, positive,
latent, lead model)`. The frontend renders from the served manifest: canvas
rules, widgets, weight slots, reference grammar, turbo, capabilities all
arrive as declarations. `tests/test_family_leaks.py` keeps it that way.

## The one thing phase 5 did not have to solve — and this branch does

`web/creator/manifest.js` exports `VIDEO` — **the** family that produces
video — and `state.js`, `canvas.js`, `models.js` bind to it at module load.
With a second video family that binding is wrong by construction: *which*
family a piece renders with becomes a field of the blob, and the controls
must read `family(blob.family)` instead of a module constant.

Plan: `creator_data.family` (absent = `"h3"`, the back-compat default —
`compile.as_piece` treatment), a family pill on the piece, and the
manifest-reading constants in `state.js`/`canvas.js` become functions of the
active family with the current names kept as the H3-bound defaults so the
diff stays reviewable. The blob's `models` block is family-shaped already
(the slot ids are the manifest's). Do this **first**, while there is still
only one family to bind — it is pure motion and every suite must stay green
and every golden byte-identical, which proves the re-plumbing changed
nothing before LTX rides in on it.

## Phases

Each ends green; goldens are re-recorded only when a phase *adds* graphs.

1. ~~**Family selection plumbing** (above). No new family yet; behaviour
   frozen by the existing suites.~~ **Done** — see below.
2. ~~**`families/ltx25/` skeleton**: registry row, slot table, canvas Rules,
   manifest.~~ **Done** — see below.
3. **The render half**: `render.py` — loaders, segment (prompt through
   Gemma as plain prose, guides via `LTXVAddGuide`, first/last frames on the
   8-grid), sampler subgraph, `ModelSamplingLTXV` patch, `LTXVConditioning`
   with the manifest's fps. Golden graphs for the LTX blobs: text-only,
   first-frame, guide-with-strength, audio on/off. **And the controls stop
   reading module constants**: the weights popover, the sampler row and the
   LoRA manager take the piece's family instead of the default's — the
   accessors are all in place from phase 1, and phase 2's manifest is the
   first one whose shape differs enough for a stale reader to show.
4. **Duration and the second pass**: the duration predictor as the seconds
   pill's "auto" (capability-gated — H3 simply lacks it), the x2 latent
   upscaler as this family's `upscale`, and seam/feather verification on the
   8-grid latent (the reel layer is family-neutral by core's own construction;
   prove it with a chained golden). Weigh native multishot here too.
5. **Taste guidance**: STG / modality / reference-audio as their own pills
   with honest cost copy — new UI, not the accel row.

## Phase 1, as landed

The field is `creator_data.family`, at piece level beside the canvas and for
the same reason. Absent means `h3`, permanently — `compile.piece_family` reads
it, and so does an unknown id, because a blob naming a family this install has
not got is a piece to draw rather than a queue to refuse. It is written to the
blob only when it is *not* the default, the rule `upscale` and `aspect_source`
already follow, which is what keeps every existing workflow byte-identical.

The catalog gained `video_families` and `default_video_family` off
`registry.video_families()` / `registry.DEFAULT_VIDEO`, so the pill offers
exactly the set the compiler accepts and falls back exactly where it does.
`manifest.js` grew `videoFamily(id)` — the forgiving lookup, `family()` still
throwing for an id the code produced itself — and `VIDEO` is now the default
family's manifest rather than "the one that makes video".

`canvas.js` grew `rulesFor(id)`; `state.js` grew `pieceFamily`, `familyOf`,
`canDo`, and one accessor per block a control reads off a family
(`referenceOf`, `weightsOf`, `routesOf`, `modesOf`, `turboOf`, `stillOf`,
`widgetsOf`, plus `modelFields` / `deviceFields` / `checkpointsOf` /
`routeOptions` / `alwaysRequired` over the slot table). The historic constants
are still there, bound to the default family — the H3-shaped controls read
those, and teaching each of them to ask the piece is phase 3's work, not a
rewrite done blind. `emptyModels`, `parseModels`, `serializeModels` and
`guessModels` take a family id already, because the weights block's *keys* are
the family's and that is the one place carrying state across would corrupt it.

`setFamily` is the switch: the writing stays (prompt, cast, pool, strip, seams)
and everything keyed by the old family's vocabulary goes — the weights block,
the turbo LoRA, each card's checkpoint pin — while a LoRA is retargeted rather
than dropped, and the canvas is re-clamped to the new family's grid, ceiling
and native edge. The pill is `models.familyPill`, in front of the weights pill
in both faces' trailing group, drawn as a static readout while there is one
family to choose.

`tests/test_family_select.py` is the proof, and it does the awkward part: since
one family makes "the control read the piece's family" unprovable, it runs the
frontend a second time against a **probe** catalog — H3's manifest with its slot
ids, routes and canvas numbers rewritten — so a reader still bound to a module
constant answers H3 for a probe piece and is caught. `layout.run` took a
`catalog=` argument for it. Every suite is green and `tests/golden` is
untouched.

## Phase 2, as landed

`families/ltx25/` is `models.py` (the slot table), `sampling.py` (the row's
defaults) and `manifest.py` (the declarations), all pure, plus a `render.py`
holding one `Family` whose `preflight` refuses in a sentence. Refusing from
`preflight` is what makes it polite: it is the first hook `core/emit.py` calls,
before a payload compiles or a node is built, so a queued LTX piece stops with
prose rather than a `NotImplementedError` three hooks deep. Every other hook is
inherited unimplemented and would raise under its own name.

The slot table is flat, one file per slot, and `test_families` holds it that
way — the encoder is one `CLIPLoader` pick typed `ltxv` and the audio VAE one
`VAELoader` pick from `vae/`, not the Gemma-3 recipe's two-file loader pair.
`Slot` grew one field, `optional`, for the two opt-in passes (`duration_head`,
`upscaler`); every H3 slot is required, so it defaults off and nothing moved.

`canvas.LTX25` sits beside `canvas.H3`, and the canvas block both manifests
serve is now `families/manifest.canvas_block(rules)` — the fields are the
contract `canvas.js` reads and they are the same fields for every family, so
the second copy was deleted rather than written.

**Two frontend fixes the second family found**, both in `state.js`, both the
kind only a real second family could surface:

- `routesOf` now falls back to a no-routing block. LTX ships one transformer,
  so its manifest declares no `routes` at all — a control offering one option
  is a lie — and `emptyModels`/`setFamily` would have thrown on the absence.
- `alwaysRequired` filtered on loads-and-not-routed, which made both opt-in
  passes weights the queue refuses without. It reads `required` now; absent
  still means required, which is what every family written before the key
  needs.

The frontend lists LTX 2.5 and selects it: `setFamily` drops the H3 weights
block, the turbo LoRA and the checkpoint pins, re-clamps the canvas to the new
grid, and the piece round-trips carrying `family: "ltx25"`. The weights popover
and the sampler row are still bound to the default family's constants — phase
3's work, as phase 1 recorded, and the reason the refusal above exists.

## What the model card settled (and where the plan was wrong)

Lightricks' LTX-2.5 card, read during phase 2. It answers both open questions
and moves numbers this plan had guessed at:

- **fps is 24, not 25.** `LTXVConditioning` defaults to 25.0, but the card's
  own reference pipeline runs at 24.0 and `LTXVDurationPredictor` clamps
  against 24.0. Two statements from Lightricks against one Comfy widget
  default. `canvas.LTX25` pins 24, `fps_fixed=False`.
- **The native canvas is 544×960**, the resolution the card's two-stage example
  samples at; the x2 spatial upscaler is what takes it to 1088×1920. So the
  native edge is stage one's, and `resolve_canvas(16/9, 544)` returns exactly
  960×544. `frames_for_seconds(5)` returns 121 — the card's own frame count.
  The area cap keeps H3's shape (960/544 = 1.76 against 1344/768 = 1.75).
- **The trained frame range is the duration head's default clamp**: 1 s to
  20 s at 24 fps on the 8n+1 grid, so 25 to 481.
- **The distilled transformer is the default row**: a fixed 8-step schedule at
  CFG 1, and the card's reference call passes `guidance_scale=1.0,
  audio_guidance_scale=1.0`. The `dev` transformer wants the node defaults
  instead (20 steps, 3.0/7.0). That is a file the user picks in the same slot,
  so it is a row they change rather than a mode the pack switches.
- **The negative prompt has a canonical answer**: diffusers ships
  `DEFAULT_NEGATIVE_PROMPT` for this family. Phase 3 uses it as the row's
  default rather than inventing a template string.
- **`refine` has a better answer than a prose template**: the family's second
  pass is Lightricks' own — sample at the native edge, run the x2 latent
  upscaler, sample again. That is `upscale`, not the prompt-expansion refine,
  and it belongs in phase 4 beside the duration head.
- **Two files this plan's layout missed**: a second video VAE
  (`-conv-`, the fast one, against the diffusion decoder) sharing the `vae`
  slot, and `latent_upscale_models/…-temporal-upscaler-x2-…`, which is a
  second candidate for the `upscaler` slot rather than a slot of its own.
- **There is a distilled LoRA** (`loras/ltx-2.5-22b-distilled-lora-450`) for
  dev-transformer workflows — the nearest thing to H3's turbo switch. Not
  declared: the shipped path is the distilled *checkpoint*, which is a pick,
  not a switch. Worth revisiting if the dev transformer becomes the default.
- **Native multishot** is new in 2.5: one pass producing several connected
  shots that hold identity across cuts. That overlaps the strip's own seam
  grammar and is worth weighing in phase 4 — a family that can cut internally
  may want fewer feathered seams, not more.

## Open questions (answer during phase 3)

- Whether `refine` has any meaning as *prompt expansion* for a plain-prose
  family (the engine is already split from H3's templates), now that the
  second-pass upscale has its own answer above.
- What the `@` reference grammar becomes here. H3 cites by ordinal into
  Context-IR; LTX has `LTXVAddGuide` (per-guide strength, frame_idx on the
  8-grid, negative indexes from the end) and IC-LoRAs. The manifest declares no
  `reference` block until this is decided.

## Frozen, still

Everything the multi-family plan froze: the `MiniMaxH3*` node ids, the 13
sampler widget slots, `/minimax_creator/*` routes, `creator_data`
back-compat. LTX's segment node gets a **new** id — a genuinely new node.

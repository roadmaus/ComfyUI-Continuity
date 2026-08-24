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
3. ~~**The render half** and the controls reading the piece's family.~~
   **Done** — see below. The x2 upscaler came forward from phase 4 with it.
4. **Duration, multishot, and ReDetail**: ~~the duration predictor as the
   seconds pill's "auto" (capability-gated — H3 simply lacks it)~~ **done —
   see "Phase 4: auto duration" below**, and
   ~~seam/feather verification on the 8-grid latent (the reel layer is
   family-neutral by core's own construction; prove it with a chained
   golden)~~ **done — see "Phase 4: the seams" below**.
   ~~Weigh native multishot here: one pass producing several connected shots
   competes with the strip's own feathered seams rather than slotting under
   them.~~ **Weighed — see "Phase 4: multishot" below.**
   **And the cross-family upscale** — see below.
5. **Taste guidance**: STG / modality / reference-audio as their own pills
   with honest cost copy — new UI, not the accel row.

## ReDetail: LTX 2.5 as an upscale pass for *any* family (phase 4)

Bambushu's ReDetail — <https://github.com/Bambushu/redetail>, discussed on
r/StableDiffusion 2026-08-15 — re-renders a finished H3 clip through LTX 2.5 at
twice the size. It is the feature this branch's user asked for as "switch to the
LTX upscaler instead of our MiniMax refiner", and it is **not** the x2 latent
upscaler phase 3 built. Two different files and two different mechanisms:

| | phase 3's `refine` | ReDetail |
|---|---|---|
| file | `latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-…` | `loras/ltx-2.5-22b-ic-lora-pixel-spatial-upscaler-x2-1.0` |
| node | `LTXVLatentUpsampler`, on the latent between two sittings | `GetICLoRAParameters` → `LTXVAddGuide(iclora_parameters=…)` |
| input | LTX's own stage-one latent | any decoded video, H3's included |

Derived from Lightricks' own
`example_workflows/2.5/LTX-2.5_V2V_ICLoRA_Single_Stage_Distilled.json`.

**The promise, said plainly, because the pill has to say it too.** This is a
generative re-render, not restoration and not sharpening: it invents the fine
detail as it goes. The author's own tests added freckles to a face that had
none and redrew a motocross jersey's graphic and number plate — stable between
frames, and not the original markings. So it is right for AI-generated or soft
footage and wrong wherever a face, a label or a logo has to survive intact. That
makes it a *different promise* from H3's refine, which resolves what the first
pass already drew, and it earns its own choice with its own copy rather than a
silent swap behind the existing pill. The author prefers 1.5× to 2× on faces for
exactly this reason — most of the extra at 2× is invented rather than recovered.

**What falls out well for this pack.** ReDetail needs the clip to carry a
soundtrack (the graph encodes A/V jointly, and the author's instructions have
users muxing a silence track in with ffmpeg first); every pass this pack makes
has one already. And the shape is one the loop has: a pass is decoded, spilled
to disk and added to the reel, and `emit_face` already reads one back, re-renders
part of it and writes a replacement. ReDetail is that, over the whole frame — so
it belongs *after* the reel node, beside the face pass, not in the latent path
where phase 3's upscaler sits.

**What is genuinely new.** An H3 render would load a second family's weights:
the LTX transformer, both LTX VAEs and the IC-LoRA, alongside whatever rendered
the pass. `emit_loaders` is one call per render today and the links object is one
family's; this needs a second set, built only when the pass is asked for. Worth
noting that the text encoder is *not* among them — the graph runs on empty
prompts, so its conditioning is a constant, and the author ships it pre-computed
at 26 KB rather than making users download 15 GB to encode two empty strings.
Doing the same here would need somewhere to keep a cached conditioning tensor and
a story for invalidating it; loading the encoder is the honest first version.

**The two constraints, and why one is free.** Both output dimensions must divide
by **64**, not 32 — the IC-LoRA encodes its guide at half the target and dilates
it onto the target's latent grid, so the latent's own /32 is halved again.
Exactly 2× off a canvas already snapped to 32 always lands on it, which is why
the author's sizing table finds 2× clean and 1.5× often unreachable; a factor
other than 2 has to re-snap and admit it is not the number on the pill. The frame
count must be `8n+1` or the model silently drops the tail — free for an LTX piece
and *not* free for an H3 one, whose counts are `17n+5`, so the pass has to snap
and say what it dropped.

**Cost, from the author's measurements.** 243 frames from 768×1408: 1.5× took
7 minutes and peaked at 65 GB, 2× took 17 minutes and 80.5 GB. Smaller chunks and
the GGUF transformer bring that within a 24 GB card; the cached conditioning took
one reported run from 30.4 GB to 24.8 GB. None of this is measured on our own
box yet and none of it should be quoted in the UI until it is.

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

## Phase 3, as landed

**The compiler is family-parameterised, and H3 is byte-identical.**
`canvas.RULES` maps a family id to its `Rules`; `compile.rules_of(piece)` is
what every piece-level helper asks, and `compile_request` / `compile_segment`
take a `family=` defaulting to H3 because their `data` is one *request* and
carries no family of its own. Every `canvas.NATIVE_SHORT_EDGE`-style constant
inside those functions became a `rules.` read. The one thing that is not canvas
arithmetic is `registry.PROMPT_PIPELINE`: `"context-ir"` composes H3's documented
form, `"plain"` is `compile.plain_prompt` — the substituted body plus the two
sound fields, which is what an encoder trained on captions should be sent. Both
manifests serve that table's value, so a UI cannot describe a prompt the
compiler did not write. `tests/golden` is untouched.

**The family contract grew three hooks and lost an assumption.**
`weights_from_blob`, `resolve_sampling` and `run_context` are the three shapes
the node used to build itself: the weights block's *keys* are the family's, the
sampler row is not a superset across families, and the turbo lead-in is H3's.
`Family.rules` is the fourth thing, read by the loop rather than through a hook,
because the finished file is written at the rate the frame counts were snapped
to. And `emit_refine` now receives the segment node: a second stage that
*continues* the first needs its conditioning, where H3's re-encodes the request
at a larger canvas and ignores it.

**The sampler is core's LTX nodes, wired.** `LTXVScheduler` → `KSamplerSelect`
→ `ModelSamplingLTXV` → `LTXVDualCFGGuider` → `SamplerCustomAdvanced`, with the
scheduler and the patch handed the same latent and the same shift pair — they
are two readings of one curve. Defaults are the distilled checkpoint's: 8 steps
at cfg 1/1.

**`MiniMaxLTX25Segment`** is the family's boundary and a genuinely new node id.
Its fourth output is a real negative rather than H3's held-back lead model,
because `LTXVDualCFGGuider`'s uncond pass always runs and every LTX guide node
takes both conditionings and returns both. Lightricks' own
`DEFAULT_NEGATIVE_PROMPT` is the row's default. The order the latent is built in
is load-bearing: guides go on the *video* latent and the audio stream is
concatenated after, because `LTXVAddGuide.append_keyframe` refuses a combined AV
latent outright.

**Guides are cropped exactly once, and never on the packed latent.**
`LTXVCropGuides` slices frames in time and the soundtrack shares that axis, so
the pass is unpacked, cropped and packed again — at the end of `emit_sampler` on
a one-stage render, and at the *start* of `emit_refine` on a two-stage one, so
the upscaler is never spent on frames that are about to be thrown away.

**`refine` is Lightricks' second stage, brought forward from phase 4.** Sample
at the native edge, run the trained x2 latent upscaler on the video latent,
sample again over a tail of the schedule (`SplitSigmasDenoise`). The factor is
the model's, so `LTX25.compile` overrides the compiler's slider-derived refine
target with exactly twice the first pass, and the resolution pill's copy reads
the capability rather than asserting H3's meaning. The upscaler loader is built
lazily, on the first `emit_refine`, because it is a pass and not a component.

**The controls ask the piece.** The weights popover, the sampler row, the LoRA
manager, the resolution and aspect pills and the mode badge all take the
family off the piece; `test_family_select.py` greps the five files for the
default-bound constants and drives the family-taking helpers against both the
probe catalog and LTX. A family that ships one transformer draws no route row,
no per-LoRA checkpoint control and no mode→checkpoint arrow. A family the
frontend has never seen gets its sampler row rendered from its declared
widgets (`declaredRow`); H3's stays handwritten, because its copy is about its
own checkpoints and that is worth more than uniformity.

**The bug a real machine found immediately.** `models.available()` walked H3's
folder table, so the listing the popover browses had no `dit`, `upscaler` or
`duration_head` in it and three correctly-placed files came up as "not set".
`models.every_slot()` merges every family's table; `tests/test_ltx25_graph.py`
holds it.

**References are allowed rather than refused.** They ride as their `<Picture N>`
labels in the prose and are encoded from nothing, and the segment node logs one
line saying so — a guide is a keyframe, and pinning a character sheet at frame 0
is not what citing a reference means. Sound seams reach the node and are not
conditioned on yet. Both are the open question below, not an oversight.

## Phase 4: the seams, as landed

The claim was that core's reel layer is family-neutral by construction and
needed only proving. It is — every node from `MiniMaxH3Reel` to the save is
byte-identical between `chained_seam` and the new `ltx_chained_seam` golden,
and the two files side by side are what that is worth reading in. What was
*not* neutral was one number in front of it.

**`FEATHER_GRID` was H3's, and silently wrong on LTX.** A feathered seam hands
the pass in front's last run over as a multi-frame guide, and the widths H3
offers — 1, 5, 22, 39 — are the counts its video VAE encodes standalone.
`LTXVAddGuide` crops a guide to the nearest 8n+1 *without saying so*, so H3's
5-frame blend reached the model as a single frame while the reel went on
trimming five off the head of the pass: four frames of drift, a join that is
not a join, and nothing in the log. 22 became 17 and 39 became 33 the same way.

The fix is that the set is derived rather than written: `canvas.feather_grid`
is `(1,) + the first three legal frame counts`, which is H3's tuple exactly —
the seam grid and the frame grid answer to the same VAE cycle, and having them
be one derivation is what makes a family unable to get this wrong. LTX's is
(1, 9, 17, 25). `_check_feather` takes the rules; the picker's Short/Medium/Long
now names a *position* in the grid rather than a frame count, because 22 was a
key in a lookup table that answered "Blend" for every LTX width.

**And the strip's arithmetic asked H3 about an LTX piece.** Chasing the grid
through the frontend turned up the rest of the same cluster, all of it phase 3
work that only a second family with a different frame rate and grid could
surface: `timelineFrames`, `sampledFrames`, `addSegmentRefusal`, `resolved`,
the pass and card readouts in `timeline.js`, and the card-length reads in
`editor.js` all snapped to H3's grid and divided by H3's rate. They take the
piece now. `setFamily` retargets a seam's width to the nearest the new family
can encode — the same courtesy a LoRA already got — and `syncCanvas` drops
what is still off the grid.

The proof is `tests/test_passes_mirror.py` run over **both** families with the
widths written as grid positions, `canvas.js`'s `featherGrid` mirrored per
family in `test_canvas_mirror.py`, the chained-strip section of
`test_ltx25_graph.py` (which pins the trim, the sound tail's span and the
refusal of a width off the grid), and `S.FEATHER_GRID` joining the grep in
`test_family_select.py`. `tests/golden` gained two files and changed none.

## Phase 4: auto duration, as landed

**The plan was wrong about where this runs, and `Links`' docstring said so out
loud.** It called the duration head "a question the seconds pill asks before a
queue", which would have made it a route. It cannot be: `LTXVDurationPredictor`
runs the transformer's own caption connectors over the *encoded* prompt, so it
needs the loaded 22B DiT and the 12B encoder — the two most expensive things a
render does, asked while somebody is typing. There is no cheap route.

So auto is resolved **inside the segment node**, which already has the model,
the clip and the latent it builds in Python. `compile_request` still works the
pill's number out and `Compiled.frames` still carries it: it is what the strip's
bar counts, what `MAX_TIMELINE_FRAMES` is checked against, and what the card
falls back to when auto goes off. It is now an *estimate*, and that is said
three times rather than hidden — `Compiled.auto_duration` flags it, the pill
draws `~5 s` dimmed, and the strip's totals wear the same `~` with a tooltip.

**The clamp is the seams'.** The head's own range is Lightricks' 1–20 s; what
is passed is that range with the floor raised to `2 × the segment's blends`,
because a pass shorter than twice its overlap delivers less than it re-made.
`compile_request` refuses exactly that for a length the user set, and this is
the same rule said to the model as a bound instead of to the user as an error.

**It is a capability, not an id.** `registry.DURATION_HEAD` maps a family to
the slot that answers — `None` for H3, and the manifest's `duration` capability
reads that table rather than spelling the slot again. `compile_request` reads a
card's `auto_duration` through it, so the flag on an H3 piece is the "no" it
is; `syncCanvas` and `setFamily` clear it rather than retargeting, because
there is no nearest answer to "let the model choose". The pill's switch appears
only where `canDo(piece, "duration")`, and `matchTail` stands down while it is
on — "matches @vid-1" would be a claim about a frame count that does not exist.

The head is loaded lazily and once, like the upscaler: a strip with three auto
cards builds one `ModelPatchLoader` and a strip with none builds no loader and
wires no input, so its graph is byte-identical to one built before any of this.
Asking for auto with the slot empty refuses by naming the pill to change.
`test_ltx25_graph.py` holds all of that; `test_family_select.py` holds the
capability gate and the round trip.

## Phase 4: multishot, weighed

The question was whether native multishot "competes with the strip's own
feathered seams rather than slotting under them". It does neither, because
**the pack already had the control and did not know it.**

### What multishot actually is (official sources only)

- **There is no node, no pipeline and no argument.** ComfyUI core's
  `comfy_extras/nodes_lt.py`, `nodes_lt_audio.py` and `comfy/ldm/lightricks/`
  contain no mention of it. `Lightricks/LTX-2` ships thirteen pipelines and
  none of them is a multishot pipeline; there is no `num_shots` anywhere in the
  repo. It is a property of the **caption**, and of nothing else.
- **The captions carry no markers.** `ltx-trainer`'s captioning instruction:
  "Narrate strictly in chronological order; if the video contains multiple
  shots, describe each one in turn. … Write everything as a single continuous
  paragraph of prose. Do not use section headers, bullet points, or labels like
  `Audio:` / `Visual:` / `Shot:`." The Gemma T2V system prompt says the same,
  and adds that the shot-type/camera-motion/viewpoint triple must be "woven
  naturally into the prose (never as tags or labels)".
- **The cut is named in the sentence.** The 2.5 prompting guide: "Name the
  transition in natural language — 'A hard cut transitions to…', 'The view cuts
  to a close-up of…', 'A match cut connects…', 'The image dissolves into…'."
  Each cut must also re-establish shot scale, angle, who is in frame and
  lighting; identity is held by reusing the same visual identifiers; and audio
  continuity must be **stated** ("the piano score continues across the cut").
- **Two to four shots per generation**, "more cuts usually need clearer,
  shorter beats per shot". And a warning worth repeating: for image-to-video
  from a first frame, "prefer a single continuous take unless you intentionally
  describe a cut away from that opening image."

### So it does not compete with the seams — it is the other pill

A strip already renders two ways, and they are exactly the two things being
compared. `render: "chained"` is one generation per card joined by feathered
seams — real frames inherited across the cut, identity carried by pixels.
`render: "single"`, and any `merge` run inside a chain, is **one generation
whose description holds several shots** — which is native multishot, under a
name this pack chose before the model had one. Nothing needed building; the
choice between them is already a control the user has, and it is now a real
choice on this family rather than one of two spellings of the same thing.

### What it did find

`group_payload` called `contextir.shot_body` for **every** family, so a merged
LTX pass reached Gemma as

    [Shot 1] A wide shot frames … [Shot 2] At 00:05.000, A hard cut …

— H3's Context-IR markup, sent to an encoder whose training captions are
defined by never containing it, sitting precisely where the cut is supposed to
be described. Same class of bug as the feather grid, and found the same way.

The join is the family's now, off `registry.PROMPT_PIPELINE` — the same table
`plain_prompt` is chosen by, so a family cannot compose a body one way and be
described the other. `compile.plain_shot_body` runs the shots together in play
order as one paragraph, inserting a full stop where one is missing, and
inventing **nothing**: no timestamp (the model has no cut-time grammar), no
transition verb (whose cut it is belongs to the description the user wrote),
and no stripping of `[Shot n]` markers a user typed themselves, which is
`plain_prompt`'s standing rule about not editing prose on a guess.

The 2–4 advice is a manifest capability with a *value* rather than a boolean —
`multishot: {advised_max: 4}` — and the pass casing wears the same
off-distribution mark for too many cuts that it already wears for a duration
outside the trained range. H3 declares no number, because nothing in its guide
gives one, and so is never marked. Advice, so nothing is refused.

**Not done, and deliberately.** Nothing rewrites a user's shots into named
transitions, re-established framing or stated audio continuity. That is the
prompt refiner's job, not the compiler's — the compiler assembles what was
written and does not author it — and teaching the refiner LTX's multi-shot
form is a natural piece of the reference-grammar work below, where its prompt
templates are being split from H3's anyway.

## Open questions (answer during phase 4)

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

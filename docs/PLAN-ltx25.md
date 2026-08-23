# LTX 2.5 — the second family

Branch: `ltx25`, cut from `multi-family` (phases 0–5 complete, rendered and
UI-tested on RunPod 2026-08-23). Not merged through `main`: this branch is
why the refactor exists, and it starts immediately on top of it.

## What core provides (verified against the running install)

All read from `~/ComfyUI-Installs/.../comfy_extras/nodes_lt.py` and
`nodes_lt_audio.py` — the design below binds to these, not to memory:

- **Text encoder**: `LTXAVTextEncoderLoader(text_encoder, ckpt_name)` — two
  files, from `text_encoders` and `checkpoints` (Gemma 3 12B), CLIP type
  `LTXV`. One loader, two picks: the slot table's "one file per slot" shape
  meets its first two-file loader here.
- **Audio VAE**: `LTXVAudioVAELoader` — picked from **`checkpoints`**, not
  `vae`, exactly as the multi-family plan warned.
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

1. **Family selection plumbing** (above). No new family yet; behaviour
   frozen by the existing suites.
2. **`families/ltx25/` skeleton**: registry row (`PRODUCES = {"video"}`),
   `models.py` slot table (dit via `UNETLoader`; `text_encoder` +
   `text_encoder_ckpt` as two slots feeding one loader — the emit half owns
   that join; `vae`; `audio_vae` from `checkpoints`; `duration_head`
   optional), `canvas` Rules instance (multiple 32, frames 8n+1, fps 25
   **fixed=False**), `manifest.py` serving it all. `test_families` grows the
   family; the frontend lists it and can select it — and refuses nothing,
   because compile refuses politely until phase 3 lands.
3. **The render half**: `render.py` — loaders, segment (prompt through
   Gemma as plain prose, guides via `LTXVAddGuide`, first/last frames on the
   8-grid), sampler subgraph, `ModelSamplingLTXV` patch, `LTXVConditioning`
   with the manifest's fps. Golden graphs for the LTX blobs: text-only,
   first-frame, guide-with-strength, audio on/off.
4. **Duration and the timeline**: the duration predictor as the seconds
   pill's "auto" (capability-gated — H3 simply lacks it), seam/feather
   verification on the 8-grid latent (the reel layer is family-neutral by
   core's own construction; prove it with a chained golden).
5. **Taste guidance**: STG / modality / reference-audio as their own pills
   with honest cost copy — new UI, not the accel row.

## Open questions (answer during phase 2, not before)

- Which loader the LTX 2.5 DiT actually ships for (`UNETLoader` vs a
  dedicated loader) — read core's model detection when the weights are on
  disk.
- Whether `refine` has any meaning for a plain-prose family (probably: the
  same expansion, different template — the refine engine is already split
  from H3's templates).
- What the negative prompt is for LTX (H3 has none in the row; the guider
  wants one — possibly a fixed template string, possibly a control).

## Frozen, still

Everything the multi-family plan froze: the `MiniMaxH3*` node ids, the 13
sampler widget slots, `/minimax_creator/*` routes, `creator_data`
back-compat. LTX's segment node gets a **new** id — a genuinely new node.

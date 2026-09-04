# Plan: Latent-Mask Continuation (H3-Motion-Context-MultiRef style)

Status: **plan only — no code changes made yet.**

Goal: replace the current "blend" seam between generated segments with the
latent-masking continuation used by
`ComfyUI-H3-Motion-Context-MultiRef`, so that segment A → segment B joins are
seamless (no visible cut/jump), matching the quality of the `NEW - AV Extension`
workflow.

---

## 1. Why the current blend shows a cut

### How Continuity does it today (keyframe conditioning)

Each segment is generated into a **fresh** `_empty_av_latent`
(`creator/families/h3/encode.py:447`). Continuation between segments is done by
*conditioning*, not by carrying content over:

- **Video:** the previous pass's last `feather` frames are read back off the
  spill (decoded, 8-bit), resized, VAE-encoded, and pinned as
  `minimax_keyframes` at frame 0 of the new segment
  (`encode.py:_context_keyframes`, `_encode_frames`). The model is *asked to
  imitate* that motion.
- **Audio:** the previous pass's audio tail is encoded as a `ref_audio` block
  (imitation) or pinned end-aligned on this segment's timeline
  (`encode.py:_seam_blocks`).
- The new segment **re-generates** the overlap region, and `MiniMaxH3Reel`
  trims the head/tail blended frames off before writing to disk
  (`creator/timeline.py:MiniMaxH3Reel.execute`, `head`/`tail` inputs).

So a join is `[seg A …] + [seg B's re-generated overlap, trimmed]`. The overlap
is **regenerated from a soft hint**, not carried over. The DiT is free to drift
in pose, framing, lighting and phase across the boundary → the visible cut.

### How H3-Motion-Context-MultiRef does it (latent masking)

`MiniMaxH3GeneratedAVMaskedContext`
(`existing_video_extension.py:586`) takes the **previous generated H3 latent**
and copies its final valid AV latent run (video + audio) *directly* into the new
target's prefix, then sets a per-stream `noise_mask`:

```
VIDEO: [ protected previous context ][ generate future ... ]
MASK:  [ 0 0 0 0 ...               ][ 1 1 1 1 ...      ]
AUDIO: [ protected AV prefix        ][ future          ]
MASK:  [ 0 (feathered release)      ][ 1               ]
```

- `0` = preserve / do not denoise this token; `1` = generate.
- The boundary is literally the previous clip's **own latent pixels/samples**,
  so there is no regeneration of the overlap and no drift → seamless join.
- Only the *future* region denoises.

### The core difference in one line

| | Continuity (today) | MultiRef (target) |
|---|---|---|
| What crosses the seam | decoded frames + audio, re-encoded as a **hint** | the previous clip's **actual latent**, protected by a mask |
| Overlap region | **regenerated** (can drift) | **preserved verbatim** (cannot drift) |
| Continuity guarantee | soft conditioning | hard pixel/sample identity at the boundary |

---

## 2. The architectural gap that must be closed

Continuity does **not retain a pass's latent**. `MiniMaxH3Reel` decodes each
pass to disk immediately and only a *path + frame count* travels the wire
(`creator/timeline.py`, `creator/core/emit.py:inherited_frames`). The next
segment inherits **decoded frames** (`MiniMaxH3PassFrames`) and **decoded audio**
(`MiniMaxH3PassAudio`), which are re-encoded as keyframes/references.

Latent masking requires the previous pass's **AV latent tail** to be available
to copy into the next target prefix. That is the single structural change this
plan hinges on — and, per the follow-up requirement, that latent must not be a
throwaway graph value: it has to be a **managed artifact with the same
lifecycle as a take**, so that a *locked* clip's latent is picked up by
reference exactly the way its video already is — saved once, re-loaded from
disk for as long as the take exists, never regenerated. See §3.5.

None of the mechanics are reimplemented here, either. `ComfyUI-H3-Motion-
Context-MultiRef` (<https://github.com/seitanism/ComfyUI-H3-Motion-Context-
MultiRef>) already ships the nodes this needs — the splice+mask math (from a
stored latent, or freshly VAE-encoded when there isn't one), a save, and a
load — and they are wired in exactly the way `creator/accel.py` wires in
Spectrum, sparse attention and memory optimization: looked up in
`nodes.NODE_CLASS_MAPPINGS`, called with arguments read off their own
`INPUT_TYPES`, and refused with the pack's own name and URL when it is not
installed. `creator/families/h3/encode.py` never learns the splice/mask/on-disk
format; it only learns that a fresh empty latent can be handed to something
else before it reaches the sampler.

### Feasibility (already in place)

- Continuity already uses `noise_mask` on H3 AV latents:
  `creator/audiolatent.py:apply_av`, `creator/families/h3/facepass.py`,
  `creator/families/h3/hires.py`. The nested `(video_mask, audio_mask)` packing
  is understood and tested.
- The main sampler path forwards the latent's mask automatically:
  `KSampler` / `KSamplerAdvanced` read `latent.get("noise_mask")`
  (`creator/families/h3/render.py:emit_sampler`, `denoise=1.0`). No sampler
  change needed for the mask to take effect.
- The segment node already outputs a fresh AV latent
  (`encode.py:_empty_av_latent`) — the natural place to splice in the protected
  prefix and attach the mask.

### Constraints inherited from MultiRef (must be respected)

1. **Same geometry across chained clips** — source/target video latent
   `[C,H,W]` and audio latent `[C,2]` shapes must match. Continuity already pins
   one canvas across every segment (`compile.py`), so this holds by construction;
   keep it that way.
2. **Context snapped to shared boundaries** — the protected prefix must be both
   a valid H3 video-VAE run and an exact 40 Hz audio-latent boundary:
   `39, 90, 141, 192, …` frames (`FRAME_PER_TOKEN = (1,4,4,4,4)`, 24 fps video,
   40 Hz audio). MultiRef snaps the requested length *down* to the largest shared
   boundary that fits. Continuity's `feather` is currently an arbitrary frame
   count; it must be snapped for the masked path.
3. **Batch size 1** — the masked continuation supports target/source batch 1.
4. **Prefix < whole target** — the protected run must not consume the entire
   target latent.

---

## 3. Proposed design

Add a **seam mode** to each blended seam: `blend` (current, keyframe) vs
`mask` (new, latent-masking). Default stays `blend` so existing renders are
unchanged; the user opts into `mask` per seam (or via a piece-level default).

### 3.1 The four external nodes this reuses

All four from `ComfyUI-H3-Motion-Context-MultiRef`, looked up the way
`accel.py`'s `_require` looks up Spectrum/sparse/memory — raise with the pack's
name and <https://github.com/seitanism/ComfyUI-H3-Motion-Context-MultiRef>
when it is not installed, never a silent fallback:

- **`MiniMaxH3GeneratedAVMaskedContext`** — `prepare(latent, source_latent,
  context_length=39, audio_feather_ticks=8) -> (latent, trim_frames)`. Does
  everything §1 described: snaps the context length to a shared 24 fps
  video / 40 Hz audio boundary, computes `video_steps`/`audio_steps`, copies
  `source_latent`'s tail into `latent`'s prefix, and returns the same latent
  with a nested `noise_mask` already attached — `0` over the protected prefix,
  a half-cosine release over the last `audio_feather_ticks` of it. `trim_frames`
  is the exact pixel-frame count that duplicates the previous pass; it is not
  recomputed anywhere in Continuity — see §3.3.
- **`MiniMaxH3MotionContextSaveLatent`** — `save(latent, filename_prefix,
  clip_index=0) -> latent_path`. Writes the AV latent's video+audio streams to
  one safetensors file under ComfyUI's output directory. `clip_index > 0` is a
  fixed slot (`*_00002.safetensors`), overwritten by a re-roll rather than
  accumulating — the same rule a take's own file already follows.
- **`MiniMaxH3MotionContextLoadLatent`** — `load(latent_path, clip_index=0) ->
  latent`. Reads it back as a plain `{"samples": [video, audio]}` — not a
  `NestedTensor`, but `_streams_from_latent` (used by both the mask node and
  the save node) accepts either, so this composes directly with
  `MiniMaxH3GeneratedAVMaskedContext`'s `source_latent` input. Pointing
  `latent_path` at a specific *file* (rather than a folder) makes `clip_index`
  inert, which is the mode Continuity uses throughout — see §3.5.
- **`MiniMaxH3ExistingVideoMaskedContext`** — `prepare(latent, vae, audio_vae,
  source_frames, source_audio, source_fps, context_length=39, crop="disabled",
  audio_feather_ticks=8) -> (latent, trim_frames)`. The fallback for a source
  with **no saved latent at all**: instead of copying an existing latent tail,
  it VAE-encodes the tail of `source_frames`/`source_audio` itself, on the same
  snapped-boundary and masking terms as `MiniMaxH3GeneratedAVMaskedContext`.
  This is what makes "my own random clip from disk as segment 1" and "an old
  take saved before this feature shipped" both continuable in `mask` mode
  without a full regeneration — see §3.2 and §3.5 point 6.

### 3.2 Splice + mask, wired between the segment and the sampler

In `creator/core/emit.py`, when a seam's `seam_mode == "mask"`, the source
resolves to one of two shapes — the same two shapes `is_clip_source` already
distinguishes everywhere else in this loop — and each takes a different node:

- **A generated pass with a saved latent** (this render's own Save output, or
  `take.get("latent")` on a held/kept card spliced in as a clip — §3.5): load
  it with `MiniMaxH3MotionContextLoadLatent` and splice with
  `MiniMaxH3GeneratedAVMaskedContext`. No VAE call, no re-encode — the fast
  path, and the common one, since every pass saves its latent unconditionally.
- **A source with no usable latent** — genuine supplied footage that was never
  an H3 pass, or a take whose saved latent is missing (deleted, or predates
  this feature): fall back to `MiniMaxH3ExistingVideoMaskedContext`, fed by
  `inherited_frames`/`inherited_audio`'s own `CLIP_FRAMES_NODE`/
  `CLIP_AUDIO_NODE` calls — the exact nodes blend mode already reads a clip's
  window through. `source_fps` is always `media.TARGET_FPS` (24.0): every clip
  window Continuity decodes is already resampled to it (`media.load_video`),
  whatever the source file's native rate — so no per-clip fps has to be
  threaded through. This re-encodes the seam's window (cheap: one VAE call on
  a handful of frames) rather than regenerating the sampling (expensive: the
  whole pass) — see §3.5 point 6.

Either way:

- The segment node still returns a **fresh** empty AV latent from
  `encode.py:_empty_av_latent`, exactly as today — nothing in `encode.py`
  changes for a masked seam. `_context_keyframes` (the head conditioning) is
  simply not built for it, the same way a hard cut already builds no seam
  inputs at all.
- Between that segment node and `family.emit_sampler`, one more link is
  spliced in — the same shape as the ControlNet guide splice `emit.py` already
  does "after the segment and before the sampler": whichever of the two mask
  nodes above applies. What reaches `emit_sampler` is the spliced, masked
  latent instead of the empty one.
- The existing `KSampler`/`KSamplerAdvanced` path denoises it unchanged — mask
  forwarding already works (§2 feasibility) — so nothing downstream of the
  sampler needs to know a seam was masked at all, except the trim.

### 3.3 Trim accounting

- Today `MiniMaxH3Reel` trims `head = one.feather` frames off a blended pass
  because the overlap was regenerated and would otherwise play twice.
- For a masked seam, **either** mask node's own `trim_frames` output *is* that
  count — the exact number of frames its target's prefix duplicates from the
  source, whether that prefix came from a loaded latent or a live encode.
  `emit.py` passes it straight into the follower's own `MiniMaxH3Reel` call as
  `head`, in place of `one.feather`. Nothing in `timeline.py` changes:
  `MiniMaxH3Reel` already turns a frame count into a sample count off `fps`,
  whatever produced the frame count.
- The *previous* pass is untouched either way — its own `MiniMaxH3Reel` call
  trims its own `tail`/nothing exactly as it does today; only the follower's
  `head` source changes from `one.feather` to the mask node's `trim_frames`.

### 3.4 UI / blob plumbing (follow existing patterns)

- **Backend:** add `seam_mode` (`"blend"` | `"mask"`, default `"blend"`) to the
  segment request; thread it onto `Compiled` in `compile.py` next to `feather`,
  and read it in `emit.py` where seams are wired (§3.2) — nothing changes in
  `families/h3/segment.py` or `encode.py` for this, since the splice happens
  between the segment node and the sampler, in `emit.py`, not inside the
  segment's own conditioning.
- **Frontend:** the seam control lives in the timeline UI. Add a per-seam toggle
  (`blend` / `mask`) next to the existing blend-width control, gated on H3 family
  + `continues`. Mirror it into the blob exactly like other seam fields.
- Keep `blend` as the default; `mask` is opt-in.

### 3.5 The latent tail as a managed artifact — follows the take, not the spill

This is the follow-up requirement: locking a card and coming back later must be
able to reuse its latent the same way it already reuses its video, with no
regeneration. There is **no new temp/spill tier** for this — `Motion Context
Save Latent` already writes straight to a permanent file the first time, so
there is nothing to promote later. The latent is a field of the take, not a
sibling artifact with its own lifecycle:

1. **Every generated H3 pass saves its latent, unconditionally.** The same way
   `MiniMaxH3Reel` spills every pass's frames and audio regardless of whether a
   future seam will ever read them back, `emit.py` wires
   `MiniMaxH3MotionContextSaveLatent` onto every pass's sampled latent — not
   only the ones immediately followed by a masked seam. This is what makes
   "lock a take today, add a masked continuation from it next week" work: the
   latent is already on disk from the run that produced the take, whether or
   not masking was in use that day.

2. **Keyed exactly like a take, not like a new numbering scheme.**
   `clip_index` is the card's own `card_no` — the same 1-based number
   `_reported`/`take_spec` already key takes on — and `filename_prefix` is a
   piece-scoped folder sibling to the video output. A re-roll of card N
   overwrites slot N, on the same terms a retake overwrites its own `.mp4`; no
   rejects accumulate.

3. **Reported and mirrored exactly like `filename`.** The Save node's own
   `latent_path` output is folded into the per-card report next to `filename`:
   `timeline.py:_reported` gains a `latent` key, and `state.js:takeFrom` mirrors
   it onto `segment.take.latent`. Nothing else in `state.js` changes —
   `takeOn`, `isKept`, `editedSince` and the delete-drops-the-take path already
   operate on the whole `take` dict, so `latent` inherits every one of those
   rules for free the instant it is a key in it.

4. **One load path for a live pass and an old take alike — and a fallback for
   everything else.** A masked seam's source resolves to a concrete latent
   path when one exists — either the Save node's output for a pass generated
   *in this render*, or `take_of(source)["latent"]` for a card that is
   held/kept and spliced in as a clip (`compile.take_spec`, which already
   turns a held card's take into a clip spec the rest of the module reads
   uniformly — it gains a `"latent"` key on the same terms as `"filename"`).
   Either way the follower wires
   `MiniMaxH3MotionContextLoadLatent(latent_path=<that path>, clip_index=0)` —
   naming a *file*, not a folder, so `clip_index` is inert and no slot is
   re-derived from a filename convention. **When no path exists at all** —
   genuine supplied footage, or a take with no `"latent"` key — there is
   nothing to load, and `emit.py` builds `MiniMaxH3ExistingVideoMaskedContext`
   instead (§3.2), deriving the same prefix from the clip's own pixels. Either
   node ends at the same shape: a spliced, masked latent and a `trim_frames`
   count.

5. **Round-tripped through disk even within the same render.** The previous
   pass's sampled latent is *not* kept as a live graph link into the next
   segment's masked splice, even when both are generated in the same render.
   `MiniMaxH3Reel`'s own docstring already gives the reason: ComfyUI keeps
   every node's output alive for the whole execution, and a live latent link
   held across a multi-segment chain is one more large tensor added to that
   total for the length of the render. A save + a load costs one small file;
   not doing it costs a resident AV latent per in-flight masked seam, for
   however long the chain is. It also means a masked seam behaves identically
   whether its source is this render's own pass or a locked take from last
   week — one code path, not two.

6. **No saved latent is never a dead end.** Genuine supplied footage never had
   one; an old take saved before this shipped, or a save that was
   hand-deleted, no longer has one either. None of these force a regenerate —
   `emit.py` treats "no `latent` on this source" as the signal to use
   `MiniMaxH3ExistingVideoMaskedContext` instead of
   `MiniMaxH3MotionContextLoadLatent` (§3.2), encoding the seam's window fresh
   from the clip's own pixels. What is never regenerated is the *sampling* —
   only a small VAE encode is repeated, on a handful of frames, which is the
   whole point of "seamlessly integrated": a random clip dragged onto segment 1
   works in `mask` mode exactly like a locked take does, on the first try, with
   nothing to pre-generate.

7. **Output-dir growth is the one real cost, and it already exists.** A
   `.safetensors` per kept card, permanent, next to its `.mp4` — the same
   growth §6 already notes for takes, now with one more small file per card.
   If it ever needs bounding, bound it the way takes would be bounded, not
   with a fourth policy.

---

## 4. What does NOT change

- The sampler (`render.py`) — mask is already forwarded via the latent dict.
- The canvas/geometry pinning — already one canvas per piece.
- Unblended seams, REF2VA segments, supplied-clip seams, LTX 2.5 family — all
  untouched (this is H3-only to start).
- The spill/disk model for *frames* and *audio* — unchanged, and untouched by
  this plan: the latent artifact does not ride the spill at all. It goes
  straight to the same permanent home a take's `.mp4` already lives in
  (§3.5), because that is what `MiniMaxH3MotionContextSaveLatent` already
  does — there is no intermediate temp tier to add.
- `encode.py` and `families/h3/segment.py` — a masked seam is entirely wired
  in `emit.py`, between the segment node and the sampler. Neither file gains a
  new input or a new code path.
- `MiniMaxH3ClipFrames`/`MiniMaxH3ClipAudio` and `inherited_frames`/
  `inherited_audio` — unchanged and reused as-is. The live-encode fallback
  (§3.2, §3.5 point 6) reads a clip's window through the exact same two nodes
  blend mode already calls; it does not add a third way to decode a clip.

---

## 5. Implementation steps (ordered)

1. **A small `_require`/`SOURCES` table for the four MultiRef nodes**
   (`MiniMaxH3GeneratedAVMaskedContext`, `MiniMaxH3ExistingVideoMaskedContext`,
   `MiniMaxH3MotionContextSaveLatent`, `MiniMaxH3MotionContextLoadLatent`),
   mirroring `accel.py`'s own — same lookup-by-`nodes.NODE_CLASS_MAPPINGS`,
   same "missing pack" error naming
   <https://github.com/seitanism/ComfyUI-H3-Motion-Context-MultiRef>. A small
   new module (e.g. `creator/families/h3/maskseam.py`) rather than adding a
   fourth idea to `accel.py`, which is about model patchers and this is not one.
2. **`compile.py`:** `seam_mode` on the segment shape, threaded onto `Compiled`
   next to `feather` (default `"blend"`); `take_spec` gains `"latent":
   take.get("latent")` so a spliced held/kept card carries its saved latent
   path forward the same way it carries `"filename"` — absent when the pass
   that produced it predates this feature.
3. **`timeline.py`:** `_reported` gains a `latent` key holding the Save node's
   `latent_path` output for that card's pass.
4. **`state.js`:** `takeFrom` mirrors `latent` onto the take dict — one line,
   next to where it already mirrors `duration_s`/`has_audio`.
5. **`emit.py`:** for every H3 AV pass, wire `MiniMaxH3MotionContextSaveLatent`
   (`clip_index=cards[index]`, one piece-scoped `filename_prefix`) onto the
   sampled latent, unconditionally — mirroring how every pass is already
   spilled regardless of whether a seam will use it. When building a segment
   whose incoming seam has `seam_mode == "mask"`: if the source has a latent
   path (this render's own Save output, or `source[1]["latent"]` off a
   spliced take), wire `MiniMaxH3MotionContextLoadLatent` then
   `MiniMaxH3GeneratedAVMaskedContext`; otherwise (supplied footage, or a take
   with no saved latent) wire `inherited_frames`/`inherited_audio`'s
   `CLIP_FRAMES_NODE`/`CLIP_AUDIO_NODE` calls into
   `MiniMaxH3ExistingVideoMaskedContext` with `source_fps=media.TARGET_FPS`
   instead. Either way: splice the result between the segment node and
   `family.emit_sampler`, skip building `seams["prev_image"]` for that seam,
   and pass the mask node's `trim_frames` output as this segment's own
   `MiniMaxH3Reel` `head` instead of `one.feather`.
6. **Blob/UI:** `seam_mode` (+ optional `audio_feather_ticks`) per seam,
   H3-gated, default `blend`.
7. **Tests:** fakes for all four nodes in the harness (same shape as
   `tests/test_accel.py`'s fakes); assert `_reported`/`take_spec` carry
   `latent`; assert a masked seam's graph wires Load → Mask → sampler with
   `trim_frames` feeding the follower's `head` when a latent exists; assert it
   wires the clip-window nodes → `MiniMaxH3ExistingVideoMaskedContext` instead
   when the source is supplied footage *or* a take with no `latent` key;
   assert a held+kept card with a latent skips the live-encode path; assert a
   missing-pack render raises naming the repo URL; assert an unmasked graph is
   byte-identical to today — no Save/Load/Mask nodes at all when nothing on
   the piece uses `seam_mode="mask"`.

---

## 6. Risks / open questions

- **Hard dependency on an external, actively-changing pack.** Same tradeoff
  `accel.py` already accepts for Spectrum/sparse/memory: if the pack renames a
  node, an input or an output, this fails loudly with the pack's own name and
  URL (`_require`), never silently on a wrong argument. Worth pinning to a
  known-good commit/`SHA256SUMS.txt` entry before this ships, the same way any
  of the other four external packs would be.
- **Save cost.** One extra safetensors write per H3 pass, unconditionally —
  cheap next to the frame/audio spill it rides beside (a joint AV latent tail
  is single digits of MB; the decoded 8-bit frames are the large one), but
  worth a quick size check on a representative clip length.
- **Output-dir growth.** One `.safetensors` per card, permanent, next to its
  `.mp4` — the same growth a take already causes, now with one more small file.
  If it ever needs bounding, bound it the way takes would be, not with a new
  policy invented just for this.
- **Live-encode fallback cost and its own window cap.** Falling back to
  `MiniMaxH3ExistingVideoMaskedContext` costs one VAE encode of the clip's own
  window — cheap next to a regenerate, but not free, and worth confirming it
  is not silently chosen every time due to a bug that fails to find an
  existing `latent`. Its window comes from `MiniMaxH3ClipFrames`/
  `MiniMaxH3ClipAudio`, whose `count` is capped at 64 frames — the same cap
  blend mode's `feather` already lives under, so this does not shrink what was
  previously reachable, but a masked seam's usable context is bounded by it
  exactly as a blended one already is.
- **Boundary snapping shrinks the overlap:** a user-set `feather` of e.g. 30
  frames snaps down to the largest shared boundary ≤ 30 (which may be small). The
  UI should show the effective snapped width so it is not surprising.
- **Audio feather default:** MultiRef uses `audio_feather_ticks=8` (≈0.2 s at
  40 Hz) for a half-cosine release on the audio mask. Adopt as default; expose if
  users want a harder/softer audio join.
- **Tail (`ends_on`) seam:** this plan masks the *head* continuation first (the
  A→B case the user described). Masking the tail (running into a supplied clip)
  is a separate, later enhancement.

---

## 7. Suggested validation before committing to the full build

1. **Proof of concept (throwaway):** in a scratch graph, take two generated H3
   passes, run the previous pass's latent through MultiRef's
   `MiniMaxH3GeneratedAVMaskedContext` into the next target, sample, and eyeball
   the join. This confirms the *quality* win on this exact model/canvas before
   any Continuity plumbing is written.
2. **Boundary check:** confirm the snapped context lengths (39/90/141) produce
   integer audio steps on this build's H3 audio VAE (the 40 Hz assumption).
3. **Save/load round-trip:** save a pass's latent with
   `MiniMaxH3MotionContextSaveLatent`, restart ComfyUI, load it back with
   `MiniMaxH3MotionContextLoadLatent`, and confirm the mask node accepts it and
   produces a bit-identical splice to the in-session case — this is the exact
   "lock a take, come back later" path the whole persistence design rests on.

If step 1 does not visibly beat the current blend on your clips, the rest is not
worth building — so it is deliberately first.
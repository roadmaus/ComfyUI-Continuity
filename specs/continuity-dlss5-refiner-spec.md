# Continuity — DLSS 5 Neural Refiner

Spec for implementation. High level: architecture and decisions, not code.

## 1. Summary

Add NVIDIA's DLSS 5 Neural Rendering model to Continuity as a general-purpose
**refiner** — a material and detail synthesis pass applied to generated stills
and video frames. Available everywhere Continuity produces or handles an image.

Upstream: `iamwavecut/MLX-DLSS` (Apache-2.0). Provides a PyTorch backend
(`--device cuda|mps|cpu`) running the recovered network, plus Metal/MLX and
Core ML backends we do not need on the Linux/CUDA path.

**This is not an upscaler.** Upstream measured DLSS Super Resolution and
deliberately excluded it — without engine motion vectors it loses to Lanczos.
What we get is material response: skin, hair, fabric, contact shadows,
subsurface scattering. Resolution in equals resolution out.

## 2. Non-negotiables

- **We ship no weights and no NVIDIA binary.** The user supplies their own
  `nvngx_dlssnr.dll` (build 310.8.0.0, SHA-verified) and runs the upstream
  extraction tool locally. Continuity provides UI for pointing at the DLL and
  invoking extraction; it never hosts, mirrors or bundles the artifact.
- **The dependency is optional.** Continuity must install, load and run
  normally with the refiner absent. Missing weights degrade to a disabled
  control with an explanatory state, never an import error.
- **Upstream is vendored at a pin, not forked.** Four days old at time of
  writing. *Amended 2026-09-06:* the first build installed the port from a git
  URL; that was a second install step buying nothing, since the port's Python
  half is 400 KB of pure Python on dependencies ComfyUI already has. The
  inference path and the extraction modules are now copied into
  `creator/mlxdlss/` by `tools/vendor_mlxdlss.py` on the `h3lora` model —
  pinned commit stamped in, LICENSE and NOTICE beside, local edits held as a
  patch that fails loudly when upstream moves under it. Track upstream by
  re-syncing; do not edit the copy in place.

## 3. Integration surfaces

Four, sharing one backend session:

1. **PreStage (stills)** — refiner step after generation, before output.
2. **Video pipeline** — per-frame pass, using upstream's temporal session so
   history and noise seed advance coherently rather than treating each frame
   as independent.
3. **Upscale bench** — as a comparison entry alongside existing upscalers,
   with a clear label that it does not change resolution. It composes *with*
   an upscaler rather than replacing one; the bench should support running it
   as a post-upscale stage.
4. **Standalone node** — refine any IMAGE, for users assembling their own
   graphs.

All four resolve to one pipeline object. Model load is expensive; hold it
across invocations and free it under the same policy as our other models.

## 4. Controls to expose

Upstream's parameter set maps cleanly onto our existing control vocabulary:
profile (style preset), processing scale, detail strength, colour strength,
intensity, and a per-pixel control mask where the channels drive blend, tone
and structure independently.

The mask is the one worth designing around rather than merely passing through.
It accepts a per-pixel map, which means our planned segmentation and masking
work can drive refinement strength regionally — full strength on faces and
fabric, suppressed on backgrounds and flat areas. Treat mask input as a
first-class socket, not an advanced option.

Defaults matter more than range here, consistent with the pack's stated
posture: working defaults over exposed knobs.

## 5. Resource behaviour

Memory scales with network input area — roughly 1 GB per megapixel at float32,
halved in fast precision. Processing scale multiplies this by its square.

Consequences for the UI: processing scale is the setting most likely to OOM a
user, and its cost is non-obvious. Surface an estimate before execution rather
than failing mid-batch. On video, memory is per-frame, so batch size is the
second lever.

## 6. Seam refinement (investigate, do not assume)

**Hypothesis.** Refine the tail frame of segment N and pass the refined result
as the conditioning frame for segment N+1, so each segment anchors on a cleaner
image and cross-segment drift is reduced.

**Problem with the naive form.** Refining only the seam frame introduces a
discontinuity *inside* segment N. The refined anchor no longer matches the
unrefined frames preceding it, so we trade a seam between segments for a jump
before it. Likely worse, not better.

**The form worth testing instead.** Apply the refiner uniformly across all
frames as a post-pass with temporal history enabled, then take the seam from
the refined stream. Every frame is in the same domain, the anchor is
consistent with its neighbours, and the seam benefit comes free rather than
being bought with a local artefact.

**Open questions for the experiment:**

- Does refinement actually reduce drift, or does it just make both sides of the
  seam look better while the seam itself is unchanged? Measure, don't eyeball.
- Deterministic noise seeding is available and should be pinned per frame index
  during the test so runs are comparable.
- Cost: a full-sequence refine pass on every segment is expensive. If the
  benefit is real but small, this may not survive the runtime budget.

Gate this behind the general refiner landing first. It is a hypothesis with a
plausible failure mode, not a planned feature.

## 7. Risks

- **Upstream maturity.** Days old, single author, accuracy figures are
  self-reported. Verify output against our own material before shipping, and
  do not present the numbers as ours.
- **Legal posture of the source binary.** The DLL is a leaked pre-release
  NVIDIA artifact. Our code is clean and our position is defensible only as
  long as we ship nothing of NVIDIA's and make the user's role explicit.
  Documentation should state this plainly rather than bury it.
- **Bias of the model.** Trained on game frames with heavy supervision on skin,
  hair and fabric. Expect strong results on figurative work and weak or odd
  results on abstract, graphic or flat material. Set expectations in the UI
  copy.
- **Support load.** DLL sourcing will generate a support tail we cannot fix,
  on a solo-maintained pack. Consider whether the diagnostic surface (SHA
  check, extraction status, clear failure states) is good enough to answer most
  of it without us.

## 8. Out of scope for v1

- Frame generation. Upstream ships it and it reproduces the library closely,
  but it is a separate capability with its own UI implications and belongs in
  its own pass.
- Super Resolution. Excluded upstream for good reason; do not revisit.
- Non-CUDA backends. Metal and Core ML exist upstream; we do not need them.

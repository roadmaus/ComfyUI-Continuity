"""The face pass: crop the face out of a finished pass, re-draw it, put it back.

`faces.py` decides where the face is and how big to crop it; this is the half
that holds the weights and the pixels.

**Why this exists.** H3 draws a face badly in proportion to how small the head
is *in frame*. That is not a resolution problem — it is there at 768 and above —
so the two-pass refine in `hires.py` cannot reach it: upscaling re-resolves what
was drawn, and what was drawn was a smudge. What does reach it is asking the
model the same question with the face filling the canvas. At a low denoise the
answer stays frame-aligned with what is already there, so it composites back
rather than replacing the shot.

**Why it runs after the reel and not before it.** A pass is decoded, trimmed and
written to disk in one node so that no decoded pass is ever held across a node
boundary (`timeline.MiniMaxH3Reel`). This node keeps that promise: it reads the
finished pass back through `spill.open_frames`' memmap, holds the crops — which
are small — and streams the repaired frames straight back out to a new spill. It
replaces the pass on the reel and hands the new one back, so a later seam
inherits the repaired frames rather than the ones the face was wrong in.

**Three things ride through untouched.**

- *The soundtrack.* It is not re-decoded and not re-derived: the rewritten pass
  points at the same audio file (`spill.rewrite`). The audio half of the latent
  is still handed to the model — the mouth is drawn by attending to it — but it
  is masked out of the denoise, so what the model does with it is read it.
- *The frames outside the face box.* The crop is deliberately wider than the
  paste. The extra is context for the sampler; what is composited is the face
  rectangle, dilated and blurred. A tight silhouette would put the seam on the
  face's own outline, where any drift shows; a looser rectangle puts it in hair
  and background, where it does not.
- *Frames where the detector found nothing.* They keep their pixels. The crop is
  interpolated across a blink so the window does not jump, but nothing is
  pasted from a frame where there was no face to repair.

**The denoise mask is core's own.** `comfy/samplers.py` unbinds a nested
`denoise_mask` per latent stream and packs it alongside the latent, so one mask
says both "hold the audio exactly" (zeros) and "work harder on the frames where
the face is smallest" (`faces.strengths`) — in one sampling pass.
"""

import gc
import logging

import numpy as np
import torch
import torch.nn.functional as F

import comfy.model_management
import comfy.nested_tensor
import comfy.sample
import comfy.samplers
import comfy.sd
import comfy.utils
import folder_paths
import latent_preview
from comfy_api.latest import io

from ... import canvas, spill
from . import faces
from ...timeline import PASS_TYPE, REEL_TYPE

# What the detector is asked for. SAM3 is open-vocabulary, so this is a prompt
# and not a class id — and it is the whole of what this pack needs from it.
DETECT_PROMPT = "face"

# Detection confidence. SAM3's own node defaults to 0.5; this sits lower because
# a small, blurred face is exactly the low-confidence case this feature is for,
# and a missed detection here costs a frame of repair while a loose one costs a
# crop that `faces.pick` will drop again the moment it stops overlapping.
DETECT_THRESHOLD = 0.35

# What the detector is fed. SAM3's own nodes resize every frame to this square.
DETECT_EDGE = 1008

# How many frames are warped at once, in either direction. The grids are the
# large temporary here — a frame of them at 768p is 8 MB — and 16 keeps that
# under a couple of hundred megabytes whatever the pass is.
WARP_CHUNK = 16


class FacePassError(RuntimeError):
    """The face pass could not run on this pass."""


def _detector(name):
    """The SAM3 checkpoint, loaded, plus the text conditioning for `DETECT_PROMPT`.

    Loaded here rather than emitted as a loader node in the render graph. Two
    reasons, and the first is the same one `MiniMaxH3Reel` gives for calling
    `VAEDecode` directly: a node's outputs are held for the whole execution, and
    a detector that is finished after this call has no business staying resident
    until the save node runs. The second is that SAM3 is a fused checkpoint —
    model and text encoder in one file — which is not the split
    `UNETLoader`/`CLIPLoader` shape `models.Links` builds.
    """
    if not str(name or "").strip():
        raise FacePassError(
            "the face pass has no detector. Open the node's weights control and "
            "pick a SAM3 checkpoint from models/checkpoints — it is what finds "
            "the face, and there is no default worth guessing.")
    try:
        from comfy_extras.nodes_sam3 import _extract_text_prompts
    except ImportError as exc:
        raise FacePassError(
            "the face pass needs SAM3, which ships with ComfyUI core — this "
            "install predates it. Update ComfyUI, or switch the face pass off."
        ) from exc

    path = folder_paths.get_full_path_or_raise("checkpoints", name)
    loaded = comfy.sd.load_checkpoint_guess_config(
        path, output_vae=False, output_clip=True,
        embedding_directory=folder_paths.get_folder_paths("embeddings"))
    model, clip = loaded[0], loaded[1]
    if clip is None:
        raise FacePassError(
            f"{name} has no text encoder in it, so it cannot be asked for a "
            f"{DETECT_PROMPT!r} — that is not a SAM3 checkpoint.")
    return model, clip, _extract_text_prompts


def _release(model):
    """Give the detector's VRAM back before H3 is asked for it again.

    The order across one pass is H3, then this, then H3 again. On a box with
    room for both that costs nothing; on a tight one it is two model swaps, and
    the least this can do is not be the reason the second one is a reload from
    disk.
    """
    try:
        comfy.model_management.unload_model_and_clones(model)
    except Exception:                       # pragma: no cover - best effort
        logging.debug("could not unload the face detector", exc_info=True)
    del model
    gc.collect()
    comfy.model_management.soft_empty_cache()


def _detect(model, clip, extract, frames, indices, threshold=DETECT_THRESHOLD):
    """-> one `(x, y, w, h)` box per sampled frame, or None where nothing was found.

    Per frame, the same call SAM3's own `SAM3_Detect` makes. The choice between
    several detections is `faces.pick`'s — it keeps the track on one person
    instead of following whichever face is largest this frame.
    """
    tokens = clip.tokenize(DETECT_PROMPT)
    conditioning = clip.encode_from_tokens_scheduled(tokens)

    comfy.model_management.load_model_gpu(model)
    device = comfy.model_management.get_torch_device()
    dtype = model.model.get_dtype()
    detector = model.model.diffusion_model
    prompts = extract(conditioning, device, dtype)

    height, width = int(frames.shape[1]), int(frames.shape[2])
    progress = comfy.utils.ProgressBar(len(indices))
    found, previous = [], None
    for index in indices:
        comfy.model_management.throw_exception_if_processing_interrupted()
        frame = torch.from_numpy(np.array(frames[index])).float().div_(255.0)
        frame = comfy.utils.common_upscale(
            frame.unsqueeze(0).movedim(-1, 1), DETECT_EDGE, DETECT_EDGE,
            "bilinear", "disabled").to(device=device, dtype=dtype)

        candidates = []
        for embeddings, mask, _ in prompts:
            results = detector(frame, text_embeddings=embeddings, text_mask=mask,
                               boxes=None, threshold=threshold,
                               orig_size=(height, width))
            scores = results["scores"][0].sigmoid()
            keep = scores > threshold
            for box in results["boxes"][0][keep].cpu():
                x1, y1, x2, y2 = (float(v) for v in box)
                if x2 > x1 and y2 > y1:
                    candidates.append((x1, y1, x2 - x1, y2 - y1))
        found.append(faces.pick(candidates, previous))
        if found[-1] is not None:
            previous = found[-1]
        progress.update(1)
    return found


def _crop(frames, boxes, span, width, height):
    """The crop batch one window samples: `[n, height, width, 3]`, 0..1 float.

    One bilinear sample per frame does the crop and the resize together, at
    sub-pixel coordinates. Slicing to whole pixels first would quantise the box,
    and that rounding — not the tracker — is the largest source of frame-to-frame
    jitter once the trajectory is smoothed.
    """
    start, end = span
    source_h, source_w = int(frames.shape[1]), int(frames.shape[2])
    device = comfy.model_management.get_torch_device()
    out = []
    for base in range(start, end, WARP_CHUNK):
        stop = min(base + WARP_CHUNK, end)
        block = torch.from_numpy(np.array(frames[base:stop])).float().div_(255.0)
        # Warped on the GPU a chunk at a time, and each chunk comes straight
        # back: the assembled crop batch is what the VAE is handed and belongs
        # in host memory until then, but a per-frame bilinear warp of a 768p
        # frame is not work for a CPU.
        block = block[..., :3].movedim(-1, 1).to(device)
        theta = torch.zeros((stop - base, 2, 3), dtype=torch.float32, device=device)
        for offset, index in enumerate(range(base, stop)):
            x, y, box_w, box_h = boxes[index]
            theta[offset, 0, 0] = box_w / source_w
            theta[offset, 0, 2] = (2.0 * x + box_w) / source_w - 1.0
            theta[offset, 1, 1] = box_h / source_h
            theta[offset, 1, 2] = (2.0 * y + box_h) / source_h - 1.0
        grid = F.affine_grid(theta, (stop - base, 3, height, width),
                             align_corners=False)
        # `border` rather than zeros: a crop that runs off the edge of the frame
        # is a face near it, and a black margin would be a thing the model had
        # to explain to itself.
        out.append(F.grid_sample(block, grid, mode="bilinear",
                                 padding_mode="border", align_corners=False)
                   .movedim(1, -1).cpu())
    return torch.cat(out, dim=0)


def _blur(mask, feather):
    """Separable gaussian on a `[n,1,h,w]` mask. `sigma = k/6`, like Impact's."""
    if feather <= 0:
        return mask
    size = 2 * int(feather) + 1
    shortest = min(mask.shape[-2], mask.shape[-1])
    if shortest <= size:
        size = max(3, int(shortest / 2) | 1)
    sigma = max(size / 6.0, 0.5)
    axis = torch.arange(size, device=mask.device, dtype=torch.float32) - size // 2
    kernel = torch.exp(-(axis ** 2) / (2 * sigma * sigma))
    kernel = (kernel / kernel.sum()).to(mask.dtype)
    pad = size // 2
    out = F.conv2d(F.pad(mask, (pad, pad, 0, 0), mode="replicate"),
                   kernel.view(1, 1, 1, size))
    return F.conv2d(F.pad(out, (0, 0, pad, pad), mode="replicate"),
                    kernel.view(1, 1, size, 1))


def _paste_mask(face, width, height, feather, device):
    """The composite mask for one frame: the face box, dilated and blurred.

    Built in canvas space, where the refined crop lives, and warped back with the
    crop itself so the blend lands exactly where the pixels do.
    """
    mask = torch.zeros((1, 1, height, width), device=device, dtype=torch.float32)
    x, y, box_w, box_h = face
    x -= faces.PASTE_DILATION
    y -= faces.PASTE_DILATION
    box_w += 2 * faces.PASTE_DILATION
    box_h += 2 * faces.PASTE_DILATION
    x0, y0 = max(0, int(round(x))), max(0, int(round(y)))
    x1 = min(width, int(round(x + box_w)))
    y1 = min(height, int(round(y + box_h)))
    if x1 > x0 and y1 > y0:
        mask[0, 0, y0:y1, x0:x1] = 1.0
    return _blur(mask, feather).clamp(0, 1)


def _composite(base, refined, boxes, face_rects, weights, device):
    """One chunk of the pass, with its faces put back. `base` is `[n,H,W,3]`.

    `refined[i]` is the re-drawn crop for frame i and `weights[i]` how much of it
    to believe — the tracker's confidence and, where two windows overlap, the
    cross-fade between two generations of the same frame.
    """
    count, height, width = base.shape[0], base.shape[1], base.shape[2]
    canvas_h, canvas_w = refined.shape[1], refined.shape[2]
    base = base.to(device)
    patch = refined.to(device).movedim(-1, 1).float().div_(255.0)

    theta = torch.zeros((count, 2, 3), dtype=torch.float32, device=device)
    masks = []
    for index in range(count):
        x, y, box_w, box_h = boxes[index]
        theta[index, 0, 0] = width / box_w
        theta[index, 0, 2] = (width - 2.0 * x) / box_w - 1.0
        theta[index, 1, 1] = height / box_h
        theta[index, 1, 2] = (height - 2.0 * y) / box_h - 1.0
        masks.append(_paste_mask(
            face_rects[index], canvas_w, canvas_h,
            faces.feather_in_canvas(box_h, canvas_h), device))
    grid = F.affine_grid(theta, (count, 3, height, width), align_corners=False)

    warped = F.grid_sample(patch, grid, mode="bilinear",
                           padding_mode="zeros", align_corners=False).movedim(1, -1)
    mask = F.grid_sample(torch.cat(masks, dim=0), grid, mode="bilinear",
                         padding_mode="zeros", align_corners=False).movedim(1, -1).clamp(0, 1)

    # Colour match inside the mask, weighted by it. The crop was generated on
    # its own canvas, so its exposure is its own; matching the mean and spread of
    # what it is replacing is what keeps the paste from reading as a patch.
    total = mask.sum(dim=(1, 2), keepdim=True).clamp_min(1e-6)
    base_mean = (base * mask).sum(dim=(1, 2), keepdim=True) / total
    patch_mean = (warped * mask).sum(dim=(1, 2), keepdim=True) / total
    base_sd = (((base - base_mean) ** 2 * mask).sum(dim=(1, 2), keepdim=True)
               / total).sqrt().clamp_min(1e-6)
    patch_sd = (((warped - patch_mean) ** 2 * mask).sum(dim=(1, 2), keepdim=True)
                / total).sqrt().clamp_min(1e-6)
    warped = ((warped - patch_mean) * (base_sd / patch_sd) + base_mean).clamp(0, 1)

    opacity = mask * torch.tensor(weights, dtype=torch.float32,
                                  device=device).view(-1, 1, 1, 1)
    return ((1.0 - opacity) * base + opacity * warped).clamp(0, 1)


def _latent_strengths(values, latent_frames):
    """A per-pixel-frame strength curve, resampled onto the latent's frames.

    H3 packs 17 pixel frames into 5 latent ones, so the finest this can be said
    is per latent frame — about three and a half frames of picture.
    """
    if latent_frames <= 1 or len(values) <= 1:
        return [values[0] if values else 1.0] * max(1, latent_frames)
    out = []
    for index in range(latent_frames):
        position = index * (len(values) - 1) / (latent_frames - 1)
        low = int(position)
        high = min(low + 1, len(values) - 1)
        out.append(values[low] + (values[high] - values[low]) * (position - low))
    return out


class MiniMaxH3FacePass(io.ComfyNode):
    """A decoded pass, with its face re-drawn at a canvas where it is large.

    Written into the graph by the render loop (`core/emit.py`) after the reel node, when the piece
    asks for it. See the module docstring for the whole of why.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3FacePass",
            display_name="H3 Face Pass",
            category="Continuity/internal",
            description="Re-draws the face in a decoded pass at a canvas where it "
                        "fills the frame, then composites it back. Written into "
                        "the graph by render.emit.",
            is_dev_only=True,
            inputs=[
                io.Model.Input("model"),
                io.Conditioning.Input("positive",
                    tooltip="Built at the crop canvas, so the references and the "
                            "prompt are encoded at the size the crop is drawn at."),
                io.Conditioning.Input("negative"),
                io.Vae.Input("vae"),
                io.Vae.Input("audio_vae"),
                io.Custom(PASS_TYPE).Input("source",
                    tooltip="The pass to repair, as the reel node wrote it."),
                io.String.Input("detector",
                    tooltip="The SAM3 checkpoint that finds the face."),
                io.Int.Input("width", default=512, min=32, max=8192, step=32),
                io.Int.Input("height", default=512, min=32, max=8192, step=32),
                io.Int.Input("seed", default=0, min=0, max=0xffffffffffffffff),
                io.Int.Input("steps", default=20, min=1, max=200),
                io.Float.Input("cfg", default=1.0, min=0.0, max=30.0),
                io.Combo.Input("sampler_name", options=comfy.samplers.KSampler.SAMPLERS),
                io.Combo.Input("scheduler", options=comfy.samplers.KSampler.SCHEDULERS),
                io.Float.Input("denoise", default=0.45, min=0.01, max=0.99, step=0.01,
                    tooltip="The ceiling. Scaled down per frame by how large the "
                            "face already is — see faces.strengths."),
                # Required, unlike the reel node's own: this runs *after* one,
                # so there is always a reel — the one ending with the pass it is
                # about to replace.
                io.Custom(REEL_TYPE).Input("reel"),
            ],
            outputs=[io.Custom(REEL_TYPE).Output(display_name="reel"),
                     io.Custom(PASS_TYPE).Output(display_name="pass")],
        )

    @classmethod
    def execute(cls, model, positive, negative, vae, audio_vae, source, detector,
                width, height, seed, steps, cfg, sampler_name, scheduler,
                denoise, reel) -> io.NodeOutput:
        import nodes
        from comfy_extras.nodes_minimax_h3 import _empty_av_latent
        # Not from core directly: `_encode_ref_audio` sits on the node class on a
        # core before 2026-08-13. `encode.py` already resolves which spelling this
        # install has.
        from .encode import _encode_ref_audio

        frames = spill.open_frames(source)
        count = int(source["frames"])
        width, height = int(width), int(height)

        indices = faces.detect_frames(count)
        detector_model, clip, extract = _detector(detector)
        try:
            sampled = _detect(detector_model, clip, extract, frames, indices)
        finally:
            _release(detector_model)

        boxes = [(0.0, 0.0, 0.0, 0.0)] * count
        found = [False] * count
        for index, box in zip(indices, sampled):
            if box is not None:
                boxes[index], found[index] = box, True
        if not any(found):
            # Nothing to repair, and nothing to invent. The pass goes on as it
            # is, said out loud rather than left to look like a render that did
            # something.
            logging.info("[MiniMax] face pass: no face found in this pass — left as it is")
            return io.NodeOutput(reel, source)

        crops, face_rects = faces.crop_boxes(boxes, found, width, height)
        heights = faces.face_heights(crops)
        strengths = faces.strengths(heights)
        confidence = faces.paste_weights(found)
        spans = faces.windows(count)
        blend = faces.window_weights(spans)
        logging.info(
            "[MiniMax] face pass: %d frames, faces %.0f-%.0f px, %d window(s) at %dx%d",
            count, min(heights), max(heights), len(spans), width, height)

        refined = []
        for span in spans:
            refined.append(cls._window(
                span, frames, crops, strengths, source, model, positive, negative,
                vae, audio_vae, width, height, seed, steps, cfg, sampler_name,
                scheduler, denoise, nodes, _empty_av_latent, _encode_ref_audio))

        device = comfy.model_management.get_torch_device()
        written = spill.rewrite(source, cls._blocks(
            frames, refined, spans, blend, crops, face_rects, confidence, device))
        # The reel this was handed already ends with the pass that has just been
        # repaired — this node runs after the one that put it there — so the
        # replacement goes in its place rather than after it.
        return io.NodeOutput([*reel[:-1], {"pass": written}], written)

    @classmethod
    def _window(cls, span, frames, crops, strengths, source, model, positive,
                negative, vae, audio_vae, width, height, seed, steps, cfg,
                sampler_name, scheduler, denoise, nodes, empty_av_latent,
                encode_ref_audio):
        """One window of the pass: cropped, re-sampled, decoded -> uint8 crops."""
        start, end = span
        length = end - start
        images = _crop(frames, crops, span, width, height)

        latent, aligned = empty_av_latent(width, height, length)
        if aligned != length:
            # `faces.windows` only ever returns lengths off `legal_frame_counts`,
            # so this is the graph having been built against other arithmetic.
            raise FacePassError(
                f"a {length}-frame window is not on H3's frame grid ({aligned} is)")
        shell = latent["samples"].unbind()
        video = vae.encode(images[..., :3])
        if video.ndim == 4:                       # [B,C,H,W] -> [1,C,T,H,W]
            video = video.unsqueeze(0).movedim(1, 2)
        video = video.to(shell[0].device, shell[0].dtype)
        if video.shape[-3:] != shell[0].shape[-3:]:
            raise FacePassError(
                f"the crop encoded to {tuple(video.shape[-3:])} where this window "
                f"wants {tuple(shell[0].shape[-3:])} — the window is off H3's "
                f"frame grid, which faces.windows exists to prevent")

        audio = shell[1]
        if "audio_path" in source:
            fps = float(source["fps"])
            clip_audio = spill.sound_between(source, start / fps, end / fps)
            encoded, _ = encode_ref_audio(audio_vae, clip_audio)
            encoded = encoded.to(audio.device, audio.dtype)
            # The encoder's length comes out of the waveform and the shell's out
            # of the frame count; they agree to within a column or two of
            # rounding, and the shell is what the DiT's layout was built for.
            shared = min(encoded.shape[-1], audio.shape[-1])
            audio = audio.clone()
            audio[..., :shared] = encoded[..., :shared]

        # One mask, two statements: hold the sound exactly (zeros), and work
        # this hard on the picture, frame by frame. Core unbinds it per stream
        # and packs it with the latent — `comfy/samplers.py`.
        curve = _latent_strengths(strengths[start:end], int(video.shape[-3]))
        video_mask = torch.tensor(curve, dtype=torch.float32).view(1, 1, -1, 1, 1)
        video_mask = video_mask.expand(video.shape).contiguous()
        mask = comfy.nested_tensor.NestedTensor(
            (video_mask, torch.zeros_like(audio, dtype=torch.float32)))

        samples = comfy.nested_tensor.NestedTensor((video, audio))
        # The seed as given, the same in every window. It used to be `seed +
        # start`, on the theory that equal-length windows should not be sampled
        # against the identical noise tensor — but the common case is one window,
        # where `start` is 0 and the offset does nothing, and where there are
        # several they are re-drawing different frames behind a per-frame
        # strength mask, so identical starting noise costs nothing. What it did
        # cost was the seed: `start` is derived from the pass's frame count, so
        # trimming a few frames off a seam moved the face repair's noise without
        # the number on the node having changed.
        noise = comfy.sample.prepare_noise(samples, seed)
        sampled = comfy.sample.sample(
            model, noise, steps, cfg, sampler_name, scheduler, positive, negative,
            samples, denoise=denoise, noise_mask=mask, seed=seed,
            callback=latent_preview.prepare_callback(model, steps),
            disable_pbar=not comfy.utils.PROGRESS_BAR_ENABLED)

        out = nodes.VAEDecode().decode(vae, {"samples": sampled})[0]
        # Kept as 8-bit: it is what the spill stores, what the encoder is handed
        # in the end, and a quarter of the memory to hold every window in until
        # the composite runs.
        return (out[..., :3] * 255).clamp(0, 255).byte().cpu()

    @classmethod
    def _blocks(cls, frames, refined, spans, blend, crops, face_rects,
                confidence, device):
        """The repaired pass, a chunk at a time, for `spill.rewrite` to stream.

        A frame covered by two windows is composited twice — once from each — so
        the cross-fade happens in the picture rather than between two latents
        that never met.
        """
        count = int(frames.shape[0])
        for base in range(0, count, WARP_CHUNK):
            comfy.model_management.throw_exception_if_processing_interrupted()
            stop = min(base + WARP_CHUNK, count)
            block = torch.from_numpy(np.array(frames[base:stop])).float().div_(255.0)
            for window, (start, end) in enumerate(spans):
                low, high = max(base, start), min(stop, end)
                if low >= high:
                    continue
                weights = [confidence[i] * blend[window][i - start]
                           for i in range(low, high)]
                if not any(weights):
                    continue
                piece = _composite(
                    block[low - base:high - base].to(device),
                    refined[window][low - start:high - start],
                    crops[low:high], face_rects[low:high], weights, device)
                block[low - base:high - base] = piece.cpu()
            yield block


NODES = [MiniMaxH3FacePass]

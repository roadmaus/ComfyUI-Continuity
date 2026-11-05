"""The live preview this pack draws for itself when KJNodes is not installed.

A render of ours used to preview through exactly one thing: KJNodes'
`ModelPreviewOverrideKJ` (`models.graph_preview`). Without that pack a render
sampled for minutes behind an empty box, on every family, the video renders and
the stills and the PreStage alike — and not because anything was missing. Every
latent format we sample declares latent2rgb factors, so core could always have
drawn *something*. It does not, because core's previewer is gated on one global
switch, `args.preview_method`, and a fresh install ships with it set to `none`;
the frontend's own setting defaults to "default", which sends no override with
the prompt, so the server's `none` stands. Asking everybody to find that setting
is asking them to know why the box is empty.

**The step callback is there whether previews are on or not.** Core's
`latent_preview.prepare_callback` always hands the sampler a callback — it drives
the progress bar — and only the *picture* inside it is gated. So a wrapper around
`OUTER_SAMPLE` sees `x0` on every step on any install, and can decode and
broadcast it on its own terms. That is the whole trick, and it is the same one
KJNodes plays; this is a deliberately small version of it, written here rather
than borrowed (that pack is GPL, this one MIT), that does latent2rgb and nothing
else. The tiny-VAE decode and the MP4 path stay KJNodes' to offer, which is why
`graph_preview` still prefers that node when it is there.

**What it sends is shaped like what KJNodes sends**, under its own event name
(`mmc_preview`), so `stage.js` and `chat.js` read both through one handler:
`node_id`, `prompt_id`, `step`, `total`, and on frames `image` (base64),
`mime`, `w`, `h`, `fps`. A video latent is drawn across the whole clip as an
animated WebP at the family's rate; a still is a JPEG. Encoding happens on a
worker thread holding at most one waiting frame, the newest, so a slow encode
costs a skipped picture, never a slower step.

**Which node the frame belongs to is read when sampling starts**, not when this
node ran. ComfyUI caches a V3 node's output by its inputs alone (`stage.js` has
the why), so the wrapper built under the PreStage's id goes on being handed out
when the Creator samples the same weights next. The server's `last_node_id` is
the display id of the node executing *now* — for anything inside our expansion,
the Creator's or the PreStage's own id — so that is asked first and the id this
node was built under is only the fallback.

**Core's own previews are switched off for the duration**, on an install where
they are on: the frontend paints those onto the canvas node, over the top of the
node body, which is where ours land. Every `decode_latent_to_preview_image` in
the previewer hierarchy is swapped for one returning nothing while this sampler
runs, and put back in a `finally`.

Nothing here may fail a render. Every decode and send is guarded, and a preview
that cannot be drawn is logged once and left out.
"""

import base64
import io as pyio
import logging
import queue
import threading

from comfy_api.latest import io

NODE_ID = "ContinuityPreview"
EVENT = "mmc_preview"
WRAPPER_KEY = "mmc_preview"


class _Worker:
    """One encode at a time, off the sampling thread, newest frame first.

    At most one frame waits. A newer one *replaces* it rather than being turned
    away: dropping the newcomer would throw out the last step's picture —
    the one closest to the finished render, and the one left on screen — any
    time the encoder was still busy with the step before.
    """

    _STOP = object()

    def __init__(self):
        self._queue = queue.Queue(maxsize=1)
        self._thread = threading.Thread(target=self._run, name="mmc_preview", daemon=True)
        self._thread.start()

    def submit(self, job):
        while True:
            try:
                self._queue.put_nowait(job)
                return
            except queue.Full:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    pass

    def _run(self):
        while True:
            job = self._queue.get()
            if job is self._STOP:
                return
            try:
                job()
            except Exception:      # noqa: BLE001 - a preview never fails a render
                logging.exception("Continuity: the live preview could not be encoded")

    def close(self, timeout=5.0):
        try:
            self._queue.put(self._STOP, timeout=timeout)
        except queue.Full:
            pass
        self._thread.join(timeout=timeout)


def video_part(x0, latent_shapes=None):
    """The picture stream of a step's x0.

    An audio+video model (H3, LTX AV) samples its streams packed flat into one
    `[B, 1, N]` tensor, video first. Core unpacks that into a nested view for
    callbacks (`samplers.py`, `sample`) — but it does so by wrapping the
    callback *before* the `OUTER_SAMPLE` wrappers run, so a wrapper is handed
    the nesting adapter as its `callback` and the callback it passes down is
    called with the packed tensor. Reading that as a picture failed on the
    first step and switched the preview off: every H3 render previewed nothing
    while every still previewed fine. So the packed form is unpacked here with
    core's own `unpack_latents` against the shapes the sampler packed it from,
    and the nested form — what a callback above the adapter would see — is
    taken as it comes.
    """
    if getattr(x0, "is_nested", False):
        return x0.tensors[0]
    if latent_shapes and len(latent_shapes) > 1:
        import comfy.utils

        return comfy.utils.unpack_latents(x0, latent_shapes)[0]
    return x0


def guide_frames(guider, latent):
    """How many latent frames at the end of `latent` are LTX guide frames.

    `LTXVAddGuide` appends the guide images to the latent's time axis and says so
    with `keyframe_idxs` on the conditioning; drawn as they are, they are a flash
    of the keyframe tacked onto every preview loop. Counted the way core's
    `nodes_lt.get_keyframe_idxs` counts them from a latent shape. Zero for every
    family that has no such thing, and for anything this cannot read.
    """
    if latent.ndim != 5:
        return 0
    try:
        positive = (getattr(guider, "conds", None) or {}).get("positive") or []
        for cond in positive:
            idxs = cond.get("keyframe_idxs") if isinstance(cond, dict) else None
            if idxs is not None:
                per_frame = int(latent.shape[-2]) * int(latent.shape[-1])
                count = int(idxs.shape[2]) // max(1, per_frame)
                return count if 0 < count < int(latent.shape[2]) else 0
    except Exception:      # noqa: BLE001
        pass
    return 0


def latent2rgb(x0, latent_format, max_frames):
    """Frames of `x0` through the format's latent2rgb factors, as PIL images.

    The same arithmetic as core's `Latent2RGBPreviewer` — linear map, then
    -1..1 to 0..255 — applied across the time axis of a video latent rather than
    to its first frame, at most `max_frames` of them evenly spread. Empty when the
    format declares no factors.
    """
    import torch
    from PIL import Image

    factors = getattr(latent_format, "latent_rgb_factors", None)
    if factors is None:
        return []
    reshape = getattr(latent_format, "latent_rgb_factors_reshape", None)
    if reshape is not None:
        x0 = reshape(x0)
    weight = torch.tensor(factors, device=x0.device, dtype=x0.dtype).transpose(0, 1)
    bias = getattr(latent_format, "latent_rgb_factors_bias", None)
    if bias is not None:
        bias = torch.tensor(bias, device=x0.device, dtype=x0.dtype)

    sample = x0[0]
    if sample.ndim == 4:                       # C, T, H, W
        count = int(sample.shape[1])
        if 0 < max_frames < count:
            step = (count - 1) / (max_frames - 1) if max_frames > 1 else 0
            sample = sample[:, [round(i * step) for i in range(max_frames)]]
        frames = sample.movedim(0, -1)         # T, H, W, C
    else:                                      # C, H, W
        frames = sample.movedim(0, -1).unsqueeze(0)
    rgb = torch.nn.functional.linear(frames, weight, bias=bias)
    rgb = ((rgb + 1.0) * 127.5).clamp(0, 255).to(torch.uint8).cpu().numpy()
    return [Image.fromarray(frame) for frame in rgb]


def encode(frames, max_px, quality, fps):
    """`(base64, mime, w, h)` for a step's frames, or None."""
    from PIL import Image, ImageOps

    if not frames:
        return None
    if max_px and max_px > 0:
        frames = [ImageOps.contain(f, (max_px, max_px), Image.LANCZOS)
                  if f.width > max_px or f.height > max_px else f for f in frames]
    buf = pyio.BytesIO()
    if len(frames) > 1:
        frames[0].save(buf, format="WEBP", save_all=True, append_images=frames[1:],
                       duration=max(1, round(1000 / max(1.0, float(fps)))),
                       loop=0, quality=int(quality), method=4)
        mime = "image/webp"
    else:
        frames[0].save(buf, format="JPEG", quality=int(quality))
        mime = "image/jpeg"
    return (base64.b64encode(buf.getvalue()).decode("ascii"), mime,
            frames[0].width, frames[0].height)


def _owner(built_id):
    """The display id of the node sampling now, else the id this was built under."""
    try:
        from server import PromptServer

        current = PromptServer.instance.last_node_id
        if current is not None:
            return str(current)
    except Exception:      # noqa: BLE001
        pass
    return built_id


def _prompt_id():
    try:
        from comfy_execution.progress import get_progress_state

        return get_progress_state().prompt_id
    except Exception:      # noqa: BLE001
        return None


def _send(payload):
    try:
        from server import PromptServer

        PromptServer.instance.send_sync(EVENT, payload, PromptServer.instance.client_id)
    except Exception:      # noqa: BLE001
        pass


def _silence_core():
    """Swap every core previewer's picture for nothing; returns the undo list."""
    import latent_preview

    undo = []
    stack = [latent_preview.LatentPreviewer]
    while stack:
        cls = stack.pop()
        stack.extend(cls.__subclasses__())
        if "decode_latent_to_preview_image" in cls.__dict__:
            undo.append((cls, cls.__dict__["decode_latent_to_preview_image"]))
            cls.decode_latent_to_preview_image = lambda self, fmt, x0: None
    return undo


class PreviewWrapper:
    """The `OUTER_SAMPLE` wrapper: decode each step's x0 and broadcast it."""

    def __init__(self, node_id, max_px, quality, fps, max_frames):
        self.node_id = None if node_id is None else str(node_id)
        self.max_px = int(max_px)
        self.quality = int(quality)
        self.fps = float(fps)
        self.max_frames = int(max_frames)

    def __call__(self, executor, noise, latent_image, sampler, sigmas, denoise_mask,
                 callback, disable_pbar, seed, latent_shapes=None):
        guider = executor.class_obj
        latent_format = guider.model_patcher.model.latent_format
        owner = _owner(self.node_id)
        prompt_id = _prompt_id()
        total = max(0, int(sigmas.shape[-1]) - 1) if sigmas is not None else 0
        _send({"node_id": owner, "prompt_id": prompt_id, "step": 0, "total": total})

        worker = _Worker()
        failed = []
        upstream = callback

        def step(index, x0, x, total_steps):
            if not failed:
                try:
                    latent = video_part(x0, latent_shapes)
                    cut = guide_frames(guider, latent)
                    if cut:
                        latent = latent[:, :, :-cut]
                    frames = latent2rgb(latent.detach(), latent_format, self.max_frames)

                    def ship(frames=frames, done=index + 1, of=total_steps):
                        packed = encode(frames, self.max_px, self.quality, self.fps)
                        if packed is None:
                            return
                        image, mime, w, h = packed
                        _send({"node_id": owner, "prompt_id": prompt_id,
                               "step": done, "total": of, "image": image,
                               "mime": mime, "w": w, "h": h,
                               "fps": self.fps if len(frames) > 1 else None})

                    if frames:
                        worker.submit(ship)
                except Exception as exc:      # noqa: BLE001
                    failed.append(exc)
                    logging.warning("Continuity: live preview disabled for this "
                                    "sampler: %s", exc)
            if upstream is not None:
                upstream(index, x0, x, total_steps)

        undo = _silence_core()
        try:
            return executor(noise, latent_image, sampler, sigmas, denoise_mask, step,
                            disable_pbar, seed, latent_shapes=latent_shapes)
        finally:
            for cls, method in undo:
                cls.decode_latent_to_preview_image = method
            worker.close()


class ContinuityPreview(io.ComfyNode):
    """Patches the built-in live preview onto a MODEL. See the module docstring."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id=NODE_ID,
            display_name="Continuity Preview",
            category="Continuity/internal",
            description="Internal: draws the live preview into the node when "
                        "KJNodes is not installed.",
            is_dev_only=True,
            inputs=[
                io.Model.Input("model"),
                io.Int.Input("max_resolution", default=640, min=64, max=4096),
                io.Int.Input("quality", default=80, min=1, max=100),
                io.Float.Input("fps", default=24.0, min=1.0, max=120.0),
                io.Int.Input("max_frames", default=1024, min=1, max=4096),
            ],
            outputs=[io.Model.Output()],
            hidden=[io.Hidden.unique_id, io.Hidden.dynprompt],
        )

    @classmethod
    def execute(cls, model, max_resolution, quality, fps, max_frames) -> io.NodeOutput:
        import comfy.patcher_extension

        dynprompt = cls.hidden.dynprompt
        node_id = cls.hidden.unique_id
        if dynprompt is not None and node_id is not None:
            node_id = dynprompt.get_display_node_id(node_id)
        patched = model.clone()
        patched.add_wrapper_with_key(
            comfy.patcher_extension.WrappersMP.OUTER_SAMPLE, WRAPPER_KEY,
            PreviewWrapper(node_id, max_resolution, quality, fps, max_frames))
        return io.NodeOutput(patched)


NODES = [ContinuityPreview]

"""The keystone: a clean early frame carried into every continued shot.

A chained strip drifts because every seam hands the next shot the tail of the
one before, and that tail was made mid-strip — it already carries every
brightening and hardening the shots before it added. The first shot of a scene
is the only pass made before any of that, and its first latent is the cleanest
frame the scene will ever have. Carrying it forward gives every later shot
something to be pulled back toward that the drift has not touched.

The method is roycho87's Geiru Context Suite
(https://github.com/roycho87/geiru_context_suite, GPL-3.0). This is a
reimplementation of the ideas, not a copy of the code: the pack is MIT and
reads them through this module only. What is borrowed, and from whom:

- **Keystone front.** The scene's first latent is written over this shot's
  latent 0 and held there by the noise mask, so every step attends to it. The
  shot's real latent 0 — the first step of the masked seam's run — is put back
  after sampling, so the keystone is never in a delivered frame. roycho87.
- **Capstone back.** The scene's last single-frame latent is tacked onto the
  *end* of the video for each model call, held, and cut off again, so nothing
  in the shot is replaced. **Late lock**: it only joins from `lock` steps in, so
  the shot settles its own pose and motion before it is shown the anchor.
  roycho87.
- **Context noise.** The masked seam's held run is given part of the sampler's
  current noise rather than handed over clean, most at its oldest step and
  fading to none at the join, so the model does not copy the drift it carries
  exactly. ethanfel's (Lumifel's) idea, in
  https://github.com/ethanfel/ComfyUI-MiniMaxH3-Context-Loop; core reads a
  fractional noise mask as exactly that.

It builds on the masked seam road (`families/h3/encode._masked_prefix`), which
is the same masked hold — seitanism's and drozbay's — that the Geiru suite is
built on. Without a masked run there is nothing for the keystone to sit beside,
and it stands down.

**Why this file imports nothing from the pack.** Under Raylight the capstone's
model wrapper has to be installed inside every Ray worker, and Ray ships it
there by pickling. `ray_install` and everything it reaches are pickled *by
value* (`register_for_ray`), which works only for code that names torch and
comfy and nothing of ours — a worker process has no reason to be able to
import this pack by its folder name. Keep it that way: a relative import here
is a Ray render that fails on the first shot.
"""

import logging

import torch

# Where a grafted latent carries what the graft did: the latents it replaced
# (to be put back after sampling) and the capstone (tacked on by the model
# wrapper). On the segment node's LATENT output only — read back off that by
# the restore and the lock, never off a sampler's output, so it does not matter
# whether a sampler keeps unknown keys.
KEY = "continuity_keystone"

# The step the capstone joins at when nothing says otherwise: Geiru's default,
# measured there as "around the last 25 % of your steps" on an 8-step turbo.
DEFAULT_LOCK = 4
MAX_LOCK = 50

# The marker the wrapper wears, so a second install replaces the first rather
# than stacking — and an uninstall finds it.
_MARK = "_continuity_keystone"

# H3's latent time grid: (1, 4, 4, 4, 4) from frame 0, so every fifth step is a
# single frame on its own. The capstone has to be one of those — a 4-frame step
# is a blend of four moments, and tacked on alone it would be read as one.
_CYCLE = 5


def _single_frame_before(steps):
    """The last single-frame step at or before `steps - 1`."""
    return _CYCLE * ((int(steps) - 1) // _CYCLE)


def _streams(samples):
    """`(video, rest)` off an H3 AV latent or a bare video tensor."""
    if getattr(samples, "is_nested", False):
        parts = list(samples.unbind())
        return parts[0], parts[1:]
    return samples, []


def _packed(video, rest):
    if not rest:
        return video
    import comfy.nested_tensor

    return comfy.nested_tensor.NestedTensor((video, *rest))


def held_steps(latent):
    """The video steps a noise mask holds outright (mask < 0.5), in order."""
    mask = latent.get("noise_mask")
    if mask is None:
        return []
    video_mask, _ = _streams(mask)
    video, _ = _streams(latent["samples"])
    if tuple(video_mask.shape) != tuple(video.shape):
        return []
    peaks = video_mask.reshape(video_mask.shape[0], video_mask.shape[1],
                               video_mask.shape[2], -1).amax(dim=(0, 1, 3))
    return [t for t in range(int(peaks.shape[0])) if float(peaks[t]) < 0.5]


def graft(latent, source, *, capstone=True, noise=1.0):
    """`latent` with the keystone written in, or `latent` unchanged.

    `latent` is a segment's latent after the masked seam wrote its run into the
    head (`encode._masked_prefix`); `source` the scene's first pass, as the
    sampler made it (its samples, video or AV). Returns `(latent, note)`, the
    note being what the log should say.

    Stands down — the latent back as it came, with a note saying why — where
    there is no masked run to sit beside, or the source is another canvas or
    another model's latent. Neither is an error: a seam that cannot carry a
    keystone is still a seam.
    """
    video, rest = _streams(latent["samples"])
    held = held_steps(latent)
    if not held or held[0] != 0:
        return latent, "no masked run at the head of this shot; keystone skipped"
    src, _ = _streams(source)
    if src.ndim != 5 or video.ndim != 5:
        return latent, "not a video latent; keystone skipped"
    if src.shape[1] != video.shape[1] or tuple(src.shape[3:]) != tuple(video.shape[3:]):
        return latent, (f"the scene's first shot is {tuple(src.shape[3:])} latent cells "
                        f"and this one {tuple(video.shape[3:])}; keystone skipped")

    video = video.clone()
    mask_video, mask_rest = _streams(latent["noise_mask"])
    mask_video = mask_video.clone()
    originals = {0: video[:, :, 0:1].clone()}
    notes = []

    # Context noise first, over the held run *after* step 0 — step 0 is about
    # to be the keystone, which stays clean. A ramp from `noise` at the oldest
    # held step to 0 at the join; core reads a mask value m as "this row is at
    # m x the current noise level", so this is exactly the partial re-noising
    # ethanfel described, and the join itself stays clean.
    ramp = held[1:]
    strength = max(0.0, min(1.0, float(noise)))
    if strength > 0 and ramp:
        span = max(1, len(ramp) - 1)
        values = []
        for i, t in enumerate(ramp):
            m = strength * (1.0 - i / span)
            if m <= 0:
                continue
            mask_video[:, :, t:t + 1] = m
            originals[t] = video[:, :, t:t + 1].clone()
            values.append(round(m, 2))
        if values:
            notes.append(f"context noise {values}")

    video[:, :, 0:1] = src[:, :, 0:1].to(device=video.device, dtype=video.dtype)
    mask_video[:, :, 0:1] = 0.0
    notes.insert(0, "keystone in latent 0")

    back = None
    if capstone:
        at = _single_frame_before(src.shape[2])
        back = src[:, :, at:at + 1].clone().cpu()
        notes.append(f"capstone (its step {at})")

    out = {key: value for key, value in latent.items() if key != KEY}
    out["samples"] = _packed(video, rest)
    out["noise_mask"] = _packed(mask_video, mask_rest)
    out[KEY] = {"originals": {t: o.cpu() for t, o in originals.items()}, "back": back}
    return out, ", ".join(notes)


def restore(sampled, grafted):
    """`sampled` with the latents the graft replaced put back.

    The keystone leaves latent 0 holding the scene's first frame and context
    noise leaves the held run a blend of what was held and what was sampled;
    the real run goes back over both, so the decode, the reel and the next
    seam all read the shot's own frames. A causal video VAE decodes every
    frame after the first through it, which is why latent 0 matters even
    though the reel trims the frames it covers.
    """
    info = grafted.get(KEY) if isinstance(grafted, dict) else None
    if not info or not info.get("originals"):
        return sampled
    video, rest = _streams(sampled["samples"])
    video = video.clone()
    for t, original in sorted(info["originals"].items()):
        if t < video.shape[2] and tuple(original.shape[3:]) == tuple(video.shape[3:]):
            video[:, :, t:t + 1] = original.to(device=video.device, dtype=video.dtype)
    out = {key: value for key, value in sampled.items() if key != KEY}
    out["samples"] = _packed(video, rest)
    return out


# ---- the capstone, on the model ---------------------------------------------


def _step_of(transformer_options, timestep, offset):
    """Which step of the whole schedule this call is, or None if unknown.

    The sampler names its own sigmas; a lead-in's second sitting is handed
    only the tail of the schedule, so `offset` puts it back on the whole run's
    count — the lock is "from step 4 of 8" whichever sitting that falls in.
    """
    sigmas = (transformer_options or {}).get("sample_sigmas")
    if sigmas is None:
        return None
    t = float(torch.as_tensor(timestep).flatten()[0])
    return int(torch.argmin((sigmas.float().cpu() - t).abs())) + int(offset)


def _tack_wrapper(back, lock, offset, prev):
    """A `model_function_wrapper` that tacks `back` onto the end of the video.

    For every model call from step `lock` on: the capstone is concatenated
    after the last video step, held by the mask (0 — so the model reads it as
    clean, and the per-token timestep says so), and the prediction for it is
    cut off again before the sampler sees it. Before `lock` the call goes
    through untouched. Audio streams pass through as they are.
    """
    warned = []

    def run(apply_model, x, t, c, args):
        if prev is None:
            return apply_model(x, t, **c)
        return prev(apply_model, {"input": x, "timestep": t, "c": c,
                                  "cond_or_uncond": args.get("cond_or_uncond")})

    def wrapper(apply_model, args):
        import comfy.utils

        x, t, c = args["input"], args["timestep"], args["c"]
        options = c.get("transformer_options", {}) or {}
        step = _step_of(options, t, offset)
        shapes = c.get("latent_shapes")
        if step is None or step < lock:
            return run(apply_model, x, t, c, args)
        window = options.get("context_window")
        if window is not None and window.index_list[-1] != window.total_frames - 1:
            return run(apply_model, x, t, c, args)    # only the window holding the end
        if shapes is not None and len(shapes) > 1:
            parts = list(comfy.utils.unpack_latents(x, shapes))
        else:
            parts = [x]
        video = parts[0]
        if (video.ndim != 5 or back.shape[1] != video.shape[1]
                or tuple(back.shape[3:]) != tuple(video.shape[3:])):
            if not warned:
                logging.warning("[Continuity] keystone: capstone %s does not fit the shot %s; "
                                "not tacked on", tuple(back.shape), tuple(video.shape))
                warned.append(True)
            return run(apply_model, x, t, c, args)
        steps = video.shape[2]
        tail = back.to(device=video.device, dtype=video.dtype).expand(video.shape[0], -1, -1, -1, -1)
        parts[0] = torch.cat([video, tail], dim=2)
        c2 = dict(c)
        if len(parts) > 1:
            x2, c2["latent_shapes"] = comfy.utils.pack_latents(parts)
        else:
            x2 = parts[0]
        mask = c.get("denoise_mask")
        if mask is None:
            mask = torch.ones((video.shape[0], 1, steps) + tuple(video.shape[3:]),
                              device=video.device, dtype=torch.float32)
        if mask.ndim == 5 and mask.shape[2] == steps:
            c2["denoise_mask"] = torch.cat([mask, torch.zeros_like(mask[:, :, :1])], dim=2)
        out = run(apply_model, x2, t, c2, args)
        if len(parts) > 1:
            pieces = list(comfy.utils.unpack_latents(out, c2["latent_shapes"]))
            pieces[0] = pieces[0][:, :, :steps]
            return comfy.utils.pack_latents(pieces)[0]
        return out[:, :, :steps]

    setattr(wrapper, _MARK, True)
    wrapper._prev = prev
    return wrapper


def _without(model):
    """`model`'s wrapper with any keystone wrapper unwound off the top."""
    prev = model.model_options.get("model_function_wrapper")
    while prev is not None and getattr(prev, _MARK, False):
        prev = prev._prev
    return prev


def lock(model, back, lock_step=DEFAULT_LOCK, offset=0):
    """A clone of `model` that tacks `back` on from step `lock_step`."""
    m = model.clone()
    m.set_model_unet_function_wrapper(
        _tack_wrapper(back, int(lock_step), int(offset), _without(m)))
    return m


def unlock(model):
    """A clone of `model` with any keystone wrapper taken off."""
    m = model.clone()
    prev = _without(m)
    if prev is None:
        m.model_options.pop("model_function_wrapper", None)
    else:
        m.set_model_unet_function_wrapper(prev)
    return m


# ---- under Raylight ---------------------------------------------------------


def ray_install(model, back, lock_step):
    """Run inside a Ray worker: the worker's model with the capstone on."""
    return lock(model, back, lock_step, 0)


def ray_remove(model):
    """Run inside a Ray worker: the worker's model with it off again."""
    return unlock(model)


def register_for_ray():
    """Have Ray pickle this module by value, so a worker need not import it.

    See the module docstring. Called by the node that ships the wrapper,
    before the first `.remote()`; registering twice is harmless.
    """
    import sys

    from ray import cloudpickle

    cloudpickle.register_pickle_by_value(sys.modules[__name__])

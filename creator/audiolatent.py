"""Supplied sound, written into a pass's audio latent before it is sampled.

`sound.py` decides *what* each pass is handed and *where* it lands; this is the
half that touches tensors. Kept apart from both families because the operation
is the same on both and the disagreement between them is two numbers, which is
what `Layout` carries.

**How supplying sound actually works.** These are joint AV models: one latent
holds a video stream and an audio stream, and sampling denoises both. So a
supplied track is not mixed in afterwards — it is written into the audio stream
and then *masked out of the denoise*, which is core's `noise_mask` convention:

    1 -> generate this, 0 -> keep what is already there

`comfy/samplers.py` blends on exactly that (`x * denoise_mask + inpaint * (1 -
denoise_mask)`), and it unbinds a nested mask so an AV latent may carry one mask
per stream. `LTXVConcatAVLatent` builds such a pair and its own description
calls it "any AV model, e.g. LTXV or MiniMax H3" — which is why this file has
no family branch in it.

**The mask is the whole feature.** Without it the encoded waveform is still
handed to the sampler as `latent_image`, and at the top of the schedule that is
replaced by noise — so the track would be silently ignored and the render would
come back with invented music that happens to be the right length. Some
published workflows leave the `SetLatentNoiseMask` out and report it "works
either way"; it does not, and this is the one line that decides it.

**Time is mapped proportionally, not by re-deriving the grid.** A family knows
how many audio steps its pass has, because it just built the empty latent with
that many. Audio steps are uniform in time, so a block covering pixel frames
`[at, at+frames)` of a pass covers steps `[at/total * steps, ...)` exactly. That
is a better answer than calling the family's frames-to-steps function again at
an intermediate value: the same number arrived at two ways is a number that can
disagree with itself, and here it would disagree by a step nobody could hear but
every golden graph would notice.
"""

import logging
from dataclasses import dataclass

from . import media

LOG = logging.getLogger("continuity")


@dataclass(frozen=True)
class Layout:
    """The two things about an audio latent that are the family's to say.

    `time_dim` is which axis of the encoded tensor is time, and the families
    genuinely differ: LTX's audio latent is `[B, C, T, F]` and H3's is
    `[B, 32, 2, T]`, so the same tensor rank hides two layouts. Detecting it by
    comparing shapes would work until a pass came out square.

    `sample_rate` is the fallback when the VAE does not name its own — 44100 for
    LTX and 32000 for H3, which are the numbers core's own reference-audio nodes
    fall back to for each.
    """
    time_dim: int
    sample_rate: int


def _encode(audio_vae, layout, filename, in_s, seconds):
    """One window of one file -> its audio latent.

    Resampled to the VAE's own rate first, the way both of core's reference-audio
    nodes do it: an encoder handed 48 kHz when it was trained at 32 does not
    fail, it encodes something a fifth too fast.
    """
    import torchaudio

    audio = media.load_audio(filename, trim=(in_s, in_s + seconds))
    rate = int(audio["sample_rate"])
    want = int(getattr(audio_vae, "audio_sample_rate", layout.sample_rate))
    waveform = audio["waveform"]
    if rate != want:
        waveform = torchaudio.functional.resample(waveform, rate, want)
    # `[:1]` rather than the whole batch: a stereo file is [1, 2, L] and the
    # batch axis is the one being kept, not the channels.
    return audio_vae.encode(waveform[:1].movedim(1, -1))


def fill(audio_vae, empty, blocks, frames, layout):
    """Write `blocks` into an empty audio latent. -> `(samples, noise_mask)`.

    `empty` is the latent the family already built for this pass — its length is
    the authority on how many steps the pass has, so nothing here re-derives it.
    `frames` is the pass's pixel-frame count, which is what `blocks` are placed
    against (`sound.for_window` put them on this pass's own clock).

    The mask comes back the same shape as the samples and is ones everywhere the
    lane left a gap, because a gap is sound the model writes rather than silence
    — see `sound.band`.
    """
    import torch

    samples = empty.clone()
    mask = torch.ones_like(samples)
    steps = samples.shape[layout.time_dim]
    if not steps or not frames:
        return samples, mask

    for block in blocks:
        first = round(block["at"] / frames * steps)
        last = round((block["at"] + block["frames"]) / frames * steps)
        room = min(last, steps) - first
        if room < 1:
            continue

        encoded = _encode(audio_vae, layout, block["filename"], block["in_s"],
                          block["seconds"])
        encoded = encoded.to(samples.device, dtype=samples.dtype)
        have = encoded.shape[layout.time_dim]

        # The encode rarely lands on exactly the steps the arithmetic asked for
        # — a container's duration is not a multiple of a latent step — so the
        # placement is authoritative and the encode is cut or let run short.
        # Short is the interesting case: the steps it does not reach stay masked
        # 1, so the model scores the tail rather than the pass ending on a
        # frozen last step, which is what padding with zeros would have made.
        take = min(room, have)
        _write(samples, encoded, layout.time_dim, first, take)
        _zero(mask, layout.time_dim, first, take)
        if have < room:
            LOG.info(
                "[MiniMax] %s is %d audio steps short of the %d it was placed "
                "across; the model writes the rest.",
                block["filename"], room - have, room)
    return samples, mask


def apply_av(latent, audio_vae, blocks, frames, layout):
    """Supplied sound into an AV latent that is *already packed*. -> a new latent.

    LTX builds its two streams separately and concatenates them last, so its
    segment node fills the audio latent before the pack and never needs this.
    H3's `_empty_av_latent` hands back the nested pair fully formed, so its
    sound has to be written into the pack — same fill, one unbind either side.

    The video half's mask is ones: nothing about supplying sound says anything
    about the picture, and a nested mask has to name both streams or core has
    nothing to unbind (`LTXVConcatAVLatent` fills the missing half the same way).
    """
    import comfy.nested_tensor
    import torch

    if not blocks:
        return latent

    video, audio = latent["samples"].unbind()
    samples, mask = fill(audio_vae, audio, blocks, frames, layout)

    existing = latent.get("noise_mask")
    video_mask = existing.unbind()[0] if existing is not None and existing.is_nested \
        else torch.ones_like(video)
    return {
        **latent,
        "samples": comfy.nested_tensor.NestedTensor((video, samples)),
        "noise_mask": comfy.nested_tensor.NestedTensor((video_mask, mask)),
    }


def _slice(tensor, dim, first, count):
    return tensor.narrow(dim, first, count)


def _write(samples, encoded, dim, first, count):
    _slice(samples, dim, first, count).copy_(_slice(encoded, dim, 0, count))


def _zero(mask, dim, first, count):
    _slice(mask, dim, first, count).zero_()

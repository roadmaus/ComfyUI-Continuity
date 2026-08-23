"""Where a seam's inherited frame actually lands on the clip it opens.

`test_payload_repair.py` proves the rewrite in `payload.py` is right about
core's coordinate system. It cannot prove the encoder *asks* for it — and for
one release it did not: `_encode_references` keyed its seam, `_encode_frames`
did not, so every chained I2VA segment whose sound also crossed the seam pinned
its inherited frame `ref_audio_t` time units before the clip's own opening. The
model read it as a frame from a second ago instead of as frame 0, and the
continuation quietly stopped continuing. Nothing raised.

So this runs the real `encode._encode_frames` against core's real `PackedLayout`
and asks the only question that matters: is the guide on the clip's first frame?

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_seam_anchor.py

Skips itself with a message if ComfyUI core cannot be imported.
"""

import importlib.util
import os
import sys

import layout
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
sys.path.insert(0, COMFY)

try:
    import torch
    from comfy.ldm.minimax.model import FRAME_RESCALE, PackedLayout
except Exception as exc:  # noqa: BLE001
    print(f"skipped: ComfyUI core not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)


def _load(name):
    if "mmc" not in sys.modules:
        package = types.ModuleType("mmc")
        package.__path__ = [layout.PY_ROOT]
        sys.modules["mmc"] = package
    spec = importlib.util.spec_from_file_location(f"mmc.{name}", layout.py(name))
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"mmc.{name}"] = module
    spec.loader.exec_module(module)
    return module


try:
    compiler = _load("compile")
    encoder = _load("encode")
    repair = _load("payload")
except Exception as exc:  # noqa: BLE001
    print(f"skipped: package not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)

from harness import FAILURES, check, passed


# ---- stubs -------------------------------------------------------------------
#
# Everything the encoder reaches through that needs weights. The seam's geometry
# is decided by the metadata on the keyframe dicts and by the layout, so the
# tensors only have to have believable shapes.

TEXT_LEN = 9
AUDIO_STEPS = 40           # what a ~1 s tail encodes to


class Clip:
    def __init__(self):
        self.tokenized = None

    def tokenize(self, prompt, **kwargs):
        self.tokenized = kwargs
        return "tokens"

    def encode_from_tokens_scheduled(self, tokens):
        return [[torch.zeros(1, TEXT_LEN, 8), {}]]


class Vae:
    """One latent step per encoded frame run, shaped [B, C, T, H, W]."""

    def encode(self, image):
        frames = image.shape[0]
        steps = 1
        if frames > 1:
            # mirror the H3 video VAE's (1, 4, 4, 4, 4) temporal grid
            covered, steps = 0, 0
            while covered < frames:
                covered += encoder.FRAME_PER_TOKEN[steps % 5]
                steps += 1
        return torch.zeros(1, 24, steps, 4, 4)


class AudioVae:
    """The H3 audio VAE's rate: 40 latent steps a second, one time unit each."""

    audio_sample_rate = 32000
    STEPS_PER_SECOND = 40

    def encode(self, waveform):  # [1, samples, channels]
        seconds = waveform.shape[1] / self.audio_sample_rate
        return torch.zeros(1, 32, 2, max(1, round(seconds * self.STEPS_PER_SECOND)))


def compiled_segment(tail=1.7, **segment):
    """A chained segment, compiled the way the Timeline node compiles it."""
    blob = {
        "version": 2, "render": "chained", "prompt": "", "aspect": "16:9", "short_edge": 768,
        "audio_tail_s": tail,
        "segments": [{"duration_s": 6, "prompt": "one"},
                     {"duration_s": 6, "prompt": "two", **segment}],
    }
    return compiler.compile_segment(compiler.timeline_payloads(blob)[1])


def encode(compiled, tail_frames=64):
    """What the segment node hands the encoder, for this compiled seam.

    The soundtrack is exactly `compiled.audio_tail_s` long because that is what
    the graph wires: `render.emit` passes that number to the pass-audio node,
    so the encoder never sees more sound than compile decided on.
    """
    clip, vae = Clip(), Vae()
    samples = max(1, round(compiled.audio_tail_s * AudioVae.audio_sample_rate))
    loaded = {
        encoder.PREV_FRAME: {"image": torch.zeros(tail_frames, 768, 1344, 3)},
        encoder.PREV_AUDIO: {"audio": {"waveform": torch.zeros(1, 2, samples),
                                       "sample_rate": 32000}},
    }
    cond, _ = encoder._encode_frames(clip, vae, AudioVae(), compiled, loaded)
    return cond[0][1]


def placed(values):
    """The repositioned layout, plus where the clip's own first frame sits."""
    keyframes = values.get("minimax_keyframes") or []
    refs = values.get("minimax_refs") or []
    # No `frame_count`: core took one until 2026-08-13, to work out where its
    # only other legal anchor — the last frame — sat. It now anchors a keyframe
    # at any index off `resolved_frame_index`, so the argument is gone.
    layout = PackedLayout(TEXT_LEN, 8, 4, 4, 12, keyframes=keyframes, refs=refs)
    repair._reposition(layout, {"keyframes": keyframes, "refs": refs})
    return layout, repair._target_origin(layout)


def pin(keyframe):
    """The pixel index the entry pins its guide at, on either core."""
    if repair.CORE_ANCHORS_ANYWHERE:
        return keyframe["resolved_frame_index"]
    return keyframe.get(repair.FRAME_INDEX_KEY)


def anchors(values):
    """Where the layout's cond rows sit, relative to the clip's first frame."""
    layout, origin = placed(values)
    return [round(float(layout.position_ids[a, 0]) - origin, 4)
            for a, _, kind in layout.segments if kind == "cond"]


def sound_span(values):
    """(first, last) instant the seam's audio rows occupy, in pixel frames."""
    layout, origin = placed(values)
    a, b = [(a, b) for a, b, kind in layout.segments if kind == "ref_audio"][0]
    times = layout.position_ids[a:b, 0]
    return ((float(times.min()) - origin) / FRAME_RESCALE,
            (float(times.max()) - origin) / FRAME_RESCALE)


# ---- the seam ----------------------------------------------------------------

# Picture only: nothing else is in the layout, so the guide was always on the
# clip. It must stay there — the keying is a repair, not a relayout.
values = encode(compiled_segment(**{"continue": True}))
check("a picture-only seam pins the inherited frame on frame 0", anchors(values), [0.0])

# Picture and sound, the classic single-frame seam. The audio tail is a
# reference block, so the target clip no longer starts where stock puts a
# "frame 0" anchor. This is the case that broke.
values = encode(compiled_segment(**{"continue": True, "continue_audio": True}))
check("the seam carries its real index",
      [pin(kf) for kf in values["minimax_keyframes"]], [0])
check("a sounding seam still pins the inherited frame on frame 0",
      anchors(values), [0.0])

# The same seam blended: every pinned step of the inherited run lands on the
# step of the clip's own grid that covers the same instants.
values = encode(compiled_segment(**{"continue": True, "continue_audio": True, "feather": 22}))
spans = [encoder._frames_covered(k) for k in range(len(values["minimax_keyframes"]))]
check("a blended seam pins each step at its own pixel offset",
      [pin(kf) for kf in values["minimax_keyframes"]], spans)
check("a blended seam's guides land on the clip's own grid",
      anchors(values),
      [round(5.0 / 3.0 * index, 4) for index in spans])

# The old-core spelling, whichever core this suite runs against: with the
# general anchor forced off, `_pin` passes the nearest legal stock anchor and
# carries the real index for `payload.py` to write in.
_had_anchor = encoder.CORE_ANCHORS_ANYWHERE
encoder.CORE_ANCHORS_ANYWHERE = False
check("old core: a mid-run guide passes stock frame 0 and carries its index",
      encoder._pin({"latent": "L"}, 9),
      {"resolved_frame_index": 0, repair.FRAME_INDEX_KEY: 9, "latent": "L"})
check("old core: a last-frame guide passes stock's own last anchor",
      encoder._pin({"latent": "L"}, 148, stock=148),
      {"resolved_frame_index": 148, repair.FRAME_INDEX_KEY: 148, "latent": "L"})
encoder.CORE_ANCHORS_ANYWHERE = _had_anchor

# ---- the blend and the tail ---------------------------------------------------
#
# A blended seam pins frames and sound from the same instants of the same source
# segment, and the model follows sound hardest — so the two have to cover the
# same span, not merely overlap. The piece's tail setting used to be capped by
# the blend rather than replaced by it, so a tail shorter than the blend pinned
# a run of motion the sound said nothing about. The blend decides now.

for tail in (0.3, 1.0, 4.0):
    for feather in (5, 22, 39):
        compiled = compiled_segment(
            tail=tail, **{"continue": True, "continue_audio": True, "feather": feather})
        check(f"a {feather}-frame blend takes its tail from the blend, not the piece's {tail} s",
              round(compiled.audio_tail_s * 24, 6), float(feather))

        first, last = sound_span(encode(compiled))
        # The audio grid runs at 40 steps a second against 24 fps, so the two
        # only meet to within a step — a fraction of one frame. Anything larger
        # is a real desync, which is what this is here to catch.
        check(f"a {feather}-frame blend's sound starts with the pinned run (tail {tail} s)",
              abs(first) < 1.0, True)
        check(f"a {feather}-frame blend's sound ends with the pinned run (tail {tail} s)",
              abs(last - (feather - 1)) < 1.0, True)

# An unblended seam is still the piece's to set: there are no pinned frames for
# its sound to be in step with, only a last frame.
check("an unblended seam keeps the piece's tail",
      compiled_segment(tail=1.7, **{"continue": True, "continue_audio": True}).audio_tail_s, 1.7)

# A segment with its own start frame and a sound seam is the same trap without
# a continuation: keyframe plus reference block, so the anchor shifts.
compiled = compiled_segment(**{"continue_audio": True})
compiled.continues_audio = True
compiled.first_frame = types.SimpleNamespace(handle="@img-1")
clip, vae = Clip(), Vae()
loaded = {
    "@img-1": {"image": torch.zeros(1, 768, 1344, 3)},
    encoder.PREV_AUDIO: {"audio": {"waveform": torch.zeros(1, 2, 32000), "sample_rate": 32000}},
}
values = encoder._encode_frames(clip, vae, AudioVae(), compiled, loaded)[0][0][1]
check("a start frame beside a sound seam stays on frame 0", anchors(values), [0.0])

# ---- a segment's own frames beside references --------------------------------
#
# The combination the two checkpoints used to refuse: references in the layout
# *and* the segment's own start/end frames, riding as pinned guides exactly as
# a seam's inherited frame does. The frames are presented after the references,
# so the references keep their <Picture N>s and the frames take the next.
mixed = compiler.compile_request(
    {"prompt": "she turns to face @img-2", "duration_s": 6, "aspect": "16:9",
     "short_edge": 768,
     "assets": [
         {"handle": "img-1", "kind": "image", "role": "first_frame", "filename": "open.png"},
         {"handle": "img-3", "kind": "image", "role": "last_frame", "filename": "close.png"},
         {"handle": "img-2", "kind": "image", "role": "reference", "filename": "face.png"},
     ]},
    image_size_lookup=lambda _f: (1344, 768))
check("frames + refs compile to REF2VA", mixed.mode, "REF2VA")

clip, vae = Clip(), Vae()
mixed_loaded = {
    "img-1": {"image": torch.zeros(1, 768, 1344, 3)},
    "img-3": {"image": torch.zeros(1, 768, 1344, 3)},
    "img-2": {"image": torch.zeros(1, 512, 512, 3)},
}
values = encoder._encode_references(clip, vae, AudioVae(), mixed, mixed_loaded)[0][0][1]
check("the frames pin at the clip's own first and last frame",
      anchors(values), [0.0, round((mixed.frames - 1) * FRAME_RESCALE, 4)])
check("the reference block still rides beside them",
      [b["kind"] for b in values["minimax_refs"]], ["image"])
check("the frames are presented after the reference",
      [item["type"] for item in clip.tokenized["minimax_ref_items"]],
      ["image", "image", "image"])
check("...at the canvas's own size, as pinned frames are",
      tuple(clip.tokenized["minimax_ref_items"][1]["data"].shape[1:3]),
      (mixed.height, mixed.width))

passed("all seam-anchor tests passed")

"""ReDetail: a finished pass, re-rendered at twice the canvas through LTX 2.5.

`redetailpass.py` is the half that holds the weights and the pixels; this is the
half that decides — which files the backend loads, what size and length a pass
has to be handed to it at, and what the pill is allowed to promise.

**What this is, said plainly, because the pill has to say it too.** Lightricks'
pixel spatial upscaler is an IC-LoRA that takes a decoded video as a guide and
re-renders it at twice the size. It is a repaint, not a polish: it invents the
fine detail as it goes. Bambushu's ReDetail — <https://github.com/Bambushu/redetail>,
where this graph and its measurements come from — reports a face gaining
freckles it never had and a motocross jersey coming back with different
markings, stable across frames and not the original's. So it is right for
AI-generated and soft footage, which has no detail to recover in the first
place, and wrong wherever a face has to stay the same person or a logo the same
logo. That is a *different promise* from a family's own second stage, which
resolves what the first pass already drew, and it is why this is its own choice
with its own copy rather than a quieter word for "upscale".

**Why it is not a family, and not a second stage either.** It runs on a decoded
pass rather than on a latent, so it can re-render an H3 render as happily as an
LTX one — the backend is the piece's choice and the family is not. It is
therefore an *upscale backend*: `compile.UPSCALE_MODES` is the pill, and this
is the third answer it can give.

**The two constraints, and why one of them is free.**

- Both output dimensions must divide by **64**, not 32. The IC-LoRA encodes its
  guide at half the target and dilates it back onto the target's latent grid
  (`LTXVAddGuide.dilate_latent`), so the latent's own /32 is halved again. At
  exactly x2 off a canvas already snapped to 32 that is free, and it is the
  whole reason `SCALE` is 2 and not a number on a slider: 1.5x lands off the
  grid for most shapes and would have to re-snap and admit the pill's number was
  not the one it ran.
- The pass must be `8n+1` frames long or the model silently drops the tail.
  Free for an LTX piece, whose grid is that grid, and not free for an H3 one,
  whose counts are `17n+5`. `padded_frames` is what makes it free anyway: the
  pass is padded *up* with its own last frame and the padding is dropped after
  decode, so nothing is lost and the cost is at most seven frames of sampling.

**Cost.** Bambushu's measurements, on an RTX PRO 6000 and 243 frames from
768x1408: 1:1 took 3 min at 52 GB, 1.5x 7 min at 65 GB, 2x 17 min at 80.5 GB,
and the rule of thumb is `frames x megapixels` under ~150 at 24 GB, ~350 at 48.
None of it is measured on our own box, so none of it is quoted in the UI.
"""

from . import canvas
from . import models as core

# The trained factor, and the only one offered. See the module docstring: it is
# the one that lands on the /64 grid for free.
SCALE = 2

# What both output dimensions must divide by. Derived rather than written: it is
# the canvas multiple halved a second time by the guide's 2x2 dilation, which is
# the same statement `LTXVAddGuide` makes in `dilate_latent`.
GRID = canvas.LTX25.multiple * 2

# The pass's own grid, which is LTX 2.5's whatever family rendered the pass.
RULES = canvas.LTX25

# The schedule, which is the model's rather than ours. Eight steps at cfg 1 on a
# curve that spends its first four almost in place — the distilled upscaler's
# own, lifted from Lightricks'
# `example_workflows/2.5/LTX-2.5_V2V_ICLoRA_Single_Stage_Distilled.json` by way
# of ReDetail. Not `LTXVScheduler`'s: this pass has no shift pair and no
# terminal to stretch to, and the sampler row's widgets say nothing about it.
SIGMAS = "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"
SAMPLER = "euler_ancestral"
CFG = 1.0

# How hard the pass's own first frame is pinned before the guide goes on.
# ReDetail's graph puts it in through `LTXVImgToVideoInplace` at 0.7, which is
# what stops a chunk from drifting away from where the one in front of it ended.
ANCHOR_STRENGTH = 0.7

# How hard the whole-video guide is applied. 1.0 — the guide *is* the picture,
# and anything less is asking the model to invent more of it than it already is.
GUIDE_STRENGTH = 1.0

# The files this backend loads. Four of the five are LTX 2.5's own slots, spelled
# with LTX 2.5's own ids on purpose: they are the same files, picked from the
# same folders, and `models.every_slot` merges by id. The fifth is the IC-LoRA
# itself, which no family has an equivalent of.
#
# A piece that *renders* on LTX 2.5 does not fill the first four — the render's
# own loaders already have them, and building a second set would load a 21.5 GB
# transformer twice. See `redetailpass.emit`.
SLOTS = {
    "dit": core.Slot("diffusion_models", "the LTX 2.5 transformer",
                     loader="UNETLoader", input="unet_name"),
    "clip": core.Slot("text_encoders", "the text encoder",
                      loader="CLIPLoader", input="clip_name",
                      extra={"type": "ltxv"}),
    "vae": core.Slot("vae", "the video VAE",
                     loader="VAELoader", input="vae_name"),
    "audio_vae": core.Slot("vae", "the audio VAE",
                           loader="VAELoader", input="vae_name", audio=True),
    # Loaded by the pass node itself rather than by a loader in the graph: it
    # goes onto the transformer through `LoraLoaderModelOnly` and its metadata
    # answers `GetICLoRAParameters`, which are one question asked of one file.
    "ic_lora": core.Slot("loras", "the ReDetail IC-LoRA"),
}

FOLDERS = {name: slot.folder for name, slot in SLOTS.items()}
LABEL = {name: slot.label for name, slot in SLOTS.items()}

# The slots the *backend* has to be pointed at whatever the piece renders with.
# Everything but the IC-LoRA drops off this list on a piece that renders on LTX
# 2.5, because the render's own weights answer for them.
SHARED_WITH = "ltx25"


def target(width, height, scale=SCALE):
    """The finished size of a pass sampled at `width` x `height`.

    Raises rather than snapping. A backend that quietly re-snapped would be a
    pill promising a number the render did not run, and every canvas this pack
    resolves is already a multiple of 32 — so the only way here is a caller that
    invented a size of its own.
    """
    out_w, out_h = int(width) * scale, int(height) * scale
    if out_w % GRID or out_h % GRID:
        raise ValueError(
            f"ReDetail renders on a /{GRID} grid and {width}x{height} at x{scale} "
            f"is {out_w}x{out_h}, which is not on it")
    return out_w, out_h


def padded_frames(count, rules=RULES):
    """The length a pass of `count` frames is handed to the model at.

    Up to the next legal count, never down: `LTXVAddGuide` crops a guide to the
    nearest `8n+1` without saying so, so a pass whose length is off the grid —
    every H3 pass, whose counts are `17n+5` — would arrive short and come back
    shorter, with the tail silently missing. Padded with its own last frame and
    trimmed again after decode, it costs at most seven frames of sampling and
    loses nothing.
    """
    count = int(count)
    if count < 1:
        raise ValueError("a pass with no frames cannot be re-detailed")
    step, offset = rules.frame_step, rules.frame_offset
    if count <= offset:
        return offset
    return -(-(count - offset) // step) * step + offset


def frame_megapixels(frames, width, height):
    """ReDetail's own VRAM dial: `frames x megapixels` at the *finished* size.

    Not a limit this refuses on — the number that predicts an out-of-memory is a
    fact about the card this is running on, and the pack has no business
    guessing it. It is logged, so a run that dies has the figure beside it.
    """
    return int(frames) * (int(width) * int(height) / 1_000_000)


def weights_from_blob(data):
    """The blob's `upscale_models` block, read against the table above.

    Its own block rather than the piece's `models`: the slot ids are shared with
    LTX 2.5 by design, and a piece rendering on H3 has an H3 file under `vae`.
    Two files cannot live under one key, so the backend keeps its own.
    """
    return core.Weights.from_blob(data, SLOTS, block="upscale_models")


def needed(family):
    """Which of this backend's slots a piece rendering on `family` must fill.

    All five, except on the family whose files these already are: an LTX 2.5
    piece has picked its transformer, encoder and both VAEs to render with, and
    the pass borrows them rather than asking twice.
    """
    if family == SHARED_WITH:
        return ["ic_lora"]
    return list(SLOTS)


def check(weights, family):
    """Refuse now if a file this pass needs was never picked.

    Its own sentence rather than `models.check`'s: this backend belongs to no
    family, its files are picked in a section of the popover of their own, and
    the escape hatch is a pill rather than another file — none of which the
    generic line has any way to say.
    """
    for name in needed(family):
        if weights.get(name):
            continue
        raise ValueError(
            f"This piece is set to finish through ReDetail, and "
            f"{LABEL[name]} has not been picked. Open the node's 'weights' "
            f"control and choose a file from models/{FOLDERS[name]} under "
            f"'ReDetail', or set the upscale pill back to a pass this family "
            f"makes on its own."
        )


def manifest():
    """What the frontend draws the backend's rows and copy from.

    Served beside the families rather than inside one (`families/manifest.py`'s
    `catalog`), because this backend belongs to no family and listing LTX 2.5's
    files inside H3's manifest would read as H3 having grown a transformer.
    """
    return {
        "id": "redetail",
        "label": "ReDetail",
        "scale": SCALE,
        "grid": GRID,
        # The family whose own weights answer for the four shared slots, so the
        # popover can draw one row instead of five and say why.
        "shares_with": SHARED_WITH,
        "description": "Re-renders the finished pass through LTX 2.5's pixel spatial "
                       "upscaler at twice the canvas. It invents fine detail rather than "
                       "recovering it, so faces and logos come back changed — right for "
                       "soft or generated footage, wrong where something has to stay "
                       "itself.",
        "weights": [{
            "id": name,
            "folder": slot.folder,
            "label": slot.label,
            "loads": bool(slot.loader),
            "gguf": slot.folder in core.GGUF_FOLDERS,
            "device": slot.loader in core.MULTIGPU,
            "title": _UI[name]["title"],
            "help": _UI[name]["help"],
            "hints": _UI[name].get("hints", []),
            "avoid": _UI[name].get("avoid", []),
        } for name, slot in SLOTS.items()],
    }


# What the weights popover says about each row. The four shared slots say the
# same thing LTX 2.5's manifest says about them, shortened: a user filling these
# in on an H3 piece is being asked for a second family's files and the copy has
# to be clear that is what is happening.
#
# The titles are bare — "Transformer", not "LTX 2.5 transformer" — because the
# group heading above the rows already says whose weights these are, and a row
# that repeats it wraps onto two lines to say nothing. Where a title is shown
# *without* that heading, the reader qualifies it: the weights pill's missing
# list prefixes the backend's name, which is one label assembled at the point of
# use rather than a second name for the same file.
_UI = {
    "dit": {
        "title": "Transformer",
        "help": "The 22B DiT the re-detail pass runs on — the distilled file. This is a second "
                "family's weights beside the ones this piece renders with, and it is loaded "
                "only when a render actually reaches the pass.",
        "hints": ["ltx-2.5", "ltx2.5"],
        "avoid": ["upscaler", "duration"],
    },
    "clip": {
        "title": "Text encoder",
        "help": "Gemma 4 12B with LTX's projections. The pass runs on empty prompts, so this "
                "computes the same constant every time — it is here because loading it is the "
                "honest version until the conditioning is cached.",
        "hints": ["gemma4-12b-with-proj", "with-proj"],
    },
    "vae": {
        "title": "Video VAE",
        "help": "LTX 2.5's video VAE. It encodes the finished pass as the guide and decodes what "
                "comes back — not the VAE the piece rendered through.",
        "hints": ["video-vae", "video_vae"],
        "avoid": ["audio"],
    },
    "audio_vae": {
        "title": "Audio VAE",
        "help": "LTX 2.5's audio VAE. The pass keeps the soundtrack it already had; this encodes "
                "it as a reference so the model knows what it is drawing to.",
        "hints": ["audio-vae", "audio_vae"],
    },
    "ic_lora": {
        "title": "Upscaler LoRA",
        "help": "The x2 IC-LoRA that does the re-detailing — "
                "'ltx-2.5-22b-ic-lora-pixel-spatial-upscaler-x2'. Its metadata carries the "
                "downscale factor the guide is dilated by, so the file is the whole recipe.",
        "hints": ["ic-lora-pixel-spatial-upscaler", "pixel-spatial"],
        "avoid": ["temporal"],
    },
}

"""Qwen Image 2.1's manifest. The values are `families/qwen21/still.py`'s
and the shared image-still constants; this module only puts controls behind
them.
"""

from ... import compile_image, guide, render_image
from .. import manifest as m
from . import declare, still


def _widgets():
    base = still.QWEN21_BASE
    return [
        m.widget("steps", "stepper", label="steps", group="sampler",
                 default=base["steps"], min=1, max=10000, step=1),
        m.widget("cfg", "slider", label="cfg", group="sampler",
                 default=base["cfg"], min=0.0, max=100.0, step=0.1),
        m.widget("sampler_name", "combo", label="sampler", group="sampler",
                 default=base["sampler_name"]),
        m.widget("scheduler", "combo", label="scheduler", group="sampler",
                 default=base["scheduler"]),
    ]


# What the weights popover says about each slot — the strings' single home;
# the frontend runs them through t() at render. `hints` are the filename
# needles the guess fills an empty field from; `avoid` the needles that name
# the *other* Qwen family's files, which sit one row away in the same folders
# and load without complaint into the wrong graph.
_UI = {
    "model": {
        "title": "Checkpoint",
        "help": "Qwen-Image-2.1 — the DiT, one file for drawing and editing. bf16 or the int8 convrot cut Comfy-Org publishes.",
        "hints": ["qwen_image_2.1", "qwen_image_2_1", "qwen-image-2.1"],
        # ...and the Fun ControlNet, whose published name starts with the
        # checkpoint's and which people drop into the same folder.
        "avoid": ["qwen_image_edit", "qwen_image_2512", "controlnet"],
    },
    "clip": {
        "title": "Text encoder",
        "help": "Qwen3-VL 8B, loaded as CLIPLoader type 'qwen_image' — the same file Ideogram 4 loads. It reads the pictures as well as the sentence.",
        "hints": ["qwen3vl_8b", "qwen3_vl_8b"],
        "avoid": ["qwen_2.5_vl", "qwen25_vl"],
    },
    "vae": {
        "title": "VAE",
        "help": "The Qwen Image 2.1 VAE — 2.1's own, with an alpha channel. Not the Qwen image VAE the edit family and Krea 2 decode with.",
        "hints": ["qwen_image_2.1_vae", "qwen_image_2_1_vae"],
        "avoid": ["qwen_image_vae"],
    },
    "control": {
        "title": "ControlNet branch",
        "help": "Optional. Qwen-Image-2.1-Fun-Controlnet-Union, from models/model_patches — "
                "what a guide on this still loads to aim the render at a tracing. One "
                "file covers edges, lines, depth, pose and grey. Loaded only when a "
                "guide is attached.",
        "hints": ["qwen-image-2.1-fun-controlnet", "qwen_image_2.1_fun", "qwen_image_2_1_fun"],
        # Z-Image's and the 2512 Qwen-Image's Fun branches sit in the same
        # folder under the same words and are not this DiT's.
        "avoid": ["z-image", "z_image", "2512"],
    },
}


def _weights():
    return [{
        "id": name,
        "folder": render_image.FOLDERS[name],
        "label": render_image.LABEL[name],
        "loads": True,
        # One DiT and no second branch to route a generation between.
        "routed": False,
        "audio": False,
        # The branch is a pass, not a component: a still without a guide
        # renders without it (`render_image.check`).
        "required": name != "control",
        "gguf": name in ("model", "clip"),
        "device": False,
        "title": _UI[name]["title"],
        "help": _UI[name]["help"],
        "hints": _UI[name]["hints"],
        "avoid": _UI[name]["avoid"],
    } for name in still.FIELDS]


def _canvas():
    return {
        "multiple": compile_image.CANVAS_MULTIPLE,
        "min_short_edge": compile_image.MIN_SHORT_EDGE,
        "max_short_edge": compile_image.MAX_SHORT_EDGE,
        "default_short_edge": compile_image.DEFAULT_SHORT_EDGE,
        "max_pixels": compile_image.MAX_PIXELS,
        "min_ratio": compile_image.MIN_RATIO,
        "max_ratio": compile_image.MAX_RATIO,
        "aspects": dict(compile_image.ASPECT_PRESETS),
        "default_aspect": compile_image.DEFAULT_ASPECT,
        # An edit's canvas is the encoder's resize of the picture, on its /32
        # grid — `still.fit_canvas`. The frontend mirrors that arithmetic
        # where it shows the size, and this is how it knows to.
        "encoder_fit": still.REF_RESOLUTION_STEP,
    }


def manifest():
    return {
        # Both the declaration's, so the id a route answers to and the name a
        # pill shows have one home apiece.
        "id": declare.ID,
        "label": declare.LABEL,
        "description": "Qwen Image 2.1 — Alibaba's open-weights DiT that draws from prose and edits "
                       "from pictures on one checkpoint, up to ten of them in, native 2K, "
                       "transparent output on request.",
        "produces": sorted(declare.PRODUCES),
        "widgets": _widgets(),
        "weights": _weights(),
        "canvas": _canvas(),
        "capabilities": {
            "refine": False, "face": False, "audio": False, "seams": False,
            "init_image": {"default_denoise": compile_image.DEFAULT_DENOISE,
                           "min_denoise": compile_image.MIN_DENOISE},
            # A LoRA and only a LoRA: there is no distilled Qwen Image 2.1
            # checkpoint, so `checkpoint` is False and the switch refuses to
            # engage without a file — Qwen Image Edit's arrangement.
            "turbo": {"steps": dict(still.TURBO_STEPS),
                      "row": dict(still.TURBO_ROW),
                      "default_quality": still.DEFAULT_TURBO_QUALITY,
                      "lora": True, "default_strength": 1.0,
                      "checkpoint": False,
                      # The LoRA names a headless render takes for it (`creator/headless.py`).
                      "hints": {"family": r"qwen.?image.?2|qwen.?2\.?1"}},
            # The guide: a Fun ControlNet branch loaded beside the DiT and aimed
            # at the drawing attached as the still's guide — `still.CONTROL_*`.
            # Absent, not False, on a core that cannot load the branch, so the
            # bench's tracing keeps going to the init slot there rather than to
            # a guide the render would refuse.
            **({"control": {
                "method": "branch",
                "slot": "control",
                "tracings": list(still.CONTROL_TRACINGS),
                "kind": "image",
                "default_strength": guide.DEFAULT_STRENGTH,
                "max_strength": guide.MAX_STRENGTH,
                # `control_context_scale` on the card, where 1.0 is full control.
                "stops": {"loose": 0.5, "firm": 0.8, "locked": 1.0},
            }} if still.control_supported() else {}),
            # References with no adapter and no layout to pick: the base weights
            # read them. `edits_first` is what makes this an edit family:
            # `Picture 1` can be the picture being changed in place, which the
            # `edit_first` blob field asks for and which makes it the canvas
            # too. Off — the default — the attached pictures are only cited
            # and the render is a new picture on the aspect pill's canvas,
            # which is what these weights do natively. No editions and no
            # native-control table: one release, and a guide is not a picture
            # here — it goes to the branch above.
            "refs": {"methods": [], "default_method": None,
                     "needs_lora": False, "edits_first": True,
                     "noun": list(still.REFS_NOUN),
                     "edit_first": compile_image.EDIT_FIRST_FIELD},
        },
        "prompt": {
            # Plain prose; references are cited as the labels the 2.1
            # tokenizer itself writes in front of each picture.
            "pipeline": "plain",
            "ordinal": "<image N>",
            "max_refs": still.REFS_LIMIT,
        },
    }

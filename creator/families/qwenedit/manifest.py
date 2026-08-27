"""Qwen Image Edit's manifest. The values are `families/qwenedit/still.py`'s
and the shared image-still constants; this module only puts controls behind
them.
"""

from ... import compile_image, render_image
from .. import manifest as m
from . import declare, still


def _widgets():
    base = still.QWEN_BASE
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
# needles the guess fills an empty field from, newest spelling first: both
# published editions load through the same three slots, so which one is on the
# disk is the only thing that decides.
_UI = {
    "model": {
        "title": "Checkpoint",
        "help": "Qwen-Image-Edit — the 20B DiT. 2511 or 2509; both load here, and the Lightning LoRAs are per edition.",
        "hints": ["qwen_image_edit_2511", "qwen_image_edit_2509", "qwen_image_edit"],
    },
    "clip": {
        "title": "Text encoder",
        "help": "Qwen2.5-VL 7B, loaded as CLIPLoader type 'qwen_image'. It reads the references as well as the sentence.",
        "hints": ["qwen_2.5_vl_7b", "qwen25_vl_7b"],
    },
    "vae": {
        "title": "VAE",
        "help": "The Qwen image VAE — the same file Krea 2 loads.",
        "hints": ["qwen_image_vae"],
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
        "gguf": name in ("model", "clip"),
        "device": False,
        "title": _UI[name]["title"],
        "help": _UI[name]["help"],
        "hints": _UI[name]["hints"],
        "avoid": [],
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
    }


def manifest():
    return {
        # Both the declaration's, so the id a route answers to and the name a
        # pill shows have one home apiece.
        "id": declare.ID,
        "label": declare.LABEL,
        "description": "Qwen Image Edit — 20B open-weights DiT that edits pictures rather than drawing from "
                       "nothing. Up to three images in, one instruction, the subject held across them.",
        "produces": sorted(declare.PRODUCES),
        "widgets": _widgets(),
        "weights": _weights(),
        "canvas": _canvas(),
        "capabilities": {
            "refine": False, "face": False, "audio": False, "seams": False,
            "init_image": {"default_denoise": compile_image.DEFAULT_DENOISE,
                           "min_denoise": compile_image.MIN_DENOISE},
            # A LoRA and only a LoRA: there is no distilled Qwen-Image-Edit
            # checkpoint, so `checkpoint` is False and the switch refuses to
            # engage without a file — Ideogram's arrangement, same reasons.
            "turbo": {"steps": dict(still.TURBO_STEPS),
                      "row": dict(still.TURBO_ROW),
                      "default_quality": still.DEFAULT_TURBO_QUALITY,
                      "lora": True, "default_strength": 1.0,
                      "checkpoint": False},
            # References with no adapter and no layout to pick: the base weights
            # were post-trained to read them, and core's detection gives these
            # files the reference method they were trained with. `edits_first`
            # is what makes this family different from every other still —
            # `Picture 1` is the picture being changed, so it is also the canvas
            # and the latent the render starts from.
            "refs": {"methods": [], "default_method": None,
                     "needs_lora": False, "edits_first": True},
        },
        "prompt": {
            # Plain prose; references are cited as the labels core's Qwen-edit
            # encoder itself writes in front of each image slot.
            "pipeline": "plain",
            "ordinal": "Picture N",
            "max_refs": compile_image.MAX_STYLE_REFS,
        },
    }

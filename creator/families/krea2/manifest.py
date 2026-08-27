"""Krea 2's manifest. The values are `families/krea2/still.py`'s and the
shared image-still constants; this module only puts controls behind them.
"""

from ... import compile_image, render_image
from .. import manifest as m
from . import declare, still


def _widgets():
    raw = still.KREA_RAW
    return [
        m.widget("steps", "stepper", label="steps", group="sampler",
                 default=raw["steps"], min=1, max=10000, step=1),
        m.widget("cfg", "slider", label="cfg", group="sampler",
                 default=raw["cfg"], min=0.0, max=100.0, step=0.1),
        m.widget("sampler_name", "combo", label="sampler", group="sampler",
                 default=raw["sampler_name"]),
        m.widget("scheduler", "combo", label="scheduler", group="sampler",
                 default=raw["scheduler"]),
    ]


# What the weights popover says about each slot — the strings' single home;
# the frontend runs them through t() at render. `hints` are the filename
# needles the guess fills an empty field from.
_UI = {
    "model": {
        "title": "Checkpoint",
        "help": "Krea 2 RAW — the undistilled base. ~52 steps at cfg 3.5, and the one to train LoRAs against.",
        "hints": ["krea2_raw"],
    },
    "turbo_model": {
        "title": "Turbo checkpoint",
        "help": "Krea 2 Turbo — the 8-step distillation the turbo pill swaps in. LoRAs trained on RAW apply here too.",
        "hints": ["krea2_turbo"],
    },
    "clip": {
        "title": "Text encoder",
        "help": "Qwen3-VL 4B, loaded as CLIPLoader type 'krea2'.",
        "hints": ["qwen3vl_4b"],
    },
    "vae": {
        "title": "VAE",
        "help": "The Qwen image VAE.",
        "hints": ["qwen_image_vae"],
    },
}


def _weights():
    return [{
        "id": name,
        "folder": render_image.FOLDERS[name],
        "label": render_image.LABEL[name],
        "loads": True,
        # The Turbo checkpoint is picked by the turbo pill, not routed by the
        # payload the way H3's pair is; the unconditional concept does not
        # exist here at all.
        "routed": False,
        "audio": False,
        "gguf": name in ("model", "turbo_model", "clip"),
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
    from .. import registry

    return {
        # Both the declaration's, so the id a route answers to and the name a
        # pill shows have one home apiece.
        "id": declare.ID,
        "label": declare.LABEL,
        "description": "Krea 2 — 12.9B open-weights DiT. RAW samples at cfg 3.5; the turbo pill swaps in "
                       "the 8-step Turbo checkpoint.",
        "produces": sorted(declare.PRODUCES),
        "widgets": _widgets(),
        "weights": _weights(),
        "canvas": _canvas(),
        "capabilities": {
            "refine": False, "face": False, "audio": False, "seams": False,
            # What this family has that H3's video path does not: an init
            # image with a strength, and the distilled Turbo checkpoint.
            "init_image": {"default_denoise": compile_image.DEFAULT_DENOISE,
                           "min_denoise": compile_image.MIN_DENOISE},
            # Two ways to be fast, one pill: the distilled checkpoint, or the
            # SVD extraction of the same weight difference as a LoRA over RAW.
            # `lora` is what the switch offers to pick — the same shape H3's
            # turbo declaration has, because it is the same switch.
            "turbo": {"steps": dict(still.TURBO_STEPS),
                      "row": dict(still.KREA_TURBO),
                      "default_quality": still.DEFAULT_TURBO_QUALITY,
                      "lora": True, "default_strength": 1.0,
                      "checkpoint": True},
            # What a reference render needs beyond the images: an adapter in the
            # stack, and the layout that adapter was trained on.
            "refs": {"methods": list(still.REF_METHODS),
                     "default_method": still.DEFAULT_REF_METHOD,
                     "needs_lora": True},
        },
        "prompt": {
            # Plain prose; references are cited as the labels core's Qwen-edit
            # encoder itself writes in front of each image slot.
            "pipeline": "plain",
            "ordinal": "Picture N",
            "max_refs": compile_image.MAX_STYLE_REFS,
        },
    }

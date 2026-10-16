"""MOSS-Image's manifest. The values are `families/moss/still.py`'s and the
shared image-still constants; this module only puts controls behind them.
"""

from ... import compile_image, render_image
from .. import manifest as m
from . import declare, still


def _widgets():
    base = still.MOSS_BASE
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
# needles the guess fills an empty field from; `avoid` disqualifies a file the
# needle would otherwise match.
_UI = {
    "model": {
        "title": "Checkpoint",
        "help": "MOSS-Image SFT (or Base) — the 5B DiT. bf16 or the int8 convrot cut; ~50 steps at cfg 3.",
        "hints": ["moss_image", "moss-image"],
        # The 8-step distillations sample only under their own loop — see
        # `still.FIELDS` — and would render as noise on this row.
        "avoid": ["turbo", "dmd"],
    },
    "clip": {
        "title": "Text encoder",
        "help": "Qwen3.5 9B, loaded as CLIPLoader type 'moss_image' — Comfy-Org's qwen3.5_9b file, int8 convrot or w4a8.",
        "hints": ["qwen3.5_9b", "qwen3_5_9b", "qwen35_9b"],
        # The community repack ComfyUI's loader cannot recognise (`check_clip`).
        "avoid": ["moss-image-sft-qwen35"],
    },
    "vae": {
        "title": "VAE",
        "help": "The Flux 2 VAE — the same file Klein and Ideogram load.",
        "hints": ["flux2-vae", "moss-image-sft-vae", "full_encoder_small_decoder"],
        "avoid": [],
    },
}


def _weights():
    return [{
        "id": name,
        "folder": render_image.FOLDERS[name],
        "label": render_image.LABEL[name],
        "loads": True,
        "routed": False,
        "audio": False,
        "gguf": name == "model",
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
    }


def manifest():
    return {
        "id": declare.ID,
        "label": declare.LABEL,
        "description": "MOSS-Image — OpenMOSS's open-weights 5B DiT (Apache 2.0). Text to image "
                       "only, strong on rendered text in English and Chinese; a JSON layout "
                       "pasted as the prompt places text and objects by box.",
        "produces": sorted(declare.PRODUCES),
        "widgets": _widgets(),
        "weights": _weights(),
        "canvas": _canvas(),
        "capabilities": {
            "refine": False, "face": False, "audio": False, "seams": False,
            "init_image": {"default_denoise": compile_image.DEFAULT_DENOISE,
                           "min_denoise": compile_image.MIN_DENOISE},
            # No `turbo` and no `refs`: nothing distilled core can sample
            # (`still.FIELDS`), and no picture input at all.
        },
        "prompt": {
            "pipeline": "plain",
            "ordinal": None,
            "max_refs": 0,
        },
    }

"""FLUX 3 Image Klein's manifest. The values are `families/flux3klein/still.py`'s
and the shared image-still constants; this module only puts controls behind
them.
"""

from ... import compile_image, render_image
from .. import manifest as m
from . import declare, still


def _widgets():
    row = still.KLEIN3
    return [
        m.widget("steps", "stepper", label="steps", group="sampler",
                 default=row["steps"], min=1, max=10000, step=1),
        m.widget("cfg", "slider", label="cfg", group="sampler",
                 default=row["cfg"], min=0.0, max=100.0, step=0.1),
        m.widget("sampler_name", "combo", label="sampler", group="sampler",
                 default=row["sampler_name"]),
        m.widget("scheduler", "combo", label="scheduler", group="sampler",
                 default=row["scheduler"]),
    ]


# What the weights popover says about each slot — the strings' single home;
# the frontend runs them through t() at render. `hints` are the filename
# needles the guess fills an empty field from; `avoid` disqualifies a file the
# needle would otherwise match — here Flux 2 Klein's, one row away.
_UI = {
    "model": {
        "title": "Checkpoint",
        "help": "FLUX 3 Image Klein — the distilled 5.6B DiT, 16 steps at cfg 1. BF16, FP8 or NVFP4. Klein Base loads here too, at ~50 steps and cfg 3.5.",
        "hints": ["flux-3-image-klein", "flux3-image-klein", "flux-3-klein", "flux3-klein", "flux3_klein"],
        "avoid": ["flux-2", "flux2"],
    },
    "clip": {
        "title": "Text encoder",
        "help": "Qwen3-VL 4B Instruct, loaded as CLIPLoader type 'flux3' — the text_encoder folder of BFL's repository, or a single-file repack of it.",
        "hints": ["qwen3vl_4b", "qwen3-vl-4b", "qwen3_vl_4b"],
        "avoid": [],
    },
    "vae": {
        "title": "VAE",
        "help": "The Flux 2 VAE — BFL's ae.safetensors for Klein 3, and the same file Flux 2 Klein loads.",
        "hints": ["flux2-vae", "flux-3-image-klein-ae", "full_encoder_small_decoder"],
        "avoid": [],
    },
}


def _weights():
    return [render_image.manifest_weight(name, _UI[name],
                                        gguf=name in ("model", "clip"))
            for name in still.FIELDS]


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
        "description": "FLUX 3 Image Klein — BFL's 5.6B image editor (FLUX Kommunity License). "
                       "Edits from an instruction, draws from prose, and combines up to ten "
                       "pictures. Wants full scene captions: Refine runs BFL's own upsampler.",
        "produces": sorted(declare.PRODUCES),
        "widgets": _widgets(),
        "weights": _weights(),
        "canvas": _canvas(),
        "capabilities": {
            "refine": False, "face": False, "audio": False, "seams": False,
            "init_image": {"default_denoise": compile_image.DEFAULT_DENOISE,
                           "min_denoise": compile_image.MIN_DENOISE},
            # No `turbo`: the one checkpoint is already the distillation.
            # References as on Flux 2 Klein: native, no adapter, and the first
            # can be the one edited in place.
            "refs": {"methods": [], "default_method": None,
                     "needs_lora": False, "edits_first": True,
                     "noun": list(still.REFS_NOUN),
                     "edit_first": compile_image.EDIT_FIRST_FIELD},
        },
        "prompt": {
            "pipeline": "plain",
            # BFL's upsampler writes the caption in the chat when the magic
            # switch is on (`magic.py`), as the refine button does here.
            "magic": True,
            "ordinal": "Picture N",
            "max_refs": still.REFS_LIMIT,
        },
    }

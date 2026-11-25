"""Ideogram 4.0's manifest. The values are `families/ideogram4/still.py`'s and
the shared image-still constants; this module only puts controls behind them.
"""

from ... import compile_image, render_image
from .. import manifest as m
from . import declare, still


def _widgets():
    # The row Ideogram actually reads: steps come from the quality preset and
    # the schedule is the model's own, so the manifest's sampler group is the
    # preset combo, the cfg the guider runs at, and the sampler name.
    return [
        m.widget("quality", "combo", label="quality", group="sampler",
                 default=still.DEFAULT_IDEOGRAM_QUALITY,
                 options=still.IDEOGRAM_QUALITIES,
                 help="The official V4 presets. Steps, mu and std travel together — the schedule is the preset's, not a widget's."),
        m.widget("cfg", "slider", label="cfg", group="sampler",
                 default=still.IDEOGRAM_CFG, min=0.0, max=100.0, step=0.1),
        m.widget("sampler_name", "combo", label="sampler", group="sampler",
                 default=still.IDEOGRAM_SAMPLER),
    ]


# What the weights popover says about each slot — see krea2's table.
_UI = {
    "model": {
        "title": "Checkpoint",
        "help": "Ideogram 4.0's conditional branch.",
        "hints": ["ideogram4"],
    },
    "uncond_model": {
        "title": "Unconditional checkpoint",
        "help": "The unconditional branch — Ideogram ships CFG as a second model. "
                "Optional: without it the render runs ordinary CFG on the one checkpoint.",
        "hints": ["ideogram4_unconditional"],
    },
    "clip": {
        "title": "Text encoder",
        "help": "Qwen3-VL 8B, loaded as CLIPLoader type 'ideogram4'.",
        "hints": ["qwen3vl_8b"],
    },
    "vae": {
        "title": "VAE",
        "help": "The Flux 2 VAE.",
        "hints": ["flux2"],
    },
}


def _weights():
    # The unconditional checkpoint is optional: without it the guider
    # degrades to ordinary CFG, which the node itself documents.
    return [render_image.manifest_weight(name, _UI[name],
                                        gguf=name in ("model", "uncond_model", "clip"),
                                        required=name != "uncond_model")
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
    from .. import registry

    return {
        # Both the declaration's, so the id a route answers to and the name a
        # pill shows have one home apiece.
        "id": declare.ID,
        "label": declare.LABEL,
        "description": "Ideogram 4.0 — 9.3B open-weights DiT with its own resolution-shifted schedule "
                       "and a second checkpoint for the unconditional branch.",
        "produces": sorted(declare.PRODUCES),
        "widgets": _widgets(),
        "weights": _weights(),
        "canvas": _canvas(),
        "capabilities": {
            "refine": False, "face": False, "audio": False, "seams": False,
            "init_image": {"default_denoise": compile_image.DEFAULT_DENOISE,
                           "min_denoise": compile_image.MIN_DENOISE},
            "qualities": {name: dict(preset) for name, preset
                          in still.IDEOGRAM_QUALITIES.items()},
            # The turbo pill, which here is a LoRA and only a LoRA: Ideogram
            # ships no distilled checkpoint, so `checkpoint` is False and the
            # switch refuses to engage without a file. Thrown on it also drops
            # the unconditional branch and the polish tail, both of which are
            # cfg machinery a distilled run at cfg 1 has no use for.
            # A LoRA reaches both checkpoints, and the unconditional one at a
            # weight of its own — the manager offers the second slider on it.
            "lora": {"uncond": True},
            "turbo": {"steps": dict(still.TURBO_STEPS),
                      # What each stop's tooltip says. Translation keys, like every string here.
                      "titles": {"draft": "2 steps — as short as the distillation goes. For framing, not for finals.",
                                 "medium": "4 steps — quick and usable.",
                                 "good": "8 steps — where a distilled Ideogram stops gaining."},
                      "row": dict(still.TURBO_ROW),
                      "default_quality": still.DEFAULT_TURBO_QUALITY,
                      "lora": True, "default_strength": still.DEFAULT_TURBO_STRENGTH,
                      "checkpoint": False,
                      # The LoRA names a headless render takes for it (`creator/headless.py`).
                      "hints": {"family": r"ideogram|turbotime"}},
        },
        "prompt": {
            # Written as prose, no reference conditioning of any kind; the
            # compile wraps it into the model's JSON caption (`still.format_prompt`).
            "pipeline": "plain",
            "ordinal": None,
            "max_refs": 0,
            # The chat can have Ideogram's own magic prompt write the caption
            # instead (`magic.py`); the switch is the room's, this says the
            # family is one it applies to.
            "magic": True,
        },
    }

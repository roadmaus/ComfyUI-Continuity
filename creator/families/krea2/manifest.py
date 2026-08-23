"""Krea 2's manifest. The values are `families/krea2/still.py`'s and the
shared image-still constants; this module only puts controls behind them.
"""

from ... import compile_image, render_image
from .. import manifest as m
from . import still


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
        "id": "krea2",
        "label": "Krea 2",
        "produces": sorted(registry.PRODUCES["krea2"]),
        "widgets": _widgets(),
        "weights": _weights(),
        "canvas": _canvas(),
        "capabilities": {
            "refine": False, "face": False, "audio": False, "seams": False,
            # What this family has that H3's video path does not: an init
            # image with a strength, and the distilled Turbo checkpoint.
            "init_image": True,
            "turbo": {"steps": dict(still.TURBO_STEPS),
                      "row": dict(still.KREA_TURBO),
                      "default_quality": still.DEFAULT_TURBO_QUALITY},
        },
        "prompt": {
            # Plain prose; references are cited as the labels core's Qwen-edit
            # encoder itself writes in front of each image slot.
            "pipeline": "plain",
            "ordinal": "Picture N",
            "max_refs": compile_image.MAX_STYLE_REFS,
        },
    }

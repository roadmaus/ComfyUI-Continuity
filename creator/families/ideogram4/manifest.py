"""Ideogram 4.0's manifest. The values are `families/ideogram4/still.py`'s and
the shared image-still constants; this module only puts controls behind them.
"""

from ... import compile_image, render_image
from .. import manifest as m
from . import still


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
                 default="euler"),
    ]


def _weights():
    return [{
        "id": name,
        "folder": render_image.FOLDERS[name],
        "label": render_image.LABEL[name],
        "loads": True,
        "routed": False,
        "audio": False,
        # The unconditional checkpoint is optional: without it the guider
        # degrades to ordinary CFG, which the node itself documents.
        "required": name != "uncond_model",
        "gguf": name in ("model", "uncond_model", "clip"),
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
        "id": "ideogram4",
        "label": "Ideogram 4.0",
        "produces": sorted(registry.PRODUCES["ideogram4"]),
        "widgets": _widgets(),
        "weights": _weights(),
        "canvas": _canvas(),
        "capabilities": {
            "refine": False, "face": False, "audio": False, "seams": False,
            "init_image": True,
            "qualities": {name: dict(preset) for name, preset
                          in still.IDEOGRAM_QUALITIES.items()},
        },
        "prompt": {
            # Plain prose, no reference conditioning of any kind.
            "pipeline": "plain",
            "ordinal": None,
            "max_refs": 0,
        },
    }

"""MiniMax H3's manifest: the declarations behind every control the frontend
draws for this family.

Nothing here is a second copy of a number. The sampler row's defaults are
`sampling.DEFAULTS`, the weight slots are `models.SLOTS`, the canvas rules are
`canvas.py`'s — this module only says which *control* each value is behind,
in the vocabulary `families/manifest.py` defines. The bounds and the help
strings are the node schema's own (`creator_node._schema`), under the same
English keys the i18n dictionaries already carry.
"""

from ... import accel, canvas, models, sampling
from .. import manifest as m
from . import still


def _widgets():
    d = sampling.DEFAULTS
    return [
        m.widget("steps", "stepper", label="steps", group="sampler",
                 default=d["steps"], min=1, max=10000, step=1),
        m.widget("cfg", "slider", label="cfg", group="sampler",
                 default=d["cfg"], min=0.0, max=100.0, step=0.1),
        m.widget("sampler_name", "combo", label="sampler", group="sampler",
                 default=d["sampler_name"]),
        m.widget("scheduler", "combo", label="scheduler", group="sampler",
                 default=d["scheduler"],
                 help="The templates use 'simple'; for reference-heavy prompts they suggest 'beta' or 'normal' instead."),
        m.widget("shift_video", "slider", label="video shift", group="sampler",
                 default=d["shift_video"], min=0.01, max=100.0, step=0.01,
                 help="The video flow shift. 12 is the checkpoints' own value; a turbo LoRA's card may name another."),
        m.widget("shift_audio", "slider", label="audio shift", group="sampler",
                 default=d["shift_audio"], min=0.01, max=100.0, step=0.01,
                 help="The audio flow shift. 3 is the checkpoints' own value. A wrong one distorts the soundtrack before it touches the picture."),
        m.widget("block_cache", "combo", label="block cache", group="accel",
                 default=d["block_cache"], options=accel.BLOCK_CACHE_MODES),
        m.widget("spectrum", "toggle", label="spectrum", group="accel",
                 default=d["spectrum"]),
        m.widget("spectrum_blend", "slider", label="spectrum blend", group="accel",
                 default=d["spectrum_blend"], min=0.0, max=1.0, step=0.01),
        m.widget("attention", "combo", label="attention", group="accel",
                 default=d["attention"], options=accel.ATTENTION_MODES),
        m.widget("chunk_ffn", "toggle", label="chunk FFN", group="accel",
                 default=d["chunk_ffn"]),
        m.widget("fp16_accumulation", "toggle", label="fp16 accumulation",
                 group="accel", default=d["fp16_accumulation"]),
    ]


def _weights():
    return [{
        "id": name,
        "folder": slot.folder,
        "label": slot.label,
        # Whether picking it builds a loader in the graph — the preview and
        # the face detector are files other nodes load for themselves.
        "loads": bool(slot.loader),
        "routed": slot.routed,
        "audio": slot.audio,
        "gguf": slot.folder in models.GGUF_FOLDERS,
        "device": name in models.DEVICE_FIELDS,
    } for name, slot in models.SLOTS.items()]


def _canvas():
    return {
        "multiple": canvas.CANVAS_MULTIPLE,
        # Fixed: H3 was trained at 24 and takes no rate conditioning. A family
        # that carries fps as conditioning declares fixed=False and the pill
        # becomes a control.
        "fps": {"value": canvas.FPS, "fixed": True},
        "min_short_edge": canvas.MIN_SHORT_EDGE,
        "max_short_edge": canvas.MAX_SHORT_EDGE,
        "native_short_edge": canvas.NATIVE_SHORT_EDGE,
        "native_max_pixels": canvas.NATIVE_MAX_PIXELS,
        "min_ratio": canvas.MIN_RATIO,
        "max_ratio": canvas.MAX_RATIO,
        "aspects": dict(canvas.ASPECT_PRESETS),
        "frames": {
            # Legal counts are step*n + offset — the temporal packing.
            "step": canvas.FRAME_STEP,
            "offset": canvas.FRAME_OFFSET,
            "trained_min": canvas.TRAINED_MIN_FRAMES,
            "trained_max": canvas.TRAINED_MAX_FRAMES,
            "min_seconds": canvas.MIN_SECONDS,
            "max_seconds": canvas.MAX_SECONDS,
        },
    }


def manifest():
    from .. import registry

    return {
        "id": "h3",
        "label": "MiniMax H3",
        "produces": sorted(registry.PRODUCES["h3"]),
        "widgets": _widgets(),
        "weights": _weights(),
        # The standing route between the family's checkpoints — the control the
        # weights popover draws beside the slots.
        "routes": {"options": m.value_list(models.ROUTES),
                   "default": models.DEFAULT_ROUTE},
        "canvas": _canvas(),
        "capabilities": {
            # The passes the loop may ask this family for.
            "refine": True, "face": True, "audio": True,
            # Chained seams with feathering — the strip's whole grammar.
            "seams": True,
        },
        "prompt": {
            # The shot description is composed into the model's documented
            # Context-IR form; references are cited by ordinal.
            "pipeline": "context-ir",
            "ordinal": "<Picture N>",
        },
        # The pre-stage branch: a still is a video generation whose first
        # latent frame is decoded as a picture.
        "still": {
            "arch": still.ARCH,
            "lengths": m.value_list(still.STILL_LENGTHS),
            "default_frames": still.DEFAULT_FRAMES,
            "default_index": still.DEFAULT_LATENT_INDEX,
            "prompt_modes": m.value_list(still.PROMPT_MODES),
        },
    }

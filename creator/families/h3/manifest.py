"""MiniMax H3's manifest: the declarations behind every control the frontend
draws for this family.

Nothing here is a second copy of a number. The sampler row's defaults are
`sampling.DEFAULTS`, the weight slots are `models.SLOTS`, the canvas rules are
`canvas.py`'s — this module only says which *control* each value is behind,
in the vocabulary `families/manifest.py` defines. The bounds and the help
strings are the node schema's own (`creator_node._schema`), under the same
English keys the i18n dictionaries already carry.
"""

from ... import accel, canvas, compile, models, sampling
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


# What the weights popover says about each slot — the strings' single home,
# under the same English keys the i18n dictionaries carry (the frontend runs
# them through t() at render). `name` is the short display name a routed slot
# goes by on badges and LoRA rows; `hints` are the filename needles the
# frontend's guess fills an empty field from, `avoid` the patterns that rule a
# candidate out (the two VAEs share a folder and both answer to "minimax", and
# the T=1 image decoder loads through the same node as the real one).
_UI = {
    "fl2va": {
        "name": "FL2VA",
        "title": "FL2VA checkpoint",
        "help": "Text-only, start/end frame and continuing shots run on these weights.",
        # What targeting this checkpoint alone means, on a LoRA's mode rows.
        "when": "Only when generating from text or start/end frames.",
        "hints": ["fl2va", "first_last"],
    },
    "ref2va": {
        "name": "Ref2VA",
        "title": "Ref2VA checkpoint",
        "help": "Anything with an @ reference runs on these weights.",
        "when": "Only when @ references are attached.",
        "hints": ["ref2va"],
    },
    "clip": {
        "title": "Text encoder",
        "help": "H3's text encoder. Loaded as CLIPLoader type 'minimax'.",
        "hints": ["minimax"],
    },
    "vae": {
        "title": "Video VAE",
        "help": "Decodes the picture.",
        "hints": ["minimax", "h3"],
        "avoid": ["t1[_-]?image", "image[_-]vae", "audio"],
    },
    "audio_vae": {
        "title": "Audio VAE",
        "help": "Decodes the sound. H3 always generates some, so this is never optional.",
        "hints": ["audio"],
    },
    "preview": {
        "title": "Preview decoder",
        "help": "taeh3, from models/vae_approx — what the live preview decodes through. "
                "Without it the preview is latent2rgb, which is colour without detail.",
        "hints": ["taeh3"],
    },
    "sam3": {
        "title": "Face detector",
        "help": "A SAM3 checkpoint, from models/checkpoints — what the face pass asks "
                "where the face is. Needed only when the face pass is switched on.",
    },
}


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
        # KeyError by design: a slot without its popover strings should fail
        # here, where the family is named, not draw a blank row.
        "title": _UI[name]["title"],
        "help": _UI[name]["help"],
        "hints": _UI[name].get("hints", []),
        "avoid": _UI[name].get("avoid", []),
        **({"name": _UI[name]["name"], "when": _UI[name]["when"]}
           if slot.routed else {}),
    } for name, slot in models.SLOTS.items()]


def _canvas():
    rules = canvas.H3
    return {
        "multiple": rules.multiple,
        # Fixed: H3 was trained at 24 and takes no rate conditioning. A family
        # that carries fps as conditioning declares fixed=False and the pill
        # becomes a control.
        "fps": {"value": rules.fps, "fixed": rules.fps_fixed},
        "min_short_edge": rules.min_short_edge,
        "max_short_edge": rules.max_short_edge,
        "native_short_edge": rules.native_short_edge,
        "native_max_pixels": rules.native_max_pixels,
        "min_ratio": rules.min_ratio,
        "max_ratio": rules.max_ratio,
        "aspects": dict(rules.aspects),
        "frames": {
            # Legal counts are step*n + offset — the temporal packing.
            "step": rules.frame_step,
            "offset": rules.frame_offset,
            "trained_min": rules.trained_min_frames,
            "trained_max": rules.trained_max_frames,
            "min_seconds": rules.min_seconds,
            "max_seconds": rules.max_seconds,
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
        # weights popover draws beside the slots — and which checkpoint the
        # mode implies. References are encoded *for* Ref2VA, so any @ reference
        # routes there and a pin only exists on the plain side; a timeline
        # defaults to the reference checkpoint outright, the superset training,
        # so a strip mixing reference and plain cards runs on one set of
        # weights. Mirrors `compile._resolve_checkpoint`.
        "routes": {"options": m.value_list(models.ROUTES),
                   "default": models.DEFAULT_ROUTE,
                   "reference": "ref2va",
                   "plain": "fl2va",
                   "timeline": "ref2va"},
        # The payload shape -> the name the mode goes by, on cards and in the
        # compiled prompt. "opens" is a first frame or a continuation seam,
        # "closes" a last frame or a cut into a clip — the same reading
        # `compile._derive_mode` makes; test_families holds the names against
        # `compile.MODES`.
        "modes": {"reference": "REF2VA",
                  "opens_closes": "FL2VA",
                  "opens": "I2VA",
                  "closes": "L2VA",
                  "text": "T2VA"},
        "canvas": _canvas(),
        "capabilities": {
            # The passes the loop may ask this family for.
            "refine": True, "face": True, "audio": True,
            # Chained seams with feathering — the strip's whole grammar.
            "seams": True,
        },
        # The reference grammar: what an attached file may be narrowed to,
        # which streams of a clip count, and how many of each the payload
        # takes — compile.py's own vocabulary, which is what makes the chips
        # and the compiler unable to disagree.
        "reference": {
            "takes": {kind: m.value_list(takes)
                      for kind, takes in compile.TAKES.items()},
            "tracks": m.value_list(compile.TRACKS),
            "default_track": compile.TRACKS[0],
            "sizes": dict(compile.DEFAULT_REF_SIZE),
            "max": {"image": compile.MAX_REF_IMAGES,
                    "video": compile.MAX_REF_VIDEOS,
                    "audio": compile.MAX_REF_AUDIOS,
                    "files": compile.MAX_REF_FILES},
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
            # The VAE's temporal packing: `base_frames` frames land in
            # `base_latent` latent frames, and each further `frame_step`
            # (the canvas grid's own) adds `latent_step`. Mirrors
            # `still.latent_frames`; test_families holds the two together.
            "latent": {"base_frames": canvas.H3.frame_offset,
                       "base_latent": still.latent_frames(canvas.H3.frame_offset),
                       "frame_step": canvas.H3.frame_step,
                       "latent_step": 5},
        },
    }

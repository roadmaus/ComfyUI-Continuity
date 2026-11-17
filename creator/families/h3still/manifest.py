"""MiniMax H3 Still's manifest. The values are `families/h3still/still.py`'s
and the shared image-still constants; this module only puts controls behind
them.
"""

from ... import compile_image, render_image
from .. import manifest as m
from . import declare, still


def _widgets():
    row = still.H3STILL_ROW
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
# needles the guess fills an empty field from; `avoid` keeps MiniMax H3
# Image's files out, which share the needles.
_UI = {
    "model": {
        "title": "Checkpoint",
        "help": "A MiniMax H3 video checkpoint — FL2VA, the one a shot renders on. It reads reference pictures too; Ref2VA also works here.",
        "hints": ["minimax_h3_fl2va", "minimax_h3_ref2va"],
        "avoid": ["h3_image"],
    },
    "clip": {
        "title": "Text encoder",
        "help": "Qwen3-VL 32B, loaded as CLIPLoader type 'minimax' — the same file H3 video reads. It reads the pictures as well as the sentence, so the text-only cut will not do.",
        "hints": ["qwen3vl_32b_minimax_h3", "qwen3vl_32b"],
        "avoid": [],
    },
    "vae": {
        "title": "VAE",
        "help": "The MiniMax H3 video VAE — the file a shot is decoded with. Not the MiniMax H3 Image VAE.",
        "hints": ["minimax_h3_video_vae", "minimax", "h3"],
        "avoid": ["t1[_-]?image", "image[_-]vae", "audio"],
    },
}


def _weights():
    return [render_image.manifest_weight(name, _UI[name],
                                        gguf=name in ("model", "clip"))
            for name in still.FIELDS]


def manifest():
    return {
        "id": declare.ID,
        "label": declare.LABEL,
        "description": "MiniMax H3 Still — the H3 video model drawing one frame. Its own look, and every "
                       "MiniMax H3 LoRA works on it. Best from about 3 MP up; 50 steps, or 20 with the Turbo LoRA.",
        "produces": sorted(declare.PRODUCES),
        # Whose cast rows this family reads — `declare.CAST_AS`.
        "cast_as": declare.CAST_AS,
        "widgets": _widgets(),
        "weights": _weights(),
        "canvas": compile_image.manifest_canvas(still),
        "capabilities": {
            "refine": False, "face": False, "audio": False, "seams": False,
            # No `init_image`: the render starts from noise (`still.INIT_REFUSAL`).
            # A LoRA and only a LoRA, at the still recipe's strength rather
            # than the LoRA's own.
            "turbo": {"steps": dict(still.TURBO_STEPS),
                      "row": dict(still.TURBO_ROW),
                      "default_quality": still.DEFAULT_TURBO_QUALITY,
                      "lora": True, "default_strength": still.DEFAULT_TURBO_STRENGTH,
                      "checkpoint": False,
                      # The LoRA names a headless render takes for it (`creator/headless.py`).
                      "hints": {"family": r"h3.*turbo|turbo.*h3"}},
            # References on the base weights, Picture 1 the one an instruction
            # changes — MiniMax H3 Image's arrangement.
            "refs": {"methods": [], "default_method": None,
                     "needs_lora": False, "edits_first": True,
                     "noun": list(still.REFS_NOUN),
                     "edit_first": compile_image.EDIT_FIRST_FIELD},
            # No `refmod` row of its own: saved references here are H3's
            # files in H3's space (`declare.REFMOD`), and the cast is H3's
            # (`cast_as`), so a member on this family is drawn on MiniMax H3's
            # tab and saved, sent and dressed there.
        },
        "prompt": {
            "pipeline": declare.PROMPT_PIPELINE,
            "ordinal": "<Picture N>",
            "max_refs": still.REFS_LIMIT,
        },
    }

"""MiniMax H3 Image's manifest. The values are `families/h3image/still.py`'s
and the shared image-still constants; this module only puts controls behind
them.
"""

from ... import compile_image, render_image
from .. import manifest as m
from . import declare, still


def _widgets():
    row = still.H3IMAGE_ROW
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
# needles the guess fills an empty field from; `avoid` keeps the H3 *video*
# files out, which share every needle but "image".
_UI = {
    "model": {
        "title": "Checkpoint",
        "help": "MiniMax H3 Image — the pruned DiT, distilled to six steps. bf16, int8 or w4a8; all load here.",
        "hints": ["minimax_h3_image"],
        "avoid": [],
    },
    "clip": {
        "title": "Text encoder",
        "help": "Qwen3-VL 32B, loaded as CLIPLoader type 'minimax' — the same file H3 video reads. It reads the pictures as well as the sentence, so the text-only cut will not do.",
        "hints": ["qwen3vl_32b_minimax_h3", "qwen3vl_32b"],
        "avoid": [],
    },
    "vae": {
        "title": "VAE",
        "help": "The MiniMax H3 Image VAE — the H3 encoder with a single-frame decoder. The H3 video VAE will not decode these latents.",
        "hints": ["minimax_h3_image_vae"],
        "avoid": [],
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
        "description": "MiniMax H3 Image — MiniMax's image model, at 4 to 20 MP. Draws from prose, edits from "
                       "any number of pictures, and inpaints under a matte. Six distilled steps at cfg 1.",
        "produces": sorted(declare.PRODUCES),
        # The pre-stage blob key the old H3 still kept its Creator-shaped
        # request under — the same word as this family's arch, frozen in saved
        # blobs. Served so `state.js`'s `migratePreStage` lifts it the way
        # `still.migrate` does without the frontend naming a family.
        "legacy_still_block": still.ARCH,
        "widgets": _widgets(),
        "weights": _weights(),
        "canvas": compile_image.manifest_canvas(still),
        "capabilities": {
            "refine": False, "face": False, "audio": False, "seams": False,
            "init_image": {"default_denoise": compile_image.DEFAULT_DENOISE,
                           "min_denoise": compile_image.MIN_DENOISE},
            # References on the base weights, Picture 1 the one an edit
            # changes — Qwen Image Edit's arrangement, without its editions.
            "refs": {"methods": [], "default_method": None,
                     "needs_lora": False, "edits_first": True,
                     "noun": list(still.REFS_NOUN),
                     "edit_first": compile_image.EDIT_FIRST_FIELD},
            # Saved references in this family's own space — `declare.REFMOD`.
            # `notes` are the menu's words for this family's modes, where
            # H3's own (a 48-grid, a 1024 edge) would be wrong.
            "refmod": {**declare.REFMOD, "notes": {
                "compressed": "Pooled to a 64-grid on the long edge and refined "
                              "against the full encode — about a quarter of a 2048 "
                              "picture's tokens. Unmeasured against the picture yet.",
                "full": "The reference MiniMax H3 Image anchors for the picture, at "
                        "up to a 2048 short edge. The same tokens as the picture: "
                        "it only pins the encode.",
            }},
            # The guide is a mask: the bench's matte, which the sampler reads
            # as its noise mask over Picture 1. `method: "mask"` tells the
            # pre-stage there is no branch file and no strength to show.
            "control": {
                "method": "mask",
                "slot": None,
                "tracings": list(still.CONTROL_TRACINGS),
                "kind": "image",
                "stops": {},
            },
        },
        "prompt": {
            "pipeline": "plain",
            "ordinal": "<Picture N>",
            "max_refs": still.REFS_LIMIT,
        },
    }

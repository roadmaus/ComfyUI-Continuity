"""Flux 2 Klein's manifest. The values are `families/flux2klein/still.py`'s
and the shared image-still constants; this module only puts controls behind
them.
"""

from ... import compile_image, render_image
from .. import manifest as m
from . import declare, still


def _widgets():
    base = still.KLEIN_BASE
    # No scheduler control: the schedule is `Flux2Scheduler`'s, a function of
    # the steps and the canvas, and a combo nothing reads is the one thing a
    # declared row can get worse than a handwritten one.
    return [
        m.widget("steps", "stepper", label="steps", group="sampler",
                 default=base["steps"], min=1, max=10000, step=1),
        m.widget("cfg", "slider", label="cfg", group="sampler",
                 default=base["cfg"], min=0.0, max=100.0, step=0.1),
        m.widget("sampler_name", "combo", label="sampler", group="sampler",
                 default=base["sampler_name"]),
    ]


# What the weights popover says about each slot — the strings' single home;
# the frontend runs them through t() at render. `hints` are the filename
# needles the guess fills an empty field from; `avoid` disqualifies a file the
# needle would otherwise match. One family covers both sizes, so the hints
# match either and the help says how the pair goes together. The `kv` build is
# avoided by name: it wants a `FluxKVCache` graph this family does not emit yet.
_UI = {
    "model": {
        "title": "Checkpoint",
        "help": "Flux 2 Klein base — the undistilled DiT, ~20 steps at cfg 5. 4B (Apache 2.0) or 9B (non-commercial); pick the Qwen3 encoder that matches the size.",
        "hints": ["flux-2-klein-base", "flux2-klein-base"],
        "avoid": ["kv"],
    },
    "turbo_model": {
        "title": "Turbo checkpoint",
        "help": "Flux 2 Klein distilled — the 4-step file the turbo pill swaps in, published at both sizes.",
        "hints": ["flux-2-klein", "flux2-klein"],
        "avoid": ["base", "kv"],
    },
    "clip": {
        "title": "Text encoder",
        "help": "Qwen3, loaded as CLIPLoader type 'flux2' — the text-only cut is the right one here; references reach the model as latents, not vision tokens. Match the checkpoint: qwen_3_4b with the 4B, qwen_3_8b with the 9B.",
        "hints": ["qwen_3_4b", "qwen_3_8b"],
        "avoid": [],
    },
    "vae": {
        "title": "VAE",
        "help": "The Flux 2 VAE — the same file Ideogram loads. full_encoder_small_decoder, the edit templates' faster decode, loads here too.",
        "hints": ["flux2-vae", "full_encoder_small_decoder"],
        "avoid": [],
    },
}


def _weights():
    return [render_image.manifest_weight(name, _UI[name],
                                        gguf=name in ("model", "turbo_model", "clip"))
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
        # Both the declaration's, so the id a route answers to and the name a
        # pill shows have one home apiece.
        "id": declare.ID,
        "label": declare.LABEL,
        "description": "Flux 2 Klein — BFL's compact Flux 2, at 4B (Apache 2.0) or 9B (non-commercial). "
                       "Draws from prose and edits from pictures natively; the turbo pill swaps in the "
                       "4-step distilled checkpoint.",
        "produces": sorted(declare.PRODUCES),
        "widgets": _widgets(),
        "weights": _weights(),
        "canvas": _canvas(),
        "capabilities": {
            "refine": False, "face": False, "audio": False, "seams": False,
            "init_image": {"default_denoise": compile_image.DEFAULT_DENOISE,
                           "min_denoise": compile_image.MIN_DENOISE},
            # A checkpoint and only a checkpoint: BFL publishes the
            # distillation as its own file and no LoRA extraction of it, so
            # the pill throws the file — Krea's arrangement minus the LoRA.
            "turbo": {"steps": dict(still.TURBO_STEPS),
                      "row": dict(still.KLEIN_TURBO),
                      "default_quality": still.DEFAULT_TURBO_QUALITY,
                      "lora": False,
                      "checkpoint": True},
            # References with no adapter and no layout to pick: the base
            # weights read the `ReferenceLatent` chain natively. `edits_first`
            # says the first picture *can* be the one edited in place — the
            # `edit_first` blob field asks for it, and the canvas follows the
            # picture then — exactly Qwen Image Edit's arrangement. No
            # editions: every published Klein reads the same chain.
            "refs": {"methods": [], "default_method": None,
                     "needs_lora": False, "edits_first": True,
                     "noun": list(still.REFS_NOUN),
                     "edit_first": compile_image.EDIT_FIRST_FIELD},
            # Saved references in the Flux 2 VAE's space — `declare.REFMOD`,
            # the table the make route encodes by and the ledger offers from.
            "refmod": dict(declare.REFMOD),
        },
        "prompt": {
            # Plain prose; references are cited as the pack's shared slot
            # labels, which the model reads as ordinary language.
            "pipeline": "plain",
            "ordinal": "Picture N",
            "max_refs": still.REFS_LIMIT,
        },
    }

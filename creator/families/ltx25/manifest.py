"""LTX 2.5's manifest: the declarations behind every control the frontend draws
for this family.

The same rule H3's manifest follows — nothing here is a second copy of a
number. The sampler defaults are `families/ltx25/sampling.py`'s, the slots are
`families/ltx25/models.py`'s, the canvas is `declare.RULES`. The bounds are the
core nodes' own (`LTXVScheduler`, `LTXVDualCFGGuider`), read off their schemas
in `comfy_extras/nodes_lt.py`.

What this family declares that H3 does not, and the reverse, is the case
`families/manifest.py` exists for. There is no `routes` block: one transformer,
so there is no checkpoint for a payload to be routed between. There is no
`still` block: LTX 2.5 renders video and the pre-stage never reaches for it.
And there is a `duration` capability H3 has no answer to at all — the duration
head predicting a shot's length from its own prompt.

The `guidance` group is the other thing only this family has. H3's extra passes
are accelerators, which buy time and spend quality; these spend time and buy
quality, so they are drawn apart from the accelerator row and say what they
cost.
"""

from ... import canvas, compile, models as core
from .. import manifest as m
from . import models, sampling
from . import declare


def _widgets():
    d = sampling.DEFAULTS
    return [
        m.widget("steps", "stepper", label="steps", group="sampler",
                 default=d["steps"], min=1, max=10000, step=1,
                 help="8 is the distilled transformer's fixed schedule. The dev transformer wants ~20."),
        m.widget("video_cfg", "slider", label="video cfg", group="sampler",
                 default=d["video_cfg"], min=0.0, max=100.0, step=0.1,
                 help="The picture's guidance scale. 1 on the distilled weights, ~3 on the dev transformer."),
        m.widget("audio_cfg", "slider", label="audio cfg", group="sampler",
                 default=d["audio_cfg"], min=0.0, max=100.0, step=0.1,
                 help="The soundtrack's own scale — the AV latent is packed, and the two modalities are guided apart. 1 on the distilled weights, ~7 on the dev transformer."),
        m.widget("sampler_name", "combo", label="sampler", group="sampler",
                 default=d["sampler_name"]),
        m.widget("max_shift", "slider", label="max shift", group="sampler",
                 default=d["max_shift"], min=0.0, max=100.0, step=0.01,
                 help="The top of the sigma shift, which the scheduler scales by the latent's token count. The model patch is given the same pair; they are two readings of one curve."),
        m.widget("base_shift", "slider", label="base shift", group="sampler",
                 default=d["base_shift"], min=0.0, max=100.0, step=0.01,
                 help="The bottom of the sigma shift. See 'max shift'."),
        m.widget("stretch", "toggle", label="stretch sigmas", group="sampler",
                 default=d["stretch"],
                 help="Stretch the schedule so its final sigma lands on the terminal value."),
        m.widget("terminal", "slider", label="terminal", group="sampler",
                 default=d["terminal"], min=0.0, max=0.99, step=0.01,
                 help="Where a stretched schedule ends. Ignored when stretch is off."),

        # Taste guidance. Its own group because it is its own kind of control:
        # nothing here changes the schedule, and each of them buys picture with
        # time at a rate worth saying out loud. `off` is what makes the pill
        # honest — 0 and 1.0 are core's own "does nothing", and neither is
        # guessable from the range beside it.
        m.widget("stg_scale", "slider", label="detail guidance", group="guidance",
                 default=d["stg_scale"], min=0.0, max=100.0, step=0.1, off=0.0,
                 help="Spatio-temporal guidance: one extra pass per step with the chosen blocks' "
                      "self-attention degraded, guided away from. Sharper spatial detail and "
                      "steadier motion, at roughly double the time of the stage it runs on. "
                      "Lightricks' own reference scale is 1."),
        m.widget("stg_blocks", "text", label="blocks", group="guidance",
                 default=d["stg_blocks"], requires="stg_scale",
                 help="Which transformer blocks detail guidance degrades, comma-separated. 29 is "
                      "the block core's own node points at; leaving this empty switches the "
                      "guidance off however high its scale."),
        m.widget("modality_scale", "slider", label="a/v sync", group="guidance",
                 default=d["modality_scale"], min=1.0, max=100.0, step=0.1, off=1.0,
                 help="Modality guidance: one extra pass per step with the audio-to-video "
                      "cross-attention severed, pushed toward the coupled prediction. Tighter "
                      "lip-sync and sound-to-picture timing, at roughly double the time of the "
                      "stage it runs on. Lightricks' own reference scale is 3."),
    ]


# What the weights popover says about each slot — the strings' single home,
# under the English keys the i18n dictionaries carry (the frontend runs them
# through t() at render). `hints` are the filename needles the guess fills an
# empty field from, `avoid` the patterns that rule a candidate out — the two
# VAEs share `models/vae`, so each has to say what it is not.
_UI = {
    "dit": {
        "title": "Transformer",
        "help": "The 22B DiT. The distilled file samples in 8 steps at cfg 1; the 'dev' file is the "
                "full, trainable one and wants ~20 steps at cfg 3/7. Comfy runs the int8-convrot "
                "builds; the nvfp4 build needs Blackwell.",
        "hints": ["ltx-2.5", "ltx2.5"],
        "avoid": ["upscaler", "duration"],
    },
    "clip": {
        "title": "Text encoder",
        "help": "Gemma 4 12B with LTX's projections — the '-with-proj' file, which carries the audio "
                "and video aggregate embeddings. Loaded as CLIPLoader type 'ltxv'.",
        "hints": ["gemma4-12b-with-proj", "with-proj"],
    },
    "vae": {
        "title": "Video VAE",
        "help": "Decodes the picture. The plain file is the diffusion decoder — sharper faces, "
                "text and texture, and heavier; '-conv-' is the fast one.",
        "hints": ["video-vae", "video_vae"],
        "avoid": ["audio"],
    },
    "audio_vae": {
        "title": "Audio VAE",
        "help": "Decodes the sound, vocoder included. LTX 2.5 generates audio with every render, so "
                "this is never optional.",
        "hints": ["audio-vae", "audio_vae"],
    },
    "duration_head": {
        "title": "Duration head",
        "help": "Optional. Predicts how long a shot wants to be from its own prompt, and snaps the "
                "answer to the frame grid — what the seconds pill's 'auto' asks. Without it the "
                "duration is yours to set, as it always is on H3.",
        "hints": ["duration-head", "duration_head"],
    },
    "upscaler": {
        "title": "Latent upscaler",
        "help": "Optional. The x2 spatial upscaler that is the second stage of Lightricks' own "
                "pipeline: sample at the native edge, upscale the latent, sample again.",
        "hints": ["spatial-upscaler", "latent-spatial"],
        "avoid": ["temporal"],
    },
}


def _weights():
    return [{
        "id": name,
        "folder": slot.folder,
        "label": slot.label,
        # Every slot here becomes a loader; the flag stays because the shape is
        # the frontend's contract, not this family's.
        "loads": bool(slot.loader),
        "routed": slot.routed,
        "audio": slot.audio,
        # Whether a render can go without the file at all — the two opt-in
        # passes. The popover draws a missing required slot in red and an
        # empty optional one as an offer.
        "required": not slot.optional,
        "gguf": slot.folder in core.GGUF_FOLDERS,
        # Asked of the wrapper table rather than assumed: ComfyUI-MultiGPU
        # subclasses the four core loaders, and neither `ModelPatchLoader` nor
        # `LatentUpscaleModelLoader` is one of them.
        "device": slot.loader in core.MULTIGPU,
        # KeyError by design: a slot without its popover strings should fail
        # here, where the family is named, not draw a blank row.
        "title": _UI[name]["title"],
        "help": _UI[name]["help"],
        "hints": _UI[name].get("hints", []),
        "avoid": _UI[name].get("avoid", []),
    } for name, slot in models.SLOTS.items()]


def manifest():
    from .. import registry

    return {
        # Both the declaration's, so the id a route answers to and the name a
        # pill shows have one home apiece.
        "id": declare.ID,
        "label": declare.LABEL,
        # What the family pill's tooltip says this family is.
        "description": "LTX 2.5 — Lightricks' 22B audio-video DiT. Picture and soundtrack come out of one "
                       "packed latent, guided apart; the frame rate is conditioning rather than a property "
                       "of the weights, and an optional duration head can pick a shot's length from its "
                       "own prompt.",
        "produces": sorted(declare.PRODUCES),
        "widgets": _widgets(),
        "weights": _weights(),
        # The payload shape -> the name it goes by on a card. Lightricks' own
        # vocabulary rather than H3's protocol names: this family conditions
        # through `LTXVAddGuide`, so what a card is is which guides its segment
        # node builds.
        #
        # **No `reference` entry, and that is the declaration.** On H3 a
        # reference is a different payload — a different checkpoint, a different
        # encode — so it is a mode. Here it changes nothing the segment node
        # builds: the files ride as `<Picture N>` labels in the prose and
        # nothing is encoded from them (see `segment.py`). A card carrying one
        # says what its guides make it, which is the truth about what will be
        # sampled, and `state.mode` falls through to the frames when a family
        # declares no reference mode.
        "modes": {"opens_closes": "FL2V",
                  "opens": "I2V",
                  "closes": "L2V",
                  "text": "T2V"},
        # The reference grammar. The same numbers and the same vocabulary H3
        # declares, because they are the same code: `compile._derive_mode` and
        # `_parse_assets` are shared, so what a piece on this family may attach
        # is what the compiler will accept from it. That the files then reach
        # the model as prose alone is this family's limitation, said in
        # `segment.py` and in the log — not a different set of caps. When the
        # compiler learns families this block is where the difference lands.
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
        "canvas": m.canvas_block(declare.RULES),
        "capabilities": {
            # The passes the loop may ask this family for. Audio always: LTX
            # 2.5 samples a packed AV latent and there is no soundless mode.
            "audio": True,
            # Chained seams with feathering. Core's reel/spill layer is
            # family-neutral by construction — `LTXVConcatAVLatent`'s own
            # description is what the joint latent was written against.
            "seams": True,
            # The second stage, and it is Lightricks' own rather than H3's:
            # sample at the native edge, run the trained x2 latent upscaler,
            # sample again over a tail of the schedule. So the upscale pill
            # means something different here — the factor is the model's and
            # not the resolution slider's — and it needs the `upscaler` slot
            # filled, which is why the slot is optional and this is a choice.
            "refine": {"kind": "latent_upscale", "factor": 2,
                       "slot": "upscaler"},
            # The face pass is H3's crop-and-repair loop, written against its
            # detector and its re-encode. Untried here, so not offered.
            "face": False,
            # Several shots out of one generation, which 2.5 holds identity
            # across. This pack already has the control for it — merging cards
            # into one pass — so what a family declares is not *whether* it can
            # but how many cuts its own guidance advises: Lightricks says
            # "prefer 2-4 shots in one generation; more cuts usually need
            # clearer, shorter beats per shot". Advice, so the strip marks a
            # longer pass rather than refusing it, exactly as it marks a
            # duration outside the trained range. H3 declares no number because
            # nothing in its guide gives one.
            "multishot": {"advised_max": 4},
            # What this family has that H3 does not. `canDo(piece, "duration")`
            # is what gates the seconds pill's "auto" — the capability is asked
            # rather than an id branched on, precisely so a control can be
            # honest about a family the code predates.
            # The slot is the registry's, not a second spelling of it: the
            # compiler reads that table to decide whether a card's
            # `auto_duration` means anything, and a manifest naming a different
            # slot would be a pill pointing at a file nothing loads.
            #
            # The seconds are the *trained* range rather than the pill's, which
            # is the one place the two differ on purpose: this is the clamp
            # handed to `LTXVDurationPredictor`, and what it bounds is what
            # Lightricks taught the head to say, not what the pill will let a
            # user set by hand.
            "duration": {"slot": declare.DURATION_HEAD,
                         "min_seconds": round(declare.RULES.trained_min_frames
                                              / declare.RULES.fps, 4),
                         "max_seconds": round(declare.RULES.trained_max_frames
                                              / declare.RULES.fps, 4)},
        },
        "prompt": {
            # Plain prose straight through Gemma. No Context-IR: H3's ordinal
            # citation grammar is a property of its own training, and what
            # replaces it here — guides through `LTXVAddGuide`, IC-LoRA
            # references — is still undecided. Read off the registry's table,
            # which is what `compile.py` branches on: a manifest describing one
            # prompt while the compiler composed another would be a UI lying
            # about what the model was sent.
            "pipeline": declare.PROMPT_PIPELINE,
        },
    }

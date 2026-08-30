"""MiniMax H3's manifest: the declarations behind every control the frontend
draws for this family.

Nothing here is a second copy of a number. The sampler row's defaults are
`sampling.DEFAULTS`, the weight slots are `slots.SLOTS`, the canvas rules are
`canvas.py`'s — this module only says which *control* each value is behind,
in the vocabulary `families/manifest.py` defines. The bounds and the help
strings are the node schema's own (`creator_node._schema`), under the same
English keys the i18n dictionaries already carry.
"""

from ... import accel, canvas, compile, guide, models as core, sampling, settings
from .. import manifest as m
from . import declare, grammar, models as slots, refine, still


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
        "help": "Decodes the picture — a shot's, and a pre-stage still's.",
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
                "where the face is, and what the sheet editor asks when you click the "
                "subject to cut out. Needed only when the face pass is on or the "
                "scissors are given clicks.",
        "hints": ["sam3"],
    },
    "cutout": {
        "title": "Background remover",
        "help": "Optional. A BiRefNet matte, from models/background_removal — what the "
                "picker's scissors run to lift a reference's subject off its background, so "
                "the room it was photographed in stops conditioning the render alongside "
                "the face. Loaded when you press them, not when you render.",
        "hints": ["birefnet"],
    },
    "control": {
        "title": "ControlNet branch",
        "help": "Optional. MiniMax-H3-Fun-Controlnet-Union, from models/controlnet — "
                "what the guide pill loads to aim a render at a tracing. One file "
                "covers edges, lines, depth and pose; alibaba-pai's original is ~6.8 GB "
                "in VideoX-Fun naming and core converts it on load, Kijai's pruned "
                "repacks are 4.2 GB (bf16) and 2.3 GB (int8) and load as they are. "
                "Loaded only when a guide is actually on the piece.",
        "hints": ["fun_controlnet_union", "minimax_h3_fun", "controlnet_union"],
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
        "gguf": slot.folder in core.GGUF_FOLDERS,
        # Asked of the wrapper table rather than of the slot list, the way
        # LTX 2.5's manifest asks: ComfyUI-MultiGPU subclasses the core
        # loaders and a family may declare one it does not.
        "device": slot.loader in core.MULTIGPU,
        # KeyError by design: a slot without its popover strings should fail
        # here, where the family is named, not draw a blank row.
        "title": _UI[name]["title"],
        "help": _UI[name]["help"],
        "hints": _UI[name].get("hints", []),
        "avoid": _UI[name].get("avoid", []),
        **({"name": _UI[name]["name"], "when": _UI[name]["when"]}
           if slot.routed else {}),
    } for name, slot in slots.SLOTS.items()]


# What each refine template is for, in the words the pill and the panel share.
# Keyed by `refine.PROMPTING.templates`, so a template with no line here fails
# at `describe` — where the family is named — rather than drawing a bare chip.
_TEMPLATE_HELP = {
    "auto": "follows what is attached: frames pick I2VA / L2VA / FL2VA, "
            "@ references pick REF2VA, a bare prompt picks T2VA.",
    "T2VA": "text only — the video is described from nothing.",
    "I2VA": "first frame — the rewrite opens on the attached image and develops forward.",
    "L2VA": "last frame — the rewrite converges on the attached image at the end.",
    "FL2VA": "first and last frame — the rewrite is the motion path between the two.",
    "REF2VA": "@ references — the six-section form that defines and tracks them. "
              "Pinnable on any request, but without references it may degrade quality.",
}


# The turbo switch: a distillation LoRA over the same checkpoints,
# not a checkpoint swap like Krea's. The declarations here are the
# H3 turbo community's numbers, said once. `row` is what engaging
# the switch sets the sampler to (euler + beta — the joint audio
# warbles on res_multistep at turbo step counts); `reset` is where
# the row returns when the switch is thrown off and nothing was
# saved — the node's own defaults. `presets` name what a distill
# file engages at, by filename match: strength and the flow shifts
# its card was distilled against — lightx2v's runs at ~0.6 with
# the video clock at 6, everything else at 1.0 on the checkpoints'
# own schedule.
#
# Hoisted out of the catalog rather than written inside it because it is the
# longest declaration in this file by a distance, and the catalog reads better
# for having one name where the whole switch used to sit.
TURBO = {
    "steps": {"draft": 4, "medium": 6, "good": 8},
    "default_quality": "medium",
    "row": {"sampler_name": "euler", "scheduler": "beta"},
    "reset": {key: sampling.DEFAULTS[key]
              for key in ("steps", "sampler_name", "scheduler",
                          "shift_video", "shift_audio")},
    "lead_max": settings.MAX_LEAD_IN,
    # A preset may also own the row and the step table. Only one
    # does: alibaba-pai's PDD acceleration files carry a bank of
    # per-interval output heads beside the trunk LoRA
    # (`h3lora/pdd.py`), and those heads were distilled against
    # fixed places on the flow grid. A render lands on them at a
    # step count that divides the 32-interval grid, under the
    # scheduler that walks the grid evenly — 4 or 8 steps on
    # `simple`, which is what the two published counts are. `beta`
    # at six steps is a different schedule and the file quietly
    # stops being what it was trained as, so the switch sets what
    # the file needs rather than what the family usually wants.
    "presets": [{"match": "lightx2v", "strength": 0.6,
                 "shift_video": 6, "shift_audio": 3},
                {"match": r"pdd|acc[-_]?8step", "strength": 1.0,
                 "shift_video": sampling.DEFAULTS["shift_video"],
                 "shift_audio": sampling.DEFAULTS["shift_audio"],
                 "row": {"sampler_name": "euler", "scheduler": "simple"},
                 "steps": {"draft": 4, "medium": 8, "good": 8},
                 "note": "Parallel decoding: this file holds one output head "
                         "per interval of the grid it was distilled against, "
                         "and only steps on them at 4 or 8 steps with the "
                         "simple scheduler."}],
    "default_strength": 1.0,
}


def manifest():
    from .. import registry

    return {
        # Both the declaration's, so the id a route answers to and the name a
        # pill shows have one home apiece.
        "id": declare.ID,
        "label": declare.LABEL,
        # What the arch pill's tooltip says this family is.
        "description": "MiniMax H3 — experimental. The still is a video generation with one latent "
                       "frame decoded as a picture, on the weights, the VAE and the canvas your render "
                       "already uses. No second model family is loaded, and no extra file to fetch.",
        "produces": sorted(declare.PRODUCES),
        "widgets": _widgets(),
        "weights": _weights(),
        # The standing route between the family's checkpoints — the control the
        # weights popover draws beside the slots — and which checkpoint the
        # mode implies. References are encoded *for* Ref2VA, so any @ reference
        # routes there and a pin only exists on the plain side; a timeline
        # defaults to the reference checkpoint outright, the superset training,
        # so a strip mixing reference and plain cards runs on one set of
        # weights. Mirrors `compile._resolve_checkpoint`.
        "routes": {"options": m.value_list(slots.ROUTES),
                   "default": core.DEFAULT_ROUTE,
                   # Which checkpoint each side of the split implies — the
                   # grammar's own routing rule, so the badge the frontend draws
                   # and the checkpoint the compiler derives cannot disagree.
                   "reference": grammar.GRAMMAR.checkpoint(
                       grammar.GRAMMAR.modes["reference"]),
                   "plain": grammar.GRAMMAR.default_route,
                   # A new timeline pins its route to the reference checkpoint
                   # outright: the superset training, so a strip mixing
                   # reference and plain cards runs on one set of weights.
                   "timeline": grammar.GRAMMAR.checkpoint(
                       grammar.GRAMMAR.modes["reference"])},
        # The payload shape -> the name the mode goes by, on cards and in the
        # compiled prompt. "opens" is a first frame or a continuation seam,
        # "closes" a last frame or a cut into a clip — the same reading
        # `compile._derive_mode` makes; test_families holds the names against
        # `compile.MODES`.
        "modes": dict(grammar.GRAMMAR.modes),
        "canvas": m.canvas_block(declare.RULES),
        "capabilities": {
            # The passes the loop may ask this family for. `audio.supplied` is
            # whether a track laid on the piece's sound lane can be *fixed*
            # rather than described — see the same entry on LTX 2.5. True here
            # for the same reason: `_empty_av_latent` builds a nested (video,
            # audio) pair and core masks the two streams separately, so the
            # supplied half can be held out of the denoise.
            "refine": True, "face": True, "audio": {"supplied": True},
            # What the picker needs to make a plate for this family: the field
            # its panels are laid on, whether a fresh pick starts out cut, and
            # which weights slot names the matte. A capability rather than a
            # control every family draws, because all three are facts about the
            # family — see `creator/plate.py` — and because a family with no
            # reference grammar has nothing to lay out. The default is off here:
            # every H3 piece ever saved was rendered against whole reference
            # pictures, and starting cut would change what an unedited workflow
            # generates the day it is opened.
            "cutout": {"default": declare.CUTOUT_DEFAULT,
                       "backdrop": declare.REF_BACKDROP, "slot": "cutout",
                       "segment": "sam3"},
            # Chained seams with feathering — the strip's whole grammar.
            "seams": True,
            # Whether a LoRA on this family can be held off the soundtrack.
            #
            # A capability rather than a control every family draws, because it
            # is a fact about H3's architecture and about the stack that loads
            # it. H3 denoises video and audio jointly through one tower, so an
            # adapter reaches the sound whether or not it was trained to, and a
            # file trained on clips whose audio was silent or scraped emits that
            # under every render. adaLN is the one place the modalities separate
            # cleanly, which is what makes a dial possible at all — see
            # `h3lora/modality.py` and `lora.modality`. LTX 2.5 duplicates its
            # tower per modality and its LoRAs go through core's loader, so
            # there is nothing here for it to answer.
            "lora": {"audio": True},
            # Whether a blended seam can *also* name its boundary frame to the
            # text encoder, on top of the run it pins for the DiT. Off by
            # default and offered as a switch; see `Compiled.feather_pin`.
            #
            # A capability rather than a control every family draws, because it
            # is a fact about how this family conditions: H3 presents pictures
            # to Qwen alongside the prompt, so there is a second channel to say
            # it in. LTX 2.5 sends Gemma text and hands the run to
            # `LTXVAddGuide` — one channel, and the boundary frame is already
            # the run's last element — so there is nothing there to pin twice
            # and no switch worth drawing.
            "seam_pin": True,
            "turbo": TURBO,
            # Whether this family can sample through Raylight's Ray workers —
            # the multi-GPU backend in the weights popover. H3's alone so far,
            # and a fact about the *fork* rather than about the architecture:
            # Karmabu's community fork is the only Raylight that carries an H3
            # sequence-parallel forward, and `creator/raylight.py` is written
            # against its node ids. A family declaring nothing here draws no
            # switch, which is the honest answer for LTX 2.5 — upstream Raylight
            # has an LTX path and this pack has never emitted it.
            "raylight": True,
            # The guide pill: a ControlNet branch loaded beside the checkpoint,
            # aimed at a clip the bench traced. `method` is the whole of what
            # separates this from Qwen-Image-Edit's answer to the same question —
            # there the weights read a tracing arriving in a picture slot and
            # nothing is loaded at all, here there is a file and a node — and it
            # is what lets one pill, one blob block and one loop hook serve both.
            #
            # `tracings` are the bench ids these weights were post-trained on.
            # A fourth one is not refused anywhere: it is a picture, and the
            # render comes out looking like the drawing instead of aimed by it,
            # which is worth a sentence rather than a wall.
            #
            # Absent entirely — not `False` — on a core without the apply node,
            # which is every core until Comfy-Org/ComfyUI#15860 lands. The
            # frontend draws the pill off the block's presence, so the switch is
            # simply not there rather than there and broken.
            **({"control": {
                "method": "branch",
                "slot": "control",
                "tracings": list(declare.CONTROL_TRACINGS),
                # A guide is a clip laid along the piece, not a still: H3's
                # branch conditions a video latent, and a single frame held for
                # six seconds is a shot told not to move.
                "kind": "video",
                "default_strength": guide.DEFAULT_STRENGTH,
                "max_strength": guide.MAX_STRENGTH,
                # How closely the render follows the drawing, as three stops the
                # pill presses — the same shape as the turbo switch's step
                # table, and for the same reason: the number is what reaches
                # the node, and a name is what the person choosing is choosing
                # between. `control_context_scale` in the checkpoint's own card.
                "stops": {"loose": 0.5, "firm": 0.8, "locked": 1.0},
                "default_stop": "firm",
                # Both ends of the schedule window are honoured. Not drawn on
                # the pill: the release point is a real dial and a rarely-moved
                # one, and two more segments would cost the row more than they
                # buy. The blob carries them and `Guide.of` clamps them.
                "schedule": True,
            }} if guide.node_available(declare.CONTROL_NODE) else {}),
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
            "max": {"image": grammar.GRAMMAR.max_images,
                    "video": grammar.GRAMMAR.max_videos,
                    "audio": grammar.GRAMMAR.max_audios,
                    "files": grammar.GRAMMAR.max_files},
        },
        "prompt": {
            # The shot description is composed into the model's documented
            # Context-IR form; references are cited by ordinal. Read off the
            # registry's table rather than spelled here, because `compile.py`
            # branches on the same value and a manifest saying one thing while
            # the compiler did another would be a UI describing a prompt nobody
            # was sent.
            "pipeline": declare.PROMPT_PIPELINE,
            "ordinal": "<Picture N>",
            # What the refiner's template pill offers, and what each choice is
            # for. The names are the prompting's own — a pin is sent back to
            # `Prompting.choose_template`, which is the thing that knows them —
            # and the copy is here because the manifest is where a family's
            # strings live. The pill used to carry this list hardcoded in
            # `refine.js`, which meant every family was offered H3's modes.
            "templates": [
                {"name": name, "help": _TEMPLATE_HELP[name]}
                for name in refine.PROMPTING.templates
            ],
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
            "latent": {"base_frames": declare.RULES.frame_offset,
                       "base_latent": still.latent_frames(declare.RULES.frame_offset),
                       "frame_step": declare.RULES.frame_step,
                       "latent_step": 5},
        },
    }

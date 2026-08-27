"""The files H3 loads, and how — the family's whole weights declaration.

The `Slot` vocabulary is `creator/models.py`'s and so is everything that reads a
table written in it: `Weights` reads the blob against one, `Links` builds the
loaders, `check` refuses a slot nobody filled. What is here is only which slots
this family has.

It was in that module, which was the right place for exactly as long as there
was one family — the shared machinery and H3's table in one file made "what
every family gets" and "what H3 declares" indistinguishable by looking. LTX
2.5's table has always been in its own package; this is H3's, in its.
"""

from ... import models as core
from . import declare

# What CLIPLoader calls the H3 text encoder. Not "minimax_h3": the value is
# uppercased into `comfy.sd.CLIPType.MINIMAX`, and a name that does not resolve
# falls back to STABLE_DIFFUSION and tokenizes the prompt with the wrong
# vocabulary rather than failing.
CLIP_TYPE = "minimax"


# Order matters twice: it is the order the loaders are emitted in — which the
# golden graphs hold — and the order the weights popover lists the fields.
SLOTS = {
    "fl2va": core.Slot("diffusion_models", "the FL2VA checkpoint",
                       loader="UNETLoader", input="unet_name", routed=True),
    "ref2va": core.Slot("diffusion_models", "the Ref2VA checkpoint",
                        loader="UNETLoader", input="unet_name", routed=True),
    "clip": core.Slot("text_encoders", "the text encoder",
                      loader="CLIPLoader", input="clip_name",
                      extra={"type": CLIP_TYPE}),
    "vae": core.Slot("vae", "the video VAE",
                     loader="VAELoader", input="vae_name"),
    "audio_vae": core.Slot("vae", "the audio VAE",
                           loader="VAELoader", input="vae_name", audio=True),
    "preview": core.Slot("vae_approx", "the preview decoder"),
    # The face pass's detector: a SAM3 checkpoint, which is a fused file — model
    # and its own text encoder together — and so is picked from `checkpoints`
    # and loaded by `facepass` itself rather than by a loader emitted here. It
    # is in the table because it is a file the user picks in the same control,
    # not because it becomes a link.
    "sam3": core.Slot("checkpoints", "the face detector"),
    # The matte the *picker* takes, when you press the scissors on a picture.
    # In the table because it is a file the user picks in the same control, not
    # because it becomes a link: no graph this pack builds loads it any more, and
    # `creator/plate.py` reads the name off the piece to run the matte where you
    # can see the result. Optional, and with no `missing` sentence, because a
    # render never asks for it — the picker does, and it says so there.
    "cutout": core.Slot(
        "background_removal", "the background-removal model", optional=True),
    # The Fun ControlNet-Union branch: `control_proj_in` plus five control
    # blocks, loaded on top of whichever checkpoint this generation routes to
    # and injected into it every tenth layer. Core's own `ControlNetLoader`
    # loads it — `load_controlnet_state_dict` detects the branch off
    # `control_proj_in.weight` and converts VideoX-Fun's naming itself — so
    # there is no loader of ours here and must not be.
    #
    # Optional, because a guide is a pass rather than a component: a piece with
    # the guide pill off must not load six gigabytes it will never inject. That
    # is `Links`' lazy-optional path, and the sentence below is what it says
    # when a guide is thrown with nothing picked — which names the pill, because
    # by then the field is not what the user is looking at.
    "control": core.Slot(
        "controlnet", "the ControlNet branch",
        loader="ControlNetLoader", input="control_net_name", optional=True,
        missing="This piece has a ControlNet guide on it and no ControlNet "
                "branch has been picked. Open the node's 'weights' control and "
                "choose a file from models/controlnet — MiniMax-H3-Fun-"
                "Controlnet-Union, or one of Kijai's pruned repacks of it — or "
                "switch the guide pill off."),
}

# The slots a generation routes between — H3's two checkpoints.
ROUTED_SLOTS = [name for name, slot in SLOTS.items() if slot.routed]

# What `route` may hold. "auto" follows the mode, which is what the node has
# always done; the other two are a standing instruction to run everything on one
# checkpoint whatever the mode works out to.
#
# Worth having because the two are one architecture trained twice, and Ref2VA
# turns out to be perfectly capable of the keyframe and text-only payloads FL2VA
# was trained for. The per-request `checkpoint` pin could already say that for one
# generation, but it is not sticky — attaching a reference makes the pin illegal,
# `normalizeCheckpoint` drops it, and removing the reference leaves you back on
# auto. A route survives all of that and applies to every segment of a timeline
# at once.
ROUTES = [core.DEFAULT_ROUTE, *declare.ROUTED]

# Where each file is picked from — the slot table's folder column. These are
# ComfyUI's own folder keys, and the listing route hands the same map to the
# frontend so the two cannot disagree about which directory a field browses.
FOLDERS = {name: slot.folder for name, slot in SLOTS.items()}

# What each field is called when this has to complain about one being unset —
# the slot table's label column.
LABEL = {name: slot.label for name, slot in SLOTS.items()}


def weights_from_blob(data):
    """H3's picks, read against the table above. See `Weights`."""
    return core.Weights.from_blob(data, SLOTS, routes=declare.ROUTED)


def needs(where, audio=True, face=False):
    """The slots an H3 render must have a file for. See ``models.check`.

    The family's own reading of its table, which is what makes the check itself
    family-neutral: the encoder and the video VAE always, the audio VAE unless
    this is the PreStage's still branch decoding picture only, the detector only
    when a pass in this render actually asks for the face pass, and exactly the
    checkpoints the compiled payloads route to — a text-only render never asks
    for the reference weights.
    """
    return ["clip", "vae",
            *(["audio_vae"] if audio else []),
            *(["sam3"] if face else []),
            *sorted(where)]

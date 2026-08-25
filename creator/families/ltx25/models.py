"""The files LTX 2.5 loads, and how.

The same `Slot` vocabulary H3's table is written in (`creator/models.py`), and
deliberately so: "which folder does this pick browse, what does an error call
it, which loader does the graph build" is one question whatever the family, and
the second table is what proves the first one was not five field names wearing
a dataclass.

The shape is one file per slot, which is worth saying because the recipe LTX's
*previous* generation used is not. `LTXAVTextEncoderLoader` and
`LTXVAudioVAELoader` exist for the Gemma-3 pack, where the encoder is two files
and the audio VAE comes out of `checkpoints`; LTX 2.5 ships neither. Verified
against `comfy/sd.py`: the `-with-proj` encoder carries
`text_embedding_projection.video_aggregate_embed.weight`, which the single-file
detection recognises and builds the whole LTXAV encoder from, and the audio VAE
answers to the generic `vocoder.…` detection through the ordinary `VAELoader`.
So both are one pick through a core loader, and the table stays flat.

`type="ltxv"` on the encoder is what the pick *means* rather than what the load
needs: the Gemma-4 branch in `sd.py` does not read `clip_type` at all, having
already decided from the file's own keys. It is declared anyway, because a
widget that says `stable_diffusion` over an LTX encoder is a lie the day core
adds a branch that does read it.
"""

from ... import models as core

# What CLIPLoader calls the encoder. Resolved by `getattr(CLIPType, type.upper())`
# with a silent fallback to STABLE_DIFFUSION, so a name that does not resolve
# tokenizes with the wrong vocabulary rather than failing — see `core.CLIP_TYPE`.
CLIP_TYPE = "ltxv"

# The x2 latent upscaler's loader, and the duration head's. Neither is a slot
# H3 has an equivalent of, and neither has a MultiGPU wrapper — which is why
# `manifest.device` asks the wrapper table rather than assuming every loader
# takes a device.
UPSCALE_LOADER = "LatentUpscaleModelLoader"
PATCH_LOADER = "ModelPatchLoader"

# Order matters twice, as it does for H3: it is the order the loaders are
# emitted in, which the golden graphs hold, and the order the weights popover
# lists the fields.
#
# One DiT and no routing. H3's pair is one architecture trained twice, so a
# payload picks between them; LTX 2.5 ships one transformer in several
# precisions, which is a choice of file rather than a choice of weights, and
# `routes` is absent from this family's manifest for that reason.
SLOTS = {
    "dit": core.Slot("diffusion_models", "the LTX 2.5 transformer",
                     loader="UNETLoader", input="unet_name"),
    "clip": core.Slot("text_encoders", "the text encoder",
                      loader="CLIPLoader", input="clip_name",
                      extra={"type": CLIP_TYPE}),
    "vae": core.Slot("vae", "the video VAE",
                     loader="VAELoader", input="vae_name"),
    "audio_vae": core.Slot("vae", "the audio VAE",
                           loader="VAELoader", input="vae_name", audio=True),
    # Both opt-in, and both a pass rather than a component: the head answers
    # "how long should this shot be" for the seconds pill's auto, and the
    # upscaler is the second stage of Lightricks' own two-stage pipeline.
    # A render that asks for neither never loads either — `models.Links` builds
    # an optional slot the first time something reaches for it, and `missing` is
    # what it says when nothing was picked. The sentence names the pass rather
    # than the field, because by then the field is not what the user has to
    # decide about.
    "duration_head": core.Slot(
        "model_patches", "the duration head",
        loader=PATCH_LOADER, input="name", optional=True,
        missing="A shot on this strip has its length set to 'auto', which asks "
                "LTX's duration head how long it wants to be — and no duration "
                "head has been picked. Choose one under the node's 'weights' "
                "control (models/model_patches), or set that shot's seconds "
                "pill to a length."),
    "upscaler": core.Slot(
        "latent_upscale_models", "the latent upscaler",
        loader=UPSCALE_LOADER, input="model_name", optional=True,
        missing="This piece is set to render in two stages, which on LTX 2.5 "
                "means Lightricks' x2 latent upscaler — and no upscaler has "
                "been picked. Choose one under the node's 'weights' control "
                "(models/latent_upscale_models), or set the upscale pill to "
                "'direct' to sample at one size."),
}

# Where each file is picked from — the slot table's folder column.
FOLDERS = {name: slot.folder for name, slot in SLOTS.items()}

# What each field is called when this has to complain about one being unset.
LABEL = {name: slot.label for name, slot in SLOTS.items()}

# The slots a render can never go without. Every loader that is not optional;
# `audio_vae` is on the list and drops off it on a soundless render, the same
# way H3's does.
REQUIRED = [name for name, slot in SLOTS.items()
            if slot.loader and not slot.optional]

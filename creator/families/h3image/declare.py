"""What MiniMax H3 Image is, before anything of it is imported.

See `families/h3/declare.py` for why this is its own module.
"""

ID = "h3image"
LABEL = "MiniMax H3 Image"

# Last in the pill, where the H3 still always sat: the pill's "minimax" entry
# has been this family's since the image weights arrived, and moving it would
# reorder a list people have learned.
ORDER = 8

# Still only — see krea2's declaration for what an absent RULES means. The
# video family no longer answers for stills at all: what used to be a video
# generation with one latent frame decoded is this model now.
PRODUCES = frozenset({"still"})
RULES = None

# What this family's stills are called under `continuity/stills/h3image/`.
OUTPUT_STEM = "H3Image"

# The pre-stage arch pill's id for it. **"minimax", not the family id**, and
# that is the one exception in the registry: "minimax" is frozen in every
# pre-stage blob ever saved, and it meant "the MiniMax still" long before it
# meant a particular way of making one. Those blobs open on this family —
# `still.migrate` lifts the old branch's request into the shared fields — so a
# saved workflow keeps rendering a MiniMax still rather than failing to compile.
STILL_ARCH = "minimax"

# Saved references (`creator/refmod.py`), in H3's own space: the image VAE is
# the H3 video encoder with a 2D decoder put after it (core's `H3ImageVAE`
# subclasses the video VAE, same latent mean and std, same /16 grid), so a mod
# made for MiniMax H3 is already the latent this family's conditioning node
# would have anchored — one file serves both, and a member saved on either tab
# reads as saved on the other. Made the way H3 makes a still's. No clips: an
# image model has no time axis to lay one along, and the reference blocks it
# reads are `image` ones.
REFMOD = {"space": "h3_video", "edge": 1024, "grid": 48, "clips": False}

PROMPT_PIPELINE = "plain"
LORA_STACK = "core"
DURATION_HEAD = None
ROUTED = ()

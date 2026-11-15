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

# Saved references (`creator/refmod.py`), in a space of this family's own.
# The image VAE has the H3 video encoder's weights and /16 grid, but an H3
# mod is not this family's reference: core's `H3ImageVAE.encode` samples the
# posterior (seeded) where the video VAE takes its mean, and the conditioning
# node anchors a picture at a 1024-2048 short edge where an H3 mod is made
# at 1024. So a mod here is made the way that node makes a reference block
# (`routes/refmod._encode_h3_image`) and a full one *is* that block. `edge`
# is the node's ceiling. `grid` is what a compressed one is pooled to on its
# long edge: half the full grid of a 2048 picture, a quarter of its tokens —
# the ratio Klein's is, and not yet measured against the picture. No clips:
# an image model has no time axis to lay one along.
REFMOD = {"space": "h3_image", "edge": 2048, "grid": 64, "clips": False}

PROMPT_PIPELINE = "plain"
LORA_STACK = "core"
DURATION_HEAD = None
ROUTED = ()

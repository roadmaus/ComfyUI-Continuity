"""What MiniMax H3 Still is, before anything of it is imported.

See `families/h3/declare.py` for why this is its own module.
"""

ID = "h3still"
LABEL = "MiniMax H3 Still"

# After MiniMax H3 Image, which holds the pill's old "minimax" entry: the two
# MiniMax stills sit side by side, the image model first because it is the one
# a saved pre-stage opens on.
ORDER = 9

# Still only, and its own family rather than a second answer of H3's: it loads
# H3's files through the still side's weights block, compiles from the shared
# pre-stage fields, and files under its own folder. What it shares with H3 is
# the model — see `still.py`.
PRODUCES = frozenset({"still"})
RULES = None

# What this family's stills are called under `continuity/stills/h3still/`.
OUTPUT_STEM = "H3Still"

# The pre-stage arch pill's id for it. Not "minimax": that word is frozen in
# every saved blob and has been MiniMax H3 Image's since those weights
# arrived, so a pre-stage saved on the old one-frame branch goes on opening
# there. This branch is picked, not migrated to.
STILL_ARCH = "h3still"

# Saved references in H3's own space, because this *is* H3's VAE and H3's
# reference path: a member saved for a shot is read here from the same file,
# and one saved here serves the shot. No clips — a still's references are
# pictures.
REFMOD = {"space": "h3_video", "edge": 1024, "grid": 48, "clips": False}

# The model's trained prompt form, composed by H3's own grammar — see
# `still.segment_payload`.
PROMPT_PIPELINE = "context-ir"
# H3's stack, patched on by H3's segment node: every LoRA made for the video
# model lands on the weights it was trained against.
LORA_STACK = "h3lora"
DURATION_HEAD = None
ROUTED = ()

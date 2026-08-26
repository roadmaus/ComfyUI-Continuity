"""What Ideogram 4.0 is, before anything of Ideogram 4.0's is imported.

See `families/h3/declare.py` for why this is its own module.
"""

ID = "ideogram4"
LABEL = "Ideogram 4.0"

ORDER = 4

# Still only. There is no duration, no frame grid and no seam, which is why
# `RULES` is None: a family with nothing to snap a frame count to has no canvas
# arithmetic to declare, and `registry.rules` says so by not having an entry.
PRODUCES = frozenset({"still"})
RULES = None

# What this family's stills are called under `minimax/stills/ideogram4/`. See
# `h3/declare.py` for why the stem is declared rather than derived.
OUTPUT_STEM = "Ideogram4"

# The pre-stage arch pill's own id for it, which is the family id: unlike H3's
# "minimax" there was never an earlier spelling to stay compatible with.
STILL_ARCH = "ideogram4"

PROMPT_PIPELINE = "plain"
LORA_STACK = "core"
DURATION_HEAD = None
ROUTED = ()

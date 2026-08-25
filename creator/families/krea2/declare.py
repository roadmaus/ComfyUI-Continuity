"""What Krea 2 is, before anything of Krea 2's is imported.

See `families/h3/declare.py` for why this is its own module.
"""

ID = "krea2"
LABEL = "Krea 2"

ORDER = 3

# Still only. There is no duration, no frame grid and no seam, which is why
# `RULES` is None: a family with nothing to snap a frame count to has no canvas
# arithmetic to declare, and `registry.rules` says so by not having an entry.
PRODUCES = frozenset({"still"})
RULES = None

# The pre-stage arch pill's own id for it, which is the family id: unlike H3's
# "minimax" there was never an earlier spelling to stay compatible with.
STILL_ARCH = "krea2"

PROMPT_PIPELINE = "plain"
LORA_STACK = "core"
DURATION_HEAD = None
ROUTED = ()

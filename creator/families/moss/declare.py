"""What MOSS-Image is, before anything of MOSS-Image's is imported.

See `families/h3/declare.py` for why this is its own module.
"""

ID = "moss"
LABEL = "MOSS-Image"

ORDER = 7

# Still only — see krea2's declaration for what an absent RULES means.
PRODUCES = frozenset({"still"})
RULES = None

# What this family's stills are called under `continuity/stills/moss/`.
OUTPUT_STEM = "MOSS"

# The pre-stage arch pill's own id for it, which is the family id: no earlier
# spelling to stay compatible with.
STILL_ARCH = "moss"

PROMPT_PIPELINE = "plain"
LORA_STACK = "core"
DURATION_HEAD = None
ROUTED = ()

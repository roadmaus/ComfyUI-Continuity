"""What Flux 2 Klein is, before anything of Klein's is imported.

See `families/h3/declare.py` for why this is its own module.
"""

ID = "flux2klein"
LABEL = "Flux 2 Klein"

ORDER = 6

# Still only — see krea2's declaration for what an absent RULES means.
PRODUCES = frozenset({"still"})
RULES = None

# What this family's stills are called under `continuity/stills/flux2klein/`.
OUTPUT_STEM = "Flux2Klein"

# The pre-stage arch pill's own id for it, which is the family id: no earlier
# spelling to stay compatible with.
STILL_ARCH = "flux2klein"

PROMPT_PIPELINE = "plain"
LORA_STACK = "core"
DURATION_HEAD = None
ROUTED = ()

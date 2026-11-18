"""What FLUX 3 Image Klein is, before anything of Klein's is imported.

See `families/h3/declare.py` for why this is its own module.
"""

ID = "flux3klein"
LABEL = "Flux 3 Klein"

# Beside Flux 2 Klein on the pill: ties at the same order break by id.
ORDER = 6

# Still only — see krea2's declaration for what an absent RULES means.
PRODUCES = frozenset({"still"})
RULES = None

# What this family's stills are called under `continuity/stills/flux3klein/`.
OUTPUT_STEM = "Flux3Klein"

# The pre-stage arch pill's own id for it, which is the family id: no earlier
# spelling to stay compatible with.
STILL_ARCH = "flux3klein"

PROMPT_PIPELINE = "plain"
LORA_STACK = "core"
DURATION_HEAD = None
ROUTED = ()

# No REFMOD yet. The references are Flux 2 VAE latents like Flux 2 Klein's,
# so its saved renditions are the right tensors, but how far a pooled grid
# holds up on this model is unmeasured.

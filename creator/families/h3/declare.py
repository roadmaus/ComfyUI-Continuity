"""What H3 is, before anything of H3's is imported.

The declaration `families/registry.py` discovers. Nothing here loads torch,
ComfyUI or the family's own render half — that is the whole reason it is its own
module: `compile.py` has to know which checkpoints a piece routes between and
how its prose reaches the encoder before a loader exists, and importing
`h3/render.py` to find out would pull in the sampler.
"""

from ... import canvas

ID = "h3"
LABEL = "MiniMax H3"

# Where this family sits in every list of them — the family pill's order.
ORDER = 1

# What it renders. H3 answers twice: a still on the pre-stage is a video
# generation one latent frame of which is decoded.
PRODUCES = frozenset({"video", "still"})

# What the pre-stage's arch pill calls this family's still branch. "minimax"
# predates the family ids and is frozen in every saved blob, so the alias is
# permanent — the id it maps to is the registry's business.
STILL_ARCH = "minimax"

# How the prose reaches the text encoder, as one word for the UI to show. H3's
# own training: section headers, `[Shot 2] At 00:05.000` cut lines, a
# `<Picture 1>` glossary defining every attached file. What actually composes it
# is `grammar.py` in this package; this is the label on it.
PROMPT_PIPELINE = "context-ir"

# How LoRAs reach the transformer. The vendored stack in `h3lora/`, which exists
# because the stock path is wrong on the quantized checkpoints nearly everybody
# runs H3 on — a merge that requantizes the adapter into rounding noise, adaLN
# pairs dropped for a basis mismatch, key conventions resolved by guesswork.
# That argument is about H3's weights and nobody else's.
LORA_STACK = "h3lora"

# The weight slot that predicts a shot's own length, or None where the family
# has no answer at all. H3 has none, and a seconds pill offering "auto" here
# would be offering nothing.
DURATION_HEAD = None

# The graph node that is this family's boundary: one self-contained payload in,
# `(model, positive, latent, lead model)` out. A ComfyUI registry key named in
# saved workflows, and frozen for it — the module it is defined in has moved and
# the id has not.
SEGMENT_NODE = "MiniMaxH3TimelineSegment"

# The checkpoints a generation routes between, in the order anything listing
# them shows them. One architecture trained twice, so a payload picks between
# them; a family shipping one transformer declares `()`.
ROUTED = ("fl2va", "ref2va")

# The canvas and duration arithmetic. The provenance of every number:
#
# - 768 px short edge and a 768*1344 area cap are what the open weights are
#   trained with; both scale together off the resolution slider so the
#   constraint keeps its shape at every setting (21:9 stays letterboxed the
#   same way at 384 as at 768).
# - `max_short_edge` is the slider's ceiling, not a statement about the
#   weights — everything above the native edge is off-distribution and the
#   pill says so. There is a reason to offer it anyway: the pre-stage's H3
#   branch decodes one latent frame as a still, where the single-image VAE
#   holds up to around 3 MP, and a 2K checkpoint is expected. A ceiling the
#   hardware and the warning already govern is better than one that has to be
#   raised again the day those weights land.
# - The 9:16..21:9 ratio envelope is the official H3 aspect range.
# - The trained frame range is ~5.2 s to ~15.1 s. Not a limit: the
#   architecture takes any 17n+5 count and clips well past the top do come
#   out; the pair exists so the UI can say when you have left the
#   distribution, which is a different statement from "you cannot".
# - The seconds range is what the pill offers: below a second there is barely
#   a shot, and a minute is about as far as anyone has reported getting a
#   coherent single generation — past it the attention cost stops being worth
#   arguing about.
RULES = canvas.Rules(
    multiple=32,
    fps=24,
    fps_fixed=True,
    native_short_edge=768,
    native_max_pixels=768 * 1344,
    min_short_edge=384,
    max_short_edge=2048,
    min_ratio=9 / 16,
    max_ratio=21 / 9,
    aspects={
        "16:9": 16 / 9,
        "4:3": 4 / 3,
        "1:1": 1.0,
        "3:4": 3 / 4,
        "9:16": 9 / 16,
        "21:9": 21 / 9,
    },
    frame_step=17,
    frame_offset=5,
    trained_min_frames=124,
    trained_max_frames=362,
    min_seconds=1,
    max_seconds=60,
)

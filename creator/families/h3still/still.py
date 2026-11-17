"""One still from the video model: MiniMax H3 sampling a single latent frame.

The pre-stage's other MiniMax family, MiniMax H3 Image, is an image model. This
one is not: it is the H3 *video* weights asked for one frame, which is what the
pre-stage's MiniMax branch was before the image model arrived. It is back
because it is a different picture — the video model's rendering has a
character of its own — and because every LoRA made for H3 video is patched
onto the weights it was trained against, where on the image model it is a
structural fit and a guess (926 of 932 tensors share a name and a shape; what
was learned on a clip is not promised to transfer).

**What changed from the old branch** is how the frame is made, and it is the
method shootthesound's Fizgig H3 Still settled (MIT,
github.com/shootthesound/ComfyUI-Fizgig-H3-Still):

- **One latent frame is sampled, not a clip.** The old branch sampled the
  shortest legal clip — five frames, two latent frames — and threw one away.
  H3's own image convention is a single latent frame, so the sampler is handed
  exactly that (`nodes.ContinuityH3StillLatent`) and the pass costs one frame.
- **The decode replicates it into a group.** The video VAE's decoder has no
  good answer for a lone latent frame; decoded as a full group of five copies
  with one pixel frame kept, it does (`nodes.ContinuityH3StillDecode`). No
  image VAE: the file that decodes the shot decodes the still.

**What did not change** is that the conditioning is the video model's own.
The graph runs H3's segment node, so the prompt is composed into the Context-IR
form the weights were trained on, references are encoded and cached the way a
shot's are (saved references included, in H3's own space), and the LoRA stack
is H3's:

    loaders -> H3 segment -> [preview] -> KSampler -> still decode -> save
                            one-frame latent --^

The segment's own latent output — a clip's — is left unwired, which is Fizgig's
arrangement over core's nodes and holds here for the same reason: a text or a
reference conditioning does not carry the clip's length. Only pinned keyframes
do, and a still has none.

**Compiled twice, on purpose.** The blob is the shared pre-stage shape, so
`compile_still` is `compile_image.compile_prestage` — the cast, the picture
slots, the canvas and the trigger words are the still flow's, as on every
other family — and what comes back is an ordinary `ImagePayload`. The payload
is then written as the one-generation request H3's compiler takes
(`segment_payload`) and compiled by it too, so a request the segment node would
refuse is refused before a loader is built.

**One checkpoint.** FL2VA reads references through the Ref2VA conditioning
well enough that the still workflows use it for edits too, so there is one
field rather than H3's routed pair and it is wired to both of the segment's
sockets. A Ref2VA file works in it as well.

Not here yet: an init image at partial denoise, and a ControlNet guide. Both
refuse rather than render without the thing asked for.
"""

import re
import sys

from . import declare

ARCH = declare.STILL_ARCH
REFMOD = declare.REFMOD

# One DiT, the encoder, the VAE. No audio VAE: the sampled latent's audio half
# is noise the decode never reads, and a still's references are pictures.
FIELDS = ("model", "clip", "vae")

# The *video* VAE — the file a shot is decoded with. MiniMax H3 Image's VAE
# has a single-frame decoder for that model's latents and is the wrong file
# here, which `vaekind` refuses by name.
VAE_KIND = "h3_video"

# The same Qwen3-VL 32B encoder H3 reads prose and pictures through.
CLIP_TYPE = "minimax"

# References are native: H3's reference conditioning, on the base weights.
TAKES_REFS = True
REFS_NOUN = ("picture", "pictures")
REFS_CITATION = "<Picture {n}>"
REFS_NEED_VISION = True

# H3's own cap on reference pictures (`h3.grammar.H3Grammar.max_images`),
# written out because this module is loaded by the pure suites without the
# video compiler; `tests/test_families.py` holds the two together.
REFS_LIMIT = 9
REFS_LIMIT_REASON = "nine is as many reference pictures as MiniMax H3 reads"

# `Picture 1` can be the picture an instruction changes, and with `edit_first`
# it decides the canvas. The render still starts from noise: the picture
# reaches the model as a reference, exactly as on MiniMax H3 Image.
EDITS_FIRST_REF = True

# The canvas. The /32 grid is the DiT's: it patches 2x2 over a /16 latent, so
# both latent sides have to be even. The range is the one the one-frame method
# was shown at — weak under about 3 MP, good to about 8 (3872x2176), which is
# far past what the same weights hold across a whole clip. The slider's floor
# is the shared one, for a draft; the ratio envelope is H3's.
CANVAS = {
    "multiple": 32,
    "min_short_edge": 512,
    "max_short_edge": 2176,
    "max_long_edge": 4096,
    "default_short_edge": 1280,
    "max_pixels": 3872 * 2176,
    "min_ratio": 9 / 21,
    "max_ratio": 21 / 9,
}

# The row. The pruned checkpoints sample at cfg 1 — the negative is never
# evaluated — and the still workflows run `er_sde` on the simple schedule: 50
# steps on the bare checkpoint, 20 under the Turbo LoRA at a strength of 0.38.
# That last number is the still recipe's and not the LoRA's own (strength 1,
# 4-8 steps, for video); the lower stops are for drafts and are not anybody's
# published row. A checkpoint with the distillation merged in (a hybrid H3
# merge) throws the same switch with no LoRA: the step table and the row, and
# nothing in the stack.
H3STILL_ROW = {"steps": 50, "cfg": 1.0, "sampler_name": "er_sde", "scheduler": "simple"}
TURBO_STEPS = {"draft": 12, "medium": 16, "good": 20}
DEFAULT_TURBO_QUALITY = "good"
DEFAULT_TURBO_STRENGTH = 0.38
TURBO_ROW = {"cfg": 1.0, "sampler_name": "er_sde", "scheduler": "simple"}
TURBO_NEEDS_LORA = (
    "MiniMax H3 Still's turbo is a Turbo LoRA over the checkpoint, or a "
    "checkpoint with the distillation merged in — pick the LoRA or the merged "
    "choice, or leave the switch off and sample the full row"
)

# No guide: H3's Fun ControlNet branch is a video family's hook, and nothing
# here loads it.
CONTROL_TRACINGS = ()

INIT_REFUSAL = (
    "MiniMax H3 Still starts from noise and cannot start from a picture yet — "
    "attach the picture as Picture 1 and say what changes, or take the init "
    "image off"
)

# The nodes this branch renders through. The segment node is H3's; the other
# two are this family's (`nodes.py`).
SEGMENT_NODE = "MiniMaxH3TimelineSegment"
LATENT_NODE = "ContinuityH3StillLatent"
DECODE_NODE = "ContinuityH3StillDecode"

# The clip the request names. A still samples no clip — the latent is one
# frame, built here and not by the segment node — but the request is one of
# H3's, and H3's compiler wants a length: the shortest legal one, which is
# also what the Context-IR's duration line then says.
REQUEST_FRAMES = 5
FPS = 24

# A reference as the shared compile cites it, for writing the citation back
# as the handle H3's compiler resolves.
_CITED = re.compile(r"<Picture (\d+)>")


def _handle(slot):
    return f"pic-{slot + 1}"


def plan(data):
    """-> (checkpoint field, schedule). One file either way: the turbo pill is
    a LoRA on it, or says the file carries the distillation itself (`merged`)."""
    from ...compile import CompileError
    from ...compile_image import turbo_block

    turbo = turbo_block(data, ARCH)
    if turbo.get("on") and not turbo.get("lora") and not turbo.get("merged"):
        raise CompileError(TURBO_NEEDS_LORA)
    return "model", {}


def max_refs(data):
    """`(references this render may carry, why)` — see `REFS_LIMIT`."""
    return REFS_LIMIT, REFS_LIMIT_REASON


def request_of(payload):
    """An `ImagePayload` -> the request H3's compiler takes for one generation.

    The pictures become reference assets in slot order, each under a handle of
    this module's making, and every `<Picture N>` the shared compile wrote is
    written back as that handle — so H3's compiler numbers the references
    itself, defines each one in the prompt the way it does for a shot, and the
    numbers cannot disagree with the ones the encoder assigns. A `<Picture N>`
    naming no slot was typed by hand and is left as it was typed.

    The LoRAs go in as the reduced entries the payload holds: name and
    strength, with no checkpoint modes, because there is one checkpoint here
    and a LoRA picked for a still is meant for it. Their trigger words are
    already in front of the sentence.
    """
    from ... import refmod

    count = len(payload.refs)

    def cite(match):
        slot = int(match.group(1)) - 1
        return f"@{_handle(slot)}" if 0 <= slot < count else match.group(0)

    assets = []
    for slot, filename in enumerate(payload.refs):
        asset = {"handle": _handle(slot), "kind": "image", "role": "reference",
                 "filename": filename}
        framed = (payload.framing or {}).get(f"ref:{slot}")
        if framed:
            asset["crop"] = framed["crop"]
        mod = (payload.mods or {}).get(slot)
        if mod and not refmod.is_mod(filename):
            asset["mods"] = {REFMOD["space"]: mod}
        assets.append(asset)
    return {
        "prompt": _CITED.sub(cite, payload.prompt),
        "assets": assets,
        "loras": [{"name": entry["name"], "strength": entry["strength"]}
                  for entry in payload.loras],
        "duration_s": REQUEST_FRAMES / FPS,
        "short_edge": min(payload.width, payload.height),
        # One pass at the canvas asked for: there is no refine pass to hand a
        # smaller first one to.
        "upscale": "direct",
    }


def segment_payload(payload):
    """The segment node's payload for this still: the request, and the canvas
    pinned to the one the still flow resolved — its range is this family's
    (`CANVAS`), not the video rules' the request would otherwise be held to."""
    from ... import canvas
    from ...families import registry

    ratio = payload.width / payload.height
    return {
        "request": request_of(payload),
        "continue": False,
        "continue_audio": False,
        "canvas": {
            "width": payload.width, "height": payload.height, "ratio": ratio,
            "label": canvas.describe_ratio(ratio, registry.RULES[registry.DEFAULT_VIDEO]),
            "from_image": False, "clamped": bool(payload.ratio_clamped),
        },
    }


def compile_still(data, image_size_lookup=None):
    """The uniform still surface — see `families/registry.py`.

    The shared flow first, then H3's own compiler over what it produced, for
    its refusals: everything the segment node would raise at render time is
    raised here instead.
    """
    from ... import compile as compiler, compile_image

    payload = compile_image.compile_prestage(data, sys.modules[__name__],
                                             image_size_lookup)
    if payload.init is not None and payload.init["denoise"] < 1.0:
        raise compiler.CompileError(INIT_REFUSAL)
    compiler.compile_segment(segment_payload(payload), image_size_lookup)
    return payload


def require_support():
    """Refuse a core without native MiniMax H3 — keyed off the encoder type
    `CLIPLoader` learned with it, as the other families key off theirs."""
    import nodes

    declared = nodes.NODE_CLASS_MAPPINGS["CLIPLoader"].INPUT_TYPES()
    types = declared.get("required", {}).get("type", [[]])[0]
    if CLIP_TYPE not in types:
        raise ValueError(
            "This ComfyUI does not know MiniMax H3 yet (CLIPLoader has no "
            "'minimax' type). Update ComfyUI and restart."
        )


def require_control():
    """Never reached: this family declares no tracings, so no still compiles
    with a guide on it."""


def emit(payload, weights, sampling, unique_id, filename_prefix):
    """-> the graph, which the caller finalizes with `core.emit.expanded`."""
    import json

    from comfy_execution.graph_utils import GraphBuilder

    from ... import models as core, render_image, settings

    module = sys.modules[__name__]
    require_support()
    render_image.check(weights, payload, module)
    render_image.check_vision(weights, payload, module)
    sampling = render_image.edit_seed(sampling, payload, module)

    graph = GraphBuilder()
    clip = render_image.emit_loader(graph, weights, "clip", type=CLIP_TYPE)
    vae = render_image.emit_loader(graph, weights, "vae")
    model = render_image.emit_unet(graph, weights, payload.checkpoint_field)

    inputs = {
        "clip": clip,
        # sort_keys so an unchanged still serialises identically every time —
        # this string is the segment node's cache key.
        "segment_data": json.dumps(segment_payload(payload), sort_keys=True),
        # One file on both sockets: the node hands back whichever the request
        # routes to, and here that is the same weights either way.
        "model_fl2va": model,
        "model_ref2va": model,
    }
    # The VAE reaches the encoder only when there is a picture to encode, as on
    # a shot: a text-only still needs it at decode alone.
    if payload.refs:
        inputs["vae"] = vae
        inputs["vae_name"] = weights.get("vae") or ""
    # The settings page's loader choice, written only off its default so a
    # machine that never moved it keeps the cache key it had.
    loader = settings.lora_loader()
    if loader != settings.DEFAULTS["lora_loader"]:
        inputs["lora_loader"] = loader
    segment = graph.node(SEGMENT_NODE, **inputs)

    # cfg 1 never evaluates the negative; zeroed, as the video path has it.
    negative = graph.node("ConditioningZeroOut", conditioning=segment.out(1)).out(0)
    model = core.graph_preview(graph, segment.out(0), weights, float(FPS))
    latent = graph.node(LATENT_NODE, width=payload.width, height=payload.height,
                        batch_size=1).out(0)
    sampled = graph.node(
        "KSampler", model=model, positive=segment.out(1), negative=negative,
        latent_image=latent, seed=sampling.seed, steps=sampling.steps,
        cfg=sampling.cfg, sampler_name=sampling.sampler_name,
        scheduler=sampling.scheduler, denoise=1.0,
    )
    image = graph.node(DECODE_NODE, samples=sampled.out(0), vae=vae).out(0)
    image = render_image.refined(graph, image, payload.neural)
    image = render_image.screened(graph, image, payload.screens, unique_id)
    save = graph.node(render_image.SAVE_NODE, images=image,
                      filename_prefix=filename_prefix)
    # The save node lives in an expanded graph on nobody's canvas; the stamp
    # files its result under the PreStage the user is looking at.
    save.set_override_display_id(unique_id)
    return graph


def emit_still(data, plan, sampling, unique_id):
    """The uniform still surface over `emit`."""
    from ... import outputs, render_image, settings

    weights = render_image.ImageWeights.from_blob(data, sys.modules[__name__])
    if plan.arch != weights.arch:
        from ...compile import CompileError

        raise CompileError("the payload and the weights disagree about the architecture")
    return emit(plan, weights, sampling, unique_id,
                filename_prefix=outputs.image(
                    data, settings.image_prefix(declare.ID)))

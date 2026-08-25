"""Blob -> payload for the PreStage image node.

The image counterpart of `compile.py`, and held to the same rule: everything in
here is pure — no torch, no ComfyUI, no disk — so the frontend can mirror these
constants (`state.js`) and the tests can run without a GPU. The blob is the
frontend's serialised state exactly as `creator_data` is; this validates it and
reduces it to the payload `render_image.emit` builds a graph from.

This is the *shared* half. What an architecture decides for itself — its
checkpoint fields, its sampler presets, which files it loads — lives in its
family package (`families/krea2/still.py`, `families/ideogram4/still.py`), and
`compile_prestage` takes that module as `family` and reads its declarations.
What stays here is what every image still shares: the prompt and its triggers,
the style-reference citations, the init image, and the /16 canvas.

Style references are cited from the prompt the way everything else in this pack
is: `@ref-1` is written where the reference belongs in the sentence and becomes
the label the encoder itself gives that slot. Core's
`TextEncodeQwenImageEditPlus` builds `Picture 1: <|vision_start|>...` per image,
so `Picture 1` is what the model is actually reading — the same arrangement the
video compile has with `<Picture N>`, and the same reason: the ordinal is
decided by the payload, not by the user counting slots.

The prompt is plain natural language for both. Ideogram was trained on
structured JSON captions and its hosted magic-prompt expands text into that
schema, but for the art-directed work this pipeline feeds, a clean sentence
prompt reads better than the schema — so the schema is deliberately not
modelled here at all.
"""

from dataclasses import dataclass, field

from .compile import HANDLE_RE, CompileError, collect_triggers
from .families import registry

# The architectures this shared half serves: the families that render nothing
# but stills, asked of the registry rather than written down — H3's still branch
# rides the video compiler instead and so is not one of these.
ARCHES = registry.IMAGE_FAMILIES
DEFAULT_ARCH = "krea2"

# The image DiTs take /16 canvases (their latent is a /8 downsample and both
# empty-latent nodes step by 16) — half as coarse as the video's /32.
CANVAS_MULTIPLE = 16

# Both models are comfortable up to a 2048x2048 area; past it Krea 2's own card
# stops and Ideogram's presets do too. The floor is where either stops making
# usable keyframes for the video pipeline.
MIN_SHORT_EDGE = 512
MAX_SHORT_EDGE = 2048
DEFAULT_SHORT_EDGE = 1024
MAX_PIXELS = 2048 * 2048

# Wider than the video envelope on purpose: a style sheet or a poster is a
# legitimate still even though no H3 render could take its shape.
MIN_RATIO = 1 / 3
MAX_RATIO = 3.0

ASPECT_PRESETS = {
    "16:9": 16 / 9,
    "3:2": 3 / 2,
    "4:3": 4 / 3,
    "1:1": 1.0,
    "3:4": 3 / 4,
    "2:3": 2 / 3,
    "9:16": 9 / 16,
    "21:9": 21 / 9,
}
DEFAULT_ASPECT = "16:9"

# Core's TextEncodeQwenImageEditPlus has three image inputs. The cap is that
# node's shape, mirrored here so the UI refuses a fourth instead of the graph.
MAX_STYLE_REFS = 3

# How much of the init image survives by default when one is attached. The same
# number the img2img tradition has always landed on: enough to keep the
# composition, enough noise to actually restyle it.
DEFAULT_DENOISE = 0.65
MIN_DENOISE = 0.05


@dataclass(frozen=True)
class ImagePayload:
    """What `render_image.emit` needs, and nothing the widgets already carry."""

    arch: str
    prompt: str
    width: int
    height: int
    # Which weights field the DiT loads from — "model" or "turbo_model". Resolved
    # here rather than in the emitter so the payload states which file runs.
    checkpoint_field: str
    loras: list = field(default_factory=list)        # [{"name", "strength"}]
    refs: list = field(default_factory=list)         # filenames, krea2 only
    init: dict = None                                # {"filename", "denoise"} or None
    # Ideogram's schedule shape, None on krea2.
    mu: float = None
    std: float = None
    ratio_clamped: bool = False


def active_image_loras(entries):
    """The entries that will be patched on, in order, as the original dicts.

    The video pipeline's `active_loras` filters by checkpoint mode as well;
    image LoRAs have no such split — one DiT per arch — so this keeps only the
    enabled/strength rules and drops the modes machinery. Original dicts rather
    than a reduced copy so `collect_triggers` can still read them.
    """
    active = []
    for entry in entries or []:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        if entry.get("enabled") is False:
            continue
        try:
            strength = float(entry.get("strength", 1.0))
        except (TypeError, ValueError):
            raise CompileError(f"LoRA {entry['name']}: strength must be a number")
        if strength == 0.0:
            continue
        active.append(entry)
    return active


def clamp_ratio(ratio):
    if ratio < MIN_RATIO:
        return MIN_RATIO, True
    if ratio > MAX_RATIO:
        return MAX_RATIO, True
    return ratio, False


def _snap(value):
    return max(CANVAS_MULTIPLE, int(value / CANVAS_MULTIPLE + 0.5) * CANVAS_MULTIPLE)


def resolve_canvas(ratio, short_edge):
    """(aspect ratio, slider short edge) -> the (width, height) generated.

    Same construction as `canvas.resolve_canvas` at the image models' /16 grid:
    the short edge is what the slider says, the long edge follows the ratio, and
    the area cap steps the long axis back down if snapping pushed past it.
    """
    ratio, _ = clamp_ratio(float(ratio))
    short_edge = max(MIN_SHORT_EDGE, min(MAX_SHORT_EDGE, int(short_edge)))

    if ratio >= 1.0:
        width, height = short_edge * ratio, float(short_edge)
    else:
        width, height = float(short_edge), short_edge / ratio

    if width * height > MAX_PIXELS:
        scale = (MAX_PIXELS / (width * height)) ** 0.5
        width, height = width * scale, height * scale
    # The long side is capped too: 2048 is the models' ceiling per axis, not
    # only as an area, and a 3:1 sheet at a big short edge would sail past it.
    if max(width, height) > MAX_SHORT_EDGE:
        scale = MAX_SHORT_EDGE / max(width, height)
        width, height = width * scale, height * scale

    width, height = _snap(width), _snap(height)
    while width * height > MAX_PIXELS and max(width, height) > CANVAS_MULTIPLE:
        if width >= height:
            width -= CANVAS_MULTIPLE
        else:
            height -= CANVAS_MULTIPLE
    return width, height


def _parse_init(raw):
    if raw is None:
        return None
    if not isinstance(raw, dict) or not raw.get("filename"):
        raise CompileError("the init image entry must carry a filename")
    try:
        denoise = float(raw.get("denoise", DEFAULT_DENOISE))
    except (TypeError, ValueError):
        raise CompileError("the init image strength must be a number")
    # A denoise of 1.0 with an init attached is a t2i render that quietly
    # ignored the image; below the floor it is the image with noise on it.
    # Clamped rather than refused: both ends are slider overshoot, not intent.
    denoise = max(MIN_DENOISE, min(1.0, denoise))
    return {"filename": raw["filename"], "denoise": denoise}


def _parse_refs(raw):
    """The style references, as `[(handle, filename)]` in slot order.

    The handle is what the prompt cites and the position is what the encoder
    labels, so both have to come out of here together — a bare filename list
    could not say which `Picture N` a citation meant.

    A handle is optional: a hand-written blob may carry filenames alone, and a
    reference nothing cites still rides in as a slot. Only a citation needs one.
    """
    refs = []
    for item in raw or []:
        filename = item.get("filename") if isinstance(item, dict) else item
        if not filename or not isinstance(filename, str):
            raise CompileError("every style reference must carry a filename")
        handle = item.get("handle") if isinstance(item, dict) else None
        refs.append((handle if isinstance(handle, str) else None, filename))
    if len(refs) > MAX_STYLE_REFS:
        raise CompileError(
            f"at most {MAX_STYLE_REFS} style references — the Qwen edit encoder "
            f"the model reads them through has exactly three image slots"
        )
    return refs


def _cite_refs(prompt, refs):
    """Replace every `@handle` with the label its slot will carry.

    `Picture N`, 1-based in slot order, because that is the string core's
    `TextEncodeQwenImageEditPlus` writes in front of each image. Plain, not
    `<Picture N>` — the angle brackets are MiniMax H3's convention and this is
    Qwen's.

    A handle-shaped token naming nothing is an error rather than prose left
    alone, exactly as it is in the video compile: it means a reference was
    removed and the sentence still points at it. Ordinary prose survives, since
    only handles that name an attached reference are touched.
    """
    labels = {handle: f"Picture {slot}"
              for slot, (handle, _) in enumerate(refs, start=1) if handle}
    dangling = sorted({h for h in HANDLE_RE.findall(prompt) if h not in labels})
    if dangling:
        raise CompileError(
            "the prompt references " + ", ".join("@" + h for h in dangling)
            + " but no such style reference is attached"
        )
    return HANDLE_RE.sub(lambda m: labels.get(m.group(1), m.group(0)), prompt)


def compile_prestage(data, family, image_size_lookup=None):
    """`prestage_data` dict -> `ImagePayload`, for `family`'s architecture.

    `family` is the architecture's own module — `families/krea2/still.py` or
    `families/ideogram4/still.py` — and supplies everything the flow below does
    not decide: whether references are read, and which checkpoint field and
    schedule shape the blob's arch block resolves to. The caller picked it off
    the blob's `arch`, so an unknown arch is refused there, not here.

    `image_size_lookup(filename) -> (width, height)` supplies the init image's
    dimensions so an img2img render keeps its source's aspect — the same
    adaptive behaviour a keyframe has on the video canvas. Injected for the same
    reason it is in `compile.py`: this module never touches disk.
    """
    if not isinstance(data, dict):
        raise CompileError("prestage_data must be a JSON object")

    prompt = str(data.get("prompt") or "").strip()
    if not prompt:
        raise CompileError("describe the image first — the prompt is empty")

    active = active_image_loras(data.get("loras"))
    loras = [{"name": e["name"], "strength": float(e.get("strength", 1.0))} for e in active]
    # Trigger words in front of the prompt, same construction and same dedup as
    # the video compile — a word only counts if its LoRA is actually in the run.
    triggers = collect_triggers(active)
    if triggers:
        prompt = f"{', '.join(triggers)}, {prompt}"

    refs = _parse_refs(data.get("refs"))
    # Cited before the family check below, so a prompt citing a reference on a
    # family that reads none is refused for the reference rather than for the
    # citation — one mistake, and the one the user actually made.
    prompt = _cite_refs(prompt, refs)
    if refs and not family.TAKES_REFS:
        # Refused rather than dropped, in the family's own words: a render that
        # silently ignored the attached images is the failure this package
        # exists to avoid.
        raise CompileError(family.REFS_REFUSAL)

    init = _parse_init(data.get("init"))

    short_edge = data.get("short_edge", DEFAULT_SHORT_EDGE)
    ratio_clamped = False
    if init is not None and image_size_lookup is not None:
        source_w, source_h = image_size_lookup(init["filename"])
        ratio, ratio_clamped = clamp_ratio(source_w / source_h)
    else:
        aspect = data.get("aspect", DEFAULT_ASPECT)
        try:
            ratio = ASPECT_PRESETS.get(aspect) or float(aspect)
        except (TypeError, ValueError):
            raise CompileError(f"unknown aspect {aspect!r}")
    width, height = resolve_canvas(ratio, short_edge)

    checkpoint_field, mu, std = family.plan(data)

    return ImagePayload(
        arch=family.ARCH, prompt=prompt, width=width, height=height,
        checkpoint_field=checkpoint_field, loras=loras,
        # Filenames alone from here on: the handles did their work above and the
        # graph loads these by name, in this order, into the encoder's slots.
        refs=[filename for _, filename in refs], init=init,
        mu=mu, std=std, ratio_clamped=ratio_clamped,
    )

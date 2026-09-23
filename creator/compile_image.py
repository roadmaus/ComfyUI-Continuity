"""Blob -> payload for the PreStage image node.

The image counterpart of `compile.py`, and held to the same rule: everything in
here is pure — no torch, no ComfyUI, no disk — so the frontend can mirror these
constants (`state.js`) and the tests can run without a GPU. The blob is the
frontend's serialised state exactly as `creator_data` is; this validates it and
reduces it to the payload `render_image.emit` builds a graph from.

This is the *shared* half. What an architecture decides for itself — its
checkpoint fields, its sampler presets, which files it loads — lives in its
family package (`families/krea2/still.py`, `families/ideogram4/still.py`,
`families/qwenedit/still.py`), and `compile_prestage` takes that module as
`family` and reads its declarations. What stays here is what every image still
shares: the prompt and its triggers, the style-reference citations, the init
image, and the /16 canvas.

Style references are cited from the prompt the way everything else in this pack
is: `@ref-1` is written where the reference belongs in the sentence and becomes
the label the encoder itself gives that slot. Core's
`TextEncodeQwenImageEditPlus` builds `Picture 1: <|vision_start|>...` per image,
so `Picture 1` is what the model is actually reading — the same arrangement the
video compile has with `<Picture N>`, and the same reason: the ordinal is
decided by the payload, not by the user counting slots.

The prompt is written as plain natural language for both, and Krea reads it
that way. Ideogram does not: it was trained on structured JSON captions, and
its authors' guide says a plain-text prompt "will not work and will likely
trigger a safety warning" — which is exactly what it did here. So the family
gets a `format_prompt` hook and Ideogram's wraps the prose into the schema
(`families/ideogram4/still.py`); a prompt that already is the schema passes
through untouched.
"""

import re
from dataclasses import dataclass, field

from . import neural, refmod
from .compile import HANDLE_RE, CompileError, collect_triggers, merge_loras
from .families import registry
from .families.h3 import subjects

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

# Six shapes, each offered both ways up. The popover draws them as a grid under
# one orientation switch, so the list growing does not cost a row apiece. 16:9
# stays first: the first entry is what a lookup falls back to.
ASPECT_PRESETS = {
    "16:9": 16 / 9,
    "21:9": 21 / 9,
    "3:2": 3 / 2,
    "4:3": 4 / 3,
    "5:4": 5 / 4,
    "1:1": 1.0,
    "4:5": 4 / 5,
    "3:4": 3 / 4,
    "2:3": 2 / 3,
    "9:16": 9 / 16,
    "9:21": 9 / 21,
}
DEFAULT_ASPECT = "16:9"

# Core's TextEncodeQwenImageEditPlus has three image inputs. The cap is that
# node's shape, mirrored here so the UI refuses a fourth instead of the graph.
MAX_STYLE_REFS = 3
REFS_LIMIT_REASON = ("the Qwen edit encoder the model reads them through has "
                     "exactly three image slots")
# What an attached picture is called, where a family does not say. Style is what
# a reference contributes on the families that carry a look across; a family
# whose references are the subject rather than the look declares its own — see
# `families/qwenedit/still.REFS_NOUN`.
REFS_NOUN = ("style reference", "style references")

# How a cited picture is spelled in the prompt, where a family does not say:
# `Picture N`, the label core's Qwen-edit encoder writes in front of each image
# slot and the one every family read until Qwen Image 2.1's tokenizer arrived
# writing `<imageN>` instead — see `families/qwen21/still.REFS_CITATION`. A
# format with the slot's 1-based number as `n`.
REFS_CITATION = "Picture {n}"

# The blob field that makes an edit family's first picture the thing edited —
# the canvas follows it and the render is fitted to it. Off, an attached picture
# is a reference and nothing more: it reaches the model through the encoder,
# cited by its label, and the aspect pill sets the canvas. Named here rather
# than in the family because the shared flow is what reads it — see the
# promotion in `compile_prestage`. It replaced `start_blank`, which was the same
# switch the other way up: the promotion by default and the flag as the way
# out. Nobody wanted the default — every picture dropped on the node became
# the thing edited, when what the reference models do natively is draw a new
# picture on an empty latent with the pictures read beside the sentence — so
# the old field is not read at all: a blob that carried it gets the new
# default, which is what it was asking for.
EDIT_FIRST_FIELD = "edit_first"

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
    loras: list = field(default_factory=list)        # [{"name", "strength", "uncond"}]
    refs: list = field(default_factory=list)         # filenames, on the families that read them
    # The saved rendition a slot is read from instead of its picture, by slot
    # index: `{0: "refmod:cast/anna.flux2"}`. Only the family's own latent
    # space (`declare.REFMOD["space"]`) is written here — a picture carrying
    # an H3 mod alone is a picture to Klein. The emitter loads the file as a
    # latent (`refmodnode`) where the slot has one, and the picture otherwise.
    mods: dict = field(default_factory=dict)
    init: dict = None                                # {"filename", "denoise"} or None
    # The framing on each picture that has one, keyed "ref:<slot>" / "init":
    # `{"crop": crop.to_dict(...), "size": [w, h]}`, the source size resolved
    # here so the graph can be emitted without a disk. Empty on a render with
    # nothing framed, which keeps every such payload the bytes it was. Read
    # through `render_image.load_picture`.
    framing: dict = field(default_factory=dict)
    # How this family's schedule is shaped for this render — the family's own
    # keys, opaque here. Ideogram's mu/std/polish; Krea's shift ramp. Empty on a
    # family whose schedule the sampler row already states in full.
    schedule: dict = field(default_factory=dict)
    ratio_clamped: bool = False
    # The pixel budget the family's encoder resizes each reference to, on a
    # family that fits the canvas to its encoder (`fit_canvas`); None on the
    # rest. Carried rather than re-derived from the canvas at emit time: the
    # canvas is *made from* the budget, and going back from a /32 canvas to
    # the budget that made it is off by a step on wide aspects.
    ref_resolution: int = None
    # The DLSS 5 refiner over the decoded still, as `neural.Request.as_dict()`,
    # or None when the pill is off. Read off the blob here so the emitters
    # never need the blob — the same reason the checkpoint field is resolved
    # above rather than in the graph.
    neural: dict = None


def neural_block(data):
    """The blob's refiner request as a plain dict, or None while it is off."""
    request = neural.Request.of(data)
    return request.as_dict() if request else None


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


def uncond_strength(entry):
    """The strength a LoRA is patched onto the *unconditional* branch at, on a
    family that samples one — Ideogram's second checkpoint. Absent means the
    same weight as the conditional branch; the row's own workflows run the
    unconditional side lighter (0.4 under 0.9), which is what the slider is
    for. Ignored by a family with one DiT."""
    strength = float(entry.get("strength", 1.0))
    if entry.get("uncond") is None:
        return strength
    try:
        return float(entry["uncond"])
    except (TypeError, ValueError):
        raise CompileError(f"LoRA {entry['name']}: uncond strength must be a number")


def turbo_block(data, arch):
    """The turbo pill's state for `arch`, `{}` where there is none.

    Per-arch like `models`, and for the same reason: the pill does not mean the
    same thing on both sides — Krea's throws a distilled checkpoint or an SVD
    extraction of it, Ideogram's throws a distillation LoRA and has no checkpoint
    to offer — so one shared block would carry one family's file onto the other
    the moment the arch pill moved.

    A blob written before the split carries the flat shape, and is read as Krea
    2's: it was the only family with a turbo pill at all.
    """
    block = data.get("turbo")
    if not isinstance(block, dict):
        return {}
    side = block.get(arch)
    if isinstance(side, dict):
        return side
    return block if arch == "krea2" and "on" in block else {}


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
    init = {"filename": raw["filename"], "denoise": denoise}
    if raw.get("crop"):
        init["crop"] = raw["crop"]
    return init


def _framed(what, filename, raw, image_size_lookup):
    """A picture's framing blob -> the payload's `framing` entry, or None.

    The still families crop in the graph with core's `ImageCrop`, which takes
    pixels, so the source's size is read here — the one place this module
    reaches for the lookup for anything but the canvas.
    """
    from . import crop as framing

    try:
        crop = framing.parse(raw, what)
    except framing.CropError as exc:
        raise CompileError(str(exc)) from exc
    if crop is None:
        return None
    if image_size_lookup is None:
        raise CompileError(f"{what}: a cropped picture needs its size, and none was looked up")
    return {"crop": framing.to_dict(crop), "size": list(image_size_lookup(filename))}


def ref_limit(family, data):
    """`(how many references this render may carry, why that is the number)`.

    Not a constant, because the encoder's three slots are not the only cap in
    play: what a checkpoint was *post-trained* to read is its own number, and on
    Qwen Image Edit it changed between editions — the base weights take one
    picture and the 2509/2511 weights three. A family with one answer for every
    file it loads declares no hook and gets the encoder's shape.
    """
    hook = getattr(family, "max_refs", None)
    return hook(data) if hook else (MAX_STYLE_REFS, REFS_LIMIT_REASON)


def refs_noun(family):
    """`(singular, plural)` for what this family's attached pictures are."""
    return getattr(family, "REFS_NOUN", REFS_NOUN)


def refs_citation(family):
    """The spelling a cited picture takes in this family's prompt."""
    return getattr(family, "REFS_CITATION", REFS_CITATION)


def _parse_refs(raw, limit=MAX_STYLE_REFS, reason=REFS_LIMIT_REASON,
                noun=REFS_NOUN, space=None):
    """The attached pictures, as `[(handle, filename)]` in slot order.

    The handle is what the prompt cites and the position is what the encoder
    labels, so both have to come out of here together — a bare filename list
    could not say which `Picture N` a citation meant.

    A handle is optional: a hand-written blob may carry filenames alone, and a
    reference nothing cites still rides in as a slot. Only a citation needs one.

    Each entry is `(handle, filename, crop, mods)`; `mods` is the picture's
    saved renditions by latent space (`refmod.parse_mods`), `{}` where it has
    none. A mod itself may stand in a slot on a family that keeps them (`space`
    is that family's): a downloaded Klein set has no picture behind it, and it
    is a reference the way a picture is, minus the picture — so it is never
    the init and never framed. On a family that keeps none, `refmod:` is
    refused with the way it does work named.
    """
    refs = []
    for item in raw or []:
        filename = item.get("filename") if isinstance(item, dict) else item
        if not filename or not isinstance(filename, str):
            raise CompileError(f"every {noun[0]} must carry a filename")
        handle = item.get("handle") if isinstance(item, dict) else None
        if refmod.is_mod(filename):
            if not space:
                raise CompileError(
                    f"{'@' + handle if isinstance(handle, str) else filename} is a saved "
                    f"reference, and this family reads none — attach the picture it "
                    f"was made of")
            if isinstance(item, dict) and item.get("mods"):
                raise CompileError(
                    f"{'@' + handle if isinstance(handle, str) else filename}: a saved "
                    f"reference is one rendition already — mods hang on the picture it "
                    f"was made of")
            refs.append((handle if isinstance(handle, str) else None, filename,
                         None, {space: filename}))
            continue
        try:
            mods = refmod.parse_mods(item.get("mods") if isinstance(item, dict) else None,
                                     owner=f"@{handle}: " if isinstance(handle, str) else "")
        except refmod.RefModError as exc:
            raise CompileError(str(exc)) from exc
        refs.append((handle if isinstance(handle, str) else None, filename,
                     item.get("crop") if isinstance(item, dict) else None, mods))
    if len(refs) > limit:
        raise CompileError(f"at most {limit} {noun[0] if limit == 1 else noun[1]} "
                           f"— {reason}")
    return refs


def _cite_refs(prompt, refs, noun=REFS_NOUN, citation=REFS_CITATION):
    """Replace every `@handle` with the label its slot will carry.

    `Picture N`, 1-based in slot order, because that is the string core's
    `TextEncodeQwenImageEditPlus` writes in front of each image. Plain, not
    `<Picture N>` — the angle brackets are MiniMax H3's convention and this is
    Qwen's. Qwen Image 2.1's encoder writes `<imageN>` and its family says so
    through `citation`; the substitution is the same either way.

    A handle-shaped token naming nothing is an error rather than prose left
    alone, exactly as it is in the video compile: it means a reference was
    removed and the sentence still points at it. Ordinary prose survives, since
    only handles that name an attached reference are touched.
    """
    labels = {handle: citation.format(n=slot)
              for slot, (handle, *_) in enumerate(refs, start=1) if handle}
    dangling = sorted({h for h in HANDLE_RE.findall(prompt) if h not in labels})
    if dangling:
        raise CompileError(
            "the prompt references " + ", ".join("@" + h for h in dangling)
            + f" but no such {noun[0]} is attached"
        )
    return HANDLE_RE.sub(lambda m: labels.get(m.group(1), m.group(0)), prompt)


def cast_into_still(data, family_id, space=None, takes_pictures=True):
    """Expand the cast members the prompt names into the still's own terms.

    The image compilers know pictures and a prompt, so a member is written in
    those: `@anna` becomes her first picture cited where her name stood, with
    her description after it — or her description alone where the family is
    sent no picture — and what she wears on this family goes onto the stack
    after the piece's own. One expansion for the two surfaces that draw a
    still with a cast, the PreStage node and the chat's room, so the two
    cannot read a member differently.

    `data` is the still's blob: `subjects` in the cast's shape (`wears` and
    all), `refs` the attached pictures — a member's pictures among them, by
    the handles their `from` lists — and `loras` the stack. `family_id` picks
    the member's row (`subjects.Subject.wears`), `space` the latent space
    the family reads saved references in. -> the blob with the prompt, the
    refs and the stack rewritten; the same dict where there is no cast.

    Which picture: the first of their looks that is attached here and is a
    picture — never a saved reference unless it is in this family's own
    space (`ref["space"]`, which the route stamps off the file's header),
    because a still family loads pictures by name and a latent is not one.
    Sent as pictures, the picture's rendition for this family is passed
    over; sent as words, no picture at all. A member's pictures that nobody
    cites come off the list, the way the video compile cuts them: a picture
    of somebody the prompt never names conditions the render exactly as hard
    as one it does. And on a family that changes the first picture cited,
    a member's picture is never the one changed — it is put after the ones
    cited plain, and where nothing was cited plain the render starts blank.
    `takes_pictures` off is a family that reads none at all: every member is
    their words, and the refusal for the pictures is the family's to give.
    """
    raw = [s for s in data.get("subjects") or [] if isinstance(s, dict) and s.get("handle")]
    if not raw:
        return data
    try:
        cast = subjects.parse(raw, family_id)
    except subjects.SubjectError as exc:
        raise CompileError(str(exc)) from exc
    prompt = str(data.get("prompt") or "")
    cited = subjects.cited(cast, [prompt])
    refs = [dict(r) for r in data.get("refs") or [] if isinstance(r, dict) and r.get("handle")]
    by_handle = {str(r["handle"]): r for r in refs}
    written = set(HANDLE_RE.findall(prompt))

    theirs = {}      # a member's picture handle -> the member
    worn = []
    plain = [r for r in refs if not any(str(r["handle"]) in s.sources for s in cast)]
    picked = []
    for subject in cited:
        picture = None
        if subject.send != "words" and takes_pictures:
            for handle in subject.sources:
                ref = by_handle.get(handle)
                if ref is None:
                    continue
                if refmod.is_mod(ref.get("filename")):
                    if space and ref.get("space") == space:
                        picture = ref
                        break
                    continue
                picture = ref
                break
        text = subject.description
        if picture is not None:
            # Sent as pictures: the picture, and no rendition of it — a still
            # reads only its own space, so none of them is this render's.
            if subject.send == "pictures":
                picture.pop("mods", None)
            if picture not in picked and picture not in plain:
                picked.append(picture)
            stood = f"@{picture['handle']}" + (f" ({text})" if text else "")
        elif text:
            stood = text
        else:
            raise CompileError(
                f"@{subject.handle} has no picture a still can be given here "
                f"and no description — describe them, or cite one of their "
                f"pictures in words.")
        prompt = re.sub(rf"@{re.escape(subject.handle)}\b", stood, prompt)
        worn += [dict(entry) for entry in subject.loras]

    # A picture of theirs the prompt writes by handle stays, whoever they are.
    kept = [r for r in refs if r in plain or r in picked or str(r["handle"]) in written]
    # Plain first, then the members', so an edit family changes what was
    # cited plain and never a look — and starts blank where nothing was.
    ordered = [r for r in kept if r in plain or str(r["handle"]) in written and r not in picked]
    ordered += [r for r in kept if r not in ordered]
    out = {**data, "prompt": prompt, "refs": ordered,
           "loras": merge_loras(data.get("loras") or [], worn)}
    if picked and not any(r in plain or str(r["handle"]) in written for r in kept):
        # Only members' pictures: nothing here is the thing being changed.
        out.pop(EDIT_FIRST_FIELD, None)
    return out


def compile_prestage(data, family, image_size_lookup=None):
    """`prestage_data` dict -> `ImagePayload`, for `family`'s architecture.

    `family` is the architecture's own module — `families/krea2/still.py`,
    `families/ideogram4/still.py`, `families/qwenedit/still.py` — and supplies
    everything the flow below does not decide: whether references are read and
    what one means to the render, and which checkpoint field and schedule block
    the blob's arch block resolves to. The caller picked it off the blob's
    `arch`, so an unknown arch is refused there, not here.

    `image_size_lookup(filename) -> (width, height)` supplies the init image's
    dimensions so an img2img render keeps its source's aspect — the same
    adaptive behaviour a keyframe has on the video canvas. Injected for the same
    reason it is in `compile.py`: this module never touches disk.
    """
    if not isinstance(data, dict):
        raise CompileError("prestage_data must be a JSON object")

    space = (getattr(family, "REFMOD", None) or {}).get("space")
    # The cast, written into the still's own terms first: a member's picture
    # is a reference from here on, their name is its citation, and what they
    # wear on this family is on the stack before the words are collected.
    # A words-only family still reads a Cast member's description. Do not
    # promote their attached photo only to refuse it below as a plain ref.
    data = cast_into_still(data, registry.STILL_ARCHES.get(getattr(family, "ARCH", None)),
                          space, takes_pictures=family.TAKES_REFS)

    prompt = str(data.get("prompt") or "").strip()
    if not prompt:
        raise CompileError("describe the image first — the prompt is empty")

    active = active_image_loras(data.get("loras"))
    loras = [{"name": e["name"], "strength": float(e.get("strength", 1.0)),
              "uncond": uncond_strength(e)} for e in active]
    # Trigger words in front of the prompt, same construction and same dedup as
    # the video compile — a word only counts if its LoRA is actually in the run.
    triggers = collect_triggers(active)
    if triggers:
        prompt = f"{', '.join(triggers)}, {prompt}"
    # A family whose model reads something other than prose says so with
    # `format_prompt` — Ideogram's is the JSON caption schema it was trained
    # on. After the triggers, so a trigger word lands inside the caption.
    format_prompt = getattr(family, "format_prompt", None)
    if format_prompt is not None:
        prompt = format_prompt(prompt)

    refs = _parse_refs(data.get("refs"), *ref_limit(family, data), refs_noun(family), space)
    # Cited before the family check below, so a prompt citing a reference on a
    # family that reads none is refused for the reference rather than for the
    # citation — one mistake, and the one the user actually made.
    prompt = _cite_refs(prompt, refs, refs_noun(family), refs_citation(family))
    if refs and not family.TAKES_REFS:
        # Refused rather than dropped, in the family's own words: a render that
        # silently ignored the attached images is the failure this package
        # exists to avoid.
        raise CompileError(family.REFS_REFUSAL)
    if refs and hasattr(family, "check_refs"):
        # And everything past "does this family read pictures at all", which is
        # the family's own business: whether the adapter that reads them is in
        # the stack, and whether the row this render will sample can do what the
        # instruction asks. Krea 2 is the family with both — see its
        # `check_refs`. Handed the reduced LoRA list, which is already only the
        # entries that will actually be patched on.
        family.check_refs(data, refs, loras)

    init = _parse_init(data.get("init"))
    if (init is None and refs and getattr(family, "EDITS_FIRST_REF", False)
            and data.get(EDIT_FIRST_FIELD) and not refmod.is_mod(refs[0][1])):
        # Asked to edit the first picture in place: it is what the render is
        # fitted to, so it is also the init — the canvas follows its aspect
        # (and on Qwen Image 2.1 its encoder resize, see `fit_canvas`), at a
        # denoise of 1.0 because the instruction reaches the model through the
        # reference conditioning rather than through leftover noise. That is
        # the shape the published Qwen-Image-Edit workflow has, said once here
        # instead of as a second image field the user would have to fill with
        # a picture already attached.
        #
        # Opt-in, not the default. Without the flag an attached picture is a
        # reference like any other — read by the encoder, cited by its label,
        # drawn beside on the canvas the aspect pill asks for — which is the
        # render these weights do natively: "here are three pictures, now make
        # a fourth" is Qwen-Image post-trained, not replaced. An explicit init
        # still wins over the flag; it is the only way to ask for a partial
        # denoise, and a family with a reference pool has no other place to
        # say "keep this composition".
        init = {"filename": refs[0][1], "denoise": 1.0}
        if refs[0][2]:
            init["crop"] = refs[0][2]

    short_edge = data.get("short_edge", DEFAULT_SHORT_EDGE)
    ratio_clamped = False
    framed = {}
    for slot, (_, filename, crop, _mods) in enumerate(refs):
        if refmod.is_mod(filename):
            continue
        entry = _framed(f"picture {slot + 1}", filename, crop, image_size_lookup)
        if entry:
            framed[f"ref:{slot}"] = entry
    # The renditions this family reads: a slot whose picture carries a mod in
    # the family's own latent space is read from the file, and a slot that is
    # a mod outright is too. A picture keeps its picture — the init promotion
    # above and the framing are about the picture, and the latent stands in
    # only where the picture would have been encoded.
    mods = {slot: entry[3][space] for slot, entry in enumerate(refs)
            if space and entry[3].get(space)}
    if init is not None:
        entry = _framed("the init image", init["filename"], init.get("crop"), image_size_lookup)
        if entry:
            framed["init"] = entry

    if init is not None and image_size_lookup is not None:
        from . import crop as framing

        source_w, source_h = framing.size(
            image_size_lookup(init["filename"]),
            framing.parse(init.get("crop"), "the init image"))
        ratio, ratio_clamped = clamp_ratio(source_w / source_h)
    else:
        aspect = data.get("aspect", DEFAULT_ASPECT)
        try:
            ratio = ASPECT_PRESETS.get(aspect) or float(aspect)
        except (TypeError, ValueError):
            raise CompileError(f"unknown aspect {aspect!r}")
    width, height = resolve_canvas(ratio, short_edge)
    ref_resolution = None
    fit = getattr(family, "fit_canvas", None)
    if fit is not None:
        # A family whose encoder resizes the pictures on its own grid fits the
        # canvas to that resize — see `qwen21.still.fit_canvas`. Handed the
        # picture's true ratio only when the canvas was taken off a picture:
        # a preset aspect has no picture the target has to line up with.
        source = ratio if (init is not None and image_size_lookup is not None) else None
        width, height, ref_resolution = fit(width, height, source)

    checkpoint_field, schedule = family.plan(data)

    return ImagePayload(
        arch=family.ARCH, prompt=prompt, width=width, height=height,
        checkpoint_field=checkpoint_field, loras=loras,
        # Filenames alone from here on: the handles did their work above and the
        # graph loads these by name, in this order, into the encoder's slots.
        refs=[filename for _, filename, _, _ in refs], init=init,
        framing=framed, mods=mods,
        schedule=schedule or {}, ratio_clamped=ratio_clamped,
        ref_resolution=ref_resolution, neural=neural_block(data),
    )

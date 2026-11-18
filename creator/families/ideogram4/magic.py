"""Ideogram 4.0's magic prompt: prose in, the JSON caption the model reads out.

Ideogram's weights were trained on structured captions and nothing else, and
their authors say what a plain line does: it "will not work and will likely
trigger a safety warning". `still.format_prompt` keeps a plain line off the
model by wrapping it into the smallest caption the schema allows — the same
sentence as the summary, the background and the one element — which renders,
but hands the model none of the structure it was trained to read. What fills
the structure in is a language model reading Ideogram's own instruction for
the job, which Ideogram publishes as the *magic prompt*
(`magic_prompt/v1.txt`, vendored byte for byte by
`tools/vendor_ideogram_magic.py`; Apache-2.0, licence beside it).

**A second pass, never a fatter first one.** The chat's turn is one small
decision in a fixed reply contract, and this is a 28 KB rule sheet whose answer
is a nested object — the two things `chat.py` keeps out of a turn on purpose.
So the turn writes prose as it always has, the cast is expanded into words the
way the render would expand it, and only then is the prose handed to this
instruction, alone, the way Ideogram's own pipeline hands it a user's idea.
The caption rides on the action, so the render never calls a model and a
retake on a new seed is the same caption.

**What is Ideogram's and what is the pack's.** The instruction and the key
order are Ideogram's: the upstream client reorders every caption into the
order `CaptionVerifier` enforces, drops the `aspect_ratio` the instruction asks
for first (it steers the bboxes, and the model never reads it), and by default
drops the bboxes too. All three are ported here (`canonical`), because this
pack's backends are not upstream's client. What is the pack's are the two
promises a prompt box makes everywhere else — quoted words survive letter for
letter, and a `{a|b}` group stays a choice for the seed — which the upstream
instruction does not know about and which are said in the user turn
(`user_message`) and checked on the answer (`caption`), never by editing the
vendored file.

No ComfyUI, no torch: the request and the reply are ordinary data.
"""

import json
import os
from fractions import Fraction

from ... import variations
from .. import refine

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "magic_prompt")
SOURCE = "v1.txt"

# Upstream's own: every configuration of its magic prompt runs at 1.0 with
# thinking off. A caption is ideation — the instruction asks the model to
# populate a sparse scene — so the chat's cold default is not this pass's.
TEMPERATURE = 1.0


class MagicError(ValueError):
    """A reply that is not a caption this pack will render, said as a sentence.

    Quoted back to the model on the one re-ask, and shown to a person if the
    second answer fails too — the same bargain `chat.ActionError` keeps.

    `broken` is a reply that is not JSON at all, and `where` the stretch of
    it the parse stopped on. Neither goes back to the model: shown its own
    broken reply, or the break in it, a small model copies the mistake
    (`reask`). `where` is for the person, if the second answer breaks too.
    """

    def __init__(self, sentence, broken=False, where=""):
        super().__init__(sentence)
        self.broken = broken
        self.where = where


_sections = {}


def _read():
    """`v1.txt` split at its `[SECTION]` markers, as upstream's `_load_sections` reads it."""
    if not _sections:
        with open(os.path.join(_HERE, SOURCE), "r", encoding="utf-8") as handle:
            raw = handle.read()
        current, lines = None, []
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]") and " " not in stripped:
                if current is not None:
                    _sections[current] = "\n".join(lines).strip()
                current, lines = stripped[1:-1].strip().lower(), []
            else:
                lines.append(line)
        if current is not None:
            _sections[current] = "\n".join(lines).strip()
    return _sections


def system_prompt(pictures):
    """The instruction. `pictures` is always empty: Ideogram reads none."""
    return _read()["system"]


def aspect_ratio(label):
    """The render's aspect label -> the `W:H` of positive integers the
    instruction asks for. A preset is already that; a bare number (the
    compiler accepts one) is written as the nearest small fraction."""
    label = str(label or "").strip()
    if ":" in label:
        return label
    ratio = Fraction(float(label)).limit_denominator(32)
    return f"{ratio.numerator}:{ratio.denominator}"


# Said only when the prose has a group, so a prompt without one is asked
# exactly what Ideogram's own pipeline asks.
GROUPS_NOTE = (
    "The idea contains choices written in braces, like {a|b}: the renderer picks "
    "one alternative per seed. Keep every such group exactly as written — braces, "
    "bars and words — inside the one field where it belongs, write each group "
    "only once, and never choose between its alternatives yourself."
)


def user_message(prose, aspect, pictures):
    """The instruction's own `[USER]` turn, filled in. `pictures` is always
    empty, as for `system_prompt`."""
    template = _read().get("user") or "TARGET IMAGE ASPECT RATIO: {{aspect_ratio}} (width:height)."
    message = template.replace("{{aspect_ratio}}", aspect_ratio(aspect))
    if "{{original_prompt}}" in message:
        message = message.replace("{{original_prompt}}", prose)
    else:
        message = f"{message}\n\n{prose}"
    if variations.has_groups(prose):
        message = f"{message}\n\n{GROUPS_NOTE}"
    return message


def reask(message, reply, problem):
    """The one correction: the request again, and what was wrong.

    A caption that parsed but broke a rule is quoted back with the rule, so
    the fix is an edit. A reply that is not JSON is not: on the lab the 4B,
    shown its own broken caption and the spot it broke, wrote the same
    break again, so it is asked afresh and told only that the JSON did not
    parse.
    """
    if getattr(problem, "broken", False):
        return (f"{message}\n\nYour previous answer could not be used: {problem}\n"
                f"Write the whole caption again as one complete, valid JSON object, "
                f"closing every brace and bracket you open.")
    return (f"{message}\n\nYour previous answer was:\n{reply[:4000]}\n\n"
            f"It could not be used: {problem}\n"
            f"Write the whole JSON object again, corrected.")


# ---- the schema --------------------------------------------------------------
#
# `CaptionVerifier`'s tables. The order is what the model was trained on, and
# `canonical` writes it rather than checking it.

TOP = ("high_level_description", "style_description", "compositional_deconstruction")
STYLE_PHOTO = ("aesthetics", "lighting", "photo", "medium", "color_palette")
STYLE_ART = ("aesthetics", "lighting", "medium", "art_style", "color_palette")
COMPOSITION = ("background", "elements")
ELEMENT = {"obj": ("type", "bbox", "desc", "color_palette"),
           "text": ("type", "bbox", "text", "desc", "color_palette")}
STYLE_PALETTE_MAX = 16
ELEMENT_PALETTE_MAX = 5
BBOX_MAX = 1000


def _ordered(block, order):
    known = [key for key in order if key in block]
    return {key: block[key] for key in (*known, *(k for k in block if k not in order))}


def canonical(data, keep_bboxes=False):
    """A caption as the model was trained to read it: upstream's
    `reorder_caption_keys` and `strip_aspect_ratio_and_bboxes`, on a copy.
    Unknown keys are kept, after the known ones, for `problems` to name."""
    data = json.loads(json.dumps(data))
    if not isinstance(data, dict):
        return data
    data.pop("aspect_ratio", None)
    style = data.get("style_description")
    if isinstance(style, dict) and ("photo" in style) != ("art_style" in style):
        data["style_description"] = _ordered(style, STYLE_PHOTO if "photo" in style else STYLE_ART)
    composition = data.get("compositional_deconstruction")
    if isinstance(composition, dict):
        composition = _ordered(composition, COMPOSITION)
        elements = composition.get("elements")
        if isinstance(elements, list):
            tidy = []
            for element in elements:
                if isinstance(element, dict):
                    if not keep_bboxes:
                        element.pop("bbox", None)
                    if element.get("type") in ELEMENT:
                        element = _ordered(element, ELEMENT[element["type"]])
                tidy.append(element)
            composition["elements"] = tidy
        data["compositional_deconstruction"] = composition
    return _ordered(data, TOP)


def _palette(value, where, most, out):
    if not isinstance(value, list):
        out.append(f"{where} must be a list of colours")
        return
    if len(value) > most:
        out.append(f"{where} has {len(value)} colours; at most {most}")
    for colour in value:
        if not (isinstance(colour, str) and len(colour) == 7 and colour[0] == "#"
                and all(c in "0123456789ABCDEF" for c in colour[1:])):
            out.append(f"{where} holds {json.dumps(colour)}, which is not an uppercase #RRGGBB colour")
            return


def problems(data):
    """What in a caption the schema does not allow, as short sentences. Empty is good.

    `CaptionVerifier.verify`, less the key order `canonical` has already
    written, plus the two fields every element is written for: a `desc`, and
    on a text element the `text` itself.
    """
    out = []
    if not isinstance(data, dict):
        return ["the answer must be one JSON object"]
    extra = [key for key in data if key not in TOP]
    if extra:
        out.append(f"the top level may hold only {', '.join(TOP)}; it also holds {', '.join(extra)}")
    if "high_level_description" in data and not isinstance(data["high_level_description"], str):
        out.append("high_level_description must be a string")
    if "style_description" in data:
        style = data["style_description"]
        if not isinstance(style, dict):
            out.append("style_description must be an object")
        elif ("photo" in style) == ("art_style" in style):
            out.append("style_description must hold exactly one of photo and art_style")
        else:
            order = STYLE_PHOTO if "photo" in style else STYLE_ART
            unknown = [key for key in style if key not in order]
            if unknown:
                out.append(f"style_description may not hold {', '.join(unknown)}")
            if "color_palette" in style:
                _palette(style["color_palette"], "style_description.color_palette",
                         STYLE_PALETTE_MAX, out)
    composition = data.get("compositional_deconstruction")
    if not isinstance(composition, dict):
        out.append("compositional_deconstruction must exist and be an object")
        return out
    if not isinstance(composition.get("background"), str):
        out.append("compositional_deconstruction.background must exist and be a string")
    elements = composition.get("elements")
    if not isinstance(elements, list):
        out.append("compositional_deconstruction.elements must exist and be a list")
        return out
    unknown = [key for key in composition if key not in COMPOSITION]
    if unknown:
        out.append(f"compositional_deconstruction may not hold {', '.join(unknown)}")
    for number, element in enumerate(elements):
        where = f"elements[{number}]"
        if not isinstance(element, dict):
            out.append(f"{where} must be an object")
            continue
        kind = element.get("type")
        if kind not in ELEMENT:
            out.append(f'{where}.type must be "obj" or "text"')
            continue
        unknown = [key for key in element if key not in ELEMENT[kind]]
        if unknown:
            out.append(f"{where} may not hold {', '.join(unknown)}")
        if not isinstance(element.get("desc"), str):
            out.append(f"{where}.desc must be a string")
        if kind == "text" and not isinstance(element.get("text"), str):
            out.append(f"{where} is a text element and needs its literal text in \"text\"")
        if "bbox" in element:
            box = element["bbox"]
            if not (isinstance(box, list) and len(box) == 4
                    and all(isinstance(v, int) and not isinstance(v, bool) for v in box)):
                out.append(f"{where}.bbox must be four whole numbers [ymin, xmin, ymax, xmax]")
            elif not all(0 <= v <= BBOX_MAX for v in box) or box[0] > box[2] or box[1] > box[3]:
                out.append(f"{where}.bbox {box} must lie in 0–{BBOX_MAX} with each min below its max")
        if "color_palette" in element:
            _palette(element["color_palette"], f"{where}.color_palette", ELEMENT_PALETTE_MAX, out)
    return out


def serialize(data):
    """Upstream's serialization: minified, non-ASCII as itself."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _strings(value, out):
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            _strings(item, out)
    elif isinstance(value, list):
        for item in value:
            _strings(item, out)
    return out


def _closed(text):
    """A caption one closing brace short, closed -> the dict, or None.

    Measured on the lab: the 4B refiner writes a whole caption and stops one
    `}` short — the elements list and the composition closed, the root not —
    and does the same again when the re-ask shows it the break. Every byte it
    wrote parses and the one brace it owes is not in doubt, so it is added.

    Only that. A reply with more left open is one that stopped writing — a
    reply budget run out after a complete element closes just as cleanly and
    is a caption with its last elements missing — and a reply ending on
    anything but a closed object had more to say. The composition is the
    instruction's last key, so a root whose last value closed has nothing
    left out.
    """
    stack, in_string, escaped = [], False, False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "{[":
            stack.append("}" if char == "{" else "]")
        elif char in "}]":
            if not stack or stack.pop() != char:
                return None
    if in_string or stack != ["}"] or not text.rstrip().endswith("}"):
        return None
    try:
        data = json.loads(text + "}")
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _object(reply):
    """The reply's object, or a broken `MagicError`.

    `refine.json_object` finds the object and quotes the head of a reply it
    cannot read; the sentence here says only what kind of break it was,
    because it goes back to the model (`reask`). What leads up to the break
    rides as `where`, for the person — a caption breaks a thousand
    characters in, and the head of it shows nothing.
    """
    try:
        return refine.json_object(reply)
    except refine.RefineError as exc:
        cause = exc.__cause__
        if not isinstance(cause, json.JSONDecodeError):
            raise MagicError("the answer held no JSON object", broken=True) from exc
        text, at = cause.doc, cause.pos
        closed = _closed(text) if at >= len(text.rstrip()) else None
        if closed is not None:
            return closed
        raise MagicError(f"its JSON did not parse ({cause.msg})", broken=True,
                         where=f"…{text[max(0, at - 80):at]}⟨HERE⟩{text[at:at + 40]}…") from exc


def caption(reply, prose, keep_bboxes=False):
    """The model's reply -> the caption to render, or `MagicError` naming what is wrong.

    Transport noise is absorbed as everywhere else (`refine.json_object`); the
    schema, the quoted words and the groups are judged. A quoted span must be
    the literal `text` of an element — the instruction's own rule, and the one
    place an on-screen word is drawn from — and every group the prose offered
    must still be offered somewhere in the caption's strings, where
    `variations.resolve_caption` chooses it on the render's seed.
    """
    data = canonical(_object(reply), keep_bboxes)
    found = problems(data)
    if found:
        raise MagicError("the caption does not follow Ideogram's schema: " + "; ".join(found[:4]))

    elements = data["compositional_deconstruction"]["elements"]
    texts = [e["text"] for e in elements if isinstance(e, dict) and e.get("type") == "text"]
    missing = refine.dropped_quotes([prose], "\n".join(texts))
    if missing:
        raise MagicError("the quoted words " + ", ".join(f'"{span}"' for span in missing)
                         + " must each be the literal text of a text element, letter for letter")

    offered = [count for string in _strings(data, []) for _, count in variations.shapes(string)]
    dropped = []
    for source, count in variations.shapes(prose):
        if count in offered:
            offered.remove(count)
        else:
            dropped.append(source)
    if dropped:
        raise MagicError("the choices " + ", ".join(dropped) + " must stay in the caption as "
                         "written, braces and bars included, for the renderer to pick from")
    return serialize(data)


def tidy(text):
    """A caption written by hand or pasted -> the same caption in the model's
    key order and minified, or None when the text is not a JSON object.
    Nothing is refused: somebody who writes the schema by hand is the judge
    of what they wrote, and the bboxes are theirs to keep."""
    try:
        data = json.loads(str(text or "").strip())
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    return serialize(canonical(data, keep_bboxes=True))

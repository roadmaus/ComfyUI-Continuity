"""FLUX 3 Image Klein's prompt upsampler, run on whatever model the pack thinks
with.

Klein was trained on full scene captions, and BFL's card is blunt about a
prompt sent as typed: it "gives generic output". Their answer is an upsampler
in front of every request — a fine-tuned 9B by default, and for anyone running
another vision-language model in its place, the system prompts that model was
fitted to (`upsample/pup_prompts_external_vlm.json`, vendored from
black-forest-labs/flux-3-image-klein at `upsample/REVISION`; Apache-2.0,
licence beside it). This is that second path: BFL's instruction as the whole
system prompt, the request as the whole message, the reply taken as the
caption.

What is BFL's is everything their `flux3/pup.py` decides: `t2i` with nothing
attached and `i2i` with references, the user turn under the references, and
greedy decoding. What is the pack's is what a request needs on the way in and
BFL's instruction cannot know about. An `@img-1` means nothing outside this
pack, so each becomes `image N` in the order the pictures are attached, which
is how BFL's own examples cite them. A cast member's `@anna` is the opposite:
it has to come back out, because the compile swaps the name for her pictures
and her LoRAs at queue time, and a caption that only describes her renders
without either. So the named subjects are listed under the request with the
one rule the pack needs kept (`NAMES_NOTE`). The layout variants (`t2i_bbox`,
`i2i_bbox`) are vendored with the rest and not offered: they answer with an
element table this pack has no way to ask for yet.

No torch, no ComfyUI: the request and the reply are ordinary data.
"""

import json
from pathlib import Path

from ..refine import HANDLE_RE, THINK_RE, names

_HERE = Path(__file__).parent / "upsample"

PROMPTS = json.loads((_HERE / "pup_prompts_external_vlm.json").read_text(encoding="utf-8"))

# `pup.py` samples at temperature 0.
TEMPERATURE = 0.0

# `pup.py`'s `I2I_SCAFFOLD[False]`: the user turn that follows the references.
I2I_MESSAGE = ("Reference images follow in order (the first image, the second image, ...).\n"
               "User request: {request}\n"
               "Output the caption.")


# Said only when the request names somebody from the cast.
NAMES_NOTE = ("Named subjects. Write each name below exactly as given, with its @, "
              "in the caption where that subject appears, and describe them there; "
              "the name is replaced by the subject itself when the image is made, so "
              "a subject left unnamed is left out:")


def system_prompt(pictures):
    """BFL's instruction for this request: `i2i` with pictures attached, else `t2i`."""
    return PROMPTS["i2i" if pictures else "t2i"]


def user_message(request, pictures, cast=()):
    """The request as BFL's upsampler is handed it.

    `pictures` is the attached pictures' handles, in the order they are
    attached. A citation of one becomes `image N`; anything else is left as
    written. `cast` is the named subjects the request may cite (`Subject`s):
    each is listed with their description and the images that show them.
    """
    request = str(request or "").strip()
    order = {handle: n for n, handle in enumerate(pictures, 1)}
    if pictures:
        request = HANDLE_RE.sub(lambda m: f"image {order[m.group(1)]}" if m.group(1) in order
                                else m.group(0), request)
        request = I2I_MESSAGE.format(request=request)
    named = [subject for subject in cast if names(request, subject.handle)]
    if not named:
        return request
    lines = [request, "", NAMES_NOTE]
    for subject in named:
        line = f"@{subject.handle}"
        if subject.description:
            line += f": {subject.description.rstrip('.')}"
        shown = [f"image {order[h]}" for h in subject.sources if h in order]
        if shown:
            line += f" (shown in {', '.join(shown)})"
        lines.append(line)
    return "\n".join(lines)


def caption(reply):
    """The model's reply -> the caption, or None where it wrote nothing.

    Transport noise only: a leaked `<think>` block, and a fence or a pair of
    quotes around the caption, which BFL's instruction forbids and a chat
    model writes anyway.
    """
    text = THINK_RE.sub("", reply or "").strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1].strip()
    if len(text) > 1 and text[0] == text[-1] == '"':
        text = text[1:-1].strip()
    return text or None

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
greedy decoding. What is the pack's is the one translation a request needs on
the way in — an `@handle` means nothing outside this pack, so each becomes
`image N` in the order the pictures are attached, which is how BFL's own
examples cite them. The layout variants (`t2i_bbox`, `i2i_bbox`) are vendored
with the rest and not offered: they answer with an element table this pack
has no way to ask for yet.

No torch, no ComfyUI: the request and the reply are ordinary data.
"""

import json
from pathlib import Path

from ..refine import HANDLE_RE, THINK_RE

_HERE = Path(__file__).parent / "upsample"

PROMPTS = json.loads((_HERE / "pup_prompts_external_vlm.json").read_text(encoding="utf-8"))

# `pup.py` samples at temperature 0.
TEMPERATURE = 0.0

# `pup.py`'s `I2I_SCAFFOLD[False]`: the user turn that follows the references.
I2I_MESSAGE = ("Reference images follow in order (the first image, the second image, ...).\n"
               "User request: {request}\n"
               "Output the caption.")


def system_prompt(pictures):
    """BFL's instruction for this request: `i2i` with pictures attached, else `t2i`."""
    return PROMPTS["i2i" if pictures else "t2i"]


def user_message(request, pictures):
    """The request as BFL's upsampler is handed it.

    `pictures` is the attached pictures' handles, in the order they are
    attached. A citation of one becomes `image N`; anything else is left as
    written.
    """
    request = str(request or "").strip()
    if not pictures:
        return request
    order = {handle: n for n, handle in enumerate(pictures, 1)}
    request = HANDLE_RE.sub(lambda m: f"image {order[m.group(1)]}" if m.group(1) in order
                            else m.group(0), request)
    return I2I_MESSAGE.format(request=request)


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

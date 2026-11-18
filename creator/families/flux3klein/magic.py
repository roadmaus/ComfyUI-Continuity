"""FLUX 3 Image Klein's magic prompt, for the chat: BFL's upsampler over the
still's prose.

The same pass the refine button runs (`upsample.py`), asked on the turn by
`routes/chat._magic` the way Ideogram's is. Unlike Ideogram, Klein reads
pictures, so the still's references ride along in the order the render cites
them and the request is written against them. The caption is plain prose: there
is no schema to check it against, and the only failure is an empty reply.
"""

from . import upsample

TEMPERATURE = upsample.TEMPERATURE


class MagicError(ValueError):
    """A reply with no caption in it. `where` is `routes/chat._magic`'s field
    for the stretch a parse broke at; plain prose has none."""

    def __init__(self, sentence):
        super().__init__(sentence)
        self.where = ""


def system_prompt(pictures):
    return upsample.system_prompt(pictures)


def user_message(prose, aspect, pictures):
    """The request as BFL's upsampler takes it. The shape is the canvas's to
    keep, and the upsampler is never told one."""
    return upsample.user_message(prose, pictures)


def caption(reply, prose, keep_bboxes=False):
    """The reply -> the caption the render reads. `keep_bboxes` is Ideogram's:
    BFL's plain upsampler writes no boxes."""
    text = upsample.caption(reply)
    if not text:
        raise MagicError("the reply was empty — write the caption")
    return text


def reask(message, reply, problem):
    """An empty reply has nothing to quote back: the request again, with why."""
    return f"{message}\n\nYour previous reply could not be used: {problem}."


def tidy(text):
    """A caption sent back by the room -> itself, or None if there is none."""
    text = str(text or "").strip()
    return text or None

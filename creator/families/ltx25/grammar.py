"""How LTX 2.5 reads a request. See `families/grammar.py`.

Three of the four answers are declared here rather than inherited, and that is
the point of the seam: they are statements about Lightricks' weights that happen
to agree with MiniMax's today, not a shared rule. The compiler used to make them
for every family because there was only ever one to make them for.

- **The caps are zero**, which is the day this file's own note said would come.
  They used to be H3's numbers, on the reasoning that an attachment rode into
  the prose and no further and so cost nothing. It does not: a citation becomes
  the literal `<Picture 1>` and `compose` sends that to Gemma, so an attached
  file put an ordinal referring to nothing into the prompt of an encoder trained
  on captions. Refusing is the smaller harm, and `refuse` says what does work.
- **The mode names are this family's own**, in Lightricks' vocabulary, and name
  what the segment node actually builds: guides, through `LTXVAddGuide`.
- **There is no reference mode**, which is a declaration and not an omission.
  Attaching a file changes nothing the segment node builds — the files ride as
  their labels in the prose and nothing is encoded from them — so a card
  carrying one says what its guides make it, which is the truth about what will
  be sampled. `Grammar.mode` falls through to the frames when a family declares
  no reference shape.
- **The prose is plain**, because Gemma was trained on captions. H3's
  Context-IR — its section headers, its cut lines, its `<Picture 1>` glossary —
  is a form of *its* training, and putting it in front of this encoder would
  spoil the prompt rather than structure it.

**The open question this file is where to answer.** LTX 2.5 has no reference
grammar yet: what replaces H3's ordinal citation is IC-LoRAs and
`GetICLoRAParameters`, and choosing that is a modelling decision rather than a
refactor. When it is chosen, the caps, the reference mode and what `compose`
does with a citation are all here, and `compile.py` does not move.
"""

from ... import compile as compiler
from .. import grammar


class LTX25Grammar(grammar.Grammar):
    """LTX 2.5's request grammar. See the module docstring."""

    # No `reference` entry — see the module docstring. The four that are here
    # are the guide configurations the segment node knows how to build.
    modes = {"opens_closes": "FL2V",
             "opens": "I2V",
             "closes": "L2V",
             "text": "T2V"}

    # **Nothing may be attached, and that is the honest number.**
    #
    # These were H3's nine images and three videos, declared here while nothing
    # in this package read a reference at all, on the reasoning that the caps
    # bound a list which rides into the prose and no further. That reasoning was
    # wrong about what the prose does. `compile._substitute` turns a cited
    # `@ref-1` into the literal string `<Picture 1>`, and this family's
    # `compose` sends the body to Gemma unchanged — so an attached file did not
    # ride along harmlessly, it put an ordinal referring to nothing into a
    # caption-trained encoder's prompt. That is worse than refusing it.
    #
    # Sound is the exception, and it is not a reference here: a track laid on the
    # piece's **sound lane** is fixed into the audio latent (`audiolatent.py`),
    # which is conditioning this family really does. The lane is not counted
    # here because it is not attached to a card — see `sound.py`.
    #
    # What would raise these again is IC-LoRA: Lightricks' `Ingredients` adapter
    # takes a composite reference sheet through `LTXVAddGuide` with an
    # `iclora_parameters` downscale factor, which is a real reference grammar
    # for this family. It is not wired yet, and a cap promising conditioning
    # that does not exist is the thing this change is undoing.
    max_images = 0
    max_videos = 0
    max_audios = 0
    max_files = 0

    def refuse(self, error, images, videos, audios):
        """Refuse every attachment, saying what to do instead.

        Overridden rather than left to the base class's counting, because the
        base's messages are all "at most N" and N is zero — "at most 0 reference
        images" is a true sentence that tells nobody anything. What a user wants
        to know here is that this family has no reference grammar *yet* and
        which controls do work.
        """
        if not (images or videos or audios):
            return
        raise error(
            "LTX 2.5 has no reference grammar yet, so an attached file would "
            "reach the model as an ordinal in the prompt with no picture "
            "behind it. What conditions this family today: a start or end "
            "frame on the card, a seam from the shot before it, and a track on "
            "the piece's sound lane. Detach the references, or switch the "
            "piece's model pill to MiniMax H3, which does read them."
        )

    # One transformer. Nothing routes, so `Grammar.checkpoint` answers `""` and
    # `compile._resolve_checkpoint` derives nothing to pin against.
    routes = {}
    default_route = ""

    def join_shots(self, shots):
        """The shots run together as prose, unmarked. Lightricks' captions carry
        no shot labels, so a `[Shot 2]` here would be a token Gemma has never
        seen standing where a description should be."""
        return compiler.plain_shot_body(shots)

    def compose(self, *, body, soundscape, music, **rest):
        """The substituted description and the two sound fields, joined.

        Nothing is invented and no format is imposed; a piece with neither sound
        field is its body, unchanged. The rest of what the compiler offers — the
        duration, the shot count, the alignment preamble — is Context-IR
        scaffolding this encoder has no use for.
        """
        return compiler.plain_prompt(body, soundscape, music)


GRAMMAR = LTX25Grammar()

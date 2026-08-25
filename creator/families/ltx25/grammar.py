"""How LTX 2.5 reads a request. See `families/grammar.py`.

Three of the four answers are declared here rather than inherited, and that is
the point of the seam: they are statements about Lightricks' weights that happen
to agree with MiniMax's today, not a shared rule. The compiler used to make them
for every family because there was only ever one to make them for.

- **The caps are the same numbers H3 declares**, and deliberately so while
  nothing here reads a reference at all: they bound a list this family carries
  into the prose and no further, so tightening them would refuse an attachment
  that costs nothing and loosening them would promise conditioning that does not
  exist. `test_family_select` holds the two identical and fails the day one of
  them stops being — which is the day this file has the real numbers in it.
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

    max_images = 9
    max_videos = 3
    max_audios = 3
    max_files = 12

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

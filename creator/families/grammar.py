"""How a family reads a request — what may be attached, what the payload shape
is called, which weights that implies, and how the prose reaches the encoder.

`compile.py` owns everything about a request that is arithmetic or bookkeeping:
the canvas, the durations, the seams, the reference pool, the cast, the strip. It
does not own what a *checkpoint's training* decided about the request, and it was
answering that too — H3's five mode names, H3's nine-image cap, H3's Context-IR
composition, H3's rule that a reference means the Ref2VA weights. Every family
compiled through those, because there was one family when they were written.

That is the seam this module is. A family's grammar is a pure declaration —
imported without ComfyUI, like `declare.py`, because the compiler runs long
before a loader exists — and `compile.py` asks it four questions:

- **What may be attached** (`refuse`). The caps, and the rule that audio is not
  a standalone reference. H3's are the model card's; another family's are its
  own, and a family that takes no references at all refuses them here rather
  than accepting files it will not encode.
- **What this payload is** (`mode`). The shape is the compiler's reading —
  something opens, something closes, something is cited — and the *name* is the
  family's, because it names a form of its own training. A family may also
  declare that references are not a shape it distinguishes.
- **Which weights that implies** (`checkpoint`). Only on a family that routes
  between more than one; the rest answer nothing and mean it.
- **What the encoder is sent** (`compose`, plus `sections` for what a family
  derives from the request and `join_shots` where a pass holds several cards).
  H3 was trained on its own Context-IR and is sent that, sections and all; an
  encoder trained on captions is sent the substituted description and nothing
  else.

**What deliberately stays in `compile.py`.** The cast — `subjects.parse`,
`cited`, `claimed`, `check` — and which section names a rewrite may carry. Those
are the *pack's* features: a band in the UI, a blob field, a refiner panel. H3 is
the family that renders a cast into prose, and that half is here (`sections`);
what a cast *means* to a family with no subject grammar is the same open question
as what a reference means to one with no citation grammar, and inventing a hook
for it before either is decided would be describing a seam nobody has crossed.

Two families declaring the same answers is not a reason to have one copy: the
answers are about weights, and two sets of weights agreeing today is a fact
about them rather than a shared rule. `test_family_select` holds the reference
grammars identical *because they are read from one place today* and fails the
day they are not, which is the day the difference has to be real.
"""

import importlib


class Grammar:
    """One family's reading of a request. Stateless; a singleton per family."""

    #: The name this family gives each payload shape — `{shape: name}`, where a
    #: shape is one of `reference`, `opens_closes`, `opens`, `closes`, `text`.
    #: A family that does not distinguish references simply has no `reference`
    #: key, and a card carrying one is named by its frames instead.
    modes = {}

    #: How many of each kind may be attached, and how many files in total.
    max_images = 0
    max_videos = 0
    max_audios = 0
    max_files = 0

    #: The routed slot each mode implies, `{mode name: slot}`, and the slot
    #: everything else lands on. Empty on a family that routes between nothing.
    routes = {}
    default_route = ""

    def refuse(self, error, images, videos, audios):
        """Raise `error` if what is attached is more than this family takes.

        `audios` is the count including video soundtracks — the compiler works
        that out, because which list a clip's sound lands in is its bookkeeping.
        """
        if len(images) > self.max_images:
            raise error(f"at most {self.max_images} reference images "
                        f"({len(images)} given)")
        if len(videos) > self.max_videos:
            raise error(f"at most {self.max_videos} reference videos "
                        f"({len(videos)} given)")
        if audios > self.max_audios:
            raise error(f"at most {self.max_audios} reference audio clips, "
                        f"counting video soundtracks ({audios} given)")
        total = len(images) + len(videos) + audios
        if total > self.max_files:
            raise error(f"at most {self.max_files} reference files total "
                        f"({total} given)")
        if not images and not videos:
            # Per the model card: audio is never a standalone reference.
            raise error("reference audio needs at least one reference image or "
                        "video alongside it")

    def mode(self, *, cited, opens, closes):
        """The name this family gives the payload the compiler just read.

        `cited` is whether anything is attached, `opens`/`closes` whether the
        generation starts and ends on a picture — a keyframe, an inherited seam
        frame, or the opening of the clip it runs into, which are the same
        statement to the model however they got there.
        """
        if cited and "reference" in self.modes:
            return self.modes["reference"]
        if opens and closes:
            return self.modes["opens_closes"]
        if opens:
            return self.modes["opens"]
        if closes:
            return self.modes["closes"]
        return self.modes["text"]

    def checkpoint(self, mode):
        """The routed slot `mode` implies, before any pin. `""` where the family
        routes between nothing — there is no second set of weights to choose."""
        if not self.routes:
            return ""
        return self.routes.get(mode, self.default_route)

    def join_shots(self, shots):
        """Several shots of one pass -> the one body that describes them.

        A pass of several cards is a single generation, so its shots have to
        become one description — and how is the family's. H3 marks its cuts
        (`[Shot 2] At 00:05.000,`) because Context-IR is what it was trained on;
        a family whose captions carry no labels must not, or the marks are
        tokens the encoder has never seen.
        """
        raise NotImplementedError(f"{type(self).__name__}.join_shots")

    def sections(self, **parts):
        """The prompt sections this family derives from the request itself.

        `{name: text}`, merged under whatever a rewrite supplied. Empty for a
        family whose encoder reads a paragraph: there are no named sections to
        fill, and filling them would be writing a document nothing reads.
        """
        return {}

    def count_shots(self, body, cards):
        """How many shots the joined body actually holds.

        `cards` is how many the strip put in the pass, which is the answer for a
        family whose body is a prose paragraph — there is nothing in one to
        count. A family that numbers its shots counts them off the finished text
        instead, because a card may write several of its own inside the one the
        timeline allotted it.
        """
        return cards

    def compose(self, **parts):
        """The prose the encoder is actually sent. -> a string.

        The keywords are the compiler's — the body, the two audio fields, the
        duration, the labels it assigned — and a family reads the ones its
        encoder has a use for. Everything a family needs that is not here is a
        sign the seam is in the wrong place.
        """
        raise NotImplementedError(f"{type(self).__name__}.compose")


def of(family):
    """The grammar of `family`. Imported on demand and pure, like `declare`."""
    return importlib.import_module(f".{family}.grammar", __package__).GRAMMAR

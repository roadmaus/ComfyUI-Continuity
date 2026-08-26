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

    #: The named sections a rewrite may carry for this family, and the whole of
    #: what `compile.refined_sections` will read back off a stored one. H3's
    #: three are the parts of its Context-IR document; a family whose reference
    #: form is one half of a caption has one, and a family with no reference form
    #: has none — where a stored section would be prose nothing composes.
    #:
    #: A filter rather than a schema: what is not named here is dropped, so a
    #: rewrite written under one family and opened under another cannot smuggle
    #: the first family's document into the second's caption.
    written_sections = ()

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

    #: What each kind of reference is *called* in the prose, by the walk's op —
    #: `%d` is the 1-based ordinal within that kind. H3's ordinal citations are
    #: the default because they were the only ones when `plan_references` was
    #: written, and they are a form of H3's own training: the tokenizer is
    #: presented the files in exactly this order and the prompt addresses them by
    #: the ordinal they took.
    #:
    #: A family whose encoder reads captions has to spell a citation as words —
    #: `<Picture 1>` is a token sequence Gemma has never seen standing where a
    #: noun phrase belongs. See `families/ltx25/grammar.py`.
    citations = {"image": "<Picture %d>", "video": "<Video %d>",
                 "soundtrack": "<Audio %d>", "audio": "<Audio %d>"}

    #: Whether a panel of a plate is a citation of its own.
    #:
    #: **False by default, because an ordinal citation is a place in a
    #: presentation.** H3 is handed a plate as one picture and calls it
    #: `<Picture 1>`; giving the thing in its top-left corner a `<Picture 2>` of
    #: its own would address a file the tokenizer was never shown. A family
    #: whose encoder reads the composite *as* a layout — LTX 2.5, whose panels
    #: are the citation — sets this True and takes its ordinals per panel.
    cites_panels = False

    def cite(self, op, ordinal):
        """What the `ordinal`-th reference of this kind is called in the prose."""
        return self.citations[op] % ordinal

    def panel_cite(self, plate_label, ordinal, count):
        """What one panel of a plate is called, on a family that cites the plate.

        Only reached where `cites_panels` is False — where it is True the panel
        took an ordinal of its own and `cite` already named it. The plate's own
        label is carried in so the name says which picture the panel is in:
        `panel 2 of <Picture 1>` is checkable against the composite in front of
        the model, where a bare `panel 2` on a request holding two plates would
        not be.

        A plate of one panel *is* its panel — there is no layout, only a picture
        the picker cut out of its background — so it takes the plate's own
        label. `panel 1 of <Picture 1>` would name a cell inside a picture that
        has no cells, and send the model looking for a region that is the whole
        frame.
        """
        if count <= 1:
            return plate_label
        return f"panel {ordinal} of {plate_label}"

    def frame_cite(self, role, ordinal):
        """What an attached start or end frame is called in the prose.

        Apart from `cite` because the two are not the same statement even on H3,
        where they happen to share a form: a reference is a file the prompt
        reaches for, a frame is where the generation begins or ends. On a family
        that conditions its frames as *guides* the model is already looking at
        them, and what the prose has to supply is a way to refer to a picture
        rather than a slot in a presentation order.

        `ordinal` is the `<Picture N>` this frame took, counted after the
        references — see `compile._trailing_frame_labels`.
        """
        return self.citations["image"] % ordinal

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

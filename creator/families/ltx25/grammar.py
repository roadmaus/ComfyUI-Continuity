"""How LTX 2.5 reads a request. See `families/grammar.py`.

Four of the five answers are declared here rather than inherited, and that is
the point of the seam: they are statements about Lightricks' weights that happen
to agree with MiniMax's today, not a shared rule. The compiler used to make them
for every family because there was only ever one to make them for.

- **Images may be attached and nothing else.** This family's reference grammar
  is Lightricks' `Ingredients` IC-LoRA: a composite reference sheet —
  characters, props and locations laid out on a black background — handed in as
  a guide with the adapter's own downscale factor, and a two-part prompt naming
  what is on it. That takes *pictures*. There is no panel a reference video or a
  reference soundtrack could be, so those two caps stay at zero and `refuse`
  says what does work rather than counting to nothing.
- **The mode names are this family's own**, in Lightricks' vocabulary, and name
  what the segment node actually builds: guides, through `LTXVAddGuide`.
- **A citation is words.** H3 addresses a reference by the ordinal it took in
  the tokenizer's presentation — `<Picture 1>` — which is a form of *its*
  training. Gemma reads captions, so an ordinal there is a token sequence
  standing where a noun phrase belongs. A reference is `panel 1` of the sheet
  and a start frame is `the first frame`, both of which are English and both of
  which the reference-sheet half of the prompt goes on to define.
- **The prose is two-part on a reference generation and plain otherwise.**
  Lightricks' own form for the Ingredients adapter is `Reference sheet: …` then
  `Generated video: …`, and nothing else about the caption changes. H3's
  Context-IR — its section headers, its cut lines, its `<Picture 1>` glossary —
  is a form of its own training and putting it in front of this encoder would
  spoil the prompt rather than structure it.
"""

from ... import compile as compiler
from .. import grammar

# What the two halves of an Ingredients prompt are called, verbatim. Lightricks'
# wording rather than a paraphrase: the adapter was trained against captions that
# open on these exact strings, so they are part of the conditioning and not a
# layout choice this pack gets to make prettier.
SHEET_LEAD = "Reference sheet:"
VIDEO_LEAD = "Generated video:"

# What an attached frame is called in the prose. Not an ordinal, and not a
# panel: a frame on this family is a real guide latent pinned at an instant, so
# what the caption needs is a phrase that says *which instant* — which is also
# what the four mode templates already tell the refiner to write about.
FRAME_CITATION = {"first_frame": "the first frame",
                  "last_frame": "the final frame"}


class LTX25Grammar(grammar.Grammar):
    """LTX 2.5's request grammar. See the module docstring."""

    # `REF2V` beside the four guide configurations: a card carrying references is
    # a different generation here, not merely a differently-worded one. It loads
    # the Ingredients IC-LoRA, it builds a sheet, and it hands that sheet in as a
    # guide — none of which a card without references does.
    modes = {"reference": "REF2V",
             "opens_closes": "FL2V",
             "opens": "I2V",
             "closes": "L2V",
             "text": "T2V"}

    # **Nine pictures, and nothing that is not a picture.**
    #
    # Nine is H3's number and it is kept deliberately: the sheet is a grid and
    # nine panels is where a 3x3 stops being a reference sheet and starts being a
    # contact sheet nothing in it is legible at. `sheet.py` lays them out and
    # says what each count looks like.
    #
    # The zeros are the honest ones. A reference video and a reference sound have
    # no panel on a sheet, and this family has no second grammar to send them
    # through — `refuse` says so and names what does condition a shot instead.
    #
    # Sound is the exception, and it is not a reference here: a track laid on the
    # piece's **sound lane** is fixed into the audio latent (`audiolatent.py`),
    # which is conditioning this family really does. The lane is not counted here
    # because it is not attached to a card — see `sound.py`.
    max_images = 9
    max_videos = 0
    max_audios = 0
    max_files = 9

    # One section, against H3's three: the reference form here is one half of a
    # caption rather than a document with named parts. The name is the
    # compiler's own key for it — see `sections` below and `refine.SHEET_SECTION`.
    written_sections = ("reference_sheet",)

    # A reference on this family is words in the caption and a panel on the
    # sheet, so the citation has to be readable English. `panel 1` rather than
    # `<Picture 1>`, and lowercase, because it is substituted mid-sentence: "the
    # woman from @img-1 walks in" becomes "the woman from panel 1 walks in",
    # which is a caption. The video and audio forms are unreachable while the
    # caps above are zero and are spelled anyway, so that raising a cap is one
    # decision rather than two.
    citations = {"image": "panel %d", "video": "clip %d",
                 "soundtrack": "sound %d", "audio": "sound %d"}

    # **The panel is the citation here, not the file.** A card on this family
    # attaches one plate — the composite sheet the picker built — and what the
    # caption reaches for is what is *on* it. So the image ordinals run over the
    # panels of the plate rather than over the attachments, which is what makes
    # `panel 3` the third cell of the grid `plate.compose` laid out. See
    # `compile.plan_references`.
    cites_panels = True

    def frame_cite(self, role, ordinal):
        """`the first frame` / `the final frame`. See `FRAME_CITATION`.

        The ordinal is ignored, and that is the difference from H3: there, a
        frame is a picture in a numbered presentation and the number is how the
        prompt reaches it. Here it is a guide the model is already looking at, so
        what the caption needs is which end of the shot it is.
        """
        return FRAME_CITATION.get(role, "the attached frame")

    def refuse(self, error, images, videos, audios):
        """Refuse anything that is not a picture, saying what to do instead.

        Overridden rather than left to the base class's counting for the videos
        and the sounds, whose caps are zero: "at most 0 reference videos" is a
        true sentence that tells nobody anything. The image cap is a real number
        and is counted the ordinary way, so the base class handles it — this only
        replaces the two messages that would otherwise count to nothing.

        The base's last rule is skipped outright: "reference audio needs a
        reference image alongside it" is H3's model card, and here there is no
        reference audio for it to be about.
        """
        if videos or audios:
            raise error(
                "LTX 2.5 reads references as a composite sheet of stills — "
                "Lightricks' Ingredients adapter — so a reference video or a "
                "reference sound has no panel to be. Attach a still instead, "
                "lay the sound on the piece's sound lane, or switch the piece's "
                "model pill to MiniMax H3, which reads both."
            )
        # One image attachment, and it is the sheet (or a lone picture, which is
        # a sheet of one). The adapter reads a single composite, and the picker
        # writes that composite while the files are being chosen — so a card
        # carrying several image files is asking the render to lay out a sheet
        # nobody has seen, which is exactly the invisible compose this family
        # removed. Refused rather than composed: what the user saw is what the
        # model gets, or the request does not run.
        if len(images) > 1:
            raise error(
                "LTX 2.5 reads one reference image — the composite sheet the "
                "picker lays out as you choose the files. Combine these into "
                f"one sheet in the picker ({len(images)} separate images given)."
            )
        # Panels, not attachments. The one plate holds up to nine pictures, so
        # counting the assets would count to one and let a twelve-panel sheet
        # through — the cap is about how many things are legible on the sheet,
        # and the sheet is what the panels are on.
        panels = sum(max(1, len(image.panels)) for image in images)
        if panels > self.max_images:
            raise error(f"at most {self.max_images} reference images "
                        f"({panels} given) — they are the panels of one "
                        f"sheet, and past nine none of them is legible")

    # One transformer. Nothing routes, so `Grammar.checkpoint` answers `""` and
    # `compile._resolve_checkpoint` derives nothing to pin against.
    routes = {}
    default_route = ""

    def join_shots(self, shots):
        """The shots run together as prose, unmarked. Lightricks' captions carry
        no shot labels, so a `[Shot 2]` here would be a token Gemma has never
        seen standing where a description should be."""
        return compiler.plain_shot_body(shots)

    def sections(self, *, cast, labels, plan, **rest):
        """`reference_sheet` — what each panel of the sheet holds.

        The half of an Ingredients prompt this pack can derive. One clause per
        panel, in the order `sheet.py` lays them out, saying which panel a file
        is and what the card said it was for — the chip on it, and the cast
        member who claimed it where there is one. That is thin prose and it is
        meant to be: the refiner overwrites it with a description of what is
        actually in the pictures, and this is what a render that was never
        refined still sends. The alternative is what the family did before —
        a caption naming `panel 1` with nothing anywhere saying what panel 1 is.

        Empty where there is no sheet, which is what keeps a card with no
        references composing exactly the caption it did before this existed.
        """
        if not plan:
            return {}
        from . import sheet

        return {"reference_sheet": sheet.describe(plan, cast)}

    def compose(self, *, body, soundscape, music, sections, **rest):
        """The caption. Two-part where there is a sheet, plain where there is not.

        `Reference sheet: … Generated video: …` is Lightricks' own form for the
        Ingredients adapter, used verbatim (`SHEET_LEAD`, `VIDEO_LEAD`) because
        the adapter was trained against captions that open on those strings.
        Everything else is `plain_prompt`'s: the substituted description and the
        two sound fields, joined, with nothing invented and no format imposed.

        The sheet section is read out of `sections` rather than rebuilt, so a
        refined one wins — `compile_request` merges the rewrite over what
        `sections` above derived, and this composes whichever survived.
        """
        video = compiler.plain_prompt(body, soundscape, music)
        panels = str((sections or {}).get("reference_sheet") or "").strip()
        if not panels:
            return video
        return f"{SHEET_LEAD} {panels}\n{VIDEO_LEAD} {video}"


GRAMMAR = LTX25Grammar()

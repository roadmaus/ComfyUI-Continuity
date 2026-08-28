"""The cast: who is in the video, as against which files are attached.

H3's reference guide splits identity from provenance. `<Picture N>` and
`<Video N>` are the files the tokenizer is shown; `<Subject N>` is the reusable
visible content — a person, an object, an environment, a look — that the target
video actually contains. Section 2.2 is explicit about which of the two a
character is:

    If an image is used only to define a character, scene, costume, or style,
    do not create a standalone picture entry. Instead, cite the image source
    inside the corresponding `<Subject N>` definition.

Everything else in this package addresses files. `@img-1` becomes `<Picture 1>`
and the prose says `<Picture 1>` walks across the room, which is the one thing
the guide says not to write. It also cannot say the three things the guide's own
examples say, and that a user with a cast in their head wants to say:

  - four photographs are one dog (`<Subject 2> is the fluffy white Samoyed in
    <Picture 2>, <Picture 3>, and <Picture 4>`);
  - a face comes from a still and a walk comes from a clip (`<Subject 1> is the
    person whose appearance comes from <Picture 1> and whose walking motion comes
    from <Video 1>`);
  - this person stands in the place of the person already in that clip, which is
    the marker `transferred` and a sentence naming who was replaced.

So a subject is declared: a handle, the reference files behind it, one word for
what of them is the reference, and optionally a description, a clip its motion
comes from, an audio reference that is its voice, and the person in a reference
video it replaces. It is cited in prose as `@anna`, exactly as an asset is, and
`compile._substitute` turns it into `<Subject N>` at queue time — so the chips,
the mention menu and the refiner's store-handles-not-ordinals rule carry it with
no changes at all.

Having that, the two sections that could previously only ever arrive from the
refiner — `subject_definitions` and `retention_analysis` — become derivable from
the direct path, because the facts they are made of are now written down.

Nothing here touches disk or imports anything of ComfyUI's, like `compile.py`
and `contextir.py`, which is what keeps `tests/test_subjects.py` a plain unit
test.
"""

import re

from . import contextir


class SubjectError(ValueError):
    """A cast that cannot be resolved. `compile.py` re-raises it as its own."""


# What of the files behind a subject is the reference. The same four words an
# image takes in `compile.TAKES` — a subject is visible content, so the whole-
# video relationships (`edit`, `camera`, `continue`) are not among them: those
# are statements about the target video with no subject in them at all, and
# `<Video N>` is the label reserved for saying them.
TAKES = ("person", "object", "scene", "style")

# The reference guide's fixed relationship markers, section 4.1. These are output
# values, not prose — the guide spells them in English in every language, and
# they are the four it spells. Two of them used to be `transferred` and `reused`,
# which are not in the guide at all: the direct path was writing a token the
# weights were never trained on into the one field whose vocabulary is fixed,
# and it was writing it on exactly the case that needs it most — a subject who
# stands in for somebody. `refine.py` and `prompts/modes/ref2va.txt` always had
# these four; this is the third copy agreeing with them.
MARKERS = ("fully_preserved", "partially_preserved", "attribute_transfer",
           "weak_reference")

# Deliberately not the asset handles' shape. `compile.HANDLE_RE` matches
# `name-digit` because that is what the handle allocator writes, and a subject is
# named by the user rather than allocated — "anna" is the whole point, since a
# cast the user cannot read is a cast they cannot pin. No hyphen, so the two
# shapes can never be confused for one another by eye or by pattern.
HANDLE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")


class Feature:
    """One thing the reference shows, and what becomes of it.

    The guide writes a subject as a named list of features and then names the
    same features again in `retention_analysis` — section 6's worked example is
    four subjects in a row built exactly that way:

        <Subject 2> is the fluffy white Samoyed in <Picture 2>, <Picture 3>, and
        <Picture 4>, with thick white fur, pointed ears, a dark nose, and a
        curved tail.
        ...
        <Subject 2> (appears in [Shot 1], [Shot 2]): fully_preserved - the
        Samoyed's thick white fur, pointed ears, dark nose, and curved tail are
        retained.

    So a feature is the unit both sections are made of, and `instead` is the one
    thing the old shape could not say: this feature is defined, and in the
    target video it is something else. That is section 4.1's `partially_preserved`
    to the word — "the referenced content is still used, but some defined
    characteristics are changed" — and it is why the marker is derived from this
    list rather than picked off one.

    `text` is written into both sections. `instead` is written into
    `retention_analysis` only: the definition says what the label denotes, and
    what the label denotes is what the reference shows. A characteristic has to
    be defined before it can be changed.
    """

    __slots__ = ("text", "instead", "attr")

    def __init__(self, text, instead="", attr=""):
        self.text = text
        self.instead = instead
        # The baseline attribute this row stands for, or "" for a feature
        # somebody typed from nothing. See `ATTRIBUTES`: a cast card seeds one
        # row per attribute of its `takes`, so "what is retained" is a list on
        # the card rather than a sentence buried in this module. `text` is then
        # optional — an untouched row says "hair" and a described one says
        # "long dark hair", and both are the same row.
        self.attr = attr

    @property
    def changed(self):
        return bool(self.instead)

    def phrase(self, takes):
        """What this feature is called in prose, under `takes`.

        The user's own words where they wrote any, and the attribute's own
        fragment where they did not. A row with neither is not a feature and
        `_parse_features` drops it.
        """
        return self.text or _attr_phrase(takes, self.attr)


class Subject:
    """One member of the cast. Immutable in practice; a plain class rather than
    a dataclass so the optional halves can carry their own docstrings."""

    __slots__ = ("handle", "sources", "takes", "description", "features",
                 "motion", "voice", "replaces", "replaces_what", "marker",
                 "seeded")

    def __init__(self, handle, sources, takes="person", description="",
                 features=(), motion=None, voice=None, replaces=(),
                 replaces_what="", marker=None, seeded=False):
        self.handle = handle
        self.sources = tuple(sources)      # asset handles defining its appearance
        self.takes = takes                 # one of TAKES
        self.description = description     # the user's own words, folded into the definition
        self.features = tuple(features)    # what the reference shows, one phrase each
        self.motion = motion               # a reference video its movement comes from
        self.voice = voice                 # an audio reference that is its voice
        # The reference videos it stands in for someone in. A tuple, because one
        # person can occupy the same role in several clips — a medium shot and a
        # close-up of the same scene is the ordinary case, and while this held a
        # single handle the second clip could only be attached and left
        # undefined. Section 2.1 puts no such limit on a subject: "one reference
        # asset may provide multiple subjects" and, symmetrically, one subject
        # may be spread across several assets.
        self.replaces = tuple(replaces or ())
        self.replaces_what = replaces_what  # who, in that video, in the user's words
        # None means "derive it" — see `relationship`. Preserved whole unless a
        # feature is changed; standing in for somebody does not move the marker,
        # because the swap is stated on the clip's own retention line.
        self.marker = marker
        # Whether the feature rows are the whole account of what this subject
        # carries. The shelf seeds one row per `ATTRIBUTES` entry when somebody
        # is cast and sets this, so an empty list means "everything was dropped"
        # rather than "nobody has said". Without it the two are the same list
        # and dropping the last row would silently hand back the whole baseline
        # — the one thing a drop must not do.
        #
        # False is every piece written before the rows existed, and `_RETAINED`
        # is what those compile to: the same sentence the seeded rows compose.
        self.seeded = bool(seeded)

    @property
    def changed(self):
        """The features the target video gives them instead."""
        return tuple(f for f in self.features if f.changed)

    @property
    def kept(self):
        """The features carried over as the reference has them."""
        return tuple(f for f in self.features if not f.changed)

    @property
    def relationship(self):
        """The retention marker this subject carries.

        Derived, and derived from facts the user stated rather than from a
        picker they could contradict. A feature the target video gives them
        instead is `partially_preserved`, by 4.1's own gloss. Everything else
        is preserved whole — *including* a subject who stands in for somebody:
        their defined role is their appearance, and in the target video it
        appears entire. This used to be `attribute_transfer`, whose gloss is
        "transferred to a different identifiable target subject" — a marker
        that keeps the target identifiable, which the model read faithfully as
        "keep the person, move the face". The swap itself lives on the *clip's*
        line (`contextir.retention_lines`), the way the model card's own edit
        example puts it: the source is partially preserved "while the central
        character is edited".

        `marker` still wins where it is set. It is the way to reach
        `weak_reference`, which nothing here can infer: "only broad similarity
        in style, category, composition, or atmosphere" is a judgement about the
        render, not a fact about the cast.
        """
        if self.marker:
            return self.marker
        if self.changed:
            return "partially_preserved"
        return "fully_preserved"

    @property
    def files(self):
        """Every asset handle this subject claims, in citation order."""
        out = list(self.sources)
        for extra in (self.motion, self.voice):
            if extra and extra not in out:
                out.append(extra)
        return out


def parse(raw):
    """The blob's `subjects` list -> `Subject`s. Shape only; see `check`.

    Validated without the assets in hand because the cast belongs to the piece
    and the assets belong to a generation: a subject nobody cites in this shot
    has no files here and is not an error, it is simply not in this shot.
    """
    cast = []
    seen = set()
    for index, item in enumerate(raw or []):
        if not isinstance(item, dict):
            raise SubjectError(f"subject #{index + 1} is not an object")
        handle = str(item.get("handle") or "").strip()
        if not handle:
            raise SubjectError(f"subject #{index + 1} has no name")
        if not HANDLE_RE.match(handle):
            raise SubjectError(
                f"@{handle}: a subject's name is letters, digits and "
                f"underscores, starting with a letter — no hyphen, which is "
                f"what tells it apart from a file's handle"
            )
        if handle in seen:
            raise SubjectError(f"two subjects are both called @{handle}")
        seen.add(handle)

        takes = str(item.get("takes") or "person")
        if takes not in TAKES:
            raise SubjectError(
                f"@{handle}: takes must be one of {', '.join(TAKES)} (got {takes!r})")

        sources = [str(h).strip() for h in (item.get("from") or []) if str(h).strip()]
        motion = str(item.get("motion") or "").strip() or None
        voice = str(item.get("voice") or "").strip() or None
        # A string or a list of them. The scalar form is every blob written
        # before a person could stand in for somebody twice, and it is read as
        # the one-element list it always meant — the alternative is a migration
        # that has to run on every load of every saved workflow, for good.
        raw_replaces = item.get("replaces")
        if isinstance(raw_replaces, str):
            raw_replaces = [raw_replaces]
        replaces = tuple(h for h in
                         (str(x).strip() for x in (raw_replaces or []))
                         if h)
        description = str(item.get("description") or "").strip()
        features = _parse_features(handle, item.get("features"))
        # A subject with nothing behind it defines nothing: the label would be
        # written into the prompt and the model would be told a name and no
        # appearance. Three things count as something behind it, and a cast entry
        # with none of them is a half-filled row — refusing it here is what stops
        # it reaching the model as a dangling `<Subject N>`.
        #
        # Files are the obvious one. Standing in for someone is the second —
        # "whoever is there now, gone" is a real thing to say. The third is a
        # description, and it is what makes a cast work at all in a generation
        # that has no references: in T2VA there is no picture to point at, and
        # "@anna is a person in their thirties, close-cropped hair" is the whole of
        # what a name can mean there. That is still worth having, because it is
        # what keeps them the same person across nine shots.
        if not sources and not motion and not replaces and not description and not features:
            raise SubjectError(
                f"@{handle}: a subject needs something behind it — a picture or "
                f"a clip to be built out of, a description of what they look "
                f"like, a feature of theirs, or the person they stand in for"
            )

        marker = item.get("relationship") or None
        if marker and marker not in MARKERS:
            raise SubjectError(
                f"@{handle}: relationship must be one of {', '.join(MARKERS)} "
                f"(got {marker!r})")

        cast.append(Subject(
            handle=handle,
            sources=sources,
            takes=takes,
            description=description,
            features=features,
            seeded=bool(item.get("seeded")),
            motion=motion,
            voice=voice,
            replaces=replaces,
            replaces_what=str(item.get("replaces_what") or "").strip(),
            marker=marker,
        ))
    return cast


def _parse_features(handle, raw):
    """The blob's `features` list -> `Feature`s.

    A row with no text is dropped rather than refused: the editor writes an
    empty row the moment somebody presses "add a feature", and a half-typed cast
    is a normal thing to be holding — the same reason `compiled_prompt` reports
    a failed compile as text instead of an error. An `instead` with no feature
    to be instead *of* has nothing to attach to and goes with it.
    """
    out = []
    for index, item in enumerate(raw or []):
        if isinstance(item, str):
            # The scalar form: a feature with nothing to say about it is the
            # phrase alone. Saves every caller that only wants the list from
            # writing {"is": ...} around each entry.
            text, instead, attr = item.strip(), "", ""
        elif isinstance(item, dict):
            text = str(item.get("is") or "").strip()
            instead = str(item.get("instead") or "").strip()
            attr = str(item.get("attr") or "").strip()
        else:
            raise SubjectError(
                f"@{handle}: feature #{index + 1} is neither a phrase nor an object")
        # A seeded row is a feature with nothing typed into it yet, and it still
        # says something — "hair" is the attribute's own name. So the row
        # survives on either half, and only one with neither is the empty row
        # the editor writes the moment somebody presses "add a feature".
        if not text and not attr:
            continue
        out.append(Feature(text.rstrip("."), instead.rstrip("."), attr))
    return tuple(out)


def citation_re(cast):
    """A pattern matching `@handle` for exactly the subjects in `cast`.

    An alternation over the declared names rather than a shape, which is the
    whole reason subject handles are safe to be words: `@anna` means something
    only where somebody has declared Anna, so no prose is reinterpreted by this
    feature existing. `None` when the cast is empty, so callers can skip the
    scan rather than run an empty alternation over every prompt in a timeline.
    """
    if not cast:
        return None
    names = sorted((s.handle for s in cast), key=len, reverse=True)
    return re.compile(r"@(" + "|".join(re.escape(n) for n in names) + r")\b")


def cited(cast, texts):
    """The subjects `texts` mentions, in cast order.

    Cast order, not order of appearance: `<Subject N>` is numbered off the list
    the user arranged, so that reordering the cast is how the speaker IDs are
    reordered too. See `speakers`.
    """
    pattern = citation_re(cast)
    if pattern is None:
        return []
    found = set()
    for text in texts:
        found.update(pattern.findall(str(text or "")))
    return [s for s in cast if s.handle in found]


def check(cast, assets):
    """Every cited subject's files are attached here, and are the right kind.

    `assets` is `compile.Asset`s — whatever this one generation carries after the
    pool has been injected. A source that is not among them is the error worth
    catching: the label would be defined in terms of a `<Picture N>` that the
    tokenizer is never shown.
    """
    by_handle = {a.handle: a for a in assets}
    names = {s.handle for s in cast}
    for subject in cast:
        if subject.handle in by_handle:
            raise SubjectError(
                f"@{subject.handle} is both a subject and an attached file — "
                f"one `@` means one thing, so rename one of them"
            )
        for handle in subject.files:
            if handle in names:
                raise SubjectError(
                    f"@{subject.handle} is built out of @{handle}, which is "
                    f"another subject — a subject is built out of files"
                )
            asset = by_handle.get(handle)
            if asset is None:
                raise SubjectError(
                    f"@{subject.handle} is built out of @{handle}, which is not "
                    f"attached to this generation"
                )
            if asset.role != "reference":
                raise SubjectError(
                    f"@{subject.handle} is built out of @{handle}, which is a "
                    f"{asset.role.replace('_', ' ')} — a keyframe is a fact "
                    f"about one moment of the target video, not a reference "
                    f"somebody is made of"
                )
        if subject.voice:
            asset = by_handle[subject.voice]
            if not _is_audio(asset):
                raise SubjectError(
                    f"@{subject.handle}'s voice is @{subject.voice}, which is "
                    f"a {asset.kind} — a voice reference is audio"
                )
        # The clip somebody is replaced *in* is not one of `files`: its own
        # content is kept — that is what a replacement is — so it keeps the
        # `<Video N>` definition an unclaimed reference gets, and only its
        # occupant moves. Which means its presence is checked here rather than
        # by the loop above.
        pairs = [(subject.motion, "motion")] if subject.motion else []
        pairs += [(handle, "place") for handle in subject.replaces]
        for handle, what in pairs:
            asset = by_handle.get(handle)
            if asset is None:
                raise SubjectError(
                    f"@{subject.handle} takes its {what} from @{handle}, which "
                    f"is not attached to this generation"
                )
            if asset.kind != "video" or _is_audio(asset):
                raise SubjectError(
                    f"@{subject.handle} takes its {what} from @{handle}, which "
                    f"is not a reference video"
                )


def _is_audio(asset):
    """Whether an asset arrives among the audio — mirrors `compile`'s own split."""
    return asset.kind == "audio" or getattr(asset, "track", None) == "sound"


def labels(cast):
    """handle -> `<Subject N>`, numbered in cast order.

    Declaration order, and deliberately: the guide numbers nothing by the order
    things happen in the target video except the speaker IDs, and those cannot
    be known before the video exists. The cast list is the order the user
    arranged, so it is the one answer they can see and change.
    """
    return {s.handle: f"<Subject {n}>" for n, s in enumerate(cast, start=1)}


def speakers(cast):
    """handle -> `S1`… for the subjects a voice is bound to, in cast order.

    The guide assigns `(Sx)` by the order of actual vocal events in the target
    video, which nothing here can know. Cast order is the substitute, and it is
    the user's to set: move Anna above Ben and Anna becomes S1.
    """
    out = {}
    for subject in cast:
        if subject.voice:
            out[subject.handle] = f"S{len(out) + 1}"
    return out


def claimed(cast):
    """Asset handles folded into a subject's definition, so nothing defines them
    twice.

    Section 2.2 again: a picture that only says what somebody looks like gets no
    entry of its own. `contextir.reference_lines` skips these, and the
    definition line below cites them instead.
    """
    return {handle for subject in cast for handle in subject.files}


# ---- the two sections -------------------------------------------------------


# What the label denotes, per `takes`. The sentence opens the way the guide's own
# examples open — "<Subject 1> is the young woman in <Picture 1>" — with the
# noun standing in for the description the user may not have written.
_NOUN = {
    "person": "the person",
    "object": "the object",
    "scene": "the environment",
    "style": "the visual style",
}

# What is carried over, where the user named no features of their own. Positive
# and only positive: section 4.1 closes with "do not treat newly added actions,
# backgrounds, or plot events in the target video as losses of reference
# fidelity", and there is not one negative clause in any of the guide's four
# retention examples.
#
# These lines used to carry a tail — "...and the source picture's background,
# palette, lighting, pose and action are not" — which is the same tail
# `contextir._DEFINE` writes for a file, borrowed. It does not belong on a
# subject, and not only because 4.1 says so: `<Subject N>` *means* "visible
# content abstracted from reference assets" (2.1), so the abstraction from the
# file is already in the label. `<Picture N>` is the label that denotes a file
# and needs saying which parts of it count; this one is not.
def _english(items):
    """`[a, b, c]` -> `"a, b, and c"`, the guide's own list punctuation."""
    items = list(items)
    if len(items) <= 1:
        return items[0] if items else ""
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


# The baseline attributes each `takes` is made of: what the label denotes when
# nobody has narrowed it. A cast card seeds one feature row per entry, so the
# four things a person reference carries are four rows somebody can describe,
# change or drop one at a time — which is the whole of "keep everything except
# his build". `_RETAINED` below is these same lists said as a sentence, for a
# subject seeded before this table existed.
#
# `(prefix, ((key, fragment), ...))`. The key is what the blob stores and what
# the card labels the row; the fragment is how it reads inside the list, which
# is not always the same word — a scene's surfaces are "its surfaces" once the
# leading "the" has been spent on the environment.
#
# `web/creator/state.js` seeds from its own copy of this table. The two are one
# list in two languages and `tests/test_cast_mirror.py` holds them to it.
ATTRIBUTES = {
    "person": ("their", (("face", "face"), ("hair", "hair"),
                         ("build", "build"), ("clothing", "clothing"))),
    "object": ("the object's own", (("form", "form"), ("colour", "colour"),
                                    ("markings", "markings"))),
    "scene": ("the", (("environment", "environment"), ("surfaces", "its surfaces"),
                      ("light", "its light"))),
    "style": ("the", (("medium", "medium"), ("palette", "palette"),
                      ("light", "light"), ("rendering", "rendering"))),
}


def _attr_phrase(takes, attr):
    """An attribute key -> the fragment it reads as, or the key itself.

    The fallback is for a row whose `takes` has moved under it — the editor
    converts a described row rather than dropping it, so a stale key is a thing
    that can arrive here, and the key is a word either way.
    """
    for key, fragment in ATTRIBUTES.get(takes, ATTRIBUTES["person"])[1]:
        if key == attr:
            return fragment
    return attr


def _all_attributes(takes):
    """The whole baseline, as one phrase. `_RETAINED`'s value, computed."""
    prefix, pairs = ATTRIBUTES[takes]
    return f"{prefix} {_english([fragment for _, fragment in pairs])}"


# What is carried over for a subject with no feature rows at all — every piece
# cast before the rows existed. Identical to what the seeded rows now compose,
# which is what keeps those pieces compiling the sentence they always did.
_RETAINED = {takes: _all_attributes(takes) for takes in TAKES}


def _cite(handles, asset_labels):
    """Asset handles -> the labels the tokenizer will see them as."""
    return _english([asset_labels.get(h, f"@{h}") for h in handles])


def _described_subject(subject):
    """A subject nothing but words stand behind, said as a noun phrase, or "".

    The description leads, because it is the whole of what is known; the `takes`
    noun follows it only where the word would otherwise be ambiguous — "the
    visual style" and "the environment" are things a sentence has to name, while
    a described person reads as a person without being called one.
    """
    described = subject.description.rstrip(".")
    if not described:
        return ""
    if subject.takes in ("person", "object"):
        return described
    return f"{_NOUN[subject.takes]}, {described}"


def definitions(cast, asset_labels, extra_lines=()):
    """The `subject_definitions` section: one line per label, cast first.

    `asset_labels` is `compile`'s handle -> `<Picture N>` map, so a definition
    cites the same ordinal the payload will present. `extra_lines` is what
    `contextir.reference_lines` wrote for the files *no* subject claimed —
    they belong in this section too rather than in a paragraph of their own,
    because the guide puts every label's meaning here and two places to look is
    one too many.

    Returns "" when there is nothing to define, which is what keeps a piece with
    no cast byte-identical to one compiled before this module existed.
    """
    subject_labels = labels(cast)
    voices = speakers(cast)
    lines = []
    for subject in cast:
        label = subject_labels[subject.handle]
        noun = _NOUN[subject.takes]
        # The relative clauses the guide's combined-source form is made of
        # (§2.1: "the woman whose appearance comes from <Picture 1> and whose
        # walking motion comes from <Video 1>"). A replacement is one of them,
        # not a branch of its own: the definition is where the model learns the
        # appearance and the vacancy belong to one person, and while these were
        # an either/or a pictured subject's "in place of" clause was written
        # nowhere at all.
        clauses = []
        if subject.sources:
            clauses.append("whose appearance comes from "
                           f"{_cite(subject.sources, asset_labels)}"
                           if subject.motion or subject.replaces else
                           f"in {_cite(subject.sources, asset_labels)}")
        if subject.motion:
            clauses.append("whose motion comes from "
                           f"{_cite([subject.motion], asset_labels)}")
        if subject.replaces:
            # The clips are where the vacancy is. Several of them read as one
            # list — the same person in a medium shot and a close-up is one
            # vacancy filmed twice, not two.
            who = subject.replaces_what or "the corresponding subject"
            clauses.append(f"who takes the place of {who} in "
                           f"{_cite(subject.replaces, asset_labels)}"
                           if subject.sources or subject.motion else
                           f"the target video puts in place of {who} in "
                           f"{_cite(subject.replaces, asset_labels)}")
        if clauses:
            line = f"{label} is {noun} {_english(clauses)}"
        else:
            # Words alone, which is what a cast is in a generation with no
            # references in it. The description *is* the definition here, so the
            # noun that stands in for a missing one would only pad it — and the
            # `, description` clause below is skipped for the same reason.
            described = _described_subject(subject)
            spoken = _described(subject.features)
            if spoken:
                described = (f"{described}, with {_feature_texts(spoken)}"
                             if described else
                             f"{noun}, {_feature_texts(spoken)}")
            lines.append(f"{label} is {described}.")
            continue
        if subject.description:
            line += f", {subject.description.rstrip('.')}"
        # The features, in the guide's own shape: "<Subject 1> is the young
        # woman in <Picture 1>, with long dark hair, a blue cardigan, and a thin
        # silver necklace." All of them, including the ones the target video
        # changes — 4.1's `partially_preserved` is a defined characteristic
        # being changed, so it has to be defined here first, and a definition
        # that quietly dropped the changed ones would leave the retention line
        # changing something the model was never told about.
        spoken = _described(subject.features)
        if spoken:
            line += f", with {_feature_texts(spoken)}"
        lines.append(line + ".")

        # The audio line is the guide's own form, and it carries the speaker ID
        # rather than the subject line doing it: section 2.3 binds a voice
        # reference to a target speaker there.
        if subject.voice:
            speaker = voices[subject.handle]
            lines.append(
                f"{_cite([subject.voice], asset_labels)} is the voice-timbre "
                f"reference for {label} ({speaker}), and its own words and "
                f"background sound are not copied."
            )
    lines.extend(line for line in extra_lines if line)
    return "\n".join(lines)


def _feature_texts(features):
    """The feature phrases, as the guide punctuates a list of them."""
    return _english([f.text for f in features])


def _described(features):
    """The features somebody actually described, for `subject_definitions`.

    A seeded row nobody has typed into is not a description — "<Subject 1> is
    the person in <Picture 1>, with face, hair, build, and clothing" says
    nothing the noun did not already say. It earns its place in
    `retention_analysis`, where the question is what is carried over rather than
    what the label denotes, and it is dropped here.
    """
    return [f for f in features if f.text]


def _carried(takes, kept):
    """What `kept` amounts to, as prose, and how many things that is.

    The seeded rows lead, in the order `ATTRIBUTES` lists them, and take the
    possessive the whole list used to be written with: four untouched rows
    compose "their face, hair, build, and clothing" — `_RETAINED` exactly, which
    is what makes seeding a card change nothing about what it compiles to. A row
    somebody described reads as their words instead of the attribute's name, and
    a row somebody dropped is simply not here.

    Features typed from nothing follow, sharing the possessive where there are
    seeded rows in front of them and standing alone where there are not: a
    subject cast before the rows existed has only these, and its line is the one
    it always was.
    """
    attrs = [f for f in kept if f.attr]
    items = ([f.phrase(takes) for f in attrs]
             + [f.text for f in kept if not f.attr])
    if not items:
        return "", 0
    if attrs:
        return f"{ATTRIBUTES[takes][0]} {_english(items)}", len(items)
    return _english(items), len(items)


def retention(cast, asset_labels, body):
    """The `retention_analysis` section: one line per subject.

    `body` is the finished description, with the labels already substituted into
    it, so the "appears in" half is read off the text rather than guessed.

    Written the way section 6's worked example writes it: the features named in
    `subject_definitions`, named again here, and said to be retained. Positively
    — see `_RETAINED` for why the negative half of these lines is gone.

    A feature the target video gives them instead is the one thing that could
    not be said before. It is a separate clause rather than a missing name,
    because 4.1's `partially_preserved` is "the referenced content is still
    used, but some defined characteristics are changed": the characteristic has
    to still be there to have been changed, so the line names what it was and
    what it is now.
    """
    subject_labels = labels(cast)
    lines = []
    for subject in cast:
        label = subject_labels[subject.handle]
        where = contextir.appears_in(label, body)
        # "appears in" is the guide's own wording for a subject entry (4.1), and
        # it is worth the two words: a bare `(<Shot 1>)` reads as the parenthetical
        # a *picture* entry takes, where the guide writes what the frame is for
        # instead ("[Shot 1] first frame").
        head = f"{label} (appears in {where})" if where else label
        clauses_lead = ""

        # What is carried over: the features they were given, or — where nobody
        # named any — the general claim their `takes` word makes.
        carried_count = 0
        if subject.kept:
            carried, carried_count = _carried(subject.takes, subject.kept)
        elif subject.features:
            # Every feature they have is changed. Nothing is carried, and saying
            # so beats naming the `takes` word's general claim, which the
            # changes below contradict one by one.
            carried = ""
        elif subject.sources or subject.motion:
            # The baseline, for a subject nobody has itemised. A seeded one has
            # said its piece — every row is gone, so nothing is carried — and
            # handing it back the whole list here is what would make dropping
            # the last row do nothing at all.
            carried = "" if subject.seeded else _RETAINED[subject.takes]
        elif subject.replaces:
            carried = ""
        else:
            # Words alone. There is no source file to carry anything over from,
            # so what the marker covers is the definition itself, and the line
            # says exactly that rather than claiming a reference it does not have.
            carried = ""
            clauses_lead = ("the definition above is the whole of what is fixed, "
                            "and nothing is carried over from a reference file")

        # One feature is a thing, several are things. The lists here are the
        # user's own noun phrases, so nothing else in the sentence can carry the
        # agreement for them.
        verb = "is" if carried_count == 1 else "are"
        clauses = [clauses_lead] if clauses_lead else []
        if carried:
            clauses.append(f"{carried} {verb} retained")
        if subject.replaces:
            # The subject is what appears; the person they stand in for is not.
            # This used to read "their face, hair, build, and clothing are
            # transferred onto <who>, whose framing, camera work and action are
            # kept" — a sentence whose every half tells the model to keep the
            # man and move the face onto him: "transferred onto" makes him the
            # surviving target, and the "whose" clause hangs the kept camera
            # work off *him*. What is kept of the clip is the clip's own line
            # to say (`contextir.retention_lines` names the replacement there),
            # and this one says only whose appearance stands in the shot and
            # whose performance it follows.
            who = subject.replaces_what or "the corresponding subject"
            clauses.append(
                f"they appear in place of {who} in "
                f"{_cite(subject.replaces, asset_labels)}, taking over the "
                f"source's action and timing")

        for feature in subject.changed:
            clauses.append(
                f"{feature.phrase(subject.takes)} is replaced by {feature.instead}")

        # A subject with nothing to say still has to say something: the marker
        # is not a sentence and a line that is only a marker claims a scope it
        # never states.
        said = "; ".join(clauses) or "the definition above is what is carried over"
        lines.append(f"{head}: {subject.relationship} - {said}.")

        if subject.voice:
            voice_label = _cite([subject.voice], asset_labels)
            lines.append(
                f"{voice_label}: reference - its vocal timbre guides how {label} "
                f"speaks, without copying the original signal."
            )
    return "\n".join(lines)

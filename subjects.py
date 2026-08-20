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


class SubjectError(ValueError):
    """A cast that cannot be resolved. `compile.py` re-raises it as its own."""


# What of the files behind a subject is the reference. The same four words an
# image takes in `compile.TAKES` — a subject is visible content, so the whole-
# video relationships (`edit`, `camera`, `continue`) are not among them: those
# are statements about the target video with no subject in them at all, and
# `<Video N>` is the label reserved for saying them.
TAKES = ("person", "object", "scene", "style")

# The reference guide's fixed relationship markers, section 4. These are output
# values, not prose — the guide spells them in English in every language.
MARKERS = ("fully_preserved", "partially_preserved", "transferred", "reused")

# Deliberately not the asset handles' shape. `compile.HANDLE_RE` matches
# `name-digit` because that is what the handle allocator writes, and a subject is
# named by the user rather than allocated — "anna" is the whole point, since a
# cast the user cannot read is a cast they cannot pin. No hyphen, so the two
# shapes can never be confused for one another by eye or by pattern.
HANDLE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")

# `[Shot 3]` and the label whose shots are being counted — see `_appears_in`.
SHOT_RE = re.compile(r"\[Shot\s+(\d+)\]")


class Subject:
    """One member of the cast. Immutable in practice; a plain class rather than
    a dataclass so the optional halves can carry their own docstrings."""

    __slots__ = ("handle", "sources", "takes", "description",
                 "motion", "voice", "replaces", "replaces_what", "marker")

    def __init__(self, handle, sources, takes="person", description="",
                 motion=None, voice=None, replaces=None, replaces_what="",
                 marker=None):
        self.handle = handle
        self.sources = tuple(sources)      # asset handles defining its appearance
        self.takes = takes                 # one of TAKES
        self.description = description     # the user's own words, folded into the definition
        self.motion = motion               # a reference video its movement comes from
        self.voice = voice                 # an audio reference that is its voice
        self.replaces = replaces           # a reference video it stands in for someone in
        self.replaces_what = replaces_what  # who, in that video, in the user's words
        # None means "derive it": a subject that replaces somebody is by
        # definition `transferred`, and anything else is preserved whole unless
        # the user says otherwise.
        self.marker = marker

    @property
    def relationship(self):
        """The retention marker this subject carries."""
        if self.marker:
            return self.marker
        return "transferred" if self.replaces else "fully_preserved"

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
        replaces = str(item.get("replaces") or "").strip() or None
        description = str(item.get("description") or "").strip()
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
        if not sources and not motion and not replaces and not description:
            raise SubjectError(
                f"@{handle}: a subject needs something behind it — a picture or "
                f"a clip to be built out of, a description of what they look "
                f"like, or the person they stand in for"
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
            motion=motion,
            voice=voice,
            replaces=replaces,
            replaces_what=str(item.get("replaces_what") or "").strip(),
            marker=marker,
        ))
    return cast


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
        for handle, what in ((subject.motion, "motion"), (subject.replaces, "place")):
            if not handle:
                continue
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
    entry of its own. `contextir.reference_preamble` skips these, and the
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

# What a definition claims and what it does not. The DiT is handed the whole
# file whatever the narrowing says, so the narrowing is prose or it is nothing —
# and a retention marker can only ever cover what the definition claimed. Same
# distinctions `contextir._DEFINE` draws for an unclaimed file, said about a
# subject rather than about a picture.
_RETAINED = {
    "person": "the face, hair, skin, build and clothing are retained, and the "
              "source picture's background, palette, lighting, pose and action "
              "are not",
    "object": "the object itself is retained, and the surroundings, lighting "
              "and arrangement it sits in are not",
    "scene": "the environment, its surfaces and its light are retained, and "
             "anyone standing in it, and its framing, are not",
    "style": "the medium, palette, light and rendering are retained, and the "
             "source's own subjects, layout and content are not",
}


def _english(items):
    """`[a, b, c]` -> `"a, b, and c"`, the guide's own list punctuation."""
    items = list(items)
    if len(items) <= 1:
        return items[0] if items else ""
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _cite(handles, asset_labels):
    """Asset handles -> the labels the tokenizer will see them as."""
    return _english([asset_labels.get(h, f"@{h}") for h in handles])


def _described(subject):
    """A subject nothing but words stand behind, said as a noun phrase.

    The description leads, because it is the whole of what is known; the `takes`
    noun follows it only where the word would otherwise be ambiguous — "the
    visual style" and "the environment" are things a sentence has to name, while
    a described person reads as a person without being called one.
    """
    described = subject.description.rstrip(".")
    if subject.takes in ("person", "object"):
        return described
    return f"{_NOUN[subject.takes]}, {described}"


def definitions(cast, asset_labels, extra_lines=()):
    """The `subject_definitions` section: one line per label, cast first.

    `asset_labels` is `compile`'s handle -> `<Picture N>` map, so a definition
    cites the same ordinal the payload will present. `extra_lines` is what
    `contextir.reference_preamble` wrote for the files *no* subject claimed —
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
        if subject.motion and subject.sources:
            line = (f"{label} is {noun} whose appearance comes from "
                    f"{_cite(subject.sources, asset_labels)} and whose motion "
                    f"comes from {_cite([subject.motion], asset_labels)}")
        elif subject.sources:
            line = f"{label} is {noun} in {_cite(subject.sources, asset_labels)}"
        elif subject.motion:
            line = (f"{label} is {noun} whose motion comes from "
                    f"{_cite([subject.motion], asset_labels)}")
        elif subject.replaces:
            # The subject is whoever the target video puts there instead, and
            # the clip is where the vacancy is.
            line = (f"{label} is {noun} the target video puts in place of "
                    f"{subject.replaces_what or 'the corresponding subject'} in "
                    f"{_cite([subject.replaces], asset_labels)}")
        else:
            # Words alone, which is what a cast is in a generation with no
            # references in it. The description *is* the definition here, so the
            # noun that stands in for a missing one would only pad it — and the
            # `, description` clause below is skipped for the same reason.
            lines.append(f"{label} is {_described(subject)}.")
            continue
        if subject.description:
            line += f", {subject.description.rstrip('.')}"
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


def _appears_in(label, body):
    """`[Shot 1], [Shot 3]` — where `label` is written, or "" if nowhere.

    Derived from the finished description rather than declared, because it is
    derivable: the shots are numbered in the text and the label is in it or it
    is not. A body with no shot markers at all is one shot, and a generation is
    one shot unless it says otherwise — so the common case answers `[Shot 1]`
    without anyone having written a marker.
    """
    if label not in (body or ""):
        return ""
    shots = []
    current = 1
    for piece in re.split(r"(\[Shot\s+\d+\])", body):
        match = SHOT_RE.fullmatch(piece)
        if match:
            current = int(match.group(1))
        elif label in piece and current not in shots:
            shots.append(current)
    return ", ".join(f"[Shot {n}]" for n in sorted(shots))


def retention(cast, asset_labels, body):
    """The `retention_analysis` section: one line per subject.

    `body` is the finished description, with the labels already substituted into
    it, so the "appears in" half is read off the text rather than guessed.
    """
    subject_labels = labels(cast)
    lines = []
    for subject in cast:
        label = subject_labels[subject.handle]
        where = _appears_in(label, body)
        head = f"{label} ({where})" if where else label
        if subject.sources or subject.motion:
            retained = _RETAINED[subject.takes]
        elif subject.replaces:
            retained = ""
        else:
            # Words alone. There is no source file to say what is carried over
            # from and what is dropped, so the line says exactly that — the
            # marker still has to cover something, and what it covers is the
            # definition.
            retained = ("the definition above is the whole of what is fixed, and "
                        "nothing is carried over from a reference file")
        if subject.replaces:
            who = subject.replaces_what or "the corresponding subject"
            moved = (f"{label} takes the place of {who} in "
                     f"{_cite([subject.replaces], asset_labels)}, whose framing, "
                     f"camera work and action are kept")
            retained = f"{retained}; {moved}" if retained else moved
        lines.append(f"{head}: {subject.relationship} - {retained}.")

        if subject.voice:
            voice_label = _cite([subject.voice], asset_labels)
            lines.append(
                f"{voice_label}: reference - its vocal timbre guides how {label} "
                f"speaks, without copying the original signal."
            )
    return "\n".join(lines)

"""The Context-IR skeleton H3-Base is actually prompted with.

H3 is a two-stage system. The hosted half — H3-Context-IR — rewrites whatever
the user typed into a labelled, sectioned intermediate representation, and the
open weights were trained only on its output. MiniMax do not open-source that
rewriter but they do publish what it emits (`skills/h3-prompt-writing`, mirrored
verbatim in the sibling `MiniMax-H3-LLM/research/sources/`), and the shape is
fixed:

    <mode instruction line>

    integrated_multimodal_description: [Shot 1] ...

    overall_soundscape: ...

    non_diegetic_music: ...

A bare sentence has none of that, so it lands off the distribution the DiT was
trained on. This module puts the skeleton back. It cannot invent the prose — a
real rewrite is phase 5's job and needs an LLM — but the field names, the
ordering and the mode instruction are mechanical, and emitting them costs
nothing and is what the model expects to read first.

**Everything here only adds what is missing.** A prompt that already carries its
own `integrated_multimodal_description:` — hand-written, or produced by a
refiner, or the six-section Ref2VA form — is passed through untouched. That is
the one rule worth holding onto: this is a floor, not a filter, so nothing a
user writes can be silently rewritten out from under them.
"""

import re

# The three base-mode fields, in the order the guide emits them.
BODY_FIELD = "integrated_multimodal_description"
SOUNDSCAPE_FIELD = "overall_soundscape"
MUSIC_FIELD = "non_diegetic_music"

# Ref2VA is a different, six-section form, and its body field is
# `detailed_description`. Its other three sections used to be the refiner's
# alone, so a reference prompt was never wrapped at all; they are derived from
# the chips and the cast now (see `summary`, `retention_lines` and
# `subjects.definitions`), so the form is always complete.
REF_BODY_FIELD = "detailed_description"

BODY_FIELDS = (BODY_FIELD, REF_BODY_FIELD)

# The three sections the reference form has that the base form does not, in the
# order the guide emits them. Each is derivable from what the user declared —
# the chips say what every file lends, the cast says who is in the video — so
# `compile_request` builds them and a refiner replaces them.
REF_SECTIONS = ("subject_definitions", "summary", "retention_analysis")

# The modes whose body belongs in `integrated_multimodal_description`.
BASE_MODES = ("T2VA", "I2VA", "L2VA", "FL2VA")

# `[Shot 1]`, `[Shot 12]` — the marker the description is segmented by.
SHOT_RE = re.compile(r"\[Shot\s+\d+\]")

# The guide's value for "there is deliberately none of this". A blank
# `non_diegetic_music` used to emit nothing at all, which reads to the model as
# a free hand rather than as a decision; `N/A` is the decision written down, and
# is the single most-cited community fix for a soundtrack nobody asked for.
NO_MUSIC = "N/A"

# What a timeline says about a sound seam. The inherited tail is presented to the
# tokenizer as `<Audio 1>`, and a label the prompt never defines is a label
# pointing at nothing — so this is the base-mode equivalent of the reference
# form's `subject_definitions`, written in the same voice.
AUDIO_SEAM_LINE = (
    "<Audio 1> is the end of the preceding shot's soundtrack. The target video's "
    "sound continues from it without a break, keeping the same ambience, key and "
    "tempo across the cut."
)


# ---- saying what each reference is ------------------------------------------
#
# The scope on an asset's chip — `Asset.takes` — is prose or it is nothing: the
# DiT is handed the same tensor whichever way the dial is set, and H3 has no
# reference-conditioning switch to carry the difference. Until now the only
# thing that read the dial was the refiner's glossary, so a piece queued without
# a rewrite had the setting quietly do nothing.
#
# These lines are the same distinction said mechanically, for the model rather
# than for a rewriter. They go where `AUDIO_SEAM_LINE` goes and for the same
# reason: the tokenizer is shown every reference and numbers it, and a label the
# prompt never defines is a label pointing at nothing.
#
# Written as statements about what is retained and what is not, because that is
# what the reference form's `subject_definitions` and `retention_analysis` say
# in the sentences the model was trained on. They cannot be a *rewrite* — no
# rule turns a sentence into a six-section document — so this stays a floor, the
# way the rest of this module is: emitted only where nothing better is present,
# and skipped entirely once a refiner has supplied the real sections.
#
# `%s` is the asset's label, already allocated by `compile.plan_references`, so
# the ordinals here and the tensors in the payload come from the one walk.
_DEFINE = {
    ("image", "full"): "%s is a reference picture. What the target video takes "
                       "from it is what the picture actually shows.",
    ("image", "person"): "%s is a person reference: the face, hair, skin, build "
                         "and clothing in it are retained, and its background, "
                         "palette, lighting, pose and action are not.",
    ("image", "object"): "%s is an object reference: the object itself is "
                         "retained, and the picture's surroundings, lighting "
                         "and arrangement are not.",
    ("image", "scene"): "%s is a scene reference: its environment, surfaces and "
                        "light are retained, and any people or passing objects "
                        "in it, and its framing, are not.",
    ("image", "style"): "%s is a style reference: its medium, palette, light "
                        "and rendering are retained, and its subjects, layout "
                        "and content are not.",
    # A still lending a pose: one moment of a movement, carried onto somebody
    # else, the way a clip's motion is. Whoever is in the picture stays out.
    ("image", "motion"): "%s is a motion reference: the action and pose in it "
                         "are carried onto the target video's own subject, and "
                         "nobody and nothing visible in the picture appears in "
                         "the target video.",

    ("video", "full"): "%s is a reference video.",
    ("video", "person"): "%s is a person reference: the face, hair, build and "
                         "clothing of the person in it are retained, and the "
                         "clip's setting, camera work, cuts and action are not.",
    ("video", "object"): "%s is an object reference: the object itself is "
                         "retained, and the clip's surroundings, camera work "
                         "and action are not.",
    ("video", "scene"): "%s is a scene reference: its environment, surfaces and "
                        "light are retained, and anyone in it, its framing and "
                        "its camera work are not.",
    ("video", "style"): "%s is a style reference: its medium, palette, light "
                        "and rendering are retained, and its subjects, action "
                        "and camera work are not.",
    # The two that move something onto a subject the clip does not contain. Both
    # say the clip's own content stays out, which is the failure they exist to
    # prevent.
    ("video", "motion"): "%s is a motion reference: the movement in it — its "
                         "path, its timing and its weight — is carried onto the "
                         "target video's own subject, and nobody and nothing "
                         "visible in the clip appears in the target video.",
    ("video", "camera"): "%s is a camera reference: its camera movement, its "
                         "shot changes and its pacing are followed, and nobody "
                         "and nothing visible in the clip appears in the target "
                         "video.",
    # The two whole-video relationships. Section 2.3's own phrasing, which is a
    # statement about what the label *is* — "<Video 1> is the source video for
    # the target video edit." These used to borrow the summary's opening line
    # instead ("The target video is an edited version of %s."), which read as
    # one sentence and was three: two edited clips claimed, twice over, to each
    # be the whole source of the edit. The summary says that sentence once now,
    # with every source in it, which is the section the guide puts it in.
    ("video", "edit"): "%s is a source video for the target video edit.",
    ("video", "continue"): "%s is the source video the target video continues "
                           "from.",

    ("audio", "full"): "%s is a reference audio clip.",
    ("audio", "voice"): "%s is a voice reference: the target speaker follows "
                        "its timbre and delivery, and its words and its "
                        "background sound are not copied.",
    ("audio", "music"): "%s is a music-style reference: its genre, "
                        "instrumentation and mood guide the target video's "
                        "score, and the recording itself is not reused.",
    ("audio", "ambience"): "%s is an ambience reference: its room tone and "
                           "sound texture guide the target video's background "
                           "sound, and the recording itself is not reused.",
    ("audio", "copy"): "%s is reused directly: its signal is the target video's "
                       "own audio.",
}

# A clip brought in with its soundtrack is two labels for one file, and the
# audio one is not addressable by handle — `_labels_from_plan` keys it
# `"<handle>:audio"` precisely because the handle is already spoken for. So its
# line names the clip it came off instead, which is the guide's own phrasing for
# a shared source.
_SOUNDTRACK = "%s is the synchronized audio track of %s."


def _define(asset, label):
    """The one sentence that says what `asset` is, or `None` for a role that
    already has one.

    A keyframe is not here: the mode instruction line above it already states
    how the target video aligns to it, and a second sentence saying the same
    thing in other words is one the model has to reconcile.
    """
    if asset.role != "reference":
        return None
    kind = "audio" if (asset.kind == "audio" or asset.track == "sound") else asset.kind
    form = _DEFINE.get((kind, asset.takes)) or _DEFINE.get((kind, "full"))
    return form % label if form else None


def reference_lines(plan, skip=(), replaced=None):
    """`compile.plan_references`'s walk -> the lines that define its labels.

    One line per label, in the order the tokenizer is shown them, so the prose
    and the payload agree about which file is which without either side
    re-deriving the order.

    `skip` is the handles a subject has already folded into its own definition —
    `subjects.claimed`. Section 2.2 of the reference guide gives a picture that
    only says what somebody looks like no entry of its own, so a claimed file is
    defined once, inside the `<Subject N>` that cites it, and not again here.
    A soundtrack's line is skipped by its `"<handle>:audio"` key, which is how
    `_labels_from_plan` addresses it.
    """
    # The `<Video N>` a soundtrack belongs to is assigned by the step after it,
    # so the clip's own label is looked up rather than carried forward.
    video_label = {step["asset"].handle: step["label"]
                   for step in plan if step["op"] == "video"}
    lines = []
    for step in plan:
        asset, label = step["asset"], step["label"]
        if step["op"] == "soundtrack":
            if f"{asset.handle}:audio" in skip:
                continue
            owner = video_label.get(asset.handle)
            lines.append(_SOUNDTRACK % (label, owner) if owner
                         else _DEFINE[("audio", "full")] % label)
            continue
        if asset.handle in skip:
            continue
        # A clip somebody is replaced in is an edit source whatever its chip
        # says — `retention_lines` and `summary` treat it as one, and a
        # definition calling it "a reference video" would be the odd voice out.
        if asset.kind == "video" and asset.handle in (replaced or {}):
            lines.append(_DEFINE[("video", "edit")] % label)
            continue
        line = _define(asset, label)
        if line:
            lines.append(line)
    return lines


# ---- what happens to each label ---------------------------------------------
#
# Section 4.1 says outright: "Use one line for each reference label." A label
# that `subject_definitions` defines and `retention_analysis` never scopes is
# half a declaration — the model is told what a file is and never told what
# becomes of it.
#
# The marker is chosen "only within the reference role already defined for that
# label", which is what decides most of these: a person reference whose defined
# role is the likeness alone is `fully_preserved` even though most of the file
# is dropped, because the *role* is what survives, not the pixels. The two that
# are not `fully_preserved` are the two that say so in the guide itself — a
# clip lending only its camera retains "only broad similarity in ... composition"
# (`weak_reference`), and motion carried onto somebody else is characteristics
# "transferred to a different identifiable target subject"
# (`attribute_transfer`).
#
# `refine.py`'s glossary tells the rewriter these same markers for these same
# takes. Two copies of one mapping is one too many, but they are addressed to
# different readers — one is an instruction to an LLM, this is the output — and
# `tests/test_ref_form.py` holds them to each other.
_MARKER = {
    ("image", "full"): "fully_preserved",
    ("image", "person"): "fully_preserved",
    ("image", "object"): "fully_preserved",
    ("image", "scene"): "fully_preserved",
    ("image", "style"): "fully_preserved",
    ("image", "motion"): "attribute_transfer",

    ("video", "full"): "fully_preserved",
    ("video", "person"): "fully_preserved",
    ("video", "object"): "fully_preserved",
    ("video", "scene"): "fully_preserved",
    ("video", "style"): "fully_preserved",
    ("video", "motion"): "attribute_transfer",
    ("video", "camera"): "weak_reference",
    # An edit keeps everything the description does not change, which is most of
    # the source and not all of it. `fully_preserved` would claim the target
    # video changes nothing, which is the one thing an edit never is.
    ("video", "edit"): "partially_preserved",
    ("video", "continue"): "partially_preserved",

    ("audio", "full"): "reference",
    ("audio", "voice"): "reference",
    ("audio", "music"): "reference",
    ("audio", "ambience"): "reference",
    ("audio", "copy"): "fully_copy",
}

# What the parenthetical after a label says. Section 4.1 gives a picture entry
# "([Shot 1] first frame)" and a video-structure entry "(cut and pacing
# structure)" — the parenthetical says what the label is *for*, and only a
# subject's says where it appears. Absent means no parenthetical at all.
_SCOPE_NOTE = {
    ("video", "camera"): "camera and pacing structure",
    ("video", "edit"): "source video",
    ("video", "continue"): "continuation point",
}

# The other half of each retention line: what actually becomes of it. Kept short
# — `subject_definitions` has already said what the label denotes, and section 4
# is where it is said what happens to it, not a second place to define it.
_BECOMES = {
    ("image", "full"): "what the picture shows is carried into the target video",
    ("image", "person"): "the likeness is carried onto the target video's own "
                         "subject and the picture's setting, light and pose are not",
    ("image", "object"): "the object is carried into the target video and the "
                         "setting it was photographed in is not",
    ("image", "scene"): "the place, its surfaces and its light are carried into "
                        "the target video and whoever stood in it is not",
    ("image", "style"): "the medium, palette, light and rendering are carried "
                        "into the target video and the source's own subject is not",
    ("image", "motion"): "the action and pose are carried onto the target "
                         "video's own subject, and nobody visible in the picture "
                         "appears in it",

    ("video", "full"): "what the clip shows is carried into the target video",
    ("video", "person"): "the likeness is carried onto the target video's own "
                         "subject and the clip's setting, camera work and action are not",
    ("video", "object"): "the object is carried into the target video and the "
                         "clip's surroundings and action are not",
    ("video", "scene"): "the place, its surfaces and its light are carried into "
                        "the target video and anyone in the clip is not",
    ("video", "style"): "the medium, palette, light and rendering are carried "
                        "into the target video and the clip's own subject and action are not",
    ("video", "motion"): "the movement, its timing and its weight are carried "
                         "onto the target video's own subject, and nobody visible "
                         "in the clip appears in it",
    ("video", "camera"): "the camera move, the shot changes and the pacing are "
                         "followed, and nothing visible in the clip appears in "
                         "the target video",
    ("video", "edit"): "everything this description does not change stays as it "
                       "is in the source video",
    ("video", "continue"): "the clip's closing subjects, framing and light carry "
                           "into the opening of the new footage",

    ("audio", "full"): "the clip guides the target video's sound without being copied",
    ("audio", "voice"): "its timbre and delivery guide the target speaker, and "
                        "its words and background sound are not copied",
    ("audio", "music"): "its genre, instrumentation and mood guide the score, "
                        "and the recording itself is not reused",
    ("audio", "ambience"): "its room tone and texture guide the background sound, "
                           "and the recording itself is not reused",
    ("audio", "copy"): "its signal is the target video's own audio",
}


def _kind(asset):
    """The vocabulary an asset's `takes` is drawn from — mirrors `_define`."""
    return "audio" if (asset.kind == "audio" or asset.track == "sound") else asset.kind


def retention_lines(plan, skip=(), body="", replaced=None):
    """`plan` -> the `retention_analysis` lines for the labels no subject claimed.

    The mirror of `reference_lines`: whatever that defined, this scopes, so the
    two sections carry the same set of labels and neither names one the other
    does not. A claimed file is skipped in both — its subject's own line covers
    it, and `subjects.retention` writes that one.

    `body` is the finished description, read only to say where a label appears.
    A label the description never cites still gets its line: it is in the
    payload either way, and an unscoped label is the thing this exists to
    prevent.

    `replaced` maps a video handle to `[(subject_label, who), ...]` — the cast
    members standing in for somebody in that clip. Its line is where the swap
    is scoped, the way the model card's own editing example scopes it ("...
    maintained while the central character is edited"): the generic edit line —
    "everything this description does not change stays as it is" — reads as
    keeping the very person the cast is replacing, since a one-line body never
    re-describes them.
    """
    video_label = {step["asset"].handle: step["label"]
                   for step in plan if step["op"] == "video"}
    lines = []
    for step in plan:
        asset, label = step["asset"], step["label"]
        if step["op"] == "soundtrack":
            if f"{asset.handle}:audio" in skip:
                continue
            # A soundtrack has no audio `takes` of its own — the chip it rides on
            # is scoped with the video vocabulary. Riding along with an edit is
            # the one case the guide settles outright ("When editing a source
            # video, use audio reuse as well if its original audio remains
            # audible"), and everything else is a reference rather than a copy.
            if asset.takes == "edit" or asset.handle in (replaced or {}):
                marker, becomes = "fully_copy", (
                    f"the original audio of {video_label.get(asset.handle, 'the source video')} "
                    f"remains audible in the target video")
            else:
                marker, becomes = "reference", (
                    "it guides the target video's sound without being copied")
            lines.append(f"{label}: {marker} - {becomes}.")
            continue
        if asset.handle in skip:
            continue
        if asset.role != "reference":
            continue
        kind = _kind(asset)
        swaps = (replaced or {}).get(asset.handle) if kind == "video" else None
        if swaps:
            # Somebody stands in for someone in this clip, so its line says both
            # halves in one sentence: everything around the vacancy is kept, and
            # the occupant is who moves. `partially_preserved` whatever the
            # chip's own take said — a clip marked `full` beside a replacement
            # would claim, `fully_preserved`, that its occupant is carried in,
            # which is the one thing this generation is for.
            marker = "partially_preserved"
            becomes = "; ".join(
                f"{who or 'the corresponding subject'} is replaced by {stands}"
                for stands, who in swaps)
            becomes = (f"the framing, camera work, timing, environment and "
                       f"everyone else are kept as they are in the source "
                       f"video, while {becomes}")
            lines.append(f"{label} (source video): {marker} - {becomes}.")
            continue
        marker = _MARKER.get((kind, asset.takes)) or _MARKER.get((kind, "full"))
        becomes = _BECOMES.get((kind, asset.takes)) or _BECOMES.get((kind, "full"))
        if not marker or not becomes:
            continue
        note = _SCOPE_NOTE.get((kind, asset.takes))
        if not note and kind != "audio":
            where = appears_in(label, body)
            note = f"appears in {where}" if where else None
        head = f"{label} ({note})" if note else label
        lines.append(f"{head}: {marker} - {becomes}.")
    return lines


# ---- what kind of job this is -----------------------------------------------
#
# Section 3's task-type table, read backwards: the prefix is not a judgement
# about the piece, it is a restatement of what the chips already say. `edit` is
# the only thing that makes a job `video editing`; a clip lending its camera is
# `reference generation`, which the guide says in as many words.
#
# The order is the guide's own, taken off its two worked examples — "[video
# editing + reference generation + audio reuse]" and "[video continuation +
# keyframe completion]". Whole-video relationships lead, then generation, then
# the frames, then the sound.
TASK_ORDER = ("video editing", "video continuation", "reference generation",
              "keyframe completion", "audio reuse", "audio reference")

_VIDEO_TASK = {"edit": "video editing", "continue": "video continuation"}


def task_types(plan, has_frames=False, edited=()):
    """The task types this generation actually satisfies, in the guide's order.

    Combined with " + " by `summary`, never repeated — section 3 says both.
    `edited` is extra video handles that are edit sources whatever their chip
    says — a clip somebody is replaced in is being directly modified, which is
    the guide's own test for `video editing`.
    """
    found = set()
    if has_frames:
        found.add("keyframe completion")
    for step in plan:
        asset = step["asset"]
        if step["op"] == "soundtrack":
            found.add("audio reuse"
                      if asset.takes == "edit" or asset.handle in edited
                      else "audio reference")
            continue
        if asset.role != "reference":
            continue
        kind = _kind(asset)
        if kind == "audio":
            found.add("audio reuse" if asset.takes == "copy" else "audio reference")
        elif kind == "video":
            if asset.handle in edited:
                found.add("video editing")
            else:
                found.add(_VIDEO_TASK.get(asset.takes, "reference generation"))
        else:
            found.add("reference generation")
    return [name for name in TASK_ORDER if name in found]


def _count(n, noun):
    """`2, "shot"` -> `"two shots"`. Small numbers as words, the way the guide
    writes them ("The three-shot exchange")."""
    words = ("no", "one", "two", "three", "four", "five", "six", "seven",
             "eight", "nine", "ten")
    count = words[n] if n < len(words) else str(n)
    return f"{count} {noun}" if n == 1 else f"{count} {noun}s"


def summary(plan, cast, subject_labels, asset_labels, shots=1, has_frames=False):
    """The `summary` section, derived rather than written.

    Section 3 wants one short paragraph: the task type, the target video, and
    the main reference relationships. Two of those three are facts this package
    already holds — the chips say what each file lends and the cast says who is
    in it — and the third is a plot summary nothing here can invent. So this
    writes what it knows and stops, which is a short paragraph about reference
    relationships and is exactly what the section is for.

    It is a floor like the rest of the module: `compile_request` only reaches
    for it where the refiner has not supplied a real one, and a refined summary
    replaces it whole.
    """
    # A clip somebody is replaced in is an edit source whether or not its chip
    # was narrowed to `edit` — the replacement is a direct modification of it.
    replaced_in = {h for s in cast for h in s.replaces}
    types = task_types(plan, has_frames, edited=replaced_in)
    prefix = f"[{' + '.join(types)}]" if types else ""

    edited = [step["label"] for step in plan
              if step["op"] == "video" and (step["asset"].takes == "edit"
                                            or step["asset"].handle in replaced_in)]
    continued = [step["label"] for step in plan
                 if step["op"] == "video" and step["asset"].takes == "continue"]

    sentences = []
    # The guide dictates this opening for an editing task, word for word.
    if edited:
        sentences.append(f"The target video is an edited version of {_english(edited)}.")
    if continued:
        sentences.append(f"The target video continues from the end of {_english(continued)}.")

    opener = "It runs" if sentences else "The target video runs"
    body = f"{opener} {_count(max(1, int(shots)), 'shot')}"
    named = [subject_labels[s.handle] for s in cast if s.handle in subject_labels]
    if named:
        body += f" and features {_english(named)}"
    sentences.append(body + ".")

    # The one relationship worth restating up here, because it is the whole job
    # wherever somebody has it set: who stands in for whom.
    for subject in cast:
        if not subject.replaces or subject.handle not in subject_labels:
            continue
        who = subject.replaces_what or "the corresponding subject"
        where = _english([asset_labels.get(h, f"@{h}") for h in subject.replaces])
        sentences.append(
            f"{subject_labels[subject.handle]} takes the place of {who} in {where}.")

    return f"{prefix} {' '.join(sentences)}".strip()


def _english(items):
    """`[a, b, c]` -> `"a, b, and c"`. `subjects._english`'s twin; the two
    modules do not import each other, which is what keeps both unit-testable
    without the package around them."""
    items = list(items)
    if len(items) <= 1:
        return items[0] if items else ""
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def count_shots(body):
    """How many shots a description holds — what `instruction`'s `Shot N` is."""
    return len(SHOT_RE.findall(body or ""))


# `[Shot 3]` with its number, for `appears_in`.
_SHOT_NUMBER_RE = re.compile(r"\[Shot\s+(\d+)\]")


def appears_in(label, body):
    """`"[Shot 1], [Shot 3]"` — where `label` is written, or "" if nowhere.

    Derived from the finished description rather than declared, because it is
    derivable: the shots are numbered in the text and the label is in it or it
    is not. A body with no shot markers at all is one shot, and a generation is
    one shot unless it says otherwise — so the common case answers `[Shot 1]`
    without anyone having written a marker.

    Lives here rather than in `subjects.py` because both sections need it —
    a subject's retention line and a bare reference's — and the shot marker is
    this module's to know.
    """
    if label not in (body or ""):
        return ""
    shots = []
    current = 1
    for piece in re.split(r"(\[Shot\s+\d+\])", body):
        match = _SHOT_NUMBER_RE.fullmatch(piece)
        if match:
            current = int(match.group(1))
        elif label in piece and current not in shots:
            shots.append(current)
    return ", ".join(f"[Shot {n}]" for n in sorted(shots))


def has_field(text, name):
    """Whether `text` already carries a `name:` section, at the start of a line."""
    return re.search(rf"^[ \t]*{re.escape(name)}[ \t]*:", text or "", re.MULTILINE) is not None


def _has_instruction(text):
    """Whether `text` already opens with a keyframe-alignment instruction.

    Matched on the two documented openings rather than on a field name, because
    the instruction is a bare sentence with no `name:` marker to look for.
    """
    head = (text or "").lstrip()
    return head.startswith("For the target video,") or head.startswith("How the reference pictures align")


def shot_time(seconds):
    """`3.5` -> `"00:03.500"`, the cut-time format the guide writes.

    Section 4.2: every shot after the first opens with a strictly increasing cut
    time. This is the only place that format is spelled, so a change here moves
    every cut in a one-pass render.
    """
    total_ms = int(round(float(seconds) * 1000))
    minutes, rest = divmod(total_ms, 60_000)
    secs, ms = divmod(rest, 1000)
    return f"{minutes:02d}:{secs:02d}.{ms:03d}"


# `At 00:03.500,` at the head of a shot — already written by hand, so not added.
CUT_TIME_RE = re.compile(r"^\s*At\s+\d{1,3}:\d{2}\.\d{3}\s*,")


def shot_body(shots):
    """`[(at_seconds, text), ...]` -> one `[Shot n]`-marked description.

    The guide's section 4.2 in one function: shot 1 carries no timestamp, every
    later shot opens with its cut time, and the prose after the comma is the
    user's own — including which of `the camera cuts to` / `the shot transitions
    to` they wanted. Inventing a transition verb here would be writing a line of
    their description for them, and the guide lists five to choose between.

    A card that already carries its own markers is passed through verbatim and
    counts for as many shots as it numbers, so writing two shots into one card
    does not knock the rest of the timeline out of step. Its numbers are checked
    against the position it actually occupies and refused if they disagree —
    refusing is not rewriting, and the alternative is a description with two
    `[Shot 2]`s in it that nothing would have complained about.
    """
    out = []
    number = 1
    for position, (at, text) in enumerate(shots, start=1):
        text = (text or "").strip()
        if not text:
            raise ValueError(
                f"shot {position} has no prompt — the shots of one pass are a "
                f"single description with cuts in it, so an empty one would leave "
                f"a cut with nothing on the far side of it"
            )

        own = [re.sub(r"\s+", " ", m) for m in SHOT_RE.findall(text)]
        if own:
            want = [f"[Shot {n}]" for n in range(number, number + len(own))]
            if own != want:
                raise ValueError(
                    f"shot {position} numbers its own shots {' '.join(own)}, but in this "
                    f"timeline it is {' '.join(want)} — renumber it, or drop the markers "
                    f"and let the timeline number the shots"
                )
            out.append(text)
            number += len(own)
            continue

        head = f"[Shot {number}]"
        if number > 1 and not CUT_TIME_RE.match(text):
            head += f" At {shot_time(at)},"
        out.append(f"{head} {text}")
        number += 1
    return " ".join(out)


def instruction(mode, seconds, shots=1):
    """The first line of the prompt for a keyframe mode, or None.

    Quoted from the official guide rather than paraphrased — including FL2VA's
    unbracketed `Picture 1`, which differs from the other two lines and is not a
    typo on this end. `S.SS` is the effective duration to exactly two decimals,
    so it must be the real frame-count-derived duration and never the pill's
    whole number.

    `shots` is how many shots the description holds. The end frame is reached by
    the *last* one — the guide writes `(from Shot N)` — which only differs from
    `Shot 1` in a one-pass render of several shots. The start frame is always
    Shot 1's, whatever follows it.

    T2VA has no instruction (there is no picture to align), and REF2VA states its
    alignment inside `retention_analysis` instead.
    """
    end = f"{float(seconds):.2f}"
    last = max(1, int(shots))
    if mode == "I2VA":
        return ("For the target video, at 0.00 seconds into the target video, "
                "<Picture 1> (from [Shot 1]) is fully referenced.")
    if mode == "FL2VA":
        return ("How the reference pictures align with the target video — Picture 1 "
                "(from Shot 1) aligns with the 0.00-second mark of the target video; "
                f"Picture 2 (from Shot {last}) aligns with the {end}-second mark of the target video.")
    if mode == "L2VA":
        return ("How the reference pictures align with the target video — <Picture 1> "
                f"(from [Shot {last}]) aligns with the {end}-second mark of the target video.")
    return None


def ref_frame_alignment(first_label, last_label, seconds, shots=1):
    """The keyframe alignment line for a reference generation carrying its own
    start/end frames, or "".

    The same statement `instruction` quotes for the base modes, with the
    ordinals the frames actually took: they are presented *after* the
    references (see `compile._trailing_frame_labels`), so the first frame is
    not `<Picture 1>` here and the line has to name the label it was given.
    Rides in `compose`'s preamble slot — REF2VA's own instruction line states
    its alignment inside `retention_analysis`, which a refined form still owns;
    this line is about the pinned frames alone and coexists with it.
    """
    end = f"{float(seconds):.2f}"
    last_shot = max(1, int(shots))
    parts = []
    if first_label:
        parts.append(f"{first_label} (from [Shot 1]) aligns with the 0.00-second "
                     f"mark of the target video")
    if last_label:
        parts.append(f"{last_label} (from [Shot {last_shot}]) aligns with the "
                     f"{end}-second mark of the target video")
    if not parts:
        return ""
    return ("How the reference pictures align with the target video — "
            + "; ".join(parts) + ".")


def compose(mode, body, soundscape="", music="", seconds=0.0, preamble="", shots=1,
            sections=None):
    """The user's prose -> the sectioned prompt the DiT was trained to read.

    `body` is what the user wrote, with `@handles` already substituted and any
    LoRA trigger words already in front of it — triggers belong inside the
    description, not above the instruction line, because the instruction has to
    be the prompt's first line.

    A blank `soundscape` or `music` emits nothing at all. `N/A` is the guide's
    value for "there is deliberately none of this", which is a real thing to say
    and a very different one from leaving the box empty, so it stays something
    the user types rather than something inferred from an empty string.

    `sections` is `REF_SECTIONS -> prose`. It used to come only from the refiner,
    and a REF2VA prompt without one was emitted as a bare sentence with
    `<Picture 1>` substituted into it — no `detailed_description:` wrapper, no
    labels defined, nothing the reference form has. That was the single largest
    thing wrong with the direct path: the six-section form is what Ref2VA was
    trained on, and a piece queued without a rewrite was landing off it
    entirely. `compile_request` now derives all three from the chips and the
    cast, so the form is complete whether or not anybody ran a refiner, and a
    refined section replaces the derived one wherever it exists.

    What no rule can derive is the guide's 350-500 words of shot description.
    This builds the document; the prose inside it is still the user's sentence
    until a refiner writes a better one.
    """
    body = (body or "").strip()
    soundscape = (soundscape or "").strip()
    music = (music or "").strip()
    sections = sections or {}

    out = []

    line = instruction(mode, seconds, shots)
    if line and not _has_instruction(body):
        out.append(line)

    # After the instruction, which has to be the first line, and before the
    # description — the same slot the reference form gives `subject_definitions`.
    preamble = (preamble or "").strip()
    if preamble:
        out.append(preamble)

    # Whether this prompt is written in the reference form, decided by whether
    # there is anything to declare rather than by which mode was derived.
    #
    # It used to be `mode == "REF2VA"`, and a cast in a text-only generation got
    # two of the sections with the base form's body field — a hybrid neither
    # guide describes. The mode is a statement about which slot the payload
    # fills, not about how the prompt is written: the two trainings share an
    # architecture, people run reference-form prompts against T2VA and get what
    # they asked for, and the weights do not police the field name. So a piece
    # that has something to define is written in the form built for defining
    # things, whatever it is about to be encoded as.
    #
    # A bare sentence with no cast and no references still gets the base form.
    # There is nothing to declare there, and `detailed_description:` with no
    # sections above it would be claiming a form the rest of which is missing —
    # which is the same mistake in the other direction.
    reference_form = any(str(sections.get(name) or "").strip() for name in REF_SECTIONS)

    # Each is skipped where the body already carries one, so a prompt somebody
    # has hand-written into full form is not given a second copy of a section it
    # already has.
    for name in (REF_SECTIONS if reference_form else ()):
        value = str(sections.get(name) or "").strip()
        if value and not has_field(body, name):
            out.append(f"{name}: {value}")

    if body:
        # Only wrapped when the body is plain prose. Anything already sectioned —
        # either form — is its own rewrite already.
        field = REF_BODY_FIELD if reference_form else BODY_FIELD
        if not any(has_field(body, f) for f in BODY_FIELDS):
            # The description is written shot by shot and every example opens on
            # a marker. A segment is one shot, so `[Shot 1]` is the whole of it —
            # unless the body already numbers its own, which is someone writing
            # several shots into one generation and knowing that they are.
            if not SHOT_RE.search(body):
                body = f"[Shot 1] {body}"
            body = f"{field}: {body}"
        out.append(body)

    if soundscape and not has_field(body, SOUNDSCAPE_FIELD):
        out.append(f"{SOUNDSCAPE_FIELD}: {soundscape}")
    # `NO_MUSIC` where the user named none: a missing field is a free hand and
    # this field is the one the model most reliably fills on its own. The
    # soundscape above has no such default — `N/A` there is a claim of total
    # silence, which is a real thing to mean and not one to infer from an empty
    # box, so a blank one still emits nothing.
    if (music or body) and not has_field(body, MUSIC_FIELD):
        # `body` guards the default and not the value: an empty request composes
        # to nothing, as it always has, and a piece that is only a music line is
        # still that line.
        out.append(f"{MUSIC_FIELD}: {music or NO_MUSIC}")

    return "\n\n".join(out)

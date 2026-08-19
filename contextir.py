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

# Ref2VA is a different, six-section form. Its body field is `detailed_description`
# and it carries four more sections we cannot synthesise from one line of prose —
# so a reference prompt is never wrapped, only checked for the two audio fields it
# shares with the base form.
REF_BODY_FIELD = "detailed_description"

BODY_FIELDS = (BODY_FIELD, REF_BODY_FIELD)

# The four sections the reference form has that the base form does not, in the
# order the guide emits them — the last of them being the body itself. Nothing
# synthesises these from a sentence; they arrive whole from the refiner or not
# at all, which is why `compose` only builds this form when it is handed them.
REF_SECTIONS = ("subject_definitions", "summary", "retention_analysis")

# The modes whose body belongs in `integrated_multimodal_description`.
BASE_MODES = ("T2VA", "I2VA", "L2VA", "FL2VA")

# `[Shot 1]`, `[Shot 12]` — the marker the description is segmented by.
SHOT_RE = re.compile(r"\[Shot\s+\d+\]")

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
    # The two whole-video relationships, phrased the way the guide's own summary
    # line opens.
    ("video", "edit"): "The target video is an edited version of %s. Everything "
                       "this description does not change stays as it is in the "
                       "source video.",
    ("video", "continue"): "The target video continues from the end of %s, "
                           "carrying its closing subjects, framing and light "
                           "into the opening of the new footage.",

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


def reference_preamble(plan):
    """`compile.plan_references`'s walk -> the lines that define its labels.

    One line per label, in the order the tokenizer is shown them, so the prose
    and the payload agree about which file is which without either side
    re-deriving the order.
    """
    # The `<Video N>` a soundtrack belongs to is assigned by the step after it,
    # so the clip's own label is looked up rather than carried forward.
    video_label = {step["asset"].handle: step["label"]
                   for step in plan if step["op"] == "video"}
    lines = []
    for step in plan:
        asset, label = step["asset"], step["label"]
        if step["op"] == "soundtrack":
            owner = video_label.get(asset.handle)
            lines.append(_SOUNDTRACK % (label, owner) if owner
                         else _DEFINE[("audio", "full")] % label)
            continue
        line = _define(asset, label)
        if line:
            lines.append(line)
    return " ".join(lines)


def count_shots(body):
    """How many shots a description holds — what `instruction`'s `Shot N` is."""
    return len(SHOT_RE.findall(body or ""))


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


def compose(mode, body, soundscape="", music="", seconds=0.0, preamble="", shots=1,
            sections=None, definitions=""):
    """The user's prose -> the sectioned prompt the DiT was trained to read.

    `body` is what the user wrote, with `@handles` already substituted and any
    LoRA trigger words already in front of it — triggers belong inside the
    description, not above the instruction line, because the instruction has to
    be the prompt's first line.

    A blank `soundscape` or `music` emits nothing at all. `N/A` is the guide's
    value for "there is deliberately none of this", which is a real thing to say
    and a very different one from leaving the box empty, so it stays something
    the user types rather than something inferred from an empty string.

    `sections` is `REF_SECTIONS -> prose`, and only the refiner ever supplies it.
    Handed them, this builds the reference form's full six sections; handed
    nothing, a REF2VA body passes through exactly as it always has. The
    distinction matters: those three sections cannot be derived from a sentence,
    so wrapping a hand-written reference prompt in `detailed_description:` would
    claim a form the rest of which is missing.

    `definitions` is `reference_preamble`'s output — one sentence per reference
    label, saying what that file lends. It stands in the same slot as `preamble`
    and is dropped the moment something better occupies it: a refined reference
    form defines its labels in `subject_definitions` and states their scope in
    `retention_analysis`, and a body that carries either section is one somebody
    has already written by hand. Two descriptions of the same reference is worse
    than none, because the model has to decide which of them it is being told.
    """
    body = (body or "").strip()
    soundscape = (soundscape or "").strip()
    music = (music or "").strip()

    out = []

    line = instruction(mode, seconds, shots)
    if line and not _has_instruction(body):
        out.append(line)

    # After the instruction, which has to be the first line, and before the
    # description — the same slot the reference form gives `subject_definitions`.
    preamble = (preamble or "").strip()
    if preamble:
        out.append(preamble)

    # The three sections that stand in front of the description in the reference
    # form. Each is skipped where the body already carries one, so a refined
    # prompt the user has since hand-edited into full form is not given a second
    # copy of a section it already has.
    reference_form = mode == "REF2VA" and bool(sections)

    # What each reference is, where nothing else says it. See `definitions`.
    definitions = (definitions or "").strip()
    if (definitions and not reference_form
            and not any(has_field(body, name) for name in REF_SECTIONS)):
        out.append(definitions)

    if reference_form:
        for name in REF_SECTIONS:
            value = str(sections.get(name) or "").strip()
            if value and not has_field(body, name):
                out.append(f"{name}: {value}")

    if body:
        # Only wrapped when the body is plain prose. Anything already sectioned —
        # either form — is its own rewrite already.
        field = (BODY_FIELD if mode in BASE_MODES else
                 REF_BODY_FIELD if reference_form else None)
        if field and not any(has_field(body, f) for f in BODY_FIELDS):
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
    if music and not has_field(body, MUSIC_FIELD):
        out.append(f"{MUSIC_FIELD}: {music}")

    return "\n\n".join(out)

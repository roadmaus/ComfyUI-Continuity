"""The cast: `<Subject N>` and the two sections it makes derivable.

Runs standalone — `python tests/test_subjects.py` — with no torch and no
ComfyUI, because `subjects.py` and `compile.py` are deliberately free of both.

The assertions that matter most are the ones about *citation*: a subject's name
is only a citation because somebody declared it, so a piece with no cast has to
compile to exactly what it always did, and `@anna` in a piece where nobody cast
Anna has to stay prose. If that ever stops being true, every prompt in the pack
that happens to contain an at-sign changes meaning at once.
"""

import importlib.util
import os
import sys

import layout
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    package = types.ModuleType("mmc")
    package.__path__ = [layout.PY_ROOT]
    sys.modules["mmc"] = package
    modules = {}
    for name in ("canvas", "contextir", "subjects", "compile"):
        spec = importlib.util.spec_from_file_location(f"mmc.{name}", layout.py(name))
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"mmc.{name}"] = module
        setattr(package, name, module)
        spec.loader.exec_module(module)
        modules[name] = module
    return modules["subjects"], modules["compile"]


subjects, compiler = _load()

from harness import FAILURES, check, passed


def expect_error(label, fn, fragment):
    try:
        fn()
    except (compiler.CompileError, subjects.SubjectError) as exc:
        if fragment.lower() not in str(exc).lower():
            FAILURES.append(f"{label}: error {str(exc)!r} does not mention {fragment!r}")
    except Exception as exc:  # noqa: BLE001
        FAILURES.append(f"{label}: raised {type(exc).__name__} instead: {exc}")
    else:
        FAILURES.append(f"{label}: expected an error, got none")


def image(handle, takes="full", **extra):
    return {"handle": handle, "kind": "image", "role": "reference",
            "filename": f"{handle}.png", **({"takes": takes} if takes != "full" else {}), **extra}


def video(handle, **extra):
    return {"handle": handle, "kind": "video", "role": "reference",
            "filename": f"{handle}.mp4", "track": "picture", **extra}


def audio(handle, **extra):
    return {"handle": handle, "kind": "audio", "role": "reference",
            "filename": f"{handle}.wav", **extra}


def request(prompt, assets, cast, **extra):
    return {"prompt": prompt, "assets": assets, "subjects": cast, **extra}


# --- parsing -----------------------------------------------------------------

expect_error("a hyphenated name is refused",
             lambda: subjects.parse([{"handle": "anna-1", "from": ["img-1"]}]),
             "no hyphen")
expect_error("two subjects cannot share a name",
             lambda: subjects.parse([{"handle": "anna", "from": ["img-1"]},
                                     {"handle": "anna", "from": ["img-2"]}]),
             "both called")
expect_error("a subject with nothing behind it at all is refused",
             lambda: subjects.parse([{"handle": "anna"}]),
             "needs something behind it")
expect_error("a description of only whitespace is nothing behind it",
             lambda: subjects.parse([{"handle": "anna", "description": "   "}]),
             "needs something behind it")

# A cast in a generation with no references in it. There is no picture to point
# at in T2VA, so the description is the whole of what the label can mean — and
# that is still worth having, because it is what keeps her the same woman in
# shot 1 and in shot 9.
described = subjects.parse([{"handle": "anna", "description": "a woman in her "
                             "thirties, close-cropped hair"}])
check("a subject described in words alone is allowed",
      described[0].description, "a woman in her thirties, close-cropped hair")
check("she claims no files",
      described[0].files, [])
check("her definition is the description, with no noun padding it",
      subjects.definitions(described, {}),
      "<Subject 1> is a woman in her thirties, close-cropped hair.")
check("a described environment is named, because the word carries information",
      subjects.definitions(subjects.parse(
          [{"handle": "loft", "takes": "scene",
            "description": "a bare concrete loft at dusk"}]), {}),
      "<Subject 1> is the environment, a bare concrete loft at dusk.")
check("her retention line says there is no reference to carry anything over from",
      subjects.retention(described, {}, "<Subject 1> waits."),
      "<Subject 1> (appears in [Shot 1]): fully_preserved - the definition above is the "
      "whole of what is fixed, and nothing is carried over from a reference file.")
expect_error("an unknown take is refused",
             lambda: subjects.parse([{"handle": "anna", "from": ["img-1"], "takes": "camera"}]),
             "takes must be one of")
expect_error("an unknown relationship marker is refused",
             lambda: subjects.parse([{"handle": "anna", "from": ["img-1"],
                                      "relationship": "kept"}]),
             "relationship must be one of")

# A subject that is only a vacancy in somebody else's clip is legal: "whoever is
# there now, replaced" is a real thing to say and has a reference behind it.
check("a replacement needs no source of its own",
      len(subjects.parse([{"handle": "anna", "replaces": "vid-1"}])), 1)


# --- citation ----------------------------------------------------------------

cast = subjects.parse([{"handle": "anna", "from": ["img-1"]},
                       {"handle": "ben", "from": ["img-2"]}])

check("a declared name is a citation",
      [s.handle for s in subjects.cited(cast, ["@anna walks in"])], ["anna"])
check("an undeclared name is not",
      subjects.cited(cast, ["@carol walks in"]), [])
check("citations come back in cast order, not order of appearance",
      [s.handle for s in subjects.cited(cast, ["@ben looks at @anna"])], ["anna", "ben"])
check("a name inside a longer word is not a citation",
      subjects.cited(cast, ["@annabelle walks in"]), [])
check("an empty cast matches nothing at all",
      subjects.citation_re([]), None)

check("labels are numbered in cast order",
      subjects.labels(cast), {"anna": "<Subject 1>", "ben": "<Subject 2>"})

_voiced = subjects.parse([{"handle": "anna", "from": ["img-1"]},
                          {"handle": "ben", "from": ["img-2"], "voice": "aud-1"},
                          {"handle": "cal", "from": ["img-3"], "voice": "aud-2"}])
check("speaker ids skip the silent and follow the cast order",
      subjects.speakers(_voiced), {"ben": "S1", "cal": "S2"})


# --- the prose ---------------------------------------------------------------

_one = subjects.parse([{"handle": "dog", "from": ["img-1", "img-2", "img-3"],
                        "takes": "object", "description": "a curved tail"}])
_labels = {"img-1": "<Picture 1>", "img-2": "<Picture 2>", "img-3": "<Picture 3>"}
check("several pictures are one subject, listed the guide's way",
      subjects.definitions(_one, _labels),
      "<Subject 1> is the object in <Picture 1>, <Picture 2>, and <Picture 3>, "
      "a curved tail.")

_split = subjects.parse([{"handle": "anna", "from": ["img-1"], "motion": "vid-1"}])
check("appearance and motion are one subject from two files",
      subjects.definitions(_split, {"img-1": "<Picture 1>", "vid-1": "<Video 1>"}),
      "<Subject 1> is the person whose appearance comes from <Picture 1> and "
      "whose motion comes from <Video 1>.")

_swap = subjects.parse([{"handle": "anna", "from": ["img-1"], "replaces": "vid-1",
                         "replaces_what": "the man at the counter"}])
_swap_labels = {"img-1": "<Picture 1>", "vid-1": "<Video 1>"}
check("a replacement stays fully_preserved — the swap is the clip's line to scope",
      _swap[0].relationship, "fully_preserved")
_ret = subjects.retention(_swap, _swap_labels, "[Shot 1] <Subject 1> pours coffee.")
check("and says who is going, in the retention line",
      "the man at the counter in <Video 1>" in _ret, True)
check("and the baseline appearance is retained, not transferred onto him",
      "their face, hair, build, and clothing are retained" in _ret, True)
check("and the subject is what appears in the vacancy",
      "they appear in place of the man at the counter in <Video 1>" in _ret, True)

_where = subjects.parse([{"handle": "anna", "from": ["img-1"]}])
check("where a subject appears is read off the shots she is written into",
      subjects.retention(_where, {"img-1": "<Picture 1>"},
                         "[Shot 1] <Subject 1> walks. [Shot 2] a door. "
                         "[Shot 3] <Subject 1> again.").split(":")[0],
      "<Subject 1> (appears in [Shot 1], [Shot 3])")
check("a body with no shot markers at all is one shot",
      subjects.retention(_where, {"img-1": "<Picture 1>"},
                         "<Subject 1> walks.").split(":")[0],
      "<Subject 1> (appears in [Shot 1])")


# --- through the compiler ----------------------------------------------------

_plain = compiler.compile_request(request("a woman walks in @img-1", [image("img-1")], []))
# The section is still written — the reference in it has to be defined — but
# nobody is in it, which is what having no cast means.
check("a piece with no cast defines its files and no subjects",
      "<Subject" in _plain.prompt, False)
check("...and the file is defined all the same",
      "subject_definitions: <Picture 1> is a reference picture." in _plain.prompt, True)
check("and an undeclared name stays prose",
      "@carol" in compiler.compile_request(
          request("@carol walks in @img-1", [image("img-1")], [])).body, True)

_cast = compiler.compile_request(request(
    "@anna looks at @ben.",
    [image("img-1"), image("img-2"), image("img-3"), audio("aud-1", takes="voice")],
    [{"handle": "anna", "from": ["img-1", "img-2"], "description": "a blue cardigan",
      "voice": "aud-1"},
     {"handle": "ben", "from": ["img-3"]}]))
check("a cited subject becomes its label in the body",
      "<Subject 1> looks at <Subject 2>." in _cast.body, True)
check("the definitions cite the pictures rather than standing beside them",
      "<Subject 1> is the person in <Picture 1> and <Picture 2>, a blue cardigan."
      in _cast.prompt, True)
check("a voice is bound with its speaker id",
      "<Audio 1> is the voice-timbre reference for <Subject 1> (S1)" in _cast.prompt, True)
check("a claimed picture gets no definition of its own",
      "<Picture 1> is a person reference" in _cast.prompt, False)
check("and the body is wrapped as the reference form's description",
      "detailed_description:" in _cast.prompt, True)
check("retention is written for every cited subject",
      _cast.prompt.count("fully_preserved"), 2)

# Take somebody out of a shot by deleting their name and their pictures go with
# them. Casting attaches files — that is what makes @anna mean anything — so a
# subject nobody cites leaves references behind that exist for no other reason,
# and encoding those sends the model a picture of somebody the prompt never
# mentions. Sole claims only: a file two of them share stays while either is
# cited, and one the user attached in its own right is nobody's to remove.
_dropped = compiler.compile_request(request(
    "@anna waits.",
    [image("img-1"), image("img-2"), image("img-3")],
    [{"handle": "anna", "from": ["img-1"]},
     {"handle": "ben", "from": ["img-2"]}]))
check("an uncited subject's own picture is not sent",
      [a.handle for a in _dropped.ref_images], ["img-1", "img-3"])
check("...and the labels are numbered off what is left, with no gap in them",
      "<Subject 1> is the person in <Picture 1>." in _dropped.prompt, True)

_shared = compiler.compile_request(request(
    "@anna waits.",
    [image("img-1")],
    [{"handle": "anna", "from": ["img-1"]},
     {"handle": "ben", "from": ["img-1"]}]))
check("a picture two of them share stays while either is cited",
      [a.handle for a in _shared.ref_images], ["img-1"])

_only = compiler.compile_request(request(
    "a room, empty.",
    [image("img-1")],
    [{"handle": "anna", "from": ["img-1"]}]))
check("a shot whose only reference belonged to somebody absent is text-only",
      _only.mode, "T2VA")
check("...and carries no picture at all", [a.handle for a in _only.ref_images], [])

# A cast in a generation with nothing attached to it at all — T2VA, the mode
# most of this pack's prompts are written in. The two sections a cast makes
# derivable have to be emitted here too: `<Subject 1>` in a description the
# prompt never defines is a label pointing at nothing, and this is the whole of
# why the shelf is on the node's own rail rather than only in a reference piece.
_text_only = compiler.compile_request(request(
    "@anna crosses the loft.", [],
    [{"handle": "anna", "description": "a woman in her thirties, close-cropped hair"}]))
check("a text-only generation is still T2VA with a cast in it",
      _text_only.mode, "T2VA")
check("the citation becomes a label there too",
      "<Subject 1> crosses the loft." in _text_only.body, True)
check("and the label is defined, so it points at something",
      "subject_definitions: <Subject 1> is a woman in her thirties, "
      "close-cropped hair." in _text_only.prompt, True)
check("retention is written for her as well",
      "retention_analysis: <Subject 1> (appears in [Shot 1]): fully_preserved"
      in _text_only.prompt, True)
# The form follows what the piece has to declare, not which mode it derived. A
# cast is something to declare, so a text-only piece carrying one is written in
# the reference form too — people run that form against T2VA and the weights do
# not police the field name, and the alternative was a hybrid of the two forms
# that neither guide describes.
check("a cast puts even a text-only piece in the reference form",
      "detailed_description:" in _text_only.prompt, True)
check("...so the base form's field is not also claimed",
      "integrated_multimodal_description:" in _text_only.prompt, False)
check("the definitions stand in front of the description, as in the guide",
      _text_only.prompt.index("subject_definitions:")
      < _text_only.prompt.index("detailed_description:"), True)
check("...and it is summarised, with no task type to claim",
      "summary: The target video runs one shot and features <Subject 1>."
      in _text_only.prompt, True)

# ...and a text-only piece with nobody cast is byte-identical to what it always
# compiled to. The sections exist only where a cast does.
check("no cast, no sections",
      "subject_definitions" in compiler.compile_request(
          request("a woman crosses the loft.", [], [])).prompt, False)

# An unclaimed reference keeps the sentence it has always had, and keeps it
# inside `subject_definitions` rather than in a paragraph of its own.
_mixed = compiler.compile_request(request(
    "@anna stands in @img-2.", [image("img-1"), image("img-2", takes="scene")],
    [{"handle": "anna", "from": ["img-1"]}]))
check("an unclaimed reference is still defined",
      "<Picture 2> is a scene reference" in _mixed.prompt, True)
check("and it is defined in the same section as the cast",
      _mixed.prompt.index("<Picture 2> is a scene reference")
      > _mixed.prompt.index("subject_definitions:"), True)

# An uncited subject costs nothing and needs nothing attached.
_uncited = compiler.compile_request(request(
    "a room, empty.", [image("img-1")],
    [{"handle": "anna", "from": ["img-9"]}]))
check("an uncited subject is not resolved and not refused",
      "<Subject" in _uncited.prompt, False)

expect_error("a cited subject whose files are missing is refused",
             lambda: compiler.compile_request(request(
                 "@anna walks in.", [image("img-1")],
                 [{"handle": "anna", "from": ["img-9"]}])),
             "not attached to this generation")
expect_error("a subject cannot be built out of a keyframe",
             lambda: compiler.compile_request(request(
                 "@anna walks in.",
                 [{"handle": "img-1", "kind": "image", "role": "first_frame",
                   "filename": "a.png"}, image("img-2")],
                 [{"handle": "anna", "from": ["img-1"]}])),
             "first frame")
expect_error("a name that is also a file's handle is refused",
             lambda: compiler.compile_request(request(
                 "@anna walks in.",
                 [{"handle": "anna", "kind": "image", "role": "reference",
                   "filename": "a.png"}],
                 [{"handle": "anna", "from": ["anna"]}])),
             "one `@` means one thing")
expect_error("a voice must be audio",
             lambda: compiler.compile_request(request(
                 "@anna speaks.", [image("img-1"), image("img-2")],
                 [{"handle": "anna", "from": ["img-1"], "voice": "img-2"}])),
             "voice reference is audio")


# --- through a timeline ------------------------------------------------------

def piece(*segments, **extra):
    return {"version": 2, "prompt": "", "segments": list(segments),
            "aspect": "16:9", "short_edge": 768, **extra}


def shot(prompt, **extra):
    return {"prompt": prompt, "duration_s": 6, **extra}


_pooled = piece(shot("@anna walks in."), shot("an empty room."),
                assets=[image("ref-1"), image("ref-2")],
                subjects=[{"handle": "anna", "from": ["ref-1", "ref-2"]}])

_payloads = compiler.timeline_payloads(_pooled)
check("casting a subject pulls her files out of the pool",
      sorted(a["handle"] for a in _payloads[0]["request"]["assets"]), ["ref-1", "ref-2"])
check("and leaves the shots that never cast her alone",
      _payloads[1]["request"].get("assets"), None)

_first = compiler.compile_segment(_payloads[0])
check("her label is written into the shot that cast her",
      "<Subject 1> walks in." in _first.body, True)
check("and her definition cites the pool's own ordinals",
      "<Subject 1> is the person in <Picture 1> and <Picture 2>." in _first.prompt, True)

# Cited in the global prompt: the join puts it in front of every shot, which is
# the attach-once gesture the pool already had.
_global = piece(shot("she walks in."), shot("she sits down."),
                prompt="@anna is the only person in this film.",
                assets=[image("ref-1")],
                subjects=[{"handle": "anna", "from": ["ref-1"]}])
check("a global citation casts her into every shot",
      [len(p["request"]["assets"]) for p in compiler.timeline_payloads(_global)], [1, 1])

# One pass merges the shots into one generation; a pool asset keeps its handle
# through the merge, so the cast still points at it.
_single = compiler.compile_single(piece(
    shot("@anna walks in."), shot("@anna sits down.", merge=True),
    assets=[image("ref-1")],
    subjects=[{"handle": "anna", "from": ["ref-1"]}]))
check("one pass carries the cast too",
      _single.body.count("<Subject 1>"), 2)
check("and defines her once", _single.prompt.count("<Subject 1> is the person"), 1)
check("and the retention line names both shots she is in",
      "<Subject 1> (appears in [Shot 1], [Shot 2])" in _single.prompt, True)

# A card's own asset is renamed onto the merged list, and the cast is renamed
# with it — the failure this guards is a subject left pointing at a handle that
# only existed inside one card.
_local = compiler.compile_single(piece(
    shot("a road."), shot("@anna walks in.", merge=True, assets=[image("img-1")]),
    subjects=[{"handle": "anna", "from": ["img-1"]}]))
check("a subject built out of a card's own file survives the merge",
      "<Subject 1> is the person in <Picture 1>." in _local.prompt, True)

# What they are, all the way through the compile. `_subject_dict` writes the blob
# each segment and each merged pass is compiled from, and it used to write the
# handle, the files and the markers and stop — so every feature anybody had typed
# was dropped on this hop and the prompt was built from a bare `from` list. The
# card said one thing and the model was told another, which is invisible from
# either end: the shelf still showed the features and the retention line still
# said something plausible, just not what the card said.
_kept = piece(shot("@anna walks in."),
              assets=[image("ref-1")],
              subjects=[{"handle": "anna", "from": ["ref-1"], "seeded": True,
                         "features": [{"attr": "face"}, {"attr": "hair"},
                                      {"attr": "build"},
                                      {"attr": "clothing", "instead": "a red waxed jacket"},
                                      {"is": "a thin silver necklace"}]}])
_seg = compiler.compile_segment(compiler.timeline_payloads(_kept)[0])
check("a segment compile carries the rows, not just the files",
      "their face, hair, build, and a thin silver necklace are retained" in _seg.prompt,
      True)
check("...including the one the target video changes",
      "clothing is replaced by a red waxed jacket" in _seg.prompt, True)
check("...and the words somebody typed reach the definition",
      "with a thin silver necklace" in _seg.prompt, True)
# The merged-pass path renames the handles as it goes, and rebuilt the subject
# from scratch to do it — so it dropped the rows a second way.
_merged = compiler.compile_single(piece(
    shot("a road."), shot("@anna walks in.", merge=True, assets=[image("img-1")]),
    subjects=[{"handle": "anna", "from": ["img-1"], "seeded": True,
               "features": [{"attr": "face"}, {"attr": "hair"},
                            {"is": "a thin silver necklace"}]}]))
check("a merged pass carries them through the rename too",
      "their face, hair, and a thin silver necklace are retained" in _merged.prompt, True)
# Every row dropped is not the same as no rows at all, and only `seeded` tells
# them apart: without it an emptied card is handed the whole baseline back, which
# is the one thing dropping the last row must not do.
_emptied = compiler.compile_segment(compiler.timeline_payloads(piece(
    shot("@anna walks in."), assets=[image("ref-1")],
    subjects=[{"handle": "anna", "from": ["ref-1"], "seeded": True}]))[0])
check("a card whose rows were all dropped claims none of them back",
      "their face, hair, build, and clothing are retained" in _emptied.prompt, False)

# --- standing in for somebody across more than one clip -----------------------
#
# The same person in a medium shot and a close-up is one vacancy filmed twice.
# While `replaces` held a single handle the second clip could only be attached
# and left undefined, and the two ways of saying it by hand both misfired: left
# at the default scope the clip compiled to "is a reference video" and nothing
# else, and set to `edit` it produced two sentences each claiming to be the
# whole source of the edit.

_two = compiler.compile_request(request(
    "@anna stands at the counter.",
    [image("img-1", takes="person"), video("vid-1", takes="edit"), video("vid-2", takes="edit")],
    [{"handle": "anna", "from": ["img-1"],
      "replaces": ["vid-1", "vid-2"], "replaces_what": "the woman at the counter"}]))
check("one subject stands in across two clips, named as one list",
      "takes the place of the woman at the counter in <Video 1> and <Video 2>"
      in _two.prompt, True)
check("...and the edit is claimed once, over both sources",
      _two.prompt.count("The target video is an edited version of"), 1)
check("...with both sources in that one sentence",
      "an edited version of <Video 1> and <Video 2>." in _two.prompt, True)
check("...each defined as a source rather than as the whole edit",
      _two.prompt.count("is a source video for the target video edit."), 2)
check("...and each given its own retention line",
      _two.prompt.count("(source video): partially_preserved"), 2)

# The old shape still reads. Every blob written before somebody could stand in
# for two clips carries a bare string, and it means the one-element list it
# always meant.
_scalar = subjects.parse([{"handle": "anna", "from": ["img-1"], "replaces": "vid-1"}])
check("a blob carrying the old single handle still parses", _scalar[0].replaces, ("vid-1",))
check("...and is written back out as a list",
      compiler._subject_dict(_scalar[0])["replaces"], ["vid-1"])

# The bug this guards: `found.add(subject.replaces)` put the tuple itself into a
# set of handles, so citing @anna carried neither clip into the segment and the
# generation was refused for a file the citation should have brought with it.
# Only bites where the clips are in the *pool* — which is where a piece keeps
# them, and where a two-card edit puts them.
_split = compiler.compile_single(piece(
    shot("@anna stands at the counter in @ref-2."),
    shot("a close-up of @anna in @ref-3.", merge=True),
    assets=[image("ref-1", takes="person"),
            video("ref-2", takes="edit"), video("ref-3", takes="edit")],
    subjects=[{"handle": "anna", "from": ["ref-1"], "replaces": ["ref-2", "ref-3"],
               "replaces_what": "the woman at the counter"}]))
check("citing a subject carries every clip they stand in for",
      "<Video 1> is a source video" in _split.prompt
      and "<Video 2> is a source video" in _split.prompt, True)

# ---- feature by feature -----------------------------------------------------
#
# The guide writes a subject as a named list of features and names the same
# features again in `retention_analysis` — section 6's worked example is four
# subjects in a row built that way:
#
#   <Subject 2> is the fluffy white Samoyed in <Picture 2>, <Picture 3>, and
#   <Picture 4>, with thick white fur, pointed ears, a dark nose, and a curved tail.
#   <Subject 2> (appears in [Shot 1], [Shot 2]): fully_preserved - the Samoyed's
#   thick white fur, pointed ears, dark nose, and curved tail are retained.
#
# What this half exists for is the one thing that shape can say and the old one
# could not: this feature is defined, and in the target video it is something
# else. That is 4.1's `partially_preserved` to the word, and before it existed the
# marker was a picker that wrote `partially_preserved` over a sentence saying
# everything was retained.

_LAB = {"img-1": "<Picture 1>", "vid-1": "<Video 1>"}
_feat = subjects.parse([{
    "handle": "vera", "from": ["img-1"], "takes": "person",
    "features": ["long dark hair", {"is": "a blue cardigan"},
                 {"is": "a thin silver necklace"}]}])
check("the features are named in the definition, the guide's way",
      subjects.definitions(_feat, _LAB),
      "<Subject 1> is the person in <Picture 1>, with long dark hair, a blue "
      "cardigan, and a thin silver necklace.")
check("...and named again as what is retained",
      subjects.retention(_feat, _LAB, "[Shot 1] <Subject 1> waits."),
      "<Subject 1> (appears in [Shot 1]): fully_preserved - long dark hair, a blue "
      "cardigan, and a thin silver necklace are retained.")
# Not one negative clause in any of the guide's four retention examples, and 4.1
# closes by saying not to write them: "do not treat newly added actions,
# backgrounds, or plot events in the target video as losses of reference
# fidelity". These lines used to end "...and the source picture's background,
# palette, lighting, pose and action are not", borrowed from the sentence
# `contextir._DEFINE` writes for a *file* — where it belongs, because
# `<Picture N>` denotes the file and `<Subject N>` denotes content abstracted
# from it (2.1). The abstraction is already in the label.
check("and says nothing about what is not retained",
      " are not." in subjects.retention(_feat, _LAB, "[Shot 1] <Subject 1> waits."), False)

_changed = subjects.parse([{
    "handle": "vera", "from": ["img-1"], "takes": "person",
    "features": [{"is": "long dark hair"},
                 {"is": "a blue cardigan", "instead": "a red waxed jacket"}]}])
# A characteristic has to be defined before it can be changed, so the definition
# names the cardigan even though the target video does not have one.
check("a changed feature is still defined",
      "with long dark hair and a blue cardigan" in subjects.definitions(_changed, _LAB), True)
check("...derives partially_preserved rather than being picked",
      _changed[0].relationship, "partially_preserved")
check("...and the line says what it was and what it is now",
      subjects.retention(_changed, _LAB, "[Shot 1] <Subject 1> waits."),
      "<Subject 1> (appears in [Shot 1]): partially_preserved - long dark hair is "
      "retained; a blue cardigan is replaced by a red waxed jacket.")

# Standing in for somebody does not move the marker — the changed feature does,
# and the swap is stated beside what is kept and what changed.
_both = subjects.parse([{
    "handle": "vera", "from": ["img-1"], "takes": "person",
    "replaces": ["vid-1"], "replaces_what": "the bench",
    "features": [{"is": "long dark hair"},
                 {"is": "a blue cardigan", "instead": "a red waxed jacket"}]}])
check("a changed feature beside a place taken is partially_preserved",
      _both[0].relationship, "partially_preserved")
_line = subjects.retention(_both, _LAB, "[Shot 1] <Subject 1> waits.")
check("...and the kept feature is retained, not transferred",
      "long dark hair is retained" in _line, True)
check("...and the swap names whose place is taken",
      "they appear in place of the bench in <Video 1>" in _line, True)
check("...and still says what changed", "replaced by a red waxed jacket" in _line, True)

# ---- the baseline, as rows ---------------------------------------------------
#
# What a `takes` word carries used to be one sentence in the compiler, reached
# only where nobody had named a feature of their own. So naming one silently
# narrowed the claim: "their face, hair, build, and clothing are retained"
# became "a red leather jacket is retained", and on a swap that meant the jacket
# moved and the replaced person's own build and hair stayed where they were.
#
# It is a list of rows now, seeded onto the card when somebody is cast. The
# sentence is what the untouched rows compose, so nothing about an untouched
# card changed; what is new is that each row can be described, changed or
# dropped by itself.

def _rows(*attrs):
    return [{"attr": a} for a in attrs]


_seeded = subjects.parse([{"handle": "vera", "from": ["img-1"], "takes": "person",
                           "features": _rows("face", "hair", "build", "clothing")}])
check("an untouched card compiles the sentence it always did",
      subjects.retention(_seeded, _LAB, "[Shot 1] <Subject 1> waits."),
      "<Subject 1> (appears in [Shot 1]): fully_preserved - their face, hair, "
      "build, and clothing are retained.")
check("...the same one a card with no rows at all still compiles",
      subjects.retention(_seeded, _LAB, "[Shot 1] <Subject 1> waits."),
      subjects.retention(
          subjects.parse([{"handle": "vera", "from": ["img-1"], "takes": "person"}]),
          _LAB, "[Shot 1] <Subject 1> waits."))
# The definition is what the label denotes, and "with face, hair, build, and
# clothing" says nothing the noun did not. A seeded row earns its place in the
# retention line, where the question is what is carried over.
check("...and says nothing extra in the definition",
      subjects.definitions(_seeded, _LAB), "<Subject 1> is the person in <Picture 1>.")

# The bug this whole shape exists for.
_plus = subjects.parse([{"handle": "vera", "from": ["img-1"], "takes": "person",
                         "features": _rows("face", "hair", "build", "clothing")
                                     + [{"is": "a red leather jacket"}]}])
check("a feature somebody types joins the baseline rather than replacing it",
      subjects.retention(_plus, _LAB, "[Shot 1] <Subject 1> waits."),
      "<Subject 1> (appears in [Shot 1]): fully_preserved - their face, hair, "
      "build, clothing, and a red leather jacket are retained.")

# The three things a row can have done to it.
_dropped = subjects.parse([{"handle": "vera", "from": ["img-1"], "takes": "person",
                            "features": _rows("face", "build", "clothing")}])
check("a dropped row leaves the rest of the baseline standing",
      "their face, build, and clothing are retained"
      in subjects.retention(_dropped, _LAB, "[Shot 1] <Subject 1> waits."), True)

_described = subjects.parse([{
    "handle": "vera", "from": ["img-1"], "takes": "person",
    "features": [{"attr": "face"}, {"attr": "hair", "is": "long dark hair"},
                 {"attr": "build"}, {"attr": "clothing"}]}])
check("a described row reads as their words in the retention line",
      "their face, long dark hair, build, and clothing are retained"
      in subjects.retention(_described, _LAB, "[Shot 1] <Subject 1> waits."), True)
check("...and is the only row that reaches the definition",
      subjects.definitions(_described, _LAB),
      "<Subject 1> is the person in <Picture 1>, with long dark hair.")

_swapped = subjects.parse([{
    "handle": "vera", "from": ["img-1"], "takes": "person",
    "features": [{"attr": "face"}, {"attr": "hair", "instead": "a short blonde bob"},
                 {"attr": "build"}, {"attr": "clothing"}]}])
check("a changed row names the attribute and what replaces it",
      subjects.retention(_swapped, _LAB, "[Shot 1] <Subject 1> waits."),
      "<Subject 1> (appears in [Shot 1]): partially_preserved - their face, build, "
      "and clothing are retained; hair is replaced by a short blonde bob.")

# A swap, which is what the narrowing broke worst: the whole baseline is what
# lands on the person going, and it says so in as many words.
_place = subjects.parse([{
    "handle": "vera", "from": ["img-1"], "takes": "person",
    "replaces": ["vid-1"], "replaces_what": "the man at the counter",
    "features": _rows("face", "hair", "build", "clothing")}])
check("a swap carries the whole baseline into the vacancy, not the last thing typed",
      subjects.retention(_place, _LAB, "[Shot 1] <Subject 1> waits."),
      "<Subject 1> (appears in [Shot 1]): fully_preserved - their face, hair, "
      "build, and clothing are retained; they appear in place of the man at the "
      "counter in <Video 1>, taking over the source's action and timing.")

# Every take has its own baseline, and the possessive is part of it: a place is
# not "their" anything.
check("a scene's rows compose the scene's own sentence",
      subjects.retention(
          subjects.parse([{"handle": "loft", "from": ["img-1"], "takes": "scene",
                           "features": _rows("environment", "surfaces", "light")}]),
          _LAB, "[Shot 1] <Subject 1> waits."),
      "<Subject 1> (appears in [Shot 1]): fully_preserved - the environment, its "
      "surfaces, and its light are retained.")

# A seeded row survives with nothing typed into it — the attribute's own name is
# what it says. Only a row with neither half is the empty one the editor writes.
check("a row with an attribute and no words is not an empty row",
      [(f.attr, f.text) for f in subjects.parse([{"handle": "v", "features":
          [{"attr": "hair"}, {"is": ""}, {"attr": "", "is": "  "}]}])[0].features],
      [("hair", "")])

# The override is the only way to reach weak_reference — "only broad similarity
# in style, category, composition, or atmosphere" is a judgement about the
# render, which no rule here can infer.
check("a marker set by hand wins over the derivation",
      subjects.parse([{"handle": "v", "from": ["img-1"], "relationship": "weak_reference",
                       "features": [{"is": "a hat", "instead": "a cap"}]}])[0].relationship,
      "weak_reference")

# An empty row is what the editor writes the moment somebody presses "add a
# feature", and refusing it would make a half-typed cast a compile error.
check("an unfilled row is dropped rather than refused",
      [f.text for f in subjects.parse([{"handle": "v", "from": ["img-1"], "features":
          [{"is": "  "}, {"is": "", "instead": "a cap"}, {"is": " a hat "}]}])[0].features],
      ["a hat"])
# ...and features alone are enough to be somebody, in a generation with no
# references in it at all.
check("features alone are something behind them",
      [f.text for f in subjects.parse([{"handle": "v", "features": ["a red coat"]}])[0].features],
      ["a red coat"])

passed("the cast holds: citation, labels, features, both sections, pool, merge and standing in")

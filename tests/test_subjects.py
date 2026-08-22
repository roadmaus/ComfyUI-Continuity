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
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    package = types.ModuleType("mmc")
    package.__path__ = [ROOT]
    sys.modules["mmc"] = package
    modules = {}
    for name in ("canvas", "contextir", "subjects", "compile"):
        spec = importlib.util.spec_from_file_location(f"mmc.{name}", os.path.join(ROOT, f"{name}.py"))
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
      "<Subject 1> ([Shot 1]): fully_preserved - the definition above is the "
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
check("a replacement derives the transferred marker",
      _swap[0].relationship, "transferred")
_ret = subjects.retention(_swap, _swap_labels, "[Shot 1] <Subject 1> pours coffee.")
check("and says who is going, in the retention line",
      "the man at the counter in <Video 1>" in _ret, True)
check("and keeps the clip's own work", "framing, camera work and action are kept" in _ret, True)

_where = subjects.parse([{"handle": "anna", "from": ["img-1"]}])
check("where a subject appears is read off the shots she is written into",
      subjects.retention(_where, {"img-1": "<Picture 1>"},
                         "[Shot 1] <Subject 1> walks. [Shot 2] a door. "
                         "[Shot 3] <Subject 1> again.").split(":")[0],
      "<Subject 1> ([Shot 1], [Shot 3])")
check("a body with no shot markers at all is one shot",
      subjects.retention(_where, {"img-1": "<Picture 1>"},
                         "<Subject 1> walks.").split(":")[0],
      "<Subject 1> ([Shot 1])")


# --- through the compiler ----------------------------------------------------

_plain = compiler.compile_request(request("a woman walks in @img-1", [image("img-1")], []))
check("a piece with no cast writes no subject_definitions",
      "subject_definitions" in _plain.prompt, False)
check("and an undeclared name stays prose",
      "@carol" in compiler.compile_request(
          request("@carol walks in @img-1", [image("img-1")], [])).body, True)

_cast = compiler.compile_request(request(
    "@anna looks at @ben.",
    [image("img-1"), image("img-2"), image("img-3"), audio("aud-1", takes="voice")],
    [{"handle": "anna", "from": ["img-1", "img-2"], "description": "a blue cardigan",
      "voice": "aud-1"},
     {"handle": "ben", "from": ["img-3"]}]), define_refs=True)
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
     {"handle": "ben", "from": ["img-2"]}]), define_refs=True)
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
      "retention_analysis: <Subject 1> ([Shot 1]): fully_preserved"
      in _text_only.prompt, True)
check("the base form's own body field is kept — this is not the reference form",
      "integrated_multimodal_description:" in _text_only.prompt, True)
check("and the reference form's body field is not claimed",
      "detailed_description:" in _text_only.prompt, False)
check("the definitions stand in front of the description, as in the guide",
      _text_only.prompt.index("subject_definitions:")
      < _text_only.prompt.index("integrated_multimodal_description:"), True)

# ...and a text-only piece with nobody cast is byte-identical to what it always
# compiled to. The sections exist only where a cast does.
check("no cast, no sections",
      "subject_definitions" in compiler.compile_request(
          request("a woman crosses the loft.", [], [])).prompt, False)

# An unclaimed reference keeps the sentence it has always had, and keeps it
# inside `subject_definitions` rather than in a paragraph of its own.
_mixed = compiler.compile_request(request(
    "@anna stands in @img-2.", [image("img-1"), image("img-2", takes="scene")],
    [{"handle": "anna", "from": ["img-1"]}]), define_refs=True)
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
      "subject_definitions" in _uncited.prompt, False)

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
      "<Subject 1> ([Shot 1], [Shot 2])" in _single.prompt, True)

# A card's own asset is renamed onto the merged list, and the cast is renamed
# with it — the failure this guards is a subject left pointing at a handle that
# only existed inside one card.
_local = compiler.compile_single(piece(
    shot("a road."), shot("@anna walks in.", merge=True, assets=[image("img-1")]),
    subjects=[{"handle": "anna", "from": ["img-1"]}]))
check("a subject built out of a card's own file survives the merge",
      "<Subject 1> is the person in <Picture 1>." in _local.prompt, True)

passed("the cast holds: citation, labels, both sections, pool and merge")

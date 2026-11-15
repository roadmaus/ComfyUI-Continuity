"""Screen replacement, up to the graph: what a card may say, what compile makes
of it, and that a card without screens compiles to the bytes it always did.

    python3 tests/test_screens.py

Pure Python. The tracking and compositing are `test_screens_track.py`, the
frontend's copy `test_screens_mirror.py`, the emitted graph
`test_screens_graph.py`.
"""

import json

import layout
from harness import FAILURES, check, passed

passed("screens are validated, stamped, compiled to a tracker reference cited "
       "where the prompt writes its handle, refused where they cannot ride or go "
       "uncited, and absent change nothing")

_pkg = layout.load("canvas", "registry", "h3_declare", "contextir", "subjects", "compile",
                   "compile_image", "h3image_still", "krea2_still", "ideogram4_still", "qwenedit_still",
                   "flux2klein_still", "screen_spec", "grammar")
spec, compiler, ci = _pkg.screen_spec, _pkg.compile, _pkg.compile_image
klein, ideogram = _pkg.flux2klein_still, _pkg.ideogram4_still


def refuses(label, run, fragment, error=Exception):
    try:
        run()
    except error as exc:
        if fragment not in str(exc):
            FAILURES.append(f"{label}: refused with {exc!r}, wanted {fragment!r} in it")
        return
    FAILURES.append(f"{label}: was not refused")


PHONE = {"handle": "phone-1", "device": "phone",
         "content": {"filename": "guide.png", "kind": "image"}}
LAPTOP = {**PHONE, "handle": "laptop-1", "device": "laptop"}
GRID = {"pattern": "grid", "colour": "white"}


# ---- the spec ---------------------------------------------------------------------

(one,) = spec.parse([PHONE])
check("the default is a plain green screen", spec.DEFAULT_STYLE, {"pattern": "none", "colour": "green"})
check("a screen set up the obvious way takes every default",
      (one.device, one.width, one.height, one.kind, one.fit, one.offset_s, one.when_short,
       one.cuts, one.pattern, one.colour),
      ("phone", 1080, 2340, "image", "fill", 0.0, "hold", "continue", "none", "green"))
check("absent, None and empty are all no screens",
      (spec.parse(None), spec.parse([])), ((), ()))
check("the tracker file is named by everything that decides its pixels",
      one.tracker_file, "continuity_trackers/v2-none-green-1080x2340.png [temp]")
check("and the name alone is enough to draw it again",
      spec.parse_tracker_file("v2-grid-white-1080x2340.png"), ("grid", "white", 1080, 2340))
check("a name from another version is not ours to draw",
      spec.parse_tracker_file("v1-grid-white-1080x2340.png"), None)

two = spec.parse([PHONE, LAPTOP], {"pattern": "plus", "colour": "magenta"})
check("a second screen takes the next free colour in palette order",
      [(s.colour, s.pattern) for s in two], [("magenta", "plus"), ("white", "plus")])
check("assign_colours starts from the chosen one",
      spec.assign_colours("green", 3), ["green", "white", "magenta"])

stamped = spec.stamp([PHONE, {**PHONE, "handle": "phone-2"}], {"pattern": "plus", "colour": "blue"})
check("stamp writes this machine's tracker onto each screen",
      [s["tracker"] for s in stamped],
      [{"pattern": "plus", "colour": "blue"}, {"pattern": "plus", "colour": "white"}])
check("and parse reads a stamped tracker over its own default",
      [s.colour for s in spec.parse(stamped)], ["blue", "white"])
piece = {"segments": [{"prompt": "a"}, {"prompt": "b"}]}
check("a piece without screens comes back as the very object",
      spec.stamp_piece(piece, spec.DEFAULT_STYLE) is piece, True)

(custom,) = spec.parse([{**PHONE, "device": "custom", "aspect": [21, 9]}])
check("a custom screen is drawn at its aspect on a 1920 long side, on even sides",
      (custom.width, custom.height), (1920, 822))

refuses("three screens", lambda: spec.parse([PHONE] * 3), "at most 2 screens")
refuses("an unknown device", lambda: spec.parse([{**PHONE, "device": "watch"}]),
        "device must be one of")
refuses("a custom screen with no aspect", lambda: spec.parse([{**PHONE, "device": "custom"}]),
        "two positive numbers")
refuses("a custom screen past 4:1",
        lambda: spec.parse([{**PHONE, "device": "custom", "aspect": [10, 1]}]), "at most 4:1")
refuses("a screen showing nothing", lambda: spec.parse([{"handle": "phone-1", "device": "phone"}]),
        "has nothing to show")
refuses("a negative offset", lambda: spec.parse([{**PHONE, "offset_s": -1}]),
        "start offset")
refuses("an unknown fit", lambda: spec.parse([{**PHONE, "fit": "zoom"}]), "fit must be one of")
refuses("two screens stamped one colour",
        lambda: spec.parse([{**PHONE, "tracker": {"pattern": "grid", "colour": "white"}},
                            {**LAPTOP, "tracker": {"pattern": "grid", "colour": "white"}}]),
        "two different key colours")
refuses("a screen with no handle", lambda: spec.parse([{**PHONE, "handle": None}]),
        "no handle to be cited by")
refuses("a handle no citation can spell", lambda: spec.parse([{**PHONE, "handle": "phone"}]),
        "no handle to be cited by")
refuses("two screens under one handle", lambda: spec.parse([PHONE, {**LAPTOP, "handle": "phone-1"}]),
        "both called @phone-1")
refuses("a tracker colour this build does not draw",
        lambda: spec.clean_style({"pattern": "grid", "colour": "red"}), "colour must be one of")

(gridded,) = spec.parse([{**PHONE, "tracker": GRID}])
check("an uncited screen is named, with how to cite it", spec.uncited([gridded], set()),
      "@phone-1 is not in the prompt — write it where that screen is in the shot, as in "
      "“the screen shows @phone-1”")
check("a cited one is not", spec.uncited([gridded], {"phone-1"}), None)


# ---- the video compile ----------------------------------------------------------------


def blob(segment, **piece_extra):
    return {"version": 2, "prompt": "", "family": "h3", "aspect": "3:4", "short_edge": 768,
            "segments": [{"prompt": "A hand holds a phone in a gallery; it shows @phone-1.",
                          "duration_s": 5,
                          "assets": [], **segment}], **piece_extra}


def compiled(segment, **piece_extra):
    return compiler.compile_segment(compiler.timeline_payloads(blob(segment, **piece_extra))[0])


with_screen = compiled({"screens": [{**PHONE, "tracker": GRID}]})
check("a screen makes the shot a reference generation", with_screen.mode, "REF2VA")
check("its tracker is the reference, under the screen's own handle",
      [(a.handle, a.filename, a.takes) for a in with_screen.ref_images],
      [("phone-1", "continuity_trackers/v2-grid-white-1080x2340.png [temp]", "screen")])
check("the body cites it where the prompt wrote it, and says nothing more",
      with_screen.body, "A hand holds a phone in a gallery; it shows <Picture 1>.")
check("and the retention section says it is shown as it is",
      "<Picture 1> (screen display): fully_preserved" in with_screen.prompt, True)
check("the screen pass is told what goes on it", [s.filename for s in with_screen.screens],
      ["guide.png"])

cited = compiled({"prompt": "@img-1 holds a phone showing @phone-1.",
                  "screens": [{**PHONE, "tracker": GRID}],
                  "assets": [{"handle": "img-1", "kind": "image", "role": "reference",
                              "filename": "anna.png"}]})
check("the user's own picture keeps <Picture 1>; the tracker comes after it",
      (cited.labels["img-1"], cited.labels["phone-1"]), ("<Picture 1>", "<Picture 2>"))

plain = compiled({"prompt": "A hand holds a phone."})
check("a shot without screens has none", (plain.screens, plain.mode), ((), "T2VA"))
empty = compiler.timeline_payloads(blob({"prompt": "A phone.", "screens": []}))[0]
bare = compiler.timeline_payloads(blob({"prompt": "A phone."}))[0]
check("an empty list compiles the prompt a card without the key does",
      compiler.compile_segment(empty).prompt, compiler.compile_segment(bare).prompt)

nine = [{"handle": f"img-{i}", "kind": "image", "role": "reference", "filename": f"{i}.png"}
        for i in range(1, 10)]
refuses("a screen the prompt never cites",
        lambda: compiled({"prompt": "A hand holds a phone.", "screens": [PHONE]}),
        "@phone-1 is not in the prompt")
refuses("a citation of a screen that is gone",
        lambda: compiled({"screens": []}), "references @phone-1 but no such asset")
refuses("a screen named like an attached file",
        lambda: compiled({"prompt": "@phone-1", "screens": [PHONE],
                          "assets": [{"handle": "phone-1", "kind": "image",
                                      "role": "reference", "filename": "p.png"}]}),
        "an attached file and of a screen")
refuses("a screen on a shot with every picture slot taken",
        lambda: compiled({"prompt": " ".join(f"@img-{i}" for i in range(1, 10)) + " @phone-1",
                          "assets": nine, "screens": [PHONE]}),
        "needs 1 more of the 9")
refuses("screens on a merged pass",
        lambda: compiler.timeline_payloads({**blob({"screens": [PHONE]}), "segments": [
            {"prompt": "one", "duration_s": 3, "screens": [PHONE]},
            {"prompt": "two", "duration_s": 3, "merge": True}]}),
        "screens on a merged pass are not supported")
refuses("screens on a family whose references ride as one sheet",
        lambda: compiled({"screens": [PHONE]}, family="ltx25"), "cannot be shown a screen tracker")

catalog = json.loads(layout.catalog_json())
families = catalog["families"] if isinstance(catalog, dict) and "families" in catalog else catalog
video_families = [f for f in families if "video" in (f.get("produces") or [])]
check("both video families are asked about", len(video_families) >= 2, True)
for family in video_families:
    check(f"{family['id']}: the manifest offers screens exactly where the grammar takes them",
          bool((family.get("capabilities") or {}).get("screens")),
          _pkg.grammar.of(family["id"]).takes_screens)


# ---- the still compile ------------------------------------------------------------------


def still(**extra):
    return {"version": 1, "arch": "flux2klein", "prompt": "a hand holding a phone showing @phone-1",
            "aspect": "3:4", "short_edge": 1024, "loras": [], **extra}


payload = ci.compile_prestage(still(screens=[{**PHONE, "tracker": GRID}]), klein)
check("a still's tracker is its last reference", payload.refs,
      ["continuity_trackers/v2-grid-white-1080x2340.png [temp]"])
check("cited by the family's own spelling, where the prompt wrote it", payload.prompt,
      "a hand holding a phone showing Picture 1")
refuses("a still whose screen the prompt never cites",
        lambda: ci.compile_prestage(still(prompt="a phone", screens=[PHONE]), klein),
        "@phone-1 is not in the prompt")
check("and the screen node is told what goes on it",
      [s["filename"] for s in payload.screens], ["guide.png"])
check("a still without screens carries none",
      ci.compile_prestage(still(prompt="a phone"), klein).screens, ())
refuses("a still on a family that reads no pictures",
        lambda: ci.compile_prestage(still(arch="ideogram4", screens=[PHONE]), ideogram),
        "cannot be shown a screen tracker")
refuses("a still whose pictures and trackers outnumber its slots",
        lambda: ci.compile_prestage(still(
            prompt="@img-1 @img-2 @img-3 and @phone-1",
            refs=[{"handle": f"img-{i}", "filename": f"{i}.png"} for i in (1, 2, 3)],
            screens=[PHONE]), klein),
        "is more than this model reads")

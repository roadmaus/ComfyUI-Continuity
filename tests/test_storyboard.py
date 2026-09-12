"""The storyboard (issue #43): a 3 x 3 sheet of the shots before a card, cited
as its last picture reference.

Runs standalone, like `test_compile.py`: everything here is the compiler's
bookkeeping — which passes a card is shown, how the sheet's cells are allotted,
what the prompt says about it, and how a shortened render keeps the numbers
straight. The graph side is `test_storyboard_graph.py`.
"""

import layout

_pkg = layout.load("canvas", "h3_declare", "contextir", "subjects", "compile",
                   package="mmc")
compiler, contextir = _pkg.compile, _pkg.contextir

from harness import FAILURES, check, passed


def shot(prompt="a room", seconds=6, **fields):
    return {"prompt": prompt, "duration_s": seconds, "assets": [], **fields}


def clip(seconds=3.0, **fields):
    return {"kind": "clip", "filename": "shot.mp4", "duration_s": seconds,
            "width": 1920, "height": 1080, **fields}


def take(seconds=6.0, **fields):
    return {"filename": "minimax/renders/takes/H3_00001_s01.mp4",
            "duration_s": seconds, "width": 1280, "height": 720,
            "has_audio": True, **fields}


def strip(*segments, **piece):
    return {"segments": list(segments), **piece}


def _look(_filename):
    return (1920, 1080)


def boards(data):
    """Each payload's storyboard cells, or None."""
    return [p.get("storyboard", {}).get("cells") if "request" in p else "clip"
            for p in compiler.timeline_payloads(data, _look)]


def expect_error(label, fn, fragment):
    try:
        fn()
    except compiler.CompileError as exc:
        if fragment.lower() not in str(exc).lower():
            FAILURES.append(f"{label}: error {str(exc)!r} does not mention {fragment!r}")
    else:
        FAILURES.append(f"{label}: expected a CompileError, got none")


# --- the cells ---------------------------------------------------------------

check("one source fills the sheet", compiler.storyboard_cells([5]), [9])
check("two equal sources split it, remainder to the first",
      compiler.storyboard_cells([5, 5]), [5, 4])
check("cells follow duration", compiler.storyboard_cells([6, 3]), [6, 3])
check("...by largest remainder, over the one cell each is owed",
      compiler.storyboard_cells([7, 2]), [6, 3])
check("a short insert still gets a cell",
      compiler.storyboard_cells([10, 0.5, 10]), [4, 1, 4])
check("nine sources get one each", compiler.storyboard_cells([1] * 9), [1] * 9)
check("more sources than cells keeps the most recent",
      compiler.storyboard_cells([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]), [1] * 9)
check("the sheet always has nine cells",
      [sum(compiler.storyboard_cells(s)) for s in ([2], [1, 1, 1], [4, 1, 1, 1, 5], [3] * 12)],
      [9, 9, 9, 9])
check("zero-length sources still count", compiler.storyboard_cells([0, 0]), [1, 1])
check("nothing in, nothing out", compiler.storyboard_cells([]), [])

# --- what each card is shown --------------------------------------------------

three = strip(shot("one", 5), shot("two", 4), shot("three", 7))
check("off by default — an old blob renders as it did",
      boards(three), [None, None, None])
check("...and the payloads carry no key at all",
      ["storyboard" in p for p in compiler.timeline_payloads(three, _look)],
      [False, False, False])
check("'previous' shows each card the pass in front of it",
      boards({**three, "storyboard": "previous"}), [None, [[0, 9]], [[1, 9]]])
check("'all' shows each card everything before it, by duration",
      boards({**three, "storyboard": "all"}), [None, [[0, 9]], [[0, 5], [1, 4]]])
expect_error("an unknown setting is refused",
             lambda: boards({**three, "storyboard": "everything"}), "storyboard setting")

# A card's own answer wins over the piece's.
check("a card can opt out", boards(strip(shot("one"), shot("two", storyboard=False),
                                        shot("three"), storyboard="all")),
      [None, None, [[0, 5], [1, 4]]])
check("a card can name the shots it sees",
      boards(strip(shot("one", 5), shot("two", 4), shot("three", 7, storyboard=[1]))),
      [None, None, [[0, 9]]])
check("...in strip order whatever order it named them",
      boards(strip(shot("one", 5), shot("two", 4), shot("three", 7, storyboard=[2, 1]))),
      [None, None, [[0, 5], [1, 4]]])
check("a name pointing at itself or past it is a leftover, not an error",
      boards(strip(shot("one"), shot("two", storyboard=[2, 3, 9]))), [None, None])
check("an empty list is off",
      boards(strip(shot("one"), shot("two", storyboard=[]), storyboard="all")), [None, None])
expect_error("anything else is refused",
             lambda: boards(strip(shot("one"), shot("two", storyboard="yes"))),
             "list of segment numbers")

# Segment 1 and clips.
check("the first card has nothing to be shown",
      boards(strip(shot("one", storyboard=[1]), shot("two"), storyboard="all")),
      [None, [[0, 9]]])
check("footage is not shown a sheet, but is on the next card's",
      boards(strip(shot("one", 5), clip(3.0), shot("three", 7), storyboard="all")),
      [None, "clip", [[0, 5], [1, 4]]])

# Merged runs: a pass is one generation and one source.
merged = strip(shot("one", 5), shot("two", 4, merge=True), shot("three", 7),
               storyboard="all")
check("a merged run is one source, at its combined length",
      boards(merged), [None, [[0, 9]]])
check("...and a name inside the run lands on the run",
      boards(strip(shot("one", 5), shot("two", 4, merge=True),
                   shot("three", 7, storyboard=[2]))),
      [None, [[0, 9]]])
check("the head of a merged run is the one that is shown it",
      boards(strip(shot("one", 5), shot("two", 4), shot("three", 7, merge=True),
                   storyboard="previous")),
      [None, [[0, 9]]])

# One pass over the whole strip has no shots before any of it.
check("a single pass is shown nothing",
      boards({**three, "render": "single", "storyboard": "all"}), [None])

# The key never reaches the request: it is a fact about the strip, and the
# request is the segment node's cache key.
payloads = compiler.timeline_payloads(strip(shot("one"), shot("two", storyboard=[1])), _look)
check("the card's key is lifted off the request",
      "storyboard" in payloads[1]["request"], False)

# --- what the prompt says ------------------------------------------------------

compiled = compiler.compile_timeline({**three, "storyboard": "all"}, _look)
check("a shown card is a reference generation", compiled[1].mode, "REF2VA")
check("...on the ref2va checkpoint", compiled[1].checkpoint, "ref2va")
check("the first card is untouched", (compiled[0].mode, compiled[0].storyboard), ("T2VA", False))
check("the sheet is the last picture", compiled[1].ref_images[-1].handle, compiler.STORYBOARD_HANDLE)
check("...and takes <Picture 1> on a card with no other pictures",
      compiled[1].labels[compiler.STORYBOARD_HANDLE], "<Picture 1>")
check("the flag survives compilation", compiled[1].storyboard, True)
check("the definition says what it is",
      "<Picture 1> is a storyboard of the video so far" in compiled[1].prompt, True)
check("...how it reads",
      "left to right and top to bottom" in compiled[1].prompt, True)
check("...that the framing is the description's",
      "Its framing is not: the target video's own shot size" in compiled[1].prompt, True)
check("...and that the sheet is not shown",
      "its grid and its frames are never shown" in compiled[1].prompt, True)
check("the retention line scopes it",
      "<Picture 1> (the shots before this one): fully_preserved" in compiled[1].prompt, True)
check("the summary names it",
      "next shot of the piece storyboarded in <Picture 1>" in compiled[1].prompt, True)

# A user's pictures keep their ordinals: the sheet rides last.
with_ref = strip(
    shot("one", 5),
    shot("two @img-1", 4, assets=[{"handle": "img-1", "kind": "image",
                                    "role": "reference", "filename": "anna.png"}]),
    storyboard="previous")
compiled = compiler.compile_timeline(with_ref, _look)
check("an attached picture stays <Picture 1>", compiled[1].labels["img-1"], "<Picture 1>")
check("...and the sheet is <Picture 2>", compiled[1].labels[compiler.STORYBOARD_HANDLE], "<Picture 2>")
check("the body cites the picture, not the sheet", compiled[1].body, "two <Picture 1>")

# A continuing card is shown the sheet alongside its inherited frame.
cont = strip(shot("one"), shot("two", **{"continue": True}), storyboard="previous")
compiled = compiler.compile_timeline(cont, _look)
check("a continuing card rides the reference road with its seam",
      (compiled[1].mode, compiled[1].continues, compiled[1].storyboard),
      ("REF2VA", True, True))
check("...and encodes video", compiled[1].encodes_video(), True)

# The caps: the sheet is one of H3's nine pictures.
nine = [{"handle": f"img-{n}", "kind": "image", "role": "reference",
         "filename": f"p{n}.png"} for n in range(1, 10)]
expect_error("a full card has no room for it",
             lambda: compiler.compile_timeline(
                 strip(shot("one"), shot("two " + " ".join(f"@img-{n}" for n in range(1, 10)),
                                          assets=nine), storyboard="previous"), _look),
             "needs one of the 9")
expect_error("the handle is the sheet's",
             lambda: compiler.compile_timeline(
                 strip(shot("one"), shot("two", assets=[{"handle": "storyboard", "kind": "image",
                                                         "role": "reference", "filename": "x.png"}]),
                       storyboard="previous"), _look),
             "rename")
expect_error("a file cannot claim the sheet's take",
             lambda: compiler.compile_request({"prompt": "x @img-1", "assets": [
                 {"handle": "img-1", "kind": "image", "role": "reference",
                  "filename": "x.png", "takes": "storyboard"}]}),
             "takes must be one of")

# A family without the sheet renders as though the switch were off.
check("LTX 2.5 draws no sheet",
      boards({**three, "family": "ltx25", "storyboard": "all"}), [None, None, None])

# --- a shortened render ----------------------------------------------------------

# Card 1 kept, card 2 being shot: the sheet is the take.
step2 = strip(shot("one", hold=True, take=take()), shot("two"), shot("three", hold=True),
              storyboard="all")
rendered = compiler.rendered_piece(step2)
check("the piece's setting is written onto the card, in the render's numbers",
      rendered["segments"][1].get("storyboard"), [1])
check("...and the sheet is the take, a clip", boards(rendered), ["clip", [[0, 9]]])

# 'all' means what exists; a named card that does not is refused.
gap = strip(shot("one", hold=True, take=take()), shot("two", hold=True), shot("three"),
            storyboard="all")
check("'all' skips a held card with nothing to play",
      compiler.rendered_piece(gap)["segments"][1].get("storyboard"), [1])
expect_error("'previous' cannot be the shot that is not there",
             lambda: compiler.rendered_piece({**gap, "storyboard": "previous"}),
             "not in this render")
expect_error("a named card that is not there is refused",
             lambda: compiler.rendered_piece(strip(
                 shot("one", hold=True, take=take()), shot("two", hold=True),
                 shot("three", storyboard=[2]))),
             "shoot segment 2 first")
check("a card that opted out stays out",
      compiler.rendered_piece(strip(shot("one", hold=True, take=take()),
                                    shot("two", storyboard=False), storyboard="all")
                              )["segments"][1].get("storyboard"), False)
check("a strip with nothing held is handed straight back",
      compiler.rendered_piece(three) is compiler.as_piece(three), True)

# Numbers on a shortened strip are the render's: card 4 named cards 1 and 3,
# card 2 is dropped, so in the render they are 1 and 2.
renumbered = strip(shot("one", hold=True, take=take()), shot("two", hold=True),
                   shot("three", hold=True, take=take()), shot("four", storyboard=[1, 3]))
rendered = compiler.rendered_piece(renumbered)
check("named cards are renumbered to where they landed",
      rendered["segments"][2].get("storyboard"), [1, 2])
check("...and resolve to those payloads", boards(rendered), ["clip", "clip", [[0, 5], [1, 4]]])

passed("the storyboard is allotted, cited and renumbered as the strip says")

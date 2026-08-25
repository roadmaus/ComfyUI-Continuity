"""The face pass's geometry, and how a piece and a shot agree about running one.

Runs standalone — `python tests/test_faces.py` — with no torch and no ComfyUI,
because `faces.py` and `compile.py` are both free of them.

The load-bearing assertions are the window ones. H3 only takes 17n+5 frames and
a trimmed pass is rarely one, so the tiling has to cover every frame of the pass
using nothing but legal lengths and without ever addressing a frame the pass does
not have. Padding to fit would be the easy way and is the one thing this must
never do — see `spill.frames`, which refuses the same trade for a seam.
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
    for name in ("canvas", "contextir", "compile", "faces"):
        spec = importlib.util.spec_from_file_location(
            f"mmc.{name}", layout.py(name))
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"mmc.{name}"] = module
        setattr(package, name, module)
        spec.loader.exec_module(module)
        modules[name] = module
    return modules["canvas"], modules["compile"], modules["faces"]


canvas, compiler, faces = _load()

# The family the face pass belongs to — its own declaration, since nothing here
# defaults to one any more.
H3 = importlib.import_module("mmc.families.h3.declare").RULES

from harness import FAILURES, check, passed


def expect_error(label, fn, fragment):
    try:
        fn()
    except (compiler.CompileError, faces.FaceError) as exc:
        if fragment.lower() not in str(exc).lower():
            FAILURES.append(f"{label}: error {str(exc)!r} does not mention {fragment!r}")
    except Exception as exc:  # noqa: BLE001
        FAILURES.append(f"{label}: raised {type(exc).__name__}: {exc}")
    else:
        FAILURES.append(f"{label}: expected an error, got none")


# --- windows -----------------------------------------------------------------

LEGAL = set(canvas.legal_frame_counts(H3))

# The common case: a lone shot is generated at a legal count and nothing trims
# it, so there is one window, no overlap, and nothing to cross-fade.
for count in (5, 22, 39, 124, 226, 362):
    check(f"{count} frames is one window", faces.windows(count), [(0, count)])

# Off the grid — a feathered seam took frames off the ends. Every window is a
# legal length, they cover the pass, and the last one ends on its last frame.
for count in (23, 40, 100, 225, 363, 500, 1445):
    spans = faces.windows(count)
    lengths = {end - start for start, end in spans}
    check(f"{count}: every window is a length H3 takes", lengths <= LEGAL, True)
    check(f"{count}: starts at the first frame", spans[0][0], 0)
    check(f"{count}: ends on the last frame", spans[-1][1], count)
    check(f"{count}: never reaches past the pass",
          all(0 <= start and end <= count for start, end in spans), True)
    covered = set()
    for start, end in spans:
        covered.update(range(start, end))
    check(f"{count}: covers every frame", len(covered), count)
    check(f"{count}: in order and always moving",
          all(spans[i][0] < spans[i + 1][0] for i in range(len(spans) - 1)), True)

# Long passes are bitten off at the trained ceiling rather than asked for in one.
check("a 1445-frame pass is windowed, not sampled whole",
      max(end - start for start, end in faces.windows(1445)) <= H3.trained_max_frames,
      True)
expect_error("a pass shorter than one generation",
             lambda: faces.windows(3), "nothing here to refine")

# The overlap is cross-faded from one window to the next, and a frame only one
# window covers keeps its full weight.
spans = faces.windows(400)
weights = faces.window_weights(spans)
check("one weight per frame of each window",
      [len(w) for w in weights], [end - start for start, end in spans])
check("weights stay inside 0..1",
      all(0.0 <= value <= 1.0 for window in weights for value in window), True)
totals = {}
for window, (start, end) in enumerate(spans):
    for offset in range(end - start):
        totals[start + offset] = totals.get(start + offset, 0.0) + weights[window][offset]
check("every frame is composited exactly once over",
      all(abs(value - 1.0) < 1e-9 for value in totals.values()), True)


# --- smoothing and tracking ---------------------------------------------------

check("smoothing a flat line changes nothing",
      [round(v, 6) for v in faces.smooth([4.0] * 30, 11)], [4.0] * 30)
check("a window of 1 is a no-op", faces.smooth([1.0, 9.0, 2.0], 1), [1.0, 9.0, 2.0])
spike = faces.smooth([0.0] * 10 + [10.0] + [0.0] * 10, 11)
check("a spike is spread rather than kept", spike[10] < 5.0, True)
check("...and nothing is invented outside the range",
      all(-0.01 <= value <= 10.01 for value in spike), True)

# Two faces in shot: the track follows the one it was already on rather than
# whichever is largest this frame.
small = (100.0, 100.0, 40.0, 40.0)
large = (600.0, 300.0, 90.0, 90.0)
check("the first frame takes the largest", faces.pick([small, large], None), large)
check("...and later frames stay on the same face",
      faces.pick([large, (104.0, 104.0, 40.0, 40.0)], small), (104.0, 104.0, 40.0, 40.0))
check("nothing detected is nothing chosen", faces.pick([], small), None)

# Where the detector found nothing for a while, nothing is pasted.
found = [True] + [False] * 40 + [True]
weights = faces.paste_weights(found)
check("a frame with a detection is fully composited", weights[0], 1.0)
check("a blink rides through", weights[faces.BLIND_HOLD], 1.0)
check("a long blind run fades to nothing", weights[20], 0.0)
expect_error("a pass with no face at all",
             lambda: faces.paste_weights([False, False]), "no face was found")


# --- crops --------------------------------------------------------------------

# A face that walks towards the camera: the crop grows with it, and the face
# stays the same fraction of the canvas on every frame. That is the whole point
# of a per-frame crop — a fixed one would leave the face small on exactly the
# frames that needed the help.
boxes = [(500.0 - index, 300.0, 30.0 + index, 30.0 + index) for index in range(60)]
found = [True] * 60
crops, rects = faces.crop_boxes(boxes, found, 512, 512)
check("one crop per frame", (len(crops), len(rects)), (60, 60))
check("the crop is square when the canvas is",
      all(abs(crop[2] - crop[3]) < 1e-6 for crop in crops), True)
check("the crop grows with the face", crops[-1][3] > crops[0][3], True)
fractions = [rect[3] / 512 for rect in rects]
check("the face is the same fraction of the canvas throughout",
      max(fractions) - min(fractions) < 0.02, True)
check("...and that fraction is 1/crop_factor",
      abs(sum(fractions) / len(fractions) - 1 / faces.CROP_FACTOR) < 0.02, True)
check("the source face height is recoverable from the crop",
      abs(faces.face_heights(crops)[30] - 60.0) < 6.0, True)

# The crop is not clamped to the frame: a face at the very edge keeps the face
# centred and samples the border instead of being dragged inwards.
edge = faces.crop_boxes([(0.0, 0.0, 40.0, 40.0)], [True], 512, 512)[0]
check("a face on the edge keeps its centre", edge[0][0] + edge[0][2] / 2, 20.0)

# Strength: small faces get most of the denoise, large ones little.
curve = faces.strengths([20.0] * 20 + [200.0] * 20)
check("a tiny face is worked hard", curve[5] > 0.7, True)
check("a large face is left nearly alone", curve[-5] < 0.4, True)
check("and the curve is smooth across the change",
      all(abs(curve[i + 1] - curve[i]) < 0.2 for i in range(len(curve) - 1)), True)

# Feather is stated in source pixels, so the blend is the same physical width
# whatever this frame's magnification is — which means a bigger number in canvas
# space on the frames that were cropped tightest.
check("a tight crop feathers wider in canvas space",
      faces.feather_in_canvas(60, 512) > faces.feather_in_canvas(400, 512), True)
check("...and never more than a third of the canvas",
      faces.feather_in_canvas(4, 512) <= 512 // 3, True)


# --- the piece and the shot ---------------------------------------------------

PIECE = {"version": 2, "prompt": "", "models": {},
         "face": {"on": True, "canvas": 512, "denoise": 0.45},
         "segments": [{"prompt": "a face", "duration_s": 5}]}


def piece(**overrides):
    return {**PIECE, **overrides}


check("off by default", compiler.face_piece({}), None)
check("a switched-off piece runs none",
      compiler.face_piece({"face": {"on": False, "canvas": 512}}), None)
check("the piece's settings come back whole",
      compiler.face_piece(PIECE),
      {"on": True, "canvas": 512, "denoise": 0.45})
check("the canvas is clamped to what the weights hold",
      compiler.face_piece({"face": {"on": True, "canvas": 4096}})["canvas"],
      compiler.MAX_FACE_CANVAS)
check("...and snapped to /32",
      compiler.face_piece({"face": {"on": True, "canvas": 500}})["canvas"] % 32, 0)
check("the denoise is clamped under a full re-generation",
      compiler.face_piece({"face": {"on": True, "denoise": 5}})["denoise"],
      compiler.MAX_FACE_DENOISE)
expect_error("a denoise that is not a number",
             lambda: compiler.face_piece({"face": {"on": True, "denoise": "lots"}}),
             "must be a number")

# A shot says one of three things and only three.
check("a shot that says nothing inherits",
      compiler.face_for(PIECE, {}), compiler.face_piece(PIECE))
check("a shot can opt out", compiler.face_for(PIECE, {"face": "off"}), None)
check("a shot can opt in", compiler.face_for(PIECE, {"face": "on"}),
      compiler.face_piece(PIECE))
expect_error("a shot opting into a pass the piece is not running",
             lambda: compiler.face_for({}, {"face": "on"}), "piece has it switched off")
expect_error("a switch nobody defined",
             lambda: compiler.face_for(PIECE, {"face": "maybe"}), "on, off")

# A resolved setting reaches the segment node's payload, and only when it is on.
payloads = compiler.timeline_payloads(piece())
check("the shot's payload carries the piece's face pass",
      payloads[0]["request"]["face"], compiler.face_piece(PIECE))
payloads = compiler.timeline_payloads(
    piece(segments=[{"prompt": "a face", "duration_s": 5, "face": "off"}]))
check("a shot that opted out carries no key at all",
      "face" in payloads[0]["request"], False)
check("a piece that is not running one carries no key either",
      "face" in compiler.timeline_payloads(
          piece(face={"on": False}))[0]["request"], False)

# One pass is one face pass: merged cards that disagree are refused by name
# rather than resolved in favour of whichever came first.
merged = piece(segments=[{"prompt": "one", "duration_s": 5},
                         {"prompt": "two", "duration_s": 5, "merge": True}])
check("merged cards that agree compile",
      compiler.timeline_payloads(merged)[0]["request"]["face"],
      compiler.face_piece(PIECE))
merged["segments"][1]["face"] = "off"
expect_error("merged cards that disagree",
             lambda: compiler.timeline_payloads(merged), "disagree about the face pass")

# What the segment node makes of it.
compiled = compiler.compile_segment(compiler.timeline_payloads(piece())[0])
check("the pass knows its crop canvas",
      (compiled.face.width, compiled.face.height, compiled.face.denoise),
      (512, 512, 0.45))
check("and a piece without one compiles to nothing",
      compiler.compile_segment(
          compiler.timeline_payloads(piece(face={"on": False}))[0]).face,
      None)

passed("face geometry, windows and the piece/shot switch all hold")

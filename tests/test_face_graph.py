"""What the face pass adds to the render graph — and that off, it adds nothing.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_face_graph.py

Nothing is sampled and no detector is loaded: this is the emitted subgraph, which
can be inspected without a model. The two claims worth pinning are at the ends of
the file — with the switch off the graph is byte-identical to the one this pack
built before the feature existed, and with it on a following seam inherits the
*repaired* pass rather than the one whose face was wrong.

Skips itself with a message if ComfyUI cannot be imported.
"""

import asyncio
import importlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.basename(ROOT)
COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
BASE = os.environ.get("COMFYUI_BASE", COMFY)


def _boot():
    sys.path.insert(0, COMFY)
    sys.argv = ["main.py", "--base-directory", BASE]
    import nodes
    import server

    loop = asyncio.new_event_loop()
    server.PromptServer(loop)
    asyncio.set_event_loop(loop)
    loop.run_until_complete(nodes.init_extra_nodes(init_custom_nodes=False))

    sys.path.insert(0, os.path.dirname(ROOT))
    return importlib.import_module(PACKAGE), nodes


try:
    package, comfy_nodes = _boot()
except Exception as exc:  # noqa: BLE001
    print(f"skipped: ComfyUI not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)

cn = importlib.import_module(f"{PACKAGE}.creator_node")

from harness import FAILURES, check, passed

MODELS = {
    "fl2va": "h3/fl2va.safetensors",
    "ref2va": "h3/ref2va.safetensors",
    "clip": "h3/text_encoder.safetensors",
    "vae": "h3/video_vae.safetensors",
    "audio_vae": "h3/audio_vae.safetensors",
    "sam3": "sam3.safetensors",
}

FACE = {"on": True, "canvas": 512, "denoise": 0.45}
NODE_ID = "7"


def piece(face=None, segments=None, models=None):
    return json.dumps({
        "version": 2,
        "prompt": "",
        "models": models if models is not None else MODELS,
        "aspect": "16:9",
        "short_edge": 768,
        **({"face": face} if face is not None else {}),
        "segments": segments or [{"prompt": "a woman crossing a market",
                                  "duration_s": 5}],
    })


def with_id(node_class, unique_id, run):
    from comfy_api.latest import io as comfy_io

    previous = node_class.hidden
    node_class.hidden = comfy_io.HiddenHolder(
        unique_id=unique_id, prompt=None, extra_pnginfo=None, dynprompt=None,
        auth_token_comfy_org=None, api_key_comfy_org=None)
    try:
        return run()
    finally:
        node_class.hidden = previous


def build(data):
    return with_id(cn.MiniMaxH3Timeline, NODE_ID,
                   lambda: cn.MiniMaxH3Timeline.execute(
                       timeline_data=data, seed=100, steps=20, cfg=1.0,
                       sampler_name="res_multistep", scheduler="simple")).expand


def normalised(graph):
    """A graph as JSON, with the builder's per-call id prefix taken out.

    `GraphBuilder` numbers each expansion it makes, so two graphs built in one
    process are never string-equal however identical their wiring is. Everything
    after that prefix — order, class, input, link — is what is being compared.
    """
    text = json.dumps(graph, sort_keys=True)
    prefix = next(iter(graph)).rsplit(".", 1)[0] + "."
    return text.replace(prefix, "#")


def by_class(graph):
    out = {}
    for node_id, node in graph.items():
        out.setdefault(node["class_type"], []).append((node_id, node["inputs"]))
    return out


def expect_error(label, fn, fragment):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        if fragment.lower() not in str(exc).lower():
            FAILURES.append(f"{label}: error {str(exc)!r} does not mention {fragment!r}")
    else:
        FAILURES.append(f"{label}: expected an error mentioning {fragment!r}, got none")


# --- off, it is not there -----------------------------------------------------
#
# Every workflow that exists was saved without this feature, and the promise is
# that they render exactly as they did. Not "equivalently": the same graph, so
# the same cache keys and the same bytes out.

check("a piece with no face key emits no face pass",
      "MiniMaxH3FacePass" in by_class(build(piece())), False)
check("switching it off is the same graph as never having it",
      normalised(build(piece(face={"on": False, "canvas": 512}))),
      normalised(build(piece())))
check("...and so is a shot opting out of a piece that is off",
      normalised(build(piece(segments=[{"prompt": "a woman crossing a market",
                                        "duration_s": 5, "face": "off"}]))),
      normalised(build(piece())))


# --- on -----------------------------------------------------------------------

graph = build(piece(face=FACE))
kinds = by_class(graph)

check("one face pass", len(kinds["MiniMaxH3FacePass"]), 1)
face_id, face_inputs = kinds["MiniMaxH3FacePass"][0]
reel_id, reel_inputs = kinds["MiniMaxH3Reel"][0]

check("it reads the pass the reel wrote", face_inputs["source"], [reel_id, 1])
check("...and the reel it went onto", face_inputs["reel"], [reel_id, 0])
check("it is given the detector that was picked", face_inputs["detector"], MODELS["sam3"])
check("it runs at the crop canvas",
      (face_inputs["width"], face_inputs["height"]), (512, 512))
check("at the piece's denoise", face_inputs["denoise"], 0.45)
check("and on the render's own sampler",
      (face_inputs["steps"], face_inputs["cfg"], face_inputs["sampler_name"],
       face_inputs["scheduler"]),
      (20, 1.0, "res_multistep", "simple"))

# The save node is the end of the reel, so it has to be reading the repaired
# pass. If this ever reads the reel node again, the face pass runs and nothing
# it produces is ever written.
save_inputs = kinds["MiniMaxH3Save"][0][1]
check("the file is written from the repaired reel", save_inputs["reel"], [face_id, 0])

# Two segment nodes now: the pass's own, and one compiled at the crop canvas so
# the conditioning is encoded at the size the crop is drawn at.
segments = kinds["MiniMaxH3TimelineSegment"]
check("a second segment node builds the crop's conditioning", len(segments), 2)
# Both are pinned — a timeline holds every segment to one geometry — so the crop
# is told apart by the canvas it is pinned *to*.
crop_id, crop = next(
    (node_id, inputs) for node_id, inputs in segments
    if json.loads(inputs["segment_data"])["canvas"]["width"] == 512)
crop_data = json.loads(crop["segment_data"])
check("pinned to the crop canvas",
      (crop_data["canvas"]["width"], crop_data["canvas"]["height"]), (512, 512))
check("...square", crop_data["canvas"]["label"], "1:1")
check("the crop pass does not ask for a face pass of its own",
      "face" in crop_data["request"], False)
shot_data = json.loads(next(inputs["segment_data"] for node_id, inputs in segments
                            if node_id != crop_id))
check("the pass it repairs did ask for one", "face" in shot_data["request"], True)
check("no seam links on it",
      any(key in crop for key in ("prev_image", "prev_audio", "next_image", "next_audio")),
      False)
check("the face node's conditioning is the crop segment's",
      face_inputs["positive"], [crop_id, 1])


# --- keyframes are dropped from the crop's conditioning ------------------------
#
# A keyframe is a condition latent for the whole picture, injected every step.
# Inside a face crop it is an instruction to match a composition that is not in
# the crop, so the crop compiles as the pass it becomes without one. References
# stay — a character sheet is exactly what a face crop wants.

# Asserted against `render.face_payload` itself rather than through a build,
# because a keyframe has to be a file on disk before the canvas can be resolved
# from it, and what is being checked here is what the payload keeps.
render_mod = importlib.import_module(f"{PACKAGE}.render")
compile_mod = importlib.import_module(f"{PACKAGE}.compile")
keyed = render_mod.face_payload({"request": {
    "prompt": "a woman crossing a market",
    "duration_s": 5,
    "face": {"on": True, "canvas": 512, "denoise": 0.45},
    "assets": [
        {"handle": "img-1", "kind": "image", "role": "first_frame",
         "filename": "start.png"},
        {"handle": "img-2", "kind": "image", "role": "reference",
         "filename": "her.png"},
    ],
}}, compile_mod.Face(512, 512, 0.45))
check("the crop's conditioning has no keyframe in it",
      [asset["role"] for asset in keyed["request"]["assets"]], ["reference"])
check("...and no face pass of its own", "face" in keyed["request"], False)
check("...at the crop canvas", keyed["canvas"]["width"], 512)


# --- the seam inherits the repaired pass ---------------------------------------

two = build(piece(face=FACE, segments=[
    {"prompt": "a woman crossing a market", "duration_s": 5},
    {"prompt": "she stops at a stall", "duration_s": 5, "continue": True},
]))
kinds = by_class(two)
check("one face pass per generated pass", len(kinds["MiniMaxH3FacePass"]), 2)
face_ids = [node_id for node_id, _ in kinds["MiniMaxH3FacePass"]]
frames_inputs = kinds["MiniMaxH3PassFrames"][0][1]
check("the second shot continues from the repaired first pass",
      frames_inputs["source"], [face_ids[0], 1])
check("the second face pass takes the reel through the first",
      kinds["MiniMaxH3FacePass"][1][1]["reel"][0] in
      {node_id for node_id, _ in kinds["MiniMaxH3Reel"]}, True)


# --- refusals ------------------------------------------------------------------

expect_error("the face pass with no detector picked",
             lambda: build(piece(face=FACE,
                                 models={k: v for k, v in MODELS.items() if k != "sam3"})),
             "models/checkpoints")
expect_error("a shot opting into a piece that is not running one",
             lambda: build(piece(segments=[{"prompt": "x", "duration_s": 5,
                                            "face": "on"}])),
             "piece has it switched off")

passed("the face pass wires up, seams inherit it, and off it is not there")

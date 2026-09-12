"""What the motion fix adds to the render graph — and that off, it adds nothing.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_motion_graph.py

Nothing is sampled: this is the emitted subgraph. The claims worth pinning are
that without the switch the graph is byte-identical to the one this pack built
before the feature existed, and that with it on the pass is re-drawn in place —
the following seam inherits the *fixed* pass, the face pass runs over it rather
than under it, and a blended seam off it takes the frames road.

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
    return nodes


try:
    comfy_nodes = _boot()
except Exception as exc:  # noqa: BLE001
    print(f"skipped: ComfyUI not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)

package = importlib.import_module(PACKAGE)
cn = importlib.import_module(f"{PACKAGE}.creator.creator_node")
derope = importlib.import_module(f"{PACKAGE}.creator.families.h3.derope")

from harness import FAILURES, check, passed

MODELS = {
    "fl2va": "h3/fl2va.safetensors",
    "ref2va": "h3/ref2va.safetensors",
    "clip": "h3/text_encoder.safetensors",
    "vae": "h3/video_vae.safetensors",
    "audio_vae": "h3/audio_vae.safetensors",
    "sam3": "sam3.safetensors",
}
NODE_ID = "7"
SHOT = {"prompt": "a dancer spins and lands", "duration_s": 5}


def piece(segments=None, **fields):
    return json.dumps({
        "version": 2, "prompt": "", "models": MODELS, "aspect": "16:9",
        "short_edge": 768, **fields,
        "segments": segments or [dict(SHOT)],
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
    text = json.dumps(graph, sort_keys=True)
    prefix = next(iter(graph)).rsplit(".", 1)[0] + "."
    return text.replace(prefix, "#")


def by_class(graph):
    out = {}
    for node_id, node in graph.items():
        out.setdefault(node["class_type"], []).append((node_id, node["inputs"]))
    return out


# --- off, it is not there -----------------------------------------------------

check("a piece with no motion_fix key emits no motion fix",
      "MiniMaxH3MotionFix" in by_class(build(piece())), False)
check("a card saying false is the same graph as never having it",
      normalised(build(piece([{**SHOT, "motion_fix": False}]))),
      normalised(build(piece())))


# --- on -----------------------------------------------------------------------

graph = build(piece([{**SHOT, "motion_fix": True}]))
kinds = by_class(graph)

check("one motion fix", len(kinds["MiniMaxH3MotionFix"]), 1)
fix_id, fix_inputs = kinds["MiniMaxH3MotionFix"][0]
reel_id, reel_inputs = kinds["MiniMaxH3Reel"][0]

check("it reads the pass the reel wrote", fix_inputs["source"], [reel_id, 1])
check("...and the reel it went onto", fix_inputs["reel"], [reel_id, 0])
check("...and the latent the reel decoded", fix_inputs["latent"], reel_inputs["samples"])
check("no head trim on a first shot", fix_inputs["head"], 0)
check("at the method's inject", fix_inputs["denoise"], derope.INJECT)
check("on the render's own sampler",
      (fix_inputs["steps"], fix_inputs["cfg"], fix_inputs["sampler_name"],
       fix_inputs["scheduler"]),
      (20, 1.0, "res_multistep", "simple"))

save_inputs = kinds["MiniMaxH3Save"][0][1]
check("the file is written from the fixed reel", save_inputs["reel"], [fix_id, 0])

segments = kinds["MiniMaxH3TimelineSegment"]
check("a second segment node builds the fix's conditioning", len(segments), 2)
fix_segment_id = fix_inputs["positive"][0]
fix_data = json.loads(dict(segments)[fix_segment_id]["segment_data"])
shot_data = json.loads(next(inputs["segment_data"] for node_id, inputs in segments
                            if node_id != fix_segment_id))
check("the fix's conditioning is at the delivered canvas",
      (fix_data["canvas"]["width"], fix_data["canvas"]["height"]),
      (shot_data["canvas"]["width"], shot_data["canvas"]["height"]))
check("the fix's own request does not ask for a fix", "motion_fix" in fix_data, False)
check("...nor does the pass's segment node carry the flag in its cache key",
      "motion_fix" in shot_data.get("request", {}), False)
check("no seam links on it",
      any(key in dict(segments)[fix_segment_id]
          for key in ("prev_image", "prev_audio", "prev_latent", "next_image")),
      False)


# --- keyframes are dropped from the fix's conditioning ------------------------

render_mod = importlib.import_module(f"{PACKAGE}.creator.families.h3.render")
compile_mod = importlib.import_module(f"{PACKAGE}.creator.compile")
compiled = compile_mod.compile_request({"prompt": "x", "duration_s": 5})
keyed = render_mod.motion_payload({"request": {
    "prompt": "x", "duration_s": 5,
    "assets": [
        {"handle": "img-1", "kind": "image", "role": "first_frame", "filename": "start.png"},
        {"handle": "img-2", "kind": "image", "role": "reference", "filename": "her.png"},
    ],
}}, compiled)
check("the fix's conditioning has no keyframe in it",
      [asset["role"] for asset in keyed["request"]["assets"]], ["reference"])
check("...at the pass's canvas", keyed["canvas"]["width"], compiled.width)
refined = compile_mod.compile_request({"prompt": "x", "duration_s": 5, "short_edge": 1080,
                                       "upscale": "two_pass"})
if refined.refine:
    check("...or the refine's, where the pass was refined",
          render_mod.motion_payload({"request": {"prompt": "x", "duration_s": 5}},
                                    refined)["canvas"]["width"],
          refined.refine.width)


# --- the seam inherits the fixed pass ------------------------------------------

two = build(piece([{**SHOT, "motion_fix": True},
                   {"prompt": "she bows", "duration_s": 5, "continue": True}]))
kinds = by_class(two)
check("only the card that asked is fixed", len(kinds["MiniMaxH3MotionFix"]), 1)
fix_id = kinds["MiniMaxH3MotionFix"][0][0]
check("the second shot continues from the fixed pass",
      kinds["MiniMaxH3PassFrames"][0][1]["source"], [fix_id, 1])

blended = by_class(build(piece([
    {**SHOT, "motion_fix": True},
    {"prompt": "she bows", "duration_s": 5, "continue": True, "feather": 22, "motion_fix": True},
])))
check("a blended seam off a fixed pass is handed no latent",
      any("prev_latent" in inputs for _, inputs in blended["MiniMaxH3TimelineSegment"]),
      False)
second_fix = blended["MiniMaxH3MotionFix"][1][1]
check("a continued card tells the fix what the reel trimmed", second_fix["head"], 22)

# --- with the face pass, the fix goes first -------------------------------------

both = by_class(build(piece([{**SHOT, "motion_fix": True}],
                            face={"on": True, "canvas": 512, "denoise": 0.45})))
fix_id = both["MiniMaxH3MotionFix"][0][0]
face_inputs = both["MiniMaxH3FacePass"][0][1]
check("the face pass repairs the fixed pass", face_inputs["source"], [fix_id, 1])
check("...on the reel the fix handed on", face_inputs["reel"], [fix_id, 0])

# --- footage is never fixed -----------------------------------------------------

footage = build(piece([dict(SHOT), {"kind": "clip", "filename": "footage/plate.mp4",
                                    "duration_s": 6, "motion_fix": True}]))
check("a clip card's flag emits nothing", "MiniMaxH3MotionFix" in by_class(footage), False)

passed("the motion fix wires up in place, seams inherit it, and off it is not there")

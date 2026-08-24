"""What the re-detail pass adds to the render graph — and that off, it adds nothing.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_redetail_graph.py

Nothing is sampled and no weights are loaded: this is the emitted subgraph, which
can be inspected without a model on the disk. The claims worth pinning are the
ones a wrong graph would fail silently on — that the pass sits *after* the whole
reel rather than inside the loop, that the file is written from what it hands
back, that an H3 piece builds a second family's loaders while an LTX 2.5 piece
borrows its own, and that a piece that never asks for it emits exactly the graph
this pack built before the backend existed.

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

# Outside the skip guard, deliberately — see `test_face_graph.py`.
package = importlib.import_module(PACKAGE)
cn = importlib.import_module(f"{PACKAGE}.creator.creator_node")
redetail = importlib.import_module(f"{PACKAGE}.creator.redetail")

from harness import FAILURES, check, passed

H3_MODELS = {
    "fl2va": "h3/fl2va.safetensors",
    "ref2va": "h3/ref2va.safetensors",
    "clip": "h3/text_encoder.safetensors",
    "vae": "h3/video_vae.safetensors",
    "audio_vae": "h3/audio_vae.safetensors",
}

LTX_MODELS = {
    "dit": "ltx/dit.safetensors",
    "clip": "ltx/gemma4-with-proj.safetensors",
    "vae": "ltx/video-vae.safetensors",
    "audio_vae": "ltx/audio-vae.safetensors",
}

# The backend's own block. Four of its five ids are LTX 2.5's own, which is why
# it cannot live in `models` on an H3 piece: `vae` there is H3's video VAE.
UPSCALE_MODELS = {
    "dit": "ltx/dit.safetensors",
    "clip": "ltx/gemma4-with-proj.safetensors",
    "vae": "ltx/video-vae.safetensors",
    "audio_vae": "ltx/audio-vae.safetensors",
    "ic_lora": "ltx-2.5-22b-ic-lora-pixel-spatial-upscaler-x2-1.0.safetensors",
}

NODE_ID = "7"


def piece(upscale=None, family=None, models=None, upscale_models=None,
          segments=None, short_edge=768):
    return json.dumps({
        "version": 2,
        "prompt": "",
        **({"family": family} if family else {}),
        "models": models if models is not None else H3_MODELS,
        **({"upscale_models": upscale_models} if upscale_models is not None else {}),
        "aspect": "16:9",
        "short_edge": short_edge,
        **({"upscale": upscale} if upscale else {}),
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

check("a piece with no upscale key emits no re-detail pass",
      "MiniMaxReDetailPass" in by_class(build(piece())), False)
check("neither does one on the family's own two passes",
      "MiniMaxReDetailPass" in by_class(build(piece(upscale="two_pass"))), False)
check("...and 'direct' is the graph it always was",
      normalised(build(piece(upscale="direct"))),
      normalised(build(piece(upscale="direct", upscale_models=UPSCALE_MODELS))))


# --- on, over an H3 piece -----------------------------------------------------

graph = build(piece(upscale="redetail", upscale_models=UPSCALE_MODELS))
kinds = by_class(graph)

check("one re-detail pass for the whole reel", len(kinds["MiniMaxReDetailPass"]), 1)
pass_id, pass_inputs = kinds["MiniMaxReDetailPass"][0]
reel_id, _ = kinds["MiniMaxH3Reel"][0]

check("it takes the finished reel", pass_inputs["reel"], [reel_id, 0])
check("the file is written from what it hands back",
      kinds["MiniMaxH3Save"][0][1]["reel"], [pass_id, 0])
check("it is given the IC-LoRA that was picked",
      pass_inputs["ic_lora"], UPSCALE_MODELS["ic_lora"])

# The canvas: sampled at the native edge, finished at twice it. 768 x 1344 is
# H3's 16:9 canvas at its native short edge (1344 x 768), and both halves of it
# land on the /64 grid the guide's dilation needs.
check("it finishes at twice the sampled canvas",
      (pass_inputs["width"], pass_inputs["height"]), (2688, 1536))
check("...which is on the IC-LoRA's own grid",
      (pass_inputs["width"] % redetail.GRID, pass_inputs["height"] % redetail.GRID),
      (0, 0))
segment_data = json.loads(kinds["MiniMaxH3TimelineSegment"][0][1]["segment_data"])
check("and the render itself sampled at the native edge",
      (segment_data["canvas"]["width"], segment_data["canvas"]["height"]),
      (1344, 768))
check("in one pass — nothing is refined up before it is re-detailed",
      "MiniMaxH3RefinePass" in kinds, False)

# A second family's weights, beside the ones the piece renders with.
loaders = {node_id: inputs for node_id, inputs in kinds["UNETLoader"]}
check("a second transformer is loaded for the pass",
      pass_inputs["model"][0] in loaders, True)
check("...and it is the backend's file, not the piece's",
      loaders[pass_inputs["model"][0]]["unet_name"], UPSCALE_MODELS["dit"])
vaes = {node_id: inputs for node_id, inputs in kinds["VAELoader"]}
check("the pass decodes through LTX's video VAE",
      vaes[pass_inputs["vae"][0]]["vae_name"], UPSCALE_MODELS["vae"])
check("...and reads the sound through LTX's audio VAE",
      vaes[pass_inputs["audio_vae"][0]]["vae_name"], UPSCALE_MODELS["audio_vae"])


# --- on, over an LTX 2.5 piece ------------------------------------------------
#
# The four shared slots are the same files under the same ids. Building a second
# set would put a 21.5 GB transformer in memory twice for one render, so the
# family's own links answer instead — and the only new file is the IC-LoRA.

ltx = build(piece(upscale="redetail", family="ltx25", models=LTX_MODELS,
                  upscale_models={"ic_lora": UPSCALE_MODELS["ic_lora"]},
                  short_edge=544))
kinds = by_class(ltx)
_, ltx_pass = kinds["MiniMaxReDetailPass"][0]
check("an LTX piece loads one transformer, not two", len(kinds["UNETLoader"]), 1)
check("...and the pass runs on it",
      ltx_pass["model"], [kinds["UNETLoader"][0][0], 0])
check("two VAEs and no more", len(kinds["VAELoader"]), 2)
check("it finishes at twice LTX's own native canvas",
      (ltx_pass["width"], ltx_pass["height"]), (1920, 1088))


# --- the seams and the strip --------------------------------------------------

two = build(piece(upscale="redetail", upscale_models=UPSCALE_MODELS, segments=[
    {"prompt": "a woman crossing a market", "duration_s": 5},
    {"prompt": "she stops at a stall", "duration_s": 5, "continue": True},
]))
kinds = by_class(two)
check("still one pass for a strip of two", len(kinds["MiniMaxReDetailPass"]), 1)
# The whole reason it runs after the loop rather than inside it: a seam that
# inherited a re-detailed pass would hand the next segment a guide at twice the
# canvas it is about to sample at.
reel_ids = {node_id for node_id, _ in kinds["MiniMaxH3Reel"]}
check("a seam inherits the pass as rendered, not as re-detailed",
      kinds["MiniMaxH3PassFrames"][0][1]["source"][0] in reel_ids, True)
check("and the pass is handed the reel the last segment ended on",
      kinds["MiniMaxReDetailPass"][0][1]["reel"][0] in reel_ids, True)


# --- refusals -----------------------------------------------------------------

expect_error("the pass with no IC-LoRA picked",
             lambda: build(piece(upscale="redetail",
                                 upscale_models={k: v for k, v in
                                                 UPSCALE_MODELS.items()
                                                 if k != "ic_lora"})),
             "models/loras")
expect_error("...or with none of the backend's files at all",
             lambda: build(piece(upscale="redetail")),
             "ReDetail")
expect_error("an LTX piece still has to name the IC-LoRA",
             lambda: build(piece(upscale="redetail", family="ltx25",
                                 models=LTX_MODELS, short_edge=544)),
             "models/loras")
expect_error("a strip carrying supplied footage",
             lambda: build(piece(upscale="redetail",
                                 upscale_models=UPSCALE_MODELS, segments=[
                                     {"prompt": "a woman crossing a market",
                                      "duration_s": 5},
                                     {"kind": "clip", "filename": "b-roll.mp4",
                                      "duration_s": 3},
                                 ])),
             "supplied footage")

passed("the re-detail pass wires onto the end of the reel, borrows LTX's weights "
       "where they are the piece's own, and off it is not there")

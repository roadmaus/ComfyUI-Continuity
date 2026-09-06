"""What the DLSS 5 refiner adds to a graph — and that off, it adds nothing.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_neural_graph.py

Nothing is sampled and no weights are loaded: this is the emitted subgraph. The
claims worth pinning are the ones a wrong graph would fail silently on — that a
still's refine node sits *between* the decode and the save so the file written
is the refined picture, that a video's pass sits after the whole reel (and
after ReDetail, so it draws on the frames at the size they leave at), that its
dials are the piece's and its seed the render's, and that a piece which never
asked emits exactly the graph it always did.

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
ps = importlib.import_module(f"{PACKAGE}.creator.prestage")
neural = importlib.import_module(f"{PACKAGE}.creator.neural")
neuralpass = importlib.import_module(f"{PACKAGE}.creator.neuralpass")

from harness import FAILURES, check, passed

passed("the neural refiner sits between decode and save on a still, after the "
       "reel on a video, and off it is not there")

REFINE, PASS = neuralpass.REFINE_NODE, neuralpass.PASS_NODE

H3_MODELS = {
    "fl2va": "h3/fl2va.safetensors",
    "ref2va": "h3/ref2va.safetensors",
    "clip": "h3/text_encoder.safetensors",
    "vae": "h3/video_vae.safetensors",
    "audio_vae": "h3/audio_vae.safetensors",
}
UPSCALE_MODELS = {
    "dit": "ltx/dit.safetensors",
    "clip": "ltx/gemma4-with-proj.safetensors",
    "vae": "ltx/video-vae.safetensors",
    "audio_vae": "ltx/audio-vae.safetensors",
    "ic_lora": "ltx-2.5-22b-ic-lora-pixel-spatial-upscaler-x2-1.0.safetensors",
}
KREA_MODELS = {"krea2": {"model": "krea2.safetensors", "clip": "qwen.safetensors",
                         "vae": "flux-vae.safetensors"}}

ON = {"on": True, "profile": "cinematic", "scale": 1.5, "detail": 2.0,
      "colour": 0.5, "intensity": 0.9, "precision": "fast"}
NODE_ID = "7"


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


def piece(neural_block=None, upscale=None, upscale_models=None, segments=None):
    return json.dumps({
        "version": 2, "prompt": "", "models": H3_MODELS, "aspect": "16:9",
        "short_edge": 768,
        **({"neural": neural_block} if neural_block is not None else {}),
        **({"upscale": upscale} if upscale else {}),
        **({"upscale_models": upscale_models} if upscale_models else {}),
        "segments": segments or [{"prompt": "a woman crossing a market", "duration_s": 5}],
    })


def video(data, seed=100):
    return with_id(cn.MiniMaxH3Timeline, NODE_ID,
                   lambda: cn.MiniMaxH3Timeline.execute(
                       timeline_data=data, seed=seed, steps=20, cfg=1.0,
                       sampler_name="res_multistep", scheduler="simple")).expand


def still_blob(arch="krea2", neural_block=None):
    data = {"version": 1, "arch": arch, "prompt": "a lantern", "aspect": "1:1",
            "short_edge": 1024, "refs": [], "loras": [], "models": KREA_MODELS}
    if arch == "minimax":
        data["minimax"] = {"frames": 5, "latent_index": 0,
                           "request": {"prompt": "a lantern", "assets": [], "loras": [],
                                       "aspect": "1:1", "short_edge": 768,
                                       "models": H3_MODELS}}
    if neural_block is not None:
        data["neural"] = neural_block
    return json.dumps(data)


def still(data):
    return with_id(ps.MiniMaxH3PreStage, NODE_ID,
                   lambda: ps.MiniMaxH3PreStage.execute(
                       prestage_data=data, seed=100, steps=52, cfg=3.5,
                       sampler_name="euler", scheduler="simple")).expand


def normalised(graph):
    text = json.dumps(graph, sort_keys=True)
    prefix = next(iter(graph)).rsplit(".", 1)[0] + "."
    return text.replace(prefix, "#")


def by_class(graph):
    out = {}
    for node_id, node in graph.items():
        out.setdefault(node["class_type"], []).append((node_id, node["inputs"]))
    return out


# --- a still ------------------------------------------------------------------

check("a still with no block emits no refine node", REFINE in by_class(still(still_blob())), False)
check("...and one with the block off is the same graph",
      normalised(still(still_blob(neural_block={"on": False}))), normalised(still(still_blob())))

for arch in ("krea2", "minimax"):
    kinds = by_class(still(still_blob(arch, neural_block=ON)))
    check(f"{arch}: one refine node", len(kinds.get(REFINE, [])), 1)
    refine_id, refine_inputs = kinds[REFINE][0]
    save = kinds["MiniMaxH3SaveImage"][0][1]
    check(f"{arch}: the save node writes the refined picture", save["images"], [refine_id, 0])
    fed = refine_inputs["image"][0]
    check(f"{arch}: the refine node reads the decode",
          kinds and any(node_id == fed for node_id, _ in kinds.get("VAEDecode", []) + kinds.get("ImageFromBatch", [])),
          True)
    check(f"{arch}: its dials are the piece's",
          {key: refine_inputs[key] for key in ("profile", "processing_scale", "detail_strength",
                                               "colour_strength", "intensity", "precision")},
          {"profile": "cinematic", "processing_scale": 1.5, "detail_strength": 2.0,
           "colour_strength": 0.5, "intensity": 0.9, "precision": "fast"})
    check(f"{arch}: a still carries no history", refine_inputs["history"], False)


# --- a video ------------------------------------------------------------------

check("a piece with no block emits no pass", PASS in by_class(video(piece())), False)
check("...and one with the block off is the graph it always was",
      normalised(video(piece(neural_block={"on": False}))), normalised(video(piece())))

graph = video(piece(neural_block=ON))
kinds = by_class(graph)
check("one pass for the whole reel", len(kinds.get(PASS, [])), 1)
pass_id, pass_inputs = kinds[PASS][0]
reel_id, _ = kinds["MiniMaxH3Reel"][0]
check("it takes the finished reel", pass_inputs["reel"], [reel_id, 0])
check("the file is written from what it hands back", kinds["MiniMaxH3Save"][0][1]["reel"], [pass_id, 0])
check("its dials are the piece's",
      {key: pass_inputs[key] for key in ("profile", "detail_strength", "colour_strength",
                                         "intensity", "precision")},
      {"profile": "cinematic", "detail_strength": 2.0, "colour_strength": 0.5,
       "intensity": 0.9, "precision": "fast"})
check("the pass has no processing scale: history runs at the frame's own size",
      "processing_scale" in pass_inputs, False)
check("its noise is seeded by the render", pass_inputs["frame_index"], 100)
check("a re-rolled piece seeds it differently",
      by_class(video(piece(neural_block=ON), seed=101))[PASS][0][1]["frame_index"], 101)

# After ReDetail, so it draws onto the frames at the size they leave at.
kinds = by_class(video(piece(neural_block=ON, upscale="redetail", upscale_models=UPSCALE_MODELS)))
redetail_id, _ = kinds["MiniMaxReDetailPass"][0]
pass_id, pass_inputs = kinds[PASS][0]
check("under ReDetail the pass reads the re-detailed reel", pass_inputs["reel"], [redetail_id, 0])
check("...and the save reads the pass", kinds["MiniMaxH3Save"][0][1]["reel"], [pass_id, 0])

# A strip of two shots: the takes come off the refined reel rather than off each
# pass as it is written, so a kept take is the refined one.
two = [{"prompt": "a", "duration_s": 5}, {"prompt": "b", "duration_s": 5, "continuity": "blend"}]
kinds = by_class(video(piece(neural_block=ON, segments=two)))
check("a refined strip writes its takes from the save node, not per pass",
      "ContinuityTake" in kinds, False)
check("...where an unrefined strip writes them per pass",
      "ContinuityTake" in by_class(video(piece(segments=two))), True)

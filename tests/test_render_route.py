"""`/continuity/render` builds what the node would queue, from a script's request.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_render_route.py

The turbo arithmetic is `tests/test_headless.py`'s. This is the joining: that a
request of a family, a prompt and a picture becomes a one-node prompt for the
right node over this machine's picks, that `fast` throws the distill for the
checkpoint the dry run actually routed to, and that everything a script can get
wrong comes back as a sentence rather than a queued render. Nothing is queued
and no model folder has to hold a file: the listing, the picks and the LoRA
names are stood in.

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
    try:
        from app.assets.manager import default_asset_manager
        server.PromptServer(loop, default_asset_manager())
    except (ImportError, TypeError):
        server.PromptServer(loop)
    asyncio.set_event_loop(loop)
    loop.run_until_complete(nodes.init_extra_nodes(init_custom_nodes=False))

    sys.path.insert(0, os.path.dirname(ROOT))


try:
    _boot()
except Exception as exc:  # noqa: BLE001
    print(f"skipped: ComfyUI not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)

importlib.import_module(PACKAGE)
route = importlib.import_module(f"{PACKAGE}.creator.routes.render")
chat = importlib.import_module(f"{PACKAGE}.creator.chat")
headless = importlib.import_module(f"{PACKAGE}.creator.headless")

from harness import FAILURES, check, passed  # noqa: E402

FL2V = "minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy_resized_avg_rank_21_bf16.safetensors"
REF8 = "minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors"
FILES = {
    "diffusion_models": ["h3_fl2va.safetensors", "h3_ref2va.safetensors", "krea2_raw.safetensors",
                         "krea2_turbo.safetensors"],
    "text_encoders": ["qwen3.safetensors", "qwen3vl_4b.safetensors"],
    "vae": ["video_vae.safetensors", "audio_vae.safetensors", "qwen_image_vae.safetensors"],
}
STORED = {"h3": {"fl2va": "h3_fl2va.safetensors", "ref2va": "h3_ref2va.safetensors",
                 "clip": "qwen3.safetensors", "vae": "video_vae.safetensors",
                 "audio_vae": "audio_vae.safetensors"},
          "krea2": {"model": "krea2_raw.safetensors", "turbo_model": "krea2_turbo.safetensors",
                    "clip": "qwen3vl_4b.safetensors", "vae": "qwen_image_vae.safetensors"}}

route.core_models.available = lambda: {"by_folder": FILES, "files": {}, "installed": {}}
# The whole defaults under the picks, as `settings.load` hands them: a stub of
# the weights alone lost every key added since (`screen_tracker` first).
route.settings.load = lambda: {**route.settings.DEFAULTS, "weights": STORED}
route.server_routes._lora_names = lambda: [FL2V, REF8, "anna.safetensors"]
# A picture's size is read off disk by the dry run; there is no disk here.
route.server_routes.media.image_size = lambda filename, crop=None: (1024, 768)


def render(**body):
    try:
        return route._render(body)
    except (headless.HeadlessError, chat.ActionError) as problem:
        return {"problem": str(problem)}


def inputs(built):
    node = built["prompt"][chat.NODE]
    field = "creator_data" if node["class_type"] == "MiniMaxH3Creator" else "prestage_data"
    return node["class_type"], node["inputs"], json.loads(node["inputs"][field])


built = render(family="h3", prompt="a cat stretches on a sunny windowsill", seed=7)
if "problem" in built:
    FAILURES.append(f"a text-only H3 render was refused: {built['problem']}")
else:
    kind, widgets, blob = inputs(built)
    check("a clip is the Creator, seeded as asked", (kind, widgets["seed"]), ("MiniMaxH3Creator", 7))
    check("over this machine's picks", blob["models"]["clip"], "qwen3.safetensors")
    check("fast by default: the FL2V distill, on the checkpoint a text render routes to",
          [(e["name"], e["modes"]) for e in blob["loras"]], [(FL2V, ["fl2va"])])
    check("and the switch's row is on the blob, where it beats the widgets",
          (blob["sampling"]["steps"], blob["sampling"]["sampler_name"]),
          (headless.turbo_of(route.manifest.describe("h3"))["steps"]["medium"], "euler"))
    check("the answer says it was turbo", built["speed"]["turbo"]["loras"], [FL2V])

built = render(family="h3", prompt="@pic-1 walks through a garden",
               pictures=[{"filename": "cat.png", "as": "ref"}], quality="good")
if "problem" in built:
    FAILURES.append(f"a reference H3 render was refused: {built['problem']}")
else:
    _, _, blob = inputs(built)
    check("a reference render takes the Ref2V distill for the quality's step count",
          [(e["name"], e["modes"]) for e in blob["loras"]], [(REF8, ["ref2va"])])
    check("with the picture on the card as a reference",
          [(a["handle"], a["role"], a["filename"]) for a in blob["segments"][-1]["assets"]],
          [("pic-1", "reference", "cat.png")])

built = render(family="h3", prompt="@pic-1 walks through a garden",
               pictures=[{"filename": "cat.png", "as": "ref"}], quality="good", merged=True)
if "problem" in built:
    FAILURES.append(f"a merged-checkpoint H3 render was refused: {built['problem']}")
else:
    _, _, blob = inputs(built)
    check("merged: the Ref2V render takes the step drop and no distill",
          (blob["loras"], blob["sampling"]["steps"], blob["turbo"].get("merged")), ([], 8, True))
check("merged is refused on a still, pointed at the turbo checkpoint slot",
      "turbo_model" in render(family="krea2", prompt="a cat", still=True,
                              merged=True).get("problem", ""), True)

STORED["h3"]["devices"] = {"clip": "cuda:1", "fl2va": "cuda:0"}
built = render(family="h3", prompt="a cat", devices={"fl2va": "cuda:1", "vae": "cpu"})
if "problem" in built:
    FAILURES.append(f"a render with pinned devices was refused: {built['problem']}")
else:
    _, _, blob = inputs(built)
    check("the machine's pins ride on a headless render, a request's own over them slot by slot",
          blob["models"]["devices"], {"clip": "cuda:1", "fl2va": "cuda:1", "vae": "cpu"})
del STORED["h3"]["devices"]

# The machine's row: what a node last set for the card, under a request's own.
# Before it was read here every headless render ran plain attention.
MACHINE = {"h3": {"attention": "kitchen", "chunk_ffn": True}}
route.settings.load = lambda: {**route.settings.DEFAULTS, "weights": STORED, "accel": MACHINE}
built = render(family="h3", prompt="a cat", accel={"chunk_ffn": False})
if "problem" in built:
    FAILURES.append(f"a render over the machine's row was refused: {built['problem']}")
else:
    _, _, blob = inputs(built)
    check("the machine's row rides on a headless render, a request's own over it",
          {k: blob["sampling"].get(k) for k in ("attention", "chunk_ffn")},
          {"attention": "kitchen", "chunk_ffn": False})
    check("beside the turbo switch's row rather than instead of it",
          blob["sampling"].get("steps"),
          headless.turbo_of(route.manifest.describe("h3"))["steps"]["medium"])
check("a request's attention is held to the row's own list",
      "attention" in render(family="h3", prompt="a cat", accel={"attention": "flash9"})
      .get("problem", ""), True)
check("and is refused on a still, where there is none to pick",
      "accel" in render(family="krea2", prompt="a cat", still=True,
                        accel={"attention": "sage"}).get("problem", ""), True)
route.settings.load = lambda: {**route.settings.DEFAULTS, "weights": STORED}

built = render(family="h3", prompt="a cat", fast=False)
_, _, blob = inputs(built)
check("fast: false is the native row, said so", (blob["loras"], built["speed"]), ([], "native"))

built = render(family="krea2", prompt="a tabby cat, studio portrait", aspect="4:5")
if "problem" in built:
    FAILURES.append(f"a Krea still was refused: {built['problem']}")
else:
    kind, _, blob = inputs(built)
    check("an image family is a still on the PreStage, on its turbo checkpoint",
          (kind, blob["arch"], blob["turbo"]["krea2"]["on"], blob["turbo"]["krea2"]["lora"]),
          ("MiniMaxH3PreStage", "krea2", True, None))

check("an unknown family is refused with the ones there are",
      "h3" in render(family="sora", prompt="x").get("problem", ""), True)
check("a still on H3 is pointed at the image families",
      "krea2" in render(family="h3", prompt="x", still=True).get("problem", ""), True)
check("a citation of a picture nobody sent is refused",
      "not in the ledger" in render(family="h3", prompt="@pic-2 runs").get("problem", ""), True)

# ---- a still's guide ----------------------------------------------------------
#
# `as: "guide"` is not a cited picture: it takes no @pic-N and lands on the blob
# as the pre-stage's Guide tool puts it, with the stop pressed beside it. The
# core probe is forced, as the graph suites force it: the local core may predate
# the Qwen Image 2.1 branch, and what is tested is the blob.
q21 = importlib.import_module(f"{PACKAGE}.creator.families.qwen21.still")
q21.control_supported = lambda: True
FILES["diffusion_models"].append("qwen_image_2.1_int8.safetensors")
FILES["text_encoders"].append("qwen3vl_8b.safetensors")
FILES["vae"].append("qwen_image_2.1_vae.safetensors")
FILES["model_patches"] = ["Qwen-Image-2.1-Fun-Controlnet-Union.safetensors"]
STORED["qwen21"] = {"model": "qwen_image_2.1_int8.safetensors", "clip": "qwen3vl_8b.safetensors",
                    "vae": "qwen_image_2.1_vae.safetensors",
                    "control": "Qwen-Image-2.1-Fun-Controlnet-Union.safetensors"}
built = render(family="qwen21", prompt="a castle like @pic-1", fast=False, guide_strength=0.8,
               pictures=["castle.png", {"filename": "edges.png", "as": "guide"}])
if "problem" in built:
    FAILURES.append(f"a guided Qwen Image 2.1 still was refused: {built['problem']}")
else:
    _, _, blob = inputs(built)
    check("the guide rides on the blob as the pre-stage's guide, after the cited picture",
          [(r["handle"], r["filename"], r.get("role")) for r in blob["refs"]],
          [("pic-1", "castle.png", None), ("guide", "edges.png", "guide")])
    check("...with the stop asked for", blob["guide"], {"strength": 0.8})
check("a guide on a family with no branch is refused",
      "nothing to read a guide" in render(family="krea2", prompt="x", still=True, pictures=[
          {"filename": "edges.png", "as": "guide"}]).get("problem", ""), True)
check("...and on a clip, for now",
      "a still's" in render(family="h3", prompt="x", pictures=[
          {"filename": "edges.png", "as": "guide"}]).get("problem", ""), True)

# ---- the caller's own LoRAs ----------------------------------------------------
built = render(family="qwen21", prompt="a dancer mid-leap", fast=False,
               loras=[{"name": "anna.safetensors", "strength": 0.7}])
if "problem" in built:
    FAILURES.append(f"a still with a LoRA was refused: {built['problem']}")
else:
    check("a requested LoRA is on the still's stack",
          [(e["name"], e["strength"]) for e in inputs(built)[2]["loras"]], [("anna.safetensors", 0.7)])
built = render(family="h3", prompt="a cat", loras=["anna.safetensors"])
if "problem" in built:
    FAILURES.append(f"a clip with a LoRA was refused: {built['problem']}")
else:
    check("...and on a clip it rides beside the turbo distill",
          [e["name"] for e in inputs(built)[2]["loras"]], ["anna.safetensors", FL2V])
check("a LoRA the machine does not have is refused with the near names",
      "did you mean anna.safetensors" in render(family="h3", prompt="a cat",
          loras=[{"name": "Anna"}]).get("problem", ""), True)

# ---- where a still lands -------------------------------------------------------
#
# Game Forge's shape: every picture a reference (`as: "ref"`), so the canvas is
# the aspect asked for rather than the first picture's, and an output prefix
# that puts the file in the take's folder.
outputs = importlib.import_module(f"{PACKAGE}.creator.outputs")
built = render(family="qwen21", prompt="a chest. Transparent background with alpha channel.", fast=False,
               aspect="4:5", short_edge=512, pictures=[{"filename": "look.png", "as": "ref"}],
               output_prefix="continuity/forge/keep/takes/chest/t1/chest")
if "problem" in built:
    FAILURES.append(f"a still with an output prefix was refused: {built['problem']}")
else:
    _, _, blob = inputs(built)
    check("the prefix is on the blob, where the save node reads it",
          outputs.image(blob, "elsewhere/x"), "continuity/forge/keep/takes/chest/t1/chest")
    check("a reference is not an edit: the canvas is the aspect asked for",
          (blob.get("edit_first"), blob.get("aspect")), (None, "4:5"))
check("a prefix that leaves the output folder is refused before anything is sampled",
      "'..' are not allowed" in render(family="qwen21", prompt="x", fast=False,
                                       output_prefix="../x/y").get("problem", ""), True)
check("...and a clip's is refused, for now",
      "a still" in render(family="h3", prompt="x", output_prefix="a/b").get("problem", ""), True)

route.server_routes._lora_names = lambda: []
check("fast with no distill on the machine refuses rather than rendering slow",
      "fast: false" in render(family="h3", prompt="a cat").get("problem", ""), True)

passed("a script's render request builds the node's own prompt")

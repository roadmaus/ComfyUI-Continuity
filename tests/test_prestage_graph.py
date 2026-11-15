"""What `MiniMaxH3PreStage.execute` wires up, for both architectures.

Same harness as `test_creator_graph.py`: nothing is sampled, the expansion is
inspected as a dict. The load-bearing cases are the two sampler shapes — Krea 2
through `KSampler`, Ideogram 4 through its own scheduler and the dual-model
guider — and that the graphs are taken from the official templates' wiring
rather than drifting toward each other.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_prestage_graph.py

Skips itself with a message if ComfyUI cannot be imported.
"""

import asyncio
import hashlib
import importlib
import math
import json
import os
import sys

# The checkout this file lives in *is* the package under test, so the import
# name is read off the directory rather than guessed — `__init__.py` imports
# relatively, which means it has to come in as a package under whatever name
# the clone was given.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.basename(ROOT)

# A stock install is one tree and `--base-directory` defaults to it. Point
# COMFYUI_PATH at the ComfyUI that actually runs, and set COMFYUI_BASE as well
# if the base directory is somewhere else (a Desktop install: it usually is).
COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
BASE = os.environ.get("COMFYUI_BASE", COMFY)


def _boot():
    sys.path.insert(0, COMFY)
    sys.argv = ["main.py", "--base-directory", BASE]
    import nodes
    import server

    loop = asyncio.new_event_loop()
    try:
        # Core 2026-09 hands the server an asset manager; older cores take none.
        from app.assets.manager import default_asset_manager
        server.PromptServer(loop, default_asset_manager())
    except (ImportError, TypeError):
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

# The pack imports *outside* the skip guard. A machine without ComfyUI is
# allowed to bow out; a pack that will not import is the exact failure the
# graph suites exist to catch, and for one afternoon a skip that swallowed it
# reported eight suites green on a branch whose node did not load.
package = importlib.import_module(PACKAGE)

ps = importlib.import_module(f"{PACKAGE}.creator.prestage")
ci = importlib.import_module(f"{PACKAGE}.creator.compile_image")
h3i = importlib.import_module(f"{PACKAGE}.creator.families.h3image.still")
k2 = importlib.import_module(f"{PACKAGE}.creator.families.krea2.still")
i4 = importlib.import_module(f"{PACKAGE}.creator.families.ideogram4.still")
outputs = importlib.import_module(f"{PACKAGE}.creator.outputs")

from harness import FAILURES, check


def expect_error(label, fn, fragment):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        if fragment not in str(exc):
            FAILURES.append(f"{label}: error {str(exc)!r} does not mention {fragment!r}")
    else:
        FAILURES.append(f"{label}: expected an error mentioning {fragment!r}, got none")


MODELS = {
    "krea2": {
        "model": "krea2_raw_bf16.safetensors",
        "turbo_model": "krea2_turbo_fp8_scaled.safetensors",
        "clip": "qwen3vl_4b_fp8_scaled.safetensors",
        "vae": "qwen_image_vae.safetensors",
    },
    "ideogram4": {
        "model": "ideogram4_fp8_scaled.safetensors",
        "uncond_model": "ideogram4_unconditional_fp8_scaled.safetensors",
        "clip": "qwen3vl_8b_fp8_scaled.safetensors",
        "vae": "flux2-vae.safetensors",
    },
}

NODE_ID = "9"


def blob(**overrides):
    data = {
        "version": 1,
        "arch": "krea2",
        "prompt": "a red room",
        "aspect": "16:9",
        "short_edge": 1024,
        "init": None,
        "refs": [],
        "loras": [],
        "turbo": {"on": False, "quality": "good", "saved": None},
        "quality": "default",
        "models": dict(MODELS),
    }
    data.update(overrides)
    return json.dumps(data)


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


def build(data=None, **overrides):
    kwargs = dict(prestage_data=data if data is not None else blob(),
                  seed=100, steps=52, cfg=3.5, sampler_name="euler", scheduler="simple")
    kwargs.update(overrides)
    return with_id(ps.MiniMaxH3PreStage, NODE_ID,
                   lambda: ps.MiniMaxH3PreStage.execute(**kwargs))


def by_class(graph):
    out = {}
    for node_id, node in graph.items():
        out.setdefault(node["class_type"], []).append((node_id, node["inputs"]))
    return out


def past_preview(kinds_, link):
    """The model link under the built-in preview, if `link` is one.

    Without KJNodes every sampler's model goes through `ContinuityPreview`
    (`livepreview.py`), which changes what it is handed by nothing but a
    wrapper. A check about the model chain steps over it.
    """
    for nid, inputs in kinds_.get("ContinuityPreview", []):
        if nid == link:
            return inputs["model"][0]
    return link


# ---- Krea 2 t2i --------------------------------------------------------------
#
# The template shape: loaders, one text encode, a zeroed negative, an empty
# 16-channel latent, one KSampler, one decode, one save. Nothing else.

out = build()
graph = out.expand
kinds = by_class(graph)

# Every node that writes a file is exported, so the executor holds this node
# uncached until each has succeeded: a save that failed, or a Cancel, must
# leave the next Run something to do. See `core.emit.expanded` (#97).
written = sorted((node_id, 0) for node_id, node in graph.items()
                 if node["class_type"] in ("MiniMaxH3SaveImage"))
check("expansion exports every node that writes a file",
      sorted(tuple(link) for link in out.result), written)
check("...and there is one", len(written) > 0, True)
check("one sampler", len(kinds["KSampler"]), 1)
check("one text encode", len(kinds["CLIPTextEncode"]), 1)
check("the negative is the prompt zeroed out", len(kinds["ConditioningZeroOut"]), 1)
check("an empty 16-channel latent", len(kinds["EmptySD3LatentImage"]), 1)
check("one decode", len(kinds["VAEDecode"]), 1)
for absent in ("LoadImage", "VAEEncode", "LoraLoaderModelOnly", "SamplerCustomAdvanced",
               "Ideogram4Scheduler", "TextEncodeQwenImageEditPlus"):
    check(f"no {absent} in a bare t2i render", absent in kinds, False)

# RAW's shift is the canvas-derived ramp, on every render rather than only the
# reference branch: core detects one arch for both checkpoint files and hands
# both of them Turbo's pin, so without this RAW samples on Turbo's schedule.
check("RAW carries the shift ramp",
      (kinds["ModelSamplingFlux"][0][1]["max_shift"],
       kinds["ModelSamplingFlux"][0][1]["base_shift"],
       kinds["ModelSamplingFlux"][0][1]["width"]),
      (k2.KREA_RAW_SHIFT["max_shift"], k2.KREA_RAW_SHIFT["base_shift"], 1824))
check("the sampler reads the shifted model",
      kinds["KSampler"][0][1]["model"][0], kinds["ModelSamplingFlux"][0][0])

check("the RAW checkpoint is loaded",
      [i["unet_name"] for _, i in kinds["UNETLoader"]], [MODELS["krea2"]["model"]])
check("the text encoder is loaded as Krea 2's",
      (kinds["CLIPLoader"][0][1]["clip_name"], kinds["CLIPLoader"][0][1]["type"]),
      (MODELS["krea2"]["clip"], "krea2"))
check("the VAE is the Qwen image VAE",
      [i["vae_name"] for _, i in kinds["VAELoader"]], [MODELS["krea2"]["vae"]])

sampler = kinds["KSampler"][0][1]
check("the sampler settings arrive verbatim",
      (sampler["seed"], sampler["steps"], sampler["cfg"], sampler["sampler_name"],
       sampler["scheduler"], sampler["denoise"]),
      (100, 52, 3.5, "euler", "simple", 1.0))

# 16:9 at a 1024 short edge on the /16 grid.
latent = kinds["EmptySD3LatentImage"][0][1]
check("the canvas follows the aspect pill on the /16 grid",
      (latent["width"] % 16, latent["height"], latent["width"] > latent["height"]),
      (0, 1024, True))

check("one save node", len(kinds["MiniMaxH3SaveImage"]), 1)
save_id, save_inputs = kinds["MiniMaxH3SaveImage"][0]
check("it is reported against the node that built it",
      graph[save_id].get("override_display_id"), NODE_ID)
check("it saves the decoded picture",
      graph[save_inputs["images"][0]]["class_type"], "VAEDecode")
check("it lands in this family's stills folder, which is its own",
      save_inputs["filename_prefix"], outputs.default_image("krea2", "Krea2"))


def save_prefix(**overrides):
    """Where a blob's still would land."""
    return by_class(build(blob(**overrides)).expand)["MiniMaxH3SaveImage"][0][1]["filename_prefix"]


# The blob decides where the file goes, and a blob that says nothing gets the
# family's own default above. This is the whole output-structure control: before
# it, the prefix was a module constant and every install on earth wrote every
# family's stills to one folder under one family's name.
check("a blob's own prefix is used instead",
      save_prefix(output_prefix="my-project/stills/take"), "my-project/stills/take")
check("a trailing slash means a folder, and keeps the family's stem",
      save_prefix(output_prefix="my-project/"), "my-project/Krea2")
check("an empty prefix falls back to the default rather than the output root",
      save_prefix(output_prefix="   "), outputs.default_image("krea2", "Krea2"))
# Refused while the graph is being built, *not* by get_save_image_path after the
# still has been sampled — which is the whole reason `outputs` exists rather
# than the save node just taking whatever it is handed.
expect_error("a prefix that climbs out of the output folder",
             lambda: save_prefix(output_prefix="../../H3"),
             "'.' and '..' are not allowed")
expect_error("an absolute prefix, pointed at the flag that does work",
             lambda: save_prefix(output_prefix="/mnt/big/stills"),
             "--output-directory")

# ---- turbo -------------------------------------------------------------------
#
# The pill swaps the checkpoint file; the sampler row it wrote arrives through
# the ordinary widgets. Nothing else about the graph may move.

turbo = by_class(build(blob(turbo={"on": True, "quality": "good", "saved": None}),
                       steps=8, cfg=1.0).expand)
# The flat block is what every blob written before the pill went per-arch
# carries, and Krea 2 is the only family that had one — so it still reads.
check("turbo loads the Turbo checkpoint",
      [i["unet_name"] for _, i in turbo["UNETLoader"]], [MODELS["krea2"]["turbo_model"]])
check("turbo changes nothing structural but the shift",
      sorted(turbo), sorted(k for k in kinds if k != "ModelSamplingFlux"))
check("turbo keeps the pin the checkpoint already detected, so emits no shift node",
      "ModelSamplingFlux" in turbo, False)
check("the pill's sampler row arrives verbatim",
      (turbo["KSampler"][0][1]["steps"], turbo["KSampler"][0][1]["cfg"]), (8, 1.0))

# ---- LoRAs and triggers ------------------------------------------------------

with_lora = by_class(build(blob(loras=[
    {"name": "krea2_darkbrush.safetensors", "strength": 0.8,
     "triggers": ["monochrome ink wash style"]},
    {"name": "off.safetensors", "strength": 1.0, "enabled": False},
])).expand)
loras = with_lora["LoraLoaderModelOnly"]
check("one LoRA patch — the disabled one is skipped", len(loras), 1)
check("model-only, at the entry's strength",
      (loras[0][1]["lora_name"], loras[0][1]["strength_model"]),
      ("krea2_darkbrush.safetensors", 0.8))
check("the shift reads the patch, and the sampler reads the shift",
      (past_preview(with_lora, with_lora["ModelSamplingFlux"][0][1]["model"][0]),
       with_lora["KSampler"][0][1]["model"][0]),
      (loras[0][0], with_lora["ModelSamplingFlux"][0][0]))
check("the trigger word rides in front of the prompt",
      with_lora["CLIPTextEncode"][0][1]["text"],
      "monochrome ink wash style, a red room")

# ---- img2img -----------------------------------------------------------------
#
# An init image replaces the empty latent with an encode of the scaled source,
# and the KSampler's denoise becomes the entry's strength. (The adaptive-aspect
# half of img2img reads the file's size and is compile-time tested elsewhere —
# here the file does not exist, so the blob is compiled with the aspect pill.)

init_payload = ci.compile_prestage(
    {"arch": "krea2", "prompt": "p", "init": {"filename": "seed.png", "denoise": 0.6},
     "aspect": "1:1", "short_edge": 1024}, k2)
check("the payload carries the init", init_payload.init,
      {"filename": "seed.png", "denoise": 0.6})

sampling_mod = importlib.import_module(f"{PACKAGE}.creator.sampling")
ri = importlib.import_module(f"{PACKAGE}.creator.render_image")

i2i_graph = ri.emit(init_payload, ri.ImageWeights(arch="krea2", files=MODELS["krea2"]),
                    sampling_mod.Sampling(seed=1, steps=52, cfg=3.5,
                                        sampler_name="euler", scheduler="simple"),
                    NODE_ID, k2)
i2i = by_class(i2i_graph.finalize())
check("the init is loaded and encoded",
      ("LoadImage" in i2i, "VAEEncode" in i2i, "EmptySD3LatentImage" in i2i),
      (True, True, False))
check("scaled to the resolved canvas first",
      i2i["ImageScale"][0][1]["upscale_method"], "lanczos")
check("the sampler starts from the encode at the entry's strength",
      i2i["KSampler"][0][1]["denoise"], 0.6)

# ---- references (Krea 2) ------------------------------------------------------
#
# The Krea 2 Edit V2 LoRAs' own conditioning, from the vendored Krea2Edit nodes:
# the pictures laid into the model as clean frames fitted to the latent the
# sampler starts from, and the instruction read with them in view. Neither
# appears without refs, and core's Qwen-edit encoder appears nowhere.

IDENTITY = {"name": "krea2_identity_edit_v2.safetensors", "strength": 1.0}
GENERAL = {"name": "krea2_general_edit_v2.safetensors", "strength": 1.0}


def refs_blob(**overrides):
    data = {"arch": "krea2", "prompt": "p", "aspect": "1:1", "short_edge": 1024,
            "refs": [{"filename": "a.png"}, {"filename": "b.png"}],
            "loras": [dict(IDENTITY)], "ref_lora": IDENTITY["name"]}
    data.update(overrides)
    return data


def refs_graph(data=None, **row):
    settings = dict(seed=0, steps=20, cfg=1.0, sampler_name="euler", scheduler="simple")
    settings.update(row)
    return by_class(ri.emit(ci.compile_prestage(data if data is not None else refs_blob(), k2),
                            ri.ImageWeights(arch="krea2", files=MODELS["krea2"]),
                            sampling_mod.Sampling(**settings), NODE_ID, k2).finalize())


refs = refs_graph()
check("the vendored nodes are what the graph builds",
      ("ContinuityKrea2EditPatch" in refs, "ContinuityKrea2EditEncode" in refs), (True, True))
_listed = asyncio.new_event_loop().run_until_complete(
    importlib.import_module(f"{PACKAGE}.creator.creator_node").MiniMaxCreatorExtension().get_node_list())
check("...and both are in the pack's node list",
      {"ContinuityKrea2EditPatch", "ContinuityKrea2EditEncode"}
      <= {node.define_schema().node_id for node in _listed}, True)
check("core's Qwen-edit encoder and the layout node are gone",
      ("TextEncodeQwenImageEditPlus" in refs, "FluxKontextMultiReferenceLatentMethod" in refs),
      (False, False))
patch = refs["ContinuityKrea2EditPatch"][0]
encode = refs["ContinuityKrea2EditEncode"][0][1]
loads = {nid: i["image"] for nid, i in refs["LoadImage"]}
check("the scene is the first picture and the subject the second, in both halves",
      ([loads[patch[1]["image"][0]], loads[patch[1]["image_b"][0]]],
       [loads[encode["image"][0]], loads[encode["image_b"][0]]]),
      (["a.png", "b.png"], ["a.png", "b.png"]))
check("the patch is handed the latent the sampler starts from",
      patch[1]["target"], refs["KSampler"][0][1]["latent_image"])
check("...and the sampler reads the patched model",
      refs["KSampler"][0][1]["model"][0], patch[0])
check("...over the RAW ramp, which wraps it",
      patch[1]["model"][0], refs["ModelSamplingFlux"][0][0])
check("the encode sees the pictures at the card's grounding size",
      encode["grounding_px"], k2.GROUNDING_PX)
check("Identity Edit with a scene: the card's composite dials",
      {k: patch[1][k] for k in ("boost", "boost_a", "place", "place_a")},
      {"boost": 2.5, "boost_a": 1.0, "place": "beside", "place_a": "aligned"})
check("no plain text encode on the reference branch", "CLIPTextEncode" in refs, False)
check("the reference branch samples on the same RAW ramp as t2i",
      (refs["ModelSamplingFlux"][0][1]["max_shift"], refs["ModelSamplingFlux"][0][1]["base_shift"]),
      (k2.KREA_RAW_SHIFT["max_shift"], k2.KREA_RAW_SHIFT["base_shift"]))

one = refs_graph(refs_blob(refs=[{"filename": "her.png"}]))
check("one picture is the only slot",
      "image_b" in one["ContinuityKrea2EditPatch"][0][1], False)
check("...restaged at the card's single-reference dials",
      {k: one["ContinuityKrea2EditPatch"][0][1][k] for k in ("boost", "place")},
      {"boost": 2.0, "place": "beside"})

edited = refs_graph(refs_blob(refs=[{"filename": "street.png"}],
                              loras=[dict(GENERAL)], ref_lora=GENERAL["name"]))
check("General Edit keeps the layout at boost 4",
      {k: edited["ContinuityKrea2EditPatch"][0][1][k] for k in ("boost", "place")},
      {"boost": 4.0, "place": "aligned"})
dialled = refs_graph(refs_blob(ref_boost=1.5, ref_place="aligned"))
check("a dial somebody set beats the LoRA's default",
      {k: dialled["ContinuityKrea2EditPatch"][0][1][k] for k in ("boost", "place")},
      {"boost": 1.5, "place": "aligned"})
check("...and leaves the scene's alone",
      {k: dialled["ContinuityKrea2EditPatch"][0][1][k] for k in ("boost_a", "place_a")},
      {"boost_a": 1.0, "place_a": "aligned"})
expect_error("an unknown placement is refused by name",
             lambda: ci.compile_prestage(refs_blob(ref_place="bag"), k2), "bag")
expect_error("a likeness off the dial is refused",
             lambda: ci.compile_prestage(refs_blob(ref_boost=50), k2), "likeness")
check("a blob saved with the retired layout field still compiles",
      ci.compile_prestage(refs_blob(ref_method="index_timestep_zero"), k2).refs,
      ["a.png", "b.png"])

# Every way of reading a reference on this model is a LoRA, so an empty stack
# is not a weaker render, it is the images going nowhere.
expect_error("references with no adapter in the stack are refused",
             lambda: ci.compile_prestage(refs_blob(loras=[], ref_lora=None), k2),
             "only through a Krea 2 Edit LoRA")
expect_error("...and a muted adapter counts as no adapter",
             lambda: ci.compile_prestage(refs_blob(
                 loras=[{**IDENTITY, "enabled": False}]), k2),
             "not in this render's LoRA stack")
# And the adapter is named rather than counted: a stack holding a style LoRA and
# nothing that reads references is the same silent failure as an empty one.
expect_error("a stack with no *reference* adapter in it is refused",
             lambda: ci.compile_prestage(refs_blob(
                 loras=[{"name": "some_painting_style.safetensors", "strength": 1.0}],
                 ref_lora=None), k2),
             "only through a Krea 2 Edit LoRA")
expect_error("...and an adapter named but never added is refused by name",
             lambda: ci.compile_prestage(refs_blob(
                 loras=[{"name": "some_painting_style.safetensors", "strength": 1.0}]), k2),
             IDENTITY["name"])
expect_error("a LoRA named as the adapter that is not one of the pair is refused",
             lambda: ci.compile_prestage(refs_blob(
                 loras=[{"name": "krea2_style_reference.safetensors", "strength": 1.0}],
                 ref_lora="krea2_style_reference.safetensors"), k2),
             "not a Krea 2 Edit LoRA")
expect_error("v1 weights, trained on the older geometry, are refused",
             lambda: ci.compile_prestage(refs_blob(
                 loras=[{"name": "krea2_identity_edit_v1_1.safetensors", "strength": 1.0}],
                 ref_lora="krea2_identity_edit_v1_1.safetensors"), k2),
             "older reference geometry")
check("...while v1.2 and the rank-reduced V2 cuts read",
      [ci.compile_prestage(refs_blob(loras=[{"name": name, "strength": 1.0}], ref_lora=name),
                           k2).arch
       for name in ("krea2_identity_edit_v1_2.safetensors",
                    "krea2_general_edit_v2_r64.safetensors")],
      ["krea2", "krea2"])
check("a stack that carries the adapter unnamed alongside others is fine",
      ci.compile_prestage(refs_blob(ref_lora=None, loras=[
          {"name": "some_painting_style.safetensors", "strength": 0.6},
          dict(IDENTITY)]), k2).refs, ["a.png", "b.png"])
expect_error("both edit LoRAs at full strength render noise, so are refused",
             lambda: ci.compile_prestage(refs_blob(loras=[dict(IDENTITY), dict(GENERAL)]), k2),
             "share a lineage")
check("...while about 0.6 each is the card's way to have both",
      ci.compile_prestage(refs_blob(loras=[{**IDENTITY, "strength": 0.6},
                                           {**GENERAL, "strength": 0.6}]), k2).arch, "krea2")

expect_error("a third picture is refused",
             lambda: ci.compile_prestage(
                 refs_blob(refs=["a.png", "b.png", "c.png"]), k2),
             "a scene and a subject")
expect_error("a canvas past the 2 MP the LoRAs were trained to is refused",
             lambda: ci.compile_prestage(refs_blob(short_edge=1536), k2), "2 MP")
check("...while the same canvas without references is not",
      ci.compile_prestage(refs_blob(short_edge=1536, refs=[]), k2).width, 1536)

check("a cited picture is written the way the card writes it",
      ci.compile_prestage(refs_blob(
          prompt="put the woman from @ref-2 into @ref-1",
          refs=[{"filename": "room.png", "handle": "ref-1"},
                {"filename": "her.png", "handle": "ref-2"}]), k2).prompt,
      "put the woman from image 2 into image 1")

# The unconditional a reference render is guided against is the same pictures
# with nothing asked of them — the card's "ground the negative too".
guided = refs_graph(cfg=3.0)
check("at real CFG the negative is a second grounded encode",
      len(guided["ContinuityKrea2EditEncode"]), 2)
check("...over the same pictures, with nothing asked of them",
      sorted(i["prompt"] for _, i in guided["ContinuityKrea2EditEncode"]), ["", "p"])
check("...and nothing is zeroed", "ConditioningZeroOut" in guided, False)
check("at cfg 1 the negative is never evaluated, so it is not paid for",
      (len(refs["ContinuityKrea2EditEncode"]), "ConditioningZeroOut" in refs),
      (1, True))

# General Edit is an editor: asked to, its first picture is the one changed,
# so it is the canvas and the latent the patch fits the pictures to.
inplace = ci.compile_prestage(refs_blob(refs=[{"filename": "street.png"}],
                                        loras=[dict(GENERAL)], ref_lora=GENERAL["name"],
                                        edit_first=True), k2, lambda name: (1920, 1080))
check("edit in place starts from the picture, at full denoise",
      inplace.init, {"filename": "street.png", "denoise": 1.0})
check("...on a canvas the picture's shape",
      inplace.width > inplace.height, True)

# Removal is the one edit the distilled checkpoint cannot do: at cfg 1 there is
# no guidance to push against the reference, so Turbo re-draws what it was asked
# to delete. A routing rule, not a tuning preference.
TURBO_ON = {"krea2": {"on": True}}
expect_error("a removal asked of the distilled row is refused",
             lambda: ci.compile_prestage(
                 refs_blob(prompt="remove the car from the driveway",
                           turbo=TURBO_ON), k2),
             "re-renders the subject instead of deleting it")
check("...while every other edit the distillation covers goes through",
      ci.compile_prestage(refs_blob(prompt="recolour the car red",
                                    turbo=TURBO_ON), k2).checkpoint_field,
      "turbo_model")
check("...and the same removal on RAW is what the rule points at",
      ci.compile_prestage(refs_blob(prompt="remove the car"), k2).checkpoint_field,
      "model")
check("a word that merely contains one is not a removal",
      ci.compile_prestage(refs_blob(prompt="a removable panel on a remote cabin",
                                    turbo=TURBO_ON), k2).arch, "krea2")

# ---- turbo as a LoRA (Krea 2) ------------------------------------------------
#
# The distillation ships twice: as its own checkpoint, and as an SVD extraction
# of the same weight difference. With the LoRA picked the DiT stays RAW and the
# stack does the distilling — which is what keeps one file resident across a
# flick of the pill and lets a content LoRA ride along.

turbo_lora = "krea2_turbo_distill.safetensors"
by_lora = by_class(build(blob(
    turbo={"krea2": {"on": True, "quality": "good", "saved": None, "lora": turbo_lora}},
    loras=[{"name": turbo_lora, "strength": 1.0}]), steps=8, cfg=1.0).expand)
check("the LoRA route keeps RAW loaded",
      [i["unet_name"] for _, i in by_lora["UNETLoader"]], [MODELS["krea2"]["model"]])
check("...and patches the distillation over it",
      by_lora["LoraLoaderModelOnly"][0][1]["lora_name"], turbo_lora)
check("...on the schedule the distillation was fitted to, not RAW's ramp",
      "ModelSamplingFlux" in by_lora, False)

# ---- Ideogram 4 --------------------------------------------------------------
#
# The other sampler shape: its own scheduler's sigmas, SamplerCustomAdvanced,
# and the dual-model guider with the late-cfg drop on the conditional branch.

ideo = by_class(build(blob(arch="ideogram4"), steps=20, cfg=7.0).expand)
check("Ideogram samples through the custom path",
      ("SamplerCustomAdvanced" in ideo, "KSampler" in ideo), (True, False))
check("on its own schedule",
      (ideo["Ideogram4Scheduler"][0][1]["steps"], ideo["Ideogram4Scheduler"][0][1]["mu"],
       ideo["Ideogram4Scheduler"][0][1]["std"]),
      (20, 0.0, 1.75))
check("the latent is Flux2's", "EmptyFlux2LatentImage" in ideo, True)
check("both checkpoints load — the unconditional branch is a separate model",
      sorted(i["unet_name"] for _, i in ideo["UNETLoader"]),
      sorted([MODELS["ideogram4"]["model"], MODELS["ideogram4"]["uncond_model"]]))
guider = ideo["DualModelGuider"][0][1]
check("the guider runs at the widget's cfg", guider["cfg"], 7.0)
override = ideo["CFGOverride"][0]
check("the conditional branch carries the polish drop",
      (override[1]["cfg"], override[1]["end_percent"]), (3.0, 1.0))
check("...and the guider reads it as its conditional model",
      guider["model"][0], override[0])
check("the text encoder is loaded as Ideogram's",
      ideo["CLIPLoader"][0][1]["type"], "ideogram4")

# The prompt is the model's JSON caption, not the prose — Ideogram's guide says
# a plain line "will not work" and trips the safety filter; a caption the user
# wrote themselves keeps every word, put in the trained key order and minified.
caption = json.loads(ideo["CLIPTextEncode"][0][1]["text"])
check("the prose is wrapped into the caption schema",
      (caption["high_level_description"],
       caption["compositional_deconstruction"]["background"],
       caption["compositional_deconstruction"]["elements"][0]),
      ("a red room", "a red room", {"type": "obj", "desc": "a red room"}))
own = '{"compositional_deconstruction": {"elements": [], "background": "a red room"}}'
check("a caption already in the schema keeps its words, in the trained order",
      by_class(build(blob(arch="ideogram4", prompt=own)).expand)["CLIPTextEncode"][0][1]["text"],
      '{"compositional_deconstruction":{"background":"a red room","elements":[]}}')
with_trigger = by_class(build(blob(arch="ideogram4", loras=[
    {"name": "ideogram_realism.safetensors", "strength": 0.9, "triggers": ["realism engine"]}])).expand)
check("a trigger word lands inside the caption",
      json.loads(with_trigger["CLIPTextEncode"][0][1]["text"])["high_level_description"],
      "realism engine, a red room")

# A LoRA over Ideogram is two patches — one per checkpoint, each at its own
# weight: the conditional side at `strength`, the unconditional at `uncond`.
paired = by_class(build(blob(arch="ideogram4", loras=[
    {"name": "ideogram_realism.safetensors", "strength": 0.9, "uncond": 0.4}])).expand)
patches = {i["strength_model"]: nid for nid, i in paired["LoraLoaderModelOnly"]}
check("two patches of the same file", sorted(patches), [0.4, 0.9])
check("the conditional patch feeds the shift",
      past_preview(paired, paired["ModelSamplingAuraFlow"][0][1]["model"][0]),
      patches[0.9])
check("the unconditional patch is the guider's negative model",
      paired["DualModelGuider"][0][1]["model_negative"][0], patches[0.4])
check("the unconditional patch sits on the unconditional checkpoint",
      next(i["unet_name"] for nid, i in paired["UNETLoader"]
           if nid == next(i["model"][0] for n, i in paired["LoraLoaderModelOnly"] if n == patches[0.4])),
      MODELS["ideogram4"]["uncond_model"])
same = by_class(build(blob(arch="ideogram4", loras=[
    {"name": "ideogram_realism.safetensors", "strength": 0.7}])).expand)
check("no uncond weight means the same weight on both",
      sorted(i["strength_model"] for _, i in same["LoraLoaderModelOnly"]), [0.7, 0.7])
off = by_class(build(blob(arch="ideogram4", loras=[
    {"name": "ideogram_realism.safetensors", "strength": 0.7, "uncond": 0}])).expand)
check("an uncond weight of zero leaves that branch bare",
      ([i["strength_model"] for _, i in off["LoraLoaderModelOnly"]],
       off["DualModelGuider"][0][1]["model_negative"][0] in {n for n, _ in off["UNETLoader"]}),
      ([0.7], True))

# The step count is the preset's, never the row's: a stale `sampling.steps`
# on the blob (12, under an older preset table) queued 12 steps under a pill
# reading "turbo · 18" — the frame Felix brought in on 2026-09-20.
stale = by_class(build(blob(arch="ideogram4", quality="turbo",
                            sampling={"steps": 12, "cfg": 7.0, "sampler_name": "euler"}),
                       steps=52).expand)
check("the preset's steps win over a stale row and the widget",
      stale["Ideogram4Scheduler"][0][1]["steps"], i4.IDEOGRAM_QUALITIES["turbo"]["steps"])
# ...and the same blob's other stale number, cfg 1 with the turbo pill off, is
# refused rather than sampled into an unguided, murky frame.
expect_error("cfg 1 without the turbo LoRA is refused by name",
             lambda: build(blob(arch="ideogram4",
                                sampling={"steps": 12, "cfg": 1.0, "sampler_name": "euler"})),
             "without guidance")

# The quality preset owns mu/std, not the user.
quality = by_class(build(blob(arch="ideogram4", quality="quality"), steps=48).expand)
check("the quality preset reshapes the schedule",
      (quality["Ideogram4Scheduler"][0][1]["mu"], quality["Ideogram4Scheduler"][0][1]["std"]),
      (0.0, 1.5))

# ---- the sampler row is the measured one, not the template's ---------------
#
# The conditional branch runs behind ModelSamplingAuraFlow at shift 5 and the
# polish tail starts at a fixed percent through that same patch; the
# unconditional checkpoint is loaded bare. res_2m is the row's sampler.

shifted = ideo["ModelSamplingAuraFlow"][0]
check("the conditional branch is shifted", shifted[1]["shift"], i4.IDEOGRAM_SHIFT)
check("...under the polish override", override[1]["model"][0], shifted[0])
check("the polish tail starts at the fixed percent",
      override[1]["start_percent"], i4.IDEOGRAM_POLISH_START)
uncond_id = next(nid for nid, i in ideo["UNETLoader"]
                 if i["unet_name"] == MODELS["ideogram4"]["uncond_model"])
check("the unconditional branch is the bare checkpoint",
      guider["model_negative"][0], uncond_id)
ideo_manifest = importlib.import_module(f"{PACKAGE}.creator.families.ideogram4.manifest").manifest()
check("the manifest's sampler default is res_2m",
      next(w["default"] for w in ideo_manifest["widgets"] if w["id"] == "sampler_name"),
      "res_2m")
check("the default preset is Turbo at 18 steps",
      (i4.DEFAULT_IDEOGRAM_QUALITY, i4.IDEOGRAM_QUALITIES["turbo"]["steps"]),
      ("turbo", 18))

check("the mirrored schedule matches core's own",
      [round(v, 6) for v in i4.sigmas(12, 1024, 1024, 0.5, 1.75)],
      [round(float(v), 6) for v in
       importlib.import_module("comfy_extras.nodes_ideogram4")
       .ideogram4_sigmas(12, 1024, 1024, 0.5, 1.75)])

# ---- turbo as a LoRA (Ideogram 4) --------------------------------------------
#
# Ideogram ships no distilled checkpoint — the presets *are* its official fast
# path — so this pill is a LoRA or it is nothing. Thrown on it also sheds the
# two pieces of cfg machinery a run at cfg 1 has no use for: the 9.3B
# unconditional file, and the polish tail's guidance drop.

ideo_turbo_lora = "ideogram4_turbotime.safetensors"
ideo_turbo = by_class(build(blob(
    arch="ideogram4",
    turbo={"ideogram4": {"on": True, "quality": "medium", "saved": None,
                         "lora": ideo_turbo_lora}},
    loras=[{"name": ideo_turbo_lora, "strength": 1.0}]), steps=4, cfg=1.0).expand)
check("turbo patches the distillation over the one checkpoint",
      ([i["unet_name"] for _, i in ideo_turbo["UNETLoader"]],
       ideo_turbo["LoraLoaderModelOnly"][0][1]["lora_name"]),
      ([MODELS["ideogram4"]["model"]], ideo_turbo_lora))
check("the unconditional branch is not loaded at all",
      "model_negative" in ideo_turbo["DualModelGuider"][0][1], False)
check("and the polish tail is gone with the guidance it dropped",
      "CFGOverride" in ideo_turbo, False)
check("...and so is the shift, which only ever placed that tail",
      "ModelSamplingAuraFlow" in ideo_turbo, False)
check("the pill opens on TurboTime's author's row: 8 steps, 0.6, euler, cfg 1",
      (i4.DEFAULT_TURBO_QUALITY, i4.TURBO_STEPS[i4.DEFAULT_TURBO_QUALITY],
       i4.DEFAULT_TURBO_STRENGTH, i4.TURBO_ROW),
      ("good", 8, 0.6, {"cfg": 1.0, "sampler_name": "euler"}))
check("the schedule is the Turbo preset's, which is shaped for a short run",
      (ideo_turbo["Ideogram4Scheduler"][0][1]["mu"],
       ideo_turbo["Ideogram4Scheduler"][0][1]["std"],
       ideo_turbo["Ideogram4Scheduler"][0][1]["steps"]),
      (i4.IDEOGRAM_QUALITIES["turbo"]["mu"], i4.IDEOGRAM_QUALITIES["turbo"]["std"],
       i4.TURBO_STEPS["medium"]))
check("...at the turbo pill's own step count, whatever the row says",
      by_class(build(blob(
          arch="ideogram4",
          turbo={"ideogram4": {"on": True, "quality": "good", "saved": None,
                               "lora": ideo_turbo_lora}},
          loras=[{"name": ideo_turbo_lora, "strength": 1.0}]), steps=52, cfg=1.0)
          .expand)["Ideogram4Scheduler"][0][1]["steps"],
      i4.TURBO_STEPS["good"])
expect_error("turbo with no LoRA picked is refused, not sampled undistilled",
             lambda: build(blob(arch="ideogram4",
                                turbo={"ideogram4": {"on": True, "quality": "medium"}})),
             "no distilled checkpoint")
check("Krea's pill does not reach across the arch split",
      "LoraLoaderModelOnly" in by_class(build(blob(
          arch="ideogram4",
          turbo={"krea2": {"on": True, "quality": "good", "lora": "k.safetensors"}},
      )).expand), False)

# Without the unconditional file the guider degrades to ordinary CFG — the
# node's own documented behaviour — rather than refusing.
one_model = dict(MODELS["ideogram4"])
del one_model["uncond_model"]
single = by_class(build(blob(arch="ideogram4",
                             models={**MODELS, "ideogram4": one_model})).expand)
check("one checkpoint is ordinary CFG, not an error",
      ("model_negative" in single["DualModelGuider"][0][1],
       len(single["UNETLoader"])),
      (False, 1))

# Ideogram i2i truncates the schedule instead of using a denoise widget.
ideo_i2i_payload = ci.compile_prestage(
    {"arch": "ideogram4", "prompt": "p", "init": {"filename": "seed.png", "denoise": 0.5},
     "aspect": "1:1", "short_edge": 1024}, i4)
ideo_i2i = by_class(ri.emit(ideo_i2i_payload,
                            ri.ImageWeights(arch="ideogram4", files=MODELS["ideogram4"]),
                            sampling_mod.Sampling(steps=20, cfg=7.0, sampler_name="euler"),
                            NODE_ID, i4).finalize())
check("i2i keeps the tail of the sigmas",
      ideo_i2i["SplitSigmasDenoise"][0][1]["denoise"], 0.5)
check("the sampler reads the truncated schedule",
      ideo_i2i["SamplerCustomAdvanced"][0][1]["sigmas"][0],
      ideo_i2i["SplitSigmasDenoise"][0][0])

# ---- Qwen Image Edit ---------------------------------------------------------
#
# The one family whose subject is a picture that already exists. The shipped
# workflow's chain — AuraFlow shift, CFG-norm, the edit encoder twice over the
# same images, and the first picture straight into the sampler as the latent —
# and the promotion that makes the last of those true without a second image
# field: `Picture 1` is the thing being changed, so it is also the init.

qe = importlib.import_module(f"{PACKAGE}.creator.families.qwenedit.still")
MODELS["qwenedit"] = {
    "model": "qwen_image_edit_2511_fp8mixed.safetensors",
    "clip": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
    "vae": "qwen_image_vae.safetensors",
}
QE_WEIGHTS = ri.ImageWeights(arch="qwenedit", files=MODELS["qwenedit"])


def edit_blob(**overrides):
    data = {"arch": "qwenedit", "prompt": "put her in the red coat", "aspect": "1:1",
            "short_edge": 1024,
            "refs": [{"filename": "her.png"}, {"filename": "coat.png"}], "loras": []}
    data.update(overrides)
    return data


def edit_graph(data=None, **row):
    settings = dict(seed=7, steps=20, cfg=4.0, sampler_name="euler", scheduler="simple")
    settings.update(row)
    payload = ci.compile_prestage(data if data is not None else edit_blob(), qe)
    return payload, by_class(ri.emit(payload, QE_WEIGHTS,
                                     sampling_mod.Sampling(**settings),
                                     NODE_ID, qe).finalize())

# `edit_first` on: the first picture is the one edited in place. The bare blob
# below — the default — reads its pictures as references beside a new picture.
edit_payload, edit = edit_graph(edit_blob(edit_first=True))

check("the schedule shift core does not detect is put back",
      edit["ModelSamplingAuraFlow"][0][1]["shift"], qe.AURAFLOW_SHIFT)
check("...and the guided prediction is normed on top of it",
      edit["CFGNorm"][0][1]["model"][0], edit["ModelSamplingAuraFlow"][0][0])
check("the sampler reads the normed model",
      edit["KSampler"][0][1]["model"][0], edit["CFGNorm"][0][0])
check("the text encoder is loaded as Qwen's",
      edit["CLIPLoader"][0][1]["type"], "qwen_image")

# Two passes of the same encoder over the same pictures. Zeroing the positive
# keeps the reference latents — `ConditioningZeroOut` copies the conditioning
# dict — but hands the model a text stream of zeros in place of the encoder's
# reading of the pictures, which is not the unconditional this post-training was
# fitted against.
check("the positive and the negative are both edit encodes",
      len(edit["TextEncodeQwenImageEditPlus"]), 2)
prompts = sorted(i["prompt"] for _, i in edit["TextEncodeQwenImageEditPlus"])
check("...the negative being the same images with nothing asked of them",
      prompts, ["", "put her in the red coat"])
check("no zeroed conditioning at real CFG", "ConditioningZeroOut" in edit, False)
for _, inputs in edit["TextEncodeQwenImageEditPlus"]:
    check("both encodes hold both pictures",
          ("image1" in inputs, "image2" in inputs, "image3" in inputs),
          (True, True, False))

# Asked to edit the first picture in place, it is promoted to the init at a
# denoise of 1.0, which is the published workflow's latent exactly.
check("the first picture becomes the render's own starting point",
      edit_payload.init, {"filename": "her.png", "denoise": 1.0})
check("...encoded into the latent rather than an empty canvas",
      ("VAEEncode" in edit, "EmptySD3LatentImage" in edit), (True, False))
check("...at full denoise, because the instruction arrives as conditioning",
      edit["KSampler"][0][1]["denoise"], 1.0)

# And the canvas follows it, the way an init image's always has.
sized_payload = ci.compile_prestage(edit_blob(edit_first=True), qe, lambda name: (1920, 1080))
check("the canvas takes the edited picture's shape",
      (sized_payload.width > sized_payload.height, sized_payload.height), (True, 1024))
# And the default, with nothing asked: the pictures are references. These are
# Qwen-Image weights post-trained, not replaced, so "here are two pictures,
# now draw a third" is the render they do natively — and attaching a picture
# must not silently turn the render into an edit of it.
blank_payload, blank = edit_graph(edit_blob())
check("an attached picture is a reference, not the subject, until asked",
      blank_payload.init, None)
check("...so the render draws onto an empty canvas",
      ("EmptySD3LatentImage" in blank, "VAEEncode" in blank), (True, False))
check("...at the aspect the pill asked for, not the picture's",
      (blank_payload.width, blank_payload.height), (1024, 1024))
check("...while both pictures are still read and still cited",
      ("image1" in blank["TextEncodeQwenImageEditPlus"][0][1],
       "image2" in blank["TextEncodeQwenImageEditPlus"][0][1]),
      (True, True))
check("an explicit init beats the flag, since it is the only partial denoise",
      ci.compile_prestage(edit_blob(edit_first=True,
                                    init={"filename": "plate.png", "denoise": 0.4}),
                          qe).init,
      {"filename": "plate.png", "denoise": 0.4})
check("Krea 2 edits in place too, now that General Edit reads its pictures",
      ci.compile_prestage(refs_blob(edit_first=True), k2).init,
      {"filename": "a.png", "denoise": 1.0})
check("the retired start_blank field is not read — its default is this one",
      ci.compile_prestage(edit_blob(start_blank=False), qe).init, None)

check("an explicit init still wins — the only way to ask for a partial denoise",
      ci.compile_prestage(edit_blob(init={"filename": "plate.png", "denoise": 0.4}),
                          qe).init,
      {"filename": "plate.png", "denoise": 0.4})

# At cfg 1 the sampler never evaluates the negative, and a second 7B encoder
# pass to build a tensor nothing reads is most of a four-step render.
_, distilled = edit_graph(edit_blob(
    turbo={"qwenedit": {"on": True, "lora": "qwen_edit_lightning_4step.safetensors"}},
    loras=[{"name": "qwen_edit_lightning_4step.safetensors", "strength": 1.0}]),
    steps=4, cfg=1.0)
check("a distilled run does not pay for an unconditional it cannot use",
      (len(distilled["TextEncodeQwenImageEditPlus"]), "ConditioningZeroOut" in distilled),
      (1, True))
check("...and the Lightning LoRA is patched model-only, like every image LoRA",
      distilled["LoraLoaderModelOnly"][0][1]["lora_name"],
      "qwen_edit_lightning_4step.safetensors")

# An edit model asked to draw from nothing is a legitimate request, and takes
# the plain text encoder: with no images the edit encoder's only contribution is
# a system prompt about an input picture there isn't one of.
_, bare = edit_graph(edit_blob(refs=[]))
check("with no pictures it is an ordinary text-to-image render",
      ("CLIPTextEncode" in bare, "TextEncodeQwenImageEditPlus" in bare,
       "EmptySD3LatentImage" in bare),
      (True, False, True))

expect_error("turbo with no Lightning LoRA picked is refused",
             lambda: ci.compile_prestage(
                 edit_blob(turbo={"qwenedit": {"on": True}}), qe),
             "Lightning LoRA")
expect_error("a fourth picture is refused here too",
             lambda: ci.compile_prestage(edit_blob(
                 refs=["a.png", "b.png", "c.png", "d.png"]), qe),
             "three image slots")

# ...but three is the 2509/2511 number, not the encoder's last word. The first
# Qwen-Image-Edit weights were post-trained on one picture, and nothing in the
# file says which release it is — so the edition is declared and the cap follows
# it rather than the three slots the node happens to have.
check("the edition defaults to the one most people are running",
      qe.edition(edit_blob()), "2511")
check("...and 2509 reads three pictures just as 2511 does",
      ci.compile_prestage(edit_blob(edition="2509"), qe).refs, ["her.png", "coat.png"])
expect_error("a second picture on the base weights is refused",
             lambda: ci.compile_prestage(edit_blob(edition="base"), qe),
             "post-trained on a single picture")
check("...while one picture on them is the render they can do",
      ci.compile_prestage(edit_blob(edition="base", refs=["her.png"]), qe).refs,
      ["her.png"])
# The built-in ControlNet, which is the one part of these weights with no node
# behind it: 2509 and 2511 follow a depth, edge or pose map arriving in an
# ordinary image slot, so the guide is Picture N and the graph is the graph a
# reference render already emits. What the pack has to get right is the slot —
# and that the edition in front of it learned to read one.
GUIDE = [{"handle": "img-1", "filename": "depth.png", "role": "guide"}]
check("a guide is wired exactly as any other picture is",
      ci.compile_prestage(edit_blob(refs=GUIDE), qe).refs, ["depth.png"])
check("...and the canvas is the aspect pill's, as for any reference",
      ci.compile_prestage(edit_blob(refs=GUIDE), qe, lambda name: (1920, 1080)).width
      == ci.compile_prestage(edit_blob(refs=GUIDE), qe, lambda name: (1920, 1080)).height,
      True)
expect_error("a guide handed to the edition that never learned one is refused",
             lambda: ci.compile_prestage(edit_blob(refs=GUIDE, edition="base"), qe),
             "would edit the guide instead of following it")
check("...while 2509 reads it, which is the edition it arrived in",
      ci.compile_prestage(edit_blob(refs=GUIDE, edition="2509"), qe).refs, ["depth.png"])
check("an ordinary picture on the base weights is untouched by that rule",
      ci.compile_prestage(edit_blob(refs=["her.png"], edition="base"), qe).refs,
      ["her.png"])

expect_error("an edition nobody published is refused by name",
             lambda: ci.compile_prestage(edit_blob(edition="2601"), qe),
             "unknown Qwen Image Edit edition")

# ---- Flux 2 Klein ------------------------------------------------------------
#
# The template shape: loaders, plain text encodes, the model's own
# resolution-shifted schedule (`Flux2Scheduler`) through
# `SamplerCustomAdvanced`, and every reference scaled to ~1MP, VAE-encoded
# once, and chained onto *both* conditionings as a `ReferenceLatent`. No
# KSampler, no shift node, no encoder image slots — and the edited picture's
# latent stays empty, because the instruction reaches the model through the
# reference conditioning alone.

kl = importlib.import_module(f"{PACKAGE}.creator.families.flux2klein.still")
MODELS["flux2klein"] = {
    "model": "flux-2-klein-base-9b-fp8.safetensors",
    "turbo_model": "flux-2-klein-9b-fp8.safetensors",
    "clip": "qwen_3_8b_fp8mixed.safetensors",
    "vae": "flux2-vae.safetensors",
}
KL_WEIGHTS = ri.ImageWeights(arch="flux2klein", files=MODELS["flux2klein"])


def klein_blob(**overrides):
    data = {"arch": "flux2klein", "prompt": "a red room", "aspect": "16:9",
            "short_edge": 1024, "refs": [], "loras": []}
    data.update(overrides)
    return data


def klein_graph(data=None, size_lookup=None, **row):
    settings = dict(seed=11, steps=20, cfg=5.0, sampler_name="euler",
                    scheduler="simple")
    settings.update(row)
    payload = ci.compile_prestage(data if data is not None else klein_blob(),
                                  kl, size_lookup)
    return payload, by_class(ri.emit(payload, KL_WEIGHTS,
                                     sampling_mod.Sampling(**settings),
                                     NODE_ID, kl).finalize())


kl_payload, kt2i = klein_graph()

check("the base checkpoint loads and the encoder is typed flux2",
      (kt2i["UNETLoader"][0][1]["unet_name"], kt2i["CLIPLoader"][0][1]["type"]),
      (MODELS["flux2klein"]["model"], "flux2"))
check("the schedule is the model's own, shaped by the canvas",
      kt2i["Flux2Scheduler"][0][1],
      {"steps": 20, "width": kl_payload.width, "height": kl_payload.height})
check("no KSampler and no shift node — the custom stack is the whole sampler",
      ("KSampler" in kt2i, "ModelSamplingFlux" in kt2i,
       "SamplerCustomAdvanced" in kt2i), (False, False, True))
check("real CFG gets a real empty-prompt negative",
      sorted(i["text"] for _, i in kt2i["CLIPTextEncode"]), ["", "a red room"])
check("the guider runs the row's cfg", kt2i["CFGGuider"][0][1]["cfg"], 5.0)
check("the latent is the template's empty Flux 2 one, at the canvas",
      kt2i["EmptyFlux2LatentImage"][0][1],
      {"width": kl_payload.width, "height": kl_payload.height, "batch_size": 1})

# The reference chain, and the promotion around it: asked to edit `Picture 1`
# in place, the canvas follows it — but its latent contribution is the
# reference chain, not an init encode about to be noised away.
kle_payload, kle = klein_graph(klein_blob(
    prompt="put @img-2 on the table", edit_first=True,
    refs=[{"filename": "room.png", "handle": "img-1"},
          {"filename": "cup.png", "handle": "img-2"}]))

check("each picture is scaled and encoded exactly once",
      (len(kle["ImageScaleToTotalPixels"]), len(kle["VAEEncode"])), (2, 2))
check("...on the snap the core requires a value for",
      sorted(i["resolution_steps"] for _, i in kle["ImageScaleToTotalPixels"]),
      [16, 16])
check("...and chained onto both conditionings",
      len(kle["ReferenceLatent"]), 4)
kle_guider = kle["CFGGuider"][0][1]
kle_ref_ids = {node_id for node_id, _ in kle["ReferenceLatent"]}
check("both branches the guider reads end on the reference chain",
      (kle_guider["positive"][0] in kle_ref_ids,
       kle_guider["negative"][0] in kle_ref_ids), (True, True))
check("a citation becomes the slot's shared label",
      sorted(i["text"] for _, i in kle["CLIPTextEncode"]),
      ["", "put Picture 2 on the table"])
check("the first picture is promoted, so the canvas will follow it",
      kle_payload.init, {"filename": "room.png", "denoise": 1.0})
check("...but its latent stays the template's empty one",
      "EmptyFlux2LatentImage" in kle, True)
sized_klein = ci.compile_prestage(
    klein_blob(refs=["room.png"], edit_first=True), kl, lambda name: (1920, 1080))
check("the canvas takes the edited picture's shape",
      sized_klein.width > sized_klein.height, True)
blank_klein, blank_kg = klein_graph(klein_blob(refs=["room.png"]))
check("unasked, the picture is a reference and not the subject",
      (blank_klein.init, "EmptyFlux2LatentImage" in blank_kg), (None, True))

# A picture carrying its saved rendition in Klein's space: the slot is read
# off the file as a latent — no scale, no encode — and chained exactly as an
# encode would have been. The picture is still the picture: it is promoted,
# framed and sized as before, and a rendition in another family's space is
# nothing to Klein.
klm_payload, klm = klein_graph(klein_blob(
    prompt="put @img-2 on the table", edit_first=True,
    refs=[{"filename": "room.png", "handle": "img-1",
           "mods": {"flux2": "refmod:cast/room.flux2", "h3_video": "refmod:cast/room"}},
          {"filename": "cup.png", "handle": "img-2", "mods": {"h3_video": "refmod:cast/cup"}}]))
check("the payload names the rendition in Klein's own space, by slot",
      klm_payload.mods, {0: "refmod:cast/room.flux2"})
check("that slot is chained off the file, in the family's own space, onto both branches",
      [(i["name"], i["space"]) for _, i in klm["ContinuityRefModReference"]],
      [("refmod:cast/room.flux2", "flux2")] * 2)
check("...and only the other is scaled and encoded",
      (len(klm["ImageScaleToTotalPixels"]), len(klm["VAEEncode"]),
       [i["image"] for _, i in klm["LoadImage"]]), (1, 1, ["cup.png"]))
check("...the encoded one on both conditionings as before", len(klm["ReferenceLatent"]), 2)
klm_guider = klm["CFGGuider"][0][1]
klm_ref_ids = {node_id for node_id, _ in klm["ReferenceLatent"]}
check("both branches the guider reads end on the chain",
      (klm_guider["positive"][0] in klm_ref_ids, klm_guider["negative"][0] in klm_ref_ids), (True, True))
check("the picture is still the picture: promoted to the canvas when asked",
      klm_payload.init, {"filename": "room.png", "denoise": 1.0})
# A mod cited outright — a downloaded Klein set, no picture behind it — is a
# reference and only that: never the init, never framed, never loaded as a
# picture. The canvas is the asked shape.
kls_payload, kls = klein_graph(klein_blob(
    prompt="Picture 1 at a window", aspect="1:1",
    refs=[{"filename": "refmod:fk9_adele_v1_refmod", "handle": "img-1"}]))
check("a mod cited outright is chained and nothing is loaded",
      (kls_payload.mods, "LoadImage" in kls, "VAEEncode" in kls,
       len(kls["ContinuityRefModReference"])),
      ({0: "refmod:fk9_adele_v1_refmod"}, False, False, 2))
check("...never the init, so the canvas is the asked shape",
      (kls_payload.init, kls_payload.width == kls_payload.height, "EmptyFlux2LatentImage" in kls),
      (None, True, True))
try:
    ci.compile_prestage({**klein_blob(refs=["refmod:x"]), "arch": "krea2"},
                        importlib.import_module(f"{PACKAGE}.creator.families.krea2.still"))
    mod_refusal = ""
except ci.CompileError as exc:
    mod_refusal = str(exc)
check("a family that keeps no mods refuses one by name",
      "reads none" in mod_refusal, True)
check("the reference node is one of the pack's nodes",
      "ContinuityRefModReference" in [
          node.define_schema().node_id
          for node in asyncio.run(package.creator.creator_node.MiniMaxCreatorExtension().get_node_list())],
      True)

# The distilled checkpoint: the turbo pill's file, four steps at cfg 1, and a
# zeroed negative in place of an encode the guider never evaluates.
_, kldist = klein_graph(klein_blob(turbo={"flux2klein": {"on": True}}),
                        steps=4, cfg=1.0)
check("the turbo pill swaps in the distilled file",
      kldist["UNETLoader"][0][1]["unet_name"],
      MODELS["flux2klein"]["turbo_model"])
check("at cfg 1 the negative is the zeroed copy",
      ("ConditioningZeroOut" in kldist, len(kldist["CLIPTextEncode"])),
      (True, 1))

# An explicit partial-denoise init is img2img on the model's own schedule:
# the sigmas' tail, Ideogram's arrangement.
_, klinit = klein_graph(klein_blob(init={"filename": "plate.png",
                                         "denoise": 0.6}),
                        size_lookup=lambda name: (1024, 1024))
check("a partial denoise keeps the tail of the model's own schedule",
      klinit["SplitSigmasDenoise"][0][1]["denoise"], 0.6)
check("...and the sampler reads the split's low half",
      klinit["SamplerCustomAdvanced"][0][1]["sigmas"],
      [klinit["SplitSigmasDenoise"][0][0], 1])
check("...over the init image encoded, not an empty canvas",
      ("VAEEncode" in klinit, "EmptyFlux2LatentImage" in klinit), (True, False))

expect_error("a fourth picture is refused with the pack's own reason",
             lambda: ci.compile_prestage(
                 klein_blob(refs=["a.png", "b.png", "c.png", "d.png"]), kl),
             "where this pack caps the reference chain")
expect_error("a missing distilled file is refused when the pill asks for it",
             lambda: ri.emit(
                 ci.compile_prestage(
                     klein_blob(turbo={"flux2klein": {"on": True}}), kl),
                 ri.ImageWeights(arch="flux2klein",
                                 files={k: v for k, v in
                                        MODELS["flux2klein"].items()
                                        if k != "turbo_model"}),
                 sampling_mod.Sampling(seed=1, steps=4, cfg=1.0,
                                       sampler_name="euler",
                                       scheduler="simple"),
                 NODE_ID, kl),
             "Turbo checkpoint")

# ---- Qwen Image 2.1 ----------------------------------------------------------
#
# The template shape, and the shortest graph here: loaders, one encoder node
# that reads the sentence and every picture together and hands back both
# conditionings, an empty latent, `KSampler`, decode. No shift node — core
# detects the schedule — no CFG-norm, no second encoder for a text-only
# render: the same node encodes with no pictures and no `vae` read.

q21 = importlib.import_module(f"{PACKAGE}.creator.families.qwen21.still")
MODELS["qwen21"] = {
    "model": "qwen_image_2.1_int8_convrot.safetensors",
    "clip": "qwen3vl_8b_int8_convrot.safetensors",
    "vae": "qwen_image_2.1_vae_bf16.safetensors",
}
Q21_WEIGHTS = ri.ImageWeights(arch="qwen21", files=MODELS["qwen21"])


def qwen21_blob(**overrides):
    data = {"arch": "qwen21", "prompt": "a red room", "aspect": "16:9",
            "short_edge": 1024, "refs": [], "loras": []}
    data.update(overrides)
    return data


def qwen21_graph(data=None, size_lookup=None, **row):
    settings = dict(seed=11, steps=25, cfg=1.0, sampler_name="euler",
                    scheduler="simple")
    settings.update(row)
    payload = ci.compile_prestage(data if data is not None else qwen21_blob(),
                                  q21, size_lookup)
    return payload, by_class(ri.emit(payload, Q21_WEIGHTS,
                                     sampling_mod.Sampling(**settings),
                                     NODE_ID, q21).finalize())


q21_payload, qt2i = qwen21_graph()
q21_encode = qt2i["TextEncodeQwenImage21"][0]

check("the checkpoint loads and the encoder is typed qwen_image",
      (qt2i["UNETLoader"][0][1]["unet_name"], qt2i["CLIPLoader"][0][1]["type"]),
      (MODELS["qwen21"]["model"], "qwen_image"))
check("one encoder node, the sentence and an empty negative, no pictures",
      (len(qt2i["TextEncodeQwenImage21"]), q21_encode[1]["prompt"],
       q21_encode[1]["negative_prompt"],
       [k for k in q21_encode[1] if k.startswith("images.")]),
      (1, "a red room", "", []))
check("no shift node and no CFG-norm — the schedule is core's own",
      ("ModelSamplingAuraFlow" in qt2i, "CFGNorm" in qt2i, "CLIPTextEncode" in qt2i),
      (False, False, False))
q21_sampler = qt2i["KSampler"][0][1]
check("the sampler reads both conditionings off the encoder node",
      (q21_sampler["positive"], q21_sampler["negative"]),
      ([q21_encode[0], 0], [q21_encode[0], 1]))
check("the latent is core's empty one at the canvas — the sampler rescales it to /16",
      qt2i["EmptyLatentImage"][0][1],
      {"width": q21_payload.width, "height": q21_payload.height, "batch_size": 1})
check("the references' pixel budget is the canvas's own area, on the vision grid",
      (q21_encode[1]["resolution"], q21_payload.ref_resolution),
      (round(math.sqrt(q21_payload.width * q21_payload.height) / 32) * 32,) * 2)
check("the row is the template's", (q21_sampler["steps"], q21_sampler["cfg"], q21_sampler["denoise"]),
      (25, 1.0, 1.0))

# Pictures: each loaded into its numbered slot on the one encoder node, cited
# the way the 2.1 tokenizer spells them, the first edited in place when asked
# so the canvas follows it — but its latent stays the template's empty one.
q21e_payload, q21e = qwen21_graph(qwen21_blob(
    prompt="put @img-2 on the table in @img-1", edit_first=True,
    refs=[{"filename": "room.png", "handle": "img-1"},
          {"filename": "cup.png", "handle": "img-2"}]),
    size_lookup=lambda name: (1920, 1080) if name == "room.png" else (640, 640))
q21e_encode = q21e["TextEncodeQwenImage21"][0][1]
q21e_loads = {node_id: inputs["image"] for node_id, inputs in q21e["LoadImage"]}
check("each picture lands in its numbered slot, in attachment order",
      [q21e_loads[q21e_encode[f"images.image_{n}"][0]] for n in (1, 2)],
      ["room.png", "cup.png"])
check("a citation becomes the tokenizer's own label",
      q21e_encode["prompt"], "put <image2> on the table in <image1>")
check("the VAE reaches the encoder, so the pictures become reference latents",
      q21e_encode["vae"], [q21e["VAELoader"][0][0], 0])
check("no VAE encode of the first picture — it reaches the model as a reference",
      ("VAEEncode" in q21e, "EmptyLatentImage" in q21e), (False, True))
check("the first picture is promoted, so the canvas follows it",
      (q21e_payload.init, q21e_payload.width > q21e_payload.height),
      ({"filename": "room.png", "denoise": 1.0}, True))
# ...and the canvas *is* the encoder's resize of that picture at the budget,
# so the empty latent the sampler starts from is the size the reference latent
# is spliced in at. A 4:3 phone photo is the case the shared /16 snap got
# wrong by a latent row: 1360 on the canvas, 1376 out of the encoder.
q43_payload, q43 = qwen21_graph(qwen21_blob(refs=["photo.png"], edit_first=True),
                                size_lookup=lambda name: (3024, 4032))
check("an edit's canvas is the encoder's own resize of the first picture",
      (q43_payload.width, q43_payload.height, q43_payload.ref_resolution,
       q43["EmptyLatentImage"][0][1]["width"], q43["EmptyLatentImage"][0][1]["height"],
       q43["TextEncodeQwenImage21"][0][1]["resolution"]),
      (1024, 1376, 1184, 1024, 1376, 1184))
check("...which is the size the encoder computes from that budget",
      q21.fit_canvas(1024, 1360, 3024 / 4032), (1024, 1376, 1184))
check("...stepping the budget down where the resize would pass the ceiling",
      q21.fit_canvas(2048, 864, 2560 / 1080), (2016, 864, 1312))
blank_q21, blank_qg = qwen21_graph(qwen21_blob(refs=["room.png"]))
check("unasked, the picture is a reference and not the subject",
      (blank_q21.init, "EmptyLatentImage" in blank_qg), (None, True))

# An explicit partial-denoise init is img2img as any other: the init encoded
# through the 2.1 VAE and the leftover noise the row asks for.
_, q21init = qwen21_graph(qwen21_blob(init={"filename": "plate.png", "denoise": 0.6}),
                          size_lookup=lambda name: (1024, 1024))
check("a partial denoise encodes the init and keeps the row's denoise",
      ("VAEEncode" in q21init, "EmptyLatentImage" in q21init,
       q21init["KSampler"][0][1]["denoise"]), (True, False, 0.6))

# Ten pictures fill ten slots; an eleventh is refused with the pack's reason.
ten = [f"p{n}.png" for n in range(1, 11)]
_, q21ten = qwen21_graph(qwen21_blob(refs=ten))
check("ten pictures fill ten numbered slots",
      sorted(int(k.rsplit("_", 1)[1]) for k in q21ten["TextEncodeQwenImage21"][0][1]
             if k.startswith("images.")), list(range(1, 11)))
expect_error("an eleventh picture is refused with the pack's own reason",
             lambda: ci.compile_prestage(qwen21_blob(refs=ten + ["p11.png"]), q21),
             "official Qwen Image 2.1 workflow stops")
expect_error("the turbo pill refuses to engage without a Lightning LoRA",
             lambda: ci.compile_prestage(qwen21_blob(turbo={"qwen21": {"on": True}}), q21),
             "Lightning LoRA")

# ---- the guide, through the Fun ControlNet ----------------------------------
#
# A picture attached with `role: "guide"` is lifted out of the pool: it never
# reaches the encoder, takes no `<imageN>`, and patches the *model* through
# core's `ModelPatchLoader` + `ZImageFunControlnet`, cropped to the canvas
# first because the patch only stretches. The core probe is forced here — the
# graph is inspected, not sampled, and the local core may predate the branch.

check("no guide, no branch", ("ModelPatchLoader" in qt2i, "ZImageFunControlnet" in qt2i),
      (False, False))
Q21_GUIDED = ri.ImageWeights(arch="qwen21", files={
    **MODELS["qwen21"], "control": "Qwen-Image-2.1-Fun-Controlnet-Union.safetensors"})
GUIDE = {"filename": "edges.png", "handle": "img-2", "role": "guide", "guide": "edges"}


def guided_graph(data, weights=Q21_GUIDED, supported=True):
    probe = q21.control_supported
    q21.control_supported = lambda: supported
    try:
        payload = ci.compile_prestage(data, q21)
        return payload, by_class(ri.emit(payload, weights, sampling_mod.Sampling(
            seed=11, steps=25, cfg=1.0, sampler_name="euler", scheduler="simple"),
            NODE_ID, q21).finalize())
    finally:
        q21.control_supported = probe


gp, gg = guided_graph(qwen21_blob(prompt="a room like @img-1",
                                  refs=[{"filename": "room.png", "handle": "img-1"}, GUIDE]))
g_encode = gg["TextEncodeQwenImage21"][0][1]
g_loads = {node_id: inputs["image"] for node_id, inputs in gg["LoadImage"]}
check("the guide is not one of the encoder's pictures",
      ([g_loads[g_encode[k][0]] for k in g_encode if k.startswith("images.")], g_encode["prompt"],
       gp.refs), (["room.png"], "a room like <image1>", ["room.png"]))
g_apply = gg["ZImageFunControlnet"][0]
g_scale = dict(gg["ImageScale"])[g_apply[1]["image"][0]]
check("the branch loads from the control field and patches the model the sampler reads",
      (gg["ModelPatchLoader"][0][1]["name"], g_apply[1]["model_patch"][0],
       gg["KSampler"][0][1]["model"]),
      (Q21_GUIDED.get("control"), gg["ModelPatchLoader"][0][0], [g_apply[0], 0]))
check("the drawing is cropped to the canvas before the patch stretches it",
      (g_loads[g_scale["image"][0]], g_scale["width"], g_scale["height"], g_scale["crop"]),
      ("edges.png", gp.width, gp.height, "center"))
check("full strength over the whole schedule by default",
      (g_apply[1]["strength"], g_apply[1]["start_percent"], g_apply[1]["end_percent"]),
      (1.0, 0.0, 1.0))
check("...and the blob's guide block where it says otherwise, clamped",
      guided_graph(qwen21_blob(refs=[GUIDE], guide={"strength": 3, "start": 0.2}))[0].control,
      {"filename": "edges.png", "strength": 1.0, "start": 0.2, "end": 1.0})
check("a guide takes no reference slot — ten pictures and a guide still render",
      len(guided_graph(qwen21_blob(refs=ten + [GUIDE]))[0].refs), 10)
check("an edit in place never edits the guide",
      guided_graph(qwen21_blob(refs=[GUIDE, "room.png"], edit_first=True))[0].init["filename"],
      "room.png")
expect_error("a sentence citing the guide is refused for that",
             lambda: ci.compile_prestage(qwen21_blob(prompt="like @img-2", refs=[GUIDE]), q21),
             "is the guide")
expect_error("two guides are one too many",
             lambda: ci.compile_prestage(qwen21_blob(refs=[GUIDE, {**GUIDE, "handle": "img-3"}]), q21),
             "one guide at a time")
expect_error("a guide with no branch picked names the weights control",
             lambda: guided_graph(qwen21_blob(refs=[GUIDE]), weights=Q21_WEIGHTS),
             "models/model_patches")
expect_error("a core that cannot load the branch says so",
             lambda: guided_graph(qwen21_blob(refs=[GUIDE]), supported=False),
             "cannot load the Qwen Image 2.1 Fun ControlNet")

# ---- an edit never starts from the noise that made its picture ---------------
#
# On the three edit families the render is the seed's noise plus the pictures
# it is told to change, and the seed that drew one of those pictures pulls the
# sampler straight back onto it (the lab, 2026-09: a sharpened copy, edit
# ignored, on all three, until the seed moved). `render_image.edit_seed`
# derives the sampled seed from the widget's seed and the pictures — the same
# inputs give the same render, and a picture's own seed is never reused.

def derived(seed, refs):
    return int.from_bytes(hashlib.blake2b((f"{seed}:" + "|".join(refs)).encode(),
                                          digest_size=8).digest(), "big")

_, seeded_q21 = qwen21_graph(qwen21_blob(refs=["room.png", "cup.png"]), seed=11)
check("qwen21 samples an edit on a seed derived from the widget's and the pictures",
      seeded_q21["KSampler"][0][1]["seed"], derived(11, ["room.png", "cup.png"]))
check("...and not on the widget's own", seeded_q21["KSampler"][0][1]["seed"] != 11, True)
check("...while a text-to-image still keeps the widget's seed exactly",
      qt2i["KSampler"][0][1]["seed"], 11)
_, seeded_kl = klein_graph(klein_blob(refs=["room.png"]), seed=11)
check("flux2klein's noise node takes the derived seed",
      seeded_kl["RandomNoise"][0][1]["noise_seed"], derived(11, ["room.png"]))
_, seeded_qe = edit_graph(seed=7)
check("qwenedit's sampler takes the derived seed",
      seeded_qe["KSampler"][0][1]["seed"], derived(7, ["her.png", "coat.png"]))
check("a different widget seed is a different derived seed",
      derived(7, ["her.png"]) != derived(8, ["her.png"]), True)
check("Krea 2's sampler takes the derived seed too, now its pictures can be the subject",
      refs_graph(seed=5)["KSampler"][0][1]["seed"], derived(5, ["a.png", "b.png"]))

# ---- MOSS-Image --------------------------------------------------------------
#
# Krea 2's text-to-image shape on the Flux 2 latent: an encode, an empty-prompt
# encode for the negative, `KSampler`. No shift node — core detects the card's
# shift 5 at multiplier 1, and `ModelSamplingSD3` would restate it at 1000 —
# and the card's guidance as `SkipLayerGuidanceDiTSimple` on layer 22, emitted
# only where the unconditional is evaluated. Only on a core that has the model
# (Comfy-Org/ComfyUI#17095); an older one says so and the section is skipped.

ms = importlib.import_module(f"{PACKAGE}.creator.families.moss.still")
MODELS["moss"] = {
    "model": "moss_image_sft_int8_convrot.safetensors",
    "clip": "qwen3.5_9b_int8_convrot.safetensors",
    "vae": "flux2-vae.safetensors",
}
MOSS_WEIGHTS = ri.ImageWeights(arch="moss", files=MODELS["moss"])
_clip_types = comfy_nodes.NODE_CLASS_MAPPINGS["CLIPLoader"].INPUT_TYPES()["required"]["type"][0]


def moss_graph(data=None, **row):
    settings = dict(seed=11, steps=50, cfg=3.0, sampler_name="euler", scheduler="simple")
    settings.update(row)
    payload = ci.compile_prestage(data if data is not None else {
        "arch": "moss", "prompt": "a red room", "aspect": "16:9",
        "short_edge": 1024, "refs": [], "loras": []}, ms)
    return by_class(ri.emit(payload, MOSS_WEIGHTS, sampling_mod.Sampling(**settings),
                            NODE_ID, ms).finalize())


if "moss_image" not in _clip_types:
    print("MOSS-Image section skipped: this core predates it")
else:
    mt2i = moss_graph()
    check("moss loads its encoder typed moss_image and samples on the Flux 2 latent",
          (mt2i["UNETLoader"][0][1]["unet_name"], mt2i["CLIPLoader"][0][1]["type"],
           "EmptyFlux2LatentImage" in mt2i),
          (MODELS["moss"]["model"], "moss_image", True))
    check("moss's negative is the empty prompt, encoded",
          sorted(n[1]["text"] for n in mt2i["CLIPTextEncode"]), ["", "a red room"])
    check("moss skips layer 22 on the uncond pass and emits no shift node",
          ([(n[1]["double_layers"], n[1]["single_layers"]) for n in mt2i["SkipLayerGuidanceDiTSimple"]],
           "ModelSamplingSD3" in mt2i, "ModelSamplingAuraFlow" in mt2i),
          ([("", "22")], False, False))
    m_sampler = mt2i["KSampler"][0][1]
    check("moss samples the card's row",
          (m_sampler["steps"], m_sampler["cfg"], m_sampler["sampler_name"],
           m_sampler["scheduler"], m_sampler["denoise"]),
          (50, 3.0, "euler", "simple", 1.0))
    mcfg1 = moss_graph(cfg=1.0)
    check("at cfg 1 neither the uncond encode nor the layer skip is emitted",
          (len(mcfg1["CLIPTextEncode"]), "SkipLayerGuidanceDiTSimple" in mcfg1,
           "ConditioningZeroOut" in mcfg1), (1, False, True))
    expect_error("moss with references is refused with directions",
                 lambda: build(blob(arch="moss", refs=["a.png"])),
                 "MOSS-Image draws from the prompt alone")

# ---- MOSS-Image --------------------------------------------------------------
#
# Krea 2's text-to-image shape on the Flux 2 latent: an encode, an empty-prompt
# encode for the negative, `KSampler`. No shift node — core detects the card's
# shift 5 at multiplier 1, and `ModelSamplingSD3` would restate it at 1000 —
# and the card's guidance as `SkipLayerGuidanceDiTSimple` on layer 22, emitted
# only where the unconditional is evaluated. Only on a core that has the model
# (Comfy-Org/ComfyUI#17095); an older one says so and the section is skipped.

ms = importlib.import_module(f"{PACKAGE}.creator.families.moss.still")
MODELS["moss"] = {
    "model": "moss_image_sft_int8_convrot.safetensors",
    "clip": "qwen3.5_9b_int8_convrot.safetensors",
    "vae": "flux2-vae.safetensors",
}
MOSS_WEIGHTS = ri.ImageWeights(arch="moss", files=MODELS["moss"])
_clip_types = comfy_nodes.NODE_CLASS_MAPPINGS["CLIPLoader"].INPUT_TYPES()["required"]["type"][0]


def moss_graph(data=None, **row):
    settings = dict(seed=11, steps=50, cfg=3.0, sampler_name="euler", scheduler="simple")
    settings.update(row)
    payload = ci.compile_prestage(data if data is not None else {
        "arch": "moss", "prompt": "a red room", "aspect": "16:9",
        "short_edge": 1024, "refs": [], "loras": []}, ms)
    return by_class(ri.emit(payload, MOSS_WEIGHTS, sampling_mod.Sampling(**settings),
                            NODE_ID, ms).finalize())


if "moss_image" not in _clip_types:
    print("MOSS-Image section skipped: this core predates it")
else:
    mt2i = moss_graph()
    check("moss loads its encoder typed moss_image and samples on the Flux 2 latent",
          (mt2i["UNETLoader"][0][1]["unet_name"], mt2i["CLIPLoader"][0][1]["type"],
           "EmptyFlux2LatentImage" in mt2i),
          (MODELS["moss"]["model"], "moss_image", True))
    check("moss's negative is the empty prompt, encoded",
          sorted(n[1]["text"] for n in mt2i["CLIPTextEncode"]), ["", "a red room"])
    check("moss skips layer 22 on the uncond pass and emits no shift node",
          ([(n[1]["double_layers"], n[1]["single_layers"]) for n in mt2i["SkipLayerGuidanceDiTSimple"]],
           "ModelSamplingSD3" in mt2i, "ModelSamplingAuraFlow" in mt2i),
          ([("", "22")], False, False))
    m_sampler = mt2i["KSampler"][0][1]
    check("moss samples the card's row",
          (m_sampler["steps"], m_sampler["cfg"], m_sampler["sampler_name"],
           m_sampler["scheduler"], m_sampler["denoise"]),
          (50, 3.0, "euler", "simple", 1.0))
    mcfg1 = moss_graph(cfg=1.0)
    check("at cfg 1 neither the uncond encode nor the layer skip is emitted",
          (len(mcfg1["CLIPTextEncode"]), "SkipLayerGuidanceDiTSimple" in mcfg1,
           "ConditioningZeroOut" in mcfg1), (1, False, True))
    expect_error("moss with references is refused with directions",
                 lambda: build(blob(arch="moss", refs=["a.png"])),
                 "MOSS-Image draws from the prompt alone")

# ---- refusals ----------------------------------------------------------------

expect_error("Ideogram with references is refused with directions",
             lambda: build(blob(arch="ideogram4", refs=["a.png"])),
             "switch the model pill to Krea 2 or Qwen Image Edit")
expect_error("an empty prompt is refused",
             lambda: build(blob(prompt="  ")),
             "prompt is empty")


def without(arch, field):
    trimmed = {k: dict(v) for k, v in MODELS.items()}
    del trimmed[arch][field]
    return blob(arch=arch, models=trimmed)


expect_error("a missing checkpoint is refused up front, naming the folder",
             lambda: build(without("krea2", "model")),
             "models/diffusion_models")
expect_error("a missing text encoder is refused too",
             lambda: build(without("krea2", "clip")),
             "models/text_encoders")
expect_error("turbo demands the Turbo file, not the RAW one",
             lambda: build(blob(turbo={"on": True, "quality": "good", "saved": None},
                                models={**MODELS, "krea2": {k: v for k, v in MODELS["krea2"].items()
                                                            if k != "turbo_model"}})),
             "Turbo checkpoint")
# The file turbo skips is not demanded — the mirror of the video nodes'
# unrouted-checkpoint rule.
check("turbo does not require the RAW file",
      "UNETLoader" in by_class(build(
          blob(turbo={"on": True, "quality": "good", "saved": None},
               models={**MODELS, "krea2": {k: v for k, v in MODELS["krea2"].items()
                                           if k != "model"}}),
          steps=8, cfg=1.0).expand), True)

# ---- MiniMax H3 Image ---------------------------------------------------------
#
# The pill's "minimax", which used to be a video generation with one latent
# frame decoded and is now MiniMax's image model through core's own
# `MiniMaxH3ImageConditioning` — the official templates' shape: one
# conditioning node that reads the prompt and the pictures and hands back the
# empty latent, a zeroed negative, and six steps at cfg 1.

MODELS["minimax"] = {
    "model": "minimax_h3_image_pruned_int8_convrot.safetensors",
    "clip": "qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
    "vae": "minimax_h3_image_vae_fp16.safetensors",
}


def h3i_blob(**overrides):
    data = {"version": 1, "arch": "minimax", "prompt": "a red room", "aspect": "16:9",
            "short_edge": 2048, "refs": [], "loras": [], "models": dict(MODELS)}
    data.update(overrides)
    return json.dumps(data)


def h3i_build(data=None, **row):
    settings = dict(seed=7, steps=6, cfg=1.0, sampler_name="euler", scheduler="simple")
    settings.update(row)
    graph = build(data if data is not None else h3i_blob(), **settings).expand
    return graph, by_class(graph)


h3_graph, h3 = h3i_build()
cond = h3["MiniMaxH3ImageConditioning"]
check("it samples once, through core's conditioning node",
      (len(h3["KSampler"]), len(cond)), (1, 1))
check("no video segment node, and no latent slice",
      ("MiniMaxH3TimelineSegment" in h3, "MiniMaxH3StillLatent" in h3), (False, False))
check("the conditioning reads the prompt at the canvas, with the VAE connected",
      (cond[0][1]["prompt"], cond[0][1]["width"], cond[0][1]["height"], "vae" in cond[0][1]),
      ("a red room", 3648, 2048, True))
check("the DiT, the encoder typed minimax and the image VAE are what load",
      (h3["UNETLoader"][0][1]["unet_name"], h3["CLIPLoader"][0][1]["type"],
       h3["VAELoader"][0][1]["vae_name"]),
      (MODELS["minimax"]["model"], "minimax", MODELS["minimax"]["vae"]))
sampler = h3["KSampler"][0][1]
check("the sampler starts from the node's own empty latent",
      (h3_graph[sampler["latent_image"][0]]["class_type"], sampler["latent_image"][1]),
      ("MiniMaxH3ImageConditioning", 1))
check("the negative is the positive zeroed, as the template has it",
      h3_graph[sampler["negative"][0]]["class_type"], "ConditioningZeroOut")
check("the row arrives verbatim — six steps, cfg 1, full denoise",
      (sampler["seed"], sampler["steps"], sampler["cfg"], sampler["sampler_name"],
       sampler["denoise"]), (7, 6, 1.0, "euler", 1.0))
check("decoded once, saved once, into MiniMax H3 Image's stills folder",
      (len(h3["VAEDecode"]), len(h3["MiniMaxH3SaveImage"]),
       h3["MiniMaxH3SaveImage"][0][1]["filename_prefix"]),
      (1, 1, outputs.default_image("h3image", "H3Image")))

# An edit: Picture 1 is the one changed, cited the MiniMax way, and every
# picture goes into the node's autogrow slots in order.
media = importlib.import_module(f"{PACKAGE}.creator.media")
real_image_size = media.image_size
media.image_size = lambda filename: (3000, 2000)
try:
    edit_graph, edit = h3i_build(h3i_blob(
        prompt="paint @img-1 like @img-2", edit_first=True,
        refs=[{"handle": "img-1", "filename": "taxi.png"},
              {"handle": "img-2", "filename": "style.png"}]))
    mask_graph, masked = h3i_build(h3i_blob(
        prompt="a pink ice-cream truck",
        refs=[{"handle": "img-1", "filename": "taxi.png"},
              {"handle": "img-2", "filename": "taxi-matte.png", "role": "guide"}]))
finally:
    media.image_size = real_image_size
econd = edit["MiniMaxH3ImageConditioning"][0][1]
check("an edit cites its pictures as <Picture N>",
      econd["prompt"], "paint <Picture 1> like <Picture 2>")
check("...and fills the node's image slots in order",
      [edit_graph[econd[f"images.image_{n}"][0]]["inputs"]["image"] for n in (1, 2)],
      ["taxi.png", "style.png"])
check("...on Picture 1's canvas, from the node's empty latent",
      ((econd["width"], econd["height"]),
       edit_graph[edit["KSampler"][0][1]["latent_image"][0]]["class_type"]),
      ((3072, 2048), "MiniMaxH3ImageConditioning"))

# Inpainting: the matte is the sampler's noise mask over Picture 1 encoded.
mcond = masked["MiniMaxH3ImageConditioning"][0][1]
check("a mask is not a picture to the encoder", "images.image_2" in mcond, False)
latent = mask_graph[masked["KSampler"][0][1]["latent_image"][0]]
check("the sampler keeps Picture 1 outside the mask",
      (latent["class_type"], mask_graph[latent["inputs"]["samples"][0]]["class_type"]),
      ("SetLatentNoiseMask", "VAEEncode"))
check("...and the mask is the matte's red channel",
      mask_graph[latent["inputs"]["mask"][0]]["inputs"]["channel"], "red")
check("...on Picture 1's canvas, nothing to load for it",
      ((mcond["width"], mcond["height"]), "ControlNetLoader" in masked,
       "ModelPatchLoader" in masked), ((3072, 2048), False, False))
check("...at full denoise, the stock sampler pinning the rest",
      masked["KSampler"][0][1]["denoise"], 1.0)

# A blob saved on the old H3 branch opens here and renders.
old_graph, old = h3i_build(json.dumps({
    "version": 1, "arch": "minimax", "models": dict(MODELS),
    "minimax": {"frames": 5, "latent_index": 0,
                "request": {"prompt": "an old still", "assets": [], "loras": [],
                            "aspect": "1:1", "models": {"fl2va": "x.safetensors"}}}}))
check("an old H3 still renders as a MiniMax H3 Image one, its sentence kept",
      (old["MiniMaxH3ImageConditioning"][0][1]["prompt"],
       old["MiniMaxH3ImageConditioning"][0][1]["width"],
       old["MiniMaxH3ImageConditioning"][0][1]["height"]),
      ("an old still", 2048, 2048))

# LoRAs go through core's loader, like every other still family.
_, lora = h3i_build(h3i_blob(loras=[{"name": "h3_character.safetensors", "strength": 0.7}]))
check("a LoRA is patched model-only through core's loader",
      [(i["lora_name"], i["strength_model"]) for _, i in lora["LoraLoaderModelOnly"]],
      [("h3_character.safetensors", 0.7)])

# ---- {a|b} chooses on the seed --------------------------------------------
#
# The same hash `compile.varied_piece` uses for a strip, as card 1: the prompt
# box lights the alternative by that number, so the render has to read it.

variations = importlib.import_module(f"{PACKAGE}.creator.variations")

varied_text = "a {red|blue} door"
for seed in (100, 2331284070, 32029067):
    chosen = variations.resolve(varied_text, seed, 1)
    check(f"an image arch renders the alternative seed {seed} chooses",
          sorted(i["text"] for _, i in
                 by_class(build(blob(prompt=varied_text), seed=seed).expand)["CLIPTextEncode"]),
          [chosen])
    check(f"...and MiniMax H3 Image the same choice on seed {seed}",
          h3i_build(h3i_blob(prompt=varied_text), seed=seed)[1]
          ["MiniMaxH3ImageConditioning"][0][1]["prompt"], chosen)
check("a choice is made — the braces never reach the encoder",
      "{" in by_class(build(blob(prompt=varied_text)).expand)["CLIPTextEncode"][0][1]["text"], False)

# ---- saved references -----------------------------------------------------------
#
# In the family's own space, not H3 video's: the image VAE samples its
# posterior and the node anchors at up to a 2048 short edge, so an H3 mod on
# the same picture is nothing to this family. The text encoder is shown the
# picture a mod hangs on; the file only takes the anchor's place.

_, h3m = h3i_build(h3i_blob(
    prompt="@img-1 beside @img-2",
    refs=[{"filename": "anna.png", "handle": "img-1",
           "mods": {"h3_image": "refmod:cast/anna.h3_image", "h3_video": "refmod:cast/anna"}},
          {"filename": "cup.png", "handle": "img-2", "mods": {"h3_video": "refmod:cast/cup"}}]))
check("a picture carrying a mod is still what the encoder is shown",
      (sorted(i["image"] for _, i in h3m["LoadImage"]), len(h3m["VAEDecode"]), "ContinuityRefModLatent" in h3m),
      (["anna.png", "cup.png"], 1, False))
check("only the rendition in the family's own space takes an anchor's place",
      [(i["name"], i["space"], i["slot"]) for _, i in h3m["ContinuityRefModH3ImageAnchor"]],
      [("refmod:cast/anna.h3_image", "h3_image", 0)])
_, h3s = h3i_build(h3i_blob(
    prompt="@img-1 at a window",
    refs=[{"filename": "refmod:cast/anna.h3_image", "handle": "img-1"}]))
check("a mod standing alone is decoded to be shown, and anchored as itself",
      ([(i["name"], i["space"]) for _, i in h3s["ContinuityRefModLatent"]],
       len(h3s["VAEDecode"]), "LoadImage" in h3s,
       [(i["name"], i["slot"]) for _, i in h3s["ContinuityRefModH3ImageAnchor"]]),
      ([("refmod:cast/anna.h3_image", "h3_image")], 2, False, [("refmod:cast/anna.h3_image", 0)]))
h3e = h3i.compile_still(json.loads(h3i_blob(
    prompt="make @img-1 smile", edit_first=True,
    refs=[{"filename": "anna.png", "handle": "img-1",
           "mods": {"h3_image": "refmod:cast/anna.h3_image"}}])), lambda name: (2048, 2048))
check("the picture an edit changes is read as itself",
      (h3e.init["filename"], h3e.mods), ("anna.png", {}))

# ---- refusals ----------------------------------------------------------------

expect_error("a MiniMax still with no VAE is refused, naming the folder",
             lambda: h3i_build(h3i_blob(models={**MODELS, "minimax": {
                 k: v for k, v in MODELS["minimax"].items() if k != "vae"}})),
             "models/vae")
expect_error("a mask with no picture under it is refused",
             lambda: h3i_build(h3i_blob(refs=[
                 {"handle": "img-1", "filename": "m.png", "role": "guide"}])),
             "Picture 1")

# ---- GGUF checkpoints -------------------------------------------------------
#
# The image branch reuses `models.loader_for`, so the claims are the creator
# graph's: a `.gguf` file swaps the loader class, drops `weight_dtype` (a core
# widget the GGUF nodes lack), and refuses up front without the pack.

GGUF_MODEL = "krea2_raw_Q4_K_M.gguf"

expect_error("a GGUF checkpoint without the pack is refused up front",
             lambda: build(blob(models={**MODELS, "krea2": {
                 **MODELS["krea2"], "model": GGUF_MODEL}})),
             "ComfyUI-GGUF")


class _FakeGGUF:
    FUNCTION = "load"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}}


_restore_gguf = dict(comfy_nodes.NODE_CLASS_MAPPINGS)
comfy_nodes.NODE_CLASS_MAPPINGS["UnetLoaderGGUF"] = _FakeGGUF
try:
    quant = by_class(build(blob(models={**MODELS, "krea2": {
        **MODELS["krea2"], "model": GGUF_MODEL}})).expand)
    check("a .gguf checkpoint loads through the pack's loader",
          quant["UnetLoaderGGUF"][0][1], {"unet_name": GGUF_MODEL})
    check("...and no core UNETLoader beside it", "UNETLoader" in quant, False)
    check("the text encoder stays on the core loader", len(quant["CLIPLoader"]), 1)
finally:
    comfy_nodes.NODE_CLASS_MAPPINGS.clear()
    comfy_nodes.NODE_CLASS_MAPPINGS.update(_restore_gguf)

# ---- the preview override on the image branches ------------------------------
#
# The same KJNodes patch the video render and the H3 still carry, and here for
# the same reason: without it these two sample behind core's previewer, whose
# frames the frontend paints onto the canvas node — over the node body, and
# nowhere the fullscreen editor can show them. Optional in the same way too, so
# the absent path is what runs unaided above.

check("no override node when the pack is not installed",
      ("ModelPreviewOverrideKJ" in kinds, "ModelPreviewOverrideKJ" in ideo),
      (False, False))
# ...but a preview all the same: core's is off on a stock install, so without
# the pack the still would sample behind an empty box (`livepreview.py`).
check("the pack's own preview stands in for it, once per render",
      (len(kinds.get("ContinuityPreview", [])), len(ideo.get("ContinuityPreview", []))),
      (1, 1))
# Under the family's own wrappers rather than over them — Krea's shift clones
# the patcher and carries the wrapper along (`render_image.py`).
check("...and the sampler samples through it",
      (kinds["ModelSamplingFlux"][0][1]["model"][0],
       kinds["KSampler"][0][1]["model"][0]),
      (kinds["ContinuityPreview"][0][0], kinds["ModelSamplingFlux"][0][0]))


class _FakePreview:
    FUNCTION = "execute"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "model": ("MODEL",),
            "max_resolution": ("INT", {"default": 1024}),
            "jpeg_quality": ("INT", {"default": 80}),
            "suppress_default_preview": ("BOOLEAN", {"default": True}),
            "preview_frames": ("INT", {"default": 1}),
            "preview_fps": ("INT", {"default": 12}),
        }}


_restore_preview = dict(comfy_nodes.NODE_CLASS_MAPPINGS)
comfy_nodes.NODE_CLASS_MAPPINGS["ModelPreviewOverrideKJ"] = _FakePreview
try:
    previewed = by_class(build().expand)
    patches = previewed["ModelPreviewOverrideKJ"]
    check("one preview patch on a Krea render", len(patches), 1)
    check("core's own overlay is suppressed — ours is the only one",
          patches[0][1]["suppress_default_preview"], True)
    # No tiny decoder: the image architectures declare no `preview` field, so
    # this is the node's own latent2rgb path — which is the point. The node is
    # emitted for where it puts the picture, not for what decodes it.
    check("...with no decoder picked", "tiny_vae" in patches[0][1], False)
    check("the shift reads the patch, and the sampler reads the shift",
          (previewed["ModelSamplingFlux"][0][1]["model"][0],
           previewed["KSampler"][0][1]["model"][0]),
          (patches[0][0], previewed["ModelSamplingFlux"][0][0]))

    # Order is what is checked: everything downstream clones the patcher and
    # carries the wrapper along, so the override has to be under the shift and
    # not over it.

    # Ideogram samples through a guider rather than a KSampler, and its
    # conditional branch carries the shift and the late-cfg drop — the
    # override goes under all of it, for the same reason.
    previewed_ideo = by_class(build(blob(arch="ideogram4"), steps=20, cfg=7.0).expand)
    ideo_patch = previewed_ideo["ModelPreviewOverrideKJ"]
    check("one preview patch on an Ideogram render", len(ideo_patch), 1)
    check("...on the conditional model, under the shift and the cfg drop",
          previewed_ideo["ModelSamplingAuraFlow"][0][1]["model"][0], ideo_patch[0][0])
    check("...and not on the unconditional one",
          previewed_ideo["DualModelGuider"][0][1]["model_negative"][0],
          [i for i, _ in previewed_ideo["UNETLoader"]
           if _["unet_name"] == MODELS["ideogram4"]["uncond_model"]][0])
finally:
    comfy_nodes.NODE_CLASS_MAPPINGS.clear()
    comfy_nodes.NODE_CLASS_MAPPINGS.update(_restore_preview)

# ---- devices ------------------------------------------------------------------
#
# A still's loaders move to a card the way a clip's do: `render_image.emit_loader`
# goes through `models.loader_for`, so a pin on the arch's side swaps the core
# loader for its ComfyUI-MultiGPU subclass and adds `device`. The pre-stage once
# emitted every loader with no device at all, and the VAE outside `loader_for`
# entirely; these pin that it no longer can. The pack is absent here, so both
# halves are worth checking: nothing pinned is the core loaders, and a pin
# without the pack is refused rather than quietly loaded on one card.

def pinned(arch="krea2", **pins):
    models = {k: dict(v) for k, v in MODELS.items()}
    models[arch]["devices"] = pins
    return blob(arch=arch, models=models)


check("no MultiGPU loaders on a still when nothing is pinned",
      [k for k in by_class(build().expand) if k.endswith("MultiGPU")], [])
expect_error("a pinned still without the pack is refused up front",
             lambda: build(pinned(clip="cuda:1")), "ComfyUI-MultiGPU")


class _FakeMultiGPU:
    FUNCTION = "override"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}, "optional": {"device": (["cpu", "cuda:0", "cuda:1"],
                                                        {"default": "cuda:0"})}}


_restore_devices = dict(comfy_nodes.NODE_CLASS_MAPPINGS)
for wrapper in ("UNETLoaderMultiGPU", "CLIPLoaderMultiGPU", "VAELoaderMultiGPU"):
    comfy_nodes.NODE_CLASS_MAPPINGS[wrapper] = _FakeMultiGPU
try:
    split = by_class(build(pinned(clip="cuda:1", vae="cpu")).expand)
    check("the still's pinned encoder uses the pack's loader, on its card",
          [(i["clip_name"], i["type"], i["device"]) for _, i in split.get("CLIPLoaderMultiGPU", [])],
          [(MODELS["krea2"]["clip"], "krea2", "cuda:1")])
    check("...and the VAE, which used to bypass `loader_for`",
          [(i["vae_name"], i["device"]) for _, i in split.get("VAELoaderMultiGPU", [])],
          [(MODELS["krea2"]["vae"], "cpu")])
    check("an unpinned DiT stays on the core loader, with its precision",
          ([i["unet_name"] for _, i in split.get("UNETLoader", [])],
           "UNETLoaderMultiGPU" in split,
           split["UNETLoader"][0][1]["weight_dtype"]),
          ([MODELS["krea2"]["model"]], False, "default"))
    check("...and the core encoder and VAE loaders are gone",
          ("CLIPLoader" in split, "VAELoader" in split), (False, False))

    # Ideogram's second DiT goes through the same helper, so it can be pinned
    # on its own — the unconditional checkpoint on the other card.
    ideo = by_class(build(pinned("ideogram4", uncond_model="cuda:1"),
                          steps=20, cfg=7.0).expand)
    check("Ideogram's unconditional checkpoint takes its own pin",
          [(i["unet_name"], i["device"]) for _, i in ideo.get("UNETLoaderMultiGPU", [])],
          [(MODELS["ideogram4"]["uncond_model"], "cuda:1")])
    check("...leaving the conditional one on the core loader",
          [i["unet_name"] for _, i in ideo.get("UNETLoader", [])],
          [MODELS["ideogram4"]["model"]])

    # A pin on the other arch's side does nothing to this one: pins are per
    # side, like the files they name.
    other = blob(models={**{k: dict(v) for k, v in MODELS.items()},
                         "ideogram4": {**MODELS["ideogram4"], "devices": {"clip": "cuda:1"}}})
    check("a pin on another arch's side does not move this arch's loaders",
          [k for k in by_class(build(other).expand) if k.endswith("MultiGPU")], [])
finally:
    comfy_nodes.NODE_CLASS_MAPPINGS.clear()
    comfy_nodes.NODE_CLASS_MAPPINGS.update(_restore_devices)

ri_mod = importlib.import_module(f"{PACKAGE}.creator.render_image")
k2_still = importlib.import_module(f"{PACKAGE}.creator.families.krea2.still")
check("a pin on a field no MultiGPU loader wraps is dropped on read",
      ri_mod.ImageWeights.from_blob(
          {"models": {"krea2": {**MODELS["krea2"],
                                "devices": {"clip": "cuda:1", "nonsense": "cuda:0"}}}},
          k2_still).devices,
      {"clip": "cuda:1"})

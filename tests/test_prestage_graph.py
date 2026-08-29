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
import importlib
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
cs = importlib.import_module(f"{PACKAGE}.creator.families.h3.still")
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


# ---- Krea 2 t2i --------------------------------------------------------------
#
# The template shape: loaders, one text encode, a zeroed negative, an empty
# 16-channel latent, one KSampler, one decode, one save. Nothing else.

out = build()
graph = out.expand
kinds = by_class(graph)

check("expansion exports no links", out.result, ())
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
      (with_lora["ModelSamplingFlux"][0][1]["model"][0],
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

# ---- style references (Krea 2) -----------------------------------------------
#
# The official reference workflow's wiring: the Qwen-edit encoder with the
# references in its image slots and the method node on its conditioning,
# neither of which appears without refs.

ADAPTER = [{"name": "krea2_style_reference.safetensors", "strength": 1.0}]


def refs_blob(**overrides):
    data = {"arch": "krea2", "prompt": "p", "aspect": "1:1", "short_edge": 1024,
            "refs": [{"filename": "a.png"}, {"filename": "b.png"}],
            "loras": list(ADAPTER), "ref_lora": ADAPTER[0]["name"]}
    data.update(overrides)
    return data


def refs_graph(data=None, **row):
    settings = dict(seed=0, steps=20, cfg=1.0, sampler_name="euler", scheduler="simple")
    settings.update(row)
    return by_class(ri.emit(ci.compile_prestage(data if data is not None else refs_blob(), k2),
                            ri.ImageWeights(arch="krea2", files=MODELS["krea2"]),
                            sampling_mod.Sampling(**settings), NODE_ID, k2).finalize())


refs_payload = ci.compile_prestage(refs_blob(), k2)
refs = by_class(ri.emit(refs_payload, ri.ImageWeights(arch="krea2", files=MODELS["krea2"]),
                        sampling_mod.Sampling(), NODE_ID, k2).finalize())
encode = refs["TextEncodeQwenImageEditPlus"][0][1]
check("both references sit in the encoder's image slots",
      ("image1" in encode, "image2" in encode, "image3" in encode),
      (True, True, False))
check("the encoder also gets the VAE for the reference latents",
      encode["vae"][0] in {nid for nid, _ in refs["VAELoader"]}, True)
check("the reference method defaults to the edit LoRAs'",
      refs["FluxKontextMultiReferenceLatentMethod"][0][1]["reference_latents_method"],
      k2.DEFAULT_REF_METHOD)

# The layout is the adapter's, not a constant: the identity-edit LoRAs index
# their reference tokens like any other frame instead of pinning them at t=0,
# and picking the wrong one is a silently weaker render rather than an error.
indexed = by_class(ri.emit(ci.compile_prestage(refs_blob(ref_method="index"), k2),
                           ri.ImageWeights(arch="krea2", files=MODELS["krea2"]),
                           sampling_mod.Sampling(), NODE_ID, k2).finalize())
check("...and follows the adapter when the blob names another",
      indexed["FluxKontextMultiReferenceLatentMethod"][0][1]["reference_latents_method"],
      "index")
expect_error("an unknown reference method is refused by name",
             lambda: ci.compile_prestage(refs_blob(ref_method="offset"), k2),
             "offset")

# Core hands Krea 2 no default reference method because the base weights have
# none — every way of reading a reference on this model is a LoRA. So an empty
# stack is not a weaker render, it is the images going nowhere.
expect_error("references with no adapter in the stack are refused",
             lambda: ci.compile_prestage(refs_blob(loras=[], ref_lora=None), k2),
             "only through a reference LoRA")
expect_error("...and a muted adapter counts as no adapter",
             lambda: ci.compile_prestage(refs_blob(
                 loras=[{**ADAPTER[0], "enabled": False}]), k2),
             "not in this render's LoRA stack")
# And the adapter is named rather than counted: a stack holding a style LoRA and
# nothing that reads references is the same silent failure as an empty one, so
# "there is a LoRA" is not the question being asked.
expect_error("a stack with no *reference* adapter in it is refused",
             lambda: ci.compile_prestage(refs_blob(
                 loras=[{"name": "some_painting_style.safetensors", "strength": 1.0}],
                 ref_lora=None), k2),
             "only through a reference LoRA")
expect_error("...and an adapter named but never added is refused by name",
             lambda: ci.compile_prestage(refs_blob(
                 loras=[{"name": "some_painting_style.safetensors", "strength": 1.0}]), k2),
             "krea2_style_reference.safetensors")
check("a stack that carries the named adapter alongside others is fine",
      ci.compile_prestage(refs_blob(loras=[
          {"name": "some_painting_style.safetensors", "strength": 0.6},
          *ADAPTER]), k2).refs, ["a.png", "b.png"])

# The unconditional a reference render is guided against is the same pictures
# with nothing asked of them — the row these adapters were trained against.
# `ConditioningZeroOut` is not that: it copies the conditioning dict, so the
# reference latents do ride along, but the text stream becomes a block of zeros
# the model never saw in training.
guided = refs_graph(cfg=3.5)
check("at real CFG the negative is a second grounded encode",
      len(guided["TextEncodeQwenImageEditPlus"]), 2)
check("...over the same pictures, with nothing asked of them",
      sorted(i["prompt"] for _, i in guided["TextEncodeQwenImageEditPlus"]), ["", "p"])
check("...laid in the same way as the positive's",
      {i["reference_latents_method"]
       for _, i in guided["FluxKontextMultiReferenceLatentMethod"]},
      {k2.DEFAULT_REF_METHOD})
check("...and nothing is zeroed", "ConditioningZeroOut" in guided, False)
check("at cfg 1 the negative is never evaluated, so it is not paid for",
      (len(refs["TextEncodeQwenImageEditPlus"]), "ConditioningZeroOut" in refs),
      (1, True))

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
check("the reference branch samples on the same RAW ramp as t2i",
      (refs["ModelSamplingFlux"][0][1]["max_shift"], refs["ModelSamplingFlux"][0][1]["base_shift"]),
      (k2.KREA_RAW_SHIFT["max_shift"], k2.KREA_RAW_SHIFT["base_shift"]))
check("no plain text encode on the reference branch", "CLIPTextEncode" in refs, False)

expect_error("a fourth reference is refused",
             lambda: ci.compile_prestage(
                 refs_blob(refs=["a.png", "b.png", "c.png", "d.png"]), k2),
             "three image slots")

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

# The quality preset owns mu/std, not the user.
quality = by_class(build(blob(arch="ideogram4", quality="quality"), steps=48).expand)
check("the quality preset reshapes the schedule",
      (quality["Ideogram4Scheduler"][0][1]["mu"], quality["Ideogram4Scheduler"][0][1]["std"]),
      (0.0, 1.5))

# ---- the polish tail is a step count, not a percentage -----------------------
#
# Each preset ends on a fixed number of steps at gw=3 — 3 of 48, 2 of 20, 1 of
# 12 — and CFGOverride takes a percent, so the boundary has to be resolved
# against the schedule this render will run. Ideogram 4 samples on
# ModelSamplingDiscreteFlow at shift 1, where the sigma *is* the timestep, so
# the percent the node converts back is exactly `1 - sigma` and the count below
# is what the sampler will really do.


def polish_steps(quality_name, width=1024, height=1024):
    preset = i4.IDEOGRAM_QUALITIES[quality_name]
    steps = preset["steps"]
    start = i4.polish_percent(steps, preset["polish"], width, height,
                              preset["mu"], preset["std"])
    row = i4.sigmas(steps, width, height, preset["mu"], preset["std"])
    return sum(1 for sigma in row[:steps] if sigma <= 1.0 - start)


for name, preset in i4.IDEOGRAM_QUALITIES.items():
    check(f"{name} runs exactly its {preset['polish']} polish step(s) at 1K",
          polish_steps(name), preset["polish"])
    check(f"{name} runs exactly its {preset['polish']} polish step(s) at 2K",
          polish_steps(name, 2048, 1152), preset["polish"])

check("the mirrored schedule matches core's own",
      [round(v, 6) for v in i4.sigmas(12, 1024, 1024, 0.5, 1.75)],
      [round(float(v), 6) for v in
       importlib.import_module("comfy_extras.nodes_ideogram4")
       .ideogram4_sigmas(12, 1024, 1024, 0.5, 1.75)])

# The fixed 0.7 this replaced was right for exactly one preset at one canvas.
check("a fixed 0.7 would have run Quality's tail more than twice too long",
      sum(1 for sigma in i4.sigmas(48, 1024, 1024, 0.0, 1.5)[:48] if sigma <= 0.3), 7)

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
check("the schedule is the Turbo preset's, which is shaped for a short run",
      (ideo_turbo["Ideogram4Scheduler"][0][1]["mu"],
       ideo_turbo["Ideogram4Scheduler"][0][1]["std"],
       ideo_turbo["Ideogram4Scheduler"][0][1]["steps"]),
      (i4.IDEOGRAM_QUALITIES["turbo"]["mu"], i4.IDEOGRAM_QUALITIES["turbo"]["std"], 4))
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

edit_payload, edit = edit_graph()

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

# The first reference is the picture being changed: promoted to the init at a
# denoise of 1.0, which is the published workflow's latent exactly.
check("the first picture becomes the render's own starting point",
      edit_payload.init, {"filename": "her.png", "denoise": 1.0})
check("...encoded into the latent rather than an empty canvas",
      ("VAEEncode" in edit, "EmptySD3LatentImage" in edit), (True, False))
check("...at full denoise, because the instruction arrives as conditioning",
      edit["KSampler"][0][1]["denoise"], 1.0)

# And the canvas follows it, the way an init image's always has.
sized_payload = ci.compile_prestage(edit_blob(), qe, lambda name: (1920, 1080))
check("the canvas takes the edited picture's shape",
      (sized_payload.width > sized_payload.height, sized_payload.height), (True, 1024))
# ...and the way out of it. These are Qwen-Image weights post-trained, not
# replaced, so "here are two pictures, now draw a third" is a render they can
# do — and the promotion above is what would otherwise make it unreachable, by
# turning the act of attaching the first picture into an edit of it.
blank_payload, blank = edit_graph(edit_blob(start_blank=True))
check("a blank start releases the first picture from being the subject",
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
      ci.compile_prestage(edit_blob(start_blank=True,
                                    init={"filename": "plate.png", "denoise": 0.4}),
                          qe).init,
      {"filename": "plate.png", "denoise": 0.4})
check("the flag means nothing on a family that never promoted anything",
      ci.compile_prestage(refs_blob(start_blank=True), k2).init, None)

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
check("...and the canvas follows it, so the render comes out its shape",
      ci.compile_prestage(edit_blob(refs=GUIDE), qe, lambda name: (1920, 1080)).width
      > ci.compile_prestage(edit_blob(refs=GUIDE), qe, lambda name: (1920, 1080)).height,
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

# The reference chain, and the promotion around it: `Picture 1` is the thing
# being edited, so the canvas follows it — but its latent contribution is the
# reference chain, not an init encode about to be noised away.
kle_payload, kle = klein_graph(klein_blob(
    prompt="put @img-2 on the table",
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
    klein_blob(refs=["room.png"]), kl, lambda name: (1920, 1080))
check("the canvas takes the edited picture's shape",
      sized_klein.width > sized_klein.height, True)
blank_klein, blank_kg = klein_graph(klein_blob(refs=["room.png"],
                                               start_blank=True))
check("a blank start releases the picture from being the subject",
      (blank_klein.init, "EmptyFlux2LatentImage" in blank_kg), (None, True))

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

# ---- MiniMax H3: a still from the video model ---------------------------------
#
# The branch that is not an image model. What matters here is that it is the
# *video* path: the video segment node, the video checkpoints, the video canvas
# — with one latent frame taken out of the sampled clip and decoded.

H3_MODELS = {
    "fl2va": "minimax_h3_fl2va_fp8.safetensors",
    "ref2va": "minimax_h3_ref2va_fp8.safetensors",
    "clip": "minimax_qwen3vl_32b.safetensors",
    "vae": "minimax_h3_video_vae_fp16.safetensors",
    "audio_vae": "minimax_h3_audio_vae.safetensors",
}


def still_blob(request=None, **overrides):
    """A pre-stage blob on the H3 branch.

    The generation lives in `minimax.request` in exactly the Creator's shape —
    the branch is driven by the Creator's own editor — so the weights, the
    assets and the canvas are all in there, under the video nodes' own keys.
    """
    inner = {"prompt": "a red room", "assets": [], "loras": [],
             "aspect": "16:9", "short_edge": 768, "models": dict(H3_MODELS)}
    inner.update(request or {})
    block = {"frames": 5, "latent_index": 0, "request": inner}
    block.update(overrides.pop("minimax", {}))
    data = {"version": 1, "arch": "minimax", "minimax": block}
    data.update(overrides)
    return json.dumps(data)


def still(data=None, **overrides):
    kwargs = dict(seed=7, steps=20, cfg=1.0, sampler_name="res_multistep", scheduler="simple")
    kwargs.update(overrides)
    return build(data if data is not None else still_blob(), **kwargs)


h3_graph = still().expand
h3 = by_class(h3_graph)

check("it samples once", len(h3["KSampler"]), 1)
check("through the video segment node", len(h3["MiniMaxH3TimelineSegment"]), 1)
check("and keeps one latent frame", len(h3["MiniMaxH3StillLatent"]), 1)
check("decoded once, saved once",
      (len(h3["VAEDecode"]), len(h3["MiniMaxH3SaveImage"])), (1, 1))
check("the first latent frame by default", h3["MiniMaxH3StillLatent"][0][1]["index"], 0)
check("the still is what gets decoded",
      h3_graph[h3["VAEDecode"][0][1]["samples"][0]]["class_type"], "MiniMaxH3StillLatent")
# The slice is two latent tokens — the shortest clip the H3 VAE will decode, one
# token being the shape that comes back as tile seams and patch-grid noise
# (Comfy-Org/ComfyUI#15416) — so the decode is five pixel frames and the picture
# is the first of them.
check("the decode is cut back to one frame", len(h3["ImageFromBatch"]), 1)
check("...the clip's first", (h3["ImageFromBatch"][0][1]["batch_index"],
                              h3["ImageFromBatch"][0][1]["length"]), (0, 1))
check("...taken off the decode",
      h3_graph[h3["ImageFromBatch"][0][1]["image"][0]]["class_type"], "VAEDecode")
check("and that one frame is what is saved",
      h3_graph[h3["MiniMaxH3SaveImage"][0][1]["images"][0]]["class_type"], "ImageFromBatch")
check("no audio is decoded", "VAEDecodeAudio" in h3, False)
check("and no video is written", "MiniMaxH3Save" in h3, False)

# ---- the H3 branch's ControlNet ---------------------------------------------
#
# **A pre-stage still is a one-frame video generation, so it is aimed the way a
# shot is** — same Fun ControlNet branch, same apply node, same weights slot.
# That is the whole claim, and it is here rather than in the guide suite because
# this branch builds its own graph: it does not go through `core/emit.py`, so
# nothing the video path asserts covers a single node of it. It went unwired for
# exactly that reason.
#
# A still guide is a *picture*, which is the shape the bench sends here and the
# right one for a render that is one frame. The video-only rule that used to
# refuse it is gone: which of the two is right is the shot's question, and a
# one-frame shot answers it with a still.

GUIDE_ASSET = {"handle": "gde-1", "kind": "image", "role": "guide",
               "filename": "continuity/control/room_edges.png", "op": "edges"}
GUIDE_MODELS = {**H3_MODELS, "control": "minimax_h3_fun_controlnet_union.safetensors"}


def guided_still(**request):
    return still_blob(request={
        "models": GUIDE_MODELS, "assets": [GUIDE_ASSET],
        "guide": {"on": True, "strength": 0.8}, **request})


g = by_class(still(guided_still()).expand)
check("the branch is loaded once", len(g["ControlNetLoader"]), 1)
check("...from the controlnet slot",
      g["ControlNetLoader"][0][1]["control_net_name"],
      "minimax_h3_fun_controlnet_union.safetensors")
check("the drawing is read once", len(g["ContinuityGuideFrames"]), 1)
check("...as the still's own canvas", len(g["MiniMaxH3FunControlNetApply"]), 1)
check("the strength is the switch's",
      g["MiniMaxH3FunControlNetApply"][0][1]["strength"], 0.8)

# What the sampler is handed. The branch goes on the conditioning, so the model
# reaching the sampler is the segment's own — which is what keeps the preview
# override and everything else on that side untouched.
guided_graph = still(guided_still()).expand
sampler = by_class(guided_graph)["KSampler"][0][1]
check("the sampler is aimed at the branch's conditioning",
      guided_graph[sampler["positive"][0]]["class_type"],
      "MiniMaxH3FunControlNetApply")

# The two halves, each alone. Same pair the video path holds: a drawing with the
# switch off must not load six gigabytes of branch, and a switch thrown with
# nothing attached has nothing to aim at.
off = by_class(still(guided_still(guide={"on": False, "strength": 0.8})).expand)
check("a drawing with the switch off loads no branch", "ControlNetLoader" in off, False)
check("...and reads no drawing", "ContinuityGuideFrames" in off, False)

bare = by_class(still(still_blob(request={
    "models": GUIDE_MODELS, "guide": {"on": True}})).expand)
check("the switch alone loads no branch", "ControlNetLoader" in bare, False)

# And the drawing stays out of the segment node's cache key: it reaches the
# model through a branch bolted on after that node, so re-tracing it must not
# re-encode the prompt.
guided_data = by_class(still(guided_still()).expand)["MiniMaxH3TimelineSegment"][0][1]["segment_data"]
check("the guide is not in the segment's cache key",
      "gde-1" in guided_data, False)


# The slice node itself. Two tokens out of however many went in, whichever one
# was asked for, and the copy is a copy rather than a view onto the clip.
import torch  # noqa: E402 — after the boot, like everything else in this file

_clip = torch.arange(3, dtype=torch.float32).view(1, 1, 3, 1, 1).expand(1, 24, 3, 4, 6)
_slice = ps.MiniMaxH3StillLatent.execute({"samples": _clip.contiguous()}, 0)
check("the slice is a two-token clip", tuple(_slice.result[0]["samples"].shape),
      (1, 24, 2, 4, 6))
check("...of the frame that was asked for, twice",
      [float(_slice.result[0]["samples"][0, 0, t, 0, 0]) for t in (0, 1)], [0.0, 0.0])
_last = ps.MiniMaxH3StillLatent.execute({"samples": _clip.contiguous()}, -1)
check("a negative index counts from the end",
      [float(_last.result[0]["samples"][0, 0, t, 0, 0]) for t in (0, 1)], [2.0, 2.0])

# Only the routed checkpoint is loaded, exactly as on a video render — and the
# audio VAE is not loaded at all, because nothing here cites sound.
check("a bare prompt loads FL2VA and nothing else",
      [i["unet_name"] for _, i in h3["UNETLoader"]], [H3_MODELS["fl2va"]])
check("one VAE, the video one the shot is decoded by",
      [i["vae_name"] for _, i in h3["VAELoader"]], [H3_MODELS["vae"]])
check("the text encoder is loaded as H3's",
      (h3["CLIPLoader"][0][1]["clip_name"], h3["CLIPLoader"][0][1]["type"]),
      (H3_MODELS["clip"], "minimax"))
check("the segment node gets no audio VAE",
      "audio_vae" in h3["MiniMaxH3TimelineSegment"][0][1], False)

sampler = h3["KSampler"][0][1]
check("the sampler settings arrive verbatim",
      (sampler["seed"], sampler["steps"], sampler["cfg"], sampler["sampler_name"],
       sampler["denoise"]),
      (7, 20, 1.0, "res_multistep", 1.0))

# The shortest legal clip, and the canvas a video render would use.
payload = json.loads(h3["MiniMaxH3TimelineSegment"][0][1]["segment_data"])
check("it samples the shortest legal clip",
      cs.latent_frames(round(payload["request"]["duration_s"] * 24)), 2)
check("on H3's own canvas",
      (payload["request"]["short_edge"], payload["request"]["aspect"]), (768, "16:9"))
check("it lands in H3's stills folder",
      h3["MiniMaxH3SaveImage"][0][1]["filename_prefix"], outputs.default_image("h3", "H3"))

# The standing route, the video nodes' own control: Ref2VA takes the text-only
# payload FL2VA was trained for, so a t2i still can be made by the reference
# weights — and then FL2VA is neither loaded nor required.
routed = by_class(still(still_blob(request={
    "models": {**{k: v for k, v in H3_MODELS.items() if k != "fl2va"}, "route": "ref2va"}})).expand)
check("a forced route loads that checkpoint and no other",
      [i["unet_name"] for _, i in routed["UNETLoader"]], [H3_MODELS["ref2va"]])
check("and it reaches the segment node as the request's own pin",
      json.loads(routed["MiniMaxH3TimelineSegment"][0][1]["segment_data"])["request"]["checkpoint"],
      "ref2va")
# Forcing FL2VA on a still with references is honoured — the slot names an
# input, not a training, and merges of the two checkpoints exist.
forced_refs = by_class(still(still_blob(request={
    "assets": [{"handle": "img-1", "kind": "image", "role": "reference",
                "filename": "face.png"}],
    "models": {**H3_MODELS, "route": "fl2va"}})).expand)
check("forcing FL2VA on a still with references loads that input",
      [i["unet_name"] for _, i in forced_refs["UNETLoader"]], [H3_MODELS["fl2va"]])

# References route to Ref2VA and are the video node's own — including a clip
# taken with its soundtrack, which is the one thing that loads the audio VAE.
refs = by_class(still(still_blob(request={"assets": [
    {"handle": "img-1", "kind": "image", "role": "reference", "filename": "face.png"},
    {"handle": "vid-1", "kind": "video", "role": "reference", "filename": "clip.mp4",
     "track": "picture+sound"},
]})).expand)
check("references route to Ref2VA",
      [i["unet_name"] for _, i in refs["UNETLoader"]], [H3_MODELS["ref2va"]])
check("a cited soundtrack loads the audio VAE",
      sorted(i["vae_name"] for _, i in refs["VAELoader"]),
      sorted([H3_MODELS["vae"], H3_MODELS["audio_vae"]]))
check("and hands it to the segment node",
      "audio_vae" in refs["MiniMaxH3TimelineSegment"][0][1], True)

silent = by_class(still(still_blob(request={"assets": [
    {"handle": "vid-1", "kind": "video", "role": "reference", "filename": "clip.mp4"},
]})).expand)
check("a clip cited for its picture alone loads no audio VAE",
      [i["vae_name"] for _, i in silent["VAELoader"]], [H3_MODELS["vae"]])

# Keyframes are the video node's too: a start frame and an end frame, with the
# canvas adapting to the start frame exactly as a shot's does. The size lookup
# is stubbed because these two files are not on this machine — it is the only
# thing on this path that touches the disk.
media = importlib.import_module(f"{PACKAGE}.creator.media")
real_image_size = media.image_size
media.image_size = lambda filename: (1920, 1080)
try:
    frames = by_class(still(still_blob(request={"assets": [
        {"handle": "img-1", "kind": "image", "role": "first_frame", "filename": "open.png"},
        {"handle": "img-2", "kind": "image", "role": "last_frame", "filename": "close.png"},
    ]})).expand)
finally:
    media.image_size = real_image_size
frames_payload = json.loads(frames["MiniMaxH3TimelineSegment"][0][1]["segment_data"])
check("both keyframes reach the request",
      sorted((a["role"], a["filename"]) for a in frames_payload["request"]["assets"]),
      [("first_frame", "open.png"), ("last_frame", "close.png")])

# The preview is the video node's, patched on the model the segment hands out.
preview = by_class(still(still_blob(
    request={"models": {**H3_MODELS, "preview": "taeh3.safetensors"}})).expand)
check("taeh3 previews the still",
      "ModelPreviewOverrideKJ" in preview or comfy_nodes.NODE_CLASS_MAPPINGS.get(
          "ModelPreviewOverrideKJ") is None, True)

# ---- refusals ----------------------------------------------------------------

expect_error("a latent frame the clip does not have is refused",
             lambda: still(still_blob(minimax={"latent_index": 4})),
             "2 latent frames")
expect_error("a still with no VAE is refused, naming the folder",
             lambda: still(still_blob(request={
                 "models": {k: v for k, v in H3_MODELS.items() if k != "vae"}})),
             "models/vae")
# A keyframe and a reference share a still generation now: the frame rides as
# a pinned guide on Ref2VA, exactly as it does in a video segment. The size
# lookup is stubbed like the keyframe test above — the adaptive canvas is the
# one thing on this path that touches the disk.
media.image_size = lambda filename: (1920, 1080)
try:
    mixed_still = by_class(still(still_blob(request={"assets": [
        {"handle": "img-1", "kind": "image", "role": "first_frame", "filename": "open.png"},
        {"handle": "img-2", "kind": "image", "role": "reference", "filename": "face.png"},
    ]})).expand)
finally:
    media.image_size = real_image_size
check("a keyframe and a reference share the still, on Ref2VA",
      [i["unet_name"] for _, i in mixed_still["UNETLoader"]], [H3_MODELS["ref2va"]])

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

check("no preview node when the pack is not installed",
      ("ModelPreviewOverrideKJ" in kinds, "ModelPreviewOverrideKJ" in ideo),
      (False, False))


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
    # conditional branch carries the late-cfg drop — the override goes under
    # both, for the same reason.
    previewed_ideo = by_class(build(blob(arch="ideogram4"), steps=20, cfg=7.0).expand)
    ideo_patch = previewed_ideo["ModelPreviewOverrideKJ"]
    check("one preview patch on an Ideogram render", len(ideo_patch), 1)
    check("...on the conditional model, under the cfg drop",
          previewed_ideo["CFGOverride"][0][1]["model"][0], ideo_patch[0][0])
    check("...and not on the unconditional one",
          previewed_ideo["DualModelGuider"][0][1]["model_negative"][0],
          [i for i, _ in previewed_ideo["UNETLoader"]
           if _["unet_name"] == MODELS["ideogram4"]["uncond_model"]][0])
finally:
    comfy_nodes.NODE_CLASS_MAPPINGS.clear()
    comfy_nodes.NODE_CLASS_MAPPINGS.update(_restore_preview)

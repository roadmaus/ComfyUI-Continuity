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
               "Ideogram4Scheduler", "TextEncodeQwenImageEditPlus", "ModelSamplingFlux"):
    check(f"no {absent} in a bare t2i render", absent in kinds, False)

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
check("it lands in the pre-stage folder, which is its own",
      save_inputs["filename_prefix"], outputs.IMAGE_PREFIX)


def save_prefix(**overrides):
    """Where a blob's still would land."""
    return by_class(build(blob(**overrides)).expand)["MiniMaxH3SaveImage"][0][1]["filename_prefix"]


# The blob decides where the file goes, and a blob that says nothing gets the
# default above. This is the whole output-structure control: before it, the
# prefix was a module constant and every install on earth wrote its stills to
# the same folder with no way to say otherwise.
check("a blob's own prefix is used instead",
      save_prefix(output_prefix="my-project/stills/take"), "my-project/stills/take")
check("a trailing slash means a folder, and keeps the default's stem",
      save_prefix(output_prefix="my-project/"), "my-project/prestage")
check("an empty prefix falls back to the default rather than the output root",
      save_prefix(output_prefix="   "), outputs.IMAGE_PREFIX)
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
check("turbo loads the Turbo checkpoint",
      [i["unet_name"] for _, i in turbo["UNETLoader"]], [MODELS["krea2"]["turbo_model"]])
check("turbo changes nothing structural",
      sorted(turbo), sorted(kinds))
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
check("the sampler reads the patch",
      with_lora["KSampler"][0][1]["model"][0], loras[0][0])
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
     "aspect": "1:1", "short_edge": 1024})
check("the payload carries the init", init_payload.init,
      {"filename": "seed.png", "denoise": 0.6})

render_mod = importlib.import_module(f"{PACKAGE}.creator.render")
ri = importlib.import_module(f"{PACKAGE}.creator.render_image")

i2i_graph = ri.emit(init_payload, ri.ImageWeights(arch="krea2", files=MODELS["krea2"]),
                    render_mod.Sampling(seed=1, steps=52, cfg=3.5,
                                        sampler_name="euler", scheduler="simple"), NODE_ID)
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
# references in its image slots, the method node on its conditioning, and the
# shift moved onto ModelSamplingFlux — none of which appears without refs.

refs_payload = ci.compile_prestage(
    {"arch": "krea2", "prompt": "p", "refs": [{"filename": "a.png"}, {"filename": "b.png"}],
     "aspect": "1:1", "short_edge": 1024})
refs = by_class(ri.emit(refs_payload, ri.ImageWeights(arch="krea2", files=MODELS["krea2"]),
                        render_mod.Sampling(), NODE_ID).finalize())
encode = refs["TextEncodeQwenImageEditPlus"][0][1]
check("both references sit in the encoder's image slots",
      ("image1" in encode, "image2" in encode, "image3" in encode),
      (True, True, False))
check("the encoder also gets the VAE for the reference latents",
      encode["vae"][0] in {nid for nid, _ in refs["VAELoader"]}, True)
check("the reference method is the official one",
      refs["FluxKontextMultiReferenceLatentMethod"][0][1]["reference_latents_method"],
      "index_timestep_zero")
check("the shift moves onto ModelSamplingFlux on this branch",
      (refs["ModelSamplingFlux"][0][1]["max_shift"], refs["ModelSamplingFlux"][0][1]["base_shift"]),
      (1.15, 0.5))
check("no plain text encode on the reference branch", "CLIPTextEncode" in refs, False)

expect_error("a fourth reference is refused",
             lambda: ci.compile_prestage(
                 {"arch": "krea2", "prompt": "p",
                  "refs": ["a.png", "b.png", "c.png", "d.png"]}),
             "three image slots")

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
check("the conditional branch carries the late-cfg drop",
      (override[1]["cfg"], override[1]["start_percent"], override[1]["end_percent"]),
      (3.0, 0.7, 1.0))
check("...and the guider reads it as its conditional model",
      guider["model"][0], override[0])
check("the text encoder is loaded as Ideogram's",
      ideo["CLIPLoader"][0][1]["type"], "ideogram4")

# The quality preset owns mu/std, not the user.
quality = by_class(build(blob(arch="ideogram4", quality="quality"), steps=48).expand)
check("the quality preset reshapes the schedule",
      (quality["Ideogram4Scheduler"][0][1]["mu"], quality["Ideogram4Scheduler"][0][1]["std"]),
      (0.0, 1.5))

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
     "aspect": "1:1", "short_edge": 1024})
ideo_i2i = by_class(ri.emit(ideo_i2i_payload,
                            ri.ImageWeights(arch="ideogram4", files=MODELS["ideogram4"]),
                            render_mod.Sampling(steps=20, cfg=7.0, sampler_name="euler"),
                            NODE_ID).finalize())
check("i2i keeps the tail of the sigmas",
      ideo_i2i["SplitSigmasDenoise"][0][1]["denoise"], 0.5)
check("the sampler reads the truncated schedule",
      ideo_i2i["SamplerCustomAdvanced"][0][1]["sigmas"][0],
      ideo_i2i["SplitSigmasDenoise"][0][0])

# ---- refusals ----------------------------------------------------------------

expect_error("Ideogram with references is refused with directions",
             lambda: build(blob(arch="ideogram4", refs=["a.png"])),
             "switch the model pill to Krea 2")
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
    "vae": "minimax_h3_t1_image_vae_step1597.safetensors",
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
check("no audio is decoded", "VAEDecodeAudio" in h3, False)
check("and no video is written", "MiniMaxH3Save" in h3, False)

# Only the routed checkpoint is loaded, exactly as on a video render — and the
# audio VAE is not loaded at all, because nothing here cites sound.
check("a bare prompt loads FL2VA and nothing else",
      [i["unet_name"] for _, i in h3["UNETLoader"]], [H3_MODELS["fl2va"]])
check("one VAE, the single-image one",
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
check("it lands in the pre-stage folder",
      h3["MiniMaxH3SaveImage"][0][1]["filename_prefix"], outputs.IMAGE_PREFIX)

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

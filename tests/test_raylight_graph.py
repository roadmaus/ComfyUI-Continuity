"""What the multi-GPU backend emits, and everything it refuses to emit.

Nothing here needs two cards, Ray, or the fork installed. What is being checked
is the *graph*: which nodes a Ray render builds, what is wired to what, and —
the larger half of the file — that every feature this backend cannot carry is
refused by name before a single node exists rather than quietly dropped from the
render. See `creator/raylight.py` for the argument behind each refusal.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_raylight_graph.py

The Raylight classes below are stand-ins carrying the fork's *real*
`INPUT_TYPES`, copied from <https://github.com/Karmabu/raylight>, for the reason
`test_accel.py`'s stand-ins do: this pack reads defaults and option lists back
off whatever is installed, so what has to be pinned is that the reading works
against the shape the fork actually declares.

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
ray = importlib.import_module(f"{PACKAGE}.creator.raylight")

from harness import FAILURES, check, passed


def expect_error(label, fn, fragment):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        if fragment not in str(exc):
            FAILURES.append(f"{label}: error {str(exc)!r} does not mention {fragment!r}")
    else:
        FAILURES.append(f"{label}: expected an error mentioning {fragment!r}, got none")


# ---- stand-ins for the installed fork ---------------------------------------


class FakeInitializer:
    """`RayInitializerAdvanced.INPUT_TYPES`, verbatim but for the tooltips.

    Nineteen inputs, fifteen of them required with a default — which is the
    whole reason `raylight._defaults` reads them off the class instead of
    carrying a copy. Two of them this pack sets and the rest it must pass
    through untouched.
    """

    FUNCTION = "spawn_actor"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "ray_cluster_address": ("STRING", {"default": "local"}),
                "ray_cluster_namespace": ("STRING", {"default": "default"}),
                "GPU": ("INT", {"default": 2}),
                "GPU_SELECT": ("STRING", {"default": ""}),
                "ulysses_degree": ("INT", {"default": 2}),
                "ring_degree": ("INT", {"default": 1}),
                "clear_vram_after_sampling": ("BOOLEAN", {"default": False}),
                "cfg_degree": ("INT", {"default": 1}),
                "dp_degree": ("INT", {"default": 1, "min": 0}),
                "sync_ulysses": ("BOOLEAN", {"default": False}),
                "FSDP": ("BOOLEAN", {"default": False}),
                "FSDP_CPU_OFFLOAD": ("BOOLEAN", {"default": False}),
                # `yunchang.kernels.AttnType`'s members. Which ones a build
                # offers is its own business, which is why `attention_option`
                # matches rather than names.
                "XFuser_attention": (
                    ["TORCH", "TORCH_FLASH", "FA", "FA3", "SAGE_FP16", "SAGE_FP8"],
                    {"default": "TORCH_FLASH"}),
                "skip_comm_test": ("BOOLEAN", {"default": False}),
                "use_mmap": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "ray_object_store_gb": ("FLOAT", {"default": 2.0}),
                "ray_dashboard_address": ("STRING", {"default": "None"}),
                "torch_dist_address": ("STRING", {"default": "127.0.0.1:29500"}),
            },
        }


class FakeUNETLoader:
    FUNCTION = "load_ray_unet"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "unet_name": (["h3/fl2va.safetensors"],),
                "weight_dtype": (["default", "fp8_e4m3fn", "fp8_e4m3fn_fast",
                                  "fp8_e5m2", "bf16", "fp16"],),
                "ray_actors_init": ("RAY_ACTORS_INIT",),
            },
            "optional": {"lora": ("RAY_LORA", {"default": None})},
        }


class FakeGGUFLoader:
    FUNCTION = "load_ray_unet"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "unet_name": (["h3/fl2va-Q8_0.gguf"],),
                "dequant_dtype": (["default", "target", "float32", "float16",
                                   "bfloat16"], {"default": "default"}),
                "patch_dtype": (["default", "target", "float32", "float16",
                                 "bfloat16"], {"default": "default"}),
                "ray_actors_init": ("RAY_ACTORS_INIT",),
            },
            "optional": {"lora": ("RAY_LORA", {"default": None})},
        }


class FakeLoraLoader:
    FUNCTION = "load_lora"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "lora_name": (["turbo.safetensors", "look.safetensors"],),
                "strength_model": ("FLOAT", {"default": 1.0}),
            },
            "optional": {"prev_ray_lora": ("RAY_LORA", {"default": None})},
        }


class FakeNode:
    """Everything else the fork registers that this pack only ever emits.

    A class has to exist for the expansion to name it, and none of these are
    read for defaults — the inputs we pass them are all ours.
    """

    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}}


class FakePreview:
    """KJNodes' override, trimmed to the inputs `models.graph_preview` reads."""

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


FORK = {
    ray.INIT_NODE: FakeInitializer,
    ray.UNET_NODE: FakeUNETLoader,
    ray.GGUF_NODE: FakeGGUFLoader,
    ray.LORA_NODE: FakeLoraLoader,
    ray.SHIFT_NODE: FakeNode,
    ray.SCHEDULER_NODE: FakeNode,
    ray.GUIDER_NODE: FakeNode,
    ray.SAMPLER_NODE: FakeNode,
    ray.K3U_EXPORT_NODE: FakeNode,
    ray.K3U_IMPORT_NODE: FakeNode,
}


def install(**extra):
    """Put the fork (and anything else asked for) in the registry."""
    comfy_nodes.NODE_CLASS_MAPPINGS.update(FORK)
    comfy_nodes.NODE_CLASS_MAPPINGS.update(extra)


def uninstall(*node_ids):
    for node_id in node_ids or tuple(FORK):
        comfy_nodes.NODE_CLASS_MAPPINGS.pop(node_id, None)


# ---- the render -------------------------------------------------------------

MODELS = {
    "fl2va": "h3/fl2va.safetensors",
    "ref2va": "h3/ref2va.safetensors",
    "clip": "h3/text_encoder.safetensors",
    "vae": "h3/video_vae.safetensors",
    "audio_vae": "h3/audio_vae.safetensors",
}

NODE_ID = "7"


def blob(models=None, **overrides):
    data = {
        "version": 1,
        "prompt": "a red room",
        "assets": [],
        "loras": [],
        "duration_s": 6,
        "aspect": "16:9",
        "short_edge": 768,
        # Two cards, which is the arrangement this exists for.
        "models": {**MODELS, "backend": "raylight", "gpus": 2, **(models or {})},
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


def build(data=None, node=None, **overrides):
    node = node or cn.MiniMaxH3Creator
    kwargs = dict(
        creator_data=data if data is not None else blob(),
        seed=100, steps=20, cfg=1.0, sampler_name="res_multistep", scheduler="simple",
    )
    kwargs.update(overrides)
    return with_id(node, NODE_ID, lambda: node.execute(**kwargs))


def by_class(graph):
    out = {}
    for node_id, node in graph.items():
        out.setdefault(node["class_type"], []).append((node_id, node["inputs"]))
    return out


UPSCALE_MODELS = {
    "dit": "ltx/dit.safetensors",
    "clip": "ltx/gemma4-with-proj.safetensors",
    "vae": "ltx/video-vae.safetensors",
    "audio_vae": "ltx/audio-vae.safetensors",
    "ic_lora": "ltx-2.5-22b-ic-lora-x2.safetensors",
}


def strip_build(segments=None, **extra):
    """A Timeline render of a Ray strip. -> the expansion.

    The route is forced, because the workers hold one transformer and a strip
    whose shots reach for both checkpoints is refused before anything else can
    be — which would make it the answer to every question asked below.
    """
    models = extra.pop("models", MODELS)
    data = json.dumps({
        "version": 2,
        "prompt": "a red room",
        "aspect": "16:9",
        "short_edge": 768,
        "models": {**models, "backend": "raylight", "gpus": 2, "route": "ref2va"},
        "segments": segments or [{"prompt": "wide", "duration_s": 5}],
        **extra,
    })
    return with_id(cn.MiniMaxH3Timeline, NODE_ID,
                   lambda: cn.MiniMaxH3Timeline.execute(
                       timeline_data=data, seed=100, steps=20, cfg=1.0,
                       sampler_name="res_multistep", scheduler="simple")).expand


install()
expansion = build().expand
kinds = by_class(expansion)

# ---- the switch itself ------------------------------------------------------

check("the fork reads as installed", ray.available(), True)

# ---- what is loaded, and where ----------------------------------------------
#
# The whole point: the checkpoint is opened inside the workers from a filename,
# so the loader that would have opened it on this card must not be built. A
# UNETLoader here is a second copy of an H3 transformer in the driver's VRAM
# that nothing samples with.

check("no core UNETLoader on a Ray render", "UNETLoader" in kinds, False)
check("one Ray initializer", len(kinds[ray.INIT_NODE]), 1)
check("one Ray checkpoint loader", len(kinds[ray.UNET_NODE]), 1)

init_id, init_inputs = kinds[ray.INIT_NODE][0]
check("it asks for the cards the blob asked for", init_inputs["GPU"], 2)
check("...and splits the sequence across all of them",
      init_inputs["ulysses_degree"], 2)
check("the fork's own defaults are passed through untouched",
      (init_inputs["ring_degree"], init_inputs["cfg_degree"],
       init_inputs["FSDP"], init_inputs["XFuser_attention"]),
      (1, 1, False, "TORCH_FLASH"))
check("...including the ones it declares optional rather than required",
      "ray_object_store_gb" in init_inputs, False)

loader_id, loader_inputs = kinds[ray.UNET_NODE][0]
check("the workers load the checkpoint the mode routes to",
      loader_inputs["unet_name"], MODELS["fl2va"])
check("...at the precision the blob picked", loader_inputs["weight_dtype"], "default")
check("...off the initializer", loader_inputs["ray_actors_init"][0], init_id)
check("no LoRA is hung on it when the piece has none",
      "lora" in loader_inputs, False)

# Everything that is *not* the transformer still loads here, because everything
# that is not the transformer still runs here: the prompt is encoded on this
# card and both VAEs decode on it.
check("the text encoder is still loaded on this side of the wire",
      kinds["CLIPLoader"][0][1]["clip_name"], MODELS["clip"])
check("both VAEs too",
      sorted(i["vae_name"] for _, i in kinds["VAELoader"]),
      sorted([MODELS["vae"], MODELS["audio_vae"]]))

# ---- the segment node -------------------------------------------------------

segment_id, segment_inputs = kinds["MiniMaxH3TimelineSegment"][0]
check("the segment is told which backend it is under",
      segment_inputs.get("sampler_backend"), "raylight")
for socket in ("model_fl2va", "model_ref2va"):
    check(f"...and is handed no {socket!r}", socket in segment_inputs, False)
check("it still encodes the prompt on this card",
      segment_inputs["clip"][0], kinds["CLIPLoader"][0][0])

# ---- the sampler ------------------------------------------------------------

check("nothing samples through core's KSampler", "KSampler" in kinds, False)
check("one distributed sampler", len(kinds[ray.SAMPLER_NODE]), 1)

sampled_id, sampled = kinds[ray.SAMPLER_NODE][0]
check("it starts from the segment's latent", sampled["latent_image"][0], segment_id)
check("...with the noise it was given the seed for",
      (sampled["add_noise"], sampled["noise_seed"]), (True, 100))

guider_id, guider = kinds[ray.GUIDER_NODE][0]
check("the guider is what the sampler runs", sampled["guider"][0], guider_id)
check("...on the segment's own conditioning", guider["positive"][0], segment_id)
check("...against a zeroed negative, as every H3 pass is",
      expansion[guider["negative"][0]]["class_type"], "ConditioningZeroOut")
check("...at the row's cfg", guider["cfg"], 1.0)

scheduler_id, scheduler = kinds[ray.SCHEDULER_NODE][0]
check("the sigmas are the run's own", sampled["sigmas"][0], scheduler_id)
check("...for the whole schedule",
      (scheduler["steps"], scheduler["scheduler"], scheduler["denoise"]),
      (20, "simple", 1.0))
check("the sampler kernel is core's own pick",
      kinds["KSamplerSelect"][0][1]["sampler_name"], "res_multistep")

# The guider, the scheduler and the export all take the actors, and all three
# have to take the *same* ones — a second initializer would be a second Ray
# cluster, and a chain that forked would sample on a model nothing patched.
check("the guider and the scheduler share one set of actors",
      guider["ray_actors"], scheduler["ray_actors"])

# ---- the reel is unchanged --------------------------------------------------
#
# The latent that comes back out of the workers is an ordinary one, which is the
# whole reason the rest of the render never learns anything was distributed.

reel_id, reel = kinds["MiniMaxH3Reel"][0]
check("the reel decodes what the workers sampled", reel["samples"][0], sampled_id)
check("...with the video VAE loaded here",
      expansion[reel["vae"][0]]["class_type"], "VAELoader")
check("one save node, as ever", len(kinds["MiniMaxH3Save"]), 1)

# ---- the LoRA stack ---------------------------------------------------------
#
# Merged inside the workers by the fork's own loader, through ComfyUI's patcher
# rather than through `h3lora`. That is the one thing this backend does
# differently without refusing, and the switch's own tooltip says so.

stacked = by_class(build(blob(loras=[
    {"name": "look.safetensors", "strength": 0.8, "enabled": True},
    {"name": "turbo.safetensors", "strength": 1.0, "enabled": True},
])).expand)
loras = stacked[ray.LORA_NODE]
check("one Ray LoRA node per enabled file", len(loras), 2)
check("the first carries the first file",
      (loras[0][1]["lora_name"], loras[0][1]["strength_model"]),
      ("look.safetensors", 0.8))
check("...and nothing before it", "prev_ray_lora" in loras[0][1], False)
check("the second hangs off the first",
      loras[1][1]["prev_ray_lora"][0], loras[0][0])
check("and the chain reaches the checkpoint loader",
      stacked[ray.UNET_NODE][0][1]["lora"][0], loras[1][0])

disabled = by_class(build(blob(loras=[
    {"name": "look.safetensors", "strength": 1.0, "enabled": False}])).expand)
check("a switched-off file is not sent to the workers",
      ray.LORA_NODE in disabled, False)

# The modality dial is `h3lora`'s and has no counterpart in a merge, so a file
# wearing one is refused rather than merged at full strength into the soundtrack
# it was turned down off.
expect_error(
    "an audio-damped LoRA is refused rather than quietly merged whole",
    lambda: build(blob(loras=[{"name": "look.safetensors", "strength": 1.0,
                               "enabled": True, "audio": 0.2}])),
    "audio dial")

# ---- a quantized checkpoint -------------------------------------------------

gguf = by_class(build(blob({"fl2va": "h3/fl2va-Q8_0.gguf"})).expand)
check("a GGUF pick goes to the fork's GGUF loader instead",
      (ray.GGUF_NODE in gguf, ray.UNET_NODE in gguf), (True, False))
check("...at the pack's own dequant defaults, not at ours",
      (gguf[ray.GGUF_NODE][0][1]["dequant_dtype"],
       gguf[ray.GGUF_NODE][0][1]["patch_dtype"]),
      ("default", "default"))
check("...and carries no weight_dtype, whose answer quantizing already gave",
      "weight_dtype" in gguf[ray.GGUF_NODE][0][1], False)

uninstall(ray.GGUF_NODE)
expect_error("a GGUF pick without city96's pack beside the fork says so",
             lambda: build(blob({"fl2va": "h3/fl2va-Q8_0.gguf"})),
             "ComfyUI-GGUF")
install()

# ---- the preview bridge -----------------------------------------------------
#
# Without KJNodes there is no bridge and no picture, which is the same trade the
# single-GPU path makes: the render is identical either way.

check("no K3U bridge without the preview pack",
      ray.K3U_EXPORT_NODE in kinds, False)

comfy_nodes.NODE_CLASS_MAPPINGS["ModelPreviewOverrideKJ"] = FakePreview
try:
    previewed = by_class(build(blob({"preview": "taeh3.safetensors"})).expand)
    export_id, export_inputs = previewed[ray.K3U_EXPORT_NODE][0]
    patch_id, patch_inputs = previewed["ModelPreviewOverrideKJ"][0]
    import_id, import_inputs = previewed[ray.K3U_IMPORT_NODE][0]
    check("the bridge exports a stand-in model from the actors",
          export_inputs["ray_actors"][0], previewed[ray.UNET_NODE][0][0])
    check("KJNodes wraps that stand-in exactly as it wraps a real model",
          patch_inputs["model"][0], export_id)
    check("...decoding through the tiny VAE the piece picked",
          patch_inputs["tiny_vae"], "taeh3.safetensors")
    check("and the wrapper comes back as a context the sampler runs",
          previewed[ray.SAMPLER_NODE][0][1]["k3u_adapter_context"][0], import_id)
    check("...off the model KJNodes patched",
          import_inputs["model"][0], patch_id)
    # The guider must be built from the actors the bridge handed back, not from
    # the ones that went in: the adapter attaches itself on the way through.
    check("the guider samples the actors the bridge returned",
          previewed[ray.GUIDER_NODE][0][1]["ray_actors"], [import_id, 1])
finally:
    comfy_nodes.NODE_CLASS_MAPPINGS.pop("ModelPreviewOverrideKJ", None)

# ---- the sigma shift --------------------------------------------------------
#
# The one model patch that survives, because the fork ships it as a patch on the
# actors — core's own node, run in the workers.

check("no shift node at the checkpoints' own schedule",
      ray.SHIFT_NODE in kinds, False)
shifted = by_class(build(blob(), shift_video=8.0).expand)
check("one shift on the actors when the pills leave it",
      len(shifted[ray.SHIFT_NODE]), 1)
check("...carrying both numbers",
      (shifted[ray.SHIFT_NODE][0][1]["shift_video"],
       shifted[ray.SHIFT_NODE][0][1]["shift_audio"]), (8.0, 3.0))
check("...and the sampler runs downstream of it",
      shifted[ray.GUIDER_NODE][0][1]["ray_actors"][0],
      shifted[ray.SHIFT_NODE][0][0])
check("core's own MODEL-side shift is not emitted",
      "MiniMaxH3SigmaShift" in shifted, False)

# ---- one strip, one cluster -------------------------------------------------
#
# Every shot on a strip asks for the actors and every one of them gets the first
# ask's: a second initializer would be a second Ray cluster, and a second loader
# would reload the checkpoint across every card between shots.

STRIP = json.dumps({
    "version": 2,
    "prompt": "a red room",
    "aspect": "16:9",
    "short_edge": 768,
    "models": {**MODELS, "backend": "raylight", "gpus": 2, "route": "ref2va"},
    "segments": [
        {"prompt": "wide", "duration_s": 5},
        {"prompt": "closer", "duration_s": 5},
        {"prompt": "wider again", "duration_s": 5},
    ],
})

strip = by_class(with_id(
    cn.MiniMaxH3Timeline, NODE_ID,
    lambda: cn.MiniMaxH3Timeline.execute(
        timeline_data=STRIP, seed=100, steps=20, cfg=1.0,
        sampler_name="res_multistep", scheduler="simple")).expand)
check("three shots", len(strip["MiniMaxH3TimelineSegment"]), 3)
check("...one Ray cluster", len(strip[ray.INIT_NODE]), 1)
check("...loading the checkpoint once", len(strip[ray.UNET_NODE]), 1)
check("...and three sampling runs on it", len(strip[ray.SAMPLER_NODE]), 3)
check("the forced route is what the workers loaded",
      strip[ray.UNET_NODE][0][1]["unet_name"], MODELS["ref2va"])

# ---- what a Ray render refuses ----------------------------------------------
#
# The larger half. Every one of these is a feature this pack has and the workers
# cannot carry, and the alternative to refusing is a render that silently comes
# out different from the one the switch was thrown on. The sentence has to name
# the thing to turn off — a refusal nobody can act on is a wall.

expect_error("the fork missing is said with somewhere to get it",
             lambda: (uninstall(ray.INIT_NODE), build())[-1],
             "github.com/Karmabu/raylight")
install()

expect_error(
    "a device pin and Ray are two answers to the same question",
    lambda: build(blob({"devices": {"clip": "cuda:1"}})),
    "ComfyUI-MultiGPU")

expect_error(
    "both checkpoints in one render would reload between shots",
    lambda: with_id(cn.MiniMaxH3Timeline, NODE_ID,
                    lambda: cn.MiniMaxH3Timeline.execute(
                        timeline_data=json.dumps({
                            "version": 2, "prompt": "x", "aspect": "16:9",
                            "short_edge": 768,
                            "models": {**MODELS, "backend": "raylight", "gpus": 2},
                            "segments": [
                                {"prompt": "wide", "duration_s": 5},
                                {"prompt": "with a reference", "duration_s": 5,
                                 "assets": [{"handle": "img-1", "kind": "image",
                                             "role": "reference",
                                             "filename": "a.png"}]},
                            ]}),
                        seed=100, steps=20, cfg=1.0,
                        sampler_name="res_multistep", scheduler="simple")),
    "one transformer")

# The guide is the one that would not have failed: it rides on the conditioning,
# so it reaches the workers intact and is then dropped, because the fork's
# parallel forward replaces the one place core reads `control`. Full speed, no
# error, and a render that ignored the drawing.
expect_error(
    "a ControlNet guide would be silently ignored, so it is refused",
    lambda: strip_build(
        guide={"on": True, "strength": 0.8, "start": 0.0, "end": 0.7},
        models={**MODELS, "control": "h3/fun_controlnet_union.safetensors"},
        segments=[{"prompt": "wide", "duration_s": 5,
                   "assets": [{"handle": "gde-1", "kind": "video",
                               "role": "guide", "op": "edges",
                               "filename": "control/edges.mp4"}]}]),
    "ControlNet guide")

# The passes that sample in-process against a real model. Each is a switch on
# the piece and each says so by name — a refusal nobody can act on is a wall.
expect_error(
    "the two-pass upscale cannot be sampled in the workers",
    lambda: build(blob(short_edge=1152)),
    "two-pass upscale")

expect_error(
    "nor the face pass",
    lambda: build(blob({"sam3": "sam3.safetensors"},
                       face={"on": True, "canvas": 512, "denoise": 0.45})),
    "face pass")

expect_error(
    "nor the re-detail pass",
    lambda: strip_build(upscale="redetail", upscale_models=UPSCALE_MODELS),
    "re-detail pass")

# The soundtrack carried across a cut. The tail is anchored by a wrapper around
# the forward, and a wrapper here never reaches the workers — so the sound would
# be read as an imitation reference instead of a continuation.
expect_error(
    "a sound seam is refused rather than quietly turned into a reference",
    lambda: strip_build(segments=[
        {"prompt": "wide", "duration_s": 5},
        {"prompt": "closer", "duration_s": 5,
         "continue": True, "continue_audio": True}]),
    "sound seam")
check("...where a picture-only seam sails through on a core that anchors itself",
      len(by_class(strip_build(segments=[
          {"prompt": "wide", "duration_s": 5},
          {"prompt": "closer", "duration_s": 5, "continue": True},
      ]))[ray.SAMPLER_NODE]), 2)

# The turbo lead-in wants the same weights loaded twice with different adapters
# on them, and the workers hold one model.
settings_mod = importlib.import_module(f"{PACKAGE}.creator.settings")
was = settings_mod.turbo_lead_in
settings_mod.turbo_lead_in = lambda: 2
try:
    turbo = blob(
        loras=[{"name": "turbo.safetensors", "strength": 0.6, "enabled": True}],
        turbo={"lora": "turbo.safetensors", "on": True, "quality": "medium"})
    expect_error("the turbo lead-in needs two models resident and is refused",
                 lambda: build(turbo, steps=6), "turbo lead-in")
    settings_mod.turbo_lead_in = lambda: 0
    check("...and with the lead-in at zero the same piece renders",
          len(by_class(build(turbo, steps=6).expand)[ray.SAMPLER_NODE]), 1)
finally:
    settings_mod.turbo_lead_in = was

for switch, value, fragment in (
        ("block_cache", "fast", "step cache"),
        ("spectrum", True, "Spectrum"),
        ("chunk_ffn", True, "chunked feed-forward"),
        ("fp16_accumulation", True, "fp16 accumulation"),
        ("attention", "kitchen", "kitchen attention")):
    expect_error(f"the {switch} accelerator is refused rather than dropped",
                 lambda switch=switch, value=value: build(**{switch: value}),
                 fragment)

# Sage is the one that survives, because Raylight picks its own kernel and the
# fork's list says which name to ask for.
saged = by_class(build(attention="sage").expand)
check("sage attention moves onto the initializer",
      saged[ray.INIT_NODE][0][1]["XFuser_attention"], "SAGE_FP16")
check("...and emits no model patch of ours",
      "MiniMaxH3MemoryEfficientSageAttentionPatch" in saged, False)

passed("all Raylight graph tests passed")

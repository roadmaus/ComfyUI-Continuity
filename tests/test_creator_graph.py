"""What `MiniMaxH3Creator.execute` wires up, and that it agrees with the Timeline.

The Creator owns its sampler now, so like the Timeline it returns a subgraph
rather than tensors and the thing worth checking is the graph. Nothing is
sampled — the expansion can be inspected without a model or a denoising step.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_creator_graph.py

The load-bearing case is the last one: a Creator render and a one-segment
one-pass timeline must emit the *same* graph. That is the whole claim behind
`render.py` existing, and it is the assertion that fails if either node grows a
private copy of the wiring.

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
    return importlib.import_module(PACKAGE), nodes


try:
    package, comfy_nodes = _boot()
except Exception as exc:  # noqa: BLE001
    print(f"skipped: ComfyUI not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)

cn = importlib.import_module(f"{PACKAGE}.creator_node")
accel_mod = importlib.import_module(f"{PACKAGE}.accel")
tl = importlib.import_module(f"{PACKAGE}.timeline")
outputs_mod = importlib.import_module(f"{PACKAGE}.outputs")
settings_mod = importlib.import_module(f"{PACKAGE}.settings")
render_mod = importlib.import_module(f"{PACKAGE}.render")

from harness import FAILURES, check


def expect_error(label, fn, fragment):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        if fragment not in str(exc):
            FAILURES.append(f"{label}: error {str(exc)!r} does not mention {fragment!r}")
    else:
        FAILURES.append(f"{label}: expected an error mentioning {fragment!r}, got none")


# The node has no sockets at all now: the weights are named in the blob and the
# loaders are built inside the subgraph. Filenames rather than links, and never
# checked against the disk — `models.py` only writes them into a loader's widget.
MODELS = {
    "fl2va": "h3/fl2va.safetensors",
    "ref2va": "h3/ref2va.safetensors",
    "clip": "h3/text_encoder.safetensors",
    "vae": "h3/video_vae.safetensors",
    "audio_vae": "h3/audio_vae.safetensors",
    "preview": "taeh3.safetensors",
}

DATA = json.dumps({
    "version": 1,
    "prompt": "a red room",
    "assets": [],
    "loras": [],
    "duration_s": 6,
    "aspect": "16:9",
    "short_edge": 768,
    "models": MODELS,
})

NODE_ID = "7"


def build(data=DATA, **overrides):
    kwargs = dict(
        creator_data=data,
        seed=100, steps=20, cfg=1.0, sampler_name="res_multistep", scheduler="simple",
    )
    kwargs.update(overrides)
    # `unique_id` reaches `execute` as a hidden input, which only the executor
    # fills in. Stamped by hand here so the save node gets the display id it
    # would get in a real run — that link is the whole reason the node can show
    # its own result, and a test that skipped it would not notice it break.
    return with_id(cn.MiniMaxH3Creator, NODE_ID, lambda: cn.MiniMaxH3Creator.execute(**kwargs))


def with_id(node_class, unique_id, run):
    """Run `run()` with the node's hidden `unique_id` filled in.

    Constructed rather than `HiddenHolder.from_dict`, whose keys are `Hidden`
    enum members and not the plain names.
    """
    from comfy_api.latest import io as comfy_io

    previous = node_class.hidden
    node_class.hidden = comfy_io.HiddenHolder(
        unique_id=unique_id, prompt=None, extra_pnginfo=None, dynprompt=None,
        auth_token_comfy_org=None, api_key_comfy_org=None)
    try:
        return run()
    finally:
        node_class.hidden = previous


def by_class(graph):
    out = {}
    for node_id, node in graph.items():
        out.setdefault(node["class_type"], []).append((node_id, node["inputs"]))
    return out


out = build()
graph = out.expand
kinds = by_class(graph)

# The node has no output sockets, so the expansion exports no links — but that
# has to be an empty tuple and not `None`, which is what `NodeOutput` gives for
# no values. `execution.py` takes `len()` of this to find the exported links,
# and a bare `NodeOutput(expand=...)` fails the whole prompt there.
check("expansion exports no links", out.result, ())

# One generation is one of everything, and none of the chaining machinery: a
# Creator render has no seam, so a last-frame or audio-tail node in here would
# be a node that can never do anything. It still makes a reel — of one pass,
# which is the same shape the save node takes from a strip.
check("one segment node", len(kinds["MiniMaxH3TimelineSegment"]), 1)
check("one sampler", len(kinds["KSampler"]), 1)
check("one reel node, which is where the decode happens", len(kinds["MiniMaxH3Reel"]), 1)
check("...so nothing decodes into the graph", "VAEDecode" in kinds, False)
for absent in ("MiniMaxH3PassFrames", "MiniMaxH3PassAudio"):
    check(f"no {absent} in a single render", absent in kinds, False)

# ---- the loaders ------------------------------------------------------------
#
# The node has no model sockets, so the graph has to build its own. The claim
# worth pinning is the one that saves real VRAM: this is a T2VA render, which
# routes to FL2VA, so the Ref2VA weights must not be loaded at all. Both used to
# be wired and both used to load, every queue.

check("one UNETLoader, not two", len(kinds["UNETLoader"]), 1)
check("...for the checkpoint the mode routes to",
      kinds["UNETLoader"][0][1]["unet_name"], MODELS["fl2va"])
check("the text encoder is loaded as H3's",
      (kinds["CLIPLoader"][0][1]["clip_name"], kinds["CLIPLoader"][0][1]["type"]),
      (MODELS["clip"], "minimax"))
check("both VAEs are loaded",
      sorted(i["vae_name"] for _, i in kinds["VAELoader"]),
      sorted([MODELS["vae"], MODELS["audio_vae"]]))

# The segment node takes the loaders' outputs, which are links exactly as the
# old sockets' raw_links were — a loaded object as a literal input value hashes
# as Unhashable and would miss the cache on every queue.
segment_id, segment_inputs = kinds["MiniMaxH3TimelineSegment"][0]
loader_ids = {node_id for node_id, _ in
              kinds["UNETLoader"] + kinds["CLIPLoader"] + kinds["VAELoader"]}
for socket in ("clip", "model_fl2va"):
    value = segment_inputs.get(socket)
    if not (isinstance(value, list) and len(value) == 2 and value[0] in loader_ids):
        FAILURES.append(f"segment input {socket!r} is not a link to a loader: {value!r}")
check("the checkpoint nothing routes to is not wired either",
      "model_ref2va" in segment_inputs, False)
# Both VAEs are built above (the decodes need them), but a T2VA render encodes
# no picture and no sound, so neither is wired into the *encoder*: they load at
# decode, after sampling, where they no longer take room the DiT wanted. This is
# the same VRAM claim the checkpoint routing makes, carried onto the VAEs.
for socket in ("vae", "audio_vae"):
    check(f"the encoder is handed no {socket!r} on a text-only render",
          socket in segment_inputs, False)
check("the reel node still reads the video VAE loader to decode with",
      graph[kinds["MiniMaxH3Reel"][0][1]["vae"][0]]["class_type"], "VAELoader")
check("...and the audio one",
      graph[kinds["MiniMaxH3Reel"][0][1]["audio_vae"][0]]["class_type"], "VAELoader")

# ---- the tail ---------------------------------------------------------------
#
# The node has no outputs either: it saves the render itself. The display-id
# stamp is what puts the result back on the node the user is looking at, and
# without it the `executed` message lands on an expanded node on nobody's canvas.

check("nothing comes out of the node", out.args, ())
check("one save node", len(kinds["MiniMaxH3Save"]), 1)
save_id, save_inputs = kinds["MiniMaxH3Save"][0]
check("it is reported against the node that built it",
      graph[save_id].get("override_display_id"), NODE_ID)
check("it saves a reel", graph[save_inputs["reel"][0]]["class_type"], "MiniMaxH3Reel")
reel_inputs = graph[save_inputs["reel"][0]]["inputs"]
check("the reel decodes the sampler's own latent",
      graph[reel_inputs["samples"][0]]["class_type"], "KSampler")
check("...and writes it out untrimmed, there being no seam to share",
      [k for k in reel_inputs if k in ("head", "tail")], [])
check("one pass has nothing in front of it on the reel", "reel" in reel_inputs, False)
check("at the rate the frame count was snapped to", save_inputs["fps"], 24.0)
# Read once, here, and carried into the graph as an input — a save node that
# read the preference itself would be a cache hit on a re-queue and would keep
# writing the quality it was built with. See `render.emit_tail`.
check("at the quality this ComfyUI is set to",
      save_inputs["crf"], settings_mod.video_crf())
check("it lands in the render folder, which is not the stills folder",
      save_inputs["filename_prefix"], outputs_mod.VIDEO_PREFIX)


def save_prefix(**overrides):
    """Where a blob's finished clip would land."""
    return by_class(build(json.dumps({**json.loads(DATA), **overrides})).expand
                    )["MiniMaxH3Save"][0][1]["filename_prefix"]


# The output-structure control. Before it the prefix was a module constant, so
# every install wrote every render it ever made into one folder.
check("a blob's own prefix is used instead",
      save_prefix(output_prefix="my-project/scene-a/take"), "my-project/scene-a/take")
check("a trailing slash means a folder, and keeps the default's stem",
      save_prefix(output_prefix="my-project/"), "my-project/H3")
# Core expands these in `get_save_image_path`; they pass through untouched,
# which is what makes a dated folder per render a thing you can just type.
check("date tokens are core's to expand, not ours to eat",
      save_prefix(output_prefix="minimax/%year%-%month%-%day%/H3"),
      "minimax/%year%-%month%-%day%/H3")
# Refused while the graph is built, not by get_save_image_path once the clip has
# already been sampled — that failure costs the user the whole render.
expect_error("a prefix that climbs out of the output folder",
             lambda: save_prefix(output_prefix="../../../H3"),
             "'.' and '..' are not allowed")
expect_error("an absolute prefix, pointed at the flag that does work",
             lambda: save_prefix(output_prefix="/mnt/big/renders"),
             "--output-directory")

# The payload is a segment payload with nothing in front of it. It carries a
# canvas like every other payload does — a lone generation goes through
# `timeline_payloads` exactly as a strip does, and that is where the one
# geometry every pass is held to gets stamped on. What it is stamped *with* is
# the answer this generation would have worked out for itself; the adaptive
# cases are asserted below.
payload = json.loads(segment_inputs["segment_data"])
check("the payload carries the request",
      sorted(payload), ["canvas", "continue", "continue_audio", "request"])
check("nothing to continue from", (payload["continue"], payload["continue_audio"]), (False, False))
check("the request is the creator blob", payload["request"]["prompt"], "a red room")

# Sampler settings arrive verbatim, and the seed is not offset — there is only
# one generation to give a seed to.
sampler = kinds["KSampler"][0][1]
check("the seed is used as given", sampler["seed"], 100)
check("the sampler settings arrive verbatim",
      (sampler["steps"], sampler["cfg"], sampler["sampler_name"], sampler["scheduler"], sampler["denoise"]),
      (20, 1.0, "res_multistep", "simple", 1.0))

# ---- prompt_override --------------------------------------------------------
#
# It has no socket any more, but a hand-written blob may still carry one, and it
# has to reach the segment node through the payload — that string is the node's
# cache key, so an override kept anywhere else would change the prompt without
# re-running the generation.

hand_written = json.loads(DATA)
hand_written["prompt_override"] = "<Picture 1> hand-written"
overridden = json.loads(
    by_class(build(json.dumps(hand_written)).expand)
    ["MiniMaxH3TimelineSegment"][0][1]["segment_data"])
check("the override rides in the payload",
      overridden.get("prompt_override"), "<Picture 1> hand-written")
check("...and changes the cache key",
      overridden["prompt_override"] != payload.get("prompt_override"), True)

# ---- weights ----------------------------------------------------------------
#
# A file nobody picked is refused before anything is queued, naming the field and
# the folder to fix it in — the same contract the missing-checkpoint error had
# when these were sockets.

def without(field):
    blob = json.loads(DATA)
    del blob["models"][field]
    return json.dumps(blob)


expect_error("a missing checkpoint is refused up front",
             lambda: build(without("fl2va")),
             "models/diffusion_models")
expect_error("...and names the generation that needed it",
             lambda: build(without("fl2va")),
             "This generation routes to it")
expect_error("a missing text encoder is refused too",
             lambda: build(without("clip")),
             "models/text_encoders")
# The reference checkpoint is not needed by a text-only render and must not be
# demanded by one — that is the whole point of only emitting what is routed to.
check("an unrouted checkpoint is not required",
      "UNETLoader" in by_class(build(without("ref2va")).expand), True)

# ---- the route --------------------------------------------------------------
#
# The two checkpoints are one architecture trained twice, and Ref2VA takes the
# text-only and keyframe payloads FL2VA was trained for. `route` says so once for
# the whole node, where the per-request `checkpoint` pin says it for one
# generation and does not survive the mode changing under it.

def routed(route, data=DATA):
    blob = json.loads(data)
    blob["models"]["route"] = route
    return json.dumps(blob)


# This request is T2VA, which derives fl2va. Forced the other way, the reference
# weights are what gets loaded — and the FL2VA ones are not loaded at all.
forced = by_class(build(routed("ref2va")).expand)
check("a forced route overrides what the mode derived",
      [i["unet_name"] for _, i in forced["UNETLoader"]], [MODELS["ref2va"]])
check("...and the segment is wired to that checkpoint",
      "model_ref2va" in forced["MiniMaxH3TimelineSegment"][0][1], True)
check("...and not to the other one",
      "model_fl2va" in forced["MiniMaxH3TimelineSegment"][0][1], False)

# It reaches the segment through the payload, because that string is the node's
# cache key: a route kept anywhere else would change which weights ran without
# re-running the generation.
check("the route rides in the payload",
      json.loads(forced["MiniMaxH3TimelineSegment"][0][1]["segment_data"])["request"]["checkpoint"],
      "ref2va")
check("...which changes the cache key",
      forced["MiniMaxH3TimelineSegment"][0][1]["segment_data"] != segment_inputs["segment_data"],
      True)

# Forcing it the other way round is honoured too: the slot names an input, not
# a training, and merges of the two checkpoints exist — the pin says what the
# user loaded there.
with_refs = json.loads(DATA)
with_refs["assets"] = [{"handle": "img-1", "kind": "image", "role": "reference",
                        "filename": "a.png"}]
check("forcing FL2VA onto a reference generation is honoured",
      [i["unet_name"] for _, i in
       by_class(build(routed("fl2va", json.dumps(with_refs))).expand)["UNETLoader"]],
      [MODELS["fl2va"]])
# ...but forcing Ref2VA onto one is a no-op rather than an error.
check("forcing Ref2VA onto a reference generation is fine",
      [i["unet_name"] for _, i in
       by_class(build(routed("ref2va", json.dumps(with_refs))).expand)["UNETLoader"]],
      [MODELS["ref2va"]])

check("auto is what it always was",
      [i["unet_name"] for _, i in by_class(build(routed("auto")).expand)["UNETLoader"]],
      [MODELS["fl2va"]])
# A route only names one checkpoint, so the other one being unset cannot stop it.
check("a forced route does not require the checkpoint it skips",
      [i["unet_name"] for _, i in
       by_class(build(routed("ref2va", without("fl2va"))).expand)["UNETLoader"]],
      [MODELS["ref2va"]])

# ---- devices ----------------------------------------------------------------
#
# ComfyUI-MultiGPU registers a subclass of each core loader taking the identical
# inputs plus `device`, so putting one field on another card is a class swap and
# one argument. The pack is absent in this harness, which makes both halves worth
# pinning: nothing pinned must emit the *core* loaders, and something pinned
# without the pack must refuse rather than silently load everything on one card.

models_mod = importlib.import_module(f"{PACKAGE}.models")


def on_device(**pins):
    blob = json.loads(DATA)
    blob["models"]["devices"] = pins
    return json.dumps(blob)


check("no MultiGPU loaders when nothing is pinned",
      [k for k in kinds if k.endswith("MultiGPU")], [])
expect_error("a pinned device without the pack is refused up front",
             lambda: build(on_device(clip="cuda:1")),
             "ComfyUI-MultiGPU")
expect_error("...naming the device that was asked for",
             lambda: build(on_device(clip="cuda:1")),
             "cuda:1")


class _FakeMultiGPU:
    """Stands in for one of the pack's wrappers. Only `INPUT_TYPES` matters —
    `models.device_options` reads the device list back off it rather than
    importing the pack, the same way `accel.node_defaults` does."""

    FUNCTION = "override"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}, "optional": {"device": (["cpu", "cuda:0", "cuda:1"],
                                                        {"default": "cuda:0"})}}


_restore = dict(comfy_nodes.NODE_CLASS_MAPPINGS)
for wrapper in ("UNETLoaderMultiGPU", "CLIPLoaderMultiGPU", "VAELoaderMultiGPU"):
    comfy_nodes.NODE_CLASS_MAPPINGS[wrapper] = _FakeMultiGPU
try:
    check("the device list comes from the installed pack",
          models_mod.device_options(), ["cpu", "cuda:0", "cuda:1"])

    # The real case: the text encoder on the second card, everything else where
    # ComfyUI would have put it.
    split = by_class(build(on_device(clip="cuda:1")).expand)
    check("the pinned field uses the pack's loader", len(split["CLIPLoaderMultiGPU"]), 1)
    check("...on the device it was pinned to",
          split["CLIPLoaderMultiGPU"][0][1]["device"], "cuda:1")
    check("...with the core loader's arguments unchanged",
          (split["CLIPLoaderMultiGPU"][0][1]["clip_name"], split["CLIPLoaderMultiGPU"][0][1]["type"]),
          (MODELS["clip"], "minimax"))
    check("an unpinned field stays on the core loader",
          "CLIPLoader" in split, False)
    check("...and so does everything else",
          sorted(k for k in split if k.endswith("Loader") or k.endswith("MultiGPU")),
          ["CLIPLoaderMultiGPU", "UNETLoader", "VAELoader"])

    # The two VAEs are separate loaders, so they can sit on separate cards —
    # which is the only reason they are not one node with two outputs.
    both = by_class(build(on_device(vae="cuda:0", audio_vae="cpu")).expand)
    check("each VAE takes its own device",
          sorted(i["device"] for _, i in both["VAELoaderMultiGPU"]), ["cpu", "cuda:0"])
finally:
    comfy_nodes.NODE_CLASS_MAPPINGS.clear()
    comfy_nodes.NODE_CLASS_MAPPINGS.update(_restore)

check("no device list without the pack", models_mod.device_options(), [])

# ---- GGUF checkpoints -------------------------------------------------------
#
# ComfyUI-GGUF's loaders take the same filename input and return the same links,
# so a quantized checkpoint is a class swap keyed off the picked file's own
# extension — no mode, no setting. What is worth pinning: the swap happens on a
# `.gguf` name and only then, `weight_dtype` (a core-loader widget the GGUF
# nodes do not have) is not emitted with it, and picking one without the pack
# refuses up front naming it, exactly as a pinned device without MultiGPU does.
# The harness boots with custom nodes off, so the refusal path runs unaided.


def with_gguf(**files):
    blob = json.loads(DATA)
    blob["models"].update(files)
    return json.dumps(blob)


GGUF_UNET = "h3/fl2va-Q4_K_M.gguf"
GGUF_CLIP = "h3/text_encoder-Q8_0.gguf"

expect_error("a GGUF checkpoint without the pack is refused up front",
             lambda: build(with_gguf(fl2va=GGUF_UNET)),
             "ComfyUI-GGUF")
expect_error("...naming the file that asked for it",
             lambda: build(with_gguf(fl2va=GGUF_UNET)),
             GGUF_UNET)


class _FakeGGUF:
    """Stands in for the pack's loaders — only their registration matters, the
    emitter writes filenames into widgets and never instantiates them."""

    FUNCTION = "load"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}}


_restore_gguf = dict(comfy_nodes.NODE_CLASS_MAPPINGS)
for gguf_node in ("UnetLoaderGGUF", "CLIPLoaderGGUF"):
    comfy_nodes.NODE_CLASS_MAPPINGS[gguf_node] = _FakeGGUF
try:
    quant = by_class(build(with_gguf(fl2va=GGUF_UNET)).expand)
    check("a .gguf checkpoint loads through the pack's loader",
          len(quant["UnetLoaderGGUF"]), 1)
    check("...by its filename",
          quant["UnetLoaderGGUF"][0][1]["unet_name"], GGUF_UNET)
    check("...without weight_dtype, which is the core loader's widget",
          "weight_dtype" in quant["UnetLoaderGGUF"][0][1], False)
    check("...and no core UNETLoader beside it", "UNETLoader" in quant, False)
    check("a safetensors text encoder stays on the core loader",
          len(quant["CLIPLoader"]), 1)

    both = by_class(build(with_gguf(fl2va=GGUF_UNET, clip=GGUF_CLIP)).expand)
    check("a .gguf text encoder swaps its loader the same way",
          both["CLIPLoaderGGUF"][0][1]["clip_name"], GGUF_CLIP)
    check("...keeping the H3 clip type",
          both["CLIPLoaderGGUF"][0][1]["type"], "minimax")

    # The two swaps compose: a quantized checkpoint pinned to a card goes
    # through MultiGPU's subclass of the *GGUF* loader, not of the core one.
    comfy_nodes.NODE_CLASS_MAPPINGS["UnetLoaderGGUFMultiGPU"] = _FakeMultiGPU
    blob = json.loads(with_gguf(fl2va=GGUF_UNET))
    blob["models"]["devices"] = {"fl2va": "cuda:1"}
    pinned = by_class(build(json.dumps(blob)).expand)
    check("a pinned .gguf checkpoint composes both swaps",
          pinned["UnetLoaderGGUFMultiGPU"][0][1],
          {"unet_name": GGUF_UNET, "device": "cuda:1"})
finally:
    comfy_nodes.NODE_CLASS_MAPPINGS.clear()
    comfy_nodes.NODE_CLASS_MAPPINGS.update(_restore_gguf)

# The one file nothing can quantize: a `.gguf` VAE has no loader in the pack
# either, and the refusal says so rather than KeyError-ing.
expect_error("a .gguf VAE is refused as unloadable",
             lambda: build(with_gguf(vae="h3/video_vae.gguf")),
             "nothing loads a GGUF VAE")

# ---- the preview override ---------------------------------------------------
#
# KJNodes' node is optional in the way the accelerators are optional, except that
# a missing one is not even a warning: the render is identical and core's own
# previews still carry this node's id. The harness boots with custom nodes off,
# so the absent path is the one that runs here unaided.

check("no preview node when the pack is not installed",
      "ModelPreviewOverrideKJ" in kinds, False)
check("the sampler reads the segment directly without it",
      kinds["KSampler"][0][1]["model"][0], segment_id)


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


_restore = dict(comfy_nodes.NODE_CLASS_MAPPINGS)
comfy_nodes.NODE_CLASS_MAPPINGS["ModelPreviewOverrideKJ"] = _FakePreview
try:
    preview_kinds = by_class(build().expand)
    patches = preview_kinds["ModelPreviewOverrideKJ"]
    check("one preview patch", len(patches), 1)
    check("it decodes through the chosen tiny VAE", patches[0][1]["tiny_vae"], MODELS["preview"])
    # Asking for more frames than the latent can hold is what puts KJNodes on its
    # full-clip decode path — see models.PREVIEW_FRAMES. A smaller number does not
    # preview less of the clip, it previews the opening of it on a loop, so this
    # is the difference between watching the video and watching its first moment.
    check("it decodes the whole clip rather than the head of it",
          patches[0][1]["preview_frames"], models_mod.PREVIEW_FRAMES)
    check("it plays at the render's own rate", patches[0][1]["preview_fps"], models_mod.PREVIEW_FPS)
    # The decision behind that number, rather than the number: the full-clip path
    # only opens if the count clears the *latent's* length, which is roughly five
    # rows per seventeen frames and not the frame count itself. The longest legal
    # generation is what it has to clear. Written as the bound so that retuning
    # either end shows up as a real failure rather than as a literal nobody
    # remembered to change — which is exactly how this check came to be here.
    from comfy_extras.nodes_minimax_h3 import video_latent_t

    from Minimax_creator import canvas as canvas_mod
    longest = video_latent_t(max(canvas_mod.legal_frame_counts()))
    check("and asks for enough to cover the longest generation's latent",
          models_mod.PREVIEW_FRAMES >= longest, True)
    # Read off the installed class rather than carried here, the way accel.py
    # reads its packs' defaults — a knob the pack retunes must not go stale.
    # (1024 here is the fake pack's own default, and only coincidentally the same
    # number as PREVIEW_FRAMES above.)
    check("the pack's own default survives for anything we do not set",
          patches[0][1]["max_resolution"], 1024)
    check("the sampler reads the patch",
          preview_kinds["KSampler"][0][1]["model"][0], patches[0][0])

    # No decoder picked is the same as no pack installed: nothing is emitted.
    check("no preview node without a decoder to use",
          "ModelPreviewOverrideKJ" in by_class(build(without("preview")).expand), False)
finally:
    comfy_nodes.NODE_CLASS_MAPPINGS.clear()
    comfy_nodes.NODE_CLASS_MAPPINGS.update(_restore)

# ---- accelerators -----------------------------------------------------------

check("no accelerator nodes by default",
      [k for k in kinds if k in (accel_mod.BLOCK_CACHE_NODE, accel_mod.SPECTRUM_NODE,
                                 accel_mod.SAGE_NODE)], [])
check("the sampler reads the segment directly when off",
      sampler["model"][0], segment_id)

expect_error("a missing pack is refused up front",
             lambda: build(spectrum=True),
             "xmarre/ComfyUI-Spectrum-MiniMax-H3")


class _FakePack:
    FUNCTION = "apply"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"model": ("MODEL",),
                             "mode": (["H3 Safe — 0.08", "H3 Fast — 0.10"], {"default": "H3 Fast — 0.10"})}}


class _FakeSage:
    """KJNodes' sage patch as the V3 shim declares it: `model` and nothing else."""

    FUNCTION = "EXECUTE_NORMALIZED"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"model": ["MODEL", {}]}}


_restore = dict(comfy_nodes.NODE_CLASS_MAPPINGS)
comfy_nodes.NODE_CLASS_MAPPINGS[accel_mod.BLOCK_CACHE_NODE] = _FakePack
try:
    accel_kinds = by_class(build(block_cache="fast").expand)
    patches = accel_kinds[accel_mod.BLOCK_CACHE_NODE]
    accel_segment = accel_kinds["MiniMaxH3TimelineSegment"][0][0]
    check("one accelerator patch", len(patches), 1)
    check("the patch reads the segment", patches[0][1]["model"][0], accel_segment)
    check("the sampler reads the patch",
          accel_kinds["KSampler"][0][1]["model"][0], patches[0][0])
    check("conditioning still comes from the segment",
          accel_kinds["KSampler"][0][1]["positive"][0], accel_segment)

    # Sage in the same graph as a cache, which is the arrangement the ordering
    # rule is about: kijai's node reads the segment and the cache reads *it*.
    comfy_nodes.NODE_CLASS_MAPPINGS[accel_mod.SAGE_NODE] = _FakeSage
    sage_kinds = by_class(build(block_cache="fast", sage=True).expand)
    sage_patch = sage_kinds[accel_mod.SAGE_NODE]
    check("one sage patch", len(sage_patch), 1)
    check("sage reads the segment",
          sage_patch[0][1]["model"][0], sage_kinds["MiniMaxH3TimelineSegment"][0][0])
    check("sage is built with model alone", list(sage_patch[0][1]), ["model"])
    check("the cache reads sage",
          sage_kinds[accel_mod.BLOCK_CACHE_NODE][0][1]["model"][0], sage_patch[0][0])
finally:
    comfy_nodes.NODE_CLASS_MAPPINGS.clear()
    comfy_nodes.NODE_CLASS_MAPPINGS.update(_restore)

expect_error("sage without KJNodes is refused up front",
             lambda: build(sage=True),
             "kijai/ComfyUI-KJNodes")

# ---- the Creator is a one-segment timeline ----------------------------------
#
# The claim `render.py` exists for. Both nodes are handed the same request at the
# same duration and canvas, and must emit the same graph — same node classes,
# same wiring, same payload. If either grows its own copy of the loop, this is
# what notices.

timeline_data = json.dumps({
    "version": 2,
    "render": "single",
    "prompt": "",
    "aspect": "16:9",
    "short_edge": 768,
    "models": MODELS,
    "segments": [{"prompt": "a red room", "assets": [], "loras": [], "duration_s": 6}],
})
tl_out = with_id(cn.MiniMaxH3Timeline, NODE_ID, lambda: cn.MiniMaxH3Timeline.execute(
    timeline_data=timeline_data,
    seed=100, steps=20, cfg=1.0, sampler_name="res_multistep", scheduler="simple"))
tl_kinds = by_class(tl_out.expand)

check("both nodes emit the same node classes",
      sorted(tl_kinds), sorted(kinds))
check("both emit one of each",
      {k: len(v) for k, v in sorted(tl_kinds.items())},
      {k: len(v) for k, v in sorted(kinds.items())})

tl_segment = tl_kinds["MiniMaxH3TimelineSegment"][0][1]
tl_payload = json.loads(tl_segment["segment_data"])

# Compared after compiling, not before. The two payloads legitimately differ in
# the raw prompt string — `single_payload` assembles the shot list itself and
# writes `[Shot 1]` in, where the Creator hands over the bare sentence and
# `contextir.compose` marks it during the compile. What has to be identical is
# what the DiT is actually handed, which is downstream of both.
compiler = importlib.import_module(f"{PACKAGE}.compile")
media = importlib.import_module(f"{PACKAGE}.media")

creator_compiled = compiler.compile_segment(payload, media.image_size)
timeline_compiled = compiler.compile_segment(tl_payload, media.image_size)
for field in ("prompt", "mode", "checkpoint", "frames", "seconds", "width", "height"):
    check(f"both compile the same {field}",
          getattr(timeline_compiled, field), getattr(creator_compiled, field))
def loader_files(kinds):
    """What each node's expansion actually loads, as filenames rather than ids —
    the node ids differ between two expansions and the files must not."""
    return {
        "unet": sorted(i["unet_name"] for _, i in kinds["UNETLoader"]),
        "clip": sorted(i["clip_name"] for _, i in kinds["CLIPLoader"]),
        "vae": sorted(i["vae_name"] for _, i in kinds["VAELoader"]),
    }


check("both build the same loaders", loader_files(tl_kinds), loader_files(kinds))
check("both sample identically",
      {k: v for k, v in tl_kinds["KSampler"][0][1].items() if k not in ("model", "positive", "negative", "latent_image")},
      {k: v for k, v in sampler.items() if k not in ("model", "positive", "negative", "latent_image")})

# ---- ...and a version-1 blob is one too --------------------------------------
#
# The same claim, made of the blob rather than of the request: hand the Timeline
# the *Creator's own* `creator_data` — the shape every workflow saved before the
# two nodes became one still holds — and `compile.as_piece` has to lift it into
# the strip that emits exactly the graph the Creator emits from it directly.
#
# This is what says the merge is safe to make. Until the two node classes are
# one, it is the only thing standing between an old workflow and a silently
# different render; after they are one, it is the test that the lift is load-
# bearing rather than decorative.

lifted_out = with_id(cn.MiniMaxH3Timeline, NODE_ID, lambda: cn.MiniMaxH3Timeline.execute(
    timeline_data=DATA,
    seed=100, steps=20, cfg=1.0, sampler_name="res_multistep", scheduler="simple"))
lifted_kinds = by_class(lifted_out.expand)

check("a v1 creator blob emits the same node classes",
      {k: len(v) for k, v in sorted(lifted_kinds.items())},
      {k: len(v) for k, v in sorted(kinds.items())})
check("...loading the same files", loader_files(lifted_kinds), loader_files(kinds))
check("...and sampling the same way",
      {k: v for k, v in lifted_kinds["KSampler"][0][1].items()
       if k not in ("model", "positive", "negative", "latent_image")},
      {k: v for k, v in sampler.items()
       if k not in ("model", "positive", "negative", "latent_image")})

lifted_payload = json.loads(lifted_kinds["MiniMaxH3TimelineSegment"][0][1]["segment_data"])
lifted_compiled = compiler.compile_segment(lifted_payload, media.image_size)
for field in ("prompt", "mode", "checkpoint", "frames", "seconds", "width", "height"):
    check(f"...and compiling the same {field}",
          getattr(lifted_compiled, field), getattr(creator_compiled, field))

# --- the two-pass upscale ----------------------------------------------------
#
# Past the native short edge the render grows a refine pass: a second segment
# node pinned to the target canvas, and a MiniMaxH3RefinePass resuming the first
# sampler's latent. At or under native — every graph above — none of it exists.

canvas_mod = importlib.import_module(f"{PACKAGE}.canvas")
TARGET = canvas_mod.resolve_canvas(16 / 9, 1152)

check("no refine pass at native", "MiniMaxH3RefinePass" in kinds, False)

hires_kinds = by_class(build(data=json.dumps({**json.loads(DATA), "short_edge": 1152})).expand)
hires_graph = {nid: dict(inputs=i, class_type=c) for c, nodes_ in hires_kinds.items()
               for nid, i in nodes_}

check("past native there are two segment nodes",
      len(hires_kinds["MiniMaxH3TimelineSegment"]), 2)
check("...one first-pass sampler", len(hires_kinds["KSampler"]), 1)
check("...and one refine pass", len(hires_kinds["MiniMaxH3RefinePass"]), 1)

refine_inputs = hires_kinds["MiniMaxH3RefinePass"][0][1]
check("the refine pass resumes the first sampler's latent",
      hires_graph[refine_inputs["latent"][0]]["class_type"], "KSampler")
check("...conditioned by the second segment",
      hires_graph[refine_inputs["positive"][0]]["class_type"], "MiniMaxH3TimelineSegment")
check("...at the slider's canvas",
      (refine_inputs["width"], refine_inputs["height"]), TARGET)
check("...with the sampler row's settings and the default refine denoise",
      (refine_inputs["steps"], refine_inputs["sampler_name"], refine_inputs["denoise"]),
      (20, "res_multistep", compiler.DEFAULT_REFINE_DENOISE))

pinned = [json.loads(i["segment_data"]) for _, i in hires_kinds["MiniMaxH3TimelineSegment"]
          if "canvas" in json.loads(i["segment_data"])]
# Both segments carry a canvas: every payload does now, because a lone
# generation compiles through `timeline_payloads` like any other piece and that
# is where the one geometry gets stamped. What matters is which canvas each of
# them is held to — the first samples at the slider's own edge, and only the
# refine pass is pinned to the target it is upscaling to.
check("the first pass samples under the target and the refine pass is at it",
      [(p["canvas"]["width"], p["canvas"]["height"]) for p in pinned],
      [(1344, 768), TARGET])

check("the reel decodes the refined latent, not the first pass's",
      hires_graph[hires_kinds["MiniMaxH3Reel"][0][1]["samples"][0]]["class_type"],
      "MiniMaxH3RefinePass")

direct_kinds = by_class(build(data=json.dumps(
    {**json.loads(DATA), "short_edge": 1152, "upscale": "direct"})).expand)
check("direct past native is the old one-pass graph",
      ("MiniMaxH3RefinePass" in direct_kinds, len(direct_kinds["MiniMaxH3TimelineSegment"])),
      (False, 1))

# --- the turbo lead-in -------------------------------------------------------
#
# One schedule sampled in two sittings: the opening steps on the model with the
# distillation held off it, then the leftover noise to the model that has it.
# The setting is this machine's, so it is patched in rather than typed into the
# blob — and off (the default, and every graph above) none of it exists.

TURBO_DATA = json.dumps({
    **json.loads(DATA),
    "loras": [{"name": "turbo/lightx2v.safetensors", "strength": 0.6},
              {"name": "look/grain.safetensors", "strength": 0.8}],
    "turbo": {"lora": "turbo/lightx2v.safetensors", "on": True, "quality": "medium"},
})

check("a turbo render with the lead-in off is one ordinary sampler",
      [len(by_class(build(data=TURBO_DATA).expand).get(k, []))
       for k in ("KSampler", "KSamplerAdvanced")],
      [1, 0])

was = settings_mod.turbo_lead_in
settings_mod.turbo_lead_in = lambda: 2
try:
    lead_kinds = by_class(build(data=TURBO_DATA, steps=6).expand)
    lead_graph = {nid: dict(inputs=i, class_type=c) for c, nodes_ in lead_kinds.items()
                  for nid, i in nodes_}

    check("the lead-in splits the schedule in two",
          [len(lead_kinds.get(k, [])) for k in ("KSampler", "KSamplerAdvanced")], [0, 2])

    opening, rest = sorted((i for _, i in lead_kinds["KSamplerAdvanced"]),
                           key=lambda i: i["start_at_step"])
    check("the opening steps come first and hand their noise on",
          (opening["add_noise"], opening["start_at_step"], opening["end_at_step"],
           opening["return_with_leftover_noise"]),
          ("enable", 0, 2, "enable"))
    check("...and the rest of the same schedule finishes it without re-noising",
          (rest["add_noise"], rest["start_at_step"], rest["end_at_step"],
           rest["return_with_leftover_noise"]),
          ("disable", 2, 6, "disable"))
    check("both sittings are one run: one seed, one step count, one sampler",
          [(i["noise_seed"], i["steps"], i["sampler_name"], i["cfg"]) for i in (opening, rest)],
          [(100, 6, "res_multistep", 1.0)] * 2)

    # The whole point: the opening steps sample on the segment node's second
    # model output, which is the stack with the distillation left off it.
    segment_id = lead_kinds["MiniMaxH3TimelineSegment"][0][0]
    check("the opening steps run on the lead model, the rest on the distilled one",
          [(i["model"][0], i["model"][1]) for i in (opening, rest)],
          [(segment_id, 3), (segment_id, 0)])
    check("...and the segment node is told which file to hold off it",
          lead_kinds["MiniMaxH3TimelineSegment"][0][1]["hold_lora"],
          "turbo/lightx2v.safetensors")
    check("the reel still decodes the finished latent",
          lead_graph[lead_kinds["MiniMaxH3Reel"][0][1]["samples"][0]]["class_type"],
          "KSamplerAdvanced")

    # A lead-in with nothing to lead: no distillation on the model, or a
    # schedule too short to give steps away from. Both are the ordinary graph,
    # and neither is an error — the switch is simply not in play.
    check("no turbo LoRA engaged is the ordinary graph",
          [len(by_class(build(data=DATA).expand).get(k, []))
           for k in ("KSampler", "KSamplerAdvanced")],
          [1, 0])
    check("a schedule no longer than the lead-in is the ordinary graph",
          [len(by_class(build(data=TURBO_DATA, steps=2).expand).get(k, []))
           for k in ("KSampler", "KSamplerAdvanced")],
          [1, 0])

    off = json.loads(TURBO_DATA)
    off["loras"][0]["enabled"] = False
    check("a distillation this shot switched off is the ordinary graph",
          [len(by_class(build(data=json.dumps(off), steps=6).expand).get(k, []))
           for k in ("KSampler", "KSamplerAdvanced")],
          [1, 0])

    # The second sitting starts with the noise switched off, and a core that
    # builds that noise from the picture alone leaves H3's soundtrack out of it
    # — the first step then dies on a tensor size a hundred seconds in, saying
    # nothing about the lead-in that asked for it (#27). Said here instead,
    # before anything is loaded, and only where a split is actually on: the
    # setting is nobody's problem on a render that runs one sampler.
    core = render_mod.CORE_EMPTY_NOISE_IS_NESTED
    render_mod.CORE_EMPTY_NOISE_IS_NESTED = False
    try:
        expect_error("a core that cannot start a split without noise says so",
                     lambda: build(data=TURBO_DATA, steps=6).expand,
                     "2026-08-11")
        check("...and a render with no split to make is untouched by it",
              [len(by_class(build(data=DATA).expand).get(k, []))
               for k in ("KSampler", "KSamplerAdvanced")],
              [1, 0])
    finally:
        render_mod.CORE_EMPTY_NOISE_IS_NESTED = core
finally:
    settings_mod.turbo_lead_in = was

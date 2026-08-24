"""What an LTX 2.5 piece expands into.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_ltx25_graph.py

Nothing is sampled: the expansion can be read without a model, which is the
whole reason the render loop builds a graph instead of doing the work. What is
worth pinning here is the shape H3's suite cannot see —

- the family's own five sampler nodes rather than one `KSampler`, with the
  scheduler and the model patch fed the same latent and the same shift pair,
- guides cropped exactly once, and on the *unpacked* video latent, because
  slicing frames off a packed AV latent would take them off the soundtrack,
- one transformer and no routing,
- the second stage as Lightricks' x2 latent upscaler rather than a re-sample,
- and the frame grid: 8n+1 at 24 fps, against H3's 17n+5.

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
canvas = importlib.import_module(f"{PACKAGE}.creator.canvas")
compiler = importlib.import_module(f"{PACKAGE}.creator.compile")

from harness import FAILURES, check, passed

MODELS = {
    "dit": "ltx/ltx-2.5-22b-distilled.safetensors",
    "clip": "ltx/gemma4-12b-with-proj.safetensors",
    "vae": "ltx/ltx-2.5-video-vae-bf16.safetensors",
    "audio_vae": "ltx/ltx-2.5-audio-vae-bf16.safetensors",
    "upscaler": "ltx/ltx-2.5-latent-spatial-upscaler-x2.safetensors",
}

NODE_ID = "9"


def piece(**overrides):
    data = {
        "version": 2,
        "family": "ltx25",
        "prompt": "",
        "aspect": "16:9",
        "short_edge": canvas.LTX25.native_short_edge,
        "models": dict(MODELS),
        "segments": [{"prompt": "a red room", "assets": [], "loras": [],
                      "duration_s": 5}],
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


def build(data):
    return with_id(cn.MiniMaxH3Creator, NODE_ID, lambda: cn.MiniMaxH3Creator.execute(
        creator_data=data, seed=100, steps=20, cfg=1.0,
        sampler_name="res_multistep", scheduler="simple"))


def by_class(graph):
    out = {}
    for node_id, node in graph.items():
        out.setdefault(node["class_type"], []).append((node_id, node["inputs"]))
    return out


def expect_error(label, fn, fragment):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        if fragment not in str(exc):
            FAILURES.append(f"{label}: error {str(exc)!r} does not mention {fragment!r}")
    else:
        FAILURES.append(f"{label}: expected an error mentioning {fragment!r}, got none")


# ---- one stage ---------------------------------------------------------------

kinds = by_class(build(piece()).expand)

check("one segment node, and it is LTX's", len(kinds["MiniMaxLTX25Segment"]), 1)
check("...and H3's is nowhere in it", "MiniMaxH3TimelineSegment" in kinds, False)
check("no KSampler — this family samples through a guider",
      "KSampler" in kinds, False)
for node in ("LTXVScheduler", "KSamplerSelect", "ModelSamplingLTXV",
             "LTXVDualCFGGuider", "RandomNoise", "SamplerCustomAdvanced"):
    check(f"one {node}", len(kinds.get(node, [])), 1)

# One transformer: there is nothing to route between, so there is exactly one
# UNETLoader whatever the payload turns out to be.
check("one UNETLoader", len(kinds["UNETLoader"]), 1)
check("...loading the picked transformer",
      kinds["UNETLoader"][0][1]["unet_name"], MODELS["dit"])
check("the text encoder is loaded as LTX's",
      (kinds["CLIPLoader"][0][1]["clip_name"], kinds["CLIPLoader"][0][1]["type"]),
      (MODELS["clip"], "ltxv"))
check("both VAEs are loaded",
      sorted(i["vae_name"] for _, i in kinds["VAELoader"]),
      sorted([MODELS["vae"], MODELS["audio_vae"]]))
# The upscaler is a pass, not a component: a one-stage render must not load it.
check("no upscaler loader on a one-stage render",
      "LatentUpscaleModelLoader" in kinds, False)

# The scheduler and the model patch are two readings of one curve and must be
# given the same numbers off the same latent — letting them disagree is a
# quality bug with nothing in the log to find it by.
sched = kinds["LTXVScheduler"][0][1]
patch = kinds["ModelSamplingLTXV"][0][1]
check("the schedule and the patch share a shift pair",
      (sched["max_shift"], sched["base_shift"]),
      (patch["max_shift"], patch["base_shift"]))
check("...and measure the same latent", sched["latent"], patch["latent"])
segment_id = kinds["MiniMaxLTX25Segment"][0][0]
check("...which is the segment's", sched["latent"], [segment_id, 2])

# The distilled row is what an untouched piece runs: 8 steps at cfg 1/1.
guider = kinds["LTXVDualCFGGuider"][0][1]
check("the distilled schedule", sched["steps"], 8)
check("the distilled scales", (guider["video_cfg"], guider["audio_cfg"]), (1.0, 1.0))

# The crop, exactly once and on the unpacked video latent — slicing frames off
# a packed AV latent would take them off the sound as well.
check("one crop", len(kinds["LTXVCropGuides"]), 1)
crop_latent = kinds["LTXVCropGuides"][0][1]["latent"]
separate_ids = {node_id for node_id, _ in kinds["LTXVSeparateAVLatent"]}
check("...fed by a separate, not by the packed pass", crop_latent[0] in separate_ids, True)
check("...and repacked before the reel", len(kinds["LTXVConcatAVLatent"]), 1)
reel_latent = kinds["MiniMaxH3Reel"][0][1]["samples"]
check("the reel decodes the repacked latent",
      reel_latent[0], kinds["LTXVConcatAVLatent"][0][0])

# The file is written at the family's rate, not at H3's.
check("saved at LTX's frame rate", kinds["MiniMaxH3Save"][0][1]["fps"], 24.0)

# ---- the frame grid ----------------------------------------------------------

payload = json.loads(kinds["MiniMaxLTX25Segment"][0][1]["segment_data"])
one = compiler.compile_segment(payload, family="ltx25")
check("5 s is the card's own 121 frames", one.frames, 121)
check("...on the 8n+1 grid", one.frames % 8, 1)
check("the native canvas is the card's 960x544", (one.width, one.height), (960, 544))

# ---- two stages --------------------------------------------------------------
#
# Past the native edge the piece samples at 544 and the x2 upscaler takes it to
# 1088 — the model decides the factor, not the slider.

two = by_class(build(piece(short_edge=1088)).expand)
check("two sampling passes", len(two["SamplerCustomAdvanced"]), 2)
check("one upscaler loader", len(two["LatentUpscaleModelLoader"]), 1)
check("...loading the picked file",
      two["LatentUpscaleModelLoader"][0][1]["model_name"], MODELS["upscaler"])
check("one upsampler", len(two["LTXVLatentUpsampler"]), 1)
check("the second stage runs a tail of the schedule",
      len(two["SplitSigmasDenoise"]), 1)
# Still exactly one crop: the guides come off between the stages, so the x2
# pass is never spent on frames that are about to be thrown away.
check("the guides are cropped once, before the upscale",
      len(two["LTXVCropGuides"]), 1)
upsampled = two["LTXVLatentUpsampler"][0][1]["samples"]
crop_out = two["LTXVCropGuides"][0][0]
concat_before_upscale = [node_id for node_id, i in two["LTXVConcatAVLatent"]
                         if i["video_latent"][0] == crop_out]
check("...and the upscaler is downstream of that crop",
      upsampled[0] in {node_id for node_id, _ in two["LTXVSeparateAVLatent"]}, True)
check("the cropped pass is repacked before it is unpacked again",
      len(concat_before_upscale), 1)

two_payload = json.loads(two["MiniMaxLTX25Segment"][0][1]["segment_data"])
two_one = compiler.compile_segment(two_payload, family="ltx25")
check("stage one samples at the native edge",
      (two_one.width, two_one.height), (960, 544))
check("stage two is exactly twice it",
      (two_one.refine.width, two_one.refine.height), (1920, 1088))

# ---- the seams, on the 8-grid ------------------------------------------------
#
# The reel and seam layer is core's and family-neutral by construction, which is
# a claim worth one chained strip rather than a comment. What is LTX's about it
# is the *width*: a seam hands the pass in front's last run over as a multi-frame
# guide, and `LTXVAddGuide` crops a guide to the nearest 8n+1 silently — so H3's
# 5-frame blend would arrive as one frame while the reel went on trimming five
# off the head. `canvas.feather_grid` is what stops that, and this is what says
# the graph got the grid's numbers rather than H3's.

FEATHER = canvas.feather_grid(canvas.LTX25)
check("LTX's seam widths are its own frame grid", FEATHER, (1, 9, 17, 25))
check("...and every one of them is a legal guide length",
      [n % 8 for n in FEATHER], [1, 1, 1, 1])

chained = by_class(build(piece(
    prompt="a house at dusk",
    audio_tail_s=1.0,
    segments=[
        {"prompt": "wide", "duration_s": 5, "assets": [], "loras": []},
        {"prompt": "closer", "duration_s": 5, "assets": [], "loras": [],
         "continue": True, "feather": FEATHER[2], "continue_audio": True},
        {"prompt": "cut away", "duration_s": 5, "assets": [], "loras": []},
    ],
)).expand)

check("three passes, three segment nodes", len(chained["MiniMaxLTX25Segment"]), 3)
check("...one sampler each", len(chained["SamplerCustomAdvanced"]), 3)
# The whole strip is one reel: each pass adds itself to the one before it, and
# only the last is handed to the save node.
check("one reel node per pass", len(chained["MiniMaxH3Reel"]), 3)

seamed = [inputs for _, inputs in chained["MiniMaxLTX25Segment"]
          if "prev_image" in inputs]
check("exactly one segment inherits a seam", len(seamed), 1)
check("...and it inherits sound as well as picture",
      "prev_audio" in seamed[0], True)
# The frames come off the *spill*, not out of a second decode — the pass was
# written to disk the moment it decoded, and a seam reads back only its own
# width. Family-neutral: this is core's node either way.
frames = {node_id: inputs for node_id, inputs in chained["MiniMaxH3PassFrames"]}
check("the inherited run is read back off the spill", len(frames), 1)
check("...at the family's own medium width",
      list(frames.values())[0]["count"], FEATHER[2])
check("the segment reads that run", seamed[0]["prev_image"][0] in frames, True)

# ...and the same width is trimmed off the head of the pass that re-generated
# it, so the blended moment plays once.
trimmed = [inputs for _, inputs in chained["MiniMaxH3Reel"] if "head" in inputs]
check("one pass has its head trimmed", len(trimmed), 1)
check("...by exactly what it inherited", trimmed[0]["head"], FEATHER[2])

# The sound crosses on the same instants the picture does: a blended seam sets
# the tail outright rather than taking the piece's setting, which on this family
# is the blend at *its* rate and not H3's.
audio = {node_id: inputs for node_id, inputs in chained["MiniMaxH3PassAudio"]}
check("the sound tail is the blend's own span",
      round(list(audio.values())[0]["seconds"], 4),
      round(FEATHER[2] / canvas.LTX25.fps, 4))

# And the arithmetic underneath: each pass still lands on 8n+1, and the strip
# delivers what it samples less the blend it re-generates.
chained_payloads = [json.loads(inputs["segment_data"])
                    for _, inputs in chained["MiniMaxLTX25Segment"]]
counts = [compiler.compile_segment(p, family="ltx25").frames for p in chained_payloads]
check("every pass is on the grid", sorted(set(n % 8 for n in counts)), [1])
check("...and the strip is the three passes less the blend",
      sum(counts) - FEATHER[2], 3 * 121 - FEATHER[2])

# A width off this family's grid is refused rather than silently cropped to 1.
expect_error("a seam width H3's VAE encodes and LTX's does not is refused",
             lambda: build(piece(segments=[
                 {"prompt": "wide", "duration_s": 5, "assets": [], "loras": []},
                 {"prompt": "closer", "duration_s": 5, "assets": [], "loras": [],
                  "continue": True, "feather": 22},
             ])),
             "a seam can inherit 1, 9, 17, 25 frames")

# ---- what is refused ---------------------------------------------------------

expect_error("a two-stage piece with no upscaler says which pill to change",
             lambda: build(piece(short_edge=1088,
                                 models={k: v for k, v in MODELS.items()
                                         if k != "upscaler"})),
             "no upscaler has been picked")
expect_error("a missing transformer names the folder",
             lambda: build(piece(models={k: v for k, v in MODELS.items()
                                         if k != "dit"})),
             "models/diffusion_models")

# ---- and H3 is untouched -----------------------------------------------------
#
# The same blob without the family field is the piece every saved workflow is,
# and it must still expand to H3's graph.

h3 = by_class(build(json.dumps({
    "version": 2, "prompt": "", "aspect": "16:9", "short_edge": 768,
    "models": {"fl2va": "h3/fl2va.safetensors", "clip": "h3/te.safetensors",
               "vae": "h3/vae.safetensors", "audio_vae": "h3/avae.safetensors"},
    "segments": [{"prompt": "a red room", "assets": [], "loras": [],
                  "duration_s": 5}],
})).expand)
check("a piece naming no family is still H3's",
      ("MiniMaxH3TimelineSegment" in h3, "KSampler" in h3), (True, True))
check("...and is saved at H3's rate", h3["MiniMaxH3Save"][0][1]["fps"], 24.0)

# ---- the listing --------------------------------------------------------------
#
# The weights popover browses one listing for the whole node and picks its rows
# out of it by slot id, so a slot the listing does not carry is a picker that
# offers nothing whatever is on disk. That is what happened the first time this
# family met a machine with the files on it: `dit`, `upscaler` and
# `duration_head` are LTX's names, they were in no table the listing walked, and
# three correctly-placed files came up as "not set".

models_mod = importlib.import_module(f"{PACKAGE}.creator.models")
ltx_slots = importlib.import_module(f"{PACKAGE}.creator.families.ltx25.models")

served = models_mod.every_slot()
for name, slot in ltx_slots.SLOTS.items():
    check(f"the listing carries the {name} slot", served.get(name), slot.folder)
check("...and still carries H3's", set(models_mod.FOLDERS) <= set(served), True)
check("the folders are the ones the model card names",
      [served["dit"], served["clip"], served["vae"], served["upscaler"]],
      ["diffusion_models", "text_encoders", "vae", "latent_upscale_models"])

listed = models_mod.available()
check("every slot gets a file list, even an empty one",
      sorted(listed["files"]), sorted(served))

passed("LTX 2.5 expands to its own sampler, crops its guides once, upscales natively, and seams on its own grid")

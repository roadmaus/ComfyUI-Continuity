"""What an LTX 2.5 piece expands into.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_ltx25_graph.py

Nothing is sampled: the expansion can be read without a model, which is the
whole reason the render loop builds a graph instead of doing the work. What is
worth pinning here is the shape H3's suite cannot see —

- the family's own sampler nodes rather than one `KSampler`, and *which* ones:
  the trained curve as a constant by default, the computed one and the model
  patch that must agree with it where the row asks for them,
- guides cropped exactly once, and on the *unpacked* video latent, because
  slicing frames off a packed AV latent would take them off the soundtrack,
- one transformer and no routing,
- the second stage as Lightricks' x2 latent upscaler rather than a re-sample,
- a still compressed before it conditions anything, which is what this model
  was trained to continue from,
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
ltx_declare = importlib.import_module(f"{PACKAGE}.creator.families.ltx25.declare")
LTX25 = ltx_declare.RULES
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
        "short_edge": LTX25.native_short_edge,
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
for node in ("ManualSigmas", "KSamplerSelect",
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

# **An untouched piece samples on the curve the checkpoint was distilled
# against, and on nothing computed.** Both of Lightricks' 2.5 workflows and
# ComfyUI's own template feed these nine numbers through `ManualSigmas` and emit
# neither `LTXVScheduler` nor `ModelSamplingLTXV`; a schedule of the same length
# through the same endpoints is not a substitute, because the distillation was
# done against this trajectory and not against that shape.
check("the trained curve, verbatim",
      kinds["ManualSigmas"][0][1]["sigmas"], ltx_declare.DISTILLED_SIGMAS)
check("no computed schedule beside it", "LTXVScheduler" in kinds, False)
check("...and no sigma-shift patch under it", "ModelSamplingLTXV" in kinds, False)
# Ancestral, in both stages, which is what those same workflows pick: the noise
# an ancestral step adds back is part of what eight steps were distilled with.
check("the trained sampler", kinds["KSamplerSelect"][0][1]["sampler_name"],
      ltx_declare.DISTILLED_SAMPLER)

# The distilled row is what an untouched piece runs: cfg 1/1.
guider = kinds["LTXVDualCFGGuider"][0][1]
check("the distilled scales", (guider["video_cfg"], guider["audio_cfg"]), (1.0, 1.0))

# ---- the scheduler route -----------------------------------------------------
#
# The other file in the `dit` slot. The full dev transformer is sampled the way
# LTX 2.3 was — a curve built from the row, and the model patch that reads the
# same one — so picking that route brings both nodes back and takes the constant
# away.

dev = by_class(build(piece(sampling={"schedule": "scheduler", "steps": 20,
                                     "video_cfg": 3.0, "audio_cfg": 7.0})).expand)
check("the scheduler route builds a curve", len(dev["LTXVScheduler"]), 1)
check("...and patches the model to match", len(dev["ModelSamplingLTXV"]), 1)
check("...with no constant left over", "ManualSigmas" in dev, False)
# The two are readings of one curve and must be given the same numbers off the
# same latent — letting them disagree is a quality bug with nothing in the log.
sched = dev["LTXVScheduler"][0][1]
patch = dev["ModelSamplingLTXV"][0][1]
check("the schedule and the patch share a shift pair",
      (sched["max_shift"], sched["base_shift"]),
      (patch["max_shift"], patch["base_shift"]))
check("...and measure the same latent", sched["latent"], patch["latent"])
check("...which is the segment's",
      sched["latent"], [dev["MiniMaxLTX25Segment"][0][0], 2])
check("the row's steps reach the scheduler", sched["steps"], 20)
check("the dev transformer's scales",
      (dev["LTXVDualCFGGuider"][0][1]["video_cfg"],
       dev["LTXVDualCFGGuider"][0][1]["audio_cfg"]), (3.0, 7.0))

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
# The second stage's curve is a constant too, and it is a tail already: 0.85 is
# where the upscaled latent re-enters, and the three values after it are the
# first stage's own trained tail. So nothing is split — there is no fraction to
# take of a schedule whose every value the distillation fixed.
check("both stages sample on a trained curve", len(two["ManualSigmas"]), 2)
check("...the second on the refine tail",
      sorted(i["sigmas"] for _, i in two["ManualSigmas"]),
      sorted([ltx_declare.DISTILLED_SIGMAS, ltx_declare.DISTILLED_REFINE_SIGMAS]))
check("...and the refine pill is not read on this route",
      "SplitSigmasDenoise" in two, False)

# On the scheduler route it is: a computed curve is where a partial pass can be
# expressed, and `refine denoise` is the fraction of it the second stage runs.
dev_two = by_class(build(piece(short_edge=1088,
                               sampling={"schedule": "scheduler"})).expand)
check("the scheduler route splits its curve for the second stage",
      len(dev_two["SplitSigmasDenoise"]), 1)
check("...at the piece's refine denoise",
      dev_two["SplitSigmasDenoise"][0][1]["denoise"],
      compiler.DEFAULT_REFINE_DENOISE)
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

# ---- taste guidance ----------------------------------------------------------
#
# STG and modality guidance each hang a post-CFG hook that runs a second forward
# pass per step. Off is the default and off means *absent*: a node that clones
# the model to install a hook returning its input unchanged is a pass nobody
# asked for, and it would move every golden that has an LTX piece in it.

check("no detail guidance on an untouched piece",
      "LTXVSpatioTemporalGuidance" in kinds, False)
check("no modality guidance on an untouched piece",
      "LTXVModalityGuidance" in kinds, False)

stg = by_class(build(piece(sampling={"stg_scale": 1.0, "stg_blocks": "29, 30"})).expand)
check("one STG node", len(stg["LTXVSpatioTemporalGuidance"]), 1)
stg_inputs = stg["LTXVSpatioTemporalGuidance"][0][1]
check("...at the scale the row asked for", stg_inputs["scale"], 1.0)
check("...over the blocks it named", stg_inputs["blocks"], "29, 30")
check("...across the whole schedule",
      (stg_inputs["start_percent"], stg_inputs["end_percent"]), (0.0, 1.0))
# Inside the sampling patch and outside nothing else: the guider samples the
# model the hook was installed on, or the extra pass is bought and never used.
check("...and it is what the guider guides",
      stg["LTXVDualCFGGuider"][0][1]["model"][0],
      stg["LTXVSpatioTemporalGuidance"][0][0])
# On the trained curve there is no shift patch to sit after, so the hook goes
# straight onto the segment node's model — which is the one the LoRAs are on.
check("...installed on the segment's model",
      stg_inputs["model"][0], stg["MiniMaxLTX25Segment"][0][0])
check("a scale without blocks is not a node",
      "LTXVSpatioTemporalGuidance" in
      by_class(build(piece(sampling={"stg_scale": 1.0, "stg_blocks": ""})).expand),
      False)

mod = by_class(build(piece(sampling={"modality_scale": 3.0})).expand)
check("one modality node", len(mod["LTXVModalityGuidance"]), 1)
check("...at the row's scale",
      mod["LTXVModalityGuidance"][0][1]["modality_scale"], 3.0)
check("...and STG is not dragged along",
      "LTXVSpatioTemporalGuidance" in mod, False)

# Both, and both on both stages of a two-stage render: the second pass is a
# continuation of the first and a piece guided in one and not the other would
# change its own look halfway through.
both = by_class(build(piece(short_edge=1088,
                            sampling={"stg_scale": 1.0,
                                      "modality_scale": 3.0})).expand)
check("STG on each stage", len(both["LTXVSpatioTemporalGuidance"]), 2)
check("modality on each stage", len(both["LTXVModalityGuidance"]), 2)
check("...composed in the order Lightricks names them",
      {i["model"][0] for _, i in both["LTXVModalityGuidance"]},
      {node_id for node_id, _ in both["LTXVSpatioTemporalGuidance"]})

# The row refuses by name rather than sampling at full cost with the guidance
# quietly inert.
expect_error("blocks naming nothing",
             lambda: build(piece(sampling={"stg_blocks": "twenty-nine"})),
             "names no block")
expect_error("modality guidance below its off value",
             lambda: build(piece(sampling={"modality_scale": 0.5})),
             "at least 1.0")

# ---- the seams, on the 8-grid ------------------------------------------------
#
# The reel and seam layer is core's and family-neutral by construction, which is
# a claim worth one chained strip rather than a comment. What is LTX's about it
# is the *width*: a seam hands the pass in front's last run over as a multi-frame
# guide, and `LTXVAddGuide` crops a guide to the nearest 8n+1 silently — so H3's
# 5-frame blend would arrive as one frame while the reel went on trimming five
# off the head. `canvas.feather_grid` is what stops that, and this is what says
# the graph got the grid's numbers rather than H3's.

FEATHER = canvas.feather_grid(LTX25)
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
      round(FEATHER[2] / LTX25.fps, 4))

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

# ---- multishot ---------------------------------------------------------------
#
# LTX 2.5 cuts inside one generation, and this pack already had the control for
# it: merging cards makes one pass whose description holds several shots. What
# it did not have was a *body* for a family that marks no shots.
#
# `contextir.shot_body` ran for every family, so a merged LTX pass reached Gemma
# as "[Shot 1] ... [Shot 2] At 00:05.000, ...". Lightricks' own trainer captions
# multi-shot footage as "a single continuous paragraph ... if the video contains
# multiple shots, describe each one in turn", with "no section headers, bullet
# points, or labels like ... 'Shot:'" — so a bracketed marker is a token
# sequence the weights were trained never to see, sitting where the cut belongs.
# Their prompting guide asks for the cut in prose instead: "A hard cut
# transitions to...". So the join is the family's, off the same table the prompt
# pipeline is.

SHOTS = [
    {"prompt": "A wide shot frames a rainy city intersection at dusk",
     "duration_s": 5, "assets": [], "loras": []},
    {"prompt": "A hard cut transitions to a medium close-up of her face.",
     "duration_s": 5, "assets": [], "loras": [], "merge": True},
    {"prompt": "Another hard cut jumps to a low-angle shot of scuffed boots.",
     "duration_s": 5, "assets": [], "loras": [], "merge": True},
]

merged = by_class(build(piece(render="single", segments=SHOTS)).expand)
check("three shots are one generation", len(merged["MiniMaxLTX25Segment"]), 1)
check("...and one sampler", len(merged["SamplerCustomAdvanced"]), 1)

merged_prompt = compiler.compile_segment(
    json.loads(merged["MiniMaxLTX25Segment"][0][1]["segment_data"]),
    family="ltx25").prompt
check("no shot markers reach Gemma", "[Shot" in merged_prompt, False)
check("...and no cut timestamps either", "00:05" in merged_prompt, False)
check("the shots are one paragraph, in play order", merged_prompt,
      "A wide shot frames a rainy city intersection at dusk. "
      "A hard cut transitions to a medium close-up of her face. "
      "Another hard cut jumps to a low-angle shot of scuffed boots.")

# ...and the same strip on H3 still gets H3's marked-up body, which is the
# whole reason the join is the family's rather than a rewrite.
h3_merged = compiler.compile_single({
    "version": 2, "prompt": "", "aspect": "16:9", "short_edge": 768,
    "render": "single", "segments": SHOTS})
check("H3 still marks its cuts", "[Shot 2] At 00:05.000," in h3_merged.prompt, True)

# The pass says how many shots it holds either way — counted off the markers
# where there are markers, and off the cards where a paragraph has nothing to
# count.
check("a prose pass counts its shots as its cards",
      compiler.group_payload({"version": 2, "family": "ltx25", "aspect": "16:9",
                              "segments": SHOTS})["shots"], 3)

# ---- the duration head -------------------------------------------------------
#
# The one capability H3 has no answer to at all. It cannot be asked before a
# queue — `LTXVDurationPredictor` runs the transformer's caption connectors over
# the encoded prompt, so it needs the loaded 22B DiT — so what the graph has to
# show is that the head reaches the segment node when a card asks for it, is
# absent when none does, and is loaded exactly once however many cards ask.

MODELS_WITH_HEAD = {**MODELS, "duration_head": "ltx/ltx-2.5-duration-head.safetensors"}

check("a piece with no auto card loads no head",
      "ModelPatchLoader" in kinds, False)
check("...and its segment node has no head wired",
      "duration_head" in kinds["MiniMaxLTX25Segment"][0][1], False)

auto = by_class(build(piece(
    models=MODELS_WITH_HEAD,
    segments=[
        {"prompt": "wide", "duration_s": 5, "assets": [], "loras": [],
         "auto_duration": True},
        {"prompt": "closer", "duration_s": 5, "assets": [], "loras": []},
        {"prompt": "last", "duration_s": 5, "assets": [], "loras": [],
         "auto_duration": True},
    ],
)).expand)

check("one head loader for the whole strip", len(auto["ModelPatchLoader"]), 1)
check("...loading the picked file",
      auto["ModelPatchLoader"][0][1]["name"], MODELS_WITH_HEAD["duration_head"])
wired = [i for _, i in auto["MiniMaxLTX25Segment"] if "duration_head" in i]
check("both auto cards get it, and the third does not", len(wired), 2)
check("...from that one loader",
      {tuple(i["duration_head"]) for i in wired},
      {(auto["ModelPatchLoader"][0][0], 0)})

# The estimate still reaches the payload: it is what the strip's bar counts and
# what the queue guard is checked against, and the node is the only place the
# head's answer replaces it.
auto_payload = json.loads(auto["MiniMaxLTX25Segment"][0][1]["segment_data"])
auto_one = compiler.compile_segment(auto_payload, family="ltx25")
check("the card still compiles to an estimate",
      (auto_one.auto_duration, auto_one.frames), (True, 121))

# And it is a capability, not a flag anybody can set: the same blob on H3 is a
# card of a fixed length, because H3 has no weights that could answer.
h3_auto = compiler.compile_segment(
    {"request": {"prompt": "wide", "duration_s": 5, "assets": [], "loras": [],
                 "auto_duration": True}}, family="h3")
check("H3 reads the flag as the 'no' it is", h3_auto.auto_duration, False)

expect_error("an auto card with no head picked says which pill to change",
             lambda: build(piece(segments=[
                 {"prompt": "wide", "duration_s": 5, "assets": [], "loras": [],
                  "auto_duration": True}])),
             "no duration head has been picked")

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

# ---- the preview override -----------------------------------------------------
#
# This family picks no tiny decoder and needs none: KJNodes recognises an LTX
# latent format and previews it through its own LTX previewer. What it does need
# is the node, because nothing else previews a render of ours — core's previews
# are off in a stock install, and where they are on the frontend paints them onto
# the canvas node instead of into the body. Before this, an LTX piece sampled for
# ten minutes behind an empty box.


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


check("nothing is emitted with the pack absent", "ModelPreviewOverrideKJ" in kinds, False)

_restore = dict(comfy_nodes.NODE_CLASS_MAPPINGS)
comfy_nodes.NODE_CLASS_MAPPINGS["ModelPreviewOverrideKJ"] = _FakePreview
try:
    previewed = by_class(build(piece()).expand)
    patches = previewed["ModelPreviewOverrideKJ"]
    check("one preview patch on a one-stage render", len(patches), 1)
    check("no decoder is asked for", "tiny_vae" in patches[0][1], False)
    check("...and the default preview is suppressed, ours being the only one",
          patches[0][1]["suppress_default_preview"], True)
    # Outermost on the model: the override wraps OUTER_SAMPLE, so everything the
    # sampling does to the model is inside it. On the trained curve nothing is,
    # so what it wraps is the segment's own model; on the scheduler route it is
    # the shift patch, and it is still the outermost thing.
    check("it wraps whatever the sampling patched",
          patches[0][1]["model"][0], previewed["MiniMaxLTX25Segment"][0][0])
    shifted = by_class(build(piece(sampling={"schedule": "scheduler"})).expand)
    check("...the shift patch, where there is one",
          shifted["ModelPreviewOverrideKJ"][0][1]["model"][0],
          shifted["ModelSamplingLTXV"][0][0])
    check("and the guider reads the wrapped model",
          previewed["LTXVDualCFGGuider"][0][1]["model"][0], patches[0][0])
    # Two stages are two sampling passes, and a second pass nobody can watch is
    # the same empty box as the first one.
    both = by_class(build(piece(short_edge=1088)).expand)
    check("one per sampling pass on a two-stage render",
          len(both["ModelPreviewOverrideKJ"]), len(both["SamplerCustomAdvanced"]))
finally:
    comfy_nodes.NODE_CLASS_MAPPINGS.clear()
    comfy_nodes.NODE_CLASS_MAPPINGS.update(_restore)

# ---- the conditioning still ---------------------------------------------------
#
# The one part of this family that is not a graph: `LTXVAddGuide` is called
# inside the segment node, so what a still looks like by the time it reaches the
# VAE is decided in Python and nothing above can see it. Every official LTX 2.5
# image-to-video graph resizes the frame to a 1536 px longest edge and runs it
# through `LTXVPreprocess` before conditioning on it — the compression is what
# makes it look like the guide frames the model was trained on, all of which
# came out of compressed clips. A clean still is off-distribution, and a first
# second that sits still is what that costs.

ltx_segment = importlib.import_module(f"{PACKAGE}.creator.families.ltx25.segment")
media = importlib.import_module(f"{PACKAGE}.creator.media")

import torch  # noqa: E402

_source = torch.rand(1, 400, 900, 3)
_loaded = media.load_image
media.load_image = lambda filename: _source
try:
    still = ltx_segment._still("a-still.png")
finally:
    media.load_image = _loaded

check("a still is resized to the longest edge the workflows use",
      max(still.shape[1], still.shape[2]), ltx_segment.GUIDE_LONGEST_EDGE)
# Kept rather than cropped: the guide node does its own resample to the latent's
# size, and cropping here would be deciding the framing of a chosen picture.
check("...with its aspect kept and nothing cropped",
      round(still.shape[2] / still.shape[1], 2),
      round(_source.shape[2] / _source.shape[1], 2))
check("...and compressed, not merely resampled",
      torch.equal(still, torch.nn.functional.interpolate(
          _source.movedim(-1, 1), size=still.shape[1:3],
          mode="bilinear").movedim(1, -1)), False)
check("...still an IMAGE in 0..1",
      (still.dtype, bool(still.min() >= 0), bool(still.max() <= 1)),
      (_source.dtype, True, True))

# A seam is not a still and is left alone: the frames it inherits are the pass
# in front's own, already at this canvas and already out of this VAE, and the
# shot has to resume from exactly them. Putting encode artefacts into a
# continuation would be inventing damage rather than matching training.
check("a still is conditioned softly, a seam is pinned",
      (ltx_segment.STILL_STRENGTH, ltx_segment.SEAM_STRENGTH), (0.7, 1.0))


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
h3_slots = importlib.import_module(f"{PACKAGE}.creator.families.h3.models")
check("...and still carries H3's", set(h3_slots.FOLDERS) <= set(served), True)
check("the folders are the ones the model card names",
      [served["dit"], served["clip"], served["vae"], served["upscaler"]],
      ["diffusion_models", "text_encoders", "vae", "latent_upscale_models"])

listed = models_mod.available()
check("every slot gets a file list, even an empty one",
      sorted(listed["files"]), sorted(served))

passed("LTX 2.5 expands to its own sampler, crops its guides once, upscales natively, and seams on its own grid")

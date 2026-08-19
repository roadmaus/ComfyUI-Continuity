"""What `MiniMaxH3Timeline.execute` actually wires up.

`compile_timeline` is covered by `test_compile.py` and needs nothing installed.
This one does: it runs the real node against the real ComfyUI, because the thing
worth checking here is the *graph*, and a stubbed GraphBuilder would only prove
the stub works. Nothing is sampled — `execute` returns a subgraph, so the whole
expansion can be inspected without a model or a single denoising step.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_timeline_graph.py

Skips itself with a message if ComfyUI cannot be imported.
"""

import asyncio
import importlib
import json
import os
import sys
import tempfile

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
    server.PromptServer(loop)          # server_routes.py registers against .instance
    asyncio.set_event_loop(loop)
    loop.run_until_complete(nodes.init_extra_nodes(init_custom_nodes=False))

    sys.path.insert(0, os.path.dirname(ROOT))
    return importlib.import_module(PACKAGE), nodes


try:
    package, comfy_nodes = _boot()
except Exception as exc:  # noqa: BLE001
    print(f"skipped: ComfyUI not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)

tl = importlib.import_module(f"{PACKAGE}.timeline")
# The user-facing node moved to `creator_node` when the Creator and the Timeline
# became one. This id is the retired one, kept loadable for saved workflows, and
# it runs the same body — so it is still the right thing to drive these through.
cn = importlib.import_module(f"{PACKAGE}.creator_node")
accel_mod = importlib.import_module(f"{PACKAGE}.accel")
outputs_mod = importlib.import_module(f"{PACKAGE}.outputs")

from harness import FAILURES, check


def expect_error(label, fn, fragment):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        if fragment not in str(exc):
            FAILURES.append(f"{label}: error {str(exc)!r} does not mention {fragment!r}")
    else:
        FAILURES.append(f"{label}: expected an error mentioning {fragment!r}, got none")


# The node has no sockets: the weights are named in the blob and the loaders are
# built inside the subgraph. Filenames rather than links, and never checked
# against the disk — they only ever become a loader's widget value.
MODELS = {
    "fl2va": "h3/fl2va.safetensors",
    "ref2va": "h3/ref2va.safetensors",
    "clip": "h3/text_encoder.safetensors",
    "vae": "h3/video_vae.safetensors",
    "audio_vae": "h3/audio_vae.safetensors",
}

NODE_ID = "12"

DATA = json.dumps({
    "version": 2,
    "prompt": "a red room",
    "aspect": "16:9",
    "short_edge": 768,
    "models": MODELS,
    "segments": [
        {"prompt": "wide", "duration_s": 5},
        {"prompt": "closer", "duration_s": 10, "continue": True},
        {"prompt": "cut away", "duration_s": 5,
         "assets": [{"handle": "img-1", "kind": "image", "role": "reference", "filename": "a.png"}]},
    ],
})


def build(data=DATA, **overrides):
    kwargs = dict(
        timeline_data=data,
        seed=100, steps=20, cfg=6.0, sampler_name="euler", scheduler="simple",
    )
    kwargs.update(overrides)
    # `unique_id` reaches `execute` as a hidden input, which only the executor
    # fills in. Stamped by hand so the save node gets the display id it would get
    # in a real run — that link is the whole reason the node can show its own
    # result, and a test that skipped it would not notice it break. Constructed
    # rather than `HiddenHolder.from_dict`, whose keys are `Hidden` enum members
    # and not the plain names.
    from comfy_api.latest import io as comfy_io

    previous = cn.MiniMaxH3Timeline.hidden
    cn.MiniMaxH3Timeline.hidden = comfy_io.HiddenHolder(
        unique_id=NODE_ID, prompt=None, extra_pnginfo=None, dynprompt=None,
        auth_token_comfy_org=None, api_key_comfy_org=None)
    try:
        return cn.MiniMaxH3Timeline.execute(**kwargs)
    finally:
        cn.MiniMaxH3Timeline.hidden = previous


def without(field, data=DATA):
    """`data` with one weights field never picked."""
    parsed = json.loads(data)
    parsed["models"] = {k: v for k, v in parsed["models"].items() if k != field}
    return json.dumps(parsed)


def blob(**fields):
    """A timeline blob with the weights already filled in.

    Every case here is about the graph rather than about the weights, and a
    literal that forgot them would fail in `models.check` before reaching the
    thing it was written to test.
    """
    return json.dumps({"version": 2, "models": MODELS, **fields})


out = build()
graph = out.expand
# No output sockets, so no exported links — as an empty tuple, not the `None`
# that `NodeOutput` gives for no values and that `execution.py` calls `len()` on.
check("expansion exports no links", out.result, ())
by_type = {}
for node_id, node in graph.items():
    by_type.setdefault(node["class_type"], []).append((node_id, node["inputs"]))

check("one segment node per segment", len(by_type["MiniMaxH3TimelineSegment"]), 3)
check("one sampler per segment", len(by_type["KSampler"]), 3)
# One reel node per pass and no decode nodes at all: a pass is decoded inside
# the reel node and written straight to disk, because a node that returns a
# decoded pass holds it for the whole execution — see `MiniMaxH3Reel`.
check("one reel node per pass", len(by_type["MiniMaxH3Reel"]), 3)
check("nothing decodes into the graph", "VAEDecode" in by_type, False)
check("...on either track", "VAEDecodeAudio" in by_type, False)
# Only segment 2 continues, so only one seam ever reads a pass back.
check("frames are read back only where a seam needs them",
      len(by_type["MiniMaxH3PassFrames"]), 1)
check("no negative connected means one zero-out per segment",
      len(by_type["ConditioningZeroOut"]), 3)

# The flow shifts. At the checkpoints' own schedule no node is emitted at all,
# so an untouched row builds the same graph it always has; off it, one shift
# node patches each pass's model on its way to the sampler.
check("the default schedule emits no shift node", "MiniMaxH3SigmaShift" in by_type, False)
shifted = {}
for node_id, node in build(shift_video=6.0).expand.items():
    shifted.setdefault(node["class_type"], []).append((node_id, node["inputs"]))
check("an off-default video shift emits one shift node per generation",
      len(shifted.get("MiniMaxH3SigmaShift", [])), 3)
check("...carrying both clocks",
      {(i["shift_video"], i["shift_audio"]) for _, i in shifted.get("MiniMaxH3SigmaShift", [])},
      {(6.0, 3.0)})
shift_ids = {node_id for node_id, _ in shifted.get("MiniMaxH3SigmaShift", [])}
check("each sampler runs on the shifted model",
      all(i["model"][0] in shift_ids for _, i in shifted.get("KSampler", [])), True)

def in_order(nodes, order):
    """The segment nodes sorted by which of `order`'s prompts they carry."""
    keyed = {json.loads(i["segment_data"])["request"]["prompt"]: (node_id, i) for node_id, i in nodes}
    return [keyed[prompt] for prompt in order]


segments = in_order(by_type["MiniMaxH3TimelineSegment"],
                    ["a red room\nwide", "a red room\ncloser", "a red room\ncut away"])
# The global prompt is folded into each payload rather than passed alongside it,
# so a segment node's inputs describe one whole generation and nothing else.
# `progress` is the one exception: the segment's own position, announced to the
# stage when the node runs — the index only, so appending a segment cannot
# touch an earlier payload's cache key.
check("each segment carries only its own payload",
      [sorted(json.loads(i["segment_data"])) for _, i in segments],
      [["canvas", "continue", "continue_audio", "progress", "request"]] * 3)
check("the progress stamp is the segment's index and nothing else",
      [json.loads(i["segment_data"])["progress"] for _, i in segments],
      [{"index": 1}, {"index": 2}, {"index": 3}])
# The loaders are built once for the whole chain, not once per segment: they are
# ordinary nodes keyed on their filenames, so every segment reads the same one.
check("every segment reads the same FL2VA loader",
      len({tuple(i["model_fl2va"]) for _, i in segments}), 1)
check("only the continuing segment takes a previous frame",
      ["prev_image" in i for _, i in segments], [False, True, False])

# The chain: segment 2's prev_image must trace back to segment 1's pass, not to
# segment 2's own and not to the reel as a whole. This is the edge the whole
# feature is.
last_frame_id, last_frame_inputs = by_type["MiniMaxH3PassFrames"][0]
check("the continuing segment reads that last frame",
      segments[1][1]["prev_image"], [last_frame_id, 0])
# The reel node's second output: the pass it just spilled, not the reel.
check("...off the pass rather than the reel", last_frame_inputs["source"][1], 1)
reel_node_id = last_frame_inputs["source"][0]
sampler_id = graph[reel_node_id]["inputs"]["samples"][0]
check("...which came from segment 1's sampler",
      graph[sampler_id]["inputs"]["model"][0], segments[0][0])

# One seed for the piece. It used to be seed + k, which meant the number on the
# node named segment 1's noise and nothing else — a shot could not be reproduced
# from it, and moving a card re-rolled every shot after it.
check("every segment runs on the seed as set",
      sorted(i["seed"] for _, i in by_type["KSampler"]), [100, 100, 100])

# ---- the loaders and the tail -----------------------------------------------
#
# This timeline runs two segments on FL2VA and one on Ref2VA, so both checkpoints
# are genuinely needed and both are built — but one loader each, not one per
# segment. The Creator's test pins the other half of the claim: a render that
# reaches for one checkpoint must not build the other.

check("one loader per checkpoint actually routed to",
      sorted(i["unet_name"] for _, i in by_type["UNETLoader"]),
      sorted([MODELS["fl2va"], MODELS["ref2va"]]))
check("one text encoder for the whole chain", len(by_type["CLIPLoader"]), 1)
check("one loader per VAE", len(by_type["VAELoader"]), 2)

# Nothing comes out of the node: it saves the whole reel itself, and the
# display-id stamp is what puts the result back on the node the user is looking
# at rather than on an expanded node nobody can see.
check("nothing comes out of the node", out.args, ())
save_id, save_inputs = by_type["MiniMaxH3Save"][0]
check("one save node", len(by_type["MiniMaxH3Save"]), 1)
check("it is reported against the node that built it",
      graph[save_id].get("override_display_id"), NODE_ID)
check("it saves the end of the reel",
      graph[save_inputs["reel"][0]]["class_type"], "MiniMaxH3Reel")

# The reel is a chain, one node per pass, each holding the one in front of it —
# and the passes reach it in play order. This is what replaced the pairwise
# join, and the property worth pinning is that nothing concatenates: every reel
# node's picture comes straight off its own decode.
reel_id = save_inputs["reel"][0]
walked = []
while reel_id is not None:
    inputs = graph[reel_id]["inputs"]
    walked.append(graph[inputs["samples"][0]]["class_type"])
    reel_id = inputs["reel"][0] if "reel" in inputs else None
check("the reel is one node per pass, samplers all the way down",
      walked, ["KSampler"] * 3)
check("the first pass opens the reel with nothing in front of it",
      "reel" in graph[[node_id for node_id, i in by_type["MiniMaxH3Reel"]
                       if "reel" not in i][0]]["inputs"], False)
check("it lands in the render folder — the same one a Creator render lands in",
      save_inputs["filename_prefix"], outputs_mod.VIDEO_PREFIX)
# One prefix for the whole timeline, because a timeline is one file: the
# passes reach the save node as one reel, so there is nothing per-segment to
# put anywhere else.
retargeted = build(json.dumps({**json.loads(DATA), "output_prefix": "film/reel-1"})).expand
check("a blob's own prefix is used instead",
      [n["inputs"]["filename_prefix"] for n in retargeted.values()
       if n["class_type"] == "MiniMaxH3Save"],
      ["film/reel-1"])

# Two continuations in a row. Worth its own case: with only one, the "previous
# segment's images" and "everything joined so far" are the same node, so a chain
# that reads from the join instead of from the previous segment still looks
# right. From the third segment on they diverge.
run = build(blob(segments=[
    {"prompt": "one", "duration_s": 5},
    {"prompt": "two", "duration_s": 5, "continue": True},
    {"prompt": "three", "duration_s": 5, "continue": True},
])).expand
chain = in_order(
    [(node_id, n["inputs"]) for node_id, n in run.items()
     if n["class_type"] == "MiniMaxH3TimelineSegment"],
    ["one", "two", "three"])
check("every segment after the first continues", [("prev_image" in i) for _, i in chain],
      [False, True, True])

def _walk(graph, start, hops):
    """Follow `hops` of (socket, the class the far end must be), naming a miss.

    The seam's provenance, as a walk: what a segment inherits has to trace back
    through the pass it names to that pass's own sampler, and not to the reel or
    to a neighbour. Both ends of a seam are checked this way, so the walk is one
    function taking the sockets that differ.
    """
    node = graph[start[0]]
    link = start
    for socket, expected in hops:
        link = node["inputs"].get(socket)
        if link is None:
            return f"<{node['class_type']} has no {socket!r}>"
        node = graph[link[0]]
        if expected and node["class_type"] != expected:
            return f"<{expected} expected, found {node['class_type']}>"
    return link[0]


def source_segment(graph, prev_image):
    """Walk pass frames -> the reel node that spilled it -> sampler -> segment."""
    return _walk(graph, prev_image,
                 (("source", "MiniMaxH3Reel"), ("samples", "KSampler"), ("model", None)))


for index in (1, 2):
    check(f"segment {index + 1} continues from segment {index}, not from the join",
          source_segment(run, chain[index][1]["prev_image"]), chain[index - 1][0])

# The circular narrative: segment 2 is an unrelated hard cut, and segment 3
# names segment 1 as its source — so its frame and its sound tail must both
# trace to segment 1's decodes, not to segment 2's.
run = build(blob(segments=[
    {"prompt": "hallway", "duration_s": 5},
    {"prompt": "dream", "duration_s": 5},
    {"prompt": "hallway again", "duration_s": 5,
     "continue": True, "continue_audio": True, "continue_from": 1},
])).expand
chain = in_order(
    [(node_id, n["inputs"]) for node_id, n in run.items()
     if n["class_type"] == "MiniMaxH3TimelineSegment"],
    ["hallway", "dream", "hallway again"])
check("only the returning segment continues",
      [("prev_image" in i) for _, i in chain], [False, False, True])
check("segment 3 continues from segment 1, two cards back",
      source_segment(run, chain[2][1]["prev_image"]), chain[0][0])


def audio_source_segment(graph, prev_audio):
    """The same walk on the sound side: pass audio -> that pass -> its segment."""
    if graph[prev_audio[0]]["class_type"] != "MiniMaxH3PassAudio":
        return f"<MiniMaxH3PassAudio expected, found {graph[prev_audio[0]]['class_type']}>"
    return _walk(graph, prev_audio,
                 (("source", "MiniMaxH3Reel"), ("samples", "KSampler"), ("model", None)))


check("...and its sound tail comes off segment 1 as well",
      audio_source_segment(run, chain[2][1]["prev_audio"]), chain[0][0])
# The named source rides the payload — it is part of the segment's cache key,
# so repointing a seam re-runs that segment and only that segment.
check("the source is on the payload, and only where one was named",
      [json.loads(i["segment_data"]).get("continue_from") for _, i in chain],
      [None, None, 0])

# A source that no longer exists — a leftover from deleting or reordering —
# falls back to the default seam rather than refusing the timeline.
run = build(blob(segments=[
    {"prompt": "one", "duration_s": 5},
    {"prompt": "two", "duration_s": 5, "continue": True, "continue_from": 7},
])).expand
chain = in_order(
    [(node_id, n["inputs"]) for node_id, n in run.items()
     if n["class_type"] == "MiniMaxH3TimelineSegment"],
    ["one", "two"])
check("an out-of-range source falls back to the previous segment",
      source_segment(run, chain[1][1]["prev_image"]), chain[0][0])
check("...and is not written onto the payload",
      json.loads(chain[1][1]["segment_data"]).get("continue_from"), None)

# What makes editing a long timeline bearable: a segment node's inputs are its
# cache key, so editing the last shot must leave the earlier segments' inputs
# byte-identical. This is the assertion to keep — it is easy to lose by handing a
# segment one field too many, and the only symptom is that everything re-runs.
edited = json.loads(DATA)
edited["segments"][2]["prompt"] = "somewhere else entirely"
before = {i["segment_data"] for _, i in by_type["MiniMaxH3TimelineSegment"]}
after = {n["inputs"]["segment_data"] for n in build(json.dumps(edited)).expand.values()
         if n["class_type"] == "MiniMaxH3TimelineSegment"}
check("editing the last segment leaves the earlier payloads untouched",
      len(before & after), 2)

# And the loader inputs must stay links: a loaded model as a literal input value
# hashes as Unhashable, which would miss the cache on every queue.
loader_ids = {node_id for kind in ("UNETLoader", "CLIPLoader", "VAELoader")
              for node_id, _ in by_type[kind]}
for _, inputs in by_type["MiniMaxH3TimelineSegment"]:
    for socket in ("clip", "vae", "audio_vae", "model_fl2va", "model_ref2va"):
        value = inputs.get(socket)
        if value is None:
            continue
        if not (isinstance(value, list) and len(value) == 2 and value[0] in loader_ids):
            FAILURES.append(f"segment input {socket!r} is not a link to a loader: {value!r}")

# ---- one pass ---------------------------------------------------------------
#
# The same timeline, rendered in a single generation. What is worth checking at
# this level is the *shape* of the expansion: everything that exists to join two
# generations together has to be gone, because there is only one.

single = json.loads(DATA)
single["render"] = "single"
# The third segment's reference would make the merged request REF2VA while the
# others carry none — legal, but it is the frames/references split that is worth
# keeping the graph test off, so this one is plain text.
single["segments"] = [{"prompt": "wide", "duration_s": 5},
                      {"prompt": "the camera cuts in closer", "duration_s": 10},
                      {"prompt": "the shot cuts away", "duration_s": 5}]
one = build(json.dumps(single))
built = {}
for node_id, node in one.expand.items():
    built.setdefault(node["class_type"], []).append((node_id, node["inputs"]))

check("one pass expands to one segment node", len(built["MiniMaxH3TimelineSegment"]), 1)
check("...and one sampler", len(built["KSampler"]), 1)
check("...on the seed as given, not seed + k", built["KSampler"][0][1]["seed"], 100)
for gone in ("MiniMaxH3PassFrames", "MiniMaxH3PassAudio"):
    check(f"no {gone} in a one-pass graph", gone in built, False)
# One generation, one checkpoint: none of these shots carries a reference, so
# the reference weights must not be loaded at all.
check("one pass loads one checkpoint",
      [i["unet_name"] for _, i in built["UNETLoader"]], [MODELS["fl2va"]])
one_save = built["MiniMaxH3Save"][0][1]
check("one pass makes a reel of one", len(built["MiniMaxH3Reel"]), 1)
one_reel = built["MiniMaxH3Reel"][0][1]
check("the reel decodes the sampler's own latent",
      one.expand[one_reel["samples"][0]]["class_type"], "KSampler")
check("...with both decoders wired into it",
      sorted(k for k in one_reel if k in ("vae", "audio_vae")), ["audio_vae", "vae"])
check("...and nothing to trim off a pass with no seams either side",
      [k for k in one_reel if k in ("head", "tail")], [])
check("...with nothing in front of it", "reel" in one_reel, False)

payload = json.loads(built["MiniMaxH3TimelineSegment"][0][1]["segment_data"])
check("the whole timeline arrives as one request", sorted(payload),
      ["continue", "continue_audio", "request", "shots"])
check("...holding every shot", payload["shots"], 3)
check("...summed rather than snapped per shot", payload["request"]["duration_s"], 20)
check("the shots are one description with cut times in it",
      payload["request"]["prompt"],
      "[Shot 1] a red room. wide [Shot 2] At 00:05.000, the camera cuts in closer "
      "[Shot 3] At 00:15.000, the shot cuts away")
check("no seam survives into the payload",
      (payload["continue"], payload["continue_audio"]), (False, False))
# The loader inputs matter here for the same reason they do when chained.
one_loaders = {node_id for kind in ("UNETLoader", "CLIPLoader", "VAELoader")
               for node_id, _ in built[kind]}
for socket in ("clip", "model_fl2va"):
    value = built["MiniMaxH3TimelineSegment"][0][1].get(socket)
    if not (isinstance(value, list) and len(value) == 2 and value[0] in one_loaders):
        FAILURES.append(f"one-pass segment input {socket!r} is not a link to a loader: {value!r}")
# This pass is plain text: it encodes no keyframe and no sound, so neither VAE is
# wired into the encoder. Both are decode-time loaders here — the reel node above
# holds them — and wiring them into the segment would load them before the first
# sampling step for an encode that never touches them.
for socket in ("vae", "audio_vae"):
    check(f"a text-only pass leaves {socket!r} off the encoder",
          socket in built["MiniMaxH3TimelineSegment"][0][1], False)

# One segment is the degenerate case: nothing to join, nothing to continue from.
lone = build(blob(segments=[{"prompt": "x", "duration_s": 6}])).expand
kinds = [n["class_type"] for n in lone.values()]
check("a lone segment makes a reel of one", kinds.count("MiniMaxH3Reel"), 1)
check("...and reads no pass back, having no seam", kinds.count("MiniMaxH3PassFrames"), 0)

# The checkpoint each segment routes to is checked before anything is queued,
# because failing here costs nothing and failing mid-chain costs every pass
# that already ran. And it must name the segment that reached for it: "pick the
# Ref2VA checkpoint" is a much shorter search with "segment 3" in front of it.
try:
    build(without("ref2va"))
except ValueError as exc:
    if "segment 3" not in str(exc).lower():
        FAILURES.append(f"missing checkpoint: {str(exc)!r} does not name segment 3")
    if "models/diffusion_models" not in str(exc):
        FAILURES.append(f"missing checkpoint: {str(exc)!r} does not name the folder")
else:
    FAILURES.append("missing checkpoint: expected a ValueError, got none")

expect_error("a missing audio VAE is refused too",
             lambda: build(without("audio_vae")),
             "models/vae")

# ---- the route --------------------------------------------------------------
#
# DATA runs two segments on FL2VA and one on Ref2VA, which is exactly the case a
# route is for: one instruction collapses the clip onto one set of weights,
# instead of pinning three shots by hand and losing the pins the next time a
# reference is attached.

def routed(route, data=DATA):
    parsed = json.loads(data)
    parsed["models"]["route"] = route
    return json.dumps(parsed)


def grouped(graph):
    out = {}
    for node_id, node in graph.items():
        out.setdefault(node["class_type"], []).append((node_id, node["inputs"]))
    return out


forced = grouped(build(routed("ref2va")).expand)
check("a forced route collapses the clip onto one checkpoint",
      [i["unet_name"] for _, i in forced["UNETLoader"]], [MODELS["ref2va"]])
check("...which every segment reads",
      len({tuple(i["model_ref2va"]) for _, i in forced["MiniMaxH3TimelineSegment"]}), 1)
check("...and no segment is wired to the other one",
      any("model_fl2va" in i for _, i in forced["MiniMaxH3TimelineSegment"]), False)
check("...so the checkpoint it skips need not be picked at all",
      [i["unet_name"] for _, i in grouped(build(routed("ref2va", without("fl2va"))).expand)["UNETLoader"]],
      [MODELS["ref2va"]])

# The other direction still refuses, and still names the segment that made it
# impossible — a route is a pin said once, not a licence to ignore the encoding.
try:
    build(routed("fl2va"))
except ValueError as exc:
    if "segment 3" not in str(exc).lower():
        FAILURES.append(f"forced FL2VA: {str(exc)!r} does not name segment 3")
    if "cannot be run through FL2VA" not in str(exc):
        FAILURES.append(f"forced FL2VA: {str(exc)!r} does not say why")
else:
    FAILURES.append("forced FL2VA: expected a ValueError, got none")

# --- the sound seam ----------------------------------------------------------
#
# The audio tail is wired exactly like the last frame: read back off the
# previous pass's spill, and only where a seam actually asks for it.

check("no tail node where no seam carries sound",
      len(by_type.get("MiniMaxH3PassAudio", [])), 0)

SOUND = blob(audio_tail_s=2.0, segments=[
    {"prompt": "wide", "duration_s": 5},
    # Sound only: the picture cuts, the room tone does not.
    {"prompt": "closer", "duration_s": 5, "continue_audio": True},
    # Both, which is the combination core cannot express unaided.
    {"prompt": "closer still", "duration_s": 5, "continue": True, "continue_audio": True},
])
sound = build(SOUND).expand
sound_by_type = {}
for node_id, node in sound.items():
    sound_by_type.setdefault(node["class_type"], []).append((node_id, node["inputs"]))

tails = sound_by_type.get("MiniMaxH3PassAudio", [])
check("one tail node per sound seam", len(tails), 2)
check("the tail length comes from the timeline", sorted({i["seconds"] for _, i in tails}), [2.0])

# Each tail must read a spilled *pass* — the reel node's second output — rather
# than the reel itself or a latent.
passes = {node_id for node_id, _ in sound_by_type["MiniMaxH3Reel"]}
check("every tail reads a pass that was written out",
      {(i["source"][0] in passes, i["source"][1]) for _, i in tails}, {(True, 1)})

# And each segment that asked for sound must actually receive one.
wired = [sorted(k for k in i if k.startswith("prev_"))
         for _, i in sound_by_type["MiniMaxH3TimelineSegment"]]
check("the seams get exactly the inputs they asked for",
      sorted(wired), [[], ["prev_audio"], ["prev_audio", "prev_image"]])

# --- the feathered seam ------------------------------------------------------
#
# A 22-frame feather: the seam inherits a run instead of a single frame, the
# audio tail is clamped to the overlap, and the re-generated head is trimmed
# off the decode before the join and before anything later inherits from it.

feathered = build(blob(audio_tail_s=2.0, segments=[
    {"prompt": "one", "duration_s": 5},
    {"prompt": "two", "duration_s": 5, "continue": True, "continue_audio": True,
     "feather": 22},
    {"prompt": "three", "duration_s": 5, "continue": True},
])).expand
fb = {}
for node_id, node in feathered.items():
    fb.setdefault(node["class_type"], []).append((node_id, node["inputs"]))

last_frames = {i.get("count", 1) for _, i in fb["MiniMaxH3PassFrames"]}
check("the feathered seam takes its run, the classic one its frame",
      sorted(last_frames), [1, 22])
check("the audio tail is clamped to the overlap",
      [i["seconds"] for _, i in fb["MiniMaxH3PassAudio"]], [22 / 24])

# The trim is the reel node's own, applied before anything is written: the
# blended head is re-generated here and would otherwise play twice.
trimmed = [(node_id, i) for node_id, i in fb["MiniMaxH3Reel"] if "head" in i]
check("one trim, on the feathered segment only", len(trimmed), 1)
check("it trims exactly the inherited run", trimmed[0][1]["head"], 22)
check("...off the head, with nothing to take off the tail",
      "tail" in trimmed[0][1], False)

fchain = in_order(
    [(node_id, n["inputs"]) for node_id, n in feathered.items()
     if n["class_type"] == "MiniMaxH3TimelineSegment"],
    ["one", "two", "three"])
# The trimming node is segment 2's own pass...
trim_id = trimmed[0][0]
trim_sampler = feathered[trimmed[0][1]["samples"][0]]
check("the trim is on the feathered segment's own pass",
      trim_sampler["inputs"]["model"][0], fchain[1][0])
# ...and what segment 3's seam inherits is that same pass, which is the trimmed
# one: there is only one spill and the overlap was dropped before it was
# written, so the source's tail can neither play twice nor leak forward.
seg3_last_frame = feathered[fchain[2][1]["prev_image"][0]]
check("the next seam inherits from the trimmed pass",
      seg3_last_frame["inputs"]["source"][0], trim_id)

# The encoder's guide arithmetic, against a stand-in VAE: one call over the
# run, one block per latent step, pinned at the offsets core's temporal grid
# dictates — and a refusal when the two stop agreeing.
import torch as _torch

encoder_mod = importlib.import_module(f"{PACKAGE}.encode")
payload_mod = importlib.import_module(f"{PACKAGE}.payload")


class _FakeVae:
    def __init__(self, steps):
        self.steps = steps

    def encode(self, frames):
        return _torch.zeros(1, 24, self.steps, 4, 4)


guides = encoder_mod._context_keyframes(_FakeVae(7), _torch.zeros(22, 64, 64, 3), 22)
check("22 frames become 7 per-step guide blocks", len(guides), 7)
if payload_mod.CORE_ANCHORS_ANYWHERE:
    check("every block anchors natively on the (1,4,4,4,4) temporal grid",
          [g["resolved_frame_index"] for g in guides], [0, 1, 5, 9, 13, 17, 18])
    check("no block carries the old-core repositioning key",
          any(payload_mod.FRAME_INDEX_KEY in g for g in guides), False)
else:
    check("every block passes the stock constructor a legal anchor",
          {g["resolved_frame_index"] for g in guides}, {0})
    check("the real positions follow the (1,4,4,4,4) temporal grid",
          [g[payload_mod.FRAME_INDEX_KEY] for g in guides], [0, 1, 5, 9, 13, 17, 18])
try:
    encoder_mod._context_keyframes(_FakeVae(6), _torch.zeros(22, 64, 64, 3), 22)
    FAILURES.append("a coverage mismatch should refuse to render, got no error")
except ValueError:
    pass

# ---- the reel node, run rather than drawn -----------------------------------
#
# Everything above is the graph's shape. This is the one node whose *execution*
# the shape cannot vouch for, and it is the node the memory argument rests on:
# it decodes a pass, trims the runs it shares with its neighbours, writes the
# result to disk and hands on a path. What has to hold is that the pass on disk
# is the pass that was decoded, that the trim came off the right end of both
# tracks together, and that the seam nodes read that same file back.

spill_mod = importlib.import_module(f"{PACKAGE}.spill")
_SPILLS = tempfile.mkdtemp(prefix="mmc-spill-")
spill_mod.directory = lambda: _SPILLS

RATE = 48000


class _DecodingVae:
    """A stand-in for the pair of decoders, answering with countable frames.

    Frame k is flat k/255 and the soundtrack counts up in the same way, so a
    trimmed pass says which frames and which samples survived rather than only
    how many.
    """

    audio_sample_rate_output = RATE

    def __init__(self, frames, audio=False):
        self.frames, self.audio = frames, audio

    def decode(self, latent):
        if self.audio:
            samples = int(round(self.frames / 24 * RATE))
            ramp = _torch.arange(samples, dtype=_torch.float32) / samples
            # (batch, samples, channels) — `vae_decode_audio` moves the last
            # axis into place, so this is the shape a real one hands back.
            return _torch.stack([ramp, ramp], dim=-1).unsqueeze(0)
        values = _torch.arange(self.frames, dtype=_torch.float32) / 255.0
        return values.view(self.frames, 1, 1, 1).expand(self.frames, 8, 8, 3).contiguous()


def _run_reel(frames, head=0, tail=0, reel=None):
    return tl.MiniMaxH3Reel.execute(
        samples={"samples": _torch.zeros(1, 4, 4, 4)},
        vae=_DecodingVae(frames), audio_vae=_DecodingVae(frames, audio=True),
        head=head, tail=tail, reel=reel)


whole = _run_reel(48)
part, spilled = whole.result[0][0], whole.result[1]
check("a pass reaches the reel as a file", list(part), ["pass"])
check("...and the pass it hands the seams is the same one", part["pass"], spilled)
check("...with every frame written", spilled["frames"], 48)
check("...and the sound that came with them",
      (spilled["rate"], spilled["channels"]), (RATE, 2))
check("the frames on disk are the frames that decoded",
      [round(float(f[0, 0, 0]) * 255) for f in spill_mod.frames(spilled, 48, "head")],
      list(range(48)))

# The trim. 5 frames off the head and 3 off the tail of a 48-frame pass leaves
# frames 5..44, and the soundtrack has to lose the matching stretch off each
# end — the two tracks cross a seam on the same instants or the sound drifts.
cut = _run_reel(48, head=5, tail=3)
trimmed = cut.result[1]
check("a blended pass is written without the runs it shares", trimmed["frames"], 40)
check("...off the right ends",
      [round(float(spill_mod.frames(trimmed, 1, end)[0, 0, 0, 0]) * 255)
       for end in ("head", "tail")], [5, 44])
check("...and the sound loses the same stretch, not the same fraction",
      trimmed["samples"], int(round(48 / 24 * RATE))
      - int(round(5 / 24 * RATE)) - int(round(3 / 24 * RATE)))

# The reel grows by one part per pass and keeps play order, and a pass never
# reaches back into the list it was handed.
second = _run_reel(12, reel=whole.result[0])
check("the reel grows by one part per pass", len(second.result[0]), 2)
check("...in play order",
      [p["pass"]["frames"] for p in second.result[0]], [48, 12])
check("...without touching the list it was handed", len(whole.result[0]), 1)

# And the seam nodes read that same file back — the run at the end of it, and
# the stretch of sound that goes with it.
check("a seam reads the last frames off the pass",
      [round(float(f[0, 0, 0]) * 255)
       for f in tl.MiniMaxH3PassFrames.execute(source=spilled, count=3).result[0]],
      [45, 46, 47])
seam_sound = tl.MiniMaxH3PassAudio.execute(source=spilled, seconds=0.5).result[0]
check("...and the tail of its sound",
      int(seam_sound["waveform"].shape[-1]), int(0.5 * RATE))

# ---- accelerators -----------------------------------------------------------
#
# The packs themselves are optional and usually absent, so what is pinned here is
# the wiring: off adds nothing at all, and on puts the patch between the segment
# node and the sampler rather than anywhere else. `accel.py`'s own tests cover
# the arguments; these cover the edge that only exists in the built graph.

check("no accelerator nodes by default",
      [t for t in by_type if t in (accel_mod.BLOCK_CACHE_NODE, accel_mod.SPECTRUM_NODE)], [])

# Every KSampler must read straight off its own segment node when nothing is on.
segments_by_id = {node_id for node_id, _ in by_type["MiniMaxH3TimelineSegment"]}
check("samplers read the segment directly when off",
      all(i["model"][0] in segments_by_id for _, i in by_type["KSampler"]), True)

# The harness boots with `init_custom_nodes=False`, so neither pack is loaded
# here even when both are installed — which is what makes a stand-in the only way
# to exercise the on path, and what keeps this test passing on a machine that has
# neither.
class _FakePack:
    FUNCTION = "apply"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"model": ("MODEL",),
                             "mode": (["H3 Safe — 0.08", "H3 Fast — 0.10"], {"default": "H3 Fast — 0.10"})}}


_restore = dict(comfy_nodes.NODE_CLASS_MAPPINGS)
comfy_nodes.NODE_CLASS_MAPPINGS[accel_mod.BLOCK_CACHE_NODE] = _FakePack
try:
    accel_graph = build(block_cache="fast").expand
    accel_by_type = {}
    for node_id, node in accel_graph.items():
        accel_by_type.setdefault(node["class_type"], []).append((node_id, node["inputs"]))

    # Its own graph, so its own node ids — the set from the run above does not
    # carry over and comparing against it is how this silently tests nothing.
    accel_segment_ids = {node_id for node_id, _ in accel_by_type["MiniMaxH3TimelineSegment"]}

    patches = accel_by_type.get(accel_mod.BLOCK_CACHE_NODE, [])
    check("one accelerator patch per segment", len(patches), 3)
    check("the patch is the pack's chosen preset",
          sorted({i["mode"] for _, i in patches}), ["H3 Fast — 0.10"])

    # The patch sits *between* the segment and the sampler: it reads a segment
    # node, and every sampler reads a patch. Getting this backwards would run the
    # accelerator on nothing and sample the unpatched model.
    patch_ids = {node_id for node_id, _ in patches}
    check("the patch reads a segment node",
          all(i["model"][0] in accel_segment_ids for _, i in patches), True)
    check("every sampler reads a patch",
          all(i["model"][0] in patch_ids for _, i in accel_by_type["KSampler"]), True)

    # The conditioning and latent still come from the segment, not the patch —
    # the accelerator is a MODEL patch and must not be in any other path.
    check("conditioning still comes from the segment",
          all(i["positive"][0] in accel_segment_ids for _, i in accel_by_type["KSampler"]), True)
    check("the latent still comes from the segment",
          all(i["latent_image"][0] in accel_segment_ids for _, i in accel_by_type["KSampler"]), True)
finally:
    comfy_nodes.NODE_CLASS_MAPPINGS.clear()
    comfy_nodes.NODE_CLASS_MAPPINGS.update(_restore)

# An accelerator asked for but not installed must fail at queue time, naming the
# pack — not silently render without it.
expect_error("a missing pack is refused up front",
             lambda: build(spectrum=True),
             "xmarre/ComfyUI-Spectrum-MiniMax-H3")

# ---- passes -----------------------------------------------------------------
#
# A run of merged segments is one generation, and the timeline is those runs
# chained. What is worth checking here is that the two halves of that sentence
# hold at once: the merged run expands to a single segment node with cuts in its
# description, and the seam to the next run still gets everything a seam gets.

mixed = build(blob(prompt="a red room", segments=[
    {"prompt": "wide", "duration_s": 5},
    {"prompt": "the camera cuts in closer", "duration_s": 5, "merge": True},
    {"prompt": "somewhere else entirely", "duration_s": 6, "continue": True},
])).expand
made = {}
for node_id, node in mixed.items():
    made.setdefault(node["class_type"], []).append((node_id, node["inputs"]))

check("two passes expand to two segment nodes", len(made["MiniMaxH3TimelineSegment"]), 2)
check("...and two samplers", len(made["KSampler"]), 2)
check("the two passes reach the reel", len(made["MiniMaxH3Reel"]), 2)
check("...and takes the first pass's last frame", len(made["MiniMaxH3PassFrames"]), 1)

first, second = (json.loads(i["segment_data"]) for _, i in made["MiniMaxH3TimelineSegment"])
check("the merged pass is one description with a cut in it",
      first["request"]["prompt"],
      "[Shot 1] a red room. wide [Shot 2] At 00:05.000, the camera cuts in closer")
check("...counted as two shots", first["shots"], 2)
check("...and generated as one 10 s clip", first["request"]["duration_s"], 10)
check("the unmerged segment is untouched",
      second["request"]["prompt"], "a red room\nsomewhere else entirely")
check("...and still continues from the pass in front of it", second["continue"], True)
check("both passes are held to one canvas",
      first["canvas"] == second["canvas"], True)

# ---- supplied clips ---------------------------------------------------------
#
# A clip card is a pass with no sampler in front of it. The claim worth pinning
# is what does *not* appear: no segment node, no KSampler, no reel node of its
# own. The file reaches the finished video through the clip reel, and the only
# thing decoded out of it is whatever a seam beside it asks for.


def with_clip(*segments, **rest):
    return build(blob(prompt="a red room", segments=list(segments), **rest)).expand


def by_class(graph):
    out = {}
    for node_id, node in graph.items():
        out.setdefault(node["class_type"], []).append((node_id, node["inputs"]))
    return out


CLIP = {"kind": "clip", "filename": "footage.mp4", "duration_s": 4,
        "width": 1920, "height": 1080}

spliced = by_class(with_clip({"prompt": "wide", "duration_s": 5}, dict(CLIP)))
check("a clip is not generated", len(spliced["MiniMaxH3TimelineSegment"]), 1)
check("...and costs no sampler", len(spliced["KSampler"]), 1)
check("...and no pass of its own to write out", len(spliced["MiniMaxH3Reel"]), 1)
check("it reaches the reel as a file", len(spliced["MiniMaxH3ClipReel"]), 1)
clip_id, clip_inputs = spliced["MiniMaxH3ClipReel"][0]
check("...behind the pass in front of it",
      spliced["MiniMaxH3Reel"][0][0], clip_inputs["reel"][0])
check("...and the save reads the clip's end of the reel",
      spliced["MiniMaxH3Save"][0][1]["reel"][0], clip_id)
spec = json.loads(clip_inputs["clip_data"])
check("the clip carries its file and its window",
      (spec["filename"], spec["start"], spec["duration"]), ("footage.mp4", 0.0, 4.0))
check("...and the size it is conformed to, which is the render's",
      (spec["width"], spec["height"]), (1344, 768))
# Its sound is resampled to whatever the generated passes decode at, which is a
# fact about the weights — so the VAE is wired in for the rate alone.
check("a clip with sound is wired to the audio VAE",
      "audio_vae" in clip_inputs, True)
muted = by_class(with_clip({"prompt": "wide", "duration_s": 5}, {**CLIP, "sound": False}))
check("a muted clip needs no VAE at all",
      "audio_vae" in muted["MiniMaxH3ClipReel"][0][1], False)

# A clip alone is a whole render: nothing is sampled, nothing is decoded, and
# the file is copied through the writer.
alone = by_class(with_clip(dict(CLIP)))
for absent in ("MiniMaxH3TimelineSegment", "KSampler", "MiniMaxH3Reel"):
    check(f"a clip on its own emits no {absent}", absent in alone, False)
check("...and still writes a file", len(alone["MiniMaxH3Save"]), 1)

# ---- a seam beside supplied footage -----------------------------------------
#
# What a seam inherits is decoded frames, and a clip has none in the graph — so
# the run is read out of the clip's own window instead, bounded by the seam's
# width rather than by the clip's length. That is the whole memory argument, as
# a graph shape: a clip nothing continues from is never decoded at all.

seamed = by_class(with_clip(
    dict(CLIP),
    {"prompt": "after", "duration_s": 5, "continue": True, "continue_audio": True,
     "feather": 22}))
check("a segment after a clip reads frames out of it",
      len(seamed["MiniMaxH3ClipFrames"]), 1)
frames_inputs = seamed["MiniMaxH3ClipFrames"][0][1]
check("...only as many as the blend crosses",
      (frames_inputs["count"], frames_inputs["at"]), (22, "tail"))
check("...and never off a spilled pass, which a clip never becomes",
      "MiniMaxH3PassFrames" in seamed, False)
check("the sound comes off the same window",
      (seamed["MiniMaxH3ClipAudio"][0][1]["at"],
       round(seamed["MiniMaxH3ClipAudio"][0][1]["seconds"], 4)),
      ("tail", round(22 / 24, 4)))
check("...and never off a spilled pass either", "MiniMaxH3PassAudio" in seamed, False)
segment_after = seamed["MiniMaxH3TimelineSegment"][0][1]
check("the continuing segment takes the clip's frames",
      segment_after["prev_image"][0], seamed["MiniMaxH3ClipFrames"][0][0])
check("...and the clip's sound",
      segment_after["prev_audio"][0], seamed["MiniMaxH3ClipAudio"][0][0])

# A hard cut after a clip decodes nothing out of it.
cut = by_class(with_clip(dict(CLIP), {"prompt": "after", "duration_s": 5}))
for absent in ("MiniMaxH3ClipFrames", "MiniMaxH3ClipAudio"):
    check(f"a hard cut after a clip emits no {absent}", absent in cut, False)

# The refusals reach the node rather than surfacing as a graph error.
expect_error("a clip cannot be merged into a pass",
             lambda: with_clip({"prompt": "a", "duration_s": 5},
                               {**CLIP, "merge": True}),
             "cannot share a generation")


# ---- takes and holds --------------------------------------------------------
#
# A strip shot a pass at a time. The rewrite itself is `test_compile.py`'s; what
# is checked here is that it reaches the graph — a held card costs no sampler, a
# kept take is spliced as the file it is, and the seam into the card after it
# reads that file rather than a pass nothing generated.

TAKE = {"filename": "minimax/renders/takes/H3_00001_s01.mp4", "duration_s": 5.0,
        "width": 1280, "height": 720, "has_audio": True}

stepped = by_class(with_clip(
    {"prompt": "wide", "duration_s": 5, "hold": True, "take": dict(TAKE)},
    {"prompt": "closer", "duration_s": 10, "continue": True},
    {"prompt": "cut away", "duration_s": 5, "hold": True},
))
check("a held card with no take costs no sampler", len(stepped["KSampler"]), 1)
check("...and a kept one costs none either",
      len(stepped["MiniMaxH3TimelineSegment"]), 1)
check("the kept take reaches the reel as a file", len(stepped["MiniMaxH3ClipReel"]), 1)
check("...named by the take",
      json.loads(stepped["MiniMaxH3ClipReel"][0][1]["clip_data"])["filename"],
      TAKE["filename"])
check("the card after it inherits from the take's tail",
      (len(stepped["MiniMaxH3ClipFrames"]), "MiniMaxH3PassFrames" in stepped),
      (1, False))
check("the card being shot is announced by its number on the strip",
      json.loads(stepped["MiniMaxH3TimelineSegment"][0][1]["segment_data"])["progress"],
      {"index": 2})

# The takes the save node is told to write: the cards that were actually
# sampled, and the seed each ran on.
plan = json.loads(stepped["MiniMaxH3Save"][0][1]["takes"])
check("the save node is told which card each part is", plan["cards"], [1, 2])
check("...and what seed it ran on", plan["seeds"], [100, 100])

# A card's own seed. The node's everywhere it is absent, which is every card
# until somebody rolls one.
seeded = by_class(with_clip(
    {"prompt": "wide", "duration_s": 5},
    {"prompt": "closer", "duration_s": 5, "seed": 4242},
))
check("a card with no seed of its own runs on the node's",
      sorted(i["seed"] for _, i in seeded["KSampler"]), [100, 4242])
check("...and the save node records the same two",
      json.loads(seeded["MiniMaxH3Save"][0][1]["takes"])["seeds"], [100, 4242])

# A lone generation has one take and it is the render, so there is nothing to
# write twice.
check("a one-pass render is told to keep nothing",
      by_class(with_clip({"prompt": "only", "duration_s": 5}))
      ["MiniMaxH3Save"][0][1]["takes"], "")

expect_error("a strip with every card held and nothing to play",
             lambda: with_clip({"prompt": "a", "duration_s": 5, "hold": True},
                               {"prompt": "b", "duration_s": 5, "hold": True}),
             "held with nothing to play")


# The takes themselves, written. `_takes` is the one part of this that touches
# the disk, and what it has to get right is which card each file belongs to —
# a take reported against the wrong number is a card that would play somebody
# else's shot without saying so.

import tempfile

import folder_paths as _folder_paths

_short = _run_reel(12)
_reel = [{"pass": spilled},
         {"clip": {"filename": "footage.mp4", "start": 0.0, "duration": 4.0,
                   "sound": True, "width": 8, "height": 8}},
         {"pass": _short.result[1]}]
_plan = json.dumps({"cards": [1, 2, 4], "seeds": [100, None, 4242]})

with tempfile.TemporaryDirectory() as _out:
    _was = _folder_paths.get_output_directory
    _folder_paths.get_output_directory = lambda: _out
    try:
        written = tl.MiniMaxH3Save._takes(_reel, _plan, "minimax/renders/H3", 24.0, 20)
    finally:
        _folder_paths.get_output_directory = _was

    check("only the generated passes are written",
          [take["segment"] for take in written], [1, 4])
    check("...into the takes shelf",
          {take["subfolder"] for take in written}, {"minimax/renders/takes"})
    check("...named for the card each one is",
          [take["filename"].endswith(f"_s{take['segment']:02}.mp4") for take in written],
          [True, True])
    check("...as long as the pass they came from",
          [take["duration_s"] for take in written], [2.0, 0.5])
    check("...carrying the seed each ran on",
          [take["seed"] for take in written], [100, 4242])
    check("...and whether there is sound in them",
          [take["has_audio"] for take in written], [True, True])
    check("the files are on disk",
          sorted(os.path.basename(p) for p in __import__("glob").glob(
              os.path.join(_out, "minimax", "renders", "takes", "*.mp4"))),
          sorted(take["filename"] for take in written))

check("a render with nothing to keep writes nothing",
      tl.MiniMaxH3Save._takes(_reel, "", "minimax/renders/H3", 24.0, 20), [])

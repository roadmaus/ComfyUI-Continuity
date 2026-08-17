"""The MiniMax H3 Creator node.

One node, one prompt box, one video — and no sockets at all. Media is chosen in
the UI and loaded from ComfyUI/input by filename; the weights are chosen the same
way and loaded by `models.emit_links` inside the subgraph; and the finished clip
is muxed, saved and played in the node body rather than handed to whatever the
user wired downstream. What the user attaches decides the mode, and the mode
decides which of the two checkpoints is loaded — FL2VA and Ref2VA are separate
weights, so routing the right one is the node's job rather than the user's, and
only the routed one is built. The routing can be pinned from the UI (`checkpoint`
in the blob) when you want the other weights on the same payload;
`compile._resolve_checkpoint` owns which pins are allowed.

**One node, one shot or twenty.** This was two nodes — a Creator that made one
clip and a Timeline that made several — and they were never two things. A Creator
render *is* a one-segment timeline: same payload shape, same emitted graph, and
`tests/test_creator_graph.py` asserts it. So the blob is the piece's, always: a
global prompt, one canvas, one set of weights, and a strip of segments. A lone
generation is a strip with one card on it, and the face the node wears follows
the strip rather than a mode anyone has to pick.

Workflows saved while they were two nodes hold the old shape. `compile.as_piece`
reads one as the one-shot piece it always was — see there for which fields move
and which deliberately do not.

**This node owns the sampler.** It used to hand out conditioning and let the
graph do the sampling, which meant every workflow re-assembled the same six
nodes behind it and got to choose wrong: the H3 templates sample with
`res_multistep` and decode sound with `VAEDecodeAudio`, and a hand-wired graph
that picked the defaults instead was quietly worse. Owning it also puts the two
optional accelerators somewhere they can be switched on, which they cannot be
from outside a node that ends at conditioning.

It has to own it for a second reason as well, which is what forced the Timeline
to be a node that builds graphs: segment 2 starts from segment 1's *decoded* last
frame, so the chain has a data dependency that only exists downstream of
sampling. Returning conditioning N times would not express it, and feeding the
result back into the node's own input would be a cycle the executor refuses to
run. So `execute` compiles the blob to one payload per pass, hands them to
`render.emit`, and returns that subgraph through the `expand` mechanism.

The node is also an *output* node, which is the other half of having no sockets:
`render.emit_tail` writes the file and stamps this node's id on the save node, so
the result is reported back against the node the user is looking at.

`creator_data` is the UI's serialised state and is managed entirely by `js/`. It
is a normal widget only so it round-trips through saved workflows; hand-editing
it is supported (that is how phase 1 was tested) but the frontend will overwrite
it.
"""

import json

from comfy_api.latest import ComfyExtension, io

from . import (accel, canvas, compile as compiler, facepass, hires, media,
               models, outputs, prestage, render, settings, timeline)

DEFAULT_DATA = json.dumps({
    "version": 2,
    # The standing description every segment inherits. Empty on a fresh node,
    # and on a piece of one shot there is nothing for it to stand over — the
    # writing happens on the card.
    "prompt": "",
    "aspect": "16:9",
    "short_edge": canvas.NATIVE_SHORT_EDGE,
    # Where the finished clip lands under output/. See `outputs`.
    "output_prefix": outputs.VIDEO_PREFIX,
    # Which files to load. Empty here rather than guessed: a fresh node has no
    # idea what is on this machine, and the UI fills it from the listing route.
    "models": {},
    # One card, because one shot is what a node dropped on the canvas is for.
    # The strip grows from here; nothing about the blob changes when it does.
    "segments": [
        {"prompt": "", "assets": [], "loras": [], "duration_s": 6, "checkpoint": "auto"},
    ],
}, indent=2)


def _schema(node_id, display_name, blob, deprecated=False):
    """The node's schema, which is the same schema whatever the blob is called.

    Written once and stamped twice: the surviving node, and the retired Timeline
    id that saved workflows still name. They must not drift — a workflow that
    loads under one and queues under the other has to mean the same thing — and
    the only honest way to guarantee that is for there to be one description of
    it.
    """
    import comfy.samplers

    return io.Schema(
        node_id=node_id,
        display_name=display_name,
        category="MiniMax",
        description=(
            "Describe a video and reference attached media with @. Routes to the "
            "FL2VA or Ref2VA checkpoint depending on what you attach, samples it, "
            "and saves the finished clip. Add a second shot and the same node "
            "becomes a timeline: a strip of shots, each with its own prompt, "
            "references and LoRAs, joined by cuts or by continuations."
        ),
        # This node returns a subgraph rather than tensors, because it owns
        # the sampler — see the module docstring. It is also an output node:
        # it saves the finished clip itself, which is what lets it have no
        # output sockets either.
        enable_expand=True,
        is_output_node=True,
        is_deprecated=deprecated,
        inputs=[
            # No model sockets. The weights are named in the blob and
            # `models.emit_links` builds the loaders inside the subgraph —
            # see that module for why that is better than five wires.
            io.String.Input(blob, multiline=True, default=DEFAULT_DATA),
            io.Int.Input("seed", default=0, min=0, max=0xffffffffffffffff, control_after_generate=True,
                tooltip="The seed for the whole piece: every segment, chained or single, and every refine and face pass inside them, runs on this number. What separates consecutive shots is their prompts and their seams, not their noise."),
            io.Int.Input("steps", default=20, min=1, max=10000),
            # The released H3 checkpoints are CFG-distilled, so guidance is
            # already in the weights and 1.0 is the value they were trained
            # to run at. Left as an ordinary widget: it is a default, not a
            # constraint, and anyone who wants to push it can.
            io.Float.Input("cfg", default=1.0, min=0.0, max=100.0, step=0.1, round=0.01),
            # What the official H3 templates sample with. Left to the combo's
            # own default this would be `euler`, which is simply the first
            # name in core's list — a 20-step H3 render is visibly worse for
            # it, and that is the whole difference between this node and a
            # hand-wired graph copied off the template.
            io.Combo.Input("sampler_name", options=comfy.samplers.KSampler.SAMPLERS,
                           default="res_multistep"),
            io.Combo.Input("scheduler", options=comfy.samplers.KSampler.SCHEDULERS,
                           default="simple",
                           tooltip="The templates use 'simple'; for reference-heavy prompts they suggest 'beta' or 'normal' instead."),
            # H3 runs the picture and the sound on separate flow schedules,
            # and the defaults here are the checkpoints' own — at exactly
            # these values no shift node is emitted, so an untouched row
            # renders exactly as it always has. Turbo LoRA cards name the
            # schedule they were distilled against; the turbo switch sets
            # these with the rest of the row and puts them back on release.
            io.Float.Input("shift_video", default=render.SHIFT_DEFAULTS[0],
                min=0.01, max=100.0, step=0.01,
                tooltip="The video flow shift. 12 is the checkpoints' own value; a turbo LoRA's card may name another."),
            io.Float.Input("shift_audio", default=render.SHIFT_DEFAULTS[1],
                min=0.01, max=100.0, step=0.01,
                tooltip="The audio flow shift. 3 is the checkpoints' own value. A wrong one distorts the soundtrack before it touches the picture."),
            # Both accelerators are other people's nodes and both are off
            # until asked for — see `accel.py`. They patch the model, so they
            # cost nothing to leave off and nothing here reimplements them.
            io.Combo.Input("block_cache", options=accel.BLOCK_CACHE_MODES, default="off",
                tooltip="Step caching, one implementation at a time. safe/fast/aggressive are FirstBlockCache presets (needs ComfyUI-MiniMaxH3-FirstBlockCache); 'easy' is core's EasyCache; 'tea' is TeaCache (needs ComfyUI-MiniMaxH3-TeaCache). All trade fidelity for speed — A/B before trusting one on a final render."),
            io.Boolean.Input("spectrum", default=False,
                tooltip="Spectrum: forecast features across steps instead of evaluating every one. Needs ComfyUI-Spectrum-MiniMax-H3. Combines with block_cache; cannot be combined with EasyCache."),
            io.Float.Input("spectrum_blend", default=0.5, min=0.0, max=1.0, step=0.01,
                tooltip="Spectrum's video spectral share. Higher is faster and further from a native render. Ignored unless 'spectrum' is on."),
            io.Boolean.Input("sage", default=False,
                tooltip="Sage attention: run H3's attention quantized (int8 queries and keys, fp8 or fp16 values). Faster and, unlike the caches, lower peak VRAM. Needs ComfyUI-KJNodes and the sageattention package, on an NVIDIA card. Composes with everything above."),
        ],
        # Nothing comes out either: the render is saved and shown in the node
        # body, so there is no socket for a graph to hang off.
        outputs=[],
        hidden=[io.Hidden.unique_id],
    )


def _fingerprint(blob):
    """Re-run when a referenced file changes on disk.

    Media is addressed by filename, not by a wired tensor, so ComfyUI has
    nothing else to notice a replaced file by. Lifted first, so an old blob's
    keyframes are walked as the shot's rather than missed for sitting where a
    piece keeps its reference pool.
    """
    try:
        return (blob, timeline.stamps(compiler.as_piece(json.loads(blob))))
    except Exception:
        return (blob, ())


def _render(blob, seed, steps, cfg, sampler_name, scheduler,
            block_cache, spectrum, spectrum_blend, unique_id,
            shift_video=render.SHIFT_DEFAULTS[0],
            shift_audio=render.SHIFT_DEFAULTS[1],
            sage=False):
    """The whole of what either node id does. See the module docstring."""
    try:
        data = compiler.as_piece(json.loads(blob))
    except json.JSONDecodeError as exc:
        raise ValueError(f"the node's data is not valid JSON: {exc}") from exc

    # One payload per pass, and a pass is a run of merged segments — usually one
    # segment long, and on a piece of one shot there is exactly one of each. How
    # the piece is *compiled* is the only thing the merging changes; what is
    # built from the result is the same loop either way. `render.emit` wires each
    # payload to the one before it, and a pass holding several segments simply
    # has no seam inside it to wire.
    payloads = compiler.timeline_payloads(data, image_size_lookup=media.image_size)
    labels = timeline.labels(compiler.timeline_runs(data))

    graph = render.emit(
        payloads, labels,
        models.Weights.from_blob(data),
        render.Sampling(seed=seed, steps=steps, cfg=cfg,
                        sampler_name=sampler_name, scheduler=scheduler,
                        shift_video=shift_video, shift_audio=shift_audio),
        accel.Settings(block_cache=block_cache, spectrum=spectrum,
                       spectrum_blend=spectrum_blend, sage=sage),
        unique_id,
        # Resolved here rather than inside the save node: a prefix that cannot be
        # used should stop the queue before anything is sampled, not after —
        # `get_save_image_path` raising at the end of a render costs the user the
        # render.
        filename_prefix=outputs.video(data, settings.video_prefix()))
    return render.expanded(graph)


class MiniMaxH3Creator(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return _schema("MiniMaxH3Creator", "MiniMax H3 Creator", "creator_data")

    @classmethod
    def fingerprint_inputs(cls, creator_data, **kwargs):
        return _fingerprint(creator_data)

    @classmethod
    def execute(cls, creator_data, seed, steps, cfg, sampler_name, scheduler,
                block_cache="off", spectrum=False, spectrum_blend=0.5,
                shift_video=render.SHIFT_DEFAULTS[0],
                shift_audio=render.SHIFT_DEFAULTS[1],
                sage=False) -> io.NodeOutput:
        return _render(creator_data, seed, steps, cfg, sampler_name, scheduler,
                       block_cache, spectrum, spectrum_blend, cls.hidden.unique_id,
                       shift_video=shift_video, shift_audio=shift_audio, sage=sage)


class MiniMaxH3Timeline(io.ComfyNode):
    """The Timeline node id, for the workflows that still hold one.

    Deprecated rather than deleted, and deprecated rather than aliased away: a
    node id that stops existing is a red box on somebody's canvas and a workflow
    they cannot queue, while `is_deprecated` keeps it loadable and takes it out
    of the node search so nobody reaches for it again.

    A sibling rather than a subclass, and a schema built from the same function:
    the two ids differ in exactly one thing — what the blob widget is called —
    and everything that would let them differ in anything else is written once,
    above. `timeline_data` keeps its name here because the value in a saved
    workflow is restored against the widget list this schema declares, and a
    Timeline that loaded its blob into a differently-named slot would be a node
    that opens empty.

    The frontend mounts the same body on both ids, so a workflow carrying this
    one behaves exactly as a Creator does. Only the title on the canvas differs.
    """

    @classmethod
    def define_schema(cls):
        return _schema("MiniMaxH3Timeline", "MiniMax H3 Timeline", "timeline_data",
                       deprecated=True)

    @classmethod
    def fingerprint_inputs(cls, timeline_data, **kwargs):
        return _fingerprint(timeline_data)

    @classmethod
    def execute(cls, timeline_data, seed, steps, cfg, sampler_name, scheduler,
                block_cache="off", spectrum=False, spectrum_blend=0.5,
                shift_video=render.SHIFT_DEFAULTS[0],
                shift_audio=render.SHIFT_DEFAULTS[1],
                sage=False) -> io.NodeOutput:
        return _render(timeline_data, seed, steps, cfg, sampler_name, scheduler,
                       block_cache, spectrum, spectrum_blend, cls.hidden.unique_id,
                       shift_video=shift_video, shift_audio=shift_audio, sage=sage)


class MiniMaxCreatorExtension(ComfyExtension):
    async def get_node_list(self):
        return [MiniMaxH3Creator, MiniMaxH3Timeline,
                *timeline.NODES, *prestage.NODES, *hires.NODES, *facepass.NODES]


async def comfy_entrypoint() -> MiniMaxCreatorExtension:
    return MiniMaxCreatorExtension()

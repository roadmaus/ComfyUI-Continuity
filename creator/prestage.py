"""The MiniMax H3 PreStage node: stills for the pipeline, made on the left.

The Creator consumes images — a start frame, an end frame, references, style
sheets — and until this node existed it had no way to make one. The PreStage
generates them locally on any still family the registry knows — Krea 2,
Ideogram 4.0, Qwen Image Edit, Flux 2 Klein, MiniMax H3 Image and the rest, all
native in core — and saves them where the picker already looks, so a finished
still is one chip away from being the next render's keyframe.

Every one of them is an image family now. MiniMax used to be the exception: a
still from it was a video generation with one latent frame decoded as a
picture, driven by a Creator-shaped request of its own. MiniMax H3 Image
replaced that (`families/h3image`), and its `migrate` is where an old blob's
request is lifted into the shared fields.

It is built exactly like the Creator, because it is driven exactly like the
Creator: zero sockets, one JSON blob the UI owns, weights named by filename,
and an expanded subgraph that loads, samples, decodes and saves — see
`creator_node.py`'s docstring for why a node that samples cannot be an ordinary
node. The one difference is social rather than structural: a PreStage is a
property of the shot being set up, not a node the user hunts the menu for, so
the frontend spawns and removes it from a pill on the Creator/Timeline body
(`web/creator/prestage.js`) rather than expecting it to be placed by
hand. It still *is* an ordinary node underneath — placeable, copyable,
saveable — because anything else would fight LiteGraph for no benefit.

Queueing both nodes at once is deliberately not an ordering: the hand-off is by
file, so there is no execution edge to get wrong, and ComfyUI's input-hash
caching makes an untouched PreStage a cache hit on the queue that renders the
video.
"""

import json

from comfy_api.latest import io

from . import (compile_image, media, neural, refmod, render_image, sampling,
               settings, variations)
from .core import emit as loop
from .compile import CompileError
from .families import registry
from .families.h3 import subjects
from .screens import spec as screen_spec
from .families.ideogram4 import still as ideogram4
from .families.krea2 import still as krea2

DEFAULT_DATA = json.dumps({
    "version": 1,
    "arch": registry.DEFAULT_STILL_ARCH,
    "prompt": "",
    "aspect": compile_image.DEFAULT_ASPECT,
    "short_edge": compile_image.DEFAULT_SHORT_EDGE,
    "init": None,
    "refs": [],
    "loras": [],
    "turbo": {"on": False, "quality": krea2.DEFAULT_TURBO_QUALITY, "saved": None},
    "quality": ideogram4.DEFAULT_IDEOGRAM_QUALITY,
    # Per-arch sub-blocks, so switching the model pill never forgets the other
    # side's files. Empty rather than guessed — the UI fills it from the
    # listing route, exactly as the Creator's block is filled. Keyed off the
    # pill's own arches rather than written down, so a family registering
    # itself gets a block here too and this cannot go stale behind one.
    "models": {arch: {} for arch in registry.STILL_ARCHES},
    # The DLSS 5 refiner over the finished still. Off, and the whole block is
    # what the pill writes when it is on — see `neural.DEFAULTS`.
    "neural": dict(neural.DEFAULTS),
    # A hint for the frontend's peer discovery, never authoritative: node ids
    # renumber on paste, so the pill re-derives the relationship by scan.
    "peer": None,
}, indent=2)


def _cast_refmod_spaces(data, family):
    """Stamp a still Cast's standalone latents from their actual file headers.

    Presets persist filenames, not authoritative latent-space metadata. The
    pure Cast compiler needs the space to choose a look; without this step a
    valid Klein mod becomes only its description. Keep file access here at
    the node boundary, as the chat route does, and never load tensor payloads.
    """
    space = (getattr(family, "REFMOD", None) or {}).get("space")
    if not space or not getattr(family, "TAKES_REFS", False):
        return data
    raw = [s for s in data.get("subjects") or [] if isinstance(s, dict) and s.get("handle")]
    if not raw:
        return data
    family_id = registry.STILL_ARCHES.get(getattr(family, "ARCH", None))
    try:
        cast = subjects.parse(raw, family_id)
    except subjects.SubjectError as exc:
        raise CompileError(str(exc)) from exc
    refs = [dict(r) if isinstance(r, dict) else r for r in data.get("refs") or []]
    by_handle = {str(r["handle"]): r for r in refs if isinstance(r, dict) and r.get("handle")}
    spaces = {}
    for member in subjects.cited(cast, [str(data.get("prompt") or "")]):
        # Supply every source's header facts; cast_into_still alone chooses
        # the first usable look and whether this member is sent as words.
        for handle in member.sources:
            ref = by_handle.get(handle)
            if ref is None:
                continue
            filename = ref.get("filename")
            if not refmod.is_mod(filename):
                continue
            if filename not in spaces:
                try:
                    meta = refmod.header(refmod.resolve(filename))
                    # A clip or a stack is a look in H3's space that a still
                    # family sharing that space cannot read (MiniMax H3
                    # Image): treated as unreadable, so another look or the
                    # member's words stand in.
                    usable = meta["kind"] == "image" or family.REFMOD.get("clips")
                    spaces[filename] = meta["space"] if usable else None
                except refmod.RefModError:
                    spaces[filename] = None
            # Never trust stale/browser-supplied metadata. Like the chat
            # route, an unreadable file has no space and falls back to words
            # (or another usable look) in the pure compiler.
            ref.pop("space", None)
            if spaces[filename] is not None:
                ref["space"] = spaces[filename]
    return {**data, "refs": refs}


class MiniMaxH3PreStage(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        import comfy.samplers

        return io.Schema(
            node_id="MiniMaxH3PreStage",
            display_name="Continuity PreStage",
            category="Continuity",
            description=(
                "Generate a still with Krea 2, Ideogram 4.0, MiniMax H3 Image or another image model for "
                "the video pipeline — a start or end frame, a reference, a style "
                "sheet. Spawned from the pre-stage pill on a Continuity node."
            ),
            enable_expand=True,
            is_output_node=True,
            # The same sampler row, under the same names, as the two video
            # nodes — a control that means the same thing is not called
            # something else here. Defaults are Krea 2 RAW's; the arch and
            # turbo pills rewrite them.
            inputs=[
                io.String.Input("prestage_data", multiline=True, default=DEFAULT_DATA),
                io.Int.Input("seed", default=0, min=0, max=0xffffffffffffffff, control_after_generate=True),
                io.Int.Input("steps", default=krea2.KREA_RAW["steps"], min=1, max=10000),
                io.Float.Input("cfg", default=krea2.KREA_RAW["cfg"], min=0.0, max=100.0, step=0.1, round=0.01),
                io.Combo.Input("sampler_name", options=comfy.samplers.KSampler.SAMPLERS,
                               default=krea2.KREA_RAW["sampler_name"]),
                io.Combo.Input("scheduler", options=comfy.samplers.KSampler.SCHEDULERS,
                               default=krea2.KREA_RAW["scheduler"],
                               tooltip="Krea 2 samples on this schedule. Ideogram 4 owns its own resolution-shifted schedule and ignores it."),
            ],
            outputs=[],
            hidden=[io.Hidden.unique_id],
        )

    @classmethod
    def fingerprint_inputs(cls, prestage_data, **kwargs):
        """Re-run when a referenced file changes on disk — same contract as the
        Creator: media is addressed by filename, so mtimes are all ComfyUI has
        to notice a replaced file by."""
        import os

        from . import lora

        stamps = []
        try:
            data = json.loads(prestage_data)
            names = [ref.get("filename") if isinstance(ref, dict) else ref
                     for ref in data.get("refs") or []]
            init = data.get("init")
            if isinstance(init, dict):
                names.append(init.get("filename"))
            # A blob from before MiniMax H3 Image keeps its media in the old
            # branch's request until it is compiled; watch those files too.
            request = (data.get("minimax") or {}).get("request") or {}
            names.extend(asset.get("filename") for asset in request.get("assets") or [])
            entries = list(data.get("loras") or []) + list(request.get("loras") or [])
            for name in names:
                try:
                    stamps.append(os.path.getmtime(media.resolve(name or "")))
                except Exception:
                    stamps.append(None)
            for entry in entries:
                try:
                    stamps.append(os.path.getmtime(lora.resolve(entry.get("name", ""))))
                except Exception:
                    stamps.append(None)
        except Exception:
            pass
        # The screen tracker is this machine's and reaches the render — see
        # `MiniMaxH3Creator`'s fingerprint.
        return (prestage_data, tuple(stamps),
                tuple(sorted(settings.screen_tracker().items())))

    @classmethod
    def execute(cls, prestage_data, seed, steps, cfg, sampler_name, scheduler) -> io.NodeOutput:
        try:
            data = json.loads(prestage_data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"prestage_data is not valid JSON: {exc}") from exc

        # The row off the blob, falling back to the widgets — see `sampling.py`.
        # This node is the case that argues for the move most plainly: its
        # architectures want different rows (Krea at 52 steps and cfg 3.5,
        # Ideogram at 7.0, H3 Image at 6 and 1.0) and there is one static schema
        # underneath them wearing Krea's numbers. The accelerator half comes back
        # off and is dropped: no image branch emits a patch, so there is nothing
        # here for one to sit between.
        sampler, _ = sampling.resolve(data, {
            "seed": seed, "steps": steps, "cfg": cfg,
            "sampler_name": sampler_name, "scheduler": scheduler,
        })

        # A `{day|night}` in the prompt is chosen here, on the seed this render
        # samples on, the way `compile.varied_piece` chooses for a strip. A
        # still is one card, so it chooses as card 1 — the number the prompt
        # box lights the alternative by. A blob from before MiniMax H3 Image is
        # lifted into the shared fields first, so its sentence is chosen here
        # like everybody else's (`h3image.still.migrate`).
        arch = data.get("arch", registry.DEFAULT_STILL_ARCH)
        family = registry.still(arch)
        if family is None:
            raise ValueError(f"unknown model architecture {arch!r}")
        migrate = getattr(family, "migrate", None)
        if migrate is not None:
            data = migrate(data)
        data = variations.vary_mapping(data, sampler.seed, 1, keys=("prompt",))
        # Then the refiner's prose in the sentence's place, before anything
        # reads the prompt — the cast's saved renditions below are looked up
        # off the members it cites, and a rewrite may cite one the typed
        # sentence did not.
        data = compile_image.with_refined(data)

        # One dispatch for every pill: the registry answers the arch with the
        # family's still module, and every family speaks the same two verbs.
        # The screens' trackers as this machine draws them (`settings`),
        # stamped on before compiling so they are part of what the render is.
        if data.get("screens"):
            data = {**data, "screens": screen_spec.stamp(data["screens"],
                                                         settings.screen_tracker())}
        try:
            data = _cast_refmod_spaces(data, family)
            plan = family.compile_still(data, media.image_size)
        except CompileError as exc:
            raise ValueError(str(exc)) from exc
        # The output prefix is refused before anything is sampled — see
        # MiniMaxH3Creator.execute.
        graph = family.emit_still(data, plan, sampler, cls.hidden.unique_id)
        return loop.expanded(graph)


class MiniMaxH3SaveImage(io.ComfyNode):
    """The last node of an image render: the still, written under output/.

    Core's `SaveImage` would write the same file, but it reports under
    "images", the key the stock frontend preview widget keys on — and with the
    PreStage's id stamped on this node, that widget would land on the canvas
    right under the stage card already showing the same picture. A key core
    does not know keeps the report and loses the widget; stage.js reads it by
    name, exactly as it reads `mmc_video`.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3SaveImage",
            display_name="Continuity Save Image",
            category="Continuity/internal",
            description="Writes a pre-stage render under output/ and reports it to the stage card.",
            is_dev_only=True,
            is_output_node=True,
            inputs=[
                io.Image.Input("images"),
                # The arch pill's opening choice, so a hand-wired save node
                # writes somewhere real. Every graph this pack emits passes the
                # prefix explicitly — see `render_image.default_prefix`.
                io.String.Input("filename_prefix", default=render_image.default_prefix(
                    registry.STILL_ARCHES[registry.DEFAULT_STILL_ARCH])),
            ],
            # Never wired to anything: `core.emit.expanded` exports it so the
            # node that expanded this graph waits for the file (#97).
            outputs=[io.Boolean.Output("done")],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo, io.Hidden.unique_id, io.Hidden.dynprompt],
        )

    @classmethod
    def execute(cls, images, filename_prefix) -> io.NodeOutput:
        import os

        import numpy as np
        from PIL import Image
        from PIL.PngImagePlugin import PngInfo

        import folder_paths
        from comfy.cli_args import args

        height, width = int(images.shape[1]), int(images.shape[2])
        directory, name, counter, subfolder, _ = folder_paths.get_save_image_path(
            filename_prefix, folder_paths.get_output_directory(), width, height)

        # The workflow, so a still dropped back onto the canvas rebuilds the
        # node that made it — the same two hidden fields core's savers write.
        collected = None
        if not args.disable_metadata:
            from . import neuraltwin

            collected = dict(cls.hidden.extra_pnginfo or {})
            collected.pop(neuraltwin.PRODUCER_KEY, None)
            if cls.hidden.prompt is not None:
                collected["prompt"] = cls.hidden.prompt

        results = []
        for index, image in enumerate(images):
            metadata = None
            if collected is not None:
                metadata = PngInfo()
                # A batch shares one producer but not one comparison picture.
                # Stamp each file separately so image 2 compares with image 2.
                producer = neuraltwin.producer_metadata(cls.hidden, index)
                tags = {**collected, **({neuraltwin.PRODUCER_KEY: producer} if producer else {})}
                for key, value in tags.items():
                    metadata.add_text(key, json.dumps(value))
            array = (image.cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
            filename = f"{name}_{counter:05}_.png"
            Image.fromarray(array).save(os.path.join(directory, filename),
                                        pnginfo=metadata, compress_level=4)
            results.append({"filename": filename, "subfolder": subfolder, "type": "output"})
            counter += 1

        return io.NodeOutput(True, ui={"mmc_image": results})


NODES = [MiniMaxH3PreStage, MiniMaxH3SaveImage]

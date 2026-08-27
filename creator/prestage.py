"""The MiniMax H3 PreStage node: stills for the pipeline, made on the left.

The Creator consumes images — a start frame, an end frame, references, style
sheets — and until this node existed it had no way to make one. The PreStage
generates them locally with Krea 2, Ideogram 4.0 (both open weights, both native
in core) or MiniMax H3 itself, and saves them where the picker already looks, so
a finished still is one chip away from being the next render's keyframe.

The third of those is a different animal and lives in `families/h3/still.py`:
H3 is a video model, so a still from it is a video generation with one latent
frame decoded as a picture. It reuses the video pipeline outright — the same
segment node, the same checkpoints, the same canvas, the same VAE — which is the
point of having it: no second model family loaded, no extra file to fetch, and a
keyframe made by the weights that will render the shot it opens.

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

from . import canvas, compile_image, media, render_image, sampling
from .core import emit as loop
from .compile import CompileError
from .families import registry
from .families.h3 import still
from .families.h3 import declare as h3_rules
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
    # The H3 branch: how long a clip it samples and which of that clip's latent
    # frames becomes the picture, plus the generation itself in the Creator's
    # own shape — because it is one. See `families/h3/still`.
    "minimax": {
        "frames": still.DEFAULT_FRAMES,
        "latent_index": still.DEFAULT_LATENT_INDEX,
        "request": {"prompt": "", "assets": [], "loras": [],
                    "aspect": "16:9", "short_edge": h3_rules.RULES.native_short_edge,
                    "models": {}},
    },
    # Per-arch sub-blocks, so switching the model pill never forgets the other
    # side's files. Empty rather than guessed — the UI fills it from the
    # listing route, exactly as the Creator's block is filled. Keyed off the
    # pill's own arches rather than written down, so a family registering
    # itself gets a block here too and this cannot go stale behind one.
    "models": {arch: {} for arch in registry.STILL_ARCHES},
    # A hint for the frontend's peer discovery, never authoritative: node ids
    # renumber on paste, so the pill re-derives the relationship by scan.
    "peer": None,
}, indent=2)


class MiniMaxH3PreStage(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        import comfy.samplers

        return io.Schema(
            node_id="MiniMaxH3PreStage",
            display_name="Continuity PreStage",
            category="Continuity",
            description=(
                "Generate a still with Krea 2, Ideogram 4.0 or MiniMax H3 for "
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
            # The H3 branch keeps its media in a creator-shaped request.
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
        return (prestage_data, tuple(stamps))

    @classmethod
    def execute(cls, prestage_data, seed, steps, cfg, sampler_name, scheduler) -> io.NodeOutput:
        try:
            data = json.loads(prestage_data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"prestage_data is not valid JSON: {exc}") from exc

        # The row off the blob, falling back to the widgets — see `sampling.py`.
        # This node is the case that argues for the move most plainly: its three
        # architectures want three different rows (Krea at 52 steps and cfg 3.5,
        # Ideogram at 7.0, H3 at 20 and 1.0) and there is one static schema
        # underneath them wearing Krea's numbers. The accelerator half comes back
        # off and is dropped: no image branch emits a patch, so there is nothing
        # here for one to sit between.
        sampler, _ = sampling.resolve(data, {
            "seed": seed, "steps": steps, "cfg": cfg,
            "sampler_name": sampler_name, "scheduler": scheduler,
        })

        # One dispatch for all three pills: the registry answers the arch with
        # the family's still module, and every family speaks the same two
        # verbs. H3's answer is a video render that keeps one latent frame —
        # same widgets, same blob, same save node; everything between them is
        # the other pipeline (`families/h3/still.py`).
        arch = data.get("arch", registry.DEFAULT_STILL_ARCH)
        family = registry.still(arch)
        if family is None:
            raise ValueError(f"unknown model architecture {arch!r}")
        try:
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
            outputs=[],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
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
        metadata = None
        if not args.disable_metadata:
            metadata = PngInfo()
            if cls.hidden.prompt is not None:
                metadata.add_text("prompt", json.dumps(cls.hidden.prompt))
            for key, value in (cls.hidden.extra_pnginfo or {}).items():
                metadata.add_text(key, json.dumps(value))

        results = []
        for image in images:
            array = (image.cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
            filename = f"{name}_{counter:05}_.png"
            Image.fromarray(array).save(os.path.join(directory, filename),
                                        pnginfo=metadata, compress_level=4)
            results.append({"filename": filename, "subfolder": subfolder, "type": "output"})
            counter += 1

        return io.NodeOutput(ui={"mmc_image": results})


class MiniMaxH3StillLatent(io.ComfyNode):
    """The shortest legal clip around one temporal slice of a sampled H3 latent.

    H3 samples a NestedTensor pair — video `[B,24,T,H/16,W/16]` and audio — and
    this takes the video half's frame `index` and hands it on as a plain video
    latent of *two* tokens: the chosen one, twice.

    Two rather than one because the H3 VAE has no decode for a single token. Its
    grid is 17k+5 pixel frames <-> 5k+2 latent tokens, so the shortest legal clip
    is two tokens, and handing the decoder one produces tile seams and 16px
    patch-grid noise instead of a picture — 31.4 and 93.7 mean absolute error
    tiled and untiled, against 3.92 for a legal decode of the same content
    (Comfy-Org/ComfyUI#15416). Duplicating the token and keeping pixel frame 0 of
    the five that come back is what that issue settled on, and for index 0 it is
    exact: the VAE is causal, so the first pixel frame is a function of the first
    token alone and never sees the copy. A later index is decoded as if it opened
    a clip, which is the same approximation the reference workaround makes.

    This is why a still needs no image VAE. The experimental T=1 decoder this
    branch used to require exists to make the illegal shape decodable; the legal
    shape is decoded by the video VAE the render already loads, and better —
    that decoder is fitted on 51k images and its own card warns it softens text,
    hair and microtexture.

    Negative indexes from the end, so -1 is the clip's last latent frame. The
    audio half is dropped here rather than never generated: the DiT samples the
    pair together, and a still simply does not read one of them.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3StillLatent",
            display_name="H3 Still Latent",
            category="Continuity/internal",
            description="Takes one temporal frame of a sampled H3 latent as the shortest clip the H3 VAE can decode.",
            is_dev_only=True,
            inputs=[
                io.Latent.Input("samples"),
                io.Int.Input("index", default=0, min=-4096, max=4096,
                             tooltip="Which latent frame becomes the picture. 0 is the causal first frame, where the decode is exact; a later frame is decoded as if it opened the clip. Negative counts from the end."),
            ],
            outputs=[io.Latent.Output()],
        )

    @classmethod
    def execute(cls, samples, index) -> io.NodeOutput:
        latent = samples["samples"]
        # The pair arrives nested from the sampler and un-nested from anything
        # that has already taken it apart; both are worth accepting, because
        # this node is also the obvious place to point a hand-built graph.
        video = latent.unbind()[0] if getattr(latent, "is_nested", False) else latent
        if video.ndim != 5:
            raise ValueError(
                f"This is not a video latent — it has {video.ndim} dimensions, and "
                f"an H3 latent has five [B, 24, T, H/16, W/16]."
            )

        total = video.shape[2]
        resolved = index if index >= 0 else total + index
        if not 0 <= resolved < total:
            raise ValueError(
                f"Latent frame {index} does not exist: this clip packs into "
                f"{total} latent frames (0..{total - 1})."
            )
        # `repeat` copies, so nothing downstream holds the whole sampled clip
        # alive to read one frame of it — and the copy is the second token the
        # VAE needs to have a legal clip to decode.
        return io.NodeOutput(
            {"samples": video[:, :, resolved:resolved + 1].repeat(1, 1, 2, 1, 1)})


NODES = [MiniMaxH3PreStage, MiniMaxH3SaveImage, MiniMaxH3StillLatent]

"""One image generation, as a graph. The PreStage's half of `render.py`.

The PreStage owns its sampler for the reason the Creator does: a node that
samples has to *be* the sampler, and ComfyUI has no way to say that except by
returning a subgraph. Unlike the video render there is no segment worker node —
an image render is loaders, an encode, a sampler and a decode, all of which are
core's, so the graph is emitted from core nodes directly and core's caching
falls out per node (an unchanged prompt re-decodes nothing).

This is the *shared* half: the loaders, the LoRA patching, the starting
latent and the save tail that every image family's graph is built around. The
sampler shape between them is the family's own — `emit` takes the family
module and hands off to its `emit_graph`, so Krea 2's `KSampler` branch lives
in `families/krea2/still.py` and Ideogram's dual-model
`SamplerCustomAdvanced` branch in `families/ideogram4/still.py`, both taken
verbatim from the official ComfyUI templates rather than invented.

The weights are named in the blob per architecture, so switching the model
pill never forgets the other side's files — the same reason `models.Weights`
keeps both video checkpoints.
"""

from dataclasses import dataclass, field

from . import models as core, outputs
from .compile import CompileError
from .models import is_gguf, loader_for

SAVE_NODE = "MiniMaxH3SaveImage"

# The preview override wants a playback rate for the animated clip it makes of a
# video latent. A still has one frame and no such clip; this is what gets passed
# so the required input has a number.
PREVIEW_FPS = 24.0


def default_prefix(family):
    """Where `family`'s stills land when the caller names nowhere.

    A folder per family under the stills shelf — `outputs` owns the shape of
    that tree and what a typed prefix is allowed to be, and the family owns its
    name. `family` is a family id — `emit` below takes the still *module* and
    maps its `ARCH` through the registry, because "minimax" is the pre-stage's
    permanent alias for H3 and not a folder anybody should see.

    Every real caller passes a prefix: they resolve the setting above the graph,
    so an unusable one stops the queue before anything is sampled. This is the
    save node's own widget default and what a hand-driven `emit` gets.
    """
    from .families import registry

    return outputs.default_image(family, registry.OUTPUT_STEM[family])


# Which directory each pickable field browses — ComfyUI's own folder keys, and
# the listing route hands the same map to the frontend.
FOLDERS = {
    "model": "diffusion_models",
    "turbo_model": "diffusion_models",
    "uncond_model": "diffusion_models",
    "clip": "text_encoders",
    "vae": "vae",
}

LABEL = {
    "model": "the checkpoint",
    "turbo_model": "the Turbo checkpoint",
    "uncond_model": "the unconditional checkpoint",
    "clip": "the text encoder",
    "vae": "the VAE",
}

@dataclass(frozen=True)
class ImageWeights:
    """The files the node was pointed at for one architecture.

    Unset is the normal state of a freshly spawned node, so this validates at
    emit time and names the empty field — the same contract `models.Weights`
    holds for the video side.
    """

    arch: str
    files: dict = field(default_factory=dict)
    dtype: str = "default"

    @classmethod
    def from_blob(cls, data, family):
        """The `models` block of a prestage_data blob, for `family`'s arch.

        The block is `{krea2: {...}, ideogram4: {...}, dtype}` — per-arch
        sub-blocks so flipping the model pill never forgets the other side.
        Which fields a side carries is the family's declaration.
        """
        arch = family.ARCH
        block = (data or {}).get("models")
        if not isinstance(block, dict):
            block = {}
        side = block.get(arch)
        if not isinstance(side, dict):
            side = {}
        files = {}
        for name in family.FIELDS:
            value = side.get(name)
            if isinstance(value, str) and value.strip():
                files[name] = value.strip()
        dtype = block.get("dtype")
        return cls(arch=arch,
                   files=files,
                   dtype=dtype if isinstance(dtype, str) and dtype else "default")

    def get(self, name):
        return self.files.get(name)


def check(weights, payload):
    """Refuse now if a file this render needs was never picked.

    The DiT field is whichever one the payload resolved (`model` or
    `turbo_model`); the unconditional checkpoint is never required, because the
    guider degrades to ordinary CFG without it.
    """
    for name in ("clip", "vae", payload.checkpoint_field):
        if weights.get(name):
            continue
        # Not .capitalize(), which would lowercase "Turbo" mid-label.
        label = LABEL[name][0].upper() + LABEL[name][1:]
        raise ValueError(
            f"{label} has not been picked. Open the "
            f"pre-stage node's 'weights' control and choose a file from "
            f"models/{FOLDERS[name]}."
        )


def emit_unet(graph, weights, name):
    """One DiT loader, GGUF-aware the way `models.Links` is: a `.gguf`
    filename swaps the class through `loader_for`, and `weight_dtype` is only a
    core-loader input — a quantized file's precision is already decided."""
    filename = weights.get(name)
    node_id, _ = loader_for("UNETLoader", None, filename)
    dtype = {} if is_gguf(filename) else {"weight_dtype": weights.dtype}
    return graph.node(node_id, unet_name=filename, **dtype).out(0)


def emit(payload, weights, sampling, unique_id, family, filename_prefix=None):
    """-> the graph, which the caller finalizes with `render.expanded`.

    `sampling` is a `render.Sampling` — the same widget names as the video
    nodes, meaning the same thing; what each family's branch does with the row
    is its own (Ideogram's schedule ignores `scheduler` outright). `family` is
    the same module `compile_prestage` compiled the payload with.
    """
    from comfy_execution.graph_utils import GraphBuilder

    from .families import registry

    if filename_prefix is None:
        filename_prefix = default_prefix(registry.STILL_ARCHES[family.ARCH])
    if payload.arch != weights.arch:
        raise CompileError("the payload and the weights disagree about the architecture")
    family.require_support()
    check(weights, payload)

    graph = GraphBuilder()

    clip = graph.node(loader_for("CLIPLoader", None, weights.get("clip"))[0],
                      clip_name=weights.get("clip"),
                      type=family.CLIP_TYPE).out(0)
    vae = graph.node("VAELoader", vae_name=weights.get("vae")).out(0)
    model = emit_unet(graph, weights, payload.checkpoint_field)
    # Model-only, exactly as the official workflows patch these DiTs — there is
    # no text-encoder half to a Krea or Ideogram LoRA.
    for entry in payload.loras:
        model = graph.node("LoraLoaderModelOnly", model=model,
                           lora_name=entry["name"],
                           strength_model=entry["strength"]).out(0)
    # The same preview override the video render and the H3 still are patched
    # with, and here for the same reason: core's previewer paints its frames
    # onto the canvas node over the top of the node body, where the stage card
    # is not, and where the fullscreen editor cannot see them at all. The
    # override broadcasts them instead — `kj_preview_override`, which stage.js
    # reads — and suppresses core's. `preview_frames` is ignored on a 4D image
    # latent, and so is the rate; both are passed because the node requires
    # them. Adds nothing when KJNodes is not installed.
    #
    # Patched here rather than in each family's branch because every wrapper
    # downstream of it clones the patcher and carries it along: Krea's
    # `ModelSamplingFlux` on the reference branch, Ideogram's `CFGOverride` and
    # its guider.
    model = core.graph_preview(graph, model, weights, PREVIEW_FPS)

    family.emit_graph(graph, payload, sampling, weights, clip, vae, model,
                      unique_id, filename_prefix)
    return graph


def emit_latent(graph, payload, vae, empty_node):
    """The starting latent: empty for t2i, the encoded init image for img2img.

    The init is scaled to the resolved canvas rather than the canvas following
    the init exactly — `compile_image` already derived the aspect from the
    image, so this only absorbs the /16 snap. Returns (latent, denoise).
    """
    if payload.init is None:
        empty = graph.node(empty_node, width=payload.width, height=payload.height,
                           batch_size=1)
        return empty.out(0), 1.0
    image = graph.node("LoadImage", image=payload.init["filename"]).out(0)
    scaled = graph.node("ImageScale", image=image, upscale_method="lanczos",
                        width=payload.width, height=payload.height,
                        crop="center").out(0)
    encoded = graph.node("VAEEncode", pixels=scaled, vae=vae).out(0)
    return encoded, payload.init["denoise"]


def emit_tail(graph, samples, vae, unique_id, filename_prefix):
    """Decode and save, reported against the node the user is looking at.

    The display-id stamp is the same mechanism `render.emit_tail` uses and
    exists for the same reason: the save node lives in an expanded graph on
    nobody's canvas, and the stamp files its `executed` message under the
    PreStage node so the stage card can show what it just made.
    """
    image = graph.node("VAEDecode", samples=samples, vae=vae).out(0)
    save = graph.node(SAVE_NODE, images=image, filename_prefix=filename_prefix)
    save.set_override_display_id(unique_id)
    return save

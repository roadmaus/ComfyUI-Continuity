"""The weights, picked in the node instead of wired into it.

Both nodes used to take `clip`, `vae`, `audio_vae`, `model_fl2va` and
`model_ref2va` as sockets, which meant the node built to need no wiring needed
five loaders in front of it. The files are named in the blob now and the loaders
are emitted *inside* the subgraph, next to everything else those nodes already
build for themselves.

That is not only tidier. Both MODEL sockets had to be connected even though
`render.emit` uses exactly one of them per generation, so every queue loaded a
checkpoint it was never going to sample with. Emitting the loaders here means
only the routed one is built at all — `emit_links` is handed the set of
checkpoints the compiled payloads actually reached for, and builds a loader for
each of those and nothing else.

**The preview override is somebody else's node and is treated as such.** Core
picks a previewer off `latent_format.taesd_decoder_name` (`latent_preview.py`),
and `MiniMaxH3Video` does not declare one — which is why an H3 render previews as
latent2rgb mush. KJNodes' `ModelPreviewOverrideKJ` fixes that by wrapping the
model and decoding through a tiny VAE from `models/vae_approx`, which is where
madebyollin's `taeh3` goes. So this wires that node up exactly the way `accel.py`
wires up the two accelerator packs: read the installed class's own defaults,
override the handful we mean, never reimplement.

Unlike an accelerator, though, a missing preview is not worth an error. The
generation is identical either way, and core's own previews already carry our
node id, so `graph_preview` quietly returns the model untouched and the node body
fills up with latent2rgb instead of taeh3.

**ComfyUI-MultiGPU gets the same treatment, and costs even less.** It registers a
subclass of each core loader that takes the identical inputs plus an optional
`device`, so putting the text encoder on the second card is a class-name swap and
one extra argument — see `loader_for`. Without it installed, or with nothing
pinned, the core loaders are emitted unchanged, so a graph nobody asked to split
never quietly depends on a pack being present. Pinning a device *does* raise when
the pack is missing, because unlike a preview that is a request the render cannot
honour.

**ComfyUI-GGUF is a third loader path, chosen by the file rather than by a
setting.** city96's pack registers `unet_gguf` / `clip_gguf` folder keys over
the same model directories filtered to `.gguf`, and loader nodes taking the same
filename input and returning the same MODEL/CLIP links, dequantizing per layer
at compute time. So a quantized checkpoint is not a mode anyone switches on:
`available` merges the pack's folders into the same pickers, and `loader_for`
swaps the class whenever the picked filename ends in `.gguf`. Picking one
without the pack raises and names it, exactly as a pinned device does — both are
requests the render cannot honour. `weight_dtype` is a core-loader input and is
not emitted for GGUF files, whose precision was decided at quantization time.
"""

from dataclasses import dataclass, field
from typing import Optional

from . import accel

PREVIEW_NODE = "ModelPreviewOverrideKJ"
PREVIEW_SOURCE = "https://github.com/kijai/ComfyUI-KJNodes"

MULTIGPU_SOURCE = "https://github.com/pollockjj/ComfyUI-MultiGPU"

# ComfyUI-MultiGPU registers a subclass of each core loader carrying one extra
# optional `device`, and changes nothing else about it. That is the whole reason
# this is four lines rather than a second loader path: the emitted node keeps the
# same inputs under the same names, so switching a loader onto another card is
# swapping the class name and adding one argument.
MULTIGPU = {
    "UNETLoader": "UNETLoaderMultiGPU",
    "CLIPLoader": "CLIPLoaderMultiGPU",
    "VAELoader": "VAELoaderMultiGPU",
    "UnetLoaderGGUF": "UnetLoaderGGUFMultiGPU",
    "CLIPLoaderGGUF": "CLIPLoaderGGUFMultiGPU",
}

GGUF_SOURCE = "https://github.com/city96/ComfyUI-GGUF"

# ComfyUI-GGUF's loader for each core loader it can stand in for. No VAE entry
# because the pack has no VAE loader — and none is needed: nobody quantizes a
# VAE to GGUF blocks.
GGUF_LOADERS = {
    "UNETLoader": "UnetLoaderGGUF",
    "CLIPLoader": "CLIPLoaderGGUF",
}

# The pack's folder keys, per core key of ours they extend: same directories,
# filtered to `.gguf`, which core's own listing leaves out.
GGUF_FOLDERS = {
    "diffusion_models": "unet_gguf",
    "text_encoders": "clip_gguf",
}

# Which fields a device can be chosen for: the five that become a loader.
# `preview` is not one — it is a filename handed to KJNodes' node, which pins its
# own decoder to wherever the sampler is running.
DEVICE_FIELDS = ["fl2va", "ref2va", "clip", "vae", "audio_vae"]

# "the pack's own default", which is what passing no `device` at all means.
DEFAULT_DEVICE = ""

# What `route` may hold. "auto" follows the mode, which is what the node has
# always done; the other two are a standing instruction to run everything on one
# checkpoint whatever the mode works out to.
#
# Worth having because the two are one architecture trained twice, and Ref2VA
# turns out to be perfectly capable of the keyframe and text-only payloads FL2VA
# was trained for. The per-request `checkpoint` pin could already say that for one
# generation, but it is not sticky — attaching a reference makes the pin illegal,
# `normalizeCheckpoint` drops it, and removing the reference leaves you back on
# auto. A route survives all of that and applies to every segment of a timeline
# at once.
ROUTES = ["auto", "fl2va", "ref2va"]
DEFAULT_ROUTE = "auto"

# Where each file is picked from. These are ComfyUI's own folder keys, and the
# listing route hands the same map to the frontend so the two cannot disagree
# about which directory a field browses.
FOLDERS = {
    "fl2va": "diffusion_models",
    "ref2va": "diffusion_models",
    "clip": "text_encoders",
    "vae": "vae",
    "audio_vae": "vae",
    "preview": "vae_approx",
    # The face pass's detector: a SAM3 checkpoint, which is a fused file — model
    # and its own text encoder together — and so is picked from `checkpoints`
    # and loaded by `facepass` itself rather than by a loader emitted here. It
    # is in this map because it is a file the user picks in the same control,
    # not because it becomes a link.
    "sam3": "checkpoints",
}

# UNETLoader's own list, read rather than invented so a retune of core's dtype
# options does not leave this carrying a stale copy.
DEFAULT_DTYPE = "default"

# What CLIPLoader calls the H3 text encoder. Not "minimax_h3": the value is
# uppercased into `comfy.sd.CLIPType.MINIMAX`, and a name that does not resolve
# falls back to STABLE_DIFFUSION and tokenizes the prompt with the wrong
# vocabulary rather than failing.
CLIP_TYPE = "minimax"

# How many frames of each step's latent the preview decodes. taeh3 is causal —
# its MemBlocks chain state forward — so KJNodes' evenly-spaced sampling
# degenerates to "decode the first N frames": a small count here previews only
# the opening of the clip on a loop, never the rest. Asking for at least as many
# frames as the latent has flips `decode_video` onto its full-clip path, and the
# preview becomes the whole video. 1024 is the node's input maximum and is above
# any latent length this node can produce.
PREVIEW_FRAMES = 1024
# Playback at the render's own rate, so the preview loop is the video at speed
# rather than a slow-motion pass (`canvas.FPS`, kept literal because this is a
# node input, not a computation).
PREVIEW_FPS = 24

# What each field is called when this has to complain about one being unset.
LABEL = {
    "fl2va": "the FL2VA checkpoint",
    "ref2va": "the Ref2VA checkpoint",
    "clip": "the text encoder",
    "vae": "the video VAE",
    "audio_vae": "the audio VAE",
    "preview": "the preview decoder",
    "sam3": "the face detector",
}


@dataclass(frozen=True)
class Weights:
    """The files the node was pointed at. Every one of them may be unset.

    Unset is the normal state of a node that has just been dropped on the canvas,
    and it is also the state a workflow saved before this existed loads in — the
    sockets it used to carry are gone and nothing can recover the filenames from
    the links ComfyUI dropped. So this validates at emit time and says which
    field is empty, rather than assuming a blob is complete.
    """

    fl2va: Optional[str] = None
    ref2va: Optional[str] = None
    clip: Optional[str] = None
    vae: Optional[str] = None
    audio_vae: Optional[str] = None
    preview: Optional[str] = None
    # The face pass's SAM3 detector. Unlike the five above it never becomes a
    # loader in the graph: `facepass` loads it, uses it and gives its VRAM back
    # inside one node. Only a render with the face pass switched on needs it.
    sam3: Optional[str] = None
    dtype: str = DEFAULT_DTYPE
    # Which checkpoint everything runs on, whatever the mode derives. "auto"
    # leaves each generation's own `checkpoint` pin alone.
    route: str = DEFAULT_ROUTE
    # `{field: "cuda:1"}` for anything pinned to a particular card. Empty is the
    # normal state and means "wherever ComfyUI would have put it".
    devices: dict = field(default_factory=dict)

    @classmethod
    def from_blob(cls, data):
        """The `models` block of a creator_data / timeline_data blob.

        A missing block is every field unset rather than an error: the blob is
        the frontend's, hand-editing it is supported, and a node with no weights
        chosen yet is a node someone is still setting up.
        """
        block = (data or {}).get("models")
        if not isinstance(block, dict):
            block = {}
        picked = {name: _clean(block.get(name)) for name in FOLDERS}
        dtype = block.get("dtype")
        raw_devices = block.get("devices")
        devices = {}
        if isinstance(raw_devices, dict):
            for name in DEVICE_FIELDS:
                chosen = _clean(raw_devices.get(name))
                if chosen:
                    devices[name] = chosen
        route = block.get("route")
        return cls(**picked,
                   dtype=dtype if isinstance(dtype, str) and dtype else DEFAULT_DTYPE,
                   route=route if route in ROUTES else DEFAULT_ROUTE,
                   devices=devices)

    def routed(self, payload):
        """`payload` with the route stamped onto its request, or unchanged.

        Applied to the payload rather than anywhere downstream because that dict
        is serialised into the segment node's cache key: changing the route has
        to re-run the generation, exactly as editing the prompt does.
        """
        if self.route == DEFAULT_ROUTE:
            return payload
        request = dict(payload.get("request") or {})
        request["checkpoint"] = self.route
        return {**payload, "request": request}

    def get(self, name):
        return getattr(self, name)

    def device(self, name):
        """Where `name` should be loaded, or None for wherever ComfyUI would."""
        return self.devices.get(name) or None


def _clean(value):
    """A filename, or None. Blank and non-string both mean unset."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def device_options():
    """Every device ComfyUI-MultiGPU offers, or `[]` when it is not installed.

    Read off the installed wrapper's own declared options rather than by
    importing the pack's `get_device_list`, for the reason `accel.node_defaults`
    exists: this way a pack that learns about a new accelerator type is followed
    rather than second-guessed, and nothing here becomes an import of somebody
    else's module.
    """
    import nodes

    node = nodes.NODE_CLASS_MAPPINGS.get(MULTIGPU["UNETLoader"])
    if node is None:
        return []
    declared = node.INPUT_TYPES().get("optional", {}).get("device")
    if not isinstance(declared, (tuple, list)) or not declared:
        return []
    return [str(option) for option in declared[0]]


def is_gguf(filename):
    """Whether a picked file is a GGUF checkpoint. The extension *is* the
    format — the listing only ever offers `.gguf` names out of the pack's own
    folder keys, so there is nothing subtler to detect."""
    return bool(filename) and filename.lower().endswith(".gguf")


def loader_for(node_id, device, filename=None):
    """The class to emit for a core loader, given its file and where it loads.

    Two swaps, composed in the order the packs themselves compose. A `.gguf`
    filename swaps the core loader for ComfyUI-GGUF's, which takes the same
    filename input minus `weight_dtype` (the caller drops that — quantized
    weights already chose their precision). A pinned device then swaps whichever
    class that produced for its MultiGPU subclass, same inputs plus `device`.
    With neither — the normal case — the core loader is emitted, so a graph
    nobody asked to quantize or split never depends on another pack.

    Either half missing its pack raises and names it: a GGUF file without a GGUF
    loader, like a pinned device without MultiGPU, is a request the render
    cannot honour.
    """
    import nodes

    if is_gguf(filename):
        gguf = GGUF_LOADERS.get(node_id)
        if gguf is None:
            raise ValueError(
                f"'{filename}' is a GGUF file, and nothing loads a GGUF "
                f"{node_id.replace('Loader', '') or 'file'} — not even "
                f"ComfyUI-GGUF. Pick a safetensors file instead."
            )
        if gguf not in nodes.NODE_CLASS_MAPPINGS:
            raise ValueError(
                f"'{filename}' is a GGUF checkpoint, which needs the '{gguf}' "
                f"node from ComfyUI-GGUF ({GGUF_SOURCE}). Install it and restart "
                f"ComfyUI, or pick a safetensors file in the node's 'weights' "
                f"control."
            )
        node_id = gguf
    if not device:
        return node_id, {}
    wrapper = MULTIGPU[node_id]
    if wrapper not in nodes.NODE_CLASS_MAPPINGS:
        raise ValueError(
            f"This is set to load on '{device}', which needs the '{wrapper}' node "
            f"from ComfyUI-MultiGPU ({MULTIGPU_SOURCE}). Install it and restart "
            f"ComfyUI, or set the device back to default in the node's 'weights' "
            f"control."
        )
    return wrapper, {"device": device}


def available():
    """`{field: [filenames]}` for every pickable field, plus what is installed.

    Walks the model directories, so callers run it off the event loop.
    """
    import folder_paths
    import nodes

    def listing(folder):
        try:
            return folder_paths.get_filename_list(folder)
        except Exception:  # noqa: BLE001 — an unconfigured folder is an empty one
            return []

    listings = {}
    for folder in set(FOLDERS.values()):
        # Core's listing filters on its own extensions, which leave `.gguf` out;
        # ComfyUI-GGUF registers keys over the same directories filtered to
        # exactly those. Merged into one list because the pick is one question —
        # which file — and `loader_for` reads the format off the answer. With
        # the pack absent its keys do not exist, the merge adds nothing, and no
        # GGUF file is offered that nothing could load.
        names = {*listing(folder), *listing(GGUF_FOLDERS.get(folder, ""))}
        listings[folder] = sorted(names)

    return {
        "files": {name: listings[folder] for name, folder in FOLDERS.items()},
        "folders": dict(FOLDERS),
        # The raw per-folder listings. The PreStage's weights control browses
        # folders rather than the video fields above, and it should not have to
        # reach through a field name that happens to share a folder.
        "by_folder": listings,
        "dtypes": ["default", "fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e5m2"],
        # Whether the taeh3 preview can be used at all. The node still renders
        # without it; the UI says so rather than offering a control that does
        # nothing.
        "preview_override": PREVIEW_NODE in nodes.NODE_CLASS_MAPPINGS,
        "preview_source": PREVIEW_SOURCE,
        # Empty unless ComfyUI-MultiGPU is installed, which is what the UI keys
        # off: no pack, no device control, rather than a control that offers one
        # choice and does nothing.
        "devices": device_options(),
        "device_fields": list(DEVICE_FIELDS),
        "multigpu_source": MULTIGPU_SOURCE,
    }


def check(weights, checkpoints, where, audio=True, face=False):
    """Refuse now if a file this render needs was never picked.

    `checkpoints` is the set the compiled payloads actually route to, so a
    text-only render never asks for the reference weights. `where[checkpoint]`
    names the first generation that reached for one, the same way
    `render.compile_all` labels a segment.

    `audio=False` is the PreStage's still branch, which decodes picture only —
    asking it for an audio VAE would be demanding a file the render will never
    open.
    """
    needed = ["clip", "vae", *(["audio_vae"] if audio else []),
              # Only when a pass in this render actually asks for the face pass:
              # a detector nothing runs is a file nobody has to own.
              *(["sam3"] if face else []),
              *sorted(checkpoints)]
    for name in needed:
        if weights.get(name):
            continue
        blame = ""
        if name in checkpoints:
            blame = f"{where[name]} routes to it — "
        raise ValueError(
            f"{blame}{LABEL[name].capitalize()} has not been picked. "
            f"Open the node's 'weights' control and choose a file from "
            f"models/{FOLDERS[name]}."
        )


def emit_links(graph, weights, checkpoints, audio=True):
    """Build the loaders inside `graph` and return them as a `render.Links`.

    One `UNETLoader` per checkpoint this render reaches for and no more, which is
    the whole reason the set is passed in rather than both being built
    unconditionally.

    Each loader is emitted on the device its field was pinned to, which on a
    two-card machine is the difference between the text encoder sharing VRAM with
    the DiT and not. Nothing pinned is the core loader unchanged.

    `audio=False` leaves the audio VAE unbuilt, for the same reason `check`
    takes the flag: a still decodes no sound, and a loader in the graph is a
    file loaded whether or not anything reads it.
    """
    from .render import Links

    def loader(field, node_id, filename, **inputs):
        wrapper, extra = loader_for(node_id, weights.device(field), filename)
        # `weight_dtype` is the core loader's input; a GGUF file's precision was
        # decided when it was quantized, and its loader takes no such widget.
        if not is_gguf(filename) and node_id == "UNETLoader":
            inputs["weight_dtype"] = weights.dtype
        return graph.node(wrapper, **inputs, **extra).out(0)

    models = {}
    for name in sorted(checkpoints):
        models[name] = loader(name, "UNETLoader", weights.get(name),
                              unet_name=weights.get(name))

    return Links(
        clip=loader("clip", "CLIPLoader", weights.clip,
                    clip_name=weights.clip, type=CLIP_TYPE),
        vae=loader("vae", "VAELoader", weights.vae, vae_name=weights.vae),
        audio_vae=loader("audio_vae", "VAELoader", weights.audio_vae,
                         vae_name=weights.audio_vae) if audio else None,
        model_fl2va=models.get("fl2va"),
        model_ref2va=models.get("ref2va"),
    )


def preview_available(weights):
    """Whether a taeh3 preview can be built: a file picked and the pack present."""
    import nodes

    return bool(weights.preview) and PREVIEW_NODE in nodes.NODE_CLASS_MAPPINGS


def graph_preview(graph, model, weights):
    """Patch the preview override onto a MODEL link. Returns the new link.

    Returns `model` untouched, adding nothing to the graph, when the pack is not
    installed or no decoder was picked. Deliberately not an error, unlike
    `accel.plan`: an accelerator that cannot run changes what you asked for, and
    a preview that cannot run changes only what you watch while it happens.
    """
    if not preview_available(weights):
        return model

    import nodes

    node = nodes.NODE_CLASS_MAPPINGS[PREVIEW_NODE]
    # Every required input has to be supplied explicitly into a built graph, and
    # this node has six. Read back off the installed class for the same reason
    # `accel.py` does it: hardcoding them here means they go stale silently the
    # first time the pack retunes one.
    kwargs = accel.node_defaults(node)
    kwargs.update({
        "tiny_vae": weights.preview,
        "preview_frames": PREVIEW_FRAMES,
        "preview_fps": PREVIEW_FPS,
        # The sampler node inside our subgraph is not on anyone's canvas, so its
        # own preview overlay has nowhere to land. Ours is the only one.
        "suppress_default_preview": True,
    })
    return graph.node(PREVIEW_NODE, model=model, **kwargs).out(0)

"""Sampling one generation across several cards, through Raylight's Ray actors.

H3 at 768p is a long shot on one GPU and an ordinary one on two. Raylight is
how the second card is reached: it starts a Ray worker per GPU, loads the
transformer into each of them, and samples the sequence split across them with
xDiT's Unified Sequence Parallelism. What comes back out is an ordinary LATENT,
which is the whole reason this fits at all — the reel, the decode, the seams and
the save node never learn that anything was distributed.

Karmabu's community fork is the one this targets
(<https://github.com/Karmabu/raylight>), because it is the one that carries
MiniMax H3: the Ulysses-aware sparse attention, the H3 block cache, the sigma
shift as an actor patch, and the K3U bridge that lets KJNodes' preview override
draw taeh3 frames while the workers sample. Upstream Raylight has no H3 path.

**The model stops being ours.** Every other backend in this pack hands the
segment node a MODEL and gets one back; a Ray render has no model on this side
of the wire at all. The transformer is loaded *by* `RayUNETLoader`, *inside* the
workers, from a filename — so the segment node's two MODEL outputs go unwired,
and everything this pack does to a model between the loader and the sampler has
to be re-said as something done to a set of actors instead, or not said.

That is the whole shape of what follows, and it is why this module is mostly
refusals. Four things move across cleanly:

- The **checkpoint**, as a filename on `RayUNETLoader` (or `RayGGUFLoader`,
  which the fork registers when city96's pack is beside it).
- The **sigma shift**, which the fork ships as `RayMiniMaxH3SigmaShift` — core's
  own node, run on the actors.
- The **sampler**, as the guider / sigmas / sampler trio and
  `XFuserSamplerCustomAdvanced`. The custom-sampler form rather than
  `XFuserKSamplerAdvanced` because it is the only one that takes a K3U context,
  and the preview is worth the three extra nodes: a distributed render is the
  one you least want to watch as an empty box.
- The **preview**, through K3U Export -> KJNodes' override -> K3U Import. The
  adapter is an allowlist of exactly one wrapper and it refuses a model carrying
  patches it did not register, which is a second reason the accelerators below
  are refused rather than half-applied.

**And what does not move is refused by name, before anything is queued.** Every
one of these is a feature this pack has and Raylight cannot carry, and the
alternative to refusing is a render that silently comes out different from the
one the switch was thrown on:

- The **LoRA stack**. `RayLoraLoader` hands the files to the workers, which
  merge them through core's `calculate_weight` — the path `h3lora` exists to
  replace on the quantized checkpoints most people run H3 on. That one is a
  *documented* degradation rather than a refusal: the switch says so, because a
  multi-GPU render with stock LoRA loading is still the render most people asked
  for. Everything below is refused outright.
- The **turbo lead-in**, which needs the same weights resident twice with
  different adapters on them. Two `RayUNETLoader`s off one initializer is two
  full loads into the same workers, and they would fight over which model the
  actors hold.
- **Blended audio seams.** The soundtrack's tail is anchored on this segment's
  own timeline by a diffusion-model wrapper (`families/h3/payload.py`), and a
  wrapper on this side of the wire never reaches the workers' forward.
- The **refine, face, hires and re-detail passes**, all of which sample
  in-process against a real MODEL object.
- The **accelerators**, except the attention backend, which Raylight owns on its
  initializer. Everything else in `accel.py` is a patch on a MODEL.
- **Device pinning.** ComfyUI-MultiGPU and Raylight are two answers to the same
  question and they both want the cards.
- **Both checkpoints in one render.** The actors hold one transformer. A piece
  that routes some shots to FL2VA and some to Ref2VA would reload between them;
  the route pill says which one to use for all of them, and Ref2VA takes
  everything FL2VA does.

Read the refusals as the feature. A backend that quietly dropped the audio seam
or the lead-in would be a backend nobody could trust a piece to.
"""

from dataclasses import dataclass

# The blob's `backend` values. "default" is this pack sampling on the card
# ComfyUI picked, which is what every render before this did and what every
# saved workflow means by having no `backend` at all.
DEFAULT = "default"
RAYLIGHT = "raylight"
BACKENDS = [DEFAULT, RAYLIGHT]

# How many workers, when the blob says nothing. Two is the setup this exists
# for — the fork's own development pair is 2x3090, and the issue that asked for
# it (#15) is a pair of 5090s.
DEFAULT_GPUS = 2
MAX_GPUS = 8

SOURCE = "https://github.com/Karmabu/raylight"

INIT_NODE = "RayInitializerAdvanced"
UNET_NODE = "RayUNETLoader"
GGUF_NODE = "RayGGUFLoader"
LORA_NODE = "RayLoraLoader"
SHIFT_NODE = "RayMiniMaxH3SigmaShift"
SCHEDULER_NODE = "RayBasicScheduler"
GUIDER_NODE = "RayCFGGuider"
SAMPLER_NODE = "XFuserSamplerCustomAdvanced"
K3U_EXPORT_NODE = "KarmabuExport"
K3U_IMPORT_NODE = "KarmabuImport"

# The node whose presence means the fork is installed rather than upstream
# Raylight. Upstream registers the initializer and the samplers; only the
# community fork carries H3, and its sigma shift is the cheapest thing to ask
# for — `render.py` emits it on any piece that has left the checkpoints' own
# schedule, so an install without it would fail later and less clearly.
FORK_NODE = SHIFT_NODE


def enabled(weights):
    """Whether this render samples through Ray. Defended, because `weights` is
    a family's own object and only the video families carry a backend at all."""
    return getattr(weights, "backend", DEFAULT) == RAYLIGHT


def available():
    """Whether the fork is installed — what the UI keys the switch off.

    Both halves are asked for: upstream Raylight answers the first and cannot
    sample H3, and offering a switch that produces a graph ComfyUI refuses to
    build is worse than not offering it.
    """
    import nodes

    return all(node_id in nodes.NODE_CLASS_MAPPINGS
               for node_id in (INIT_NODE, SAMPLER_NODE, FORK_NODE))


def _require(node_id):
    """The installed class for `node_id`, or the sentence that says what to do.

    The same terms as `accel._require` and `models.loader_for`: a request the
    render cannot honour is refused by name, with somewhere to get the thing.
    """
    import nodes

    node = nodes.NODE_CLASS_MAPPINGS.get(node_id)
    if node is None:
        raise ValueError(
            f"Multi-GPU sampling needs the '{node_id}' node from the Raylight "
            f"community fork ({SOURCE}). Install it and restart ComfyUI, or set "
            f"the backend back to single-GPU in the node's 'weights' control."
        )
    return node


def _defaults(node, skip=()):
    """`{input: default}` for the required inputs we do not set ourselves.

    `accel.node_defaults` written against a different skip list, and for the
    same reason it exists there: Raylight's initializer declares nineteen
    inputs, a built graph has to pass every required one, and a copy of its
    tuning here would go stale the first time the fork retunes a knob.
    """
    from . import accel

    return {name: value for name, value in accel.node_defaults(node, skip=()).items()
            if name not in skip}


# ---- what a Ray render cannot carry ----------------------------------------


def preflight(acceleration):
    """Refuse a Ray render this machine or these settings cannot make.

    Called before a payload is compiled, which is where the two cheap questions
    belong: is the fork installed, and is the accelerator row asking for
    anything the workers cannot carry. Both are answers that do not depend on
    what is being rendered, and both are better heard before the queue than
    after the first segment has encoded.
    """
    for node_id in (INIT_NODE, SAMPLER_NODE, FORK_NODE):
        _require(node_id)
    refuse_accel(acceleration)


def refuse_weights(weights, routes):
    """Refuse a weights block Ray cannot load. Called before any node is built.

    Both of these are about the actors holding exactly one model on exactly the
    cards Ray was given.
    """
    if getattr(weights, "devices", None):
        pinned = ", ".join(sorted(weights.devices))
        raise ValueError(
            f"Multi-GPU sampling through Raylight and ComfyUI-MultiGPU are two "
            f"answers to the same question, and this piece is asking both: "
            f"{pinned} is pinned to a device. Raylight's workers take the cards "
            f"themselves. Clear the device pins in the node's 'weights' control, "
            f"or set the backend back to single-GPU."
        )
    if len(routes) > 1:
        named = " and ".join(sorted(name.upper() for name in routes))
        raise ValueError(
            f"This render routes to both {named}, and Raylight's workers hold "
            f"one transformer — sampling it would reload the weights across "
            f"every card between shots. Open the node's 'weights' control and "
            f"set the route to one checkpoint (Ref2VA takes everything FL2VA "
            f"does), or set the backend back to single-GPU."
        )


def refuse_guide():
    """Refuse a ControlNet guide, which the workers' forward does not read.

    The odd one out among the refusals: a guide reaches H3 through the
    *conditioning*, not the model, so it survives the trip to the workers
    intact — and is then dropped on the floor. The fork's `usp_dit_forward`
    replaces core's `MiniMaxH3Model._forward` wholesale, and core's is where
    `control` is picked off the conditioning and advanced every tenth layer.
    Nothing in the parallel forward mentions it.

    So the failure mode is the worst kind there is: no error, full speed, and a
    render that ignored the drawing it was aimed by. Refusing is the only honest
    answer until the fork carries the control branch.
    """
    raise ValueError(
        "A ControlNet guide reaches H3 through the conditioning, and Raylight's "
        "parallel forward replaces the one place core reads it — so a guided "
        "shot would sample across the cards at full speed and ignore the drawing "
        "entirely. Switch the guide pill off, or set the backend back to "
        "single-GPU."
    )


def refuse_accel(acceleration):
    """Refuse the accelerators that are patches on a MODEL.

    The attention backend is the exception and is not refused here: Raylight
    picks its own kernel on the initializer, and `attention_option` below maps
    ours onto what the installed fork offers.

    Kept as one sentence per switch rather than a list, because what the user
    has to do differs — a cache is switched off, an attention backend is
    switched to something Raylight has.
    """
    if acceleration.block_cache != "off":
        raise ValueError(
            f"The '{acceleration.block_cache}' step cache patches the model on "
            f"this side of the wire, and a Ray render's model is in the "
            f"workers. Switch the cache off under Settings -> Rendering, or use "
            f"Raylight's own 'MiniMax H3 Block Cache' node in a hand-built "
            f"graph. (It is not wired up here because its thresholds are its "
            f"own and this pack's three presets are not those numbers.)"
        )
    if acceleration.spectrum:
        raise ValueError(
            "Spectrum patches the model on this side of the wire, and a Ray "
            "render's model is in the workers. Switch it off under Settings -> "
            "Rendering, or set the backend back to single-GPU."
        )
    if acceleration.chunk_ffn:
        raise ValueError(
            "The chunked feed-forward is a KJNodes patch on the model, and a "
            "Ray render's model is in the workers. Switch it off under Settings "
            "-> Rendering, or set the backend back to single-GPU."
        )
    if acceleration.fp16_accumulation:
        raise ValueError(
            "fp16 accumulation hangs a callback on the model while it samples, "
            "and a Ray render samples in the workers. Switch it off under "
            "Settings -> Rendering — on a bf16 or quantized H3 checkpoint it "
            "changes nothing anyway."
        )
    if acceleration.attention == "kitchen":
        raise ValueError(
            "The kitchen attention kernel is core's own model patch and does "
            "not reach Raylight's workers. Set the attention to 'default' — "
            "Raylight picks its kernel on the initializer — or to 'sage', which "
            "it can run itself."
        )


def refuse_run(compiled, splits, label=None):
    """Refuse one compiled generation Ray cannot make.

    `label` names the segment where there is more than one, the same way
    `models.check` blames a route.
    """
    where = f"{label}: " if label else ""
    if splits:
        raise ValueError(
            f"{where}the turbo lead-in samples the opening steps on the same "
            f"checkpoint with the distillation held off it, which means the "
            f"weights loaded twice — and Raylight's workers hold one model. Set "
            f"the turbo lead-in to 0 steps under Settings -> Rendering, which "
            f"sends the whole schedule to one sampler, or set the backend back "
            f"to single-GPU."
        )
    if compiled.continues_audio or compiled.ends_on_audio:
        raise ValueError(
            f"{where}this seam carries the soundtrack across the cut, and the "
            f"tail is anchored on the segment's own timeline by a wrapper "
            f"around the forward pass — which runs on this side of the wire and "
            f"never reaches Raylight's workers. Sampled through Ray the sound "
            f"would be read as an imitation reference instead of a "
            f"continuation. Switch the sound seam off for this shot, or set the "
            f"backend back to single-GPU."
        )
    for pass_name, attribute, setting in (
            ("refine", "refine", "the two-pass upscale"),
            ("face", "face", "the face pass"),
            ("re-detail", "redetail", "the re-detail pass")):
        if getattr(compiled, attribute, None):
            raise ValueError(
                f"{where}{setting} samples in-process against a real model, "
                f"which a Ray render does not have on this side of the wire. "
                f"Switch the {pass_name} pass off for this shot, or set the "
                f"backend back to single-GPU."
            )


def refuse_seam(compiled, anchors_anywhere, label=None):
    """Refuse a picture seam on a core too old to place its anchors.

    The wrapper that repairs a keyframe's coordinate is the same one the audio
    tail needs and is just as unreachable from here; on a core with the general
    anchor there is nothing to repair and a picture seam sails through, which is
    every core since 2026-08-14. See `families/h3/payload.py`.
    """
    if anchors_anywhere:
        return
    if compiled.continues or compiled.ends_on:
        where = f"{label}: " if label else ""
        raise ValueError(
            f"{where}this seam pins the previous shot's last frames alongside "
            f"the references, which this ComfyUI places by a wrapper around the "
            f"forward pass — and that wrapper does not reach Raylight's "
            f"workers. Update ComfyUI to 2026-08-14 or later (e01fb4c5, \"Add "
            f"MiniMaxH3AddGuide\"), which anchors them itself, or set the "
            f"backend back to single-GPU."
        )


def attention_option(node, attention):
    """What to put on the initializer's `XFuser_attention` for our setting.

    Read off the installed class's own list rather than named here: the options
    are `yunchang.kernels.AttnType`'s members, the fork gains and loses them
    with the kernels it can build against, and a name it does not offer would be
    a graph ComfyUI refuses to build.

    "default" is the node's own pick, whatever it is. "sage" is the first option
    that says so — the enum spells it several ways across versions
    (`SAGE_FP16`, `SAGE_FP8`) and which one a build offers is its business.
    """
    declared = node.INPUT_TYPES()["required"]["XFuser_attention"]
    options = [str(option) for option in declared[0]]
    if attention == "sage":
        match = next((option for option in options if "SAGE" in option.upper()), None)
        if match is None:
            raise ValueError(
                f"This Raylight cannot run sage attention — '{INIT_NODE}' "
                f"offers {options}. Its kernels come from the yunchang package; "
                f"install a build with sage in it, or set the attention back to "
                f"'default' under Settings -> Rendering."
            )
        return match
    return None


# ---- the actors ------------------------------------------------------------


@dataclass(frozen=True)
class Spread:
    """How many cards, and how the sequence is split over them.

    One number in the blob and the rest derived, because the derivation is the
    only one that makes sense for a single H3 generation: every worker takes a
    slice of the same sequence (`ulysses_degree = gpus`), nothing is ring-split,
    and neither CFG nor data parallelism has anything to divide — H3 samples at
    cfg 1.0 with the negative skipped, and one generation is one latent.

    A user who wants another arrangement has Raylight's own nodes and a hand-
    built graph; what this pack offers is the arrangement that makes one shot
    finish sooner.
    """

    gpus: int = DEFAULT_GPUS

    @property
    def ulysses(self):
        return self.gpus


class Actors:
    """The workers this render samples in, built once and handed out.

    One per render, made by the family's `emit_loaders` and carried on the links
    object beside the loaders it stands in for — which is what makes "built
    once" true across a strip: every segment asks this for its actors and the
    second ask returns the first ask's link.

    It has to be asked *late*, from the sampler hook, because the LoRA stack is
    the payload's and the loaders are built before any payload is compiled. And
    it refuses a second, different stack for the same reason `refuse_weights`
    refuses two checkpoints: the workers hold one model with one set of adapters
    merged into it, and re-loading it between shots is not a thing a strip
    should do quietly.
    """

    def __init__(self, graph, weights, spread):
        self._graph = graph
        self._weights = weights
        self._spread = spread
        self._link = None
        self._key = None

    def of(self, checkpoint, loras, acceleration):
        """The RAY_ACTORS link holding `checkpoint` with `loras` merged in.

        `loras` is `[(filename, strength), ...]` in the order they are applied —
        the family's own reading of the payload's stack, because which adapters
        claim a checkpoint is a thing only the family knows. Filenames rather
        than loaded weights: `RayLoraLoader` opens the file in the workers, and
        nothing on this side of the wire ever holds it.
        """
        key = (checkpoint, tuple((name, round(float(strength), 6))
                                 for name, strength in loras))
        if self._link is not None:
            if key != self._key:
                raise ValueError(
                    "Every shot in a Ray render shares one set of weights: the "
                    "workers load the checkpoint and merge the LoRAs in once, "
                    "and this strip asks for a different combination partway "
                    "through. Give the shots the same LoRAs and the same "
                    "checkpoint, render them in separate queues, or set the "
                    "backend back to single-GPU."
                )
            return self._link
        self._key = key
        self._link = self._build(checkpoint, loras, acceleration)
        return self._link

    def _build(self, checkpoint, loras, acceleration):
        init = _require(INIT_NODE)
        kwargs = _defaults(init, skip=("GPU", "ulysses_degree"))
        kwargs["GPU"] = int(self._spread.gpus)
        kwargs["ulysses_degree"] = int(self._spread.ulysses)
        # The initializer's own pick stands unless we have something to say,
        # which is `attention_option`'s whole contract — see there for why the
        # name is read off the class rather than written here.
        chosen = attention_option(init, acceleration.attention)
        if chosen is not None:
            kwargs["XFuser_attention"] = chosen
        actors_init = self._graph.node(INIT_NODE, **kwargs).out(0)

        # The stack, first file first, each hanging off the one before —
        # Raylight's own chaining, in the order the files were listed, which is
        # the order the single-GPU stack fuses them in too.
        lora = None
        for name, strength in loras:
            _require(LORA_NODE)
            inputs = {"lora_name": name, "strength_model": float(strength)}
            if lora is not None:
                inputs["prev_ray_lora"] = lora
            lora = self._graph.node(LORA_NODE, **inputs).out(0)

        filename = self._weights.get(checkpoint)
        return self._loader(filename, actors_init, lora).out(0)

    def _loader(self, filename, actors_init, lora):
        """`RayUNETLoader`, or the fork's GGUF loader for a quantized file.

        The same swap `models.loader_for` makes on the single-GPU side and for
        the same reason: the format is the file's, not a mode anyone switches
        on. The fork registers its GGUF loader only when city96's pack is
        installed beside it, so a `.gguf` pick without one is refused by name.
        """
        from . import models as core

        inputs = {"ray_actors_init": actors_init}
        if lora is not None:
            inputs["lora"] = lora
        if core.is_gguf(filename):
            # `dequant_dtype` and `patch_dtype` are the pack's own two knobs and
            # its defaults are the answer to both; a quantized file's precision
            # was decided when it was quantized, which is the same reason
            # `weight_dtype` is left off the core GGUF loader.
            import nodes

            if GGUF_NODE not in nodes.NODE_CLASS_MAPPINGS:
                raise ValueError(
                    f"'{filename}' is a GGUF checkpoint, and Raylight registers "
                    f"its '{GGUF_NODE}' only when city96's ComfyUI-GGUF is "
                    f"installed beside it ({core.GGUF_SOURCE}). Install that and "
                    f"restart ComfyUI, or pick a safetensors checkpoint."
                )
            node = nodes.NODE_CLASS_MAPPINGS[GGUF_NODE]
            return self._graph.node(
                GGUF_NODE, unet_name=filename, **_defaults(node), **inputs)
        _require(UNET_NODE)
        return self._graph.node(
            UNET_NODE, unet_name=filename,
            weight_dtype=self._weights.dtype, **inputs)

"""Optional sampling accelerators, wired in rather than reimplemented.

Five accelerators make H3 substantially faster and none of them is ours:

- **FirstBlockCache** (`ComfyUI-MiniMaxH3-FirstBlockCache`) skips the rest of the
  DiT when the first block's residual barely moved between steps.
- **EasyCache** (core's `nodes_easycache.py`) reuses whole cached steps when the
  model's output is barely moving — the no-install option on the same axis.
- **TeaCache** (`ComfyUI-MiniMaxH3-TeaCache`) skips transformer forwards on
  timestep-similarity, through core's own `set_model_unet_function_wrapper`.
- **Spectrum** (`ComfyUI-Spectrum-MiniMax-H3`) forecasts features across steps
  instead of evaluating every one of them.
- **Sage attention** (`ComfyUI-KJNodes`) swaps H3's own attention forward for a
  quantized one — int8 queries and keys, fp8 or fp16 values.
- **Comfy Kitchen attention** (core's `ModelAttentionBackend`) is the same idea
  with nothing to install: core's own int8 attention kernel, set as the model's
  optimized attention. It is the other end of one switch with sage, not a
  second one — see `attention` below.
- **Chunked feed-forward** (`ComfyUI-KJNodes`) splits H3's SwiGLU over the
  packed sequence. Alone among these it does not trade anything: activations
  are quantized per token, so the output matches the unchunked model and only
  peak VRAM moves.
- **fp16 accumulation** (`ComfyUI-KJNodes`) lets CUDA accumulate matmuls in
  fp16 while this model runs. Not a patch on the model — a callback that sets
  one torch flag before the run and clears it after — and the only one here
  that needs a recent enough torch rather than a pack setting.

The first three are one axis — each skips or reuses steps of the same forward,
so running two at once would cache a cache — and share the `cache` widget.
Spectrum is a different idea and its own switch; its README rules out exactly
one pairing (EasyCache), which is refused by name.

Attention is a third idea again, and the only one that does not touch *which*
steps run: it changes what one attention call costs, so it composes with every
cache and with Spectrum. It gets its own switch for that reason, and it goes on
first — innermost of the patches — so everything else wraps a model whose
attention is already quantized. Kijai's node reaches the attention by object
patch rather than by replacing DiT blocks, which is also why FirstBlockCache
does not read it as a conflict: that check looks at `patches_replace["dit"]` and
sage is not there.

**Sage and Kitchen are one switch and not two.** Both of them answer "what does
one attention call cost", and a model has one attention: switching both on would
mean whichever ran last silently won. So `attention` names the backend — the
checkpoint's own, sage, or core's kitchen kernel — and picking one is what turns
the other off. Kitchen needs no install and no NVIDIA-only package, which is why
it is worth offering next to sage rather than instead of it: core hides the
option itself on a build that cannot run it, and this reads that list rather
than guessing at it.

**Chunked feed-forward is a fourth axis and its own switch.** It touches the
MLP, not the attention and not the schedule, so it composes with every one of
the above. It is also the only accelerator here that is not a trade: chunking a
per-token-quantized SwiGLU is arithmetic rearrangement, and what moves is peak
VRAM rather than fidelity. It reaches the model by object patch on each block's
`mlp.forward`, so, like sage, FirstBlockCache does not see it as a DiT block
replacement.

All of them are MODEL patchers: model in, patched model out, everything else
unchanged. That is the whole reason this module can be twenty lines of wiring —
there is no sampling logic here and there must never be any. Copying their maths
in would mean owning their bugs and freezing their tuning at whatever it was the
day it was copied, so this only ever *calls* them, and says so plainly when they
are not installed.

**Why the parameters are read rather than written.** Every required input of a
node has to be supplied explicitly when it is built into a graph, and both packs
have a dozen. Hardcoding that many defaults here means they go stale silently the
first time either pack retunes one — the node would keep running, just no longer
at the settings its author recommends. So `node_defaults` reads them back off the
installed class's own `INPUT_TYPES`, and this module only names the handful it
actually overrides. A pack that gains a knob gets its own default for it.

**Order is `attention -> chunked ffn -> torch settings -> block cache ->
spectrum -> sampler`**,
which is the packs' own advice: FirstBlockCache refuses to sit downstream of
another DiT block replacement, and Spectrum documents itself as the last patch
before the guider. They compose — the caches are wrappers and block patches
respectively, the attention and the MLP are object patches under both, and none
of them trips another's conflict check.

Nothing here is Timeline-specific. `graph_apply` is for the nodes that build a
subgraph and `direct_apply` for the ones holding a real MODEL, so the Creator
node can take the same settings later without this module changing.
"""

from dataclasses import dataclass, replace

BLOCK_CACHE_NODE = "ApplyMiniMaxH3FirstBlockCache"
EASYCACHE_NODE = "EasyCache"
TEACACHE_NODE = "MiniMaxH3TeaCache"
SPECTRUM_NODE = "SpectrumApplyMiniMaxH3"
SAGE_NODE = "MiniMaxH3MemoryEfficientSageAttentionPatch"
KITCHEN_NODE = "ModelAttentionBackend"
CHUNK_FFN_NODE = "MiniMaxChunkFeedForward"
TORCH_SETTINGS_NODE = "ModelPatchTorchSettings"

# What core's node calls the kernel. Matched against the options the installed
# class actually offers rather than passed blind: `ModelAttentionBackend` leaves
# this out of its list entirely on a build where the kernel is unavailable, and
# a name it does not offer would otherwise fall back to pytorch attention with a
# line in the log nobody reads.
KITCHEN_OPTION = "comfy kitchen attention"

# Where to get each pack, named in the error rather than in a README nobody is
# reading at the moment the node fails. EasyCache ships with ComfyUI itself, so
# missing means the install predates it.
SOURCES = {
    BLOCK_CACHE_NODE: "https://github.com/duckyshell/ComfyUI-MiniMaxH3-FirstBlockCache",
    TEACACHE_NODE: "https://github.com/Icyoung/ComfyUI-MiniMaxH3-TeaCache",
    EASYCACHE_NODE: "ComfyUI core (comfy_extras/nodes_easycache.py) — update ComfyUI",
    SPECTRUM_NODE: "https://github.com/xmarre/ComfyUI-Spectrum-MiniMax-H3",
    SAGE_NODE: "https://github.com/kijai/ComfyUI-KJNodes (and the sageattention package)",
    KITCHEN_NODE: "ComfyUI core (comfy_extras/nodes_model_advanced.py) — update ComfyUI",
    CHUNK_FFN_NODE: "https://github.com/kijai/ComfyUI-KJNodes",
    TORCH_SETTINGS_NODE: "https://github.com/kijai/ComfyUI-KJNodes",
}

# What the `attention` widget offers. One backend at a time, because a model has
# one attention and two patches would mean the last one applied quietly won.
# "default" is the checkpoint's own and emits no node at all.
ATTENTION_MODES = ["default", "sage", "kitchen"]

# KJNodes' own defaults are 2 chunks over 4096 tokens; 4 is what the H3 workflows
# that use it settle on and what issue #18 asked for. Named here rather than read
# off the class because these two are a *preset* — the pack's defaults are its
# answer to "chunk at all", and this is ours to "chunk for H3 video".
CHUNK_FFN_CHUNKS = 4
CHUNK_FFN_THRESHOLD = 4096

# What the node's `block_cache` widget offers — one step-caching accelerator at
# a time, whichever implementation. The FirstBlockCache presets are matched
# against the *installed* pack's mode list by prefix, because its labels carry
# the threshold in them ("H3 Fast — 0.10 / max 2") and would break this the
# first time one is retuned. "off" is not a mode: it means no cache node is
# ever built. "easy" is core's EasyCache at its own defaults; "tea" is the
# TeaCache pack at its card's defaults, told the run's real step count.
BLOCK_CACHE_MODES = ["off", "safe", "fast", "aggressive", "easy", "tea"]
_FBC_MODES = ("safe", "fast", "aggressive")


@dataclass(frozen=True)
class Settings:
    """What the user asked for. Both accelerators off is the default everywhere."""

    block_cache: str = "off"
    spectrum: bool = False
    spectrum_blend: float = 0.5
    attention: str = "default"
    chunk_ffn: bool = False
    fp16_accumulation: bool = False

    @property
    def any(self):
        return (self.block_cache != "off" or self.spectrum
                or self.attention != "default" or self.chunk_ffn
                or self.fp16_accumulation)


def uncached(settings):
    """`settings` with the step caches off and everything else as it stands.

    For the turbo lead-in's opening steps, which are the ones a step cache would
    be reusing — and reusing the opening of a schedule is precisely what the
    lead-in exists to stop. The attention backend and the chunked feed-forward
    survive, because they skip nothing: they make one call cheaper or smaller and
    every step still runs.
    """
    return replace(settings, block_cache="off", spectrum=False)


def _node_class(node_id):
    """The installed class for `node_id`, or None. Looked up per call.

    Not cached and not imported at module load: a pack installed while ComfyUI is
    running should not need this one to be reloaded too, and importing either of
    them here would turn an optional accelerator into a hard dependency.
    """
    import nodes

    return nodes.NODE_CLASS_MAPPINGS.get(node_id)


def _require(node_id):
    node = _node_class(node_id)
    if node is None:
        raise ValueError(
            f"This needs the '{node_id}' node, which is not installed. "
            f"Get it from {SOURCES[node_id]}, restart ComfyUI, or switch the "
            f"accelerator off."
        )
    return node


def node_defaults(node, skip=("model",)):
    """`{input: default}` for every required input the class declares but `skip`.

    Required inputs have to be passed explicitly into a built graph, and reading
    them back off the class is what keeps this module from carrying a stale copy
    of somebody else's tuning. An input with no declared default is left out
    rather than guessed at — ComfyUI will say which one is missing, which is a
    better error than a number this module invented.

    Public because `models.py` wires up KJNodes' preview override on exactly the
    same terms, and two copies of this would be two copies of the argument for it.
    """
    spec = node.INPUT_TYPES().get("required", {})
    out = {}
    for name, declared in spec.items():
        if name in skip:
            continue
        if isinstance(declared, (tuple, list)) and len(declared) > 1 and isinstance(declared[1], dict):
            if "default" in declared[1]:
                out[name] = declared[1]["default"]
    return out


def _block_cache_kwargs(node, mode):
    """The pack's own arguments for one of our three preset names."""
    kwargs = node_defaults(node)
    options = node.INPUT_TYPES()["required"]["mode"][0]
    wanted = f"h3 {mode}"
    match = next((o for o in options if str(o).lower().startswith(wanted)), None)
    if match is None:
        raise ValueError(
            f"'{node.__name__}' has no '{mode}' preset — it offers {list(options)}. "
            f"The pack has renamed its modes; use its own node directly."
        )
    kwargs["mode"] = match
    return kwargs


def _kitchen_kwargs(node):
    """Core's arguments for the kitchen kernel, or a message saying why not.

    The option list is built per call inside `INPUT_TYPES` off
    `COMFY_KITCHEN_INT8_ATTENTION_IS_AVAILABLE`, so asking the installed class
    is the only way to know whether this machine can run it. A build without the
    kernel offers "pytorch attention" alone, and core's own node would answer a
    name it does not know by warning to the log and sampling on pytorch
    attention — which is the render you did not ask for, finished. So this
    raises instead, on the same terms as a missing pack.
    """
    kwargs = node_defaults(node)
    options = node.INPUT_TYPES()["required"]["attention"][0]
    if KITCHEN_OPTION not in options:
        raise ValueError(
            f"This ComfyUI cannot run '{KITCHEN_OPTION}' — '{KITCHEN_NODE}' "
            f"offers {list(options)}. The kernel ships with comfy-kitchen and "
            f"needs a card and a Triton it supports; switch the attention back "
            f"to 'default' or to 'sage'.")
    kwargs["attention"] = KITCHEN_OPTION
    return kwargs


def _chunk_ffn_kwargs(node):
    """KJNodes' arguments for the chunked feed-forward, at our preset.

    Everything but the two numbers comes off the class, so a knob the pack gains
    arrives with the pack's own default for it.
    """
    kwargs = node_defaults(node)
    kwargs["chunks"] = CHUNK_FFN_CHUNKS
    kwargs["seq_threshold"] = CHUNK_FFN_THRESHOLD
    return kwargs


def _spectrum_kwargs(node, blend):
    kwargs = node_defaults(node)
    kwargs["enabled"] = True
    kwargs["blend_weight"] = float(blend)
    return kwargs


def plan(settings, sampler_steps=None):
    """`[(node_id, kwargs), ...]` in the order they must be applied.

    Shared by both entry points so the graph path and the direct path cannot
    drift apart on ordering or arguments — the difference between them is only
    how a node gets run, never which nodes or with what. `sampler_steps` is the
    run's real step count, which TeaCache needs to place its skip window.
    """
    if settings.block_cache == "easy" and settings.spectrum:
        raise ValueError(
            "Spectrum cannot be combined with EasyCache — its own conflict "
            "check refuses the pair. Pick one, or switch the cache to another "
            "implementation.")
    if settings.attention not in ATTENTION_MODES:
        raise ValueError(
            f"unknown attention backend {settings.attention!r} — "
            f"this build offers {ATTENTION_MODES}")
    steps = []
    # First, so everything downstream wraps a model whose attention is already
    # quantized. Kijai's node has no inputs but `model` — there is no tuning
    # there to go stale, and `node_defaults` correctly returns nothing for it.
    if settings.attention == "sage":
        steps.append((SAGE_NODE, node_defaults(_require(SAGE_NODE))))
    elif settings.attention == "kitchen":
        steps.append((KITCHEN_NODE, _kitchen_kwargs(_require(KITCHEN_NODE))))
    # Then the MLP, which is the other object patch and the other thing every
    # step pays for. Its order against the attention does not matter — they
    # patch different keys on different modules and neither wraps the other —
    # so it goes here, under everything that decides which steps run at all.
    if settings.chunk_ffn:
        steps.append((CHUNK_FFN_NODE, _chunk_ffn_kwargs(_require(CHUNK_FFN_NODE))))
    # Not a patch on the model at all, in the end: it hangs a callback that
    # flips one torch flag while this model runs and puts it back afterwards. It
    # sits with the others because it belongs to the same question — what one
    # step costs — and because a run either has it or does not.
    if settings.fp16_accumulation:
        kwargs = node_defaults(_require(TORCH_SETTINGS_NODE))
        kwargs["enable_fp16_accumulation"] = True
        steps.append((TORCH_SETTINGS_NODE, kwargs))
    if settings.block_cache in _FBC_MODES:
        node = _require(BLOCK_CACHE_NODE)
        steps.append((BLOCK_CACHE_NODE, _block_cache_kwargs(node, settings.block_cache)))
    elif settings.block_cache == "easy":
        steps.append((EASYCACHE_NODE, node_defaults(_require(EASYCACHE_NODE))))
    elif settings.block_cache == "tea":
        kwargs = node_defaults(_require(TEACACHE_NODE))
        if sampler_steps is not None:
            kwargs["total_steps"] = int(sampler_steps)
        steps.append((TEACACHE_NODE, kwargs))
    elif settings.block_cache != "off":
        raise ValueError(
            f"unknown cache mode {settings.block_cache!r} — "
            f"this build offers {BLOCK_CACHE_MODES}")
    if settings.spectrum:
        node = _require(SPECTRUM_NODE)
        steps.append((SPECTRUM_NODE, _spectrum_kwargs(node, settings.spectrum_blend)))
    return steps


def graph_apply(graph, model, settings, sampler_steps=None):
    """Patch a MODEL *link* inside a `GraphBuilder` subgraph. Returns the new link.

    For the nodes that return an expanded graph rather than tensors. With both
    accelerators off this returns `model` untouched and adds nothing to the
    graph — an unused node is still a node ComfyUI has to cache and schedule.
    """
    for node_id, kwargs in plan(settings, sampler_steps):
        model = graph.node(node_id, model=model, **kwargs).out(0)
    return model


def direct_apply(model, settings, sampler_steps=None):
    """Patch a real MODEL object. Returns the patched model.

    The Creator node's half of the same contract: it holds a loaded model rather
    than a link, so it calls the packs the way ComfyUI would. Unused today and
    kept beside `graph_apply` deliberately — the two are one decision, and
    splitting them across a later commit is how they stop agreeing.
    """
    for node_id, kwargs in plan(settings, sampler_steps):
        node = _require(node_id)
        model = getattr(node(), node.FUNCTION)(model=model, **kwargs)[0]
    return model

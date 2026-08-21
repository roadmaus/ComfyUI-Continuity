"""Contract tests for `accel.py`, the accelerator wiring.

Runs standalone — `python tests/test_accel.py` — with no torch and no ComfyUI.
Both packs import torch, so the classes here are stand-ins carrying their *real*
`INPUT_TYPES`, copied from the installed sources. That is the point of the test:
`accel.py` reads defaults and preset labels back off whatever is installed, so
what has to be pinned is that the reading works against the shape those packs
actually declare, and that it fails loudly rather than quietly when it does not.
"""

import importlib.util
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# `accel` imports `nodes` (ComfyUI's registry) inside its functions, so a stub
# module under that name is the whole of the harness.
NODES = types.ModuleType("nodes")
NODES.NODE_CLASS_MAPPINGS = {}
sys.modules["nodes"] = NODES

package = types.ModuleType("mmc")
package.__path__ = [ROOT]
sys.modules["mmc"] = package
spec = importlib.util.spec_from_file_location("mmc.accel", os.path.join(ROOT, "accel.py"))
accel = importlib.util.module_from_spec(spec)
sys.modules["mmc.accel"] = accel
spec.loader.exec_module(accel)

from harness import FAILURES, check, passed


def expect_error(label, fn, fragment):
    try:
        fn()
    except Exception as exc:
        if fragment not in str(exc):
            FAILURES.append(f"{label}: error {str(exc)!r} does not mention {fragment!r}")
    else:
        FAILURES.append(f"{label}: expected an error mentioning {fragment!r}, got none")


# ---- stand-ins for the two installed packs ---------------------------------

class FakeBlockCache:
    """`ApplyMiniMaxH3FirstBlockCache.INPUT_TYPES`, verbatim."""

    FUNCTION = "apply"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "mode": ([
                    "H3 Safe — 0.08 / max 2",
                    "H3 Fast — 0.10 / max 2",
                    "H3 Aggressive — 0.12 / max 2",
                    "Custom — manual values",
                ], {"default": "H3 Fast — 0.10 / max 2"}),
                "threshold": ("FLOAT", {"default": 0.10, "min": 0.0, "max": 1.0, "step": 0.005}),
                "start_percent": ("FLOAT", {"default": 0.10, "min": 0.0, "max": 1.0, "step": 0.01}),
                "end_percent": ("FLOAT", {"default": 0.95, "min": 0.0, "max": 1.0, "step": 0.01}),
                "max_consecutive_hits": ("INT", {"default": 2, "min": 1, "max": 20, "step": 1}),
                "temporal_guard": ("BOOLEAN", {"default": False}),
            },
        }

    def apply(self, model, **kwargs):
        return (("block_cache", model, tuple(sorted(kwargs.items()))),)


class FakeSpectrum:
    """`SpectrumApplyMiniMaxH3.INPUT_TYPES`, required half verbatim."""

    FUNCTION = "apply"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "enabled": ("BOOLEAN", {"default": True}),
                "blend_weight": ("FLOAT", {"default": 0.50, "min": 0.0, "max": 1.0, "step": 0.01}),
                "degree": ("INT", {"default": 1, "min": 1, "max": 16, "step": 1}),
                "ridge_lambda": ("FLOAT", {"default": 0.10, "min": 0.0, "max": 10.0, "step": 0.01}),
                "window_size": ("FLOAT", {"default": 2.0, "min": 1.0, "max": 16.0, "step": 0.05}),
                "flex_window": ("FLOAT", {"default": 0.75, "min": 0.0, "max": 8.0, "step": 0.05}),
                "warmup_steps": ("INT", {"default": 1, "min": 0, "max": 64, "step": 1}),
                "tail_actual_steps": ("INT", {"default": 1, "min": 0, "max": 64, "step": 1}),
                "max_history": ("INT", {"default": 8, "min": 2, "max": 64, "step": 1}),
                "debug": ("BOOLEAN", {"default": False}),
            },
            # Optional inputs are the pack's own business and must not be sent.
            "optional": {
                "history_storage": (["system_ram", "vram"], {"default": "system_ram"}),
                "audio_blend_weight": ("FLOAT", {"default": 0.0}),
            },
        }

    def apply(self, model, **kwargs):
        return (("spectrum", model, tuple(sorted(kwargs.items()))),)


class FakeEasyCache:
    """Core's `EasyCache` required inputs, verbatim from nodes_easycache.py."""

    FUNCTION = "apply"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "reuse_threshold": ("FLOAT", {"default": 0.2, "min": 0.0, "max": 3.0, "step": 0.01}),
                "start_percent": ("FLOAT", {"default": 0.15, "min": 0.0, "max": 1.0, "step": 0.01}),
                "end_percent": ("FLOAT", {"default": 0.95, "min": 0.0, "max": 1.0, "step": 0.01}),
                "verbose": ("BOOLEAN", {"default": False}),
            },
        }

    def apply(self, model, **kwargs):
        return (("easycache", model, tuple(sorted(kwargs.items()))),)


class FakeTeaCache:
    """`MiniMaxH3TeaCache.INPUT_TYPES`, verbatim from the pack."""

    FUNCTION = "apply"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "rel_l1_thresh": ("FLOAT", {"default": 0.15, "min": 0.0, "max": 1.0, "step": 0.01}),
                "start_step": ("INT", {"default": 2, "min": 0, "max": 1000}),
                "end_step": ("INT", {"default": -2, "min": -1000, "max": 1000}),
                "total_steps": ("INT", {"default": 20, "min": 1, "max": 1000}),
            },
        }

    def apply(self, model, **kwargs):
        return (("teacache", model, tuple(sorted(kwargs.items()))),)


class FakeSage:
    """`MiniMaxH3MemoryEfficientSageAttentionPatch`, as the registry holds it.

    Kijai's node is a V3 `io.ComfyNode`, the first one `accel.py` reaches for, so
    what this stands in for is the *shim's* shape rather than the source's: one
    `model` input carrying an empty options dict, and a `FUNCTION` naming the
    generated `EXECUTE_NORMALIZED` rather than the `execute` its author wrote.
    Both were read off a live ComfyUI 0.33 rather than guessed at.

    It declares nothing else, which is the point of it — there is no tuning here
    that could go stale, so `node_defaults` must come back empty and the node
    must be built with `model` alone.
    """

    FUNCTION = "EXECUTE_NORMALIZED"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"model": ["MODEL", {}]}}

    def EXECUTE_NORMALIZED(self, model, **kwargs):
        return (("sage", model, tuple(sorted(kwargs.items()))),)


class FakeKitchen:
    """Core's `ModelAttentionBackend`, on a build that has the int8 kernel.

    Its option list is *computed* — core appends "comfy kitchen attention" only
    where `COMFY_KITCHEN_INT8_ATTENTION_IS_AVAILABLE` — so the list is the whole
    reason `accel.py` reads it back rather than sending the name blind.
    """

    FUNCTION = "patch"
    BACKENDS = ["pytorch attention", "comfy kitchen attention"]

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"model": ("MODEL",), "attention": (cls.BACKENDS,)}}

    def patch(self, model, **kwargs):
        return (("kitchen", model, tuple(sorted(kwargs.items()))),)


class KernelLessKitchen(FakeKitchen):
    """The same node on a build that cannot run the kernel."""

    BACKENDS = ["pytorch attention"]


class FakeChunkFFN:
    """`MiniMaxChunkFeedForward.define_schema`, as the registry holds it."""

    FUNCTION = "EXECUTE_NORMALIZED"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ["MODEL", {}],
                "chunks": ["INT", {"default": 2, "min": 1, "max": 64, "step": 1}],
                "seq_threshold": ["INT", {"default": 4096, "min": 256, "max": 262144, "step": 256}],
            },
        }

    def EXECUTE_NORMALIZED(self, model, **kwargs):
        return (("chunk_ffn", model, tuple(sorted(kwargs.items()))),)


class FakeTorchSettings:
    """`ModelPatchTorchSettings.INPUT_TYPES`, verbatim from KJNodes."""

    FUNCTION = "patch"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "model": ("MODEL",),
            "enable_fp16_accumulation": ("BOOLEAN", {"default": False}),
        }}

    def patch(self, model, **kwargs):
        return (("torch_settings", model, tuple(sorted(kwargs.items()))),)


def install(*, block_cache=True, spectrum=True, easycache=True, teacache=True, sage=True,
            kitchen=True, chunk_ffn=True, torch_settings=True):
    NODES.NODE_CLASS_MAPPINGS = {}
    if block_cache:
        NODES.NODE_CLASS_MAPPINGS[accel.BLOCK_CACHE_NODE] = FakeBlockCache
    if spectrum:
        NODES.NODE_CLASS_MAPPINGS[accel.SPECTRUM_NODE] = FakeSpectrum
    if easycache:
        NODES.NODE_CLASS_MAPPINGS[accel.EASYCACHE_NODE] = FakeEasyCache
    if teacache:
        NODES.NODE_CLASS_MAPPINGS[accel.TEACACHE_NODE] = FakeTeaCache
    if sage:
        NODES.NODE_CLASS_MAPPINGS[accel.SAGE_NODE] = FakeSage
    if kitchen:
        NODES.NODE_CLASS_MAPPINGS[accel.KITCHEN_NODE] = FakeKitchen
    if chunk_ffn:
        NODES.NODE_CLASS_MAPPINGS[accel.CHUNK_FFN_NODE] = FakeChunkFFN
    if torch_settings:
        NODES.NODE_CLASS_MAPPINGS[accel.TORCH_SETTINGS_NODE] = FakeTorchSettings


class FakeGraph:
    """Enough of `GraphBuilder` to record what was built, in order."""

    def __init__(self):
        self.built = []

    def node(self, node_id, **kwargs):
        self.built.append((node_id, kwargs))
        outer = self

        class Node:
            def out(self, index):
                return f"{node_id}:{index}"

        return Node()


# ---- off is genuinely off ---------------------------------------------------

install()
off = accel.Settings()
check("default settings are off", off.any, False)
check("nothing planned when off", accel.plan(off), [])

graph = FakeGraph()
check("model link passes through untouched", accel.graph_apply(graph, "MODEL_LINK", off), "MODEL_LINK")
check("no nodes built when off", graph.built, [])

# An accelerator that is off must not be built even when its pack is missing —
# nothing should depend on a pack it was not asked to use.
install(block_cache=False, spectrum=False, sage=False, kitchen=False, chunk_ffn=False,
        torch_settings=False)
check("off needs no pack installed", accel.plan(accel.Settings()), [])

# ---- presets resolve against the pack's own labels --------------------------

install()
for mode, want in [("safe", "H3 Safe — 0.08 / max 2"),
                   ("fast", "H3 Fast — 0.10 / max 2"),
                   ("aggressive", "H3 Aggressive — 0.12 / max 2")]:
    steps = accel.plan(accel.Settings(block_cache=mode))
    check(f"{mode} resolves to the pack's label", steps[0][1]["mode"], want)

# Every required input the pack declares is supplied, and `model` never is —
# a missing required input is a hard executor error at queue time.
kwargs = accel.plan(accel.Settings(block_cache="fast"))[0][1]
check("block cache sends every required input",
      sorted(kwargs),
      ["end_percent", "max_consecutive_hits", "mode", "start_percent", "temporal_guard", "threshold"])
check("block cache keeps the pack's threshold", kwargs["threshold"], 0.10)
check("block cache keeps the pack's window", (kwargs["start_percent"], kwargs["end_percent"]), (0.10, 0.95))

# `off` is ours, not the pack's, and must never be sent as a mode.
check("off is not a pack mode", "off" in [m for m in accel.BLOCK_CACHE_MODES[1:]], False)

# ---- spectrum ---------------------------------------------------------------

kwargs = accel.plan(accel.Settings(spectrum=True))[0][1]
check("spectrum is enabled when asked for", kwargs["enabled"], True)
check("spectrum takes our blend", kwargs["blend_weight"], 0.5)
check("spectrum blend is overridable", accel.plan(accel.Settings(spectrum=True, spectrum_blend=0.8))[0][1]["blend_weight"], 0.8)
check("spectrum keeps the pack's tuning", (kwargs["degree"], kwargs["warmup_steps"], kwargs["max_history"]), (1, 1, 8))
check("spectrum sends no optional inputs", "history_storage" in kwargs, False)

# ---- the other two cache implementations ------------------------------------

install()
easy = accel.plan(accel.Settings(block_cache="easy"))
check("easy plans core's EasyCache", easy[0][0], accel.EASYCACHE_NODE)
check("easy keeps core's own tuning",
      (easy[0][1]["reuse_threshold"], easy[0][1]["start_percent"]), (0.2, 0.15))

tea = accel.plan(accel.Settings(block_cache="tea"), sampler_steps=8)
check("tea plans the TeaCache node", tea[0][0], accel.TEACACHE_NODE)
check("tea keeps the pack's threshold and window",
      (tea[0][1]["rel_l1_thresh"], tea[0][1]["start_step"], tea[0][1]["end_step"]),
      (0.15, 2, -2))
check("tea is told the run's real step count", tea[0][1]["total_steps"], 8)
check("tea falls back to the pack's own step default",
      accel.plan(accel.Settings(block_cache="tea"))[0][1]["total_steps"], 20)

# One cache at a time: the widget is one axis, so a plan never holds two.
for mode in ("safe", "fast", "aggressive", "easy", "tea"):
    planned = [n for n, _ in accel.plan(accel.Settings(block_cache=mode))]
    check(f"'{mode}' plans exactly one cache node", len(planned), 1)

expect_error("easy + spectrum is refused by name",
             lambda: accel.plan(accel.Settings(block_cache="easy", spectrum=True)),
             "EasyCache")
expect_error("a mode this build does not know is refused",
             lambda: accel.plan(accel.Settings(block_cache="fancy")),
             "unknown cache mode")

install(teacache=False)
expect_error("missing teacache pack names the repo",
             lambda: accel.plan(accel.Settings(block_cache="tea")),
             "Icyoung/ComfyUI-MiniMaxH3-TeaCache")
install(easycache=False)
expect_error("a core without EasyCache says to update",
             lambda: accel.plan(accel.Settings(block_cache="easy")),
             "update ComfyUI")

# ---- the attention backend --------------------------------------------------

install()
check("attention is the checkpoint's own by default", accel.Settings().attention, "default")
check("default attention plans nothing", accel.plan(accel.Settings()), [])
check("sage alone counts as an accelerator", accel.Settings(attention="sage").any, True)
check("kitchen alone counts as an accelerator", accel.Settings(attention="kitchen").any, True)

sage = accel.plan(accel.Settings(attention="sage"))
check("sage plans kijai's node", [node_id for node_id, _ in sage], [accel.SAGE_NODE])
check("sage is built with model alone", sage[0][1], {})

kitchen = accel.plan(accel.Settings(attention="kitchen"))
check("kitchen plans core's node", [node_id for node_id, _ in kitchen], [accel.KITCHEN_NODE])
check("kitchen asks for the kernel by core's own name",
      kitchen[0][1], {"attention": accel.KITCHEN_OPTION})

# One backend at a time: a model has one attention, so a plan never holds two.
for backend in ("sage", "kitchen"):
    planned = [n for n, _ in accel.plan(accel.Settings(attention=backend))]
    check(f"'{backend}' plans exactly one attention node", len(planned), 1)

# Neither backend is a step-caching accelerator, so unlike the three that are
# they rule nothing out — every cache and Spectrum both have to survive beside
# them. The one pair that is refused stays refused for its own reason.
for backend, node_id in (("sage", accel.SAGE_NODE), ("kitchen", accel.KITCHEN_NODE)):
    for mode in ("safe", "fast", "aggressive", "easy", "tea"):
        planned = [n for n, _ in accel.plan(accel.Settings(block_cache=mode, attention=backend))]
        check(f"{backend} composes with '{mode}'", (planned[0], len(planned)), (node_id, 2))
expect_error("sage does not rescue easy + spectrum",
             lambda: accel.plan(accel.Settings(block_cache="easy", spectrum=True, attention="sage")),
             "EasyCache")
expect_error("a backend this build does not know is refused",
             lambda: accel.plan(accel.Settings(attention="flash")),
             "unknown attention backend")

# A ComfyUI whose build cannot run the kernel does not offer it, and is told so
# rather than quietly sampling on pytorch attention — which is what core's own
# node does with a name it does not know.
install()
NODES.NODE_CLASS_MAPPINGS[accel.KITCHEN_NODE] = KernelLessKitchen
expect_error("a build without the kernel is refused by name",
             lambda: accel.plan(accel.Settings(attention="kitchen")),
             accel.KITCHEN_OPTION)

install(sage=False)
expect_error("missing sage pack names the node",
             lambda: accel.plan(accel.Settings(attention="sage")), accel.SAGE_NODE)
expect_error("missing sage pack names KJNodes and the library",
             lambda: accel.plan(accel.Settings(attention="sage")), "kijai/ComfyUI-KJNodes")
install(kitchen=False)
expect_error("a core without the attention node says to update",
             lambda: accel.plan(accel.Settings(attention="kitchen")), "update ComfyUI")

# ---- the chunked feed-forward -----------------------------------------------

install()
check("chunked ffn is off by default", accel.Settings().chunk_ffn, False)
check("chunked ffn alone counts as an accelerator", accel.Settings(chunk_ffn=True).any, True)

chunked = accel.plan(accel.Settings(chunk_ffn=True))
check("chunked ffn plans kijai's node", [node_id for node_id, _ in chunked], [accel.CHUNK_FFN_NODE])
check("chunked ffn sends every required input", sorted(chunked[0][1]), ["chunks", "seq_threshold"])
check("chunked ffn runs at our preset rather than the pack's default",
      (chunked[0][1]["chunks"], chunked[0][1]["seq_threshold"]),
      (accel.CHUNK_FFN_CHUNKS, accel.CHUNK_FFN_THRESHOLD))

# It touches the MLP rather than the schedule, so it composes with everything.
for mode in ("safe", "fast", "aggressive", "easy", "tea"):
    planned = [n for n, _ in accel.plan(accel.Settings(block_cache=mode, chunk_ffn=True))]
    check(f"chunked ffn composes with '{mode}'",
          (planned[0], len(planned)), (accel.CHUNK_FFN_NODE, 2))

install(chunk_ffn=False)
expect_error("missing chunked ffn pack names the node",
             lambda: accel.plan(accel.Settings(chunk_ffn=True)), accel.CHUNK_FFN_NODE)
expect_error("missing chunked ffn pack names KJNodes",
             lambda: accel.plan(accel.Settings(chunk_ffn=True)), "kijai/ComfyUI-KJNodes")

# ---- fp16 accumulation ------------------------------------------------------

install()
check("fp16 accumulation is off by default", accel.Settings().fp16_accumulation, False)
check("fp16 accumulation alone counts as an accelerator",
      accel.Settings(fp16_accumulation=True).any, True)

accum = accel.plan(accel.Settings(fp16_accumulation=True))
check("fp16 accumulation plans kijai's node",
      [node_id for node_id, _ in accum], [accel.TORCH_SETTINGS_NODE])
check("fp16 accumulation is asked for rather than left at the node's default",
      accum[0][1], {"enable_fp16_accumulation": True})

# Off emits nothing at all rather than the node with the flag off: this sets a
# *global* torch flag, and a run that was not asked to touch it must not.
check("off plans no torch settings node", accel.plan(accel.Settings()), [])

install(torch_settings=False)
expect_error("missing torch settings node names KJNodes",
             lambda: accel.plan(accel.Settings(fp16_accumulation=True)),
             "kijai/ComfyUI-KJNodes")

# ---- what the lead-in keeps -------------------------------------------------

# The step caches come off for the turbo lead-in's opening steps; the two that
# skip nothing stay on, because every step still runs and each one is cheaper.
install()
kept = accel.uncached(accel.Settings(block_cache="fast", spectrum=True,
                                     attention="sage", chunk_ffn=True,
                                     fp16_accumulation=True))
check("the lead-in drops the caches",
      (kept.block_cache, kept.spectrum), ("off", False))
check("the lead-in keeps everything that skips nothing",
      (kept.attention, kept.chunk_ffn, kept.fp16_accumulation), ("sage", True, True))

# ---- ordering ---------------------------------------------------------------

install()
both = accel.Settings(block_cache="fast", spectrum=True)
check("block cache is applied before spectrum",
      [node_id for node_id, _ in accel.plan(both)],
      [accel.BLOCK_CACHE_NODE, accel.SPECTRUM_NODE])

graph = FakeGraph()
out = accel.graph_apply(graph, "MODEL_LINK", both)
check("both nodes are built", [node_id for node_id, _ in graph.built],
      [accel.BLOCK_CACHE_NODE, accel.SPECTRUM_NODE])
check("block cache takes the incoming link", graph.built[0][1]["model"], "MODEL_LINK")
check("spectrum chains off the block cache", graph.built[1][1]["model"], f"{accel.BLOCK_CACHE_NODE}:0")
check("the sampler gets spectrum's output", out, f"{accel.SPECTRUM_NODE}:0")

# Sage goes on first of all three, so the caches wrap a model whose attention is
# already quantized rather than the other way round.
everything = accel.Settings(block_cache="fast", spectrum=True,
                            attention="sage", chunk_ffn=True,
                            fp16_accumulation=True)
check("the per-call patches are applied before the cache and spectrum",
      [node_id for node_id, _ in accel.plan(everything)],
      [accel.SAGE_NODE, accel.CHUNK_FFN_NODE, accel.TORCH_SETTINGS_NODE,
       accel.BLOCK_CACHE_NODE, accel.SPECTRUM_NODE])

graph = FakeGraph()
out = accel.graph_apply(graph, "MODEL_LINK", everything)
check("sage takes the incoming link", graph.built[0][1]["model"], "MODEL_LINK")
check("the chunked ffn chains off sage", graph.built[1][1]["model"], f"{accel.SAGE_NODE}:0")
check("the torch settings chain off the chunked ffn",
      graph.built[2][1]["model"], f"{accel.CHUNK_FFN_NODE}:0")
check("the cache chains off the torch settings",
      graph.built[3][1]["model"], f"{accel.TORCH_SETTINGS_NODE}:0")
check("the sampler still gets spectrum's output", out, f"{accel.SPECTRUM_NODE}:0")

# ---- a missing pack says which, and where to get it -------------------------

install(block_cache=False)
expect_error("missing block cache pack names the node",
             lambda: accel.plan(accel.Settings(block_cache="fast")),
             accel.BLOCK_CACHE_NODE)
expect_error("missing block cache pack names the repo",
             lambda: accel.plan(accel.Settings(block_cache="fast")),
             "duckyshell/ComfyUI-MiniMaxH3-FirstBlockCache")

install(spectrum=False)
expect_error("missing spectrum pack names the repo",
             lambda: accel.plan(accel.Settings(spectrum=True)),
             "xmarre/ComfyUI-Spectrum-MiniMax-H3")

# A pack that renames its presets is refused rather than silently run on a
# preset we picked for the user.
class RenamedBlockCache(FakeBlockCache):
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"model": ("MODEL",),
                             "mode": (["Balanced", "Turbo"], {"default": "Balanced"})}}


install()
NODES.NODE_CLASS_MAPPINGS[accel.BLOCK_CACHE_NODE] = RenamedBlockCache
expect_error("renamed presets are refused",
             lambda: accel.plan(accel.Settings(block_cache="fast")),
             "renamed its modes")

# ---- direct_apply runs the same plan ---------------------------------------

install()
result = accel.direct_apply("MODEL", both)
check("direct_apply chains both packs in order",
      (result[0], result[1][0]), ("spectrum", "block_cache"))
check("direct_apply is a no-op when off", accel.direct_apply("MODEL", accel.Settings()), "MODEL")

# The V3 half of the same contract: a node whose `FUNCTION` is the shim's
# generated name rather than a method its author wrote still runs, and still
# comes back through `[0]`.
check("direct_apply runs a V3 node through its shim",
      accel.direct_apply("MODEL", accel.Settings(attention="sage"))[:2], ("sage", "MODEL"))

passed("all accelerator tests passed")

"""Guarded Turbo is one cache unit, and cancelled histories release tensors.

COMFYUI_PATH points at ComfyUI. Core's Euler implementation runs numbered toy
predictions on CPU; no H3 checkpoint or GPU rendering is involved. Graph cache
checks use ComfyUI's actual CacheKeySetInputSignature, not hand-made hashes.
"""

import asyncio
import gc
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import weakref
from unittest.mock import patch

import layout
from harness import check, skip

comfy_path = Path(os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI")))
if not (comfy_path / "folder_paths.py").is_file():
    skip("set COMFYUI_PATH to a ComfyUI installation")
sys.path.insert(0, str(comfy_path))


class FakePatcher:
    def __init__(self):
        self.post_cfg = []
        self.wrappers = {}

    def clone(self):
        return FakePatcher()

    def set_model_sampler_post_cfg_function(self, function, **kwargs):
        self.post_cfg.append(function)

    def add_wrapper_with_key(self, kind, key, function):
        self.wrappers.setdefault(kind, {})[key] = function


with tempfile.TemporaryDirectory(prefix="continuity-truncate-") as temporary:
    root = Path(temporary)
    sys.argv = ["test_truncate_cache", "--cpu", "--base-directory", str(root)]
    import comfy.cli_args
    comfy.cli_args.args.cpu = True
    import folder_paths
    for kind in ("input", "output", "temp", "user"):
        directory = root / kind
        directory.mkdir()
        getattr(folder_paths, f"set_{kind}_directory")(str(directory))

    import torch
    import comfy.model_management
    import comfy.patcher_extension
    from comfy.k_diffusion.sampling import sample_euler
    import nodes
    pkg = layout.load("truncate", "creator_node", "settings", package="truncate_cache_contract")
    truncate = pkg.truncate
    schedule = torch.linspace(1, 0, 9)
    initial = {"samples": torch.zeros((1, 1, 1, 1, 1)), "batch_index": [0]}
    calls = []
    references = []

    def wrapper(model):
        return model.wrappers[comfy.patcher_extension.WrappersMP.SAMPLER_SAMPLE][truncate.TRUNCATE_NODE]

    def toy_sitting(model, sigmas, samples, fail=False):
        def predicted(x, sigma, **kwargs):
            number = int(torch.argmin((schedule - float(sigma[0])).abs())) + 1
            prediction = torch.full_like(x, float(number))
            for hook in model.post_cfg:
                hook({"denoised": prediction, "sigma": sigma,
                      "model_options": {"transformer_options": {"sample_sigmas": sigmas}}})
            references.extend(weakref.ref(term) for term, _ in truncate._current().terms)
            if fail:
                raise comfy.model_management.InterruptProcessingException()
            return prediction

        def executor(guider, sigmas, *rest):
            return sample_euler(predicted, samples.clone(), sigmas, disable=True)
        return wrapper(model)(executor, None, sigmas)

    def core_adapter(self, **kwargs):
        # Replace only the model-facing core call boundary. The new node chooses
        # all real KSamplerAdvanced arguments, and Euler itself is not mocked.
        calls.append(kwargs)
        sigmas = schedule[kwargs["start_at_step"]:kwargs["end_at_step"] + 1]
        result = dict(kwargs["latent_image"])
        result["samples"] = toy_sitting(kwargs["model"], sigmas, result["samples"])
        return (result,)

    def run(guesses=8):
        return truncate.MiniMaxH3GuardedTurboSampler.execute(
            model=truncate._patch(FakePatcher(), guesses),
            lead_model=truncate._patch(FakePatcher(), guesses),
            positive=[], negative=[], latent_image=initial, noise_seed=123,
            steps=8, lead_steps=3, cfg=1.0, sampler_name="euler", scheduler="simple")[0]

    with patch.object(nodes.KSamplerAdvanced, "sample", core_adapter):
        cold = run()
        warm = run()
        check("cold guarded Turbo averages all eight guesses", cold["samples"].item(), 4.5)
        check("a rerun has the same complete history", warm["samples"].item(), 4.5)
        check("all guesses outside the five-step tail are included", len(calls), 4)
        check("three-guess control is unchanged", run(3)["samples"].item(), 7.0)
        check("LATENT metadata survives the two core calls", cold["batch_index"], [0])
        for lead, tail in zip(calls[::2], calls[1::2]):
            check("core lead-in arguments", (lead["add_noise"], lead["start_at_step"],
                  lead["end_at_step"], lead["return_with_leftover_noise"]), ("enable", 0, 3, "enable"))
            check("core tail arguments", (tail["add_noise"], tail["start_at_step"],
                  tail["end_at_step"], tail["return_with_leftover_noise"]), ("disable", 3, 8, "disable"))
            check("both calls keep one seed and schedule",
                  [(call["noise_seed"], call["steps"], call["cfg"], call["sampler_name"], call["scheduler"])
                   for call in (lead, tail)], [(123, 8, 1.0, "euler", "simple")] * 2)
    check("grouped success leaves no active run", truncate._run.get(), None)
    check("grouped success leaves no legacy history", truncate._open, None)
    gc.collect()
    check("finished prediction tensors are released", any(ref() is not None for ref in references), False)

    # The legacy standalone wrapper also owns its failed history. ComfyUI's
    # cancellation is a BaseException, deliberately not caught as Exception.
    references.clear()
    try:
        toy_sitting(truncate._patch(FakePatcher(), 8), schedule, initial["samples"], fail=True)
    except comfy.model_management.InterruptProcessingException:
        pass
    check("cancelled wrapper clears its legacy trajectory", truncate._open, None)
    gc.collect()
    check("cancelled wrapper releases predictions", any(ref() is not None for ref in references), False)

    # Fail before the tail's wrapper is entered: only the grouped node's outer
    # finally can release the successful lead-in at this boundary.
    references.clear()
    count = [0]
    def between_halves(self, **kwargs):
        count[0] += 1
        if count[0] == 2:
            raise comfy.model_management.InterruptProcessingException()
        return core_adapter(self, **kwargs)

    with patch.object(nodes.KSamplerAdvanced, "sample", between_halves):
        try:
            run()
        except comfy.model_management.InterruptProcessingException:
            pass
    check("between-half cancellation closes the run", truncate._run.get(), None)
    gc.collect()
    check("between-half cancellation releases predictions", any(ref() is not None for ref in references), False)

    references.clear()
    with patch.object(nodes.KSamplerAdvanced, "sample", core_adapter), \
            patch.object(truncate.Trajectory, "finish", side_effect=ValueError("finish failed")):
        try:
            run()
        except ValueError as error:
            check("finish failure is not swallowed", str(error), "finish failed")
    check("finish failure closes the run", truncate._run.get(), None)
    gc.collect()
    check("finish failure releases predictions", any(ref() is not None for ref in references), False)

    nested = [False]
    def with_nested_run(self, **kwargs):
        result = core_adapter(self, **kwargs)
        if kwargs["start_at_step"] == 0 and not nested[0]:
            owner, trajectory = truncate._run.get(), truncate._current()
            nested[0] = True
            check("nested run has its own complete history", run()["samples"].item(), 4.5)
            check("nested completion restores the outer owner", truncate._run.get() is owner, True)
            check("nested completion preserves the outer history", truncate._current() is trajectory, True)
        return result

    with patch.object(nodes.KSamplerAdvanced, "sample", with_nested_run):
        check("outer run survives a nested run", run()["samples"].item(), 4.5)
    check("nested and outer runs close together", truncate._run.get(), None)

    # Existing manually split patched samplers still carry history across a
    # successful nonfinal sitting; a grouped run must not steal that history.
    legacy = truncate._patch(FakePatcher(), 8)
    opening = toy_sitting(legacy, schedule[:4], initial["samples"])
    legacy_history = truncate._open
    with patch.object(nodes.KSamplerAdvanced, "sample", core_adapter):
        check("group alongside a legacy split has its own history", run()["samples"].item(), 4.5)
    check("group does not replace legacy history", truncate._open is legacy_history, True)
    check("legacy split still consumes its opening guesses",
          toy_sitting(legacy, schedule[3:], opening).item(), 4.5)
    check("legacy successful tail closes its history", truncate._open, None)

    # Real graph/cache topology: off -> EasyCache changes only the distilled
    # model, which formerly left the opening KSamplerAdvanced as a cache hit.
    from comfy_api.latest import io
    from comfy_execution.caching import CacheKeySetInputSignature
    from comfy_execution.graph import DynamicPrompt
    from comfy_execution.graph_utils import GraphBuilder
    from comfy_extras.nodes_easycache import EasyCacheNode
    nodes.NODE_CLASS_MAPPINGS["EasyCache"] = EasyCacheNode
    segment_module = importlib.import_module("truncate_cache_contract.families.h3.segment")
    nodes.NODE_CLASS_MAPPINGS["MiniMaxH3TimelineSegment"] = segment_module.MiniMaxH3TimelineSegment
    for node in truncate.NODES:
        nodes.NODE_CLASS_MAPPINGS[node.define_schema().node_id] = node
    check("group sampler is registered with the creator", truncate.MiniMaxH3GuardedTurboSampler in
          asyncio.run(pkg.creator_node.MiniMaxCreatorExtension().get_node_list()), True)

    piece = {"version": 2, "family": "h3", "aspect": "1:1", "short_edge": 480,
             "models": {"fl2va": "fl.safetensors", "ref2va": "ref.safetensors",
                        "clip": "text.safetensors", "vae": "video.safetensors",
                        "audio_vae": "audio.safetensors"},
             "segments": [{"duration_s": 5, "prompt": "one"}],
             "turbo": {"on": True, "lora": "turbo.safetensors"},
             "loras": [{"name": "turbo.safetensors", "strength": 1.0}]}

    def build(cache="off", guard=8):
        GraphBuilder.set_default_prefix("12", 0, 0)
        pkg.creator_node.MiniMaxH3Timeline.hidden = io.HiddenHolder(
            unique_id="12", prompt=None, extra_pnginfo=None, dynprompt=None,
            auth_token_comfy_org=None, api_key_comfy_org=None)
        with patch.object(pkg.settings, "drift_guard", return_value=guard), \
                patch.object(pkg.settings, "turbo_lead_in", return_value=3):
            return pkg.creator_node.MiniMaxH3Timeline.execute(
                timeline_data=json.dumps(piece), seed=100, steps=8, cfg=1.0,
                sampler_name="euler", scheduler="simple", block_cache=cache).expand

    def matching(graph, kind):
        return [key for key, node in graph.items() if node["class_type"] == kind]

    class Unchanged:
        async def get(self, node_id):
            return None

    async def signature(graph):
        dynamic = DynamicPrompt(graph)
        keys = CacheKeySetInputSignature(dynamic, list(graph), Unchanged())
        return await keys.get_node_signature(dynamic, matching(graph, truncate.GUARDED_TURBO_NODE)[0])

    off, easy = build(), build("easy")
    check("guarded Turbo has exactly one sampler cache unit", len(matching(off, truncate.GUARDED_TURBO_NODE)), 1)
    check("no separately cached opening remains", matching(off, "KSamplerAdvanced"), [])
    check("tail acceleration invalidates the whole guarded run",
          asyncio.run(signature(off)) != asyncio.run(signature(easy)), True)
    check("identical guarded runs retain the same cache key",
          asyncio.run(signature(off)), asyncio.run(signature(build())))
    unguarded = build(guard=0)
    check("guard OFF keeps the original two core sampler nodes", len(matching(unguarded, "KSamplerAdvanced")), 2)
    check("guard OFF emits no grouped node", matching(unguarded, truncate.GUARDED_TURBO_NODE), [])

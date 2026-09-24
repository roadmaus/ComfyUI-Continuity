"""H3's secondary passes inherit the loader and their own sampler settings.

Actual compiler, graph emitters and segment dispatch, on CPU without a server
or model weights. Only the optional TeaCache schema and heavy LoRA/encoding
boundaries are substituted. COMFYUI_PATH points at an installed ComfyUI.
"""

import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import layout
from harness import check, passed, skip

COMFY = Path(os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI")))
if not (COMFY / "folder_paths.py").is_file():
    skip("set COMFYUI_PATH to a ComfyUI installation")
sys.path.insert(0, str(COMFY))

with tempfile.TemporaryDirectory(prefix="continuity-pass-settings-") as temporary:
    root = Path(temporary)
    sys.argv = ["test_h3_pass_settings", "--cpu", "--base-directory", str(root)]
    import comfy.options
    comfy.options.enable_args_parsing()
    import comfy.cli_args
    comfy.cli_args.args.cpu = True
    comfy.cli_args.args.base_directory = str(root)
    comfy.cli_args.args.database_url = "sqlite:///:memory:"
    import folder_paths
    for kind in ("input", "output", "temp", "user"):
        directory = root / kind
        directory.mkdir(exist_ok=True)
        setattr(comfy.cli_args.args, f"{kind}_directory", str(directory))
        getattr(folder_paths, f"set_{kind}_directory")(str(directory))

    from comfy_execution.graph_utils import GraphBuilder
    pkg = layout.load("h3_segment", "compile", "sampling", "accel", "settings",
                      package="h3_pass_settings")
    render = importlib.import_module("h3_pass_settings.families.h3.render")
    guidepass = importlib.import_module("h3_pass_settings.families.h3.guidepass")
    family = render.FAMILY
    payload = {"request": {"prompt": "a woman crossing a market", "duration_s": 5,
                           "aspect": "16:9", "short_edge": 480,
                           "loras": [{"name": "example.safetensors", "strength": 1.0}]}}
    compiled = pkg.compile.compile_segment(payload)
    weights = render.slots.weights_from_blob({"models": {
        "fl2va": "fl2va.safetensors", "ref2va": "ref2va.safetensors",
        "clip": "clip.safetensors", "vae": "video.safetensors",
        "audio_vae": "audio.safetensors", "sam3": "sam3.safetensors"}})

    class Links:
        clip = ["clip", 0]
        vae = ["video_vae", 0]
        audio_vae = ["audio_vae", 0]

        def get(self, name):
            return [name, 0]

    links = Links()
    sampling = pkg.sampling.Sampling(steps=20)

    def refine_payload(steps=None):
        request = {**payload["request"], "short_edge": 1152, "refine_denoise": 0.3}
        if steps is not None:
            request["refine_steps"] = steps
        return {"request": request}

    def emit_all(loader):
        graph = GraphBuilder()
        written = graph.node("SourcePlaceholder")
        acceleration = pkg.accel.Settings()
        with patch.object(pkg.settings, "lora_loader", return_value=loader), \
             patch.object(render.core, "preview_available", return_value=False):
            family.emit_segment(graph, links, payload, compiled, weights, sampling,
                                {}, render.LeadIn())
            refined = refine_payload()
            family.emit_refine(graph, links, None, refined,
                               pkg.compile.compile_segment(refined), weights, {},
                               ["latent", 0], sampling, acceleration, 123, render.LeadIn())
            face = pkg.compile.Face(512, 512, 0.45)
            cropped = family.face_payload(payload, face)
            family.emit_face(graph, links, cropped, pkg.compile.compile_segment(cropped),
                             face, written, weights, sampling, acceleration, 123)
            family.emit_motion_fix(graph, links, payload, compiled, written, ["latent", 0],
                                   0, weights, sampling, acceleration, 123)
            family.emit_seam_restore(graph, links, ["frames", 0], payload, compiled, 0.2,
                                     weights, sampling, acceleration, 123)
        return [node["inputs"] for node in graph.finalize().values()
                if node["class_type"] == render.SEGMENT_NODE]

    labels = ("main", "refine", "face", "motion fix", "seam restore")
    default = emit_all("vendored")
    core = emit_all("core")
    check("all five ordinary conditioning paths were exercised", len(core), len(labels))
    for label, before, after in zip(labels, default, core):
        check(f"{label}: default keeps the existing cache-key shape",
              "lora_loader" in before, False)
        check(f"{label}: core loader reaches the segment input", after.get("lora_loader"), "core")
        check(f"{label}: no unrelated conditioning input changes",
              {k: v for k, v in after.items() if k != "lora_loader"}, before)

    # Follow those actual emitted inputs through execute -> lora.apply. No
    # media is needed to determine the loader; stop precisely at that boundary.
    class ReachedEncoder(Exception):
        pass

    lora = pkg.h3_segment.lora
    for choice, nodes, wanted in (("vendored", default, "h3lora"), ("core", core, "core")):
        seen = []
        with patch.object(lora, "stack", return_value=[{"name": "fixture"}]), \
             patch.object(lora, "_apply_core", side_effect=lambda m, r: seen.append("core") or m), \
             patch.object(lora, "_apply_h3", side_effect=lambda m, r: seen.append("h3lora") or m), \
             patch.object(pkg.h3_segment.media, "load_all", side_effect=ReachedEncoder), \
             patch.object(pkg.settings, "lora_loader", return_value=choice):
            for inputs in nodes:
                try:
                    pkg.h3_segment.MiniMaxH3TimelineSegment.execute(
                        **{**inputs, "model_fl2va": object(), "model_ref2va": object()})
                except ReachedEncoder:
                    pass
            check(f"{choice}: every ordinary pass dispatches to the selected stack",
                  seen, [wanted] * len(labels))
            seen.clear()
            guidepass.MiniMaxH3GuideModel.execute(object(),
                                                 json.dumps(payload["request"]["loras"]), "fl2va")
            check(f"{choice}: guide finisher retains its intentional core policy", seen, ["core"])

    # Public TeaCache v0.1 schema (Icyoung, 4cbb50d). A schema fixture is enough
    # to test what our actual accelerator planner puts into the render graph.
    class TeaSchema:
        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {"model": ("MODEL",), **{
                key: (kind, {"default": value}) for key, kind, value in (
                    ("rel_l1_thresh", "FLOAT", 0.15), ("start_step", "INT", 2),
                    ("end_step", "INT", -2), ("total_steps", "INT", 20))}}}

    for override in (None, 0, 3, 20, 32):
        expected = override or sampling.steps
        for cache in ("off", "tea"):
            graph = GraphBuilder()
            refined = refine_payload(override)
            with patch.object(pkg.accel, "_require", return_value=TeaSchema), \
                 patch.object(render.core, "preview_available", return_value=False):
                family.emit_refine(graph, links, None, refined,
                                   pkg.compile.compile_segment(refined), weights, {},
                                   ["latent", 0], sampling, pkg.accel.Settings(block_cache=cache),
                                   123, render.LeadIn())
            nodes = list(graph.finalize().values())
            sampler = next(n["inputs"] for n in nodes if n["class_type"] == render.REFINE_NODE)
            tea = [n["inputs"] for n in nodes if n["class_type"] == pkg.accel.TEACACHE_NODE]
            label = f"refine_steps={override}, cache={cache}"
            check(f"{label}: sampler gets the resolved step count", sampler["steps"], expected)
            check(f"{label}: cache enabled only when selected", len(tea), int(cache == "tea"))
            if tea:
                check(f"{label}: cache and sampler agree", tea[0]["total_steps"], sampler["steps"])
            check(f"{label}: main sampling settings are not mutated", sampling.steps, 20)

passed("all H3 pass settings tests passed")

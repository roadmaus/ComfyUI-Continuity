"""The published upscaler precisions survive real file loading and forwarding.

Tiny networks use the published key layout, not downloaded trained weights.
Actual SafeTensors/PyTorch readers and ModelPatcher run on CPU. ComfyUI's
device-loader is replaced only during the tiny forward; no GPU/server starts.
"""

import gc
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

with tempfile.TemporaryDirectory(prefix="continuity-upscaler-precision-") as temporary:
    root = Path(temporary)
    sys.argv = ["test_latentup_precision", "--cpu", "--base-directory", str(root)]
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

    import torch
    from safetensors.torch import save_file
    latentup = layout.load("latentup", package="latentup_precision").latentup
    folder_paths.add_model_folder_path(latentup.FOLDER, str(root))
    torch.manual_seed(0)
    torch.set_num_threads(1)
    source = latentup.LatentResizer3D(24, 3, 2, 32, 5)

    for dtype in (torch.float16, torch.bfloat16, torch.float32):
        name = str(dtype).split(".")[-1]
        filename = name + (".pth" if dtype == torch.float32 else ".safetensors")
        state = {key: value.to(dtype) for key, value in source.state_dict().items()}
        # Cover the two checkpoint wrappers supported by load() as well.
        if dtype == torch.float32:
            torch.save({"model": state}, root / filename)
        else:
            prefix = "upscaler." if dtype == torch.bfloat16 else ""
            save_file({prefix + key: value for key, value in state.items()}, str(root / filename))
        patcher = latentup.load(filename)
        model = patcher.model
        check(f"{name}: parameter dtype survives load",
              {parameter.dtype for parameter in model.parameters()}, {dtype})
        check(f"{name}: checkpoint tensor storage is not inflated",
              sum(t.numel() * t.element_size() for t in model.state_dict().values()),
              sum(t.numel() * t.element_size() for t in state.values()))
        check(f"{name}: cached load returns the same patcher", latentup.load(filename) is patcher, True)
        check(f"{name}: evaluation mode", model.training, False)
        check(f"{name}: gradients disabled", any(p.requires_grad for p in model.parameters()), False)
        for key, value in model.state_dict().items():
            check(f"{name}: {key} retained checkpoint values", torch.equal(value, state[key]), True)

        # Short and chunked forwards both run the real network. Compare with
        # the same quantized weights computed in FP32, not a different model.
        reference = latentup._build(state).float().eval()
        reference.load_state_dict(state, strict=True)
        for count in (2, latentup.CHUNK + 1):
            video = torch.randn(1, 24, count, 2, 2)
            seen = []
            hook = model.register_forward_pre_hook(lambda _, args: seen.append(args[0].dtype))
            with patch.object(latentup.comfy.model_management, "load_models_gpu", return_value=None):
                drawn = latentup.upscale(video, 64, 64, filename)
            hook.remove()
            check(f"{name}/{count}: forward uses checkpoint dtype", seen, [dtype])
            check(f"{name}/{count}: caller dtype is preserved", drawn.dtype, video.dtype)
            check(f"{name}/{count}: requested shape", tuple(drawn.shape), (1, 24, count, 4, 4))
            check(f"{name}/{count}: finite result", bool(torch.isfinite(drawn).all()), True)
            mean = torch.tensor(latentup.MEAN).view(1, -1, 1, 1, 1)
            std = torch.tensor(latentup.STD).view(1, -1, 1, 1, 1)
            with torch.inference_mode():
                expected = reference((video - mean) / std, 2.0, 4, 4) * std + mean
            relative = (drawn - expected).abs().mean() / expected.abs().mean().clamp_min(1e-6)
            tolerance = 0.03 if dtype == torch.bfloat16 else 0.005
            check(f"{name}/{count}: stable versus FP32 computation of the same weights",
                  bool(relative < tolerance), True)

    # Mixed files predate the precision-preserving loader. Keep their FP32
    # destination rather than using just the first layer's dtype and losing a
    # later full-precision layer's values.
    mixed = {key: value.half() for key, value in source.state_dict().items()}
    mixed["conv_out.bias"] = torch.linspace(0.123456, 0.765432, 24)
    save_file(mixed, str(root / "mixed.safetensors"))
    mixed_patcher = latentup.load("mixed.safetensors")
    check("mixed half/full file retains FP32 computation",
          {p.dtype for p in mixed_patcher.model.parameters()}, {torch.float32})
    check("mixed file's full-precision layer is not rounded",
          torch.equal(mixed_patcher.model.conv_out.bias, mixed["conv_out.bias"]), True)
    # A registered integer buffer must survive dtype selection and Module.to.
    # The current published net has none; this fixture protects that contract
    # without adding a buffer to the production architecture.
    buffered = {key: value.half() for key, value in source.state_dict().items()}
    buffered["counter"] = torch.tensor(7, dtype=torch.int64)
    save_file(buffered, str(root / "buffered.safetensors"))
    build = latentup._build

    def with_buffer(state):
        net = build(state)
        net.register_buffer("counter", torch.tensor(0, dtype=torch.int64))
        return net

    with patch.object(latentup, "_build", side_effect=with_buffer):
        buffered_patcher = latentup.load("buffered.safetensors")
    check("integer buffer does not force a half checkpoint to FP32",
          {p.dtype for p in buffered_patcher.model.parameters()}, {torch.float16})
    check("integer buffer retains dtype and value",
          (buffered_patcher.model.counter.dtype, buffered_patcher.model.counter.item()),
          (torch.int64, 7))
    latentup._LOADED.clear()
    del patcher, mixed_patcher, buffered_patcher
    gc.collect()  # release real patchers before Comfy's modules are torn down

passed("all latent upscaler precision tests passed")

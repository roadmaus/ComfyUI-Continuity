"""Checkpoint precision follows core's compute policy for the load device.

Tiny networks use the published key layout, not downloaded trained weights.
Actual SafeTensors/PyTorch readers and ModelPatcher run on CPU. ComfyUI's
device-loader is replaced during the tiny forward; no GPU/server starts.
Mocked device-policy cases test selection, not real accelerator support.
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
    management = latentup.comfy.model_management
    files = {}

    for dtype in (torch.float16, torch.bfloat16, torch.float32):
        name = str(dtype).split(".")[-1]
        filename = name + (".pth" if dtype == torch.float32 else ".safetensors")
        files[dtype] = filename
        state = {key: value.to(dtype) for key, value in source.state_dict().items()}
        # Cover the two checkpoint wrappers supported by load() as well.
        if dtype == torch.float32:
            torch.save({"model": state}, root / filename)
        else:
            prefix = "upscaler." if dtype == torch.bfloat16 else ""
            save_file({prefix + key: value for key, value in state.items()}, str(root / filename))
        patcher = latentup.load(filename)
        model = patcher.model
        check(f"{name}: real core CPU policy selects FP32",
              {parameter.dtype for parameter in model.parameters()}, {torch.float32})
        check(f"{name}: storage follows the selected FP32 dtype",
              sum(t.numel() * t.element_size() for t in model.state_dict().values()),
              sum(t.numel() * 4 for t in state.values()))
        check(f"{name}: cached load returns the same patcher", latentup.load(filename) is patcher, True)
        check(f"{name}: evaluation mode", model.training, False)
        check(f"{name}: gradients disabled", any(p.requires_grad for p in model.parameters()), False)
        for key, value in model.state_dict().items():
            check(f"{name}: {key} retained checkpoint values",
                  torch.equal(value, state[key].float()), True)

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
            check(f"{name}/{count}: forward uses CPU compute dtype", seen, [torch.float32])
            check(f"{name}/{count}: caller dtype is preserved", drawn.dtype, video.dtype)
            check(f"{name}/{count}: requested shape", tuple(drawn.shape), (1, 24, count, 4, 4))
            check(f"{name}/{count}: finite result", bool(torch.isfinite(drawn).all()), True)
            mean = torch.tensor(latentup.MEAN).view(1, -1, 1, 1, 1)
            std = torch.tensor(latentup.STD).view(1, -1, 1, 1, 1)
            with torch.inference_mode():
                expected = reference((video - mean) / std, 2.0, 4, 4) * std + mean
            check(f"{name}/{count}: matches FP32 computation of the same weights",
                  torch.equal(drawn, expected), True)

    # No tensor is moved to this device. A non-default index catches a gate
    # called on the default device rather than the patcher's actual target.
    device = torch.device("cuda:7")
    for dtype, policy in ((torch.float16, "should_use_fp16"),
                          (torch.bfloat16, "should_use_bf16")):
        for allowed in (True, False):
            name = f"{dtype}/{allowed} mocked policy"
            latentup._LOADED.clear()
            # The other precision is allowed when this one is rejected: that
            # must still fall back to FP32, not change checkpoint precision.
            fp16_allowed = allowed if dtype == torch.float16 else not allowed
            bf16_allowed = allowed if dtype == torch.bfloat16 else not allowed
            with (patch.object(management, "get_torch_device", return_value=device),
                  patch.object(management, "should_use_fp16", return_value=fp16_allowed) as fp16,
                  patch.object(management, "should_use_bf16", return_value=bf16_allowed) as bf16):
                patcher = latentup.load(files[dtype])
            selected = dtype if allowed else torch.float32
            check(f"{name}: selects the permitted computation dtype",
                  {p.dtype for p in patcher.model.parameters()}, {selected})
            gate, other = (fp16, bf16) if policy == "should_use_fp16" else (bf16, fp16)
            gate.assert_called_once_with(device=device)
            other.assert_not_called()
            check(f"{name}: patcher uses the same target device", patcher.load_device, device)
            check(f"{name}: model stays on CPU until core loads it",
                  {p.device.type for p in patcher.model.parameters()}, {"cpu"})
            check(f"{name}: storage follows the selected dtype",
                  sum(t.numel() * t.element_size() for t in patcher.model.state_dict().values()),
                  sum(t.numel() for t in source.state_dict().values())
                  * (2 if allowed else 4))

    # FORCE_FP32 is core's import-time value of --force-fp32. Run the actual
    # policy functions with that flag, without querying accelerator hardware.
    # Disable the separate CPU-mode fallback so it cannot hide a flag regression.
    for dtype, policy in ((torch.float16, "should_use_fp16"),
                          (torch.bfloat16, "should_use_bf16")):
        latentup._LOADED.clear()
        with (patch.object(management, "get_torch_device", return_value=device),
              patch.object(management, "cpu_mode", return_value=False),
              patch.object(management, "FORCE_FP32", True),
              patch.object(management.args, "force_fp32", True),
              patch.object(management.args, "force_fp16", False),
              patch.object(management, policy, wraps=getattr(management, policy)) as gate,
              patch.object(torch.cuda, "get_device_properties",
                           side_effect=AssertionError("unexpected hardware query"))):
            patcher = latentup.load(files[dtype])
        gate.assert_called_once_with(device=device)
        check(f"{dtype}: core --force-fp32 policy selects FP32",
              {p.dtype for p in patcher.model.parameters()}, {torch.float32})

    # Mixed files predate the precision-preserving loader. Keep their FP32
    # destination rather than using just the first layer's dtype and losing a
    # later full-precision layer's values.
    mixed = {key: value.half() for key, value in source.state_dict().items()}
    mixed["conv_out.bias"] = torch.linspace(0.123456, 0.765432, 24)
    save_file(mixed, str(root / "mixed.safetensors"))
    latentup._LOADED.clear()
    with (patch.object(management, "get_torch_device", return_value=device),
          patch.object(management, "should_use_fp16", return_value=True) as fp16,
          patch.object(management, "should_use_bf16", return_value=True) as bf16):
        mixed_patcher = latentup.load("mixed.safetensors")
        full_patcher = latentup.load(files[torch.float32])
    fp16.assert_not_called()
    bf16.assert_not_called()
    check("explicit FP32 file stays FP32 even when half policies would accept",
          {p.dtype for p in full_patcher.model.parameters()}, {torch.float32})
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

    for allowed in (True, False):
        latentup._LOADED.clear()
        with (patch.object(latentup, "_build", side_effect=with_buffer),
              patch.object(management, "get_torch_device", return_value=device),
              patch.object(management, "should_use_fp16", return_value=allowed) as gate):
            buffered_patcher = latentup.load("buffered.safetensors")
        gate.assert_called_once_with(device=device)
        check(f"integer buffer/{allowed}: floating weights follow device policy",
              {p.dtype for p in buffered_patcher.model.parameters()},
              {torch.float16 if allowed else torch.float32})
        check(f"integer buffer/{allowed}: retains dtype and value",
              (buffered_patcher.model.counter.dtype, buffered_patcher.model.counter.item()),
              (torch.int64, 7))
    latentup._LOADED.clear()
    del patcher, mixed_patcher, full_patcher, buffered_patcher
    gc.collect()  # release real patchers before Comfy's modules are torn down

passed("all latent upscaler precision tests passed")

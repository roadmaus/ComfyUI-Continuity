# Model downloads

Nothing is bundled and nothing is fetched at runtime. You put files where
ComfyUI already looks and pick them on the node's **weights** pill. If a render
needs a file it doesn't have, it is refused before the queue starts, and the
message names the field and the folder.

A few notes that apply everywhere:

- Pick **one** weight per slot. The quantizations in a repo (`bf16`,
  `fp8_scaled`, `int8_convrot`, `nvfp4`) are alternatives, not a set. `bf16` is
  the reference, the others trade memory for quality.
- `fp8` only speeds up sampling on cards with hardware fp8 matmul (RTX
  40-series and later). On older cards it still saves memory.
- GGUF files work if [ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) is
  installed. Drop the `.gguf` in the same folder and pick it like any other
  file.
- If a long render dies with a `HostBuffer.read_file_slice` CUDA OOM, start
  ComfyUI with `--disable-dynamic-vram`
  ([ComfyUI#15255](https://github.com/Comfy-Org/ComfyUI/issues/15255)).

All folders below are under `ComfyUI/models/`.

## MiniMax H3 (video with sound, and stills)

From [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3):

| Slot | File | Folder |
|---|---|---|
| FL2VA checkpoint | `minimax_h3_fl2va_*.safetensors` | `diffusion_models` |
| Ref2VA checkpoint | `minimax_h3_ref2va_*.safetensors` | `diffusion_models` |
| Text encoder | `qwen3vl_32b_minimax_h3_*.safetensors` | `text_encoders` |
| Video VAE | `minimax_h3_video_vae_fp16.safetensors` | `vae` |
| Audio VAE | `minimax_h3_audio_vae_fp32.safetensors` | `vae` |

You need both checkpoints: H3 routes between them based on what you attach.
The same repo carries the turbo distillation LoRAs under `loras/`; the turbo
switch on the sampler row finds them there.

Optional: [`taeh3.safetensors`](https://github.com/madebyollin/taehv/blob/main/safetensors/taeh3.safetensors)
in `vae_approx` gives H3 a properly decoded live preview.

## LTX 2.5 (video with sound)

From [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5):

| Slot | File | Folder |
|---|---|---|
| Transformer | `ltx-2.5-22b-distilled-transformer-*.safetensors` | `diffusion_models` |
| Text encoder | `gemma4-12b-with-proj-ltx-2.5-*.safetensors` | `text_encoders` |
| Video VAE | `ltx-2.5-video-vae-bf16.safetensors` | `vae` |
| Audio VAE | `ltx-2.5-audio-vae-bf16.safetensors` | `vae` |

Optional files, each unlocking one control:

| Unlocks | File | Folder |
|---|---|---|
| The seconds pill's **auto** | `ltx-2.5-duration-head-bf16.safetensors` | `model_patches` |
| The resolution pill's **two passes** | `ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors` | `latent_upscale_models` |
| **ReDetail** | [LTX-2.5-22b-IC-LoRA-Pixel-Spatial-Upscaler](https://huggingface.co/Lightricks/LTX-2.5-22b-IC-LoRA-Pixel-Spatial-Upscaler) | `loras` |
| References | [LTX-2.3-22b-IC-LoRA-Ingredients](https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-Ingredients) | `loras` |

About that last row: citing a reference on LTX 2.5 needs the Ingredients
IC-LoRA, which is what makes a reference sheet mean anything to the
transformer. Lightricks hasn't released a 2.5 Ingredients yet, so use the 2.3
one. Most 2.3 IC-LoRAs load and work on 2.5, and that file is what this pack
was built and tested against. A shot with no references never asks for it.

## Krea 2 (stills)

From [Comfy-Org/Krea-2](https://huggingface.co/Comfy-Org/Krea-2):

| Slot | File | Folder |
|---|---|---|
| Checkpoint | `krea2_raw_*.safetensors` | `diffusion_models` |
| Turbo checkpoint | `krea2_turbo_*.safetensors` | `diffusion_models` |
| Text encoder | `qwen3vl_4b_*.safetensors` | `text_encoders` |
| VAE | `qwen_image_vae.safetensors` | `vae` |

## Ideogram 4.0 (stills)

From [Comfy-Org/Ideogram-4](https://huggingface.co/Comfy-Org/Ideogram-4):

| Slot | File | Folder |
|---|---|---|
| Checkpoint | `ideogram4_*.safetensors` | `diffusion_models` |
| Unconditional checkpoint (optional) | `ideogram4_unconditional_*.safetensors` | `diffusion_models` |
| Text encoder | `qwen3vl_8b_*.safetensors` | `text_encoders` |
| VAE | `flux2-vae.safetensors` | `vae` |

## Qwen Image Edit (stills, edited from a picture)

From [Comfy-Org/Qwen-Image-Edit_ComfyUI](https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI):

| Slot | File | Folder |
|---|---|---|
| Checkpoint | `qwen_image_edit_2511_*.safetensors` (or `2509`) | `diffusion_models` |
| Text encoder | `qwen_2.5_vl_7b_*.safetensors` | `text_encoders` |
| VAE | `qwen_image_vae.safetensors` | `vae` |

The turbo pill wants a
[Lightning LoRA](https://huggingface.co/lightx2v/Qwen-Image-Edit-2511-Lightning)
in `loras`, matched to the edition of your checkpoint. There is no distilled
checkpoint for this family; the LoRA is the whole speed axis. The VAE is the
same file Krea 2 loads.

## Flux 2 Klein (stills, edited from a picture)

Published by [Black Forest Labs](https://huggingface.co/black-forest-labs) at
two sizes: 4B (Apache 2.0) or 9B (non-commercial).

| Slot | File | Folder |
|---|---|---|
| Checkpoint | `flux-2-klein-base` (4B or 9B) | `diffusion_models` |
| Turbo checkpoint | the 4-step distilled file, same sizes | `diffusion_models` |
| Text encoder | `qwen_3_4b` or `qwen_3_8b`, matched to the checkpoint size | `text_encoders` |
| VAE | `flux2-vae.safetensors` | `vae` |

The VAE is the same file Ideogram loads. The turbo pill swaps in the distilled
checkpoint; there is no turbo LoRA for this family.

## Cutouts and the faces pass

| For | File | Folder |
|---|---|---|
| One-click cutouts | [`birefnet.safetensors`](https://huggingface.co/Comfy-Org/BiRefNet) | `background_removal` |
| Click-to-select cutouts, the faces pass, and the Matte tracing | [`sam3.1_multiplex_fp16.safetensors`](https://huggingface.co/Comfy-Org/sam3.1) | `checkpoints` |

BiRefNet mattes the most prominent subject with no clicks, which is enough for
a picture with one subject in it. SAM 3 is for saying which subject you mean,
and it is also the file the per-frame faces pass and the ControlNet bench's
Matte tracing need.

## The Refine button

Any Qwen3-VL 4B or 8B in `text_encoders`, for example
`qwen3vl_4b_bf16.safetensors`. If you already have Krea 2 or Ideogram 4.0
installed, you're done: their text encoders are those exact files.

H3's own 32B encoder is not a candidate. It is truncated and has no head to
decode text with, and the picker says so if you choose it.

Or skip the file: Refine can point at any OpenAI-compatible server instead.
See [the-node.md](the-node.md#refine).

## The ControlNet bench

The five arithmetic tracings need nothing. Depth and Pose run a model:

| Tracing | File | Folder |
|---|---|---|
| Depth | any Depth Anything 3 model | `geometry_estimation` |
| Pose | `sdpose_wholebody_fp16.safetensors`, plus any SD 1.5 VAE | `checkpoints`, `vae` |

Matte uses the SAM 3 checkpoint from the cutouts table above.

## The upscale bench

| Backend | File | Folder |
|---|---|---|
| Sharpen | any GAN upscaler spandrel loads (`RealESRGAN_x4plus`, `4x-UltraSharp`, DAT, SwinIR, SPAN) | `upscale_models` |
| Restore | `seedvr2_3b_int8_convrot.safetensors` and `seedvr2_ema_vae_fp16.safetensors` (from Comfy-Org/SeedVR2) | `diffusion_models`, `vae` |

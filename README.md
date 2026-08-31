# Continuity

One node for AI video and stills in ComfyUI. Write a prompt, attach media with
`@`, press Render. Six model families, all through ComfyUI core, all local
open weights. The one thing that can talk to the outside is the prompt
refiner, and only if you point it at your own server or provider - LM Studio,
Ollama, or a hosted API with your key.

![A shot sampling, with the render beside it](docs/img/hero.png)

## Install

```
cd ComfyUI/custom_nodes
git clone https://github.com/roadmaus/ComfyUI-Continuity
```

That leaves one folder, `ComfyUI-Continuity`, inside `custom_nodes/`. Restart
ComfyUI. Nothing to pip install.

### Already have MiniMax Creator installed

Don't clone. This pack was renamed, and GitHub redirects the old address here,
so a pull in the folder you already have is the whole update:

```
cd ComfyUI/custom_nodes/ComfyUI-MiniMax-Creator
git pull
```

The folder name doesn't matter to ComfyUI, so rename it or leave it. If it came
from the Manager, update it there as usual.

Cloning next to the old folder is what breaks. The node ids stayed the same
through the rename so that old workflows keep loading, so two folders are two
packs registering the same ids, and the result is no node in the search at all,
under either name. If you already have both, delete one and restart. Your
presets, settings, favourites and LoRA memory are in ComfyUI's `user/`
directory, not in the pack folder.

## Documentation

- [Getting started](docs/getting-started.md)
- [Model downloads](docs/models.md) - every file, and the folder it goes in
- [The node](docs/the-node.md) - prompting, references, the cast, Refine
- [Timelines](docs/timeline.md) - pieces with more than one shot
- [Model families](docs/families.md) - what each model can do
- [Tools](docs/tools.md) - ControlNet, upscaling, presets, LoRAs
- [FAQ and troubleshooting](docs/faq.md)
- [Changelog](CHANGELOG.md) - what changed, release by release

![The node in the simple view](docs/img/simple.png)

![The full view](docs/img/full.png)

![Two references cited in a prompt](docs/img/mentions.png)

![The style atlas](docs/img/style-atlas.png)

## Models

| Family | Makes | Weights |
|---|---|---|
| MiniMax H3 | video with sound, and stills | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3) |
| LTX 2.5 | video with sound | [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5) |
| Krea 2 | stills | [Comfy-Org/Krea-2](https://huggingface.co/Comfy-Org/Krea-2) |
| Ideogram 4.0 | stills | [Comfy-Org/Ideogram-4](https://huggingface.co/Comfy-Org/Ideogram-4) |
| Qwen Image Edit | stills, edited from a picture | [Comfy-Org/Qwen-Image-Edit_ComfyUI](https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI) |
| Flux 2 Klein | stills, edited from a picture | [Black Forest Labs](https://huggingface.co/black-forest-labs) |

See [docs/models.md](docs/models.md) for which files you need and where they go.

## Thanks

This pack is glue. The work underneath it belongs to other people:

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) by Comfy Org - every family here lives in core, this node drives them
- [Lightricks](https://huggingface.co/Lightricks) - LTX 2.5, its IC-LoRAs, the duration head and the two-stage pipeline
- [ComfyUI-Spectrum-MiniMax-H3](https://github.com/xmarre/ComfyUI-Spectrum-MiniMax-H3) by xmarre - an accelerator on the sampler row
- [ComfyUI-MiniMaxH3-FirstBlockCache](https://github.com/duckyshell/ComfyUI-MiniMaxH3-FirstBlockCache) by duckyshell - an accelerator on the sampler row
- [ComfyUI-MiniMaxH3-TeaCache](https://github.com/Icyoung/ComfyUI-MiniMaxH3-TeaCache) by Icyoung - an accelerator on the sampler row
- [ComfyUI-KJNodes](https://github.com/kijai/ComfyUI-KJNodes) by Kijai - the live preview decoder, sage attention, the low vram pill
- [ComfyUI-MultiGPU](https://github.com/pollockjj/ComfyUI-MultiGPU) by pollockjj - the device chip on the weights popover
- [ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) by city96 - loads the `.gguf` files the weights popover offers
- [ComfyUI#15416](https://github.com/Comfy-Org/ComfyUI/issues/15416) by matlowai - the fix behind H3 single-frame stills
- [ComfyUI-MiniMaxH3_LatentUpscaler](https://github.com/Tr1dae/ComfyUI-MiniMaxH3_LatentUpscaler) by Tr1dae - pioneered the two-pass upscale our refine pass reimplements
- [ComfyUI-H3-FaceRefine](https://github.com/Carasibana/ComfyUI-H3-FaceRefine) by Carasibana, and zuanfilm's graph on it - worked out the face pass ours reimplements
- [minimax-h3-style-atlas](https://github.com/hoodtronik/minimax-h3-style-atlas) by hoodtronik, over [minimax_h3_1k](https://huggingface.co/datasets/ostris/minimax_h3_1k) by ostris - the 941 looks on the style tab
- [taehv](https://github.com/madebyollin/taehv) by madebyollin - the tiny decoder behind the live preview
- [BiRefNet](https://github.com/ZhengPeng7/BiRefNet) by ZhengPeng7 - the matte behind every one-click cutout
- [ComfyUI-H3-PowerLoraStack](https://github.com/cicalooo/ComfyUI-H3-PowerLoraStack) by cicalooo - the H3-safe LoRA loader, vendored (Apache-2.0)
- larryvrh and lightx2v - the H3 distillation LoRAs behind turbo
- CiviMeta - the sidecar format the LoRA cards read

All of those packs are optional. If one is installed, the matching pills light
up.

## License

[MIT](LICENSE). ComfyUI itself is GPL-3.0 and this pack imports it; if you
redistribute the two together rather than as a node pack people install
themselves, that combination is what the GPL has an opinion about.

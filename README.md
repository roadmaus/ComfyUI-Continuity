# Continuity

One node for AI video and stills in ComfyUI. Write a prompt, attach media with
`@`, press Render. Drives six model families through ComfyUI core, local open
weights only, no API key.

![A shot sampling, with the render beside it](docs/img/hero.png)

## Install

```
cd ComfyUI/custom_nodes
git clone https://github.com/roadmaus/ComfyUI-Continuity
```

Restart ComfyUI. Nothing to pip install.

## Documentation

- [Getting started](docs/getting-started.md)
- [Model downloads](docs/models.md) - every file, and the folder it goes in
- [The node](docs/the-node.md) - prompting, references, the cast, Refine
- [Timelines](docs/timeline.md) - pieces with more than one shot
- [Model families](docs/families.md) - what each model can do
- [Tools](docs/tools.md) - ControlNet, upscaling, presets, LoRAs
- [FAQ and troubleshooting](docs/faq.md)

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

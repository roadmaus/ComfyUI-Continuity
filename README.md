# MiniMax H3 Creator

Write a sentence, attach your media with `@`, press Render. One node holds the
whole generation and hands back a finished clip with its sound already in it —
no conditioning sockets, no sampler to re-assemble, no VAE to remember to
connect. Write a second shot on it and the same node is a timeline.

Local open weights only, through core's `comfy_extras/nodes_minimax_h3.py`. No
API key, nothing uploaded.

![A shot sampling, with the render beside it](docs/img/hero.png)

Release notes live in [CHANGELOG.md](CHANGELOG.md). The design decisions, in
full, are in [docs/PLAN.md](docs/PLAN.md).

## Install

```
cd ComfyUI/custom_nodes
git clone https://github.com/roadmaus/comfyui-minimax-creator ComfyUI-MiniMax-Creator
```

Restart ComfyUI. Nothing to `pip install`. You need a ComfyUI new enough to ship
`comfy_extras/nodes_minimax_h3.py`, since that is where the model lives.

Then put the weights where ComfyUI already looks:

| file | folder |
|---|---|
| FL2VA, Ref2VA | `models/diffusion_models` |
| text encoder | `models/text_encoders` (CLIPLoader type `minimax`) |
| video VAE, audio VAE | `models/vae` |
| preview decoder | `models/vae_approx` — [`taeh3.safetensors`](https://github.com/madebyollin/taehv) |
| refiner (optional) | `models/text_encoders` — any Qwen3-VL, 4B is plenty |
| Krea 2 / Ideogram 4.0 (optional) | `models/diffusion_models`, `models/text_encoders`, `models/vae` |
| single-image H3 VAE (optional) | `models/vae` — [MiniMax-H3-Image-VAE](https://huggingface.co/Mamad8/MiniMax-H3-Image-VAE), for H3 stills |

You pick the files on the node's **weights** pill. Anything a render needs and
does not have is refused before the queue starts, naming the field and the
folder it looks in. GGUF checkpoints and text encoders work with
[ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) installed — drop the
`.gguf` in the same folder and pick it like any other file.

Two machine notes. fp8 checkpoints only *speed up* sampling on cards with
hardware fp8 matmul (RTX 40-series and later); on older cards they still halve
the memory and change nothing else. And recent ComfyUI streams weights with
Dynamic VRAM by default — if a long render dies with a
`HostBuffer.read_file_slice` CUDA OOM, start ComfyUI with
`--disable-dynamic-vram` ([#15255](https://github.com/Comfy-Org/ComfyUI/issues/15255)).

## The node

![The node in the simple view](docs/img/simple.png)

Everything is on it. The rail attaches images, video, audio and LoRAs; the box in
the middle is your prompt; the pills under it are duration, aspect, resolution and
the sampler. The mode badge (`T2VA → FL2VA`) says which checkpoint this render
will land on — you never pick one.

Drop the node, type, press Render. That is the workflow.

`Ctrl+Shift+M` opens the node as the whole window instead of a rectangle on the
canvas, with two views over the same state: **Simple** is one column for when the
piece is one prompt, **Full** puts the pre-stage, the shot and the picture side by
side for when it is being built out of parts. Switching mid-sentence keeps the
sentence — it is the same node, the same blob, the same queue.

![The full view](docs/img/full.png)

## Attaching things

Type `@` anywhere in the prompt. The menu lists what is already attached first,
then everything in your input folder; pick a file that is not attached yet and it
gets attached. The rail buttons open the same library with a tab per kind, search,
shelves, favourites and upload — and a **Renders** tab over `output/`, so a clip
you just made goes straight back in as a reference.

![Two references cited in a prompt](docs/img/mentions.png)

Every attachment gets a colour and its chip in the sentence wears the same one.

This matters because H3 does not take free text. It takes a structured
description where every reference is addressed as `<Picture 1>`, `<Video 2>`,
`<Audio 1>`. Writing `use @img-1 for their face` assigns those labels for you, in
the order the tokenizer expects.

Each reference also gets a **scope dial**, on its chip. An image's reads `full ·
person · object · scene · style` — on `person`, "them from @img-1" stops dragging
that image's background, palette and pose along with the face. A clip adds
`motion`, `camera`, `edit` and `continue`; a sound reads `voice · music ·
ambience · copy`. H3 has no reference-conditioning input, so each of these is a
different sentence in the compiled prompt or it is nothing.

Video and audio get a segment editor on the chip: scrub, drag the handles, or
slide a fixed-length selection along the waveform. Three buttons decide what a
video contributes — picture + sound, picture only, or sound only.

## The cast

A reference is a file. A *subject* is who is in the video, and H3 keeps the two
apart. So people are **cast**, not attached: press Cast on the rail, name them,
and hang files on them — a face from three stills, a walk from a clip, a voice
from an mp3, a person they take the place of in some footage.

Hanging a file on somebody sets its scope dial for you, because the two settings
were never independent. Then write with them: `@anna walks in and looks at @ben`.
Citing a subject is what carries their files into that shot, so a shot that never
names them does not pay for their pictures. A name and a description with no files
behind it is a subject too — and it is what keeps them the same person in shot 1
and in shot 9.

## More than one shot

Under the prompt there is a stretch of unexposed film — **Write the next shot**.
Click it and the piece has two shots, and the node's face becomes a lane strictly
proportional to their durations. Each card is a whole generation with its own
prompt, references and LoRAs. Delete back down to one and the single-shot face
comes back. There is no mode to pick.

**Chained** renders each segment and joins them; a seam can continue from any
earlier segment's last frame, at one frame or a 5/22/39-frame blend that carries
real motion and phase-locked sound across the cut. **One pass** compiles the same
cards into a *single* generation, since H3's prompt format is already a shot
list — no seam at all, and music or dialogue carries across.

**Piece references** attach a file to the timeline itself and hand out `@ref-N`
handles: cite one in the global prompt and it rides into every segment, cite it in
one card and it rides into that card alone.

Every card also carries a **padlock**: locked cards are not rendered, so you can
shoot a long strip one pass at a time, keeping the takes you like — each pass is
written as its own file under `takes/` — and re-shooting only the card you are
working on.

## Presets and the style atlas

**Presets** on the rail saves a setup you can put back: a whole piece, one shot
off a strip, a pre-stage, or one cast member. It saves the sampler row too, which
was never in the blob. Applying is per-section — tick *look* and *speed* to drop a
canvas and a step count onto a shot you have already written, and the prose stays
where it is. **From a render** turns a finished MP4 or PNG back into a preset, out
of the workflow the file already carries.

![The style atlas](docs/img/style-atlas.png)

The library's last tab is a catalogue rather than a shelf of your own work: **941
looks** indexed from [ostris/minimax_h3_1k](https://huggingface.co/datasets/ostris/minimax_h3_1k)
by [hoodtronik's Style Atlas](https://github.com/hoodtronik/minimax-h3-style-atlas),
with a still off every clip. They are worth having because they are not adjectives
somebody thought of — they are the exact strings this model was captioned with.
Applying one *swaps the lead* of your prompt rather than replacing it, so trying
six looks on one shot gives you six prompts rather than six stacked paragraphs.
The atlas is vendored (~5 MB of index and stills); nothing is downloaded.

## The rest, briefly

- **Refine** rewrites your sentence into the long sectioned description H3 was
  trained to read, using a small local vision model, and lands it in an editable
  box under the prompt. It is a button rather than a queue-time step so you see
  what the model will read *before* five minutes of sampling.
- **PreStage** generates the stills the pipeline eats — start frames, end frames,
  references — on the same canvas, with Krea 2, Ideogram 4.0 or H3 itself. Its
  result card writes the finished still straight into the peer node.
- **Faces** runs a second small generation per pass: the face is tracked, cropped
  to fill 512 px, re-drawn by H3 at a denoise scaled by how big the head already
  is, and pasted back under a feathered mask. Needs a SAM3 checkpoint, which ships
  with core.
- **LoRAs** get a full-screen manager over `models/loras`, with cards built from
  whatever sidecar metadata is sitting beside the file, per-LoRA strength, and
  trigger words prefixed at compile time.
- **Modes** are picked by what you attach, and the mode picks the checkpoint —
  nothing attached is T2VA, frames are FL2VA, any reference is Ref2VA, and frames
  *and* references run on Ref2VA with the frames pinned as guides. Clicking the
  badge forces everything onto one checkpoint.
- **Duration** must satisfy `n % 17 == 5` at 24 fps, so there is no 6.00-second H3
  video; the pill shows whole seconds and the compiler lands on the nearest legal
  count. Resolution sets the short edge (native 768); past 768 it samples native
  and refines up in a second pass rather than going off-distribution directly.
- **Where files go** is a per-machine setting (Settings → Folders), not part of
  the workflow, with `%year%`-style tokens; MP4 quality is a setting too.
- **Language** follows ComfyUI's own locale — English, 日本語, 한국어, 简体中文.
  Corrections are one-line edits in `js/minimax_creator/locales/`.

## Thanks

This pack is glue. The work underneath it belongs to other people:

- **[Comfy Org](https://github.com/comfyanonymous/ComfyUI)** — H3 lives in core;
  this node only drives it.
- **[ComfyUI-Spectrum-MiniMax-H3](https://github.com/xmarre/ComfyUI-Spectrum-MiniMax-H3)**
  by xmarre,
  **[ComfyUI-MiniMaxH3-FirstBlockCache](https://github.com/duckyshell/ComfyUI-MiniMaxH3-FirstBlockCache)**
  by duckyshell and
  **[ComfyUI-MiniMaxH3-TeaCache](https://github.com/Icyoung/ComfyUI-MiniMaxH3-TeaCache)**
  by Icyoung — the accelerator pills on the sampler row. The cache pill also
  offers core's own EasyCache (`easy`), which needs nothing installed. One
  cache at a time; all of them trade fidelity for speed, so A/B against a
  native render before trusting one on a final piece.
- **[ComfyUI-KJNodes](https://github.com/kijai/ComfyUI-KJNodes)** by Kijai — gives the
  live preview a real decoder, `sage` on the attention pill — H3's own attention
  run quantized, which is faster and, unlike the caches, wants *less* VRAM
  rather than trading fidelity for steps, and needs the
  [sageattention](https://github.com/thu-ml/SageAttention) package and an NVIDIA
  card — and the `low vram` pill, which splits H3's feed-forward over the
  packed sequence for the same lower peak and no trade at all: the activations
  are quantized per token, so the frames are the ones you would have had — and
  `fast math`, which lets cuBLAS accumulate fp16 matmuls in fp16 while the model
  runs. That last one reaches fp16 matmuls only: the released H3 checkpoints run
  bf16 and their quantized layers use comfy-kitchen's kernels rather than cuBLAS,
  so it is there for an fp16 model and does nothing on the usual bakes. All three
  compose with everything else on the row. Kijai's turbo conversions are in the
  switch too.
- **ComfyUI core** — `kitchen` on the attention pill is core's own int8
  attention kernel, with nothing to install. The option appears only on a build
  that ships the kernel and can run it; where it does not, the pill says so
  rather than sampling on something else.
- **[ComfyUI-MultiGPU](https://github.com/pollockjj/ComfyUI-MultiGPU)** by pollockjj —
  puts a device chip on every row of the weights popover.
- **[ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF)** by city96 — loads the
  `.gguf` files the weights popover offers once it is installed.
- **[MiniMax-H3-Image-VAE](https://huggingface.co/Mamad8/MiniMax-H3-Image-VAE)** by
  Mamad8 — the experimental single-image decoder the PreStage's H3 branch reads a
  still through. Trained with H3's own encoder frozen, which is what lets one file
  both encode the references and decode the picture.
- **[ComfyUI-MiniMaxH3_LatentUpscaler](https://github.com/Tr1dae/ComfyUI-MiniMaxH3_LatentUpscaler)**
  by Tr1dae — pioneered the two-pass workflow the resolution popover's "two
  passes" option is built on: upscale the video half of the AV latent between
  two samplers, leave the audio out of the re-noise. Our refine pass is an
  independent implementation of that idea, wired into the render graph.
- **[ComfyUI-H3-FaceRefine](https://github.com/Carasibana/ComfyUI-H3-FaceRefine)** by
  Carasibana, and **zuanfilm**'s graph built on it — worked out the face pass this
  pack's **faces** pill runs: a per-frame crop that holds the face at a constant
  fraction of one canvas, a denoise scaled by how big the face already is, and a
  paste of the face box alone rather than the whole crop. Ours is an independent
  implementation of those findings, using core's SAM3 in place of the
  ultralytics/insightface stack theirs needs.
- **[minimax-h3-style-atlas](https://github.com/hoodtronik/minimax-h3-style-atlas)**
  by hoodtronik, over the
  **[minimax_h3_1k](https://huggingface.co/datasets/ostris/minimax_h3_1k)** dataset
  by **ostris** — the 941 looks on the preset library's style tab, and the still
  on every card. Vendored as text and one frame per clip; the dataset's video is
  neither shipped nor fetched.
- **[taehv](https://github.com/madebyollin/taehv)** by madebyollin — the tiny decoder
  that makes the preview look like the video.
- **[ComfyUI-H3-PowerLoraStack](https://github.com/cicalooo/ComfyUI-H3-PowerLoraStack)**
  by cicalooo — the H3-safe LoRA library this pack loads every LoRA through.
  Vendored (Apache-2.0) rather than called, because it is the correct path
  rather than an optional one; see `h3lora/__init__.py`.
- **larryvrh** and **lightx2v** — the H3 distillation LoRAs behind turbo.
- **CiviMeta** — the sidecar format the LoRA cards read.

Every one of those packs is optional and none of them is required. If they are
installed, the matching pills light up.

## License

[MIT](LICENSE). ComfyUI itself is GPL-3.0 and this pack imports it; if you
redistribute the two together rather than as a node pack people install
themselves, that combination is what the GPL has an opinion about.

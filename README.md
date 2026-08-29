# Continuity

Write a sentence, attach your media with `@`, press Render. One node holds the
whole generation and hands back a finished clip with its sound already in it —
no conditioning sockets, no sampler to re-assemble, no VAE to remember to
connect. Write a second shot on it and the same node is a timeline.

Continuity is the script supervisor's job: the same person, the same prop and
the same light in shot 1 and in shot 9. That is what this node is built around,
and it is why the cast, the references and the seams are the parts with the most
thought in them.

Local open weights only, through ComfyUI core. No API key, nothing uploaded.

![A shot sampling, with the render beside it](docs/img/hero.png)

Release notes live in [CHANGELOG.md](CHANGELOG.md). The design decisions, in
full, are in [docs/PLAN.md](docs/PLAN.md).

## It used to be MiniMax Creator

That was an honest name while H3 was the only thing this drove. It now drives
five model families, and the old name described a fifth of it. Continuity is
the part that is true of all five: the same person, the same prop and the same
light in shot 1 and in shot 9, whichever model is doing the sampling. What that
buys you is the section below.

The repository is now `ComfyUI-Continuity`. GitHub redirects the old address, so
an existing clone still pulls, but it is worth pointing it at the new one:

```
git remote set-url origin https://github.com/roadmaus/ComfyUI-Continuity.git
```

Nothing in a saved workflow changed. The node ids, the widget names and the
folders your renders land in are all the same, so old graphs load and old files
stay where they are.

## Five families, one node

A **family** is a model architecture and everything this pack knows about how to
talk to it: which checkpoints it routes between, how prose reaches its encoder,
what a reference means to it, how a LoRA gets in. The node is the same node on
all of them. What changes is the pill that says which one this shot lands on.

| family | makes | how it reads references |
|---|---|---|
| **MiniMax H3** | video with sound, and stills | each reference encoded on its own, addressed as `<Picture 1>` in a structured prompt |
| **LTX 2.5** | video with sound | up to nine stills composited into one Ingredients reference sheet. Stills only — a reference clip or sound has no panel to be |
| **Krea 2** | stills | up to three, cited as `Picture N` — the labels core's Qwen-edit encoder writes |
| **Ideogram 4.0** | stills | none. Prose only |
| **Qwen Image Edit** | stills | up to three, on the base weights. The first one is not a reference at all — it is the picture being changed |

You are not asked to pick one and stay there. A strip can be H3 throughout, or
a pre-stage on Krea 2 feeding start frames into shots on LTX 2.5. Every render
files into a folder named after whatever rendered it, and carries that name on
the file.

Qwen Image Edit is the odd one out and the reason it is here: the other four
answer a sentence, and it answers a sentence *about a picture you already have*.
Attach the last frame of shot 1, write "the coat is red now", and what comes
back is the same person in the same room. That is shot 9's start frame, which is
the whole errand this pack is named after.

It reads a *strip* the same way. The **Contact sheet** tool on the pre-stage's
rail lays nine frames of a clip out as one gutterless picture; edit that picture
with one instruction and the model holds the subject across the tiles, because
as far as it is concerned they are one image. The same tool cuts the edited
sheet back into nine frames in the input folder. It is a real experiment in
continuity across a shot rather than across a cut, and it costs one render.

## Install

```
cd ComfyUI/custom_nodes
git clone https://github.com/roadmaus/ComfyUI-Continuity
```

Restart ComfyUI. Nothing to `pip install`. You need a ComfyUI new enough to ship
the families you want in `comfy_extras/` — H3 is `nodes_minimax_h3.py`, and the
rest are core nodes too. This pack drives them; it does not carry them.

## Weights

Nothing is bundled and nothing is fetched. You put files where ComfyUI already
looks and pick them on the node's **weights** pill. Anything a render needs and
does not have is refused before the queue starts, naming the field and the folder
it looks in.

The convenient part: **the Comfy-Org and Lightricks repositories are laid out as
`models/` already.** A file at `diffusion_models/krea2_raw_bf16.safetensors` in
the repo goes to `ComfyUI/models/diffusion_models/krea2_raw_bf16.safetensors`.
Download by path and you cannot put it in the wrong place.

Pick one weight per slot — the quantisations below are alternatives, not a set.
`bf16` is the reference, `fp8_scaled` halves the memory, `int8_convrot` and
`nvfp4` go smaller again. Two machine notes: fp8 only *speeds up* sampling on
cards with hardware fp8 matmul (RTX 40-series and later), and recent ComfyUI
streams weights with Dynamic VRAM by default — if a long render dies with a
`HostBuffer.read_file_slice` CUDA OOM, start ComfyUI with
`--disable-dynamic-vram`
([#15255](https://github.com/Comfy-Org/ComfyUI/issues/15255)).

GGUF checkpoints and text encoders work with
[ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) installed — drop the
`.gguf` in the same folder and pick it like any other file.

### Video — MiniMax H3

[**Comfy-Org/MiniMax-H3**](https://huggingface.co/Comfy-Org/MiniMax-H3)

| slot | file | folder |
|---|---|---|
| FL2VA checkpoint | `diffusion_models/minimax_h3_fl2va_*.safetensors` | `models/diffusion_models` |
| Ref2VA checkpoint | `diffusion_models/minimax_h3_ref2va_*.safetensors` | `models/diffusion_models` |
| text encoder | `text_encoders/qwen3vl_32b_minimax_h3_*.safetensors` | `models/text_encoders` |
| video VAE | `vae/minimax_h3_video_vae_fp16.safetensors` | `models/vae` |
| audio VAE | `vae/minimax_h3_audio_vae_fp32.safetensors` | `models/vae` |

Both checkpoints, because H3 routes between them by what you attach and the
badge that says which is not a thing you set. The same repo carries the turbo
distillation LoRAs under `loras/` — the turbo switch on the sampler row finds
them there.

### Video — LTX 2.5

[**Lightricks/LTX-2.5**](https://huggingface.co/Lightricks/LTX-2.5)

| slot | file | folder |
|---|---|---|
| transformer | `diffusion_models/ltx-2.5-22b-distilled-transformer-*.safetensors` | `models/diffusion_models` |
| text encoder | `text_encoders/gemma4-12b-with-proj-ltx-2.5-*.safetensors` | `models/text_encoders` |
| video VAE | `vae/ltx-2.5-video-vae-bf16.safetensors` | `models/vae` |
| audio VAE | `vae/ltx-2.5-audio-vae-bf16.safetensors` | `models/vae` |

Three optional files, each unlocking one control. Pick none and the pack still
renders; pick none and reach for the control anyway and it says which file it
wanted.

| unlocks | file | folder |
|---|---|---|
| the seconds pill's **auto** | `model_patches/ltx-2.5-duration-head-bf16.safetensors` | `models/model_patches` |
| the resolution pill's **two passes** | `latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors` | `models/latent_upscale_models` |
| **ReDetail** | [`LTX-2.5-22b-IC-LoRA-Pixel-Spatial-Upscaler`](https://huggingface.co/Lightricks/LTX-2.5-22b-IC-LoRA-Pixel-Spatial-Upscaler) | `models/loras` |

**Citing a reference on LTX 2.5 needs the Ingredients IC-LoRA**, which is what
makes a reference sheet mean anything to the transformer. Lightricks has not
released a 2.5 Ingredients yet, so use
[**the 2.3 one**](https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-Ingredients) —
most 2.3 IC-LoRAs load and work on 2.5, and that is the file this has been built
and tested against. Drop it in `models/loras`. A shot with no references never
asks for it.

### Stills — Krea 2

[**Comfy-Org/Krea-2**](https://huggingface.co/Comfy-Org/Krea-2)

| slot | file | folder |
|---|---|---|
| checkpoint | `diffusion_models/krea2_raw_*.safetensors` | `models/diffusion_models` |
| Turbo checkpoint | `diffusion_models/krea2_turbo_*.safetensors` | `models/diffusion_models` |
| text encoder | `text_encoders/qwen3vl_4b_*.safetensors` | `models/text_encoders` |
| VAE | `vae/qwen_image_vae.safetensors` | `models/vae` |

### Stills — Qwen Image Edit

[**Comfy-Org/Qwen-Image-Edit_ComfyUI**](https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI)

| slot | file | folder |
|---|---|---|
| checkpoint | `diffusion_models/qwen_image_edit_2511_*.safetensors` (or `2509`) | `models/diffusion_models` |
| text encoder | `text_encoders/qwen_2.5_vl_7b_*.safetensors` | `models/text_encoders` |
| VAE | `vae/qwen_image_vae.safetensors` | `models/vae` |

The turbo pill wants a [**Lightning
LoRA**](https://huggingface.co/lightx2v/Qwen-Image-Edit-2511-Lightning) in
`models/loras` — four or eight steps at cfg 1, matched to the edition your
checkpoint is. There is no distilled checkpoint to swap to; the LoRA is the whole
speed axis. The VAE is the same file Krea 2 loads.

### Stills — Ideogram 4.0

[**Comfy-Org/Ideogram-4**](https://huggingface.co/Comfy-Org/Ideogram-4)

| slot | file | folder |
|---|---|---|
| checkpoint | `diffusion_models/ideogram4_*.safetensors` | `models/diffusion_models` |
| unconditional checkpoint (optional) | `diffusion_models/ideogram4_unconditional_*.safetensors` | `models/diffusion_models` |
| text encoder | `text_encoders/qwen3vl_8b_*.safetensors` | `models/text_encoders` |
| VAE | `vae/flux2-vae.safetensors` | `models/vae` |

### Cutouts and segmentation

Press the scissors on a reference picture and the subject is lifted off its
background onto a flat field, so citing somebody's portrait for their face stops
also citing the room they stood in. This runs in the picker, not in a render —
what the card carries afterwards is the picture you were looking at.

| for | file | folder |
|---|---|---|
| cutting out — the default, no clicks needed | [`background_removal/birefnet.safetensors`](https://huggingface.co/Comfy-Org/BiRefNet) | `models/background_removal` |
| clicking the subject you mean | [`checkpoints/sam3.1_multiplex_fp16.safetensors`](https://huggingface.co/Comfy-Org/sam3.1) | `models/checkpoints` |

BiRefNet is *salient object* matting: no prompt, no box, no click, a soft alpha
at the picture's own resolution. That is enough for a picture with one subject in
it, which is most of them. A picture with two subjects needs you to say which,
and that is SAM3 — click the thing you mean, click again on what you do not.

**SAM3 is also what the faces pass uses.** If you want the second per-pass
generation that re-draws faces at 512 px and pastes them back under a feathered
mask, this is the file it needs.

### Everything else

| for | file | folder |
|---|---|---|
| H3's live preview, decoded properly | [`taeh3.safetensors`](https://github.com/madebyollin/taehv/blob/main/safetensors/taeh3.safetensors) | `models/vae_approx` |
| the **Refine** button | any Qwen3-VL 4B or 8B, e.g. `qwen3vl_4b_bf16.safetensors` | `models/text_encoders` |

H3 stills on the pre-stage need nothing of their own: they are decoded by the
same video VAE the shot is.

The refiner is free if you already have Krea 2 or Ideogram 4.0 installed — their
text encoders *are* Qwen3-VL 4B and 8B, and the refiner reads the same files.
H3's own 32B encoder is not one of them: it is truncated to its hidden states and
has no head to decode text with, and the picker says so if you choose it.

Or skip the file entirely: the refiner's settings can point it at an
OpenAI-compatible server instead — LM Studio, Ollama, llama.cpp, vLLM, or a
hosted API with a key. The key is kept server-side on your machine and never
enters the browser or a workflow file. A server you keep loaded for other work
stays loaded; one that is only answering this button can be told to drop the
model the moment the rewrite is in, so the sampler gets the memory back.

**And the prompting is yours if you want it.** Put a `.md` file in the node's
`creator/skills/` folder and the refiner's settings offer it by name: either
added to the built-in prompting — its guides, its checks and its reply format
all still standing — or replacing it outright, in which case what you wrote is
the model's only instruction and its answer is kept whole. Agent skill packages
(`.skill`) go in the same folder and work the same way.

### The minimum

One family and its required rows. H3 video is five files; LTX 2.5 video is four;
a Krea 2 still is four. Everything in the two sections above is optional, and the
control that wants a missing file is the one that tells you.

## The node

![The node in the simple view](docs/img/simple.png)

Everything is on it. The rail attaches images, video, audio and LoRAs; the box in
the middle is your prompt; the pills under it are duration, aspect, resolution and
the sampler. The model pill says which family and which checkpoint this render
will land on.

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

This matters because a family does not take free text — it takes whatever
structure it was trained on, and the two here are not the same structure. H3
wants a sectioned description where every reference is addressed as
`<Picture 1>`, `<Video 2>`, `<Audio 1>`. LTX 2.5 wants a reference *sheet*: the
stills composited into one panelled image, described as a sheet, and it conditions
through guides rather than through the prompt. Writing
`use @img-1 for their face` is what lets one sentence become either.

Each reference also gets a **scope dial**, on its chip. An image's reads `full ·
person · object · scene · style` — on `person`, "them from @img-1" stops dragging
that image's background, palette and pose along with the face. A clip adds
`motion`, `camera`, `edit` and `continue`; a sound reads `voice · music ·
ambience · copy`.

Video and audio get a segment editor on the chip: scrub, drag the handles, or
slide a fixed-length selection along the waveform. Three buttons decide what a
video contributes — picture + sound, picture only, or sound only.

## The cast

A reference is a file. A *subject* is who is in the video, and the two are kept
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
prompt, references, LoRAs and family. Delete back down to one and the single-shot
face comes back. There is no mode to pick.

**Chained** renders each segment and joins them; a seam can continue from any
earlier segment's last frame, at one frame or a blend that carries real motion and
phase-locked sound across the cut. How wide a blend may be is the family's answer,
not a constant. **One pass** compiles the same cards into a *single* generation,
since both video families take a shot list — no seam at all, and music or dialogue
carries across.

**Piece references** attach a file to the timeline itself and hand out `@ref-N`
handles: cite one in the global prompt and it rides into every segment, cite it in
one card and it rides into that card alone.

Every card also carries a **padlock**: locked cards are not rendered, so you can
shoot a long strip one pass at a time, keeping the takes you like — each pass is
written as its own file under `takes/` — and re-shooting only the card you are
working on.

## Presets and the style atlas

**Presets** on the rail saves a setup you can put back: a whole piece, one shot
off a strip, a pre-stage, or one cast member. It saves the sampler row too, and
the row it saves is the family's — applying an H3 preset does not push H3's
sampler onto an LTX shot. Applying is per-section: tick *look* and *speed* to drop
a canvas and a step count onto a shot you have already written, and the prose
stays where it is. **From a render** turns a finished MP4 or PNG back into a
preset, out of the workflow the file already carries.

![The style atlas](docs/img/style-atlas.png)

The library's last tab is a catalogue rather than a shelf of your own work: **941
looks** indexed from [ostris/minimax_h3_1k](https://huggingface.co/datasets/ostris/minimax_h3_1k)
by [hoodtronik's Style Atlas](https://github.com/hoodtronik/minimax-h3-style-atlas),
each with the frames it was cut from. They are worth having because they are not adjectives
somebody thought of — they are the exact strings this model was captioned with.
Applying one *swaps the lead* of your prompt rather than replacing it, so trying
six looks on one shot gives you six prompts rather than six stacked paragraphs.
The atlas is vendored — 941 looks over 2000 frames, about 40 MB, which is most
of this repository's size — and nothing is downloaded at runtime.

## The ControlNet bench

Every other picture in this pack starts from a sentence. This one starts from a
file you already have. Press the wordmark at the top of the editor and open
**ControlNet**: drop in a clip or a photograph, cut the span you want on the same
trim bar the picker uses, choose a tracing, and it writes a guide into the input
folder that a pre-stage or a shot can be aimed at.

The tracings are **Edges** (Canny — the hard outlines), **Lines** (a drawing that
follows the form rather than a threshold), **Blocks** (the frame flattened into
fields of one colour), **Luma** (the tones with the colour taken out) and **Blur**
(the masses and nothing else). **As shot** does no tracing at all, for when the
footage is already what you want to hand over and only needs cutting or its
soundtrack stripped.

**Depth** and **Pose** are the other two, and they run a model rather than an
arithmetic operator — Depth Anything 3 and SDPose, both of which ComfyUI ships
itself. Put a Depth Anything 3 model in `models/geometry_estimation`, or
`sdpose_wholebody_fp16.safetensors` plus any SD 1.5 VAE in `models/checkpoints`
and `models/vae`, and the tracing turns on. The file is picked on the same
**weights** pill the pre-stage and the shot use, and the pick is remembered for
the machine — set it when you install the model and never again. Nothing is
downloaded from here: a tracing whose files are missing says which ones and
where they go.

Nothing queues. The five arithmetic tracings are pixels in and pixels out, so the
frame under the pointer redraws while a threshold is being dragged — which is why
the settings are sliders and not a form with an Apply button, and why pressing
play traces the clip as it runs rather than leaving a still on the glass. Depth
and pose are a model per frame and cannot be chased like that; press **Trace**
and the written file is what plays on the right. The picture is one rectangle
with a seam across it: footage on the left, tracing on the right, and the seam is
dragged, so an outline that has slipped off a shoulder is visible instead of
being two pictures you have to compare.

What comes out is a file in `input/continuity/control/` and nothing else — no
node is added and no workflow is touched. **Send to pre-stage** makes it the
still's init image; **Send to the shot** attaches it as a reference you can name
with `@`. Neither is required: the file is in the picker either way.

## The upscale bench

The other question a folder of renders eventually asks: here is a file, make it
bigger. Press the wordmark and open **Upscale**. It takes any still or clip —
last night's render, something off a phone, a frame somebody sent you — and it
does not care which family made it or whether this pack made it at all. The card
you opened it from lends it its newest render as a starting point, and you can
drop or choose anything else instead.

Two backends, and choosing between them is choosing what to promise about the
result.

**Sharpen** is a GAN — ESRGAN, DAT, SwinIR, SPAN, anything spandrel loads —
through core's own tiling. Put a model in
`models/upscale_models` (`RealESRGAN_x4plus` is the one core's templates use,
`4x-UltraSharp` the usual pick for photographs) and choose it on the same
**weights** pill everything else in this pack uses. It resolves the detail that
is already in the picture and invents none: a face comes back the same face.
Soft footage comes back soft and bigger, which is the honest answer for it and
not a fault in the model. **Bigger by** is what you get, whatever factor the
model itself was trained at — a x4 model asked for x2 runs once and comes back
down, which is sharper than a x2 model would have been.

The glass shows **one square of the source at the size it will actually come
out**, because a 4K frame fitted into a light box is a picture of everything
except the detail you are judging. Move the square on the locator in the left
column. The seam across it is not the source against the result — it is plain
resampling against the model, which is the comparison worth making: what you
would have had for free, beside what the model gives you.

The resampled half follows the dials. The model half is a press — **Try it
here**, in the corner of the glass — and it runs the backend on that square
alone, seconds instead of the whole file. Nothing here loads a checkpoint until
you ask it to, so you can read what a backend is for, and dial it, without
starting it.

A clip comes back as a clip, its soundtrack copied across untouched and its
timing intact, and the trim bar cuts the span first — worth doing on anything
long, because every frame is a model pass. **This frame** takes the single frame
under the playhead as a picture instead, which is usually what you want when one
shot in a strip is the one worth blowing up.

**Restore** is SeedVR2, which ComfyUI ships nodes for. It does not enlarge the
picture so much as repair it at the size you asked for: compression artefacts,
grain, and the softness of a frame that was small to begin with. On a clip it
reads several frames at once, which is what keeps movement from boiling — the
bench chunks the clip, blends one chunk into the next so the joins do not show,
and **Frames at a time** is the dial to bring down when a long shot runs out of
VRAM. Put `seedvr2_3b_int8_convrot.safetensors` in `models/diffusion_models` and
`seedvr2_ema_vae_fp16.safetensors` in `models/vae` (both from Comfy-Org/SeedVR2)
and it turns on. It is much slower than Sharpen and it is the right answer for
footage that has something wrong with it.

The result lands in `output/continuity/upscaled/`, on a shelf beside your
renders, where the gallery already looks — and from there **Attach to the shot**
makes it a reference you can name with `@`, **Attach to the pre-stage** makes it
one of the pictures the still is drawn from, and **Open it** opens the file. On
a clip, a door that wants a picture upscales the frame under the playhead rather
than refusing. None of it is required: the file is on the shelf either way.

Re-detail is deliberately *not* offered here. It re-renders rather than
resolves — the LTX 2.5 pass that invents detail as it goes — so it belongs to a
render's own settings, and a bench that offered it under the same verb as these
would be promising the same picture back when it cannot.

## The rest, briefly

- **Refine** rewrites your sentence into the long description the family it is
  aimed at was trained to read, using a small local vision model — or any
  OpenAI-compatible server you already run — and lands it in an editable box
  under the prompt. It is a button rather than a queue-time step so you see
  what the model will read *before* five minutes of sampling.
- **Contact sheet** lays a clip out as one picture — nine frames, no gutter — so
  an edit model can be asked about a whole shot at once, and cuts the edited
  sheet back into frames. Browser-side arithmetic: no queue, no weights, and
  the files land in the input folder where the pickers already look.
- **PreStage** generates the stills the pipeline eats — start frames, end frames,
  references — on the same canvas, with Krea 2, Ideogram 4.0, Qwen Image Edit or
  H3 itself. Its result card writes the finished still straight into the peer
  node, or back into the pre-stage as the next render's subject: `↻ edit` is one
  press, and editing the edit is most of what an edit model is for.
- **Faces** runs a second small generation per pass: the face is tracked, cropped
  to fill 512 px, re-drawn at a denoise scaled by how big the head already is, and
  pasted back under a feathered mask.
- **ReDetail** is LTX 2.5's own second pass over a finished render, through
  Lightricks' x2 IC-LoRA — it spends time to buy picture rather than resolution.
- **LoRAs** get a full-screen manager over `models/loras`, with cards built from
  whatever sidecar metadata is sitting beside the file, per-LoRA strength, and
  trigger words prefixed at compile time.
- **Which checkpoint** is picked by what you attach — on H3, nothing attached is
  T2VA, frames are FL2VA, any reference is Ref2VA, and frames *and* references run
  on Ref2VA with the frames pinned as guides. Clicking the badge forces everything
  onto one checkpoint.
- **Duration** is the family's arithmetic, not a free number. H3 must satisfy
  `n % 17 == 5` at 24 fps, so there is no 6.00-second H3 video; the pill shows
  whole seconds and the compiler lands on the nearest legal count. LTX 2.5 has a
  duration head that can be asked how long a shot wants to be.
- **Resolution** sets the short edge. Past a family's native size it samples
  native and refines up in a second pass rather than going off-distribution
  directly.
- **Where files go** is a per-machine setting (Settings → Folders), not part of
  the workflow, with `%year%`-style tokens; MP4 quality is a setting too. Every
  family files into a folder of its own — `output/continuity/renders/ltx25/` and
  `output/continuity/stills/krea2/` — and each has its own row to override.
- **Language** follows ComfyUI's own locale — English, 日本語, 한국어, 简体中文.
  Corrections are one-line edits in `web/creator/locales/`.

## Where this is going

No dates, and none of this is a promise - it is what is being worked on.

- a **3D scene** step for blocking a shot out before anything samples
- more of the small tools that live on the rail, as they turn out to be needed

A family is a package under `creator/families/` with a `declare.py` the registry
picks up, which is deliberate: adding the next one should not mean touching the
node. If there is a model you want in here, open an issue.

## Thanks

This pack is glue. The work underneath it belongs to other people:

- **[Comfy Org](https://github.com/comfyanonymous/ComfyUI)** — every family here
  lives in core; this node only drives them.
- **[Lightricks](https://huggingface.co/Lightricks)** — LTX 2.5, the Ingredients
  and upscaler IC-LoRAs, the duration head, and the two-stage pipeline the
  resolution pill's "two passes" follows.
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
  live preview a real decoder, `sage` on the attention pill — attention run
  quantized, which is faster and, unlike the caches, wants *less* VRAM rather
  than trading fidelity for steps, and needs the
  [sageattention](https://github.com/thu-ml/SageAttention) package and an NVIDIA
  card — and the `low vram` pill, which splits the feed-forward over the packed
  sequence for the same lower peak and no trade at all: the activations are
  quantized per token, so the frames are the ones you would have had — and
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
- **[ComfyUI#15416](https://github.com/Comfy-Org/ComfyUI/issues/15416)** by matlowai —
  measured what a single-token H3 decode actually costs (31.4 and 93.7 mean absolute
  error, against 3.92 for a legal clip) and found the fix the PreStage's H3 still now
  uses: give the VAE the two tokens its grid is built on and keep the first pixel
  frame.
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
- **[BiRefNet](https://github.com/ZhengPeng7/BiRefNet)** by ZhengPeng7 — the matte
  behind every cutout taken without a click.
- **[ComfyUI-H3-PowerLoraStack](https://github.com/cicalooo/ComfyUI-H3-PowerLoraStack)**
  by cicalooo — the H3-safe LoRA library this pack loads every H3 LoRA through.
  Vendored (Apache-2.0) rather than called, because it is the correct path
  rather than an optional one; see `creator/h3lora/__init__.py`.
- **larryvrh** and **lightx2v** — the H3 distillation LoRAs behind turbo.
- **CiviMeta** — the sidecar format the LoRA cards read.

Every one of those packs is optional and none of them is required. If they are
installed, the matching pills light up.

## License

[MIT](LICENSE). ComfyUI itself is GPL-3.0 and this pack imports it; if you
redistribute the two together rather than as a node pack people install
themselves, that combination is what the GPL has an opinion about.

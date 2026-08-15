# MiniMax H3 Creator

Write a sentence, attach your media with `@`, press Run. One node holds the whole
generation and hands back a finished clip with its sound already in it — no
conditioning sockets, no sampler to re-assemble, no VAE to remember to connect.

Write a second shot on it and the same node is a timeline.

Local open weights only, through core's `comfy_extras/nodes_minimax_h3.py`. No API
key, nothing uploaded.

![Sampling, then the finished clip playing beside the node](docs/img/preview.gif)

## What is new in 2.1

**[Presets](#presets).** A setup you can put back — the whole node, or the
sections of it you tick. Saved off a node you have dialled in, or read back out
of a render you already made, since the file carries the workflow that made it.
The library is on the rail beside Gallery and Settings.

Also in 2.1: the settings page no longer resets the fields you did not touch
([#8](https://github.com/roadmaus/ComfyUI-MiniMax-Creator/issues/8)). A save is a
patch over the file now, so naming a video folder stops putting the stills folder
back.

### Coming from 2.0

Nothing to do. Presets are additive, and a node with no preset saved behaves
exactly as it did.

### Coming from 1.x

The headline is that there is one node now instead of two. Update, restart, open
your workflows — they load and render the same. Nothing about a saved piece has
to be redone; see
[Upgrading from the two-node version](#upgrading-from-the-two-node-version) for
what happens to a Timeline node you already placed.

- **One node, one shot or twenty.** The Creator grew the strip rather than
  handing it to a second node. **Write the next shot** under the prompt turns the
  face into a timeline; deleting cards back down to one brings the shot back.
  A Creator render always was a one-segment timeline underneath — the split only
  ever lived in the UI.
- **Two flow clocks on the sampler row.** H3 samples picture and sound on
  separate schedules, and the row now carries both as **shift** pills. They ship
  hidden (Settings → **Nodes**) because most rows never leave the checkpoints'
  own 12/3, at which no shift node is emitted at all; a value off that schedule
  shows its pill regardless. **turbo** presets them to what the LoRA family it
  engages was distilled against, and puts them back on release.
- **Three cache implementations on one pill.** FirstBlockCache and TeaCache from
  the community, plus core's own EasyCache, which needs nothing installed. One
  cache at a time.
- **References citable in the PreStage prompt.** `@ref-2` becomes `Picture 2` —
  the label core's Qwen-edit encoder writes in front of that slot.
- **The render overlay counts passes**, not segments — *Pass 3 of 5* — matching
  what the strip calls them.

## The node

![The Creator node](docs/img/ui_simple.png)

Everything is on it. The rail at the top attaches images, video, audio and LoRAs;
the box in the middle is your prompt; the pills at the bottom are duration, aspect,
resolution and the sampler. The badge on the right (`REF2VA → Ref2VA`) tells you
which checkpoint this render will land on.

That is the whole workflow. Drop the node, type, run.

Under the prompt there is a stretch of unexposed film — **Write the next shot**.
Click it and the piece has two shots instead of one, the strip opens on the new
one, and the node's face becomes the timeline described [below](#more-than-one-shot).
Delete cards back down to one and the face comes back. There is no mode to pick:
one shot or twenty, it is the same node and the same blob.

The **Timeline** pill shows the piece without adding a shot — the standing prompt
every shot inherits, the reference pool, and the LoRAs patched onto all of them.
Click it again to go back to the shot. It is a view, not a setting: nothing about
the render changes, and the choice is saved with the node rather than in the blob.

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

You pick the files in the node itself, on the **weights** pill. Anything a render
needs and does not have is refused before the queue starts, naming the field and
the folder it looks in.

GGUF-quantized checkpoints and text encoders work too, with
[ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) installed: drop the
`.gguf` in the same folders and pick it like any other file — the format is read
off the extension and the right loader is emitted, no setting to switch. The
precision control does not apply to them (theirs was decided at quantization),
and picking one without the pack refuses up front naming it.

> The single-image VAE is a merged H3 VAE and loads through the same node as the
> real one, so nothing downstream can tell them apart. It belongs in the
> PreStage's VAE slot and nowhere else — in a video workflow it costs multi-frame
> reconstruction. The weights pill will not auto-fill it as a video VAE, but it
> will let you pick it, so read the filename.

Two machine notes. fp8 checkpoints only *speed up* sampling on cards with
hardware fp8 matmul (RTX 40-series and later); on older cards they still halve
the memory and change nothing else. And recent ComfyUI streams weights with
Dynamic VRAM by default — if a long render dies with a
`HostBuffer.read_file_slice` CUDA OOM, start ComfyUI with
`--disable-dynamic-vram` (a known core regression as of August 2026,
[#15255](https://github.com/Comfy-Org/ComfyUI/issues/15255)).

## Attaching things

Type `@` anywhere in the prompt. The menu lists what is already attached first, then
everything in your input folder — pick a file that is not attached yet and it gets
attached.

![The @ menu](docs/img/mention-menu.png)

The rail buttons open the same library with a tab per kind, search, shelves,
favourites and upload. The **Renders** tab browses `output/`, so a clip you just
made can go straight back in as a reference.

![The Renders tab](docs/img/render_gallery.png)

**Gallery** on the rail opens straight onto that tab. It is the same picker, so
renders organize exactly like input files do: make a shelf, drag thumbnails onto
it, star the keepers, and use **Organize** to move or delete in bulk. Stills and
finished clips arrive on separate shelves, because videos and stills write to
separate folders — see below.

Every attachment gets a colour and its chip in the sentence wears the same one, so
you can match a reference in the prose to a picture without reading.

Why this matters: H3 does not take free text. It takes a structured description
where every reference is addressed as `<Picture 1>`, `<Video 2>`, `<Audio 1>`.
Writing `use @img-1 for her face` assigns those labels for you, in the exact order
the tokenizer expects.

### Trimming

Video and audio get a segment editor — on the picker cell or on the attached chip.
Scrub, drag the handles, or slide a fixed-length selection along the clip. The range
sits on the waveform, decoded in the browser, so you can see where the sound is
before you cut it.

![The segment editor](docs/img/video_and_audio_trim.png)

The three buttons underneath decide what a video reference contributes: **picture +
sound** brings its soundtrack in as a reference audio too, **picture only**
references it silently, and **sound only** throws the picture away — which is what
you want for a voice, a room tone, or scoring that happens to live in an mp4.

Reference *images* get a scope dial instead: `full · person · object · scene ·
style`. On `person`, "her from @img-1" stops dragging that image's background,
palette and pose along with the face.

The PreStage's style references are cited the same way. Writing `@ref-2` becomes
`Picture 2` — the label core's Qwen-edit encoder writes in front of that slot, so
it is the name the model is actually reading. Which slot a reference gets is the
payload's to decide, not yours to count.

## LoRAs

![The LoRA manager](docs/img/lora_picker.png)

A full-screen manager over `models/loras`. Cards carry the showcase image or clip,
the title, base model and trigger words read from whatever is sitting beside the
file; a LoRA nothing has described still gets a working card from its filename.
Each card sets a strength, which checkpoint it belongs to, and its trigger words.
Those words are prefixed to the prompt at compile time and printed under the LoRA
chips in the node body.

Metadata is read from whichever of these it finds, and merged — later entries only
fill in what earlier ones left blank, except for the trigger words and the strength,
where anything *you* wrote outranks anything a website said:

| Written by | Files read |
| --- | --- |
| CiviMeta | `{model}.safetensors.civitai/` — `meta.json`, `images.json`, `media/`, `thumbnails/` |
| ComfyUI-Lora-Manager | `{model}.metadata.json`, and its example-images folder if one is configured |
| Civitai Helper, CivitAI Browser+ | `{model}.civitai.info`, `{model}.api_info.json`, `{model}_0.jpg`… |
| A1111, Forge, and downstream | `{model}.json` (activation text, preferred weight), `{model}.txt`, `{model}.description.txt` |
| ComfyUI core, hayden-fr's manager, pysssss | `{model}.preview.{png,jpg,webp,mp4,webm,…}`, `{model}.{ext}`, `{model}.md` |
| The file itself | ModelSpec (`modelspec.title`, `.trigger_phrase`, `.thumbnail`) and kohya's embedded `ssmd_cover_images` |

Nothing is written back: every one of these is read-only, and a LoRA the pack cannot
identify is a card with a filename on it rather than an error. Double-clicking a card
opens the detail sheet — the showcase with the generation settings recorded for each
image, and, at the bottom, which of the files above each field was read from. **Rescan**
re-reads everything, which is what to press after editing a sidecar by hand.

**turbo** on the sampler row is a switch, not a preset: it adds a distillation LoRA
(larryvrh's `minimax_h3_turbo_v4_step600_ema`, the lightx2v 4-step distill, or
Kijai's conversions), moves the sampler to euler + beta, drops the steps to
4 / 6 / 8, and sets the two **shift** pills to the schedule the picked LoRA's
card was distilled against (the lightx2v distill runs the video clock at 6;
larryvrh's keeps the checkpoints' own 12/3). Switching it off puts all of it
back. The shift pills are ordinary controls the rest of the time — H3 samples
picture and sound on two flow clocks, and at the default 12/3 the graph carries
no shift node at all.

## Refine

`Refine` rewrites your sentence into the long, sectioned description H3 was actually
trained to read, using a small local vision model. The result lands in an editable
box under the prompt — correct it, switch it off without losing it, or revert.

It looks at your attached images, writes real dialogue lines instead of "she says
something", always writes a soundscape, keeps quoted words exactly, and picks how
many shots the clip holds and the second each one starts on.

It is a button rather than a queue-time step on purpose: you should see what the
model will read *before* five minutes of sampling, not infer it from the result.

## PreStage

![PreStage feeding a Creator](docs/img/pre-stage.png)

The pipeline eats stills — start frames, end frames, references, storyboards — and
making one usually means a second workflow, a second tab and a trip through the
output folder. The PreStage generates them on the same canvas, locally, with Krea 2,
Ideogram 4.0, or H3 itself.

Spawn it from the **pre-stage** pill; it lands at the left edge of the node it
belongs to. Its result card has chips that write the finished still straight into
the peer as a start frame, end frame or reference. The hand-off is by file, so one
Run does both and an untouched PreStage is a cache hit.

### Stills from H3 itself

Experimental, and the reason to bother: the other two are image models, so a
keyframe from them means loading a second model family and then matching a look
across an architecture boundary. Switch the model pill to **MiniMax H3** and the
still is made by the weights that will render the shot, on the canvas that shot
will run at.

It is a video generation with one frame kept. The node samples the shortest legal
clip, takes one temporal slice of the latent, and decodes it with an
image-specialised H3 VAE —
[MiniMax-H3-Image-VAE](https://huggingface.co/Mamad8/MiniMax-H3-Image-VAE) by
Mamad8 (`minimax_h3_t1_image_vae_*`) — whose decoder was
fine-tuned to turn a single temporal latent into a picture while its encoder was
left frozen. That is why one file does both jobs here: the encoder that reads your
references is still the stock H3 one, bit for bit.

The body is the shot editor's, because the request is a shot's — nine reference
images, three clips, three sounds, a start frame, an end frame, LoRAs, `@`
mentions, FL2VA/Ref2VA routing, the taeh3 preview. Two pills are its own:

| pill | what it does |
|---|---|
| `5f · 2 latent` | how much video is sampled to get the one frame. 5 is cheapest; H3's trained range starts at 124, so longer is more in-distribution and proportionally slower. |
| `latent 0` | which latent frame becomes the picture. 0 is the causal first frame — the one slice the decoder was fitted to. Negative counts from the end. |

Reconstruction is soft compared to a dedicated image model: fine text, thin
contours and hair are where it shows first. It is an experiment, marked as one in
the UI, and the video VAE is not a substitute for it in either direction.

## More than one shot

Past one shot the node's face becomes the piece at a glance: the global prompt,
the shots as a lane strictly proportional to their durations, and the numbers.
Each card is a whole generation — its own prompt, references and LoRAs, edited in
the same editor the single-shot face is.

![The node with a strip on it](docs/img/timeline-node.png)

**Edit timeline** opens the strip, which is where the work happens.

![The Timeline strip](docs/img/timeline.png)

**Chained** renders each segment and joins them; a segment can start from an
earlier segment's last frame and inherit a tail of its sound. The seam continues
from the previous segment by default, but from segment 3 on a *from* control under
the seam's two switches lets it name any earlier one — a story that returns to
segment 1's hallway after an unrelated segment 2 continues from segment 1, while
segment 2 stays a hard cut.

A continuing seam works in every mode, references included: a Ref2VA segment can
continue from another Ref2VA segment's last frame, with its `@` references intact.
The seam's width is adjustable too — the *last frame / blend* control widens it
from the classic single frame to a 5-, 22- or 39-frame blend. A blended seam pins
the source's last run as motion context, so the model reads real movement across
the cut instead of guessing it from a still, and the sound seam is then pinned
on the new segment's own timeline — continued phase-locked rather than imitated.
The overlap is re-generated at the segment's head and trimmed off after decode,
so a blended segment delivers up to 1.6 s less than its card says. **One pass**
compiles the
same cards into a *single* generation, since H3's prompt format is already a shot
list — nothing is decoded and re-encoded mid-clip, so there is no seam and music or
dialogue carries across a cut. **Refine all** rewrites every card in one call, which
is the only way a later shot keeps the look an earlier one established.

**Piece references** attach a file to the timeline itself — a character sheet, a
location plate, a voice — instead of once per segment it appears in. The shelf
above the strip hands out `@ref-N` handles, and the citation is the attachment:
write the handle in the **global prompt** (or click the handle on its chip) and
the reference rides into *every* segment; write it in one segment's prompt and it
rides into that segment alone. Uncited, it rides into none — so editing an
unrelated segment re-renders nothing extra. A globally cited reference cannot
share the strip with a start/end-frame segment (references and frames are
different checkpoints), and the compiler says so naming both. The `@` menu
inside every segment offers the pool under *Piece references*, the refiner is
shown it once and may cite it where the subject appears — globally included —
and a reference image can be narrowed (*person*, *object*, *scene*, *style*) so
a sheet contributes the likeness without its background. In one pass, all
citations of the same piece reference share a single `<Picture N>`.

While a chained piece renders, the preview overlay names the pass the sampler is
on — *Pass 3 of 5* — so a long strip's step count finally says where in the piece
you are. Cached segments are skipped, so the chip always names the segment
actually being made.

### Upgrading from the two-node version

Through 1.x the Creator and the Timeline were two nodes. As of 2.0 they are one
— a Creator render was always a one-segment timeline underneath, and the split
only ever lived in the UI.

Nothing to do, and nothing to migrate. Saved 1.x workflows keep working:

- A **Creator** node opens exactly as it did, on the shot you wrote. Its blob is
  read as the one-shot piece it always was.
- A **Timeline** node keeps its own id, which is deprecated rather than removed:
  it is gone from the node search, it still loads, and it mounts the same body.
  Only the title on the canvas differs. Copy the JSON into a fresh Creator and
  delete it if you would rather not keep one around.

The blob's shape is the timeline's either way — a global prompt, one canvas, one
set of weights and a list of segments — so the right-click **Copy creator_data
JSON** now hands you a piece rather than a lone request.

## Presets

A preset is a setup you can put back. **Presets** on the rail opens the library —
beside Gallery and Settings on a Creator, last on a PreStage's single group, and
in the right-click menu of all three node ids.

What it saves is the blob *and the sampler row*, because the row was never in the
blob: `steps`, `cfg`, the sampler, the scheduler, the two flow shifts and the
cache pill are stock widgets the node hides and redraws as pills. A preset holding
only `creator_data` would drop the turbo schedule and the step count, which is
most of what anyone actually tunes.

Three things can be saved, and each knows which of them it is:

| scope | saved from | holds |
|---|---|---|
| **piece** | a Creator, whatever is on its face | canvas, weights, the sampler row, the writing, LoRAs, the reference pool, the strip |
| **shot** | one card off a strip | its writing, its references and LoRAs, the row it was dialled at, and how long it runs with the seam in front of it |
| **prestage** | a PreStage | its architecture, canvas and quality, the writing, references and LoRAs, and the weights for the architecture it runs |

Applying is per-section rather than all-or-nothing, which is the point: tick
*look* and *speed* to drop a canvas and a step count onto a shot you have already
written, and the prose stays where it is. A section that cannot cross into the
target is shown with the reason on it instead of hidden — *Weights: this PreStage
runs Krea 2, and these are H3 checkpoints* is information, and a missing row is a
bug report.

Two fields are never captured. The **seed** is the one number that has to be
different next time, and the **output prefix** is a per-machine preference the
[folders page](#where-files-go) already draws a line around. Applying runs the
same normalisers the editor does, so a preset cannot put a node into a state you
could not have built by hand: seams the restored durations can no longer afford
are pruned, a checkpoint pin the restored references make illegal is dropped, and
a piece's nine reference images are cut to the three slots Krea 2's edit path has.
Ctrl+Z is the undo. A preset naming a LoRA or a checkpoint this machine does not
have applies anyway and the affected chips render as missing, which is what a
workflow from someone else's disk already does.

### Taken from a render

By the time you know which render was the good one, you have usually moved on —
three prompts later, a different LoRA, the strip rebuilt. The setup is not gone,
though. Both save nodes embed the workflow that made the file, the MP4 in its
container tags and the PNG in its text chunks, so **From a render** opens the
gallery and the file you pick becomes a preset. Nothing is stored for this; it was
in the files all along.

It reads the API-form `prompt` tag and never the canvas `workflow` tag, because
that one is keyed by name. `workflow` holds `widgets_values`, which is
*positional*, and this pack has already changed the length of that row once when
the two flow shifts arrived — a render from before that carries nine entries where
the node now declares eleven, and everything after the gap reads one slot out with
no error anywhere. A file saved under `--disable-metadata` carries neither tag,
and the library says which of those it is rather than failing.

### The card

The hero of a card is the render the preset was saved from. The stage is already
holding it when you press save, so the cover is the thing you were looking at when
you decided you liked it — nothing to guess and no best frame to pick. It fills an
empty cover only, because a card you recognise must not change under you; **Set**
and **Change** open the same gallery for one chosen by hand, and **Clear** puts the
card back on the lane.

With no cover the card draws the piece itself: the lane at its real proportions,
merged shots closed up under one casing, seams between them, and the blocks filled
with the thumbnails of whatever the preset names. With neither, the flat lane. The
library stars, shelves and searches the way the picker does.

Seven starters ship with the pack — a native 20-step row and a 4-step draft row, a
9:16 canvas, a feathered continuation and a hard cut, and a poster and a character
sheet for the two image architectures. They are the same for everybody, so they
cannot be renamed or deleted: apply one, change what you want and press **Save
current setup** to get one that is yours.

Presets live in ComfyUI's user data next to the picker's favourites, as one index
plus a file per preset. That means they follow the user rather than the workflow,
which is why **Export** and **Import** hand the library — or one card — over as
JSON when you move to another machine.

## Modes and duration

What you attach picks the mode, and the mode picks the checkpoint — only that one is
loaded:

| attached | mode | checkpoint |
|---|---|---|
| nothing | T2VA | FL2VA |
| start and/or end frame | I2VA / L2VA / FL2VA | FL2VA |
| any reference image/video/audio | REF2VA | Ref2VA |

Frames and references cannot be combined. Clicking the mode badge forces everything
onto one checkpoint instead, which is worth it because Ref2VA handles text and
keyframes fine and one checkpoint can then cover a whole timeline.

Frame counts must satisfy `n % 17 == 5` at 24 fps, so there is no 6.00-second H3
video. The pill shows whole seconds and the compiler lands on the nearest legal
count:

| shown | 5 | 6 | 7 | 8 | 9 | 10 | 12 | 15 |
|---|---|---|---|---|---|---|---|---|
| frames | 124 | 141 | 175 | 192 | 209 | 243 | 294 | 362 |
| real | 5.17 | 5.88 | 7.29 | 8.00 | 8.71 | 10.13 | 12.25 | 15.08 |

The resolution slider sets the **short edge** (384–2048, native 768); both axes snap
to 32. In the image modes the aspect comes from the keyframe.

Past 768 the popover offers a choice, because the open weights were trained at a
768 px short edge and going above it directly is off-distribution. **Two passes**
(the default) samples at the first-pass canvas — native, unless the `sampled at`
stepper lowers it — then a second pass interpolates the video latent up to the
slider's size, re-noises it partway down the schedule (the `refine` stepper,
default 0.50) and samples again — against conditioning rebuilt at the target
size, so keyframes and references are re-encoded to match. The soundtrack is
never re-noised: the sound you got from the first pass is the sound in the
file. **Direct** is the old behaviour, one pass at the slider's size, warning
and all. At or under 768 there is no warning to answer, but the `sampled at`
stepper is still there: lowering it under the slider buys the first pass's
speed at any size — sample at 512, refine up to 768 — and is itself the
two-pass opt-in.

## Where files go

Renders are saved by the node itself, under ComfyUI's output folder. **Settings →
Folders** sets where — one answer per machine, for every node in the pack:

| | default | lands in |
|---|---|---|
| Creator | `minimax/renders/H3` | `output/minimax/renders/H3_00001_.mp4` |
| PreStage | `minimax/stills/prestage` | `output/minimax/stills/prestage_00001_.png` |

The last segment names the **files**, not a folder: `client-a/hero` writes
`hero_00001_.mp4` into `output/client-a/`. Ending with a slash keeps the default
filename, so `client-a/` is usually what you want.

`%year%`, `%month%`, `%day%`, `%hour%`, `%minute%`, `%second%`, `%width%` and
`%height%` are filled in as each file is written, in a folder as readily as in a
filename — `minimax/%year%-%month%-%day%/H3` gives you a folder per day. There is
a button per token, and the field shows the exact path the next file will take.

These are preferences of this ComfyUI, not of the workflow: a `.json` shared with
someone else writes into *their* folders rather than carrying yours onto their
disk. A hand-edited blob may still set `output_prefix` for one node, which wins
over the setting — that is the only way to have two nodes write to different
places.

### Output quality

**Settings** in the rail opens the page for preferences that belong to this
ComfyUI rather than to a workflow. The first of them is what the encoder is
allowed to throw away when it writes an `.mp4`:

| | crf | |
|---|---|---|
| Draft | 28 | About half the size of Standard. Banding in dark gradients. |
| **Standard** | **23** | libx264's own default — what this pack wrote before the setting existed. |
| Fine | 18 | About twice the size of Standard. |
| Archival | 14 | About three times. Keeps grain and fine texture H.264 eats first. |

CRF is libx264's quality target: lower is better and larger, and six points is
roughly double the file. The container is unchanged either way — MP4, H.264,
8-bit 4:2:0.

This is **not** saved into the workflow. A `.json` shared with someone else makes
the same shot at whatever quality their ComfyUI is set to, which is the same
split as the folder pill above: where a file lands is part of the piece, how many
megabytes it takes is not. The value lives in `user/minimax_creator.settings.json`
and applies to every video the Creator writes. PreStage stills are PNG and have
nothing to set.

Needs ComfyUI 0.29 or newer, which is where `crf` reached core's video writer.
On an older build anything but Standard is refused at save time rather than
quietly written at the default.

### Moving the input and output folders themselves

The pill is relative to ComfyUI's output folder and cannot climb out of it. To
move the folders themselves, use ComfyUI's own flags — this pack reads every path
through `folder_paths`, so they work here with nothing to configure:

```bash
python main.py --input-directory /Volumes/Media/comfy-in \
               --output-directory /Volumes/Media/comfy-out
# or --base-directory to move input, output, temp, user and models together
```

Two things worth knowing:

- `extra_model_paths.yaml` **cannot** do this. It only adds model search paths;
  input and output are not model folders.
- **Symlinking a folder into `input/` does not work**, and the picker will not
  list files that resolve outside the folder they appear in. ComfyUI resolves
  symlinks before checking that a path stays inside the input directory, and that
  check is what stops a crafted filename reaching the rest of your disk — so it is
  not something this pack works around. Use `--input-directory` instead.

## Language

The UI speaks English, 日本語, 한국어 and 简体中文. There is no language picker in
the pack: it follows ComfyUI's own — **Settings → Comfy → Locale** — so the nodes
and the app around them always agree. Traditional Chinese falls back to
Simplified until someone contributes it.

Every string the UI shows goes through one gate (`js/minimax_creator/i18n.js`),
keyed by the English sentence itself. A key with no translation shows the
English, so a half-finished dictionary degrades to the UI this pack always had
rather than to bare token names. The dictionaries live in
`js/minimax_creator/locales/` as plain English → translation pairs a native
speaker can review without the source open — corrections are one-line edits, and
pull requests for them (or for new languages) are welcome. Node names and
descriptions in ComfyUI's own library and search are translated separately, in
`locales/<lang>/nodeDefs.json` at the pack root, which core merges by itself.

The translations are machine-drafted against a fixed glossary. The short labels
are safe; the long tooltips would profit from a native speaker's pass.

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
  live preview a real decoder. Kijai's turbo conversions are in the switch too.
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
- **[taehv](https://github.com/madebyollin/taehv)** by madebyollin — the tiny decoder
  that makes the preview look like the video.
- **larryvrh** and **lightx2v** — the H3 distillation LoRAs behind turbo.
- **CiviMeta** — the sidecar format the LoRA cards read.

All four packs are optional and none of them is required. If they are installed, the
matching pills light up.

## Tests

```
python3 tests/test_compile.py         # canvas math, modes, limits, ordering
python3 tests/test_refine.py
python3 tests/test_assets.py          # what the picker's listing walk finds
python3 tests/test_outputs.py         # what an output prefix may be
python3 tests/test_settings.py        # what the settings file may hold, and that a save is a patch
python3 tests/test_presets.py         # capture, apply per section, and what never crosses
python3 tests/test_canvas_mirror.py   # canvas.js against canvas.py
python3 tests/test_piece_mirror.py    # an old creator_data blob lifts to one shot
python3 tests/test_prestage_mirror.py
python3 tests/test_outputs_mirror.py  # outputs.js against outputs.py
python3 tests/test_js_bodies.py       # the frontend loads and every node body mounts
```

Those need neither torch nor ComfyUI (the mirror tests need `node`). The graph tests do, and skip themselves with a
message when it is not importable:

```
COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_creator_graph.py
```

Set `COMFYUI_BASE` as well when `--base-directory` points somewhere else — on a
Desktop install the running tree and the folder holding `custom_nodes`, `models` and
`output` are usually two different places.

The design decisions, in full, are in [PLAN.md](PLAN.md).

## License

[MIT](LICENSE). ComfyUI itself is GPL-3.0 and this pack imports it; if you
redistribute the two together rather than as a node pack people install themselves,
that combination is what the GPL has an opinion about.

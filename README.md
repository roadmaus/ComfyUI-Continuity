# MiniMax H3 Creator

Write a sentence, attach your media with `@`, press Run. One node holds the whole
generation and hands back a finished clip with its sound already in it — no
conditioning sockets, no sampler to re-assemble, no VAE to remember to connect.

Write a second shot on it and the same node is a timeline.

Local open weights only, through core's `comfy_extras/nodes_minimax_h3.py`. No API
key, nothing uploaded.

![Sampling, then the finished clip playing beside the node](docs/img/preview.gif)

Release notes live in [CHANGELOG.md](CHANGELOG.md).

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

Every reference also gets a scope dial. An image's reads `full · person · object ·
scene · style`; on `person`, "her from @img-1" stops dragging that image's
background, palette and pose along with the face.

A clip's dial takes the same four and four more, which are the roles H3's
reference guide gives a video: `motion` lends the action alone and carries it
onto whoever the prompt puts in the shot, `camera` lends the move, the cuts and
the pacing with nothing in the clip appearing, `edit` says the clip *is* the
video being edited — which is how you replace a subject and keep the rest — and
`continue` picks the video up where the clip ends. Each one is a different label
in the rewrite: the content takes and `motion` mine the clip for a `<Subject N>`,
while `camera`, `edit` and `continue` are the whole-video relationships
`<Video N>` is reserved for. The dial is on the chip, next to the trim.

An audio reference's dial reads `full · voice · music · ambience · copy`, which
are the roles the guide gives an `<Audio N>`. `voice` carries a timbre and a
delivery onto whoever speaks without carrying the words, `music` and `ambience`
reference a style or a room without reusing the recording, and `copy` says the
signal itself becomes the video's audio. A clip you set to **sound only** scopes
here rather than with the pictures — it is an audio reference that happens to
have arrived in an mp4.

None of this reaches the DiT as a switch: H3 has no reference-conditioning
input, so every one of these distinctions is prose or it is nothing. Refine
reads the dial and writes that prose for you. If you queue without refining,
turn on **Reference scopes in the prompt** under Settings → Nodes and the
compiler writes it instead — one sentence per reference in front of the
description, shown in the prompt box above your own text so you can read what is
being sent. It steps aside for a refined reference form, which says the same
thing better and in the model's own sections.

The PreStage's style references are cited the same way. Writing `@ref-2` becomes
`Picture 2` — the label core's Qwen-edit encoder writes in front of that slot, so
it is the name the model is actually reading. Which slot a reference gets is the
payload's to decide, not yours to count.

## The cast

A reference is a file. A *subject* is who is in the video, and H3 keeps the two
apart: `<Picture 1>` is a picture the tokenizer is shown, `<Subject 1>` is a
person, an object, a place or a look that the target video actually contains.
The reference guide is blunt about which of the two a character is — an image
used only to define somebody gets no picture entry of its own; it is cited
*inside* that subject's definition.

So people are cast, not attached. **Cast** is on the rail beside Add image; the
same shelf is in the Timeline window, under the piece references. Press it, give
the subject a name, and hang files on her.

Each file behind her is a thumbnail on her card, badged with what it lends her.
Click a thumbnail to change that, or to take it off; click the dashed tile to
hang another one on, picking from what is attached or attaching something new.

- **Several pictures, one person.** Four angles of the same face are one subject,
  not four references that happen to rhyme. Files that give her looks wear no
  badge — they are the common case; the badges mark the three departures from it.
- **A face from a still, a walk from a clip.** Set one file to *she moves like
  this* and the definition says her appearance comes from the pictures and her
  motion from the clip.
- **A voice.** *This is her voice* binds an audio reference as her voice timbre
  and gives her a speaker ID. IDs run in cast order, so the first speaker is the
  one at the top of the shelf.
- **Swapping a person for a person.** *She takes somebody's place in this* names
  a reference clip, and the box under it says who — "the man at the counter". The
  clip's framing, camera work and action are kept; its occupant is replaced by
  her. That is the whole gesture, and the one the guide spells as the
  `transferred` marker.
- **Nothing behind her at all.** A name and a description is a subject too, and
  it is the useful one in a prompt with no references in it: it is what keeps
  her the same woman in shot 1 and in shot 9. Her description becomes her whole
  definition.

Then you write with her. `@anna walks in and looks at @ben` — the same `@` chip
everything else uses, in the same menu, under **Cast**. Citing a subject is what
carries her files into that shot, exactly as citing a piece reference carries
that file: a shot that never names her does not pay for her pictures.

A name is only a name because you declared it. `@anna` in a piece where nobody
cast Anna is ordinary prose and stays that way — nothing you have already written
changes meaning because this shelf exists.

A subject nobody has written into a prompt is in no shot, and her card says so —
click that and it writes her name in for you.

What it produces is the part of the form that could not be written before. At
queue time the compiler emits `subject_definitions` and `retention_analysis` in
the guide's own shapes, in the reference form and in the plain modes alike — so a
`<Subject 1>` is always defined wherever it is written. Every subject is defined
once and its fate marked `fully_preserved`, `partially_preserved`, `transferred`
or `reused`, with the shots she appears in read off the description. Refine is
handed the cast as pinned fact: it writes the film around your subjects and is told not to define or
renumber them.

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

## Faces

H3 draws a face badly in proportion to how small the head is **in frame**. It is
not a resolution problem — it is there at 768 and above — so no upscaler reaches
it: an upscaler re-resolves what was drawn, and what was drawn was a smudge.

The **faces** pill on the sampler row switches on a second, small generation per
pass. After a pass is rendered, its face is tracked frame by frame, cropped out
so it fills a 512 px canvas, re-drawn by H3 itself at a low denoise — low enough
that it stays frame-aligned and keeps the lipsync the soundtrack already has —
and composited back under a feathered mask. Only the face box is pasted; the
wider crop is context for the sampler, not content for the composite.

Two knobs, both in the pill's popover:

- **crop at** — the canvas each crop is generated at. 512 by default; the face
  fills it either way, so most of what a larger one buys is the hair around it.
- **redraw** — how much of the schedule the crop re-runs. This is a *ceiling*:
  it is scaled down frame by frame by how large the face already is, so a shot
  where somebody walks towards the camera is synthesised where the head is tiny
  and barely touched by the time it is close.

On a timeline every card carries a small **face** chip while the pass is on;
click it to leave that shot alone. The two knobs stay the piece's — one render
has one answer for how the pass works, and what a card says is whether this shot
needs it.

It needs a **SAM3 checkpoint** in `models/checkpoints`, picked in the weights
control. SAM3 ships with ComfyUI core, so there is nothing to install — it is
open-vocabulary, so it is simply asked for "face", and it tracks, which is what
keeps a crop on one person when two are in shot. Nothing else is needed: no
ultralytics, no insightface, no segmentation pack.

What it costs: one extra generation per pass, at a quarter of a 768 pass's
pixels, plus loading the detector between passes. Frames where no face is found
are left exactly as they rendered, and a pass with no face in it at all is left
alone and says so in the log.

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
unrelated segment re-renders nothing extra. A cited reference rides into a
start/end-frame segment like any other: the segment becomes a Ref2VA
generation and its frames ride as pinned guides. The `@` menu
inside every segment offers the pool under *Piece references*, the refiner is
shown it once and may cite it where the subject appears — globally included —
and a reference can be narrowed (*person*, *object*, *scene*, *style*, for a clip
*motion*, *camera*, *edit*, *continue*, and for a sound *voice*, *music*,
*ambience*, *copy*) so a sheet contributes the likeness without its background.
In one pass, all citations of the same piece reference share a single
`<Picture N>`.

While a chained piece renders, the preview overlay names the pass the sampler is
on — *Pass 3 of 5* — so a long strip's step count finally says where in the piece
you are. Cached segments are skipped, so the chip always names the segment
actually being made.

### Shooting a piece a pass at a time

A long strip does not have to be rendered all at once. Every card carries a
padlock, at the right of its head: **unlocked** is in the next render, **locked**
is not. Write all three segments, lock the last two, render — you get segment 1
alone. Look at it. If it is wrong, render again; if it is right, lock segment 1
too and unlock segment 2, and the next render generates segment 2 continuing
from the file segment 1 already made, without sampling segment 1 again.

Nothing on a locked card is lost: its prompt, references, LoRAs, seam and length
are all still set and still editable, it is simply not generated. What the card
*looks* like says what the lock is holding — solid because the film already
exists, perforated because it has not been shot yet — and the chip in its meta
row names it, **kept** or **not shot**. The bar says what the next queue will
cost: *6.0 s next*, against the piece's full length.

Every render of more than one pass writes each pass as its own file under
`takes/`, next to the finished video, and hands it back to the card that made
it. A card carrying one shows **take ready** until you rule on it. Locking the
card is what keeps that take; leaving it unlocked is what shoots it again. Edit
a card whose take is kept and it says **kept · edited** — the take still plays,
but it is no longer what the card describes.

A lock belongs to a *pass*, not a card: a merged run is one generation and one
file, so it locks, keeps and draws as one piece of film, with its padlock on the
pass rail. A strip where every card is locked and kept is not an error — it
queues the piece written out of the takes it already has, at no sampling cost at
all.

**A card may also carry its own seed**, on the seed pill in its editor. Absent —
which is every card until you roll one there — it runs on the number on the
node, and the piece stays one look under one handle. It is retaking that needs
the exception: re-rolling the node's seed to shoot segment 2 again would move
the number that made the take already locked in on segment 1, so a take's seed
is a fact about the take. The pill says which of the two is in force, and names the
seed the card's take was made on.

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

### The style atlas

A fourth tab, and the only one that is a catalogue rather than a shelf of your
own work. It holds **941 looks** indexed from
[ostris/minimax_h3_1k](https://huggingface.co/datasets/ostris/minimax_h3_1k) — a
thousand H3 clips with detailed captions — by
[hoodtronik's Style Atlas](https://github.com/hoodtronik/minimax-h3-style-atlas),
grouped into eight media categories with a still off every clip.

What makes them worth having is that they are not adjectives somebody thought of.
They are the exact strings this model was captioned with, in the position the
caption puts them: *Claymation with visible fingerprint texture and gently
stuttering stop-motion movement* is not a description of claymation, it is a
phrase H3 has seen a thousand frames of.

Applying one **swaps the lead** rather than replacing the prompt. The descriptor
goes in front, and where the prompt already opens with a descriptor from the
atlas, that one comes out — so trying six looks on the same shot gives you six
prompts rather than six stacked paragraphs:

```
The cat knocks a mug off the table, and it shatters.
  → Claymation with visible fingerprint texture …, the cat knocks a mug off …
  → LEGO brickfilm stop motion with bright plastic sheen …, the cat knocks a mug …
```

Nothing else moves — not the canvas, the strip, the weights, or a card that was
already written — and it lands on a piece, a card or a PreStage alike.

The atlas is **vendored**: the index and one still per clip, about 5 MB, sitting
in the pack. No video, nothing downloaded and nothing streamed from Hugging Face,
so the tab works with the network off and costs the dataset's author nothing. The
module is fetched the first time you open the tab, never at boot.

Some descriptors run past the look into the setting the clip happened to have —
upstream reads the *opening* of a caption and H3's captions fuse the two. That is
not trimmed, because trimming means guessing where a look stops being a look. The
whole descriptor is in the inspector before you press Apply, and what lands is a
prompt sitting in the editor, ready to be cut.

Updating the copy is one script: `python3 tools/vendor_style_atlas.py <clone>`
rewrites the index, drops stills for clips upstream removed, and stamps the
revision it was taken from. Details in
[docs/DESIGN-style-atlas.md](docs/DESIGN-style-atlas.md).

## Modes and duration

What you attach picks the mode, and the mode picks the checkpoint — only that one is
loaded:

| attached | mode | checkpoint |
|---|---|---|
| nothing | T2VA | FL2VA |
| start and/or end frame | I2VA / L2VA / FL2VA | FL2VA |
| any reference image/video/audio | REF2VA | Ref2VA |
| frames *and* references | REF2VA | Ref2VA |

Frames and references combine: the frames ride as guides pinned at the clip's
first and last frame — the same mechanism a timeline seam has always used — and
the generation runs on Ref2VA, whose training reads keyframes alongside its
references. Clicking the mode badge forces everything onto one checkpoint
instead — in either direction, since the slots name what you loaded into them
and merges of the two checkpoints exist — which is worth it because one
checkpoint can then cover a whole timeline.

Frame counts must satisfy `n % 17 == 5` at 24 fps, so there is no 6.00-second H3
video. The pill shows whole seconds and the compiler lands on the nearest legal
count:

| shown | 5 | 6 | 7 | 8 | 9 | 10 | 12 | 15 |
|---|---|---|---|---|---|---|---|---|
| frames | 124 | 141 | 175 | 192 | 209 | 243 | 294 | 362 |
| real | 5.17 | 5.88 | 7.29 | 8.00 | 8.71 | 10.13 | 12.25 | 15.08 |

The resolution slider sets the **short edge** (384–2048, native 768); both axes snap
to 32. By default the aspect comes from the start frame when there is one, then
from supplied footage, then from the ratio pill — but the pill's popover lets
you take it from *any* attached picture instead: a start or end frame, a
reference image or video, a clip card's footage, or a pool reference, with the
presets available to force over all of them.

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

The page's **Nodes** tab holds three more. *Preview playback*, the only one on
by default, decides whether the stage plays a clip the moment it has one — set
it to *Waits for play* and a finished render holds its first frame, still, with
the browser's controls to start it, which spares a crowded canvas a decoder per
looping clip. *Flow shift pills* decides whether the sampler row offers H3's
two schedule clocks — a control over who has to look at them, not over what is
sampled. *Reference scopes in the prompt* is the one setting on the page that
changes what is queued: on, the compiler writes each reference's scope into the
prompt as prose, and the prompt box shows it above your own text. Worth knowing
before you share a workflow — someone whose copy is set the other way renders
the other prose.

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
  live preview a real decoder, and the `sage` pill: H3's own attention run
  quantized, which is faster and, unlike the caches, wants *less* VRAM rather
  than trading fidelity for steps. It needs the
  [sageattention](https://github.com/thu-ml/SageAttention) package and an NVIDIA
  card; it composes with everything else on the row. Kijai's turbo conversions
  are in the switch too.
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
- **larryvrh** and **lightx2v** — the H3 distillation LoRAs behind turbo.
- **CiviMeta** — the sidecar format the LoRA cards read.

All four packs are optional and none of them is required. If they are installed, the
matching pills light up.

## Tests

```
python3 tests/test_compile.py         # canvas math, modes, limits, ordering
python3 tests/test_faces.py           # face windows, crops, and the piece/shot switch
python3 tests/test_refine.py
python3 tests/test_subjects.py       # the cast: citation, labels, and the two sections it writes
python3 tests/test_assets.py          # what the picker's listing walk finds
python3 tests/test_outputs.py         # what an output prefix may be
python3 tests/test_settings.py        # what the settings file may hold, and that a save is a patch
python3 tests/test_presets.py         # capture, apply per section, and what never crosses
python3 tests/test_style_atlas.py     # the vendored atlas is whole, and a style leads the prompt
python3 tests/test_canvas_mirror.py   # canvas.js against canvas.py
python3 tests/test_piece_mirror.py    # an old creator_data blob lifts to one shot
python3 tests/test_prestage_mirror.py
python3 tests/test_cast_mirror.py     # state.js against subjects.py
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

The design decisions, in full, are in [docs/PLAN.md](docs/PLAN.md).

## License

[MIT](LICENSE). ComfyUI itself is GPL-3.0 and this pack imports it; if you
redistribute the two together rather than as a node pack people install themselves,
that combination is what the GPL has an opinion about.

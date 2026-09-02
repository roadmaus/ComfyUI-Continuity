# The node

![The node in the simple view](img/simple.png)

Everything is on one node. From top to bottom:

- **The rail**: buttons for attaching images, video, audio and LoRAs, plus the
  cast, presets, the gallery and settings.
- **The prompt box**: your prompt, with attached files cited by `@` name.
- **The pills**: duration, aspect, resolution and the sampler row. The model
  pill says which family and checkpoint this render lands on.
- **Render**.

Drop the node, type, press Render. That is the whole workflow.

## Attaching files

Type `@` anywhere in the prompt. The menu lists what is already attached
first, then the cast, the cast library, piece references and your input
folder. Picking a file that isn't attached yet attaches it.

The rail buttons open the same library as a full picker: a tab per kind,
search, shelves, favourites and upload, plus a **Renders** tab over your
output folder, so a clip you just made can go straight back in as a reference.

A shelf is a folder on disk and nothing else. The "+" makes the directory,
dragging a thumbnail onto a chip moves the file into it, and the row shows what
is actually there, so a folder you delete from a terminal is gone from the
picker on the next listing. An empty one you made by mistake has a *Remove
shelf* at the end of the row; a folder with anything in it is a file manager's
job.

![Two references cited in a prompt](img/mentions.png)

Every attachment gets a colour, and its chip in the sentence wears the same
one. Citing a file by name in the prompt matters: the models here don't take
free text plus a pile of images, they take structured prompts where each
reference is addressed, and writing `use @img-1 for their face` is what lets
the compiler build that structure for you.

### Scope: what a reference contributes

Each reference chip has a scope dial that narrows what the file is for:

| Kind | Scopes |
|---|---|
| Image | `full`, `person`, `object`, `scene`, `style`, `action` |
| Video | the image scopes, plus `camera`, `edit`, `continue` |
| Audio | `full`, `voice`, `music`, `ambience`, `copy` |

On `person`, "them from @img-1" stops dragging that image's background,
palette and pose along with the face. `action` is the opposite cut: the
action alone, carried onto whoever the prompt puts in the shot - a clip lends
the whole movement, a still lends its pose. On a clip, `camera` borrows the
camera move without the people in it, `edit` means "change something in this
footage", and `continue` picks up where the clip ends.

### Trimming, and picture vs sound

Video and audio chips open a segment editor: scrub, drag the handles, or
slide a fixed-length selection along the waveform. Three buttons decide what a
video contributes: picture and sound, picture only, or sound only. A clip
attached for its sound alone scopes with the audio dial, since there is no
picture left to narrow.

### Cutouts

Press the scissors on a reference picture and the subject is lifted off its
background, so citing a portrait for a face stops also citing the room. This
runs in the picker, not in a render. With only BiRefNet installed it grabs the
most prominent subject automatically; with SAM 3 you can click the subject you
mean, and click again on what you don't. Files for both are in
[models.md](models.md#cutouts-and-the-faces-pass).

## The cast

A reference is a file. A subject is who is in the video, and the two are kept
apart. People are **cast**, not attached: press Cast on the rail, name them,
and hang files on them - a face from a few stills, a walk from a clip, a voice
from an mp3, or footage they take somebody's place in.

Then write with them: `@anna walks in and looks at @ben`. Citing a subject
carries their files into that shot, so a shot that never names them doesn't
pay for their pictures. A name and a description with no files behind it is a
valid subject too, and it is what keeps a character consistent from shot 1 to
shot 9.

Hanging a file on a cast member sets its scope dial for you.

Each file on a member has its own menu, from its tile. At its head is a line
for what the file shows of them - "her face, front-lit", "the green coat",
"the golf swing" - which is written after that file's label in the subject
definition, so the model knows which picture is which and what the clip is
of. Under the roles is the size the file is encoded at, `match` or `max`, the
same choice the reference card offers, and it is kept with the member: a
member taken out of the cast library comes back with each picture at the size
it was kept at. A tile wears a small `max` when it is encoded at full detail
and a dot when words are attached to it.

To have somebody perform an action the way another person does it, hang the
clip or still of that person on them as "their action comes from this", and
say what the action is on the tile. (The blob and the prompt keep the guide's
own word for it, `motion`.) The definition then reads "whose appearance comes
from Picture 1 and whose motion comes from Video 1 (the golf swing)", and the
retention line says the movement is followed.

A cast member can be swapped for another from the card's swap button: the
replacement takes over their clips, their slot in the cast order, and every
sentence that named the old name is rewritten to the new one. Removing a
member removes only what they were built out of (their pictures, voice,
movement clips); footage they were cast into stays attached.

## Spoken lines

Close a quote in the prompt and a small menu opens:

- **Spoken** turns the words into an actual line of dialogue, in the exact
  form H3 was trained to voice. You pick who says it (from the cast, or a
  description typed on the spot), in which language, and how: says, asks,
  replies, whispers, shouts, sings, or an off-screen voiceover.
- **Written in the picture** leaves the quotes alone, because plain double
  quotes are already how you ask for a sign, a banner or a subtitle.

A spoken line is drawn with a rule down its left edge in the speaker's colour
(dashed for a voiceover). Press it to edit the words, the speaker, the
language or the delivery, or to turn it back into on-screen text.

## Refine

The **Refine** button rewrites your sentence into the long, structured
description the target family was trained on, and puts the result in an
editable box under the prompt. It is a button rather than a queue-time step so
you see what the model will read before minutes of sampling. Everything you
named survives the rewrite; quoted words are checked mechanically and carried
through verbatim.

Two ways to run it, chosen in the refiner's settings:

- **This ComfyUI**: a small Qwen3-VL text encoder loaded in-process, evicted
  like any other model when the sampler needs the VRAM. See
  [models.md](models.md#the-refine-button) for the file.
- **A server**: any OpenAI-compatible endpoint - LM Studio, Ollama, llama.cpp,
  vLLM, or a hosted API with a key. The key is stored server-side on your
  machine, never in the browser or a workflow file. "Eject when done" asks a
  local server to unload the model as soon as the rewrite is in, so the
  sampler gets the memory back.

### Your own prompting

Put a `.md` file in the node's `creator/skills/` folder and the refiner's
settings offer it by name, either added to the built-in prompting or replacing
it outright. A file can pick its mode in its own frontmatter (`mode:
replace`). Agent skill packages (`.skill`) go in the same folder.

## The pre-stage

The pipeline eats stills: start frames, end frames, references. The
**pre-stage** pill spawns a second card that generates them on the same
canvas, with any of the stills families (Krea 2, Ideogram 4.0, Qwen Image
Edit, Flux 2 Klein) or H3 itself. Its result card writes the finished still
straight into the shot as a start frame, end frame or reference, or back into
the pre-stage as the next edit's subject. With an edit model, `edit` on the
result is one press, and editing the edit is most of what an edit model is
for.

One Queue runs both cards; an untouched pre-stage is a cache hit and doesn't
re-render.

## Sampler row extras

- **Turbo** engages the family's distillation (a LoRA on H3 and Qwen Image
  Edit, a checkpoint swap on Krea 2 and Flux 2 Klein) and presets the sampler
  row. Releasing it restores your row exactly.
- **Faces** runs a second small generation per pass: each face is tracked,
  cropped, re-drawn at 512 px and pasted back under a feathered mask. Needs
  the SAM 3 checkpoint.
- Accelerator pills (caches, sage attention, low vram, and so on) appear when
  the matching optional pack is installed. All caches trade fidelity for
  speed, so A/B against a native render before trusting one on a final piece.

## Sampling on two GPUs

H3 can sample one shot across several cards, which on a pair is roughly half
the wall clock. Install the [Raylight community
fork](https://github.com/Karmabu/raylight), since the upstream Raylight has no
H3 path, and a **Sampling** row appears at the top of the weights popover. Pick
`Raylight · 2 GPUs` and queue as usual: the checkpoint is loaded into one Ray
worker per card and the sequence is split across them, while the prompt is
still encoded and the video still decoded on your own card. Preview frames keep
working if you have KJNodes and `taeh3.safetensors`.

It carries the first sampling pass and nothing else. These are **refused before
the queue starts**, with a message saying what to switch off, rather than
quietly dropped from the render:

- the refine (two-pass upscale), faces and re-detail passes,
- the turbo lead-in,
- sound seams, meaning a shot continuing the previous one's soundtrack,
- ControlNet guides: they reach H3 through the conditioning, so they would
  arrive intact and then be ignored by Raylight's own forward pass,
- every accelerator except sage attention, which Raylight runs itself,
- device pins from ComfyUI-MultiGPU: the Ray workers want the cards,
- a strip that routes to both checkpoints. Force the route to Ref2VA; it takes
  everything FL2VA does.

One thing changes without being refused: LoRAs are merged inside the workers by
ComfyUI's own loader instead of this pack's H3 stack, which is worse on
quantized checkpoints. Picture seams, the sigma shift, GGUF checkpoints and
everything the compiler does are unaffected.

The pre-stage's stills always sample on one card. Starting a Ray cluster to make
one frame costs far more than it saves.

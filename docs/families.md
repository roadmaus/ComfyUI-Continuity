# Model families

A family is a model architecture and everything this pack knows about talking
to it: which checkpoints it routes between, how your prompt reaches its
encoder, what a reference means to it, how a LoRA gets in. The node is the
same node on all of them; the model pill picks which one a render lands on.

| Family | Makes | References |
|---|---|---|
| MiniMax H3 | video with sound, and stills | each encoded on its own, addressed in a structured prompt |
| LTX 2.5 | video with sound | up to nine stills, composited into one reference sheet |
| Krea 2 | stills | up to three |
| Ideogram 4.0 | stills | none, prose only |
| Qwen Image Edit | stills | up to three; click the first to edit it in place |
| Flux 2 Klein | stills | up to three; click the first to edit it in place |
| Qwen Image 2.1 | stills | up to ten; click the first to edit it in place |

Every render files into a folder named after its family
(`output/continuity/renders/ltx25/`, `output/continuity/stills/krea2/`) and
carries the family name on the file.

## MiniMax H3

Video with synchronized sound, and stills on the pre-stage.

- **Two checkpoints, routed for you.** Nothing attached runs text-to-video,
  frames run FL2VA, references run Ref2VA, and frames plus references run
  Ref2VA with the frames pinned as guides. A badge on the node says which;
  clicking it forces one checkpoint.
- **Duration is a grid.** H3's frame count must satisfy `n % 17 == 5` at 24
  fps, so there is no exact 6.00-second H3 video. The pill shows whole seconds
  and the compiler lands on the nearest legal count.
- **cfg defaults to 1.0.** The released checkpoints are CFG-distilled;
  guidance is already in the weights, and real guidance on top burns the
  picture and doubles the cost.
- **Above 768 px it renders in two passes** by default: sample at the native
  size, then refine up, rather than going off-distribution directly. The
  choice lives in the resolution popover, with what draws the first pass up
  beside it: bicubic, or a trained latent upscaler once one is picked under
  weights (see [models.md](models.md#minimax-h3-video-with-sound-and-stills)).
  Switching to the trained one sets the refine to 0.30 and 3 steps, the
  recipe measured for it; both stay yours to change.
- **Spoken dialogue** is a first-class feature; see the spoken lines section
  in [the-node.md](the-node.md#spoken-lines).
- **Turbo** is a distillation LoRA (in the same repo as the weights), driven
  by the turbo pill at 4 to 8 steps.
- **A guide LoRA pass** finishes a render through a file trained to map one
  video to another — a sharpener, a style transfer — with each pass pinned as
  its own aligned guide (see [tools.md](tools.md#guide-lora-pass)).

## LTX 2.5

Video with synchronized sound.

- **References are a sheet.** Up to nine stills are composited into one
  Ingredients reference sheet, which needs the Ingredients IC-LoRA installed
  (see [models.md](models.md#ltx-25-video-with-sound)). Stills only: a
  reference clip or a sound file has no panel to be.
- **Duration can be the model's call.** With the duration head installed, the
  seconds pill offers **auto**, and the model is asked how long the shot wants
  to be. Shots can also run much longer than H3's.
- **Two passes** past the native size uses Lightricks' own latent spatial
  upscaler, and **ReDetail** is a second pass over a finished render that
  spends time to buy picture detail.
- Renders can be guided for detail and for lip-sync; the pills appear when the
  files behind them are installed.

## Krea 2

Stills, up to three references, cited as `Picture N` in the prompt.

- Two checkpoints: RAW is the reference, Turbo is the distilled one the turbo
  pill swaps in. LoRAs train on RAW and apply on Turbo, so the turbo pill
  doesn't touch them.

## Ideogram 4.0

Stills from prose alone.

- **No references.** The model reads none, and a render with references
  attached is refused with a message rather than silently ignoring them.
  Switch the model pill to another stills family, or clear the references.
- Prompts are plain natural language, wrapped into the JSON caption the
  model was trained on; a caption you write or paste yourself is used as
  written. In the chat, the *Magic prompt* switch has Ideogram's own magic
  prompt write the full caption instead (see [the chat](tools.md#chat)). Its
  speed axis is the official preset ladder (48, 20 or 18 steps) rather than
  a turbo file.
- The unconditional checkpoint is optional and enables proper CFG.

## Qwen Image Edit

Stills, edited from a picture you already have.

- An attached picture is a reference: the model reads it beside the sentence
  and the aspect pill sets the canvas. To change a picture *in place*, click
  the first picture's label so it reads "editing" — the canvas follows that
  picture then. Attach the last frame of shot 1, click it, write "the coat is
  red now", and what comes back is the same person in the same room: shot 9's
  start frame.
- Up to three pictures total, on the base weights.
- **Turbo** is a Lightning LoRA (four or eight steps at cfg 1), matched to
  your checkpoint's edition. There is no distilled checkpoint.
- Works on a whole strip too, via the contact sheet tool: see
  [tools.md](tools.md#contact-sheet).

## Flux 2 Klein

Stills, drawn from prose or edited from a picture, natively.

- Black Forest Labs' compact Flux 2, at 4B (Apache 2.0) or 9B
  (non-commercial). Pick the Qwen3 text encoder that matches the size.
- Same arrangement as Qwen Image Edit: pictures are references, and the
  first one's label switches it to being edited in place. Up to three
  pictures.
- **Turbo** swaps in the 4-step distilled checkpoint. No turbo LoRA exists for
  this family.
- The base checkpoint runs around 20 steps at cfg 5. There is no scheduler
  control: the schedule is a function of the step count and the canvas.

## Qwen Image 2.1

Stills, drawn from prose or edited from pictures, on one checkpoint.

- Alibaba's second-generation Qwen-Image, behind the Qwen3-VL 8B encoder
  Ideogram 4.0 already uses. Native 2K; ask for "an RGBA image with a
  transparent background" and the PNG comes out with an alpha channel.
- Same arrangement as Qwen Image Edit and Flux 2 Klein: pictures are
  references, and the first one's label switches it to being edited in place,
  with the canvas following it. Up to ten pictures, the official workflow's
  own cap. Cite them with
  `@` handles as anywhere else; in the prompt the model reads them as
  `<image1>`, `<image2>`, which is how its own tokenizer names them.
- Every reference is resized to about the canvas's area before the encoder
  reads it, on the encoder's own /32 grid — and on an edit in place the
  canvas *is* that resize of the first picture, which is why the size on the
  stage card can differ by a few pixels from the other families' at the same
  edge. The official note is that sampling at any other size shifts the edit.
- The row is the template's 20 steps at cfg 1, euler/simple. Qwen's card
  asks 40-50 steps, and cfg 3 over the empty negative gives a slightly
  crisper ruff and skin — at four times the wall clock on a 2K canvas, since
  every step is evaluated twice. Raise both when a render is worth it.
- The strongest way to use it: render the character once as a single
  picture, then attach that picture and cite it — a
  turnaround sheet, a scene, a costume study. The face, hair, jewellery and
  fabric carry over panel for panel; what the picture does not show, the
  model invents, so give it a second picture where the gown matters.
- **Turbo** is a Lightning LoRA or nothing: there is no distilled 2.1
  checkpoint, and no Lightning LoRA for 2.1 had been published when this was
  written. The pill is where one goes.
- An edit inherits the *look* of the first picture: a stylised source comes
  back stylised. Feed edits a photo where you can.
- **Guides** aim the still at a tracing (edges, lines, depth, pose, grey)
  through alibaba-pai's Fun ControlNet-Union. Press **Guide** in the
  pre-stage's tool row: *Pick a tracing* takes one the ControlNet bench
  already wrote, *Trace a picture* opens the bench on any picture and its
  **Aim the still at it** button brings the tracing back. It lands as a
  *guide* chip: not one of the ten pictures, and the prompt does not cite it.
  The prompt says what things are; the guide says where they go. Pick the
  ControlNet file once in the weights pill (the chip says so until you do;
  see [models.md](models.md#qwen-image-21-stills-drawn-or-edited-from-pictures)).
  The loose / firm / locked stops beside the guide pill set how hard it
  pulls: locked follows the drawing so closely that it decides what things
  are too, firm leaves the prompt room. The branch
  was trained on Edges, Lines, Depth, Pose and Luma; a guide of another
  aspect than the canvas is cropped to the canvas from its centre. Needs a
  ComfyUI from late September 2026 or newer; on an older one the tracing
  goes to the init image as it does on Krea 2.
- It is not an edition of Qwen Image Edit. Different DiT, different VAE,
  different encoder file, no shift node, no editions pill, and no built-in
  ControlNet: the guide is a separate file, as above.

## Editing a picture you just rendered

On the edit families (Qwen Image Edit, Flux 2 Klein, Qwen Image 2.1) the
seed the sampler uses is derived from the seed widget *and* the attached
pictures. Reusing the seed that made a picture would otherwise start the edit
from that picture's own noise, and the model then reproduces the picture
instead of changing it. You never have to touch the seed after a render; the
same widget value with the same pictures is still the same edit.

## Mixing families

You are not asked to pick one family and stay there. Different cards on a
timeline can use different families, and the pre-stage's stills can feed any
video family's shots. A preset saves the sampler row of the family it was made
on and never pushes it onto another family's shot.

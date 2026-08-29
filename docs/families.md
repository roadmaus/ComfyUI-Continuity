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
| Qwen Image Edit | stills | up to three; the first is the picture being edited |
| Flux 2 Klein | stills | up to three; the first is the picture being edited |

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
  choice lives in the resolution popover.
- **Spoken dialogue** is a first-class feature; see the spoken lines section
  in [the-node.md](the-node.md#spoken-lines).
- **Turbo** is a distillation LoRA (in the same repo as the weights), driven
  by the turbo pill at 4 to 8 steps.

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
- Prompts are plain natural language. Its speed axis is the official preset
  ladder (48, 20 or 12 steps) rather than a turbo file.
- The unconditional checkpoint is optional and enables proper CFG.

## Qwen Image Edit

Stills, edited from a picture you already have.

- The first attached picture is not a reference, it is the picture being
  changed. Attach the last frame of shot 1, write "the coat is red now", and
  what comes back is the same person in the same room: shot 9's start frame.
- Up to three pictures total, on the base weights.
- **Turbo** is a Lightning LoRA (four or eight steps at cfg 1), matched to
  your checkpoint's edition. There is no distilled checkpoint.
- Works on a whole strip too, via the contact sheet tool: see
  [tools.md](tools.md#contact-sheet).

## Flux 2 Klein

Stills, drawn from prose or edited from a picture, natively.

- Black Forest Labs' compact Flux 2, at 4B (Apache 2.0) or 9B
  (non-commercial). Pick the Qwen3 text encoder that matches the size.
- Same arrangement as Qwen Image Edit: the first picture is the one being
  edited, with "start blank" as the way out. Up to three pictures.
- **Turbo** swaps in the 4-step distilled checkpoint. No turbo LoRA exists for
  this family.
- The base checkpoint runs around 20 steps at cfg 5. There is no scheduler
  control: the schedule is a function of the step count and the canvas.

## Mixing families

You are not asked to pick one family and stay there. Different cards on a
timeline can use different families, and the pre-stage's stills can feed any
video family's shots. A preset saves the sampler row of the family it was made
on and never pushes it onto another family's shot.

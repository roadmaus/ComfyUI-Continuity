# Model families

A family is a model architecture and everything this pack knows about talking
to it: which checkpoints it routes between, how your prompt reaches its
encoder, what a reference means to it, how a LoRA gets in. The node is the
same node on all of them; the model pill picks which one a render lands on.

| Family | Makes | References |
|---|---|---|
| MiniMax H3 | video with sound | each encoded on its own, addressed in a structured prompt |
| LTX 2.5 | video with sound | up to nine stills, composited into one reference sheet |
| Krea 2 | stills | up to three |
| Ideogram 4.0 | stills | none, prose only |
| Qwen Image Edit | stills | up to three; click the first to edit it in place |
| Flux 2 Klein | stills | up to three; click the first to edit it in place |
| Flux 3 Klein | stills | up to ten; click the first to edit it in place |
| Qwen Image 2.1 | stills | up to ten; click the first to edit it in place |
| MOSS-Image | stills | none, prose only |
| MiniMax H3 Image | stills | as many as you like (core's ceiling is 100); click the first to edit it in place, or mask it to inpaint |
| MiniMax H3 Still | stills | up to nine; click the first to fit the canvas to it |

Every render files into a folder named after its family
(`output/continuity/renders/ltx25/`, `output/continuity/stills/krea2/`) and
carries the family name on the file.

## MiniMax H3

Video with synchronized sound. For stills there are two MiniMax families
below: MiniMax H3 Image, the image model, and MiniMax H3 Still, which draws
one frame with these video weights.

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
  weights (see [models.md](models.md#minimax-h3-video-with-sound)).
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

## Flux 3 Klein

Stills, drawn from prose or edited from pictures, natively.

- Black Forest Labs' FLUX 3 Image Klein: a 5.6B DiT behind a Qwen3-VL 4B
  text encoder and the Flux 2 VAE, under the FLUX Kommunity License
  (non-commercial, with a commercial-output exception for small users; read it).
- Same arrangement as Flux 2 Klein: pictures are references, and the first
  one's label switches it to being edited in place. Up to ten pictures.
- The checkpoint is the distilled one: 16 steps at cfg 1, euler/simple. There
  is no turbo pill, because it is already the fast model. Klein Base loads in
  the same slot if you raise the row to about 50 steps and cfg 3.5.
- **Write full scene captions, or let BFL's upsampler write them.** The model
  was trained on them, and a short prompt or a one-line edit instruction gives
  generic output. **Refine** on a Flux 3 Klein still runs BFL's own upsampler
  instruction on your refiner model: a full caption from a short request, or,
  with pictures attached, an edit instruction written against them. In the
  chat, the *Magic prompt* switch does the same for every still it draws on
  Flux 3 Klein.
- Needs a ComfyUI from 15 October 2026 or newer.

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

## MOSS-Image

Stills from prose, and only from prose.

- OpenMOSS's 5B DiT (Apache 2.0), behind a Qwen3.5 9B text encoder and the
  Flux 2 VAE. Its strength is rendered text — signs, notes, labels, in
  English and Chinese — so quote the words you want drawn.
- No references: it has no picture input at all, and attaching one is
  refused. An init image still works, the same as on Krea 2.
- The row is the model card's: 50 steps at cfg 3, euler/simple. The card
  calls 30 the bottom of the useful range. On the unconditional pass layer 22
  is skipped, which is the card's own guidance; the pack adds it for you and
  leaves it off at cfg 1, where that pass never runs.
- **No turbo.** The published 8-step distillations need their own sampler
  loop, which ComfyUI does not have; on the ordinary sampler they are not
  the same model.
- A JSON layout pasted as the prompt (`summary.caption`, `items` with boxes)
  places text and objects where the boxes say. See the
  [MOSS-Image user guide](https://github.com/OpenMOSS/MOSS-Image/blob/main/USERGUIDE.md#layout-prompts-experimental)
  for the format. Use the same canvas size the boxes were written for.
- Needs a ComfyUI from 16 October 2026 or newer.

## MiniMax H3 Image

Stills drawn from prose, edited from pictures, or inpainted under a mask.

- MiniMax's image model, native in ComfyUI 0.45 and newer. It is the pre-stage's
  **MiniMax** choice: a still saved there before opens on it, its prompt,
  pictures and LoRAs carried over. (That choice used to run the H3 *video*
  model on a short clip and keep one frame; this replaces it.)
- **It wants a big canvas.** The working range is about 4 to 20 megapixels and
  it is best near 16; the resolution slider runs 512 to 4096 on the short
  edge, starting at 2048 (4 MP) because that is the cheap end. Below 4 MP the
  pictures come out soft, but the slider goes there if you want to try.
- Same arrangement as Qwen Image Edit and Flux 2 Klein: pictures are
  references, and the first one's label switches it to being edited in place,
  with the canvas following it. No cap on the pictures beyond core's hundred
  inputs — every one costs memory, so experiment. In the prompt they are
  `<Picture 1>`, `<Picture 2>`, MiniMax's own spelling.
- **Inpainting.** Press **Mask** in the pre-stage's tool row: *Pick a matte*
  takes one the ControlNet bench already wrote, *Mask a picture* opens the
  bench on the picture to change, and its **Inpaint under it** button brings
  the matte back. It lands as a *mask* chip. The white of the matte is
  repainted over Picture 1 and everything else is kept; the prompt says what
  goes in the hole. A mask always edits Picture 1 in place, so attach the
  picture the matte was traced from first.
- The row is six steps at cfg 1, euler/simple: the checkpoint is distilled to
  six steps, and other step counts fall between the steps it learned.
- **No turbo.** It is already a six-step model.
- LoRAs load the ordinary way. The DiT is the same shape as H3 video's pruned
  checkpoints, so an H3 video LoRA loads onto it; whether it helps is
  untested.
- Detailed, complete descriptions work best (it reads up to 4,096 tokens).

## MiniMax H3 Still

Stills from the H3 *video* model: one frame, drawn by the weights that render
your shots.

- **Why it exists beside MiniMax H3 Image.** The video model has a look of its
  own, and every LoRA made for MiniMax H3 was trained on it. Here those LoRAs
  go onto the weights they were made for, through the same loader a shot uses.
  On MiniMax H3 Image they only fit structurally.
- It is the pre-stage's **MiniMax H3 Still** choice. A still saved on the old
  one-frame branch still opens on MiniMax H3 Image; pick this one to come back.
- **It loads H3's own files**: one video checkpoint (FL2VA is the one to pick;
  it reads reference pictures too), the Qwen3-VL encoder and the H3 *video*
  VAE. Nothing extra to download if H3 already renders for you.
- **One frame is sampled, not a clip.** The old branch sampled a five-frame
  clip and kept one frame. This samples a single latent frame and decodes it
  through the video VAE as a repeated group, the method from
  [Fizgig H3 Still](https://github.com/shootthesound/ComfyUI-Fizgig-H3-Still).
  It is several times faster and holds much larger pictures.
- **Best from about 3 MP up.** The slider runs 512 to 2176 on the short edge
  (up to about 8 MP, 3872x2176), starting at 1280. Small pictures come out
  noticeably weaker.
- The row is 50 steps at cfg 1, er_sde/simple. **Turbo is a LoRA**: pick
  `minimax_h3_turbo_v4_step600_ema` and the switch sets it to 0.38 strength
  and 20 steps, the recipe the still workflows use. A checkpoint with the
  distillation merged in (a hybrid H3 merge) takes the switch's "no LoRA ·
  merged checkpoint" choice instead: same steps and row, nothing added to the
  stack. The lower stops (12, 16) are for drafts.
- **Pictures are references**, up to nine, `<Picture 1>`, `<Picture 2>` in the
  prompt. To change a picture, attach it and say what changes; clicking the
  first one's label fits the canvas to it. The render always starts from
  noise.
- The prompt is written to the model in H3's own structured form, the same
  way a shot's is.
- **The cast is MiniMax H3's.** It is the same model, so a member's LoRAs,
  their saved references and how they are sent are shared with MiniMax H3:
  set once, used by shots and stills alike. On the cast card this model has
  no tab of its own; its settings are the MiniMax H3 tab.
- **Not here yet:** starting from an init image at partial denoise, and a
  ControlNet guide. Both are refused with a message.

## Editing a picture you just rendered

On the edit families (Qwen Image Edit, Flux 2 Klein, Flux 3 Klein, Qwen Image 2.1, MiniMax
H3 Image, MiniMax H3 Still) the
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

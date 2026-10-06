# Rendering from a script or a coding agent

Continuity can be driven without opening ComfyUI's page: from a shell, a CI
job, or a coding agent like Claude Code that you ask to "make a clip of a cat".
The pack ships a small command-line client, `skills/continuity-render/render.py`, that talks to a
running ComfyUI over HTTP. It needs only Python 3.9 or newer (no packages to
install) and runs on the ComfyUI machine or on any machine that can reach its
port.

## Quick start

From the pack's folder (`ComfyUI/custom_nodes/ComfyUI-Continuity`):

```
python3 skills/continuity-render/render.py families
python3 skills/continuity-render/render.py h3 "a cat stretches on a sunny windowsill"
```

The first command lists every model family, whether its files are installed,
and which turbo files a fast render would use. The second renders a six-second
MiniMax H3 clip, waits for it, downloads it to `./renders/` and prints the path
of the downloaded file.

The client talks to `http://127.0.0.1:8188` unless you set `--url` or the
`COMFY_URL` environment variable:

```
export COMFY_URL=http://192.168.1.20:8188
python3 skills/continuity-render/render.py krea2 "a tabby cat, studio portrait" --aspect 4:5
```

## What it decides for you

- **Weights.** The server picks each model file the way the node does: the
  files you last used on that machine, or the only file in a folder whose name
  fits. A file can be overridden with `--model SLOT=FILE`; `families` lists the
  slot names.
- **Speed.** A render is fast by default. The client turns on the family's turbo
  switch, the same one on the node's sampler row: a distilled checkpoint where
  the family has one, or a distillation LoRA from `models/loras`. For MiniMax H3
  it picks the FL2V or Ref2V distill to match the checkpoint the render
  actually uses. `--quality draft|medium|good` picks the step count.
  `--native` renders at the family's full step count instead, which for video
  can take many times longer.
- **GPUs.** Each model loads where this machine's remembered weights pin it:
  the device you last picked for that slot on the node's weights popover
  (ComfyUI-MultiGPU). With nothing pinned everything shares ComfyUI's default
  card, which on a two-card box means the text encoder and the video model swap
  in and out of one GPU. `--device SLOT=DEVICE` pins a slot for one render
  (`--device clip=cuda:1`). The queued line says where each slot loads.
- **Attention and memory.** A clip samples with the attention kernel, low VRAM
  and fast math you last set on a node's sampler row for that family; the
  machine remembers them the way it remembers the weights. Before you have set
  one, a render runs plain attention, which on H3 can be several times slower
  than the kitchen or sage kernel. `--attention default|sage|kitchen|sla`,
  `--low-vram` / `--no-low-vram` and `--fast-math` / `--no-fast-math` set them
  for one render, and the queued line names the attention it runs.
- **Clip or picture.** Video families make a clip, and image families (Krea 2,
  Ideogram 4, Qwen, Flux 2 Klein) make a picture.

If the server can't tell which LoRA is the turbo one, because there is none or
there are several, it refuses the render and names the candidates. Pass one
with `--turbo-lora NAME`, or use `--native`. It never falls back to a slow render
without saying so.

Some checkpoints have the distillation merged into their weights and need no
turbo LoRA at all. Pass `--merged` for those: the render gets the turbo step
count and sampler with no LoRA, the same as the node's "no LoRA · merged
checkpoint" choice. The server can't tell a merged checkpoint from its
filename, so it's yours to say. It works for video families only; a picture
family's turbo checkpoint goes in its `turbo_model` slot.

## Attaching pictures

```
python3 skills/continuity-render/render.py h3 "@pic-1 turns and walks out of frame" --image cat.png
python3 skills/continuity-render/render.py h3 "@pic-1 and @pic-2 meet in a park" --image a.png:ref --image b.png:ref
```

`--image PATH[:AS]` is repeatable. A local file is uploaded to ComfyUI's input
folder. Any other name refers to a file already there, including an earlier
render such as `"H3_00012_.png [output]"`. Files are cited in the prompt in the
order given: pictures as `@pic-1`, `@pic-2`, videos as `@clip-1`, sounds as
`@snd-1`.

`AS` decides what a picture does in a clip. `start` makes it the opening frame
and `end` the closing frame. `ref` makes it a reference the model draws from, and
a scope such as `style` or `person` makes it a reference for that one thing.
Without `AS`, the first picture opens the shot.

On a Qwen Image 2.1 still, `AS` can also be `guide`: the picture is a tracing
from the ControlNet bench and the render is aimed at it, the way the pre-stage's
Guide tool does it. It is not cited in the prompt. `--guide-strength` sets how
hard it pulls: 1 (the default) follows it line for line, 0.8 leaves the prompt
room to change what things are, 0.5 only suggests the layout.

```
python3 skills/continuity-render/render.py qwen21 "a ruined castle tower on a snowy hill" --image tower-edges.png:guide --guide-strength 0.8
```

## Other options

| Option | Meaning |
|---|---|
| `--seconds N` | clip length; the family's default otherwise |
| `--aspect 16:9` | shape; `9:16`, `1:1`, `4:5` and the others the node offers |
| `--edge N` | short edge in pixels; the family's native size otherwise |
| `--seed N` | random otherwise; printed either way |
| `--still` | a picture rather than a clip |
| `--lora NAME[:N]` | a LoRA from `models/loras` (subfolder included) at strength N, 1 otherwise; repeatable, beside the turbo LoRA |
| `--out DIR` | where to download; `./renders` by default |
| `--no-wait` | queue it, print the prompt id, and return |

The client prints only the downloaded paths on stdout. Progress and errors go to
stderr, and the exit status is non-zero when a render can't be built or fails,
with the server's own explanation. A render queued this way is an ordinary
ComfyUI job: it shows in the queue, Cancel stops it, and the file lands in the
output folder like any other.

## For coding agents

The pack ships a Claude Code skill that teaches an agent this whole page:
finding the client, checking the server, rendering, and what to do when a render
is refused. Install it once by copying (or linking) the folder into your
skills:

```
cp -r ComfyUI/custom_nodes/ComfyUI-Continuity/skills/continuity-render ~/.claude/skills/
```

After that, "render a clip of a cat with H3" is enough. The agent asks you which ComfyUI to render on
before its first render. Other agents can be
pointed at this page or at `python3 skills/continuity-render/render.py --help`. Without the skill, a
line in your project's `CLAUDE.md` does most of the job:

```
To render with ComfyUI, use `python3 <path-to-pack>/skills/continuity-render/render.py` (see its --help).
Run `families` first; never write ComfyUI workflow JSON by hand.
```

## The HTTP API underneath

The client is a thin wrapper over two routes, which you can call from any
language.

`GET /continuity/render` returns what the machine can render: each family's id,
whether it is ready, the files it would use, and what a fast render would use.

`POST /continuity/render` takes JSON and queues one render:

```json
{"family": "h3", "prompt": "@pic-1 walks off", "pictures": [{"filename": "cat.png", "as": "start"}],
 "seconds": 6, "aspect": "16:9", "short_edge": 768, "seed": 7,
 "fast": true, "quality": "good", "turbo_lora": null, "merged": false, "still": false,
 "models": {"clip": "some_encoder.safetensors"}, "devices": {"clip": "cuda:1"},
 "accel": {"attention": "kitchen", "chunk_ffn": false, "fp16_accumulation": false}}
```

Only `family` and `prompt` are required. It answers
`{"prompt_id", "speed", "piece"}`, or `{"problem": "..."}` with status 400
when the render can't be built. Upload files first with ComfyUI's own
`POST /upload/image`. Poll `GET /history/<prompt_id>`, where the saved file
appears under the output key `mmc_video` (clips) or `mmc_image` (pictures), and
download it with `GET /view`. Send the body as `application/json`: the pack
refuses cross-site requests.

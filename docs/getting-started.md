# Getting started

## What you need

- A recent ComfyUI. The model families themselves ship with ComfyUI core (H3
  is `comfy_extras/nodes_minimax_h3.py`, and the others are core nodes too).
  This pack drives them, it does not carry them.
- No extra Python packages. Cloning the repo is the whole install.
- The weight files for at least one family. See [models.md](models.md).

## Install

```
cd ComfyUI/custom_nodes
git clone https://github.com/roadmaus/ComfyUI-Continuity
```

That leaves one folder, `ComfyUI-Continuity`, inside `custom_nodes/`. Restart
ComfyUI.

**If you already have MiniMax Creator installed, don't clone alongside it.**
This pack used to be called MiniMax Creator and kept its node ids through the
rename, so the old folder and a new clone are two packs claiming the same
nodes — and what people report is not one of them winning, it is neither of
them appearing. Update the old clone in place instead:

```
cd ComfyUI/custom_nodes/ComfyUI-MiniMax-Creator
git remote set-url origin https://github.com/roadmaus/ComfyUI-Continuity.git
git pull
```

Or delete the old folder and then clone. Nothing you have made is inside it —
presets, settings and favourites live in ComfyUI's `user/` directory and are
read back under their old names. If the old copy came from the ComfyUI
Manager, uninstall it there rather than deleting the folder.

## Download one family's weights

Pick the family you want to start with and download its files from
[models.md](models.md). The minimum is small: H3 video is five files, LTX 2.5
video is four, a Krea 2 still is four. Everything else in the models list is
optional.

The Comfy-Org and Lightricks repositories are laid out like the `models/`
folder already, so a file at `diffusion_models/krea2_raw_bf16.safetensors` in
the repo goes to `ComfyUI/models/diffusion_models/`. Download by path and you
can't put it in the wrong place.

## First render

1. Add the node: double-click the canvas and search for "Continuity".
2. Click the model pill and pick your family and checkpoint. The weights pill
   next to it is where you point each slot at the files you downloaded. Picks
   are remembered per family, so this is a one-time chore.
3. Type a prompt in the box.
4. Press Render.

The finished clip or still lands in `output/continuity/`, filed under the
family that made it, and shows up in the node's own gallery.

If a file is missing, the render is refused before the queue starts, with a
message naming the field and the folder it looks in. That message is the fix:
put the named file in the named folder.

## The fullscreen editor

`Ctrl+Shift+M` opens the node as the whole window. Two views over the same
state:

- **Simple** is one column, for when the piece is one prompt.
- **Full** puts the pre-stage, the shot and the picture side by side, for when
  the piece is built out of parts.

Switching views mid-sentence keeps the sentence. It is the same node either
way.

## Where to go next

- Attaching pictures, clips and sound to a prompt: [the-node.md](the-node.md)
- More than one shot: [timeline.md](timeline.md)
- What each model family can and can't do: [families.md](families.md)

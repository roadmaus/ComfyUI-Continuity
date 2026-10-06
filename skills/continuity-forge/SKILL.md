---
name: continuity-forge
description: Plan and keep a game's assets (characters, sprites, tiles, tilesets, backgrounds, icons, UI, materials, textures, sounds) in a Game Forge project on a ComfyUI server that has the Continuity node pack, with the forge.py bundled in this skill. Use whenever the user asks to set up, plan, list, import, check, look at, export to an engine, check the status of, or download a game's art or sound assets "on ComfyUI", "in the forge" or "with Continuity", for any engine (Godot, LÖVE, Tiled, Game Boy, GB Studio, Unity, Unreal, glTF). Never write project.json or MANIFEST.md by hand; this client keeps them.
---

# Game Forge

Game Forge keeps a game's assets in one **project** on the ComfyUI machine: one
art style, one or more engine targets, fixed seeds, and an asset list where
every asset is a **recipe** (what to make, from what, with which seed and
family, followed by which post-steps) plus the files it produced. The project
writes its own `MANIFEST.md`, which is both the documentation of the game's art
and the queue of what is still missing.

You drive it with `forge.py`, bundled here. It talks to the same
`/continuity/forge/*` routes the bench in the browser uses, so anything the
bench can do, you can.

## 1. The client and the server

- **Client:** `forge.py` in this skill's own folder (the base directory given
  when the skill loads). Run it as `python3 <skill dir>/forge.py`. **Do not
  search the filesystem for it.** It is self-contained (Python 3.9+, standard
  library only).
- **Server:** if the user has not given you the ComfyUI address in this
  conversation, **ask them for it before running anything**, as one short
  question. Don't guess, don't read env vars, memory or config for it, and
  don't probe ports. Pass the answer with `--url` on every call.

Always start with:

```
python3 <skill dir>/forge.py --url URL capabilities
```

It confirms the server is reachable and has the forge, and lists the asset
kinds, render modes, targets and still families. If it says the server has no
`/continuity/forge`, the pack is missing or too old: tell the user.

## 2. Plan, don't click

Write the asset list once as a **plan** and apply it:

```
forge.py new mygame --mode pixel --target gbstudio --target godot4 --clause "16-colour pixel art, black outlines"
forge.py schema sprite            # the exact fields a sprite recipe takes
forge.py plan mygame plan.json    # merge by asset name; safe to run again
forge.py status mygame
```

A plan is JSON:

```json
{"assets": [
  {"kind": "character", "name": "hero", "prompt": "a small knight with a red plume", "seed": 7},
  {"kind": "sprite", "name": "hero-walk", "of": "hero", "frame": [16, 16],
   "animations": [{"name": "walk", "frames": 4, "fps": 8, "loop": true}], "directions": 4},
  {"kind": "tile", "name": "grass", "prompt": "short grass", "tile": [8, 8]}
]}
```

- **Run `schema <kind>` before writing entries of a kind.** Unknown fields are
  refused, not ignored; don't guess field names.
- **One plan, edited and re-applied**, beats many `add` calls. Applying is a
  merge by name: unchanged entries stay unchanged, an edited entry is replaced
  and goes **stale** if it was already made, and assets the plan does not name
  are left alone. A plan never removes anything; `rm` does, and even `rm` only
  moves the files to `.versions/`.
- **Prompts say what the thing is.** The style clause is appended to every
  prompt by the forge; don't repeat it in each entry.
- **Fixed seeds.** An asset with no seed gets one fixed from the project seed
  and its name. Give characters an explicit seed and keep it.
- Names are lowercase letters, digits, `-` and `_`.

## 3. Status, files, and what is made

```
forge.py status mygame            # planned / made / exported / stale, per asset
forge.py import mygame hero hero.png    # a picture made elsewhere becomes the masters
forge.py history mygame hero      # every set of masters it has had
forge.py files mygame --under assets
forge.py pull mygame --out ./mygame-art
```

- `status` marks an asset **(not looked at)** when nobody has viewed it since it
  was made. Don't describe what an asset looks like unless you have looked at
  its file.
- `import` takes local files (uploaded for you) or names already in ComfyUI's
  input folder. The import replaces the asset's masters as one set; the set it
  replaces is kept and listed by `history`.

Generation (`make`) is coming in a later step; `capabilities` will list it
when the server has it. Until then, make pictures with the `continuity-render`
skill and `import` them. A picture that should have transparency (sprites,
characters, icons) must be imported **with** alpha: matting an opaque picture
runs on the GPU and is not in the forge yet, so the build refuses it with
`matte.opaque`.

## 4. Check, look, export

```
forge.py check mygame                     # every target's budgets, every made asset
forge.py sheet mygame hero-walk           # a contact sheet PNG; look at it
forge.py export mygame godot4 --pull ./game/art
forge.py post mygame hero-walk baseline --target generic   # one step, frames kept as variants
```

- **Run `check` after every import or make, and fix what it reports.** Each
  problem is one line on stdout: target, asset, frame, tile (`column,row` or
  `-`), code, sentence. Codes start `budget.` (`budget.colours`,
  `budget.tiles`, `budget.grid`, `budget.atlas`, …). Where the problem has a
  place, the overlay PNG named on stderr outlines it in red.
- **Look at the `sheet` before saying anything about how an asset looks.** It
  shows the masters, then each target's converted frames, with that target's
  problems written over its row. Writing it clears **(not looked at)**.
- `export` writes engine files under `build/<target>/`: PNG + Aseprite JSON
  for every target, plus Godot `SpriteFrames`/`TileSet` `.tres`, Tiled
  `.tsx`/`.tmj`, a LÖVE Lua table, indexed PNGs for Game Boy, Game Boy Color
  and GB Studio (in GB Studio's `assets/` folders). Planned assets are skipped
  and listed. An export is from the masters every time; nothing in `build/` is
  worth editing by hand.
- Converting to pixel art happens on export, at the frame, tile or icon size
  in the recipe. A character, UI piece or background in a pixel project needs
  the style's `grid` (master pixels per art pixel), or `targets.<target>.size`
  on the asset.

## 5. Poses

A pose set is a project's mannequin poses for one animation or one shot:
`poses/<set>.json`, the body sliders, a frame rate, and a pose per frame in
VNCCS Pose Studio's `pose_data` shape. They are what characters will be drawn
into; for now you make them and look at them.

```
forge.py pose mygame import walk ~/Downloads/walk.fbx --fps 12   # a Mixamo clip, one pose per sample
forge.py pose mygame render walk --out ./walk                    # mannequin PNGs; look at them
forge.py pose mygame render walk --yaw 90 --frame 0 --frame 3    # from the side, two frames
forge.py pose mygame new stand                                   # one rest pose
forge.py pose mygame set stand 0 upperarm_l=0,0,-60 head=10,0,0  # turn bones, degrees
forge.py pose mygame paste nod pose_data.json                    # from Pose Studio's node
forge.py poses mygame
```

- **`import` and `render` are done by an open ComfyUI tab**, because the
  mannequin is drawn with WebGL in a browser. With no tab open they refuse at
  once with `pose.no_tab`: ask the user to open ComfyUI in a browser and keep
  the tab open, then try again. Frames already drawn come back without a tab.
- Imports come in **in place**: every frame is retargeted onto the standing
  rig, so a walk walks on the spot.
- `render` draws at 484x1088 by default, one cell of the four-frame grid a
  sprite's frames will be rendered in. `--yaw` turns the figure for another
  direction.
- Bone names are the mannequin's (`pelvis`, `spine_01`…`03`, `neck_01`,
  `head`, `clavicle_l`, `upperarm_l`, `lowerarm_l`, `hand_l`, `thigh_l`,
  `calf_l`, `foot_l`, `ball_l`, fingers as `index_01_l`…, and `_r` for the
  right); an unknown one is refused with `pose.bone`.
- Mixamo clips are the user's own download: never fetch or redistribute them.

## 6. Output and refusals

- stdout is data: names or paths one per line. Add `--json` to any command for
  the server's whole answer; sentences and progress go to stderr.
- A refusal exits 1 with the server's sentence on stderr. With `--json` the
  refusal is printed on stdout as `{"problem": "...", "code": "...", ...}`:
  branch on `code` (for example `recipe.unknown`, `recipe.field`,
  `asset.missing`, `project.exists`) and relay `problem` to the user.
- `check`, `export` and `post` exit 2 when they did their work but something
  breaks a target's budget; the problems are on stderr (and in `--json`).
- A server that cannot be reached exits 3: say so and ask for the address
  again rather than trying others.

## 7. Etiquette

- Report seeds with anything made, so it can be made again.
- Don't hand-edit `project.json` or `MANIFEST.md` on the server; change the
  project through the client and the manifest follows.
- For LÖVE projects, the `lua-25d-game` skill says how assets should be planned
  (placeholders first, one style paragraph, model sheet first); this forge is
  where that plan lives. For a shot rather than an asset, use
  `continuity-render`.

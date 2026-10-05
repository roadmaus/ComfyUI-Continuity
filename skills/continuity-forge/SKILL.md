---
name: continuity-forge
description: Plan and keep a game's assets (characters, sprites, tiles, tilesets, backgrounds, icons, UI, materials, textures, sounds) in a Game Forge project on a ComfyUI server that has the Continuity node pack, with the forge.py bundled in this skill. Use whenever the user asks to set up, plan, list, import, check the status of, or download a game's art or sound assets "on ComfyUI", "in the forge" or "with Continuity", for any engine (Godot, LÖVE, Tiled, Game Boy, GB Studio, Unity, Unreal, glTF). Never write project.json or MANIFEST.md by hand; this client keeps them.
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

Generation (`make`), the post-steps and checks (`check`, `sheet`) and engine
exports (`export`) are coming to the forge in later steps; `capabilities` will
list them when the server has them. Until then, make pictures with the
`continuity-render` skill and `import` them.

## 4. Output and refusals

- stdout is data: names or paths one per line. Add `--json` to any command for
  the server's whole answer; sentences and progress go to stderr.
- A refusal exits 1 with the server's sentence on stderr. With `--json` the
  refusal is printed on stdout as `{"problem": "...", "code": "...", ...}`:
  branch on `code` (for example `recipe.unknown`, `recipe.field`,
  `asset.missing`, `project.exists`) and relay `problem` to the user.
- A server that cannot be reached exits 3: say so and ask for the address
  again rather than trying others.

## 5. Etiquette

- Report seeds with anything made, so it can be made again.
- Don't hand-edit `project.json` or `MANIFEST.md` on the server; change the
  project through the client and the manifest follows.
- For LÖVE projects, the `lua-25d-game` skill says how assets should be planned
  (placeholders first, one style paragraph, model sheet first); this forge is
  where that plan lives. For a shot rather than an asset, use
  `continuity-render`.

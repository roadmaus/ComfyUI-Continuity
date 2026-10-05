# Continuity — Game Forge

Spec for a new bench. High level: architecture and decisions, not code.
Written 2026-10-05 against `main` at `6347afe`, after the research in §3 and
§4.

## 1. Summary

A bench reached from the tools dashboard where a game's assets are made: the
characters and their animation frames, tiles and tilesets, materials,
textures for 3D models that already exist, backgrounds, icons and UI, sound
effects, ambience and music. Everything belongs to a **project**, and the
project carries what every asset in it must agree on: one art style, one or
more engine targets, a palette and grid when the style needs them, and fixed
seeds. What comes out is game-ready: engine files, not pictures to be cut up
by hand afterwards.

It is not a pixel-art tool, a Game Boy tool, or a LÖVE tool, though all three
are first-class targets. A project can be painted, flat vector, toon, pixel,
or realistic PBR, and the same masters can be exported to Godot and to GB
Studio at once.

**The shape, in one paragraph.** An asset is a **recipe** (what to make, from
which references, with which seed, through which family, followed by which
post-steps) plus the files it produced. The recipe is kept, so any asset can
be made again, varied, or re-exported for another target without being
redrawn. The project's asset list is written out as a `MANIFEST.md` that is
both the documentation of the game's art and the queue: "make what is
missing" walks it.

**First iteration, deliberately small** (§12): the project, the manifest, the
post-steps and the exports, then 2D generation. Audio, materials and model
texturing follow, in that order, each behind the one before.

**Agents are first-class users** (§11). Everything the bench can do, an agent
can do from a shell with the pack's CLI, through the same routes the bench
uses: plan a project, make its assets, check them against a target, look at
them, export them. The bench is one client of the forge's HTTP surface; the
CLI is the other, and neither may do anything the other cannot.

## 2. Non-negotiables

- **Local.** Nothing leaves the machine, as everywhere else in the pack.
- **No new pip dependencies.** numpy, SciPy, torch, PIL and PyAV are what the
  pack already uses. Optional capability arrives the way it does now: a node
  pack detected at runtime through `nodes.NODE_CLASS_MAPPINGS`, and a pill
  that lights up only when it is there.
- **GPU work goes through the queue.** `jobs.register` and `ContinuityJob`
  for single jobs, `jobs.enqueue` with an API-format prompt for multi-node
  pipelines (the lift pattern). Never a thread of our own beside the queue.
  Previews that are arithmetic stay HTTP GETs, gated by
  `jobs.refuse_if_busy()`.
- **Nothing runs a model until it is asked to.** The upscale bench's rule
  (`web/creator/upscale.js`): dials that cost arithmetic redraw live, dials
  that cost weights are a press.
- **Writes are safe.** Names checked against a safe pattern, every path
  joined under the project root, a set of files swapped in with one
  `os.replace`, the set it replaces kept as a numbered version. (VNCCS does
  this well, §3.1; we copy the idea, not the code.)
- **The bench and the CLI have parity.** No capability lives only in the
  browser. Anything the bench does is a `/continuity/forge/*` route with JSON
  in and JSON out, and the CLI has a command for it (§11). A test holds the
  two lists together.

## 3. What the research says

### 3.1 VNCCS, the prompt for this

`AHEKOT/ComfyUI_VNCCS` makes visual-novel sprite sets: character, then poses,
then costumes, then emotions, each a transparent PNG under
`output/VNCCS/Characters/<name>/`. Its consistency is **reference editing**,
not LoRA training or IPAdapter: every new image is an edit of the base image
with Qwen Image 2.1, Flux 2 Klein or (first frame only) MiniMax H3, plus pose
and costume LoRAs. The emotion pass crops the face, edits only that, and
pastes it back feathered.

Worth taking: the asset model on disk, edit-from-a-sheet as the consistency
mechanism, the atomic versioned writes, a good hand-written chroma keyer,
per-stage caching with single-image regenerate.

Not worth taking: calling other nodes by reflection (it silently drops
arguments and breaks when they change), GPU work on its own thread outside
the queue, llama-cpp-python wizards, a key node in a separate repo, and no
check at all that the character still looks like the character.

### 3.2 The lua-25d-game skill

The Flash-style LÖVE skill is the guidance for how assets should be *made*,
and most of it generalises past LÖVE:

- **Placeholders first, art second**, and an asset manifest with every
  image's exact size, alpha, depth, pivot and full prompt. Here the manifest
  is generated from the project rather than written by hand.
- **One fixed style paragraph** ends every prompt; **fixed seeds** per
  character.
- **A model sheet first**; variants are edits of the same crop on the same
  canvas, so anchors and pivots do not move.
- **Author at the large size once, convert per target**, never scale at
  runtime. A handheld gets its own downscaled set; a Game Boy is the extreme
  case of the same rule.
- **Alpha bleed** before export: copy edge colours into fully transparent
  texels, or scaled and rotated parts get dark halos.
- **Atlases** ≤ 2048, metadata as plain data a person or Claude can edit.
- For HD cutout characters: parts with 15–25 % overlap at joints, nine mouth
  shapes (Rhubarb A–H, X), three eye states, pivots recorded.

### 3.3 Texturing a mesh that already has UVs

The state of the art is one loop with variations: render the mesh from
several cameras, generate a picture per view conditioned on depth and/or
normals, project the pictures back into UV space, fill what no camera saw,
pad the islands. TEXTure and Text2Tex do it a view at a time; Paint3D adds a
UV-space inpaint for the unseen texels; SyncMVD fuses the views inside
denoising; Hunyuan3D-Paint 2.1 and MV-Adapter are trained multi-view models;
TRELLIS.2 textures in 3D directly.

None of the trained multi-view adapters targets the families this pack
drives. The practical routes for us are, in order of preference:

1. **One grid image.** Tile 4–6 orthographic views into one canvas and
   generate them in one pass with depth control. The DiT's attention couples
   the views. No adapter, works with Qwen Image Edit's native depth control.
2. **Sequential**, TEXTure-style: render the partial texture into the next
   view and regenerate only what is unpainted or seen badly.
3. **A base from TRELLIS.2 texturing** (the pack already runs TRELLIS.2 for
   lift), refined through 1 or 2.

Pitfalls the design must answer: views that disagree (§6 colour match,
grid generation), seams (soft weights, dilation, a refine round), lighting
baked into the albedo (prompt flat, delight when a model is available), the
face on the back of the head (view words in each tile's prompt, the front
view as a reference), mirrored UVs (several surface points share one texel),
and grazing angles (clamp `N·v`).

ComfyUI core now has the pieces around the loop: `RenderMesh` (depth and
normal renders from a camera), `UnwrapMesh`, `BakeNormalMapFromMesh`,
`BakeAmbientOcclusion`, `ApplyTextureToMesh`, Load3D/Save3D. The research
could not open docs.comfy.org; names are to be checked against an install
before they are wired.

### 3.4 Seamless tiling

Circular padding is the UNet trick and does little to a DiT, which
patchifies. For Qwen, Flux and Krea the working method is to **roll the
latent by a random offset every step** (roll, denoise, roll back), so no
seam forms anywhere fixed, and decode with circular padding. One axis for
parallax layers and trim sheets, both for tiles. Fallback for anything: offset
by half and repair the cross-shaped seam with a masked edit.

### 3.5 Sprites

Image models cannot draw true 8×8 or 16×16 art. They can draw clean, flat
pixel-art-styled pictures at 1024. The conversion is ours: detect the grid,
take the **mode** of each cell (never a blend), quantise to the palette *at
the target size*, optionally ordered-dither, remove orphans. Sheets stay
consistent when their frames are generated **together in one grid image**
with a fixed seed and reference, and feet are snapped to one baseline.

Directions: Qwen Image Edit with the Multiple-Angles LoRA (8 azimuths × 4
elevations), or, more consistent, lift the sheet to a mesh, texture it, and
render 8 directions from a fixed orthographic camera.

### 3.6 Audio

- **LTX 2.5** (in the pack already) samples a joint audio+video latent. Its
  audio path is 16 kHz mel in, **24 kHz stereo** out of the vocoder: fine for
  ambience and foley, thin above ~12 kHz for UI clicks. Lightricks'
  `ComfyUI-LTXVideo` adds `LTXVAudioOnlyModel` (the video stream switched
  off) and a mask-by-time video-to-audio mode for **foley on a given clip**.
  `creator/sound.py` today says plainly there is no soundless mode.
- **Native core alternatives**, optional: Stable Audio 3 Small SFX (44.1 kHz,
  crisp short effects), ACE-Step 1.5 (music, MIT, under 4 GB).
- **Game-audio hygiene**: trim to a −50…−60 dBFS gate with short fades;
  loops by equal-power crossfade snapped to zero crossings, music loops cut
  to whole bars; loudness by BS.1770 to category anchors with a −1 dBTP
  true-peak ceiling (Sony ASWG-R001: −24 LUFS console, −18 mobile);
  variations as numbered sets, not baked randomness; 48 kHz 16-bit WAV
  masters, OGG Vorbis runtime copies, a `smpl` chunk for loop points.
- **Retro**: the honest version is transcription to four monophonic voices
  written as hUGETracker `.uge` (what GB Studio and GBDK play). The cheap
  version — resample, bitcrush, band-limit — only sounds the part.
- **MiniMax H3**: the research reports a community licence that excludes the
  US, EU, UK and South Korea from self-hosting. Unverified here (it came from
  secondary sources) and it matters for the whole pack, not only this bench;
  it is §13's first risk. Game Forge's audio does not default to H3.

### 3.7 Export conventions

- **2D:** PNG sheet + Aseprite-format JSON (frames, durations, `frameTags`,
  pivots as `slices`) is the one format Phaser, LÖVE, Unity importers and
  Godot plugins all read. Godot 4 `SpriteFrames` / `TileSet` are text
  `.tres` we can write directly. Tiled `.tsx` / `.tmj` for tilesets and maps.
  Pixel art: nearest filtering, no mipmaps, lossless.
- **Game Boy:** 160×144, 8×8 tiles, 4 shades, sprites 8×8 or 8×16 with three
  colours plus transparent, 40 sprites, 10 per line, about 192 unique
  background tiles in GB Studio. GBC: 8 background palettes of 4, 8 sprite
  palettes of 3 + transparent, RGB555. We emit indexed PNGs that
  `png2asset`, `rgbgfx` and GB Studio take as they are, and validate the
  budgets; we do not write our own compiler.
- **PBR:** glTF is base colour sRGB, ORM linear (R occlusion, G roughness,
  B metallic), OpenGL normals. Unreal: DirectX normals (flip G), `T_` names,
  ORM as masks. Unity HDRP mask map: R metallic, G AO, B detail, A smoothness
  (1 − roughness). Godot `ORMMaterial3D`: OpenGL normals, ORM as glTF.
  Power-of-two sizes, 2–8 px island padding, consistent texel density.

## 4. What the pack already has

| Need | Where it is |
|---|---|
| Stills, references, edits | The still families (`creator/families/*/still.py`, `creator/compile_image.py`): Qwen Image 2.1 up to 10 references cited as `<imageN>`, Qwen Image Edit and Flux 2 Klein up to 3, Krea 2 by reference LoRA, Ideogram 4.0 none. Canvas on a /16 grid, short edge 512–2048. |
| **Transparency** | **Qwen Image 2.1 generates a full alpha channel itself**: its VAE is 64 channels with alpha in and out (`families/qwen21/still.py:34-38`, `manifest.py:45`). BiRefNet in `creator/cutout.py` is the cleanup, and the fallback for families without alpha. |
| Guides | The tracing bench, `creator/control.py`: edges, lines, blocks, depth (Depth Anything 3), pose, matte (SAM3). Qwen Image Edit reads depth, edges and pose natively. No normal tracing. |
| Style | Preset scopes including `style` and `cast` (`web/creator/presets.js`), the 941-style atlas (`presets/atlas.js`, cast by `atlas:` address), RefMod for Klein (`creator/refmod.py`), LoRA stacks. |
| A 3D viewer | `web/creator/liftstage.js`: vendored three.js with GLTFLoader, textured/clay/wire/normals modes, `photo()` with depth, normals and mask passes from the framed camera, `turntable()`, a path tracer. |
| Image-to-3D | `creator/lift.py`: Pixal3D and TRELLIS.2 through core nodes, PBR bake via `UnwrapMesh` / `BakeTextureFromVoxel` / `BakeNormalMapFromMesh` / `BakeAmbientOcclusion`. GLB only, to `output/continuity/meshes/`. It textures only meshes it made. |
| Audio | LTX 2.5 and H3 audio VAEs, `vae_decode_audio` in `MiniMaxH3Reel`, PyAV writing in `creator/mux.py`, peaks and waveform drawing (`waveform.js`, `/continuity/peaks`). |
| Post | The upscale bench (`creator/upscale.py`: ESRGAN, SeedVR2), neural refine. |
| Planar warps | `creator/screens/` homography and `grid_sample` warp — a 2D quad, usable for decals, not for UV projection. |
| Plumbing | `jobs.register` / `submit` / `enqueue` / `progress`, `ContinuityJob`, `bench.hold` for weights, `styles/bench.js`, the dashboard's `destinations()` in `web/creator/fullscreen.js:856-951` ("a tool becomes reachable by becoming a card here"). |

**What is missing**, and is built here as general capability the rest of the
pack can use too:

1. **Alpha that survives to the file.** The 2.1 VAE carries it; the pack's
   save path (`MiniMaxH3SaveImage`, `prestage.py`) writes RGB. Find where the
   fourth channel is dropped and carry it through for 2.1. Then BiRefNet
   tightens it (§6.1).
2. **Seamless tiling** (§3.4), as a model wrapper any still family can take.
3. **Masked inpainting on stills.** No still family takes a mask. Seam
   repair, hole fill and layer cleanup all want one.
4. **Texturing an existing UV-mapped mesh** (§7.4).
5. **Sound without picture** (§8).
6. **A normal tracing**, for 2D lighting and as a control image.

## 5. The project

### 5.1 On disk

```
output/continuity/forge/<project>/
  project.json         style, targets, palette and grid, seeds, the asset list
  MANIFEST.md          written from project.json; never edited by hand
  style/               reference pictures, swatches
  assets/<kind>/<name>/
    recipe.json        what, from what, how, through which family, which post-steps
    masters/           the large originals, with alpha
    variants/          directions, frames, expressions, costumes, maps, takes
  build/<target>/      engine-ready output, regenerated from masters
  .versions/           sets replaced by a later write
```

Under `output/` because these are finished things a person goes looking for,
beside the renders — the upscale bench's reasoning. A project folder is
self-contained: zip it and it moves.

### 5.2 The style

Not a prompt suffix. A style is:

- **a clause** — from a `style` preset or an atlas entry, appended to every
  prompt, the skill's "one fixed style paragraph";
- **reference pictures** — the style sheet, cast as references wherever the
  family takes them, as a RefMod where the family has one;
- **LoRAs**;
- **seeds** — one per character, one per set;
- **a render mode** — `painted`, `flat`, `toon`, `pixel`, `pbr`. The mode
  decides the post-chain an asset gets by default (§6). `pixel` brings a
  grid size and a palette with it; `pbr` brings texel density.

### 5.3 Targets

A project has one or more targets, and a target is a profile: an export
writer, limits to validate against, and the conversions it needs from the
masters. v1 profiles: **Generic** (PNG + Aseprite JSON), **Godot 4**,
**Tiled**, **LÖVE**, **Game Boy** (DMG), **Game Boy Color**, **GB Studio**,
**glTF/PBR** with Unreal and Unity HDRP switches. A target never changes a
master; it only reads them.

### 5.4 The manifest

Every asset, one row: kind, name, file, size, alpha, depth or layer, pivot,
seed, family, full prompt, status (planned / made / exported / stale). It is
the skill's MANIFEST.md, generated. A planned row with no files is a
placeholder; "make what is missing" queues every planned row. An asset whose
recipe changed after its files were made is **stale**, and says so.

## 6. Post-steps

Shared by every kind, chosen by the render mode, each a pure function of
masters → files with its own test. Cheap ones preview live.

1. **Matte.** For Qwen Image 2.1, its own alpha, then BiRefNet as a
   tightening pass: the two mattes are combined (the model's alpha where it
   is confident, BiRefNet's at the uncertain edge) rather than one replacing
   the other. For every other family, BiRefNet alone on a flat backdrop.
   SAM3 point prompts when a part needs rescuing.
2. **Alpha bleed.** Edge colours pushed into transparent texels.
3. **Baseline and pivot.** Frames aligned on a common foot line; pivots
   stored, not guessed later.
4. **Colour match.** Each frame or view histogram-matched to the set's first.
5. **Pixelize** (`pixel` mode): grid detection, mode-of-cell downscale,
   palette quantisation at the target size, optional ordered dither, orphan
   removal.
6. **Constraint check** per target: colours per tile, palettes, unique tiles
   (with flips on Game Boy), sprites per line, texture sizes. Violations are
   drawn on the picture, not listed in a log: "tile (3, 2) needs 5 colours".
7. **Atlas pack** with extrude and spacing per target; ≤ 2048.
8. **PBR derive** (`pbr` mode, §7.3).

## 7. The workshops

The bench has one tab per kind. Each is a recipe editor, a light box, and the
same foot that runs a job and says what came of it.

### 7.1 Characters and sprites

1. **Model sheet.** Text → still with the project style. Neutral pose, arms
   away from the body, mouth closed, eyes open (the skill's sheet).
2. **Variants** are edits of the sheet on the same canvas: costumes,
   expressions (face-only crop, edit, feathered paste-back — VNCCS's method,
   our code), held items.
3. **Directions**: 4 or 8, by the Multiple-Angles LoRA when installed, or by
   the 3D route (§3.5) when consistency matters more than time.
4. **Frames**: walk, idle, attack and the rest, generated as **one grid
   image** per animation so the frames share identity, then split.
5. Post-chain, then the animation's metadata (durations, tags, pivots).

For HD cutout characters (the skill's rig): parts with joint overlap, nine
mouths, three eyes, pivots, and a starting `rig.lua`.

### 7.2 Tiles and tilesets

Seamless generation (§3.4), terrain sets, trim sheets (tiling on one axis).
Tiles are de-duplicated, with flips on targets that support them, and counted
against the target's budget live. Export: Tiled `.tsx`, Godot `TileSet`,
Game Boy tile data via indexed PNG.

### 7.3 Materials

Seamless base colour from the style; height and normal derived from it
(luminance and Sobel — arithmetic, live), roughness and metallic heuristic by
default. When an intrinsic-decomposition model is installed (Marigold-IID,
RGB↔X), it replaces the heuristic. Packing is the target's business (§3.7).

### 7.4 Texturing an existing model

Input: a GLB from the lift shelf or uploaded, and OBJ through a small parser
of our own (a format simple enough not to need a library). The mesh must have
UVs; one without them is offered core's `UnwrapMesh` first.

1. **Render passes** server-side, per orthographic camera (4–6, framed on
   the bounds): depth, normal, triangle id, UV. A pure-torch rasteriser for
   meshes under ~100k triangles; core's `RenderMesh` where it serves.
2. **Generate** all views in one grid image with depth control, each tile
   prompted with its direction ("back view of…"), the front view as a
   reference.
3. **Delight**: prompt for flat even light; decompose when a model is
   installed.
4. **Back-project, texel by texel**: rasterise in UV space for each texel's
   position and normal; for each view, a shadow-map visibility test, a
   bilinear sample, weight `max(0, N·v)^k` with an eroded silhouette falloff
   and `N·v` clamped above ~0.2; accumulate and normalise.
5. **Fill** what no view saw: push–pull first; then, for large holes, a new
   camera aimed at the hole and step 4 again.
6. **Dilate** the islands 8–16 texels.
7. **Refine**: render the textured mesh, low-denoise (0.2–0.35) with depth
   control, reproject. One or two rounds.
8. **Bake** normal and AO from the geometry with core's nodes; apply; write
   GLB; preview in `liftstage.js`.

Later: **paint from here** — project from wherever the viewer's camera is,
StableProjectorz-style, with `photo()`'s depth, normals and mask as the
control images.

### 7.5 Backgrounds and parallax

One scene, sliced into layers by depth (Depth Anything 3 from the tracing
bench) and matte, the gaps behind each layer filled by masked edit, named
`NN_name` back to front. Far layers tinted toward the sky. Wrapping layers
tile on X. On Game Boy, the map is checked against 32×32 tiles and the tile
budget.

### 7.6 UI, icons and items

Sets generated as one grid for a shared look, split, matted. Panels exported
9-slice. Bitmap fonts later.

### 7.7 Sound

§8.

## 8. Audio

**Kinds**, each with defaults: UI (50–400 ms, mono), footsteps (6–10
variations per surface, mono), impacts (mono), ambience (30–60 s stereo
loop), music (N bars, stereo loop), barks (mono, dialogue anchor), and
**foley for an animation**.

**Engines**, chosen per kind, all optional beyond what the pack has:

- **LTX 2.5, audio only**, through `LTXVAudioOnlyModel` when
  `ComfyUI-LTXVideo` is installed. Without it, the fallback is a full AV
  render at the smallest legal picture with the picture discarded: slower,
  honest about why, and it works today.
- **LTX 2.5 foley**: the animation is rendered to a clip (the blockout
  bench's frames → mp4 route already does this), then scored with
  mask-by-time video-to-audio.
- **Stable Audio 3 Small SFX** and **ACE-Step 1.5** when core has them.
  Short UI sounds default to Stable Audio when it is present, because of
  LTX's 24 kHz ceiling.

**Post**, numpy and PyAV: trim and fades, loop crossfade at zero crossings,
bar-exact music loops (tempo by onset autocorrelation, no librosa), a
BS.1770 loudness meter of our own with category targets and a −1 dBTP
limiter, numbered variation sets (seeds, ±1–3 semitones, ±1–2 dB), 48 kHz
16-bit WAV masters with `smpl` loop chunks, OGG copies, Godot loop fields.

**Retro**: resample and bitcrush in v1; `.uge` transcription later.

## 9. Exports in v1

1. PNG sheet + Aseprite JSON.
2. Godot 4 `SpriteFrames` and `TileSet` `.tres`.
3. Tiled `.tsx` / `.tmj`.
4. LÖVE: the Aseprite JSON plus a Lua quads table.
5. Game Boy / GBC / GB Studio: indexed PNGs, validated.
6. PBR sets in glTF convention with Unreal and Unity HDRP switches; textured
   GLB.
7. Audio as §8.

Later: Unity `.meta`, Unreal `.uasset`, Wwise and FMOD projects (they take
WAVs anyway), `.uge`.

## 10. Architecture

- **Python** `creator/forge/`: `project.py` (storage, versions, manifest),
  `style.py`, `kinds/<kind>.py` (recipe → job body), `post/` (`matte.py`,
  `bleed.py`, `pixelize.py`, `constraints.py`, `atlas.py`, `tiling.py`,
  `pbr.py`, `loop.py`, `loudness.py`), `uv/` (`raster.py`, `project.py`,
  `fill.py`), `export/<target>.py`. No ComfyUI or torch imports at module
  scope where tests need the module.
- **Routes** `creator/routes/forge.py` under `/continuity/forge/*`: project
  CRUD, asset recipes, previews (GETs), runs (`jobs.submit("forge", …)` or
  `jobs.enqueue` for pipelines), exports. Imported from the root
  `__init__.py`.
- **Nodes**: none user-facing in v1. Internal stage nodes, if a pipeline
  needs them, are `Continuity/internal` and `is_dev_only`, the lift pattern.
- **Frontend** `web/creator/forge.js` and `forge/*.js`, the bench room from
  `styles/bench.js`, a card in `destinations()` with art in `cards/`. Strings
  through `t()`, with the three locales.
- **CLI** `skills/continuity-forge/forge.py` and `SKILL.md` (§11), beside
  `continuity-render`.
- **Tests**: plain scripts in `tests/` on `harness.py`; golden images for
  pixelize, atlas, bleed and projection; a golden manifest; the exporters
  checked against fixture files.

## 11. Agents and the CLI

The pack already has the pattern: `skills/continuity-render/` is a Claude Code
skill plus `render.py`, a standard-library client of `/continuity/render`.
The server builds the render; the client uploads, queues, waits and downloads,
prints paths on stdout and progress on stderr, and exits non-zero with the
server's own sentence. Game Forge ships the same way, as
`skills/continuity-forge/` with `SKILL.md` and `forge.py`.

### 11.1 Why agents need more than the render client

A render is one request. A game's art is hundreds of assets that must agree,
built over many sessions, and an agent cannot see the bench. So the CLI has
to give an agent three things the render client does not:

- **A plan it can write down.** The project and its assets are data, and the
  agent edits data rather than driving a UI.
- **Eyes.** Every result comes with something an agent with vision can read:
  a contact sheet, a constraint overlay, a waveform. And every result comes
  with numbers an agent without vision can act on.
- **Resumability.** Jobs outlive the shell that started them, and the
  project says what is made, what is missing and what is stale, so the next
  session picks up where the last one stopped.

### 11.2 Declarative first

The main way an agent works is to write a **plan** and apply it:

```
forge.py new mygame --mode pixel --target gb-studio --target godot4
forge.py plan mygame plan.json           # merge assets into the project; idempotent
forge.py status mygame                   # planned / made / stale / failing checks
forge.py make mygame --missing           # queue every planned asset
forge.py check mygame --json             # constraint violations, per asset
forge.py export mygame godot4 --pull ./game/assets
```

A plan is the project's own asset list in JSON: kind, name, prompt, sizes,
references, seed, target overrides. Applying it is a merge by asset name, so
running it twice changes nothing and editing one entry marks only that asset
stale. `forge.py schema <kind>` prints the JSON schema for a kind's recipe,
so an agent never guesses field names. This is the lua-25d-game skill's
manifest step made executable: the agent writes the asset list once, and the
forge turns it into files.

### 11.3 The commands

Every route has a command; these are the groups.

| Group | Commands |
|---|---|
| Discovery | `capabilities` (families, optional packs, engines per kind — the forge's `families`), `targets`, `modes`, `schema <kind>` |
| Projects | `projects`, `new`, `show`, `style` (clause, references, LoRAs, seeds, mode), `target add/rm` |
| Assets | `plan`, `add`, `edit`, `rm` (moves to `.versions/`, never deletes), `status`, `history <asset>` |
| Making | `make <asset…>`, `make --missing`, `make --stale`, `vary <asset> --n`, `post <asset> <step…>` |
| Looking | `sheet <asset>` (contact sheet PNG), `check` (overlay PNG + JSON), `sound-report` (loudness, peak, loop seam error, waveform PNG) |
| 3D | `texture <mesh> <recipe>`, `views <mesh>` (the depth and normal renders it will condition on) |
| Moving files | `import` (pictures, meshes, sounds into the project), `export <target>`, `pull` (download `build/<target>/` or the whole project) |
| Jobs | `jobs`, `wait <id>`, `cancel <id>` |

### 11.4 The contract

- **Standard library only**, Python 3.9+, self-contained in the skill folder,
  runs on the ComfyUI machine or anywhere that can reach its port. The same
  server etiquette as `continuity-render`: ask for the URL, never scan.
- **stdout is data.** Paths one per line by default; `--json` on every
  command for a structured answer. Progress on stderr.
- **Refusals are sentences** with a machine-readable code beside them
  (`{"problem": "...", "code": "budget.tiles", "asset": "...", "at": [3, 2]}`),
  so an agent can branch on the code and relay the sentence.
- **`--no-wait`** queues and prints job ids; `wait` resumes. Jobs are
  ComfyUI prompts, so they survive the client.
- **Dry runs.** `make --dry-run` prints what would be queued and the
  estimated cost (renders, frames, seconds of audio) before anything runs.
- **Never destructive.** `rm` and every overwrite go through `.versions/`.
  There is no command that empties a project.

### 11.5 What the skill teaches

`SKILL.md` is the agent's manual, written like the render skill's: start with
`capabilities`; write a plan rather than many `add` calls; generate the
**model sheet first** and look at it before making variants; run `check`
after every `make` and fix what it reports; look at the `sheet` before
claiming what anything looks like; one job at a time on a shared GPU; report
seeds. It cross-references the lua-25d-game skill for LÖVE projects and the
render skill for anything that is a shot rather than an asset.

### 11.6 Parity, tested

A test enumerates the routes registered under `/continuity/forge/` and the
CLI's command table and fails on any route with no command. A second runs the
CLI against a stub server for each command and checks stdout, `--json` and
exit codes. Golden JSON for `status`, `check` and `schema` keeps the
contract stable for agents that have learned it.

## 12. Sequencing

1. **Foundation.** Project storage and manifest, targets, the dashboard card,
   alpha carried to the file for 2.1, post-steps 6.1–6.7, exports 1–5. Works
   on pictures made anywhere — immediately useful for a Game Boy project.
   The CLI and its skill ship in this step, not after: every route lands
   with its command, and the parity test from day one.
2. **2D generation.** Style, characters and sprites, tiles with seamless
   tiling, icons, masked inpainting.
3. **Audio.**
4. **Materials and model texturing.** A one-mesh spike of §7.4 runs early,
   in parallel with 2, because it is the biggest unknown: the grid-of-views
   route is plausible and unproven on these families.
5. **Backgrounds and parallax, HD rigs, `.uge`, further engines.**

## 13. Risks

- **The MiniMax H3 licence** (§3.6) is reported, not verified, and bears on
  the whole pack. Check the licence text before anything else.
- **Node names** (`LTXVAudioOnlyModel`, `RenderMesh`, the bake nodes) come
  from research that could not reach the docs. Each is verified against an
  install before it is wired, and each path has a fallback that does not need
  it.
- **Grid-of-views consistency** may not hold on Qwen Image Edit at 4–6
  views. The spike decides; sequential projection is the fallback.
- **Pixel conversion** is only as good as the 1024 picture. The constraint
  check makes failure visible; a pixel touch-up editor may be wanted later.
- **Agents acting blind.** An agent that never looks will ship a sheet
  that passes every check and looks wrong. The skill makes `sheet` part of
  the loop, and `status` marks an asset nobody has viewed since it was made.
- **Scope.** v1 is §12 steps 1 and 2. Everything else waits until those are
  used.

## 14. Not in v1

Rigging beyond a starting `rig.lua`, skeletal animation, LoRA training of a
character, an identity-similarity score, `.uge`, engine-native binaries,
level layout beyond Tiled export, voice cloning.

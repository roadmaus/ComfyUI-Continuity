# Continuity — Game Forge

Spec for a new bench. High level: architecture and decisions, not code.
Written 2026-10-05 against `main` at `6347afe`, after the research in §3 and
§4. Revised 2026-10-06 against `00a9a8f`: posing through VNCCS Pose Studio
(§3.9, §7.9): a pose stage on VNCCS Pose Studio's vendored viewer and
its pose LoRAs, and Qwen Image Edit dropped in favour of Qwen Image 2.1 throughout.
Corrected the same day after vendoring at VNCCS Utils `eedaed7`: the pose
library is not vendored, the modules are copied as `.mjs`, and the mannequin
is loaded by the core's client. Then the lab spike of the QI2.1 pose LoRA
(§12): frames are rendered as one grid, not one render per pose (§7.1).
Then the render job was built (§7.9, §12): what it does, what it stores, and
that imported clips come in place.

## 1. Summary

A bench reached from the tools dashboard where a game's assets are made: the
characters and their animation frames, tiles and tilesets, materials,
3D models with clean quad topology, textures for 3D models that already exist, backgrounds, icons and UI, sound
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
   the views. No multi-view adapter: the depth grid is one guide through
   Qwen Image 2.1's Fun ControlNet-Union branch.
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

Directions: the same pose turned in Pose Studio, one render per azimuth, each
drawn onto the character by the pose LoRA (§3.9). The Multiple-Angles LoRA
is not used: it is a Qwen Image Edit LoRA. Or, more consistent,
lift the sheet to a mesh, texture it, and render 8 directions from a fixed
orthographic camera.

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

### 3.8 Retopology

A lifted mesh is dense, triangulated and sometimes non-manifold: fine to look
at, wrong to animate, UV or ship. Game models want a clean, low,
**quad-dominant** mesh whose edges follow the form — what ZBrush's ZRemesher
does. The detail is not lost: it is baked from the dense mesh onto the clean
one as normal and AO maps.

- **Core has the triangle half and the bake, not quads.** `RemeshMesh` is a
  narrow-band distance field and dual contouring (`udf` is robust to
  non-manifold input), `DecimateMesh` is QEM to an exact face count,
  `UnwrapMesh` is a torch/scipy unwrap, and the bakes take a high and a low
  poly. The lift already chains these (`creator/lift.py:446-503`). No core
  node makes quads.
- **The field-aligned methods are the practical route.** Instant Meshes
  (BSD-3) solves an orientation field and a position field on the surface and
  extracts quads from them; QuadriFlow (MIT) adds a flow step that removes
  singularities; QuadWild (GPL-3) traces feature lines first and has the most
  artist-like flow. Controls across them: target count, crease angle,
  quad-dominant or pure quad, boundary alignment; symmetry only in Blender's
  QuadriFlow; density painting in none of the free ones.
- **Python wrappers exist**: `pynanoinstantmeshes` (BSD, prebuilt wheels;
  already used by Stable Fast 3D and kijai's Hunyuan3D wrapper) and
  `pyQuadriFlow`. Both are small, one-maintainer projects.
- **Neural "artist mesh" models are not ready to be the default.**
  MeshAnything V2 caps at 1,600 faces and is non-commercial; DeepMesh (Apache
  2.0) reaches ~30k faces but is slow and heavy; BPT is in Hunyuan's wrapper;
  QuadGPT, Meshtron and QuadLink have no local weights. Mostly triangles.
  Watched, not built on.
- **Our own is feasible**: a simplified Instant-Meshes pipeline in torch —
  hierarchy, 4-RoSy orientation field, 4-PoSy position field, extraction — is
  about 2–3k lines and 2–4 weeks to usable. Extraction is most of the work
  and most of the bugs (holes, T-junctions, flipped quads near singularities
  and thin parts). It runs after core's remesh and decimate have produced a
  clean manifold of 50–150k triangles, which removes the worst inputs.

All of this comes from search results; the research could not open the
licence files or package pages. Licences and wheel platforms are checked
before anything is wired.

### 3.9 Posing: VNCCS Pose Studio and its LoRAs

A sprite set is one character in many poses, and a prompt is a poor way to
say "this pose". VNCCS's answer is the one the forge takes: pose a 3D
mannequin, render it, and have a LoRA redraw the character in the
mannequin's pose. Read from source (ComfyUI_VNCCS `9ee83cd`,
ComfyUI_VNCCS_Utils `eedaed7`, both MIT).

**Pose Studio** is `VNCCS_PoseStudio` in **VNCCS Utils**, not the main
VNCCS repo. One node holds several pose tabs and up to four characters
(MakeHuman body sliders, CC0 mesh), a camera and lights. It outputs
`images` (one per tab in LIST mode, or one pasted grid in GRID mode) and
`lighting_prompt`, a sentence per image describing the light and camera.
What it draws is **a lit, skin-textured mannequin on a flat background**
(white by default), not an OpenPose skeleton, at the tab's `view_width ×
view_height` (VNCCS's own workflow: 640×1536). Skins: `naked`,
`naked_marks` (orientation crosses on torso and face), `dummy_white`. The
`pose_data` widget is JSON, schema 3: per pose, sparse bone Euler rotations
on Unreal-style bone names, the model's rotation, the camera. It imports
OpenPose, HMR2, RTMW, MeTRAbs and Mixamo FBX poses, and a picture through
SAM 3D Body.

**Its rendering is browser-only.** `nodes/pose_studio.py` says so in its
header: MakeHuman morphing, skinning, posing and rendering all run in the
browser, and the backend renderer was removed. The node asks the tab holding
*that node on its canvas* (`app.graph.getNodeById`) for captures and fails
without one.

**What it already does, and the forge will not redo.** The work is in a few
plain modules under `web/`, and only the 16k-line `PoseStudioWidget` around
them is tied to ComfyUI's graph:

- `vnccs_pose_studio_core.js` exports `PoseViewerCore` (load the mannequin,
  body morphs, bones, IK, lights, camera, capture) and `AnalyticIKSolver`;
- `vnccs_pose_animation.mjs`: the timeline, local-quaternion keys,
  interpolation presets, frame sampling at an FPS (default 12);
- `vnccs_mixamo_import.js`: **Mixamo FBX → retargeted clip on the
  mannequin**, through three.js's `FBXLoader`, with the bone map and the
  rest-pose correction;
- `vnccs_openpose_import.js`, `vnccs_hand_presets.js`,
  `vnccs_pose_characters.mjs`, `vnccs_pose_morph_runtime.mjs` (+ worker);
- the mannequin `web/assets/pose_studio_makehuman.v2.bin.gz` (38 MB:
  MakeHuman mesh, morphs, rig, weights, **CC0**) and the skins
  `web/textures/skin.png`, `skin_marks.png`, `skin_dummy.png` (10 MB, under
  the repo's **MIT**).

The mannequin reaches the core through the widget, not the core itself:
`PoseStudioWidget` decodes the pack (`loadMorphPack`), solves the body
sliders in the morph worker (`solveMorph`) and hands the result to
`PoseViewerCore.loadData`. A client of the core does those two steps itself.

Ready poses are not in the repo. Upstream's server downloads them from the
Hugging Face dataset `MIUProject/VNCCS_PoseLibrary_Main` (and a second user's
dataset), and neither declares a licence.

**So the forge vendors it** (§7.9), the way the pack carries `h3lora`,
`mlxdlss` and `vdnh3`: copied by a script, local fixes held as a patch and
marked `# MMC:` (`// MMC:` in JavaScript), the upstream revision stamped in, credited in the README.
Everything VNCCS Utils is MIT and its mesh CC0, so this is allowed with the
notices kept. Using the installed pack instead was rejected: its updates
could break the forge without a change on our side, and installing it brings
its own requirements (SAM 3D Body and the rest) for a viewer that needs none.

(PoseStudio/PoseStudio on GitHub is an unrelated project: a native C++/Qt/
Vulkan desktop poser, Windows-only, GPL-3. Nothing from it is used.)

**The pose LoRAs** (AHEKOT, Hugging Face org `MIUProject`) are trained to
read that mannequin as reference 1 and the character as reference 2. No
trigger words; strength 1.0 in every workflow and in VNCCS's code.

| Family | File | Where | How VNCCS drives it |
|---|---|---|---|
| **Qwen Image 2.1** | `VNCCS_QI2_PoseStudioV1.1.safetensors` | `MIUProject/VNCCS_PoseStudio_QI2.1` (no licence in the card); Civitai 2957080 (commercial use allowed) | `TextEncodeQwenImage21` with images `(pose, character)`, an empty latent at the pose's size scaled to ~1 MP, cfg 1, euler/simple; in UniCanvas with the Viggle turbo LoRA (`Qwen-Image-2.1-viggle-turbo-v0.2.1-6step`) at 6 steps. Prompt, verbatim: `Replace the pose of <image 2> with the pose of <image 1>. Keep the character of <image 2>. ` + the per-pose prompt + `Transparent background with alpha channel.` |
| **MiniMax H3** | `VNCCS_PoseStudioH3_V1.safetensors` | `MIUProject/VNCCS_v3.0`, `models/loras/MiniMaxH3/VNCCS/` (Apache-2.0). VNCCS's own catalogue points at a path that 404s. | `MiniMaxH3ReferenceToVideo`, `ref_image_1` = pose, `ref_image_2` = character, 5 frames at the pose's aspect, ~1.5 MP, /32; frame 0 kept. Needs the audio VAE too. |
| Flux 2 Klein 9B | `VNCCS_PoseStudioKlein9b_V2.2` | `MIUProject/VNCCS_v3.0` | Not used here. |
| Qwen Image Edit 2511 | `VNCCS_QIE2511_PoseStudio_ART_*` | `MIUProject/VNCCS_PoseStudio` | Not used: retired in VNCCS itself, and the forge does not use Qwen Image Edit. |

VNCCS as a whole, from its README, against where the forge stands:

| VNCCS | The forge |
|---|---|
| Character Creator (Illustrious, Anima, Qwen 2.1; style library with previews; wizard) | §7.1 model sheet with the project style (§5.2, the 941-style atlas). No SDXL-era families. |
| Character Cloner (start from an existing picture) | A model sheet may be an imported picture; the posed-variant step does the rest. |
| Pose Studio | §7.9: its viewer, FBX import and animation vendored, our bench page and render job around them. |
| Clothes Designer, clone clothes from a picture | §7.1 variants, ClothesCore when installed; the garment picture is a third reference. |
| Emotion Studio (face crop, edit, paste back) | §7.1 variants, same method. |
| BG Remove (chroma presets, SAM3 detail recovery) | §6.1: 2.1's own alpha + BiRefNet, SAM3 point rescue. No green screen needed on 2.1. |
| Control Center (model downloads) | Out of scope; refusals name the file and its URL. |
| Output folder of PNGs | Engine exports and a manifest (§5, §9). |

Two sibling LoRAs follow the same contract and serve §7.1's variants:
**ClothesCore** (QI2 V2.6, H3 V1; "Dress character to clothes from image 2")
and, for expressions, no LoRA at all on QI2 — VNCCS crops the face and
prompts the emotion, which is what §7.1 already does.

What this means for the forge:

- **Pose LoRA routing is the family's business, by file name**, so it works
  as soon as the file is in `models/loras`: a render with a pose attached
  loads the newest `*PoseStudio*` LoRA for the family's base (`VNCCS_QI2_` for
  2.1, `H3` for H3) at 1.0, and refuses with the file name and its Hugging
  Face URL when there is none. No hidden fallback to an unposed render.
- **References go in VNCCS's order**, pose first, character second, and the
  canvas is the pose's. That is the order Qwen Image 2.1 already wants: its
  first picture is the one being redrawn.
- **The prompt is VNCCS's sentence verbatim**, `<image 2>` with its space,
  not passed through the pack's `<imageN>` citation: it is what the LoRA was
  fitted on, and the 2.1 tokenizer adds its own picture markers regardless.
- **The render is theirs, unchanged.** The LoRAs learned Pose Studio's
  captures, and the vendored `PoseViewerCore` makes exactly those: same
  mesh, skins, lights and background. The `// MMC:` patches touch loading and
  wiring, never the look.
- **`pose_data` schema 3 is the pose format**, because it is their code's
  own. A pose made in Pose Studio pastes into the forge and back.
- **The mannequin is not a tracing.** The Fun ControlNet-Union pose branch
  reads an OpenPose skeleton and would read the mannequin as a picture. The
  two pose routes stay separate and named: *mannequin* (our stage + LoRA),
  and *pose from a picture* (SDPose skeleton from the tracing bench + the
  ControlNet branch, for when the pose comes from a photo or a frame).

## 4. What the pack already has

| Need | Where it is |
|---|---|
| Stills, references, edits | The still families (`creator/families/*/still.py`, `creator/compile_image.py`): Qwen Image 2.1 up to 10 references cited as `<imageN>`, Qwen Image Edit and Flux 2 Klein up to 3, Krea 2 by reference LoRA, Ideogram 4.0 none. Canvas on a /16 grid, short edge 512–2048. |
| **Transparency** | **Qwen Image 2.1 generates a full alpha channel itself**: its VAE is 64 channels with alpha in and out (`families/qwen21/still.py:34-38`, `manifest.py:45`). The pack's save node writes the decoded picture as it is, so a 2.1 still lands as an RGBA PNG. BiRefNet in `creator/cutout.py` is the cleanup, and the fallback for families without alpha. |
| Guides | The tracing bench, `creator/control.py`: edges, lines, blocks, depth (Depth Anything 3), pose, matte (SAM3). Qwen Image 2.1 follows edges, lines, depth, pose and luma through the Fun ControlNet-Union branch (`families/qwen21/still.py`). No normal tracing. |
| Poses | Nothing yet; VNCCS Pose Studio's viewer, FBX import and animation are vendored for the pose stage (§7.9). Not dependent on VNCCS being installed. The pose LoRAs load through the core LoRA stack on 2.1 and `h3lora` on H3; both paths are checked with the VNCCS files before they are wired. |
| Style | Preset scopes including `style` and `cast` (`web/creator/presets.js`), the 941-style atlas (`presets/atlas.js`, cast by `atlas:` address), RefMod for Klein (`creator/refmod.py`), LoRA stacks. |
| A 3D viewer | `web/creator/liftstage.js`: vendored three.js with GLTFLoader, textured/clay/wire/normals modes, `photo()` with depth, normals and mask passes from the framed camera, `turntable()`, a path tracer. |
| Image-to-3D | `creator/lift.py`: Pixal3D and TRELLIS.2 through core nodes, PBR bake via `UnwrapMesh` / `BakeTextureFromVoxel` / `BakeNormalMapFromMesh` / `BakeAmbientOcclusion`. GLB only, to `output/continuity/meshes/`. It textures only meshes it made. |
| Audio | LTX 2.5 and H3 audio VAEs, `vae_decode_audio` in `MiniMaxH3Reel`, PyAV writing in `creator/mux.py`, peaks and waveform drawing (`waveform.js`, `/continuity/peaks`). |
| Post | The upscale bench (`creator/upscale.py`: ESRGAN, SeedVR2), neural refine. |
| Planar warps | `creator/screens/` homography and `grid_sample` warp — a 2D quad, usable for decals, not for UV projection. |
| Plumbing | `jobs.register` / `submit` / `enqueue` / `progress`, `ContinuityJob`, `bench.hold` for weights, `styles/bench.js`, the dashboard's `destinations()` in `web/creator/fullscreen.js:856-951` ("a tool becomes reachable by becoming a card here"). |

**What is missing**, and is built here as general capability the rest of the
pack can use too:

1. **Seamless tiling** (§3.4), as a model wrapper any still family can take.
2. **Masked inpainting on stills.** No still family takes a mask. Seam
   repair, hole fill and layer cleanup all want one.
3. **Texturing an existing UV-mapped mesh** (§7.4).
4. **Sound without picture** (§8).
5. **A normal tracing**, for 2D lighting and as a control image.
6. **Quad retopology** and the rest of making a mesh game-ready: LODs,
   collision, scale and pivot (§3.8, §7.6).
7. **A pose stage** (§7.9): Pose Studio's viewer vendored, frames rendered
   in any open tab on request, and the render used as a recipe input that routes the family's pose LoRA, puts
   itself first among the references and sets the canvas. Any still render
   can take one, not only the forge's.

## 5. The project

### 5.1 On disk

```
output/continuity/forge/<project>/
  project.json         style, targets, palette and grid, seeds, the asset list
  MANIFEST.md          written from project.json; never edited by hand
  style/               reference pictures, swatches
  poses/<set>.json     a pose set: pose_data per pose, frame timing for an
                       animation; renders are derived, cached under build/
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

Everything below is Qwen Image 2.1 by default, H3 where the recipe says
so; both carry a VNCCS pose LoRA (§3.9).

1. **Model sheet.** Text → still with the project style. Neutral pose, arms
   away from the body, mouth closed, eyes open (the skill's sheet). Or, to
   fix the proportions first, the stage's A-pose (§7.9) drawn onto a prompted
   character by the pose LoRA.
2. **Poses.** A pose set made on the pose stage (§7.9), or written as
   JSON by an agent, or pasted from Pose Studio.
3. **Posed variants.** Sheet + mannequin render → the character in that
   pose, pose LoRA at 1.0, VNCCS's sentence plus the style clause. Same
   seed across a set. A single pose (a model sheet's A-pose, a portrait) is
   one render; a set of frames is a grid (step 6).
4. **Variants** are edits of the sheet or a posed variant on the same
   canvas: costumes (ClothesCore when installed), expressions (face-only
   crop, edit, feathered paste-back — VNCCS's method, our code), held items.
5. **Directions**: 4 or 8 — one pose, the model rotation stepped per
   azimuth on the stage, through step 3; or the 3D route (§3.5) when consistency matters
   more than time. A direction shows only what faces the camera: a lantern
   on the far hip is correctly absent from a side view, so the sheet must
   show what each side carries, or the opposite direction invents it.
   Untested: whether the mirrored walk draws the far side's items from a
   front-only sheet.
6. **Frames**: walk, idle, attack and the rest, as a pose set with one pose
   per frame, rendered as **one grid**: the frames' mannequins side by side
   in one canvas, the sheet as the second reference, one render, split
   back into frames by cell. Proven on the lab (§12): one render per frame
   follows each pose but not its framing — the LoRA reframes compact poses
   (a walk's passing frames) to fill the canvas, so scale jumps from frame to
   frame. The grid keeps one scale, one baseline and one identity, and
   follows the poses more closely. The canvas is the large one, about 2 MP
   for four frames (1936×1088 at 16:9, cells ~470 px wide): at 1280×720 a
   busy costume loses detail (a cape shrank to a collar). Longer sets are
   split into grids of four sharing seed and sheet, held together by the
   colour match (§6).
7. Post-chain, then the animation's metadata (durations, tags, pivots).

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

### 7.6 3D models

The lift bench already turns a picture into a textured mesh. The forge does
not copy it: it **calls `lift.build`** with the project's pictures and keeps
the result in the project, and then does what the lift bench does not —
makes the mesh game-ready. A model is an asset like any other, with a recipe,
masters and variants.

1. **Source.** A concept or model sheet from the project (§7.1), so the
   model has the project's style. When the character workshop has made the
   front, left, back and right views, they feed Pixal3D's multi-view rig
   directly — the same views, now doing a second job.
2. **Lift**, through `lift.build` and `jobs.enqueue`, unchanged: Pixal3D or
   TRELLIS.2, at the lift's detail settings. The dense result is kept as the
   model's **high poly** and never edited.
3. **Retopology**, one of three, chosen per asset:
   - **Triangles** (always available): core `RemeshMesh` and `DecimateMesh`
     to a face budget. What the lift does today.
   - **Q-Remesh** (quad-dominant): the forge's quad remesher, with target
     faces, crease angle, quad-dominant or pure quad, boundary alignment and
     symmetry. It runs on whichever backend the machine has, best first:
     an **external tool** the user has pointed the pack at in its settings
     (Instant Meshes, QuadWild, or Blender for its QuadriFlow with symmetry —
     run as a subprocess, which is also what keeps GPL code out of the pack);
     then **`pynanoinstantmeshes` or `pyQuadriFlow`** if installed, detected
     at runtime like any optional pack; then **our own** torch
     implementation (§3.8), which is always there once it exists. The
     result says which backend made it.
   - **Keep** the lifted mesh as it is.
4. **UVs.** Core `UnwrapMesh` on the triangulated low poly; the quad topology
   is kept beside it for the formats that can carry quads.
5. **Surface.** Either bake the lift's own texture across (base colour,
   metallic, roughness from the voxels, as `_bake` does now), or paint it
   with §7.4, which is the better route when the style matters. Then normal
   and AO baked from the high poly onto the low, with a cage distance of
   1–2 % of the bounds and the target's normal convention.
6. **Game-ready.**
   - **Scale and pivot:** a real-world height in metres, the pivot at the
     bottom centre unless the recipe says otherwise, Y-up for glTF.
   - **LODs:** `DecimateMesh` at 100/50/25/12.5 % by default, named
     `_LOD0…_LODn`. Whether core's decimate can hold UV seams fixed is to be
     checked; if not, LODs are decimated before the unwrap and each is baked.
   - **Collision:** a convex hull (`scipy.spatial.ConvexHull`), or a box or
     capsule fit, named `UCX_<name>_NN` for Unreal. Convex decomposition is
     later.
7. **Checks**, the mesh version of §6.6: face budget per LOD, non-manifold
   edges, holes, UV overlap and texel density against the project's
   density, bake artefacts as a heat map.
8. **Look.** The lift stage (`liftstage.js`) shows it: textured, clay, wire
   and normals, with the quad wire drawn from the kept topology rather than
   the triangles glTF stores. For agents, `sheet` writes a turntable contact
   sheet with a wire row.

The project's style carries into 3D the same way it does into 2D: the
source pictures are made in the style, and the paint step (§7.4) uses the
same clause, references and seeds.

### 7.7 UI, icons and items

Sets generated as one grid for a shared look, split, matted. Panels exported
9-slice. Bitmap fonts later.

### 7.8 Sound

§8.

### 7.9 The pose stage

VNCCS Pose Studio's viewer, FBX import and animation, vendored (§3.9), on a
page of the forge bench. Every workshop that wants a figure — sprites,
directions, frames, a model sheet's proportions — gets one without a second
pack installed.

**Vendored, not rewritten.** `tools/vendor_posestudio.py` copies from a
VNCCS Utils checkout into `web/creator/vendor/posestudio/`: the core, the
animation, Mixamo and OpenPose import modules, the hand presets, characters
and morph runtime with its worker, their `three.module.js` r160 with
`OrbitControls` and `TransformControls`, the mannequin and the three skins,
plus `LICENSE` (MIT), the CC0 text and the mesh's licence note. Not taken:
`PoseStudioWidget` and its node, UniCanvas, the 3D factory, SAM 3D Body,
the model manager, and the pose library, which has no licence (§3.9). The
upstream revision is stamped into the copy's README.

**Every module is copied as `.mjs`.** ComfyUI imports every `.js` file under
an extension's web directory on every page load. As `.js`, the morph worker's
top-level `self.onmessage = …` would take over `window.onmessage` on every
ComfyUI page, and about 2 MB of three and core would be parsed for users who
never open the forge. The script renames the files and the names inside them
mechanically as it copies, the way `vendor_three.py` re-roots imports; no
patch hunk is involved.

The `// MMC:` patches (`tools/posestudio.patch`, `--save` to regenerate), each
small and each explained at its site:

- **`FBXLoader` from a file, not a CDN.** Upstream imports three and
  `FBXLoader` from esm.sh at run time; the script fetches `FBXLoader.js`
  r160 and its `fflate`, `NURBSCurve` and `NURBSUtils` imports from the npm
  package, re-rooted onto their three, and the importer loads those. FBX
  works offline, nothing on the page reaches a third-party host, and the
  clip is built on the same three instance as the mannequin.
- Nothing that changes how a pose is solved or how a frame looks.

**Their three r160 stays theirs.** The lift stage runs our three 0.170.
Moving their code to 0.170 would be a patch to every file and a re-test of
their look for no gain; two module instances on a page are fine as long as
no object crosses between them, and none does — the pose stage hands the
rest of the forge PNGs and JSON.

**What we build around it** is the forge's half, and where it goes further
than Pose Studio:

- **The bench page** (built, `web/creator/forge/posepage.js`). A
  `PoseViewerCore` in a forge panel with our own small UI: body sliders, joint
  gizmos, a frame strip with onion skin, FBX drop, FPS. The onion skins are
  the core's passive characters, made translucent; the strip's thumbnails are
  drawn by a second, hidden viewer in the same tab, not by a render job, so
  looking at a set caches nothing into the project. An edit is saved by
  pasting the set over itself (`/pose/paste` with `replace`, which keeps the
  set's `source`), so the page needs no route the CLI lacks. Symmetry and
  Flip are ours (`forge/mirror.js`): the rig's rest frames are all
  world-aligned with the figure facing +Z, left at +X, so a twin's rotation
  is `[x, -y, -z]` and its offset `[-x, y, z]` (checked: a mirrored arm and
  leg draw 0.9 % asymmetric, the bare figure 0.5 %, the unmirrored copy
  53 %). The view pad snaps the core's camera to its capture camera; the
  sprite camera view zooms to the frame cell and leaves the core's capture
  frame showing, so the box on the stage is the drawing.
- **Imports settled** (built, `web/creator/forge/figure.js`). The vendored
  retarget anchors every keypoint at the resting pelvis, so a clip loses its
  height as well as its travel: Sneak Walk's feet floated 47 to 91 px in a
  1088 frame, Standard Walk's sank up to 38. After the import each frame's
  Root is moved until the lowest point of its feet is on the standing
  figure's ground, plus the clip's own lift read from the FBX (under a tenth
  of a leg counts as standing: a rolling foot moves its joints that much),
  and the clip is turned to face forward on average from its hip line
  (Sneak Walk: 36°). Settled, the feet sit within -10 to +21 px of the ground
  point in the picture; the rest is perspective, the camera being at chest
  height. `ground` and `face` on the import turn either off.
- **Frames that say where things are** (built). The tab measures each drawn
  frame (box, ground under the hips, lowest point of each foot) and the
  server keeps it beside the PNG, works out which edges it touches, and
  answers a render with `clipped` and a `fit` size; the CLI's `--fit` draws
  again at it. Requested by the agent making Harker's Journal, which pivoted
  frames by measuring silhouettes and lost a sneak's head to the 484 width.
- **Pitch** (built). A render takes `pitch`, degrees the camera looks down
  (-89 to 89; the core's own sign is the opposite and the tab negates it),
  and it is part of a frame's cache key only when not level, so frames drawn
  before it existed keep their names. Tilting the model instead (a
  `modelRotation` x) also tilts the light, which the camera does not. Not root motion: the vendored import retargets each sampled frame
  onto the standing rig by keypoints, so a clip comes in place (seen on the
  walk: every frame centred, one baseline) and there is no travel to keep. It is a client of their core, not a copy of
  their widget, so it does the widget's set-up itself: decode the pack,
  solve the sliders in the vendored worker, `loadData` the result, turn the
  directional skydome off (`setDirectionalSkydomeVisible(false)`: the
  core's default is on and draws a grid behind the figure; the widget's
  `directional_skydome_enabled` defaults to off), and light it with the
  widget's two default lights (directional 2.0 at (10, 20, 30), ambient
  `#505050` 1.0) on white. Proven headless in the spike: Chromium,
  SwiftShader, `capture(w, h, 1, [255, 255, 255], 0, 0, yaw, 0)`.
- **Rendering from any tab** (built, `creator/forge/pose.py` and
  `web/creator/forge/pose.js`). A frame render, and an FBX import, is a
  forge job: the server announces `continuity.pose.job` to every tab, the
  first to `POST /pose/claim` gets the task (poses, body, size), builds a
  `PoseViewerCore` on a canvas off screen, and posts the PNGs (or the
  retargeted poses) to `/pose/done`, which completes the job. A tab claims
  one job at a time, and a hidden tab waits two seconds so a visible one,
  whose timers are not throttled, wins. Upstream needs the one tab holding
  that node on its canvas; we need a tab. No tab connected, the request is
  refused at once (`pose.no_tab`); no claim within 15 s, or a tab silent
  for two minutes after claiming, fails the job with a sentence. These are
  not ComfyUI prompts: they use no server GPU, and holding the queue while
  a browser draws would block the renders the forge exists for. They live in
  the server's memory; their output is on disk before they answer. The two
  routes a tab calls are a table of their own (`TAB_ROUTES`) beside the
  client routes, so parity does not ask the CLI for them. This is how the
  CLI and agents pose.
- **Frames are a cache.** A frame's picture depends on its pose, the body,
  the size and the yaw, so it is stored as
  `build/poses/<set>/<frame>-<hash>.png`; asking again answers without a
  tab, and an edited frame redraws alone. A stored pose keeps only bones,
  bone positions and model rotation, at full precision: the camera and IK
  helpers draw the same to the pixel without them, and rounding to six
  decimals did not.
- **Sets as project data.** `poses/<set>.json` holds `pose_data` per pose
  and the clip's FPS; the PNGs are derived and cached under `build/`.
- **Straight into the sprite pipeline.** Frames go to the grid render
  (§7.1 step 6) at the grid's canvas — captured at each cell's size, not
  scaled after — then split, matte → baseline and pivot → pixelize →
  atlas → engine export, instead of a folder of PNGs. 2.1's own alpha came
  back clean on every spike render; BiRefNet stays the tightening pass.
- **Posing by joint** (built, `creator/forge/joints.py`). Raw `pose_data`
  is Euler degrees on each bone's own axes: exact, and useless to reason
  with — an agent cannot know which of three numbers bends an elbow, or that
  the standing figure's elbows are already bent 47°. So a pose can be set in
  words: `elbow_l.bend=90`, `shoulder_r.raise=150`, `spine.lean=-10`,
  `hand_l=fist`, `body.bend=90` (the whole figure, through its
  `modelRotation`, laid face down for a crawl: tipping the `Root` bone
  instead pivots at the floor and leaves the capture's frame, as the first
  crawl on the lab showed; a tipped figure's render yaw is composed in front
  of its rotation, so it turns on the floor rather than rolling). A joint is a
  bone and three named motions, each a turn about
  an axis fixed in the rig with its sign chosen so + means what the name says
  (`raise` away from the body, `bend` closing, `turn`/`lean` to the figure's
  own left, the forearm's `twist` palm up — each checked by drawing it on the
  mannequin). Angles are anatomical, read against a zero configuration (the
  limb straight down, the forearm in line with the upper arm), not against
  the A-pose, so `bend=0` is a straight arm and `raise=180` overhead; the
  axes come from the rest directions measured once from the pack's base mesh,
  so they hold to a degree or two across body sliders. A motion not named
  keeps its value. Limits refuse, never clamp. The right side is the left
  reflected, so every word means the same on both. `spine` spreads over its
  three bones; hands take Pose Studio's own three presets (copied, held
  against the vendored file by a test) rather than a guessed finger curl.
  `--mirror` sets the twin too, `pose flip` writes a frame's mirror image
  over another (`joints.flip_pose`, held against `mirror.js`), and `pose show
  --joints` reads any frame back in the same words, imports included. The
  bench keeps its rings: the words are for agents and scripts; a person drags.
  Not built: IK goals ("right hand on the hip"). The core's solver runs only
  in a tab and the server does not know a body's bone lengths, so it would be
  a tab job; it waits until an agent posing with the words and the two-view
  sheet below shows where they fall short.
- **Keys and in-betweens** (built). A set may name its `keys`, each with the
  ease that leaves it (`linear`, `ease-in`, `ease-out`, `ease-in-out`,
  `hold`), and `loop`. Every other frame is drawn between the keys either side
  of it by `pose.py`'s `tween`, which runs whenever the set is written, so an
  edited key moves its in-betweens and nobody keeps them up to date by hand.
  Rotations turn the short way (quaternion slerp), never as averaged Euler
  numbers; positions blend straight, and a position one key has and the other
  lacks is refused (`pose.tween_position`), because the server does not know
  a bone's rest position. Posing an in-between makes it a key, on the bench as
  in the CLI. It is done on the server rather than with the vendored
  `vnccs_pose_animation.mjs`, which stays unused: an agent with no tab open
  gets in-betweens too, and the bench and the CLI cannot disagree about them.
  On the bench a set without keys shows every frame as a key; un-keying a
  frame (K) is how an artist starts letting frames be drawn. The bench drops
  bone positions equal to the bone's rest before saving, since the core
  reports the root's on every pose and that would make every bench frame
  "move" the root against every CLI frame.
- **Front and side in one look** (built). A render takes `views`, yaws to
  draw each frame at in one job (`--views 0,90`), and `/pose/sheet` puts
  drawn frames into one picture, a row per view, a column per frame
  (`--sheet`). One view hides what a pose does in depth; the sheet is the
  agent's single look before it corrects a pose.
- **Directions as a property of a set.** (Built as the yaw a set is drawn
  at, chosen on the page's compass and passed to the render job; not yet
  stored on the set.) Turn the whole walk to 4 or 8
  azimuths in one go (`modelRotation` per pass).
- **A pose check on the finished sprite.** The mannequin's silhouette
  against the sprite's matte, per frame, so a frame where the LoRA ignored
  the pose is flagged, not shipped.

Mixamo clips are the user's to import, never shipped: Adobe's terms allow
using them in a game, not redistributing them. The same goes for VNCCS's
pose library until it declares a licence: a user who has it can paste a pose
from it (`pose_data` is the format), and the forge ships none of it.

**Credits.** The README's *Thanks* gets
`[ComfyUI_VNCCS_Utils](https://github.com/AHEKOT/ComfyUI_VNCCS_Utils) by
AHEKOT (MIUProject) - Pose Studio's viewer, FBX import and animation behind
the pose stage, vendored (MIT)`, the MakeHuman project for the mannequin
(CC0), and `MIUProject` for the pose LoRAs the stage feeds. Its closing line
about "the three vendored libraries" becomes four. The bench's pose page
shows the same credit, and `docs/` names Pose Studio where it explains the
stage.

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
7. Models: GLB with LODs and collision as separate named nodes, and OBJ with
   true quads for handing to a modelling package.
8. Audio as §8.

Later: FBX through a binary FBX writer of our own (Unity and Unreal import
both GLB and OBJ, so FBX waits until a target needs it, and a hand-written
FBX must be proven in both engines first), Unity `.meta`, Unreal `.uasset`, Wwise and FMOD projects (they take
WAVs anyway), `.uge`.

## 10. Architecture

- **Python** `creator/forge/`: `project.py` (storage, versions, manifest),
  `style.py`, `kinds/<kind>.py` (recipe → job body), `post/` (`matte.py`,
  `bleed.py`, `pixelize.py`, `constraints.py`, `atlas.py`, `tiling.py`,
  `pbr.py`, `loop.py`, `loudness.py`), `pose.py` (pose sets, the
  render job and its upload route), `uv/` (`raster.py`, `project.py`,
  `fill.py`), `mesh/` (`lift.py` calling `creator/lift.py`, `retopo.py` with
  one module per backend, `qremesh.py` for our own, `lod.py`, `collision.py`,
  `checks.py`), `export/<target>.py`. External remesh tools are paths in
  `settings.py`, the machine's settings, never in a project file: a project
  that could name an executable would be a project that runs one. No ComfyUI or torch imports at module
  scope where tests need the module.
- **Routes** `creator/routes/forge.py` under `/continuity/forge/*`: project
  CRUD, asset recipes, previews (GETs), runs (`jobs.submit("forge", …)` or
  `jobs.enqueue` for pipelines), exports. Imported from the root
  `__init__.py`.
- **Nodes**: none user-facing in v1. Internal stage nodes, if a pipeline
  needs them, are `Continuity/internal` and `is_dev_only`, the lift pattern.
- **Frontend** `web/creator/forge.js` and `forge/*.js` (`forge/pose.js` the
  pose page and the offscreen render listener), `vendor/posestudio/`, the bench room from
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
| 3D | `lift <asset>`, `retopo <asset> --mode tris\|quads\|keep --faces N`, `lod <asset>`, `collision <asset>`, `texture <mesh> <recipe>`, `views <mesh>` (the depth and normal renders it will condition on) |
| Poses | `joints` (the joint vocabulary), `poses <project>`, and `pose <project>` with `new <set> [--from <set>[/<frame>]]`, `import <set> <clip.fbx> [--fps 12] [--replace]`, `set <set> <frame> <joint.motion>=<deg>… <hand_l>=<shape> <bone>=<x,y,z>… [--mirror]`, `flip <set> <frame> [--to <frame>]`, `keys <set> [<frame>[:<ease>]…] [--length N] [--loop\|--no-loop] [--clear]`, `paste <set> <pose_data.json> [--replace]`, `render <set> [--frame N…] [--width] [--height] [--yaw] [--pitch] [--views 0,90] [--sheet]` (mannequin PNGs — the agent's eyes on a pose), `show <set> [--joints [--frame N…]]`, `rm <set>`. `import` and `render` run in an open ComfyUI tab (§7.9) and refuse when there is none. |
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
   post-steps 6.1–6.7, exports 1–5. Works
   on pictures made anywhere — immediately useful for a Game Boy project.
   The CLI and its skill ship in this step, not after: every route lands
   with its command, and the parity test from day one.
2. **2D generation.** Style, characters and sprites, tiles with seamless
   tiling, icons, masked inpainting. The pose stage (§7.9) is part of this
   step: the vendor script (done, `c03334b`), then a lab spike (QI2.1 half
   done), then the render job (done: pose sets, the tab job, the CLI's
   `pose` commands; tested on the lab 2026-10-06 with a headless Chromium
   tab of its ComfyUI: the Mixamo walk imported, 15 frames in about a second,
   four side frames drawn in two seconds and served from the cache after;
   with no listening tab the job failed with its sentence), then the pose
   page (done, tested on a Mac against a real ComfyUI tab: the Mixamo walk
   imported through it, a ring drag saved, the body re-solved, the walk drawn
   at 90° from the page), then posing by joint, keys with in-betweens, flip
   and the two-view sheet (done; every joint motion drawn on the mannequin
   through a real ComfyUI tab to check its direction and sign). The bench around it was reworked in the same change:
   shelf, glass and inspector for assets, the project's settings in a drawer,
   the recipe as a form. A tab loaded before the pack was updated counts as connected but
   has no listener, so it gets the 15-second failure rather than the
   immediate refusal: reload open tabs after an update.

   **The spike, 2026-10-06, QI2.1 half.** A Mixamo walk through the vendored
   import, captured headless (side view, frames 0/3/6/9 of 15 at 12 fps),
   two sheets (a painted adventurer; an ink-and-hatching plague doctor with
   a one-shoulder cape, vial bandolier, lantern and satchel) and the frames
   through the pack's existing 2.1 still route: pose as picture 1, sheet as
   picture 2, VNCCS's sentence verbatim, the LoRA at 1.0, the base row (20
   steps, cfg 1, euler/simple). Nothing new was needed in the pack: it kept
   both uncited pictures in order and left `<image 2>` alone. Results: the
   poses, identity and style hold on both characters; per-frame renders
   jump in scale and the grid does not (§7.1 step 6); about 21 s per render
   at 1280×720, 78 s at 1936×1088. Not done: the H3 half (its LoRA is not
   on the lab), a side-by-side with VNCCS's own output, and its Viggle
   6-step setup against our base row.
3. **Audio.**
4. **3D.** Materials, model texturing, and 3D models (§7.6) with
   triangle retopology and Q-Remesh on the optional and external backends.
   A one-mesh spike of §7.4 runs early, in parallel with 2, because it is the
   biggest unknown: the grid-of-views route is plausible and unproven on
   these families.
5. **Our own Q-Remesh** (§3.8), so quads do not depend on anything
   installed. Backgrounds and parallax, HD rigs, `.uge`, FBX, further
   engines.

## 13. Risks

- **Node names** (`LTXVAudioOnlyModel`, `RenderMesh`, the bake nodes) come
  from research that could not reach the docs. Each is verified against an
  install before it is wired, and each path has a fallback that does not need
  it.
- **Q-Remesh quality.** Our own field-aligned remesher will be behind
  Instant Meshes and QuadriFlow for a long time, and far behind ZRemesher on
  edge flow around faces and hands. The external and optional backends are
  why it is not on the critical path; the checks say when a result is poor.
- **Grid-of-views consistency** may not hold on Qwen Image 2.1 at 4–6
  views with one depth grid as the guide. The spike decides; sequential
  projection is the fallback.
- **Vendoring a fast-moving upstream.** VNCCS Utils changes weekly. Our
  copy is pinned, so their changes cannot break a project; re-syncing is
  deliberate, and a patch hunk that no longer applies stops the script. The
  render job's contract with their core (`PoseViewerCore` construction and
  capture) is the thing to re-check on every sync.
- **48 MB of assets** (mannequin and skins) enter the repo and the published
  package. Upstream ships them the same way; if the registry objects, the
  vendor script can instead fetch them at a pinned commit into `models/` on
  first use, with the licence files beside them.
- **The QI2.1 pose LoRA** declares no licence on Hugging Face; Civitai's
  terms allow commercial use. Checked before the auto-routing ships.
- **The pose LoRAs' file names** are the routing key, and VNCCS has already
  shipped a catalogue entry pointing at a path that 404s. The needle is
  loose (`PoseStudio` + family marker), and the refusal names the file and
  URL so a mismatch is one sentence, not a silent unposed render.
- **Hidden-side items.** A direction draws only what faces it (§7.1
  step 5). A character whose sheet shows one side may get the other side
  invented. Multi-view sheets are the likely answer; untested.
- **Pixel conversion** is only as good as the 1024 picture. The constraint
  check makes failure visible; a pixel touch-up editor may be wanted later.
- **Agents acting blind.** An agent that never looks will ship a sheet
  that passes every check and looks wrong. The skill makes `sheet` part of
  the loop, and `status` marks an asset nobody has viewed since it was made.
- **Scope.** v1 is §12 steps 1 and 2. Everything else waits until those are
  used.

## 14. Not in v1

Rigging beyond a starting `rig.lua`, skeletal animation, skinning,
neural retopology, density painting and edge-flow strokes for Q-Remesh,
convex decomposition, LoRA training of a
character, an identity-similarity score, `.uge`, engine-native binaries,
level layout beyond Tiled export, voice cloning.

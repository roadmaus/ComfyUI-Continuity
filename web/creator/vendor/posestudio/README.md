# Pose Studio's viewer, vendored

From [ComfyUI_VNCCS_Utils](https://github.com/AHEKOT/ComfyUI_VNCCS_Utils) by
AHEKOT (MIUProject), revision `eedaed7` (2026-09-30), MIT (`LICENSE`). The
MakeHuman mannequin in `assets/` is CC0 (`assets/*.CC0-1.0.md`); the skins in
`textures/` are under the repo's MIT. `FBXLoader.mjs` and the three modules it
imports are from the three.js 0.160.0 npm package, MIT, matching upstream's
own `three.module.mjs`.

Copied by `tools/vendor_posestudio.py`, which says what is taken and why, and
why every module is `.mjs` here. Local changes are marked `// MMC:` and held in
`tools/posestudio.patch`. Do not edit these files except through that patch.

The forge's pose stage (spec §7.9) is a client of `PoseViewerCore`: it draws
the mannequin the VNCCS pose LoRAs were trained to read, and nothing here is
patched in a way that changes how a pose is solved or how a frame looks.

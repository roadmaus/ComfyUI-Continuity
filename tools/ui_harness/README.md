# UI harness

Renders the real frontend in a browser without ComfyUI, torch or a GPU, so a
design can be looked at (and screenshotted) from any checkout.

```sh
python3 tools/ui_harness/server.py            # then open http://127.0.0.1:8188/
node tools/ui_harness/shots.cjs out/          # node, full, simple, timeline, dashboard PNGs
node tools/ui_harness/shots.cjs out/ --light  # the same on ComfyUI's light palette
```

`shots.cjs` starts its own server on a free port. It needs a resolvable
`playwright`; `PLAYWRIGHT_MODULE` and `BROWSER_EXECUTABLE_PATH` work as they
do in `tests/browser/`.

## The pictures in the docs, and the film

```sh
node tools/ui_harness/docs.cjs                # every picture README.md and docs/ show, into docs/img
node tools/ui_harness/docs.cjs out/ hero chat # two of them, somewhere else
node tools/ui_harness/film.cjs                # docs/vid/timeline-blockout-stagehand.mp4
node tools/ui_harness/film.cjs out.mp4 --dry  # one picture per held moment, nothing encoded
```

Both stand on `demo.cjs`, which answers in the browser what a piece needs and
the server above does not: these also need `ffmpeg`.

- **Takes and faces** are cut from the style atlas that ships in
  `web/creator/presets/atlas/` (one frame each of clips from
  `ostris/minimax_h3_1k`), a take being a still with a slow push in. Nothing
  shown was rendered by this pack.
- **Stagehand's model** is a script of replies. The tools it calls are the real
  ones, so the film it writes and the set it builds are what those calls make.
- **The blockout's guides** are drawn for real and the routes that would write
  them accept them and keep nothing.
- **The settings** say the chat room's first-run questions were answered.

The film is not a screen recording. Each frame is a screenshot taken after the
page was put where that frame needs it (a letter typed, the pointer moved, the
playhead set), so it comes out the same on any machine. The pointer and the
captions are drawn over the page by the script.

Two pictures are not made here and were taken in ComfyUI: `simple-prestage.png`
(the pre-stage is a second node, and there is no graph to spawn it in) and
`style-atlas.png`.

## What is real and what is not

- **Real:** everything under `web/` (layout, components, CSS), and the family
  catalog at `/continuity/families`, which is built from the Python side the
  way the test suites build it.
- **Stood in:** `scripts/app.js` and `scripts/api.js` (the two host modules
  the frontend imports), the node object in `index.html`, and ComfyUI's
  palette, which is copied in by hand as CSS variables.
- **Absent:** every other backend route answers 404, so settings, model and
  LoRA lists and anything that renders show their empty or error state
  (the "weights missing" pill is one of these). The server prints each
  unanswered route. To answer one, put JSON in `stubs/`, named after the path
  with `/` as `__`: `/continuity/settings` is `stubs/continuity__settings.json`.

This is for looking at the UI. It is not a test of ComfyUI integration: the
isolated regression checks live in `tests/browser/`.

## Driving it yourself

The page sets `globalThis.harnessReady` once the node is mounted, exposes the
node as `globalThis.node`, and `openFullscreen()` opens the fullscreen editor.
`?theme=light` switches the palette.

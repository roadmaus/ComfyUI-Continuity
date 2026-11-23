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

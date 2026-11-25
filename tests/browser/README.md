# Isolated browser regression checks

These scripts read this checkout's production JavaScript methods and CSS and run
them in a fresh, headless Playwright browser context. They are optional developer
checks: **ComfyUI does not gain a Playwright/runtime dependency**.

## Run

Use a recent Node.js version. If `playwright` is already resolvable, install its
Chromium browser with `npx playwright install chromium`, then run the scripts
below from the repository root. Script paths are resolved relative to the script,
not the current working directory.

Alternatively, this PowerShell example keeps all test dependencies outside the
checkout, in a new temporary directory:

```powershell
$browserTestDeps = Join-Path ([IO.Path]::GetTempPath()) ('continuity-browser-tests-' + [guid]::NewGuid().ToString('N'))
npm install --prefix $browserTestDeps --no-package-lock --no-save playwright
$env:PLAYWRIGHT_MODULE = Join-Path $browserTestDeps 'node_modules/playwright'
node (Join-Path $env:PLAYWRIGHT_MODULE 'cli.js') install chromium

node tests/browser/test-style-scroll.cjs
node tests/browser/test-reference-preview.cjs
node tests/browser/test-timeline-reel.cjs
node tests/browser/test-blockout-bench.cjs
node tests/browser/test-stagehand-tools.cjs
```

On other operating systems, the same scripts work with the equivalent environment
variables. `PLAYWRIGHT_MODULE` is optional and can name any installed Playwright
module directory. `BROWSER_EXECUTABLE_PATH` optionally selects an existing
Chromium-based browser executable instead of Playwright's bundled Chromium.

The style-strip suite normally runs 12 checks against the current checkout. Set
`CONTINUITY_BASELINE_DIR` to an older, unmodified checkout to add three comparisons
that reproduce the previous vertical-wheel behavior. No baseline copy is bundled.

Every suite exits nonzero on failure and prints its results to stdout. Network
requests are blocked and counted; successful runs require zero requests. The
scripts do not launch ComfyUI, touch a user browser profile, or modify project data.

## Coverage and limits

- **Style strip:** actual category methods, DOM helpers, atlas categories and CSS;
  wheel directions/units/modifiers, scroll limits, keyboard navigation, focus,
  filtering, listener stability, RTL and grid-scroll isolation. Catalogue loading
  and card rendering are local fixtures.
- **Reference preview:** actual viewer module, relevant DOM helpers, editor
  reference-chip callbacks and CSS. The browser records a tiny local WebM to check
  playback, unloading, navigation, fullscreen/Escape, focus, narrow layouts and
  read-only state. API URL resolution and model-state helpers are adapters; this
  does not establish support for every user video codec.
- **Timeline reel:** the real `timeline.js`, `state.js` and CSS loaded as ES
  modules, with ComfyUI's `api`/`app` stubbed and the family catalog dumped by
  `tests/layout.py` (so this one needs `python3`). Checks cover the one-surface
  layout, the piece inspector, kept takes and what an edit or a reshoot
  releases, Shoot, Enter/Backspace in the script, cutting and blocked joins,
  the cast and reference inspectors, and dragging a shot's length. Thumbnail
  and take requests are answered empty by the stub and counted as `media`.

- **Blockout bench:** the real `staging.js`, `reel.js`, `blockout.js`,
  `state.js` and CSS, with the same stubs as the reel's, on a piece of two sets
  and three shots. Checks cover the three columns, the header, the glass's
  Stage and Guide, a shot's guide on its card, scrubbing, the staging rows,
  Shoot deriving and attaching a guide (the frame and write routes are answered
  locally), starting a set, the handles and what each edit releases, the lens,
  the adds, joins and lining them up, Enter, the one-shot mode and its doors,
  reading an old saved scene, Copy and the sweep on close; and, handled by
  hand, the plan and the monitor, the badge, the sheet of stops (retiming a
  stop, adding one, stepping between them), Draw path, what the model is given
  with whose words it sends, and the labelled pass. `SHOT=path.png` writes
  screenshots at 2×.

- **Stagehand's tools:** the real `stagehand.js` with the same stubs, and a
  model that is a script: each exchange is answered here with the next calls
  on a list. Every tool is called for an answer and for a refusal, and the
  piece that results is read back. Also covered: one picture for the changes
  of a reply, a shot's length against its own family (one family's longest
  shot is shortened in the catalog for this), the kept take in the scene's
  lines, what a message carries and sends, a change of model between messages,
  Stop under an exchange and between two calls, a server's failure, and the
  limit on exchanges. The server half has its own suite,
  `tests/test_stagehand.py`; `tools/stagehand_bench.py --fake` runs the two
  together.

These are isolated browser regression tests, **not end-to-end ComfyUI tests or
GPU/rendering validation**. Source extraction is intentionally explicit: if a
production method's structure changes, update the corresponding fixture rather
than silently testing a stale copy.

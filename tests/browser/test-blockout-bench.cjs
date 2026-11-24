// Isolated browser checks for the blockout bench: the real staging.js, reel.js,
// blockout.js, state.js and CSS, loaded as ES modules from this checkout into a
// fresh headless page.
// ComfyUI's `api` and `app` are stubbed, the family catalog is the one
// `families/manifest.catalog()` serves (dumped through tests/layout.py), and
// every request that is not one of those files is aborted and counted. This is
// not an end-to-end ComfyUI test and renders nothing.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '../..');
const ORIGIN = 'http://localhost:5999';
const catalog = execFileSync('python3', ['-c',
  'import sys; sys.path.insert(0, "tests"); import layout; sys.stdout.write(layout.catalog_json())'],
  { cwd: root, encoding: 'utf8' }).replace(/\}[^}]*$/, '}');   // the harness appends its report line
// Concatenated, not a template literal: the catalog's own escapes must reach
// the page as written.
const apiStub = "const ok = (body) => new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } });\n"
  + "const CATALOG = " + catalog + ";\n"
  + "export const api = {\n"
  + "  async fetchApi(url, init) { if (/^\\/(continuity\\/(blockout|probe)|upload\\/image)/.test(url)) return fetch(url, init);\n"
  + "    return url.startsWith('/continuity/families') ? ok(CATALOG) : ok({}); },\n"
  + "  apiURL: (u) => u, getUserData: async () => new Response('{}', { status: 404 }),\n"
  + "  storeUserData: async () => {}, addEventListener() {}, removeEventListener() {},\n"
  + "};\n";
const appStub = `export const app = { graph: { _nodes: [] }, extensionManager: { setting: { get() {} } }, ui: { settings: { getSettingValue() {} } } }; globalThis.app = app;`;

let browser, requests = 0, media = 0, guideFrames = 0;
const writes = [];
const sweeps = [];
let uploads = 0;
const results = [];
async function check(name, fn) { await fn(); results.push({ name, passed: true }); }

(async () => {
  browser = await chromium.launch({ executablePath: process.env.BROWSER_EXECUTABLE_PATH || undefined, headless: true });
  const page = await browser.newPage({ viewport: { width: 1500, height: 950 }, deviceScaleFactor: process.env.SHOT ? 2 : 1 });
  page.setDefaultTimeout(4000);
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin === ORIGIN) {
      if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: '<!doctype html><html><body></body></html>' });
      if (url.pathname === '/scripts/api.js') return route.fulfill({ contentType: 'text/javascript', body: apiStub });
      if (url.pathname === '/scripts/app.js') return route.fulfill({ contentType: 'text/javascript', body: appStub });
      if (url.pathname.startsWith('/ext/web/creator/') && url.pathname.endsWith('.js')) {
        const file = path.join(root, url.pathname.slice('/ext/'.length));
        if (fs.existsSync(file)) return route.fulfill({ contentType: 'text/javascript', body: fs.readFileSync(file) });
      }
    }
    // Thumbnails and takes, asked of the stubbed ComfyUI server. Answered empty:
    // there are no files here, and the reel has to draw without them.
    // The scene the old bench saved beside a guide it wrote.
    if (url.origin === ORIGIN && url.pathname === '/view' && /blockout-depth\.json/.test(url.search)) {
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ continuity_blockout: 1, op: 'depth', fps: 24, scene: {
        objects: [{ kind: 'block', x: 0, z: 5, w: 0.52, h: 1.74, d: 0.42, plays: 'anna' }, { kind: 'wall', x: 0, z: 7.6, w: 6.2, h: 2.9 }],
        marks: [{ x: 0, y: 1.6, z: 1.1, yaw: 0, pitch: 0, mm: 50 }, { x: 0, y: 1.58, z: 2.7, yaw: 0, pitch: 0, mm: 50 }],
        duration: 4, aspect: '16:9', pass: 'depth' } }) });
    }
    if (url.origin === ORIGIN && (url.pathname === '/view' || url.pathname === '/continuity/thumb')) {
      media++;
      if (process.env.SHOT) return route.fulfill({ contentType: 'image/svg+xml', body: `<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><rect width="320" height="180" fill="${/k1|s2/.test(url.href) ? '#345c4a' : /k2|s3/.test(url.href) ? '#334a78' : '#8a5a34'}"/><circle cx="160" cy="90" r="50" fill="#ffffff55"/></svg>` });
      return route.fulfill({ status: 404, body: '' });
    }
    // The derived guides Shoot writes: the frames are accepted and counted, and
    // the write answers with the name it was asked for, as the server does.
    if (url.origin === ORIGIN && url.pathname === '/continuity/blockout/frames') {
      guideFrames++;
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ held: 1 }) });
    }
    if (url.origin === ORIGIN && url.pathname === '/continuity/blockout/write') {
      const body = JSON.parse(route.request().postData() || '{}');
      writes.push(body);
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ path: `continuity/blockout/${body.name}.mp4`, kind: 'video' }) });
    }
    if (url.origin === ORIGIN && url.pathname === '/upload/image') {
      uploads++;
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ name: 'blockout-depth.png', subfolder: 'continuity/blockout' }) });
    }
    if (url.origin === ORIGIN && url.pathname === '/continuity/blockout/sweep') {
      sweeps.push(JSON.parse(route.request().postData() || '{}').keep);
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ gone: 0 }) });
    }
    if (url.origin === ORIGIN && url.pathname === '/continuity/probe') {
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ missing: false }) });
    }
    requests++;
    return route.abort();
  });
  await page.goto(`${ORIGIN}/`);
  await page.addStyleTag({ content: ':root{--comfy-menu-bg:#353535;--input-text:#ddd;--descrip-text:#999;--fg-color:#fff;--bg-color:#202020;--error-text:#f44} body{margin:0;background:#202020;font-family:Arial}' });

  // The prototype's piece: a kitchen and a street, two shots kept on the
  // kitchen set and a third, on the street, not shot yet.
  const open = async (extra = '') => page.evaluate(async (extra) => {
    document.querySelectorAll('.mmc-overlay').forEach((node) => node.remove());
    (await import('/ext/web/creator/styles.js')).installStyles();
    const S = await import('/ext/web/creator/state.js');
    const B = await import('/ext/web/creator/staging.js');
    const tl = S.parseTimeline(JSON.stringify({
      version: 2, render: 'chained', seeds: 'each', aspect: '16:9', short_edge: 768,
      prompt: 'A small kitchen early in the morning. Grey light through the window, steam, nobody quite awake.',
      soundscape: 'A kettle ticking as it cools, rain on the glass.',
      subjects: [{ handle: 'anna', takes: 'person', from: [] }, { handle: 'ben', takes: 'person', from: [] }],
      sets: [
        { id: 'kitchen', name: 'Kitchen', view: { yaw: -0.62, pitch: -0.46, orbit: 10.5, x: -0.2, y: 0.9, z: 1.5 }, objects: [
          { id: 1, kind: 'wall', x: 0, z: 4.1, w: 7.2, h: 3, d: 0.2 },
          { id: 2, kind: 'wall', x: -3.6, z: 1.4, w: 5.4, h: 3, d: 0.2, ry: Math.PI / 2 },
          { id: 3, kind: 'wall', x: 2.3, z: 3.92, w: 1.1, h: 2.2, d: 0.16, word: 'doorway' },
          { id: 4, kind: 'block', x: -1.7, z: 3.5, w: 2.8, h: 0.95, d: 0.7, word: 'counter' },
          { id: 5, kind: 'block', x: 1.2, z: 0.7, w: 1.4, h: 0.75, d: 0.8, word: 'table' },
          { id: 6, kind: 'block', x: 2.25, z: 0.7, w: 0.5, h: 0.9, d: 0.5, word: 'chair' },
          { id: 7, kind: 'person', x: -1.5, z: 2.75, h: 1.7, plays: 'anna' },
          { id: 8, kind: 'person', x: 2.3, z: 3.4, h: 1.8, ry: Math.PI, plays: 'ben' } ] },
        { id: 'street', name: 'Street', objects: [
          { id: 1, kind: 'wall', x: 0, z: 7.2, w: 15, h: 6, d: 0.3, word: 'house front' },
          { id: 2, kind: 'block', x: 1.4, z: 3.1, w: 4.2, h: 1.4, d: 1.8, word: 'car' },
          { id: 3, kind: 'post', x: -3.1, z: 4.7, w: 0.25, h: 3.6, d: 0.25, word: 'street lamp' },
          { id: 5, kind: 'person', x: -2.2, z: 6.7, h: 1.7, ry: Math.PI, plays: 'anna' } ] } ],
      segments: [
        { prompt: '@anna stands at the counter with her back to us, pouring coffee. @ben comes in through the doorway behind her.',
          duration_s: 5, assets: [], loras: [], set: 'kitchen',
          staging: { camera: [{ t: 0, x: -0.3, y: 1.5, z: -3.9, yaw: 0.04, pitch: -0.04, mm: 28 }, { t: 5, x: -0.8, y: 1.5, z: -1.9, yaw: -0.1, pitch: -0.04, mm: 28 }],
                     people: { 8: [{ t: 0, x: 2.3, z: 3.4, ry: 3.14 }, { t: 5, x: 1.7, z: 1.9, ry: 3.0 }] } } },
        { prompt: '@ben sits down at the table. @anna turns round to him, cup in hand.', duration_s: 4, assets: [], loras: [],
          continue: true, continue_audio: true, set: 'kitchen',
          staging: { camera: [{ t: 0, x: -0.8, y: 1.5, z: -1.9, yaw: -0.1, pitch: -0.04, mm: 28 }, { t: 4, x: -0.7, y: 1.4, z: -1.7, yaw: 0.42, pitch: -0.07, mm: 28 }],
                     people: { 8: [{ t: 0, x: 1.7, z: 1.9, ry: 3.0 }, { t: 4, x: 2.2, z: 0.95, ry: 2.4 }], 7: [{ t: 0, x: -1.5, z: 2.75 }, { t: 4, x: -1.4, z: 2.6, ry: 2.1 }] } } },
        { prompt: 'Outside, a car waits at the kerb in the rain. @anna steps out of the house and walks towards it.', duration_s: 5, assets: [], loras: [],
          set: 'street',
          staging: { camera: [{ t: 0, x: -3.4, y: 1.2, z: -2.6, yaw: 0.52, pitch: 0.03, mm: 35 }, { t: 5, x: -1.2, y: 1.2, z: -3.0, yaw: 0.3, pitch: 0.03, mm: 35 }],
                     people: { 5: [{ t: 0, x: -2.2, z: 6.7, ry: 3.14 }, { t: 5, x: -0.9, z: 4.9, ry: 2.5 }] } } },
      ],
    }));
    const queued = S.queuedCards(tl);
    S.attachTakes(tl, [1, 2].map((n) => ({ segment: n, filename: `s${n}.mp4`, subfolder: 'takes', duration_s: 5, has_audio: true })), queued);
    window.S = S; window.tl = tl; window.queued = 0; window.timelineOpened = 0;
    if (extra) (0, eval)(extra);
    B.openStaging({ timeline: tl, onCommit: () => {}, queue: () => { window.queued++; },
      openTimeline: () => { window.timelineOpened++; }, opened: (bench) => { window.bench = bench; } });
    return 'ok';
  }, extra);
  assert.equal(await open(), 'ok');
  await page.waitForTimeout(250);
  const ink = () => page.evaluate(() => {
    const canvas = document.querySelector('.mmc-st canvas');
    const data = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
    let lit = 0;
    for (let i = 0; i < data.length; i += 4 * 97) if (data[i] + data[i + 1] + data[i + 2] > 60) lit++;
    return { w: canvas.width, h: canvas.height, lit };
  });

  await check('Three columns over the strip: the script, the stage, the inspector', async () => {
    assert.deepEqual(await page.evaluate(() => ({
      title: document.querySelector('.mmc-reel-title').textContent,
      columns: [...document.querySelector('.mmc-reel-main').children].map((node) => node.className),
      labels: [...document.querySelectorAll('.mmc-reel-script .mmc-reel-label')].map((n) => n.textContent),
      rows: document.querySelectorAll('.mmc-reel-shots .mmc-reel-shot').length,
      cut: [...document.querySelectorAll('.mmc-st-cuthint')].map((n) => n.textContent),
      frames: [...document.querySelectorAll('.mmc-reel-face.frame .mmc-reel-face-name')].map((n) => n.textContent),
      piece: document.querySelector('.mmc-reel-ihead b').textContent,
    })), { title: 'Blockout', columns: ['mmc-reel-script', 'mmc-st-col', 'mmc-reel-side'], labels: ['Scene', 'Sound', 'Score'],
      rows: 3, cut: ['Hard cut · the street set'], frames: ['Kitchen', 'Street'], piece: 'The piece' });
  });

  await check('The header says what the next render shoots and what it plays', async () => {
    assert.deepEqual(await page.evaluate(() => [document.querySelector('.mmc-reel-meta').textContent,
      document.querySelector('.mmc-reel-plan').textContent, document.querySelector('.mmc-reel-shoot').textContent,
      document.querySelector('.mmc-reel-head .mmc-reel-btn.quiet:not([hidden])')?.textContent]),
    ['3 shots · 14.1 s', 'Shoots 1 shot · plays 2 kept takes', 'Shoot', 'Open the timeline']);
  });

  await check('The glass draws the stage, and the guide exactly as the file will hold it', async () => {
    const stage = await ink();
    assert.ok(stage.lit > 50, `the stage drew nothing: ${JSON.stringify(stage)}`);
    assert.ok(stage.w >= 320 && Math.abs(stage.w / stage.h - 1344 / 768) < 0.02, JSON.stringify(stage));
    await page.locator('.mmc-bo-hud.top').getByText('Guide', { exact: true }).click();
    await page.waitForTimeout(80);
    const depth = await page.evaluate(() => {
      const canvas = document.querySelector('.mmc-st canvas');
      const data = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
      let grey = true;
      for (let i = 0; i < data.length; i += 4 * 131) if (data[i] !== data[i + 1] || data[i] !== data[i + 2]) grey = false;
      return grey;
    });
    assert.equal(depth, true, 'the depth pass is grey');
    assert.equal(await page.locator('.mmc-bo-hud.top button', { hasText: 'Still' }).isDisabled(), true);
    await page.locator('.mmc-bo-hud.top').getByText('Stage', { exact: true }).click();
  });

  await check('A shot with no take shows its guide on its card, dimmed', async () => {
    await page.waitForTimeout(150);
    assert.deepEqual(await page.evaluate(() => [...document.querySelectorAll('.mmc-reel-card')].map((card) => [
      Boolean(card.querySelector('canvas.mmc-st-thumb')), card.querySelector('.mmc-reel-card-tag')?.textContent ?? ''])),
    [[false, ''], [false, ''], [true, 'Not shot yet · its guide']]);
    assert.ok(await page.evaluate(() => {
      const canvas = document.querySelector('canvas.mmc-st-thumb');
      const data = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
      let lit = 0;
      for (let i = 0; i < data.length; i += 4 * 17) if (data[i] > 30) lit++;
      return lit > 20;
    }));
  });

  await check('Drag across a shot to scrub it: the glass and the playhead follow', async () => {
    const card = await page.locator('.mmc-reel-card').nth(1).boundingBox();
    await page.mouse.move(card.x + card.width * 0.3, card.y + card.height / 2);
    await page.mouse.down();
    await page.mouse.move(card.x + card.width / 2, card.y + card.height / 2, { steps: 4 });
    await page.mouse.up();
    const at = await page.evaluate(() => [bench.at.index, bench.at.t, document.querySelector('.mmc-st-said').textContent,
      bench.sel?.kind, Math.round(parseFloat(document.querySelector('.mmc-st-head').style.left))]);
    assert.equal(at[0], 1);
    assert.ok(Math.abs(at[1] - 2) < 0.15, `t ${at[1]}`);
    assert.match(at[2], /^Shot 2 · 2\.\d \/ 4\.0 s$/);
    assert.equal(at[3], 'shot');
    assert.ok(Math.abs(at[4] - (card.x - (await page.locator('.mmc-reel-track-area').boundingBox()).x + card.width / 2)) < 6, `head at ${at[4]}`);
  });

  await check('A staged shot shows its staging in the inspector', async () => {
    assert.deepEqual(await page.evaluate(() => [
      document.querySelector('.mmc-reel-ihead b').textContent,
      document.querySelector('.mmc-reel-ihead span').textContent,
      [...document.querySelectorAll('.mmc-reel-inspect .mmc-reel-ilabel')].map((n) => n.textContent),
      document.querySelector('.mmc-reel-inspect .mmc-reel-compiled').textContent.split('\n')[0].replace(/staged-[0-9a-z]+-/, 'staged-#-'),
    ]), ['Shot 2', '4.0 s · the kitchen set',
      ['Length', 'Camera', 'Marks', 'Lens', 'Staging', 'Guide', 'Seed'],
      'input/continuity/blockout/staged-#-as_staged.mp4 · 96 frames · As staged']);
  });

  await check('Shoot draws the guide of the shot it shoots, attaches it, and queues', async () => {
    const before = writes.length;
    await page.locator('.mmc-reel-shoot').click();
    await page.waitForFunction(() => window.queued === 1, null, { timeout: 15000 });
    const guide = await page.evaluate(() => {
      const asset = S.stagedClip(tl.segments[2]);
      return { asset: asset && { role: asset.role, ref_size: asset.ref_size, track: asset.track, staged: S.isStagedGuide(asset) },
               words: tl.segments[2].staging.words, others: [S.stagedClip(tl.segments[0]), S.stagedClip(tl.segments[1])],
               kept: tl.segments.map((seg) => S.isKept(seg)) };
    });
    assert.equal(writes.length - before, 1);
    assert.equal(writes[writes.length - 1].op, 'as_staged');
    assert.match(writes[writes.length - 1].name, /^staged-[0-9a-z]+-as_staged$/);
    assert.ok(guideFrames >= 5, `frames sent ${guideFrames}`);
    assert.deepEqual(guide.asset, { role: 'reference', ref_size: 'match', track: 'picture', staged: true });
    assert.match(guide.words, /@anna/);
    assert.deepEqual(guide.others, [null, null]);
    assert.deepEqual(guide.kept, [true, true, false]);
  });

  await check('A shot with no staging offers the sets there are, and the ways to start one', async () => {
    await open("tl.segments[2].staging = undefined; delete tl.segments[2].staging; delete tl.segments[2].set;");
    await page.waitForTimeout(100);
    await page.evaluate(() => bench.select({ kind: 'shot', index: 2 }));
    await page.waitForTimeout(60);
    const offered = await page.evaluate(() => [...document.querySelectorAll('.mmc-st-starts button')].map((b) => b.textContent));
    assert.deepEqual(offered, ['On the kitchen set', 'On the street set', 'Bare floor', 'Two-shot', 'Corridor', 'Interview', 'Street corner']);
    await page.locator('.mmc-st-starts').getByText('Two-shot').click();
    assert.deepEqual(await page.evaluate(() => [tl.segments[2].set, tl.sets.length, tl.segments[2].staging.camera.length,
      S.isKept(tl.segments[0]), S.isKept(tl.segments[1])]), ['s3', 3, 2, true, true]);
    await page.evaluate(() => bench.step(bench.done, bench.undone));
    assert.deepEqual(await page.evaluate(() => [tl.segments[2].set ?? null, tl.sets.length]), [null, 2]);
  });

  // Where a world point lands on the screen, through the glass's own camera.
  const onGlass = (expr) => page.evaluate((expr) => {
    const [px, py] = (0, eval)(expr);
    const rect = bench.canvas.getBoundingClientRect();
    const scale = Math.min(rect.width / bench.raster.w, rect.height / bench.raster.h);
    return { x: rect.left + (rect.width - bench.raster.w * scale) / 2 + px * scale,
             y: rect.top + (rect.height - bench.raster.h * scale) / 2 + py * scale };
  }, expr);
  const dragBy = async (from, dx, dy, mods = []) => {
    for (const key of mods) await page.keyboard.down(key);
    await page.mouse.move(from.x, from.y);
    await page.mouse.down();
    await page.mouse.move(from.x + dx, from.y + dy, { steps: 6 });
    await page.mouse.up();
    for (const key of mods) await page.keyboard.up(key);
    await page.waitForTimeout(60);
  };

  await check('The sets ride over the film as brackets, and select their set', async () => {
    await open();
    await page.waitForTimeout(150);
    assert.deepEqual(await page.evaluate(() => [...document.querySelectorAll('.mmc-reel-passes .mmc-reel-pass')].map((n) => n.textContent)),
      ['Kitchen set', 'Street set']);
    await page.locator('.mmc-reel-passes .mmc-reel-pass').first().click();
    assert.deepEqual(await page.evaluate(() => [document.querySelector('.mmc-reel-ihead b').textContent,
      [...document.querySelectorAll('.mmc-reel-inspect .mmc-reel-ilabel')].map((n) => n.textContent),
      [...document.querySelectorAll('.mmc-reel-inspect .mmc-reel-value')].map((n) => n.textContent)]),
    ['Kitchen', ['Name', 'On it', 'Add'], ['Doorway', 'Counter', 'Table', 'Chair', '@anna', '@ben']]);
  });

  await check('A person moved in a shot is blocked in that shot alone, at the playhead', async () => {
    await page.evaluate(() => { bench.select({ kind: 'shot', index: 1 }); bench.at.t = 2; bench.select({ kind: 'cast', handle: 'ben' }); });
    await page.waitForTimeout(60);
    assert.equal(await page.evaluate(() => [bench.sel.kind, bench.sel.id].join()), 'thing,8');
    const centre = await onGlass('const g = bench.gizmo(bench.eye()); [g.at.x, g.at.y]');
    await dragBy(centre, 60, 10);
    assert.deepEqual(await page.evaluate(() => [tl.segments[1].staging.people[8].map((m) => m.t),
      tl.sets[0].objects.find((o) => o.id === 8).x, tl.segments.map((seg) => S.isKept(seg)),
      document.querySelector('.mmc-reel-ihead span').textContent]),
    [[0, 2, 4], 2.3, [true, false, false], 'in shot 2 at 2.0 s']);
  });

  await check('A wall moved is the set: every shot on it is released', async () => {
    await open();
    await page.waitForTimeout(120);
    await page.evaluate(() => { bench.select({ kind: 'shot', index: 0 }); bench.select({ kind: 'thing', id: 4 }); });
    const x0 = await page.evaluate(() => tl.sets[0].objects.find((o) => o.id === 4).x);
    const arrow = await onGlass('const g = bench.gizmo(bench.eye()); const p = g.parts.find((q) => q.key === "x").pts[1]; [p[0], p[1]]');
    const tail = await onGlass('const g = bench.gizmo(bench.eye()); [g.at.x, g.at.y]');
    await dragBy(arrow, (arrow.x - tail.x) * 2, (arrow.y - tail.y) * 2);
    assert.deepEqual(await page.evaluate((x0) => [tl.sets[0].objects.find((o) => o.id === 4).x > x0,
      tl.sets[0].objects.find((o) => o.id === 4).z, tl.segments.map((seg) => S.isKept(seg)), Object.keys(tl.segments[0].staging.people)], x0),
    [true, 3.5, [false, false, false], ['8']]);
  });

  await check('Turn snaps to 15°, and Lift takes a piece off the floor', async () => {
    await open();
    await page.waitForTimeout(120);
    await page.evaluate(() => { bench.select({ kind: 'shot', index: 0 }); bench.select({ kind: 'thing', id: 5 }); });
    await page.keyboard.press('2');
    assert.equal(await page.evaluate(() => bench.tool), 'turn');
    const ring = await onGlass('const g = bench.gizmo(bench.eye()); const pts = g.parts.find((q) => q.key === "y").pts.filter(Boolean); const p = pts[6]; [p[0], p[1]]');
    await dragBy(ring, 25, 25);
    const ry = await page.evaluate(() => tl.sets[0].objects.find((o) => o.id === 5).ry);
    assert.ok(ry !== 0 && Math.abs(Math.round(ry * 180 / Math.PI) % 15) === 0, `turned to ${ry}`);
    await page.keyboard.press('3');
    const body = await onGlass('const g = bench.gizmo(bench.eye()); [g.at.x, g.at.y]');
    await dragBy(body, 0, -60);
    assert.ok(await page.evaluate(() => tl.sets[0].objects.find((o) => o.id === 5).y > 0.3));
  });

  await check('Through the lens every gesture writes a camera mark at the playhead; free look writes nothing', async () => {
    await open();
    await page.waitForTimeout(120);
    await page.evaluate(() => { bench.select({ kind: 'shot', index: 0 }); });
    const glass = await page.locator('.mmc-st canvas').boundingBox();
    const middle = { x: glass.x + glass.width / 2, y: glass.y + glass.height * 0.75 };
    const noView = () => page.evaluate(() => JSON.stringify(JSON.parse(S.serializeTimeline(tl)), (k, v) => (k === 'view' ? undefined : v)));
    const before = await noView();
    await dragBy(middle, 80, 0);
    assert.equal(await noView(), before);
    assert.deepEqual(await page.evaluate(() => tl.segments.map((seg) => S.isKept(seg))), [true, true, false]);
    await page.locator('.mmc-bo-hud.top').getByText('What the camera sees').click();
    await page.evaluate(() => { bench.at.t = 2.5; bench.paint(); });
    await dragBy(middle, 40, 0);
    assert.deepEqual(await page.evaluate(() => [tl.segments[0].staging.camera.map((m) => m.t), S.isKept(tl.segments[0]), S.isKept(tl.segments[1])]),
      [[0, 2.5, 5], false, false]);
  });

  await check('The adds put a piece on the set; Delete takes it off', async () => {
    await open();
    await page.waitForTimeout(120);
    await page.evaluate(() => bench.select({ kind: 'shot', index: 2 }));
    await page.locator('.mmc-bo-hud.bottom').getByText('+ Block').click();
    assert.deepEqual(await page.evaluate(() => [tl.sets[1].objects.length, bench.sel.kind,
      document.querySelector('.mmc-reel-ihead b').textContent]), [5, 'thing', 'Block']);
    await page.evaluate(() => document.activeElement?.blur());
    await page.keyboard.press('Delete');
    assert.equal(await page.evaluate(() => tl.sets[1].objects.length), 4);
  });

  await check('A join says whether it continues, and a hard cut which set it goes to', async () => {
    await page.evaluate(() => bench.select({ kind: 'join', index: 2 }));
    assert.deepEqual(await page.evaluate(() => [document.querySelector('.mmc-reel-ihead span').textContent,
      [...document.querySelectorAll('.mmc-reel-inspect .mmc-reel-ilabel')].map((n) => n.textContent)]),
    ['hard cut', ['Continues', 'Set']]);
    await page.locator('.mmc-reel-inspect .mmc-reel-seg').getByText('Kitchen').click();
    assert.equal(await page.evaluate(() => tl.segments[2].set), 'kitchen');
    await page.evaluate(() => bench.select({ kind: 'join', index: 1 }));
    assert.deepEqual(await page.evaluate(() => [...document.querySelectorAll('.mmc-reel-inspect .mmc-reel-ilabel')].map((n) => n.textContent).slice(0, 2)),
      ['Continues', 'Blend']);
  });

  await check('A continuing join that does not line up says so, wears the accent, and is fixed', async () => {
    await open();
    await page.waitForTimeout(120);
    await page.evaluate(() => bench.select({ kind: 'join', index: 1 }));
    assert.deepEqual(await page.evaluate(() => [document.querySelectorAll('.mmc-reel-join.mmc-st-jump').length,
      [...document.querySelectorAll('.mmc-reel-inspect .mmc-reel-irow')].pop().textContent]),
    [0, 'StagingLines up. The camera and everyone on set start where shot 1 leaves them.']);
    await page.evaluate(() => { tl.segments[1].staging.camera[0].x = 0.4; tl.segments[1].staging.people[8][0].z = 3; bench.commit(); });
    assert.deepEqual(await page.evaluate(() => [document.querySelectorAll('.mmc-reel-join.mmc-st-jump').length,
      document.querySelector('.mmc-reel-inspect .mmc-st-warn').textContent]),
    [1, 'Does not line up: the camera starts 1.2 m from where shot 1 leaves it, and @ben stands 1.1 m from where they stopped. The model will be handed frames that contradict the guide.']);
    await page.locator('.mmc-reel-inspect').getByText('Start shot 2 where shot 1 ends').click();
    assert.deepEqual(await page.evaluate(() => [document.querySelectorAll('.mmc-reel-join.mmc-st-jump').length,
      tl.segments[1].staging.camera[0].x, tl.segments[1].staging.people[8][0].z]), [0, -0.8, 1.9]);
  });

  await check('Enter at the end of a shot starts the next one where it ended', async () => {
    await open();
    await page.waitForTimeout(120);
    const box = page.locator('.mmc-reel-shot .mmc-prompt').nth(1);
    await box.click();
    await page.evaluate(() => {
      const root = document.querySelectorAll('.mmc-reel-shot .mmc-prompt')[1];
      const range = document.createRange();
      range.selectNodeContents(root);
      range.collapse(false);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
    });
    await page.keyboard.press('Enter');
    await page.waitForTimeout(80);
    assert.deepEqual(await page.evaluate(() => {
      const shot = tl.segments[2];
      const end = tl.segments[1].staging.camera.at(-1);
      return [tl.segments.length, shot.set, shot.continue, shot.staging.camera.length,
        shot.staging.camera[0].x === end.x && shot.staging.camera[0].z === end.z,
        Object.keys(shot.staging.people).sort(), document.querySelector('.mmc-reel-status .mmc-reel-hint').textContent,
        tl.segments.map((seg) => S.isKept(seg))];
    }), [4, 'kitchen', true, 1, true, ['7', '8'],
      'Shot 3 starts where shot 2 ends: same set, same marks, the camera where it stopped.', [true, true, false, false]]);
  });

  await check('Opened without a piece it is one shot: no strip, Write the guide, and the doors', async () => {
    const opened = await page.evaluate(async () => {
      document.querySelectorAll('.mmc-overlay').forEach((node) => node.remove());
      const B = await import('/ext/web/creator/staging.js');
      window.taken = [];
      B.openBlockout({ cast: ['anna'], targets: [
        { id: 'guide', label: 'Aim the shot at it', does: 'Every frame follows.', take: (r) => window.taken.push(['guide', r.kind, r.path]) },
        { id: 'pre', kinds: ['image'], label: 'Aim the still at it', does: 'Loads the branch.', take: (r) => window.taken.push(['pre', r.kind, r.path]) },
      ], back: () => { window.backed = true; } });
      return 'ok';
    });
    assert.equal(opened, 'ok');
    await page.waitForTimeout(120);
    const shell = await page.evaluate(() => [getComputedStyle(document.querySelector('.mmc-st-single .mmc-reel-foot')).display,
      document.querySelector('.mmc-reel-head .mmc-reel-shoot').textContent, document.querySelector('.mmc-reel-head .mmc-reel-shoot').disabled]);
    assert.deepEqual(shell, ['none', 'Write the guide', true]);
    await page.locator('.mmc-st-starts').getByText('Interview').click();
    const before = writes.length;
    await page.locator('.mmc-reel-head .mmc-reel-shoot').click();
    await page.waitForFunction(() => /Wrote/.test(document.querySelector('.mmc-reel-plan').textContent), null, { timeout: 15000 });
    assert.equal(writes.length - before, 1);
    assert.equal(writes[writes.length - 1].scene.objects.length, 3);
    assert.equal(writes[writes.length - 1].scene.objects[0].kind, 'person');
    await page.locator('.mmc-reel-shot .mmc-reel-num').first().click();
    assert.deepEqual(await page.evaluate(() => [...document.querySelectorAll('.mmc-reel-inspect .mmc-reel-ilabel')].map((n) => n.textContent)
      .filter((label) => ['Written', 'Send'].includes(label))), ['Written', 'Send']);
    await page.locator('.mmc-reel-inspect').getByText('Aim the still at it').click();
    await page.waitForFunction(() => window.taken.length === 1, null, { timeout: 15000 });
    assert.deepEqual(await page.evaluate(() => window.taken[0].slice(0, 2)), ['pre', 'image']);
    assert.ok(uploads >= 1);
    await page.locator('.mmc-st-back').click();
    assert.deepEqual(await page.evaluate(() => [window.backed, document.querySelectorAll('.mmc-st-bench').length]), [true, 0]);
  });

  await check('A shot carrying a guide the old bench wrote takes its saved scene as its staging', async () => {
    await open(`tl.segments[2].staging = undefined; delete tl.segments[2].staging; delete tl.segments[2].set;
      tl.segments[2].assets = [{ handle: 'vid-1', kind: 'video', role: 'guide', track: 'picture', filename: 'continuity/blockout/blockout-depth.mp4' }];`);
    await page.waitForFunction(() => Boolean(tl.segments[2].staging), null, { timeout: 5000 });
    assert.deepEqual(await page.evaluate(() => [tl.sets.length, tl.sets[2].name, tl.sets[2].objects.map((o) => o.plays || o.kind),
      tl.segments[2].staging.camera.map((m) => m.t), S.isKept(tl.segments[0])]),
    [3, 'Saved set', ['anna', 'wall'], [0, 5], true]);
  });

  await check('Copy puts what the model is given for a shot on the clipboard', async () => {
    await page.evaluate(() => { window.copied = null; navigator.clipboard.writeText = async (text) => { window.copied = text; }; bench.select({ kind: 'shot', index: 0 }); });
    await page.locator('.mmc-reel-machine').getByText('Copy').click();
    assert.match(await page.evaluate(() => window.copied), /^@anna .*The camera /);
  });

  await check('Open the timeline closes the bench and opens the reel on the same piece', async () => {
    await open();
    await page.waitForTimeout(100);
    await page.locator('.mmc-reel-head').getByText('Open the timeline').click();
    assert.deepEqual(await page.evaluate(() => [window.timelineOpened, document.querySelectorAll('.mmc-st-bench').length]), [1, 0]);
    await page.waitForTimeout(100);
    // Closing sweeps the derived guides nothing points at, keeping those the piece names.
    assert.ok(sweeps.length >= 1 && Array.isArray(sweeps[sweeps.length - 1]));
  });

  await check('A set is removed, asking twice; its shots stay, unstaged', async () => {
    await open();
    await page.evaluate(() => bench.select({ kind: 'set', id: 'street' }));
    await page.getByText('Remove the set', { exact: true }).click();
    assert.equal(await page.evaluate(() => tl.sets.length), 2);
    await page.getByText('Really remove?', { exact: true }).click();
    assert.deepEqual(await page.evaluate(() => [tl.sets.map((s) => s.id), tl.segments.length, tl.segments[2].set ?? null, tl.segments[2].staging ?? null]),
      [['kitchen'], 3, null, null]);
  });

  await check('A shot is removed from the bench, asking twice', async () => {
    await open();
    await page.evaluate(() => bench.select({ kind: 'shot', index: 2 }));
    await page.locator('.mmc-reel-inspect-body .mmc-asset-x').click();
    await page.getByText('Really remove?', { exact: true }).click();
    assert.equal(await page.evaluate(() => tl.segments.length), 2);
  });

  if (process.env.SHOT) {
    await open();
    await page.waitForTimeout(300);
    await page.evaluate(() => bench.select({ kind: 'shot', index: 1 }));
    await page.waitForTimeout(300);
    await page.screenshot({ path: process.env.SHOT });
    await page.evaluate(() => { bench.at.t = 2; bench.select({ kind: 'thing', id: 8 }); });
    await page.waitForTimeout(300);
    await page.screenshot({ path: process.env.SHOT.replace('.png', '2.png') });
  }

  assert.deepEqual(errors, []);
  assert.equal(requests, 0, 'Fixture attempted a network request');
  console.log(JSON.stringify({ passed: results.length, requests, media, results }, null, 2));
})().catch((error) => { console.error(error); process.exitCode = 1; }).finally(async () => { await browser?.close(); });

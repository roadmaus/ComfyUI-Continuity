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
  + "  async fetchApi(url, init) { if (/^\\/continuity\\/(blockout|probe)/.test(url)) return fetch(url, init);\n"
  + "    return url.startsWith('/continuity/families') ? ok(CATALOG) : ok({}); },\n"
  + "  apiURL: (u) => u, getUserData: async () => new Response('{}', { status: 404 }),\n"
  + "  storeUserData: async () => {}, addEventListener() {}, removeEventListener() {},\n"
  + "};\n";
const appStub = `export const app = { graph: { _nodes: [] }, extensionManager: { setting: { get() {} } }, ui: { settings: { getSettingValue() {} } } }; globalThis.app = app;`;

let browser, requests = 0, media = 0, guideFrames = 0;
const writes = [];
const results = [];
async function check(name, fn) { await fn(); results.push({ name, passed: true }); }

(async () => {
  browser = await chromium.launch({ executablePath: process.env.BROWSER_EXECUTABLE_PATH || undefined, headless: true });
  const page = await browser.newPage({ viewport: { width: 1500, height: 950 } });
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
      ['Length', 'Camera', 'Marks', 'Lens', 'Staging', 'Guide', 'Guide holds', 'Seed'],
      'input/continuity/blockout/staged-#-depth.mp4 · 96 frames · Depth']);
  });

  await check('Shoot draws the guide of the shot it shoots, attaches it, and queues', async () => {
    const before = writes.length;
    await page.locator('.mmc-reel-shoot').click();
    await page.waitForFunction(() => window.queued === 1, null, { timeout: 15000 });
    const guide = await page.evaluate(() => {
      const asset = S.guideAsset(tl.segments[2]);
      return { asset: asset && { role: asset.role, strength: asset.strength, op: asset.op, staged: S.isStagedGuide(asset) },
               words: tl.segments[2].staging.words, others: [S.guideAsset(tl.segments[0]), S.guideAsset(tl.segments[1])],
               kept: tl.segments.map((seg) => S.isKept(seg)) };
    });
    assert.equal(writes.length - before, 1);
    assert.equal(writes[writes.length - 1].op, 'depth');
    assert.match(writes[writes.length - 1].name, /^staged-[0-9a-z]+-depth$/);
    assert.ok(guideFrames >= 5, `frames sent ${guideFrames}`);
    assert.deepEqual(guide.asset, { role: 'guide', strength: 1, op: 'depth', staged: true });
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

  await check('Open the timeline closes the bench and opens the reel on the same piece', async () => {
    await open();
    await page.waitForTimeout(100);
    await page.locator('.mmc-reel-head').getByText('Open the timeline').click();
    assert.deepEqual(await page.evaluate(() => [window.timelineOpened, document.querySelectorAll('.mmc-st-bench').length]), [1, 0]);
  });

  if (process.env.SHOT) {
    await open();
    await page.waitForTimeout(300);
    await page.evaluate(() => bench.select({ kind: 'shot', index: 1 }));
    await page.waitForTimeout(300);
    await page.screenshot({ path: process.env.SHOT });
  }

  assert.deepEqual(errors, []);
  assert.equal(requests, 0, 'Fixture attempted a network request');
  console.log(JSON.stringify({ passed: results.length, requests, media, results }, null, 2));
})().catch((error) => { console.error(error); process.exitCode = 1; }).finally(async () => { await browser?.close(); });

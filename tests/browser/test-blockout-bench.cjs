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
  + "  async fetchApi(url, init) { if (/^\\/(continuity\\/(blockout|probe|stagehand|refine\\/remote)|upload\\/image)/.test(url)) return fetch(url, init);\n"
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
// Stagehand's model: a script of replies, each a list of `[tool, arguments]`,
// handed out one exchange at a time when `go()` lets the next one answer.
const hand = { script: [], sent: [], stops: [], waiting: [], go() { this.waiting.shift()?.(); } };

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
      sweeps.push(JSON.parse(route.request().postData() || '{}').drop);
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ gone: 0 }) });
    }
    if (url.origin === ORIGIN && url.pathname === '/continuity/refine/remote') {
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ url: 'http://192.168.1.20:8080/v1', key_set: false }) });
    }
    if (url.origin === ORIGIN && url.pathname === '/continuity/stagehand/stop') {
      hand.stops.push(JSON.parse(route.request().postData()).session);
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ stopped: true }) });
    }
    if (url.origin === ORIGIN && url.pathname === '/continuity/stagehand') {
      hand.sent.push(JSON.parse(route.request().postData()));
      await new Promise((resolve) => hand.waiting.push(resolve));
      const next = hand.script.shift();
      const message = typeof next === 'string' ? { role: 'assistant', content: next } : { role: 'assistant', content: '', tool_calls: (next ?? []).map(([name, given], at) => (
        { id: `c${hand.sent.length}-${at}`, type: 'function', function: { name, arguments: JSON.stringify(given) } })) };
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ result: { choices: [{ message, finish_reason: 'stop' }] } }) }).catch(() => {});
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
      openTimeline: () => { window.timelineOpened++; },
      // The checks written for the flown-round view keep it; the plan has its own below.
      opened: (bench) => { window.bench = bench; bench.plan = false; } });
    return 'ok';
  }, extra);
  assert.equal(await open(), 'ok');
  await page.waitForTimeout(250);
  const ink = () => page.evaluate(() => {
    const canvas = document.querySelector('.mmc-st > canvas');
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
      [...document.querySelectorAll('.mmc-reel-head .mmc-reel-btn:has(svg)')].map((button) => button.textContent).join(', ')]),
    ['3 shots · 14.1 s', 'Shoots 1 shot · plays 2 kept takes', 'Shoot', 'Open the timeline, Stagehand']);
  });

  await check('The glass draws the stage, and the guide exactly as the file will hold it', async () => {
    // Handled from outside the shot camera, the stage is the whole of the glass.
    const stage = await ink();
    assert.ok(stage.lit > 50, `the stage drew nothing: ${JSON.stringify(stage)}`);
    const room = await page.evaluate(() => { const r = document.querySelector('.mmc-st-glass').getBoundingClientRect(); return r.width / r.height; });
    assert.ok(stage.w >= 320 && Math.abs(stage.w / stage.h - room) < 0.02, JSON.stringify([stage, room]));
    // The shot camera's frustum is drawn in the marks' blue on the stage, and nowhere in a guide.
    const inked = () => page.evaluate(() => {
      const canvas = document.querySelector('.mmc-st > canvas');
      const data = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
      let blue = 0;
      for (let i = 0; i < data.length; i += 4) if (data[i + 2] > 220 && data[i] < 150 && data[i + 1] > 150) blue++;
      return blue;
    });
    assert.ok(await inked() > 20, 'the stage shows the shot camera');
    await page.locator('.mmc-bo-hud.top').getByText('Guide', { exact: true }).click();
    await page.waitForTimeout(80);
    const guide = await ink();
    assert.ok(Math.abs(guide.w / guide.h - 1344 / 768) < 0.02, `the guide is the render's frame: ${JSON.stringify(guide)}`);
    assert.equal(await inked(), 0, 'the guide carries no staging aid');
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
      [...document.querySelectorAll('.mmc-st-gets .mmc-reel-ilabel')].map((n) => n.textContent),
      document.querySelector('.mmc-st-gets .mmc-st-file').textContent.replace(/staged-[0-9a-z]+-/, 'staged-#-'),
    ]), ['Shot 2', '4.0 s · the kitchen set',
      ['Length', 'Camera', 'Keep looking at', 'Camera shake', 'Lens', 'Seed'],
      ['Guide', 'Words', 'Depth as alpha'],
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
    assert.deepEqual(offered, ['On the kitchen set', 'On the street set', 'Bare floor', 'Two-shot', 'Corridor', 'Interview', 'Street corner', 'Scene library…']);
    await page.locator('.mmc-st-starts').getByText('Two-shot').click();
    assert.deepEqual(await page.evaluate(() => [tl.segments[2].set, tl.sets.length, tl.segments[2].staging.camera.length,
      S.isKept(tl.segments[0]), S.isKept(tl.segments[1])]), ['s3', 3, 2, true, true]);
    await page.evaluate(() => bench.step(bench.done, bench.undone));
    assert.deepEqual(await page.evaluate(() => [tl.segments[2].set ?? null, tl.sets.length]), [null, 2]);
  });

  await check('The scene library starts a whole set of models, and closes once the shot is on it', async () => {
    await page.locator('.mmc-st-starts').getByText('Scene library…').click();
    const shelf = await page.evaluate(() => [...document.querySelectorAll('.mmc-st-scene')].map((b) => b.textContent));
    assert.ok(shelf.length >= 12 && shelf.includes('Kitchen') && shelf.includes('Forest clearing'), String(shelf));
    await page.locator('.mmc-st-scene').getByText('Kitchen', { exact: true }).click();
    assert.deepEqual(await page.evaluate(() => {
      const set = tl.sets.find((one) => one.id === tl.segments[2].set);
      return [set.name, set.objects.some((piece) => piece.model === 'table'), set.objects.filter((piece) => piece.kind === 'person').length,
        tl.segments[2].staging.camera.length, Boolean(document.querySelector('.mmc-st-shelf'))];
    }), ['Kitchen', true, 2, 2, false]);
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
    const glass = await page.locator('.mmc-st > canvas').boundingBox();
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
    await page.locator('.mmc-st-gets').getByText('Copy').click();
    assert.match(await page.evaluate(() => window.copied), /^@anna .*The camera /);
  });

  await check('Open the timeline closes the bench and opens the reel on the same piece', async () => {
    await open();
    await page.waitForTimeout(100);
    await page.locator('.mmc-reel-head').getByText('Open the timeline').click();
    assert.deepEqual(await page.evaluate(() => [window.timelineOpened, document.querySelectorAll('.mmc-st-bench').length]), [1, 0]);
    await page.waitForTimeout(100);
    // Closing drops only what this window named and no longer does.
    const named = await page.evaluate(() => tl.segments.flatMap((s) => s.assets.map((a) => a.filename)));
    assert.ok(sweeps.every((drop) => Array.isArray(drop) && drop.length && drop.every((path) => !named.includes(path))));
  });

  await check('The stage is the render\'s frame: a new ratio reshapes it at once', async () => {
    await open();
    await page.waitForTimeout(120);
    // Through the shot camera the glass is the frame; handled from outside, the monitor is.
    const monitor = () => page.evaluate(() => { const c = document.querySelector('.mmc-st-monitor canvas'); return c.width / c.height; });
    assert.ok(await monitor() > 1.7, 'the monitor is the frame');
    await page.evaluate(() => bench.setLook('lens'));
    await page.waitForTimeout(120);
    const wide = await ink();
    await page.evaluate(() => { tl.aspect = '9:16'; bench.commit(); });
    await page.waitForTimeout(120);
    const tall = await ink();
    await page.evaluate(() => bench.setLook('around'));
    await page.waitForTimeout(120);
    assert.ok(await monitor() < 0.6, 'the monitor follows the ratio');
    assert.ok(wide.w > wide.h && tall.h > tall.w && tall.lit > 50, JSON.stringify([wide, tall]));
  });

  await check('Focus folds the script and the strip away; the inspector is a drawer; Escape steps back out', async () => {
    await open();
    await page.waitForTimeout(120);
    const width = () => page.evaluate(() => document.querySelector('.mmc-st-glass').getBoundingClientRect().width);
    const before = await width();
    await page.keyboard.press('f');
    await page.waitForTimeout(300);
    const shown = (selector) => page.evaluate((selector) => {
      const node = document.querySelector(selector);
      return Boolean(node) && getComputedStyle(node).display !== 'none' && getComputedStyle(node).visibility !== 'hidden';
    }, selector);
    assert.deepEqual([await shown('.mmc-reel-script'), await shown('.mmc-reel-lane'), await shown('.mmc-reel-side')], [false, false, false]);
    assert.ok(await width() > before * 1.4, `the stage did not grow: ${before} -> ${await width()}`);
    assert.equal(await page.evaluate(() => getComputedStyle(document.querySelector('.mmc-reel-side')).position), 'absolute', 'the drawer takes room from the stage');
    await page.evaluate(() => bench.select({ kind: 'thing', id: 4 }));
    await page.waitForTimeout(250);
    assert.equal(await shown('.mmc-reel-side'), true);
    await page.keyboard.press('i');
    await page.waitForTimeout(250);
    assert.equal(await shown('.mmc-reel-side'), false);
    await page.keyboard.press('Escape');
    await page.waitForTimeout(80);
    assert.deepEqual(await page.evaluate(() => [Boolean(document.querySelector('.mmc-st-focus')), Boolean(document.querySelector('.mmc-st-bench'))]), [false, true]);
    assert.equal(await shown('.mmc-reel-script'), true);
  });

  await check('Size stretches one side from the other, scales a person from the floor, and says so', async () => {
    await open();
    await page.waitForTimeout(120);
    await page.evaluate(() => { bench.select({ kind: 'shot', index: 0 }); bench.select({ kind: 'thing', id: 5 }); });
    await page.keyboard.press('4');
    assert.equal(await page.evaluate(() => bench.tool), 'size');
    const table = () => page.evaluate(() => { const o = tl.sets[0].objects.find((q) => q.id === 5); return { w: o.w, left: o.x - o.w / 2, h: o.h, d: o.d }; });
    const was = await table();
    const side = await onGlass('const g = bench.gizmo(bench.eye()); const q = g.handles.find((k) => k.kind === "face" && k.key === "x" && k.sign === 1); [q.x, q.y]');
    const inward = await onGlass('const g = bench.gizmo(bench.eye()); [g.at.x, g.at.y]');
    await dragBy(side, (side.x - inward.x) * 0.8, (side.y - inward.y) * 0.8);
    const now = await table();
    assert.ok(now.w > was.w + 0.3 && Math.abs(now.left - was.left) < 0.01 && now.h === was.h && now.d === was.d, JSON.stringify([was, now]));

    await page.evaluate(() => bench.select({ kind: 'thing', id: 7 }));
    const anna = () => page.evaluate(() => { const o = tl.sets[0].objects.find((q) => q.id === 7); return [o.h, o.w / o.h, o.y]; });
    const before = await anna();
    const corner = await onGlass('const g = bench.gizmo(bench.eye()); const q = g.handles.find((k) => k.kind === "corner"); [q.x, q.y]');
    await page.evaluate(async () => { window.BO = await import('/ext/web/creator/blockout.js'); });
    const feet = await onGlass('const o = bench.selectedThing(); const p = BO.project(bench.eye(), [o.x, 0, o.z], bench.raster.w, bench.raster.h); [p.x, p.y]');
    await dragBy(corner, corner.x - feet.x, corner.y - feet.y);
    const after = await anna();
    assert.ok(after[0] > before[0] * 1.6 && Math.abs(after[1] - before[1]) < 0.02 && after[2] === 0, JSON.stringify([before, after]));
    assert.match(await page.evaluate(() => tl.segments[0].staging.words), /@anna, towering at/);
    await page.locator('.mmc-reel-inspect').getByText('Doll 0.3').click();
    assert.equal(await page.evaluate(() => tl.sets[0].objects.find((q) => q.id === 7).h), 0.3);
    assert.match(await page.evaluate(() => tl.segments[0].staging.words), /@anna, tiny, 30 cm tall/);
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

  // ---- handled by hand: the plan, the sheet of stops, and what the model is given ----

  await check('The plan looks straight down, the shot camera keeps its corner, and a person dragged on it is blocked', async () => {
    await open();
    await page.waitForTimeout(120);
    await page.evaluate(() => { bench.setLook('plan'); bench.select({ kind: 'shot', index: 1 }); bench.at.t = 2; bench.select({ kind: 'thing', id: 8 }); });
    await page.waitForTimeout(120);
    assert.deepEqual(await page.evaluate(() => [bench.eye().pitch < -1.5, bench.eye().y > 100,
      document.querySelector('.mmc-bo-hud.top button[aria-pressed="true"]:not(:first-child)')?.textContent ?? '',
      [...document.querySelectorAll('.mmc-bo-hud.top [aria-label="Which camera"] button')].map((b) => [b.textContent, b.getAttribute('aria-pressed')].join(':')),
      document.querySelector('.mmc-st-monitor').hidden, document.querySelector('.mmc-st-monitor span').textContent]),
    [true, true, '', ['Plan:true', 'Look around:false', 'What the camera sees:false'], false, 'Camera · 28 mm']);
    // On a plan a drag to the right is a move along x and nothing else.
    const before = await page.evaluate(() => { const p = bench.objectsNow().find((o) => o.id === 8); return [p.x, p.z]; });
    const centre = await onGlass('const g = bench.gizmo(bench.eye()); [g.at.x, g.at.y]');
    await dragBy({ x: centre.x, y: centre.y + 4 }, 50, 0);
    const moved = await page.evaluate(() => { const m = tl.segments[1].staging.people[8].find((mark) => mark.t === 2); return [m.x, m.z, tl.segments[1].staging.people[8].length]; });
    assert.ok(moved[0] > before[0] + 0.3 && Math.abs(moved[1] - before[1]) < 0.08 && moved[2] === 3, JSON.stringify([before, moved]));
    // The floor dragged slides the plan, and is not an edit.
    const text = await page.evaluate(() => S.serializeTimeline(tl));
    const view = await page.evaluate(() => ({ ...bench.planView() }));
    const rect = await page.evaluate(() => { const r = bench.canvas.getBoundingClientRect(); return { x: r.left + 30, y: r.bottom - 70 }; });
    await dragBy(rect, 40, -20);
    assert.deepEqual(await page.evaluate(([text, view]) => [S.serializeTimeline(tl) === text, bench.planView().x < view.x, bench.planView().z < view.z], [text, view]), [true, true, true]);
    // The monitor is the way into the shot camera.
    await page.locator('.mmc-st-monitor canvas').click();
    await page.waitForTimeout(80);
    assert.deepEqual(await page.evaluate(() => [bench.lens, document.querySelector('.mmc-st-monitor').hidden]), [true, true]);
  });

  await check('The badge says what a drag is about to do before it does it', async () => {
    await open();
    await page.waitForTimeout(120);
    const badge = () => page.evaluate(() => { const b = document.querySelector('.mmc-st-badge'); return b.hidden ? null : [b.className.split(' ')[1], b.textContent]; });
    await page.evaluate(() => { bench.select({ kind: 'shot', index: 1 }); });
    assert.equal(await badge(), null);
    await page.evaluate(() => { bench.at.t = 2; bench.select({ kind: 'thing', id: 8 }); });
    await page.waitForTimeout(60);
    assert.deepEqual(await badge(), ['new', 'A drag writes a new stop for @ben at 2.0 s']);
    await page.evaluate(() => { bench.at.t = 4; bench.paint(); });
    await page.waitForTimeout(60);
    assert.deepEqual(await badge(), ['move', 'A drag moves @ben\'s stop at 4.0 s']);
    await page.evaluate(() => bench.select({ kind: 'thing', id: 5 }));
    await page.waitForTimeout(60);
    assert.deepEqual(await badge(), ['set', 'Table is the set: moving it changes every shot staged on it']);
    await page.evaluate(() => { bench.at.t = 1; bench.setLook('lens'); });
    await page.waitForTimeout(60);
    assert.deepEqual(await badge(), ['new', 'A drag writes a new camera stop at 1.0 s']);
  });

  await check('The sheet has a lane for each mover: a diamond dragged is another moment, a lane double-clicked gains a stop', async () => {
    await open();
    await page.waitForTimeout(120);
    await page.evaluate(() => bench.select({ kind: 'shot', index: 1 }));
    await page.waitForTimeout(60);
    assert.deepEqual(await page.evaluate(() => [
      [...document.querySelectorAll('.mmc-st-lane button.mmc-st-lanename')].map((n) => n.textContent),
      [...document.querySelectorAll('.mmc-st-lane')].slice(1).map((lane) => lane.querySelectorAll('.mmc-st-stop').length),
      document.querySelector('.mmc-st-lane.held .mmc-st-lanename').textContent,
      document.querySelector('.mmc-st-shotname').textContent, document.querySelector('.mmc-st-pacehost').hidden,
      [...document.querySelectorAll('.mmc-st-tick')].map((n) => n.textContent)]),
    [['Camera', '@anna', '@ben'], [2, 2, 2], 'Camera', 'Shot 2 of 3', true, ['0 s', '1 s', '2 s', '3 s', '4 s']]);
    // @ben's last stop, dragged a quarter of the lane to the left: he arrives a second sooner.
    const lane = page.locator('.mmc-st-lane', { hasText: '@ben' });
    const track = await lane.locator('.mmc-st-track').boundingBox();
    const last = await lane.locator('.mmc-st-stop').last().boundingBox();
    await dragBy({ x: last.x + last.width / 2, y: last.y + last.height / 2 }, -track.width / 4, 0);
    assert.deepEqual(await page.evaluate(() => [tl.segments[1].staging.people[8].map((m) => m.t), bench.at.t, bench.sel.kind, bench.sel.id,
      tl.segments.map((seg) => S.isKept(seg)), document.querySelector('.mmc-st-lane.held .mmc-st-lanename').textContent]),
    [[0, 3], 3, 'thing', 8, [true, false, false], '@ben']);
    // A press on a lane moves the playhead and snaps to a stop.
    await page.mouse.click(track.x + track.width * 0.5, track.y + track.height / 2);
    assert.equal(await page.evaluate(() => bench.at.t), 2);
    await page.mouse.click(track.x + track.width * 0.745, track.y + track.height / 2);
    assert.equal(await page.evaluate(() => bench.at.t), 3);
    // The camera's lane, double-clicked a quarter of the way in.
    const cam = await page.locator('.mmc-st-lane', { hasText: 'Camera' }).locator('.mmc-st-track').boundingBox();
    await page.mouse.dblclick(cam.x + cam.width * 0.25, cam.y + cam.height / 2);
    await page.waitForTimeout(60);
    assert.deepEqual(await page.evaluate(() => [tl.segments[1].staging.camera.map((m) => m.t), bench.sel.kind]), [[0, 1, 4], 'shot']);
    // K is a stop at the playhead, and the comma and the full stop walk the stops.
    await page.evaluate(() => { bench.goTo(1, 2.5); bench.paint(); });
    await page.keyboard.press('k');
    assert.deepEqual(await page.evaluate(() => tl.segments[1].staging.camera.map((m) => m.t)), [0, 1, 2.5, 4]);
    await page.keyboard.press(',');
    await page.keyboard.press(',');
    assert.equal(await page.evaluate(() => bench.at.t), 0);
    await page.keyboard.press('.');
    assert.equal(await page.evaluate(() => bench.at.t), 1);
    // The speed lane is the sheet's second page.
    await page.locator('.mmc-st-sheethead').getByText('Speed', { exact: true }).click();
    assert.deepEqual(await page.evaluate(() => [document.querySelector('.mmc-st-pacehost').hidden, document.querySelector('.mmc-st-pacename').textContent]), [false, 'Camera: speed']);
    // And the way to the next shot stays when the reel is folded away.
    await page.keyboard.press('f');
    await page.locator('.mmc-st-stepper button').last().click();
    assert.deepEqual(await page.evaluate(() => [bench.index(), document.querySelector('.mmc-st-shotname').textContent]), [2, 'Shot 3 of 3']);
    await page.keyboard.press('f');
  });

  await check('Draw path lays a walk by clicking the floor, spread over the shot at one pace', async () => {
    await open();
    await page.waitForTimeout(120);
    await page.evaluate(() => { bench.setLook('plan'); bench.select({ kind: 'shot', index: 0 }); bench.select({ kind: 'thing', id: 7 }); });
    await page.waitForTimeout(80);
    await page.keyboard.press('p');
    assert.deepEqual(await page.evaluate(() => [bench.tool, document.querySelector('.mmc-st-badge').textContent]), ['path', 'Click the floor: each click is @anna\'s next stop']);
    // Two clicks on bare floor in front of the counter.
    const spot = (x, z) => onGlass(`const B = bench.eye(); const p = (() => { const sy = Math.sin(B.yaw), cy = Math.cos(B.yaw), sp = Math.sin(B.pitch), cp = Math.cos(B.pitch); const dx = ${x} - B.x, dy = -B.y, dz = ${z} - B.z; const x1 = cy * dx - sy * dz, z1 = sy * dx + cy * dz; const y2 = cp * dy - sp * z1, z2 = sp * dy + cp * z1; const fl = (bench.raster.h / 2) / Math.tan(Math.atan(12 / B.mm)); return [bench.raster.w / 2 + fl * x1 / z2, bench.raster.h / 2 - fl * y2 / z2]; })(); p`);
    const a = await spot(-0.5, 1.6), b = await spot(0.4, -0.6);
    await page.mouse.click(a.x, a.y);
    await page.waitForTimeout(60);
    await page.mouse.click(b.x, b.y);
    await page.waitForTimeout(60);
    const marks = await page.evaluate(() => tl.segments[0].staging.people[7].map((m) => [m.t, Math.round(m.x * 10) / 10, Math.round(m.z * 10) / 10]));
    assert.equal(marks.length, 3, JSON.stringify(marks));
    assert.deepEqual([marks[0], marks[1].slice(1), marks[2]], [[0, -1.5, 2.8], [-0.5, 1.6], [5, 0.4, -0.6]], JSON.stringify(marks));
    // One pace: the stop in between falls where the distance puts it.
    const d1 = Math.hypot(1, 1.15), d2 = Math.hypot(0.9, 2.2);
    assert.ok(Math.abs(marks[1][0] - (5 * d1) / (d1 + d2)) < 0.12, JSON.stringify(marks));
    assert.deepEqual(await page.evaluate(() => [tl.segments.map((seg) => S.isKept(seg)), /@anna: 3 stops/.test(bench.statusHost.textContent)]), [[false, false, false], true]);
    // A set piece stays put, and says how it could move.
    await page.evaluate(() => bench.select({ kind: 'thing', id: 5 }));
    await page.mouse.click(a.x, a.y);
    assert.match(await page.evaluate(() => bench.statusHost.textContent), /part of the set and stays put/);
    await page.keyboard.press('Escape');
    assert.equal(await page.evaluate(() => bench.tool), 'move');
  });

  await check('What the model is given stays under the inspector: the frames, the words, and whose words they are', async () => {
    await open();
    await page.waitForTimeout(120);
    await page.evaluate(() => bench.select({ kind: 'thing', id: 5 }));
    await page.waitForTimeout(80);
    const given = () => page.evaluate(() => ({
      head: document.querySelector('.mmc-st-getshead').textContent,
      frames: [...document.querySelectorAll('.mmc-st-frames canvas')].map((c) => c.width / c.height > 1.7),
      prose: document.querySelector('.mmc-st-prose').textContent.slice(0, 22),
      cite: document.querySelector('.mmc-st-cite')?.textContent ?? null,
      clauses: [...document.querySelectorAll('.mmc-st-clause')].map((n) => n.dataset.id),
      told: document.querySelector('.mmc-st-told')?.textContent.slice(0, 40) ?? null,
      seg: [...document.querySelectorAll('.mmc-st-gets .mmc-reel-seg button[aria-pressed="true"]')].map((n) => n.textContent),
    }));
    // A piece of the set is selected, and the panel is still the shot's.
    assert.deepEqual(await given(), { head: 'What the model is givenshot 1Copy', frames: [true, true], prose: '@anna stands at the co',
      cite: 'The camera, framing and staging follow @the-clip, a rough blockout of this shot.',
      clauses: ['7', '5', '6', '4', '3', '8', 'camera'], told: '@anna stands at frame left in the midgro', seg: ['As staged', 'Yours, then the staging'] });
    // A clause pointed at lights its piece; pressed, it is selected.
    await page.locator('.mmc-st-clause[data-id="8"]').hover();
    assert.equal(await page.evaluate(() => bench.hot), 8);
    await page.locator('.mmc-st-clause[data-id="8"]').click();
    assert.deepEqual(await page.evaluate(() => [bench.sel.kind, bench.sel.id]), ['thing', 8]);
    // The shot's own words alone: nothing written about the scene, and the takes say so.
    await page.locator('.mmc-st-gets').getByText('Yours only', { exact: true }).click();
    await page.waitForTimeout(80);
    const own = await given();
    assert.deepEqual([own.clauses, own.told, own.seg, own.cite], [[], null, ['As staged', 'Yours only'],
      'The camera, framing and staging follow @the-clip, a rough blockout of this shot.']);
    assert.deepEqual(await page.evaluate(() => [tl.segments[0].staging.say, tl.segments[0].staging.words ?? null, tl.staging_say ?? null, tl.segments.map((seg) => S.isKept(seg))]),
      ['own', null, null, [false, false, false]]);
    // For the piece: every staged shot follows, and one that says otherwise keeps its say.
    await page.evaluate(() => bench.select(null));
    await page.locator('.mmc-reel-inspect').getByText('Yours only', { exact: true }).click();
    assert.deepEqual(await page.evaluate(() => [tl.staging_say, tl.segments.map((seg) => S.stagingSay(tl, seg)), tl.segments.map((seg) => seg.staging.words ?? null)]),
      ['own', ['own', 'own', 'own'], [null, null, null]]);
  });

  await check('A labelled guide is the stage as it is seen: the cast in their colours, every name in the frame', async () => {
    await open();
    await page.waitForTimeout(120);
    await page.evaluate(() => { bench.select({ kind: 'shot', index: 1 }); bench.goTo(1, 2); });
    await page.locator('.mmc-st-gets').getByText('Labelled', { exact: true }).click();
    await page.waitForTimeout(80);
    await page.locator('.mmc-bo-hud.top').getByText('Guide', { exact: true }).click();
    await page.waitForTimeout(120);
    // A tag is a flat field of the member's own hue, which no clay pixel is.
    const hues = await page.evaluate(async () => {
      const B = await import('/ext/web/creator/blockout.js');
      const canvas = document.querySelector('.mmc-st > canvas');
      const data = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
      const count = (rgb) => { let n = 0; for (let i = 0; i < data.length; i += 4) if (data[i] === rgb[0] && data[i + 1] === rgb[1] && data[i + 2] === rgb[2]) n++; return n; };
      return [count(B.tagRGB(S.tagIndex('anna'))) > 80, count(B.tagRGB(S.tagIndex('ben'))) > 80, count([14, 15, 17]) > 200];
    });
    assert.deepEqual(hues, [true, true, true]);
    assert.deepEqual(await page.evaluate(() => [tl.segments[1].staging.pass, S.stagedGuideName(tl, 1).endsWith('-labelled'),
      document.querySelector('.mmc-st-cite').textContent]),
    ['labelled', true, 'The camera, framing and staging follow @the-clip, a rough blockout of this shot. Its colours and name tags only say who and what each block is: they are not part of the picture.']);
    // Shot, it is one reference clip, and the words that go with it are the shot's and the line that names it.
    await page.evaluate(() => { tl.staging_say = 'own'; bench.commit(); });
    writes.length = 0;
    await page.locator('.mmc-reel-shoot').click();
    await page.waitForFunction(() => window.queued > 0, null, { timeout: 20000 });
    const clip = await page.evaluate(() => { const a = S.stagedClip(tl.segments[1]); return [a.role, /-labelled\.mp4$/.test(a.filename), tl.segments[1].staging.words.replace(`@${a.handle}`, '@clip')]; });
    assert.deepEqual(clip, ['reference', true, 'The camera, framing and staging follow @clip, a rough blockout of this shot. Its colours and name tags only say who and what each block is: they are not part of the picture.']);
    assert.ok(writes.some((body) => body.op === 'labelled'), JSON.stringify(writes));
  });

  await check('Depth as alpha lays the clip over black by how near it is: far fades, near stays, and it is another clip', async () => {
    await open();
    await page.waitForTimeout(120);
    await page.evaluate(() => { bench.select({ kind: 'shot', index: 1 }); bench.setView('guide'); });
    await page.waitForTimeout(120);
    // The mean light of the top third (the far wall) and of the bottom rows (the floor at the camera's feet).
    const light = () => page.evaluate(() => {
      const canvas = document.querySelector('.mmc-st > canvas');
      const context = canvas.getContext('2d');
      const mean = (y, rows) => { const d = context.getImageData(0, y, canvas.width, rows).data; let sum = 0; for (let i = 0; i < d.length; i += 4) sum += d[i] + d[i + 1] + d[i + 2]; return sum / (d.length / 4) / 3; };
      return [mean(Math.round(canvas.height * 0.3), 8), mean(canvas.height - 9, 8)];
    });
    const name = () => page.evaluate(() => S.stagedGuideName(tl, 1));
    const plain = await light(), before = await name();
    await page.locator('.mmc-st-gets .mmc-reel-irow', { hasText: 'Depth as alpha' }).locator('.mmc-reel-switch').click();
    await page.waitForTimeout(150);
    const faded = await light();
    // A kitchen is a few metres deep on the depth pass's own scale of twenty-five, so its far wall loses a fifth.
    assert.ok(faded[0] < plain[0] * 0.85, `the far wall fades: ${JSON.stringify([plain, faded])}`);
    assert.ok(faded[1] > plain[1] * 0.85 && faded[1] / plain[1] > faded[0] / plain[0] + 0.05, `the near floor fades less: ${JSON.stringify([plain, faded])}`);
    assert.deepEqual(await page.evaluate(() => [tl.segments[1].staging.depth, S.stagingDepth(tl, tl.segments[1]), S.stagingDepth(tl, tl.segments[0]),
      /depth as alpha$/.test(document.querySelector('.mmc-st-file').textContent), S.isKept(tl.segments[1])]), [true, true, false, true, false]);
    assert.notEqual(await name(), before);
    // A traced pass has no footage to lay it into, and the switch goes with it.
    await page.locator('.mmc-st-gets').getByText('Depth', { exact: true }).click();
    await page.waitForTimeout(80);
    assert.deepEqual(await page.evaluate(() => [S.stagingDepth(tl, tl.segments[1]),
      [...document.querySelectorAll('.mmc-st-gets .mmc-reel-ilabel')].map((n) => n.textContent)]), [false, ['Guide', 'Words']]);
  });


  // ---- Stagehand: the agent's window over the inspector --------------------------------

  const refiner = (block) => page.evaluate((block) => {
    if (block) localStorage.setItem('continuity.refiner', JSON.stringify(block)); else localStorage.removeItem('continuity.refiner');
  }, block);
  const handState = () => page.evaluate(() => {
    const win = document.querySelector('.mmc-sh');
    return { open: !win.hidden, pressed: document.querySelector('.mmc-st-handbtn').getAttribute('aria-pressed'),
      model: win.querySelector('.mmc-sh-model').textContent, size: win.querySelector('.mmc-sh-size').textContent,
      box: win.querySelector('.mmc-sh-box').contentEditable === 'false', send: [win.querySelector('.mmc-sh-send').textContent, win.querySelector('.mmc-sh-send').disabled],
      note: win.querySelector('.mmc-sh-note').hidden ? '' : win.querySelector('.mmc-sh-note').textContent };
  });
  const lines = () => page.evaluate(() => [...document.querySelector('.mmc-sh-log').children].map((node) =>
    `${node.className.replace('mmc-sh-', '')}: ${(node.querySelector('summary') ?? node).textContent}${node.querySelectorAll('.mmc-sh-pic').length ? ` [${node.querySelectorAll('.mmc-sh-pic').length}]` : ''}`));
  const locks = () => page.evaluate(() => ({
    working: bench.locked, modal: bench.modal.classList.contains('mmc-agent-working'),
    inert: [bench.scriptEl.inert, bench.inspectHost.inert, bench.hudBottom.inert],
    shoot: [bench.shootButton.disabled, bench.shootButton.title], undo: bench.undoButton.disabled,
    status: document.querySelector('.mmc-reel-status .mmc-reel-hint').textContent,
    pill: bench.agentPill.hidden ? '' : bench.agentPill.textContent, dot: !bench.handDot.hidden }));
  const say = async (words) => {
    await page.locator('.mmc-sh-box').fill(words);
    await page.locator('.mmc-sh-box').press('Enter');
  };
  /** Let the next exchange answer, and wait until the one after it is asked or the message is over. */
  const step = async () => {
    const asked = hand.sent.length;
    while (!hand.waiting.length) await page.waitForTimeout(10);
    hand.go();
    for (let tries = 0; tries < 300; tries++) {
      if (hand.sent.length > asked && hand.waiting.length) return;
      if (!(await page.evaluate(() => bench.locked))) return;
      await page.waitForTimeout(10);
    }
    throw new Error('the exchange never ended');
  };

  await check('Stagehand opens as a window over the inspector, and closes again', async () => {
    await refiner({ backend: 'remote', remoteModel: 'Bonsai-27B' });
    await open();
    await page.waitForTimeout(200);
    assert.deepEqual([(await handState()).open, (await handState()).pressed], [false, 'false']);
    await page.locator('.mmc-st-handbtn').click();
    await page.waitForTimeout(100);
    const shown = await handState();
    assert.deepEqual([shown.open, shown.pressed, shown.box, shown.send, shown.note], [true, 'true', false, ['Send', false], '']);
    assert.equal(shown.model, 'Bonsai-27B · on 192.168.1.20');
    assert.equal(shown.size, 'Designed for larger models, 27B and up.');
    const over = await page.evaluate(() => {
      const win = document.querySelector('.mmc-sh').getBoundingClientRect(), side = document.querySelector('.mmc-reel-side').getBoundingClientRect();
      const stage = document.querySelector('.mmc-st').getBoundingClientRect(), script = document.querySelector('.mmc-reel-script').getBoundingClientRect();
      return { inside: win.right <= side.right && win.top >= side.top && win.bottom <= side.bottom, wide: win.width > side.width * 0.9,
        clear: win.left > stage.left + stage.width * 0.8 && script.right < win.left, inspector: Boolean(document.querySelector('.mmc-reel-side .mmc-reel-ihead')),
        shadow: getComputedStyle(document.querySelector('.mmc-sh')).boxShadow !== 'none' };
    });
    assert.deepEqual(over, { inside: true, wide: true, clear: true, inspector: true, shadow: true });
    assert.match((await lines())[0], /^empty: Say what the set should be/);
    // Escape closes the window before it closes the bench.
    await page.keyboard.press('Escape');
    assert.deepEqual([(await handState()).open, await page.evaluate(() => document.querySelectorAll('.mmc-overlay').length)], [false, 1]);
    await page.locator('.mmc-st-handbtn').click();
    await page.locator('.mmc-sh-x').click();
    assert.equal((await handState()).open, false);
  });

  await check('An @ in a message lists the piece\'s cast, then the cast library; somebody picked from there is cast onto the piece', async () => {
    // One kept member, as the library's index holds them.
    await page.evaluate(async () => {
      const { api } = await import('/scripts/api.js');
      const P = await import('/ext/web/creator/presets.js');
      const real = api.getUserData;
      api.getUserData = async () => new Response(JSON.stringify({ presets: [{ id: 'vera', name: 'vera', scope: 'cast', builtin: true, updated: 1,
        note: 'A night guard.', facts: {}, data: { cast: { handle: 'vera', takes: 'person', description: 'A night guard.', files: [] } } }] }), { status: 200 });
      await P.listPresets({ force: true });
      api.getUserData = real;
    });
    const box = page.locator('.mmc-sh-box');
    const listed = () => page.evaluate(() => {
      const list = document.querySelector('.mmc-mention');
      return list ? { heads: [...list.querySelectorAll('.mmc-mention-head')].map((node) => node.textContent),
        names: [...list.querySelectorAll('.mmc-mention-handle')].map((node) => node.textContent) } : null;
    });
    const state = () => page.evaluate(() => ({ words: bench.handWindow.box.getValue(), draft: bench.agent.draft,
      cast: bench.timeline.subjects.map((member) => member.handle), open: !document.querySelector('.mmc-sh').hidden }));
    // The box's own grace for a press landing on a menu row, after the window before closed.
    await page.waitForTimeout(200);
    await page.locator('.mmc-st-handbtn').click();
    await box.click();
    await page.keyboard.type('Put @');
    await page.waitForTimeout(150);
    const all = await listed();
    assert.deepEqual(all.names.slice(0, 3), ['@anna', '@ben', '@vera'], JSON.stringify(all));
    await page.keyboard.type('be');
    await page.waitForTimeout(80);
    assert.deepEqual((await listed()).names, ['@ben']);
    await page.keyboard.press('Enter');
    await page.waitForTimeout(80);
    assert.deepEqual([await listed(), (await state()).words.trim(), (await state()).open], [null, 'Put @ben', true]);
    await page.keyboard.type(' beside @ver');
    await page.waitForTimeout(80);
    assert.deepEqual((await listed()).names, ['@vera']);
    await page.keyboard.press('Enter');
    await page.waitForTimeout(200);
    const cast = await state();
    assert.deepEqual([cast.cast, cast.words.replace(/\s+/g, ' ').trim(), cast.draft === cast.words], [['anna', 'ben', 'vera'], 'Put @ben beside @vera', true]);
    await page.keyboard.type(' and @');
    await page.waitForTimeout(80);
    await page.keyboard.press('Escape');
    await page.waitForTimeout(80);
    assert.deepEqual([await listed(), (await state()).open], [null, true], 'Escape closes the list, not the window');
    await page.evaluate(() => { bench.handWindow.box.setValue(''); bench.agent.draft = ''; bench.timeline.subjects.pop(); bench.commit(); });
    await page.locator('.mmc-st-handbtn').click();
  });

  await check('Its header names the refiner\'s model on either backend, and Change opens the refiner\'s settings', async () => {
    await refiner({ backend: 'local', model: 'qwen35_27b' });
    await page.locator('.mmc-st-handbtn').click();
    assert.equal((await handState()).model, 'qwen35_27b · in ComfyUI');
    const before = await page.evaluate(() => document.querySelectorAll('.mmc-refine-pop').length);
    await page.locator('.mmc-sh-row .mmc-sh-btn', { hasText: 'Change' }).click();
    await page.waitForTimeout(150);
    assert.equal(await page.evaluate(() => document.querySelectorAll('.mmc-refine-pop').length), before + 1);
    await page.keyboard.press('Escape');
    await page.waitForTimeout(100);
    await page.evaluate(() => document.querySelectorAll('.mmc-refine-pop').forEach((node) => node.remove()));
  });

  await check('With no model selected the composer is shut, and says where one is chosen', async () => {
    await refiner({ backend: 'remote', remoteModel: '' });
    await page.evaluate(() => bench.handWindow.render());
    const remote = await handState();
    assert.deepEqual([remote.model, remote.box, remote.send], ['No model selected', true, ['Send', true]]);
    assert.equal(remote.note, 'No model chosen. Pick one of the server\'s models in the refiner\'s settings.Open the refiner\'s settings');
    await refiner(null);
    await page.evaluate(() => bench.handWindow.render());
    assert.match((await handState()).note, /^No text encoder chosen\. .* pick it in the refiner's settings\.Open the refiner's settings$/);
    await page.evaluate(() => { bench.handWindow.box.disabled = false; bench.handWindow.box.value = 'go'; bench.handWindow.send(); });
    assert.deepEqual([hand.sent.length, await page.evaluate(() => bench.locked)], [0, false], 'nothing is asked of no model');
    await refiner({ backend: 'remote', remoteModel: 'Bonsai-27B', eject: true });
    await page.evaluate(() => bench.handWindow.render());
    assert.deepEqual([(await handState()).box, (await handState()).note], [false, '']);
  });

  await check('A message works in the bench while you watch: each call lands before the next, editing waits, and it is one step back', async () => {
    await open();
    await page.waitForTimeout(200);
    await page.locator('.mmc-st-handbtn').click();
    const before = await page.evaluate(() => ({ text: S.serializeTimeline(tl), steps: bench.done.length, objects: tl.sets[0].objects.length,
      kept: S.isKept(tl.segments[0]), view: JSON.stringify(Object.values(bench.freeCam()).map((v) => Math.round(v * 100) / 100)),
      meta: document.querySelector('.mmc-reel-meta').textContent }));
    hand.script = [
      [['add_objects', { objects: [{ what: 'block', x: 0, z: 1, name: 'crate' }, { what: 'lamp', x: 9, z: 99 }] }]],
      [['write_film_text', { look: 'A kitchen at night, one lamp.' }]],
      [['change_shot', { shot: 1, seconds: 6 }], ['move_object', { id: 99, x: 0 }]],
      [['look_through_camera', { shot: 1 }]],
      'The crate is by the table and shot 1 runs 6 seconds.'];
    hand.sent.length = 0;
    await say('Add a crate and make shot 1 longer.');
    while (!hand.sent.length) await page.waitForTimeout(10);
    // Asked, and not yet answered: the bench is for looking.
    const locked = await locks();
    assert.deepEqual([locked.working, locked.modal, locked.inert, locked.undo, locked.dot], [true, true, [true, true, true], true, true]);
    assert.deepEqual(locked.shoot, [true, 'Stagehand is working. Stop it to shoot.']);
    assert.equal(locked.status, 'Stagehand is working. You can look around; editing waits until it is done or stopped.');
    assert.equal(locked.pill, 'Stagehand: working');
    assert.deepEqual(await lines(), ['user: Add a crate and make shot 1 longer.', 'working: Working']);
    assert.deepEqual([(await handState()).send, (await handState()).box], [['Stop', false], true]);
    const { session, messages, tools, seen, client_id, ...asked } = hand.sent[0];
    assert.deepEqual(asked, { backend: 'remote', model: 'Bonsai-27B', device: '', eject: true });
    assert.match(messages[0].content, /^Add a crate and make shot 1 longer\.\n\nThe bench has shot 1 open, at 0 s\. The glass shows the set "Kitchen"\. Nothing is selected\. The frame is \d+ by \d+\. The longest shot this film's model renders is 60 s\.\n\nFilm: /);
    assert.match(messages[0].content, /\nShot 1: 5 s, on set "Kitchen", has a kept take that a change to the shot releases\. Text: /);
    // A hand on the glass turns the view and moves nothing; keys that write wait.
    const box = await page.locator('.mmc-st > canvas').boundingBox();
    const spot = await page.evaluate(() => { const at = bench.raster && null; const p = tl.sets[0].objects.find((o) => o.id === 5); return [p.x, p.z]; });
    await page.evaluate(() => bench.select({ kind: 'thing', id: 5 }));
    await page.keyboard.press('Delete');
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down(); await page.mouse.move(box.x + box.width / 2 + 60, box.y + box.height / 2 + 20, { steps: 4 }); await page.mouse.up();
    await page.keyboard.press('Control+z');
    // The drag turned the view, which is looking; the piece's objects and its steps are as they were.
    const looked = await page.evaluate(() => { const p = tl.sets[0].objects.find((o) => o.id === 5); return [p.x, p.z, tl.sets[0].objects.length, bench.done.length, JSON.stringify(Object.values(bench.freeCam()).map((v) => Math.round(v * 100) / 100))]; });
    assert.deepEqual(looked.slice(0, 4), [...spot, before.objects, before.steps]);
    assert.notEqual(looked[4], before.view);
    before.view = looked[4];
    await page.evaluate(() => bench.select(null));

    // The first call: the crate is on the stage and the transcript before the model is asked again.
    await step();
    const first = await page.evaluate(() => ({ objects: tl.sets[0].objects.map((o) => o.word || o.kind).slice(-1), steps: bench.done.length,
      lit: [...(bench.litThings ?? [])], locked: bench.locked }));
    assert.deepEqual(first, { objects: ['crate'], steps: before.steps, lit: [9], locked: true });
    assert.deepEqual((await lines()).slice(1), ['call: ✓Added 1 object to the set Kitchen [1]', 'working: Working']);
    assert.equal(hand.sent.length, 2, 'and only then is the next asked');
    // The second: the words are in the script, whole, and lit.
    await step();
    assert.deepEqual(await page.evaluate(() => [tl.prompt, bench.promptBox.getValue(), bench.promptBox.frame.classList.contains('mmc-st-lit')]),
      ['A kitchen at night, one lamp.', 'A kitchen at night, one lamp.', true]);
    assert.equal((await lines()).at(-2), 'call: ✓Wrote the film\'s text');
    // The third: the shot is longer on the strip, its kept take is released, and the refused call is drawn as that.
    await step();
    assert.deepEqual(await page.evaluate(() => [tl.segments[0].duration_s, S.isKept(tl.segments[0]), document.querySelector('.mmc-reel-meta').textContent]),
      [6, false, '3 shots · 14.8 s']);
    assert.notEqual(before.meta, '3 shots · 14.8 s', 'the header follows');
    assert.equal(before.kept, true);
    assert.deepEqual((await lines()).slice(-3, -1), ['call: ✓Shot 1 is 6 s now', 'call refused: ✕Refused: Moved #99. there is no object #99 in the set "Kitchen"']);
    // The fourth: what it looked at is in the transcript, and can be enlarged.
    await step();
    assert.equal((await lines()).at(-2), 'call looks: ◉Looked through the camera of shot 1 [1]');
    assert.equal((await locks()).pill, 'Stagehand: looking through the camera of shot 1');
    await page.locator('.mmc-sh-call.looks .mmc-sh-pic').click();
    assert.equal(await page.locator('.mmc-sh-zoom img').count(), 1);
    await page.locator('.mmc-sh-zoom').click();
    assert.equal(await page.locator('.mmc-sh-zoom').count(), 0);
    // A line opens to the tool's own answer.
    await page.locator('.mmc-sh-call summary').first().click();
    assert.match(await page.locator('.mmc-sh-call .mmc-sh-answer').first().textContent(), /^Added #9 block "crate", at x 0, z 1, .*\nObject 2 of the list was not added: z has to be between -40 and 40/s);
    assert.equal(await page.evaluate(() => JSON.stringify(Object.values(bench.freeCam()).map((v) => Math.round(v * 100) / 100))), before.view, 'the glass keeps the view the person has');

    // Its last words: the bench is the person's again without a click.
    await step();
    const free = await locks();
    assert.deepEqual([free.working, free.modal, free.inert, free.shoot[0], free.shoot[1], free.undo, free.pill, free.dot],
      [false, false, [false, false, false], false, '', false, '', false]);
    assert.notEqual(free.status, locked.status);
    assert.equal((await lines()).at(-1), 'say: The crate is by the table and shot 1 runs 6 seconds.');
    assert.deepEqual((await handState()).send, ['Send', false]);
    assert.equal(hand.stops.length, 0);
    // One message, one step back; and forward again.
    assert.equal(await page.evaluate(() => bench.done.length), before.steps + 1);
    await page.locator('.mmc-reel-step:not(.redo)').click();
    assert.deepEqual(await page.evaluate(() => [S.serializeTimeline(tl), bench.done.length, tl.sets[0].objects.length]), [before.text, before.steps, before.objects]);
    await page.locator('.mmc-reel-step.redo').click();
    assert.deepEqual(await page.evaluate(() => [tl.sets[0].objects.at(-1).word, tl.segments[0].duration_s, tl.prompt]), ['crate', 6, 'A kitchen at night, one lamp.']);
    // The conversation is not rewound by a step back: the next message carries the scene as it stands.
    await page.locator('.mmc-reel-step:not(.redo)').click();
    hand.script = ['Nothing to do.'];
    hand.sent.length = 0;
    await say('And now?');
    await step();
    assert.match(hand.sent[0].messages.at(-1).content, /\nSet "Kitchen", 8 objects:\n/);
    assert.equal(hand.sent[0].messages.length > 8, true);
  });

  await check('A change of set is followed by the glass, and a change by hand is free the moment it is done', async () => {
    hand.script = [[['use_set', { name: 'Street' }]], 'On the street.'];
    await page.evaluate(() => bench.select({ kind: 'shot', index: 0 }));
    assert.equal(await page.evaluate(() => bench.set().name), 'Kitchen');
    await say('Go to the street.');
    await step();
    assert.equal(await page.evaluate(() => bench.set().name), 'Street');
    await step();
    // No step for a message that changed nothing, and a drag by hand works at once.
    const steps = await page.evaluate(() => bench.done.length);
    await page.evaluate(() => { bench.select({ kind: 'thing', id: 2 }); });
    await page.keyboard.press('Delete');
    assert.deepEqual(await page.evaluate(() => [tl.sets[1].objects.some((o) => o.id === 2), bench.done.length]), [false, steps + 1]);
    await page.keyboard.press('Control+z');
  });

  await check('A picture attached goes out with the message, scaled, and is shown with it', async () => {
    const png = Buffer.from(await page.evaluate(() => {
      const canvas = Object.assign(document.createElement('canvas'), { width: 2400, height: 1200 });
      const context = canvas.getContext('2d');
      context.fillStyle = '#356'; context.fillRect(0, 0, 2400, 1200); context.fillStyle = '#fc8'; context.fillRect(300, 200, 900, 500);
      return canvas.toDataURL('image/png').split(',')[1];
    }), 'base64');
    const files = [1, 2, 3, 4, 5].map((n) => ({ name: `kitchen-${n}.png`, mimeType: 'image/png', buffer: png }));
    await page.locator('.mmc-sh input[type=file]').setInputFiles(files);
    await page.waitForFunction(() => document.querySelectorAll('.mmc-sh-chip').length === 4);
    assert.match((await handState()).note, /^A message carries up to 4 pictures\./);
    await page.locator('.mmc-sh-chip button').nth(3).click();
    await page.locator('.mmc-sh-chip button').nth(2).click();
    assert.deepEqual(await page.evaluate(() => [...document.querySelectorAll('.mmc-sh-chip span')].map((n) => n.textContent)), ['kitchen-1.png', 'kitchen-2.png']);
    // Dropped on the window, one more.
    await page.evaluate(async (b64) => {
      const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
      const data = new DataTransfer();
      data.items.add(new File([bytes], 'dropped.png', { type: 'image/png' }));
      data.items.add(new File(['words'], 'notes.txt', { type: 'text/plain' }));
      document.querySelector('.mmc-sh').dispatchEvent(new DragEvent('drop', { dataTransfer: data, bubbles: true, cancelable: true }));
    }, png.toString('base64'));
    await page.waitForFunction(() => document.querySelectorAll('.mmc-sh-chip').length === 3);
    hand.script = ['I see a kitchen.'];
    hand.sent.length = 0;
    await say('Like this.');
    while (!hand.sent.length) await page.waitForTimeout(10);
    const { content } = hand.sent[0].messages.at(-1);
    assert.deepEqual(content.map((part) => part.type), ['image_url', 'image_url', 'image_url', 'text']);
    assert.match(content[3].text, /^Like this\.\n\nThe bench has /);
    const sizes = await page.evaluate(async (urls) => Promise.all(urls.map(async (url) => {
      const picture = new Image(); picture.src = url; await picture.decode(); return [url.slice(0, 23), picture.naturalWidth, picture.naturalHeight];
    })), content.slice(0, 3).map((part) => part.image_url.url));
    assert.deepEqual(sizes, [['data:image/jpeg;base64,', 1024, 512], ['data:image/jpeg;base64,', 1024, 512], ['data:image/jpeg;base64,', 1024, 512]]);
    assert.equal(await page.locator('.mmc-sh-chip').count(), 0);
    assert.equal((await lines()).at(-2), 'user: Like this. [3]');
    await step();
    assert.equal(await page.evaluate(() => (tl.assets ?? []).length + tl.segments.reduce((n, card) => n + (card.assets?.length ?? 0), 0)), 0, 'a picture said is not a reference of the piece');
  });

  await check('Stop ends it at once and gives the bench back, with what was done as one step', async () => {
    const before = await page.evaluate(() => ({ steps: bench.done.length, text: S.serializeTimeline(tl) }));
    hand.script = [[['add_objects', { objects: [{ what: 'post', x: 3, z: 3, name: 'sign' }] }]], [['add_objects', { objects: [{ what: 'post', x: 4, z: 3 }] }]]];
    hand.stops.length = 0; hand.sent.length = 0;
    await say('Put up signs.');
    await step();
    assert.equal((await locks()).working, true);
    await page.locator('.mmc-sh-send', { hasText: 'Stop' }).click();
    await page.waitForFunction(() => !bench.locked);
    const after = await locks();
    assert.deepEqual([after.modal, after.inert, after.shoot[0], after.pill], [false, [false, false, false], false, '']);
    assert.equal((await lines()).at(-1), 'quiet: Stopped. What was done stays, as one step to undo.');
    assert.deepEqual(await page.evaluate(() => [bench.set().objects.at(-1).word, bench.done.length]), ['sign', before.steps + 1]);
    for (let tries = 0; tries < 100 && !hand.stops.length; tries++) await page.waitForTimeout(10);
    assert.equal(hand.stops.length, 1);
    hand.go();
    await page.keyboard.press('Control+z');
    assert.equal(await page.evaluate(() => S.serializeTimeline(tl)), before.text);
    // And the conversation goes on from it.
    hand.script = ['Yes.'];
    await say('Still there?');
    await step();
    assert.equal((await lines()).at(-1), 'say: Yes.');
  });

  await check('A failure is said in the server\'s words, and New conversation forgets what was said', async () => {
    await page.evaluate(() => { bench.agent.hand.ask = async () => { throw new Error('the server answered 400: the request exceeds the available context size'); }; });
    await say('More.');
    await page.waitForFunction(() => !bench.locked);
    assert.equal((await lines()).at(-1), 'error: the server answered 400: the request exceeds the available context sizeNew conversation');
    assert.equal((await locks()).working, false);
    const text = await page.evaluate(() => S.serializeTimeline(tl));
    await page.locator('.mmc-sh-error .mmc-sh-btn').click();
    assert.match((await lines())[0], /^empty: /);
    assert.deepEqual(await page.evaluate(() => [bench.agent.hand.messages.length, S.serializeTimeline(tl)]), [0, text]);
  });

  await check('Closing the bench does not stop it: opened again, the conversation is there and still working', async () => {
    hand.script = [[['add_objects', { objects: [{ what: 'block', x: -2, z: 1, name: 'box' }] }]], [['add_objects', { objects: [{ what: 'block', x: -3, z: 1, name: 'box two' }] }]], 'Two boxes.'];
    hand.sent.length = 0;
    await page.evaluate(() => { window.wrote = 0; });
    await say('Two boxes.');
    await step();
    await page.evaluate(() => bench.close());
    assert.equal(await page.evaluate(() => document.querySelectorAll('.mmc-overlay').length), 0);
    // With no window open the call still lands in the piece.
    await step();
    assert.deepEqual(await page.evaluate(() => tl.sets.find((set) => set.objects.some((o) => o.word === 'box')).objects.slice(-2).map((o) => o.word)), ['box', 'box two']);
    await page.evaluate(async () => {
      const B = await import('/ext/web/creator/staging.js');
      B.openStaging({ timeline: tl, onCommit: () => {}, queue: () => {}, opened: (bench) => { window.bench = bench; bench.plan = false; } });
    });
    await page.waitForTimeout(200);
    const again = await locks();
    assert.deepEqual([again.working, again.modal, again.shoot[0], again.dot], [true, true, true, true]);
    await page.locator('.mmc-st-handbtn').click();
    assert.deepEqual((await lines()).slice(-3), ['call: ✓Added 1 object to the set Street [1]', 'call: ✓Added 1 object to the set Street [1]', 'working: Working']);
    const steps = await page.evaluate(() => bench.done.length);
    await step();
    assert.deepEqual([(await locks()).working, (await lines()).at(-1), await page.evaluate(() => bench.done.length)], [false, 'say: Two boxes.', steps + 1]);
  });

  if (process.env.SHOT) {
    await open();
    await page.waitForTimeout(300);
    await page.evaluate(() => { bench.setLook('plan'); bench.select({ kind: 'shot', index: 1 }); bench.at.t = 2; bench.select({ kind: 'thing', id: 8 }); });
    await page.waitForTimeout(300);
    await page.screenshot({ path: process.env.SHOT });
    await page.evaluate(() => { bench.setLook('lens'); bench.select({ kind: 'shot', index: 1 }); });
    await page.waitForTimeout(300);
    await page.screenshot({ path: process.env.SHOT.replace('.png', '2.png') });
    // Stagehand at work: a message under way, its lines and what it looked at.
    await refiner({ backend: 'remote', remoteModel: 'Bonsai-27B' });
    await page.evaluate(() => { bench.setLook('around'); bench.select(null); });
    await page.locator('.mmc-st-handbtn').click();
    hand.script = [[['add_objects', { objects: [{ what: 'lamp', x: 0.4, z: 2.6, name: 'lamp' }] }]], [['change_shot', { shot: 1, seconds: 6 }], ['move_object', { id: 99, x: 0 }]],
      [['look_through_camera', { shot: 1 }]]];
    await say('Put a lamp by the counter and give shot 1 another second.');
    for (let n = 0; n < 3; n++) await step();
    await page.waitForTimeout(300);
    await page.screenshot({ path: process.env.SHOT.replace('.png', '3.png') });
    await page.locator('.mmc-sh-send').click();
  }

  assert.deepEqual(errors, []);
  assert.equal(requests, 0, 'Fixture attempted a network request');
  console.log(JSON.stringify({ passed: results.length, requests, media, results }, null, 2));
})().catch((error) => { console.error(error); process.exitCode = 1; }).finally(async () => { await browser?.close(); });

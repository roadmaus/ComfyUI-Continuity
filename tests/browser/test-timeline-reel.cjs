// Isolated browser checks for the timeline's reel: the real timeline.js, state.js
// and CSS, loaded as ES modules from this checkout into a fresh headless page.
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
  + "  async fetchApi(url) { return url.startsWith('/continuity/families') ? ok(CATALOG) : ok({}); },\n"
  + "  apiURL: (u) => u, getUserData: async () => new Response('{}', { status: 404 }),\n"
  + "  storeUserData: async () => {}, addEventListener() {}, removeEventListener() {},\n"
  + "};\n";
const appStub = `export const app = { graph: { _nodes: [] }, extensionManager: { setting: { get() {} } }, ui: { settings: { getSettingValue() {} } } }; globalThis.app = app;`;

let browser, requests = 0, media = 0;
const results = [];
async function check(name, fn) { await fn(); results.push({ name, passed: true }); }

(async () => {
  browser = await chromium.launch({ executablePath: process.env.BROWSER_EXECUTABLE_PATH || undefined, headless: true });
  const page = await browser.newPage({ viewport: { width: 1500, height: 950 } });
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
      return route.fulfill({ status: 404, body: '' });
    }
    requests++;
    return route.abort();
  });
  await page.goto(`${ORIGIN}/`);
  await page.addStyleTag({ content: ':root{--comfy-menu-bg:#353535;--input-text:#ddd;--descrip-text:#999;--fg-color:#fff;--bg-color:#202020;--error-text:#f44} body{margin:0;background:#202020;font-family:Arial}' });
  const opened = await page.evaluate(async () => {
    (await import('/ext/web/creator/styles.js')).installStyles();
    const S = await import('/ext/web/creator/state.js');
    const T = await import('/ext/web/creator/timeline.js');
    const tl = S.emptyTimeline();
    tl.prompt = 'Night at a black lake. @wader walks in.';
    tl.assets = [{ handle: 'ref-1', kind: 'image', role: 'reference', filename: 'cast/wader.png' },
                 { handle: 'ref-2', kind: 'image', role: 'reference', filename: 'refs/poster.png' }];
    tl.subjects = [{ handle: 'wader', takes: 'person', from: ['ref-1'] }];
    const shot = (prompt, cont) => Object.assign(cont ? S.continuingSegment(tl) : S.emptySegment(), { prompt, duration_s: 5 });
    tl.segments = [shot('He walks through the trees.', false), shot('He wades in.', true),
                   shot('Close on the skull, lit like @ref-2.', false)];
    tl.segments[2].assets = [{ handle: 'img-1', kind: 'image', role: 'first_frame', filename: 'refs/key.png' }];
    S.ensureCardIds(tl); S.syncTimeline(tl);
    S.attachTakes(tl, [1, 2, 3].map((n) => ({ segment: n, filename: `takes/s${n}.mp4`, duration_s: 5, has_audio: true })));
    window.S = S; window.tl = tl; window.queued = 0;
    T.openTimeline({ timeline: tl, onCommit: () => {}, queue: () => { window.queued++; },
      opened: (reel) => { window.reel = reel; } });
    return 'ok';
  });
  assert.equal(opened, 'ok');
  await page.waitForTimeout(150);

  await check('The window is one surface: no disclosures, shelves or pill bar', async () => {
    assert.deepEqual(await page.evaluate(() => ({
      sections: document.querySelectorAll('.mmc-reel .mmc-tl-section').length,
      oldStrip: document.querySelectorAll('.mmc-reel .mmc-tl-card, .mmc-reel .mmc-tl-bar').length,
      labels: [...document.querySelectorAll('.mmc-reel-script .mmc-reel-label')].map((n) => n.textContent),
      rows: document.querySelectorAll('.mmc-reel-shots .mmc-reel-row').length,
      faces: [...document.querySelectorAll('.mmc-reel-face-name')].map((n) => n.textContent),
    })), { sections: 0, oldStrip: 0, labels: ['Scene', 'Sound', 'Score'], rows: 3, faces: ['@wader', '@ref-2'] });
  });

  await check('Nothing selected shows the piece, and every take is kept', async () => {
    assert.deepEqual(await page.evaluate(() => ({
      head: document.querySelector('.mmc-reel-ihead b').textContent,
      rows: [...document.querySelectorAll('.mmc-reel-ilabel')].map((n) => n.textContent).slice(0, 4),
      plan: document.querySelector('.mmc-reel-plan').textContent,
      shoot: document.querySelector('.mmc-reel-shoot').disabled,
      tags: document.querySelectorAll('.mmc-reel-card-tag').length,
    })), { head: 'Piece', rows: ['Model', 'Frame', 'Resolution', 'Look'],
           plan: 'Every shot is kept. Change one, or reshoot it, to shoot again.', shoot: true, tags: 0 });
  });

  await check('Editing a kept shot releases it and the shot that continues from it', async () => {
    await page.locator('.mmc-reel-shots .mmc-prompt').first().click();
    await page.keyboard.press('End');
    await page.keyboard.type(' Slowly.');
    assert.deepEqual(await page.evaluate(() => ({
      held: tl.segments.map((s) => S.isHeld(s)),
      tags: [...document.querySelectorAll('.mmc-reel-card-tag')].map((n) => n.textContent),
      plan: document.querySelector('.mmc-reel-plan').textContent,
    })), { held: [false, false, true], tags: ['Changed, reshoots', 'Reshoots'],
           plan: 'Next render shoots 2 shots, plays 1 kept' });
  });

  await check('Shoot queues the node, and says so once the server has it', async () => {
    const button = () => page.evaluate(() => [window.queued, document.querySelector('.mmc-reel-shoot').textContent]);
    await page.locator('.mmc-reel-shoot').click();
    assert.deepEqual(await button(), [1, 'Shoot']);
    await page.evaluate(() => reel.accepted());
    assert.deepEqual(await button(), [1, 'Queued']);
  });

  await check('A refused Shoot says why and can be pressed again', async () => {
    await page.waitForTimeout(2100);
    await page.locator('.mmc-reel-shoot').click();
    await page.evaluate(() => reel.refused([{ what: 'Prompt has no outputs' }]));
    assert.deepEqual(await page.evaluate(() => [document.querySelector('.mmc-reel-plan').textContent,
      document.querySelector('.mmc-reel-shoot').textContent, document.querySelector('.mmc-reel-shoot').disabled]),
      ['Prompt has no outputs', 'Shoot', false]);
    await page.evaluate(() => { reel.refusal = null; reel.renderHead(); });
  });

  await check('A take that lands redraws the open window', async () => {
    const seen = await page.evaluate(() => {
      const before = document.querySelector('.mmc-reel-plan').textContent;
      const was = structuredClone(tl.segments.map((s) => ({ hold: s.hold, take: s.take })));
      S.attachTakes(tl, [1, 2].map((n) => ({ segment: n, filename: `takes/new${n}.mp4`, duration_s: 5, has_audio: true })));
      reel.landed();
      const after = document.querySelector('.mmc-reel-plan').textContent;
      const tags = document.querySelectorAll('.mmc-reel-card-tag').length;
      tl.segments.forEach((s, i) => { s.take = was[i].take; if (was[i].hold) s.hold = true; else delete s.hold; });
      reel.landed();
      return { before, after, tags };
    });
    assert.deepEqual(seen, { before: 'Next render shoots 2 shots, plays 1 kept',
      after: 'Every shot is kept. Change one, or reshoot it, to shoot again.', tags: 0 });
  });

  await check('Enter at the end of a shot starts the next one; Backspace in it takes it out', async () => {
    await page.locator('.mmc-reel-shots .mmc-prompt').nth(2).click();
    await page.keyboard.press('End');
    await page.keyboard.press('Enter');
    const grown = await page.evaluate(() => [tl.segments.length, document.activeElement === document.querySelectorAll('.mmc-reel-shots .mmc-prompt')[3]]);
    await page.keyboard.press('Backspace');
    const shrunk = await page.evaluate(() => tl.segments.length);
    assert.deepEqual([grown, shrunk], [[4, true], 3]);
  });

  await check('A join is cut with one click and its settings are all on the side', async () => {
    await page.locator('.mmc-reel-join').first().click();
    assert.deepEqual(await page.evaluate(() => ({
      continues: tl.segments[1].continue,
      head: document.querySelector('.mmc-reel-ihead b').textContent,
      rows: [...document.querySelectorAll('.mmc-reel-ilabel')].map((n) => n.textContent),
    })), { continues: false, head: 'Join 1 → 2', rows: ['Picture', 'Sound', 'Storyboard', 'One generation'] });
    await page.locator('.mmc-reel-join').first().click();
    const rows = await page.evaluate(() => [...document.querySelectorAll('.mmc-reel-ilabel')].map((n) => n.textContent));
    assert.ok(rows.includes('Blend'), rows.join(','));
  });

  await check('A join that cannot continue does not, and says why where it is', async () => {
    await page.locator('.mmc-reel-join').nth(1).click();
    assert.deepEqual(await page.evaluate(() => ({
      continues: tl.segments[2].continue,
      disabled: document.querySelector('.mmc-reel-seg.motion button').disabled,
      said: document.querySelector('.mmc-reel-icontrol .mmc-reel-note')?.textContent.length > 0,
    })), { continues: false, disabled: true, said: true });
  });

  await check('Reshoot on a kept shot names and releases what follows it', async () => {
    await page.evaluate(() => { S.attachTakes(tl, [1, 2, 3].map((n) => ({ segment: n, filename: `takes/t${n}.mp4`, duration_s: 5, has_audio: true }))); });
    await page.locator('.mmc-reel-card').first().click();
    const note = await page.locator('.mmc-reel-actions .mmc-reel-note').first().textContent();
    await page.locator('.mmc-reel-btn.primary').click();
    assert.deepEqual([note, await page.evaluate(() => tl.segments.map((s) => S.isHeld(s)))],
      ['Shot 2 continues from it and is shot again too.', [false, false, true]]);
  });

  await check('Faces and frames open the cast member and the reference', async () => {
    await page.locator('.mmc-reel-face').first().click();
    const member = await page.locator('.mmc-reel-ihead').textContent();
    await page.locator('.mmc-reel-face.frame').click();
    const reference = await page.locator('.mmc-reel-ihead').textContent();
    assert.ok(member.startsWith('@wader') && member.includes('in every shot'), member);
    assert.ok(reference.startsWith('@ref-2') && reference.includes('in shot 3'), reference);
  });

  await check('Dragging a shot\'s edge changes its length on the frame grid', async () => {
    const edge = page.locator('.mmc-reel-edge').first();
    const box = await edge.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + 120, box.y + box.height / 2, { steps: 6 });
    await page.mouse.up();
    const seconds = await page.evaluate(() => tl.segments[0].duration_s);
    assert.ok(seconds > 5 && seconds < 9, String(seconds));
  });

  assert.deepEqual(errors, []);
  assert.equal(requests, 0, 'Fixture attempted a network request');
  console.log(JSON.stringify({ passed: results.length, requests, media, results }, null, 2));
})().catch((error) => { console.error(error); process.exitCode = 1; }).finally(async () => { await browser?.close(); });

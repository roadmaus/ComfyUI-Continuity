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
           plan: 'Every shot is kept. The next render puts the piece together.', shoot: false, tags: 0 });
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
      after: 'Every shot is kept. The next render puts the piece together.', tags: 0 });
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

  await check('A join is selected by a click and changed on the side', async () => {
    const before = await page.evaluate(() => S.serializeTimeline(tl));
    await page.locator('.mmc-reel-join').first().click();
    await page.locator('.mmc-reel-sdot').first().click();
    assert.equal(await page.evaluate(() => S.serializeTimeline(tl)), before);
    await page.locator('.mmc-reel-seg.motion button').nth(1).click();
    assert.deepEqual(await page.evaluate(() => ({
      continues: tl.segments[1].continue,
      head: document.querySelector('.mmc-reel-ihead b').textContent,
      rows: [...document.querySelectorAll('.mmc-reel-ilabel')].map((n) => n.textContent),
    })), { continues: false, head: 'Join 1 → 2', rows: ['Picture', 'Sound', 'Storyboard', 'One generation'] });
    await page.locator('.mmc-reel-seg.motion button').first().click();
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

  // A fresh piece per check below, so each says what it starts from.
  const reset = (prompts, setup = '') => page.evaluate(([list, code]) => {
    tl.segments = list.map((prompt, i) => Object.assign(i ? S.continuingSegment(tl) : S.emptySegment(), { prompt, duration_s: 5 }));
    new Function('tl', 'S', code)(tl, S);
    S.ensureCardIds(tl); S.syncTimeline(tl);
    reel.arranged = S.arrangement(tl); reel.sel = null; reel.rows.clear(); reel.render();
  }, [prompts, setup]);
  const order = () => page.evaluate(() => tl.segments.map((s) => s.kind === 'clip' ? s.filename : s.prompt));
  const drag = async (from, x, y, { release = true } = {}) => {
    const box = await from.boundingBox();
    await page.mouse.move(box.x + 20, box.y + 12);
    await page.mouse.down();
    await page.mouse.move(x, y, { steps: 8 });
    if (release) await page.mouse.up();
  };
  await page.evaluate(() => {
    reel.pickClip = async () => S.clipSegment({ filename: 'mine.mp4', duration: 4, width: 1280, height: 720, hasAudio: true });
  });
  const keepAll = "S.ensureCardIds(tl); S.syncTimeline(tl); S.attachTakes(tl, tl.segments.map((_, i) => ({ segment: i + 1, filename: `k${i}.mp4`, duration_s: 5 })));";

  await check('A blank opening shot becomes a clip in place, and the next shot continues from it', async () => {
    await reset(['', '']);
    const said = await page.locator('.mmc-reel-useclip').first().textContent();
    await page.locator('.mmc-reel-useclip').first().click();
    assert.deepEqual([said, await order(), await page.evaluate(() => [tl.segments[0].kind, tl.segments[1].continue])],
      ['or start with a clip you already have', ['mine.mp4', ''], ['clip', true]]);
  });

  await check('A clip goes in front of a written first shot, which offers no replacing', async () => {
    await reset(['one', 'two']);
    assert.equal(await page.locator('.mmc-reel-useclip:visible').count(), 0);
    const gap = page.locator('.mmc-reel-gap').first();
    await gap.hover();
    await gap.locator('button').nth(1).click();
    assert.deepEqual(await order(), ['mine.mp4', 'one', 'two']);
  });

  await check('A card dragged on the reel moves, and the takes made from another one are released', async () => {
    await reset(['one', 'two', 'three', 'four'], keepAll + 'tl.segments[3].continue = tl.segments[3].continue_audio = false; tl.segments.forEach((s) => { delete s.take; delete s.hold; });' + keepAll);
    const target = await page.locator('.mmc-reel-card').nth(2).boundingBox();
    await drag(page.locator('.mmc-reel-card').nth(0), target.x + target.width - 20, target.y + 30);
    assert.deepEqual([await order(), await page.evaluate(() => tl.segments.map((s) => S.isHeld(s))),
      await page.evaluate(() => reel.sel)],
      [['two', 'three', 'one', 'four'], [false, false, true, true], { kind: 'shot', index: 2 }]);
  });

  await check('A number dragged in the script moves its shot', async () => {
    await reset(['one', 'two', 'three']);
    const row = await page.locator('.mmc-reel-shot').nth(0).boundingBox();
    await drag(page.locator('.mmc-reel-handle').nth(2), row.x + 40, row.y + 3);
    assert.deepEqual(await order(), ['three', 'one', 'two']);
  });

  await check('Escape puts a dragged card back and leaves the window open; a press still selects', async () => {
    await reset(['one', 'two', 'three']);
    const target = await page.locator('.mmc-reel-card').nth(2).boundingBox();
    await drag(page.locator('.mmc-reel-card').nth(0), target.x + target.width - 20, target.y + 30, { release: false });
    const marked = await page.locator('.mmc-reel-drop.reel').count();
    await page.keyboard.press('Escape');
    await page.mouse.up();
    assert.deepEqual([marked, await order(), await page.locator('.mmc-reel').count(), await page.locator('.mmc-reel-drop, .mmc-reel-ghostcard').count()],
      [1, ['one', 'two', 'three'], 1, 0]);
    await page.waitForTimeout(50);
    await page.locator('.mmc-reel-card').nth(1).click();
    assert.deepEqual(await page.evaluate(() => reel.sel), { kind: 'shot', index: 1 });
  });

  await check('A pass keeps together when a shot leaves it, and takes one dropped inside it', async () => {
    const merge = 'tl.segments[1].merge = tl.segments[2].merge = true;';
    const runs = () => page.evaluate(() => S.passes(tl).map((p) => p.segments.map((s) => s.prompt).join('+')));
    await reset(['a', 'b', 'c', 'd'], merge);
    await page.evaluate(() => reel.moveTo(0, 3));
    const left = await runs();
    await reset(['a', 'b', 'c', 'd'], merge);
    await page.evaluate(() => reel.moveTo(3, 1));
    assert.deepEqual([left, await runs()], [['b+c', 'd', 'a'], ['a+d+b+c']]);
  });

  await check('A seam that names its source still names it after a move', async () => {
    await reset(['a', 'b', 'c', 'd'], 'tl.segments[3].continue_from = 1;');
    await page.evaluate(() => reel.moveTo(0, 1));
    assert.equal(await page.evaluate(() => tl.segments[3].continue_from), 2);
  });

  // `reset` writes behind the window's back, so its undo starts over too.
  const fresh = () => page.evaluate(() => { reel.done = []; reel.undone = []; reel.lastField = null; reel.now = reel.capture(); reel.renderSteps(); });

  await check('Undo puts a drag and the takes it released back; redo does it again', async () => {
    await reset(['one', 'two', 'three'], keepAll);
    await fresh();
    await page.evaluate(() => reel.moveTo(0, 2));
    const moved = await page.evaluate(() => S.serializeTimeline(tl));
    await page.locator('.mmc-reel-step').first().click();
    const back = [await order(), await page.evaluate(() => tl.segments.map((s) => S.isHeld(s)))];
    await page.locator('.mmc-reel-step.redo').click();
    assert.deepEqual([back, await page.evaluate(() => S.serializeTimeline(tl)) === moved],
      [[['one', 'two', 'three'], [true, true, true]], true]);
  });

  await check('Typing is one step, undone from the keyboard with the caret in it, and not by ComfyUI too', async () => {
    await reset(['one', 'two']);
    await fresh();
    await page.evaluate(() => {
      window.comfyUndo = 0;
      window.addEventListener('keydown', (e) => requestAnimationFrame(() => {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') window.comfyUndo++;
      }), true);
    });
    await page.locator('.mmc-reel-shots .mmc-prompt').first().click();
    await page.keyboard.press('End');
    await page.keyboard.type(' more words');
    const typed = await order();
    await page.keyboard.press('Control+z');
    await page.waitForTimeout(60);
    assert.deepEqual([typed, await order(), await page.locator('.mmc-reel-shots .mmc-prompt').first().textContent(),
      await page.evaluate(() => window.comfyUndo)], [['one more words', 'two'], ['one', 'two'], 'one', 0]);
  });

  await check('The keys undo the piece ahead of ComfyUI even where its listener came first', async () => {
    const seen = await page.evaluate(async () => {
      let hit = 0;
      window.removeEventListener('keydown', reel.onUndoKey, true);
      window.addEventListener('keydown', (e) => requestAnimationFrame(() => { if (e.ctrlKey) hit++; }), true);
      window.addEventListener('keydown', reel.onUndoKey, true);
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'z', ctrlKey: true, cancelable: true }));
      await new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)));
      return hit;
    });
    assert.equal(seen, 0);
  });

  await check('A take that lands survives an undo', async () => {
    await reset(['one', 'two']);
    await fresh();
    const got = await page.evaluate(() => {
      reel.insertShot(2);
      S.attachTakes(tl, [1, 2].map((n) => ({ segment: n, filename: `land${n}.mp4`, duration_s: 5 })));
      reel.landed();
      reel.step(reel.done, reel.undone);
      return tl.segments.map((s) => [s.take?.filename, S.isHeld(s)]);
    });
    assert.deepEqual(got, [['land1.mp4 [output]', true], ['land2.mp4 [output]', true]]);
  });

  await check('A piece of clips alone can be put together, and an empty one cannot', async () => {
    const head = () => page.evaluate(() => [document.querySelector('.mmc-reel-plan').textContent,
      document.querySelector('.mmc-reel-shoot').textContent, document.querySelector('.mmc-reel-shoot').disabled]);
    await reset([], "tl.segments = [S.clipSegment({ filename: 'a.mp4', duration: 3, hasAudio: true })];");
    await page.evaluate(() => { clearTimeout(reel.shootTimer); reel.shootLabel = null; reel.renderHead(); });
    const clips = await head();
    await reset([]);
    assert.deepEqual([clips, await head()], [['Nothing to shoot. The next render puts your clips together.', 'Put together', false],
      ['Nothing in the piece yet.', 'Shoot', true]]);
  });

  await check('A blend leaves the cards it joins readable and their edges free', async () => {
    await reset(['one', 'two']);
    assert.equal(await page.evaluate(() => {
      const edge = document.querySelector('.mmc-reel-edge').getBoundingClientRect();
      const on = document.elementFromPoint(edge.left + 5, edge.top + 40);
      return Boolean(on.closest('.mmc-reel-edge'))
        && document.querySelectorAll('.mmc-reel-card-head')[1].getBoundingClientRect().left
           >= document.querySelector('.mmc-reel-blend').getBoundingClientRect().right;
    }), true);
  });

  await check('A blend is ticks until both shots have a picture, then slits; its bracket selects the join', async () => {
    const read = () => page.evaluate(() => [document.querySelectorAll('.mmc-reel-blend.filmed').length,
      [...document.querySelectorAll('.mmc-reel-film')].map((f) => f.style.maskImage.startsWith('linear-gradient'))]);
    await reset(['one', 'two']);
    const before = await read();
    await reset(['one', 'two'], keepAll);
    const after = await read();
    const said = await page.locator('.mmc-reel-bracket').textContent();
    const text = await page.evaluate(() => S.serializeTimeline(tl));
    await page.locator('.mmc-reel-bracket').click();
    assert.deepEqual([before, after, /^\d\.\d s$/.test(said), await page.evaluate(() => reel.sel), await page.evaluate(() => S.serializeTimeline(tl)) === text],
      [[0, []], [1, [false, true]], true, { kind: 'join', index: 1 }, true]);
  });

  await check('A written shot takes a clip and keeps its words; they survive saving and come back as a shot', async () => {
    await reset(['one', 'two', 'three']);
    await page.locator('.mmc-reel-card').nth(1).click();
    const offered = await page.locator('.mmc-reel-useclip:visible').allTextContents();
    await page.locator('.mmc-reel-useclip:visible').click();
    const note = page.locator('.mmc-reel-words textarea');
    const kept = await note.inputValue();
    await note.fill('two, and it ends on the door');
    const saved = await page.evaluate(() => S.parseTimeline(S.serializeTimeline(tl)).segments.map((s) => [s.kind, s.prompt]));
    await page.getByRole('button', { name: 'Generate it instead' }).click();
    assert.deepEqual([offered, kept, saved[1], await order(), await page.evaluate(() => tl.segments[1].kind)],
      [['use a clip for this shot'], 'two', ['clip', 'two, and it ends on the door'],
       ['one', 'two, and it ends on the door', 'three'], undefined]);
  });

  await check('A blend is dragged on a join into a clip, from nothing too', async () => {
    await reset(['one', 'two'], "tl.segments[1] = Object.assign(S.clipSegment({ filename: 'c.mp4', duration: 5, hasAudio: true }), { continue: true });");
    const widths = [];
    for (const by of [60, -300]) {
      const box = await page.locator('.mmc-reel-grip').boundingBox();
      await page.mouse.move(box.x + 7, box.y + 30);
      await page.mouse.down();
      await page.mouse.move(box.x + 7 + by, box.y + 30, { steps: 6 });
      await page.mouse.up();
      widths.push(await page.evaluate(() => S.feather(tl.segments[1], tl)));
    }
    assert.ok(widths[0] > 1 && widths[1] === 1, widths.join(','));
    assert.equal(await page.locator('.mmc-reel-grip').count(), 1);
  });

  await check('The scene, its lines, the back link and empty script all lead back to the piece', async () => {
    await reset(['one', 'two']);
    const head = () => page.locator('.mmc-reel-ihead b').first().textContent();
    const seen = [];
    for (const spot of ['.mmc-reel-scene .mmc-prompt', '.mmc-reel-quiet textarea', '.mmc-reel-back', '.mmc-reel-script']) {
      await page.locator('.mmc-reel-card').nth(1).click();
      seen.push(await head());
      const box = await page.locator(spot).first().boundingBox();
      if (spot === '.mmc-reel-script') await page.mouse.click(box.x + box.width / 2, box.y + box.height - 6);
      else await page.locator(spot).first().click();
      seen.push(await head());
    }
    assert.deepEqual(seen, Array(4).fill(['Shot 2', 'Piece']).flat());
  });

  const withCast = (code = '') => reset(['@wader walks. Lit like @ref-2.', 'two'], `
    tl.prompt = 'A lake.'; tl.soundscape = ''; tl.music = '';
    tl.assets = [{ handle: 'ref-1', kind: 'image', role: 'reference', filename: 'cast/wader.png' },
                 { handle: 'ref-2', kind: 'image', role: 'reference', filename: 'refs/poster.png' },
                 { handle: 'ref-3', kind: 'image', role: 'reference', filename: 'cast/wader2.png' }];
    tl.subjects = [{ handle: 'wader', takes: 'person', from: ['ref-1', 'ref-3'] }];
    tl.segments[0].assets = [{ handle: 'img-1', kind: 'image', role: 'first_frame', filename: 'refs/key.png' }];
    tl.segments[0].refined = { body: '@wader strides, like @ref-2 does.', source: tl.segments[0].prompt, enabled: true, scope: 'shot' };
    ${code}`);
  const piece = () => page.evaluate(() => ({ assets: tl.assets.map((a) => a.handle), cast: tl.subjects.map((s) => s.handle),
    own: tl.segments[0].assets.map((a) => a.handle), prompt: tl.segments[0].prompt, body: tl.segments[0].refined?.body }));

  await check('A member taken out of the piece takes their files, leaves plain words, and Undo brings it all back', async () => {
    await withCast();
    await fresh();
    const before = await piece();
    await page.locator('.mmc-reel-face-wrap').first().hover();
    await page.locator('.mmc-reel-face-wrap .mmc-reel-x').first().click();
    const gone = await piece();
    await page.locator('.mmc-reel-step').first().click();
    assert.deepEqual([gone, await piece()], [{ assets: ['ref-2'], cast: [], own: ['img-1'],
      prompt: 'wader walks. Lit like @ref-2.', body: 'wader strides, like @ref-2 does.' }, before]);
  });

  await check('A reference taken out of the piece takes its mentions with it', async () => {
    await withCast();
    await page.locator('.mmc-reel-face.frame').focus();
    await page.keyboard.press('Delete');
    assert.deepEqual(await piece(), { assets: ['ref-1', 'ref-3'], cast: ['wader'], own: ['img-1'],
      prompt: '@wader walks. Lit like.', body: '@wader strides, like does.' });
  });

  await check('A shot drops its own file, a reference and a member, and the piece keeps the last two', async () => {
    await withCast();
    await page.locator('.mmc-reel-card').first().click();
    const thumbs = page.locator('.mmc-reel-thumb-wrap');
    const removable = await page.locator('.mmc-reel-thumb-wrap .mmc-reel-x').count();
    for (const alt of ['@img-1', '@ref-2']) {
      const thumb = thumbs.filter({ has: page.locator(`img[alt="${alt}"]`) });
      await thumb.hover();
      await thumb.locator('.mmc-reel-x').click();
    }
    await page.locator('.mmc-reel-lora .mmc-reel-chip-x').first().click();
    assert.deepEqual([removable, await piece()], [2, { assets: ['ref-1', 'ref-2', 'ref-3'], cast: ['wader'], own: [],
      prompt: 'wader walks. Lit like.', body: 'wader strides, like does.' }]);
    await page.getByRole('button', { name: 'Add someone', exact: true }).click();
    await page.locator('.mmc-pop').getByText('@wader').click();
    assert.equal(await page.evaluate(() => tl.segments[0].prompt), 'wader walks. Lit like. @wader ');
  });

  await check('A file comes off a member, but not their last', async () => {
    await withCast();
    await page.locator('.mmc-reel-face').first().click();
    const thumb = page.locator('.mmc-reel-thumb-wrap').first();
    await thumb.hover();
    await thumb.locator('.mmc-reel-x').click();
    assert.deepEqual([(await piece()).assets, await page.locator('.mmc-reel-thumb-wrap .mmc-reel-x').count()], [['ref-2', 'ref-3'], 0]);
  });

  await check('One shot is refined from its row: its words stay, the other takes and the sound too', async () => {
    await reset(['one', 'two', 'three'], "tl.subjects = []; tl.segments[2].continue = tl.segments[2].continue_audio = false;" + keepAll);
    await fresh();
    await page.evaluate(async () => {
      const { api } = await import('/scripts/api.js');
      window.asked = null;
      window.realFetch = api.fetchApi;
      api.fetchApi = async (url, init) => {
        if (!String(url).startsWith('/continuity/refine')) return window.realFetch(url, init);
        window.asked = JSON.parse(init.body);
        return new Response(JSON.stringify({ result: { shots: [{ index: 2, body: 'A refined three.' }], scope: 'shot',
          soundscape: 'wind', music: 'drums' } }), { status: 200 });
      };
    });
    await page.locator('.mmc-reel-card').nth(2).click();
    await page.locator('.mmc-reel-shot').nth(2).getByRole('button', { name: 'refine', exact: true }).click();
    await page.waitForFunction(() => tl.segments[2].refined?.body, null, { timeout: 4000 });
    await page.waitForTimeout(50);
    const got = await page.evaluate(() => ({ asked: [asked.kind, asked.index], prompt: tl.segments[2].prompt, body: tl.segments[2].refined.body,
      held: tl.segments.map((s) => S.isHeld(s)), sound: tl.soundscape + tl.music }));
    assert.deepEqual(got, { asked: ['segment', 2], prompt: 'three', body: 'A refined three.', held: [true, true, false], sound: '' });
    assert.equal(await page.locator('.mmc-reel-rewritten:visible').textContent(), 'The model reads a rewrite of this');
    if (process.env.SHOT) await page.screenshot({ path: process.env.SHOT.replace('.png', '4.png') });
    await page.locator('.mmc-reel-inspect .mmc-refined-box').first().click();
    await page.keyboard.press('End');
    await page.keyboard.type('!!');
    assert.ok((await page.evaluate(() => tl.segments[2].refined.body)).includes('!!'));
    await page.locator('.mmc-reel-step').first().click();
    assert.equal(await page.evaluate(() => tl.segments[2].refined.body), 'A refined three.');
    await page.locator('.mmc-reel-inspect').getByText('Revert').click();
    assert.equal(await page.evaluate(() => S.refinedBody(tl.segments[2])), '');
    assert.equal(await page.locator('.mmc-reel-rewritten:visible').count(), 0);
    await page.evaluate(async () => { (await import('/scripts/api.js')).api.fetchApi = window.realFetch; });
  });

  if (process.env.SHOT) {
    await reset(['', 'He wades in.', 'Close on the skull.']);
    const target = await page.locator('.mmc-reel-card').nth(2).boundingBox();
    await drag(page.locator('.mmc-reel-card').nth(0), target.x + target.width - 20, target.y + 30, { release: false });
    await page.screenshot({ path: process.env.SHOT });
    await page.keyboard.press('Escape'); await page.mouse.up();
    await page.locator('.mmc-reel-gap').nth(1).hover();
    await page.screenshot({ path: process.env.SHOT.replace('.png', '2.png') });
    await reset(['one', 'two', 'three'], keepAll);
    await page.locator('.mmc-reel-join').nth(1).click();
    await page.screenshot({ path: process.env.SHOT.replace('.png', '3.png'), clip: { x: 40, y: 690, width: 1420, height: 230 } });
  }

  assert.deepEqual(errors, []);
  assert.equal(requests, 0, 'Fixture attempted a network request');
  console.log(JSON.stringify({ passed: results.length, requests, media, results }, null, 2));
})().catch((error) => { console.error(error); process.exitCode = 1; }).finally(async () => { await browser?.close(); });

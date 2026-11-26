// Isolated browser checks for `talk.js`: what the chat room and Stagehand's
// window share. The real module, with ComfyUI's `api` and `app` stubbed and no
// server: asking again, reading a failure, the transcript, a failure's line.
// How each conversation uses it is checked in its own suite.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '../..');
const ORIGIN = 'http://localhost:5999';
const apiStub = `export const api = { clientId: 'tab-1', async fetchApi() { return new Response('{}'); }, apiURL: (u) => u,
  getUserData: async () => new Response('{}', { status: 404 }), storeUserData: async () => {}, addEventListener() {}, removeEventListener() {} };`;
const appStub = `export const app = { graph: { _nodes: [] }, extensionManager: { setting: { get() {} } }, ui: { settings: { getSettingValue() {} } } }; globalThis.app = app;`;

let browser, requests = 0;
const results = [];
async function check(name, fn) { await fn(); results.push({ name, passed: true }); }

(async () => {
  browser = await chromium.launch({ executablePath: process.env.BROWSER_EXECUTABLE_PATH || undefined, headless: true });
  const page = await browser.newPage();
  page.setDefaultTimeout(8000);
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin === ORIGIN) {
      if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: '<!doctype html><html><body><div id="log" style="height:100px;overflow-y:auto"></div></body></html>' });
      if (url.pathname === '/scripts/api.js') return route.fulfill({ contentType: 'text/javascript', body: apiStub });
      if (url.pathname === '/scripts/app.js') return route.fulfill({ contentType: 'text/javascript', body: appStub });
      if (url.pathname.startsWith('/ext/web/creator/') && url.pathname.endsWith('.js')) {
        const file = path.join(root, url.pathname.slice('/ext/'.length));
        if (fs.existsSync(file)) return route.fulfill({ contentType: 'text/javascript', body: fs.readFileSync(file) });
      }
    }
    requests++;
    return route.abort();
  });
  await page.goto(`${ORIGIN}/`);
  await page.evaluate(async () => { window.T = await import('/ext/web/creator/talk.js'); });

  await check('a failure is read for its kind, and only one that passes is asked again unasked', async () => {
    const kinds = await page.evaluate(() => [
      new Error('the server answered 500: out of memory'), new Error('the server answered 429: slow down'),
      new Error('could not reach http://127.0.0.1:1234/v1: refused — is the server running?'),
      new Error("the server's reply could not be read: Expecting value"), new Error('Failed to fetch'),
      new Error('your reply was empty.'), new Error('Stagehand is still working on this conversation.'),
      new Error('the server answered 401: bad key'), new Error('the server answered 400: model not found'),
      new Error('no text encoder chosen'), new Error('the server answered 400: the request exceeds the available context size'),
      Object.assign(new Error('Stopped.'), { stopped: true }), Object.assign(new Error('cancelled'), { cancelled: true }),
      Object.assign(new Error('stopped after 60 turns'), { limit: 60 }),
    ].map((error) => { const { kind, again } = T.failureOf(error); return `${kind}${again ? '+' : ''}`; }));
    assert.deepEqual(kinds, ['passing+', 'passing+', 'passing+', 'passing+', 'passing+', 'passing+', 'passing+',
      'other', 'other', 'other', 'long', 'stopped', 'stopped', 'limit']);
  });

  await check('asking asks again up to three times, says so before each, and throws the last failure as it was', async () => {
    const run = (failures, message = 'the server answered 503: loading') => page.evaluate(async ([failures, message]) => {
      const told = [];
      let asked = 0;
      try {
        const answer = await T.asking(async () => { asked++; if (asked <= failures) throw new Error(message); return 'answered'; },
          { pauses: [1, 1], onAgain: ({ attempt, of, text }) => told.push(`${attempt}/${of} ${text}`) });
        return { answer, asked, told };
      } catch (error) { return { failed: error.message, asked, told }; }
    }, [failures, message]);
    assert.deepEqual(await run(0), { answer: 'answered', asked: 1, told: [] });
    assert.deepEqual(await run(2), { answer: 'answered', asked: 3, told: ['2/3 the server answered 503: loading', '3/3 the server answered 503: loading'] });
    assert.deepEqual(await run(3), { failed: 'the server answered 503: loading', asked: 3, told: ['2/3 the server answered 503: loading', '3/3 the server answered 503: loading'] });
    assert.deepEqual(await run(1, 'the server answered 401: bad key'), { failed: 'the server answered 401: bad key', asked: 1, told: [] });
  });

  await check('a Stop ends the wait between attempts at once, and is not asked again', async () => {
    const out = await page.evaluate(async () => {
      const stop = new AbortController();
      let asked = 0;
      const began = performance.now();
      const work = T.asking(async () => { asked++; throw new Error('could not reach the server'); }, { signal: stop.signal, pauses: [60000, 60000] });
      setTimeout(() => stop.abort(Object.assign(new Error('Stopped.'), { stopped: true })), 20);
      try { await work; } catch (error) { return { failed: error.message, stopped: T.failureOf(error).kind, asked, quick: performance.now() - began < 2000 }; }
    });
    assert.deepEqual(out, { failed: 'Stopped.', stopped: 'stopped', asked: 1, quick: true });
  });

  await check('the transcript keeps a row whose key did not change, draws one whose key did, and drops one that left', async () => {
    const out = await page.evaluate(() => {
      const log = document.getElementById('log');
      const transcript = new T.Transcript(log);
      const line = (text) => Object.assign(document.createElement('div'), { textContent: text, style: 'height:60px' });
      const a = {}, b = {}, c = {};
      let drawn = 0;
      const row = (of, key, text) => ({ of, key, draw: () => { drawn++; return line(text); } });
      transcript.show([row(a, 1, 'a'), row(b, 1, 'b')]);
      const first = [...log.children];
      const tail = line('working');
      transcript.show([row(a, 1, 'a'), row(b, 2, 'b again'), row(c, 1, 'c'), null, tail]);
      const second = [...log.children];
      transcript.show([row(c, 1, 'c')]);
      return { drawn, keptA: second[0] === first[0], redrewB: second[1] !== first[1], texts: second.map((node) => node.textContent),
        left: [...log.children].map((node) => node.textContent), remembered: [transcript.nodesOf(a).length, transcript.nodesOf(c).length] };
    });
    assert.deepEqual(out, { drawn: 4, keptA: true, redrewB: true, texts: ['a', 'b again', 'c', 'working'], left: ['c'], remembered: [0, 1] });
  });

  await check('the transcript follows the newest line for somebody reading it, leaves somebody who scrolled up, and keeps the caret', async () => {
    const out = await page.evaluate(() => {
      const log = document.getElementById('log');
      log.replaceChildren();
      const transcript = new T.Transcript(log);
      const items = [];
      const add = () => { const of = {}; items.push({ of, key: 1, draw: () => Object.assign(document.createElement('div'), { style: 'height:80px' }) }); };
      for (let n = 0; n < 4; n++) add();
      transcript.show(items);
      const atEnd = log.scrollTop + log.clientHeight >= log.scrollHeight - 1;
      log.scrollTop = 0;
      add();
      transcript.show(items);
      const stayed = log.scrollTop === 0;
      transcript.show(items, { follow: 'always' });
      const followed = log.scrollTop + log.clientHeight >= log.scrollHeight - 1;
      // A field in a kept row, typed into while a row is added above it.
      const field = Object.assign(document.createElement('input'), { value: 'six seconds' });
      const holder = {};
      items.push({ of: holder, key: 1, draw: () => field });
      transcript.show(items);
      field.focus();
      field.setSelectionRange(3, 3);
      items.unshift({ of: {}, key: 1, draw: () => document.createElement('div') });
      transcript.show(items);
      return { atEnd, stayed, followed, focused: document.activeElement === field, caret: field.selectionStart };
    });
    assert.deepEqual(out, { atEnd: true, stayed: true, followed: true, focused: true, caret: 3 });
  });

  await check('a failure has the doors it was given and no others, and its words are never markup', async () => {
    const out = await page.evaluate(() => {
      let again = 0, restart = 0;
      const both = T.failRow({ text: '<b>the server answered 500</b>', cls: 'mine', door: 'mydoor', words: 'mywords', again: () => { again++; }, restart: () => { restart++; } });
      const none = T.failRow({ text: 'no model' });
      for (const button of both.querySelectorAll('button')) button.click();
      return { classes: both.className, role: both.getAttribute('role'), text: both.querySelector('.mywords').textContent, bold: both.querySelectorAll('b').length,
        doors: [...both.querySelectorAll('button.mydoor')].map((button) => button.textContent), again, restart, bare: none.querySelectorAll('button').length };
    });
    assert.deepEqual(out, { classes: 'mine mmc-talk-fail', role: 'alert', text: '<b>the server answered 500</b>', bold: 0,
      doors: ['Try again', 'New conversation'], again: 1, restart: 1, bare: 0 });
  });

  assert.deepEqual(errors, []);
  assert.equal(requests, 0, 'Fixture attempted a network request');
  console.log(JSON.stringify({ passed: results.length, requests, results }, null, 2));
})().catch((error) => { console.error(error); process.exitCode = 1; }).finally(async () => { await browser?.close(); });

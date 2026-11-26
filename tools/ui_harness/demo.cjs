// What docs.cjs and film.cjs stand on: the harness page in a Playwright
// browser, with the routes a piece needs answered here instead of by ComfyUI.
//
//   const demo = await require('./demo.cjs').start({ width, height, scale });
//
// - Takes and thumbnails are stand-ins, cut with ffmpeg from the style atlas
//   that ships in web/creator/presets/atlas (one frame each of clips from
//   ostris/minimax_h3_1k). Nothing here was rendered by this pack.
// - Stagehand's model is a script: `hand.script` holds the replies, each a
//   sentence or a list of `[tool, arguments]`, and `step()` lets the next one
//   answer. The tools themselves are the real ones and do the real work.
// - The blockout's guide routes accept what they are sent and write nothing.
const { spawn, execFileSync } = require('node:child_process');
const fs = require('node:fs');
const net = require('node:net');
const os = require('node:os');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const ROOT = path.resolve(__dirname, '../..');
const ATLAS = path.join(ROOT, 'web/creator/presets/atlas/full');
const MEDIA = path.join(os.tmpdir(), 'continuity-ui-harness-media');
const TYPES = { webm: 'video/webm', jpg: 'image/jpeg', png: 'image/png' };

// name: [atlas clip, ffmpeg filter]. A take is the still with a slow push in.
const FRAME = 'scale=1344:768:force_original_aspect_ratio=increase,crop=1344:768';
const STILLS = {
  s1: ['000053', FRAME],
  s2: ['000982', FRAME],
  s3: ['000058', `crop=672:384:0:330,${FRAME}`],
  anna: ['000982', 'crop=200:200:560:10,scale=512:512'],
  ben: ['000982', 'crop=200:200:200:60,scale=512:512'],
  fox: ['000328', FRAME],
  wood: ['000044', 'scale=768:768:force_original_aspect_ratio=increase,crop=768:768'],
  runner: ['000328', 'crop=420:420:560:120,scale=768:768'],
};
const TAKES = ['s1', 's2', 's3', 'fox'];

function media() {
  fs.mkdirSync(MEDIA, { recursive: true });
  const ffmpeg = (...args) => execFileSync('ffmpeg', ['-loglevel', 'error', '-y', ...args]);
  for (const [name, [clip, filter]] of Object.entries(STILLS)) {
    const out = path.join(MEDIA, `${name}.jpg`);
    if (!fs.existsSync(out)) ffmpeg('-i', path.join(ATLAS, `${clip}.webp`), '-vf', filter, '-q:v', '2', out);
  }
  for (const name of TAKES) {
    const out = path.join(MEDIA, `${name}.webm`);
    if (fs.existsSync(out)) continue;
    ffmpeg('-loop', '1', '-i', path.join(MEDIA, `${name}.jpg`), '-vf',
      "zoompan=z='1+0.0006*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=144:s=1344x768:fps=24",
      '-t', '6', '-c:v', 'libvpx-vp9', '-b:v', '0', '-crf', '34', '-an', out);
  }
}

const freePort = () => new Promise((resolve) => {
  const probe = net.createServer().listen(0, '127.0.0.1', () => {
    const { port } = probe.address();
    probe.close(() => resolve(port));
  });
});

exports.MEDIA = MEDIA;
exports.ROOT = ROOT;

exports.start = async ({ width = 1600, height = 900, scale = 2, refiner = 'qwen3-vl-30b' } = {}) => {
  media();
  const port = await freePort();
  const server = spawn('python3', [path.join(__dirname, 'server.py'), String(port)], { stdio: ['ignore', 'pipe', 'inherit'] });
  await new Promise((resolve) => server.stdout.once('data', resolve));
  const browser = await chromium.launch({ executablePath: process.env.BROWSER_EXECUTABLE_PATH || undefined });
  const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: scale });
  page.setDefaultTimeout(5000);
  page.on('pageerror', (error) => console.log('[pageerror]', String(error.stack || error).slice(0, 600)));

  const hand = { script: [], sent: [], waiting: [], go() { this.waiting.shift()?.(); } };
  const json = (route, body) => route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const at = url.pathname;
    if (at === '/view' || at === '/continuity/thumb') {
      const name = (url.searchParams.get('filename') || url.searchParams.get('path') || '').replace(/ \[\w+\]$/, '');
      const base = path.basename(name).replace(/\.\w+$/, '');
      const video = at === '/view' && /\.(mp4|webm)$/.test(name);
      // A guide the bench derived has no file here; `guide.jpg` is the glass, photographed by whoever wants one shown.
      const file = path.join(MEDIA, /blockout/.test(name) && !video ? 'guide.jpg' : `${base}.${video ? 'webm' : 'jpg'}`);
      if (fs.existsSync(file)) return route.fulfill({ contentType: TYPES[video ? 'webm' : 'jpg'], body: fs.readFileSync(file) });
      return route.fulfill({ status: 404, body: '' });
    }
    // The chat room asks its three first-run questions until the settings say they were answered.
    if (at === '/continuity/settings') return json(route, { settings: { chat: { setup: true } } });
    if (at === '/continuity/chat/setup') return json(route, {});
    if (at === '/continuity/blockout/frames') return json(route, { held: 1 });
    if (at === '/continuity/blockout/write') {
      const body = JSON.parse(route.request().postData() || '{}');
      return json(route, { path: `continuity/blockout/${body.name}.mp4`, kind: 'video' });
    }
    if (at === '/upload/image') return json(route, { name: 'blockout-depth.png', subfolder: 'continuity/blockout' });
    if (at === '/continuity/blockout/sweep') return json(route, { gone: 0 });
    if (at === '/continuity/refine/remote') return json(route, { url: 'http://127.0.0.1:1234/v1', key_set: false });
    if (at === '/continuity/probe') return json(route, { missing: false });
    if (at === '/continuity/stagehand/stop') return json(route, { stopped: true });
    if (at === '/continuity/stagehand') {
      hand.sent.push(JSON.parse(route.request().postData()));
      await new Promise((resolve) => hand.waiting.push(resolve));
      const next = hand.script.shift();
      const message = typeof next === 'string' ? { role: 'assistant', content: next }
        : { role: 'assistant', content: '', tool_calls: (next ?? []).map(([name, given], n) => (
          { id: `c${hand.sent.length}-${n}`, type: 'function', function: { name, arguments: JSON.stringify(given) } })) };
      return json(route, { result: { choices: [{ message, finish_reason: 'stop' }] } }).catch(() => {});
    }
    return route.continue();
  });
  // Stagehand runs on the refiner's model, so one has to be selected.
  await page.addInitScript((model) => localStorage.setItem('continuity.refiner',
    JSON.stringify({ backend: 'remote', remoteModel: model })), refiner);

  return {
    page, hand,
    /** A fresh page with the node mounted. */
    async boot(query = '') {
      await page.goto(`http://127.0.0.1:${port}/${query}`);
      await page.waitForFunction('globalThis.harnessReady');
      await page.evaluate(async () => { window.S = await import('/extensions/continuity/creator/state.js'); });
    },
    /** Let Stagehand's next exchange answer; back when the one after it is asked or the message is over. */
    async step() {
      const asked = hand.sent.length;
      for (let tries = 0; !hand.waiting.length; tries++) {
        if (tries > 500) throw new Error('Stagehand was not asked anything');
        await page.waitForTimeout(10);
      }
      hand.go();
      for (let tries = 0; tries < 500; tries++) {
        if (hand.sent.length > asked && hand.waiting.length) return;
        if (!(await page.evaluate(() => node.mmcBody.reel?.locked))) return;
        await page.waitForTimeout(10);
      }
    },
    /** Takes land on shots, as a finished render reports them: `{ shot number: name }`. */
    async land(takes) {
      await page.evaluate((takes) => {
        const body = node.mmcBody;
        S.attachTakes(body.timeline, Object.entries(takes).map(([segment, name]) => (
          { segment: Number(segment), filename: `${name}.mp4`, subfolder: 'continuity', duration_s: 6, has_audio: true })));
        body.commit();
        body.reel?.landed();
      }, takes);
    },
    async close() { await browser.close(); server.kill(); },
  };
};

// ---- the piece the pictures and the film are about --------------------------------

exports.FILM = {
  look: 'A cluttered family kitchen on a stormy evening. Warm practical light inside, green storm light at the window.',
  sound: 'Rain on the glass, a pot coming to the boil, the fridge humming.',
  cast: [
    ['anna', 'A woman in her forties, dark hair tied back, a flowered apron over a red top.'],
    ['ben', 'A man in his forties, short dark curls, a grey-blue polo shirt.'],
  ],
  shots: [
    ['The kitchen stands empty. Storm light at the window over the sink, the curtains stirring.', 5, 'cuts'],
    ['@anna stirs a pot at the counter, steam rising. @ben comes in from the hall and opens the fridge behind her.', 6, 'continues'],
    ['Night, outside. Rain on the street under a sodium lamp. @ben steps out of the house and walks to the car.', 5, 'cuts'],
  ],
};

/** The cast, with a face each, as somebody would have made them before writing the film. */
exports.castReady = (demo, { cast } = exports.FILM) => demo.page.evaluate((cast) => {
  const body = node.mmcBody, piece = body.timeline;
  piece.assets = cast.map(([handle], n) => ({ handle: `ref-${n + 1}`, kind: 'image', role: 'reference', filename: `cast/${handle}.png` }));
  piece.subjects = cast.map(([handle, description], n) => ({ handle, takes: 'person', from: [`ref-${n + 1}`], description }));
  S.syncTimeline(piece);
  body.commit();
}, cast);

/** What Stagehand answers when asked for the film, one exchange per entry. */
exports.buildFilm = ({ look, sound, shots } = exports.FILM) => [
  [['write_film_text', { look, sound }]],
  // The piece opens on one empty shot, so the first is written into it.
  shots.map(([text, seconds, join], n) => (n ? ['add_shot', { text, seconds, join }] : ['change_shot', { shot: 1, text, seconds }])),
  'Three shots: the empty kitchen, @anna and @ben at the counter, and @ben leaving in the rain. Shoot is yours.',
];

/** What it answers when asked to stage shot 2: the library's kitchen, the two of them, a walk and a camera. */
exports.stageShot = () => [
  [['open_blockout', { shot: 2 }]],
  [['use_set', { name: 'Kitchen', library: 'kitchen' }]],
  [['remove_objects', { ids: [12] }], ['describe_object', { id: 11, plays: 'anna' }],
   ['add_objects', { objects: [
     { what: 'block', x: 1.6, z: 5.15, width: 0.8, height: 1.9, depth: 0.7, name: 'fridge' },
     { what: 'doorwall', x: 4.1, z: 3.6, facing: -90, name: 'hall door' },
     { what: 'person', x: 3.6, z: 3.3, facing: -90, plays: 'ben' }] }]],
  [['walk', { shot: 2, id: 14, points: [{ time: 0, x: 3.6, z: 3.3 }, { time: 2.5, x: 2.3, z: 4.3 }, { time: 4.5, x: 1.6, z: 4.5, facing: 0 }] }],
   ['move_camera', { shot: 2, points: [
     { time: 0, x: -1.6, y: 1.5, z: -0.8, at_x: 0.6, at_y: 1.1, at_z: 4.8, lens: 28 },
     { time: 6, x: -1.0, y: 1.45, z: 0.3, at_x: 0.8, at_y: 1.1, at_z: 4.8, lens: 28 }] }]],
  [['look_through_camera', { shot: 2, time: 4.5 }]],
  'Shot 2 is staged on the kitchen set: @anna at the counter, @ben in from the hall to the fridge, and a slow push in on a 28 mm.',
];

/** The same piece, put there without the conversation: for a picture that starts in the middle. */
exports.pieceReady = async (demo, { staged = true } = {}) => {
  const { page, hand } = demo;
  await exports.castReady(demo);
  await page.evaluate(() => node.mmcBody.open());
  await page.waitForTimeout(400);
  await page.locator('.mmc-st-handbtn').click();
  const talk = async (words, script) => {
    const exchanges = script.length;
    hand.script = [...script];
    await page.locator('.mmc-sh-box').click();
    await page.keyboard.type(words);
    await page.keyboard.press('Enter');
    for (let n = 0; n < exchanges; n++) await demo.step();
    await page.waitForTimeout(200);
  };
  await talk(exports.WORDS.film, exports.buildFilm());
  if (staged) await talk(exports.WORDS.stage, exports.stageShot());
};

exports.WORDS = {
  film: 'A short kitchen scene in a storm. @anna cooks, @ben comes home, then he leaves in the rain. Three shots.',
  stage: 'Stage shot 2 in 3D: @anna at the counter, @ben comes in from the hall and goes to the fridge.',
};

// Screenshots of the main surfaces, from this checkout's code.
//
//   node tools/ui_harness/shots.cjs [outdir] [--light]
//
// Starts the harness server on a free port, drives it with Playwright and
// writes node.png, full.png, simple.png, timeline.png and dashboard.png.
// Needs a resolvable `playwright` (or PLAYWRIGHT_MODULE, as tests/browser does).
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const net = require('node:net');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const args = process.argv.slice(2);
const light = args.includes('--light');
const out = path.resolve(args.find((a) => !a.startsWith('--')) || 'ui-shots');
const PROMPT = 'A fox walks through a snowy wood at dusk, breath fogging, the camera tracking low beside her.';

const freePort = () => new Promise((resolve) => {
  const probe = net.createServer().listen(0, '127.0.0.1', () => {
    const { port } = probe.address();
    probe.close(() => resolve(port));
  });
});

(async () => {
  fs.mkdirSync(out, { recursive: true });
  const port = await freePort();
  const server = spawn('python3', [path.join(__dirname, 'server.py'), String(port)], { stdio: ['ignore', 'pipe', 'inherit'] });
  await new Promise((resolve) => server.stdout.once('data', resolve));
  let browser;
  try {
    browser = await chromium.launch({ executablePath: process.env.BROWSER_EXECUTABLE_PATH || undefined });
    const page = await browser.newPage({ viewport: { width: 1600, height: 950 }, deviceScaleFactor: 2 });
    page.on('pageerror', (error) => console.log('[pageerror]', String(error.stack || error).slice(0, 400)));
    const shot = async (name) => {
      await page.waitForTimeout(900);
      await page.screenshot({ path: path.join(out, name + '.png') });
      console.log(path.join(out, name + '.png'));
    };
    const boot = async () => {
      await page.goto(`http://127.0.0.1:${port}/${light ? '?theme=light' : ''}`);
      await page.waitForFunction('globalThis.harnessReady');
    };
    const fullscreen = async () => {
      await page.evaluate('openFullscreen()');
      await page.waitForTimeout(1200);
      await page.locator('.mmc-fs [contenteditable]').first().click();
      await page.keyboard.type(PROMPT);
    };

    await boot();
    await shot('node');
    await fullscreen();
    await page.locator('.mmc-fs-view', { hasText: 'Full' }).click();
    await shot('full');
    await page.locator('.mmc-fs-view', { hasText: 'Simple' }).click();
    await shot('simple');
    await page.locator('.mmc-fs-view', { hasText: 'Full' }).click();
    await page.locator('.mmc-grow-shot').click();
    await shot('timeline');

    await boot();
    await fullscreen();
    await page.locator('.mmc-fs-mark').click();
    await shot('dashboard');
  } finally {
    await browser?.close();
    server.kill();
  }
})().catch((error) => { console.error(error); process.exit(1); });

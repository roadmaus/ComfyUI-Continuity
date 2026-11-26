// The pictures README.md and docs/ show, taken from this checkout's frontend.
//
//   node tools/ui_harness/docs.cjs [outdir] [name ...]
//
// Writes into docs/img unless told otherwise; with names, only those pictures.
// Needs what demo.cjs needs (python3, ffmpeg, a resolvable playwright), and
// what is stood in is said there: no picture here shows a render.
const fs = require('node:fs');
const path = require('node:path');
const D = require('./demo.cjs');

const args = process.argv.slice(2);
const out = path.resolve(args.find((a) => /[\\/]/.test(a)) || path.join(D.ROOT, 'docs/img'));
const only = args.filter((a) => !/[\\/]/.test(a));
const FOX = 'A fox walks through a snowy wood at dusk, breath fogging, the camera tracking low beside her.';

/** The fullscreen editor on a fresh page, in one of its two views. */
async function editor(demo, view = 'Full') {
  await demo.boot();
  await demo.page.evaluate('openFullscreen()');
  await demo.page.waitForTimeout(900);
  await demo.page.locator('.mmc-fs-view', { hasText: view }).click();
  await demo.page.waitForTimeout(300);
}
const write = async (page, words) => {
  await page.locator('.mmc-fs [contenteditable]').first().click();
  await page.keyboard.type(words);
};
const bench = (page, code) => page.evaluate(`(() => { const bench = node.mmcBody.reel; ${code} })()`);

const PICTURES = {
  // The piece on the timeline, two takes kept, a shot selected.
  async hero({ demo, page }) {
    await editor(demo);
    await D.pieceReady(demo, { staged: false });
    await page.locator('.mmc-sh-x').click();
    await demo.land({ 1: 's1', 2: 's2' });
    await page.evaluate(() => node.mmcBody.reel.select({ kind: 'shot', index: 1 }));
  },

  // The same window on a join.
  async timeline({ demo, page }) {
    await editor(demo);
    await D.pieceReady(demo, { staged: false });
    await page.locator('.mmc-sh-x').click();
    await demo.land({ 1: 's1', 2: 's2' });
    await page.locator('.mmc-reel-join').first().click();
  },

  // Stagehand in the timeline, the film just built.
  async 'timeline-stagehand'({ demo, page }) {
    await editor(demo);
    await D.pieceReady(demo, { staged: false });
  },

  async simple({ demo, page }) {
    await editor(demo, 'Simple');
    await write(page, FOX);
  },

  // Two references, each cited in the sentence.
  async mentions({ demo, page }) {
    await demo.boot();
    await page.evaluate(() => {
      const body = node.mmcBody, shot = body.timeline.segments[0];
      shot.assets = [
        { handle: 'img-1', kind: 'image', role: 'reference', filename: 'wood.jpg', takes: 'scene' },
        { handle: 'img-2', kind: 'image', role: 'reference', filename: 'runner.jpg', takes: 'person' }];
      shot.prompt = 'The runner from @img-2 moves slowly through the forest of @img-1 at first light, mist between the trunks. Use only the trees and the light of the forest.';
      S.syncTimeline(body.timeline);
      body.commit();
      body.reload?.();
    });
    await page.evaluate('openFullscreen()');
    await page.waitForTimeout(900);
    await page.locator('.mmc-fs-view', { hasText: 'Simple' }).click();
  },

  async dashboard({ demo, page }) {
    await page.setViewportSize({ width: 1600, height: 1230 });
    await editor(demo);
    await page.locator('.mmc-fs-mark').click();
  },

  async chat({ demo, page }) {
    await page.setViewportSize({ width: 1600, height: 760 });
    await editor(demo);
    await page.locator('.mmc-fs-mark').click();
    await page.waitForTimeout(400);
    await page.getByText('Chat', { exact: true }).first().click();
  },

  // The bench by hand: the plan, @ben selected at the end of his walk.
  async blockout({ demo, page }) {
    await editor(demo);
    await D.pieceReady(demo);
    await page.locator('.mmc-sh-x').click();
    await demo.land({ 1: 's1' });
    await bench(page, "bench.setLook('plan'); bench.select({ kind: 'shot', index: 1 }); bench.goTo(1, 4.5); bench.select({ kind: 'thing', id: 14 }); bench.draw();");
  },

  // Stagehand in the bench, part-way through staging a shot.
  async stagehand({ demo, page }) {
    await editor(demo);
    await D.pieceReady(demo, { staged: false });
    const script = D.stageShot();
    demo.hand.script = [...script];
    await page.locator('.mmc-sh-box').click();
    await page.keyboard.type(D.WORDS.stage);
    await page.keyboard.press('Enter');
    // Everything but its last word, so it is still working when the picture is taken.
    for (let n = 0; n < script.length - 1; n++) await demo.step();
    await page.waitForTimeout(300);
    await bench(page, "bench.setLook('around'); bench.draw();");
    await page.evaluate(() => { const log = document.querySelector('.mmc-sh-log'); log.scrollTop = log.scrollHeight; });
  },
};

(async () => {
  fs.mkdirSync(out, { recursive: true });
  const names = only.length ? only : Object.keys(PICTURES);
  for (const name of names) {
    if (!PICTURES[name]) throw new Error(`no picture called ${name}: ${Object.keys(PICTURES).join(', ')}`);
    // A browser each: nothing one picture did is there for the next.
    const demo = await D.start({ width: 1600, height: 900, scale: 2 });
    try {
      await PICTURES[name]({ demo, page: demo.page });
      await demo.page.waitForTimeout(900);
      await demo.page.screenshot({ path: path.join(out, `${name}.png`) });
      console.log(path.join(out, `${name}.png`));
    } finally {
      await demo.close();
    }
  }
})().catch((error) => { console.error(error); process.exit(1); });

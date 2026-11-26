// The film in docs/vid: the timeline, Stagehand and the blockout bench, driven
// in the real frontend and photographed a frame at a time.
//
//   node tools/ui_harness/film.cjs [out.mp4] [--dry]
//
// Nothing is recorded live. Every frame is a screenshot taken after the page
// was put where that frame needs it, so the film is the same on any machine
// and as sharp as a still. `--dry` takes one picture per held moment into
// `<out>-frames/` and encodes nothing, for looking a change over quickly.
// Needs ffmpeg, and what demo.cjs needs. What is stood in is said there.
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const D = require('./demo.cjs');

const args = process.argv.slice(2);
const dry = args.includes('--dry');
const out = path.resolve(args.find((a) => !a.startsWith('--')) || path.join(D.ROOT, 'docs/vid/timeline-blockout-stagehand.mp4'));
const frames = out.replace(/\.mp4$/, '') + '-frames';
const FPS = 30;
const W = 1600, H = 900, SCALE = 1.2;   // 1920 × 1080

(async () => {
  fs.rmSync(frames, { recursive: true, force: true });
  fs.mkdirSync(frames, { recursive: true });
  const demo = await D.start({ width: W, height: H, scale: SCALE });
  const { page, hand } = demo;
  const wait = (ms) => page.waitForTimeout(ms);

  // ---- the camera -------------------------------------------------------------
  const list = [];
  /** One picture, shown for `seconds`. */
  const snap = async (seconds) => {
    const file = path.join(frames, `f${String(list.length).padStart(5, '0')}.jpg`);
    await page.screenshot({ path: file, type: 'jpeg', quality: 93 });
    list.push([file, seconds]);
  };
  const hold = async (seconds) => { await wait(120); await snap(seconds); };
  /** One frame of something moving. Dry, it only adds its time to the last picture. */
  const frame = async (count = 1) => {
    if (dry && list.length) { list.at(-1)[1] += count / FPS; return; }
    await snap(count / FPS);
  };

  // ---- what is drawn over the page: a pointer, a caption, a card ----------------
  const icon = fs.readFileSync(path.join(D.ROOT, 'docs/img/icon.svg'), 'utf8');
  const overlay = () => page.evaluate((icon) => {
    if (document.getElementById('film')) return;
    const film = document.createElement('div');
    film.id = 'film';
    film.innerHTML = `<style>
      /* Room under the window for the caption, so it covers nothing. */
      .mmc-overlay { padding: 12px 26px 74px !important; background: #1c1c1c !important; }
      #film { position: fixed; inset: 0; z-index: 2147483647; pointer-events: none; font-family: Inter, system-ui, sans-serif; }
      #film-caption { position: absolute; left: 50%; bottom: 13px; transform: translateX(-50%); width: max-content; max-width: 1400px; padding: 10px 22px;
        border-radius: 12px; background: rgba(12,12,12,.94); border: 1px solid rgba(255,255,255,.16); color: #fff;
        font-size: 19px; line-height: 1.35; text-align: center; box-shadow: 0 10px 40px rgba(0,0,0,.6); }
      #film-caption:empty { display: none; }
      #film-pointer { position: absolute; left: 0; top: 0; width: 24px; height: 24px; filter: drop-shadow(0 2px 3px rgba(0,0,0,.7)); }
      #film-ring { position: absolute; left: 0; top: 0; width: 34px; height: 34px; margin: -17px 0 0 -17px; border-radius: 50%;
        border: 2px solid #f0a53a; opacity: 0; }
      #film-card { position: absolute; inset: 0; background: #161616; display: none; flex-direction: column; align-items: center;
        justify-content: center; gap: 18px; color: #fff; text-align: center; }
      #film-card svg { width: 96px; height: 96px; }
      #film-card h1 { margin: 6px 0 0; font-size: 54px; font-weight: 650; letter-spacing: -.01em; }
      #film-card p { margin: 0; font-size: 24px; color: #b9b9b9; max-width: 1000px; line-height: 1.4; }
      #film-card small { font-size: 16px; color: #7d7d7d; margin-top: 18px; }
      #film-card b { color: #f0a53a; font-weight: 600; }
    </style>
    <div id="film-ring"></div>
    <svg id="film-pointer" viewBox="0 0 24 24"><path d="M4 2 L4 19 L8.6 14.9 L11.6 21.6 L14.3 20.4 L11.4 13.8 L17.6 13.6 Z" fill="#fff" stroke="#111" stroke-width="1.3" stroke-linejoin="round"/></svg>
    <div id="film-caption"></div>
    <div id="film-card"></div>`;
    document.body.append(film);
    window.filmIcon = icon;
  }, icon);
  const caption = (text) => page.evaluate((text) => { document.getElementById('film-caption').textContent = text; }, text);
  const card = (html) => page.evaluate((html) => {
    const node = document.getElementById('film-card');
    node.style.display = html ? 'flex' : 'none';
    node.innerHTML = html ? window.filmIcon + html : '';
    document.getElementById('film-pointer').style.display = html ? 'none' : '';
  }, html);

  let at = [W * 0.62, H * 0.5];
  const pointer = ([x, y], ring = 0) => page.evaluate(([x, y, ring]) => {
    document.getElementById('film-pointer').style.transform = `translate(${x - 4}px, ${y - 2}px)`;
    const mark = document.getElementById('film-ring');
    mark.style.transform = `translate(${x}px, ${y}px) scale(${0.4 + ring})`;
    mark.style.opacity = ring ? String(1 - ring * 0.8) : '0';
  }, [x, y, ring]);
  const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - ((-2 * t + 2) ** 2) / 2);
  /** Where something is: a locator's middle, or the point given. */
  const where = async (target, [fx, fy] = [0.5, 0.5]) => {
    if (Array.isArray(target)) return target;
    const box = await target.boundingBox();
    return [box.x + box.width * fx, box.y + box.height * fy];
  };
  const move = async (target, part) => {
    const to = await where(target, part);
    const from = at, far = Math.hypot(to[0] - from[0], to[1] - from[1]);
    const steps = Math.max(8, Math.min(26, Math.round(far / 34)));
    for (let n = 1; n <= steps; n++) {
      const k = ease(n / steps);
      at = [from[0] + (to[0] - from[0]) * k, from[1] + (to[1] - from[1]) * k];
      await page.mouse.move(...at);
      await pointer(at);
      await frame();
    }
  };
  const click = async (target, part, after = 0.5) => {
    await move(target, part);
    await frame(3);
    await pointer(at, 0.3); await frame(2);
    await page.mouse.down(); await page.mouse.up();
    await wait(160);
    await pointer(at, 0.8); await frame(2);
    await pointer(at);
    await hold(after);
  };
  const type = async (words) => {
    for (let n = 0; n < words.length; n += 2) {
      await page.keyboard.type(words.slice(n, n + 2));
      await frame(3);
    }
  };
  /** Say something to Stagehand and let it answer one exchange at a time. */
  const talk = async (words, script, { said, each = 1.1 } = {}) => {
    hand.script = [...script];
    await click(page.locator('.mmc-sh-box'), [0.3, 0.5], 0.3);
    await type(words);
    await hold(0.7);
    await page.keyboard.press('Enter');
    await wait(250);
    await hold(0.9);
    for (let n = 0; n < script.length; n++) {
      await demo.step();
      await wait(350);
      await page.evaluate(() => { const log = document.querySelector('.mmc-sh-log'); if (log) log.scrollTop = log.scrollHeight; });
      if (said?.[n]) await caption(said[n]);
      await hold(typeof script[n] === 'string' ? each + 1.2 : each);
    }
  };
  const bench = (code) => page.evaluate(`(() => { const bench = node.mmcBody.reel; ${code} })()`);

  // ---- the film -----------------------------------------------------------------
  await demo.boot();
  await page.evaluate('openFullscreen()');
  await wait(900);
  await D.castReady(demo);
  await overlay();
  await pointer(at);

  await card('<h1>Continuity</h1><p>The timeline, Stagehand and the blockout bench:<br>from a sentence to a staged, shot film.</p>');
  await hold(3.2);

  // The timeline, empty.
  await page.evaluate(() => node.mmcBody.open());
  await wait(600);
  await card(null);
  await caption('The timeline is one window for a whole piece: the script on the left, the inspector on the right, the reel underneath.');
  await hold(4.2);

  // Stagehand writes the film.
  await caption('Stagehand builds the film by talking. It runs on the model your refiner already uses, on your machine.');
  await click(page.locator('.mmc-st-handbtn'), undefined, 2.4);
  await caption('Say what the film is. @ names the cast.');
  await talk(D.WORDS.film, D.buildFilm(), { said: [
    'Each thing it does lands in the script and on the reel as it happens.',
    'Three shots, each with its text, its length and the join in front of it.',
    'It never renders. Shoot stays yours, and everything one message did is one Undo.'] });
  await hold(1.6);

  // A join, by hand.
  await caption('Everything it wrote is yours to change. A join carries the picture and the sound across a cut, or doesn’t.');
  await click(page.locator('.mmc-sh-x'), undefined, 0.5);
  await click(page.locator('.mmc-reel-join').first(), undefined, 3.2);

  // Into the blockout.
  await caption('Ask for a 3D scene and Stagehand opens the blockout bench on that shot.');
  await click(page.locator('.mmc-st-handbtn'), undefined, 0.8);
  await talk(D.WORDS.stage, D.stageShot(), { each: 1.5, said: [
    'The blockout: the same piece, staged in 3D out of plain shapes.',
    'It starts from a kitchen in the scene library…',
    '…puts @anna at the counter, adds a fridge, a door and @ben…',
    '…walks him in from the hall, and sets a camera that pushes in.',
    'Then it looks through the shot camera to check its own work.',
    'Editing waits while it works. Stop ends it at once.'] });
  await hold(1.4);

  // The stage, by hand.
  await click(page.locator('.mmc-sh-x'), undefined, 0.4);
  await bench("bench.select({ kind: 'shot', index: 1 }); bench.goTo(1, 0); bench.draw();");
  await caption('Look around the set. The monitor in the corner is what the shot camera sees.');
  await click(page.getByRole('button', { name: 'Look around', exact: true }), undefined, 1.6);
  await caption('Play the shot: @ben walks his path, the camera travels its own.');
  await move(page.locator('.mmc-st-col button').filter({ has: page.locator('svg') }).nth(1));
  const play = async (from, to, speed = 1) => {
    for (let t = from; t <= to + 1e-6; t += speed / FPS) {
      await bench(`bench.at.t = ${Math.min(t, to).toFixed(4)}; bench.draw();`);
      await frame();
    }
  };
  await play(0, 6);
  await hold(0.8);
  await caption('Plan is the floor plan. Drag anybody to block them; the stops sit on the sheet below.');
  await click(page.getByRole('button', { name: 'Plan', exact: true }), undefined, 1.0);
  await bench('bench.goTo(1, 4.5); bench.draw();');
  await hold(2.6);
  await caption('What the camera sees: stand in the shot camera and frame it.');
  await click(page.getByRole('button', { name: 'What the camera sees', exact: true }), undefined, 0.6);
  await play(0, 6, 1.5);
  await hold(0.6);
  await caption('Guide is the pass the video model is given, exactly as the file will hold it.');
  await click(page.getByRole('button', { name: 'Guide', exact: true }), undefined, 2.8);
  await page.locator('.mmc-st > canvas').screenshot({ path: path.join(D.MEDIA, 'guide.jpg'), type: 'jpeg', quality: 90 });
  await caption('The inspector shows what the model gets for this shot: first and last frame, the guide clip, and the words.');
  await move(page.locator('.mmc-reel-side'), [0.5, 0.6]);
  await hold(3.4);

  // Shoot, and the takes that come back.
  await caption('Shoot derives the guides and queues the render.');
  await click(page.locator('.mmc-reel-shoot'), undefined, 0.5);
  await move([at[0] - 150, at[1] + 70]);
  // The guides are really drawn, frame by frame; the film watches the start and waits out the rest.
  for (let n = 0; n < 240 && /\d/.test(await page.locator('.mmc-reel-shoot').textContent()); n++) {
    await wait(250);
    if (n < 12) await snap(0.2);
  }
  await hold(0.8);
  await demo.land({ 1: 's1', 2: 's2' });
  await bench("bench.setView('take'); bench.goTo(1, 0); bench.draw();");
  await wait(500);
  await caption('Takes land on their shots and are kept: the next render plays them instead of shooting them again.');
  await hold(4.2);

  // Back on the timeline.
  await caption('Open the timeline: the same piece, with its takes on the reel.');
  await click(page.getByRole('button', { name: 'Open the timeline' }), undefined, 1.2);
  await page.evaluate(() => node.mmcBody.reel.select({ kind: 'shot', index: 1 }));
  await wait(500);
  await hold(1.4);
  const video = page.locator('.mmc-reel video').first();
  if (await video.count()) {
    for (let t = 0; t <= 3; t += 1 / FPS) {
      await video.evaluate((node, t) => new Promise((done) => { node.onseeked = done; node.currentTime = t; setTimeout(done, 400); }), t);
      await frame();
    }
  }
  await caption('Change a shot and only what depends on it is shot again.');
  await click(page.locator('.mmc-reel-shots .mmc-prompt').nth(1), [0.96, 0.75], 0.3);
  await page.keyboard.press('End');
  await type(' She does not look round.');
  await hold(3.6);

  await caption('');
  await card('<h1>Continuity</h1><p>One node for AI video and stills in ComfyUI.<br><b>github.com/roadmaus/ComfyUI-Continuity</b></p>'
    + '<small>Recorded in the UI harness. The model’s replies are scripted and the two takes are stand-in stills, not renders.</small>');
  await hold(4.5);

  await demo.close();

  // ---- the file -----------------------------------------------------------------
  const seconds = list.reduce((sum, [, s]) => sum + s, 0);
  console.log(`${list.length} pictures, ${seconds.toFixed(1)} s`);
  if (dry) return console.log(frames);
  const concat = path.join(frames, 'list.txt');
  fs.writeFileSync(concat, list.map(([file, s]) => `file '${file}'\nduration ${s.toFixed(5)}`).join('\n') + `\nfile '${list.at(-1)[0]}'\n`);
  fs.mkdirSync(path.dirname(out), { recursive: true });
  execFileSync('ffmpeg', ['-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', concat,
    '-vf', `fps=${FPS},scale=1920:1080:flags=lanczos,format=yuv420p`, '-c:v', 'libx264', '-preset', 'slow', '-crf', '23',
    '-movflags', '+faststart', '-an', out], { stdio: 'inherit' });
  fs.rmSync(frames, { recursive: true, force: true });
  console.log(out);
})().catch((error) => { console.error(error); process.exit(1); });

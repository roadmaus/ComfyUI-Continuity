/* Isolated headless browser checks: real viewer/DOM/CSS, in-memory media and API
 * adapters. No ComfyUI/profile/network/GPU execution. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '../..');
const read = file => fs.readFileSync(path.join(root, 'web/creator', file), 'utf8');
const dom = read('dom.js');
const helper = name => dom.match(new RegExp(`export function ${name}\\([^]*?^\\}`, 'm'))[0].replace('export ', '');
const code = read('reference-preview.js').replace(/^import .*;\r?\n/gm, '').replace(/^export /gm, '');
const renderAssets = read('editor.js').match(/^  renderAssets\(\) \{[^]*?^  \}/m)[0];
const css = ['base', 'picker', 'editor', 'overlays'].map(name => read(`styles/${name}.js`).match(/export const css = `([^]*)`;\s*$/)[1]).join('\n');
const results = [];
let browser;
let requests = 0;
const test = async (name, run) => { await run(); results.push(name); console.log(`PASS ${name}`); };
(async () => {
  browser = await chromium.launch({ executablePath: process.env.BROWSER_EXECUTABLE_PATH || undefined, headless: true });
  const context = await browser.newContext({ viewport: { width: 1100, height: 850 } });
  await context.route('**/*', route => { requests++; return route.abort(); });
  const page = await context.newPage();
  await page.setContent(`<style>${css}</style><button id="outside">Outside</button><span id="thumb">Thumb</span>`);
  await page.evaluate(async () => {
    const canvas = document.createElement('canvas'); canvas.width = 64; canvas.height = 96;
    canvas.getContext('2d').fillRect(0, 0, 64, 96);
    const chunks = [];
    const stream = canvas.captureStream(10);
    const recorder = new MediaRecorder(stream, { mimeType: 'video/webm' });
    recorder.ondataavailable = event => chunks.push(event.data);
    const done = new Promise(resolve => recorder.onstop = resolve);
    recorder.start();
    let frame = 0;
    const ticker = setInterval(() => {
      const ctx = canvas.getContext('2d'); ctx.fillStyle = ++frame % 2 ? 'red' : 'blue'; ctx.fillRect(0,0,64,96);
    }, 45);
    await new Promise(resolve => setTimeout(resolve, 600));
    clearInterval(ticker);
    recorder.stop(); await done;
    stream.getTracks().forEach(track => track.stop());
    window.videoUrl = URL.createObjectURL(new Blob(chunks, { type: 'video/webm' }));
    window.imageUrl = canvas.toDataURL();
  });
  await page.evaluate(`(() => { ${helper('el')}\n${helper('mountOverlay')}\n${helper('swappable')}
    Object.assign(window,{el,mountOverlay});
    const t = (text, values = {}) => text.replace(/\\{([^}]+)\\}/g, (_, key) => values[key] ?? key);
    const S = { isRefMod: a => String(a?.filename ?? '').startsWith('refmod:'), thumbCrop: a => a.crop ?? null };
    window.urlCalls = [];
    const viewUrl = (file, opts) => { urlCalls.push({file, opts}); return file.endsWith('.webm') ? videoUrl : imageUrl; };
    ${code}
    Object.assign(window, {openReferencePreview, previewable, isVisualReference});
    window.assets = [
      {kind:'image', filename:'portrait.png', handle:'ref-1', crop:{x:0.2}, trim:{start:1,end:2}},
      {kind:'video', filename:'motion.webm', handle:'ref-2', crop:{x:0.8}, trim:{start:3,end:5}},
      {kind:'video', filename:'refmod:saved', handle:'ref-3'},
    ];
    window.snapshot = JSON.stringify(assets);
    window.previewOpens = 0;
    window.rowClicks = 0;
    document.body.addEventListener('click', () => rowClicks++);
    previewable(document.querySelector('#thumb'), {title:'Preview',open: returnFocus => {previewOpens++; window.closePreview = openReferencePreview(assets,{returnFocus});}});
    Object.assign(S, {passedOver:()=>new Set(),asleepHere:()=>new Set(),citedCast:()=>[],
      isPlate:()=>false,croppable:()=>false,tagIndex:()=>0,muted:()=>false,citedPool:s=>s.pool,
      roleLabel:role=>role});
    const referenceSummary=()=>'';
    const keepScroll=x=>x;
    const ICONS={image:'',video:'',audio:''};
    const svg=()=>el('span');
    class Renderer { ${renderAssets} }
    window.mountAssetFixture = (segment = true) => {
      document.querySelector('#fixture')?.remove();
      const state={assets:[{...assets[0],role:'reference'},{...assets[1],role:'reference'},
        {filename:'voice.wav',kind:'audio',handle:'aud-1',role:'reference'}],
        pool:[{...assets[0],filename:'pooled.png',handle:'ref-4'},{...assets[1],filename:'pooled.webm',handle:'ref-5'}]};
      window.fixtureState=state;
      window.fixtureSnapshot=JSON.stringify(state);
      window.swaps=0;
      const fixture=Object.assign(new Renderer(),{state,piece:segment?{segments:[state]}:state,
        castPiece:{subjects:[]},replaceAsset:()=>swaps++,muteButton:()=>el('button'),remove:()=>{},openReferenceSheet:()=>{}});
      const host=fixture.renderAssets();host.id='fixture';document.body.append(host);
    };
  })()`);
  await test('visual filter excludes missing/audio/sound-only, includes video RefMod', async () => {
    assert.deepEqual(await page.evaluate(() => [
      isVisualReference(null), isVisualReference({kind:'image'}),
      isVisualReference({filename:'a.wav',kind:'audio'}),
      isVisualReference({filename:'a.mp4',kind:'video',track:'sound'}),
      isVisualReference(assets[0]),isVisualReference(assets[1]),isVisualReference(assets[2])
    ]), [false,false,false,false,true,true,true]);
  });
  await test('single click is inert; double click opens exactly one viewer without bubbling', async () => {
    await page.locator('#thumb').click();
    assert.equal(await page.locator('.mmc-reference-preview').count(),0);
    await page.locator('#thumb').dblclick();
    assert.deepEqual(await page.evaluate(() => [previewOpens,rowClicks]),[1,0]);
    assert.equal(await page.locator('.mmc-reference-preview').count(),1);
  });
  await test('image crop is preserved and first native video uses uncropped source/no autoplay', async () => {
    assert.deepEqual(await page.evaluate(() => urlCalls.at(-1)),{file:'portrait.png',opts:{crop:{x:0.2}}});
    await page.getByRole('button',{name:'Next reference'}).click();
    const result = await page.evaluate(() => { const v=document.querySelector('video'); return {call:urlCalls.at(-1),controls:v.controls,autoplay:v.autoplay,paused:v.paused,inline:v.playsInline}; });
    assert.deepEqual(result,{call:{file:'motion.webm',opts:undefined},controls:true,autoplay:false,paused:true,inline:true});
    assert.match(await page.locator('.mmc-reference-preview-note').innerText(),/Configured range: 3–5 s/);
    await page.waitForFunction(() => document.querySelector('video').readyState >= 2);
  });
  await test('local synthetic video plays and changing reference stops/unloads it', async () => {
    await page.evaluate(async () => { window.oldVideo=document.querySelector('video'); oldVideo.loop=true; await oldVideo.play(); });
    assert.equal(await page.evaluate(() => oldVideo.paused),false);
    await page.getByRole('button',{name:'Next reference'}).click();
    assert.deepEqual(await page.evaluate(() => [oldVideo.paused,oldVideo.getAttribute('src'),oldVideo.isConnected]),[true,null,false]);
    assert.equal(await page.locator('.mmc-reference-preview-stage img').count(),1);
    assert.match(await page.locator('.mmc-reference-preview-note').innerText(),/RefMod preview image/);
  });
  await test('media error has useful visible message; changing files resets it', async () => {
    await page.locator('.mmc-reference-preview-stage img').dispatchEvent('error');
    assert.equal(await page.locator('.mmc-reference-preview-error').isVisible(),true);
    await page.getByRole('button',{name:'Previous reference'}).click();
    assert.equal(await page.locator('.mmc-reference-preview-error').isVisible(),false);
  });
  await test('close cleans video, restores source focus and does not mutate assets', async () => {
    await page.evaluate(() => window.oldVideo=document.querySelector('video'));
    await page.getByRole('button',{name:'Close',exact:true}).click();
    assert.deepEqual(await page.evaluate(() => [oldVideo.paused,oldVideo.getAttribute('src'),document.activeElement.id,JSON.stringify(assets)===snapshot]),[true,null,'thumb',true]);
    await page.evaluate(() => {closePreview();closePreview();});
    assert.equal(await page.locator('.mmc-reference-preview').count(),0);
  });
  await test('Enter and Space activate preview, holding key does not create duplicates', async () => {
    await page.locator('#thumb').focus(); await page.keyboard.press('Enter');
    await page.keyboard.press('Escape');
    await page.locator('#thumb').focus(); await page.keyboard.press('Space');
    await page.evaluate(() => document.querySelector('#thumb').dispatchEvent(new KeyboardEvent('keydown',{key:' ',repeat:true,bubbles:true})));
    assert.equal(await page.locator('.mmc-reference-preview').count(),1);
    await page.keyboard.press('Escape');
  });
  await test('nested Escape closes preview only; second Escape belongs to parent', async () => {
    await page.evaluate(() => {
      window.parentEsc=0; const p=el('div',{class:'mmc-overlay',id:'parent'});
      window.closeParent=mountOverlay(p,()=>{parentEsc++;closeParent();});
      window.closePreview=openReferencePreview(assets);
    });
    await page.keyboard.press('Escape');
    assert.equal(await page.evaluate(() => parentEsc),0);
    assert.equal(await page.locator('#parent').count(),1);
    await page.keyboard.press('Escape');
    assert.equal(await page.evaluate(() => parentEsc),1);
  });
  await test('focus guards wrap and multiple opens replace the previous viewer', async () => {
    await page.evaluate(() => {openReferencePreview([assets[0]]);openReferencePreview(assets);});
    assert.equal(await page.locator('.mmc-reference-preview').count(),1);
    await page.getByRole('button',{name:'Close',exact:true}).focus(); await page.keyboard.press('Shift+Tab');
    assert.equal(await page.evaluate(() => document.activeElement.getAttribute('aria-label')),'Next reference');
    await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(() => document.activeElement.getAttribute('aria-label')),'Close');
    await page.keyboard.press('Escape');
  });
  await test('backdrop closes and unloads media', async () => {
    await page.evaluate(() => {openReferencePreview([assets[1]]);window.oldVideo=document.querySelector('video');});
    await page.locator('.mmc-reference-preview-overlay').click({position:{x:5,y:5}});
    assert.deepEqual(await page.evaluate(() => [oldVideo.paused,oldVideo.getAttribute('src'),document.querySelectorAll('.mmc-reference-preview').length]),[true,null,0]);
  });
  await test('native fullscreen exits before Escape closes the preview', async () => {
    await page.evaluate(() => {
      openReferencePreview([assets[1]]);
      const trigger=document.createElement('button');trigger.id='fullscreen-fixture';trigger.textContent='Fullscreen test';
      trigger.onclick=()=>document.querySelector('video').requestFullscreen();
      document.querySelector('.mmc-reference-preview-head').append(trigger);
    });
    await page.locator('#fullscreen-fixture').click();
    await page.waitForFunction(() => Boolean(document.fullscreenElement));
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => !document.fullscreenElement);
    assert.equal(await page.locator('.mmc-reference-preview').count(),1);
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('.mmc-reference-preview').count(),0);
  });
  await test('narrow viewport and long names stay inside modal; controls below media', async () => {
    await page.setViewportSize({width:390,height:740});
    await page.evaluate(() => openReferencePreview([{...assets[1],filename:'Long_name_'.repeat(35)+'.webm'}]));
    const rects=await page.evaluate(() => ['.mmc-reference-preview','.mmc-reference-preview-stage','.mmc-reference-preview-foot'].map(s=>{const r=document.querySelector(s).getBoundingClientRect(); return {x:r.x,right:r.right,y:r.y,bottom:r.bottom};}));
    assert.ok(rects.every(r=>r.x>=0&&r.right<=390&&r.y>=0&&r.bottom<=740));
    assert.ok(rects[1].bottom<=rects[2].y);
    await page.keyboard.press('Escape');
  });
  await page.setViewportSize({width:1100,height:850});
  await test('owned chips swap on single click and preview on double click; pooled chips only preview', async () => {
    await page.evaluate(() => { swaps=0; mountAssetFixture(true); });
    for (const [index,file,tag,owned] of [[0,'portrait.png','img',true],[1,'motion.webm','video',true],[3,'pooled.png','img',false],[4,'pooled.webm','video',false]]) {
      const thumb=page.locator('#fixture .mmc-asset-thumb').nth(index);
      const before=await page.evaluate(() => swaps);
      await thumb.click();
      await page.waitForTimeout(400);
      assert.equal(await page.locator('.mmc-reference-preview').count(),0);
      assert.equal(await page.evaluate(() => swaps),before+(owned?1:0));
      // The first click of a double must not leave a swap behind.
      await thumb.dblclick();
      await page.waitForTimeout(400);
      assert.equal(await page.evaluate(() => swaps),before+(owned?1:0));
      assert.equal(await page.locator('.mmc-reference-preview').count(),1);
      assert.equal(await page.locator('.mmc-reference-preview-stage '+tag).count(),1);
      assert.equal(await page.evaluate(() => urlCalls.at(-1).file),file);
      await page.keyboard.press('Escape');
    }
    assert.deepEqual(await page.evaluate(() => [swaps,JSON.stringify(fixtureState)===fixtureSnapshot]),[2,true]);
  });
  await test('real nonvisual audio chip keeps single-click replacement', async () => {
    await page.evaluate(() => { swaps=0; });
    await page.locator('#fixture .mmc-asset-thumb').nth(2).click();
    assert.equal(await page.evaluate(() => swaps),1);
    assert.equal(await page.locator('.mmc-reference-preview').count(),0);
  });
  await test('real Prestage/non-segment renderer retains thumbnail swap rather than preview', async () => {
    await page.evaluate(() => { swaps=0; mountAssetFixture(false); });
    await page.locator('#fixture .mmc-asset-thumb').nth(0).click();
    await page.locator('#fixture .mmc-asset-thumb').nth(1).click();
    assert.equal(await page.evaluate(() => swaps),2);
    assert.equal(await page.locator('#fixture .mmc-reference-preview-target').count(),0);
    assert.equal(await page.locator('.mmc-reference-preview').count(),0);
  });
  await test('editor owns both preview bindings and keeps nonvisual swap + handle menu', async () => {
    const source=read('editor.js');
    assert.equal((source.match(/open: \(returnFocus\) => openReferencePreview\(\[asset\], \{ returnFocus \}\)/g)||[]).length,2);
    assert.match(source,/Audio keeps its established single-click replacement action/);
    assert.match(source,/Swap file/);
  });
  assert.equal(requests,0,'Fixture must not issue network requests');
  console.log(JSON.stringify({passed:results.length,networkRequests:requests,scope:'isolated browser: real viewer/DOM/CSS; stub API/state; synthetic local WebM, not ComfyUI/GPU or arbitrary user codecs'}));
})().catch(error => {console.error(error);process.exitCode=1;}).finally(async()=>{await browser?.close();});

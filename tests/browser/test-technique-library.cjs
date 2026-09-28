/* Isolated native-browser contract checks with fixture catalogue/media.
 * Runs actual ES modules and CSS. All requests are fulfilled in memory; this
 * does not use a ComfyUI installation, a GPU, or the source website. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
let playwright;
try { playwright = require(process.env.PLAYWRIGHT_MODULE || 'playwright'); }
catch (error) {
  throw new Error('Playwright is required for this browser suite. Install playwright locally or set PLAYWRIGHT_MODULE to an installed Playwright module.', { cause: error });
}
const { chromium } = playwright;
const root = path.resolve(__dirname, '../..');
const source = file => fs.readFileSync(path.join(root, 'web/creator', file));
const css = ['base', 'picker', 'techniques'].map(name => source(`styles/${name}.js`).toString().match(/export const css = `([^]*)`;\s*$/)[1]).join('\n');
const categories = Array.from({length:13}, (_,i) => ({id:`category-${i}`,title:i===0?'Camera Movement':`Category ${i}`,count:i<8?33:32}));
const items = Array.from({length:424},(_,i)=>({id:`category-${i%13}/item-${i}`,slug:`item-${i}`,title:`Technique ${i}`,categoryId:`category-${i%13}`,
  categoryTitle:categories[i%13].title,aliases:[i===0?'fixture-alias':''],description:`Original description ${i}.`,
  thumbnail:`media/thumbnail.png`,video:'media/preview.webm',detail:`details/item-${i}.json`,sourceUrl:`https://melies.co/cinematic-techniques/category-${i%13}/item-${i}`}));
const original='[Shot 1]\nAn unrelated example person.\n  Keep original spacing.  ';
const detail = i => ({...items[i],sourceHtmlSha256:`fixture-hash-${i}`,prompt:{guidance:['A camera approaches [Subject] for [Duration] seconds.'],example:original},
  sections:[{id:'usage',title:'When to use it',blocks:[{type:'paragraph',text:'Original usage paragraph. See Technique 1.',links:[{text:'Technique 1',url:items[1].sourceUrl}]},{type:'list-item',text:'Original list item.'},
    {type:'heading',text:'Film examples'},{type:'quote',text:'Original film example.'},{type:'paragraph',text:'<img src=x onerror=alert(1)>'}],
    links:[{text:'Source reference',url:'https://melies.co/example'},{text:'Unsafe link',url:'javascript:alert(1)'}],media:[]},
    {id:'vs',title:'Compared with similar shots',blocks:[{type:'list-item',text:'Technique 1A linked comparison.',displayText:'Technique 1\nA linked comparison.',links:[{text:'Technique 1A linked comparison.',url:items[1].sourceUrl}]},
      {type:'list-item',text:'Technique 2A still-image comparison.',displayText:'Technique 2\nA still-image comparison.',links:[{text:'Technique 2A still-image comparison.',url:items[2].sourceUrl}]}],links:[],
      media:[{kind:'image',path:'media/compare.png',alt:'Technique 1'},{kind:'video',path:'media/compare.webm',alt:'Technique 1'},{kind:'image',path:'media/still-only.png',alt:'Technique 2'}]},
    {id:'examples-film',title:'In film',blocks:[{type:'list-item',text:'Film 2000A genuine still.',displayText:'Film 2000\nA genuine still.'}],links:[],media:[{kind:'image',path:'media/film.png',alt:'Film 2000'}]},
    {id:'faq',title:'Frequently asked questions',blocks:[{type:'heading',text:'Original question?'},{type:'paragraph',text:'Original answer.'}],links:[],media:[]},
    {id:'prompt',title:'Prompt it',blocks:[{type:'paragraph',text:'A camera approaches [Subject] for [Duration] seconds.'},{type:'quote',text:original}],links:[],media:[]}],
  media:[{kind:'video',path:'media/second.webm',alt:'Second source video'},{kind:'image',path:'media/second.png',alt:'Film still'}]});
const fixtureStructure={version:1,sourceCapturedAt:'fixture-capture',offsetEncoding:'utf16',items:Object.fromEntries(items.map((item,i)=>[item.id,{
  sourceHtmlSha256:`fixture-hash-${i}`,sections:{usage:{cards:[],inlineLinks:[{blockIndex:0,sourceText:'Original usage paragraph. See Technique 1.',ranges:[{start:30,end:41,text:'Technique 1',targetId:items[1].id}]}]},
    vs:{cards:[{kind:'technique',blockIndex:0,title:'Technique 1',description:'A linked comparison.',targetId:items[1].id,media:{kind:'video',path:'media/compare.webm',poster:'media/compare.png',alt:'Technique 1'}},
      {kind:'technique',blockIndex:1,title:'Technique 2',description:'A still-image comparison.',targetId:items[2].id,media:{kind:'image',path:'media/still-only.png',alt:'Technique 2'}}],inlineLinks:[]},
    'examples-film':{cards:[{kind:'film',blockIndex:0,title:'Film 2000',description:'A genuine still.',media:{kind:'image',path:'media/film.png',alt:'Film 2000'}}],inlineLinks:[]}},recommendedIds:[items[1].id,items[2].id]}]))};
const localText={ko:{description:'피사체를 향해 카메라가 이동합니다.',usage:'인물에게 집중할 때 사용합니다.',heading:'사용 시점'},
  ja:{description:'被写体に向かってカメラが移動します。',usage:'人物に注目させたいときに使います。',heading:'使用する場面'},
  zh:{description:'摄影机向主体移动。',usage:'用于将注意力集中在人物上。',heading:'适用场景'}};
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aPioAAAAASUVORK5CYII=','base64');
const results=[];
let browser;
const test=async(name,fn)=>{await fn();results.push(name);console.log(`PASS ${name}`);};
(async()=>{
  const executablePath=process.env.BROWSER_EXECUTABLE_PATH || process.env.BROWSER_EXECUTABLE;
  browser=await chromium.launch({headless:true,...(executablePath?{executablePath}:{})});
  const context=await browser.newContext({viewport:{width:1400,height:950},locale:'en-US',permissions:['clipboard-read','clipboard-write']});
  const page=await context.newPage();
  page.setDefaultTimeout(10000);
  await page.setContent('<canvas></canvas>');
  const videoBytes=await page.evaluate(async()=>{
    const canvas=document.querySelector('canvas');canvas.width=96;canvas.height=64;
    const stream=canvas.captureStream(12);const chunks=[];const recorder=new MediaRecorder(stream,{mimeType:'video/webm'});
    recorder.ondataavailable=e=>chunks.push(e.data);const done=new Promise(resolve=>recorder.onstop=resolve);recorder.start();
    let f=0;const timer=setInterval(()=>{const ctx=canvas.getContext('2d');ctx.fillStyle=++f%2?'#d39a30':'#245d89';ctx.fillRect(0,0,96,64);},45);
    await new Promise(resolve=>setTimeout(resolve,700));clearInterval(timer);recorder.stop();await done;stream.getTracks().forEach(t=>t.stop());
    return [...new Uint8Array(await new Blob(chunks,{type:'video/webm'}).arrayBuffer())];
  });
  const video=Buffer.from(videoBytes);
  let catalogFailures=1;
  let detailFailures=0;
  let holdDetail=false;
  let actualCatalogue=false;
  let missingStructure=false;
  const urls=[];
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await context.route('**/*',async route=>{
    const url=new URL(route.request().url());urls.push(url.href);
    if(url.origin!=='https://technique.test')throw new Error(`Unexpected remote request: ${url.href}`);
    if(actualCatalogue && url.pathname.startsWith('/web/creator/techniques/')) {
      const relative=url.pathname.slice('/web/creator/'.length);
      const full=path.join(root,'web/creator',relative);
      if(!fs.existsSync(full))return route.fulfill({status:404,body:'Download still pending'});
      const ext=path.extname(full);
      return route.fulfill({contentType:ext==='.json'?'application/json':ext==='.mp4'?'video/mp4':ext==='.webm'?'video/webm':ext==='.webp'?'image/webp':ext==='.png'?'image/png':'image/jpeg',body:fs.readFileSync(full)});
    }
    if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:`<style>:root{--comfy-menu-bg:#191919;--fg-color:#eee;--bg-color:#161616;--input-text:#ddd;--descrip-text:#aaa;}body{background:#161616;}${css}</style><button id="outside">Open fixture</button><script type="module">
      import {openTechniqueLibrary} from '/web/creator/techniques.js';
      import {el,mountOverlay} from '/web/creator/dom.js';
      window.openTechniqueLibrary=openTechniqueLibrary;window.el=el;window.mountOverlay=mountOverlay;
      window.applied=[];window.refined=true;window.failApply=false;
      window.targets=[{id:'global',label:'Global prompt',kind:'global',subjects:[{handle:'anna',label:'@anna'}],duration:null,
        apply:async value=>{if(window.failApply)return {ok:false,reason:'Fixture refused'};window.applied.push({target:'global',...value});return {ok:true};}},
        {id:'segment-3',label:'Segment 3',kind:'segment',subjects:[{handle:'anna',label:'@anna'},{handle:'hero_2',label:'@hero_2'}],duration:6,
         requiresRefineAcknowledgement:()=>window.refined,warning:()=>window.refined?'Active refinement fixture.':null,
         apply:async value=>{if(window.failApply)return {ok:false,reason:'Fixture refused'};window.applied.push({target:'segment-3',...value});window.refined=false;return {ok:true};}}];
      window.ready=true;
    </script>`});
    if(url.pathname.endsWith('/techniques/catalog.json')){
      if(catalogFailures-->0)return route.fulfill({status:503,body:'fixture failure'});
      return route.fulfill({contentType:'application/json',body:JSON.stringify({version:1,capturedAt:'fixture-capture',categories,items,sourceUrl:'https://melies.co/cinematic-techniques'})});
    }
    if(url.pathname.endsWith('/techniques/structure.json'))return route.fulfill({status:missingStructure?404:200,contentType:'application/json',body:JSON.stringify(fixtureStructure)});
    const translation=url.pathname.match(/\/techniques\/translations\/(ko|ja|zh)\/(.+)$/);
    if(translation){
      const locale=translation[1], words=localText[locale];
      if(translation[2]==='catalog.json')return route.fulfill({contentType:'application/json',body:JSON.stringify({version:1,locale,sourceCapturedAt:'fixture-capture',
        items:{[items[0].id]:{description:words.description},[items[2].id]:{description:words.description}}})});
      const item=translation[2].match(/item-(\d+)\.json$/);
      if(item&&[0,2].includes(Number(item[1])))return route.fulfill({contentType:'application/json',body:JSON.stringify({version:1,locale,id:items[Number(item[1])].id,
        sourceHtmlSha256:Number(item[1])===0?'fixture-hash-0':'stale-source-hash',description:words.description,
        sections:[{id:'usage',title:words.heading,blocks:[{index:0,text:words.usage}]},
          {id:'prompt',title:'Localized prompt heading',blocks:[{index:0,text:'DO NOT SHOW TRANSLATED PROMPT'},{index:1,text:'DO NOT SHOW TRANSLATED EXAMPLE'}]}]})});
      return route.fulfill({status:404,body:'No translation fixture'});
    }
    const hit=url.pathname.match(/\/details\/item-(\d+)\.json$/);
    if(hit){
      if(detailFailures-->0)return route.fulfill({status:500,body:'fixture detail failure'});
      if(holdDetail)await new Promise(resolve=>setTimeout(resolve,300));
      return route.fulfill({contentType:'application/json',body:JSON.stringify(detail(Number(hit[1])))});
    }
    if(url.pathname.endsWith('.webm'))return route.fulfill({contentType:'video/webm',body:video});
    if(url.pathname.endsWith('.png'))return route.fulfill({contentType:'image/png',body:png});
    const prefix='/web/creator/';
    if(url.pathname.startsWith(prefix))return route.fulfill({contentType:'text/javascript',body:source(url.pathname.slice(prefix.length))});
    return route.fulfill({status:404,body:'Not found'});
  });
  await page.goto('https://technique.test/');
  await page.waitForFunction(()=>window.ready);
  const open=async(options='{}')=>{await page.evaluate(`window.closeLibrary=openTechniqueLibrary(${options})`);};
  const back=async()=>{if(await page.locator('.mmc-tech-back').isVisible())await page.locator('.mmc-tech-back').click();};
  const select=async i=>{await back();await page.locator(`[data-technique="category-${i%13}/item-${i}"]`).click();await page.locator('.mmc-tech-detail-title h2').filter({hasText:`Technique ${i}`}).waitFor();};
  await test('catalogue failure is explicit and Retry recovers all 424 items',async()=>{
    await open('{target:targets[1],targets}');
    await page.getByText('No catalogue was loaded. Check that the complete test package was extracted.').waitFor();
    await page.getByRole('button',{name:'Retry',exact:true}).click();
    await page.getByText('424 / 424 techniques',{exact:true}).waitFor();
    assert.equal(await page.locator('.mmc-tech-card').count(),48);
    assert.equal(await page.locator('.mmc-tech-categories button').count(),15);
    assert.deepEqual(await page.locator('.mmc-tech-categories button').evaluateAll(es=>es.slice(0,3).map(e=>e.textContent)),['All categories','☆ Bookmarks','Camera Movement · 33']);
    assert.equal(await page.locator('.mmc-tech-scope, .mmc-tech-explanation-bar').count(),0);
    assert.equal(await page.locator('.mmc-tech-inspector').isVisible(),false);
  });
  await test('wrapping categories stay within the modal; All and Bookmarks combine with a category',async()=>{
    const fits=await page.locator('.mmc-tech-categories').evaluate(e=>e.scrollWidth<=e.clientWidth+1);
    assert.equal(fits,true);
    await page.locator('.mmc-tech-star').first().click();
    await page.getByRole('button',{name:'☆ Bookmarks',exact:true}).click();
    assert.equal(await page.locator('.mmc-tech-card').count(),1);
    await page.locator('.mmc-tech-categories button').filter({hasText:'Category 1 ·'}).click();
    assert.equal(await page.locator('.mmc-tech-card').count(),0);
    await page.getByRole('button',{name:'All categories',exact:true}).click();
    assert.equal(await page.locator('.mmc-tech-card').count(),1);
    await page.getByRole('button',{name:'☆ Bookmarks',exact:true}).click();
    assert.equal(await page.getByRole('button',{name:'☆ Bookmarks',exact:true}).getAttribute('aria-pressed'),'false');
  });
  await test('search finds aliases; selection does not apply; source HTML is harmless text',async()=>{
    await page.getByRole('searchbox').fill('fixture-alias');
    assert.equal(await page.locator('.mmc-tech-card').count(),1);
    await select(0);
    assert.equal(await page.evaluate(()=>applied.length),0);
    assert.match(await page.locator('.mmc-tech-article').innerText(),/Original usage paragraph/);
    assert.match(await page.locator('.mmc-tech-article').innerText(),/Original answer/);
    assert.equal(await page.locator('.mmc-tech-article img[onerror]').count(),0);
    assert.equal(await page.getByRole('link',{name:'Unsafe link'}).count(),0);
    assert.equal(await page.locator('.mmc-tech-source-section').filter({hasText:'<img src=x onerror=alert(1)>'}).count(),1);
  });
  await test('full-width detail has one body scroll and its editable prompt precedes long usage content',async()=>{
    assert.equal(await page.locator('.mmc-tech-list').isVisible(),false);
    const geometry=await page.locator('.mmc-tech-inspector').evaluate(inspector=>{
      const modal=inspector.closest('.mmc-tech-modal'), body=inspector.querySelector('.mmc-tech-detail-body');
      const application=inspector.querySelector('.mmc-tech-application'), source=inspector.querySelector('.mmc-tech-source-section');
      const scrollAreas=[...inspector.querySelectorAll('*')].filter(e=>e.tagName!=='TEXTAREA'&&e.getClientRects().length&&/(auto|scroll)/.test(getComputedStyle(e).overflowY)&&e.scrollHeight>e.clientHeight+1);
      return {fullWidth:inspector.clientWidth>=modal.clientWidth-2,scrollAreas:scrollAreas.map(e=>e.className),
        earlyPrompt:Boolean(application.compareDocumentPosition(source)&Node.DOCUMENT_POSITION_FOLLOWING),bodyScrollable:body.scrollHeight>body.clientHeight};
    });
    assert.equal(geometry.fullWidth,true);
    assert.deepEqual(geometry.scrollAreas,['mmc-tech-detail-body']);
    assert.equal(geometry.earlyPrompt,true);
    assert.equal(geometry.bodyScrollable,true);
  });
  await test('only real target handles are offered; placeholders preserve source until explicitly chosen',async()=>{
    assert.deepEqual(await page.getByLabel('Subject placeholder',{exact:true}).locator('option').evaluateAll(es=>es.map(e=>e.value)),['','@anna','@hero_2']);
    assert.equal(await page.getByLabel('Editable insertion preview').inputValue(),'A camera approaches [Subject] for 6 seconds.');
    await page.getByLabel('Subject placeholder',{exact:true}).selectOption('@anna');
    assert.equal(await page.getByLabel('Editable insertion preview').inputValue(),'A camera approaches @anna for 6 seconds.');
  });
  await test('generated placeholder choices survive target and mode changes without leaking into another target',async()=>{
    await page.getByLabel('Duration placeholder (seconds)').fill('12');
    assert.equal(await page.locator('.mmc-tech-preview').inputValue(),'A camera approaches @anna for 12 seconds.');
    await page.getByLabel('Apply to',{exact:true}).selectOption('global');
    assert.equal(await page.getByLabel('Subject placeholder',{exact:true}).inputValue(),'');
    assert.equal(await page.getByLabel('Duration placeholder (seconds)').inputValue(),'');
    await page.getByLabel('Apply to',{exact:true}).selectOption('segment-3');
    assert.equal(await page.getByLabel('Subject placeholder',{exact:true}).inputValue(),'@anna');
    assert.equal(await page.getByLabel('Duration placeholder (seconds)').inputValue(),'12');
    assert.equal(await page.locator('.mmc-tech-preview').inputValue(),'A camera approaches @anna for 12 seconds.');
    await page.getByRole('button',{name:'Original example',exact:true}).click();
    assert.equal(await page.locator('.mmc-tech-preview').inputValue(),original);
    await page.getByRole('button',{name:'Technique only',exact:true}).click();
    assert.equal(await page.locator('.mmc-tech-preview').inputValue(),'A camera approaches @anna for 12 seconds.');
  });
  await test('active refinement requires unchecked consent; exact reviewed text and destination are submitted',async()=>{
    assert.equal(await page.getByRole('button',{name:'Add to prompt',exact:true}).isDisabled(),true);
    await page.getByLabel('Editable insertion preview').fill('My edited camera instruction.');
    await page.getByRole('checkbox').check();
    await page.getByRole('button',{name:'Add to prompt',exact:true}).click();
    await page.getByText('Added to Segment 3. Existing prompt text was preserved.').waitFor();
    assert.deepEqual(await page.evaluate(()=>({target:applied[0].target,text:applied[0].text,allowRefined:applied[0].allowRefined,mode:applied[0].mode})),
      {target:'segment-3',text:'My edited camera instruction.',allowRefined:true,mode:'technique'});
  });
  await test('original prompt mode and copy preserve text (OS clipboard line endings excepted) without applying',async()=>{
    await page.getByRole('button',{name:'Original example',exact:true}).click();
    assert.equal(await page.getByLabel('Editable insertion preview').inputValue(),original);
    assert.equal(await page.locator('.mmc-tech-original-block, .mmc-tech-original').count(),0);
    await page.locator('.mmc-tech-copy').click();
    assert.equal((await page.evaluate(()=>navigator.clipboard.readText())).replace(/\r\n/g,'\n'),original);
    assert.equal(await page.evaluate(()=>applied.length),1);
  });
  await test('clipboard denial selects original-mode editor text for manual copy without changing a prompt',async()=>{
    await page.evaluate(()=>{window.oldClipboardWrite=navigator.clipboard.writeText;navigator.clipboard.writeText=async()=>{throw new Error('Denied fixture');};});
    await page.locator('.mmc-tech-copy').click();
    await page.getByText('Clipboard unavailable. The prompt is selected; use your copy shortcut.').waitFor();
    assert.deepEqual(await page.locator('.mmc-tech-preview').evaluate(e=>[e.selectionStart,e.selectionEnd]),[0,original.length]);
    assert.equal(await page.evaluate(()=>applied.length),1);
    await page.evaluate(()=>navigator.clipboard.writeText=oldClipboardWrite);
  });
  await test('single editor keeps both mode drafts; explicit reset restores only the current example draft',async()=>{
    await page.locator('.mmc-tech-preview').fill('Edited source example for this target.');
    assert.equal(await page.locator('.mmc-tech-reset-original').filter({hasText:'Reset to source example'}).isVisible(),true);
    await page.getByRole('button',{name:'Technique only',exact:true}).click();
    const techniqueDraft=await page.locator('.mmc-tech-preview').inputValue();
    await page.getByRole('button',{name:'Original example',exact:true}).click();
    assert.equal(await page.locator('.mmc-tech-preview').inputValue(),'Edited source example for this target.');
    await page.getByRole('button',{name:'Reset to source example',exact:true}).click();
    assert.equal(await page.locator('.mmc-tech-preview').inputValue(),original);
    await page.getByRole('button',{name:'Technique only',exact:true}).click();
    assert.equal(await page.locator('.mmc-tech-preview').inputValue(),techniqueDraft);
    await page.getByRole('button',{name:'Review prompt above',exact:true}).click();
    assert.equal(await page.locator('.mmc-tech-preview').evaluate(e=>e===document.activeElement),true);
    assert.equal(await page.locator('.mmc-tech-original, .mmc-tech-original-block').count(),0);
    assert.equal(await page.locator('[data-section="prompt"] blockquote').count(),0);
    assert.equal(await page.locator('.mmc-tech-article a[href]').count(),0);
  });
  await test('target changes clear refinement consent and global target does not inherit segment duration',async()=>{
    await page.getByLabel('Apply to',{exact:true}).selectOption('global');
    await page.getByRole('button',{name:'Technique only',exact:true}).click();
    assert.equal(await page.getByLabel('Duration placeholder (seconds)').inputValue(),'');
    assert.equal(await page.getByLabel('Editable insertion preview').inputValue(),'A camera approaches [Subject] for [Duration] seconds.');
    assert.deepEqual(await page.getByLabel('Subject placeholder',{exact:true}).locator('option').evaluateAll(es=>es.map(e=>e.value)),['','@anna']);
    assert.equal(await page.locator('.mmc-tech-refine-ack input').isChecked(),false);
  });
  await test('callback {ok:false,reason} remains failure without success announcement',async()=>{
    await page.evaluate(()=>window.failApply=true);
    await page.getByRole('button',{name:'Add to prompt',exact:true}).click();
    await page.getByText('Could not apply technique — Fixture refused').waitFor();
    assert.equal(await page.evaluate(()=>applied.length),1);
    await page.evaluate(()=>window.failApply=false);
  });
  await test('thin-footer copy uses reviewed text; denied clipboard selects it without applying',async()=>{
    const text='Reviewed English camera instruction.\n  Preserve spacing.  ';
    await page.locator('.mmc-tech-preview').fill(text);
    await page.locator('.mmc-tech-copy').click();
    assert.equal((await page.evaluate(()=>navigator.clipboard.readText())).replace(/\r\n/g,'\n'),text);
    await page.evaluate(()=>{window.oldClipboardWrite=navigator.clipboard.writeText;navigator.clipboard.writeText=async()=>{throw new Error('Denied fixture');};});
    await page.locator('.mmc-tech-copy').click();
    await page.getByText('Clipboard unavailable. The prompt is selected; use your copy shortcut.').waitFor();
    assert.deepEqual(await page.locator('.mmc-tech-preview').evaluate(e=>[e.selectionStart,e.selectionEnd]),[0,text.length]);
    assert.equal(await page.evaluate(()=>applied.length),1);
    await page.evaluate(()=>navigator.clipboard.writeText=oldClipboardWrite);
  });
  await test('all detail previews autoplay silently without controls and pointer movement cannot stop them',async()=>{
    await page.waitForFunction(()=>[...document.querySelectorAll('.mmc-tech-inspector video')].every(v=>v.readyState>=2&&!v.paused));
    assert.equal(await page.locator('.mmc-tech-hero video').evaluate(v=>v.paused),false);
    assert.equal(await page.locator('.mmc-tech-inspector video').evaluateAll(vs=>vs.every(v=>v.muted&&v.loop&&v.autoplay&&v.playsInline&&!v.controls)),true);
    assert.equal(await page.locator('.mmc-tech-inspector video').evaluateAll(vs=>vs.every(v=>v.playbackRate===1.2&&v.defaultPlaybackRate===1.2)),true);
    assert.equal(await page.locator('.mmc-tech-list').isVisible(),false);
    await page.locator('.mmc-tech-card').first().dispatchEvent('pointerenter');await page.waitForTimeout(230);
    assert.equal(await page.locator('.mmc-tech-card video').count(),0);
    await page.locator('.mmc-tech-detail-name').hover();
    assert.equal(await page.locator('.mmc-tech-inspector video').evaluateAll(vs=>vs.every(v=>!v.paused)),true);
    await page.locator('.mmc-tech-hero video').evaluate(v=>v.currentTime=0.6);
    await page.waitForTimeout(250);
    assert.equal(await page.locator('.mmc-tech-hero video').evaluate(v=>!v.paused&&v.currentTime<0.6),true);
  });
  await test('detail visibility lifecycle pauses all previews and resumes at1.2x without changing outside video speed',async()=>{
    await page.evaluate(()=>{
      window.outsideVideo=document.createElement('video');document.body.append(outsideVideo);
      Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));
    });
    assert.equal(await page.locator('.mmc-tech-inspector video').evaluateAll(vs=>vs.every(v=>v.paused)),true);
    await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'));});
    await page.waitForFunction(()=>[...document.querySelectorAll('.mmc-tech-inspector video')].every(v=>!v.paused&&v.playbackRate===1.2));
    assert.deepEqual(await page.evaluate(()=>[outsideVideo.playbackRate,outsideVideo.defaultPlaybackRate]),[1,1]);
    await page.evaluate(()=>{delete document.hidden;outsideVideo.remove();});
  });
  await test('hover creates one muted loop then releases decoder and source on leave',async()=>{
    await back();
    await page.getByRole('searchbox').hover();
    await page.locator('.mmc-tech-card').first().hover();
    await page.waitForFunction(()=>document.querySelector('.mmc-tech-card video')?.readyState>=2);
    assert.deepEqual(await page.locator('.mmc-tech-card video').evaluate(v=>{window.hoveredVideo=v;return [v.muted,v.loop,v.paused];}),[true,true,false]);
    assert.deepEqual(await page.locator('.mmc-tech-card video').evaluate(v=>[v.playbackRate,v.defaultPlaybackRate]),[1.2,1.2]);
    await page.getByRole('searchbox').hover();
    assert.deepEqual(await page.evaluate(()=>[hoveredVideo.paused,hoveredVideo.getAttribute('src'),hoveredVideo.isConnected]),[true,null,false]);
    await select(0);
  });
  await test('fullscreen Escape exits video first; close unloads all detail video sources',async()=>{
    await page.locator('.mmc-tech-hero video').evaluate(async v=>{window.oldVideos=[...document.querySelectorAll('.mmc-tech-inspector video')];await v.requestFullscreen();});
    await page.keyboard.press('Escape');
    await page.waitForFunction(()=>!document.fullscreenElement);
    assert.equal(await page.locator('.mmc-tech-modal').count(),1);
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('.mmc-tech-list').isVisible(),true);
    assert.equal(await page.evaluate(()=>oldVideos.every(v=>v.paused&&!v.hasAttribute('src'))),true);
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('.mmc-tech-modal').count(),0);
    assert.equal(await page.evaluate(()=>oldVideos.every(v=>v.paused&&!v.hasAttribute('src'))),true);
  });
  await test('reopen restores search, selection and bookmarks; explicit initial technique overrides hidden filters',async()=>{
    await open('{targets,target:targets[0]}');
    await page.locator('.mmc-tech-list').waitFor();
    assert.equal(await page.locator('.mmc-tech-inspector').isVisible(),false);
    assert.equal(await page.getByRole('searchbox').inputValue(),'fixture-alias');
    assert.equal(await page.locator('.mmc-tech-star').first().getAttribute('aria-pressed'),'true');
    await page.evaluate(()=>closeLibrary());
    await open('{targets,target:targets[0],initialTechnique:"category-1/item-1"}');
    await page.getByRole('heading',{name:'Technique 1',exact:true}).waitFor();
    assert.equal(await page.locator('.mmc-tech-search input').inputValue(),'');
    assert.equal(await page.locator('.mmc-tech-card').count(),33);
  });
  await test('blocked bookmark storage still retains stars across modal reopening for this session',async()=>{
    await page.evaluate(()=>{window.oldStorageSet=Storage.prototype.setItem;Storage.prototype.setItem=()=>{throw new Error('Blocked fixture');};});
    await page.locator('.mmc-tech-detail-bookmark').click();
    await page.getByText('Bookmarks are kept for this session; browser storage is unavailable.').waitFor();
    await page.evaluate(()=>closeLibrary());
    await open('{targets,target:targets[0],initialTechnique:"category-1/item-1"}');
    await page.getByRole('heading',{name:'Technique 1',exact:true}).waitFor();
    assert.equal(await page.locator('.mmc-tech-detail-bookmark').getAttribute('aria-pressed'),'true');
    await page.evaluate(()=>Storage.prototype.setItem=oldStorageSet);
  });
  await test('pagination appends a bounded next batch and keyboard focus continues at the first new card',async()=>{
    await back();
    await page.getByRole('button',{name:'All categories',exact:true}).click();
    assert.equal(await page.locator('.mmc-tech-card').count(),48);
    await page.getByRole('button',{name:'Show 48 more',exact:true}).click();
    assert.equal(await page.locator('.mmc-tech-card').count(),96);
    assert.equal(await page.evaluate(()=>document.activeElement.dataset.technique),'category-9/item-48');
  });
  await test('Back restores pagination, scroll, focus, filter state, target and target-specific edited draft',async()=>{
    const selectedCard=page.locator('[data-technique="category-5/item-70"]');
    await selectedCard.scrollIntoViewIfNeeded();
    const before=await page.locator('.mmc-tech-list').evaluate(e=>e.scrollTop);
    assert.ok(before>0);
    await select(70);
    await page.getByLabel('Apply to',{exact:true}).selectOption('segment-3');
    await page.locator('.mmc-tech-preview').fill('Draft for segment 3, technique 70.');
    await back();
    assert.equal(await page.locator('.mmc-tech-card').count(),96);
    assert.equal(await page.locator('.mmc-tech-list').evaluate(e=>e.scrollTop),before);
    assert.equal(await page.evaluate(()=>document.activeElement.dataset.technique),'category-5/item-70');
    assert.equal(await page.getByRole('button',{name:'All categories',exact:true}).getAttribute('aria-pressed'),'true');
    assert.equal(await page.getByRole('button',{name:'☆ Bookmarks',exact:true}).getAttribute('aria-pressed'),'false');
    await select(70);
    assert.equal(await page.getByLabel('Apply to',{exact:true}).inputValue(),'segment-3');
    assert.equal(await page.locator('.mmc-tech-preview').inputValue(),'Draft for segment 3, technique 70.');
    await page.getByLabel('Apply to',{exact:true}).selectOption('global');
    assert.notEqual(await page.locator('.mmc-tech-preview').inputValue(),'Draft for segment 3, technique 70.');
    await page.getByLabel('Apply to',{exact:true}).selectOption('segment-3');
    assert.equal(await page.locator('.mmc-tech-preview').inputValue(),'Draft for segment 3, technique 70.');
    await back();
  });
  await test('detail load error retries; selecting while an older fetch waits cannot show stale result',async()=>{
    detailFailures=1;
    await page.locator('[data-technique="category-2/item-2"]').click();
    await page.locator('.mmc-tech-detail-body').getByRole('button',{name:'Retry',exact:true}).click();
    await page.getByRole('heading',{name:'Technique 2',exact:true}).waitFor();
    holdDetail=true;
    await back();
    await page.locator('[data-technique="category-3/item-3"]').click();
    await back();
    await page.locator('[data-technique="category-4/item-4"]').click();
    await page.getByRole('heading',{name:'Technique 4',exact:true}).waitFor();
    holdDetail=false;
    assert.equal(await page.locator('.mmc-tech-detail-title h2').innerText(),'Technique 4');
  });
  await test('Back during a pending detail request stays in the list after the response arrives',async()=>{
    await back();holdDetail=true;
    await page.locator('[data-technique="category-5/item-5"]').click();
    await back();
    await page.waitForTimeout(450);holdDetail=false;
    assert.equal(await page.locator('.mmc-tech-list').isVisible(),true);
    assert.equal(await page.locator('.mmc-tech-inspector').isVisible(),false);
    assert.equal(await page.evaluate(()=>document.activeElement.dataset.technique),'category-5/item-5');
    await select(4);
  });
  await test('grouped cards preserve exact poster pairs and independent stills; internal history restores drafts and scroll',async()=>{
    assert.equal(await page.locator('[data-source-card="technique"]').count(),2);
    assert.equal(await page.locator('[data-card-title="Technique 1"] video').getAttribute('poster'),'https://technique.test/web/creator/techniques/media/compare.png');
    assert.equal(await page.locator('.mmc-tech-article img[src$="compare.png"]').count(),0);
    assert.equal(await page.locator('[data-card-title="Technique 2"] img[src$="still-only.png"]').count(),1);
    assert.equal(await page.locator('[data-source-card="film"] img[src$="film.png"]').count(),1);
    await page.getByLabel('Apply to',{exact:true}).selectOption('global');
    await page.getByRole('button',{name:'Original example',exact:true}).click();
    await page.locator('.mmc-tech-preview').fill('History draft four.');
    const internal=page.locator('[data-section="usage"] [data-technique-link]').first();
    await internal.scrollIntoViewIfNeeded();await internal.focus();
    const oldScroll=await page.locator('.mmc-tech-detail-body').evaluate(e=>e.scrollTop);
    const beforeApply=await page.evaluate(()=>applied.length);
    await page.locator('.mmc-tech-inspector video').evaluateAll(vs=>window.historyVideos=vs);
    await internal.click();
    await page.getByRole('heading',{name:'Technique 1',exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>historyVideos.every(v=>v.paused&&!v.hasAttribute('src'))),true);
    await page.locator('.mmc-tech-preview').fill('History draft one.');
    await page.locator('[data-card-title="Technique 2"] .mmc-tech-card-link').click();
    await page.getByRole('heading',{name:'Technique 2',exact:true}).waitFor();
    await page.locator('.mmc-tech-previous').click();
    await page.getByRole('heading',{name:'Technique 1',exact:true}).waitFor();
    assert.equal(await page.locator('.mmc-tech-preview').inputValue(),'History draft one.');
    await page.locator('.mmc-tech-previous').click();
    await page.getByRole('heading',{name:'Technique 4',exact:true}).waitFor();
    assert.equal(await page.locator('.mmc-tech-preview').inputValue(),'History draft four.');
    assert.equal(await page.getByLabel('Apply to',{exact:true}).inputValue(),'global');
    assert.ok(Math.abs(await page.locator('.mmc-tech-detail-body').evaluate(e=>e.scrollTop)-oldScroll)<2);
    assert.equal(await page.evaluate(()=>document.activeElement.dataset.navKey),'usage:0:0');
    assert.equal(await page.evaluate(()=>applied.length),beforeApply);
    assert.equal(page.url(),'https://technique.test/');
    await back();assert.equal(await page.evaluate(()=>document.activeElement.dataset.technique),'category-4/item-4');
    await select(4);
  });
  await test('nested overlay owns Escape; focus guards keep keyboard within the catalogue',async()=>{
    await page.evaluate(()=>{const node=el('div',{class:'mmc-overlay',id:'nested'});window.unmountNested=mountOverlay(node,()=>unmountNested());});
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#nested').count(),0);
    assert.equal(await page.locator('.mmc-tech-modal').count(),1);
    await page.locator('.mmc-tech-focus-guard').last().focus();
    assert.equal(await page.evaluate(()=>document.activeElement.closest('.mmc-tech-modal')!==null),true);
  });
  await test('narrow viewport keeps categories and application controls accessible without horizontal overflow',async()=>{
    await page.setViewportSize({width:390,height:844});
    await back();
    assert.equal(await page.locator('.mmc-tech-modal').evaluate(e=>e.scrollWidth<=e.clientWidth+1),true);
    assert.equal(await page.locator('.mmc-tech-categories').evaluate(e=>e.scrollWidth<=e.clientWidth+1),true);
    await select(4);
    await page.getByRole('button',{name:'Add to prompt',exact:true}).scrollIntoViewIfNeeded();
    assert.equal(await page.getByRole('button',{name:'Add to prompt',exact:true}).isVisible(),true);
  });
  await test('1.6 text scale at 768×900 retains a reachable apply footer and no horizontal overflow',async()=>{
    await page.setViewportSize({width:768,height:900});
    await page.evaluate(()=>document.documentElement.style.setProperty('--mmc-type','1.6'));
    assert.equal(await page.locator('.mmc-tech-modal').evaluate(e=>e.scrollWidth<=e.clientWidth+1),true);
    assert.equal(await page.locator('.mmc-tech-categories').evaluate(e=>e.scrollWidth<=e.clientWidth+1),true);
    await page.locator('.mmc-tech-apply').scrollIntoViewIfNeeded();
    const contained=await page.locator('.mmc-tech-apply').evaluate(button=>{
      const a=button.getBoundingClientRect(),b=button.closest('.mmc-tech-application-footer').getBoundingClientRect();
      return a.x>=b.x-1&&a.right<=b.right+1&&a.y>=b.y-1&&a.bottom<=b.bottom+1&&a.bottom<=innerHeight;
    });
    assert.equal(contained,true);
    await page.evaluate(()=>document.documentElement.style.removeProperty('--mmc-type'));
  });
  await test('browse-only opening does not expose apply controls; media URLs remain local',async()=>{
    await page.evaluate(()=>closeLibrary());
    await open('{initialTechnique:"category-0/item-0"}');
    await page.getByRole('heading',{name:'Technique 0',exact:true}).waitFor();
    assert.equal(await page.locator('.mmc-tech-apply').isVisible(),false);
    assert.equal(await page.locator('.mmc-tech-target').isVisible(),false);
    assert.equal(await page.locator('.mmc-tech-copy').isVisible(),true);
    await page.getByRole('button',{name:'Original example',exact:true}).click();
    await page.locator('.mmc-tech-copy').click();
    assert.equal((await page.evaluate(()=>navigator.clipboard.readText())).replace(/\r\n/g,'\n'),original);
    assert.equal(urls.every(url=>new URL(url).origin==='https://technique.test'),true);
    assert.equal(errors.length,0,errors.join('\n'));
  });
  await test('blocked autoplay exposes one manual start without retry loops and resumes safely at1.2x',async()=>{
    await page.evaluate(()=>{
      closeLibrary();window.blockPlayback=true;window.playAttempts=0;window.originalPlay=HTMLMediaElement.prototype.play;
      window.pauseBlocked=e=>{if(blockPlayback&&e.target.tagName==='VIDEO')e.target.pause();};document.addEventListener('play',pauseBlocked,true);
      HTMLMediaElement.prototype.play=function(){playAttempts++;return blockPlayback?Promise.reject(new DOMException('Policy fixture','NotAllowedError')):originalPlay.call(this);};
    });
    await open('{target:targets[0],targets,initialTechnique:"category-0/item-0"}');
    await page.waitForFunction(()=>document.querySelectorAll('.mmc-tech-play:not([hidden])').length===3);
    const attempts=await page.evaluate(()=>playAttempts);
    await page.evaluate(()=>document.dispatchEvent(new Event('visibilitychange')));
    await page.waitForTimeout(150);
    assert.equal(await page.evaluate(()=>playAttempts),attempts);
    await page.evaluate(()=>window.blockPlayback=false);
    await page.locator('.mmc-tech-hero .mmc-tech-play').click();
    await page.waitForFunction(()=>!document.querySelector('.mmc-tech-hero video').paused);
    assert.deepEqual(await page.locator('.mmc-tech-hero video').evaluate(v=>[v.playbackRate,v.defaultPlaybackRate,v.muted,v.controls]),[1.2,1.2,true,false]);
    await page.evaluate(()=>{closeLibrary();HTMLMediaElement.prototype.play=originalPlay;document.removeEventListener('play',pauseBlocked,true);});
  });
  await test('hidden-visible race resumes pending AbortError previews once rather than treating it as policy denial',async()=>{
    await page.evaluate(()=>{
      window.originalPlay=HTMLMediaElement.prototype.play;window.firstPlays=new WeakSet();window.pendingRejects=[];window.raceAttempts=0;
      HTMLMediaElement.prototype.play=function(){raceAttempts++;if(!firstPlays.has(this)){firstPlays.add(this);return new Promise((resolve,reject)=>pendingRejects.push(reject));}return originalPlay.call(this);};
    });
    await open('{target:targets[0],targets,initialTechnique:"category-0/item-0"}');
    await page.waitForFunction(()=>pendingRejects.length===3);
    await page.evaluate(()=>{
      Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));
      Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'));
      pendingRejects.forEach(reject=>reject(new DOMException('Interrupted by pause','AbortError')));
    });
    await page.waitForFunction(()=>[...document.querySelectorAll('.mmc-tech-inspector video')].every(v=>!v.paused&&v.playbackRate===1.2));
    assert.equal(await page.locator('.mmc-tech-play:not([hidden])').count(),0);
    await page.waitForTimeout(100);
    assert.equal(await page.evaluate(()=>raceAttempts),6);
    await page.evaluate(()=>{closeLibrary();HTMLMediaElement.prototype.play=originalPlay;delete document.hidden;});
  });
  await test('live target provider refreshes labels/additions, blocks clips/deletions and surfaces target warnings',async()=>{
    await page.evaluate(()=>{
      window.clipBlocked=false;window.liveTargetValid=true;
      window.dynamicTarget={id:'dynamic',label:'Segment 7',kind:'segment',subjects:[],duration:4,
        isValid:()=>liveTargetValid,blockedReason:()=>clipBlocked?'This segment is a supplied clip and has no generated prompt.':null,
        warning:()=>clipBlocked?'This segment is a supplied clip and has no generated prompt.':null,
        apply:async value=>{applied.push({target:'dynamic',...value});return {ok:true,warnings:['Fixture reference remained muted.']};}};
      window.liveTargets=[targets[0],dynamicTarget];
    });
    await open('{target:dynamicTarget,getTargets:()=>liveTargets,initialTechnique:"category-0/item-0"}');
    await page.getByRole('heading',{name:'Technique 0',exact:true}).waitFor();
    assert.equal(await page.getByLabel('Apply to',{exact:true}).inputValue(),'dynamic');
    await page.evaluate(()=>{dynamicTarget.label='Segment 12';liveTargets.push(targets[1]);});
    await page.getByLabel('Apply to',{exact:true}).focus();
    assert.deepEqual(await page.getByLabel('Apply to',{exact:true}).locator('option').allTextContents(),['Global prompt','Segment 12','Segment 3']);
    await page.locator('.mmc-tech-apply').click();
    await page.getByText(/Fixture reference remained muted/).waitFor();
    await page.evaluate(()=>window.clipBlocked=true);
    await page.getByLabel('Apply to',{exact:true}).selectOption('global');
    await page.getByLabel('Apply to',{exact:true}).selectOption('dynamic');
    assert.equal(await page.locator('.mmc-tech-apply').isDisabled(),true);
    assert.match(await page.locator('.mmc-tech-warnings').innerText(),/supplied clip/);
    await page.evaluate(()=>{window.clipBlocked=false;});
    await page.getByLabel('Apply to',{exact:true}).selectOption('global');
    await page.getByLabel('Apply to',{exact:true}).selectOption('dynamic');
    await page.evaluate(()=>{window.liveTargetValid=false;window.liveTargets=[targets[0]];});
    const before=await page.evaluate(()=>applied.length);
    await page.locator('.mmc-tech-apply').click();
    await page.getByText('This prompt target has changed. Reopen the technique library.').waitFor();
    assert.equal(await page.evaluate(()=>applied.length),before);
    assert.equal(await page.getByLabel('Apply to',{exact:true}).inputValue(),'dynamic');
  });
  for(const locale of ['ko','ja','zh'])await test(`${locale} explanations localize while titles, guidance, examples and approved text stay English`,async()=>{
    await page.evaluate(locale=>{closeLibrary();window.app={extensionManager:{setting:{get:()=>locale}}};
      localStorage.setItem('continuity-technique-view-v1',JSON.stringify({originalExplanations:true}));},locale);
    await open('{target:targets[0],targets,initialTechnique:"category-0/item-0"}');
    await page.getByRole('heading',{name:'Technique 0',exact:true}).waitFor();
    assert.equal(await page.locator('[data-technique="category-0/item-0"] > strong').innerText(),'Technique 0');
    assert.equal(await page.locator('[data-technique="category-0/item-0"] .mmc-tech-description').innerText(),localText[locale].description);
    assert.match(await page.locator('.mmc-tech-article').innerText(),new RegExp(localText[locale].usage.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));
    assert.equal(await page.locator('[data-translation]').getAttribute('data-translation'),'partial');
    assert.equal(await page.locator('.mmc-tech-explanation-bar').count(),0);
    assert.doesNotMatch(await page.locator('.mmc-tech-article').innerText(),/DO NOT SHOW TRANSLATED/);
    assert.equal(await page.locator('.mmc-tech-original').count(),0);
    assert.equal(await page.locator('.mmc-tech-preview').inputValue(),'A camera approaches [Subject] for [Duration] seconds.');
    await page.locator('.mmc-tech-preview').fill('My English camera instruction.');
    await back();
    await select(0);
    assert.equal(await page.locator('[data-translation]').getAttribute('data-translation'),'partial');
    assert.equal(await page.locator('.mmc-tech-preview').inputValue(),'My English camera instruction.');
    await page.locator('.mmc-tech-apply').click();
    assert.deepEqual(await page.evaluate(()=>({title:applied.at(-1).item.title,description:applied.at(-1).item.description,text:applied.at(-1).text})),
      {title:'Technique 0',description:items[0].description,text:'My English camera instruction.'});
    await back();
    await page.locator('.mmc-tech-search input').fill(localText[locale].description);
    assert.equal(await page.locator('.mmc-tech-card').count(),1);
    await page.locator('.mmc-tech-search input').fill('');
    await page.locator('.mmc-tech-categories button').first().click();
    assert.equal(await page.locator('[data-technique="category-1/item-1"] .mmc-tech-language').count(),1);
    await select(2);
    assert.equal(await page.locator('[data-translation]').getAttribute('data-translation'),'missing');
    assert.match(await page.locator('.mmc-tech-article').innerText(),/Original usage paragraph/);
  });
  await test('Korean single-scroll detail and Refine consent fit at 1.6 text scale and 768×900',async()=>{
    await page.evaluate(()=>{closeLibrary();window.app={extensionManager:{setting:{get:()=> 'ko'}}};window.refined=true;document.documentElement.style.setProperty('--mmc-type','1.6');});
    await page.setViewportSize({width:768,height:900});
    await open('{target:targets[1],targets,initialTechnique:"category-0/item-0"}');
    await page.getByRole('heading',{name:'Technique 0',exact:true}).waitFor();
    assert.equal(await page.locator('.mmc-tech-modal').evaluate(e=>e.scrollWidth<=e.clientWidth+1),true);
    assert.equal(await page.locator('.mmc-tech-refine-ack').isVisible(),true);
    assert.equal(await page.locator('.mmc-tech-modal .mmc-close').evaluate(e=>{
      const a=e.getBoundingClientRect(),b=e.parentElement.getBoundingClientRect();return b.right-a.right<30;
    }),true);
    await page.locator('.mmc-tech-refine-ack').scrollIntoViewIfNeeded();
    assert.equal(await page.locator('.mmc-tech-refine-ack').evaluate(e=>{
      const a=e.getBoundingClientRect(),b=e.closest('.mmc-tech-detail-body').getBoundingClientRect();
      return a.top>=b.top-1&&a.bottom<=b.bottom+1;
    }),true);
    assert.equal(await page.locator('.mmc-tech-inspector').evaluate(e=>[...e.querySelectorAll('*')].filter(n=>n.tagName!=='TEXTAREA'&&n.getClientRects().length&&/(auto|scroll)/.test(getComputedStyle(n).overflowY)&&n.scrollHeight>n.clientHeight+1).length),1);
    await page.locator('.mmc-tech-apply').scrollIntoViewIfNeeded();
    assert.equal(await page.locator('.mmc-tech-apply').evaluate(button=>{
      const a=button.getBoundingClientRect(),b=button.closest('.mmc-tech-application-footer').getBoundingClientRect();
      return a.x>=b.x-1&&a.right<=b.right+1&&a.y>=b.y-1&&a.bottom<=b.bottom+1&&a.bottom<=innerHeight;
    }),true);
    await page.evaluate(()=>document.documentElement.style.removeProperty('--mmc-type'));
  });
  await page.evaluate(()=>{closeLibrary();window.app=null;});
  await test('missing supplemental metadata falls back safely without guessed grouping or outgoing links',async()=>{
    missingStructure=true;
    await page.goto('https://technique.test/');await page.waitForFunction(()=>window.ready);
    await open('{target:targets[0],targets,initialTechnique:"category-0/item-0"}');
    await page.getByRole('heading',{name:'Technique 0',exact:true}).waitFor();
    assert.match(await page.locator('.mmc-tech-article').innerText(),/Original usage paragraph/);
    assert.equal(await page.locator('.mmc-tech-article a[href]').count(),0);
    assert.equal(await page.locator('[data-source-card]').count(),0);
    assert.equal(await page.locator('.mmc-tech-article img[src$="compare.png"]').count(),1);
    assert.equal(await page.locator('.mmc-tech-preview').inputValue(),'A camera approaches [Subject] for [Duration] seconds.');
    await page.locator('[data-section="usage"] [data-technique-link]').first().click();
    await page.getByRole('heading',{name:'Technique 1',exact:true}).waitFor();
    assert.equal(page.url(),'https://technique.test/');
    missingStructure=false;
  });
  const actualPath=path.join(root,'web/creator/techniques/catalog.json');
  if(fs.existsSync(actualPath)) {
    actualCatalogue=true;
    await page.evaluate(()=>closeLibrary());
    await page.setViewportSize({width:1400,height:950});
    await page.goto('https://technique.test/');
    await page.waitForFunction(()=>window.ready);
    const realCatalog=JSON.parse(fs.readFileSync(actualPath,'utf8'));
    await test('actual extracted catalogue exposes all 424 techniques and all 13 categories',async()=>{
      await open('{target:targets[1],targets,initialTechnique:"camera-movement/dolly-in"}');
      await page.getByRole('heading',{name:'Dolly In',exact:true}).waitFor();
      assert.equal(await page.locator('.mmc-tech-categories button').count(),15);
      await back();
      await page.getByRole('button',{name:'All categories',exact:true}).click();
      assert.equal(await page.locator('.mmc-tech-count').innerText(),'424 / 424 techniques');
      for(const category of realCatalog.categories) {
        await page.getByRole('button',{name:`${category.title} · ${category.count}`,exact:true}).click();
        assert.equal(await page.locator('.mmc-tech-count').innerText(),`${category.count} / 424 techniques`);
      }
    });
    await test('actual source Dolly In example is unaltered and every extracted article heading is present',async()=>{
      await page.evaluate(()=>closeLibrary());
      await open('{target:targets[1],targets,initialTechnique:"camera-movement/dolly-in"}');
      await page.getByRole('heading',{name:'Dolly In',exact:true}).waitFor();
      const dolly=JSON.parse(source('techniques/details/camera-movement/dolly-in.json'));
      await page.getByRole('button',{name:'Original example',exact:true}).click();
      assert.equal(await page.getByLabel('Editable insertion preview').inputValue(),dolly.prompt.example);
      for(const section of dolly.sections) if(section.title) assert.equal(await page.locator('.mmc-tech-source-section h3').filter({hasText:section.title}).count(),1);
      assert.match(await page.locator('.mmc-tech-article').innerText(),/Also known as/);
      assert.equal(await page.getByRole('heading',{name:'Related source links',exact:true}).count(),0);
      assert.equal(await page.locator('.mmc-tech-article a[href]').count(),0);
    });
    await test('actual still-image technique uses image hero and no invented preview video',async()=>{
      await page.evaluate(()=>closeLibrary());
      await open('{target:targets[1],targets,initialTechnique:"framing/close-up"}');
      await page.getByRole('heading',{name:'Close-Up (CU)',exact:true}).waitFor();
      assert.equal(await page.locator('.mmc-tech-hero img').count(),1);
      assert.equal(await page.locator('.mmc-tech-hero video').count(),0);
      assert.equal(errors.length,0,errors.join('\n'));
    });
    await test('actual Orbit comparison cards play at1.2x, retain film/strip media and navigate inside the library',async()=>{
      await page.evaluate(()=>closeLibrary());
      await open('{target:targets[0],targets,initialTechnique:"camera-movement/orbit-360"}');
      await page.getByRole('heading',{name:'360-Degree Orbit',exact:true}).waitFor();
      const orbit=JSON.parse(source('techniques/details/camera-movement/orbit-360.json'));
      const layout=JSON.parse(source('techniques/structure.json')).items[orbit.id];
      assert.equal(await page.locator('[data-section="vs"] [data-source-card="technique"]').count(),3);
      for(const card of layout.sections.vs.cards) {
        assert.equal(await page.locator(`[data-card-title="${card.title}"] video`).getAttribute('poster'),new URL(card.media.poster,'https://technique.test/web/creator/techniques/').href);
        assert.equal(await page.locator(`.mmc-tech-article img[src$="${card.media.poster.split('/').pop()}"]`).count(),0);
      }
      assert.equal(await page.locator('[data-source-card="film"] img').count(),2);
      assert.equal(await page.locator(`img[src$="${layout.strip.path.split('/').pop()}"]`).count(),1);
      for(const entry of layout.excludedMedia ?? [])assert.equal(await page.locator(`.mmc-tech-article img[src$="${entry.path.split('/').pop()}"]`).count(),0);
      await page.waitForFunction(()=>[...document.querySelectorAll('.mmc-tech-inspector video')].every(v=>v.readyState>=2&&!v.paused));
      assert.equal(await page.locator('.mmc-tech-inspector video').evaluateAll(vs=>vs.every(v=>v.muted&&v.autoplay&&v.loop&&!v.controls&&v.playbackRate===1.2&&v.defaultPlaybackRate===1.2)),true);
      const before=await page.locator('[data-section="vs"] video').evaluateAll(vs=>vs.map(v=>v.currentTime));
      await page.waitForTimeout(350);
      const after=await page.locator('[data-section="vs"] video').evaluateAll(vs=>vs.map(v=>v.currentTime));
      assert.equal(after.every((time,index)=>Math.abs(time-before[index])>0.1),true);
      await page.locator('[data-card-title="Arc Right"] .mmc-tech-card-link').click();
      await page.getByRole('heading',{name:'Arc Right',exact:true}).waitFor();
      assert.equal(page.url(),'https://technique.test/');
      await page.locator('.mmc-tech-previous').click();
      await page.getByRole('heading',{name:'360-Degree Orbit',exact:true}).waitFor();
      assert.equal(await page.locator('.mmc-tech-article a[href]').count(),0);
      assert.equal(await page.locator('.mmc-tech-original').count(),0);
      if(process.env.TECHNIQUE_SCREENSHOT){
        await page.evaluate(()=>document.querySelector('#outside').hidden=true);
        await page.locator('[data-section="vs"]').evaluate(e=>e.scrollIntoView({block:'start'}));
        await page.screenshot({path:process.env.TECHNIQUE_SCREENSHOT.replace(/\.png$/,'-orbit-comparison.png')});
        await page.locator('[data-section="examples-film"]').scrollIntoViewIfNeeded();
        await page.screenshot({path:process.env.TECHNIQUE_SCREENSHOT.replace(/\.png$/,'-orbit-film.png')});
        await page.evaluate(()=>{closeLibrary();window.app={extensionManager:{setting:{get:()=> 'ko'}}};});
        await open('{target:targets[0],targets,initialTechnique:"camera-movement/orbit-360"}');
        await page.getByRole('heading',{name:'360-Degree Orbit',exact:true}).waitFor();
        await page.locator('[data-section="vs"]').evaluate(e=>e.scrollIntoView({block:'start'}));
        await page.screenshot({path:process.env.TECHNIQUE_SCREENSHOT.replace(/\.png$/,'-orbit-comparison-ko.png')});
        await page.setViewportSize({width:390,height:844});
        await page.locator('[data-card-title="Arc Right"]').scrollIntoViewIfNeeded();
        assert.equal(await page.locator('.mmc-tech-modal').evaluate(e=>e.scrollWidth<=e.clientWidth+1),true);
        await page.screenshot({path:process.env.TECHNIQUE_SCREENSHOT.replace(/\.png$/,'-orbit-comparison-narrow.png')});
        await page.setViewportSize({width:1400,height:950});
        await page.evaluate(()=>{closeLibrary();window.app=null;});
      }
    });
    for(const locale of ['ko','ja','zh']) {
      const overlayCatalogPath=path.join(root,`web/creator/techniques/translations/${locale}/catalog.json`);
      if(!fs.existsSync(overlayCatalogPath))continue;
      const overlayCatalog=JSON.parse(fs.readFileSync(overlayCatalogPath,'utf8'));
      const localizedIds=Object.keys(overlayCatalog.items ?? {});
      if(!localizedIds.length)continue;
      await test(`actual ${locale} overlays load all available proof entries without translating names or prompt payloads`,async()=>{
        for(const id of localizedIds) {
          const item=realCatalog.items.find(item=>item.id===id);
          const originalDetail=JSON.parse(source(`techniques/${item.detail}`));
          const translated=JSON.parse(source(`techniques/translations/${locale}/${item.detail}`));
          await page.evaluate(locale=>{closeLibrary();window.app={extensionManager:{setting:{get:()=>locale}}};},locale);
          await open(`{target:targets[0],targets,initialTechnique:${JSON.stringify(id)}}`);
          await page.getByRole('heading',{name:item.title,exact:true}).waitFor();
          assert.equal(await page.locator('[data-translation]').getAttribute('data-translation'),'complete');
          assert.equal(await page.locator(`.mmc-tech-article > p[lang="${locale}"]`).innerText(),translated.description);
          assert.equal(await page.locator('.mmc-tech-preview').inputValue(),originalDetail.prompt.guidance.filter(text=>typeof text==='string'&&text.trim()).join('\n\n'));
          if(originalDetail.prompt.example){
            await page.locator('.mmc-tech-modes button').nth(1).click();
            assert.equal(await page.locator('.mmc-tech-preview').inputValue(),originalDetail.prompt.example);
          }
          assert.equal(await page.locator('.mmc-tech-explanation-bar').count(),0);
        }
        const missing=realCatalog.items.find(item=>!overlayCatalog.items[item.id]);
        if(missing) {
          await page.evaluate(()=>closeLibrary());
          await open(`{target:targets[0],targets,initialTechnique:${JSON.stringify(missing.id)}}`);
          await page.getByRole('heading',{name:missing.title,exact:true}).waitFor();
          assert.equal(await page.locator('[data-translation]').getAttribute('data-translation'),'missing');
          assert.equal(await page.locator(`[data-technique="${missing.id}"] .mmc-tech-language`).count(),1);
        }
        console.log(`  Actual ${locale}: ${localizedIds.length} translated detail files; ${realCatalog.items.length-localizedIds.length} explicitly fall back to English.`);
      });
    }
    await page.evaluate(()=>{closeLibrary();window.app=null;});
    // A real-source screenshot, rather than a fabricated catalogue, is useful
    // evidence for native layout review. Never implies a GPU render occurred.
    if(process.env.TECHNIQUE_SCREENSHOT){
      await page.evaluate(()=>closeLibrary());
      await open('{target:targets[1],targets,initialTechnique:"camera-movement/dolly-in"}');
      await page.getByRole('heading',{name:'Dolly In',exact:true}).waitFor();
      await page.getByRole('button',{name:'Technique only',exact:true}).click();
      await page.waitForTimeout(300);
    }
  }
  if(process.env.TECHNIQUE_SCREENSHOT){
    await page.setViewportSize({width:1400,height:950});
    await page.evaluate(()=>{window.refined=false;document.querySelector('#outside').hidden=true;});
    await page.evaluate(()=>closeLibrary());
    await open('{target:targets[1],targets,initialTechnique:"camera-movement/dolly-in"}');
    await page.getByRole('heading',{name:'Dolly In',exact:true}).waitFor();
    await page.locator('.mmc-tech-hero video').evaluate(async v=>{await v.play();v.pause();});
    await page.screenshot({path:process.env.TECHNIQUE_SCREENSHOT});
    await page.locator('.mmc-tech-application').scrollIntoViewIfNeeded();
    await page.screenshot({path:process.env.TECHNIQUE_SCREENSHOT.replace(/\.png$/,'-prompt.png')});
    await back();
    await page.getByRole('button',{name:'All categories',exact:true}).click();
    await page.screenshot({path:process.env.TECHNIQUE_SCREENSHOT.replace(/\.png$/,'-grid.png')});
    await page.evaluate(()=>{window.app={extensionManager:{setting:{get:()=> 'ko'}}};closeLibrary();});
    await open('{target:targets[1],targets,initialTechnique:"camera-movement/dolly-in"}');
    await page.getByRole('heading',{name:'Dolly In',exact:true}).waitFor();
    await page.screenshot({path:process.env.TECHNIQUE_SCREENSHOT.replace(/\.png$/,'-ko.png')});
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:process.env.TECHNIQUE_SCREENSHOT.replace(/\.png$/,'-narrow.png')});
    await page.setViewportSize({width:1400,height:950});
    await back();
    await page.locator('.mmc-tech-categories button').first().click();
    await page.screenshot({path:process.env.TECHNIQUE_SCREENSHOT.replace(/\.png$/,'-grid-ko.png')});
  }
  await page.evaluate(()=>closeLibrary());
  console.log(`\n${results.length} browser checks passed. All requests fixture-fulfilled; no ComfyUI/GPU render.`);
  await browser.close();
})().catch(async error=>{console.error(error);await browser?.close();process.exitCode=1;});

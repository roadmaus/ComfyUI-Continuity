// Isolated browser checks: actual helper, methods and CSS, with model/API seams
// stubbed. This does not import ComfyUI or perform any GPU generation.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '../../web/creator');
const read = p => fs.readFileSync(path.join(root, p), 'utf8');
const source = read('timeline.js');
const castSource = read('cast.js');
// Timeline's disclosure header also hosts the Technique entry point now.
// Extract its real button factory; library behavior has its own suite.
const techniqueButton = read('technique-controls.js').match(/export function techniqueButton\([^]*?^\}/m)[0].replace(/^export /, '');
const method = (name, code = source) => {
  const found = code.match(new RegExp(`^  (?:async )?${name}\\([^]*?^  \\}`, 'm'));
  assert.ok(found, name); return found[0];
};
const helper = read('disclosure.js').replace(/^import .*;\r?\n/gm, '').replace(/^export /gm, '');
const domSource = read('dom.js');
const dom = domSource.match(/export function el\([^]*?^\}/m)[0].replace(/^export /, '');
const popovers = [
  domSource.match(/const popoverOwners[^]*?(?=\/\*\* Close-on-outside-click)/)[0],
  ...['floatAbove','dismissable','placeNear'].map(name => domSource.match(new RegExp(`export function ${name}\\([^]*?^\\}`, 'm'))[0].replace(/^export /,'')),
].join('\n').replace(/^export /gm,'');
const css = ['base', 'editor', 'timeline'].map(name => read(`styles/${name}.js`).match(/export const css = `([^]*)`;\s*$/)[1]).join('\n');
const code = `
${dom}
${popovers}
${helper}
const t = (text, vars = {}) => text.replace(/\\{([^}]+)\\}/g, (_, key) => vars[key] ?? key);
const icon = () => el('span', { text: '·' });
${techniqueButton}
const seamGroup = children => children.length ? el('div', {class:'mmc-tl-seam-group'}, children) : null;
const blendSeconds = (frames, rules) => (frames / rules.fps).toFixed(1);
const blendSetsTail = (segment, piece) => S.continuesAudio(segment) && S.feather(segment, piece) > 1;
const passNumbers = () => '1';
const rulesFor = () => ({fps:24});
const SoundLane = class { constructor() { this.host = el('div'); } };
const mountOverlay = (node) => { document.body.append(node); return () => node.remove(); };
const S = {
  takesReferences: state => state.takesRefs !== false,
  familyOf: () => ({label:'Fixture'}),
  pieceFamily: () => 'fixture',
  continues: item => !!item.continue,
  continuesAudio: item => !!item.continue_audio,
  isClip: item => item?.kind === 'clip',
  blockedReason: (item, key) => item['blocked_' + key] || null,
  continueSource: (item,index) => item.continue_from ?? index,
  feather: item => item.feather ?? 1,
  featherPin: () => false,
  canDo: state => state.storyboard !== false,
  storyboardSheet: () => [],
  clipSeamBlocked: (state,index,key) => state.segments[index]['blocked_' + key] || null,
  maxClipFeather: () => 24,
  poolCitedGlobally: (state, asset) => (state.prompt || '').includes('@' + asset.handle),
  refCaps: () => ({files:4}),
};
let pickerAnswer = null;
const openPicker = async () => pickerAnswer;
class Subject {
 ${['mount','textBox','setGlobalPrompt','renderPool','openCastMember','renderClipJoin','renderJoin','citeName','citeInGlobal','addPoolAssets'].map(name=>method(name)).join('\n')}
 globalPromptBox() {
   const root = el('div', {contenteditable:'true',class:'mmc-prompt'});
   return {root, frame:el('div',{class:'mmc-tl-prompt-frame'},[root]),
     setValue(value) { root.textContent=value; }, closeMenu() { window.menuClosed++; }};
 }
 render() { this.renderPool(); }
 renderCast() {}
 renderBar() {}
 openTechniques() { window.techniqueOpens++; }
 commit() { this.commits++; this.renderPool(); }
 poolChip(asset) { return el('button',{text:asset.handle}); }
 poolPlate() { return null; }
 poolEntry(pick) { return {handle:'ref-'+(this.timeline.assets.length+1),kind:pick.kind,filename:pick.path}; }
 earlierPasses() { return this.passes || []; }
 close() { this.unmount(); }
 pickFeather(anchor) { window.lastPick={kind:'blend',anchor}; }
 pickClipFeather(anchor) { window.lastPick={kind:'clipBlend',anchor}; }
 pickContinueFrom(anchor) { window.lastPick={kind:'source',anchor}; }
 pickStoryboard(anchor) { window.lastPick={kind:'board',anchor}; }
 mergeAt() { window.lastPick={kind:'merge'}; }
}
window.menuClosed=0;
window.techniqueOpens=0;
window.subject=Object.assign(new Subject(),{timeline:{prompt:'Standing scene',soundscape:'Room tone',music:'N/A',assets:[],subjects:[],segments:[{},{}]},commits:0});
window.createDisclosure=createDisclosure;
window.setPickerAnswer = value => { pickerAnswer=value; };
window.Subject=Subject;
window.makePopover=(anchor, name) => {
  const node=el('div',{class:'mmc-pop'},[el('button',{text:name})]);document.body.append(node);
  placeNear(node,anchor); const close=dismissable(node,()=>{window.popoverClosed.push(name);});return {node,close};
};
window.popoverClosed=[];
const WearsPanel = class {};
class FixtureCast {
 ${['constructor','openMember','render'].map(name=>method(name,castSource)).join('\n')}
 ${castSource.match(/^  isExpanded\(.*$/m)[0]}
 ${castSource.match(/^  reveal\(.*$/m)[0]}
 typing() { return false; }
 problem(subject) { return subject.problem || ''; }
 card(subject) { return el('div',{text:subject.handle+(this.opened===subject?' open':' shut')}); }
}
window.FixtureCast=FixtureCast;
subject.mount();
`;
const results = [];
new (require('node:vm').Script)(code, { filename: 'timeline-fixture.js' });
let browser, requests = 0;
async function check(name, fn) { await fn(); results.push({name,passed:true}); }
(async () => {
  browser = await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
  const page = await browser.newPage({viewport:{width:1100,height:850}});
  await page.route('**/*', route => { requests++; return route.abort(); });
  await page.setContent(`<html><head><style>${css}</style></head><body style="--mmc-type:1;--mmc-surface:#242424;--mmc-surface-2:#333;--mmc-line:#555;--mmc-line-2:#777;--mmc-text:#eee;--mmc-dim:#bbb;--mmc-accent:#acf;background:#111;font-family:Arial"></body></html>`);
  await page.evaluate(`(() => { ${code} })()`);
  await check('Four Timeline shells open by default and global label retains prompt value', async () => {
    assert.deepEqual(await page.evaluate(() => ({states:[subject.promptSection,subject.soundscapeSection,subject.musicSection,subject.poolSection].map(s=>s.isOpen()),label:subject.promptSection.toggle.textContent,prompt:subject.timeline.prompt,aria:subject.soundscapeBox.getAttribute('aria-labelledby')===subject.soundscapeSection.titleId})),{states:[true,true,true,true],label:'⌄global_prompt',prompt:'Standing scene',aria:true});
  });
  await check('Independent folding retains textarea DOM, values and serialized state', async () => {
    assert.equal(await page.evaluate(() => {
      const before=JSON.stringify(subject.timeline), input=subject.soundscapeBox;
      subject.soundscapeSection.toggle.click();
      const good=subject.musicSection.isOpen()&&!subject.soundscapeSection.isOpen();
      subject.soundscapeSection.toggle.click();
      return good&&input===subject.soundscapeBox&&input.value==='Room tone'&&before===JSON.stringify(subject.timeline)&&subject.commits===0;
    }),true);
  });
  await check('Native Enter and Space toggle exactly once; prompt menu closes on fold', async () => {
    const button=page.locator('.mmc-tl-section-toggle').first();
    await button.focus(); await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(()=>subject.promptSection.isOpen()),false);
    await page.keyboard.press('Space');
    assert.equal(await page.evaluate(()=>subject.promptSection.isOpen()),true);
    assert.equal(await page.evaluate(()=>menuClosed),1);
  });
  await check('Programmatic collapse restores focus and hides body from tab order', async () => {
    assert.equal(await page.evaluate(() => {
      subject.musicBox.focus(); subject.musicSection.setOpen(false);
      const good=document.activeElement===subject.musicSection.toggle&&getComputedStyle(subject.musicSection.body).display==='none';
      subject.musicSection.setOpen(true); return good;
    }),true);
  });
  await check('Pool shell/toggle remains focused and collapsed across refresh; warnings visible', async () => {
    assert.equal(await page.evaluate(() => {
      const toggle=subject.poolSection.toggle;
      subject.poolSection.setOpen(false); toggle.focus(); subject.poolError='Fixture failure'; subject.renderPool();
      return toggle===subject.poolSection.toggle&&document.activeElement===toggle&&!subject.poolSection.isOpen()&&!subject.poolWarning.hidden&&subject.poolWarning.textContent==='Fixture failure';
    }),true);
  });
  await check('Unsupported empty pool hides; existing unsupported refs retain visible warning', async () => {
    assert.equal(await page.evaluate(() => {
      subject.timeline.takesRefs=false; subject.renderPool();
      const hidden=getComputedStyle(subject.poolHost).display==='none';
      subject.timeline.assets=[{handle:'ref-1'}]; subject.renderPool();
      const good=hidden&&!subject.poolHost.hidden&&subject.poolSection.toggle.textContent.includes('reads no attached references');
      subject.timeline.takesRefs=true; subject.renderPool();return good;
    }),true);
  });
  await check('Right action cancel does not toggle; successful Add reveals and retains assets', async () => {
    assert.equal(await page.evaluate(async () => {
      subject.poolSection.setOpen(false); setPickerAnswer(null); subject.poolAdd.click(); await Promise.resolve();
      const cancelled=!subject.poolSection.isOpen(); setPickerAnswer([{path:'test.png',kind:'image'}]);
      subject.poolAdd.click(); await Promise.resolve();
      return cancelled&&subject.poolSection.isOpen()&&subject.timeline.assets.length===2;
    }),true);
  });
  await check('Successful citation reveals global prompt without changing stored key', async () => {
    assert.equal(await page.evaluate(() => {
      subject.promptSection.setOpen(false); subject.citeName('subject');
      return subject.promptSection.isOpen()&&subject.timeline.prompt.includes('@subject')&&!Object.hasOwn(subject.timeline,'global_prompt');
    }),true);
  });
  await check('Hidden Cast navigation forces open while visible navigation keeps normal toggle', async () => {
    assert.deepEqual(await page.evaluate(() => {
      const calls=[]; let expanded=false;
      subject.castShelf={isExpanded:()=>expanded,openMember:(handle,options)=>{calls.push(options.forceOpen);return handle==='known'?'opened':false;},reveal:()=>{expanded=true;}};
      subject.openCastMember('bad'); const unknown=expanded; subject.openCastMember('known'); subject.openCastMember('known');
      return {calls,unknown,expanded};
    }),{calls:[true,true,false],unknown:false,expanded:true});
  });
  await check('Actual CastShelf methods preserve already-open member across whole-shelf hide/reveal', async () => {
    assert.equal(await page.evaluate(() => {
      const member={handle:'subject'},other={handle:'subject_2'},members=[member,other];
      const shelf=new FixtureCast({getCast:()=>members,getAssets:()=>[],disclosure:true});
      subject.castShelf=shelf;subject.castHost.replaceChildren(shelf.root);shelf.render();
      const initial=shelf.isExpanded(),toggle=shelf.section.toggle;
      shelf.openMember('subject');shelf.section.setOpen(false);
      subject.openCastMember('missing');const untouched=!shelf.isExpanded()&&shelf.opened===member;
      subject.openCastMember('subject');const revealed=shelf.isExpanded()&&shelf.opened===member;
      subject.openCastMember('subject');const shut=shelf.opened===null;
      shelf.section.setOpen(false);shelf.render();
      return initial&&untouched&&revealed&&shut&&toggle===shelf.section.toggle&&!shelf.isExpanded();
    }),true);
  });
  await check('Cast reference warnings remain visible outside folded list', async () => {
    assert.equal(await page.evaluate(() => {
      const shelf=subject.castShelf; shelf.getCast()[0].problem='Missing reference';shelf.render();shelf.section.setOpen(false);
      return !shelf.sectionWarning.hidden&&shelf.sectionWarning.textContent==='@subject: Missing reference'&&!shelf.section.body.contains(shelf.sectionWarning);
    }),true);
  });
  await check('Nested picker pointer preserves ancestor; scoped collapse cleans descendants after anchor refresh', async () => {
    await page.evaluate(() => {
      subject.poolSection.setOpen(true);
      const anchor=document.createElement('button');subject.poolSection.body.append(anchor);
      window.parentPop=makePopover(anchor,'parent');
      window.childPop=makePopover(parentPop.node.firstChild,'child');
      window.otherPop=makePopover(subject.musicBox,'other');
      // Ownership must survive ordinary chip refresh detaching the anchor.
      anchor.remove();
    });
    // Wait on the page's timer queue, after dismissable's deferred listeners,
    // instead of racing a host-side 20ms delay on a busy/browser-throttled run.
    await page.evaluate(()=>new Promise(resolve=>setTimeout(resolve,0)));
    assert.equal(await page.evaluate(() => {
      childPop.node.firstChild.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}));
      return parentPop.node.isConnected&&childPop.node.isConnected;
    }),true);
    await page.evaluate(()=>subject.poolSection.setOpen(false));
    assert.deepEqual(await page.evaluate(()=>({parent:parentPop.node.isConnected,child:childPop.node.isConnected,other:otherPop.node.isConnected,closed:[...popoverClosed].sort()})),{parent:false,child:false,other:false,closed:['child','other','parent']});
  });
  await check('Collapse without pointer event never dismisses an unrelated live popover', async () => {
    assert.equal(await page.evaluate(() => {
      subject.poolSection.setOpen(true);
      const anchor=document.createElement('button');subject.poolSection.body.append(anchor);
      const inside=makePopover(anchor,'owned-new'),outside=makePopover(subject.musicBox,'unrelated-new');
      subject.poolSection.setOpen(false);const good=!inside.node.isConnected&&outside.node.isConnected;
      outside.close();outside.close();return good&&popoverClosed.filter(x=>x==='unrelated-new').length===1;
    }),true);
  });
  await check('Default outside pointer dismissal still disposes once after deferred registration', async () => {
    await page.evaluate(()=>{window.regularPop=makePopover(subject.musicBox,'regular');});
    await page.evaluate(()=>new Promise(resolve=>setTimeout(resolve,0)));
    await page.evaluate(()=>document.body.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true})));
    assert.equal(await page.evaluate(()=>!regularPop.node.isConnected&&popoverClosed.filter(x=>x==='regular').length===1),true);
  });
  await check('Seam option matrix has no empty groups; One pass stays direct child', async () => {
    const rows=await page.evaluate(() => {
      const result=[];
      for (const [on,sound,passes] of [[false,false,2],[false,true,2],[true,false,1],[true,true,2]]) {
        const s=Object.assign(new Subject(),{timeline:{segments:[{},{},{continue:on,continue_audio:sound}]},passes:Array.from({length:passes},(_,i)=>({start:i,end:i+1})),commits:0});
        const node=s.renderJoin(2);document.body.append(node);
        result.push({groups:node.querySelectorAll('.mmc-tl-seam-group').length,options:node.querySelectorAll('.mmc-tl-join-from').length,empty:[...node.querySelectorAll('.mmc-tl-seam-group')].some(g=>!g.children.length),merge:node.querySelector('.mmc-tl-join-merge')?.parentNode===node});node.remove();
      }return result;
    });
    assert.deepEqual(rows,[{groups:3,options:0,empty:false,merge:true},{groups:4,options:1,empty:false,merge:true},{groups:4,options:1,empty:false,merge:true},{groups:4,options:2,empty:false,merge:true}]);
  });
  await check('Clip seams and generation after clip keep original capability gates', async () => {
    assert.deepEqual(await page.evaluate(() => {
      const s=Object.assign(new Subject(),{timeline:{segments:[{},{kind:'clip',continue:true}]},commits:0});
      const front=s.renderJoin(1);const f={groups:front.children.length,merge:!!front.querySelector('.mmc-tl-join-merge'),board:!!front.querySelector('.mmc-tl-join-board')};
      s.timeline.segments=[{kind:'clip'},{continue:false}];const back=s.renderJoin(1);return {front:f,backMerge:!!back.querySelector('.mmc-tl-join-merge')};
    }),{front:{groups:3,merge:false,board:false},backMerge:false});
  });
  await check('Seam buttons preserve callback anchors and disabled behavior', async () => {
    assert.equal(await page.evaluate(() => {
      const s=Object.assign(new Subject(),{timeline:{assets:[],segments:[{},{},{continue:true,continue_audio:true}]},passes:[{start:0,end:1},{start:1,end:2}],commits:0});
      const node=s.renderJoin(2),options=node.querySelectorAll('.mmc-tl-join-from');
      options[0].click();const first=lastPick.kind==='source'&&lastPick.anchor===options[0];
      options[1].click();const second=lastPick.kind==='blend'&&lastPick.anchor===options[1];
      s.timeline.segments[2]={blocked_continue:'No reference keyframes'};const locked=s.renderJoin(2).querySelector('button');locked.click();
      return first&&second&&locked.disabled&&s.commits===0;
    }),true);
  });
  await check('Large localized headings and action buttons do not overlap at narrow widths', async () => {
    const rows=await page.evaluate(() => {
      const results=[];
      for(const [title,hint] of [['작품 레퍼런스','한 번만 첨부하세요. 전역 프롬프트에 인용한 참조는 모든 세그먼트에 사용됩니다.'],['作品リファレンス','グローバルプロンプトで参照すると、すべてのセグメントで使用されます。'],['作品参考素材','在全局提示词中引用素材名称，即可应用到所有片段。'],['non_diegetic_music','The score only the audience hears.']]) {
        const action=document.createElement('button');action.textContent='From library';
        const d=createDisclosure({title,hint,content:document.createElement('textarea'),actions:[action]});
        Object.assign(d.root.style,{width:'285px'});d.root.style.setProperty('--mmc-type','1.5');document.body.append(d.root);
        const a=action.getBoundingClientRect(),b=d.toggle.getBoundingClientRect(),r=d.root.getBoundingClientRect();
        results.push({overlap: a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top,overflow:d.root.scrollWidth>r.width+1});d.root.remove();
      }return results;
    });assert.ok(rows.every(r=>!r.overlap&&!r.overflow),JSON.stringify(rows));
  });
  await check('Global Technique pill sits immediately beside the title with independent native hit area', async () => {
    assert.equal(await page.evaluate(() => {
      const section=subject.promptSection,head=section.head;
      const pill=head.querySelector('.mmc-tl-section-inline-actions button');
      const title=head.querySelector('.mmc-tl-section-title').getBoundingClientRect();
      const p=pill.getBoundingClientRect(),h=head.getBoundingClientRect();
      return !head.querySelector('button button')&&pill.parentElement.parentElement===head&&
        p.left>=title.right&&p.left-title.right<=24&&Math.abs(p.top-title.top)<20&&
        p.width<h.width/2&&document.elementFromPoint(p.right+12,p.top+p.height/2)===head&&
        subject.poolSection.head.children.length===2&&!subject.poolSection.head.classList.contains('mmc-tl-section-head-inline');
    }),true);
  });
  await check('Global Technique pill is inset without shrinking text or unrelated pills', async () => {
    const result=await page.evaluate(()=>{
      const pill=subject.promptSection.head.querySelector('.mmc-tl-section-inline-actions button');
      const head=subject.promptSection.head;
      const normal=document.createElement('button');normal.className='mmc-pill';normal.textContent=pill.textContent;
      head.parentElement.append(normal);
      const p=pill.getBoundingClientRect(),h=head.getBoundingClientRect(),n=normal.getBoundingClientRect();
      const good=p.top-h.top>=3&&h.bottom-p.bottom>=3&&p.height<n.height&&
        getComputedStyle(pill).fontSize===getComputedStyle(normal).fontSize;
      normal.remove();return good;
    });assert.equal(result,true);
  });
  await check('Only visible pill click opens techniques; blank header and inter-control gap fold once', async () => {
    await page.evaluate(()=>{subject.promptSection.setOpen(true);techniqueOpens=0;});
    const pill=page.locator('.mmc-tl-section-inline-actions button').first();
    await pill.click();
    assert.deepEqual(await page.evaluate(()=>[techniqueOpens,subject.promptSection.isOpen()]),[1,true]);
    const rect=await pill.boundingBox();
    await page.mouse.click(rect.x+rect.width+14,rect.y+rect.height/2);
    assert.deepEqual(await page.evaluate(()=>[techniqueOpens,subject.promptSection.isOpen(),document.activeElement===subject.promptSection.toggle]),[1,false,true]);
    const title=await page.locator('.mmc-tl-section-toggle').first().boundingBox();
    await page.mouse.click((title.x+title.width+rect.x)/2,rect.y+rect.height/2);
    assert.deepEqual(await page.evaluate(()=>[techniqueOpens,subject.promptSection.isOpen()]),[1,true]);
    await pill.locator('span').last().click();
    assert.deepEqual(await page.evaluate(()=>[techniqueOpens,subject.promptSection.isOpen()]),[2,true]);
  });
  await check('Tab, Enter and Space keep title folding separate from Technique activation', async () => {
    await page.evaluate(()=>{subject.promptSection.setOpen(true);techniqueOpens=0;subject.promptSection.toggle.focus();});
    await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(()=>document.activeElement===subject.promptSection.head.querySelector('.mmc-tl-section-inline-actions button')),true);
    await page.keyboard.press('Enter');
    await page.keyboard.press('Space');
    assert.deepEqual(await page.evaluate(()=>[techniqueOpens,subject.promptSection.isOpen()]),[2,true]);
    await page.keyboard.press('Shift+Tab');
    await page.keyboard.press('Space');
    assert.deepEqual(await page.evaluate(()=>[techniqueOpens,subject.promptSection.isOpen()]),[2,false]);
    await page.keyboard.press('Enter');
    assert.deepEqual(await page.evaluate(()=>[techniqueOpens,subject.promptSection.isOpen()]),[2,true]);
  });
  await check('Inline and trailing actions stay independent, including disabled and prevented clicks', async () => {
    assert.equal(await page.evaluate(() => {
      let calls=0;
      const inline=document.createElement('button');inline.textContent='Techniques';inline.onclick=()=>calls++;
      const trailing=document.createElement('button');trailing.textContent='Add';trailing.onclick=()=>calls++;
      const d=createDisclosure({title:'Fixture',inlineActions:[inline],actions:[trailing]});document.body.append(d.root);
      inline.click();trailing.click();const activated=calls===2&&d.isOpen();
      trailing.disabled=true;trailing.click();const disabled=calls===2&&d.isOpen();
      d.head.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));const blank=!d.isOpen();
      const prevented=new MouseEvent('click',{bubbles:true,cancelable:true});prevented.preventDefault();d.head.dispatchEvent(prevented);
      const good=activated&&disabled&&blank&&!d.isOpen();d.root.remove();return good;
    }),true);
  });
  await check('Localized inline pills remain inside narrow headers at enlarged text sizes', async () => {
    const rows=await page.evaluate(() => {
      const results=[];
      for(const label of ['기법','テクニック','技巧','Techniques']) {
        const pill=document.createElement('button');pill.className='mmc-pill';pill.textContent=label;
        const d=createDisclosure({title:'global_prompt',inlineActions:[pill]});
        d.root.style.width='245px';d.root.style.setProperty('--mmc-type','1.6');document.body.append(d.root);
        const p=pill.getBoundingClientRect(),b=d.toggle.getBoundingClientRect(),r=d.root.getBoundingClientRect();
        results.push({overlap:p.left<b.right&&p.right>b.left&&p.top<b.bottom&&p.bottom>b.top,
          overflow:d.root.scrollWidth>r.width+1||p.right>r.right+1,visible:p.width>0&&p.height>0});d.root.remove();
      }return results;
    });assert.ok(rows.every(r=>!r.overlap&&!r.overflow&&r.visible),JSON.stringify(rows));
  });
  if (process.env.TIMELINE_SCREENSHOT) {
    await page.setViewportSize({width:1200,height:800});
    await page.locator('.mmc-tl-section-head-inline').first().screenshot({path:process.env.TIMELINE_SCREENSHOT});
  }
  assert.equal(requests,0);
  console.log(JSON.stringify({passed:results.length,requests,results},null,2));
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{await browser?.close();});

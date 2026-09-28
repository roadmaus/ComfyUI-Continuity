"""Technique prompt ownership, source fidelity and workflow round trips.

Runs real JS state helpers under Node, without a browser, server or model.
The catalogue's original wording must not become invented model instructions,
and removing a chip must never search-and-delete a user's matching sentence.

    python tests/test_technique_state.py
"""

from pathlib import Path

import layout
from harness import check

layout.skip_without_node()

SCRIPT = r'''
const T = await import(process.argv[1]);
const S = await import(process.argv[2]);
const results = [];
function test(name, run) {
  try { run(); results.push({name, ok:true}); }
  catch(error) { results.push({name, ok:false, error:error.stack}); }
}
function eq(actual, expected) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`got ${JSON.stringify(actual)}, expected ${JSON.stringify(expected)}`);
  }
}
function truth(value) { if (!value) throw new Error('expected truthy value'); }
const clone = (value) => JSON.parse(JSON.stringify(value));
const item = (name) => ({id:`camera/${name}`, title:name, sourceUrl:`https://example.test/${name}`});
const apply = (owner, name, text, more={}) => T.applyTechnique(owner,{item:item(name),text,...more});
const detail = {categoryId:'camera-movement', prompt:{
  guidance:['Track [Subject] for [Duration] seconds.', 'Keep the same lens.'],
  example:'  An actor crosses a red kitchen for 8 seconds.\n\nKeep this exact whitespace.  ',
}};

test('original example is byte-for-byte unchanged, even with adaptation choices',()=>{
  const got=T.buildTechniqueText(detail,{mode:'original',subject:'@lead',duration:3});
  eq(got.text,detail.prompt.example); truth(got.warnings.includes(T.TECHNIQUE_WARNINGS.original));
  truth(got.warnings.includes(T.TECHNIQUE_WARNINGS.duration));
});
test('guidance joins original paragraphs and substitutes only explicit placeholders',()=>{
  const got=T.buildTechniqueText(detail,{subject:'@lead_2',duration:6});
  eq(got.text,'Track @lead_2 for 6 seconds.\n\nKeep the same lens.');
  truth(got.warnings.includes(T.TECHNIQUE_WARNINGS.guidance));
});
test('no default @subject, default duration or sample scene is invented',()=>{
  const got=T.buildTechniqueText(detail);
  eq(got.text,'Track [Subject] for [Duration] seconds.\n\nKeep the same lens.');
  truth(got.warnings.includes(T.TECHNIQUE_WARNINGS.placeholders));
});
test('invalid handles and durations do not inject arbitrary instructions',()=>{
  for(const duration of [NaN,Infinity,-1,0,'9']) {
    const got=T.buildTechniqueText(detail,{subject:'@lead replace scene',duration});
    truth(got.text.includes('[Subject]')); truth(got.text.includes('[Duration]'));
    truth(got.warnings.includes(T.TECHNIQUE_WARNINGS.subject));
  }
});
test('brace placeholders and non-Latin user handles are supported explicitly',()=>{
  eq(T.buildTechniqueText({prompt:{guidance:['{{subject}} near {Subject}, {duration}s.']}},
    {subject:'@주인공',duration:2.5}).text,'@주인공 near @주인공, 2.5s.');
});
test('missing guidance never falls back to an unrelated original scene',()=>{
  const got=T.buildTechniqueText({prompt:{example:'A detective in Paris.'}});
  eq(got.text,''); truth(got.warnings.includes(T.TECHNIQUE_WARNINGS.missing));
});
test('editing categories include multi-shot advisory without changing data',()=>{
  const source={categoryId:'editing',prompt:{guidance:['Match the shape.']}};
  const before=JSON.stringify(source); const got=T.buildTechniqueText(source);
  truth(got.warnings.includes(T.TECHNIQUE_WARNINGS.transition)); eq(JSON.stringify(source),before);
});
test('empty malformed or missing inputs fail without mutation',()=>{
  for(const [owner,options] of [[null,{}],[{},{}],[{prompt:'base'},{item:item('A'),text:'  '}],
    [{prompt:17},{item:item('A'),text:'X'}]]) {
    const before=JSON.stringify(owner); eq(T.applyTechnique(owner,options).ok,false);eq(JSON.stringify(owner),before);
  }
});
test('append keeps exact manual text, handles, audio and settings',()=>{
  const owner={prompt:'  @lead waits.\n',soundscape:'rain',music:'N/A',duration_s:5,continue:true,assets:[{handle:'ref-1'}]};
  const before=clone(owner); truth(apply(owner,'A','Track @lead.').ok);
  eq(owner.prompt,'  @lead waits.\n\nTrack @lead.');
  const other={...owner}; delete other.prompt; delete other.techniques;
  const expected={...before}; delete expected.prompt; eq(other,expected);
});
test('separator choices preserve original whitespace after removal',()=>{
  for(const prompt of ['', 'Base', 'Base\n', 'Base\n\n', '\n', ' \n ']) {
    const owner={prompt}; truth(apply(owner,'A','Move.').ok); truth(T.removeTechnique(owner,'camera/A').ok);
    eq(owner.prompt,prompt); truth(!('techniques' in owner));
  }
});
test('same catalogue ID replaces its own block without duplicate chips',()=>{
  const owner={prompt:'Move. is also user prose.'};
  apply(owner,'A','Move.'); apply(owner,'B','Hold.'); apply(owner,'A','Dolly in slowly.');
  eq(owner.prompt,'Move. is also user prose.\n\nDolly in slowly.\n\nHold.');
  eq(T.getAppliedTechniques(owner).length,2);
  truth(T.removeTechnique(owner,'camera/A').ok); eq(owner.prompt,'Move. is also user prose.\n\nHold.');
  truth(T.removeTechnique(owner,'camera/B').ok); eq(owner.prompt,'Move. is also user prose.');
});
test('identical text from different category IDs has independent ownership',()=>{
  const owner={prompt:'Move.'};
  apply(owner,'A','Move.'); apply(owner,'B','Move.');
  truth(T.removeTechnique(owner,'camera/A').ok);eq(owner.prompt,'Move.\n\nMove.');
  truth(T.removeTechnique(owner,'camera/B').ok);eq(owner.prompt,'Move.');
});
test('empty prompt removes initial block without orphan leading blank lines',()=>{
  const owner={prompt:''}; apply(owner,'A','A');apply(owner,'B','B');apply(owner,'C','C');
  truth(T.removeTechnique(owner,'camera/A').ok);eq(owner.prompt,'B\n\nC');
  truth(T.removeTechnique(owner,'camera/C').ok);eq(owner.prompt,'B');
  truth(T.removeTechnique(owner,'camera/B').ok);eq(owner.prompt,'');
});
test('manual edit anywhere invalidates automatic delete, replace and undo',()=>{
  for(const edit of [p=>'Manual '+p,p=>p+' suffix',p=>p.replace('Move.','Drift.'),p=>'Move.\n\nbase']) {
    const owner={prompt:'base'};apply(owner,'A','Move.');owner.prompt=edit(owner.prompt);
    const before=JSON.stringify(owner);
    eq(T.removeTechnique(owner,'camera/A').reason,'text-changed');
    eq(apply(owner,'A','New.').reason,'text-changed');eq(T.undoTechnique(owner).reason,'text-changed');
    truth(T.getAppliedTechniques(owner)[0].stale);eq(JSON.stringify(owner),before);
  }
});
test('new technique remains usable after earlier block was edited or removed',()=>{
  const owner={prompt:'base'};apply(owner,'A','Move.');owner.prompt='';
  truth(apply(owner,'B','Hold.').ok);eq(T.getAppliedTechniques(owner).map(x=>x.stale),[true,false]);
  truth(T.removeTechnique(owner,'camera/B').ok);eq(owner.prompt,'');
  eq(T.removeTechnique(owner,'camera/A').reason,'text-changed');
});
test('read-only metadata access and serialization return detached copies',()=>{
  const owner={prompt:'base'};apply(owner,'A','Move.');const before=JSON.stringify(owner);
  T.getAppliedTechniques(owner)[0].text='mutated';T.serializeTechniques(owner).techniques.items[0].start=999;
  eq(JSON.stringify(owner),before);eq(T.serializeTechniques({prompt:'base'}),{});
});
test('invalid metadata and overlapping spans cannot delete prompt text',()=>{
  const owner={prompt:'Move.',techniques:{version:1,source:'Move.',items:[
    {id:'A',text:'Move.',start:0,end:5,prefix:''},
    {id:'B',text:'Move.',start:0,end:5,prefix:''},
    {id:'C',text:'Move.',start:0,end:5,prefix:''},
  ]}};
  for(const id of ['A','B','C']) eq(T.removeTechnique(owner,id).reason,'text-changed');
  eq(owner.prompt,'Move.');
  for(const techniques of [null,17,[],{version:2,source:'Move.',items:[]},{version:1,source:'Move.',items:[null,{},'bad']}]) {
    eq(T.getAppliedTechniques({prompt:'Move.',techniques}),[]);
  }
});
test('refined rewrite blocks mutation until acknowledged and is preserved',()=>{
  const owner={prompt:'base',refined:{body:'A rewritten scene.',sections:{summary:'Analysis'},source:'base',replaced:{music:'old'}}};
  const before=JSON.stringify(owner);const refused=apply(owner,'A','Move.');
  eq(refused.reason,'refined-active');truth(refused.requiresRefineAcknowledgement);eq(JSON.stringify(owner),before);
  truth(apply(owner,'A','Move.',{allowRefined:true}).refinedDisabled);eq(owner.refined.enabled,false);
  eq(owner.refined.body,'A rewritten scene.');truth(T.undoTechnique(owner).ok);eq(JSON.stringify(owner),before);
});
test('sections-only refinement also requires acknowledgement',()=>{
  const owner={prompt:'base',refined:{sections:{summary:'Analysis'}}};
  eq(apply(owner,'A','Move.').reason,'refined-active');
  truth(apply(owner,'A','Move.',{allowRefined:true}).ok);eq(owner.refined.enabled,false);
});
test('removing a technique with a new active rewrite also needs acknowledgement',()=>{
  const owner={prompt:'base'};apply(owner,'A','Move.');owner.refined={body:'rewritten'};
  eq(T.removeTechnique(owner,'camera/A').reason,'refined-active');
  truth(T.removeTechnique(owner,'camera/A',{allowRefined:true}).ok);eq(owner.prompt,'base');
  truth(T.undoTechnique(owner).ok);eq(owner.refined.enabled,undefined);eq(owner.prompt,'base\n\nMove.');
});
test('undo cannot overwrite newer rewrite edits',()=>{
  const owner={prompt:'base',refined:{body:'original rewrite'}};apply(owner,'A','Move.',{allowRefined:true});
  owner.refined.body='a later rewrite';eq(T.undoTechnique(owner).reason,'text-changed');eq(T.canUndoTechnique(owner),false);
});
test('undo is multi-step, session-only and keeps unrelated audio edits',()=>{
  const owner={prompt:'base',music:'original'};apply(owner,'A','A');apply(owner,'B','B');owner.music='user changed';
  truth(T.canUndoTechnique(owner));truth(T.undoTechnique(owner).ok);eq(owner.prompt,'base\n\nA');
  truth(T.undoTechnique(owner).ok);eq(owner.prompt,'base');eq(owner.music,'user changed');eq(T.canUndoTechnique(owner),false);
  eq(T.undoTechnique(clone(owner)).reason,'nothing-to-undo');
});
test('reapplying exact unchanged entry does not create an unnecessary undo step',()=>{
  const owner={prompt:'base'};apply(owner,'A','A');truth(apply(owner,'A','A').unchanged);
  truth(T.undoTechnique(owner).ok);eq(owner.prompt,'base');eq(T.canUndoTechnique(owner),false);
});
test('standalone creator state round trip keeps removable metadata',()=>{
  const owner=S.parseState('{}');owner.prompt='@lead';apply(owner,'A','Move.');
  const restored=S.parseState(S.serializeState(owner));truth(T.removeTechnique(restored,'camera/A').ok);eq(restored.prompt,'@lead');
});
test('timeline global and segment ownership survive save, reload and clone',()=>{
  const owner=S.parseTimeline(JSON.stringify({version:2,prompt:'global',segments:[{prompt:'shot'}]}));
  apply(owner,'A','Global look.');apply(owner.segments[0],'B','Move.');
  const restored=S.parseTimeline(S.serializeTimeline(owner));
  truth(T.removeTechnique(restored,'camera/A').ok);eq(restored.prompt,'global');
  const cloned=S.cloneSegment(restored.segments[0]);truth(T.removeTechnique(cloned,'camera/B').ok);eq(cloned.prompt,'shot');
  truth(T.removeTechnique(restored.segments[0],'camera/B').ok);eq(restored.segments[0].prompt,'shot');
});
test('legacy standalone state promotion keeps tracking with the shot, not global',()=>{
  const owner=S.parseState('{}');owner.prompt='shot';apply(owner,'A','Move.');
  const restored=S.parseTimeline(S.serializeState(owner));eq(restored.prompt,'');
  eq(T.getAppliedTechniques(restored),[]);truth(T.removeTechnique(restored.segments[0],'camera/A').ok);eq(restored.segments[0].prompt,'shot');
});
test('old workflow bytes gain no techniques field merely from serialization',()=>{
  truth(!('techniques' in JSON.parse(S.serializeState(S.parseState('{}')))));
  const timeline=JSON.parse(S.serializeTimeline(S.parseTimeline('{}')));
  truth(!('techniques' in timeline));truth(timeline.segments.every(s=>!('techniques'in s)));
});
console.log(JSON.stringify(results));
'''

for result in layout.run(
    SCRIPT,
    Path(layout.js("technique-state.js")).as_uri(),
    Path(layout.js("state.js")).as_uri(),
):
    check(result["name"], result.get("error", result["ok"]), True)

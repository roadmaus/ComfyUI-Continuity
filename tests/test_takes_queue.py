"""Queue ownership under identical cards, overlapping submissions and reloads.

    python tests/test_takes_queue.py

Actual state/TimelineBody/Stage/queue methods, a small DOM and a mocked ComfyUI
transport. The transport matches api.queuePrompt(number, {output, workflow})
and its {prompt_id} response; promptQueued has no server id to correlate.
"""

import layout
from domshim import DOM
from harness import check, passed

layout.skip_without_node()

SCRIPT = r"""
const { strict: assert } = await import('node:assert');
const { api } = await import('../scripts/api.js');
const originalFetch = api.fetchApi;
let history = {}, running = [], deferredHistory = null;
api.fetchApi = async (url, ...args) => {
  if (url.startsWith('/history/')) {
    if (deferredHistory) return await deferredHistory;
    return {ok:true, json:async()=>history};
  }
  if (url === '/queue') return {ok:true, json:async()=>({queue_running:running,queue_pending:[]})};
  return originalFetch.call(api, url, ...args);
};
const events = new Map();
api.addEventListener = (name, fn) => {
  if (!events.has(name)) events.set(name, new Set());
  events.get(name).add(fn);
};
api.removeEventListener = (name, fn) => events.get(name)?.delete(fn);
const say = (name, detail) => { for (const fn of events.get(name) ?? []) fn({type:name,detail}); };
const requests = [];
api.queuePrompt = function(...args) {
  return new Promise((resolve,reject)=>requests.push({args,resolve,reject,receiver:this}));
};
const S = await import('./web/creator/state.js');
const { TimelineBody } = await import('./web/creator/timeline.js');
// Layout/model catalog painting is not the ownership contract. The real
// constructor, commit serialization, Stage, API hook and take methods run.
TimelineBody.prototype.render = function() {};
TimelineBody.prototype.adoptWeights = function() {};
const bodies = [];
const make = (names=['A','B'], id='11', initial=null, type='MiniMaxH3Creator', widgets={}) => {
  let blob = initial ?? JSON.stringify({version:2,prompt:'piece',segments:names.map(prompt=>({prompt,duration_s:5,assets:[],loras:[]}))});
  const body = new TimelineBody({read:()=>blob,write:value=>{blob=value;},nodeId:()=>id,widgets});
  body.testNodeType = type;
  bodies.push(body);
  return body;
};
const outputOf = (...bodies) => Object.fromEntries(bodies.map(body=>[
  String(body.nodeId()),{class_type:body.testNodeType,inputs:{
    [body.testNodeType === 'MiniMaxH3Creator' ? 'creator_data' : 'timeline_data']:body.read()
  }}
]));
const report = (segment,filename) => ({segment,filename,duration_s:5});
const names = body => body.timeline.segments.map(card=>card.take?.filename ?? null);
const queue = async (body,id,output=outputOf(body)) => {
  const pending = api.queuePrompt(0,{output,workflow:{}});
  requests.at(-1).resolve({prompt_id:id});
  await pending;
  say('promptQueued',{number:0,batchCount:1,requestId:requests.length});
  return output;
};
const deliver = (body,id,reports) => say('executed',{
  display_node:String(body.nodeId()),prompt_id:id,output:{mmc_takes:reports}
});

// Content equality is never live ownership, even after the old owner vanished.
{
  const body=make(['same','same']);
  await queue(body,'identical');
  body.timeline.segments.splice(0,1); body.commit();
  deliver(body,'identical',[report(1,'deleted.mp4')]);
  assert.deepEqual(names(body),[null]);
  deliver(body,'identical',[report(2,'survivor.mp4')]);
  assert.deepEqual(names(body),['survivor.mp4 [output]']);
  body.destroy();
}
{
  const body=make(['same']);
  await queue(body,'clone');
  const original=body.timeline.segments[0];
  const copy=S.cloneSegment(original);
  assert.notEqual(copy.card_id, original.card_id);
  body.timeline.segments=[copy]; body.commit();
  deliver(body,'clone',[report(1,'original.mp4')]);
  assert.deepEqual(names(body),[null]);
  body.destroy();
}

// Replies arrive in reverse order; each still owns its submitted strip, not
// the last promptQueued event or the strip after afterQueued advanced widgets.
{
  const body=make();
  const first=api.queuePrompt(0,{output:outputOf(body),workflow:{}});
  const request1=requests.at(-1);
  body.timeline.segments.reverse(); body.commit();
  const second=api.queuePrompt(0,{output:outputOf(body),workflow:{}});
  requests.at(-1).resolve({prompt_id:'second'});
  request1.resolve({prompt_id:'first'});
  await Promise.all([first,second]);
  say('promptQueued',{number:0,batchCount:2,requestId:42});
  deliver(body,'first',[report(1,'first-A.mp4'),report(2,'first-B.mp4')]);
  assert.deepEqual(names(body),['first-B.mp4 [output]','first-A.mp4 [output]']);
  deliver(body,'second',[report(1,'second-B.mp4'),report(2,'second-A.mp4')]);
  assert.deepEqual(names(body),['second-B.mp4 [output]','second-A.mp4 [output]']);
  assert.equal(request1.receiver,api);
  body.destroy();
}

// A serialized prompt can already differ from the live UI when it is posted.
{
  const body=make(['submitted']);
  const output=outputOf(body);
  body.timeline.segments[0].prompt='edited after graph serialization'; body.commit();
  await queue(body,'serialized',output);
  body.reload(); // New objects, same persisted identities.
  deliver(body,'serialized',[report(1,'submitted.mp4')]);
  assert.deepEqual(names(body),['submitted.mp4 [output]']);
  assert.deepEqual([...S.editedSince(body.timeline)],[0]);
  body.destroy();
}

// Multiple Creator nodes in one graph retain separate snapshots and reports.
{
  const a=make(['A'],'11'), b=make(['B'],'22',null,'MiniMaxH3Timeline');
  await queue(a,'two-nodes',outputOf(a,b));
  deliver(b,'two-nodes',[report(1,'B.mp4')]);
  assert.deepEqual(names(a),[null]);
  assert.deepEqual(names(b),['B.mp4 [output]']);
  deliver(a,'two-nodes',[report(1,'A.mp4')]);
  assert.deepEqual(names(a),['A.mp4 [output]']);
  a.destroy();b.destroy();
}

// A take may arrive before the HTTP response. /queue is the authoritative
// submitted graph; accepting the response later cannot replace its identity.
{
  const body=make(['fast']);
  const output=outputOf(body);
  const pending=api.queuePrompt(0,{output,workflow:{}});
  running=[[0,'fast',output,{},[]]];
  await body.takeTakes([report(1,'fast.mp4')],{promptId:'fast'});
  assert.deepEqual(names(body),['fast.mp4 [output]']);
  requests.at(-1).resolve({prompt_id:'fast'});await pending;
  running=[];body.destroy();
}

// After reload, history carries both the prompt id and its original graph.
{
  const old=make(['reload']);
  const output=outputOf(old), blob=old.read();old.destroy();
  const body=make([], '11', blob);
  body.timeline.segments[0].prompt='edited after reload';body.commit();
  history={recovered:{prompt:[0,'recovered',output,{},[]],outputs:{
    '11.take':{mmc_takes:[report(1,'recovered.mp4')]},
    '11.save':{mmc_video:[{filename:'whole.mp4',type:'output'}]}
  }}};
  const tasks=[];
  body.stage.onTakes=(reports,context)=>{const task=body.takeTakes(reports,context);tasks.push(task);return task;};
  body.stage.promptId='recovered';body.stage.state='sampling';
  await body.stage.probe();await Promise.all(tasks);
  assert.deepEqual(names(body),['recovered.mp4 [output]']);
  assert.deepEqual([...S.editedSince(body.timeline)],[0]);
  assert.equal(body.stage.state,'done');history={};body.destroy();
}

// Unknown prompt/node ownership is left in history, never attached by number.
{
  const body=make(['unknown']);
  await body.takeTakes([report(1,'unknown.mp4')],{promptId:'unknown'});
  assert.deepEqual(names(body),[null]);
  const pending=api.queuePrompt(0,{output:outputOf(body),workflow:{}});
  requests.at(-1).reject(new Error('refused'));
  await assert.rejects(pending,/refused/);
  assert.equal(body.queued.size,0);
  body.destroy();
}

// An in-flight recovery response for job 1 cannot land after job 2 started.
{
  const body=make(['probe']);let resolve;
  deferredHistory=new Promise(done=>{resolve=done;});
  body.stage.promptId='old';body.stage.state='sampling';
  const pending=body.stage.probe();
  say('execution_start',{prompt_id:'new'});
  resolve({ok:true,json:async()=>({old:{prompt:[0,'old',outputOf(body)],outputs:{
    '11.save':{mmc_video:[{filename:'old.mp4'}],mmc_takes:[report(1,'old.mp4')]}
  }}})});
  await pending;
  assert.deepEqual(names(body),[null]);
  assert.equal(body.stage.result,null);
  deferredHistory=null;body.destroy();
}

// Frontend identity is excluded from render stamps; cloning has the same
// content stamp but different ownership. Only explicit, unique legacy
// history reconstruction may use content, never a live snapshot.
{
  const strip=S.parseTimeline(JSON.stringify({segments:[{prompt:'a'},{prompt:'b'}]}));
  const queued=S.queuedCards(strip);
  const copy=S.parseTimeline(S.serializeTimeline(strip));
  copy.segments.forEach(card=>{delete card.card_id;});S.ensureCardIds(copy);
  assert.deepEqual(S.queuedCards(copy).stamps,queued.stamps);
  S.attachTakes(copy,[report(1,'legacy.mp4')],{...queued,legacy:true});
  assert.equal(copy.segments[0].take.filename,'legacy.mp4 [output]');
  const ambiguous=S.parseTimeline(JSON.stringify({segments:[{prompt:'same'},{prompt:'same'}]}));
  const prior=S.queuedCards(ambiguous,{legacy:true});
  ambiguous.segments.forEach(card=>{delete card.card_id;});S.ensureCardIds(ambiguous);
  assert.equal(S.attachTakes(ambiguous,[report(1,'ambiguous.mp4')],prior),false);
}

// An id-only migration cannot pre-fill default sampling and prevent the
// existing legacy-widget adoption. Version-1 Creator data keeps its id too.
{
  const body=make([], '11', JSON.stringify({version:1,prompt:'legacy shot',duration_s:5}),
    'MiniMaxH3Creator',{steps:{value:19},cfg:{value:2.5}});
  const raw=JSON.parse(body.read());
  assert.equal(raw.sampling,undefined);
  assert.ok(raw.card_id);
  await queue(body,'version-one');
  body.reload();
  const adopted=JSON.parse(body.read());
  assert.equal(adopted.sampling.steps,19);
  assert.equal(adopted.sampling.cfg,2.5);
  assert.equal(adopted.segments[0].card_id,raw.card_id);
  deliver(body,'version-one',[report(1,'legacy.mp4')]);
  assert.deepEqual(names(body),['legacy.mp4 [output]']);
  body.destroy();
}

// One legacy card without an id does not weaken another card's known id.
{
  const raw=JSON.stringify({version:2,prompt:'piece',segments:[
    {card_id:'known-original',prompt:'A',duration_s:5}, {prompt:'B',duration_s:5}
  ]});
  const body=make([], '11', raw);
  body.timeline.segments[0]=S.cloneSegment(body.timeline.segments[0]);body.commit();
  const output={'11':{class_type:'MiniMaxH3Creator',inputs:{creator_data:raw}}};
  await body.takeTakes([report(1,'removed-known.mp4'),report(2,'legacy-B.mp4')],
    {promptId:'mixed',prompt:[0,'mixed',output]});
  assert.deepEqual(names(body),[null,'legacy-B.mp4 [output]']);
  body.destroy();
}

// Recovery for an older report may complete after a newer report has already
// landed. Only that card's older take is refused; no global "last request wins".
{
  const body=make(['one']);const output=outputOf(body);let resolve;
  deferredHistory=new Promise(done=>{resolve=done;});
  const older=body.takeTakes([report(1,'older.mp4')],{promptId:'slow-history'});
  await queue(body,'newer-direct');
  deliver(body,'newer-direct',[report(1,'newer.mp4')]);
  resolve({ok:true,json:async()=>({'slow-history':{prompt:[0,'slow-history',output]}})});
  await older;
  assert.deepEqual(names(body),['newer.mp4 [output]']);
  deferredHistory=null;body.destroy();
}

// The shared wrapper is transparent to partial-queue options and response
// identity, and it cannot write back into a body destroyed during the request.
{
  const body=make(['destroyed']);const options={partialExecutionTargets:['11']};
  const pending=api.queuePrompt(-1,{output:outputOf(body),workflow:{}},options);
  const request=requests.at(-1), answer={prompt_id:'destroyed',node_errors:{}};
  body.destroy();request.resolve(answer);
  assert.equal(await pending,answer);
  assert.equal(request.receiver,api);
  assert.equal(request.args[0],-1);
  assert.equal(request.args[2],options);
  assert.equal(body.queued.size,0);
}

// Corrupt or not-yet-assigned widget values retain parseTimeline's safe default
// fallback, rather than a migration throwing before the node can be opened.
{
  for (const raw of ['', '{broken', 'null', '42', 'true', '[]', '"text"']) {
    const fallback=S.parseTimeline(raw);
    const body=make([], '11', raw);
    assert.equal(body.timeline.segments.length,fallback.segments.length);
    assert.deepEqual(S.queuedCards(body.timeline).stamps,S.queuedCards(fallback).stamps);
    assert.equal(body.read(),raw);
    body.destroy();
  }
  let reads=0,writes=0;
  const body=new TimelineBody({nodeId:()=>11,
    read:()=>++reads === 1 ? '{"segments":[{"prompt":"a"}]}' : '',
    write:()=>{writes++;}});
  assert.equal(writes,0);
  body.destroy();
  const writeError=new Error('widget write failed');
  assert.throws(()=>new TimelineBody({nodeId:()=>11,
    read:()=>'{"segments":[{"prompt":"a"}]}',
    write:()=>{throw writeError;}}),error=>error===writeError);
}
for(const body of bodies) body.destroy();
console.log(JSON.stringify({passed:true,scenarios:16}));
"""

with layout.pack() as packed:
    result = layout.in_pack(DOM + SCRIPT, packed)
check("prompt-scoped take ownership scenarios", result, {"passed": True, "scenarios": 16})
passed("take identities, submitted prompts and history recovery stay paired")

"""All library entry points share live, owner-stable prompt targets.

Actual editor/control/timeline modules execute against the DOM shim. Only the
library opening boundary is captured; modal navigation has its browser suite.
No ComfyUI server, installed node, network or GPU is involved.
"""
from pathlib import Path

import domshim
import layout
from harness import check, passed

layout.skip_without_node()

SCRIPT = domshim.DOM + r'''
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import path from "node:path";
import * as S from "./web/creator/state.js";
import { CreatorEditor } from "./web/creator/editor.js";
import { techniqueTargetsForPiece } from "./web/creator/technique-controls.js";
import { getAppliedTechniques } from "./web/creator/technique-state.js";
globalThis.app = { extensionManager: { setting: { get: () => "en" } } };
const timelineURL = pathToFileURL(path.join(process.cwd(), "web/creator/timeline.js"));
const source = readFileSync(timelineURL, "utf8").replace("class Timeline {", "export class Timeline {")
  .replace(/from "(\.[^"]+)"/g, (_, spec) => `from "${new URL(spec, timelineURL).href}"`);
const { Timeline, TimelineBody } = await import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));
const item = { id: "camera/dolly", title: "Dolly In" };
const results = [];
const test = (name, fn) => { fn(); results.push(name); };
const makePiece = count => {
  const piece = S.parseTimeline(JSON.stringify({version:2,prompt:"Global base.",subjects:[{handle:"subject",from:[]}],
    segments:Array.from({length:count},(_,i)=>({prompt:`Original ${i+1}.`,duration_s:i+3,assets:[]}))}));
  if (!count) piece.segments = [];
  return piece;
};
const makeEditor = (piece, index=0) => {
  const editor=Object.create(CreatorEditor.prototype);
  editor.state=piece.segments[index];editor.piece=piece;editor.castPiece=piece;
  editor.techniqueHost=document.createElement("div");
  editor.prompt={value:editor.state.prompt,setValue(text){this.value=text;}};
  editor.writes=0;editor.renders=0;
  editor.onCommit=()=>{editor.writes++;editor.saved=S.serializeTimeline(piece);};
  editor.render=()=>{editor.renders++;editor.renderTechniques();};
  return editor;
};
const makeTimeline = piece => Object.assign(Object.create(Timeline.prototype), {
  timeline:piece,techniqueHost:document.createElement("div"),promptBox:{setValue(){}},promptSection:{setOpen(){}},
  writes:0,commit(){this.writes++;this.saved=S.serializeTimeline(this.timeline);},
});
const makeBody = piece => Object.assign(Object.create(TimelineBody.prototype), {
  timeline:piece,writes:0,commit(){this.writes++;this.saved=S.serializeTimeline(this.timeline);},
});
const fire = node => { assert.ok(node); for(const fn of node.listeners?.click??[])fn({target:node,preventDefault(){},stopPropagation(){}}); };
const checkOpen = (call,piece,owner) => {
  assert.equal(call.targets.length,piece.segments.length+1);
  assert.equal(call.target.owner,owner);
  assert.deepEqual(call.targets.map(target=>target.owner),[piece,...piece.segments]);
  assert.equal(new Set(call.targets.map(target=>target.id)).size,call.targets.length);
  assert.deepEqual(call.getTargets().map(target=>target.id),call.targets.map(target=>target.id));
};

for(const count of [0,1,7,12]) {
  test(`${count} segments: global/body/every segment entry expose the same complete inventory`,()=>{
    const piece=makePiece(count),modal=makeTimeline(piece),body=makeBody(piece);
    modal.openTechniques();checkOpen(lastTechniqueOpen,piece,piece);
    const ids=lastTechniqueOpen.targets.map(target=>target.id);
    body.openTechniques();checkOpen(lastTechniqueOpen,piece,piece);
    assert.deepEqual(lastTechniqueOpen.targets.map(target=>target.id),ids);
    for(let i=0;i<count;i++) {
      const editor=makeEditor(piece,i);editor.openTechniques();checkOpen(lastTechniqueOpen,piece,piece.segments[i]);
      assert.deepEqual(lastTechniqueOpen.targets.map(target=>target.id),ids);
      assert.equal(lastTechniqueOpen.target.label,`Segment ${i+1}`);
    }
  });
}
test("Technique chip entry retains all targets and chooses only its own default",()=>{
  const piece=makePiece(7),editor=makeEditor(piece,4),target=editor.techniqueTargets().find(t=>t.owner===editor.state);
  assert.equal(target.apply({item,text:"Dolly slowly."}).ok,true);
  fire(editor.techniqueHost.querySelector(".mmc-technique-chip").children[0]);
  checkOpen(lastTechniqueOpen,piece,piece.segments[4]);assert.equal(lastTechniqueOpen.initialTechnique,item.id);
});
test("Reordering keeps identity and updates display number without redirecting a write",()=>{
  const piece=makePiece(7),modal=makeTimeline(piece);modal.openTechniques();
  const call=lastTechniqueOpen,target=call.targets[5],owner=piece.segments[4],id=target.id;
  piece.segments.unshift(piece.segments.splice(4,1)[0]);
  assert.equal(target.label,"Segment 1");assert.equal(target.isValid(),true);
  assert.equal(call.getTargets()[1].id,id);
  assert.equal(target.apply({item,text:"Follow the selected owner."}).ok,true);
  assert.match(owner.prompt,/Follow the selected owner/);
  assert.equal(piece.segments[4].prompt,"Original 4.");
  const copy={...owner,card_id:owner.card_id};piece.segments.push(copy);
  assert.notEqual(call.getTargets().at(-1).id,id,"Copied card IDs must not alias prompt owners");
});
test("Added/deleted/replaced targets are re-read; stale transactions cannot mutate anything",()=>{
  const piece=makePiece(1),modal=makeTimeline(piece);modal.openTechniques();const call=lastTechniqueOpen;
  const removed=piece.segments[0],stale=call.targets[1];
  piece.segments.push(S.emptyState());assert.equal(call.getTargets().length,3);
  piece.segments.shift();const before=JSON.stringify([piece,removed]);
  assert.equal(stale.isValid(),false);assert.equal(stale.apply({item,text:"No resurrection."}).ok,false);
  assert.equal(stale.remove(item.id).ok,false);assert.equal(stale.undo().ok,false);
  assert.equal(JSON.stringify([piece,removed]),before);
  const global=call.targets[0];modal.timeline=makePiece(1);
  assert.equal(global.apply({item,text:"No old graph."}).ok,false);
  assert.ok(!call.getTargets().some(target=>target.id===global.id));
});
test("Host replacement, destroyed editor and closed Timeline block captured targets",()=>{
  const piece=makePiece(2),editor=makeEditor(piece),modal=makeTimeline(piece),body=makeBody(piece);
  let live=true;editor.techniqueContextCurrent=()=>live;modal.isCurrent=()=>live;
  const targets=[editor.techniqueTargets()[2],modal.techniqueTargets()[2]];
  live=false;for(const target of targets)assert.equal(target.apply({item,text:"Blocked."}).ok,false);
  live=true;const editTarget=editor.techniqueTargets()[2];editor.destroy();
  assert.equal(editTarget.isValid(),false);
  const modalTarget=modal.techniqueTargets()[2];modal.closed=true;assert.equal(modalTarget.isValid(),false);
  const bodyTarget=body.techniqueTargets()[2];body.destroyed=true;assert.equal(bodyTarget.isValid(),false);
});
test("Non-current apply persists only that owner and leaves the current editable text alone",()=>{
  const piece=makePiece(7),editor=makeEditor(piece,2),remote=piece.segments[5];
  const before=piece.segments.map(row=>row.prompt),global=piece.prompt,input=editor.prompt.value;
  const target=editor.techniqueTargets().find(row=>row.owner===remote);
  assert.equal(target.apply({item,text:"Dolly toward @subject."}).ok,true);
  assert.equal(editor.prompt.value,input);assert.equal(editor.state.prompt,before[2]);
  assert.equal(piece.prompt,global);assert.equal(editor.writes,1);
  assert.deepEqual(piece.segments.map(row=>row.prompt),before.map((text,index)=>index===5?text+"\n\nDolly toward @subject.":text));
  const restored=S.parseTimeline(editor.saved);
  assert.equal(getAppliedTechniques(restored.segments[5])[0].id,item.id);
  assert.equal(getAppliedTechniques(restored.segments[2]).length,0);
  assert.equal(editor.techniqueHost.querySelectorAll(".mmc-technique-chip").length,0);
});
test("Non-current local references wake/remove/undo through their own owner, never the visible one",()=>{
  const piece=makePiece(2),editor=makeEditor(piece),remote=piece.segments[1];
  const asset=handle=>({handle,kind:"image",role:"reference",filename:"lighting/local.png",enabled:false});
  editor.state.assets=[asset("img-1")];remote.assets=[asset("img-1")];
  const target=editor.techniqueTargets().find(t=>t.owner===remote);
  assert.equal(target.apply({item,text:"Dolly toward @img-1."}).ok,true);
  assert.equal(S.muted(remote.assets[0]),false);assert.equal(S.muted(editor.state.assets[0]),true);
  target.remove(item.id);assert.equal(S.muted(remote.assets[0]),true);
  const remoteEditor=makeEditor(piece,1);remoteEditor.renderTechniques();
  assert.equal(remoteEditor.techniqueHost.hidden,false);
  assert.ok(remoteEditor.techniqueHost.children.some(node=>node.textContent==="Undo technique change"));
  target.undo();assert.equal(S.muted(remote.assets[0]),false);
  target.undo();assert.equal(S.muted(remote.assets[0]),true);assert.equal(remote.prompt,"Original 2.");
  assert.equal(editor.prompt.value,"Original 1.");
});
test("Global selection modifies the one shared prompt instead of cloning into segments",()=>{
  const piece=makePiece(12),editor=makeEditor(piece,4),before=piece.segments.map(row=>row.prompt);
  const target=editor.techniqueTargets()[0];assert.equal(target.kind,"global");
  target.apply({item,text:"Shared camera language."});
  assert.equal(piece.prompt,"Global base.\n\nShared camera language.");
  assert.deepEqual(piece.segments.map(row=>row.prompt),before);assert.equal(editor.writes,1);
});
test("Non-current active refinement requires acknowledgement and undo restores only that owner",()=>{
  const piece=makePiece(7),editor=makeEditor(piece),remote=piece.segments[6];
  remote.refined={body:"Earlier rewrite.",scope:"shot",enabled:true};
  const target=editor.techniqueTargets()[7],before=JSON.stringify(piece);
  assert.equal(target.requiresRefineAcknowledgement(),true);
  assert.equal(target.apply({item,text:"Dolly."}).requiresRefineAcknowledgement,true);
  assert.equal(JSON.stringify(piece),before);assert.equal(editor.writes,0);
  assert.equal(target.apply({item,text:"Dolly.",allowRefined:true}).ok,true);
  assert.equal(remote.refined.enabled,false);assert.equal(remote.refined.body,"Earlier rewrite.");
  assert.equal(editor.state.refined,null);target.undo();
  assert.equal(remote.refined.enabled,true);assert.equal(remote.prompt,"Original 7.");
});
test("Legacy global refinement guard examines every segment including the last",()=>{
  const piece=makePiece(12),editor=makeEditor(piece),last=piece.segments[11];
  last.refined={body:"Includes the old global prompt.",enabled:true};
  const target=editor.techniqueTargets()[0],before=JSON.stringify(piece);
  assert.ok(target.blockedReason());assert.equal(target.apply({item,text:"Blocked."}).ok,false);
  assert.equal(JSON.stringify(piece),before);last.refined.scope="shot";
  assert.equal(target.apply({item,text:"Allowed."}).ok,true);
});
test("Live cast handles and duration belong to the selected owner",()=>{
  const piece=makePiece(7),editor=makeEditor(piece),target=editor.techniqueTargets()[6];
  assert.equal(target.duration,piece.segments[5].duration_s);
  piece.segments[5].duration_s=19;piece.subjects.push({handle:"subject_2",from:[]});
  assert.equal(target.duration,19);assert.deepEqual(target.subjects.map(row=>row.handle),["subject","subject_2"]);
  assert.equal(editor.techniqueTargets()[0].duration,null);
});
test("Supplied clips remain listed but cannot accept ignored generated prose",()=>{
  const piece=makePiece(2);piece.segments[1]={kind:"clip",filename:"clip.mp4"};
  const targets=techniqueTargetsForPiece({piece}),clip=targets[2];
  assert.equal(targets.length,3);assert.equal(clip.label,"Segment 2");assert.equal(clip.isValid(),true);
  assert.match(clip.blockedReason(),/supplied clip/);const before=JSON.stringify(piece);
  assert.equal(clip.apply({item,text:"Unused text."}).ok,false);assert.equal(JSON.stringify(piece),before);
});
test("Manual editing a non-current target still protects removal and undo",()=>{
  const piece=makePiece(2),target=makeTimeline(piece).techniqueTargets()[2];
  target.apply({item,text:"Dolly."});piece.segments[1].prompt+=" Hand-written.";
  const before=JSON.stringify(piece);assert.equal(target.remove(item.id).ok,false);assert.equal(target.undo().ok,false);
  assert.equal(JSON.stringify(piece),before);
});
test("Actual segment editor refreshes its parent when applying to a different segment",()=>{
  const piece=makePiece(7);let writes=0,spawned=null;
  const modal=new Timeline({timeline:piece,onCommit:()=>writes++},()=>{});modal.mount();
  const original=CreatorEditor.prototype.renderTechniques;
  CreatorEditor.prototype.renderTechniques=function(...args){spawned=this;return original.apply(this,args);};
  try { modal.edit(4); } finally { CreatorEditor.prototype.renderTechniques=original; }
  const beforeText=spawned.prompt.getValue(),global=modal.promptBox.getValue();
  const redraws={};
  for(const method of ["renderStrip","renderPool","renderCast"]){
    const real=modal[method].bind(modal);redraws[method]=0;
    modal[method]=(...args)=>{redraws[method]++;return real(...args);};
  }
  const target=spawned.techniqueTargets().find(row=>row.owner===piece.segments[1]),beforeWrites=writes;
  assert.equal(target.apply({item,text:"Remote camera direction."}).ok,true);
  assert.equal(writes-beforeWrites,1);assert.deepEqual(redraws,{renderStrip:1,renderPool:1,renderCast:1});
  assert.equal(spawned.prompt.getValue(),beforeText);assert.equal(modal.promptBox.getValue(),global);
  assert.match(piece.segments[1].prompt,/Remote camera direction/);
  const oldPiece=modal.timeline;modal.timeline=makePiece(7);
  assert.equal(target.apply({item,text:"Must not touch the discarded piece."}).ok,false);
  assert.equal(oldPiece.segments[1].prompt,"Original 2.\n\nRemote camera direction.");
});
console.log(JSON.stringify({results}));
'''

with layout.pack(skip=("atlas", "techniques")) as target:
    # Capture the public opening contract without fetching the library corpus.
    Path(target, "web", "creator", "techniques.js").write_text(
        "export function openTechniqueLibrary(options) { globalThis.lastTechniqueOpen = options; }\n",
        encoding="utf-8",
    )
    got = layout.in_pack(SCRIPT, target)

check("all focused target cases ran", len(got["results"]), 17)
passed("all 17 live technique target cases passed")

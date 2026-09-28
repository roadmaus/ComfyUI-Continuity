"""Technique targets use the real editor/timeline owners, commits and serializers.

These are actual frontend modules running against the project's small DOM shim,
not browser layout/GPU-render tests. The companion browser suite tests the modal.
"""

import domshim
import layout
from harness import check

layout.skip_without_node()

SCRIPT = domshim.DOM + r'''
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import path from "node:path";
import * as S from "./web/creator/state.js";
import { CreatorEditor } from "./web/creator/editor.js";
import { techniqueTarget, renderTechniqueBar } from "./web/creator/technique-controls.js";
import { getAppliedTechniques } from "./web/creator/technique-state.js";

globalThis.app = { extensionManager: { setting: { get: () => "en" } } };
const timelineURL = pathToFileURL(path.join(process.cwd(), "web/creator/timeline.js"));
const source = readFileSync(timelineURL, "utf8")
  .replace("class Timeline {", "export class Timeline {")
  .replace(/from "(\.[^"]+)"/g, (_, spec) => `from "${new URL(spec, timelineURL).href}"`);
const { Timeline } = await import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));
const settle = async () => { for (let i = 0; i < 4; i++) await new Promise(resolve => setTimeout(resolve, 0)); };
const fire = (node, type) => {
  if (!node) throw new Error(`Missing ${type} target`);
  const event = { target: node, currentTarget: node, preventDefault() {}, stopPropagation() {} };
  for (const callback of node.listeners?.[type] ?? []) callback(event);
};
const item = { id: "camera-movement/dolly-in", title: "Dolly In", sourceUrl: "https://melies.co/cinematic-techniques/camera-movement/dolly-in" };
const item2 = { id: "lighting/soft-light", title: "Soft Light" };
const makePiece = () => S.parseTimeline(JSON.stringify({ version: 2, render: "chained",
  prompt: "A shared studio.", soundscape: "Room tone.", music: "No music.",
  subjects: [{ handle: "subject", takes: "person", from: [], description: "A performer." }],
  assets: [{ handle: "ref-1", kind: "image", filename: "lighting/studio.png", role: "reference" }],
  segments: [{ prompt: "@subject looks left.", duration_s: 5, assets: [], loras: [] },
             { prompt: "@subject turns.", duration_s: 8, continue: true, audio_continue: true, assets: [], loras: [] }],
}));
const out = {};
const piece = makePiece();
const protectedState = object => JSON.stringify(object, (key, value) => ["prompt", "techniques"].includes(key) ? undefined : value);
const protectedBefore = protectedState(JSON.parse(S.serializeTimeline(piece)));
let persisted = null, renders = 0;
const editor = Object.create(CreatorEditor.prototype);
editor.state = piece.segments[1]; editor.piece = piece; editor.castPiece = piece;
editor.techniqueHost = document.createElement("div");
editor.prompt = { setValue(value) { this.value = value; } };
editor.citations = [];
editor.liveCited = handles => editor.citations.push(...handles);
editor.onCommit = () => { persisted = S.serializeTimeline(piece); };
editor.render = () => { renders++; editor.renderTechniques(); };
const targets = editor.techniqueTargets();
const current = targets.find(target => target.owner === editor.state);
const global = targets.find(target => target.kind === "global");
out.owners = { kinds: [current.kind, global.kind], stableIds: current.id !== global.id
    && editor.techniqueTargets().find(target => target.owner === editor.state).id === current.id,
  labels: [current.label, global.label], currentIsSecond: current.owner === piece.segments[1], globalIsPiece: global.owner === piece,
  duration: current.duration, globalDuration: global.duration, subjects: current.subjects.map(row => row.handle) };
const originalGlobal = piece.prompt;
out.currentApply = current.apply({ item, text: "Dolly toward @subject; keep @ref-1." });
out.current = { globalUnchanged: piece.prompt === originalGlobal,
  firstUnchanged: piece.segments[0].prompt === "@subject looks left.",
  prompt: piece.segments[1].prompt, input: editor.prompt.value, citations: editor.citations,
  commits: persisted !== null, renders, edited: editor.techniqueHost.dataset.techniqueEdited,
  chips: editor.techniqueHost.querySelectorAll(".mmc-technique-chip").length };
out.globalApply = global.apply({ item: item2, text: "Soft practical light." });
const reloaded = S.parseTimeline(persisted);
out.persisted = { global: reloaded.prompt, second: reloaded.segments[1].prompt,
  globalItems: getAppliedTechniques(reloaded).map(row => row.id),
  secondItems: getAppliedTechniques(reloaded.segments[1]).map(row => row.id),
  protectedUnchanged: protectedBefore === protectedState(JSON.parse(S.serializeTimeline(piece))) };

// A newly selected prompt never becomes the old modal's accidental destination.
editor.state = piece.segments[0];
const staleSnapshot = JSON.stringify(piece);
out.switchedTarget = { result: current.apply({ item, text: "Must not land." }), unchanged: staleSnapshot === JSON.stringify(piece) };
editor.state = piece.segments[1];
piece.segments.splice(1, 1);
const removedSnapshot = JSON.stringify(piece);
out.removedTarget = { result: current.apply({ item, text: "Must not resurrect." }), unchanged: removedSnapshot === JSON.stringify(piece) };

const edited = { prompt: "Keep original prose." };
const editedTarget = techniqueTarget({ owner: edited });
editedTarget.apply({ item, text: "Dolly slowly." });
edited.prompt += " My manual addition.";
const editedHost = document.createElement("div");
renderTechniqueBar(editedHost, editedTarget);
const deleteButton = editedHost.querySelector(".mmc-technique-chip").children[1];
const editedBefore = JSON.stringify(edited);
out.manualEdit = { stale: editedTarget.applied()[0].stale, disabled: "disabled" in deleteButton.attrs,
  remove: editedTarget.remove(item.id), undo: editedTarget.undo(), unchanged: editedBefore === JSON.stringify(edited) };

// Acknowledgement is consistent with the transaction layer for both legacy
// body-only refinements and the section-bearing refinement representation.
out.refined = [];
for (const refined of [{ body: "A rewritten shot.", enabled: true },
                       { body: "", sections: { summary: "A rewritten shot." }, enabled: true }]) {
  const owner = { prompt: "A written shot.", refined: structuredClone(refined), soundscape: "No changes." };
  let commits = 0;
  const target = techniqueTarget({ owner, onChange: () => commits++ });
  const gate = target.requiresRefineAcknowledgement();
  const refusal = target.apply({ item, text: "Move slowly." });
  const acknowledged = target.apply({ item, text: "Move slowly.", allowRefined: true });
  const disabled = owner.refined.enabled === false;
  const kept = JSON.stringify({ ...owner.refined, enabled: true }) === JSON.stringify(refined);
  const undo = target.undo();
  out.refined.push({ gate, refused: refusal.ok === false, acknowledged: acknowledged.ok, disabled, kept,
    undo: undo.ok, restored: JSON.stringify(owner.refined) === JSON.stringify(refined), commits,
    audio: owner.soundscape });
}
const legacyPiece = makePiece();
legacyPiece.segments[0].refined = { body: "Contains the old global prompt.", enabled: true };
const legacyTarget = techniqueTarget({ owner: legacyPiece, piece: legacyPiece, kind: "global" });
const legacyBefore = JSON.stringify(legacyPiece);
out.legacy = { warning: !!legacyTarget.warning(), blocked: !legacyTarget.apply({ item, text: "Global camera direction." }).ok,
  unchanged: JSON.stringify(legacyPiece) === legacyBefore };
legacyPiece.segments[0].refined.scope = "shot";
out.shotScopedAllowsGlobal = legacyTarget.apply({ item, text: "Global camera direction." }).ok;
legacyPiece.segments[0].refined = { body: "", sections: { summary: "A section-only rewrite." }, enabled: true };
out.sectionsOnlyAllowsGlobal = legacyTarget.apply({ item: item2, text: "Global lighting direction." }).ok;

// Removing the final chip must not strand the undo action in a hidden host.
const empty = { prompt: "Base." }, bar = document.createElement("div");
let barTarget;
barTarget = techniqueTarget({ owner: empty, onChange: () => {
  bar.dataset.techniqueEdited = "true"; renderTechniqueBar(bar, barTarget);
} });
barTarget.apply({ item, text: "Move." });
barTarget.remove(item.id);
const undoButton = bar.children.find(node => node.tagName === "BUTTON" && node.textContent === "Undo technique change");
out.lastRemoval = { visible: !bar.hidden, hasUndo: !!undoButton, prompt: empty.prompt };
fire(undoButton, "click");
out.lastRemoval.afterUndo = empty.prompt;

// The editor's ordinary @handle hooks wake local muted references when a name
// is inserted and mute them when its final mention is removed. Techniques
// must use both halves of that contract, including undo/removal transactions.
const localOwner = S.emptyState();
localOwner.prompt = "A quiet studio.";
localOwner.assets = [{ handle: "img-1", kind: "image", role: "reference", filename: "lighting/local.png", enabled: false }];
const localEditor = Object.create(CreatorEditor.prototype);
localEditor.state = localOwner; localEditor.piece = localOwner; localEditor.castPiece = localOwner;
localEditor.techniqueHost = document.createElement("div");
localEditor.prompt = { setValue(value) { this.value = value; } };
localEditor.onCommit = () => {};
localEditor.render = () => localEditor.renderTechniques();
localEditor.flash = message => { throw new Error(message); };
const localTarget = localEditor.techniqueTargets()[0];
localTarget.apply({ item, text: "Move toward @img-1." });
const afterReferenceApply = !S.muted(localOwner.assets[0]);
localTarget.remove(item.id);
const afterReferenceRemove = S.muted(localOwner.assets[0]);
localTarget.undo();
out.localReferenceLifecycle = { wakesOnApply: afterReferenceApply, mutesAfterLastMentionRemoved: afterReferenceRemove,
  wakesOnUndoRemove: !S.muted(localOwner.assets[0]), keptFile: localOwner.assets[0].filename === "lighting/local.png" };
localTarget.undo();
out.localReferenceLifecycle.mutesOnUndoApply = S.muted(localOwner.assets[0]);
out.localReferenceLifecycle.restoresWrittenPrompt = localOwner.prompt === "A quiet studio.";
localOwner.prompt = "Keep @img-1 visible.";
delete localOwner.assets[0].enabled;
localTarget.apply({ item, text: "Dolly toward @img-1." });
localTarget.remove(item.id);
out.localReferenceLifecycle.otherMentionKeepsReference = !S.muted(localOwner.assets[0]);

// Mount the actual Timeline and its actual segment editor. Capture the editor
// instance without changing constructor/target/commit implementations.
const realPiece = makePiece();
let timelineWrites = 0;
const modal = new Timeline({ timeline: realPiece, onCommit: () => { timelineWrites++; } }, () => {});
modal.mount(); await settle();
let spawnedEditor = null;
const realRender = CreatorEditor.prototype.renderTechniques;
CreatorEditor.prototype.renderTechniques = function(...args) { spawnedEditor = this; return realRender.apply(this, args); };
modal.edit(1);
CreatorEditor.prototype.renderTechniques = realRender;
await settle();
const modalTarget = spawnedEditor.techniqueTargets().find(target => target.kind === "global");
const writesBeforeApply = timelineWrites;
const childApply = modalTarget.apply({ item: item2, text: "Window bounce light." });
out.segmentToGlobal = { ok: childApply.ok, writes: timelineWrites - writesBeforeApply, prompt: realPiece.prompt,
  displayedPrompt: modal.promptBox.getValue(),
  chips: modal.techniqueHost.querySelectorAll(".mmc-technique-chip").length };
const globalControl = modal.techniqueTarget();
const beforeTimeline = modal.timeline;
modal.timeline = makePiece();
const oldText = beforeTimeline.prompt;
out.replacedTimeline = { result: globalControl.apply({ item, text: "Must not write old graph." }), oldUnchanged: beforeTimeline.prompt === oldText };
console.log(JSON.stringify(out));
'''

with layout.pack(skip=("atlas", "techniques")) as target:
    got = layout.in_pack(SCRIPT, target)

check("segment editor exposes separate current segment and global owners", got["owners"],
      {"kinds": ["segment", "global"], "stableIds": True,
       "labels": ["Segment 2", "Global prompt — all segments"], "currentIsSecond": True,
       "globalIsPiece": True, "duration": 8, "globalDuration": None, "subjects": ["subject"]})
check("current segment target accepts an explicit application", got["currentApply"]["ok"], True)
check("actual editor commit updates its prompt, citations, chips and persistence", got["current"],
      {"globalUnchanged": True, "firstUnchanged": True,
       "prompt": "@subject turns.\n\nDolly toward @subject; keep @ref-1.",
       "input": "@subject turns.\n\nDolly toward @subject; keep @ref-1.", "citations": ["ref-1"],
       "commits": True, "renders": 1, "edited": "true", "chips": 1})
check("alternate global target also accepts an explicit application", got["globalApply"]["ok"], True)
check("real serialization preserves target-specific tracking without touching audio or seams", got["persisted"],
      {"global": "A shared studio.\n\nSoft practical light.",
       "second": "@subject turns.\n\nDolly toward @subject; keep @ref-1.",
       "globalItems": ["lighting/soft-light"], "secondItems": ["camera-movement/dolly-in"], "protectedUnchanged": True})
for field in ("switchedTarget", "removedTarget"):
    check(field + " rejects outdated owner without mutation", [got[field]["result"]["ok"], got[field]["unchanged"]], [False, True])
check("manual prompt edits make destructive tracking actions inert", got["manualEdit"],
      {"stale": True, "disabled": True, "remove": {"ok": False, "reason": "text-changed"},
       "undo": {"ok": False, "reason": "text-changed"}, "unchanged": True})
for index, result in enumerate(got["refined"]):
    check(f"refinement representation {index + 1} offers explicit acknowledgement and keeps undo", result,
          {"gate": True, "refused": True, "acknowledged": True, "disabled": True, "kept": True,
           "undo": True, "restored": True, "commits": 2, "audio": "No changes."})
check("legacy refinement embedding globals blocks misleading global application", got["legacy"],
      {"warning": True, "blocked": True, "unchanged": True})
check("shot-scoped refinements do not block independent global instructions", got["shotScopedAllowsGlobal"], True)
check("sections-only refinements do not falsely claim to embed the global body", got["sectionsOnlyAllowsGlobal"], True)
check("last chip removal leaves a visible working undo action", got["lastRemoval"],
      {"visible": True, "hasUndo": True, "prompt": "Base.", "afterUndo": "Base.\n\nMove."})
check("technique transactions honor both ordinary local reference citation hooks", got["localReferenceLifecycle"],
      {"wakesOnApply": True, "mutesAfterLastMentionRemoved": True, "wakesOnUndoRemove": True, "keptFile": True,
       "mutesOnUndoApply": True, "restoresWrittenPrompt": True, "otherMentionKeepsReference": True})
check("applying from a segment to global refreshes the parent prompt and chips", got["segmentToGlobal"],
      {"ok": True, "writes": 1, "prompt": "A shared studio.\n\nWindow bounce light.",
       "displayedPrompt": "A shared studio.\n\nWindow bounce light.", "chips": 1})
check("a replaced timeline invalidates its previous modal target", [got["replacedTimeline"]["result"]["ok"], got["replacedTimeline"]["oldUnchanged"]], [False, True])

"""Explicitly citing a muted reference restores it through every menu path.

Runs the real PromptBox and CreatorEditor over the shared DOM shim. No model,
ComfyUI server, or user files are needed.

    python tests/test_reference_reactivation.py
"""

import layout
from domshim import DOM
from harness import check

layout.skip_without_node()

SCRIPT = r'''
const S = await import("./web/creator/state.js");
const { PromptBox } = await import("./web/creator/prompt.js");
const { CreatorEditor } = await import("./web/creator/editor.js");
const out = {};
const file = (handle, kind = "image", extra = {}) => ({
  handle, kind, role: "reference", filename: `${handle}.${kind === "image" ? "png" : kind === "video" ? "mp4" : "wav"}`,
  ...(kind === "video" ? { track: "picture", trim: [0, 1] } : {}), ...extra,
});
function host(assets, cast = []) {
  const state = S.parseState(JSON.stringify({ assets, subjects: cast }));
  // Avoid mounting unrelated model controls. These are the real host methods
  // used by a prompt edit; commit only records that the host would redraw.
  const editor = Object.assign(Object.create(CreatorEditor.prototype), {
    state, castPiece: state, piece: null, commits: 0, flashes: [],
    commit() { this.commits++; }, flash(text) { this.flashes.push(text); },
  });
  state.subjects = cast;
  const events = [];
  const box = new PromptBox({
    getState: () => state, getCast: () => cast,
    onInput: (text) => { state.prompt = text; events.push("input"); },
    onUncited: (handles) => editor.dropCited(handles),
    onCited: (handles) => { events.push("cited"); editor.liveCited(handles); },
    onAttach: () => null, attachBlocked: () => null,
  });
  document.body.appendChild(box.root);
  editor.prompt = box;
  return { editor, state, box, events };
}

// The shared shim has no real selection. Model just the collapsed caret used
// by insertChip's normal menu path, so this tests that branch as well as the
// fallback that appends when focus moved to the menu.
function atCaret(box, handle) {
  const createRange = document.createRange;
  const getSelection = window.getSelection;
  let caret = box.root;
  document.createRange = () => ({
    setStart(node) { caret = node; }, collapse() {},
    insertNode(node) { box.root.appendChild(node); },
  });
  window.getSelection = () => ({
    rangeCount: 1, getRangeAt: () => ({ startContainer: caret, startOffset: 0 }),
    removeAllRanges() {}, addRange() {},
  });
  try { box.insertChip(handle); }
  finally { document.createRange = createRange; window.getSelection = getSelection; }
}

// Re-inserting via the menu, including its no-selection fallback. Cast names
// are arbitrary; no behavior depends on the spelling @subject.
for (const [name, kind] of [["img-1", "image"], ["vid-1", "video"], ["aud-1", "audio"]]) {
  for (const path of ["insert", "caret", "write"]) {
    const { state, box, events } = host([file(name, kind)]);
    box.setValue(`@${name}`);
    box.root.replaceChildren();
    box.onEdit();
    const muted = state.assets[0].enabled === false;
    events.length = 0;
    if (path === "insert") box.insertChip(name);
    else if (path === "caret") atCaret(box, name);
    else box.writeName("", null, name);
    out[`${name}-${path}`] = { muted, live: !S.muted(state.assets[0]), events,
      named: state.prompt.includes(`@${name}`), count: state.assets.length };
  }
}

for (const path of ["insert", "write", "shelf"]) {
  const cast = [{ handle: "lead", from: ["img-1"], motion: ["vid-1"], voice: "aud-1" }];
  const { state, box, editor } = host([
    file("img-1"), file("vid-1", "video"), file("aud-1", "audio"),
    file("img-2", "image", { enabled: false }),
  ], cast);
  box.setValue("@lead waits.");
  box.root.replaceChildren();
  box.onEdit();
  const muted = state.assets.slice(0, 3).every(S.muted);
  if (path === "insert") box.insertChip("lead");
  else if (path === "write") box.writeName("", null, "lead");
  else editor.citeName("lead");
  out[`cast-${path}`] = { muted, live: state.assets.slice(0, 3).every(a => !S.muted(a)),
    unrelatedMuted: S.muted(state.assets[3]), claims: cast[0].from };
}

// Loading a workflow is not a request to unmute a reference. The user may
// have muted it deliberately with its name still in the sentence.
{
  const { state, box, events } = host([file("img-1", "image", { enabled: false })]);
  box.setValue("@img-1 stays attached, but muted.");
  out.reopen = { muted: S.muted(state.assets[0]), events: [...events] };
  // Selecting a name again is an explicit request even if its old chip was
  // restored already. No empty-text transition is required to recover it.
  box.writeName(state.prompt, null, "img-1");
  out.savedRecited = !S.muted(state.assets[0]);
}

// A card cannot wake the piece's shared pool or a sibling's references.
{
  const { state, editor } = host([file("img-1", "image", { enabled: false })]);
  state.pool = [file("ref-1", "image", { enabled: false })];
  editor.liveCited(["ref-1"]);
  out.pool = { muted: S.muted(state.pool[0]), localMuted: S.muted(state.assets[0]) };
}

// Re-citation keeps the same capacity gate as the reference mute button.
{
  const { state, box, editor } = host([
    ...Array.from({ length: 9 }, (_, i) => file(`img-${i + 1}`)),
    file("img-10", "image", { enabled: false }),
  ]);
  box.insertChip("img-10");
  out.cap = { muted: S.muted(state.assets[9]), warned: editor.flashes.length > 0 };
}
console.log(JSON.stringify(out));
'''

with layout.pack(skip=["atlas"]) as target:
    result = layout.in_pack(DOM + SCRIPT, target)

for name in ("img-1", "vid-1", "aud-1"):
    for path in ("insert", "caret", "write"):
        check(f"{name} restores its existing file via {path}", result[f"{name}-{path}"],
              {"muted": True, "live": True, "events": ["input", "cited"],
               "named": True, "count": 1})
for path in ("insert", "write", "shelf"):
    check(f"cast re-citation via {path} restores looks, motion, and voice only",
          result[f"cast-{path}"], {"muted": True, "live": True,
                                  "unrelatedMuted": True, "claims": ["img-1"]})
check("reopening does not silently unmute saved references", result["reopen"],
      {"muted": True, "events": []})
check("explicit re-citation recovers an already visible saved name", result["savedRecited"], True)
check("a shot leaves shared pool mute decisions alone", result["pool"],
      {"muted": True, "localMuted": True})
check("re-citation refuses and explains an over-cap reference", result["cap"],
      {"muted": True, "warned": True})

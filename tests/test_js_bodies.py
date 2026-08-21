"""The frontend loads, and all three node bodies actually mount.

Everything else in `tests/` checks what the backend builds. This checks the half
that runs in the browser, because the failure it exists for is silent from
Python's side and total from the user's: one throw anywhere in the module graph
and `app.registerExtension` never runs, so every node in the pack renders as its
raw widgets and nothing says why.

That has now happened twice for reasons no syntax check could catch — the CSS
lives in template literals (one per module under `js/minimax_creator/styles/`,
concatenated by `styles.js`), so a backtick inside a CSS comment ends the string
and turns the rest of the stylesheet into code that still parses. `node --check`
passes; the extension is dead.

So this imports the extension for real, against a DOM small enough to write down
(`dom.mjs`, generated below) and stubs for the three ComfyUI modules the pack
imports. Then it builds each node's body and reads the rendered text back. It is
not a rendering test — the shim has no layout and no CSS — it answers "did it
mount, and is the expected furniture in it".

    python3 tests/test_js_bodies.py

Skips itself if node is not installed.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---- the stylesheet is one template literal per file ------------------------
#
# Every module under js/minimax_creator/styles/ is `export const css = ` and then
# the whole stylesheet, so one stray backtick — in a comment, around a property
# name, anywhere — closes the literal early and the rest of the file parses as
# JavaScript. What that costs is not the rule: it is the module, and with it the
# extension, and with that every node body on the canvas.
#
# The run below already catches it, as an import stack twenty frames deep with
# nothing in it about backticks. This says which file and which line.

STYLES = os.path.join(ROOT, "js", "minimax_creator", "styles")
stray = []
for name in sorted(os.listdir(STYLES)):
    if not name.endswith(".js"):
        continue
    inside = False
    with open(os.path.join(STYLES, name), encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            # The header comment above the literal says the rule and so contains
            # the very characters it is about. Only what is inside counts.
            if line.strip() == "export const css = `":
                inside = True
                continue
            if line.strip() == "`;":
                inside = False
                continue
            if inside and ("`" in line or "${" in line):
                stray.append(f"{name}:{number}: {line.strip()[:70]}")
if stray:
    print("a stylesheet has a backtick or ${} outside its delimiters — the module "
          "will not parse:")
    for line in stray:
        print("  -", line)
    sys.exit(1)


if shutil.which("node") is None:
    print("skipped: node is not installed")
    sys.exit(0)

from domshim import DOM  # noqa: E402  (after the node check above)

STUBS = {
    # `queuePrompt` and `graphToPrompt` are here because the pack wraps them —
    # what the last queue ran on is read off the serialized prompt, so the stub
    # has to be able to hand one back.
    "app.js": """
export const app = {
  registerExtension: (e) => { globalThis.__ext = e; },
  graph: null, canvas: null,
  async queuePrompt() { return this.graphToPrompt(); },
  async graphToPrompt() { return globalThis.__prompt ?? { output: {} }; },
};
""",
    # `fetchApi` answers the settings route the way the server does, and records
    # what was posted — which is what lets the settings page be exercised here.
    "api.js": """
globalThis.__posted = [];
let stored = { video_crf: 23, video_prefix: "minimax/renders/H3",
               image_prefix: "minimax/stills/prestage" };
export const api = {
  addEventListener() {}, removeEventListener() {}, apiURL: (u) => u,
  async fetchApi(route, options) {
    if (route.endsWith("/settings") && options?.method === "POST") {
      const patch = JSON.parse(options.body);
      globalThis.__posted.push(patch);
      stored = { ...stored, ...patch };
    }
    return { ok: true, status: 200, json: async () => ({ settings: stored }) };
  },
};
""",
    "widgets.js": "export const ComfyWidgets = {};",
}

CHECK = """
await import("./dom.mjs");
await import("./js/minimax_creator.js");
const S = await import("./js/minimax_creator/state.js");
const { app } = await import("../scripts/app.js");
const ext = globalThis.__ext;
// The seed memory is installed here, the same way the frontend installs it.
await ext.setup?.();

const out = { registered: ext?.name ?? null, nodes: {}, still: null, errors: [] };

const fakeNode = (comfyClass, widgetName, blob) => ({
  comfyClass, id: 3, size: [400, 300], pos: [0, 0], title: comfyClass,
  widgets: [
    { name: widgetName, value: blob, type: "customtext", options: {}, computeSize: () => [0, 0] },
    // The after-generate control is a *linked* widget the frontend hangs off the
    // seed, which is where the pack finds it — and it arrives on "randomize",
    // which is the thing being overridden.
    { name: "seed", value: 0,
      linkedWidgets: [{ name: "control_after_generate", value: "randomize", options: {} }] },
    { name: "steps", value: 20 }, { name: "cfg", value: 1 },
    { name: "sampler_name", value: "res_multistep" }, { name: "scheduler", value: "simple" },
  ],
  addDOMWidget(name, type, el) { this.dom = el; return { name, element: el }; },
  graph: { setDirtyCanvas() {}, _nodes: [], add() {} },
  properties: {},
});

// The two piece ids are one node now, so what a body wears is decided by the
// piece and not by which id was dropped: one shot gets that shot's editor, and
// a strip gets the strip's summary. Both are driven here, under the id a saved
// workflow would carry them under.
const ONE_SHOT = JSON.stringify({
  version: 2, prompt: "", models: {},
  segments: [{ prompt: "", assets: [], loras: [], duration_s: 6 }],
});
const A_STRIP = JSON.stringify({
  version: 2, prompt: "", models: {},
  segments: [{ prompt: "shot 1", assets: [], loras: [], duration_s: 5 },
             { prompt: "shot 2", assets: [], loras: [], duration_s: 5 }],
});

for (const [cls, widget, blob] of [
  ["MiniMaxH3Creator", "creator_data", ONE_SHOT],
  ["MiniMaxH3Timeline", "timeline_data", A_STRIP],
  ["MiniMaxH3PreStage", "prestage_data", "{}"],
  ["MiniMaxH3PreStage", "prestage_data", JSON.stringify({ arch: "minimax" })],
]) {
  const node = fakeNode(cls, widget, blob);
  try {
    await ext.nodeCreated(node);
    const key = cls + (cls === "MiniMaxH3PreStage" && blob !== "{}" ? " (H3 still)" : "");
    out.nodes[key] = { mounted: !!node.mmcBody && !!node.dom,
                       body: node.mmcBody?.editor?.constructor.name
                          ?? node.mmcBody?.constructor.name };
    if (cls === "MiniMaxH3PreStage" && blob !== "{}") out.still = node.mmcBody.root.text;
    if (cls === "MiniMaxH3Creator") out.creator = node.mmcBody.root.text;
  } catch (error) {
    out.errors.push(`${cls}: ${error.message}`);
  }
}

// Somebody typed into the sentence. The `@` menu offers the cast library where
// the host owns a piece to cast her into, and picking her is what attaches her
// files — so the hook the menu calls has to land a whole subject, not a name.
try {
  const node = fakeNode("MiniMaxH3Creator", "creator_data", ONE_SHOT);
  await ext.nodeCreated(node);
  const hooks = node.mmcBody.faceBody().prompt.hooks;
  const handle = await hooks.castFromLibrary({
    handle: "anna", takes: "person", description: "dark coat",
    files: [{ slot: "from", filename: "anna/face.png", kind: "image" },
            { slot: "voice", filename: "anna/voice.wav", kind: "audio" }],
  });
  const piece = node.mmcBody.timeline;
  const shot = piece.segments[0];
  out.castFromMention = {
    handle,
    cast: (piece.subjects ?? []).length,
    // Her files are ordinary references on the shot the face is drawing — a
    // piece of one shot has no pool worth the name.
    attached: (shot.assets ?? []).map((asset) => `${asset.handle}=${asset.filename}`).join(","),
    poolLeftAlone: (piece.assets ?? []).length === 0,
    voiceBound: piece.subjects?.[0]?.voice === shot.assets?.[1]?.handle,
    // Nothing to cast her into, nothing offered: a PreStage's prompt box has no
    // piece behind it, so the roster stays out of its menu.
    notOnAPreStage: null,
  };
  const still = fakeNode("MiniMaxH3PreStage", "prestage_data",
                         JSON.stringify({ arch: "minimax" }));
  await ext.nodeCreated(still);
  out.castFromMention.notOnAPreStage =
    !still.mmcBody.editor?.prompt?.hooks?.castFromLibrary;
} catch (error) {
  out.errors.push(`castFromMention: ${error.message}`);
}

// …and her name is written into the sentence by string surgery rather than by
// caret surgery, because casting her rebuilds the box the caret was in. This is
// the bug: the "@" was typed, she was cast, and the name never arrived.
try {
  const node = fakeNode("MiniMaxH3Creator", "creator_data", ONE_SHOT);
  await ext.nodeCreated(node);
  const editor = node.mmcBody.faceBody();
  const box = editor.prompt;
  box.setValue("a woman at the door, @");
  editor.state.prompt = box.getValue();
  const before = box.getValue();
  const handle = await box.hooks.castFromLibrary({
    handle: "anna", takes: "person",
    files: [{ slot: "from", filename: "anna/face.png", kind: "image" }],
  });
  box.writeName(before, { at: before.length - 1, length: 1 }, handle);
  out.wroteName = {
    // In the state, which is what queues…
    state: editor.state.prompt,
    // …and in the box, read back through the chips it was rebuilt into.
    value: box.getValue(),
  };
} catch (error) {
  out.errors.push(`wroteName: ${error.message}`);
}

// The face is typed into, and the window is where a prompt goes when it stops
// fitting. The box on the face is the live one — that is the whole point of it
// being there — and the corner control opens the same body full size.
try {
  const find = (root, cls) => {
    let hit = null;
    const walk = (n) => {
      if (!hit && String(n.className ?? "").split(" ").includes(cls)) hit = n;
      (n.children ?? []).forEach(walk);
    };
    walk(root);
    return hit;
  };
  const node = fakeNode("MiniMaxH3Creator", "creator_data", JSON.stringify({
    version: 1, prompt: "a long sentence about a lighthouse. ".repeat(40),
    assets: [], loras: [],
  }));
  await ext.nodeCreated(node);
  const expand = find(node.mmcBody.root, "mmc-expand");
  const before = document.body.children.length;
  expand?.listeners?.click?.[0]?.();
  const sheet = document.body.children.at(-1);
  out.face = {
    boxOnFace: !!find(node.mmcBody.root, "mmc-prompt"),
    expand: !!expand,
    opened: document.body.children.length === before + 1,
    boxInSheet: !!find(sheet, "mmc-prompt"),
    // The window's box is a different box over the same state, so the face's
    // own is still there behind it.
    sameState: find(sheet, "mmc-prompt") !== find(node.mmcBody.root, "mmc-prompt"),
  };
} catch (error) {
  out.errors.push(`node face: ${error.message}`);
}

// The rewrite is edited in place, never rebuilt under the caret.
//
// Typing in the refined box commits, and on the node face a commit re-renders
// the whole body — which used to replace the very textarea being typed into.
// A browser gives the focus to nobody when the element holding it is removed,
// and the replacement starts scrolled to the top, so the box took one character
// per click and jumped back to the top after each one. Nothing here has a caret
// to lose, so what is checked is the thing the caret rides on: the box you are
// writing in has to be the same object afterwards.
try {
  const find = (root, cls) => {
    let hit = null;
    const walk = (n) => {
      if (!hit && String(n.className ?? "").split(" ").includes(cls)) hit = n;
      (n.children ?? []).forEach(walk);
    };
    walk(root);
    return hit;
  };
  // No `model` on the rewrite: with none chosen here either, the panel's head
  // says the same thing before and after the second rewrite lands below, which
  // is what makes that one a refresh rather than a rebuild.
  const node = fakeNode("MiniMaxH3Creator", "creator_data", JSON.stringify({
    version: 2, prompt: "", models: {},
    segments: [{
      prompt: "a lighthouse", assets: [], loras: [], duration_s: 6, soundscape: "surf",
      refined: { body: "A lighthouse at dusk.", source: "a lighthouse", enabled: true,
                 sections: { subject_definitions: "", summary: "", retention_analysis: "" } },
    }],
  }));
  await ext.nodeCreated(node);
  const body = node.mmcBody;
  const type = (box, text) => {
    box.value = text;
    box.listeners.input.forEach((fn) => fn({ target: box }));
  };

  const first = find(body.root, "mmc-refined-box");
  document.activeElement = first;
  type(first, "A lighthouse at dusk, lamp turning.");
  const afterOne = find(body.root, "mmc-refined-box");
  type(afterOne, "A lighthouse at dusk, lamp turning slowly.");

  out.refineBox = {
    drawn: !!first,
    // The whole bug, in two comparisons.
    sameAfterOne: first === afterOne,
    sameAfterTwo: first === find(body.root, "mmc-refined-box"),
    stillFocused: document.activeElement === first,
    // ...and it is still writing through to the blob on every one of them.
    written: JSON.parse(node.widgets[0].value).segments[0].refined.body,
  };

  // The other half: a panel that is not rebuilt still has to show a rewrite
  // that lands on top of an identical one, or refining twice would leave the
  // first rewrite's prose on screen.
  body.faceEditor.refinePanel.apply(
    { soundscape: "surf", music: "", seen: "", problems: [],
      sections: { subject_definitions: "", summary: "", retention_analysis: "" } },
    { body: "A second rewrite." });
  const afterApply = find(body.root, "mmc-refined-box");
  out.refineBox.applied = afterApply?.value;
  out.refineBox.sameAfterApply = first === afterApply;
} catch (error) {
  out.errors.push(`refine box: ${error.message}`);
}

// A strip with supplied footage in it, on the node and in the modal.
//
// A clip card is not a generation and holds none of one's machinery — no
// assets, no prompt, no checkpoint — so every accessor the two renders call
// over the segments has to answer for it without asking it a sampler's
// question. One that does throws mid-render and takes the whole body with it,
// which is invisible from Python and total from the user's side: the strip
// stops redrawing and the card never appears.
try {
  const clipBlob = JSON.stringify({
    version: 2, render: "chained", prompt: "a corridor", aspect: "16:9", short_edge: 768,
    segments: [
      { prompt: "shot 1", duration_s: 5, assets: [], loras: [] },
      { kind: "clip", filename: "footage/take-3.mp4", duration_s: 12.5,
        width: 1920, height: 1080, continue: true, feather: 22 },
      { prompt: "shot 3", duration_s: 5, assets: [], loras: [], continue: true },
    ],
  });
  const node = fakeNode("MiniMaxH3Timeline", "timeline_data", clipBlob);
  await ext.nodeCreated(node);
  const body = node.mmcBody;
  out.clip = { mounted: !!node.dom, node: body.root.text };
  const { openTimeline } = await import("./js/minimax_creator/timeline.js");
  openTimeline({ timeline: body.timeline, onCommit: () => body.commit() });
  await new Promise((done) => setTimeout(done, 0));
  out.clip.modal = document.body.children.at(-1).text;
  // ...and the strip still redraws once something on it is touched, which is
  // the path an added clip actually takes.
  body.commit();
  out.clip.recommitted = body.root.children.length > 0;
} catch (error) {
  out.errors.push(`clip card: ${error.message}`);
}

// A piece cannot be empty.
//
// The strip could hold no cards at all while it was a node of its own, and the
// two ways to begin one were the whole of what it showed. Under one node that
// state is a dead end: it is reached by deleting cards, and what it leaves is a
// summary reporting nothing with a button that opens a strip holding nothing.
// So a piece is at least one shot, and clearing the last card blanks it instead
// — from a blob that says otherwise, from a fresh node, and from the delete.
try {
  const node = fakeNode("MiniMaxH3Timeline", "timeline_data", "{}");
  await ext.nodeCreated(node);
  const body = node.mmcBody;
  const { openTimeline: openTimelineModal } = await import("./js/minimax_creator/timeline.js");
  out.empty = {
    // An empty blob opens as one blank shot, which is the Creator's own default.
    cards: body.timeline.segments.length,
    // ...and writes one back. Committed first on purpose: the widget still holds
    // the blob it was given until something commits, so reading it before that
    // would be reading the input rather than what the node now holds.
    written: (() => { body.commit(); return JSON.parse(body.read()).segments.length; })(),
    wears: body.editor ? "shot" : "strip",
    // ...and one written to hold none does too.
    fromEmptyList: (() => {
      const other = S.parseTimeline(JSON.stringify({ version: 2, segments: [] }));
      return other.segments.length;
    })(),
    // Deleting down to nothing leaves a blank shot rather than an empty piece,
    // and the face goes back to being that shot's editor.
    cleared: await (async () => {
      const two = fakeNode("MiniMaxH3Creator", "creator_data", JSON.stringify({
        version: 2, prompt: "", models: {},
        segments: [{ prompt: "shot 1", assets: [], loras: [], duration_s: 5 },
                   { prompt: "shot 2", assets: [], loras: [], duration_s: 5 }],
      }));
      await ext.nodeCreated(two);
      openTimelineModal({ timeline: two.mmcBody.timeline,
                          onCommit: () => two.mmcBody.commit() });
      await new Promise((done) => setTimeout(done, 0));
      two.mmcBody.timeline.segments.splice(0, 2);
      two.mmcBody.commit();
      return { cards: two.mmcBody.timeline.segments.length,
               prompt: two.mmcBody.timeline.segments[0].prompt,
               wears: two.mmcBody.editor ? "shot" : "strip" };
    })(),
    // ...and the strip still redraws once something is added, which is the path
    // every piece takes on its first click.
    added: (() => {
      body.timeline.segments.push(S.continuingSegment());
      body.commit();
      return S.passes(body.timeline).length;
    })(),
  };
} catch (error) {
  out.errors.push(`empty timeline: ${error.message}`);
}

// Clear: the piece goes, the machine stays.
//
// The line it draws between the two halves is the whole feature, so it is
// driven through the rail rather than through `S.clearPiece` — a tool the face
// does not draw is the same bug to the user as one that empties the wrong half.
try {
  const all = (root, cls) => {
    const hits = [];
    const walk = (n) => {
      if (String(n.className ?? "").split(" ").includes(cls)) hits.push(n);
      (n.children ?? []).forEach(walk);
    };
    walk(root);
    return hits;
  };
  const press = (node) => node?.listeners?.click?.[0]?.();
  const shot = (prompt) => ({ prompt, assets: [], loras: [], duration_s: 5 });
  const written = (segments) => JSON.stringify({
    version: 2,
    prompt: "the whole piece",
    soundscape: "rain",
    music: "strings",
    aspect: "9:16",
    short_edge: 512,
    assets: [{ handle: "ref-1", kind: "image", role: "reference", filename: "sheet.png" }],
    // Somebody cast into the piece. Written here with the prompt that cites
    // them, and so gone with it — a subject left behind is a shelf of people
    // the next scene never asked for, still riding down onto every card.
    subjects: [{ handle: "anna", from: ["ref-1"], takes: "person" }],
    loras: [{ name: "style.safetensors", strength: 0.8 }],
    models: { fl2va: "fl2va.safetensors", clip: "clip.safetensors", vae: "vae.safetensors" },
    turbo: { lora: "turbo.safetensors" },
    segments,
  });

  const strip = fakeNode("MiniMaxH3Creator", "creator_data",
                         written([shot("shot 1"), shot("shot 2")]));
  await ext.nodeCreated(strip);
  const tool = () => all(strip.mmcBody.root, "mmc-tool-danger")[0];
  out.clear = { onStrip: Boolean(tool()) };
  // The first press only arms it — the piece is still whole afterwards, and the
  // label is now the question.
  press(tool());
  out.clear.armedLabel = (tool()?.text ?? "").trim();
  out.clear.survivesOnePress = strip.mmcBody.timeline.segments.length;
  press(tool());

  const after = strip.mmcBody.timeline;
  out.clear.kept = {
    models: after.models.fl2va,
    turbo: after.turbo.lora,
    loras: after.loras.length,
    aspect: after.aspect,
    short_edge: after.short_edge,
  };
  out.clear.emptied = {
    prompt: after.prompt,
    soundscape: after.soundscape,
    music: after.music,
    assets: after.assets.length,
    cast: after.subjects.length,
    cards: after.segments.length,
    cardPrompt: after.segments[0].prompt,
  };
  // ...and in the widget, which is what actually queues.
  out.clear.blob = JSON.parse(strip.mmcBody.read());
  // Nobody rides down onto the blank card either — `syncCanvas` mirrors the
  // cast onto every segment, and a stale copy there is what the prompt box's
  // chips and `mode()` would still be reading.
  out.clear.cardCast = (after.segments[0].cast ?? []).length;
  // Emptied, the tool has nothing left to do and says so rather than arming
  // over an empty piece.
  out.clear.disabledAfter = tool()?.attrs?.disabled !== undefined;

  // The other face: one shot wears that shot's editor, and Clear is in its rail
  // too — the piece is what it empties from either.
  const lone = fakeNode("MiniMaxH3Creator", "creator_data", written([shot("the only shot")]));
  await ext.nodeCreated(lone);
  const loneTool = () => all(lone.mmcBody.root, "mmc-tool-danger")[0];
  out.clear.onLoneShot = Boolean(loneTool());
  press(loneTool());
  press(loneTool());
  out.clear.loneEmptied = lone.mmcBody.timeline.segments[0].prompt;
  out.clear.loneKept = lone.mmcBody.timeline.models.fl2va;
} catch (error) {
  out.errors.push(`clear: ${error.message}`);
}

// LoRAs: muted rather than removed, swapped in place, and named wherever a
// piece is written.
//
// The stack used to be a row of labels with one control on it — the ✕ — so the
// ordinary question "is this LoRA the reason it looks like that" cost the
// strength, the checkpoint and the trigger words to ask. On the strip it cost
// more than that: the timeline drew a pill counting the stack and nothing that
// named it, so the answer was not reachable at all.
try {
  const all = (root, cls) => {
    const hits = [];
    const walk = (n) => {
      if (String(n.className ?? "").split(" ").includes(cls)) hits.push(n);
      (n.children ?? []).forEach(walk);
    };
    walk(root);
    return hits;
  };
  const click = (node) => node?.listeners?.click?.[0]?.();
  const stack = [{ name: "styles/glow.safetensors", strength: 0.8, triggers: ["glow"] },
                 { name: "turbo.safetensors", strength: 1 }];

  // The shot face, where the stack belongs to the shot.
  // Nothing written on the piece: a piece prompt, a piece reference or a piece
  // LoRA is what makes the node wear the strip instead. See `loneShot`.
  const creator = fakeNode("MiniMaxH3Creator", "creator_data", JSON.stringify({
    version: 2, prompt: "", assets: [],
    segments: [{ prompt: "a lighthouse", assets: [], loras: stack, duration_s: 5 }],
  }));
  await ext.nodeCreated(creator);
  const names = () => all(creator.mmcBody.root, "mmc-asset-name");
  const entry = () => creator.mmcBody.timeline.segments[0].loras[0];
  out.loras = { named: names().map((n) => n.text.trim()) };
  // The name is the mute, and it is the same click back.
  click(names()[0]);
  out.loras.muted = entry().enabled;
  out.loras.stillThere = {
    count: creator.mmcBody.timeline.segments[0].loras.length,
    strength: entry().strength,
    triggers: (entry().triggers ?? []).length,
  };
  // ...and the run is told: a muted LoRA is off the checkpoint and its trigger
  // words are off the front of the prompt.
  out.loras.active = S.activeLoras(creator.mmcBody.timeline.segments[0]).length;
  out.loras.triggers = S.promptTriggers(creator.mmcBody.timeline.segments[0]).length;
  out.loras.serialized = (JSON.parse(creator.mmcBody.read()).segments[0].loras ?? [])[0]?.enabled;
  click(names()[0]);
  out.loras.backOn = entry().enabled;

  // The strip, where it belongs to the piece and was drawn nowhere.
  const strip = fakeNode("MiniMaxH3Creator", "creator_data", JSON.stringify({
    version: 2, prompt: "the piece", assets: [], loras: stack,
    segments: [{ prompt: "shot 1", assets: [], loras: [], duration_s: 5 },
               { prompt: "shot 2", assets: [], loras: [], duration_s: 5 }],
  }));
  await ext.nodeCreated(strip);
  const { openTimeline: openStrip } = await import("./js/minimax_creator/timeline.js");
  openStrip({ timeline: strip.mmcBody.timeline, onCommit: () => strip.mmcBody.commit() });
  await new Promise((done) => setTimeout(done, 0));
  const sheet = document.body.children.at(-1);
  out.loras.onStrip = all(sheet, "mmc-asset-name").map((n) => n.text.trim());
  click(all(sheet, "mmc-asset-name")[1]);
  out.loras.stripMuted = strip.mmcBody.timeline.loras[1].enabled;
  // The pill over the chips counts what is in the run, so it moves with them.
  out.loras.stripActive = S.activeGlobalLoras(strip.mmcBody.timeline).length;

  // The swap: a different file in the same slot, keeping what the slot is for.
  const piece = { loras: [{ name: "a.safetensors", strength: 0.8, modes: ["fl2va"], enabled: false },
                          { name: "b.safetensors", strength: 1, modes: ["fl2va", "ref2va"] }] };
  S.replaceLora(piece, "a.safetensors", "c.safetensors", ["trig"], 0.55);
  out.loras.swapped = {
    order: piece.loras.map((l) => l.name),
    strength: piece.loras[0].strength,
    modes: piece.loras[0].modes,
    muted: piece.loras[0].enabled,
    triggers: piece.loras[0].triggers,
  };
  // Onto a file already in the stack: the same LoRA cannot be patched twice, so
  // the old slot goes rather than the stack holding it under two names.
  S.replaceLora(piece, "c.safetensors", "b.safetensors");
  out.loras.swappedOntoTwin = piece.loras.map((l) => l.name);
} catch (error) {
  out.errors.push(`loras: ${error.message}`);
}

// Two controls that write through somebody else's callback, and were dead.
//
// The render toggle wrote merge flags, which are statements about the seam in
// front of a card — so on a strip of one card, where there is no seam, it wrote
// nothing and the control did not move. The route badge in the shot window
// writes through the *node's* editor, which re-rendered the face and left the
// window drawing the answer from before the click.
try {
  const all = (root, cls) => {
    const hits = [];
    const walk = (n) => {
      if (String(n.className ?? "").split(" ").includes(cls)) hits.push(n);
      (n.children ?? []).forEach(walk);
    };
    walk(root);
    return hits;
  };
  const click = (node) => node?.listeners?.click?.[0]?.();

  // One card, and the toggle at both ends of its travel.
  const node = fakeNode("MiniMaxH3Timeline", "timeline_data", JSON.stringify({
    version: 2, segments: [{ prompt: "shot 1", duration_s: 5, assets: [], loras: [] }],
  }));
  await ext.nodeCreated(node);
  const { openTimeline: openTimelineModal } = await import("./js/minimax_creator/timeline.js");
  openTimelineModal({ timeline: node.mmcBody.timeline, onCommit: () => node.mmcBody.commit() });
  await new Promise((done) => setTimeout(done, 0));
  const opts = () => all(document.body.children.at(-1), "mmc-tl-render-opt");
  click(opts()[1]);
  const toSingle = node.mmcBody.timeline.render;
  click(opts()[0]);
  const backToChained = node.mmcBody.timeline.render;

  // The route badge, clicked in the window rather than on the face.
  const creator = fakeNode("MiniMaxH3Creator", "creator_data", JSON.stringify({
    version: 1, prompt: "a lighthouse", assets: [], loras: [],
  }));
  await ext.nodeCreated(creator);
  click(all(creator.mmcBody.root, "mmc-expand")[0]);
  const sheet = document.body.children.at(-1);
  const badge = () => all(sheet, "mmc-mode")[0];
  const before = badge()?.text;
  click(badge());
  out.controls = {
    toSingle, backToChained,
    route: creator.mmcBody.timeline.models.route,
    // The window has to redraw itself: the click landed on the node's editor.
    badgeMoved: badge()?.text !== before,
  };
} catch (error) {
  out.errors.push(`live controls: ${error.message}`);
}

// One window, opened from two places.
//
// A shot's body over a shot's state is the same thing whether the shot is a
// card on a strip or the node's own — and for a while it was two windows, built
// and sized separately, so the one the face opened drifted: full-bleed, an
// uncapped prompt box, a body centred in a column of its own. Both go through
// `openEditorSheet` now, and this is what says so.
try {
  const all = (root, cls) => {
    const hits = [];
    const walk = (n) => {
      if (String(n.className ?? "").split(" ").includes(cls)) hits.push(n);
      (n.children ?? []).forEach(walk);
    };
    walk(root);
    return hits;
  };
  const click = (node) => node?.listeners?.click?.[0]?.();
  const sheetClass = () => String(all(document.body.children.at(-1), "mmc-modal")[0]?.className ?? "");

  const creator = fakeNode("MiniMaxH3Creator", "creator_data", JSON.stringify({
    version: 1, prompt: "a lighthouse", assets: [], loras: [],
  }));
  await ext.nodeCreated(creator);
  click(all(creator.mmcBody.root, "mmc-expand")[0]);
  const fromFace = sheetClass();

  const node = fakeNode("MiniMaxH3Timeline", "timeline_data", JSON.stringify({
    version: 2, segments: [{ prompt: "shot 1", duration_s: 5, assets: [], loras: [] }],
  }));
  await ext.nodeCreated(node);
  const { openTimeline: openTimelineModal } = await import("./js/minimax_creator/timeline.js");
  openTimelineModal({ timeline: node.mmcBody.timeline, onCommit: () => node.mmcBody.commit() });
  await new Promise((done) => setTimeout(done, 0));
  click(all(document.body.children.at(-1), "mmc-tl-edit")[0]);
  const fromCard = sheetClass();

  out.window = {
    fromFace, fromCard,
    same: !!fromFace && fromFace === fromCard,
    // ...and it is the shot's body in there, not a bare box.
    body: all(document.body.children.at(-1), "mmc-prompt").length === 1,
  };
} catch (error) {
  out.errors.push(`editor window: ${error.message}`);
}

// A piece that *opens* on supplied footage.
//
// The strip has to hold a card, so a new node starts as one empty shot — which
// is what used to make the first card of every piece a generation. The card is
// a placeholder now (`state.blankSegment`) and a clip cut into a strip that is
// still nothing but that card takes its place, so both renders have to survive
// a clip at index 0: no pass in front of it to inherit from, and no seam.
try {
  const firstBlob = JSON.stringify({
    version: 2, render: "chained", prompt: "", aspect: "16:9", short_edge: 768,
    segments: [
      { kind: "clip", filename: "footage/opening.mp4", duration_s: 8,
        width: 1920, height: 1080 },
      { prompt: "shot 2", duration_s: 5, assets: [], loras: [], continue: true },
    ],
  });
  const node = fakeNode("MiniMaxH3Timeline", "timeline_data", firstBlob);
  await ext.nodeCreated(node);
  const body = node.mmcBody;
  const { openTimeline: openTimelineModal } = await import("./js/minimax_creator/timeline.js");
  openTimelineModal({ timeline: body.timeline, onCommit: () => body.commit() });
  await new Promise((done) => setTimeout(done, 0));
  out.clipFirst = {
    mounted: !!node.dom,
    modal: document.body.children.at(-1).text,
  };
} catch (error) {
  out.errors.push(`clip first: ${error.message}`);
}

// The global prompt is the same rich box a segment's is, so a pool handle
// written into it is a chip rather than grey text — that is the whole reason
// it stopped being a textarea, and a chip is what says "@" works here.
try {
  const poolBlob = JSON.stringify({
    version: 2, render: "chained", prompt: "@ref-1 walks the corridor",
    aspect: "16:9", short_edge: 768,
    assets: [{ handle: "ref-1", kind: "image", role: "reference", filename: "sheet.png" }],
    segments: [{ prompt: "shot 1", duration_s: 5, assets: [], loras: [] }],
  });
  const node = fakeNode("MiniMaxH3Timeline", "timeline_data", poolBlob);
  await ext.nodeCreated(node);
  const { openTimeline: openTimelineModal } = await import("./js/minimax_creator/timeline.js");
  openTimelineModal({ timeline: node.mmcBody.timeline, onCommit: () => {} });
  await new Promise((done) => setTimeout(done, 0));
  const modal = document.body.children.at(-1);
  const chips = [];
  const walk = (element) => {
    if (element.dataset?.handle) chips.push(element.dataset.handle);
    (element.children ?? []).forEach(walk);
  };
  walk(modal);
  out.globalPrompt = { chips, text: modal.text.includes("walks the corridor") };
} catch (error) {
  out.errors.push(`global prompt: ${error.message}`);
}

// The pre-stage swaps its whole body when the model pill changes, which is the
// one place a rebuild can leave the node blank.
try {
  const node = fakeNode("MiniMaxH3PreStage", "prestage_data", JSON.stringify({ arch: "minimax" }));
  await ext.nodeCreated(node);
  const body = node.mmcBody;
  body.state.minimax.request.prompt = "a lighthouse";
  body.setArch("krea2");
  const image = body.editor.constructor.name;
  body.setArch("minimax");
  out.switch = { image, back: body.editor.constructor.name,
                 promptKept: body.state.minimax.request.prompt === "a lighthouse",
                 rendered: body.root.children.length > 0 };
} catch (error) {
  out.errors.push(`arch switch: ${error.message}`);
}

// The settings page: three tabs now — how good the file is, where it goes, and
// what the node faces offer. Read the rendered tree rather than a screenshot
// — what matters is that the tabs exist, the folder fields carry the stored
// prefixes, and a committed edit posts the key the server expects.
try {
  const { openSettings } = await import("./js/minimax_creator/settings.js");
  openSettings();
  await new Promise((done) => setTimeout(done, 0));
  const page = document.body.children.at(-1);
  const tabs = [];
  const walk = (node) => {
    if (node.className === "mmc-tab") tabs.push(node.text.trim());
    (node.children ?? []).forEach(walk);
  };
  walk(page);
  out.settings = { tabs, quality: page.text.includes("crf 23") };

  // Switch to Folders and commit a new renders prefix, the way the field does.
  const tabButtons = [];
  const collect = (node) => {
    if (node.className === "mmc-tab") tabButtons.push(node);
    (node.children ?? []).forEach(collect);
  };
  collect(page);
  tabButtons[1].listeners.click[0]();
  const fields = [];
  const findFields = (node) => {
    if (node.className === "mmc-out-field") fields.push(node);
    (node.children ?? []).forEach(findFields);
  };
  findFields(page);
  out.settings.fields = fields.map((f) => f.value);
  fields[0].value = "client/shoot-3/take";
  fields[0].listeners.change[0]();
  await new Promise((done) => setTimeout(done, 0));
  // Copied, not referenced: the Nodes tab clicks below append to the same array.
  out.settings.posted = [...globalThis.__posted];

  // The Nodes tab: the two node settings, read but not clicked — a click would
  // append to __posted, which is why the folder assertion above copies it.
  tabButtons[2].listeners.click[0]();
  const opts = [];
  const findOpts = (node) => {
    if (node.className === "mmc-opt mmc-set-opt") opts.push(node);
    (node.children ?? []).forEach(findOpts);
  };
  findOpts(page);
  out.settings.shiftRows = opts.map((o) => o.getAttribute("aria-checked"));

  // Then turn the advanced controls on — the first section's second row — and
  // count again. The turbo lead-in's three rows are what should appear: it is
  // an advanced control, and while the switch is off its section is not on the
  // page at all. Clicked last, so `posted` above is still only the folder edit.
  opts[1].listeners.click[0]();
  await new Promise((done) => setTimeout(done, 0));
  const shown = [];
  const findShown = (node) => {
    if (node.className === "mmc-opt mmc-set-opt") shown.push(node);
    (node.children ?? []).forEach(findShown);
  };
  findShown(page);
  out.settings.advancedRows = shown.length;
  out.settings.advancedLeadIn = page.text.includes("Turbo lead-in");
} catch (error) {
  out.errors.push(`settings page: ${error.message}`);
}

// ---- the face rule ---------------------------------------------------------
//
// The face is the smallest one that can show everything this piece has set. One
// segment is not enough on its own: a global prompt, a reference pool, LoRAs
// patched onto every shot and the two audio fields all live at piece level and
// none of them has anywhere to go on a one-shot face. A face that cannot draw a
// field it still queues is a trap, so any of them takes the strip instead.
//
// Every case here is one segment. What changes is only what else is set.
try {
  const has = (root, cls) => {
    let hit = false;
    const walk = (n) => {
      if (String(n.className ?? "").split(" ").includes(cls)) hit = true;
      (n.children ?? []).forEach(walk);
    };
    walk(root);
    return hit;
  };
  const shot = { prompt: "a lighthouse", assets: [], loras: [], duration_s: 6 };
  const faceOf = async (extra) => {
    const node = fakeNode("MiniMaxH3Creator", "creator_data", JSON.stringify({
      version: 2, models: {}, segments: [{ ...shot }], ...extra,
    }));
    await ext.nodeCreated(node);
    return {
      wears: node.mmcBody.editor ? "shot" : "strip",
      // The unexposed stretch of film that grows the piece — only ever on the
      // one-shot face, because on a strip the way to another card is the strip.
      grow: has(node.mmcBody.root, "mmc-tl-grow"),
    };
  };

  out.faces = {
    lone: await faceOf({}),
    globalPrompt: await faceOf({ prompt: "Dawn on the estuary" }),
    pool: await faceOf({ assets: [{ handle: "ref-1", kind: "image",
                                    role: "reference", filename: "sheet.png" }] }),
    globalLoras: await faceOf({ loras: [{ name: "grain.safetensors", strength: 0.8 }] }),
    soundscape: await faceOf({ soundscape: "wind over water" }),
    music: await faceOf({ music: "a slow piano" }),
    twoShots: await faceOf({ segments: [{ ...shot }, { ...shot }] }),
    // A piece of one supplied clip has no generation to put on a face at all.
    oneClip: await faceOf({ segments: [{ kind: "clip", filename: "b-roll.mp4",
                                         duration_s: 4 }] }),
    // A v1 blob is a lone shot, which is the whole point of lifting one.
    legacy: await (async () => {
      const node = fakeNode("MiniMaxH3Creator", "creator_data", JSON.stringify({
        version: 1, prompt: "a lighthouse", assets: [], loras: [], duration_s: 6,
      }));
      await ext.nodeCreated(node);
      return { wears: node.mmcBody.editor ? "shot" : "strip",
               grow: has(node.mmcBody.root, "mmc-tl-grow") };
    })(),
  };

  // ---- the panel is the writing area ----
  //
  // A contenteditable is only clickable where its box is, and its box is the
  // text's slot rather than the panel around it — so the panel's padding and
  // the gaps between its rows looked like somewhere to write and were not.
  // Clicking one of them now puts the caret at the end. Controls and the pill
  // row keep their own clicks.
  {
    const node = fakeNode("MiniMaxH3Creator", "creator_data", JSON.stringify({
      version: 2, models: {}, segments: [{ ...shot }],
    }));
    await ext.nodeCreated(node);
    const first = (root, cls) => {
      let hit = null;
      const walk = (n) => {
        if (!hit && String(n.className ?? "").split(" ").includes(cls)) hit = n;
        (n.children ?? []).forEach(walk);
      };
      walk(root);
      return hit;
    };
    const box = first(node.mmcBody.root, "mmc-prompt");
    const panel = first(node.mmcBody.root, "mmc-panel");
    const down = (target) => {
      document.activeElement = null;
      target.listeners?.pointerdown?.forEach((fn) => fn({
        target, preventDefault() {}, stopPropagation() {},
      }));
      // Dispatched on the panel too, the way a real bubble would reach it.
      if (target !== panel) {
        panel.listeners?.pointerdown?.forEach((fn) => fn({
          target, preventDefault() {}, stopPropagation() {},
        }));
      }
      return document.activeElement === box;
    };
    out.claim = {
      panelItself: down(panel),
      // The pill row is a region of the panel that is not the writing area.
      pills: down(first(node.mmcBody.root, "mmc-pills")),
      // ...and so is anything that answers a click for itself.
      aButton: down(first(node.mmcBody.root, "mmc-pill")),
    };
  }

  // ---- the piece-view toggle ----
  //
  // A piece holds things a shot does not — the standing prompt, the reference
  // pool, the LoRAs on every shot — and while it has one shot none of them has
  // anywhere to be shown. Without a way to the strip face they would not be
  // reachable at all: you would need a second shot before you could set the
  // standing prompt the second shot is for.
  const pieced = (pinned, segments) => {
    const node = fakeNode("MiniMaxH3Creator", "creator_data", JSON.stringify({
      version: 2, models: {}, segments,
    }));
    node.properties = pinned ? { mmc_face_piece: true } : {};
    return node;
  };
  const find = (root, cls) => {
    let hit = null;
    const walk = (n) => {
      if (!hit && String(n.className ?? "").split(" ").includes(cls)) hit = n;
      (n.children ?? []).forEach(walk);
    };
    walk(root);
    return hit;
  };

  const off = pieced(false, [{ ...shot }]);
  await ext.nodeCreated(off);
  const on = pieced(true, [{ ...shot }]);
  await ext.nodeCreated(on);
  const many = pieced(false, [{ ...shot }, { ...shot }]);
  await ext.nodeCreated(many);

  // Clicking it on the shot face pins the piece view; the pin is a node
  // property rather than anything in the blob, which the render never reads.
  const blobBefore = off.widgets.find((w) => w.name === "creator_data").value;
  find(off.mmcBody.root, "mmc-piece-toggle")?.listeners?.click?.[0]?.();
  out.pieceView = {
    shotFaceOffers: !!find(off.mmcBody.root, "mmc-piece-toggle"),
    pinnedWears: on.mmcBody.editor ? "shot" : "strip",
    stripFaceOffersWayBack: !!find(on.mmcBody.root, "mmc-piece-toggle"),
    // Nothing to go back to once there are two shots, so no control claiming so.
    manyShotsHideIt: !find(many.mmcBody.root, "mmc-piece-toggle"),
    clickPinned: off.properties.mmc_face_piece === true,
    clickSwitchedFace: off.mmcBody.editor ? "shot" : "strip",
    blobUntouched: off.widgets.find((w) => w.name === "creator_data").value === blobBefore,
    // ...and clicking it again comes back, leaving the property as it found it.
    backAgain: (() => {
      find(on.mmcBody.root, "mmc-piece-toggle")?.listeners?.click?.[0]?.();
      return { wears: on.mmcBody.editor ? "shot" : "strip",
               pinGone: !("mmc_face_piece" in on.properties) };
    })(),
  };

  // ---- and growing one into a strip ----
  //
  // The face must not mutate behind the user: the shot they wrote becomes card
  // 1, a new card 2 opens for writing, and the window is what narrates it.
  const node = fakeNode("MiniMaxH3Creator", "creator_data", JSON.stringify({
    version: 2, models: {}, segments: [{ ...shot }],
  }));
  await ext.nodeCreated(node);
  const before = document.body.children.length;
  const grow = (() => {
    let hit = null;
    const walk = (n) => {
      if (!hit && String(n.className ?? "").split(" ").includes("mmc-tl-grow")) hit = n;
      (n.children ?? []).forEach(walk);
    };
    walk(node.mmcBody.root);
    return hit;
  })();
  grow?.listeners?.click?.[0]?.();
  await new Promise((done) => setTimeout(done, 0));
  out.grew = {
    cards: node.mmcBody.timeline.segments.length,
    // The shot that was on the face is card 1, untouched. Promoting its text to
    // the piece's standing prompt would change what card 2 generates.
    firstKept: node.mmcBody.timeline.segments[0].prompt,
    piecePromptStillEmpty: !(node.mmcBody.timeline.prompt || "").trim(),
    // The new card opens the way appending to the strip already opens one.
    secondContinues: node.mmcBody.timeline.segments[1].continue === true,
    // The strip arrived, rather than the face quietly becoming a summary.
    windowOpened: document.body.children.length > before,
    // ...and the face has changed by the time it is closed.
    faceNow: node.mmcBody.editor ? "shot" : "strip",
  };
} catch (error) {
  out.errors.push(`face rule: ${error.message}`);
}

// ---- a popover outlives the row that opened it ------------------------------
//
// Rows that commit — the face pass's on/off, the two-pass section's — re-render
// the node underneath the open popover, so the button that was clicked is
// replaced by an identical one. The popover then grows (the face pass's knobs
// appear), its ResizeObserver re-places it, and if that measures the *old*
// button it measures nothing and the popover lands in the top-left corner.
try {
  const dom = await import("./js/minimax_creator/dom.js");
  const row = dom.el("div");
  const anchor = dom.el("button", { text: "faces off" });
  row.appendChild(anchor);
  document.body.appendChild(row);
  // Measured only while it is in the document — a detached element really does
  // report all zeros, and that is the whole of what goes wrong here.
  anchor.getBoundingClientRect = () => (anchor.isConnected
    ? { top: 700, left: 420, width: 60, height: 24, bottom: 724, right: 480 }
    : { top: 0, left: 0, width: 0, height: 0, bottom: 0, right: 0 });
  const pop = dom.el("div");
  document.body.appendChild(pop);
  dom.placeNear(pop, anchor);
  const placed = { left: pop.style.left, top: pop.style.top };
  // What committing does: the row is redrawn and the old button is detached.
  row.replaceChildren(dom.el("button", { text: "faces" }));
  globalThis.__observers.forEach((observer) => observer.fire());
  out.placement = { placed, after: { left: pop.style.left, top: pop.style.top },
                    anchorGone: anchor.isConnected === false };
} catch (error) {
  out.errors.push(`placement: ${error.message}`);
}

// ---- the seed does not move on its own, and the last one is reachable -------
//
// A render here is minutes, and the seed widget is hidden — so the frontend's
// own "randomize" would roll the one variable being held still, invisibly. The
// node opens on "fixed" instead, and because a fixed seed is only half the
// answer, the row also offers the seed the last queue actually ran on: the way
// back to a shot worth keeping once the number has moved on.
try {
  const first = (root, cls) => {
    let hit = null;
    const walk = (n) => {
      if (!hit && String(n.className ?? "").split(" ").includes(cls)) hit = n;
      (n.children ?? []).forEach(walk);
    };
    walk(root);
    return hit;
  };
  const node = fakeNode("MiniMaxH3Creator", "creator_data", ONE_SHOT);
  await ext.nodeCreated(node);
  const seed = node.widgets.find((w) => w.name === "seed");
  const backButton = () => first(node.mmcBody.root, "mmc-seed-last");
  out.seed = {
    // Set at creation, over what the frontend handed us.
    control: seed.linkedWidgets[0].value,
    // The button is there from the start — it is how anyone finds out the
    // feature exists — but nothing has been queued, so it is inert.
    beforeQueue: !!backButton(),
    beforeQueueOff: "disabled" in (backButton()?.attrs ?? {}),
  };

  // A queue goes out. What the server was asked to run is what gets remembered
  // — read off the serialized prompt, not off the widget, because the widget is
  // free to have moved on by then. Which is what happens next.
  globalThis.__prompt = { output: { "3": { inputs: { seed: 4242 } } } };
  app.graph = { _nodes: [node], setDirtyCanvas() {} };
  await app.queuePrompt();
  seed.value = 999;
  node.mmcBody.render();

  const back = backButton();
  out.seed.afterQueue = !("disabled" in (back?.attrs ?? {}));
  back?.listeners?.click?.[0]?.();
  out.seed.restored = seed.value;
  // ...and once the seed *is* that one, it goes inert again rather than
  // offering a click that would change nothing.
  out.seed.thenOff = "disabled" in (backButton()?.attrs ?? {});
} catch (error) {
  out.errors.push(`seed: ${error.message}`);
}

// The pool shelf reports where each piece reference is used, and it has to do
// it while the card that cites it is being written — the shelf was redrawn only
// by a full render of the modal, so a handle typed into a segment left the chip
// on "cited nowhere yet" for the whole of the edit that cited it. Reported in
// #12: from the outside that is the feature simply not working.
try {
  const findAll = (root, cls) => {
    const hits = [];
    const walk = (n) => {
      if (String(n.className ?? "").split(" ").includes(cls)) hits.push(n);
      (n.children ?? []).forEach(walk);
    };
    walk(root);
    return hits;
  };
  const node = fakeNode("MiniMaxH3Timeline", "timeline_data", JSON.stringify({
    version: 2, render: "chained", prompt: "", aspect: "16:9", short_edge: 768,
    assets: [{ handle: "ref-1", kind: "image", role: "reference", filename: "sheet.png" }],
    segments: [{ prompt: "shot 1", duration_s: 5, assets: [], loras: [] },
               { prompt: "shot 2", duration_s: 5, assets: [], loras: [] }],
  }));
  await ext.nodeCreated(node);
  const timeline = node.mmcBody.timeline;
  const { openTimeline: openTimelineModal } = await import("./js/minimax_creator/timeline.js");
  openTimelineModal({ timeline, onCommit: () => node.mmcBody.commit() });
  await new Promise((done) => setTimeout(done, 0));
  const modal = document.body.children.at(-1);
  const shelf = () => findAll(modal, "mmc-tl-pool")[0]?.text ?? "";

  out.poolShelf = { idle: shelf().includes("cited nowhere yet") };

  // Open card 1 and write the citation into its box, the way a user does.
  findAll(modal, "mmc-tl-edit")[0].listeners.click[0]();
  const sheet = document.body.children.at(-1);
  const box = findAll(sheet, "mmc-prompt")[0];
  box.append(document.createTextNode(" @ref-1"));
  box.listeners.input.forEach((fn) => fn({ target: box }));

  out.poolShelf.wrote = timeline.segments[0].prompt;
  // The whole bug: this used to still say "cited nowhere yet".
  out.poolShelf.live = shelf().includes("in segment 1");
} catch (error) {
  out.errors.push(`pool shelf: ${error.message}`);
}

// ...and the one way that readout is true and still reads as broken: the same
// picture attached to a card in its own right. The piece copy is uncited, the
// card copy is doing the work, and "cited nowhere yet" said nothing about the
// reference plainly on screen in that card. Also #12.
try {
  const findAll = (root, cls) => {
    const hits = [];
    const walk = (n) => {
      if (String(n.className ?? "").split(" ").includes(cls)) hits.push(n);
      (n.children ?? []).forEach(walk);
    };
    walk(root);
    return hits;
  };
  const node = fakeNode("MiniMaxH3Timeline", "timeline_data", JSON.stringify({
    version: 2, render: "chained", prompt: "", aspect: "16:9", short_edge: 768,
    assets: [{ handle: "ref-1", kind: "image", role: "reference", filename: "sheet.png" }],
    segments: [{
      prompt: "shot 1 with @img-2", duration_s: 5, loras: [],
      assets: [{ handle: "img-2", kind: "image", role: "reference", filename: "sheet.png" }],
    }],
  }));
  await ext.nodeCreated(node);
  const { openTimeline: openTimelineModal } = await import("./js/minimax_creator/timeline.js");
  openTimelineModal({ timeline: node.mmcBody.timeline, onCommit: () => {} });
  await new Promise((done) => setTimeout(done, 0));
  const shelf = findAll(document.body.children.at(-1), "mmc-tl-pool")[0]?.text ?? "";
  out.poolDouble = {
    says: shelf.includes("attached to segment 1 (@img-2)"),
    notIdle: !shelf.includes("cited nowhere yet"),
  };
} catch (error) {
  out.errors.push(`pool double: ${error.message}`);
}

// A rewrite takes only what the reply carries. The two audio fields are typed
// in by hand as often as they are written, and a reply that skipped them used
// to blank them — deleting a line the user wrote, in a box they were looking
// at. The timeline has always taken them this way; this is the face agreeing.
try {
  const node = fakeNode("MiniMaxH3Creator", "creator_data", JSON.stringify({
    version: 2, prompt: "", models: {},
    segments: [{ prompt: "a lighthouse", assets: [], loras: [], duration_s: 6,
                 soundscape: "surf on shingle", music: "a low drone" }],
  }));
  await ext.nodeCreated(node);
  const shot = node.mmcBody.timeline.segments[0];
  node.mmcBody.faceEditor.refinePanel.apply(
    { soundscape: "", music: "", seen: "", problems: [] },
    { body: "A lighthouse at dusk." });
  out.audioKept = { soundscape: shot.soundscape, music: shot.music };
  // ...and a reply that *does* carry them still wins.
  node.mmcBody.faceEditor.refinePanel.apply(
    { soundscape: "wind over the lamp", music: "", seen: "", problems: [] },
    { body: "A lighthouse at dusk." });
  out.audioKept.written = shot.soundscape;
  out.audioKept.musicStill = shot.music;
} catch (error) {
  out.errors.push(`audio kept: ${error.message}`);
}

// The prompt box reads back whatever is actually in it.
//
// Its DOM is meant to be flat and everything the box does keeps it that way,
// but undo restores the engine's snapshot rather than ours and Ctrl+B is the
// browser's own command on a contenteditable. Reading the top level only made
// a wrapper the engine put there cost the line break it stands for and turned
// a chip inside it into its own label — silently, on a keystroke, straight
// into the state. Built here the way an engine builds it, not the way the box
// does.
try {
  const find = (root, cls) => {
    let hit = null;
    const walk = (n) => {
      if (!hit && String(n.className ?? "").split(" ").includes(cls)) hit = n;
      (n.children ?? []).forEach(walk);
    };
    walk(root);
    return hit;
  };
  const node = fakeNode("MiniMaxH3Creator", "creator_data", JSON.stringify({
    version: 2, prompt: "", models: {},
    segments: [{
      prompt: "", duration_s: 6, loras: [],
      assets: [{ handle: "img-1", kind: "image", role: "reference", filename: "a.png" }],
    }],
  }));
  await ext.nodeCreated(node);
  const body = node.mmcBody;
  const box = find(body.root, "mmc-prompt");
  const chip = document.createElement("span");
  chip.setAttribute("data-handle", "img-1");
  chip.textContent = "@img-1";
  const wrapper = document.createElement("div");
  wrapper.append(document.createTextNode("second line about "), chip);
  box.replaceChildren(document.createTextNode("first line"), wrapper);
  box.listeners.input.forEach((fn) => fn({ target: box }));
  out.nested = { read: body.timeline.segments[0].prompt };

  // ...and a wrapper around the whole content is not a blank first line.
  const whole = document.createElement("div");
  whole.append(document.createTextNode("all of it"));
  box.replaceChildren(whole);
  box.listeners.input.forEach((fn) => fn({ target: box }));
  out.nested.wrapped = body.timeline.segments[0].prompt;
} catch (error) {
  out.errors.push(`nested: ${error.message}`);
}

// The cast, on the node's own face.
//
// The shelf used to live only in the Timeline window and to refuse to open at
// all until a reference had been attached — which put it out of reach of a
// text-only generation, where a name and a description are the whole of what
// keeps the same woman in shot 1 and in shot 9. It is on the rail now, on a
// node with nothing attached to it, and this is the path end to end: press the
// rail, name her, describe her, cite her, and read `subjects` back out of the
// blob the node writes.
try {
  const all = (root, cls) => {
    const hits = [];
    const walk = (n) => {
      if (String(n.className ?? "").split(" ").includes(cls)) hits.push(n);
      (n.children ?? []).forEach(walk);
    };
    walk(root);
    return hits;
  };
  const click = (node) => node?.listeners?.click?.[0]?.();
  const type = (field, value) => {
    field._value = value;
    field.listeners?.input?.forEach((fn) => fn({ target: { value } }));
  };

  const node = fakeNode("MiniMaxH3Creator", "creator_data", JSON.stringify({
    version: 1, prompt: "a bare loft at dusk", assets: [], loras: [],
  }));
  await ext.nodeCreated(node);
  const body = node.mmcBody;

  const railCast = all(body.root, "mmc-tool").find((b) => b.text.includes("Cast"));
  const beforePress = all(body.root, "mmc-cast-card").length;
  click(railCast);
  const cards = () => all(body.root, "mmc-cast-card");

  const name = all(body.root, "mmc-cast-name")[0];
  type(name, "anna");
  name.listeners?.blur?.forEach((fn) => fn());
  const desc = all(body.root, "mmc-cast-desc")[0];
  type(desc, "a woman in her thirties, close-cropped hair");
  desc.listeners?.blur?.forEach((fn) => fn());

  // Cast but never written into a prompt: the readout says so, and clicking it
  // is what fixes it.
  const idle = all(body.root, "mmc-cast-where-idle");
  click(idle[0]);

  // The shelf must not redraw itself while it holds the caret. Every keystroke
  // in a cast field is written straight through to the blob, and writing to the
  // blob is what redraws the node — so a shelf that rebuilt on demand would
  // rebuild the field under the caret between one letter and the next, and you
  // could type exactly one character before the focus went with it.
  const shelf = body.faceEditor.castShelf;
  const card = () => all(shelf.root, "mmc-cast-card")[0];
  const held = card();
  shelf.root.contains = () => true;          // ...as it would while typing
  globalThis.document.activeElement = all(shelf.root, "mmc-cast-name")[0];
  shelf.render();
  const survived = card() === held;
  globalThis.document.activeElement = null;
  shelf.root.contains = () => false;
  shelf.render();
  const rebuilt = card() !== held;

  const blob = JSON.parse(node.widgets.find((w) => w.name === "creator_data").value);
  out.cast = {
    onRail: !!railCast,
    // Ungated: nothing is attached to this node at all.
    railEnabled: !railCast?.attrs?.disabled,
    beforePress,
    afterPress: cards().length,
    idleBefore: idle.length,
    idleAfter: all(body.root, "mmc-cast-where-idle").length,
    survived, rebuilt,
    prompt: body.timeline.segments[0].prompt,
    subjects: blob.subjects,
  };

  // Last, because it takes her away: casting somebody attaches files, so
  // removing them has to detach them. Here rather than in `test_cast_detach`
  // because the interesting half is this body's own host callback — the
  // `piece === state` branch, which reads its own texts with no timeline around
  // it and would throw if that branch were wrong.
  const shot = body.faceEditor;
  shot.state.assets.push(
    { handle: "img-1", kind: "image", role: "reference", filename: "anna.png" },
    { handle: "img-2", kind: "image", role: "reference", filename: "kept.png" });
  const anna = shot.piece.subjects[0];
  anna.from = ["img-1"];
  // A second file nobody is built out of, written into the prompt by hand: it
  // has to survive somebody else's departure.
  shot.state.prompt = `${shot.state.prompt} — @img-2 on the table`;
  shelf.remove(anna);
  out.cast.detached = {
    left: shot.state.assets.map((a) => a.handle),
    cast: shot.piece.subjects.length,
  };
} catch (error) {
  out.errors.push(`cast: ${error.stack}`);
}

console.log(JSON.stringify(out));
"""

work = tempfile.mkdtemp(prefix="mmc-js-")
try:
    # The pack imports ComfyUI's own modules from above its own directory, the
    # way the frontend serves them — so the copy keeps that shape: the js tree
    # inside a stand-in for the pack, and the stubs beside it.
    pack = os.path.join(work, "pack")
    shutil.copytree(os.path.join(ROOT, "js"), os.path.join(pack, "js"))
    os.makedirs(os.path.join(work, "scripts"), exist_ok=True)
    for name, source in STUBS.items():
        with open(os.path.join(work, "scripts", name), "w", encoding="utf-8") as handle:
            handle.write(source)
    for name, source in (("dom.mjs", DOM), ("check.mjs", CHECK)):
        with open(os.path.join(pack, name), "w", encoding="utf-8") as handle:
            handle.write(source)

    result = subprocess.run(["node", os.path.join(pack, "check.mjs")],
                            capture_output=True, text=True, cwd=pack)
finally:
    shutil.rmtree(work, ignore_errors=True)

if result.returncode != 0:
    # The whole point: a module-level throw takes the extension with it, and
    # this is where that shows up as a failure rather than as a dead canvas.
    print("the frontend did not load:\n" + (result.stderr.strip() or result.stdout.strip()))
    sys.exit(1)

report = json.loads(result.stdout.strip().splitlines()[-1])
from harness import FAILURES, check, passed


FAILURES.extend(report["errors"])
check("the extension registers", report["registered"], "minimax.creator")

# Each node's body, and which editor drives it. The H3 pre-stage is the one that
# differs: its still is a video generation, so it is driven by the Creator's own
# body rather than by the image-model editor beside it.
#
# The two piece ids mount the same body and differ only in what the blob says:
# one shot wears that shot's editor, a strip wears the strip's summary. Driven
# under both ids because a saved workflow may carry either.
check("a piece of one shot wears that shot's editor",
      report["nodes"].get("MiniMaxH3Creator"),
      {"mounted": True, "body": "CreatorEditor"})
check("a piece of several wears the strip", report["nodes"].get("MiniMaxH3Timeline"),
      {"mounted": True, "body": "TimelineBody"})
check("the image pre-stage mounts", report["nodes"].get("MiniMaxH3PreStage"),
      {"mounted": True, "body": "PreStageEditor"})
check("the H3 pre-stage mounts the Creator's body",
      report["nodes"].get("MiniMaxH3PreStage (H3 still)"),
      {"mounted": True, "body": "CreatorEditor"})

# What a still is set up with. Every one of these is the video nodes' own
# control, reached by being a video request rather than by being re-described.
for wanted in ("Add image", "Add video", "Add audio", "Add LoRA", "Gallery", "From video",
               "Start frame", "End frame", "MiniMax H3", "latent", "T2VA"):
    if wanted not in (report["still"] or ""):
        FAILURES.append(f"the H3 still's body has no {wanted!r}")

# ...and what it must *not* have. The settings page is the video rate control;
# a node that writes PNGs offering it is a control over nothing.
for unwanted in ("Settings", " s ", "sweep"):
    if unwanted in (report["still"] or ""):
        FAILURES.append(f"the H3 still's body should not carry {unwanted!r}")
check("the Creator keeps the settings tool", "Settings" in (report["creator"] or ""), True)

# ---- somebody typed into the sentence ---------------------------------------

mention = report.get("castFromMention", {})
check("picking a kept member out of the @ menu casts her", mention.get("handle"), "anna")
check("...as one subject on the piece", mention.get("cast"), 1)
check("...with her files attached as ordinary references on the shot",
      mention.get("attached"), "img-1=anna/face.png,aud-1=anna/voice.wav")
check("...and nothing hidden in a pool the face does not draw",
      mention.get("poolLeftAlone"), True)
check("...and her voice still bound to the file that is her voice",
      mention.get("voiceBound"), True)
check("a pre-stage is offered no roster — it has no piece to cast her into",
      mention.get("notOnAPreStage"), True)

wrote = report.get("wroteName", {})
check("her name lands where the @ was typed, not on a lost caret",
      wrote.get("state"), "a woman at the door, @anna ")
check("...and reads back off the box as the same sentence",
      wrote.get("value"), "a woman at the door, @anna ")

# The settings page owns three questions now — how good the file is, where it
# goes, and what the node faces offer — so it has three tabs, and the folder
# fields are the only place the prefixes can be set.
settings = report.get("settings", {})
check("the settings page has all three tabs", settings.get("tabs"),
      ["Quality", "Folders", "Nodes"])
# Every row on the tab, in order, with each setting's default checked on a fresh
# settings file: previews ship playing, and the advanced controls, the scopes
# and the shift pills all ship off. Advanced leads, because it decides how much
# of the rest of the tab there is — the turbo lead-in is an advanced control and
# its three rows are simply not on the page while it is off, which is what makes
# this list four pairs and not four pairs plus a triple. Then preview playback,
# which governs the biggest thing a node draws, the reference scopes, which
# change what is queued, and the shift pills last, which change only what is
# drawn.
check("the node settings show their defaults checked",
      settings.get("shiftRows"),
      ["true", "false", "true", "false", "true", "false", "true", "false"])
# And with the advanced controls on, the turbo lead-in is back on the page: the
# four pairs plus its three rows. That is the whole of what the switch does to
# this tab — it adds a section, it never disables one.
check("advanced controls bring the turbo lead-in back to the page",
      (settings.get("advancedRows"), settings.get("advancedLeadIn")), (11, True))
check("the quality tab shows the encoder value", settings.get("quality"), True)
check("the folders tab carries both stored prefixes", settings.get("fields"),
      ["minimax/renders/H3", "minimax/stills/prestage"])
check("editing a folder writes it back under the server's own key",
      settings.get("posted"), [{"video_prefix": "client/shoot-3/take"}])

# The node face is a preview and the prompt is written in a sheet.
face = report.get("face", {})
check("the face carries the live prompt box", face.get("boxOnFace"), True)
check("...and a way into the window", face.get("expand"), True)
check("clicking it opens the window", face.get("opened"), True)
check("...with a box of its own in it", face.get("boxInSheet"), True)
check("...which is not the face's", face.get("sameState"), True)

# The rewrite is edited in place. A commit re-renders the body, and the box the
# rewrite is written in is on the commit path of its own keystrokes — so it has
# to survive them as the same element, or it loses the caret once per character.
box = report.get("refineBox", {})
check("the rewrite is drawn in a box", box.get("drawn"), True)
check("...which survives a keystroke", box.get("sameAfterOne"), True)
check("...and the next one", box.get("sameAfterTwo"), True)
check("...keeping the focus it had", box.get("stillFocused"), True)
check("...while still writing through to the blob",
      box.get("written"), "A lighthouse at dusk, lamp turning slowly.")
check("a second rewrite still lands in it", box.get("applied"), "A second rewrite.")
check("...without rebuilding it", box.get("sameAfterApply"), True)

# ...and it is the same window a card on the strip opens.
window = report.get("window", {})
check("the face and a strip card open one window", window.get("same"), True)
check("...with the shot's body in it", window.get("body"), True)

# Supplied footage: both renders survive it, and both say it is there.
clip = report.get("clip", {})
check("a timeline with a clip in it mounts", clip.get("mounted"), True)
check("the strip still redraws after a clip is committed", clip.get("recommitted"), True)
for wanted in ("clip", "take-3.mp4"):
    if wanted not in (clip.get("modal") or ""):
        FAILURES.append(f"the timeline modal does not name the clip's {wanted!r}")

# The Timeline node's own rail: the Creator's two clusters, with the piece's
# reference pool standing in for a card's attachments.
for wanted in ("Add image", "Add video", "Add audio", "Add LoRA", "Gallery", "Settings"):
    if wanted not in (clip.get("node") or ""):
        FAILURES.append(f"the timeline node body has no {wanted!r} tool")

# A piece is at least one shot: the empty strip is not a state the node can be
# left in, because every way of reaching it is somebody deleting cards.
empty = report.get("empty", {})
check("an empty blob opens as one blank shot", empty.get("cards"), 1)
check("...which is what gets written back", empty.get("written"), 1)
check("...and it wears that shot's editor", empty.get("wears"), "shot")
check("a blob written with no cards opens the same way", empty.get("fromEmptyList"), 1)
check("deleting every card leaves one blank shot",
      (empty.get("cleared") or {}).get("cards"), 1)
check("...with nothing written in it", (empty.get("cleared") or {}).get("prompt"), "")
check("...and the face back to being that shot's",
      (empty.get("cleared") or {}).get("wears"), "shot")
check("...and the strip still draws once a second is added", empty.get("added"), 2)

# ---- Clear ------------------------------------------------------------------
#
# One control, one line: what you wrote for this scene goes, what you set up for
# this machine stays. Both halves are checked, because getting either wrong is
# what makes the button unusable — one loses the setup, the other does nothing.
clear = report.get("clear", {})
check("the strip face carries Clear", clear.get("onStrip"), True)
check("...and so does the lone shot's", clear.get("onLoneShot"), True)
check("one press only asks", clear.get("armedLabel"), "Really clear?")
check("...and changes nothing", clear.get("survivesOnePress"), 2)
check("clearing keeps the machine",
      clear.get("kept"),
      {"models": "fl2va.safetensors", "turbo": "turbo.safetensors", "loras": 1,
       "aspect": "9:16", "short_edge": 512})
check("...and empties the piece",
      clear.get("emptied"),
      {"prompt": "", "soundscape": "", "music": "", "assets": 0, "cast": 0,
       "cards": 1, "cardPrompt": ""})
check("...leaving nobody mirrored onto the blank card", clear.get("cardCast"), 0)
check("...in the blob the node queues", (clear.get("blob") or {}).get("prompt"), "")
check("...which casts nobody", (clear.get("blob") or {}).get("subjects"), None)
check("...which keeps its weights", ((clear.get("blob") or {}).get("models") or {}).get("fl2va"),
      "fl2va.safetensors")
check("an emptied piece has nothing left to clear", clear.get("disabledAfter"), True)
check("clearing from the lone shot empties it too", clear.get("loneEmptied"), "")
check("...and keeps the weights there as well", clear.get("loneKept"), "fl2va.safetensors")

# ---- the LoRA stack ---------------------------------------------------------
#
# One chip, four things to do to a LoRA: mute it, re-weight it, swap the file
# under it, drop it. The mute is the one this section exists for — it is what
# makes "is this LoRA the problem" a question you can ask twice.
loras = report.get("loras", {})
check("the shot face names its LoRAs", loras.get("named"), ["glow", "turbo"])
check("clicking a name mutes it", loras.get("muted"), False)
check("...and keeps everything set up on it",
      loras.get("stillThere"), {"count": 2, "strength": 0.8, "triggers": 1})
check("...takes it off the checkpoint", loras.get("active"), 1)
check("...and its trigger words off the prompt", loras.get("triggers"), 0)
check("...in the blob the node queues", loras.get("serialized"), False)
check("...and the same click brings it back", loras.get("backOn"), True)
check("the strip names the piece's stack too", loras.get("onStrip"), ["glow", "turbo"])
check("...and mutes from there", loras.get("stripMuted"), False)
check("...which is one fewer in the run", loras.get("stripActive"), 1)
check("a swap keeps the slot and takes the new file's setup",
      loras.get("swapped"),
      {"order": ["c.safetensors", "b.safetensors"], "strength": 0.55,
       "modes": ["fl2va"], "muted": False, "triggers": ["trig"]})
check("...and swapping onto one already in the stack is a removal",
      loras.get("swappedOntoTwin"), ["b.safetensors"])

# Controls that write through an owner's callback still move what they draw.
# ---- the face rule ----------------------------------------------------------

faces = report.get("faces", {})
check("one shot and nothing else wears the shot's editor",
      faces.get("lone"), {"wears": "shot", "grow": True})
check("...and a version-1 blob lifts into exactly that",
      faces.get("legacy"), {"wears": "shot", "grow": True})
# Each of these is still one segment. What takes the strip is that the one-shot
# face has nowhere to show them — and a face that hides a queued field is worse
# than a face that is bigger than it needs to be.
for name, what in [("globalPrompt", "a standing prompt"),
                   ("pool", "a reference pool"),
                   ("globalLoras", "LoRAs on every shot"),
                   ("soundscape", "a soundscape"),
                   ("music", "a score")]:
    check(f"one shot plus {what} wears the strip",
          faces.get(name), {"wears": "strip", "grow": False})
check("two shots wear the strip", faces.get("twoShots"), {"wears": "strip", "grow": False})
check("a piece of one supplied clip wears the strip — there is no shot to show",
      faces.get("oneClip"), {"wears": "strip", "grow": False})

# The panel is the writing area, not just the box inside it.
claim = report.get("claim", {})
check("clicking the panel's dead space puts the caret in the box",
      claim.get("panelItself"), True)
check("...but the pill row keeps its own clicks", claim.get("pills"), False)
check("...and so does a control", claim.get("aButton"), False)

# The piece-view toggle: the only way to the piece's own controls while the
# piece is one shot, and the way back once you are there.
view = report.get("pieceView", {})
check("the shot face offers the toggle", view.get("shotFaceOffers"), True)
check("pinned, one shot wears the strip", view.get("pinnedWears"), "strip")
check("...and offers the way back", view.get("stripFaceOffersWayBack"), True)
check("two shots hide it — there is no shot face to go back to",
      view.get("manyShotsHideIt"), True)
check("clicking it pins the node, not the blob", view.get("clickPinned"), True)
check("...switches the face", view.get("clickSwitchedFace"), "strip")
check("...and writes nothing the render reads", view.get("blobUntouched"), True)
check("clicking it again comes back to the shot",
      (view.get("backAgain") or {}).get("wears"), "shot")
check("...leaving the property as it found it",
      (view.get("backAgain") or {}).get("pinGone"), True)

grew = report.get("grew", {})
check("writing the next shot adds a card", grew.get("cards"), 2)
check("...leaves the first one's prompt where it was", grew.get("firstKept"), "a lighthouse")
check("...does not promote it to the piece's standing prompt",
      grew.get("piecePromptStillEmpty"), True)
check("...opens the new card's seam the way the strip does",
      grew.get("secondContinues"), True)
check("...and narrates it by opening the strip rather than swapping the face",
      grew.get("windowOpened"), True)
check("...after which the face is the strip", grew.get("faceNow"), "strip")

controls = report.get("controls", {})
check("the render toggle moves a one-card strip to one pass", controls.get("toSingle"), "single")
check("...and back to chained", controls.get("backToChained"), "chained")
check("the route badge in the window changes the route", controls.get("route"), "fl2va")
check("...and the window redraws it", controls.get("badgeMoved"), True)

# A piece that opens on footage, and the placeholder rule that lets it.
first = report.get("clipFirst", {})
check("a timeline whose first card is a clip mounts", first.get("mounted"), True)
if "opening.mp4" not in (first.get("modal") or ""):
    FAILURES.append("the timeline modal does not name the clip it opens on")


# "@" in the global prompt: the pool handle is a chip, which is what says the
# box is the same one a segment has rather than a textarea.
global_prompt = report.get("globalPrompt", {})
check("a pool citation in the global prompt is a chip", global_prompt.get("chips"), ["ref-1"])
check("...and the prose around it is still there", global_prompt.get("text"), True)

# A wrapper the engine put in the box costs neither the line it stands for nor
# the chip inside it.
nested = report.get("nested", {})
check("a block in the prompt box reads back as the newline it is",
      nested.get("read"), "first line\nsecond line about @img-1")
check("...but one around the whole content is not a blank first line",
      nested.get("wrapped"), "all of it")

# The pool shelf: where each piece reference is used, kept true while the card
# that cites it is being written rather than only after the window closes.
shelf = report.get("poolShelf", {})
check("a pool reference nothing cites says so", shelf.get("idle"), True)
check("...and writing its handle into a card lands in that card's prompt",
      shelf.get("wrote"), "shot 1 @ref-1")
check("...which the shelf reports without waiting for the window to close",
      shelf.get("live"), True)

double = report.get("poolDouble", {})
check("a piece reference attached to a card in its own right names that card",
      double.get("says"), True)
check("...rather than reporting a picture plainly in use as unused",
      double.get("notIdle"), True)

# A rewrite writes what it returned and nothing else.
audio = report.get("audioKept", {})
check("a reply with no soundscape leaves the one that was typed",
      audio.get("soundscape"), "surf on shingle")
check("...and the score with it", audio.get("music"), "a low drone")
check("a reply that carries a soundscape still writes it",
      audio.get("written"), "wind over the lamp")
check("...without blanking the score it said nothing about",
      audio.get("musicStill"), "a low drone")

check("switching to an image model rebuilds the body",
      report.get("switch", {}).get("image"), "PreStageEditor")
check("and switching back rebuilds it again",
      report.get("switch", {}).get("back"), "CreatorEditor")
check("the prompt survives the round trip",
      report.get("switch", {}).get("promptKept"), True)
check("the rebuilt body is not empty",
      report.get("switch", {}).get("rendered"), True)

placement = report.get("placement", {})
check("the popover is placed against the pill that opened it",
      (placement.get("placed") or {}).get("top"), "592px")
check("the row under it is redrawn and the pill it was placed against is gone",
      placement.get("anchorGone"), True)
check("...and the popover stays where it was rather than jumping to the corner",
      placement.get("after"), placement.get("placed"))

# The seed: fixed on arrival, and the last queued one always reachable.
seed = report.get("seed", {})
check("a fresh node opens on a fixed seed", seed.get("control"), "fixed")
check("the way back to the last seed is on the row from the start",
      seed.get("beforeQueue"), True)
check("...inert until something has been queued", seed.get("beforeQueueOff"), True)
check("after a queue it offers the seed that ran", seed.get("afterQueue"), True)
check("...and clicking it puts that seed back", seed.get("restored"), 4242)
check("...after which it is inert again", seed.get("thenOff"), True)


# ---- the cast, on the node face ---------------------------------------------
cast = report.get("cast") or {}
check("the cast is on the rail", cast.get("onRail"), True)
check("and is not gated on having attached anything", cast.get("railEnabled"), True)
check("the shelf is hidden until it is asked for", cast.get("beforePress"), 0)
check("one press of the rail casts the first person", cast.get("afterPress"), 1)
check("a subject nobody cites says so", cast.get("idleBefore"), 1)
check("and clicking that is what cites her", cast.get("idleAfter"), 0)
check("the shelf does not redraw under the caret", cast.get("survived"), True)
check("and redraws once the field is left", cast.get("rebuilt"), True)
check("the citation lands in the prompt",
      "@anna" in (cast.get("prompt") or ""), True)
check("she is described in words alone, with no reference behind her",
      (cast.get("subjects") or [{}])[0].get("description"),
      "a woman in her thirties, close-cropped hair")
check("and rides in the blob the node writes",
      (cast.get("subjects") or [{}])[0].get("handle"), "anna")

# Casting somebody attaches files, so removing them has to detach them — on this
# body, whose piece and state are the same object and whose only texts are its
# own. See tests/test_cast_detach.py for the rule itself.
detached = cast.get("detached") or {}
check("removing her takes her own picture off the node, and leaves the one "
      "the prompt writes by hand", detached.get("left"), ["img-2"])
check("...and she is out of the cast", detached.get("cast"), 0)

passed(f"the frontend loads and all {len(report['nodes'])} bodies mount")

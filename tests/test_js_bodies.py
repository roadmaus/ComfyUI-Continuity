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
  async queuePrompt(number, batch, targets) {
    // Recorded raw, because the third argument means two different things
    // depending on which frontend reads it — see the fullscreen block below,
    // which puts what the pack sends through both.
    globalThis.__queued = targets ?? null;
    // A refused prompt is caught by ComfyUI itself: it puts the dialog up and
    // resolves, exactly as this does. Only an accepted one is announced.
    if (!globalThis.__refuse) globalThis.__say?.("promptQueued", { batchCount: 1 });
    return this.graphToPrompt();
  },
  async graphToPrompt() { return globalThis.__prompt ?? { output: {} }; },
};
""",
    # `fetchApi` answers the settings route the way the server does, and records
    # what was posted — which is what lets the settings page be exercised here.
    "api.js": """
globalThis.__posted = [];
let stored = { video_crf: 23, video_prefix: "minimax/renders/H3",
               image_prefix: "minimax/stills/prestage" };
// A real listener table, because the shell now listens for the one thing the
// frontend says out loud when a prompt is accepted — see `promptQueued` below.
const listeners = {};
globalThis.__say = (type, detail) => {
  for (const fn of [...(listeners[type] ?? [])]) fn({ type, detail });
};
export const api = {
  addEventListener(type, fn) { (listeners[type] ??= []).push(fn); },
  removeEventListener(type, fn) {
    listeners[type] = (listeners[type] ?? []).filter((f) => f !== fn);
  },
  apiURL: (u) => u,
  interrupt() { globalThis.__interrupted = true; },
  async fetchApi(route, options) {
    if (route.endsWith("/settings") && options?.method === "POST") {
      const patch = JSON.parse(options.body);
      globalThis.__posted.push(patch);
      stored = { ...stored, ...patch };
    }
    // The compiler's answer, in the shape `server_routes.compiled_prompt`
    // sends it: one entry per pass, and a card -> pass map whose keys are
    // strings because that is what JSON does to Python's int keys.
    if (route.endsWith("/compiled_prompt")) {
      return { ok: true, status: 200, json: async () => ({
        passes: [{ index: 0, clip: false, mode: "REF2VA", overridden: false,
                   prompt: "subject_definitions: <Subject 1> is the person in <Picture 1>."
                         + "\\n\\ndetailed_description: [Shot 1] They turn to the camera." }],
        cards: { "0": 0 },
      }) };
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

// …and deleting a chip takes what it named back out again.
//
// The @ menu creates the thing and writes the chip in one gesture, so the chip
// *is* the attachment and deleting it has to be the way out. The half of that
// which is not cosmetic: a bare reference sits in `assets`, and everything in
// `assets` is encoded and shown to the model whether or not a word of the
// prompt mentions it — so a name deleted out of the sentence left a picture
// conditioning the render exactly as hard as one still named.
try {
  const node = fakeNode("MiniMaxH3Creator", "creator_data", ONE_SHOT);
  await ext.nodeCreated(node);
  const editor = node.mmcBody.faceBody();
  const box = editor.prompt;
  const piece = node.mmcBody.timeline;
  const shot = piece.segments[0];

  // Everything arrives the way the redesign makes it arrive: through the menu.
  const anna = await box.hooks.castFromLibrary({
    handle: "anna", takes: "person",
    files: [{ slot: "from", filename: "anna/face.png", kind: "image" }],
  });
  const door = box.hooks.onAttach({ path: "doors/red.png", kind: "image" });
  const lamp = box.hooks.onAttach({ path: "lamps/brass.png", kind: "image" });

  // Backspace against a chip, which is the only way one can be deleted: it is
  // contenteditable="false", so the caret cannot get inside it.
  const cut = (handle) => {
    box.root.children.find((n) => n.dataset?.handle === handle)?.remove();
    box.onEdit();
  };
  // A muted reference is still attached — that is the whole point of it — so
  // the readout has to tell the two apart: `img-2!` is on the node and out of
  // the run, and a handle that is simply gone is gone.
  const refs = () => (shot.assets ?? [])
    .map((a) => `${a.handle}${a.enabled === false ? "!" : ""}`).join(",");
  const cast = () => (piece.subjects ?? []).map((s) => s.handle).join(",");

  box.setValue(`@${anna} at @${door}, lit by @${lamp}`);
  editor.state.prompt = box.getValue();
  // The lamp is written in the soundscape too, so cutting it out of the prompt
  // is the deletion of one occurrence and not of the reference.
  editor.state.soundscape = `a hum off @${lamp}`;
  out.reap = { chips: box.chipped.size, refs: refs(), cast: cast() };

  cut(lamp);
  out.reap.citedElsewhere = refs();
  cut(door);
  out.reap.afterTheRef = refs();
  out.reap.castUntouched = cast();
  cut(anna);
  out.reap.afterTheName = cast();
  // Her picture was attached by casting her, so it leaves with her — muting is
  // for a file you might put back, and there is nobody left to put it back for.
  out.reap.andHerPictures = refs();
  // And all of it is in the blob, which is what queues.
  out.reap.blob = JSON.parse(node.widgets[0].value).segments[0].assets
    .map((a) => `${a.handle}${a.enabled === false ? "!" : ""}`).join(",");
} catch (error) {
  out.errors.push(`reap: ${error.stack}`);
}

// ---- and the switch that does it by hand ------------------------------------
//
// The same mute a LoRA carries, on a reference: out of the run, kept exactly as
// it was attached. It is the other half of the deletion above — that is how you
// take a picture out of a shot while writing, this is how you do it without
// touching the sentence, and it is the only way back from either.
//
// Not the name, which is how a LoRA spells it: a reference's name is already the
// door onto its card. So it is a glyph beside the ✕, and this presses it.
try {
  const node = fakeNode("MiniMaxH3Creator", "creator_data", ONE_SHOT);
  await ext.nodeCreated(node);
  const editor = node.mmcBody.faceBody();
  const shot = node.mmcBody.timeline.segments[0];
  editor.prompt.hooks.onAttach({ path: "doors/red.png", kind: "image" });
  const asset = shot.assets[0];
  const mute = () => editor.assetsHost.querySelectorAll(".mmc-asset-mute")[0];
  const press = () => mute()?.listeners?.click?.forEach((fn) => fn({
    preventDefault() {}, stopPropagation() {},
  }));
  const chip = () => String(editor.assetsHost.querySelectorAll(".mmc-asset")[0]?.className ?? "")
    .split(" ").includes("off");

  const liveMode = S.mode(shot);
  press();
  const offMode = S.mode(shot);
  const dimmedWhileOff = chip();
  const blob = JSON.parse(node.widgets[0].value).segments[0].assets[0];
  press();
  out.mute = {
    liveMode, offMode, backMode: S.mode(shot),
    // Attached throughout — that is the whole difference between this and ✕.
    kept: shot.assets.length,
    file: shot.assets[0]?.filename,
    // The blob is what queues, and compile reads exactly this key.
    written: blob?.enabled,
    // ...and absent again once it is live, so nothing that was never muted
    // grows a key.
    clean: JSON.parse(node.widgets[0].value).segments[0].assets[0]?.enabled === undefined,
    dimmedWhileOff, dimmedAfter: chip(),
  };
} catch (error) {
  out.errors.push(`mute: ${error.stack}`);
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

// ---- what the model reads ---------------------------------------------------
//
// The rail under the prompt box, opened. The failure it exists for shipped once
// and was completely silent: the hook the lone-shot face handed the box called
// `this.compiledFor`, a method that lives on the other class, so opening the
// panel threw inside an async function nobody awaited and the box just sat
// there empty. So this presses the rail for real and reads back what landed —
// a panel that draws nothing is the bug, whatever the reason.
try {
  const first = (root, cls) => root.querySelectorAll("." + cls)[0] ?? null;
  const node = fakeNode("MiniMaxH3Creator", "creator_data", ONE_SHOT);
  await ext.nodeCreated(node);
  const rail = first(node.mmcBody.root, "mmc-compiled-rail");
  rail?.listeners?.click?.forEach((fn) => fn({ stopPropagation() {}, preventDefault() {} }));
  // The rail draws its waiting state before it asks, so there is something on
  // screen either side of this await.
  const waiting = first(node.mmcBody.root, "mmc-compiled-doc")?.children.length ?? 0;
  // Let the stubbed fetch and the .json() inside it settle.
  await new Promise((done) => setTimeout(done, 0));
  const doc = first(node.mmcBody.root, "mmc-compiled-doc");
  const keys = (doc?.children ?? [])
    .map((block) => (first(block, "mmc-compiled-key")?.text ?? "").trim())
    .filter(Boolean);
  out.compiled = {
    settled: doc?.children.length ?? 0,
    // Not on the fold's <summary>: it was, and every click that missed it
    // folded the prompt away instead of opening anything.
    railOutsideTheHead: !!rail && rail.parent?.className !== "mmc-prompt-head",
    waiting,
    keys,
    // The block holding the description is marked, and it is the only one.
    mine: (doc?.children ?? [])
      .filter((block) => String(block.className ?? "").split(" ").includes("mine"))
      .map((block) => (first(block, "mmc-compiled-key")?.text ?? "").trim()),
  };
} catch (error) {
  out.errors.push(`compiled: ${error.stack}`);
}

// ---- the body leaves the node, and comes back -------------------------------
//
// The fullscreen editor borrows the body's element rather than rebuilding one.
// That only holds if the element can travel: `attach()` gives the DOM widget a
// wrapper to keep positioning, and the editor moves the body between that
// wrapper and its own column. What is checked is the round trip, because the
// failure it guards against is silent — a body that goes fullscreen and does
// not come back leaves a node with a blank face and no error anywhere.
try {
  const fs = await import("./js/minimax_creator/fullscreen.js");
  const node = fakeNode("MiniMaxH3Creator", "creator_data", ONE_SHOT);
  await ext.nodeCreated(node);
  // The editor scans the graph for the piece and its PreStage, so the node has
  // to actually be in one — `nodeCreated` runs before the frontend adds it.
  node.graph._nodes.push(node);
  app.graph = node.graph;

  const body = node.mmcBody;
  const parked = body.root.parent === node.mmcHost;

  fs.openFullscreen(node);
  out.__docked = body.satellite?.docked?.className === "mmc-fs-dock";
  const shell = document.body.children.at(-1);
  const inShell = body.root.parent?.className === "mmc-fs-col";
  // Read before the press below, which puts the shell into its working state
  // and turns the Render label into a progress report.
  const opened = shell?.className === "mmc-fs";
  const hasRender = (shell?.text ?? "").includes("Render");

  // Each press names its node. Both bodies are outputs of one graph, so a
  // plain queue runs the pair — which is what the shell used to do, and why
  // touching the still's prompt made the next Render remake the still too.
  const press = (root, cls) => {
    const hit = root.querySelectorAll("." + cls)[0];
    hit?.listeners?.click?.forEach((fn) => fn({ stopPropagation() {}, preventDefault() {} }));
    return globalThis.__queued;
  };
  const raw = press(shell, "mmc-fs-run");
  // The same argument, read by both generations of frontend. 1.47 and 1.49+
  // normalize an array into `{ queueNodeIds }`; 1.44, 1.45 and 1.48 take the
  // whole argument *as* the id list and forward it verbatim to the server as
  // `partial_execution_targets`. Reported in #27 as "The prompt has no
  // outputs": an object reaches the older ones intact, the server asks whether
  // the node id is one of its *keys*, and a graph whose output node is sitting
  // right there is refused for having none.
  const shotAim = Array.isArray(raw) ? raw : raw?.queueNodeIds;
  // `x in partial_execution_list` as execution.validate_prompt spells it —
  // over a list it is the ids, over a dict it is the keys.
  const reaches = (targets) => (Array.isArray(targets)
    ? targets.includes(String(node.id))
    : Object.keys(targets ?? {}).includes(String(node.id)));
  const everyFrontend = reaches(shotAim) && reaches(raw);
  const settle = () => new Promise((done) => setTimeout(done, 0));
  const runLabel = () => shell?.querySelectorAll(".mmc-fs-run")[0]?.text ?? "";
  // The press that was accepted stands as a report of the render it started.
  await settle();
  const busyWhenAccepted = runLabel().includes("Sampling");
  // ...and the press that was refused does not. ComfyUI catches the refusal
  // itself — dialog up, promise resolved — so nothing here rejects and nothing
  // is announced, and a row that only ever spends its optimism on success goes
  // on saying "Sampling" over a render that was never queued. #27, where the
  // log shows the way out that leaves: Cancel, three times.
  globalThis.__refuse = true;
  press(shell, "mmc-fs-run");
  await settle();
  const freeAgainWhenRefused = runLabel().includes("Render");
  globalThis.__refuse = false;

  fs.close();
  out.fullscreen = {
    // The queue is aimed, not broadcast.
    rendersOneNode: JSON.stringify(shotAim) === JSON.stringify([String(node.id)]),
    // ...at a node the server can find, whichever frontend forwards the aim.
    everyFrontend,
    busyWhenAccepted,
    freeAgainWhenRefused,
    // The widget is handed a wrapper, never the body itself.
    widgetHost: node.dom?.className,
    parkedOnTheNode: parked,
    opened,
    bodyMoved: inShell,
    // The one control the canvas used to provide, and the one that stops it
    // being provided twice.
    hasRender,
    hasCancel: (shell?.text ?? "").includes("Cancel"),
    // Gallery and Settings stay in the body's rail; the bar does not repeat them.
    barIsNotARail: !(shell?.children?.[0]?.text ?? "").includes("Gallery"),
    // The satellite stops following and hands its stage over.
    dockedWhileOpen: out.__docked,
    undocked: body.satellite?.docked === null,
    // …and the body is back where the widget can position it.
    cameBack: body.root.parent === node.mmcHost,
    closed: !document.body.children.includes(shell),
  };
} catch (error) {
  out.errors.push(`fullscreen: ${error.message}`);
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

  // The Appearance tab: three sections, in the order they are drawn — four
  // points on the text scale, two answers on the colour, four on the surface
  // separation. Each is a number or a class the stylesheet reads, so for each
  // one the press has to land in two places: on the server, and on the document
  // element. A setting stored and never drawn is the failure being watched for.
  tabButtons[3].listeners.click[0]();
  // The pin lives in styles.js, and it is two facts: the preference from this
  // page and whether the shell is up. Imported here so the second one can be
  // said out loud without opening a real fullscreen editor.
  const packStyles = await import("./js/minimax_creator/styles.js");
  const setOpts = () => {
    const found = [];
    const walk = (node) => {
      if (node.className === "mmc-opt mmc-set-opt") found.push(node);
      (node.children ?? []).forEach(walk);
    };
    walk(page);
    return found;
  };
  // Rows are counted off in section order. A re-render replaces the nodes, so
  // this is re-read after every press rather than held.
  const sizes = setOpts();
  out.settings.textRows = sizes.slice(0, 4).map((o) => o.getAttribute("aria-checked"));
  out.settings.themeRows = sizes.slice(4, 6).map((o) => o.getAttribute("aria-checked"));
  out.settings.liftRows = sizes.slice(6, 10).map((o) => o.getAttribute("aria-checked"));
  out.settings.textPercents = page.text.includes("92%") && page.text.includes("125%");
  out.settings.liftPercents = page.text.includes("60%") && page.text.includes("180%");
  sizes[2].listeners.click[0]();
  await new Promise((done) => setTimeout(done, 0));
  out.settings.textPosted = globalThis.__posted.at(-1);
  out.settings.typeVar = document.documentElement.style["--mmc-type"];

  // Pinning the pack dark is a class rather than a property: what it turns on is
  // a block of tokens and the light-accent correction it has to turn off. It is
  // also two facts and not one — the preference *and* an open shell — so setting
  // it from this page must not by itself darken anything: the node faces behind
  // this page are part of nodes ComfyUI draws in its own palette.
  setOpts()[5].listeners.click[0]();
  await new Promise((done) => setTimeout(done, 0));
  out.settings.themePosted = globalThis.__posted.at(-1);
  out.settings.darkClassIdle = document.documentElement.classList.contains("mmc-force-dark");
  // With the shell up, the same preference does apply.
  packStyles.noteFullscreen(true);
  out.settings.darkClassOpen = document.documentElement.classList.contains("mmc-force-dark");
  packStyles.noteFullscreen(false);
  out.settings.darkClassShut = document.documentElement.classList.contains("mmc-force-dark");
  // And going back to following has to leave it off even with the shell up — a
  // pin that cannot be unpinned is worse than no pin.
  setOpts()[4].listeners.click[0]();
  await new Promise((done) => setTimeout(done, 0));
  packStyles.noteFullscreen(true);
  out.settings.followClass = document.documentElement.classList.contains("mmc-force-dark");
  packStyles.noteFullscreen(false);

  setOpts()[8].listeners.click[0]();
  await new Promise((done) => setTimeout(done, 0));
  out.settings.liftPosted = globalThis.__posted.at(-1);
  out.settings.liftVar = document.documentElement.style["--mmc-lift"];
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
      // The pill that grows the piece a shot — only ever on the one-shot face,
      // because on a strip the way to another card is the strip.
      grow: has(node.mmcBody.root, "mmc-grow-shot"),
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
               grow: has(node.mmcBody.root, "mmc-grow-shot") };
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
      if (!hit && String(n.className ?? "").split(" ").includes("mmc-grow-shot")) hit = n;
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

// ---- the way into the fullscreen shell --------------------------------------
//
// The shell has always had a command and a keybinding, and the setting in
// ComfyUI's own page decides what a *new* node opens as — none of which is a
// door you can see. Both faces grow one, and the node's menu carries a third.
try {
  const shot = { prompt: "a lighthouse", assets: [], loras: [], duration_s: 6 };
  const face = (segments) => {
    const node = fakeNode("MiniMaxH3Creator", "creator_data", JSON.stringify({
      version: 2, models: {}, segments,
    }));
    return node;
  };
  const hunt = (root, cls) => {
    let hit = null;
    const walk = (n) => {
      if (!hit && String(n.className ?? "").split(" ").includes(cls)) hit = n;
      (n.children ?? []).forEach(walk);
    };
    walk(root);
    return hit;
  };
  const one = face([{ ...shot }]);
  await ext.nodeCreated(one);
  const strip = face([{ ...shot }, { ...shot }]);
  await ext.nodeCreated(strip);
  // The window over a card is not a node face and has no node to draw over.
  const card = new (await import("./js/minimax_creator/editor.js")).CreatorEditor({
    state: { ...shot }, onCommit: () => {},
  });
  // The menu entry is installed on the node *type*, not on an instance, so it
  // is registered the way ComfyUI registers it and then called off the
  // prototype with a node as `this`.
  const nodeType = { prototype: {} };
  ext.beforeRegisterNodeDef?.(nodeType, { name: "MiniMaxH3Creator" });
  const menu = [];
  nodeType.prototype.getExtraMenuOptions?.call(one, null, menu);
  out.fsDoor = {
    onShot: !!hunt(one.mmcBody.root, "mmc-tool-expand"),
    onStrip: !!hunt(strip.mmcBody.root, "mmc-fs-enter"),
    notInACard: !hunt(card.root, "mmc-tool-expand"),
    inTheMenu: menu.some((entry) => String(entry.content).toLowerCase().includes("fullscreen")),
  };
} catch (error) {
  out.errors.push(`fullscreen door: ${error.message}`);
}

// ---- the cast shelf, summoned from a name in the sentence -------------------
//
// The simple fullscreen view draws neither the Cast tool nor the shelf: casting
// is the @ menu's roster, building is the library's Cast tab, and removing
// somebody is deleting their chip. The one thing left over is editing the copy
// of somebody that lives in *this* piece, and clicking their name is what asks
// for it. Driven through the editor here: this block is the hand-off, and the
// block below it performs the press.
try {
  const node = fakeNode("MiniMaxH3Creator", "creator_data", JSON.stringify({
    version: 2, models: {},
    subjects: [{ handle: "vera", takes: "person", from: [] }],
    segments: [{ prompt: "@vera waits", assets: [], loras: [], duration_s: 6 }],
  }));
  await ext.nodeCreated(node);
  const editor = node.mmcBody.editor;
  // The card, said out loud. The body is the node's own either way — the shell
  // borrows it — so this is the only thing that tells the two views apart, and
  // driving the summons without it was driving it on a face.
  editor.castResident = false;
  const shut = () => {
    let hit = null;
    const walk = (n) => {
      if (!hit && String(n.className ?? "").split(" ").includes("mmc-cast-shut")) hit = n;
      (n.children ?? []).forEach(walk);
    };
    walk(editor.castHost);
    return hit;
  };
  editor.openCastMember("vera");
  const opened = {
    open: editor.castOpen === true,
    summoned: editor.castSummoned === true,
    onThem: editor.castShelf?.opened?.handle === "vera",
    marked: String(editor.castShelf?.root?.className ?? "").split(" ").includes("summoned"),
    hasShut: !!shut(),
  };
  shut()?.listeners?.click?.[0]?.();
  await new Promise((done) => setTimeout(done, 0));
  // A name nobody answers to leaves the shelf exactly as it was.
  editor.openCastMember("nobody");
  out.castSummon = {
    ...opened,
    shutClosed: editor.castOpen === false && editor.castSummoned === false,
    strangerIgnored: editor.castOpen === false,
  };
} catch (error) {
  out.errors.push(`cast summon: ${error.message}`);
}

// ---- the card that draws no shelf: a press puts it up, a press takes it away -
//
// The simple fullscreen card has no cast drawer and no Cast tool, so the only
// shelf it can show is one a press summoned — and the only way to be rid of it
// is the same press again. That failed for a year of the wrong question: the
// body the card borrows is the *node's* body, `nodeId` and all, so asking
// "have I got a node?" answered "the shelf is a row of me" for a card that
// draws no shelf, and the second press left it standing. The card says which
// it is now (fullscreen.js sets `castResident`), and this drives both answers.
try {
  const first = (root, sel) => root.querySelectorAll(sel)[0] ?? null;
  const node = fakeNode("MiniMaxH3Creator", "creator_data", JSON.stringify({
    version: 2, models: {},
    subjects: [{ handle: "vera", takes: "person", from: [] }],
    segments: [{ prompt: "@vera waits", assets: [], loras: [], duration_s: 6 }],
  }));
  await ext.nodeCreated(node);
  const editor = node.mmcBody.editor;
  const box = editor.prompt.root;
  const press = () => box.listeners?.click?.forEach((fn) => fn({
    target: first(box, '.mmc-ref-cast[data-handle="vera"]'),
    preventDefault() {}, stopPropagation() {},
  }));
  const rows = () => (editor.castHost.children ?? []).length;

  editor.castResident = false;
  editor.render();
  const cardEmpty = rows() === 0;
  press();
  const cardOpen = { rows: rows(), on: editor.castShelf?.opened?.handle ?? null,
                     marked: String(editor.castShelf?.root?.className ?? "")
                       .split(" ").includes("summoned") };
  press();
  const cardShut = rows();

  // And the face, where the drawer *is* a row: the same second press closes the
  // member without taking the drawer with them.
  editor.castResident = true;
  editor.castSummoned = false;
  editor.castOpen = false;
  editor.render();
  const faceRows = rows();
  press();
  const faceOn = editor.castShelf?.opened?.handle ?? null;
  press();
  out.castCard = {
    cardEmpty, ...cardOpen, cardShut, faceRows, faceOn,
    faceKept: rows(), faceClosed: editor.castShelf?.opened ?? null,
  };
} catch (error) {
  out.errors.push(`cast card: ${error.stack}`);
}

// ---- ...and it survives the editor being rebuilt under the open shell -------
//
// `castResident` is what the card says about itself, and it lived on the editor
// — which is not what outlives the view. The face's editor is rebuilt whenever
// the segment object under it changes: a preset carrying a strip parses new
// segments, Clear makes one, a re-read of the blob makes all of them. The
// replacement knew nothing about the shell it was born into, answered "the
// shelf is a row of me" from its node id alone, and so a press on a name built
// a resident drawer that the simple view's stylesheet hides. The press looked
// dead, and the only way out was a round trip through the full view — which
// calls `setCastResident` again and repairs it by accident.
//
// The body remembers now and stamps whoever it builds next. Driven through the
// real shell, because the hand-off is the thing under test.
try {
  const fs = await import("./js/minimax_creator/fullscreen.js");
  globalThis.localStorage = { getItem: (k) => (k === "mmc.fullscreen.view" ? "simple" : null),
                              setItem() {}, removeItem() {} };
  const node = fakeNode("MiniMaxH3Creator", "creator_data", JSON.stringify({
    version: 2, models: {},
    subjects: [{ handle: "vera", takes: "person", from: [] }],
    segments: [{ prompt: "@vera waits", assets: [], loras: [], duration_s: 6 }],
  }));
  await ext.nodeCreated(node);
  node.graph._nodes.push(node);
  app.graph = node.graph;
  fs.openFullscreen(node);
  const simple = String(document.body.children.at(-1)?.className ?? "").includes("simple");
  const told = node.mmcBody.editor?.castResident === false;

  // What a preset apply carrying a strip does to the face.
  node.mmcBody.dropFaceEditor();
  node.mmcBody.render();
  const editor = node.mmcBody.editor;
  const box = editor.prompt.root;
  box.listeners?.click?.forEach((fn) => fn({
    target: box.querySelectorAll('.mmc-ref-cast[data-handle="vera"]')[0],
    preventDefault() {}, stopPropagation() {},
  }));
  out.castRebuilt = {
    simple, told,
    fresh: editor !== undefined && editor.castResident === false,
    notResident: editor.castResidentHere() === false,
    // The whole point: the drawer that arrives is the summoned one, which is
    // the only kind this view draws.
    summoned: editor.castSummoned === true,
    marked: String(editor.castShelf?.root?.className ?? "").split(" ").includes("summoned"),
    onThem: editor.castShelf?.opened?.handle ?? null,
  };
  fs.close();
} catch (error) {
  out.errors.push(`cast rebuilt: ${error.stack}`);
}

// ---- and summoned by clicking the name, which is the gesture ----------------
//
// The block above drives `openCastMember` directly, on the grounds that the
// gesture is the box's business and the hand-off is what a body test can see.
// That left the gesture itself — the only part of this a person ever performs —
// covered by nothing, and it has been broken by unrelated work in the prompt box
// more than once: the chip stops carrying the class, or the hook stops being
// passed, or the handler is hung on an element the click never reaches, and
// every one of those looks exactly like a chip that does nothing.
//
// So this clicks it. The listener is delegated to the box, which is where a
// chip rebuilt on every keystroke has to be listened for, so the press is
// delivered the way the browser delivers it: to the box, with the chip as the
// target.
//
// A look is a cast member too — `presets.castIntoPiece` makes a style subject —
// so the same press opens it, and that is checked here rather than assumed.
try {
  const first = (root, sel) => root.querySelectorAll(sel)[0] ?? null;
  const node = fakeNode("MiniMaxH3Creator", "creator_data", JSON.stringify({
    version: 2, models: {},
    subjects: [{ handle: "vera", takes: "person", description: "close-cropped hair" },
               { handle: "lego_brickfilm", takes: "style", description: "a brickfilm look" }],
    segments: [{ prompt: "@lego_brickfilm, @vera waits by @img-1",
                 assets: [{ handle: "img-1", kind: "image", filename: "a.png",
                            role: "reference" }],
                 loras: [], duration_s: 6 }],
  }));
  await ext.nodeCreated(node);
  const editor = node.mmcBody.editor;
  const box = editor.prompt.root;
  const press = (handle) => {
    const chip = first(box, `.mmc-ref-cast[data-handle="${handle}"]`);
    if (!chip) return false;
    box.listeners?.click?.forEach((fn) => fn({
      target: chip, preventDefault() {}, stopPropagation() {},
    }));
    return true;
  };
  // What the browser would do with the press if nobody stopped it: select the
  // whole chip and leave the name sitting in a blue block until you click
  // elsewhere. Cancelled at mousedown, which is where the selection is made.
  const held = (root, sel) => root.querySelectorAll(sel)[0] ?? null;
  const cancelled = (node) => {
    let stopped = false;
    box.listeners?.mousedown?.forEach((fn) => fn({
      target: node, preventDefault() { stopped = true; }, stopPropagation() {},
    }));
    return stopped;
  };
  const chips = box.querySelectorAll(".mmc-ref").length;
  // The other way this gesture dies, and the one no click can catch: the body
  // is rebuilt on a render, so the chip the press started on is detached before
  // the browser can finish the click on it. A face editor kept across renders is
  // what makes a chip pressable at all.
  const beforeEditor = editor;
  const beforeChip = first(box, `.mmc-ref-cast[data-handle="vera"]`);
  node.mmcBody.render();
  node.mmcBody.render();
  const stable = {
    editorKept: node.mmcBody.editor === beforeEditor,
    boxKept: node.mmcBody.editor?.prompt?.root === box,
    chipKept: first(box, `.mmc-ref-cast[data-handle="vera"]`) === beforeChip,
  };
  out.castClick = {
    ...stable,
    // Three chips: two names and a file, and only the names are somebody.
    chips,
    cast: box.querySelectorAll(".mmc-ref-cast").length,
    // The affordance: without it the chip is a pointer nobody grows.
    castable: String(box.className).split(" ").includes("mmc-prompt-castable"),
    pressedPerson: press("vera"),
    onPerson: editor.castShelf?.opened?.handle ?? null,
    pressedStyle: press("lego_brickfilm"),
    onStyle: editor.castShelf?.opened?.handle ?? null,
  };
  out.castClick.noSelectOnName =
    cancelled(held(box, `.mmc-ref-cast[data-handle="vera"]`));
  // ...and a file's chip is not a control, so it goes on selecting the way any
  // other part of the sentence does.
  out.castClick.fileStillSelects =
    !cancelled(held(box, `.mmc-ref[data-handle="img-1"]`));
  // The press is its own undo: the same name again shuts the card it opened.
  press("lego_brickfilm");
  out.castClick.shutAgain = editor.castShelf?.opened ?? null;
  // ...and a third press opens them once more, rather than latching shut.
  press("lego_brickfilm");
  out.castClick.reopened = editor.castShelf?.opened?.handle ?? null;
} catch (error) {
  out.errors.push(`cast click: ${error.stack}`);
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


// ---- a name is a door, in every box that draws one --------------------------
//
// The regression this exists for: `onCastChip` was wired on the Creator's face
// and nowhere else, so the Timeline window's standing prompt and a card's
// editor both drew cast chips that changed the cursor and did nothing. It was
// invisible from every other test — the chips render, the sentence queues, and
// only the click is dead.
try {
  const { openTimeline: openTimelineModal } = await import("./js/minimax_creator/timeline.js");
  const all = (root, cls) => {
    const hits = [];
    const walk = (n) => {
      if (String(n.className ?? "").split(" ").includes(cls)) hits.push(n);
      (n.children ?? []).forEach(walk);
    };
    walk(root);
    return hits;
  };
  // Read off the element rather than off the hook: the class is the pointer the
  // user is being promised, and a box that answers for the chip without wearing
  // it is the same dead click from the other side.
  const castable = (root) =>
    all(root, "mmc-prompt").map((box) => String(box.className).includes("mmc-prompt-castable"));

  const strip = fakeNode("MiniMaxH3Creator", "creator_data", JSON.stringify({
    version: 2, prompt: "@anna walks", models: {},
    assets: [{ handle: "ref-1", kind: "image", role: "reference", filename: "anna.png" }],
    subjects: [{ handle: "anna", from: ["ref-1"], takes: "person" }],
    segments: [{ prompt: "shot 1", assets: [], loras: [], duration_s: 5 },
               { prompt: "@anna at the door", assets: [], loras: [], duration_s: 5 }],
  }));
  await ext.nodeCreated(strip);

  const single = fakeNode("MiniMaxH3Creator", "creator_data", ONE_SHOT);
  await ext.nodeCreated(single);
  out.doors = { onTheFace: castable(single.mmcBody.root).join(",") };

  openTimelineModal({ timeline: strip.mmcBody.timeline,
                      onCommit: () => strip.mmcBody.commit() });
  await new Promise((done) => setTimeout(done, 0));
  const modal = document.body.children.at(-1);
  out.doors.inTheWindow = castable(modal).join(",");

  // ...and a card of the strip, which is where a cast is owned a level up. Its
  // editor used to look the piece's subjects up on the segment, find none, and
  // open nothing — while deleting a chip took nobody out of anything.
  const card = all(modal, "mmc-tl-card")[1] ?? all(modal, "mmc-tl-card")[0];
  card?.listeners?.dblclick?.[0]?.();
  await new Promise((done) => setTimeout(done, 0));
  const sheet = document.body.children.at(-1);
  out.doors.inACard = sheet === modal ? "no card opened" : castable(sheet).join(",");
} catch (error) {
  out.errors.push(`doors: ${error.stack}`);
}

// Clicking the name opens that member, and only that member — on a body with no
// node, where the shelf is not resident and has to arrive with the summons.
try {
  const node = fakeNode("MiniMaxH3Creator", "creator_data", ONE_SHOT);
  await ext.nodeCreated(node);
  const editor = node.mmcBody.faceBody();
  const box = editor.prompt;
  const anna = await box.hooks.castFromLibrary({
    handle: "anna", takes: "person",
    files: [{ slot: "from", filename: "anna/face.png", kind: "image" }],
  });
  // A style is a subject too — same shelf, same chip, same way out. This is the
  // shape `presetlib.castStill` puts in.
  const look = await box.hooks.castFromLibrary({
    handle: "claymation", takes: "style", description: "Claymation, fingerprint texture",
    files: [{ slot: "from", filename: "styles/clay.webp", kind: "image" }],
  });
  box.setValue(`@${look}, @${anna} at the door`);
  editor.state.prompt = box.getValue();

  box.hooks.onCastChip(look);
  out.summon = {
    opened: editor.castShelf?.opened?.handle ?? null,
    takes: editor.castShelf?.opened?.takes ?? null,
    // A name nobody answers to leaves the shelf exactly as it was, rather than
    // putting up an empty one.
    strangerLeavesItAlone: (() => {
      box.hooks.onCastChip("nobody");
      return editor.castShelf?.opened?.handle ?? null;
    })(),
  };

  // ...and deleting the style's chip takes the style off the node, picture and
  // all — the same reaping a cast member gets, because it is the same thing.
  box.root.children.find((n) => n.dataset?.handle === look)?.remove();
  box.onEdit();
  out.summon.styleGone = (node.mmcBody.timeline.subjects ?? [])
    .map((s) => s.handle).join(",");
  out.summon.andItsPicture = (node.mmcBody.timeline.segments[0].assets ?? [])
    .map((a) => a.filename).join(",");
} catch (error) {
  out.errors.push(`summon: ${error.stack}`);
}

// ---- the reference card -----------------------------------------------------
//
// The chip's four narrowing buttons are one door now. What this guards is the
// thing the simple fullscreen view could not do at all: take a picture that is
// at its default and make it a style reference.
try {
  const node = fakeNode("MiniMaxH3Creator", "creator_data", ONE_SHOT);
  await ext.nodeCreated(node);
  const editor = node.mmcBody.faceBody();
  const handle = editor.prompt.hooks.onAttach({ path: "doors/red.png", kind: "image" });
  const asset = editor.state.assets.find((a) => a.handle === handle);

  const all = (root, cls) => {
    const hits = [];
    const walk = (n) => {
      if (String(n.className ?? "").split(" ").includes(cls)) hits.push(n);
      (n.children ?? []).forEach(walk);
    };
    walk(root);
    return hits;
  };
  const door = all(editor.root, "mmc-asset-door")[0];
  out.refsheet = { hasDoor: Boolean(door), said: all(editor.root, "mmc-asset-said").length };
  door?.listeners?.click?.[0]?.({ currentTarget: door });
  const sheet = all(document.body, "mmc-refsheet")[0];
  out.refsheet.opened = Boolean(sheet);
  const options = all(sheet ?? { children: [] }, "mmc-refsheet-opt");
  out.refsheet.offers = options.map((o) => o.text.trim()).join(",");
  options.find((o) => o.text.trim() === "style")?.listeners?.click?.[0]?.();
  out.refsheet.takes = asset.takes ?? "full";
  // ...and the chip now says so, where before it said nothing until you opened
  // the row of buttons that were hidden for saying nothing.
  out.refsheet.chipSays = all(editor.root, "mmc-asset-said").map((n) => n.text).join(",");
} catch (error) {
  out.errors.push(`refsheet: ${error.stack}`);
}

// ---- the / menu -------------------------------------------------------------
try {
  const node = fakeNode("MiniMaxH3Creator", "creator_data", ONE_SHOT);
  await ext.nodeCreated(node);
  const box = node.mmcBody.faceBody().prompt;

  await box.openMenu("", "/");
  // The input folder answers with two files — openMenu re-reads it, so they go
  // in after. A bare "/" listing them under the sources is the failure this
  // checks for.
  box.library = [{ path: "doors/red.png", kind: "image" },
                 { path: "lamps/brass.png", kind: "image" }];
  out.slash = {
    sources: box.groups().flatMap((g) => g.options).map((o) => o.branch ?? o.door).join(","),
    head: box.groups()[0]?.head ?? null,
    // Typing searches every source at once, without choosing one first.
    across: (() => {
      box.query = "lamp";
      const found = box.groups().flatMap((g) => g.options)
        .map((o) => o.path ?? o.branch ?? `door:${o.door}`).join(",");
      box.query = "";
      return found;
    })(),
  };
  // Drilling into a source narrows what is listed; the way back restores it.
  box.branch = "refs";
  out.slash.inRefs = box.groups().map((g) => g.head).join("|");
  // The catalogue, searched in the menu rather than behind a door. This is the
  // thing the branch was missing: typing "claymation" after a slash found
  // nothing, not even inside the Style branch, because the branch was one row
  // that opened a window.
  box.branch = "style";
  await box.readStyles();
  const looks = () => box.groups().flatMap((g) => g.options);
  out.slash.styleRows = looks().filter((o) => o.kind === "style").length;
  box.query = "claymation";
  const clay = looks().filter((o) => o.kind === "style");
  out.slash.clay = clay.length;
  out.slash.clayFirst = clay[0]?.row?.lead ?? null;
  // ...and it is found from the top level too, without choosing Style first.
  box.branch = null;
  out.slash.clayFromEverything =
    looks().filter((o) => o.kind === "style").length > 0;
  // The whole descriptor is searched, not only the lead: "needle-felted" is in
  // the middle of one.
  box.query = "needle-felted";
  out.slash.midDescriptor = looks().filter((o) => o.kind === "style").length > 0;
  box.query = "";

  // `@` is untouched by any of it — the two openings share one renderer and
  // this is the half that already worked.
  await box.openMenu("", "@");
  out.slash.mentionStillWorks = box.mode;
} catch (error) {
  out.errors.push(`slash: ${error.stack}`);
}

// ---- casting a look out of the atlas ----------------------------------------
//
// Three bugs in one gesture, all of them silent. The atlas is only read when its
// tab is *pressed*, so opening the library straight onto it showed the grid's
// empty line — which said "could not be read" about a read nobody had started.
// The handle a style is cast under has to satisfy SUBJECT_HANDLE_RE, and a
// quarter of the atlas opens on a number, so every one of those arrived as
// `@subject` while the button promised its own name. And nothing wrote the name
// into the sentence, so there was no chip to click even when it was right.
try {
  const { styleRows } = await import("./js/minimax_creator/presets/stylelib.js");
  const { styleCastMember } = await import("./js/minimax_creator/presetlib.js");
  const P = await import("./js/minimax_creator/presets.js");
  const rows = styleRows();
  out.atlas = { rows: rows.length };

  const node = fakeNode("MiniMaxH3Creator", "creator_data", ONE_SHOT);
  await ext.nodeCreated(node);
  const piece = node.mmcBody.timeline;
  const shot = piece.segments[0];
  shot.prompt = "A woman waits at the gate.";

  // The row whose name opens on a number — the case that produced `@subject`.
  const numeric = rows.find((row) => /^[0-9]/.test(row.name)) ?? rows[0];
  out.atlas.rowName = numeric.name;
  // The very member `castStill` passes — not one the test made up, or this
  // checks a rule nothing follows. Built without a fetch or an upload, which is
  // the point of it: a look's frame is a file the pack already ships and is
  // cited where it sits.
  const cast = styleCastMember(numeric, 0);
  out.atlas.cited = cast.files[0].filename;
  P.applyToPiece({ cast }, ["cast"], piece,
    node.mmcBody.widgetIO?.() ?? { set() {}, value: () => 0 }, { from: "cast" });

  const look = (piece.subjects ?? [])[0] ?? {};
  out.atlas.handle = look.handle;
  out.atlas.takes = look.takes;
  // ...and it leads the prompt that is actually on screen — a piece of one shot
  // wears that shot's editor, not the standing prompt behind it.
  out.atlas.leads = shot.prompt;
  out.atlas.standingLeftAlone = piece.prompt;

  // A second look replaces the first rather than stacking on it — the promise
  // the descriptor-swap used to make, kept now that a look is a subject.
  const other = rows.find((row) => /^[A-Za-z]/.test(row.name) && row !== numeric);
  const second = styleCastMember(other, 0);
  P.applyToPiece({ cast: second }, ["cast"], piece,
                 { set() {}, value: () => 0 }, { from: "cast" });
  out.atlas.afterSecond = {
    prompt: shot.prompt,
    cast: (piece.subjects ?? []).map((s) => s.handle).join(","),
    // ...and the first look's picture goes with it, rather than riding into
    // every render as an uncited reference.
    files: (shot.assets ?? []).map((a) => a.filename).join(","),
    cited: second.files[0].filename,
  };
} catch (error) {
  out.errors.push(`atlas: ${error.stack}`);
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

# ---- ...and deleted it out again ---------------------------------------------
#
# The chip is the attachment, so deleting it is the way out. What makes this a
# contract rather than a tidy-up is the last line: `assets` is what gets encoded
# and shown to the model, and a reference nobody mentions conditions the render
# exactly as hard as one they do.

reap = report.get("reap", {})
check("the box knows which chips it is showing", reap.get("chips"), 3)
check("...over the shot's own references", reap.get("refs"), "img-1,img-2,img-3")
check("...and the piece's cast", reap.get("cast"), "anna")
# One occurrence deleted is not the reference deleted: the soundscape still
# writes the lamp, so the lamp stays.
check("a handle still written elsewhere survives losing its chip",
      reap.get("citedElsewhere"), "img-1,img-2,img-3")
check("a reference whose last mention goes is muted, not detached",
      reap.get("afterTheRef"), "img-1,img-2!,img-3")
check("...and takes nobody out of the cast with it", reap.get("castUntouched"), "anna")
check("deleting a name takes the member off the shelf", reap.get("afterTheName"), "")
check("...and the pictures casting her attached go with her", reap.get("andHerPictures"),
      "img-2!,img-3")
check("...and all of it is written through to the blob that queues",
      reap.get("blob"), "img-2!,img-3")

# The same switch by hand: the glyph beside the ✕, which is where the other
# thing you can do to a whole file already lives.
mute = report.get("mute", {})
check("a live reference routes the shot to Ref2VA", mute.get("liveMode"), "REF2VA")
check("...and muting it takes the shot back to text", mute.get("offMode"), "T2VA")
check("...and unmuting brings it back", mute.get("backMode"), "REF2VA")
check("a muted reference is still attached", mute.get("kept"), 1)
check("...with its file still on it", mute.get("file"), "doors/red.png")
check("...said in the blob compile reads", mute.get("written"), False)
check("...and unsaid again once it is live", mute.get("clean"), True)
check("the chip is dimmed while it is out of the run", mute.get("dimmedWhileOff"), True)
check("...and lit again after", mute.get("dimmedAfter"), False)

# ---- the body leaves the node, and comes back --------------------------------
#
# The fullscreen editor is a host, not a second frontend: it moves the body's
# element into a shell and puts it back. Everything below is that contract.

full = report.get("fullscreen", {})
check("the DOM widget is handed a wrapper, not the body",
      full.get("widgetHost"), "mmc-widget-host")
check("...which is where the body sits on the canvas", full.get("parkedOnTheNode"), True)
check("the shell opens", full.get("opened"), True)
check("...and the body moves into its column", full.get("bodyMoved"), True)
check("...with a Render button, since ComfyUI's is behind it", full.get("hasRender"), True)
# A pre-stage is an output node of the same graph, so a plain queue runs it
# alongside the shot — right for the canvas Run button, wrong for a button at
# the foot of one column. Each press names its own node.
check("...that queues that node alone, not every output in the graph",
      full.get("rendersOneNode"), True)
# The aim is sent as a bare array, which is the one shape both generations of
# frontend read the same way. Wrapped in `{ queueNodeIds }` it survives 1.47 and
# 1.49+ and reaches 1.44, 1.45 and 1.48 as the id list itself — so the server is
# asked for a node id among the *keys* of an object, finds none, and refuses the
# prompt for having no outputs. #27.
check("...and reaches the node whichever frontend forwards the aim",
      full.get("everyFrontend"), True)
check("...and the row reports the render it started",
      full.get("busyWhenAccepted"), True)
# ComfyUI catches a refused prompt itself, so the press resolves and the row's
# optimism was never spent: "Sampling" over a render that was never queued, and
# Cancel the only thing left to press. #27.
check("...and offers the press again when the prompt is refused",
      full.get("freeAgainWhenRefused"), True)
check("...and a Cancel beside it", full.get("hasCancel"), True)
check("...but no second Gallery: the rail already has one",
      full.get("barIsNotARail"), True)
check("the satellite hands its stage to the dock", full.get("dockedWhileOpen"), True)
check("closing gives the picture back to the canvas", full.get("undocked"), True)
check("...and the body back to the node", full.get("cameBack"), True)
check("...and takes the shell down with it", full.get("closed"), True)

# The settings page owns four questions now — how good the file is, where it
# goes, what the node faces offer and what a render does on the way there, and
# how large they are drawn — so it has four tabs, and the folder fields are the
# only place the prefixes can be set. The third is "General" rather than
# "Nodes": it carries a Rendering group as well as a Nodes one, so the old name
# was the name of half of it.
settings = report.get("settings", {})
check("the settings page has all four tabs", settings.get("tabs"),
      ["Quality", "Folders", "General", "Appearance"])
# Every row on the tab, in order, with each setting's default checked on a fresh
# settings file: previews ship playing, the reference cache ships on, and the
# advanced controls and the shift pills ship off. Advanced leads, because it
# decides how much of the rest of the tab there is — the turbo lead-in is an
# advanced control and its three rows are simply not on the page while it is
# off, which is what makes this list four pairs and not four pairs plus a
# triple. Then preview playback, which governs the biggest thing a node draws,
# the reference cache, and the shift pills last, which change only what is
# drawn.
#
# There used to be a fourth pair here, for whether the compiler wrote each
# reference's scope into the prompt. It is not a choice any more — a label the
# prompt never defines is a label pointing at nothing — so the setting is gone
# and the prompt box shows what is actually sent instead.
check("the node settings show their defaults checked",
      settings.get("shiftRows"),
      ["true", "false", "true", "false", "true", "false", "true", "false"])
# And with the advanced controls on, the turbo lead-in is back on the page: the
# four pairs plus its three rows. That is the whole of what the switch does to
# this tab — it adds a section, it never disables one.
check("advanced controls bring the turbo lead-in back to the page",
      (settings.get("advancedRows"), settings.get("advancedLeadIn")), (11, True))
check("the quality tab shows the encoder value", settings.get("quality"), True)
# The text scale: four points with the drawn sizes checked on a fresh file, each
# row saying what it is as a percentage the way the quality rows say their crf.
check("the appearance tab offers four sizes with the default checked",
      settings.get("textRows"), ["false", "true", "false", "false"])
check("...each with its multiplier as a percentage", settings.get("textPercents"), True)
# And the press has to land in two places. The multiplier goes to the server,
# because it is a per-machine preference like every other one on this page; and
# it goes onto the document element, because a scale nothing reads is a number
# in a file. `--mmc-type` on :root is what every rule in styles/ multiplies by.
check("choosing a size posts the multiplier", settings.get("textPosted"),
      {"text_scale": 1.12})
check("...and writes it where the stylesheet reads it",
      settings.get("typeVar"), "1.12")
# The colour: two answers, following checked on a fresh file. Following is not a
# neutral default here — it is the whole of what the stylesheet does unaided, so
# a fresh file has to land on it.
check("the appearance tab offers both palettes with following checked",
      settings.get("themeRows"), ["true", "false"])
check("pinning the pack dark posts the theme", settings.get("themePosted"),
      {"theme": "dark"})
# The pin is where it is *not* applied that matters. A node face is part of a
# node ComfyUI draws in its own palette, so the preference alone changes nothing.
check("...but on its own darkens nothing, so no node face becomes an island",
      settings.get("darkClassIdle"), False)
check("...and with the fullscreen shell up it takes hold",
      settings.get("darkClassOpen"), True)
check("...and leaving the shell puts the palette back",
      settings.get("darkClassShut"), False)
check("...and following again stays light even with the shell up",
      settings.get("followClass"), False)
# The surface separation: four points, the drawn ladder checked, each row saying
# what it is as a percentage the way the sizes above do.
check("the appearance tab offers four separations with the default checked",
      settings.get("liftRows"), ["false", "true", "false", "false"])
check("...each with its multiplier as a percentage", settings.get("liftPercents"), True)
check("choosing a separation posts the multiplier", settings.get("liftPosted"),
      {"surface_lift": 1.4})
check("...and writes it where the stylesheet reads it",
      settings.get("liftVar"), "1.4")
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

# The compiled prompt, under the box rather than in place of it.
compiled = report.get("compiled", {})
check("the rail is not on the prompt's own fold head", compiled.get("railOutsideTheHead"), True)
check("opening it draws a waiting state before it asks", compiled.get("waiting"), 3)
# Every section the compiler wrote, under the field name the model is handed.
check("...and then a block per section, keyed as the model is given them",
      (compiled.get("settled"), compiled.get("keys")),
      (2, ["subject_definitions", "detailed_description yours"]))
# One mark, on the one block that is yours: that is the whole answer to "what
# did the compiler add", and a panel that marks everything or nothing gives it
# back as a question.
check("the description is marked as yours, and nothing else is",
      compiled.get("mine"), ["detailed_description yours"])

# Clicking somebody's name in the sentence opens them. The gesture, not the
# hand-off it ends in — this is the half that keeps being broken by work
# elsewhere in the box, because nothing performed it.
click = report.get("castClick", {})
check("both names and the file are chips", click.get("chips"), 3)
check("...and both are marked as somebody, a look included", click.get("cast"), 2)
check("...in a box that says so with the pointer", click.get("castable"), True)
# A press is a pointerdown and a click on the same element. Rebuild the body
# between the two and the browser has nothing to fire the click on — which is a
# chip that does nothing, from an edit nowhere near the prompt box.
check("a render leaves the face editor where it was", click.get("editorKept"), True)
check("...the box with it", click.get("boxKept"), True)
check("...and the chip the press would land on", click.get("chipKept"), True)
check("clicking a person opens them on the shelf",
      (click.get("pressedPerson"), click.get("onPerson")), (True, "vera"))
check("...and clicking a look opens the look",
      (click.get("pressedStyle"), click.get("onStyle")), (True, "lego_brickfilm"))
# A press on a name is a command, so the browser must not also turn the name
# into a blue block — which is what a click on a contenteditable="false" chip
# does if nobody stops it, and it stays one until you click somewhere else.
check("pressing a name makes no selection", click.get("noSelectOnName"), True)
check("...while a file's chip still selects", click.get("fileStillSelects"), True)
check("clicking the same name again shuts the card", click.get("shutAgain"), None)
check("...and once more opens it", click.get("reopened"), "lego_brickfilm")

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

door = report.get("fsDoor", {})
check("the shot face carries a way into the shell", door.get("onShot"), True)
check("...and so does the strip face", door.get("onStrip"), True)
check("...but a card's editor does not — there is no node to draw over",
      door.get("notInACard"), True)
check("the node's own menu carries it too", door.get("inTheMenu"), True)

summon = report.get("castSummon", {})
check("clicking a name puts the shelf up", summon.get("open"), True)
check("...on that member, and nobody else", summon.get("onThem"), True)
check("...marked as summoned, so a view that hides the shelf shows this one",
      summon.get("marked"), True)
check("...with the chevron that takes it away", summon.get("hasShut"), True)
check("closing the card closes the shelf it was summoned into",
      summon.get("shutClosed"), True)
check("a name nobody answers to leaves the shelf where it was",
      summon.get("strangerIgnored"), True)

card = report.get("castCard", {})
check("the card that draws no shelf opens with none", card.get("cardEmpty"), True)
check("...a press on a name puts one up", card.get("rows"), 1)
check("...on that member", card.get("on"), "vera")
check("...marked summoned, which is what the card's stylesheet shows",
      card.get("marked"), True)
check("...and the same press again takes it away entirely", card.get("cardShut"), 0)
check("a face draws the drawer whether or not anybody pressed", card.get("faceRows"), 1)
check("...a press opens somebody on it", card.get("faceOn"), "vera")
check("...and the press that closes them leaves the drawer", card.get("faceKept"), 1)
check("...with nobody open on it", card.get("faceClosed"), None)

# The same press, after the face's editor was rebuilt under the open shell —
# which is what applying a preset that carries a strip does. `castResident` used
# to live on the editor, so the replacement answered from its node id alone and
# put up a resident drawer the simple view hides. The body remembers it now.
rebuilt = report.get("castRebuilt", {})
check("the shell opens on the simple view", rebuilt.get("simple"), True)
check("...and tells the body's editor it draws no drawer", rebuilt.get("told"), True)
check("...an editor rebuilt under it is told the same", rebuilt.get("fresh"), True)
check("...and answers the same", rebuilt.get("notResident"), True)
check("...so a press on a name summons the drawer", rebuilt.get("summoned"), True)
check("...marked, which is what the card's stylesheet shows", rebuilt.get("marked"), True)
check("...on the member whose name was pressed", rebuilt.get("onThem"), "vera")

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

# ---- a name is a door -------------------------------------------------------
#
# `onCastChip` was wired on the Creator's face and nowhere else, so the Timeline
# window's standing prompt and a card's editor both drew cast chips that changed
# the cursor and did nothing. Every one of these read "false" before the fix, and
# nothing else in this file noticed: the chips render and the sentence queues.
doors = report.get("doors") or {}
check("a cast chip on the node face opens somebody", doors.get("onTheFace"), "true")
check("...and so does one in the timeline's standing prompt",
      doors.get("inTheWindow"), "true")
check("...and one in a card of the strip, whose cast is owned a level up",
      doors.get("inACard"), "true")

summon = report.get("summon") or {}
check("clicking a name opens that member", summon.get("opened"), "claymation")
check("a style is a subject like any other, and opens the same shelf",
      summon.get("takes"), "style")
check("a name nobody answers to leaves the shelf as it was",
      summon.get("strangerLeavesItAlone"), "claymation")
check("deleting a style's chip takes the style off the node",
      summon.get("styleGone"), "anna")
check("...and its picture with it", summon.get("andItsPicture"), "anna/face.png")

# ---- the reference card -----------------------------------------------------
#
# The chip's four narrowing buttons are one door now, which is what lets the
# simple fullscreen view narrow a reference at all: it hid any of them still
# holding a default, and the default is the answer you are trying to leave.
sheet = report.get("refsheet") or {}
check("a reference's handle is a button", sheet.get("hasDoor"), True)
check("...that opens the card", sheet.get("opened"), True)
check("...offering every narrowing, defaults included",
      sheet.get("offers"), "full,person,object,scene,style,match,max")
check("...and picking one lands on the asset", sheet.get("takes"), "style")
check("...where the chip then says so without being opened again",
      sheet.get("chipSays"), "style · max")

# ---- the / menu -------------------------------------------------------------
slash = report.get("slash") or {}
check("slash offers the three sources", slash.get("sources"), "style,cast,refs")
check("...under one head", slash.get("head"), "Bring in")
check("...and nothing else until something is asked",
      slash.get("sources"), "style,cast,refs")
check("typing searches every source at once, with the way to the picker under it",
      slash.get("across"), "lamps/brass.png,door:browse")
check("drilling into references narrows the menu to the input folder",
      slash.get("inRefs"), "Input folder")
check("the style branch lists the catalogue", slash.get("styleRows"), 40)
check("...typing finds the claymation entries", (slash.get("clay") or 0) > 0, True)
check("...by the medium their name opens on",
      "laymation" in (slash.get("clayFirst") or ""), True)
check("...and finds them from the top level too, without choosing Style first",
      slash.get("clayFromEverything"), True)
check("...searching the whole descriptor, not just its lead",
      slash.get("midDescriptor"), True)
check("and the @ menu is untouched by any of it",
      slash.get("mentionStillWorks"), "@")

# ---- casting a look out of the atlas ----------------------------------------
atlas = report.get("atlas") or {}
check("the shipped atlas reads", atlas.get("rows"), 941)
check("a look whose name opens on a number keeps its name",
      atlas.get("handle"), "look_2d_cutout_paper")
check("...and is cast as a style", atlas.get("takes"), "style")
check("...leading the prompt the node is actually showing",
      atlas.get("leads"), "@look_2d_cutout_paper, a woman waits at the gate.")
check("...and not the standing one behind it", atlas.get("standingLeftAlone"), "")
second = atlas.get("afterSecond") or {}
check("a second look replaces the first in the sentence",
      second.get("prompt"), "@claymation_animation_with, a woman waits at the gate.")
check("...and on the piece", second.get("cast"), "claymation_animation_with")
check("...taking the first one's picture with it",
      second.get("files"), second.get("cited"))
# The frame is cited where the pack ships it, not copied into ComfyUI/input —
# a copy per look ever cast used to pile up in the picker forever.
check("...and a look's frame is cited, not copied into the input folder",
      str(atlas.get("cited") or "").startswith("atlas:"), True)

passed(f"the frontend loads and all {len(report['nodes'])} bodies mount")

// Entry point. ComfyUI auto-imports every js/**/*.js as an extension, so this is
// the only file in the package allowed to have import side effects — everything
// under web/creator/ is a plain module it pulls in.

import { app } from "../../scripts/app.js";
import { installStyles } from "./creator/styles.js";
import { TimelineBody } from "./creator/timeline.js";
import { PreStageBody } from "./creator/prestage.js";
import { Satellite } from "./creator/satellite.js";
import { adopted, SAMPLING_WIDGETS } from "./creator/sampling.js";
import { rememberQueuedSeeds } from "./creator/seedmemory.js";
import { primeSettings } from "./creator/api.js";
import { close as closeFullscreen, fullscreenNode, openFullscreen, remount as remountFullscreen,
         stepToShot, toggleFullscreen } from "./creator/fullscreen.js";
import { openPresetLibrary } from "./creator/presetlib.js";
import { el } from "./creator/dom.js";
import * as S from "./creator/state.js";
import { t } from "./creator/i18n.js";

const CREATOR = "MiniMaxH3Creator";
// The retired Timeline id. One shot and twenty are the same node now, and this
// is only what saved workflows still name — it mounts the same body, reads the
// same piece-shaped blob and behaves identically. See `creator_node.py`.
const TIMELINE = "MiniMaxH3Timeline";
const PRESTAGE = "MiniMaxH3PreStage";
// Both ids drive one body, so the pair of them is worth naming once rather than
// spelling out at every branch below.
const PIECE = [CREATOR, TIMELINE];
// Unchanged by the stage: the picture floats in a satellite card beside the
// node, so a node with a render is the same size as one without.
const MIN_SIZE = { [CREATOR]: [620, 520], [TIMELINE]: [620, 520], [PRESTAGE]: [460, 420] };
const WIDGET = { [CREATOR]: "creator_data", [TIMELINE]: "timeline_data", [PRESTAGE]: "prestage_data" };
// Which edge of the node the satellite result card hangs off. The PreStage sits
// to the *left* of its Creator, so its result goes further left — the desk
// reads *still ← pre-stage · creator → video* and nothing ever overlaps.
const SIDE = { [PRESTAGE]: "left" };

// ---- the pre-stage pairing --------------------------------------------------
//
// The PreStage is spawned by a pill on the Creator/Timeline and sits at its
// left edge. The pairing is *derived by scan*, never trusted from a stored id:
// the blob's `peer` field is the primary key, but ids renumber on paste, so a
// PreStage whose peer no longer exists is adopted by the nearest node it was
// visibly beside. The pill's on/off state falls out of the same scan, which is
// why deleting a PreStage by hand needs no bookkeeping at all.

/** Gap between the spawned PreStage's right edge and its peer, in graph units. */
const SPAWN_GAP = 28;

// Where a closed PreStage's blob waits: a property on the mother node, because
// node.properties ride the workflow JSON for free while the creator/timeline
// blobs are strict whitelists compile.py reads at queue time — a UI-only stash
// does not belong in what gets sent to the server. Toggling the pill back on
// seeds the new node from here, so closing the pre-stage discards nothing.
const STASH = "mmc_prestage_stash";

// Whether this node's face is pinned to the piece rather than to its one shot.
// A property for the same reason the stash is one: it rides the workflow JSON
// for free, and it is a preference about *this node on this canvas* rather than
// anything the render reads — the blob is a strict whitelist compile.py parses
// at queue time, and a view preference has no business in what gets queued.
//
// Only meaningful while the piece has one shot. Past that the strip is the only
// face that can show the piece, so nothing reads this.
const FACE_PIN = "mmc_face_piece";

/** What the body's piece-view toggle writes through. */
const faceControls = (node) => ({
  pinned: () => node.properties?.[FACE_PIN] === true,
  pin: (on) => {
    node.properties = node.properties || {};
    if (on) node.properties[FACE_PIN] = true;
    // Deleted rather than set false, so a node that never left its shot saves
    // exactly the JSON it always did.
    else delete node.properties[FACE_PIN];
    node.graph?.setDirtyCanvas(true, true);
  },
});

const nodeById = (graph, id) =>
  (graph?._nodes ?? []).find((n) => String(n.id) === String(id)) ?? null;

function findPreStage(node) {
  return (node.graph?._nodes ?? []).find((n) =>
    n.comfyClass === PRESTAGE && n.mmcBody
    && String(n.mmcBody.state?.peer) === String(node.id)) ?? null;
}

/** A PreStage whose peer id resolves to nothing — pasted, or its peer deleted —
 *  sitting roughly where a spawned one would: claim it rather than let the pill
 *  spawn a duplicate next to it. */
function adoptOrphan(node) {
  const orphan = (node.graph?._nodes ?? []).find((n) =>
    n.comfyClass === PRESTAGE && n.mmcBody
    && n.mmcBody.state?.peer != null
    && !nodeById(node.graph, n.mmcBody.state.peer)
    && n.pos[0] < node.pos[0]
    && Math.abs(n.pos[1] - node.pos[1]) < 600) ?? null;
  if (orphan) {
    orphan.mmcBody.state.peer = node.id;
    orphan.mmcBody.commit();
  }
  return orphan;
}

/** Mirror the PreStage into its mother's stash — the settings' second home, so
 *  removing the node never destroys the only copy.
 *
 *  Still two halves, though the second is now nearly vestigial: the sampler row
 *  moved into the blob (see `sampling.py`) and the blob carries it, so what the
 *  widget half restores is the fallback and the seed. Kept because the seed is
 *  genuinely still a widget, and because a stash written by an older build has
 *  the row only on that side. */
function stashPreStage(mother, pre) {
  const state = pre?.mmcBody?.state;
  if (!mother || !state) return;
  const sampling = {};
  for (const widget of pre.widgets ?? []) {
    if (widget.name === WIDGET[PRESTAGE]) continue;
    if (["string", "number", "boolean"].includes(typeof widget.value)) sampling[widget.name] = widget.value;
  }
  mother.properties = mother.properties || {};
  mother.properties[STASH] = JSON.stringify({ blob: S.serializePreStage(state), sampling });
}

function togglePreStage(node) {
  const existing = findPreStage(node) ?? adoptOrphan(node);
  if (existing) {
    // Not a discard: the settings move into the mother's stash, and the next
    // toggle puts them back exactly. Configure once, close freely.
    stashPreStage(node, existing);
    node.graph.remove(existing);
    node.graph.setDirtyCanvas(true, true);
    return;
  }
  const spawned = globalThis.LiteGraph?.createNode?.(PRESTAGE);
  if (!spawned) {
    // The class is not registered — the backend half of the package did not
    // load. Nothing to place; the console already carries the import error.
    return;
  }
  node.graph.add(spawned);
  spawned.pos = [node.pos[0] - spawned.size[0] - SPAWN_GAP, node.pos[1]];
  // The body is built by `nodeCreated`, which the frontend runs while the node
  // is constructed — but a frame late on some builds, so the claim waits for it.
  const claim = () => {
    const body = spawned.mmcBody;
    if (!body) { requestAnimationFrame(claim); return; }
    // Waited for the body on purpose: `attach` has enforced MIN_SIZE by now,
    // so matching the mother's height here cannot be clamped back down.
    spawned.size = [spawned.size[0], Math.max(spawned.size[1], node.size[1])];
    const stashed = node.properties?.[STASH];
    if (stashed) {
      try {
        const { blob, sampling } = JSON.parse(stashed);
        body.setState(S.parsePreStage(blob));
        for (const [name, value] of Object.entries(sampling ?? {})) {
          const widget = spawned.widgets?.find((w) => w.name === name);
          if (!widget) continue;
          widget.value = value;
          widget.callback?.(value);
        }
      } catch {
        // An unreadable stash costs nothing but the restore — the node opens
        // fresh, same as before there was a stash.
      }
    }
    body.state.peer = node.id;
    // commit serializes `body.state` back into the blob widget, so the restored
    // settings (peer id included) land there in one move.
    body.commit();
  };
  claim();
  node.graph.setDirtyCanvas(true, true);
}

/** What the two host editors hand their pre-stage pill. */
const preStageControls = (node) => ({
  active: () => !!findPreStage(node),
  toggle: () => {
    togglePreStage(node);
    // The pill spawns or removes a whole node, and fullscreen hosts the pair in
    // two columns — so the editor has to be told the second one arrived. A frame
    // later: the new node is not in the graph yet, and the scan that finds it
    // reads the graph.
    requestAnimationFrame(() => remountFullscreen(node));
  },
});

/** What the PreStage's result chips resolve at click time: the peer body and
 *  its attach entry point. Late, by scan — the peer can be deleted, renumbered
 *  or replaced between render and click. */
const peerOf = (node) => () => {
  const id = node.mmcBody?.state?.peer;
  const peer = id == null ? null : nodeById(node.graph, id);
  const body = peer?.mmcBody;
  if (!body?.attachFromPreStage) return null;
  return {
    label: peer.title || peer.comfyClass,
    attach: (role, filename) => {
      body.attachFromPreStage({ role, filename });
      // The hand-off is the reason the pair exists, so it is also where the
      // simple view's card should go: the still is made, and what it was made
      // for now has it. Ignored by the desk, which shows both at once.
      stepToShot();
    },
  };
};

// Both nodes own their sampler, but that is no reason for half of it to be
// stock widgets and half of it to be the node's own controls. These are hidden
// and re-drawn as pills by `sampling.js`; they stay in node.widgets because that
// is where graphToPrompt reads the values from. The list lives beside the row
// that draws them, so the two cannot fall out of step — a widget drawn but not
// hidden would appear twice.

/**
 * Collapse the raw JSON widget. It stays in node.widgets — that is what
 * graphToPrompt reads the value from — it just stops taking up space.
 *
 * Setting `type = "hidden"` is the obvious move and is wrong: it breaks
 * rendering under Nodes 2.0. A multiline string widget is a DOM textarea, so
 * hiding it means hiding its element too; computeSize alone leaves the textarea
 * floating in the node body.
 */
function hideWidget(widget) {
  if (!widget) return;
  widget.hidden = true;
  widget.options = widget.options || {};
  widget.options.hidden = true;
  widget.computeSize = () => [0, 0];
  if (widget.element) {
    // A DOM widget: hide its element too, or the textarea floats in the body.
    widget.element.style.display = "none";
  } else if (widget.type !== "hidden") {
    // A canvas-drawn widget (the sampler numbers and combos). `hidden` alone is
    // honoured by current frontends; the type swap is what older ones read, and
    // it is the one thing that must not be done to a DOM widget — hiding the
    // type there stops the element being managed and leaves it on screen.
    widget.origType = widget.type;
    widget.type = "hidden";
  }
}

/**
 * Hide the stock sampler widgets and hand them back by name, for `samplingBar`
 * to re-draw. Shared by both nodes because both declare the same ones.
 */
function collectSampling(node) {
  const widgets = {};
  for (const name of SAMPLING_WIDGETS) {
    const found = node.widgets?.find((w) => w.name === name);
    if (!found) continue;
    widgets[name] = found;
    hideWidget(found);
    // `control_after_generate` is attached to the seed rather than declared, so
    // it can also arrive as a linked widget with a name the frontend chose.
    // Hide whatever hangs off the ones we know.
    for (const linked of found.linkedWidgets || []) {
      widgets.control_after_generate = widgets.control_after_generate || linked;
      hideWidget(linked);
    }
  }
  // Fixed, not the frontend's "randomize". A render here is minutes and often a
  // pass in a piece being tuned a line at a time, so a seed that moves on its
  // own throws away the one variable you were holding still — and it moves
  // invisibly, because the widget is hidden and the pill is the only thing
  // saying so. Set at creation only: a saved workflow assigns its widget values
  // after `nodeCreated`, so a node that chose otherwise keeps its choice.
  if (widgets.control_after_generate) widgets.control_after_generate.value = "fixed";
  // The seed a fresh node starts on. Random, and deliberately not a number
  // picked for being a good one: the only study of "golden" seeds finds them by
  // ranking a thousand of them on one model's own output, and reports different
  // winners for SD 2.0 and SDXL Turbo — so a number lifted from an image model
  // says nothing about H3, and there is no published search for H3 to lift from.
  // Every seed is one noise sample and none of them is known to be better.
  //
  // What was actually wrong with 0 is that it is the same 0 for everybody. It
  // is the schema's default, this node holds it (`control_after_generate` is
  // pinned to "fixed" just above), and so every first render anyone makes with
  // a fresh node is the same noise. A seed per node is the honest answer to
  // that, and it is the same 32-bit draw the seed row's own dice button makes.
  //
  // Set at creation only, like the line above it: a saved or pasted workflow
  // assigns its widget values after `nodeCreated`, so a node that already has a
  // seed keeps it.
  if (widgets.seed) widgets.seed.value = Math.floor(Math.random() * 0xffffffff);
  requestAnimationFrame(() => Object.values(widgets).forEach(hideWidget));
  return widgets;
}

/** Shared setup: hide the blob, mount a DOM body, give the node room. */
function attach(node, build) {
  installStyles();
  const widget = node.widgets?.find((w) => w.name === WIDGET[node.comfyClass]);
  if (!widget) return null;

  hideWidget(widget);
  // The textarea element is created lazily, so it may not exist yet on the
  // first pass — hide it again once the frontend has built it.
  requestAnimationFrame(() => hideWidget(widget));

  const body = build(widget);
  // The DOM widget writes left/top/width/height straight onto the element it is
  // handed, every frame. The body has to be able to leave the node — the
  // fullscreen editor hosts this very element (fullscreen.js) — so what the
  // widget gets is a wrapper it can go on positioning while the body is away.
  // Empty, the wrapper is a blank box on a node nobody is looking at, which is
  // cheaper than the alternative: collapsing the node would serialize into the
  // saved workflow, and a workflow that comes back collapsed is a bug.
  // data-capture-wheel is the frontend's own contract for DOM widgets that
  // scroll: without it, useCanvasInteractions forwards every wheel over the
  // body to the canvas as zoom — keepScroll never even sees the event. With
  // it, the wheel is ours whenever the focus is somewhere in the body (the
  // same deal the stock textarea widget gets), which is what lets the well
  // scroll a rewrite that outgrew the face.
  const host = el("div", { class: "mmc-widget-host", "data-capture-wheel": "true" }, [body.root]);
  node.mmcHost = host;
  // The sampler row reads UI preferences (the shift pills' visibility) from the
  // settings cache, which is empty until the server first answers. Prime it —
  // fetched once, ever — and repaint this body when the answer lands, so a node
  // drawn before the reply shows the row the settings actually ask for.
  primeSettings(() => body.render?.());
  node.addDOMWidget("mmc_ui", "MMC_CREATOR", host, {
    serialize: false,
    hideOnZoom: false,
    getMinHeight: () => 200,
  });
  const [minWidth, minHeight] = MIN_SIZE[node.comfyClass];
  node.size = [Math.max(node.size?.[0] ?? 0, minWidth), Math.max(node.size?.[1] ?? 0, minHeight)];

  // The picture lives beside the node, not in it: the body builds the stage
  // (it owns the gallery), and the satellite floats it at the node's right
  // edge, absent until a render gives it something to be.
  const satellite = body.stage
    ? new Satellite({ node, stage: body.stage, side: SIDE[node.comfyClass] ?? "right" })
    : null;
  // On the body rather than local: the fullscreen editor has to dock it, and
  // the body is what it is given.
  body.satellite = satellite;

  // The body listens on `api` for its own previews, and those listeners outlive
  // the DOM: without this, deleting a node leaves it decoding frames for a
  // stage nobody can see. The satellite's element is on document.body, so it
  // too outlives the node unless told.
  const removed = node.onRemoved;
  node.onRemoved = function () {
    removed?.apply(this, arguments);
    // Deleting the piece the editor is showing closes it: there is no node left
    // to put the body back into, and a shell around a destroyed body is a blank
    // screen with no way out but the keybinding.
    if (fullscreenNode() === node) closeFullscreen();
    body.destroy?.();
    satellite?.destroy();
  };
  return body;
}

/** Whether new and selected pieces open in the fullscreen editor.
 *
 *  ComfyUI's own store, not `/continuity/settings`: that file is one copy
 *  for the whole install with, as `api.js` puts it, "no request behind it and
 *  so no ComfyUI user". Which editor you look at is a preference about a
 *  person, and this is the store that is per-person and already the place
 *  people go to change how ComfyUI behaves.
 *
 *  English rather than t(): setting definitions are read once, at registration,
 *  while the frontend is still booting and the locale store has not answered.
 *  A string translated there would be whatever the boot order gave it, forever.
 */
const FULLSCREEN_SETTING = "Continuity.Editor.Fullscreen";

const wantsFullscreen = () => {
  try {
    return app.extensionManager?.setting?.get?.(FULLSCREEN_SETTING) === true;
  } catch {
    return false;
  }
};

app.registerExtension({
  name: "continuity",

  settings: [{
    id: FULLSCREEN_SETTING,
    category: ["Continuity", "Editor", "Fullscreen"],
    name: "Open the node fullscreen",
    tooltip: "Draw the node's body over the whole window instead of on the canvas. "
           + "The node stays in the graph and is queued exactly as it always was. "
           + "Ctrl+Shift+M toggles it; Escape and the button in its corner go back.",
    type: "boolean",
    defaultValue: false,
  }],

  // The way in and, more importantly, the way back: once the shell is up there
  // is no node to right-click, so the editor cannot be the only thing that
  // knows how to close itself.
  commands: [{
    id: "continuity.toggleFullscreen",
    label: "Continuity: fullscreen editor",
    function: toggleFullscreen,
  }],
  keybindings: [{
    commandId: "continuity.toggleFullscreen",
    combo: { key: "m", ctrl: true, shift: true },
  }],

  setup() {
    // One hook for the whole canvas, installed once — every node's seed row
    // reads out of the same memory.
    rememberQueuedSeeds();
  },

  async nodeCreated(node) {
    if (PIECE.includes(node.comfyClass)) {
      node.mmcBody = attach(node, (widget) => new TimelineBody({
        read: () => widget.value,
        write: (raw) => {
          widget.value = raw;
          node.graph?.setDirtyCanvas(true, true);
        },
        widgets: collectSampling(node),
        onWidgetChange: () => node.graph?.setDirtyCanvas(true, true),
        // Read late rather than captured: a node pasted from the clipboard is
        // renumbered after it is built, and the stage matches previews by id.
        nodeId: () => node.id,
        preStage: preStageControls(node),
        face: faceControls(node),
        // Deferred a frame for the same reason the setting's path is: this runs
        // before the node is in the graph, and the editor scans the graph for
        // the piece and its PreStage.
        fullscreen: () => requestAnimationFrame(() => openFullscreen(node)),
      }));
      // Deferred a frame: `nodeCreated` runs before the node is in the graph
      // and before a pasted one is renumbered, and the editor scans the graph
      // for the piece and its PreStage.
      if (wantsFullscreen()) requestAnimationFrame(() => openFullscreen(node));
    } else if (node.comfyClass === PRESTAGE) {
      node.mmcBody = attach(node, (widget) => {
        const state = S.parsePreStage(widget.value);
        let body;
        body = new PreStageBody({
          state,
          onCommit: () => {
            widget.value = S.serializePreStage(body.state);
            node.graph?.setDirtyCanvas(true, true);
          },
          samplingWidgets: collectSampling(node),
          onWidgetChange: () => node.graph?.setDirtyCanvas(true, true),
          nodeId: () => node.id,
          peer: peerOf(node),
        });
        return body;
      });
      // Deleting the node by hand is closing it too: mirror the blob into the
      // mother's stash on the way out, same as the pill. Guarded — during a
      // whole-graph teardown the peer may already be gone, and then there is
      // nothing to stash onto (the saved workflow keeps its own copy anyway).
      const removed = node.onRemoved;
      node.onRemoved = function () {
        stashPreStage(nodeById(node.graph, node.mmcBody?.state?.peer), node);
        removed?.apply(this, arguments);
      };
    }
  },

  // Loading a saved workflow assigns widget values after nodeCreated, so the
  // body has to re-read its blob once the graph has finished configuring.
  loadedGraphNode(node) {
    const body = node.mmcBody;
    if (!body) return;
    if (node.comfyClass === PRESTAGE) {
      const widget = node.widgets?.find((w) => w.name === WIDGET[PRESTAGE]);
      // The sampler row moved off the widgets into the blob; this is where a
      // pre-stage saved before that crosses over. Here rather than in
      // `nodeCreated` because widget values are assigned after it, which is the
      // same reason this hook exists at all. See `sampling.adopted`.
      const carried = adopted(widget.value, collectSampling(node),
                              S.parsePreStage, S.serializePreStage);
      if (carried) widget.value = carried;
      const state = S.parsePreStage(widget.value);
      body.onCommit = () => {
        widget.value = S.serializePreStage(state);
        node.graph?.setDirtyCanvas(true, true);
      };
      body.setState(state);
    } else {
      body.reload();
    }
  },

  beforeRegisterNodeDef(nodeType, nodeData) {
    const name = WIDGET[nodeData.name];
    if (!name) return;
    const original = nodeType.prototype.getExtraMenuOptions;
    nodeType.prototype.getExtraMenuOptions = function (canvas, options) {
      original?.apply(this, arguments);
      // The second way into the shell, and the idiomatic one: a node action
      // belongs on the node's own menu. The face carries the first — a rail tile
      // on a shot, a pill on a strip — and Ctrl+Shift+M has always been the
      // third. Only the pieces: the shell opens on a Creator or a Timeline, and
      // a PreStage is drawn beside one rather than instead of it.
      if (PIECE.includes(nodeData.name)) {
        options.push({
          content: t("Fullscreen editor"),
          callback: () => openFullscreen(this),
        });
      }
      // The path for a node the user has right-clicked rather than opened. The
      // target is read late, off the mounted body — a node whose body has not
      // been built yet opens the library read-only rather than not at all.
      options.push({
        content: t("Presets…"),
        callback: () => openPresetLibrary({ target: this.mmcBody?.presetTarget?.() ?? null }),
      });
      options.push({
        content: t("Copy {name} JSON", { name }),
        callback: () => {
          const widget = this.widgets?.find((w) => w.name === name);
          if (widget) navigator.clipboard?.writeText(widget.value);
        },
      });
      return options;
    };
  },
});

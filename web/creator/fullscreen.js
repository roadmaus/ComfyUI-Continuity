// The node body, given the whole window.
//
// ComfyUI is where this pack lives, not what it is shaped like. Everything the
// Creator does — the blob, the queue, the previews, the gallery, the picker —
// already works without a canvas under it, and the single thing tying the body
// to a node is where its element hangs. So this borrows the element rather than
// rebuilding anything: `attach()` mounts the body inside a wrapper the DOM
// widget positions, and fullscreen lifts the body out of that wrapper into a
// fixed shell and puts it back on the way out.
//
// **The node never leaves the graph.** It keeps its hidden blob widget, it is
// still what `graphToPrompt` serializes, and it is still what the server runs.
// Nothing here is a second source of truth and closing the editor loses nothing
// — which is the whole reason this is a hundred lines and not a second frontend.
//
// Two things the canvas gave the body for free have to be supplied here:
//
// * **the picture.** On canvas the Stage floats in a Satellite, which derives
//   its screen position from the node's graph position every frame. There is no
//   node on screen to derive it from, so the satellite is *docked* (satellite.js)
//   — it hands the stage to a column and stops following.
// * **the queue.** ComfyUI's Run button is behind the shell, so the shell grows
//   its own, and a Cancel beside it. Render is `app.queuePrompt`, the same call
//   the toolbar makes; Cancel is `api.interrupt()`, the same call its cancel
//   makes. Neither reimplements anything.
//
//   What it does add is an aim. A pre-stage is an output node of the same graph
//   the shot is in, so a plain queue runs both — which is right on the canvas,
//   where the Run button is about the workflow, and wrong here, where the button
//   is at the foot of one column and reads as being about that column. So each
//   button names its node (`queueNodeIds`, ComfyUI's own partial execution) and
//   runs that one. Making the still and making the shot are two decisions, and
//   they were being taken with one press.
//
// What is deliberately *not* here: a Gallery button and a Settings button. Both
// already sit in the body's own rail, at the far edge where `.mmc-rail-group`
// puts them, and a second copy in the title bar would be two doors to one room.
//
// **Two views over the one shell.** `full` is the desk: the pre-stage, the shot
// and the picture side by side, which is what a piece being built out of parts
// actually looks like. `simple` is the other half of the day — one column in the
// middle of the screen, the frame above it and the writing below, for when the
// piece is one prompt and everything else is in the way. They are a class on the
// shell and nothing more: the same bodies, the same state, the same queue, so
// switching mid-sentence keeps the sentence.
//
// **And in the simple view a pre-stage is a step, not a second panel.** There is
// no room beside one column for another one, and there should not be: the pair
// is a sequence — make the still, then make the video out of it — so the card in
// the middle shows whichever of the two you are on and a switch at its top says
// which — and the Render under it runs the step you are on. Both nodes stay in
// the graph either way; the step is what you are writing *and* what you press.
// The desk, having both columns on screen, gives each its own button.

import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import { watch as watchQueue } from "./queue.js";
import { viewUrl } from "./api.js";
import { el, icon, mark, spinner } from "./dom.js";
import { buildDashboard } from "./navigate.js";
import { openControl } from "./control.js";
import { openUpscale } from "./upscale.js";
import { openPresetLibrary } from "./presetlib.js";
import { elapsed } from "./stage.js";
import { t } from "./i18n.js";
import { noteFullscreen } from "./styles.js";
import * as S from "./state.js";

/** Node classes whose body this editor can host. Kept here rather than imported
 *  from the entry point, because the entry point imports this. */
const PIECE = ["MiniMaxH3Creator", "MiniMaxH3Timeline"];
const PRESTAGE = "MiniMaxH3PreStage";

/**
 * A tool card's plate.
 *
 * The two Go-to cards show the piece, because the piece is what they take you
 * to. A bench does not: it is a room of its own with its own subject, and the
 * first cut of this surface — every card cut from whatever frame the piece was
 * carrying — put the same photograph on the grid five times over.
 *
 * So each tool has a picture of its own, shipped beside the code. They are one
 * set on purpose: a black stage, one warm key, deep falloff, no text and no
 * faces. And each was chosen for what its card *does* to it — the mannequin and
 * its rigging because a depth pass over it is a figure you can read at a glance,
 * the knurled lens barrel because the detail on it visibly dies at forty-four
 * pixels wide. The ControlNet card ships two: the frame, and the depth map the
 * bench itself made of it.
 *
 * Off `import.meta.url`, so the installed folder's name stays the browser's
 * business — the same trick `presets/atlasref.js` uses for the atlas.
 */
const cardArt = (name) => new URL(`./cards/${name}.webp`, import.meta.url).href;

/** The open editor, or null. One at a time: it is the window. */
let open = null;

/** Which view the shell opens in. localStorage rather than ComfyUI's setting
 *  store: this is a switch you flip while working, several times an hour, and a
 *  preference that has to be found in a settings dialog to be changed is not
 *  that. It survives a reload, which is all it has to do. */
const VIEW_KEY = "mmc.fullscreen.view";
const VIEWS = ["full", "simple"];

/** How big the live picture is drawn, as a fraction of the room the plate has.
 *  Stored beside the view and for the same reason: it is a thing you reach for
 *  while working — small to see the take beside the writing, full to judge a
 *  face — not a preference to go and find in a dialog. */
const PLATE_KEY = "mmc.fullscreen.plate";
const PLATE_MIN = 0.4;
const PLATE_MAX = 1;
/** Sizes the grip catches on the way past, and how near it has to be. Not a
 *  ratchet: the drag is continuous and these only give the three readings
 *  anybody actually names a little gravity. */
const PLATE_DETENTS = [0.5, 0.75, 1];
const PLATE_CATCH = 0.03;

const clampPlate = (value) => Math.min(PLATE_MAX, Math.max(PLATE_MIN, value));

function storedPlate() {
  try {
    const seen = Number(localStorage.getItem(PLATE_KEY));
    return Number.isFinite(seen) && seen > 0 ? clampPlate(seen) : PLATE_MAX;
  } catch {
    return PLATE_MAX;
  }
}

/** How the take crosses between the lip and the plate. Long enough to be read
 *  as one object moving rather than two objects swapping, short enough that a
 *  second press does not have to be waited for. The fade is the answer for the
 *  cases with no rectangle to fly between. */
const REVIEW_FLIGHT = { duration: 280, easing: "cubic-bezier(.2,.75,.25,1)" };
const REVIEW_FADE = { duration: 160, easing: "ease-out" };


/** Asked at the moment of the animation rather than cached: this is a system
 *  setting and it can change under a window that is already open. */
const reduced = () =>
  globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

/** The transform that puts a box laid out at `to` over the rectangle `from`.
 *  Both boxes hold the same picture at the same aspect, so the two scales agree
 *  to within a border and nothing is stretched on the way. */
const flipFrom = (from, to) =>
  `translate(${(from.left + from.width / 2) - (to.left + to.width / 2)}px, `
  + `${(from.top + from.height / 2) - (to.top + to.height / 2)}px) `
  + `scale(${from.width / to.width}, ${from.height / to.height})`;

/** The pair, in the order the hand-off runs: the pre-stage makes the still the
 *  shot is built on. Labels are the pack's own words for the two nodes. */
const STEPS = [["pre", "Pre-stage"], ["shot", "Shot"]];

function storedView() {
  try {
    const seen = localStorage.getItem(VIEW_KEY);
    return VIEWS.includes(seen) ? seen : "full";
  } catch {
    return "full";
  }
}

export function isFullscreen() {
  return open !== null;
}

/** The node the editor is currently showing, or null. */
export function fullscreenNode() {
  return open?.node ?? null;
}

const creators = () =>
  (app.graph?._nodes ?? []).filter((n) => PIECE.includes(n.comfyClass) && n.mmcBody);

/** The PreStage paired with `node`, by the same scan the spawn pill uses — the
 *  blob's `peer` field, never a stored id, because ids renumber on paste. */
const preStageOf = (node) =>
  (node.graph?._nodes ?? []).find((n) =>
    n.comfyClass === PRESTAGE && n.mmcBody
    && String(n.mmcBody.state?.peer) === String(node.id)) ?? null;

/**
 * Which piece the editor opens on: the selected one, else the only one, else
 * nothing. Deliberately does not create a node — a keybinding that silently
 * edits the graph is a keybinding people learn to be afraid of. The command
 * that calls this handles the empty graph itself.
 */
export function subject() {
  const all = creators();
  const selected = all.find((n) => n.is_selected || app.canvas?.selected_nodes?.[n.id]);
  return selected ?? (all.length ? all[0] : null);
}

class Fullscreen {
  constructor(node) {
    this.node = node;
    // The PreStage whose body this editor is currently holding, or null. See
    // `mount`, which is re-runnable and has to know what it is replacing.
    this.hosted = null;
    // What each half of the pair is doing, because each half is now pressed
    // on its own: the desk runs the shot and the still from two buttons, and
    // the simple view runs whichever step it is standing on. One shared flag
    // said "something is going" and lit both.
    this.runs = {
      shot: { queued: false, state: "idle", progress: null },
      pre: { queued: false, state: "idle", progress: null },
    };
    this.view = storedView();
    // Which of the pair the simple view's card is showing. Not remembered: it
    // is where you are in a piece, not a preference, and a session that opened
    // on the pre-stage of a piece you had finished would be answering a
    // question nobody asked.
    this.step = "shot";
    // Whether the simple view is showing the sampler row. Off by default and
    // not remembered: it is a look under the hood, and a hood that stayed open
    // between sessions would make the simple view the desk with extra steps.
    this.advanced = false;

    this.piece = el("span", { class: "mmc-fs-piece" });
    this.run = el("button", {
      class: "mmc-fs-run", onclick: () => this.render_(this.step),
    });
    // The desk's second press. On the foot of the pre-stage's own column, under
    // the thing it makes, because a still and a shot are two renders and a
    // single button that quietly did both was the reason you could not make one
    // without waiting for the other. Quiet, not amber: the accent is the piece's
    // and this is the step before it. The simple view has no second column and
    // no need for it — there the one button follows the step switch.
    this.preRun = el("button", {
      class: "mmc-fs-run ghost", onclick: () => this.render_("pre"),
    });
    this.preRunRow = el("div", { class: "mmc-fs-runrow mmc-fs-prerun" }, [this.preRun]);
    this.cancel = el("button", {
      class: "mmc-fs-cancel", text: t("Cancel"), onclick: () => this.interrupt(),
    });
    this.note = el("span", { class: "mmc-fs-note" });
    // Only the simple view folds the sampler away, so only the simple view
    // offers the fold. It sits with Render because that is what it is about:
    // the numbers this press is going to use.
    this.more = el("button", {
      class: "mmc-fs-more",
      title: t("Show the seed, the steps and the sampler for this render"),
      onclick: () => { this.advanced = !this.advanced; this.paint(); },
    }, [icon("sliders", 15), el("span", { text: t("Sampling settings") })]);
    this.runRow = el("div", { class: "mmc-fs-runrow" }, [
      this.run, this.cancel, this.more, this.note,
    ]);

    // Which half of the pair the card is showing, and — in the simple view — the
    // only control over the pair at all. On the card rather than in the title
    // bar, because the bar is about the window (which view, the way back) and
    // this is about the work.
    //
    // It is always here, whether or not a pre-stage exists: pressing Pre-stage
    // when there is none spawns one and takes you to it. The shot's own row used
    // to carry an amber pill that did the spawning, and two controls over one
    // node is one too many — the switch says where you are *and* gets you there,
    // which is what a step is.
    //
    // Two segments and nothing else. The pre step used to carry an × that took
    // the node back out of the graph, and a switch is the wrong place for it: in
    // this view you are on one step or the other, and the only thing either
    // segment should do is take you there. Removing the pre-stage is the desk's
    // — the toggle in the shot's own row, which the desk still draws.
    // The lit segment, as one object that travels rather than as a background
    // that appears on whichever button was pressed. It is the only thing on
    // screen that is continuous across the switch — the card's contents are
    // replaced outright — so it is what the eye follows, and the direction it
    // travels is the direction the new card arrives from. See `paintInk`.
    this.stepInk = el("span", { class: "mmc-fs-step-ink" });
    this.stepBar = el("div", { class: "mmc-fs-stepbar" }, [this.stepInk,
      ...STEPS.map(([step, label]) =>
        el("button", {
          class: "mmc-fs-step", "data-step": step,
          title: step === "pre"
            ? t("The still this shot is built on — its prompt, its references, its checkpoint.")
            : t("The video: the prompt, the cast and everything the render reads."),
          onclick: () => this.setStep(step),
        }, [el("span", { text: t(label) })]))]);

    // What each column is, said once at the top of it. The desk shows two
    // node faces that are built from the same parts — the same rail, the same
    // prompt well, the same pills — so without a name on each, the first thing
    // the eye meets on the left is a second copy of the toolbar it is already
    // reading on the right. The simple view has the step switch instead and
    // hides these.
    this.preHead = el("div", { class: "mmc-fs-head" }, [el("span", { text: t("Pre-stage") })]);
    this.colHeadName = el("span");
    this.colHead = el("div", { class: "mmc-fs-head" }, [this.colHeadName]);

    this.preStill = el("div", { class: "mmc-fs-still" });
    this.pre = el("div", { class: "mmc-fs-pre" });
    this.face = el("div", { class: "mmc-fs-face" });
    this.col = el("div", { class: "mmc-fs-col" });
    // The dock is never empty, because an empty dock is a third of the window
    // with nothing in it and a hairline border ending in mid-air. Until there
    // is a picture it holds the frame the piece is about to make, drawn at its
    // own ratio — so the render lands in the box that was already there rather
    // than into a void, and nothing on screen moves when it does.
    this.frame = el("div", { class: "mmc-fs-frame" });
    this.dock = el("div", { class: "mmc-fs-dock" }, [this.frame]);
    // Everything this editor has finished, oldest at the top, with the live
    // stage at the bottom of the column — so the newest picture is always the
    // one nearest the writing and the older ones are up the scroll. See
    // `keepTake`: the stage is cleared by the next queue, and without somewhere
    // to put what it was holding, every render erased the one before it.
    // One per step. A still and a clip are two different things to have made,
    // and one column alternating between them would be a history you cannot
    // read — so each step keeps its own and the reel shows the one you are on.
    this.past = { shot: el("div", { class: "mmc-fs-strip-run" }),
                  pre: el("div", { class: "mmc-fs-strip-run" }) };
    // The result each step's stage is showing, and the only one not in `past`.
    this.shown = { shot: null, pre: null };
    // The take the plate has been borrowed for, or null. See `review`: an older
    // render is shown in a layer *over* the stage rather than written into it,
    // so the run underneath goes on running and there is nothing to put back.
    this.reviewing = null;
    // The picture region, in two parts that do not share an axis.
    //
    // They used to: one scrolling column held the history *and* the live stage,
    // so where the live picture sat was a function of how many renders there had
    // been — centred while the column was empty, shoved to the floor by the
    // first take, and further down with every one after it. The thing you are
    // waiting for was the thing that would not hold still.
    //
    // So the reel takes the whole height and centres what is in it, always, and
    // history runs left to right along a shelf beneath *the window* — under the
    // card as much as under the picture. Spanning both is what keeps them level:
    // a lip inside the picture's own column would have taken its height out of
    // the picture and not out of the writing, and the two would have sat half a
    // lip apart for as long as there was any history at all.
    //
    // The shelf is reserved for the whole of `working` — empty for exactly one
    // render — because a shelf that arrived with the second take would move
    // everything above it, which is the thing all of this is here to stop.
    // How big the picture is drawn, and the corner you drag to say so. The
    // handle lives at the *top* right: the bottom edge of a render is spoken
    // for three times over — the progress rule, the readout, and a finished
    // clip's own transport — and a control that has to be reached around the
    // scrub bar is a control nobody uses twice.
    //
    // The plate stays centred while it resizes, so the picture grows and
    // shrinks about its own middle and nothing else in the window moves. That
    // is the same promise the plate makes about history, kept under a second
    // kind of change.
    this.plateScale = storedPlate();
    this.sizeRead = el("span", { class: "mmc-stage-chip mmc-fs-size" });
    this.grip = el("button", {
      class: "mmc-fs-grip",
      title: t("Drag to resize the picture. Double-click for full size."),
      "aria-label": t("Picture size"),
      role: "slider", "aria-valuemin": "40", "aria-valuemax": "100",
      onpointerdown: (event) => this.gripDown(event),
      ondblclick: () => this.setPlate(PLATE_MAX),
      onkeydown: (event) => this.gripKey(event),
    }, [icon("grip", 15)]);
    this.sizer = el("div", { class: "mmc-fs-sizer" }, [this.sizeRead, this.grip]);
    // The room around the picture is the way out of a review — see `review`.
    // On the reel rather than on the dock so the margin the plate is centred in
    // counts as empty space too, which is what it looks like.
    this.reel = el("div", {
      class: "mmc-fs-reel",
      onclick: (event) => {
        if (event.target === this.reel || event.target === this.dock) this.endReview();
      },
    }, [this.dock]);
    this.strip = el("div", { class: "mmc-fs-strip" }, [this.past.shot]);
    // The two control cards are one object: the desk. They are wrapped rather
    // than laid out beside the reel as three equals so that stretching them to
    // each other stretches them to *each other* — a flex line takes the height
    // of its container, and the body is the window. The wrapper is only as tall
    // as the taller card, so that is the height they both get. In the simple
    // view it is display:contents and this row does not exist at all.
    this.desk = el("div", { class: "mmc-fs-desk" }, [this.pre, this.col]);
    this.body = el("div", { class: "mmc-fs-body" }, [this.desk, this.reel]);
    // Everything under the bar, as one box, so the dashboard has something to
    // cover. It covers rather than replaces: the desk stays mounted and laid
    // out behind it, which is why the prompt you were half-way through is still
    // there when you come back, and why a render that finishes while the
    // dashboard is up still has a plate with a width to measure itself against.
    this.room = el("div", { class: "mmc-fs-room" }, [this.body, this.strip]);

    this.root = el("div", { class: "mmc-fs" }, [
      el("div", { class: "mmc-fs-bar" }, [
        // The pack's own mark rather than a rail glyph: the bar is the one place
        // in the window that says whose room this is, and `timeline` is a control
        // icon that means "the strip" everywhere else it is drawn.
        //
        // And it is the door. Pressing it turns the room over to the dashboard
        // — the editor's tools, as cards — and pressing it again turns it back;
        // the caret is what says the name is pressable at all, and which way it
        // points is which side you are on. No keystroke raises it: there was a
        // ⌘K once, and every pack on the canvas wants that key.
        this.mark = el("button", {
          class: "mmc-fs-mark",
          title: t("Tools"),
          "aria-expanded": false,
          onclick: () => this.toggleDash(),
        }, [
          el("span", { class: "mmc-fs-logo" }, [mark(22)]),
          // The pack, and it is a product name rather than copy, so it is not
          // translated and does not change with what is on the card.
          el("span", { text: "Continuity" }),
          el("span", { class: "mmc-fs-caret" }, [icon("chevron", 12)]),
        ]),
        el("span", { class: "mmc-fs-slash", text: "/" }),
        // Which family this piece renders with. Filled on mount rather than
        // here, because the shell is built before it is holding a piece — read
        // off the default at build time it would say H3 over an LTX 2.5 piece.
        this.family = el("span", { class: "mmc-fs-family" }),
        // The node's own name, and only when there is one: LiteGraph titles a
        // fresh node after its display name, so an unrenamed one would put
        // "Continuity" on the bar twice and say nothing the mark did not.
        this.pieceGroup = el("span", { class: "mmc-fs-piece-group" }, [
          el("span", { class: "mmc-fs-slash", text: "/" }),
          this.piece,
        ]),
        el("span", { class: "mmc-fs-gap" }),
        this.views = el("div", { class: "mmc-fs-views" }, VIEWS.map((view) =>
          el("button", {
            class: "mmc-fs-view",
            "data-view": view,
            title: view === "simple"
              ? t("One column in the middle: the frame, the prompt, and Render.")
              : t("The desk: the pre-stage, the shot and the picture side by side."),
            onclick: () => this.setView(view),
          }, [el("span", { text: view === "simple" ? t("Simple") : t("Full") })]))),
        el("button", {
          class: "mmc-fs-exit", title: t("Back to the graph"),
          onclick: () => close(),
        }, [icon("expand", 15), el("span", { text: t("Back to the graph") })]),
      ]),
      this.room,
    ]);

    // Escape belongs to whatever is on top, and the shell is the bottom of that
    // stack — everything in this pack that takes Escape opens *over* it.
    //
    // Bubble phase, deliberately, and it is the whole mechanism: every popover
    // (`dismissable`) and every modal (`mountOverlay`) listens in capture and
    // stops propagation when the key is theirs, so a keystroke only reaches here
    // when none of them wanted it. Listening in capture too would have made this
    // a race that registration order decides — and the shell registers first,
    // so it would have won every time and closed the editor out from under an
    // open picker.
    // A review is the one thing this pack puts over the shell that the shell
    // itself owns, so it takes Escape here rather than through `dismissable`:
    // the layer is not a popover and has nothing to register. Same rule either
    // way — the topmost thing goes first, and the second press closes the
    // editor.
    this.onKey = (event) => {
      if (event.key !== "Escape") return;
      if (this.reviewing) { this.endReview(); return; }
      // The dashboard is the shell's own layer, like a review — not a popover
      // and not a modal, so it has nothing registered in capture and takes its
      // Escape here. Topmost first either way: the press that puts the room
      // back is not the press that leaves the editor.
      if (this.dash) { this.closeDash(); return; }
      close();
    };
    document.addEventListener("keydown", this.onKey);

    // How deep the queue is, from the one place that tracks it — the benches and
    // the refine pill read the same state, which is what lets a bench say it is
    // waiting for *this* render. See `web/creator/queue.js`.
    this.unwatchQueue = watchQueue(({ remaining }) => {
      this.remaining = remaining;
      // Optimism spent: the server has the job, so the flag stops standing in
      // for it and the real state takes over.
      if (remaining === 0) for (const run of Object.values(this.runs)) run.queued = false;
      this.paint();
    });

    // Whether anything actually reached the queue. ComfyUI's `queuePrompt`
    // catches a refused prompt itself — it shows the dialog and resolves — so
    // the promise the press returns never rejects, and the row's optimism is
    // never spent: "Sampling" stands over a render that was never queued, and
    // the only way out anybody finds is Cancel, pressed until something
    // happens. That is the three interrupts in the log of #27, under a button
    // that had nothing to interrupt.
    //
    // `promptQueued` is the one thing the frontend says out loud when a prompt
    // is accepted — dispatched once per press, and only when a batch went out
    // — and every frontend that has the editor's aim has it.
    this.accepted = 0;
    // How many presses are still waiting on the server. A press made while
    // another is in flight is pushed onto the queue the first one is draining
    // and answered immediately, before the batch it joined has gone out, so it
    // is the last one back that gets to say nothing was accepted.
    this.inflight = 0;
    this.onQueued = () => { this.accepted += 1; };
    api.addEventListener("promptQueued", this.onQueued);

    this.setPlate(this.plateScale, { store: false });
    this.mount();
    document.body.appendChild(this.root);
    // The shell is the only surface the dark pin applies to — see applyTheme()
    // in styles.js for why a node body is the wrong place for it.
    noteFullscreen(true);
    this.paint();
  }

  /**
   * Move the bodies in and take over their stages. Re-runnable: `remount()`
   * calls it again when the pre-stage pill spawns or removes the second column,
   * which is why what is hosted is tracked rather than assumed.
   */
  mount() {
    const paired = preStageOf(this.node);
    // A step you cannot be on. The pill that removes the pre-stage is in the
    // shot's own row, so this is reachable, and landing back on the shot is the
    // only answer: there is nothing else left to show.
    if (!paired || this.view !== "simple") this.step = "shot";
    // The desk shows both at once, so it has no step to be on and no switch to
    // draw. In the simple view the switch is the card's, and only once there is
    // a second thing for it to switch to.
    const stepping = this.view === "simple" && !!this.node.mmcBody?.preStage;
    this.stepBar.style.display = stepping ? "" : "none";

    // The one the card is showing, and the one beside it on the desk. In the
    // simple view the second is null and its node keeps its body on the canvas,
    // exactly as an unopened node does — nothing about it is hidden or held.
    const front = this.step === "pre" ? paired : this.node;
    const beside = this.view === "simple" ? null : paired;

    const body = front.mmcBody;
    // Kept, because the frame and the teardown both have to ask the body that
    // is actually on the card rather than the node the editor was opened on.
    this.front = front;
    this.colHeadName.textContent =
      this.node.mmcBody?.showsStrip?.() ? t("Strip") : t("Shot");
    this.paintMark();
    // The body goes inside a wrapper the card keeps, rather than straight into
    // the card. What it buys is a stable element: `mount` replaces the body on
    // every step change, and the turn between the two steps has to be run on
    // something that is still there afterwards. See `turnTo`.
    this.col.replaceChildren(this.colHead, this.stepBar, this.face, this.runRow);
    this.face.replaceChildren(body.root);
    // The card the simple view draws has no cast drawer and no Cast tool — see
    // styles/fullscreen.js for why — so the body it borrows has to be told, or
    // it goes on answering "the shelf is a row of me" because it still knows
    // its node id. Everything press-a-name does keys off that answer: whether
    // the press is what put the shelf up, and so whether the next press takes
    // it away again. The desk draws the drawer, so there it stays resident.
    this.setCastResident(body, this.view !== "simple");
    // The stage is the satellite's until it is told otherwise.
    body.satellite?.dock(this.dock);
    // `onVisibility` stays the satellite's — it owns "is there a picture". This
    // is the other question, and the run row is the only thing that asks it.
    const step = this.step;
    if (body.stage) body.stage.onState = (state, progress) => {
      Object.assign(this.runs[step], { state, progress });
      this.keepTake(body.stage, step);
      this.paint();
    };
    // The lip is the front step's history, and the front step's alone — so a
    // review borrowed from the lip we are about to swap out has to go first,
    // and without the flight home: the cell it would fly back to is leaving.
    this.endReview({ animate: false });
    this.strip.replaceChildren(this.past[step]);
    // And the grip goes on whatever picture is now on the plate. It lives
    // inside the stage's own element because that element *is* the picture —
    // the dock around it is a centring box the size of the whole plate, and a
    // corner of that is a corner of the room rather than of the render.
    if (body.stage) body.stage.root.appendChild(this.sizer);
    // The empty frame is drawn from whatever the card is about to make — the
    // shot's canvas and length, or the still's canvas. The body says when it
    // has redrawn — which is after every commit, and so is also the only
    // notice the bar gets that the family pill moved.
    body.onRender = () => { this.paintFrame(); this.paintMark(); };
    this.paintFrame();

    // Whatever is no longer where it belongs goes home first. This is the path
    // a closed pre-stage takes out, and the path the step it just left takes:
    // its node may well still exist, and a body left parented in a hidden column
    // is a node with a blank face and nothing on screen to say so.
    for (const node of [this.hosted, this.node, paired]) {
      if (node && node !== front && node !== beside) this.release(node);
    }
    this.hosted = beside;
    if (beside) {
      // Still above controls, the same order the canvas pair reads in: the
      // PreStage's satellite already puts its result on the far side of it.
      this.pre.replaceChildren(this.preHead, this.preStill, beside.mmcBody.root,
                               this.preRunRow);
      beside.mmcBody.satellite?.dock(this.preStill);
      // Its own button has to say what its own node is doing. No `keepTake`:
      // the reel belongs to the step the card is on, and on the desk that is
      // always the shot — the still keeps its picture in the column above.
      const preStage = beside.mmcBody.stage;
      if (preStage) preStage.onState = (state, progress) => {
        Object.assign(this.runs.pre, { state, progress });
        this.paint();
      };
    } else {
      this.pre.replaceChildren();
    }
    this.pre.classList.toggle("on", Boolean(beside));

    // The node's own title, which LiteGraph already lets you rename and already
    // saves into the workflow. A piece name is a thing this pack would otherwise
    // have had to invent, store and reconcile; the graph has one.
    //
    // **Shown only when it is a name somebody gave.** A node nobody has renamed
    // is titled after its display name, so drawing it here would spell the
    // pack's name a second time — `Continuity / MiniMax H3 / Continuity` — and
    // the reader would have to notice that the third word was the one that
    // could have been different. Against the constructor's title rather than a
    // hardcoded list, so this keeps working whatever the node ends up called.
    const named = (this.node.title || "").trim();
    const untitled = !named || named === (this.node.constructor?.title ?? "").trim();
    this.piece.textContent = named;
    this.pieceGroup.classList.toggle("on", !untitled);
  }

  /**
   * Switch which half of the pair the card is showing.
   *
   * `mount` again, for the same reason `setView` does: the bodies swap places
   * and the reel swaps with them. Neither node leaves the graph and neither
   * blob is touched, so this is a change of what is on screen and nothing else
   * — including for the queue, which runs both nodes on one Render whichever
   * step you pressed it from.
   */
  setStep(step) {
    if (!STEPS.some(([name]) => name === step)) return;
    // Pressing a step there is nothing behind is asking for it. The same call
    // the removed pill made, and the node it spawns is not in the graph until
    // the next frame — `preStage.toggle` already schedules the remount that
    // finds it, so this only has to say where to land.
    if (step === "pre" && !preStageOf(this.node)) {
      this.step = "pre";
      this.node.mmcBody?.preStage?.toggle();
      return;
    }
    if (step === this.step) return;
    // Which way the pair reads, so the turn goes the way the switch does.
    // Pre-stage is left of Shot and always has been — it is the step before it
    // — so the sign is the whole of the direction.
    const was = STEPS.findIndex(([name]) => name === this.step);
    this.turnTo(step, Math.sign(STEPS.findIndex(([name]) => name === step) - was));
  }

  /**
   * Turn the card over onto its other step.
   *
   * Both steps are now the same rectangle — a fixed measure in both axes, see
   * styles/fullscreen.js — and two faces the same size that you switch between
   * is a *card*. So the switch turns it: the work rotates away on its own
   * vertical axis, the other step is mounted while its back is to you, and it
   * comes round the rest of the way. Only the work turns. The switch you pressed
   * and the Render under it stay where they are, because they belong to the
   * window rather than to the step, and a control that flees the press is a
   * control you press twice.
   *
   * The two halves are deliberately uneven. Leaving is quicker than arriving and
   * accelerates into the edge; arriving decelerates out of it and carries a
   * touch of overshoot in the light rather than in the geometry — the lit
   * segment of the switch is still travelling underneath the whole time, which
   * is what says the two halves are one gesture.
   *
   * With reduced motion it is the swap and nothing else.
   */
  turnTo(step, dir) {
    const land = () => {
      this.step = step;
      this.mount();
      this.paint();
    };
    if (reduced() || this.view !== "simple" || !this.face.animate) {
      land();
      return;
    }
    // A second press mid-turn would mount under a running animation and leave
    // the card edge-on. The switch itself stays live — this only drops presses
    // that arrive inside the third of a second the turn takes.
    if (this.turning) return;
    this.turning = true;
    // The lit segment goes now, on the press, rather than at the swap: it is
    // the one thing on screen that crosses the whole gesture, and a highlight
    // that waited for the card to be half-turned would have nothing to say
    // about the first half of it.
    this.paintInk(step);
    // Lit from the side it is turning away from, so the face darkens as it goes
    // edge-on and comes back up into the light. Nothing else says a flat
    // rectangle has a thickness.
    const away = this.face.animate([
      { transform: "perspective(1600px) rotateY(0deg)", filter: "brightness(1)" },
      { transform: `perspective(1600px) rotateY(${dir * -90}deg) scale(.94)`,
        filter: "brightness(.45)" },
    ], { duration: 190, easing: "cubic-bezier(.6, 0, .9, .5)", fill: "forwards" });
    away.finished.then(() => {
      land();
      // Started before the half that held the card edge-on is cancelled, and
      // not after: two animations on one element resolve in the order they were
      // started, so this one is already overriding that held state by the time
      // it goes. Cancelling first would show the new face flat for one frame.
      const back = this.face.animate([
        { transform: `perspective(1600px) rotateY(${dir * 90}deg) scale(.94)`,
          filter: "brightness(.45)" },
        { transform: "perspective(1600px) rotateY(0deg)", filter: "brightness(1)" },
      ], { duration: 280, easing: "cubic-bezier(.2, .85, .3, 1)" });
      back.finished.finally(() => { away.cancel(); this.turning = false; });
    }, () => { this.turning = false; });
  }

  /**
   * Put the lit segment under the step you are on.
   *
   * Measured rather than declared: the two segments are the width of their own
   * words, in whatever language the shell is drawn in, so there is no fraction
   * to slide the ink by. The first placement is silent — a pill that slid in
   * from the left edge on open would announce a switch nobody made.
   */
  paintInk(step = this.step, retry = true) {
    const on = [...this.stepBar.children].find((el) => el.dataset?.step === step);
    if (!on) return;
    // Nothing to measure until the bar is in the document and displayed, which
    // on the first open is a frame away. Asked once more and then let go.
    if (!on.offsetWidth) {
      if (retry && this.stepBar.style.display !== "none") {
        requestAnimationFrame(() => this.paintInk(step, false));
      }
      return;
    }
    this.stepInk.style.width = `${on.offsetWidth}px`;
    this.stepInk.style.transform = `translateX(${on.offsetLeft}px)`;
    if (!this.inked) {
      this.inked = true;
      // After the placement above has been painted, or the class that turns the
      // transition on is in force for the placement itself.
      requestAnimationFrame(() => this.stepInk.classList.add("travels"));
    }
  }

  /**
   * Switch views. `mount` again rather than rebuild: the simple view hosts one
   * body where the desk hosts two, so which nodes are borrowed changes — and
   * everything else about the switch is a class name, which is why the prompt
   * you were half-way through typing is still there afterwards.
   */
  setView(view) {
    if (!VIEWS.includes(view) || view === this.view) return;
    // The switch is in the bar and stays pressable while the dashboard is up,
    // so it puts the room back: a control whose whole result is hidden behind
    // the surface you are looking at is a control that appears to do nothing.
    this.closeDash();
    this.view = view;
    try { localStorage.setItem(VIEW_KEY, view); } catch { /* private mode; the session still switches */ }
    this.mount();
    this.paint();
  }

  // ---- where else the editor can go ------------------------------------------

  /**
   * The mark, pressed. Up becomes down and down becomes up — one control for
   * both directions, because the dashboard covers the room the mark sits over
   * and there is no outside left to click.
   */
  toggleDash() {
    if (this.dash) this.closeDash(); else this.openDash();
  }

  /**
   * Turn the room over to the tools.
   *
   * Built fresh every time for the same reason the list was: a card's
   * destination is resolved against whichever body is on the card *now*, and
   * the step can have changed since the last time this was up.
   */
  openDash() {
    if (this.dash) return;
    this.dash = buildDashboard({
      groups: this.destinations(),
      onLeave: () => this.closeDash(),
    });
    this.room.appendChild(this.dash);
    this.mark.setAttribute("aria-expanded", "true");
    // Focus goes to the first card, so the surface is usable from the keyboard
    // the moment it is up rather than after tabbing back through the bar.
    this.dash.querySelector(".mmc-dash-card:not(.soon)")?.focus();
  }

  /** And back to the piece. */
  closeDash() {
    if (!this.dash) return;
    // Only when the keyboard was on the surface being taken away — otherwise
    // this is the view switch closing it, and moving focus onto the mark from
    // a button somebody just pressed elsewhere in the bar is focus theft.
    const held = this.dash.contains?.(document.activeElement);
    this.dash.remove();
    this.dash = null;
    this.mark.setAttribute("aria-expanded", "false");
    if (held) this.mark.focus();
  }

  /**
   * Everywhere the wordmark can take you.
   *
   * Two groups, and the split between them is what a card *does* to the window.
   * **Go to** rearranges the room you are already in: the same piece, one column
   * in the middle of the screen, showing the step you named. **Tools** open a
   * surface over it. Both are cards because both are destinations, and a person
   * pressing the mark is asking the same question either way — where else can I
   * be — but a card that moves the furniture and a card that opens a door should
   * not be adjacent without a line between them.
   *
   * The quick links exist because the two halves of a piece are two rooms and the
   * way between them was three presses in two different places: the view switch
   * in the bar, then the step switch on the card, and the step switch is not even
   * drawn until the view is simple. One card, one press, and pressing Pre-stage
   * when the piece has none spawns it on the way — the same thing `setStep` has
   * always done, said out loud.
   *
   * Built fresh on every open, because every one of these is resolved against
   * whichever body is on the card *now*. A tool becomes reachable by becoming a
   * card here, not by growing a button somewhere.
   */
  destinations() {
    const body = this.front?.mmcBody;
    const editor = body?.editor ?? body;
    const strip = this.node.mmcBody?.showsStrip?.();
    // What the two Go-to cards are made of: the piece itself. The tools carry
    // their own plates — see `cardArt` for why the two halves of this surface
    // are pictured differently.
    const still = this.pieceFrame();
    const clip = this.shown?.shot && !this.shown.shot.isImage ? this.shown.shot.url : null;
    return [
      { title: t("Go to"), items: [
        { label: t("Pre-stage"), glyph: "image",
          sub: t("The still this shot is built on, alone in the middle of the screen"),
          art: { kind: "still", url: still },
          go: () => this.goTo("pre") },
        { label: strip ? t("Strip") : t("Shot"), glyph: "video",
          sub: t("The video — the prompt, the cast and everything the render reads"),
          // The rendered clip if there is one, and the still it was built from
          // cut into frames if there is not: the card says what the shot *is* so
          // far, and never repeats the pre-stage card's photograph whole.
          art: clip ? { kind: "clip", url: clip } : { kind: "strip", url: still },
          go: () => this.goTo("shot") },
      ] },
      { title: t("Tools"), items: [
        { label: t("Presets"), sub: t("Apply a saved setup, or save this one"),
          glyph: "star",
          art: { kind: "deck", url: cardArt("presets") },
          go: () => openPresetLibrary({
            target: editor?.presetTarget?.() ?? body?.pieceTarget?.() ?? null,
          }).then(() => editor?.render?.()) },
        // The bench, and the pair of doors back. Not a preview and not a node:
        // what it hands back is a file in the input folder, and the targets below
        // are the two places this piece can take one.
        { label: t("ControlNet"), glyph: "pen",
          sub: t("Trace footage into edges, lines or tones — then aim a render at it"),
          art: { kind: "trace", url: cardArt("controlnet"),
                 made: cardArt("controlnet-depth") },
          go: () => openControl({ targets: this.guideTargets(), back: () => this.openDash() }) },
        // The other bench, and the one with no doors: what it makes is the
        // finished file rather than something a render reads, so it lands on a
        // shelf beside the renders and nothing here has to take it anywhere.
        { label: t("Upscale"), glyph: "expand",
          sub: t("Make a still or a clip bigger — the file itself, not a new render"),
          art: { kind: "scale", url: cardArt("upscale") },
          go: () => openUpscale({
            source: this.lastTake(), targets: this.upscaleTargets(),
            // The way back. A card opened a room; its wordmark is what puts the
            // cards up again, so leaving a tool is the same press that entered
            // it rather than the ✕ at the other end of the bar.
            back: () => this.openDash(),
          }) },
      ] },
    ];
  }

  /**
   * The piece's frame: what the Go-to cards are pictures of.
   *
   * A piece has several places one could come from, and this takes them in the
   * order of how much each is the thing on the screen right now: the still that
   * was just rendered, the still it was rendered from, a reference somebody
   * attached to the pre-stage, a reference on the piece's own shelf.
   *
   * Null on a piece with nothing on it at all, and those two cards fall back to
   * their glyphs — the honest answer on the first day, rather than a stand-in
   * picture of work nobody has done yet.
   *
   * Previews rather than originals: two cards holding the same 4000-pixel PNG
   * is the picker's old mistake, and core re-encodes on request.
   */
  pieceFrame() {
    const shown = this.shown?.pre ?? (this.shown?.shot?.isImage ? this.shown.shot : null);
    if (shown?.url) return shown.url;
    const pre = preStageOf(this.node)?.mmcBody?.state;
    const attached = pre?.init?.filename
      ?? (pre?.refs ?? []).find((ref) => ref.filename)?.filename
      ?? (this.node.mmcBody?.timeline?.assets ?? [])
           .find((asset) => asset.filename && asset.kind !== "video")?.filename;
    return attached ? viewUrl(attached, { preview: true }) : null;
  }

  /**
   * Where a finished upscale can go.
   *
   * Fewer doors than a tracing has, and that is the difference between the two
   * benches rather than an omission: a tracing is an instruction to the sampler
   * and there are three different ones it can be, where an upscale is a
   * *picture* — so both doors here are the same act, attaching it, and what
   * changes is which card it lands on. The file is on the shelf either way;
   * these only save the trip through the picker.
   */
  upscaleTargets() {
    const targets = [];
    const shot = this.node.mmcBody;
    if (shot?.takeReference) {
      targets.push({
        id: "shot", label: t("Attach to the shot"),
        does: t("Read as a look, and named in the prompt with @."),
        take: (result) => shot.takeReference({ path: result.path, kind: result.kind }),
      });
    }
    const pre = preStageOf(this.node)?.mmcBody;
    if (pre?.attachFromMention) {
      targets.push({
        // Pictures only, and the bench answers that by upscaling the frame under
        // its playhead rather than by greying the door out — the encoder's slots
        // are pictures and a clip has to be a frame first.
        id: "pre", kinds: ["image"], label: t("Attach to the pre-stage"),
        does: t("A picture the still is drawn from, cited by its handle."),
        take: (result) => {
          const handle = pre.attachFromMention({ path: result.path, kind: result.kind });
          // The pool has three slots and it can be full. Said on the card the
          // file was going to, which is where somebody would go looking for it.
          if (handle === null) pre.flash?.(t("The pre-stage has no slot free for it."));
          this.paintFrame();
          this.revealPreStage();
        },
      });
    }
    return targets;
  }

  /**
   * The newest finished render on this card, in the shape a bench takes a
   * source in — or null, on a card that has not rendered yet.
   *
   * It is a convenience and not a wiring: the upscale bench takes any file at
   * all, and this only saves somebody going and finding in the picker the thing
   * that is on the screen behind them. `saved` carries the folder ComfyUI wrote
   * to, so the path is annotated the way the gallery's own paths are and
   * `media.resolve` reads it without a second species of path being invented.
   */
  lastTake() {
    const shown = this.shown?.shot ?? this.shown?.pre ?? null;
    const saved = shown?.saved;
    if (!saved?.filename) return null;
    const folder = saved.subfolder ? `${saved.subfolder}/` : "";
    return {
      path: `${folder}${saved.filename} [${saved.type || "output"}]`,
      kind: shown.isImage ? "image" : "video",
    };
  }

  /** Put the pre-stage in front, wherever this shell happens to be.
   *
   *  In the desk view both columns are already on screen and there is nothing
   *  to do; in the simple view the pre-stage is a step, and a step you are not
   *  on is a step you cannot see. */
  revealPreStage() {
    if (this.view === "simple" && preStageOf(this.node)) this.setStep("pre");
  }

  /** A quick link, pressed: one column, showing the step named. `setView` first,
   *  because `setStep` in the desk view has no card to turn and nothing to say. */
  goTo(step) {
    this.setView("simple");
    this.setStep(step);
  }

  /**
   * Where a finished guide can go, and what happens to it there.
   *
   * Every target is one of the piece's own bodies — nothing here is a second
   * way of holding a file. What differs between them is what the drawing *does*
   * once it lands, which is why each carries a `does`: a guide the shot is
   * aimed at, a picture the still is built on and a reference named in a prompt
   * are three different instructions, and a row of buttons that all say "send"
   * makes them look like one.
   *
   * `kinds` says what shape a door takes, not what it refuses. A pre-stage
   * renders a still, so it takes one; the bench answers that by cutting the
   * frame under its playhead rather than by greying the door out. What a door
   * genuinely cannot be given — a moving guide out of a photograph — is a door
   * the bench never draws, from the moment the source lands.
   */
  guideTargets() {
    const targets = [];
    const pre = preStageOf(this.node)?.mmcBody;
    if (pre?.takeGuide) {
      // Which slot it lands in is the weights' answer, not this button's — see
      // `PreStageEditor.takeGuide`. Said here because it is the difference
      // between a render aimed at the tracing and a render *of* the tracing,
      // and the press is where somebody would want to know.
      // Three answers, because there are three ways a pre-stage can take a
      // drawing and they do genuinely different things to the render.
      const native = S.preStageReadsGuides(pre.state);
      const branch = S.preStageLoadsBranch(pre.state);
      targets.push({
        id: "pre", kinds: ["image"],
        label: native || branch ? t("Aim the still at it") : t("Build the still on it"),
        does: native
          ? t("These weights follow a tracing on their own — nothing to load.")
          : branch
            ? t("Loads the ControlNet branch that reads it.")
            : t("Becomes the pre-stage's init image."),
        // Closes the bench and puts the pre-stage in front, because sending is
        // the end of the errand: the guide exists to be written a prompt
        // around, and the next thing anybody does is write it.
        closeOnSend: true,
        take: (result) => {
          pre.takeGuide(result);   // carries `opId`, which the pre-stage reads
          this.paintFrame();
          this.revealPreStage();
        },
      });
    }
    // The guide slot: not a reference and not a picture the render starts from,
    // but the drawing this shot is aimed at. Offered first, because on a family
    // that has a ControlNet it is what the bench was opened for — the other two
    // are what you do with a tracing when there is nothing to load that reads
    // it.
    //
    // It goes through `takeGuide` on the body rather than writing an asset from
    // here, so a drawing that arrives from the bench lands by exactly the same
    // path as one picked in the Guide tab: same handle rules, same swap of an
    // existing one, same switch thrown on arrival. Two ways in, one attach.
    //
    // A picture or a clip, and only where the family declares a branch. On a
    // family with no ControlNet there is nothing to aim with, which is a real
    // answer and not a missing feature — Qwen-Image-Edit reads a tracing
    // straight out of a picture slot, which is what the pre-stage target above
    // already does.
    //
    // No `kinds`: which shape is right is the shot's question rather than the
    // file's, and `compile._parse_assets` answers it the same way. A clip is
    // what a moving shot wants, one frame aimed at each of its own; a still is
    // one drawing the whole shot is held against, which is unusual, legitimate,
    // and exactly what a one-frame generation wants.
    const body = this.node.mmcBody;
    if (body?.takeGuide && S.controlOf(S.pieceFamily(body.timeline ?? {}))) {
      targets.unshift({
        id: "guide", label: t("Aim the shot at it"),
        does: t("Every frame of the shot follows a frame of the drawing."),
        // The same door, told what it is doing when the drawing does not move.
        doesStill: t("The whole shot is aimed at this one drawing, held throughout."),
        closeOnSend: true,
        // `opId` is why the bench hands over more than a path: which tracing
        // this is decides whether these weights were ever post-trained on it,
        // and the pill says so once it is attached.
        take: (result) => body.takeGuide({
          path: result.path, kind: result.kind, op: result.opId,
        }),
      });
    }
    const shot = this.node.mmcBody;
    if (shot?.takeReference) {
      targets.push({
        id: "shot", label: t("Attach as a reference"),
        does: t("Read as a look, and named in the prompt with @."),
        take: (result) => shot.takeReference({ path: result.path, kind: result.kind }),
      });
    }
    return targets;
  }

  /**
   * Move the finished picture into the reel when the next queue takes the stage.
   *
   * The stage is one box and it is cleared by the next run of its own — see
   * `Stage.begin` — which is right on a canvas — a card beside a node showing last week's render while this
   * week's is sampling would be a card that lies. In a window there is room for
   * both, and the thing that was lost was the comparison: you queue a second
   * take of a shot precisely to look at it beside the first.
   *
   * So the hand-off is the transition rather than the result. A run that starts
   * is what retires whatever the stage was holding; a run that finishes only
   * records what to retire next time. Nothing is copied and nothing is stored —
   * the entry points at the same file the gallery would open, which is why
   * closing the editor loses only the list and not a single render.
   */
  keepTake(stage, step) {
    if (stage.state === "sampling") {
      if (this.shown[step]) {
        // Newest first. The lip reads outward from the plate: the take nearest
        // the left edge is the one that was on the picture a moment ago, and
        // the further right you look the older it gets. Appending put the
        // newest at the far end of a row that only grows, so the one thing you
        // reach for was the one thing that kept moving away and had to be
        // scrolled back to.
        this.past[step].prepend(this.take(this.shown[step]));
        this.shown[step] = null;
        this.strip.scrollLeft = 0;
      }
      return;
    }
    if (stage.state === "done" && stage.result) this.shown[step] = stage.result;
  }

  /**
   * One finished render, as it sits on the lip.
   *
   * **No transport.** A thumbnail is not a player: eight scrub bars along a
   * shelf are eight rows of chrome over eight pictures too small to scrub, and
   * the one gesture the lip actually wants — press it, look at it big — was
   * competing with a play button for the same twelve pixels. The whole cell is
   * the button now, and the picture it holds is undecorated.
   *
   * **Still at rest, moving under the pointer.** Ten clips looping at once is
   * not history, it is noise, so nothing plays until it is pointed at — and
   * then it plays, because along a lip of takes of the same shot, with the same
   * truncated filename stem, motion is the only thing that tells one from
   * another. Off the pointer it winds back to its first frame, so the shelf is
   * the same shelf you left.
   */
  take(result) {
    const media = result.isImage
      ? el("img", { class: "mmc-fs-take-media", src: result.url, alt: "" })
      // The media fragment asks for a frame rather than a black rectangle.
      : el("video", {
          class: "mmc-fs-take-media", src: `${result.url}#t=0.1`,
          loop: true, playsinline: true, preload: "metadata",
        });
    // The property, not the attribute: the attribute is only read as the
    // autoplay gate at parse time, and this clip is started by hand.
    if (media.tagName === "VIDEO") media.muted = true;
    const tile = el("button", {
      class: "mmc-fs-take", title: result.name,
      "aria-label": t("Show this render on the picture"),
      onclick: () => this.review(result, tile),
      onkeydown: (event) => this.takeKey(event, tile),
      onpointerenter: () => media.play?.().catch(() => {}),
      onpointerleave: () => {
        if (!media.pause) return;
        media.pause();
        media.currentTime = 0.1;
      },
    }, [
      media,
      // What it cost, which is the one thing about a past take you cannot see by
      // looking at it — and the reason the clock on the plate is worth keeping
      // after the render lands. The filename moved to the tooltip: on a lip of
      // thumbnails it was a row of identical truncated stems.
      el("div", { class: "mmc-fs-take-note",
                  text: result.tookMs ? elapsed(result.tookMs) : "" }),
    ]);
    return tile;
  }

  /** Along the lip without a pointer. The cells are buttons, so Tab already
   *  reaches them; this is the other half of a row — the arrows walk it. */
  takeKey(event, tile) {
    const next = { ArrowRight: "nextElementSibling",
                   ArrowLeft: "previousElementSibling" }[event.key];
    if (!next) return;
    const target = tile[next];
    if (!target) return;
    event.preventDefault();
    target.focus();
  }

  // ---- looking at an earlier take -------------------------------------------

  /**
   * The hand-off chips, on a take borrowed back from the lip.
   *
   * A still does not stop being usable because a newer one was made. The
   * pre-stage's plate has carried "→ start / → end / → ref" since the pair
   * existed, but the moment the next queue retired that still to the lip the
   * only way to reach the row again was to re-render the picture you were
   * already looking at — which is the one thing the lip exists to make
   * unnecessary. Reviewing is *for* choosing between takes; the choice has to
   * be actionable where it is made.
   *
   * Not re-implemented here: the row is whatever the body on the card builds
   * from an `executed` payload, which is `PreStageBody.renderResultChips` and
   * its late-resolved peer. So a take answers to the same capacity and
   * exclusivity rules the live still does, resolved at the press rather than
   * at the render — and a step whose body has no such row (the shot's, whose
   * takes are clips) simply gets none.
   */
  reviewChips(result) {
    // `saved` is the output entry the chips name the file from, and a clip is
    // not a frame: the shot's own takes are videos, and a video has no place in
    // a start-frame slot.
    if (!result.saved || !result.isImage) return [];
    return this.front?.mmcBody?.renderResultChips?.(result.saved) ?? [];
  }

  /**
   * Put a take from the lip on the picture.
   *
   * **A layer over the stage, not a picture written into it.** The stage owns
   * exactly one render — the one that is happening — and rebuilds itself on
   * every frame the sampler sends; handing it an older file would be a picture
   * the next preview erases, and a run to put back afterwards. So the take is
   * shown in front of the stage and the stage is left entirely alone. That is
   * also the whole of why this works mid-render: there is no special case for
   * "while sampling", because nothing about the run is being interrupted to
   * show you something else. The progress under the layer goes on being made,
   * and when it lands it lands — on the plate you will come back to, not over
   * the thing you were looking at.
   *
   * @param {object} result  the retired render, as `keepTake` recorded it
   * @param {HTMLElement} tile  the cell on the lip it flies out of
   */
  review(result, tile) {
    // The same press again is the way back — a take already on the picture has
    // nowhere further to go, and pressing it a second time is what people try.
    if (this.reviewing?.tile === tile) { this.endReview(); return; }
    this.endReview({ animate: false });

    const media = result.isImage
      ? el("img", {
          class: "mmc-fs-review-media", src: result.url, alt: result.name,
          onload: (event) => this.reviewSized(event.currentTarget.naturalWidth,
                                              event.currentTarget.naturalHeight),
        })
      // Everything the plate's own finished player is, by the same argument
      // made in stage.js: the transport is the browser's, it loops, it starts
      // silent because no browser would start it otherwise, and the sound
      // follows the pointer. One video, one set of manners, in one window.
      : el("video", {
          class: "mmc-fs-review-media", src: result.url,
          autoplay: true, controls: true, loop: true, playsinline: true,
          preload: "metadata",
          onloadedmetadata: (event) => this.reviewSized(event.currentTarget.videoWidth,
                                                        event.currentTarget.videoHeight),
          onmouseenter: (event) => { event.currentTarget.muted = false; },
          onmouseleave: (event) => { event.currentTarget.muted = true; },
        });
    if (media.tagName === "VIDEO") media.muted = true;

    this.reviewCard = el("div", { class: "mmc-fs-review-card" }, [
      media,
      // The plate's own readout grammar, in the plate's own two slots: the way
      // out on the left where the stage puts Gallery, the clock on the right
      // where the stage puts the clock. A take on the picture has to say it is
      // not the render — and saying it here means the picture never has to be
      // taken away from you to make the point.
      el("div", { class: "mmc-stage-readout" }, [
        el("div", { class: "mmc-stage-side" }, [
          el("button", {
            class: "mmc-stage-chip mmc-fs-review-back",
            onclick: () => this.endReview(),
          }, [icon("rewind", 13), el("span", { text: t("Back to the render") })]),
          ...this.reviewChips(result),
        ]),
        result.tookMs
          ? el("div", { class: "mmc-stage-side end" }, [
              el("span", { class: "mmc-stage-chip mmc-stage-clock",
                           title: t("How long this render took"),
                           text: elapsed(result.tookMs) }),
            ])
          : null,
      ]),
    ]);
    this.reviewLayer = el("div", {
      class: "mmc-fs-review",
      // The room around the card, which is the same gesture as the room around
      // the plate: press where the picture is not.
      onclick: (event) => { if (event.target === this.reviewLayer) this.endReview(); },
    }, [this.reviewCard]);

    tile.classList.add("up");
    this.dock.appendChild(this.reviewLayer);
    // The scrim arrives on its own clock rather than as part of the flight: it
    // is the room dimming, and the take is the thing crossing it.
    requestAnimationFrame(() => this.reviewLayer?.classList.add("lit"));
    this.reviewing = { result, tile, media, from: tile.getBoundingClientRect() };
  }

  /**
   * The card has a shape, so it has a size — and only now can the flight be
   * measured. The same two custom properties the stage hands its own dock, for
   * the same reason: which of the two bounds a picture hits first is arithmetic
   * CSS will not do from a ratio alone.
   */
  reviewSized(width, height) {
    if (!width || !height || !this.reviewCard) return;
    this.reviewCard.style.setProperty("--mmc-review-ar", `${width} / ${height}`);
    this.reviewCard.style.setProperty("--mmc-review-arn", `${width / height}`);
    this.reviewCard.dataset.sized = "1";
    this.flyIn();
  }

  /**
   * The take travels out of its cell onto the plate.
   *
   * A FLIP: the cell's rectangle was taken at the press, the card's is taken
   * once it has been laid out, and the difference between them is played as a
   * transform on the card. Nothing is laid out twice and nothing animates a
   * width, so the picture is never reflowed mid-flight.
   *
   * It is worth the machinery for one reason: it says which take is on the
   * picture without printing a label saying so. The cell it left is still on
   * the lip, dimmed and holding its own footprint, and the line between the two
   * was drawn by the movement.
   */
  flyIn() {
    const state = this.reviewing;
    if (!state || state.flown) return;
    state.flown = true;
    const to = this.reviewCard.getBoundingClientRect();
    const flight = reduced() || !to.width || !state.from?.width
      ? this.reviewCard.animate([{ opacity: 0 }, { opacity: 1 }], REVIEW_FADE)
      : this.reviewCard.animate([{ transform: flipFrom(state.from, to), borderRadius: "10px" },
                                 { transform: "none", borderRadius: "18px" }], REVIEW_FLIGHT);
    // A press that comes back before the take has finished arriving cancels
    // this, and a cancelled animation rejects. Nothing is waiting on it.
    flight.finished.catch(() => {});
  }

  /**
   * Give the picture back. The take flies home to the cell it came from, which
   * is the same sentence read backwards and the reason the lip never has to be
   * searched for where the thing you were looking at went.
   *
   * `animate: false` for the cases where there is no home to fly to: the lip
   * being swapped for the other step's, or the whole editor going away.
   */
  endReview({ animate = true } = {}) {
    const state = this.reviewing;
    if (!state) return;
    this.reviewing = null;
    const { tile } = state;
    const layer = this.reviewLayer;
    const card = this.reviewCard;
    this.reviewLayer = null;
    this.reviewCard = null;
    // Before anything is measured: a clip left playing behind a fade is a clip
    // still talking after it is gone.
    state.media.pause?.();
    tile.classList.remove("up");
    layer.classList.remove("lit");

    // The flight out may still be running, and a rectangle read off a card
    // mid-transform is not the rectangle the card is laid out at. Cancelling
    // puts it back where CSS says it is, this frame, before it is measured.
    for (const running of card.getAnimations()) running.cancel();
    const home = tile.isConnected ? tile.getBoundingClientRect() : null;
    const from = card.getBoundingClientRect();
    const flight = animate && !reduced() && home?.width && from.width
      ? card.animate([{ transform: "none", borderRadius: "18px" },
                      { transform: flipFrom(home, from), borderRadius: "10px" }],
                     REVIEW_FLIGHT)
      : card.animate([{ opacity: 1 }, { opacity: 0 }],
                     animate ? REVIEW_FADE : { duration: 0 });
    const done = () => layer.remove();
    flight.finished.then(done, done);
  }

  // ---- how big the picture is drawn -----------------------------------------

  /**
   * Set the plate's scale and say so, in the one place that has to know: a
   * custom property on the shell, which the picture's two maxima are written
   * in terms of. Nothing is measured and nothing is laid out by hand — the
   * plate goes on centring whatever is in it, so a change of size is a change
   * of size and not a change of position.
   */
  setPlate(scale, { store = true } = {}) {
    this.plateScale = clampPlate(scale);
    this.root.style.setProperty("--mmc-plate-scale", String(this.plateScale));
    this.sizeRead.textContent = `${Math.round(this.plateScale * 100)}%`;
    this.grip.setAttribute("aria-valuenow", String(Math.round(this.plateScale * 100)));
    if (!store) return;
    try { localStorage.setItem(PLATE_KEY, String(this.plateScale)); }
    catch { /* private mode; the session still resizes */ }
  }

  /**
   * The drag. Pointer capture rather than window listeners, so a pointer that
   * leaves the picture — which it does immediately, because the plate is
   * shrinking away from it — keeps steering the thing it grabbed.
   *
   * The movement is read as a fraction of the picture's own size rather than in
   * pixels: dragging an inch has to mean the same amount on a phone-sized
   * portrait render and on a 4K landscape one. Doubled, because the plate grows
   * from its centre and the corner therefore only travels half of what the
   * picture gains.
   */
  gripDown(event) {
    // The card under the shell pans on drag, and the video under this one
    // scrubs; neither is what a grab on the corner means.
    event.preventDefault();
    event.stopPropagation();
    const box = this.sizer.parentElement?.getBoundingClientRect();
    if (!box?.width || !box?.height) return;
    const from = { x: event.clientX, y: event.clientY, scale: this.plateScale };
    this.sizer.classList.add("dragging");
    this.grip.setPointerCapture(event.pointerId);

    const move = (moved) => {
      // Right is wider and up is taller, which is what a handle in the top
      // right corner means. Averaged over the two axes so a diagonal drag —
      // which is how anybody actually grabs a corner — moves at the rate the
      // two edges agree on rather than at their sum.
      const k = ((moved.clientX - from.x) / box.width
                 + (from.y - moved.clientY) / box.height) / 2;
      let next = clampPlate(from.scale * (1 + 2 * k));
      // A little gravity at the three sizes anybody names, and none anywhere
      // else: the drag stays continuous, it just does not slide off 100% by a
      // percent on the way past.
      for (const stop of PLATE_DETENTS) {
        if (Math.abs(next - stop) < PLATE_CATCH) next = stop;
      }
      this.setPlate(next, { store: false });
    };
    const done = () => {
      this.sizer.classList.remove("dragging");
      this.grip.removeEventListener("pointermove", move);
      this.grip.removeEventListener("pointerup", done);
      this.grip.removeEventListener("pointercancel", done);
      // Written once, at the end: a drag across the plate is a hundred moves
      // and localStorage is not a thing to write to a hundred times.
      this.setPlate(this.plateScale);
    };
    this.grip.addEventListener("pointermove", move);
    this.grip.addEventListener("pointerup", done);
    this.grip.addEventListener("pointercancel", done);
  }

  /** The same control without a pointer. It is a button and it takes focus, so
   *  it has to do something when it has it. */
  gripKey(event) {
    const step = { ArrowRight: .05, ArrowUp: .05, "+": .05,
                   ArrowLeft: -.05, ArrowDown: -.05, "-": -.05 }[event.key];
    if (step === undefined) return;
    event.preventDefault();
    this.setPlate(this.plateScale + step);
  }

  /** Give one node's body back to the wrapper the DOM widget positions, and its
   *  picture back to the card that follows the node. */
  /** Whether the view this body is drawn in draws its cast drawer as a row.
   *  Both bodies an editor can be — the Creator's, and a PreStage's H3 branch —
   *  answer through the same editor, so this asks the body for it rather than
   *  reaching for a field that may not be there. */
  setCastResident(body, resident) {
    if (!body) return;
    // On the body first, because the body is what outlives the editor. A card's
    // editor is rebuilt whenever the segment object under it changes — a preset
    // carrying a strip, the piece cleared, a workflow re-read — and the new one
    // knew nothing about the view it had been borrowed into. It answered "the
    // shelf is a row of me", so pressing a name built a resident drawer that
    // this view's stylesheet hides, and the press looked like it had done
    // nothing. The body remembers; whoever builds the next editor stamps it.
    body.castResident = resident;
    const editor = body.editor;
    if (!editor) return;
    editor.castResident = resident;
    // A drawer put up by a press in the window has no business surviving the
    // view it was pressed in.
    if (!resident || !editor.castSummoned) return;
    editor.castSummoned = false;
    editor.castOpen = false;
    editor.render?.();
  }

  release(node) {
    const body = node?.mmcBody;
    if (!body) return;
    // Home to the canvas, where the face draws the drawer itself.
    this.setCastResident(body, true);
    if (body.stage) body.stage.onState = null;
    // Before the body goes home: the grip is the editor's, and a node dropped
    // back on the canvas with a resize handle on its satellite would be sizing
    // a card that is sized by the node.
    if (body.stage?.root.contains(this.sizer)) this.sizer.remove();
    body.onRender = null;
    body.satellite?.undock();
    node.mmcHost?.appendChild(body.root);
  }

  /**
   * Draw the frame the next render will fill: a hairline rectangle at the
   * piece's ratio, and under it the size and the length in plain numbers.
   *
   * An <svg> rather than a div because this is the one shape CSS cannot contain:
   * a box given both a width and a height simply ignores its aspect-ratio, while
   * a replaced element carrying the canvas as its intrinsic size letterboxes
   * exactly the way the picture that replaces it will. The stroke is drawn in
   * user units and told not to scale, so the hairline is a hairline at any size
   * the window gives it. The corner radius cannot take the same treatment — there
   * is no non-scaling-radius — so it is written as a fraction of the canvas
   * instead, which lands near the plate's own 18px at the sizes a frame is
   * actually drawn at. The outline has to be the shape the picture will be.
   */
  /** The family crumb: what the card in front of you renders with.
   *
   *  Read off the step rather than off the piece, because the two steps do not
   *  answer to the same pill. The shot's family is the piece's — the family pill
   *  on the rail — while a pre-stage's is its arch pill, which is a separate
   *  choice on a separate node and is routinely a different one: a Krea 2 still
   *  feeding a shot that lands on LTX 2.5 is the ordinary case, not a corner.
   *
   *  Only the simple view has a step to be on; the desk puts both columns on
   *  screen with the arch pill visible above the still, and forces `step` to
   *  the shot. So on the desk this is the piece's family, which is the one the
   *  bar is not otherwise saying.
   *
   *  **The piece is `mmcBody.timeline`, and only a pre-stage's is `.state`.**
   *  Worth saying because the two bodies are reached through the same property
   *  and the wrong one costs nothing at the time: `familyOf(undefined)` is a
   *  valid call that answers with the default family, so reading `.state` off a
   *  piece drew "MiniMax H3" over an LTX 2.5 shot and never once looked broken.
   *  Neither branch below is allowed to pass a missing object on. */
  paintMark() {
    const pre = this.step === "pre" ? preStageOf(this.node)?.mmcBody?.state : null;
    const piece = this.node.mmcBody?.timeline;
    const label = pre ? S.PRESTAGE_ARCH_LABEL[pre.arch]
                : piece ? S.familyOf(piece).label
                : null;
    this.family.textContent = label ? t(label) : "";
  }

  paintFrame() {
    const spec = this.front?.mmcBody?.frame?.();
    if (!spec?.width || !spec?.height) { this.frame.replaceChildren(); return; }
    const holder = document.createElement("span");
    holder.innerHTML = '<svg class="mmc-fs-frame-box" viewBox="0 0 ' + spec.width + ' '
      + spec.height + '" width="' + spec.width + '" height="' + spec.height
      + '"><rect x="0.5" y="0.5" width="' + (spec.width - 1) + '" height="' + (spec.height - 1)
      + '" rx="' + Math.round(spec.width / 45)
      + '" vector-effect="non-scaling-stroke"/></svg>';
    this.frame.replaceChildren(
      holder.firstElementChild,
      el("div", {
        class: "mmc-fs-frame-note",
        // A still has no length, so the pre-stage's frame is a size and nothing
        // else. Said by leaving it out rather than by printing "0.0 s".
        text: spec.width + " × " + spec.height
            + (spec.seconds ? " · " + spec.seconds.toFixed(1) + " s" : ""),
      }),
    );
  }

  /** Put everything back where the canvas expects it. */
  unmount() {
    // The layer hangs off the dock, which is the shell's, so it would go with
    // it — but the clip inside it would keep playing until the object was
    // collected. Stopped rather than dropped.
    this.endReview({ animate: false });
    document.removeEventListener("keydown", this.onKey);
    this.unwatchQueue?.();
    api.removeEventListener("promptQueued", this.onQueued);
    this.release(this.node);
    this.release(this.hosted);
    this.release(this.front);
    this.hosted = null;
    this.front = null;
    this.root.remove();
    noteFullscreen(false);
  }

  // ---- the queue ------------------------------------------------------------

  /** Named with a trailing underscore so it cannot be mistaken for the `render`
   *  every body in this pack has, which draws rather than queues. */
  render_(kind) {
    // Pressable while a render is running, exactly as ComfyUI's own Queue button
    // is: the queue is a queue, and the whole gesture of lining up three takes
    // and going to make coffee was refused by a button that disabled itself on
    // the first one. What the row says while busy is a status — "Sampling", the
    // step count, how many are behind it — not a lock.
    //
    // Optimistic: `status` will confirm within a tick, but the row has to stop
    // saying Render the instant it is pressed rather than a round trip later.
    const run = this.runs[kind] ?? this.runs.shot;
    run.queued = true;
    this.paint();
    // Exactly what the toolbar's own button calls, batch count included — with
    // the one node this press is about named, so the *other* half of the pair
    // is left alone. Both nodes are outputs of the same graph and a plain queue
    // runs every output in it, which is why one Render used to make a still
    // nobody had asked for whenever the pre-stage's prompt had been touched.
    // ComfyUI's own partial execution; a frontend too old to know the third
    // argument ignores it and runs the graph, which is where this started.
    //
    // A bare array, which is the one shape every frontend that knows the
    // argument at all reads the same way. `{ queueNodeIds: [...] }` is read by
    // 1.47 and 1.49+ and is the whole third argument to 1.44, 1.45 and 1.48 —
    // which forward it verbatim as `partial_execution_targets`, so the server
    // asks whether the node id is a *key* of `{queueNodeIds: [...]}`, finds it
    // is not, counts no output nodes and refuses the prompt: "Prompt has no
    // outputs", from a graph whose output node is sitting right there.
    const target = kind === "pre" ? preStageOf(this.node) : this.node;
    const before = this.accepted;
    this.inflight += 1;
    app.queuePrompt(0, 1, [String(target?.id ?? this.node.id)])
      // A rejection here is the exception rather than the rule — ComfyUI
      // swallows the ordinary refusal — and it lands where that one does.
      .catch(() => {})
      .finally(() => {
        this.inflight -= 1;
        // The press went out and nothing was accepted while it was in the air:
        // the prompt was refused, and the row goes back to offering the press
        // rather than reporting a render that is not happening. The dialog
        // ComfyUI put up says what was wrong with it.
        if (this.inflight || this.accepted !== before) return;
        run.queued = false;
        this.paint();
      });
  }

  /** ComfyUI's own cancel. Unscoped on purpose: the editor is a one-piece view,
   *  so the run in front of the user is the run they mean. */
  interrupt() {
    api.interrupt();
  }

  /** Whether one half of the pair has work in the queue or on the sampler. */
  busy(kind) {
    const run = this.runs[kind] ?? this.runs.shot;
    return run.queued || run.state === "sampling";
  }

  /** One run button, saying what its own node is doing. Never disabled — see
   *  `render_`: the queue is a queue, and the title is where the second press
   *  is offered because the label is busy reporting the first. */
  paintRun(button, kind, label) {
    const busy = this.busy(kind);
    const run = this.runs[kind];
    // Through el() rather than straight into replaceChildren: the step count is
    // an optional child, and el() is where this pack drops the ones that are not
    // there. replaceChildren would take the null and throw.
    button.replaceChildren(el("span", { class: "mmc-fs-label" }, [
      busy ? spinner() : icon("play", 16),
      el("span", { text: busy ? t("Sampling") : label }),
      busy && run.progress?.total
        ? el("span", {
            class: "mmc-fs-steps",
            text: `${run.progress.step} / ${run.progress.total}`,
          })
        : null,
    ]));
    button.classList.toggle("busy", busy);
    button.title = busy ? t("Queue another render behind this one") : "";
  }

  paint() {
    // The card's button runs the card's node, so what it is called is what that
    // node makes. On the desk the two are named apart because both are on
    // screen; in the simple view the step switch above has already said which.
    this.paintRun(this.run, this.step, t("Render"));
    this.paintRun(this.preRun, "pre", t("Render still"));
    // One Cancel for the shell, because `api.interrupt` is one call: it stops
    // whatever the sampler is on, and a copy of it under each column would have
    // promised a choice the server does not offer.
    const anyBusy = this.busy("shot") || this.busy("pre");
    this.cancel.style.display = anyBusy ? "" : "none";
    // The whole of what a view is, on the outside of everything it changes.
    this.root.classList.toggle("simple", this.view === "simple");
    this.root.classList.toggle("advanced", this.advanced);
    // Whether there is a picture column at all. The simple view opens it on the
    // press rather than on the first preview — `queued` is optimistic for exactly
    // this reason, and a column that arrived thirty seconds after the button
    // would read as something going wrong rather than as something starting.
    this.root.classList.toggle("working",
      this.busy(this.step) || this.dock.classList.contains("showing")
      || this.past[this.step].childElementCount > 0);
    for (const button of this.views.children) {
      button.setAttribute("aria-pressed", String(button.dataset.view === this.view));
    }
    for (const button of this.stepBar.children) {
      if (!button.dataset?.step) continue;   // the travelling ink, which is not a control
      button.setAttribute("aria-pressed", String(button.dataset.step === this.step));
    }
    this.paintInk();
    this.more.setAttribute("aria-pressed", String(this.advanced));
    const sampling = Object.values(this.runs).some((run) => run.state === "sampling");
    const left = Math.max(0, (this.remaining ?? 0) - (sampling ? 1 : 0));
    this.note.textContent = left > 0 ? t("{count} more in the queue", { count: left }) : "";
  }
}

/** Open the editor on `node`, replacing whatever it was showing. */
export function openFullscreen(node) {
  if (!node?.mmcBody) return;
  if (open?.node === node) return;
  close();
  open = new Fullscreen(node);
}

/** Rebuild the columns in place — a PreStage spawned or closed under the editor
 *  is a change to what it hosts, not a reason to tear the whole shell down and
 *  lose the scroll position of everything in it. */
export function remount(node) {
  if (!open || (node && open.node !== node)) return;
  open.mount();
  // The step switch is drawn from what mount() just found — whether there is a
  // pre-stage at all, and which half is in front — so a remount that skipped
  // this left the switch lit for a node that had just been spawned or deleted.
  open.paint();
}

/**
 * Put the card on the shot, because something the pre-stage made just landed on
 * it. The frame-grab and the result chips are the whole point of the pair — you
 * make the still to build the shot out of — so the moment one is handed over,
 * the step you want is the one that received it. A no-op unless the editor is
 * open on the simple view's pre-stage step.
 */
export function stepToShot() {
  open?.setStep("shot");
}

/**
 * Put the pre-stage in front of whoever is looking, and say whether anybody was.
 *
 * The other half of "send it to the pre-stage": a picture handed over that
 * lands somewhere nobody is looking has to be gone and found again. `false`
 * means this shell is closed or is open on some other node, and the caller
 * opens its own window instead — see `PreStageBody.reveal`.
 */
export function revealPreStage(nodeId) {
  if (!open) return false;
  // By id, because a body knows the id it was built for and not the node object
  // — and either half of the pair counts: the shell hosts the shot and reaches
  // its pre-stage through it, so a send from either lands in the same room.
  const ids = [open.node?.id, preStageOf(open.node)?.id];
  if (nodeId != null && !ids.some((id) => String(id) === String(nodeId))) return false;
  open.revealPreStage();
  return true;
}

export function close() {
  open?.unmount();
  open = null;
}

/** The command and the keybinding both land here. */
export function toggleFullscreen() {
  if (open) return close();
  const node = subject();
  if (node) openFullscreen(node);
}

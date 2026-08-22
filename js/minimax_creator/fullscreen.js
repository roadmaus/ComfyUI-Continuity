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
import { el, icon, mark } from "./dom.js";
import { elapsed } from "./stage.js";
import { t } from "./i18n.js";

/** Node classes whose body this editor can host. Kept here rather than imported
 *  from the entry point, because the entry point imports this. */
const PIECE = ["MiniMaxH3Creator", "MiniMaxH3Timeline"];
const PRESTAGE = "MiniMaxH3PreStage";

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
    this.stepDrop = el("button", {
      class: "mmc-fs-step-drop", title: t("Remove the pre-stage node"),
      onclick: (event) => { event.stopPropagation(); this.dropPreStage(); },
      text: "×",
    });
    this.stepBar = el("div", { class: "mmc-fs-stepbar" }, STEPS.map(([step, label]) =>
      el("button", {
        class: "mmc-fs-step", "data-step": step,
        title: step === "pre"
          ? t("The still this shot is built on — its prompt, its references, its checkpoint.")
          : t("The video: the prompt, the cast and everything the render reads."),
        onclick: () => this.setStep(step),
      }, [el("span", { text: t(label) }), ...(step === "pre" ? [this.stepDrop] : [])])));

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
    this.reel = el("div", { class: "mmc-fs-reel" }, [this.dock]);
    this.strip = el("div", { class: "mmc-fs-strip" }, [this.past.shot]);
    // The two control cards are one object: the desk. They are wrapped rather
    // than laid out beside the reel as three equals so that stretching them to
    // each other stretches them to *each other* — a flex line takes the height
    // of its container, and the body is the window. The wrapper is only as tall
    // as the taller card, so that is the height they both get. In the simple
    // view it is display:contents and this row does not exist at all.
    this.desk = el("div", { class: "mmc-fs-desk" }, [this.pre, this.col]);
    this.body = el("div", { class: "mmc-fs-body" }, [this.desk, this.reel]);

    this.root = el("div", { class: "mmc-fs" }, [
      el("div", { class: "mmc-fs-bar" }, [
        // The pack's own mark rather than a rail glyph: the bar is the one place
        // in the window that says whose room this is, and `timeline` is a control
        // icon that means "the strip" everywhere else it is drawn.
        el("span", { class: "mmc-fs-mark" }, [
          el("span", { class: "mmc-fs-logo" }, [mark(22)]),
          el("span", { text: "MiniMax H3" }),
        ]),
        el("span", { class: "mmc-fs-slash", text: "/" }),
        this.piece,
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
      this.body,
      this.strip,
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
    this.onKey = (event) => {
      if (event.key !== "Escape") return;
      close();
    };
    document.addEventListener("keydown", this.onKey);

    // The queue is global; the button reports it. `status` is how ComfyUI says
    // how much is left, and it fires on every change to the queue including the
    // one our own Render caused.
    this.onStatus = (event) => {
      const left = event.detail?.exec_info?.queue_remaining;
      if (typeof left !== "number") return;
      this.remaining = left;
      // Optimism spent: the server has the job, so the flag stops standing in
      // for it and the real state takes over.
      if (left === 0) for (const run of Object.values(this.runs)) run.queued = false;
      this.paint();
    };
    api.addEventListener("status", this.onStatus);

    this.setPlate(this.plateScale, { store: false });
    this.mount();
    document.body.appendChild(this.root);
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
    // The way out of the pair, and only where it cannot be pressed by accident:
    // on the step you are standing on, next to the name of the thing it removes.
    this.stepDrop.style.display = paired && this.step === "pre" ? "" : "none";

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
    this.col.replaceChildren(this.colHead, this.stepBar, body.root, this.runRow);
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
    // The lip is the front step's history, and the front step's alone.
    this.strip.replaceChildren(this.past[step]);
    // And the grip goes on whatever picture is now on the plate. It lives
    // inside the stage's own element because that element *is* the picture —
    // the dock around it is a centring box the size of the whole plate, and a
    // corner of that is a corner of the room rather than of the render.
    if (body.stage) body.stage.root.appendChild(this.sizer);
    // The empty frame is drawn from whatever the card is about to make — the
    // shot's canvas and length, or the still's canvas. The body says when it
    // has redrawn.
    body.onRender = () => this.paintFrame();
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
    this.piece.textContent = this.node.title || t("untitled piece");
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
    this.step = step;
    this.mount();
    this.paint();
  }

  /** Take the pre-stage back out of the graph. `mount` puts the card back on the
   *  shot on its own — there is nothing else left for it to show. */
  dropPreStage() {
    if (!preStageOf(this.node)) return;
    this.node.mmcBody?.preStage?.toggle();
  }

  /**
   * Switch views. `mount` again rather than rebuild: the simple view hosts one
   * body where the desk hosts two, so which nodes are borrowed changes — and
   * everything else about the switch is a class name, which is why the prompt
   * you were half-way through typing is still there afterwards.
   */
  setView(view) {
    if (!VIEWS.includes(view) || view === this.view) return;
    this.view = view;
    try { localStorage.setItem(VIEW_KEY, view); } catch { /* private mode; the session still switches */ }
    this.mount();
    this.paint();
  }

  /**
   * Move the finished picture into the reel when the next queue takes the stage.
   *
   * The stage is one box and it is cleared by `execution_start`, which is right
   * on a canvas — a card beside a node showing last week's render while this
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
        this.past[step].appendChild(this.take(this.shown[step]));
        this.shown[step] = null;
        // The newest is at the end of the lip, so that is where it stays.
        this.strip.scrollLeft = this.strip.scrollWidth;
      }
      return;
    }
    if (stage.state === "done" && stage.result) this.shown[step] = stage.result;
  }

  /** One finished render, as it sits on the lip. Deliberately not autoplaying:
   *  the live plate plays itself because it is the answer to what you just
   *  queued, and ten clips playing at once along a strip is not history, it is
   *  noise. The media fragment asks for a frame rather than a black rectangle. */
  take(result) {
    const media = result.isImage
      ? el("img", { class: "mmc-fs-take-media", src: result.url, alt: result.name })
      : el("video", {
          class: "mmc-fs-take-media", src: `${result.url}#t=0.1`,
          controls: true, loop: true, playsinline: true, preload: "metadata",
        });
    return el("div", { class: "mmc-fs-take", title: result.name }, [
      media,
      // What it cost, which is the one thing about a past take you cannot see by
      // looking at it — and the reason the clock on the plate is worth keeping
      // after the render lands. The filename moved to the tooltip: on a lip of
      // thumbnails it was a row of identical truncated stems.
      el("div", { class: "mmc-fs-take-note",
                  text: result.tookMs ? elapsed(result.tookMs) : "" }),
    ]);
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
    const editor = body?.editor;
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
    document.removeEventListener("keydown", this.onKey);
    api.removeEventListener("status", this.onStatus);
    this.release(this.node);
    this.release(this.hosted);
    this.release(this.front);
    this.hosted = null;
    this.front = null;
    this.root.remove();
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
    // `queueNodeIds` is ComfyUI's own partial execution; a frontend too old to
    // know the option ignores it and runs the graph, which is where this started.
    const target = kind === "pre" ? preStageOf(this.node) : this.node;
    app.queuePrompt(0, 1, { queueNodeIds: [String(target?.id ?? this.node.id)] })
      .catch(() => {
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
      icon(busy ? "clock" : "play", 16),
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
      button.setAttribute("aria-pressed", String(button.dataset.step === this.step));
    }
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

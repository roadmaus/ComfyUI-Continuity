// The stage: the picture, and nothing at all when there is no picture.
//
// The node makes video and used to show none of it. Everything about a
// generation was legible except the generation — the live preview was latent2rgb
// mush on a KSampler nobody could see, and the finished clip only existed if you
// wired a save node to it yourself.
//
// It behaves like every other preview in ComfyUI, which is the point: **absent
// until there is something to show, and then as large as the node will allow.**
// A box reserving space for a render nobody has asked for is a box permanently
// full of nothing, so the element is display:none while idle and the owner is
// told when that changes. The owner is a Satellite (satellite.js): a card that
// floats at the node's right edge, so the picture arrives beside the controls
// rather than displacing them.
//
// Running previews keep their light overlay. A finished video's actions and
// clocks sit below the media, leaving the browser's native transport untouched.
//
// **Everything here keys off the node's own id**, because a render is a subgraph
// and nothing in it is on the canvas:
//
// - `progress_state` carries `parent_node_id`, which is exactly our id for every
//   node the expansion emitted. That is how the step readout finds the sampler.
// - core's `b_preview_with_metadata` carries the same field.
// - KJNodes' `kj_preview_override` carries only the emitting node's raw id,
//   which is ours plus a `GraphBuilder` prefix — so that one is a prefix match.
//   Its own frontend looks for a canvas node with that id, finds none, and does
//   nothing, so listening in on it costs that pack nothing. **That id is not
//   always this run's**, though — see `executing` below for why, and for the
//   second way a frame is known to be ours.
// - `executing` and `executed` carry `display_node`, which core sets to the
//   parent of every node in an expansion — our id — and which
//   `render.emit_tail` has stamped on the save node besides.

import { api } from "../../../scripts/api.js";
import { el } from "./dom.js";
import { outputUrl, uiSetting } from "./api.js";
import { openLoupe } from "./loupe.js";
import { submission } from "./queue.js";
import { t } from "./i18n.js";
import { ExecutionTiming } from "./timing.js";

/** Every event this listens to. `b_preview` is the metadata-less legacy frame:
 *  it names no node, so it is only trusted while `progress_state` already says
 *  one of ours is the thing sampling — see the handler. `mmc_segment` is our
 *  own: the timeline's segment node announcing which segment the queue has
 *  reached, the moment it starts encoding. `mmc_refused` is ours too: the
 *  server turned a prompt away before it was queued (queue.js), which is the
 *  one failure the socket never carries. */
const EVENTS = ["progress_state", "b_preview_with_metadata", "b_preview",
                "kj_preview_override", "executing", "executed", "execution_error",
                "execution_start", "execution_success", "execution_interrupted", "mmc_segment", "mmc_refused",
                "reconnected", "status"];

/** A progress report this long is a sampler; the loaders and decoders report a
 *  step or two each. What lets the stage open on progress rather than waiting
 *  for a first frame, without opening as an empty black box for as long as a
 *  checkpoint takes to read off disk. */
const OPENS_ON_STEPS = 4;

/** How long a render may go without saying anything before the stage stops
 *  trusting the wire and starts asking the server directly, and how often it
 *  asks once it has started. A slow step is silence too, so the first number is
 *  long enough that an ordinary one never trips it; the ask is a small GET and
 *  only ever happens while nothing else is arriving. */
const QUIET_MS = 30000;
const PROBE_EVERY_MS = 5000;

/** ...and how long before the readout says so. Until then a quiet render is
 *  just a quiet render; past it, a clock ticking under a frozen preview is
 *  indistinguishable from a hang unless the stage admits it has lost contact. */
const STALL_MS = 60000;

/** The step preview's `src` is an object URL revoked the instant the next frame
 *  lands (or a base64 `data:` URL just as long-lived), so every action the
 *  browser's picture menu offers — open in a new tab, save as, copy address —
 *  aims at a URL that has already stopped existing by the time it is used. On
 *  ComfyUI Desktop that is not merely a broken link: opening a live preview
 *  frame in a new window takes the whole app down (#30). The menu is suppressed
 *  on the transient frame only; the finished render below keeps its own, where
 *  the `src` is a real `/view` URL and "save image as" does what it says. */
const noMenu = (event) => event.preventDefault();

/**
 * Double-click the finished picture to open it in the loupe.
 *
 * The stage is as large as the room it is in and no larger — a card beside a
 * node, a plate in the shell — and neither is the size a 4K render was made to
 * be looked at.
 *
 * This used to be `requestFullscreen` on the picture element, which was the
 * cheap answer: the whole display rather than the whole window, Escape already
 * meaning what everyone expects. What it cost was everything a render is
 * actually looked at *for*. Firefox lays its own banner over the top of the
 * screen every time; the picture is fitted to the display and cannot be
 * magnified into; and there is nowhere to put the comparison — which for a
 * render made with the neural refiner on is the whole question. `loupe.js` is
 * the room that answers those, and it is this pack's, so it can carry them.
 *
 * On the finished render only. The step preview is an object URL that the next
 * frame revokes, so a viewer pointed at it would go blank a second later — the
 * same reason that one has no context menu.
 */

/**
 * A finished render as a file anyone can open: `{path, kind}`, or null.
 *
 * The shape every room in this pack takes a source in — the benches, the picker,
 * the loupe — assembled from what the save node reported. Exported because four
 * surfaces were each doing these three lines from their own copy of a result,
 * and the annotation ("name.png [output]") is the kind of detail that is right
 * in three of four places for a while.
 */
export function stageSource(result) {
  const saved = result?.saved;
  if (!saved?.filename) return null;
  const folder = saved.subfolder ? `${saved.subfolder}/` : "";
  return {
    path: `${folder}${saved.filename} [${saved.type || "output"}]`,
    kind: result.isImage ? "image" : "video",
  };
}

export class Stage {
  /**
   * @param {object} spec
   * @param {() => string|number} spec.nodeId  read late: a node pasted from the
   *   clipboard is renumbered after it is built
   * @param {(showing: boolean) => void} [spec.onVisibility]  fired when the
   *   stage appears or disappears — assigned by the Satellite that hosts it,
   *   which shows and hides the floating card off this signal
   */
  /**
   * @param {(state: string, progress: object|null) => void} [spec.onState]
   *   fired on every render with the run's state and step count. `onVisibility`
   *   above answers "is there a picture"; this answers "is it still going",
   *   which is a different question the moment somebody has to draw a Cancel
   *   button — the fullscreen editor's, since ComfyUI's own is behind it.
   */
  /**
   * @param {(saved: object) => HTMLElement[]} [spec.resultChips]  extra chips
   *   for the finished-render overlay, built by the owner from the `executed`
   *   payload — the PreStage's "start frame / end frame / reference" hand-off.
   */
  /**
   * @param {(index: number) => string} [spec.segmentLabel]  how to say which
   *   segment is being rendered — the Timeline passes one that knows the strip
   *   ("Segment 2 of 5"); without it the announce's index shows bare.
   */
  constructor({ nodeId, onVisibility, onState, onGallery, resultChips, segmentLabel,
                onTakes = null, onRestyle = null }) {
    this.nodeId = nodeId;
    this.onVisibility = onVisibility;
    this.onState = onState;
    this.onGallery = onGallery;
    this.onRestyle = onRestyle;
    this.resultChips = resultChips;
    this.segmentLabel = segmentLabel;
    // What each pass of this render wrote, for the body that owns a strip to
    // hand back to the cards that made them. The stage itself has no use for
    // it — it shows one finished piece — but the executed message is where the
    // files are named and there is one of those, not one per node.
    this.onTakes = onTakes;
    this.state = "idle";
    this.segment = null;     // 1-based index of the segment now rendering
    this.progress = null;    // {step, total}
    this.frame = null;       // object URL or data URI of the newest preview
    this.result = null;      // {url, name} of the finished video
    // Why there is no picture: `{started, items: [{where, what}]}`. `started`
    // says whether the run got as far as the sampler — a refusal never does —
    // and each item is one thing that went wrong, said as where and what.
    this.failure = null;
    // The same items for a press refused *while* this stage is sampling —
    // said in the readout rather than over the live picture. See `mmc_refused`.
    this.refused = null;
    this.startedAt = null;
    this.renderPromptId = null;
    this.timing = new ExecutionTiming();
    this.probes = new Set();
    this.probeAgain = new Set();
    this.probeTimes = new Map();
    this.destroyed = false;
    // Which queued prompt the stage believes it is watching, and when it last
    // heard anything about it. Between them they are the whole of the recovery
    // path in `probe()`: the id says what to ask the server about, and the
    // silence says when to start asking.
    this.promptId = null;
    // Whether the running prompt has been seen executing one of our nodes —
    // the ground under `kj_preview_override`, whose own id cannot be trusted.
    this.claimed = false;
    this.lastNewsAt = 0;
    this.probedAt = 0;
    this.probing = false;
    // How long the finished render took, in ms. Held past the run because the
    // clock is the one reading the readout keeps after the picture lands: the
    // whole reason you watch it tick is to know what the next one will cost.
    this.tookMs = null;

    this.media = el("div", { class: "mmc-stage-media" });
    this.rule = el("div", { class: "mmc-stage-rule" });
    this.readout = el("div", { class: "mmc-stage-readout" });
    this.root = el("div", { class: "mmc-stage" }, [this.media, this.rule, this.readout]);
    this.stopFooterSize = watchFooterSize(this.root, this.readout);

    this.onEvent = (event) => this.handle(event.type, event.detail);
    for (const name of EVENTS) api.addEventListener(name, this.onEvent);

    this.render();
  }

  /** Called when the node body is torn down. Listeners on `api` outlive the DOM
   *  otherwise, and a deleted node would go on decoding previews forever. */
  destroy() {
    this.destroyed = true;
    this.stopFooterSize();
    for (const name of EVENTS) api.removeEventListener(name, this.onEvent);
    this.releaseFrame();
    clearInterval(this.ticker);
  }

  /**
   * Tell the card what shape the picture in it is.
   *
   * A box that hugs a contained image is not something CSS can work out on its
   * own: the shrink-to-fit width of a parent comes from the image's *intrinsic*
   * width, which ignores any cap on its height — so a portrait render in a
   * height-limited card sat in the middle of a box as wide as the file, with
   * black down both sides. On a satellite that never showed, because there the
   * card's height is the node's and width is the only free axis. Docked in the
   * fullscreen editor, where both axes are bounded, it was the whole shape of
   * the thing.
   *
   * So the one fact CSS cannot derive is measured off the media and handed over,
   * and `aspect-ratio` does the rest. Called from the media's own load, because
   * that is the first moment either size is known.
   *
   * **Twice, in two forms, because the ratio and the number are not the same
   * thing to CSS.** `aspect-ratio` takes `w / h`, which cannot be multiplied by
   * anything; the docked card has to work out which of its two bounds it hits
   * first and that is arithmetic, so it gets the number as well. `data-sized`
   * says the measurement has happened at all — the card has no shape to hug
   * before a picture lands, and a failed render never gets one.
   */
  setAspect(width, height) {
    if (!width || !height) return;
    this.root.style.setProperty("--mmc-media-ar", `${width} / ${height}`);
    this.root.style.setProperty("--mmc-media-arn", `${width / height}`);
    this.root.dataset.sized = "1";
  }

  clearAspect() {
    this.root.style.removeProperty("--mmc-media-ar");
    this.root.style.removeProperty("--mmc-media-arn");
    delete this.root.dataset.sized;
  }

  releaseFrame() {
    if (this.frameUrl) URL.revokeObjectURL(this.frameUrl);
    this.frameUrl = null;
  }

  /** Is `id` this node, or something the expansion emitted from it? */
  ours(id) {
    if (id === null || id === undefined) return false;
    const mine = String(this.nodeId());
    const other = String(id);
    return other === mine || other.startsWith(`${mine}.`);
  }

  /** Whether there is anything worth taking up room for. */
  showing() {
    return this.state !== "idle";
  }

  // ---- the wire ------------------------------------------------------------

  handle(type, detail) {
    // Core's frontend emits a bare null for the queue's final `executing`,
    // after history has been filed. Reconnection also need not have a payload.
    if (type === "reconnected" || (type === "executing" && detail === null)) {
      this.recoverTimings(true);
      return;
    }
    if (!detail) return;
    switch (type) {
      case "execution_start":
        // A new queue — and not necessarily *this* stage's queue. Every stage on
        // the page hears every prompt, and a piece is routinely two of them: the
        // shot and the pre-stage that feeds it. Clearing here cleared the shot's
        // finished render the moment you stepped over to the pre-stage and made
        // a still, and cleared it past recovery — the fullscreen lip is handed
        // the picture by the run that *starts*, and no run ever started for the
        // shot, so the take was not retired to the shelf either. It was simply
        // gone.
        //
        // So the clearing moved to `begin`, which is the first word that the
        // run is ours. Until then the last render stays up, which is what the
        // reader wants anyway while a checkpoint is being read off disk.
        //
        // Kept even though this stage may turn out to have no part in the run:
        // it is the only place the prompt id is ever said, and by the time the
        // stage knows the render is its own the message has long gone by.
        this.promptId = detail.prompt_id == null ? null : String(detail.prompt_id);
        this.timing.start(this.promptId, detail.timestamp);
        this.claimed = false;
        this.lastNewsAt = Date.now();
        break;

      case "executing":
        // The executor stepping into a node of the running prompt, which it
        // names by its display node: for anything in an expansion, the node
        // that expanded it. Nothing opens on this — the loaders execute long
        // before the sampler does, and a box that opened on them is the empty
        // box `OPENS_ON_STEPS` exists to avoid — but from here on the run is
        // known to be ours, whatever the previewer calls itself.
        //
        // Unlike `executed`, the frontend does not pass the message through:
        // it dispatches `display_node || node` alone, a bare id string. Read
        // as an object it named nobody, the claim never happened, and a
        // pre-stage after a chat render sat blank until the cache let go.
        if (String(detail) !== String(this.nodeId())) break;
        this.claimed = true;
        this.news();
        break;

      case "status":
        // Some frontends announce a reattached socket only by sending the queue
        // state down it. A `status` arriving in the middle of a long silence is
        // that, near enough, and costs one small GET to act on.
        if (this.quiet() > QUIET_MS) this.recoverTimings();
        break;

      case "execution_success":
        this.endTiming(type, detail);
        break;

      case "progress_state": {
        // Every node the expansion emitted reports `parent_node_id` = our id.
        // The one with the most steps is the sampler; the loaders and decoders
        // report a step or two each and would otherwise win the race.
        let best = null;
        for (const entry of Object.values(detail.nodes ?? {})) {
          if (!this.ours(entry.parent_node_id) && !this.ours(entry.node_id)) continue;
          if (entry.state !== "running") continue;
          if (!best || (entry.max ?? 0) > (best.max ?? 0)) best = entry;
        }
        if (!best) break;
        if (!this.acceptPrompt(detail.prompt_id ?? best.prompt_id)) break;
        this.news();
        // The stage opens the moment something with real steps is running —
        // not on the loaders (their one-step reports stay below the
        // threshold), and not waiting for a first preview frame either, which
        // may simply never arrive (preview method off, or a frontend that
        // stopped carrying metadata on the frames).
        // Against the run rather than against the picture: with the last
        // render left up until this one is known to be ours (see
        // `execution_start`), "there is something in the box" no longer means
        // "a render is under way", and a stage that asked the box would never
        // start the clock on the second take at all.
        if (this.state !== "sampling" || this.renderPromptId !== this.promptId) {
          if ((best.max ?? 0) < OPENS_ON_STEPS) break;
          this.begin();
          this.render();
        }
        this.progress = { step: best.value ?? 0, total: best.max ?? 0 };
        this.renderReadout();
        break;
      }

      case "b_preview_with_metadata":
        // Core's own previewer — latent2rgb unless somebody pointed the H3
        // latent format at a decoder, which nothing does. This is the fallback
        // when KJNodes is not installed, and it beats an empty box.
        if (!this.ours(detail.parentNodeId) && !this.ours(detail.nodeId)) break;
        if (!this.acceptPrompt(detail.promptId ?? detail.prompt_id)) break;
        this.news();
        this.metaFrameAt = Date.now();
        this.begin();
        this.releaseFrame();
        this.frameUrl = URL.createObjectURL(detail.blob);
        this.frame = this.frameUrl;
        this.frameIsClip = false;
        this.render();
        break;

      case "b_preview": {
        // The legacy frame: a bare blob, naming no node. Only trusted while
        // this stage is already sampling — the queue runs one thing at a time,
        // so while ours is the sampler every frame on the wire is ours. Stands
        // down whenever the metadata variant is flowing, which carries the
        // same picture with a name on it.
        if (this.state !== "sampling") break;
        if (this.renderPromptId !== this.promptId) break;
        if (this.metaFrameAt && Date.now() - this.metaFrameAt < 2000) break;
        const blob = detail instanceof Blob ? detail : detail.blob;
        if (!blob) break;
        this.news();
        this.releaseFrame();
        this.frameUrl = URL.createObjectURL(blob);
        this.frame = this.frameUrl;
        this.frameIsClip = false;
        this.render();
        break;
      }

      case "kj_preview_override": {
        // Ours by the id on the frame — or by the run, because the id is
        // whichever node first built this previewer, not the one sampling now.
        // ComfyUI caches a node's output by its inputs, and means to add the
        // node's own id to that key for a node that reads `UNIQUE_ID`; for a
        // V3 node it never does, because `_io.py` files the hidden inputs as
        // one-tuples and `caching.py` looks for the bare string. So the same
        // weights previewed under the chat's id go on answering under it
        // when the pre-stage samples them next, and the other way round, and
        // a stage that trusted the id alone showed nothing until the file
        // landed.
        if (!this.ours(detail.node_id) && !this.claimed) break;
        if (!this.acceptPrompt(detail.prompt_id)) break;
        this.news();
        // The boundary-0 message carries the sigma schedule and often no picture
        // at all. Take the step count from it, but do not open the stage on it —
        // see above. Written after `begin`, whose clearing of the last render
        // would take the count with it on the frame that opens the box.
        const progress = Number.isFinite(detail.total)
          ? { step: detail.step ?? 0, total: detail.total } : null;
        if (!detail.image) {
          if (progress) this.progress = progress;
          break;
        }
        this.begin();
        if (progress) this.progress = progress;
        this.releaseFrame();
        this.frame = `data:${detail.mime || "image/jpeg"};base64,${detail.image}`;
        // With NVENC available the pack encodes the step clip as video/mp4,
        // which an <img> renders as a black box. webp — animated or not — and
        // jpeg are images either way.
        this.frameIsClip = (detail.mime || "").startsWith("video/");
        this.render();
        break;
      }

      case "executed":
        // `render.emit_tail` stamped our id on the save node, so this is our
        // render coming back even though the node that made it is not on the
        // canvas.
        if (String(detail.display_node) !== String(this.nodeId())) break;
        if (!this.acceptPrompt(detail.prompt_id, { completed: true })) break;
        this.finish(detail.output, { promptId: detail.prompt_id ?? this.promptId });
        break;

      case "mmc_segment":
        // The segment node announcing itself as it starts to encode — the one
        // signal that says *whose* steps the sampler's are about to be. Held
        // until the next announce: the sampler, the decoders and any refine
        // pass that follow all belong to the same segment.
        if (!this.ours(detail.node)) break;
        this.news();
        this.segment = detail.index ?? null;
        this.renderReadout();
        break;

      case "execution_interrupted":
        this.endTiming(type, detail);
        // Cancelled. There is no `executed` and no `execution_error` coming, so
        // without this the stage sat on "sampling" forever — and everything that
        // reads `onState` sat with it: the fullscreen editor's Render button
        // stayed a readout of a run that had already stopped, with no way back
        // to a button short of closing the editor.
        //
        // The error's node can be anywhere in the expansion; its prompt id,
        // unlike that node id, reliably identifies the run being interrupted.
        if (this.state !== "sampling") break;
        if (!this.sameRender(detail.prompt_id)) break;
        // Back to nothing, rather than leaving the last preview frame up: it is
        // a step of a video that was never finished, and a stage still showing
        // it reads as a render that landed.
        this.reset();
        break;

      case "execution_error": {
        this.endTiming(type, detail);
        if (detail.prompt_id && this.promptId && String(detail.prompt_id) !== String(this.promptId)) break;
        // A later node can fail after our save succeeded. Keep that valid file
        // and finalize its total without replacing it with a failure slate.
        if (this.state === "done" && this.result?.promptId === String(detail.prompt_id)) break;
        // Ours if the node that raised is in our expansion — or if the press
        // that queued this prompt was ours and the node that raised is a
        // loader wired in upstream: the failure is still the answer to that
        // press, and a stage that only listened for its own id sat idle while
        // ComfyUI marked a node behind the fullscreen shell.
        const sent = submission(detail.prompt_id);
        if (!this.ours(detail.node_id) && !this.claims(sent)) break;
        const title = sent?.titles?.[String(detail.node_id)];
        this.fail([{
          where: this.ours(detail.node_id) ? null : title ?? detail.node_type ?? null,
          what: detail.exception_message || t("the render failed"),
        }], { started: true });
        break;
      }

      case "mmc_refused":
        // Never queued, so nothing else is coming: this is the whole story of
        // the press. Ours if a refused node is ours, or the press named us, or
        // — a plain queue naming nobody — we were in the graph it sent.
        if (!detail.items?.some((item) => this.ours(item.nodeId))
            && !this.claims(detail)) break;
        // A second press, refused while the first is still on the sampler:
        // the picture in the box is a render that is happening, and a slate
        // over it would say the opposite. The refusal rides the readout
        // instead, the way a stall does, for the rest of the run.
        if (this.state === "sampling") {
          this.refused = detail.items;
          this.renderReadout();
          break;
        }
        this.fail(detail.items, { started: false });
        break;
    }
  }

  /** Whether a submission — `{targets, nodes|titles}` — was this node's press:
   *  named as a target, or in a graph queued whole. */
  claims(sent) {
    if (!sent) return false;
    if (sent.targets?.length) return sent.targets.some((id) => this.ours(id));
    const ids = sent.nodes ?? Object.keys(sent.titles ?? {});
    return ids.some((id) => this.ours(id));
  }

  /** Frames without ids belong to the active queue. Named late messages from
   *  a previous queue must not start a fresh clock or overwrite its successor. */
  acceptPrompt(promptId, { completed = false } = {}) {
    const id = promptId == null ? this.promptId : String(promptId);
    const known = id == null ? null : this.timing.runs.get(id);
    if (!completed && known?.terminal) return false;
    if (id && this.promptId && id !== this.promptId && known) return false;
    // A stage mounted/reconnected after execution_start can learn the current
    // prompt from progress. Its missing start time stays unknown until history.
    if (id) this.promptId = id;
    this.timing.get(id);
    return true;
  }

  sameRender(promptId) {
    return promptId == null ? this.renderPromptId === this.promptId
      : String(promptId) === this.renderPromptId;
  }

  endTiming(type, detail) {
    const id = detail.prompt_id == null ? this.promptId : String(detail.prompt_id);
    this.timing.stop(id, type, detail.timestamp);
    this.renderReadout();
    this.syncTicker();
    const run = id == null ? null : this.timing.runs.get(id);
    if (run?.results.size || this.awaitingResult(id)) this.probe(id, true);
  }

  awaitingResult(promptId) {
    if (this.state === "sampling") return this.sameRender(promptId);
    // A cached result has no sampler/begin at all. An observed own executing
    // node is enough to recover its missed save, without claiming other queues.
    return this.state !== "failed" && this.claimed && this.promptId === promptId
      && this.result?.promptId !== promptId;
  }

  /** The two clocks describe the shown result, never another stage's queue. */
  clockTiming() {
    if (this.state === "done" && this.result) {
      const { totalMs = null, tookMs = null, totalPending = false } = this.result;
      return { totalMs, tookMs, totalPending };
    }
    if (this.state !== "sampling" && this.state !== "failed") {
      return { totalMs: null, tookMs: null, totalPending: false };
    }
    const run = this.renderPromptId == null ? null : this.timing.runs.get(this.renderPromptId);
    return { ...this.timing.read(run), tookMs: this.state === "sampling" && this.startedAt !== null
      ? Math.max(0, Date.now() - this.startedAt) : this.tookMs };
  }

  syncTicker() {
    const needed = this.state === "sampling" || this.timing.pendingResults().length;
    if (needed && !this.ticker && !this.destroyed) this.ticker = setInterval(() => this.tick(), 1000);
    if (!needed) { clearInterval(this.ticker); this.ticker = null; }
  }

  recoverTimings(force = false) {
    const ids = new Set(this.timing.pendingResults().map((run) => run.promptId));
    if (this.state === "sampling" && this.renderPromptId) ids.add(this.renderPromptId);
    if (this.promptId && this.awaitingResult(this.promptId)) ids.add(this.promptId);
    // execution_success is sent just before history is filed. `executing:null`
    // gives a missed-start total a second chance after that small race.
    if (this.result?.promptId && this.result.totalMs === null
        && !this.timing.runs.get(this.result.promptId)?.history) ids.add(this.result.promptId);
    for (const id of ids) this.probe(id, force);
  }

  /**
   * The run is over and there is no picture. The slate replaces whatever the
   * box held — a previous take left up under a failure reads as the failure's
   * result, and the take is on the lip and in the gallery anyway.
   *
   * @param {{where: string|null, what: string}[]} items  one per thing wrong
   * @param {{started: boolean}} spec  whether the queue ran the prompt at all
   *   — a refusal is the one case it did not. The clock is kept only if the
   *   sampler was reached: a loader that raised has no time worth reading.
   */
  fail(items, { started, promptId = this.promptId, recovered = false }) {
    const observedRender = started && !recovered && this.state === "sampling" && this.sameRender(promptId);
    const tookMs = observedRender && this.startedAt !== null ? Math.max(0, Date.now() - this.startedAt) : null;
    const renderPromptId = started ? promptId : null;
    this.clearRender();
    this.state = "failed";
    this.tookMs = tookMs;
    this.renderPromptId = renderPromptId;
    this.syncTicker();
    this.failure = { started, items: items.filter((item) => item?.what) };
    if (!this.failure.items.length) this.failure.items.push({ where: null, what: t("the render failed") });
    this.render();
  }

  /** Everything the last render left in the box — the picture, the clock, what
   *  went wrong. Not the run's bookkeeping: `reset` adds that, and `begin` keeps
   *  it, because a run that is starting is the one asking. */
  clearRender() {
    this.metaFrameAt = 0;
    this.result = null;
    this.failure = null;
    this.refused = null;
    this.tookMs = null;
    this.startedAt = null;
    this.renderPromptId = null;
    this.progress = null;
    this.segment = null;
    this.releaseFrame();
    this.frame = null;
    this.frameIsClip = false;
    this.clearAspect();
  }

  reset() {
    this.promptId = null;
    this.claimed = false;
    this.lastNewsAt = 0;
    this.probedAt = 0;
    this.state = "idle";
    this.clearRender();
    this.syncTicker();
    this.render();
  }

  /** First frame of a queue. Starts the clock once rather than on every step, so
   *  the elapsed readout is elapsed and not a stutter. */
  begin() {
    if (this.state === "sampling" && this.renderPromptId === this.promptId) return;
    // The first word that this queue is ours, and so the moment the last one's
    // picture stops being the answer — see `execution_start`.
    this.clearRender();
    this.state = "sampling";
    this.renderPromptId = this.promptId;
    this.timing.get(this.renderPromptId);
    this.probedAt = 0;
    this.startedAt = Date.now();
    this.lastNewsAt = Date.now();
    // Only the readout, and only once a second: the frames arrive when they
    // arrive, and a full render on a timer would fight the preview for the box.
    this.syncTicker();
  }

  // ---- the render lands, however it reaches us -----------------------------

  /**
   * A finished render, from the `executed` message or from the history the
   * server kept of it — the two are the same payload and this is the one place
   * that reads it.
   *
   * Under our own keys, not "images": that is the key core's stock widgets
   * watch, and they were rendering a second player on the canvas node right
   * under this stage. `MiniMaxH3Save` reports `mmc_video` and
   * `MiniMaxH3SaveImage` reports `mmc_image` instead; which one arrives is also
   * what says whether the result is a clip or a still.
   */
  finish(output, { promptId = this.promptId, prompt = null, recovered = false } = {}) {
    // The passes, each as its own file, so a card whose pass came out right
    // never has to be sampled again. Before the `saved` gate: most takes now
    // arrive one at a time from `ContinuityTake` while the render is still
    // running — an executed message with a take and no piece in it — and the
    // rest still ride the save node's report the way they always did.
    if (output?.mmc_takes?.length) this.onTakes?.(output.mmc_takes, { promptId, prompt });
    const saved = output?.mmc_video?.[0] ?? output?.mmc_image?.[0];
    if (!saved) return;
    promptId = promptId == null ? null : String(promptId);
    // Duplicate delivery is not another render window, nor a reason to restart
    // playback. History may still improve the total on this same result object.
    if (promptId && this.result?.promptId === promptId && this.result.url === outputUrl(saved)) {
      this.timing.refreshAll();
      this.renderReadout();
      return;
    }
    const observedSave = !recovered && this.state === "sampling" && this.sameRender(promptId);
    const tookMs = observedSave && this.startedAt !== null ? Math.max(0, Date.now() - this.startedAt) : null;
    this.state = "done";
    this.progress = null;
    // The clock stops here rather than on the next tick, so what the readout
    // shows after the render is the render's own length and not a second of
    // whatever happened to follow it.
    this.tookMs = tookMs;
    this.renderPromptId = promptId;
    this.result = { url: outputUrl(saved), name: saved.filename,
                    isImage: !output?.mmc_video, saved,
                    // Carried on the result as well as held here: the
                    // fullscreen reel keeps finished renders past the run
                    // that made them, and a take without its cost is a
                    // picture you can only compare on looks.
                    tookMs: this.tookMs, promptId };
    this.timing.attach(promptId, this.result);
    // The finished clip takes the preview's place, so the last sampled frame is
    // now a picture that can never be shown again — and the clock it was
    // ticking under has stopped.
    this.syncTicker();
    this.releaseFrame();
    this.frame = null;
    this.render();
  }

  /** A step, a frame, a segment — something said this render is still alive. */
  news() {
    const wasStalled = this.quiet() > STALL_MS;
    this.lastNewsAt = Date.now();
    if (wasStalled) this.renderReadout();
  }

  /** How long since anything was heard about the render now on the stage. */
  quiet() {
    return this.lastNewsAt ? Date.now() - this.lastNewsAt : 0;
  }

  /** One second of a running render: the clock, and — once the wire has gone
   *  quiet for longer than a slow step explains — a question to the server. */
  tick() {
    this.timing.refreshAll();
    this.renderReadout();
    if (this.quiet() > QUIET_MS) this.recoverTimings();
  }

  /**
   * Ask the server what became of this render.
   *
   * **`executed` is sent once, to whoever is listening, and is never replayed.**
   * So a socket that drops mid-render takes the end of the render with it: the
   * file is written and the queue empties, while the stage sits on a step
   * preview under a clock that never stops, looking exactly like a hang
   * ([#24](https://github.com/roadmaus/ComfyUI-Continuity/issues/24)). It does
   * not take an exotic failure to get there — a reverse proxy with a frame cap,
   * a laptop that slept, a tab reopened on a render already running.
   *
   * `/history/{prompt_id}` holds the same payload the message carried, so the
   * recovery is to read it back rather than to guess from a timeout. A missing
   * entry normally means the render is still running, but can also mean its
   * history is unavailable. Neither proves a completion time; a slow step is
   * silence too, so that case only lets the readout say it has lost contact.
   */
  async probe(promptId = this.renderPromptId ?? this.promptId, force = false) {
    if (this.destroyed || !promptId) return;
    if (this.probes.has(promptId)) {
      if (force) this.probeAgain.add(promptId);
      return;
    }
    const current = promptId === (this.renderPromptId ?? this.promptId);
    const probedAt = current ? this.probedAt : this.probeTimes.get(promptId);
    if (!force && probedAt && Date.now() - probedAt < PROBE_EVERY_MS) return;
    this.probes.add(promptId);
    this.probing = true;
    this.probeTimes.set(promptId, Date.now());
    if (current) this.probedAt = Date.now();
    try {
      const response = await api.fetchApi(`/history/${encodeURIComponent(promptId)}`);
      if (!response.ok) return;
      const entry = (await response.json())?.[promptId];
      if (this.destroyed || !entry) return;
      this.timing.fromHistory(promptId, entry);
      this.syncTicker();
      this.renderReadout();
      // The stage may have caught up on its own while this was in flight — the
      // wire coming back mid-probe is the likeliest moment of all — and a probe
      // must never overwrite a result that arrived the ordinary way.
      if (this.promptId !== promptId || !this.awaitingResult(promptId)) return;
      // The takes first, wherever the entry holds them: `ContinuityTake`
      // reports them one node at a time, so they are scattered across the
      // entry's outputs rather than riding the save node's. The failed render
      // is the case this exists for — the passes that landed before the
      // failure are exactly the ones worth keeping.
      const takes = this.takesOf(entry.outputs, entry.meta);
      if (takes.length) this.onTakes?.(takes, { promptId, prompt: entry.prompt });
      const output = this.savedOutput(entry.outputs, entry.meta);
      if (output) {
        // History has workflow boundaries, not the time our save node emitted
        // its file. Counting through a disconnected tab would invent a render
        // duration, so only the total is recovered from that authoritative log.
        this.finish(output, { promptId, prompt: entry.prompt, recovered: true });
        return;
      }
      // In history, with nothing of ours in it: the render failed or was
      // cancelled while nobody was listening. Saying so is the point — this is
      // the state the report describes as costing a 179-second render, because
      // a stage that cannot tell "running" from "over" gets cancelled by hand.
      this.fail([{ where: null,
                   what: failureText(entry.status) ?? t("the render ended without a file") }],
                { started: true, promptId, recovered: true });
    } catch { /* the wire is down as well; the ticker asks again in five seconds */ }
    finally {
      this.probes.delete(promptId);
      this.probing = this.probes.size > 0;
      if (this.probeAgain.delete(promptId) && !this.destroyed) this.probe(promptId, true);
    }
  }

  /**
   * The `mmc_video`/`mmc_image` output belonging to this node in a history
   * entry, or null.
   *
   * History keys outputs by the node that *made* them, which inside our
   * expansion is our id with a suffix, and records the id it was displayed
   * under in `meta` — `render.emit_tail`'s stamp, and the same id the
   * `executed` message carries. Either identifies it.
   *
   * **And if neither does, one unambiguous render still counts.** The keys are
   * this pack's own, so an `mmc_` output in a prompt this stage was sampling in
   * is this stage's render — the queue runs one prompt at a time. Only where
   * there is exactly one, though: a prompt holding two of our nodes is a
   * question this cannot answer, and guessing there would hand a stage somebody
   * else's file. The alternative to this fallback is worse than a miss — the
   * caller reads "no output of ours" as a render that wrote nothing, so an id
   * shape this does not recognise would report a finished render as failed.
   */
  /** Every take of ours in a history entry's outputs, in one list. */
  takesOf(outputs = {}, meta = {}) {
    const takes = [];
    for (const [id, output] of Object.entries(outputs ?? {})) {
      if (!output?.mmc_takes?.length) continue;
      if (this.ours(id) || this.ours(meta?.[id]?.display_node)) {
        takes.push(...output.mmc_takes);
      }
    }
    return takes;
  }

  savedOutput(outputs = {}, meta = {}) {
    const mine = [];
    const anyOfOurs = [];
    for (const [id, output] of Object.entries(outputs ?? {})) {
      if (!output?.mmc_video?.[0] && !output?.mmc_image?.[0]) continue;
      anyOfOurs.push(output);
      if (this.ours(id) || this.ours(meta?.[id]?.display_node)) mine.push(output);
    }
    if (mine.length) return mine[0];
    return anyOfOurs.length === 1 ? anyOfOurs[0] : null;
  }

  // ---- render --------------------------------------------------------------

  render() {
    const showing = this.showing();
    this.root.style.display = showing ? "flex" : "none";
    this.root.dataset.state = this.state;
    if (this.state === "done" && this.result) this.root.dataset.media = this.result.isImage ? "image" : "video";
    else delete this.root.dataset.media;
    // Told rather than inferred: the owner has to give up the height the prompt
    // box was growing into, and it cannot know to do that from a re-render it
    // did not trigger.
    this.onVisibility?.(showing);
    // Before the early return: a run that has finished or failed is exactly
    // when the stage stops showing, and that is the transition a Cancel
    // button most needs to hear.
    this.onState?.(this.state, this.progress);
    if (!showing) return;

    if (this.state === "done" && this.result) {
      this.media.replaceChildren(this.result.isImage ? this.still() : this.video());
    }
    else if (this.state === "failed") this.media.replaceChildren(this.slate());
    else if (this.frame) this.media.replaceChildren(this.previewFrame());
    else this.media.replaceChildren();

    if (this.state === "sampling" && this.progress?.total) {
      this.rule.style.transform = `scaleX(${Math.min(1, this.progress.step / this.progress.total)})`;
      this.rule.style.opacity = "1";
    } else {
      this.rule.style.opacity = "0";
    }

    this.renderReadout();
  }

  /**
   * The overlay. Its own method because the clock ticks it every second, and
   * rebuilding the picture for that would restart a playing video.
   *
   * **Two sides, in every state, so that nothing in the row changes address
   * when the render lands.** The left says what this is — which segment, which
   * step, or the way back to the ones before it — and the right is the clock.
   * It counts while the sampler runs and then holds the total, in the same
   * place, in the same type: the whole reason you watch it tick is to learn
   * what the next take will cost, and a number that vanished at the moment it
   * became the answer was the one reading the row could not give you.
   */
  renderReadout() {
    if (!this.showing()) return;
    // Built as two lists and hung on the row at the end, so the empty case is
    // an empty row — which is what `.mmc-stage-readout:empty` hides, and the
    // reason a finished still with no chips does not draw a scrim over itself.
    const left = [];
    const right = [];

    if (this.state === "failed") {
      // The slate says what happened; the row keeps only the clock, in the
      // slot it always has — what the failed run cost is still a reading.
      if (this.tookMs) right.push(el("span", {
        class: "mmc-stage-chip mmc-stage-clock",
        title: t("How long the render ran before it failed"),
        text: elapsed(this.tookMs),
      }));
    } else if (this.state === "sampling") {
      // Which segment these steps belong to — announced by the segment node,
      // so it names the one actually being made, cached ones skipped.
      if (this.segment) left.push(el("span", {
        class: "mmc-stage-chip mmc-stage-segment",
        text: this.segmentLabel?.(this.segment) ?? t("Segment {n}", { n: this.segment }),
      }));
      left.push(el("span", {
        class: "mmc-stage-chip mmc-stage-count",
        text: this.progress?.total ? `${this.progress.step} / ${this.progress.total}` : t("sampling"),
      }));
      // Nothing has arrived for a long time and the server has not said the
      // render is over either. Worth saying out loud: a clock ticking under a
      // frozen preview is indistinguishable from a hang, and the report this
      // came from describes a healthy render cancelled by hand because of it.
      // A second press turned away while this one runs — see `mmc_refused`.
      // The first reason on the chip, all of them on hover.
      if (this.refused?.length) left.push(el("span", {
        class: "mmc-stage-chip warn",
        title: this.refused.map((item) => [item.where, item.what].filter(Boolean).join(": ")).join("\n"),
        text: t("Next render not started: {why}", { why: this.refused[0].what }),
      }));
      if (this.quiet() > STALL_MS) left.push(el("span", {
        class: "mmc-stage-chip warn",
        title: t("Nothing has arrived from the server for a while. The render may well still "
               + "be running — this node is now asking the server directly, and will show the "
               + "result the moment it lands."),
        text: t("out of contact {when}", { when: elapsed(this.quiet()) }),
      }));
      right.push(...timingChips(this.clockTiming()));
    } else if (this.state === "done") {
      // A finished render is the picture — plus the way to the ones before it,
      // plus whatever hand-off chips the owner builds from the result (the
      // PreStage's "start frame / end frame / reference" row).
      if (this.onGallery) left.push(el("button", {
        class: "mmc-stage-chip mmc-stage-gallery",
        text: t("Gallery"),
        title: t("Browse finished renders"),
        onclick: () => this.onGallery(),
        onpointerdown: (event) => event.stopPropagation(),
      }));
      if (this.result?.saved && this.resultChips) left.push(...this.resultChips(this.result.saved));
      // A look for this render: opens the library on the Style tab with this
      // frame in the wipe. Only where the owner has the pass to run it.
      if (this.onRestyle) left.push(el("button", {
        class: "mmc-stage-chip mmc-stage-gallery",
        text: t("Restyle"),
        title: t("Pick a look from the style atlas and generate this render again in it."),
        onclick: () => this.onRestyle(),
        onpointerdown: (event) => event.stopPropagation(),
      }));
      right.push(...timingChips(this.clockTiming()));
    }

    this.readout.replaceChildren(
      ...(left.length ? [el("div", { class: "mmc-stage-side mmc-stage-actions" }, left)] : []),
      ...(right.length ? [el("div", { class: "mmc-stage-side end mmc-stage-times" }, right)] : []),
    );
  }

  /**
   * The slate: what stands in the frame when the render did not. Black, like
   * the frame it stands in for, and the reason written across it in the type
   * the rest of the card uses — a title card rather than a dialog, because it
   * lives where the picture lives and goes when the next take starts.
   *
   * Each item is two lines where there are two things to say: *where* it went
   * wrong — the node the user would have to open, in the warning colour — and
   * *what* the server said, verbatim, since that wording is what a search or an
   * issue will need. Where the failure is this node's own, there is no where.
   */
  slate() {
    const items = this.failure?.items ?? [];
    return el("div", {
      class: "mmc-stage-slate",
      // Selectable, and scrollable when a traceback runs long: the readout
      // over it swallows the pointer and this opts back in for both.
      onpointerdown: (event) => event.stopPropagation(),
      onwheel: (event) => event.stopPropagation(),
    }, [
      el("div", { class: "mmc-stage-slate-lead",
                  text: this.failure?.started ? t("The render failed.") : t("The render did not start.") }),
      ...items.map((item) => el("div", { class: "mmc-stage-slate-item" }, [
        item.where ? el("div", { class: "mmc-stage-slate-where", text: item.where }) : null,
        el("div", { class: "mmc-stage-slate-what", text: item.what }),
      ])),
    ]);
  }

  /** The newest step preview. An animated clip plays itself in a bare <video>;
   *  no transport, no sound-on-hover — it is a rough decode of the step's
   *  latent, not the result, and the result's player is video() below. */
  previewFrame() {
    if (!this.frameIsClip) {
      return el("img", {
        class: "mmc-stage-img", src: this.frame, alt: "",
        oncontextmenu: noMenu,
        onload: (event) => this.setAspect(event.currentTarget.naturalWidth,
                                          event.currentTarget.naturalHeight),
      });
    }
    const clip = el("video", {
      class: "mmc-stage-video",
      src: this.frame,
      oncontextmenu: noMenu,
      // Always moving, whatever Settings → Nodes says about finished renders.
      // A step preview is silent, has no controls, and is the one render that
      // is sampling right now — "Waits for play" is for a canvas of finished
      // clips decoding for nobody, and applied here it left the stage on a
      // still that no click could start ([#95]). Whether this is a <video> at
      // all is KJNodes' call: its encoder order now prefers x264 over WebP, so
      // the animated preview that used to be an <img> arrives as mp4 instead.
      autoplay: true,
      loop: true, playsinline: true, preload: "metadata",
      onloadedmetadata: (event) => this.setAspect(event.currentTarget.videoWidth,
                                                  event.currentTarget.videoHeight),
    });
    // The property rather than the attribute: Chromium's autoplay gate reads
    // `muted`, and setAttribute("muted") sets only the attribute.
    clip.muted = true;
    return clip;
  }

  /**
   * The finished render, in the loupe.
   *
   * The file rather than the element: the loupe fetches its own copy at full
   * size and probes it for its own dimensions, because what is on the stage is
   * fitted to a card and a viewer built on that would be magnifying a thumbnail.
   */
  toLoupe() {
    const source = stageSource(this.result);
    if (source) openLoupe({ source });
  }

  /** A finished still. An <img> and nothing else — no transport to draw, and
   *  the hand-off chips live in the readout overlay with the gallery. */
  still() {
    return el("img", {
      class: "mmc-stage-img",
      src: this.result.url,
      alt: this.result.name,
      // No tooltip. The double-click is still there and still opens fullscreen;
      // what is gone is the label that popped up over every finished render
      // whenever the pointer rested on it — a hint that costs the picture it is
      // covering, on the one element in the body worth looking at.
      ondblclick: () => this.toLoupe(),
      onload: (event) => this.setAspect(event.currentTarget.naturalWidth,
                                        event.currentTarget.naturalHeight),
      onpointerdown: (event) => event.stopPropagation(),
    });
  }

  video() {
    // Plays itself, silently, forever. Silence is not a preference: no browser
    // will autoplay a video with sound at all, so an unmuted one would simply
    // sit on its first frame — and a node body that starts talking the moment a
    // render lands is a node body you turn off.
    //
    // **So the sound follows the pointer**, which is what VHS's preview does and
    // is the only place volume can come from without either a click or a
    // surprise: putting the pointer on the picture is deliberate enough to mean
    // "let me hear this", and taking it off takes the sound away again. Nothing
    // about the autoplay policy is being worked around — the page has sticky
    // user activation long before a render exists, because queueing one is a
    // click.
    //
    // The control bar is the browser's: scrubbing and volume are solved problems
    // and a hand-built transport here would only be a worse one. Muting from it
    // sticks until the pointer next arrives, which is the same rule.
    //
    // Whether it plays *itself* is Settings → Nodes' preview-playback answer,
    // read at draw time off the same cache the shift pills use. Off means the
    // first frame, still, and the browser's play button — everything above
    // (loop, hover sound) applies unchanged once it is started by hand.
    return el("video", {
      class: "mmc-stage-video",
      src: this.result.url,
      // No tooltip, for the reason `still` gives.
      ondblclick: () => this.toLoupe(),
      autoplay: uiSetting("autoplay_previews", true),
      controls: true, loop: true, muted: true, playsinline: true, preload: "metadata",
      onloadedmetadata: (event) => this.setAspect(event.currentTarget.videoWidth,
                                                  event.currentTarget.videoHeight),
      onmouseenter: (event) => { event.currentTarget.muted = false; },
      onmouseleave: (event) => { event.currentTarget.muted = true; },
      // The canvas pans on drag, and a drag that starts on the scrub bar is a
      // scrub rather than a pan.
      onpointerdown: (event) => event.stopPropagation(),
    });
  }
}

/** A read-only pair, shared by the live stage and fullscreen take review.
 *  Labels matter: neither the difference nor the shorter number means model
 *  loading or sampler-only time. Unknown old/cached results are not zero. */
export function timingChips({ totalMs = null, tookMs = null, totalPending = false } = {}) {
  const whole = t("From workflow execution start to completion, including loading and other nodes; queue waiting is excluded.");
  const window = t("From the first detected sampling progress or preview to the saved result, including decoding, post-processing and saving; not sampling alone.");
  return [
    [t("Total execution"), totalMs, whole, totalPending],
    [t("Render window"), tookMs, window, false],
  ].map(([label, ms, explanation, pending]) => {
    const known = Number.isFinite(ms) && ms >= 0;
    const note = pending ? t("The workflow is still running.")
      : known ? "" : t("Timing is unavailable for this result.");
    return el("span", {
      class: "mmc-stage-chip mmc-stage-clock",
      title: [explanation, note].filter(Boolean).join(" "),
      "aria-label": `${label}: ${known ? elapsed(ms) : "—"}${note ? `. ${note}` : ""}`,
    }, [
      el("span", { class: "mmc-stage-clock-label", text: label }),
      el("span", { class: "mmc-stage-clock-value", text: known ? elapsed(ms) : "—" }),
    ]);
  });
}

/** Measure the footer in layout pixels, not canvas-zoomed screen pixels.
 *  Text scale, translations and wrapping can all change its height. The dock
 *  subtracts this from its media budget so the video retains its own aspect.
 *  A no-op in non-browser harnesses; the observer is owned by the view. */
export function watchFooterSize(root, readout) {
  if (typeof ResizeObserver === "undefined") return () => {};
  let previous = -1;
  const observer = new ResizeObserver(() => {
    const height = readout.offsetHeight;
    if (Number.isFinite(height) && height !== previous) {
      previous = height;
      root.style.setProperty("--mmc-stage-footer-height", `${height}px`);
    }
  });
  observer.observe(readout);
  return () => observer.disconnect();
}

/** What a history entry's status says went wrong, if it says anything.
 *  `messages` holds the events that would have come down the socket, as
 *  `[name, payload]` pairs — kept by the server for exactly this reason. */
function failureText(status) {
  for (const [event, payload] of status?.messages ?? []) {
    if (event === "execution_error" && payload?.exception_message) return payload.exception_message;
  }
  return null;
}

export function elapsed(ms) {
  const total = Math.max(0, Math.round(ms / 1000));
  const seconds = String(total % 60).padStart(2, "0");
  if (total < 3600) return `${Math.floor(total / 60)}:${seconds}`;
  return `${Math.floor(total / 3600)}:${String(Math.floor(total / 60) % 60).padStart(2, "0")}:${seconds}`;
}

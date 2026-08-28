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
// The step count and the clock are overlaid on the picture for the same reason:
// a caption row under the box is space the picture could have had.
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
//   nothing, so listening in on it costs that pack nothing.
// - `executed` carries `display_node`, which `render.emit_tail` has already
//   stamped with our id.

import { api } from "../../../scripts/api.js";
import { el } from "./dom.js";
import { outputUrl, uiSetting } from "./api.js";
import { t } from "./i18n.js";

/** Every event this listens to. `b_preview` is the metadata-less legacy frame:
 *  it names no node, so it is only trusted while `progress_state` already says
 *  one of ours is the thing sampling — see the handler. `mmc_segment` is our
 *  own: the timeline's segment node announcing which segment the queue has
 *  reached, the moment it starts encoding. */
const EVENTS = ["progress_state", "b_preview_with_metadata", "b_preview",
                "kj_preview_override", "executed", "execution_error", "execution_start",
                "execution_interrupted", "mmc_segment", "reconnected", "status"];

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
 * Double-click the finished picture for the browser's own fullscreen.
 *
 * The stage is as large as the room it is in and no larger — a card beside a
 * node, a plate in the shell — and neither is the size a 4K render was made to
 * be looked at. The way out was to find the file in the gallery and open it in
 * a tab, which is a detour around a picture that is already on screen.
 *
 * The browser's fullscreen rather than a lightbox of our own: it is the whole
 * display rather than the whole window, the video keeps its own transport, and
 * Escape already means what everyone expects it to. Toggled, because a second
 * double-click on the same picture is the obvious way back and the first one is
 * how you got here.
 *
 * On the finished render only. The step preview is an object URL that the next
 * frame revokes, so a fullscreen of it would go blank a second later — the same
 * reason that one has no context menu.
 */
const toFullscreen = (event) => {
  const media = event.currentTarget;
  event.preventDefault();
  if (document.fullscreenElement === media) {
    document.exitFullscreen?.();
    return;
  }
  // webkit's prefixed name is the one Safari has on a non-video element.
  const open = media.requestFullscreen ?? media.webkitRequestFullscreen;
  try { open?.call(media)?.catch?.(() => {}); } catch { /* refused; nothing to do */ }
};

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
                onTakes = null }) {
    this.nodeId = nodeId;
    this.onVisibility = onVisibility;
    this.onState = onState;
    this.onGallery = onGallery;
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
    this.error = null;
    this.startedAt = 0;
    // Which queued prompt the stage believes it is watching, and when it last
    // heard anything about it. Between them they are the whole of the recovery
    // path in `probe()`: the id says what to ask the server about, and the
    // silence says when to start asking.
    this.promptId = null;
    this.lastNewsAt = 0;
    this.probedAt = 0;
    this.probing = false;
    // How long the finished render took, in ms. Held past the run because the
    // clock is the one reading the readout keeps after the picture lands: the
    // whole reason you watch it tick is to know what the next one will cost.
    this.tookMs = 0;

    this.media = el("div", { class: "mmc-stage-media" });
    this.rule = el("div", { class: "mmc-stage-rule" });
    this.readout = el("div", { class: "mmc-stage-readout" });
    this.root = el("div", { class: "mmc-stage" }, [this.media, this.rule, this.readout]);

    this.onEvent = (event) => this.handle(event.type, event.detail);
    for (const name of EVENTS) api.addEventListener(name, this.onEvent);

    this.render();
  }

  /** Called when the node body is torn down. Listeners on `api` outlive the DOM
   *  otherwise, and a deleted node would go on decoding previews forever. */
  destroy() {
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
        this.promptId = detail.prompt_id ?? null;
        this.lastNewsAt = Date.now();
        break;

      case "reconnected":
        // The wire came back. Nothing that happened while it was gone will be
        // repeated — `executed` is sent once, to whoever was listening — so the
        // question goes to the server now rather than after another 30 seconds
        // of silence.
        if (this.state !== "sampling") break;
        this.probedAt = 0;
        this.probe();
        break;

      case "status":
        // Some frontends announce a reattached socket only by sending the queue
        // state down it. A `status` arriving in the middle of a long silence is
        // that, near enough, and costs one small GET to act on.
        if (this.state === "sampling" && this.quiet() > QUIET_MS) this.probe();
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
        if (this.state !== "sampling") {
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
        if (!this.ours(detail.node_id)) break;
        this.news();
        // The boundary-0 message carries the sigma schedule and often no picture
        // at all. Take the step count from it, but do not open the stage on it —
        // see above.
        if (Number.isFinite(detail.total)) {
          this.progress = { step: detail.step ?? 0, total: detail.total };
        }
        if (!detail.image) break;
        this.begin();
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
        this.finish(detail.output);
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
        // Cancelled. There is no `executed` and no `execution_error` coming, so
        // without this the stage sat on "sampling" forever — and everything that
        // reads `onState` sat with it: the fullscreen editor's Render button
        // stayed a readout of a run that had already stopped, with no way back
        // to a button short of closing the editor.
        //
        // Whose run it was is not asked, for the same reason `b_preview` does
        // not ask: the queue runs one thing at a time, so an interrupt landing
        // while this stage is sampling is this stage's interrupt. The payload
        // names the node the executor was inside, which is somewhere in the
        // expansion and not reliably prefixed with ours.
        if (this.state !== "sampling") break;
        // Back to nothing, rather than leaving the last preview frame up: it is
        // a step of a video that was never finished, and a stage still showing
        // it reads as a render that landed.
        this.reset();
        break;

      case "execution_error":
        if (!this.ours(detail.node_id)) break;
        this.state = "failed";
        this.progress = null;
        clearInterval(this.ticker);
        this.error = detail.exception_message || t("the render failed");
        this.render();
        break;
    }
  }

  /** Everything the last render left in the box — the picture, the clock, what
   *  went wrong. Not the run's bookkeeping: `reset` adds that, and `begin` keeps
   *  it, because a run that is starting is the one asking. */
  clearRender() {
    this.metaFrameAt = 0;
    this.result = null;
    this.error = null;
    this.tookMs = 0;
    this.progress = null;
    this.segment = null;
    this.releaseFrame();
    this.frame = null;
    this.frameIsClip = false;
    this.clearAspect();
  }

  reset() {
    clearInterval(this.ticker);
    this.promptId = null;
    this.lastNewsAt = 0;
    this.probedAt = 0;
    this.state = "idle";
    this.clearRender();
    this.render();
  }

  /** First frame of a queue. Starts the clock once rather than on every step, so
   *  the elapsed readout is elapsed and not a stutter. */
  begin() {
    if (this.state === "sampling") return;
    // The first word that this queue is ours, and so the moment the last one's
    // picture stops being the answer — see `execution_start`.
    this.clearRender();
    this.state = "sampling";
    this.startedAt = Date.now();
    this.lastNewsAt = Date.now();
    clearInterval(this.ticker);
    // Only the readout, and only once a second: the frames arrive when they
    // arrive, and a full render on a timer would fight the preview for the box.
    this.ticker = setInterval(() => this.tick(), 1000);
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
  finish(output) {
    const saved = output?.mmc_video?.[0] ?? output?.mmc_image?.[0];
    if (!saved) return;
    // The passes, each as its own file. Reported alongside the piece by
    // `MiniMaxH3Save` on any render of more than one pass, so a card whose
    // pass came out right never has to be sampled again.
    if (output?.mmc_takes?.length) this.onTakes?.(output.mmc_takes);
    this.state = "done";
    this.progress = null;
    // The clock stops here rather than on the next tick, so what the readout
    // shows after the render is the render's own length and not a second of
    // whatever happened to follow it.
    this.tookMs = this.startedAt ? Date.now() - this.startedAt : 0;
    this.result = { url: outputUrl(saved), name: saved.filename,
                    isImage: !output?.mmc_video, saved,
                    // Carried on the result as well as held here: the
                    // fullscreen reel keeps finished renders past the run
                    // that made them, and a take without its cost is a
                    // picture you can only compare on looks.
                    tookMs: this.tookMs };
    // The finished clip takes the preview's place, so the last sampled frame is
    // now a picture that can never be shown again — and the clock it was
    // ticking under has stopped.
    clearInterval(this.ticker);
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
    this.renderReadout();
    if (this.state === "sampling" && this.quiet() > QUIET_MS) this.probe();
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
   * recovery is to read it back rather than to guess from a timeout. A prompt
   * that is not in it yet is a render still running, which is the answer as
   * often as not — a slow step is silence too — and that case does nothing but
   * let the readout say it has lost contact.
   */
  async probe() {
    if (this.probing || !this.promptId) return;
    if (Date.now() - this.probedAt < PROBE_EVERY_MS) return;
    this.probing = true;
    this.probedAt = Date.now();
    try {
      const response = await api.fetchApi(`/history/${encodeURIComponent(this.promptId)}`);
      if (!response.ok) return;
      const entry = (await response.json())?.[this.promptId];
      // The stage may have caught up on its own while this was in flight — the
      // wire coming back mid-probe is the likeliest moment of all — and a probe
      // must never overwrite a result that arrived the ordinary way.
      if (this.state !== "sampling") return;
      if (!entry) return;
      const output = this.savedOutput(entry.outputs, entry.meta);
      if (output) {
        this.finish(output);
        return;
      }
      // In history, with nothing of ours in it: the render failed or was
      // cancelled while nobody was listening. Saying so is the point — this is
      // the state the report describes as costing a 179-second render, because
      // a stage that cannot tell "running" from "over" gets cancelled by hand.
      this.state = "failed";
      this.progress = null;
      clearInterval(this.ticker);
      this.error = failureText(entry.status) ?? t("the render ended without a file");
      this.render();
    } catch { /* the wire is down as well; the ticker asks again in five seconds */ }
    finally { this.probing = false; }
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
      left.push(el("span", { class: "mmc-stage-chip warn", text: this.error }));
    } else if (this.state === "sampling") {
      // Which segment these steps belong to — announced by the segment node,
      // so it names the one actually being made, cached ones skipped.
      if (this.segment) left.push(el("span", {
        class: "mmc-stage-chip mmc-stage-segment",
        text: this.segmentLabel?.(this.segment) ?? t("Segment {n}", { n: this.segment }),
      }));
      left.push(el("span", {
        class: "mmc-stage-chip",
        text: this.progress?.total ? `${this.progress.step} / ${this.progress.total}` : t("sampling"),
      }));
      // Nothing has arrived for a long time and the server has not said the
      // render is over either. Worth saying out loud: a clock ticking under a
      // frozen preview is indistinguishable from a hang, and the report this
      // came from describes a healthy render cancelled by hand because of it.
      if (this.quiet() > STALL_MS) left.push(el("span", {
        class: "mmc-stage-chip warn",
        title: t("Nothing has arrived from the server for a while. The render may well still "
               + "be running — this node is now asking the server directly, and will show the "
               + "result the moment it lands."),
        text: t("out of contact {when}", { when: elapsed(this.quiet()) }),
      }));
      right.push(el("span", {
        class: "mmc-stage-chip mmc-stage-clock",
        text: elapsed(Date.now() - this.startedAt),
      }));
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
      // The same slot the ticking clock had. Titled rather than labelled: the
      // row is read at a glance and "took" is a word the position already says.
      if (this.tookMs) right.push(el("span", {
        class: "mmc-stage-chip mmc-stage-clock",
        title: t("How long this render took"),
        text: elapsed(this.tookMs),
      }));
    }

    this.readout.replaceChildren(
      ...(left.length ? [el("div", { class: "mmc-stage-side" }, left)] : []),
      ...(right.length ? [el("div", { class: "mmc-stage-side end" }, right)] : []),
    );
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
      // Settings → Nodes decides whether it moves before being asked; a stage
      // told to hold still holds the clip's first frame (preload paints it).
      autoplay: uiSetting("autoplay_previews", true),
      loop: true, playsinline: true, preload: "metadata",
      onloadedmetadata: (event) => this.setAspect(event.currentTarget.videoWidth,
                                                  event.currentTarget.videoHeight),
    });
    // The property rather than the attribute: Chromium's autoplay gate reads
    // `muted`, and setAttribute("muted") sets only the attribute.
    clip.muted = true;
    return clip;
  }

  /** A finished still. An <img> and nothing else — no transport to draw, and
   *  the hand-off chips live in the readout overlay with the gallery. */
  still() {
    return el("img", {
      class: "mmc-stage-img",
      src: this.result.url,
      alt: this.result.name,
      title: t("Double-click for fullscreen"),
      ondblclick: toFullscreen,
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
      title: t("Double-click for fullscreen"),
      ondblclick: toFullscreen,
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

/** `92000` -> `"1:32"`. Minutes only: a render that runs for an hour has bigger
 *  problems than its readout. Exported because the fullscreen lip captions each
 *  past take with what it cost, and two clocks in one window that round
 *  differently is one clock too many. */
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
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

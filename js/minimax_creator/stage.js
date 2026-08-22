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
                "execution_interrupted", "mmc_segment"];

/** A progress report this long is a sampler; the loaders and decoders report a
 *  step or two each. What lets the stage open on progress rather than waiting
 *  for a first frame, without opening as an empty black box for as long as a
 *  checkpoint takes to read off disk. */
const OPENS_ON_STEPS = 4;

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
   */
  setAspect(width, height) {
    if (!width || !height) return;
    this.root.style.setProperty("--mmc-media-ar", `${width} / ${height}`);
  }

  clearAspect() {
    this.root.style.removeProperty("--mmc-media-ar");
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
        // A new queue: whatever is on the stage belongs to the last one. Back to
        // hidden until the first frame of this one arrives, rather than leaving
        // the previous render up while a different one is being made.
        this.reset();
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
        // The stage opens the moment something with real steps is running —
        // not on the loaders (their one-step reports stay below the
        // threshold), and not waiting for a first preview frame either, which
        // may simply never arrive (preview method off, or a frontend that
        // stopped carrying metadata on the frames).
        if (!this.showing()) {
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
        this.releaseFrame();
        this.frameUrl = URL.createObjectURL(blob);
        this.frame = this.frameUrl;
        this.frameIsClip = false;
        this.render();
        break;
      }

      case "kj_preview_override": {
        if (!this.ours(detail.node_id)) break;
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

      case "executed": {
        // `render.emit_tail` stamped our id on the save node, so this is our
        // render coming back even though the node that made it is not on the
        // canvas.
        if (String(detail.display_node) !== String(this.nodeId())) break;
        // Under our own keys, not "images": that is the key core's stock
        // widgets watch, and they were rendering a second player on the canvas
        // node right under this stage. MiniMaxH3Save reports mmc_video and
        // MiniMaxH3SaveImage reports mmc_image instead; which one arrives is
        // also what says whether the result is a clip or a still.
        const saved = detail.output?.mmc_video?.[0] ?? detail.output?.mmc_image?.[0];
        if (!saved) break;
        // The passes, each as its own file. Reported alongside the piece by
        // `MiniMaxH3Save` on any render of more than one pass, so a card whose
        // pass came out right never has to be sampled again.
        if (detail.output?.mmc_takes?.length) this.onTakes?.(detail.output.mmc_takes);
        this.state = "done";
        this.progress = null;
        // The clock stops here rather than on the next tick, so what the readout
        // shows after the render is the render's own length and not a second of
        // whatever happened to follow it.
        this.tookMs = this.startedAt ? Date.now() - this.startedAt : 0;
        this.result = { url: outputUrl(saved), name: saved.filename,
                        isImage: !detail.output?.mmc_video, saved,
                        // Carried on the result as well as held here: the
                        // fullscreen reel keeps finished renders past the run
                        // that made them, and a take without its cost is a
                        // picture you can only compare on looks.
                        tookMs: this.tookMs };
        // The finished clip takes the preview's place, so the last sampled
        // frame is now a picture that can never be shown again — and the clock
        // it was ticking under has stopped.
        clearInterval(this.ticker);
        this.releaseFrame();
        this.frame = null;
        this.render();
        break;
      }

      case "mmc_segment":
        // The segment node announcing itself as it starts to encode — the one
        // signal that says *whose* steps the sampler's are about to be. Held
        // until the next announce: the sampler, the decoders and any refine
        // pass that follow all belong to the same segment.
        if (!this.ours(detail.node)) break;
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

  reset() {
    clearInterval(this.ticker);
    this.metaFrameAt = 0;
    this.state = "idle";
    this.result = null;
    this.error = null;
    this.tookMs = 0;
    this.progress = null;
    this.segment = null;
    this.releaseFrame();
    this.frame = null;
    this.frameIsClip = false;
    this.clearAspect();
    this.render();
  }

  /** First frame of a queue. Starts the clock once rather than on every step, so
   *  the elapsed readout is elapsed and not a stutter. */
  begin() {
    if (this.state === "sampling") return;
    this.state = "sampling";
    this.startedAt = Date.now();
    clearInterval(this.ticker);
    // Only the readout, and only once a second: the frames arrive when they
    // arrive, and a full render on a timer would fight the preview for the box.
    this.ticker = setInterval(() => this.renderReadout(), 1000);
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
        onload: (event) => this.setAspect(event.currentTarget.naturalWidth,
                                          event.currentTarget.naturalHeight),
      });
    }
    const clip = el("video", {
      class: "mmc-stage-video",
      src: this.frame,
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
export function elapsed(ms) {
  const total = Math.max(0, Math.round(ms / 1000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

// The sound lane: what the piece is being cut to, and where it sits. The
// surface; `sound.js` is the arithmetic under it.
//
// **Why the lane needs an axis the strip does not have.** The card strip is
// deliberately not to scale: `cardWidth` compresses durations by their square
// root so a one-second card is still wide enough for its own buttons and a
// sixty-second one is not most of a metre. That is right for a storyboard and
// useless for sound, which has to be placed *at a time*. So the lane brings its
// own linear axis and a proportional reel above it — the same picture of the
// piece the node body draws — and the reel is the bridge between the two
// readings. The strip says what the shots are; the reel says how long they run;
// the lane sits under the reel because that is the one it shares a clock with.
//
// **The band is always full.** Where a file was laid down it is solid; where
// none was, it is perforated — the strip's own grammar for film that exists
// against film that does not, carried onto sound. This is not decoration. These
// are joint audio-video models: a stretch nobody covered is not silence, it is a
// stretch the model scores, and "I left a gap so it would be quiet" is the one
// thing everybody assumes and nobody is told. The perforation is the telling.
//
// **Two kinds of thing appear here and they are not interchangeable.** A block
// is a `copy` — the signal itself becomes the video's own audio, which is what
// `AUDIO_TAKES` has meant by that word since before anything could honour it. A
// hairline under a card is an *imitation* reference attached to that card:
// `voice`, `music`, `ambience`, sound-like-this, which rides to the model as a
// reference block and prose. The lane draws both because you should be able to
// see all the sound in one place; it lets you drag only the first, because
// dragging the second would silently turn "sound like this" into "this is the
// sound".

import { el } from "./dom.js";
import { probe } from "./api.js";
import { t } from "./i18n.js";
import { peaks, draw } from "./waveform.js";
import { openPicker } from "./picker.js";
import { openTrim, formatTime } from "./trim.js";
import * as S from "./state.js";
import { rulesFor, secondsForFrames, matchSeconds } from "./canvas.js";
import { MIN_SECONDS, atFrame, lane, band, pinned } from "./sound.js";

// How near a snap target has to be before a drag lands on it, in pixels. Chosen
// in pixels rather than frames on purpose: it is a statement about the pointer,
// and a piece ten minutes long would otherwise snap from half a screen away.
const SNAP_PX = 7;

const WAVE_COLOUR = "rgba(255,255,255,.30)";

// Tick spacings a clock is read in. The ruler takes the first one that leaves
// fewer than a dozen labels, so a fifteen-second piece is counted in twos and a
// ten-minute one in minutes without either being asked to.
const TICKS = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600];

/** A tick's own label. Seconds while the piece is short enough to think in
 *  them, m:ss once it is not — the same switch a stopwatch makes. */
const tickLabel = (seconds, span) => (span >= 60
  ? `${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, "0")}`
  : `${Number(seconds.toFixed(1))}s`);

/** What a take says it does to the sound, for the hairline's own label. */
const TAKE_WORD = {
  full: "sounds like",
  voice: "voice of",
  music: "music of",
  ambience: "room of",
  copy: "is",
};

export class SoundLane {
  /**
   * @param {object} options
   * @param {() => object} options.read     the piece, live
   * @param {() => void} options.onCommit   called after any edit lands
   * @param {(message: string) => void} options.flash  how this surface complains
   */
  constructor({ read, onCommit, flash }) {
    this.read = read;
    this.onCommit = onCommit;
    this.flash = flash ?? (() => {});
    // path -> seconds. A block needs its file's whole length to know how far a
    // trim handle may travel, and that is a fact about the file rather than
    // about the piece, so it comes from the probe route and is remembered here.
    this.lengths = new Map();
    this.host = el("div", { class: "mmc-snd" });
    this.waves = new Map();
    // block index -> its element, for the duration of one render. A drag writes
    // through this rather than re-rendering; see `blocks()`.
    this.nodes = new Map();
    // The drag's own copy of the lane, and which block it has hold of. Null
    // whenever the pointer is up, which is what every edit reads to know
    // whether it is painting or committing.
    this.working = null;
    this.dragging = null;
  }

  get piece() { return this.read(); }

  rules() { return rulesFor(S.pieceFamily(this.piece)); }

  seconds(frames) { return secondsForFrames(frames, this.rules()); }

  commit(sound) {
    this.piece.sound = sound;
    this.onCommit();
    this.render();
  }

  // ---- geometry ------------------------------------------------------------

  /** The lane's own width, in frames. The whole piece, always: a lane that
   *  stopped at the last block would move every block whenever the last one
   *  was trimmed. */
  total() { return Math.max(1, S.timelineFrames(this.piece)); }

  /** A frame count as a percentage of the lane. Percentages rather than pixels
   *  so the lane survives the modal being resized without measuring anything —
   *  only the waveforms need a redraw, and they ask for their own. */
  pct(frames) { return `${(frames / this.total()) * 100}%`; }

  /** Where the pointer is, in frames on the piece's clock. */
  frameAt(event) {
    const rect = this.laneEl.getBoundingClientRect();
    if (!rect.width) return 0;
    const at = (event.clientX - rect.left) / rect.width;
    return Math.round(Math.min(1, Math.max(0, at)) * this.total());
  }

  /** How many frames a pixel is worth, for the snap radius. */
  perPixel() {
    const width = this.laneEl?.getBoundingClientRect().width || 1;
    return this.total() / width;
  }

  /**
   * Everywhere a drag should want to land: the ends of the piece, every cut
   * between passes, and the edges of every other block.
   *
   * The cuts are the ones that matter and the reason the reel is drawn at all —
   * "this cue starts on the cut" is the gesture this whole surface exists for,
   * and a lane that made you land it by eye would be a lane that never quite
   * did.
   */
  snapPoints(exclude) {
    const points = [0, this.total()];
    for (const window of S.passWindows(this.piece)) {
      points.push(window.at, window.at + window.frames);
    }
    for (const block of lane(this.piece)) {
      if (block.index === exclude) continue;
      points.push(block.at, block.at + block.frames);
    }
    return points;
  }

  /** `frame` pulled onto the nearest snap point within reach, or left alone.
   *  Returns the frame and what it landed on, so the drag can draw the line
   *  that says why it stopped there. */
  snap(frame, exclude) {
    const reach = SNAP_PX * this.perPixel();
    let best = null;
    for (const point of this.snapPoints(exclude)) {
      const gap = Math.abs(point - frame);
      if (gap <= reach && (best === null || gap < Math.abs(best - frame))) best = point;
    }
    return best === null ? { frame, snapped: null } : { frame: best, snapped: best };
  }

  // ---- editing -------------------------------------------------------------

  /**
   * The blocks an edit works on.
   *
   * Normally the piece's own, read fresh. **While the pointer is down it is the
   * drag's working copy**, and that is not a nicety: a commit re-renders the
   * lane, a re-render replaces the node the pointer is captured on, and a
   * captured node that leaves the document loses the capture. Committing every
   * move meant every drag died on its first pixel — the block jumped once and
   * then sat there while the pointer went on moving over a lane that was no
   * longer listening. So a drag mutates this list, paints what it did, and
   * writes back once on release.
   */
  blocks() { return this.working ?? lane(this.piece); }

  /** Where an edit lands: on the screen while a drag is live, in the piece
   *  when it is not. */
  settle(blocks) {
    if (this.working) this.paint();
    else this.commit(this.store(blocks));
  }

  /** One block out of a list by its own index, never by its position. The two
   *  agree for anything `store` has written — it sorts — and do not have to for
   *  a blob somebody typed. */
  at(blocks, index) { return blocks.find((block) => block.index === index); }

  /** The blocks as the blob stores them, back from the working list. */
  store(blocks) {
    const rules = this.rules();
    return blocks
      .slice()
      .sort((a, b) => a.at - b.at)
      .map((block) => ({
        filename: block.filename,
        at_s: Number((block.at / rules.fps).toFixed(3)),
        in_s: Number(block.in_s.toFixed(3)),
        out_s: Number(block.out_s.toFixed(3)),
      }));
  }

  /**
   * Move one block to `at`, past its neighbours if it is pushed far enough.
   *
   * One stretch of a piece has one soundtrack — there is one audio latent and
   * two files cannot both be the sound at 0:04 — so two blocks never overlap,
   * and a neighbour stops one arriving where it stands. Butting up against it
   * is the useful behaviour and most of a drag ends there.
   *
   * But a wall that cannot be got past is a lane where the only way to put a
   * cue in front of another is to delete both and lay them again in the other
   * order. So the wall gives way at the halfway mark: **push a block more than
   * half way past its neighbour and the two trade places**, closing up against
   * the side the drag is heading. Nothing overlaps at any point, the pair keeps
   * the stretch it already occupied, and pushing back the other way puts them
   * back — the reorder is part of the same gesture, not a mode.
   */
  slide(index, at) {
    const blocks = this.blocks();
    const block = this.at(blocks, index);
    if (!block) return;
    const others = blocks.filter((entry) => entry.index !== block.index);
    const before = others.filter((entry) => entry.at + entry.frames <= block.at);
    const after = others.filter((entry) => entry.at >= block.at + block.frames);
    const floor = before.length ? Math.max(...before.map((e) => e.at + e.frames)) : 0;
    const ceiling = after.length ? Math.min(...after.map((e) => e.at))
      : this.total();

    // Halfway is measured centre to centre, so the swap happens where the two
    // look as though they have already changed places rather than when some
    // edge of one clears some edge of the other. That is the mark the eye is
    // watching, and it is the only one that reads the same whether the block in
    // hand is the longer of the two or the shorter.
    const middle = (entry) => entry.at + entry.frames / 2;
    const wall = at < floor ? before.find((entry) => entry.at + entry.frames === floor)
      : at + block.frames > ceiling ? after.find((entry) => entry.at === ceiling)
      : null;
    if (wall && at < floor && at + block.frames / 2 < middle(wall)) {
      // Both stay inside the stretch the pair already had, butted at its head:
      // whatever gap sat between them comes out the far side.
      block.at = wall.at;
      wall.at = block.at + block.frames;
      return this.settle(blocks);
    }
    if (wall && at >= floor && middle(wall) < at + block.frames / 2) {
      const end = wall.at + wall.frames;
      block.at = end - block.frames;
      wall.at = block.at - wall.frames;
      return this.settle(blocks);
    }

    block.at = Math.max(floor, Math.min(at, ceiling - block.frames));
    this.settle(blocks);
  }

  /**
   * Trim one end of a block.
   *
   * Two windows move and only one of them is the one being dragged. The head
   * handle moves where the block sits in the *piece* and where it opens in the
   * *file* together — that is what trimming a head means, and moving only one
   * of them would be a slip. The tail handle moves only the file's out point.
   *
   * The card a trim drags along with it is settled by the caller — `grip` reads
   * the match once, before the drag starts. It has to be read then: the match is
   * derived from the piece agreeing with the block, and half way through a trim
   * nothing agrees with anything.
   */
  trim(index, edge, frame) {
    const rules = this.rules();
    const blocks = this.blocks();
    const block = this.at(blocks, index);
    if (!block) return;
    const whole = this.lengths.get(block.filename) ?? null;

    if (edge === "head") {
      const end = block.at + block.frames;
      const limit = end - atFrame(MIN_SECONDS, rules);
      // Not past the head of the file: a block cannot open before its own
      // first sample, however far the handle is dragged.
      const room = block.at - atFrame(block.in_s, rules);
      const at = Math.max(room, Math.min(frame, limit));
      block.in_s += (at - block.at) / rules.fps;
      block.at = at;
      block.frames = end - at;
    } else {
      const limit = block.at + atFrame(MIN_SECONDS, rules);
      const ceiling = whole === null ? Infinity
        : block.at + atFrame(whole - block.in_s, rules);
      const end = Math.max(limit, Math.min(frame, ceiling));
      block.frames = end - block.at;
      block.out_s = block.in_s + block.frames / rules.fps;
    }
    if (edge === "head") block.out_s = block.in_s + block.frames / rules.fps;

    this.settle(blocks);
  }

  /**
   * The card this block's length was agreed with, or null.
   *
   * "Agreed" is `S.lengthMatch(...).matched` — whether the card already lands on
   * the same frame count as the reference it is offered a match against. It is
   * derived rather than stored, which is exactly what makes this safe: there is
   * no flag to go stale, and a card that was never matched cannot be moved by a
   * trim it has nothing to do with.
   */
  matchedCard(block) {
    const piece = this.piece;
    const windows = S.passWindows(piece);
    for (let index = 0; index < (piece.segments ?? []).length; index += 1) {
      const window = windows[S.passIndexOf(piece, index)];
      if (!window || window.at !== block.at) continue;
      const segment = piece.segments[index];
      const match = S.lengthMatch(segment, (name) => this.lengths.get(name), piece);
      if (match?.matched) return index;
    }
    return null;
  }

  rematch(index, seconds) {
    const segment = this.piece.segments[index];
    if (!segment) return;
    segment.duration_s = matchSeconds(seconds, this.rules());
    this.onCommit();
    this.render();
  }

  remove(index) {
    const blocks = lane(this.piece).filter((block) => block.index !== index);
    this.commit(this.store(blocks));
  }

  /** Open the trim modal on a block — the same one every other file in this
   *  pack is trimmed in, so a cue is cut the way a reference is. */
  async openBlock(index) {
    const block = this.at(lane(this.piece), index);
    if (!block) return;
    const chosen = await openTrim({
      path: block.filename,
      kind: "audio",
      trim: { start: block.in_s, end: block.out_s },
      showTrack: false,
      cardSeconds: this.seconds(block.frames),
    });
    if (!chosen) return;
    const rules = this.rules();
    const blocks = lane(this.piece);
    const target = this.at(blocks, index);
    if (!target) return;
    const matched = this.matchedCard(target);
    target.in_s = chosen.trim?.start ?? 0;
    target.out_s = chosen.trim?.end ?? target.out_s;
    target.frames = Math.max(1, atFrame(target.out_s - target.in_s, rules));
    this.commit(this.store(blocks));
    if (matched) this.rematch(matched, target.frames / rules.fps);
  }

  /**
   * Add one or more files to the lane.
   *
   * The picker is opened with no `capacity`: the lane is bounded by the length
   * of the piece, not by reference slots, and inventing a bucket so the modal
   * had something to divide by would be a control pretending to be a limit.
   * Video is offered alongside audio because a clip's soundtrack is a perfectly
   * ordinary thing to lay down — `media.load_audio` decodes the audio stream
   * out of a container either way.
   */
  async add() {
    const chosen = await openPicker({ kinds: ["audio", "video"], kind: "audio" });
    if (!chosen?.length) return;
    await this.lay(chosen);
  }

  /**
   * Lay picked files end to end after whatever is already on the lane.
   *
   * Split from `add` so the arithmetic can be tested without a modal: what a
   * file's length is, where the next one starts, and what happens when the
   * piece runs out are the parts that can be wrong, and none of them needs a
   * picker to exercise.
   */
  async lay(chosen) {
    const rules = this.rules();
    const blocks = lane(this.piece);
    let at = blocks.length
      ? Math.max(...blocks.map((block) => block.at + block.frames)) : 0;
    for (const file of chosen) {
      const whole = await this.lengthOf(file.path);
      const start = file.trim?.start ?? 0;
      const end = file.trim?.end ?? whole;
      if (!Number.isFinite(end) || end - start < MIN_SECONDS) {
        this.flash(t("{name} is too short to lay down — the shortest block is {min} s.",
                     { name: file.path.split("/").pop(), min: MIN_SECONDS }));
        continue;
      }
      if (at >= this.total()) {
        this.flash(t("The piece is full — lengthen a shot, or trim what is on the lane, "
                   + "to make room for {name}.", { name: file.path.split("/").pop() }));
        break;
      }
      // Cut to what is left of the piece rather than refused for overrunning
      // it: a four-minute album track dropped onto a twenty-second piece is
      // somebody asking for its first twenty seconds.
      const room = this.seconds(this.total() - at);
      const frames = Math.max(1, atFrame(Math.min(end - start, room), rules));
      blocks.push({
        index: blocks.length, filename: file.path, at, frames,
        in_s: start, out_s: start + frames / rules.fps,
      });
      at += frames;
    }
    this.commit(this.store(blocks));
  }

  async lengthOf(path) {
    if (!this.lengths.has(path)) {
      const { duration } = await probe(path);
      this.lengths.set(path, Number.isFinite(duration) ? duration : null);
    }
    return this.lengths.get(path);
  }

  // ---- drag ----------------------------------------------------------------

  /**
   * Pointer-drag on the lane. `begin` runs on pointerdown and returns the
   * per-move step, so each grab closes over where it started — which is what
   * lets a block move as a rigid window instead of jumping its own width to
   * meet the pointer. Same shape as `trim.js`'s, for the same reason. `done`
   * runs once after the release has been written back, for whatever has to
   * follow the whole gesture rather than each pixel of it.
   *
   * **Nothing here re-renders while the pointer is down.** The drag holds the
   * blocks in `working`, moves come out on the block's own style, and the piece
   * is written once on release. A render mid-drag pulls the captured node out
   * of the document, and the browser drops the capture with it: the moment this
   * committed per move, it stopped being a drag at all.
   */
  drag(node, index, begin, done) {
    node.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      event.stopPropagation();
      node.setPointerCapture(event.pointerId);
      this.working = lane(this.piece);
      this.dragging = index;
      const from = this.frameAt(event);
      const step = begin(from);
      let dirty = false;
      const move = (moved) => {
        const { frame, snapped } = this.snap(this.frameAt(moved), index);
        this.showSnap(snapped);
        dirty = true;
        step(frame);
      };
      const up = () => {
        node.removeEventListener("pointermove", move);
        node.removeEventListener("pointerup", up);
        node.removeEventListener("pointercancel", up);
        this.showSnap(null);
        this.showRead(null);
        const blocks = this.working;
        this.working = null;
        this.dragging = null;
        // A press that never moved is a click on its way to opening the block,
        // and neither writing nor rendering must get in front of it: a click
        // only lands when the same node saw both halves of the press.
        if (!dirty) return;
        this.commit(this.store(blocks));
        done?.();
      };
      node.addEventListener("pointermove", move);
      node.addEventListener("pointerup", up);
      node.addEventListener("pointercancel", up);
    });
  }

  /**
   * Put the lane where the working list now says it is.
   *
   * The whole live half of a drag. Every block rather than only the one in
   * hand, because a swap moves two of them, and the gaps with them: the
   * perforation is this lane's statement that the model writes the sound where
   * nothing was laid, and a drag that left it drawn over the stretch the block
   * has already left would be making that statement about the wrong seconds.
   */
  paint() {
    const blocks = this.working ?? [];
    for (const block of blocks) {
      const node = this.nodes.get(block.index);
      if (!node) continue;
      node.style.left = this.pct(block.at);
      node.style.width = this.pct(block.frames);
      const length = node.querySelector(".mmc-snd-len");
      if (length) {
        length.textContent = t("{length} s", { length: this.seconds(block.frames).toFixed(1) });
      }
    }
    this.paintGaps(blocks);
    const dragged = this.at(blocks, this.dragging);
    if (!dragged) return;
    this.nodes.get(this.dragging)?.classList.add("dragging");
    this.showRead(dragged);
  }

  /** The perforated stretches, redrawn from a block list. Their own layer, so a
   *  drag can rebuild them without going near the node the pointer is on. */
  paintGaps(blocks) {
    if (!this.gapsEl) return;
    this.gapsEl.replaceChildren(
      ...band(blocks, this.total())
        .filter((part) => !part.block)
        .map((part) => this.renderGap(part)));
  }

  /**
   * What the block has got to, while it is being moved or trimmed.
   *
   * On the piece's clock, not the file's: a drag is a question about the cut.
   * Centred on the block and then held off the lane's own ends, because the
   * lane clips and a cue dragged to 0:00 would otherwise read half a badge.
   */
  showRead(block) {
    if (!this.readEl) return;
    this.readEl.classList.toggle("on", !!block);
    if (!block) return;
    const from = this.seconds(block.at);
    const to = this.seconds(block.at + block.frames);
    this.readEl.style.left =
      `clamp(76px, ${this.pct(block.at + block.frames / 2)}, calc(100% - 76px))`;
    this.readAtEl.textContent = `${formatTime(from)} – ${formatTime(to)}`;
    this.readLenEl.textContent = t("{length} s", { length: (to - from).toFixed(1) });
  }

  /** The line that says a drag stopped somewhere on purpose. */
  showSnap(frame) {
    if (!this.snapEl) return;
    this.snapEl.classList.toggle("on", frame !== null);
    if (frame !== null) this.snapEl.style.left = this.pct(frame);
  }

  /** Arrow keys on a focused block: a frame, or a second with shift. The same
   *  two steps `trim.js` offers, because they are the same two questions. */
  arrows(node, apply) {
    node.addEventListener("keydown", (event) => {
      const rules = this.rules();
      const step = event.shiftKey ? rules.fps : 1;
      if (event.key === "ArrowLeft") apply(-step);
      else if (event.key === "ArrowRight") apply(step);
      else if (event.key === "Delete" || event.key === "Backspace") apply(null);
      else return;
      event.preventDefault();
      event.stopPropagation();
    });
    return node;
  }

  // ---- render --------------------------------------------------------------

  render() {
    const piece = this.piece;
    const windows = S.passWindows(piece);
    const blocks = lane(piece);
    const total = this.total();

    for (const block of blocks) this.lengthOf(block.filename);
    this.nodes.clear();

    this.snapEl = el("div", { class: "mmc-snd-snap" });
    this.gapsEl = el("div", { class: "mmc-snd-gaps" });
    // Where the pointer is asked to look while a shot in the reel is hovered.
    // One element moved rather than a wash per pass, because only ever one of
    // them is being asked about.
    this.shotEl = el("div", { class: "mmc-snd-shot" });
    // Two zones rather than one, because the two things in them are not the
    // same kind of thing and must not be able to overlap: the band is placed in
    // time and the gutter belongs to the cards. A ref drawn across a block also
    // read as though it were under it, which is the one thing this surface must
    // not imply.
    const refs = pinned(piece, windows).filter((entry) => entry.take !== "copy");
    this.laneEl = el("div", { class: `mmc-snd-lane${refs.length ? " has-refs" : ""}` }, [
      // Every cut between passes, drawn through the sound rather than only
      // above it. That is the whole point: a cue that runs over a boundary can
      // be seen doing it instead of being measured against the reel.
      el("div", { class: "mmc-snd-cuts" }, windows.slice(1).map((window) =>
        el("div", { class: "mmc-snd-cut", style: { left: this.pct(window.at) } }))),
      this.shotEl,
      // The gaps and the blocks are drawn in two layers rather than one list.
      // They are one list in `band` and have to be — a gap is only knowable
      // from the blocks either side of it — but a drag rebuilds the gaps on
      // every move, and rebuilding a list holding the block the pointer is on
      // would take the pointer with it.
      this.gapsEl,
      el("div", { class: "mmc-snd-band" },
         blocks.map((block) => this.renderBlock(block))),
      ...(refs.length
        ? [el("div", { class: "mmc-snd-refs" }, refs.map((entry) => this.renderPinned(entry)))]
        : []),
      this.snapEl,
      this.renderRead(),
    ]);

    this.host.replaceChildren(
      el("div", { class: "mmc-snd-head" }, [
        el("span", { class: "mmc-snd-name", text: t("Sound") }),
        el("span", {
          class: "mmc-snd-hint",
          text: blocks.length
            ? t("{n} on the lane · {length}", {
                n: t("{count} tracks", { count: blocks.length }),
                length: t("{s} s of {total} s covered", {
                  s: this.seconds(blocks.reduce((n, b) => n + b.frames, 0)).toFixed(1),
                  total: this.seconds(total).toFixed(1),
                }),
              })
            // The empty state is an invitation and says what laying one down
            // does, because what it does is the non-obvious part: the picture is
            // generated against the sound, not laid over it afterwards.
            : t("Every shot writes its own sound. Lay a track down and the picture is "
              + "generated against it instead."),
        }),
        // What the lane can be done to, where the doing is: the affordances are
        // drawn on the blocks, and this is the one line that names them. Only
        // when there is something to drag — on an empty lane the invitation
        // above is the whole message.
        ...(blocks.length
          ? [el("span", { class: "mmc-snd-how", text: t("Drag to move · an end to trim") })]
          : []),
        // No icon, matching the strip's own inline ghosts ("Split"): in this
        // pack an icon means the rail, where a tool is a thing you reach for,
        // and a button sitting in a header is a sentence you finish.
        el("button", {
          class: "mmc-ghost mmc-snd-add",
          text: t("Add track"),
          title: t("Add a track to the lane. It becomes the piece's own sound for as long "
                 + "as it runs, and the shots under it are generated against it."),
          onclick: () => this.add(),
        }),
      ]),
      this.renderReel(windows),
      this.laneEl,
      this.renderRuler(),
    );
    this.paintGaps(blocks);
    this.paintWaves();
    return this.host;
  }

  /**
   * The piece to scale — the bridge between the storyboard above and the lane
   * below.
   *
   * The same picture the node body's reel draws, and deliberately the same
   * reading: a block per pass, filled because its film exists and hollow
   * because it does not. What it adds here is the axis, which is the one thing
   * the card strip cannot give the sound.
   */
  renderReel(windows) {
    const piece = this.piece;
    const all = S.passes(piece);
    return el("div", { class: "mmc-snd-reel" }, windows.map((window, index) => {
      const pass = all[index];
      const head = pass.segments[0];
      const label = pass.segments.length > 1
        ? t("{from}–{to}", { from: pass.start + 1, to: pass.start + pass.segments.length })
        : String(pass.start + 1);
      const state = S.isHeld(head) ? (S.takeOn(head) ? " kept" : " unshot") : "";
      return el("div", {
        class: `mmc-snd-pass${window.clip ? " clip" : ""}${state}`,
        style: { left: this.pct(window.at), width: this.pct(window.frames) },
        // Hovering a shot lights the stretch of lane it owns. The reel says
        // which shot; this says where it is — and where it is is the question
        // the strip above cannot answer, because the strip is not to scale.
        onpointerenter: () => this.showShot(window),
        onpointerleave: () => this.showShot(null),
        title: window.clip
          ? t("Clip {label} · {s} s of supplied footage. Sound over it is mixed, "
            + "not generated — nothing here is sampled.",
              { label, s: this.seconds(window.frames).toFixed(1) })
          : t("Pass {label} · {s} s, from {at} s.",
              { label, s: this.seconds(window.frames).toFixed(1),
                at: this.seconds(window.at).toFixed(1) }),
      }, [el("span", { text: label })]);
    }));
  }

  /** The drag badge, built once per render and moved by `showRead`. */
  renderRead() {
    this.readAtEl = el("span", { class: "mmc-snd-read-at" });
    this.readLenEl = el("span", { class: "mmc-snd-read-len" });
    this.readEl = el("div", { class: "mmc-snd-read" }, [this.readAtEl, this.readLenEl]);
    return this.readEl;
  }

  /**
   * The clock, under the band that is placed on it.
   *
   * The reel above says which shot; this says what second. Without it the lane
   * is a picture of proportions — you can see that a cue is half the piece long
   * and not that it starts at four seconds, which is the number anybody cutting
   * to a downbeat is actually after.
   */
  renderRuler() {
    const span = this.seconds(this.total());
    const step = TICKS.find((size) => span / size <= 12) ?? 900;
    const marks = [];
    for (let at = 0; at < span - step / 2; at += step) marks.push(at);
    return el("div", { class: "mmc-snd-ruler" }, [
      ...marks.map((at, index) => el("div", {
        class: `mmc-snd-tick${index === 0 ? " first" : ""}`,
        style: { left: this.pct(atFrame(at, this.rules())) },
      }, [el("span", { text: tickLabel(at, span) })])),
      // The end is always drawn, whatever the step landed on: it is the length
      // of the piece, and it is the one number on this axis that is a fact
      // about the piece rather than about the ruler.
      el("div", { class: "mmc-snd-tick last", style: { left: "100%" } },
         [el("span", { text: tickLabel(span, span) })]),
    ]);
  }

  /** Light the stretch of lane one shot owns, or nothing. */
  showShot(window) {
    if (!this.shotEl) return;
    this.shotEl.classList.toggle("on", !!window);
    if (!window) return;
    this.shotEl.style.left = this.pct(window.at);
    this.shotEl.style.width = this.pct(window.frames);
  }

  /** One laid-down track. */
  renderBlock(block) {
    const name = block.filename.split("/").pop();
    const node = el("div", {
      class: "mmc-snd-block",
      tabIndex: 0,
      style: { left: this.pct(block.at), width: this.pct(block.frames) },
      title: t("{name} · {from}–{to} of the file, at {at} s of the piece. Drag to move — "
             + "push it half way past a neighbour to trade places with it. Drag an end to "
             + "trim, click to open it.",
               { name, from: formatTime(block.in_s), to: formatTime(block.out_s),
                 at: this.seconds(block.at).toFixed(1) }),
      onclick: (event) => { if (!this.moved) this.openBlock(block.index); event.stopPropagation(); },
    }, [
      el("canvas", { class: "mmc-snd-wave" }),
      // Name and length, not the file's in and out points: the two numbers a
      // block is dragged by are where it sits — which the block's own edges
      // already show — and how long it runs, which nothing else here says. The
      // file's own window stays in the tooltip and in the trim modal, where it
      // is the question being asked.
      el("span", { class: "mmc-snd-label" }, [
        el("span", { class: "mmc-snd-file", text: name }),
        el("span", { class: "mmc-snd-len",
          text: t("{length} s", { length: this.seconds(block.frames).toFixed(1) }) }),
      ]),
      this.grip(block, "head"),
      this.grip(block, "tail"),
    ]);

    this.waves.set(node, block.filename);
    // A drag paints straight onto this node, so it has to be findable by the
    // block it belongs to rather than by walking the lane looking for it.
    this.nodes.set(block.index, node);
    // The body slides; the grips trim. Both are set up here so a block is one
    // object with three grabbable parts rather than three siblings that have to
    // be kept in step.
    this.drag(node, block.index, (from) => {
      const origin = block.at;
      this.moved = false;
      return (frame) => {
        if (frame !== from) this.moved = true;
        this.slide(block.index, origin + (frame - from));
      };
    });
    this.arrows(node, (step) => {
      if (step === null) return this.remove(block.index);
      this.slide(block.index, block.at + step);
    });
    return node;
  }

  grip(block, edge) {
    const node = el("button", {
      class: `mmc-snd-grip ${edge}`,
      "aria-label": edge === "head" ? t("Trim the start") : t("Trim the end"),
      title: edge === "head"
        ? t("Where this track starts, in the piece and in the file at once.")
        : t("Where this track stops. The file is not moved."),
      // A grip is a handle, not a way into the block: without this a press that
      // trims nothing still bubbles a click to the block and opens the modal on
      // top of the drag that was just made.
      onclick: (event) => event.stopPropagation(),
    });
    // The card this trim drags along with it, read once at the top of the
    // gesture and applied once at the bottom of it. Read then because the match
    // is the piece agreeing with the block, and mid-trim it agrees with nothing;
    // applied then because a card resized on every pixel of a drag is a card
    // resized a hundred times to get to one length.
    let matched = null;
    this.drag(node, block.index, () => {
      matched = this.matchedCard(block);
      return (frame) => this.trim(block.index, edge, frame);
    }, () => {
      if (matched === null) return;
      const now = this.at(lane(this.piece), block.index);
      if (now) this.rematch(matched, now.frames / this.rules().fps);
    });
    this.arrows(node, (step) => {
      if (step === null) return;
      const was = this.matchedCard(block);
      this.trim(block.index, edge,
                edge === "head" ? block.at + step : block.at + block.frames + step);
      if (was === null) return;
      const now = this.at(lane(this.piece), block.index);
      if (now) this.rematch(was, now.frames / this.rules().fps);
    });
    return node;
  }

  /** A stretch nobody covered. Perforated, and labelled where there is room —
   *  a gap is not an absence here, it is the model writing the sound. */
  renderGap(part) {
    const wide = part.frames / this.total() > 0.14;
    return el("div", {
      class: "mmc-snd-gap",
      style: { left: this.pct(part.at), width: this.pct(part.frames) },
      title: t("{s} s with nothing laid down. The model writes the sound here — this is "
             + "not silence. Write it in the soundscape and music fields, or lay a "
             + "track across it.", { s: this.seconds(part.frames).toFixed(1) }),
    }, wide ? [el("span", { text: t("generated") })] : []);
  }

  /**
   * An imitation reference, under the card it is attached to.
   *
   * A hairline rather than a block, because it is not placed in time — it
   * belongs to a shot, and the shot decides where it is. Not draggable for the
   * same reason: moving it would be changing which shot it belongs to, which is
   * a thing to do on the card, not by dropping it somewhere.
   */
  renderPinned(entry) {
    const handle = entry.asset.handle;
    return el("div", {
      class: `mmc-snd-ref take-${entry.take}`,
      style: { left: this.pct(entry.at), width: this.pct(entry.frames) },
      title: t("@{handle} is attached to shot {n} as a reference — the model is asked to "
             + "sound like it, not to play it. Open the shot to change or remove it.",
               { handle, n: entry.segment + 1 }),
    }, [el("span", { text: t("{word} @{handle}",
                             { word: t(TAKE_WORD[entry.take] ?? "sounds like"), handle }) })]);
  }

  /** Waveforms, once their peaks arrive. Best effort: an undecodable file
   *  leaves a plain block, which is what every other surface in this pack does
   *  with a waveform it could not get. */
  paintWaves() {
    for (const [node, path] of this.waves) {
      if (!node.isConnected) { this.waves.delete(node); continue; }
      const canvas = node.querySelector(".mmc-snd-wave");
      peaks(path).then((data) => {
        if (canvas.isConnected) draw(canvas, data, WAVE_COLOUR);
      });
    }
  }

  destroy() {
    this.waves.clear();
    this.nodes.clear();
  }
}

// The mark sheet: every stop of the shot on the glass, on one clock.
//
// A staging is stops in time: the shot camera's, and each person's. They used
// to be seen one mover at a time and never as time: the camera's were chips in
// the inspector, a person's were dots on the floor, and a stop was made by
// dragging with the playhead somewhere new. So nothing showed who does what
// when, and a stop once made could not be moved to another moment.
//
// This is a lane for each mover under the glass, a diamond for each stop, and
// one playhead through them all. Drag a diamond to change when; double-click a
// lane to make a stop there; drag anywhere else to scrub. It is the bench's
// clock in every layout, so focus, which folds the reel away, loses neither the
// playhead nor the way to the next shot. The speed lane (`pacelane.js`) sits
// under it, for whoever is being worked on.

import { el, icon } from "./dom.js";
import { t } from "./i18n.js";
import { clamp } from "./blockout.js";
import { PaceLane } from "./pacelane.js";
import * as S from "./state.js";

/** The mover a lane without a piece is for. */
export const CAMERA = "camera";

/** The nearest two stops may be brought together, in seconds. */
const CLOSEST = 0.05;

export class MarkSheet {
  /** `bench`: the window this sheet is in; its playhead and selection are read. */
  constructor(bench) {
    this.bench = bench;
    this.pace = new PaceLane(bench);
    const button = (face, title, onclick, extra = "") => el("button", { class: `mmc-reel-btn mmc-st-key${extra}`, title, "aria-label": title, onclick }, [face]);
    const glyph = (text) => el("span", { text });
    this.playButton = button(icon("play", 16), t("Play (Space)"), () => (bench.playing ? bench.stopPlay() : bench.startPlay()));
    this.addButton = el("button", { class: "mmc-reel-btn", title: t("A stop at the playhead for whoever is selected, or the camera (K)"),
      onclick: () => bench.addStop() }, [el("span", { text: `◆ ${t("Add stop")}` })]);
    // The speed lane is the sheet's second page: there for a stretch that needs
    // a pace of its own, out of the way of the stops otherwise.
    this.paced = false;
    this.paceButton = el("button", { class: "mmc-reel-btn quiet", "aria-pressed": "false",
      title: t("How fast the stretch at the playhead is taken, for whoever is selected or the camera"),
      onclick: () => { this.paced = !this.paced; this.sync(); bench.paint(); } }, [el("span", { text: t("Speed") })]);
    this.paceHost = el("div", { class: "mmc-st-pacehost", hidden: true }, [this.pace.node]);
    this.shotName = el("span", { class: "mmc-st-shotname" });
    this.before = button(glyph("‹"), t("The shot before"), () => this.shot(-1), " quiet");
    this.after = button(glyph("›"), t("The next shot"), () => this.shot(1), " quiet");
    this.stepper = el("div", { class: "mmc-st-stepper" }, [this.before, this.shotName, this.after]);
    this.lanes = el("div", { class: "mmc-st-lanes", hidden: true });
    this.head = el("div", { class: "mmc-st-sheethead" }, [
      button(icon("skipBack", 16), t("The stop before (,)"), () => bench.stepStop(-1)),
      this.playButton,
      button(icon("skipForward", 16), t("The next stop (.)"), () => bench.stepStop(1)),
      bench.timeSaid,
      this.addButton,
      this.paceButton,
      el("span", { class: "mmc-bn-gap" }),
      this.stepper,
    ]);
    this.node = el("div", { class: "mmc-st-sheet" }, [this.head, this.lanes, this.paceHost]);
  }

  shot(by) {
    const to = this.bench.index() + by;
    if (to < 0 || to >= this.bench.timeline.segments.length) return;
    this.bench.select({ kind: "shot", index: to });
  }

  /** Who has a lane: the camera, everyone on the set, and whatever moves in
   *  this shot. -> `[{ id, name, hue, marks }]`; `marks` is null for somebody
   *  the shot gives no stop, who stands where the set has them. */
  movers() {
    const bench = this.bench, set = bench.set(), staging = bench.staging();
    if (!set || !staging) return [];
    const out = [{ id: CAMERA, name: t("Camera"), hue: "var(--mmc-role-motion, #6ebeff)", marks: staging.camera }];
    for (const piece of set.objects) {
      const marks = staging.people?.[piece.id] ?? null;
      if (piece.kind !== "person" && !marks) continue;
      out.push({ id: piece.id, name: bench.labelOf(piece), marks,
        hue: piece.plays ? `var(--mmc-tag-${S.tagIndex(piece.plays) % 8})` : "var(--mmc-dim)" });
    }
    return out;
  }

  /** The lanes, as the staging stands. Rebuilt when the piece or the selection
   *  changes; `sync` moves the playhead between those. */
  render() {
    const bench = this.bench;
    const movers = bench.view === "take" ? [] : this.movers();
    this.lanes.hidden = !movers.length;
    this.stepper.hidden = bench.single === true;
    const count = bench.timeline.segments.length;
    this.shotName.textContent = t("Shot {n} of {count}", { n: bench.index() + 1, count });
    this.before.disabled = bench.index() <= 0;
    this.after.disabled = bench.index() >= count - 1;
    if (!movers.length) { this.lanes.replaceChildren(); this.sync(); return; }
    const seconds = Math.max(0.01, bench.seconds());
    const pct = (at) => `${(clamp(at / seconds, 0, 1) * 100).toFixed(3)}%`;
    const held = bench.moverId();
    const ruler = el("div", { class: "mmc-st-track mmc-st-ruler", onpointerdown: (event) => this.scrub(event, ruler, null) },
      Array.from({ length: Math.floor(seconds + 1e-6) + 1 }, (_, second) => el("span", {
        class: `mmc-st-tick${seconds - second < 0.4 ? " end" : ""}`, style: { left: pct(second) }, text: t("{n} s", { n: second }) })));
    const rows = [el("div", { class: "mmc-st-lane" }, [el("span", { class: "mmc-st-lanename" }), ruler])];
    for (const mover of movers) {
      const track = el("div", { class: "mmc-st-track", style: { "--hue": mover.hue }, title: t("Drag to move the playhead. Double-click to add a stop here."),
        onpointerdown: (event) => { if (event.target === track) this.scrub(event, track, mover); } });
      const marks = mover.marks ?? [];
      for (let k = 0; k + 1 < marks.length; k++) {
        const a = marks[k], b = marks[k + 1];
        const still = Math.hypot(b.x - a.x, (b.y ?? 0) - (a.y ?? 0), b.z - a.z) < 0.02;
        track.append(el("span", { class: `mmc-st-leg${still ? " still" : ""}`, style: { left: pct(a.t), width: pct(b.t - a.t) } }));
      }
      if (!marks.length) track.append(el("span", { class: "mmc-st-stop rest", style: { left: "0%" }, title: t("Stays where the set has them in this shot") }));
      marks.forEach((mark, k) => track.append(this.stop(mover, mark, k, track, pct)));
      rows.push(el("div", { class: `mmc-st-lane${mover.id === held ? " held" : ""}` }, [
        el("button", { class: "mmc-st-lanename", title: mover.id === CAMERA ? t("The shot camera") : t("Select {who}", { who: mover.name }),
          onclick: () => this.pick(mover) }, [el("span", { class: "mmc-st-hue", style: { "--tag": mover.hue } }), el("span", { text: mover.name })]),
        track,
      ]));
    }
    this.playhead = el("div", { class: "mmc-st-playhead" });
    this.lanes.replaceChildren(...rows, el("div", { class: "mmc-st-playwrap" }, [this.playhead]));
    this.sync();
  }

  /** One stop, as a diamond: pressed, it is gone to; dragged, it is another moment. */
  stop(mover, mark, k, track, pct) {
    const bench = this.bench;
    const said = () => t("{s} s", { s: mark.t.toFixed(2).replace(/0$/, "") });
    const node = el("button", { class: "mmc-st-stop", style: { left: pct(mark.t) }, "data-t": String(mark.t),
      "aria-label": t("{who}, stop at {s}", { who: mover.name, s: said() }), title: t("{s}: press to go to it, drag to change when", { s: said() }) });
    node.addEventListener("pointerdown", (event) => {
      if (event.button) return;
      event.preventDefault();
      event.stopPropagation();
      bench.stopPlay();
      const marks = mover.marks, seconds = bench.seconds();
      const rect = track.getBoundingClientRect(), x0 = event.clientX;
      const low = k > 0 ? marks[k - 1].t + CLOSEST : 0, high = k < marks.length - 1 ? marks[k + 1].t - CLOSEST : seconds;
      let moved = false;
      const move = (at) => {
        if (!moved && Math.abs(at.clientX - x0) < 3) return;
        moved = true;
        const when = clamp((at.clientX - rect.left) / Math.max(1, rect.width), 0, 1) * seconds;
        mark.t = clamp(Math.round(when * 20) / 20, Math.min(low, high), Math.max(low, high));
        node.style.left = pct(mark.t);
        node.dataset.t = String(mark.t);
        bench.at.t = mark.t;
        bench.paint();
      };
      const up = () => {
        node.removeEventListener("pointermove", move);
        node.removeEventListener("pointerup", up);
        node.removeEventListener("pointercancel", up);
        bench.at.t = mark.t;
        if (moved) {
          bench.say(t("{who}'s stop is now at {s}.", { who: mover.name, s: said() }));
          this.hold(mover);
          bench.commit();
        } else this.pick(mover);
      };
      try { node.setPointerCapture(event.pointerId); } catch { /* a pointer already gone */ }
      node.addEventListener("pointermove", move);
      node.addEventListener("pointerup", up);
      node.addEventListener("pointercancel", up);
    });
    return node;
  }

  /** Put the selection on a lane's mover without a redraw of its own. */
  hold(mover) {
    const bench = this.bench;
    bench.sel = mover.id === CAMERA ? { kind: "shot", index: bench.index() } : { kind: "thing", id: mover.id };
  }

  pick(mover) {
    const bench = this.bench;
    bench.select(mover.id === CAMERA ? { kind: "shot", index: bench.index() } : { kind: "thing", id: mover.id });
  }

  /** The moment under the pointer on a track, onto a stop where it is all but on one. */
  when(event, track, mover) {
    const rect = track.getBoundingClientRect(), seconds = this.bench.seconds();
    const at = clamp((event.clientX - rect.left) / Math.max(1, rect.width), 0, 1) * seconds;
    const stop = (mover?.marks ?? []).find((mark) => Math.abs(((mark.t - at) / Math.max(0.01, seconds)) * rect.width) < 7);
    return stop ? stop.t : Math.round(at * 20) / 20;
  }

  scrub(event, track, mover) {
    if (event.button) return;
    event.preventDefault();
    const bench = this.bench;
    bench.stopPlay();
    // A second press on the same lane in the same place is a stop there. Told
    // here and not by a dblclick: the first press redraws the lanes, so the
    // second lands on a track that was not there for the first.
    const again = this.pressed;
    this.pressed = mover ? { id: mover.id, x: event.clientX, at: event.timeStamp } : null;
    if (mover && again?.id === mover.id && Math.abs(again.x - event.clientX) < 6 && event.timeStamp - again.at < 450) {
      this.pressed = null;
      this.addAt(event, track, mover);
      return;
    }
    const seek = (at) => { bench.goTo(bench.index(), this.when(at, track, mover)); bench.paint(); };
    seek(event);
    const up = () => {
      track.removeEventListener("pointermove", seek);
      track.removeEventListener("pointerup", up);
      track.removeEventListener("pointercancel", up);
      // A lane pressed is its mover's: the keys and the speed lane follow.
      if (mover && bench.moverId() !== mover.id) this.pick(mover); else bench.renderSide();
    };
    try { track.setPointerCapture(event.pointerId); } catch { /* a pointer already gone */ }
    track.addEventListener("pointermove", seek);
    track.addEventListener("pointerup", up);
    track.addEventListener("pointercancel", up);
  }

  addAt(event, track, mover) {
    const bench = this.bench;
    bench.goTo(bench.index(), this.when(event, track, null));
    this.hold(mover);
    bench.addStop();
  }

  /** What moves with the playhead: the line, the stops under it, the buttons. */
  sync() {
    const bench = this.bench;
    const seconds = Math.max(0.01, bench.seconds());
    if (this.playhead) this.playhead.style.left = `${(clamp(bench.at.t / seconds, 0, 1) * 100).toFixed(3)}%`;
    for (const node of this.lanes.querySelectorAll(".mmc-st-stop[data-t]")) {
      node.classList.toggle("here", Math.abs(Number(node.dataset.t) - bench.at.t) < 0.07);
    }
    if (this.playButton.dataset.playing !== String(bench.playing)) {
      this.playButton.dataset.playing = String(bench.playing);
      this.playButton.replaceChildren(icon(bench.playing ? "pause" : "play", 16));
    }
    this.addButton.disabled = !bench.set() || bench.view !== "stage" || bench.stopHere() != null;
    const paced = this.paced && !this.lanes.hidden;
    this.paceHost.hidden = !paced;
    this.paceButton.hidden = this.lanes.hidden;
    this.paceButton.setAttribute("aria-pressed", String(this.paced));
    if (paced) this.pace.paint();
  }
}

// The speed lane: how fast the thing you are working on moves through its shot.
//
// Under the glass, for whoever is selected, or the camera when nobody is. The
// stops keep their times: raising the curve in one place lowers it elsewhere in
// the same stretch, so everyone still arrives when they did. A stretch is what
// lies between two stops, and the buttons act on the one the playhead is in.

import { el } from "./dom.js";
import { t } from "./i18n.js";
import { clamp, cameraAt, poseAt, legSpeed, legEnds, strideOf, MOST_PACE } from "./blockout.js";

/** Ways to take a stretch: [id, label, speed leaving, speed arriving], the
 *  speeds as multiples of the stretch's average. */
const WAYS = [
  ["natural", "Natural", null, null, "The speed the stops give by themselves"],
  ["steady", "Steady", 1, 1, "One speed the whole way"],
  ["start", "Start gently", 0, 1.5, "From standing still"],
  ["stop", "Stop gently", 1.5, 0, "To standing still"],
  ["rushin", "Rush in", 0.2, 2.6, "Slow at first, fast on arrival"],
  ["rushoff", "Rush off", 2.6, 0.2, "Fast at first, slow on arrival"],
];
const SAMPLES = 120;
const PAD = { left: 10, right: 10, top: 16, bottom: 8 };
const same = (a, b) => Math.abs((a ?? -1) - (b ?? -1)) < 0.01;

export class PaceLane {
  /** `bench`: the window this lane is in; its playhead and selection are read. */
  constructor(bench) {
    this.bench = bench;
    this.title = el("span", { class: "mmc-st-pacename" });
    this.ways = el("div", { class: "mmc-reel-seg", role: "group", "aria-label": t("How this stretch is taken") });
    this.wait = el("button", { class: "mmc-reel-btn quiet", text: t("Wait until here"),
      title: t("Stay at the last stop until the playhead, then go"), onclick: () => this.waitHere() });
    this.now = el("span", { class: "mmc-st-pacenow" });
    this.canvas = el("canvas", { "aria-label": t("Speed"), onpointerdown: (event) => this.press(event) });
    this.node = el("div", { class: "mmc-st-pace", hidden: true }, [
      el("div", { class: "mmc-st-pacehead" }, [this.title, this.ways, this.wait]),
      this.canvas,
      this.now,
    ]);
  }

  /** Who the lane is about: `{ marks, person, name }`, or null off a set. */
  mover() {
    const staging = this.bench.staging();
    if (!staging) return null;
    const thing = this.bench.selectedThing();
    if (thing?.kind === "person") {
      return { marks: staging.people?.[thing.id] ?? [], person: true, name: this.bench.labelOf(thing) };
    }
    return { marks: staging.camera, person: false, name: t("Camera") };
  }

  /** Metres for a mover that goes anywhere, degrees for a camera that only turns. */
  unitOf({ marks, person }) {
    if (person) return "m";
    return marks.some((mark, k) => k && strideOf(marks, k - 1, "m") > 0.1) ? "m" : "deg";
  }

  /** The stretch the playhead is in, or the nearest one. */
  leg(marks) {
    let i = 0;
    while (i < marks.length - 2 && marks[i + 1].t <= this.bench.at.t) i++;
    return i;
  }

  speedAt(mover, unit, at) {
    const { marks } = mover;
    const read = (when) => (mover.person ? poseAt(marks, when) : cameraAt(marks, when));
    const from = Math.max(marks[0].t, at - 0.02), to = Math.min(marks[marks.length - 1].t, at + 0.02);
    if (to - from < 1e-4) return 0;
    return legSpeed(read(from), read(to), to - from, unit);
  }

  /** The points that can be dragged: one at each end of each stretch, joined
   *  into one where both sides of a stop have the same speed. */
  handles(mover, unit) {
    const { marks } = mover;
    const ends = [];
    for (let i = 0; i < marks.length - 1; i++) {
      const average = strideOf(marks, i, unit) / Math.max(1e-6, marks[i + 1].t - marks[i].t);
      if (average < (unit === "m" ? 0.02 : 0.5)) continue;
      const [out, into] = legEnds(marks, i);
      const a = { t: marks[i].t, speed: out * average, sides: [{ mark: marks[i], key: "out", average }] };
      const before = ends[ends.length - 1];
      if (before?.t === a.t && Math.abs(before.speed - a.speed) < 0.05 * Math.max(before.speed, a.speed, 0.01)) {
        before.sides.push(a.sides[0]);
      } else ends.push(a);
      ends.push({ t: marks[i + 1].t, speed: into * average, sides: [{ mark: marks[i + 1], key: "in", average }] });
    }
    return ends;
  }

  xOf(at, width) {
    return PAD.left + (at / Math.max(0.01, this.bench.seconds())) * (width - PAD.left - PAD.right);
  }

  yOf(speed, height) {
    return height - PAD.bottom - (speed / this.top) * (height - PAD.top - PAD.bottom);
  }

  /** The whole lane, as things stand. Called with every frame of the glass. */
  paint() {
    const mover = this.mover();
    this.node.hidden = !mover;
    if (!mover) return;
    const { marks } = mover;
    const moves = marks.length > 1;
    const unit = this.unitOf(mover);
    this.title.textContent = t("{who}: speed", { who: mover.name });
    this.paintHead(mover, moves, unit);
    const width = this.canvas.clientWidth, height = this.canvas.clientHeight;
    if (!width || !height) return;
    const dpr = Math.min(2, globalThis.devicePixelRatio || 1);
    if (this.canvas.width !== Math.round(width * dpr)) this.canvas.width = Math.round(width * dpr);
    if (this.canvas.height !== Math.round(height * dpr)) this.canvas.height = Math.round(height * dpr);
    const context = this.canvas.getContext("2d");
    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    context.clearRect(0, 0, width, height);
    const style = getComputedStyle(this.canvas);
    const ink = style.color, accent = style.getPropertyValue("--mmc-accent").trim() || "#6ebeff";
    context.font = `11px ${style.fontFamily}`;
    context.fillStyle = ink;
    if (!moves) {
      context.globalAlpha = 0.7;
      context.fillText(mover.person
        ? t("Stays put. Move the playhead, then drag them somewhere, and they walk there.")
        : t("Stays still. Move the playhead, then move the camera, and it travels there."), PAD.left, height / 2 + 4);
      context.globalAlpha = 1;
      return;
    }
    const first = marks[0].t, last = marks[marks.length - 1].t;
    const speeds = Array.from({ length: SAMPLES + 1 }, (_, k) => {
      const at = first + ((last - first) * k) / SAMPLES;
      return [at, this.speedAt(mover, unit, at)];
    });
    const handles = this.handles(mover, unit);
    // Held through a drag, so the curve does not rescale under the pointer.
    if (!this.dragging) {
      this.top = 1.25 * Math.max(unit === "m" ? 1 : 10, ...speeds.map((point) => point[1]), ...handles.map((handle) => handle.speed));
    }
    // The stretch the buttons act on.
    const leg = this.leg(marks);
    const x0 = this.xOf(marks[leg].t, width), x1 = this.xOf(marks[leg + 1].t, width);
    context.globalAlpha = 0.07;
    context.fillRect(x0, PAD.top - 6, x1 - x0, height - PAD.top - PAD.bottom + 6);
    context.globalAlpha = 0.25;
    context.fillRect(PAD.left, height - PAD.bottom, width - PAD.left - PAD.right, 1);
    for (const mark of marks) context.fillRect(this.xOf(mark.t, width), PAD.top - 6, 1, height - PAD.top - PAD.bottom + 6);
    context.globalAlpha = 1;
    context.strokeStyle = accent;
    context.lineWidth = 2;
    context.beginPath();
    speeds.forEach(([at, speed], k) => context[k ? "lineTo" : "moveTo"](this.xOf(at, width), this.yOf(speed, height)));
    context.stroke();
    for (const handle of handles) {
      context.beginPath();
      context.arc(this.xOf(handle.t, width), this.yOf(handle.speed, height), 5, 0, Math.PI * 2);
      context.fillStyle = handle.sides.some((side) => side.mark[side.key] !== undefined) ? accent : style.backgroundColor;
      context.fill();
      context.stroke();
    }
    context.fillStyle = ink;
    context.fillRect(this.xOf(this.bench.at.t, width), 0, 1.5, height);
  }

  paintHead(mover, moves, unit) {
    const { marks } = mover;
    const leg = moves ? this.leg(marks) : -1;
    const at = this.bench.at.t;
    const inside = moves && at > marks[0].t && at < marks[marks.length - 1].t;
    const speed = inside ? this.speedAt(mover, unit, at) : 0;
    const said = unit === "deg" ? t("{n}° a second", { n: Math.round(speed) }) : t("{n} m a second", { n: speed.toFixed(1) });
    const word = !mover.person || !inside ? "" : speed < 0.05 ? t("standing") : speed < 0.5 ? t("slow walk")
      : speed <= 2 ? t("walk") : speed <= 3.2 ? t("jog") : t("run");
    this.now.textContent = moves ? (word ? `${said} · ${word}` : said) : "";
    this.ways.hidden = !moves;
    this.wait.hidden = !moves || !inside || marks.some((mark) => Math.abs(mark.t - at) < 0.14);
    const out = marks[leg]?.out, into = marks[leg + 1]?.in;
    const current = !moves ? null : out === undefined && into === undefined ? "natural"
      : WAYS.find((way) => same(way[2], out) && same(way[3], into))?.[0] ?? null;
    // Rebuilt only when it would differ: this runs with every frame played.
    const key = `${leg}|${current}`;
    if (key === this.headKey) return;
    this.headKey = key;
    this.ways.replaceChildren(...WAYS.map(([id, label, a, b, note]) => el("button", {
      "aria-pressed": String(id === current), title: t(note), onclick: () => this.take(a, b),
    }, [el("span", { text: t(label) })])));
  }

  /** Take the stretch at the playhead one of the ways. */
  take(out, into) {
    const mover = this.mover();
    if (!mover || mover.marks.length < 2) return;
    this.bench.stopPlay();
    const i = this.leg(mover.marks);
    const put = (mark, key, value) => { if (value === null) delete mark[key]; else mark[key] = value; };
    put(mover.marks[i], "out", out);
    put(mover.marks[i + 1], "in", into);
    this.bench.commit();
  }

  /** Stay at the stop before the playhead until the playhead. */
  waitHere() {
    const mover = this.mover();
    if (!mover || mover.marks.length < 2) return;
    this.bench.stopPlay();
    const i = this.leg(mover.marks);
    const before = mover.marks[i];
    const { in: _in, ...held } = before;
    held.t = Math.round(this.bench.at.t * 20) / 20;
    delete before.out;
    mover.marks.splice(i + 1, 0, held);
    this.bench.commit();
  }

  press(event) {
    const mover = this.mover();
    if (event.button || !mover) return;
    event.preventDefault();
    this.bench.stopPlay();
    const rect = this.canvas.getBoundingClientRect();
    const { width, height } = rect;
    const near = (handle) => Math.hypot(this.xOf(handle.t, width) - (event.clientX - rect.left),
                                        this.yOf(handle.speed, height) - (event.clientY - rect.top));
    const handles = mover.marks.length > 1 ? this.handles(mover, this.unitOf(mover)) : [];
    const grab = handles.filter((handle) => near(handle) < 12).sort((a, b) => near(a) - near(b))[0];
    let changed = false;
    const move = (at) => {
      if (grab) {
        const speed = Math.max(0, ((rect.bottom - PAD.bottom - at.clientY) / (height - PAD.top - PAD.bottom)) * this.top);
        for (const { mark, key, average } of grab.sides) {
          mark[key] = Math.round(clamp(speed / average, 0, MOST_PACE) * 100) / 100;
        }
        changed = true;
      } else {
        const along = (at.clientX - rect.left - PAD.left) / Math.max(1, width - PAD.left - PAD.right);
        this.bench.goTo(this.bench.index(), clamp(along, 0, 1) * this.bench.seconds());
      }
      this.bench.paint();
    };
    const up = () => {
      this.canvas.removeEventListener("pointermove", move);
      this.canvas.removeEventListener("pointerup", up);
      this.canvas.removeEventListener("pointercancel", up);
      this.dragging = false;
      if (changed) this.bench.commit();
      else this.bench.renderSide();
    };
    this.dragging = Boolean(grab);
    if (!grab) move(event);
    try { this.canvas.setPointerCapture(event.pointerId); } catch { /* a pointer already gone */ }
    this.canvas.addEventListener("pointermove", move);
    this.canvas.addEventListener("pointerup", up);
    this.canvas.addEventListener("pointercancel", up);
  }
}

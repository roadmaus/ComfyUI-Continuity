// Image to 3D: a picture in, a textured mesh out, and every stage in between.
//
// **Not a bench.** The benches are a file on a light box with an instrument
// beside it, and their room (`styles/bench.js`) is built for that: a rail of
// dials, a rectangle with a seam through it, a foot that runs the job. A mesh is
// not a rectangle. It is something you walk around, and the most useful thing
// the tool can show is not a before-and-after but *where the picture was taken
// from* — so the stage here is the whole room, a WebGL scene (`liftstage.js`)
// with the picture standing at the camera Pixal3D estimated for it and the mesh
// under its rays. The settings are a narrow drawer beside it; the build is a
// track along its foot.
//
// **The track is the pipeline, and it is real.** Six stages in the order core
// runs them — cut out, camera, structure, shape, texture, bake — each mapped to
// the nodes that make it up (`creator/lift.py` files every node under one). The
// build is an ordinary graph on ComfyUI's queue, so every node's state arrives
// on `progress_state` and each stage's result on `executed`; the track is drawn
// from exactly that and nothing is estimated. A finished stage can be pressed to
// put what it made back on the stage — the cut-out, the camera's rays, the
// voxels, the clay shape, the painted mesh — which is how a build that went
// wrong says where it went wrong.
//
// **Changing a setting does not throw the mesh away.** It is still a real answer
// to the settings it was built with, and the track says it is out of date
// rather than clearing it. Building again with nothing changed draws a new seed:
// the queue's cache would otherwise hand back the same mesh instantly, and a
// button that does nothing the second time is a broken button.

import { el, icon, mark, dragsFiles, mountOverlay, keepScroll } from "./dom.js";
import { upload, viewUrl, outputUrl, liftModels, liftRun, revealFolder,
         blockoutFrames, blockoutWrite } from "./api.js";
import { openPicker } from "./picker.js";
import { t } from "./i18n.js";
import { follow, stopPrompt, busy as queueBusy, watch as watchQueue } from "./queue.js";

/** Where a dropped picture is uploaded to, under input/. */
const SUBFOLDER = "continuity/lift";
/** Where the finished mesh lands, under output/ — `outputs.MESHES`. */
const SHELF = "continuity/meshes";
const PREFS_KEY = "mmc.lift";

const SIDES = ["front", "left", "back", "right"];
const STAGES = ["cutout", "camera", "structure", "shape", "texture", "bake"];

// The settings a build takes, their choices, and their defaults — the frontend's
// half of `lift.CHOICES` / `lift.DEFAULTS`.
const DEFAULTS = { model: "pixal", detail: "standard", background: "remove",
                   surface: "pbr", texture: 2048, faces: 200000 };
const FACES_MIN = 10000;
const FACES_MAX = 2000000;

/** The face slider is logarithmic: 10k to 2M is two and a half decades, and a
 *  linear slider would spend nine tenths of its travel above half a million. */
const facesAt = (fraction) =>
  Math.round(FACES_MIN * Math.pow(FACES_MAX / FACES_MIN, fraction) / 1000) * 1000;
const fractionOf = (faces) =>
  Math.log(Math.max(FACES_MIN, faces) / FACES_MIN) / Math.log(FACES_MAX / FACES_MIN);
const count = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : `${Math.round(n / 1000)}k`);
const seconds = (ms) => {
  const s = Math.max(0, ms / 1000);
  return s < 60 ? `${Math.round(s)} s` : `${Math.floor(s / 60)} min ${String(Math.round(s % 60)).padStart(2, "0")} s`;
};

/** When a stage's clock starts: where the last stage before it stopped, or
 *  where the prompt began executing. A stage's own "running" report is no
 *  use for this — the cut-out and the camera finish between two progress
 *  events, so timing them from it read 0 s, and the loaders a stage waits on
 *  are part of what it costs. */
export function stageStart(times, stage, began, now) {
  const ends = STAGES.slice(0, STAGES.indexOf(stage))
    .map((earlier) => times[earlier]?.end).filter((end) => end !== undefined);
  return ends.length ? Math.max(...ends) : began ?? now;
}

/**
 * Which diffusion model a build runs. The frontend's half of `lift.model_role`:
 * one picture falls back to the multi-view model when that is the only
 * Pixal3D checkpoint on the machine.
 */
export function roleOf(settings, views, models = null) {
  if (settings.model === "trellis") return "trellis";
  if (views > 1) return "pixal_views";
  if (models && !models.pixal?.found && models.pixal_views?.found) return "pixal_views";
  return "pixal";
}

/**
 * Which models a build needs. The frontend's half of `lift.needs`, so the drawer
 * can say what is missing before Build is pressed rather than after the queue
 * reaches a loader.
 */
export function needs(settings, views, models = null) {
  const many = views > 1;
  const roles = [roleOf(settings, views, models), "dino", "shape_vae"];
  if (settings.surface !== "none") roles.push("texture_vae");
  if (settings.background === "remove") roles.push("cutout");
  if (settings.model === "pixal" && !many) roles.push("moge");
  return roles;
}

let open = null;

/**
 * Open the tool. `source` is an asset (`{path, kind}`) to start from — the
 * piece's still, usually; `back` puts the dashboard up again from the wordmark.
 */
export function openLift(options = {}) {
  open?.close();
  return new Promise((resolve) => {
    open = new Lift(options, resolve);
    open.mount();
  });
}

class Lift {
  constructor(options, resolve) {
    this.resolve = resolve;
    this.back = options.back ?? null;
    this.views = { front: null, left: null, back: null, right: null };
    const source = options.source;
    if (source?.path && (source.kind ?? "image") === "image") this.views.front = source;
    this.settings = { ...DEFAULTS, ...this.remembered() };
    this.seed = 42;
    this.models = null;
    this.stage = null;               // the LiftStage, once three.js has loaded
    this.running = false;
    this.plan = null;
    this.promptId = null;
    this.state = {};                 // stage -> wait | run | done | skip | fail
    this.progress = {};              // stage -> 0..1
    this.times = {};                 // stage -> {start, end}
    this.began = null;               // when the prompt left the queue
    this.results = {};               // stage -> the stage node's record
    this.viewing = null;
    this.built = null;               // the settings the mesh on the stage was built with
    this.error = null;
    this.mode = "textured";
    this.picture = true;
    this.atCamera = false;
    this.turning = null;
    this.queue = { remaining: 0, running: false };
  }

  remembered() {
    try {
      const saved = JSON.parse(localStorage.getItem(PREFS_KEY) || "{}");
      return Object.fromEntries(Object.entries(saved).filter(([key]) => key in DEFAULTS));
    } catch { return {}; }
  }

  remember() {
    try { localStorage.setItem(PREFS_KEY, JSON.stringify(this.settings)); } catch { /* private mode */ }
  }

  // ---- the room ---------------------------------------------------------------

  mount() {
    this.glass = el("div", { class: "mmc-lf-glass" });
    this.slots = el("div", { class: "mmc-lf-slots" });
    this.holderNote = el("div", { class: "mmc-lf-holdnote" });
    this.modes = el("div", { class: "mmc-lf-seg mmc-lf-modes", role: "group", "aria-label": t("Surface view") });
    this.pictureChip = el("button", { class: "mmc-lf-chip", onclick: () => this.togglePicture() },
                          [el("i"), el("span", { text: t("Picture in scene") })]);
    this.cameraChip = el("button", { class: "mmc-lf-chip", onclick: () => this.toPicture() },
                         [el("span", { text: t("Picture's camera") })]);
    this.caption = el("div", { class: "mmc-lf-caption" });
    this.empty = el("div", { class: "mmc-lf-empty" });
    this.track = el("div", { class: "mmc-lf-track", role: "list", "aria-label": t("Build stages") });
    this.runButton = el("button", { class: "mmc-lf-run", onclick: () => this.press() });
    this.note = el("div", { class: "mmc-lf-est" });
    this.toastBox = el("div", { class: "mmc-lf-toast", role: "status" });

    const stageBox = el("section", { class: "mmc-lf-stage", "aria-label": t("3D stage") }, [
      this.glass,
      this.empty,
      el("div", { class: "mmc-lf-holder" }, [this.slots, this.holderNote]),
      el("div", { class: "mmc-lf-views" }, [
        this.modes,
        el("div", { class: "mmc-lf-chips" }, [this.pictureChip, this.cameraChip]),
      ]),
      this.caption,
      this.toastBox,
      el("div", { class: "mmc-lf-foot" }, [
        this.track,
        el("div", { class: "mmc-lf-go" }, [this.runButton, this.note]),
      ]),
    ]);

    this.drawerBody = keepScroll(el("div", { class: "mmc-lf-drawer-body" }));
    this.out = el("div", { class: "mmc-lf-out" });
    const drawer = el("aside", { class: "mmc-lf-drawer", "aria-label": t("Settings") },
                      [this.drawerBody, this.out]);

    this.sheet = el("div", { class: "mmc-lf" }, [
      el("div", { class: "mmc-bn-bar" }, [
        this.back
          ? el("button", {
              class: "mmc-bn-home", title: t("Back to the tools"),
              onclick: () => { this.close(); this.back(); },
            }, [
              el("span", { class: "mmc-bn-logo" }, [mark(20)]),
              el("span", { text: "Continuity" }),
              el("span", { class: "mmc-bn-caret" }, [icon("chevron", 12)]),
            ])
          : el("span", { class: "mmc-bn-mark" }, [
              el("span", { class: "mmc-bn-logo" }, [mark(20)]),
              el("span", { class: "mmc-bn-word", text: "Continuity" }),
            ]),
        el("span", { class: "mmc-bn-slash", text: "/" }),
        el("span", { class: "mmc-bn-here", text: t("Image to 3D") }),
        el("span", { class: "mmc-bn-gap" }),
        el("button", { class: "mmc-close", text: "✕", title: t("Close"), onclick: () => this.close() }),
      ]),
      el("div", { class: "mmc-lf-room" }, [stageBox, drawer]),
    ]);

    this.overlay = el("div", {
      class: "mmc-overlay mmc-bn-over",
      // A picture dropped anywhere is the front, unless it lands on a slot —
      // the slot's own handler takes it first. Files only: the stage is
      // dragged across all the time, and a room that lit up as a drop target
      // while somebody orbited the mesh would be claiming a file nobody held.
      ondragover: (event) => {
        if (!dragsFiles(event)) return;
        event.preventDefault();
        this.overlay.classList.add("dropping");
      },
      ondragleave: (event) => { if (event.target === this.overlay) this.overlay.classList.remove("dropping"); },
      ondrop: (event) => {
        if (!dragsFiles(event)) return;
        event.preventDefault();
        this.overlay.classList.remove("dropping");
        const file = event.dataTransfer?.files?.[0];
        if (file) this.take("front", file);
      },
    }, [this.sheet]);

    this.unmount = mountOverlay(this.overlay, () => this.close());
    this.unwatchQueue = watchQueue((state) => {
      this.queue = state;
      if (this.overlay.isConnected && this.running) this.paintRun();
    });
    this.render();
    this.boot();
  }

  /** Three.js on demand: 800 KB nobody should pay for until they open this. */
  async boot() {
    try {
      const { LiftStage } = await import("./liftstage.js");
      if (!this.overlay.isConnected) return;
      this.stage = new LiftStage(this.glass);
      this.stage.onLeave = () => {
        if (!this.atCamera) return;
        this.atCamera = false;
        this.stage.pictureOpacity(1);
        this.paintViews();
      };
    } catch (error) {
      console.error("[Continuity] the 3D stage could not start", error);
      this.error = t("The 3D stage could not start: {message}", { message: String(error.message || error) });
      this.render();
    }
    try {
      this.models = await liftModels();
    } catch (error) {
      this.models = null;
      this.error ??= String(error.message || error);
    }
    if (this.overlay.isConnected) this.render();
  }

  close() {
    if (open === this) open = null;
    this.unwatchQueue?.();
    this.following?.abandon();
    clearInterval(this.clock);
    this.stage?.dispose();
    this.stage = null;
    this.unmount?.();
    this.resolve?.();
  }

  render() {
    this.paintSlots();
    this.paintViews();
    this.paintTrack();
    this.paintRun();
    this.paintDrawer();
    this.paintOut();
    this.paintCaption();
  }

  // ---- the pictures -------------------------------------------------------------

  viewCount() { return SIDES.filter((side) => this.views[side]).length; }

  paintSlots() {
    const pixal = this.settings.model === "pixal";
    const sides = pixal ? SIDES : ["front"];
    this.slots.replaceChildren(...sides.map((side) => this.slot(side)));
    this.holderNote.textContent = !this.views.front
      ? ""
      : pixal && this.viewCount() === 1
        ? t("Add left, back or right views and the hidden sides are built from them too.")
        : "";
  }

  slot(side) {
    const asset = this.views[side];
    const label = { front: t("Front"), left: t("Left"), back: t("Back"), right: t("Right") }[side];
    const drop = {
      ondragover: (event) => { if (dragsFiles(event)) { event.preventDefault(); event.stopPropagation(); } },
      ondrop: (event) => {
        if (!dragsFiles(event)) return;
        event.preventDefault();
        event.stopPropagation();
        this.overlay.classList.remove("dropping");
        const file = event.dataTransfer?.files?.[0];
        if (file) this.take(side, file);
      },
    };
    if (!asset) {
      return el("button", {
        class: "mmc-lf-slot empty", title: t("Add a {side} view", { side: label.toLowerCase() }),
        onclick: () => this.browse(side), ...drop,
      }, [el("b", { text: "+" }), el("span", { text: label })]);
    }
    const remove = side === "front" ? null : el("i", {
      class: "mmc-lf-x", text: "✕", title: t("Remove this view"),
      onclick: (event) => { event.stopPropagation(); this.setView(side, null); },
    });
    return el("button", {
      class: "mmc-lf-slot", title: t("Replace the {side} picture", { side: label.toLowerCase() }),
      onclick: () => this.browse(side), ...drop,
    }, [
      el("img", { src: viewUrl(asset.path, { preview: true }), alt: "", draggable: false }),
      el("span", { text: label }),
      remove,
    ]);
  }

  async browse(side) {
    const chosen = await openPicker({
      kinds: ["image", "renders"], kind: "image", single: true,
      capacity: () => ({ used: 0, max: 1, filesLeft: 1 }),
    });
    const asset = chosen?.[0];
    if (!asset || !this.overlay.isConnected) return;
    if (asset.kind && asset.kind !== "image") {
      this.toast(t("Pick a picture — a clip has no single view to lift."));
      return;
    }
    this.setView(side, asset);
  }

  async take(side, file) {
    try {
      const asset = await upload(file, SUBFOLDER);
      if (asset.kind !== "image") throw new Error(t("Pick a picture — a clip has no single view to lift."));
      if (this.overlay.isConnected) this.setView(side, asset);
    } catch (error) {
      this.error = String(error.message || error);
      this.paintRun();
    }
  }

  setView(side, asset) {
    this.views[side] = asset;
    // The front is what everything is posed to; without one there is nothing
    // the other views are the sides *of*.
    if (side === "front" && !asset) for (const other of SIDES) this.views[other] = null;
    this.error = null;
    this.render();
  }

  // ---- the settings ---------------------------------------------------------------

  paintDrawer() {
    const s = this.settings;
    const many = this.viewCount() > 1;
    const pixal = s.model === "pixal";
    const seg = (key, options) => el("div", { class: "mmc-lf-seg wide", role: "group" },
      options.map(([value, label]) => el("button", {
        text: label, "aria-pressed": s[key] === value,
        onclick: () => this.change({ [key]: value }),
      })));
    const field = (label, control, note = null, extra = null) => el("div", { class: "mmc-lf-field" }, [
      el("div", { class: "mmc-lf-label" }, [el("span", { text: label }), extra]),
      control,
      note ? el("p", { class: "mmc-lf-note", text: note }) : null,
    ]);

    const modelName = !pixal ? "TRELLIS.2"
      : roleOf(s, this.viewCount(), this.models) === "pixal_views" ? t("Pixal3D multi-view") : "Pixal3D";
    const modelSub = many ? t("From {n} views of one object", { n: this.viewCount() })
      : this.views.front ? t("From one picture") : t("Add a picture to start");
    const faces = el("output", { class: "mmc-lf-value", text: count(s.faces) });
    const slider = el("input", {
      type: "range", min: 0, max: 1000, value: Math.round(fractionOf(s.faces) * 1000),
      "aria-label": t("Faces"),
      oninput: (event) => {
        const next = facesAt(Number(event.target.value) / 1000);
        faces.textContent = count(next);
        this.settings.faces = next;
      },
      onchange: () => this.change({}),
    });

    const children = [
      el("div", { class: "mmc-lf-model" }, [
        el("div", {}, [
          el("div", { class: "mmc-lf-modelname", text: modelName }),
          el("div", { class: "mmc-lf-modelsub", text: modelSub }),
        ]),
        el("div", { class: "mmc-lf-dots", "aria-hidden": "true" },
           SIDES.map((side) => el("i", { class: this.views[side] ? "on" : "" }))),
      ]),
      field(t("Model"), seg("model", [["pixal", "Pixal3D"], ["trellis", "TRELLIS.2"]]),
            pixal ? t("Keeps the mesh where the picture put it, seen from the picture's own camera.")
                  : t("Builds a centred object from one picture, not aligned to its camera.")),
      field(t("Detail"), seg("detail", [["standard", t("Standard")], ["high", t("High")]]),
            s.detail === "high" ? t("Shape at 1536. Slower, and heavier on memory.")
                                : t("Shape at 1024. High builds at 1536, slower and heavier on memory.")),
      field(t("Background"), seg("background", [["remove", t("Remove it")], ["keep", t("Already cut out")]]),
            s.background === "keep" ? t("Reads the picture's own transparency as the cut-out.") : null),
      field(t("Surface"), seg("surface", [["pbr", t("Full PBR")], ["color", t("Colour")], ["none", t("Shape only")]]),
            s.surface === "pbr" ? t("Unwrapped, with colour, roughness, metal, normal and occlusion maps baked.")
              : s.surface === "color" ? t("Colours painted onto the vertices. No unwrap, no bake.")
                : t("Geometry alone. The texture model is never loaded.")),
      s.surface === "pbr"
        ? field(t("Texture size"), seg("texture", [[1024, "1K"], [2048, "2K"], [4096, "4K"]]))
        : null,
      field(t("Faces"), slider,
            t("Decimated to this after the remesh. Lower is lighter to stage and shoot around."), faces),
    ];

    const missing = this.missing();
    if (missing.length) {
      children.push(el("div", { class: "mmc-lf-missing" }, [
        el("div", { class: "mmc-lf-label" }, [el("span", { text: t("Not on this machine") })]),
        ...missing.map((entry) => el("div", { class: "mmc-lf-need" }, [
          el("span", { class: "mmc-lf-needfile", text: `models/${entry.folder}/${entry.file}` }),
          el("a", { href: entry.url, target: "_blank", rel: "noopener", text: t("Download") }),
        ])),
      ]));
    }

    const maps = this.results.bake?.maps;
    if (maps && this.state.bake === "done") {
      const names = [["base_color", t("Colour")], ["roughness", t("Rough")], ["metallic", t("Metal")],
                     ["normal_map", t("Normal")], ["occlusion", t("Occlusion")]];
      children.push(el("div", { class: "mmc-lf-rule" }), field(t("Baked maps"), el("div", { class: "mmc-lf-maps" },
        names.filter(([key]) => maps[key]).map(([key, label]) => el("a", {
          class: "mmc-lf-map", href: outputUrl(maps[key]), target: "_blank", rel: "noopener",
        }, [el("img", { src: outputUrl(maps[key]), alt: "" }), el("span", { text: label })])))));
    }
    this.drawerBody.replaceChildren(...children.filter(Boolean));
  }

  /** The models this build needs that the machine does not have. */
  missing() {
    if (!this.models) return [];
    return needs(this.settings, this.viewCount(), this.models)
      .map((role) => this.models[role])
      .filter((entry) => entry && !entry.found);
  }

  change(patch) {
    Object.assign(this.settings, patch);
    // TRELLIS.2 reads one picture; the side views stay in the slots but are
    // hidden while it is picked, and come back with Pixal3D.
    this.remember();
    this.render();
  }

  /** The settings a build sends, as a comparable string. */
  signature() {
    const views = Object.fromEntries(SIDES.map((side) => [side, this.views[side]?.path ?? null]));
    return JSON.stringify({ ...this.settings, views: this.settings.model === "pixal" ? views : { front: views.front } });
  }

  stale() { return this.built !== null && this.built !== this.signature(); }

  // ---- the build ----------------------------------------------------------------

  press() {
    if (this.running) { this.stop(); return; }
    // Nothing changed since the last build: a new seed, or the cache would hand
    // the same mesh straight back.
    if (this.built !== null && !this.stale()) this.seed += 1;
    this.build();
  }

  async build() {
    if (!this.views.front || this.missing().length) return;
    const pixal = this.settings.model === "pixal";
    const views = Object.fromEntries(SIDES
      .filter((side) => this.views[side] && (pixal || side === "front"))
      .map((side) => [side, this.views[side].path]));
    this.error = null;
    this.running = true;
    this.plan = null;
    this.state = {};
    this.progress = {};
    this.times = {};
    this.began = null;
    this.results = {};
    this.atCamera = false;
    const signature = this.signature();
    const following = follow({
      started: () => { this.began = performance.now(); },
      progress: (nodes) => this.heard(nodes),
      executed: (_node, output) => {
        const record = output?.continuity_lift?.[0];
        if (record) this.arrived(record);
      },
    });
    this.following = following;
    this.clock = setInterval(() => this.paintTrack(), 1000);
    this.render();
    try {
      const answer = await liftRun({ views, ...this.settings, seed: this.seed });
      this.plan = answer.plan;
      this.name = answer.name;
      for (const stage of STAGES) this.state[stage] = answer.plan.skipped.includes(stage) ? "skip" : "wait";
      following.expect(answer.prompt_id);
      this.promptId = answer.prompt_id;
      this.render();
      await following.promise;
      this.built = signature;
      const final = Object.values(this.results).find((record) => record.final);
      if (final) this.toast(t("Written to output/{path}", { path: `${final.mesh.subfolder}/${final.mesh.filename}` }));
    } catch (error) {
      following.abandon();
      for (const stage of STAGES) if (this.state[stage] === "run") this.state[stage] = "fail";
      if (error.cancelled) this.error = t("Stopped.");
      else if (error.missing) { this.error = null; this.models = await liftModels().catch(() => this.models); }
      else this.error = String(error.message || error);
    } finally {
      this.running = false;
      this.promptId = null;
      clearInterval(this.clock);
      if (this.overlay.isConnected) this.render();
    }
  }

  stop() {
    if (this.promptId) stopPrompt(this.promptId);
  }

  /** `progress_state`: which stages have a node running, and how far. */
  heard(nodes) {
    if (!this.plan) return;
    const running = new Map();
    for (const [key, entry] of Object.entries(nodes)) {
      const stage = this.plan.stages[entry.display_node_id ?? entry.node_id ?? key] ?? this.plan.stages[key];
      if (!stage || entry.state !== "running") continue;
      const fraction = entry.max ? (entry.value ?? 0) / entry.max : null;
      running.set(stage, Math.max(running.get(stage) ?? 0, fraction ?? 0));
    }
    for (const [stage, fraction] of running) {
      if (this.state[stage] === "wait") {
        this.state[stage] = "run";
        this.times[stage] = { start: stageStart(this.times, stage, this.began, performance.now()) };
      }
      if (this.state[stage] === "run") this.progress[stage] = fraction;
    }
    this.paintTrack();
    this.paintRun();
  }

  /** A stage's node said what it made. */
  arrived(record) {
    const stage = record.stage;
    this.results[stage] = record;
    this.state[stage] = "done";
    this.progress[stage] = 1;
    const time = this.times[stage] ??= { start: stageStart(this.times, stage, this.began, performance.now()) };
    time.end = performance.now();
    // An earlier stage whose nodes were all cached never reported running;
    // having heard from a later one, it is done too.
    for (const earlier of STAGES.slice(0, STAGES.indexOf(stage))) {
      if (this.state[earlier] === "wait" || this.state[earlier] === "run") this.state[earlier] = "done";
    }
    this.look(stage);
    this.render();
  }

  // ---- the track --------------------------------------------------------------------

  paintTrack() {
    const names = { cutout: t("Cut out"), camera: t("Camera"), structure: t("Structure"),
                    shape: t("Shape"), texture: t("Texture"), bake: t("Bake") };
    this.track.replaceChildren(...STAGES.map((stage, index) => {
      const state = this.state[stage] ?? (this.skipsNow(stage) ? "skip" : "idle");
      const time = this.times[stage];
      const said = state === "skip" ? t("skipped")
        : state === "wait" ? t("waiting")
          : state === "fail" ? t("stopped")
            : state === "run" ? (time ? seconds(performance.now() - time.start) : t("running"))
              : state === "done" && time?.end ? seconds(time.end - time.start) : "";
      const done = state === "done" && this.results[stage];
      const step = el("button", {
        class: `mmc-lf-step ${state}`, role: "listitem",
        "aria-current": done && this.viewing === stage && !this.running,
        disabled: !done,
        onclick: () => this.look(stage),
      }, [
        el("span", { class: "mmc-lf-steptop" }, [
          el("span", { class: "mmc-lf-stepn", text: String(index + 1) }),
          el("span", { class: "mmc-lf-stepname", text: names[stage] }),
        ]),
        el("span", { class: "mmc-lf-steptime", text: said }),
        el("span", { class: "mmc-lf-fill" }),
      ]);
      step.style.setProperty("--p", String(state === "done" ? 1 : this.progress[stage] ?? 0));
      return step;
    }));
    this.track.classList.toggle("stale", this.stale());
  }

  /** Which stages the current settings would skip — drawn before any build. */
  skipsNow(stage) {
    const s = this.settings;
    if (stage === "camera") return !(s.model === "pixal" && this.viewCount() <= 1);
    if (stage === "cutout") return false;
    if (stage === "texture") return s.surface === "none";
    if (stage === "bake") return s.surface !== "pbr";
    return false;
  }

  paintRun() {
    const missing = this.missing().length > 0;
    const ready = !!this.views.front && !missing;
    this.runButton.className = "mmc-lf-run" + (this.running ? " stop" : this.built && !this.stale() ? " quiet" : "");
    this.runButton.textContent = this.running ? t("Stop") : this.built ? t("Build again") : t("Build mesh");
    this.runButton.disabled = !this.running && !ready;
    this.runButton.title = this.built && !this.stale() && !this.running
      ? t("Nothing has changed, so this draws a different take.") : "";
    const waiting = this.running && !STAGES.some((stage) => ["run", "done"].includes(this.state[stage]));
    const note = this.error ? this.error
      : !this.views.front ? t("Add a picture to lift.")
        : missing ? t("Download the missing models first.")
          : waiting && (this.queue.remaining > 1 || queueBusy()) ? t("Waiting for the render ahead of it")
            : this.stale() ? t("Settings changed since this build")
              : this.built && !this.running ? t("Built in {time}", { time: seconds(this.elapsed()) })
                : this.running ? t("Building on this machine") : "";
    this.note.textContent = note;
    this.note.classList.toggle("bad", !!this.error);
  }

  elapsed() {
    const spans = Object.values(this.times).filter((time) => time.end);
    if (!spans.length) return 0;
    return Math.max(...spans.map((time) => time.end)) - Math.min(...spans.map((time) => time.start));
  }

  // ---- the stage ---------------------------------------------------------------------

  /** The picture's camera, when the model has one: `{fov, pad}`. */
  cameraOf() {
    const camera = this.plan?.camera;
    if (!camera) return null;
    const fov = camera.fov ?? this.results.camera?.value;
    return fov ? { fov, pad: camera.pad } : null;
  }

  /** Put one stage's result on the stage. */
  async look(stage) {
    this.viewing = stage;
    const record = this.results[stage];
    const stageView = this.stage;
    this.paintTrack();
    this.paintCaption();
    this.paintViews();
    if (!stageView || !record) return;
    const cutout = this.results.cutout?.image ? outputUrl(this.results.cutout.image) : null;
    const camera = this.cameraOf();
    if (stage === "cutout") {
      // No camera yet, or none at all for TRELLIS.2: the cut-out still stands
      // on a notional one, so there is something to see at the first stage.
      stageView.setPicture(camera ?? { fov: 40, pad: 1 }, cutout);
      await stageView.show(null);
      await stageView.toPicture();
      stageView.pictureOpacity(1);
      return;
    }
    stageView.setPicture(camera, cutout);
    stageView.showPicture(this.picture);
    if (stage === "camera") {
      await stageView.show(null);
      await stageView.toOverview();
      return;
    }
    const look = stage === "structure" || stage === "shape" ? "clay" : "own";
    try {
      await stageView.show(outputUrl(record.mesh), look);
    } catch (error) {
      this.error = t("That mesh could not be loaded: {message}", { message: String(error.message || error) });
      this.paintRun();
      return;
    }
    if (stage === "structure" || !this.framed) {
      this.framed = true;
      await stageView.toOverview();
    }
    stageView.setMode(this.mode);
  }

  paintViews() {
    const record = this.results[this.viewing];
    const meshUp = !!record?.mesh;
    const clayOnly = this.viewing === "structure" || this.viewing === "shape";
    const modes = [["textured", t("Textured")], ["clay", t("Clay")], ["wire", t("Wire")], ["normals", t("Normals")]];
    this.modes.replaceChildren(...modes.map(([mode, label]) => el("button", {
      text: label,
      disabled: !meshUp || (mode === "textured" && clayOnly),
      "aria-pressed": meshUp && (this.mode === mode || (clayOnly && mode === "clay" && this.mode === "textured")),
      onclick: () => { this.mode = mode; this.stage?.setMode(mode); this.paintViews(); },
    })));
    const camera = !!this.cameraOf();
    this.pictureChip.disabled = !camera;
    this.pictureChip.setAttribute("aria-pressed", String(camera && this.picture));
    this.cameraChip.disabled = !camera;
    this.cameraChip.setAttribute("aria-pressed", String(this.atCamera));
  }

  togglePicture() {
    this.picture = !this.picture;
    this.stage?.showPicture(this.picture);
    this.paintViews();
  }

  async toPicture() {
    if (!this.stage || !this.cameraOf()) return;
    const cutout = this.results.cutout?.image ? outputUrl(this.results.cutout.image) : null;
    if (!this.stage.picture) this.stage.setPicture(this.cameraOf(), cutout);
    this.stage.showPicture(true);
    await this.stage.toPicture();
    // Half the picture at its own camera: the mesh is meant to sit exactly
    // under it, and this is where that is checked.
    this.atCamera = !!this.results[this.viewing]?.mesh;
    if (this.atCamera) this.stage.pictureOpacity(0.5);
    this.paintViews();
    this.paintCaption();
  }

  paintCaption() {
    const record = this.results[this.viewing];
    let text = null;
    let small = null;
    if (this.atCamera) {
      text = t("Seen from the picture's camera: the mesh sits under its own picture");
      small = t("drag to leave");
    } else if (record) {
      const faces = record.faces ? count(record.faces) : "";
      ({
        cutout: () => { text = this.settings.background === "keep" ? t("The picture's own cut-out") : t("Background removed"); small = t("the crop the model reads"); },
        camera: () => { text = t("Camera found: {fov}° field of view", { fov: (record.value ?? 0).toFixed(1) }); small = t("every pixel now has a ray"); },
        structure: () => { text = t("Sparse structure"); small = t("where the object is, in 32³ voxels"); },
        shape: () => { text = t("Shape: {faces} faces", { faces }); small = t("remeshed and decimated, no colour yet"); },
        texture: () => { text = t("Colour from the picture's own pixels"); small = t("painted onto the vertices"); },
        bake: () => { text = t("{faces} faces, unwrapped and baked", { faces }); small = t("{size}² maps", { size: this.settings.texture }); },
      })[this.viewing]?.();
    }
    this.caption.hidden = !text;
    this.caption.replaceChildren(...(text ? [el("span", { text }), small ? el("small", { text: small }) : null].filter(Boolean) : []));
    const nothing = !Object.keys(this.results).length;
    this.empty.hidden = !nothing || this.running;
    this.empty.replaceChildren(
      el("b", { text: this.views.front ? t("Ready to build") : t("Add a picture to lift") }),
      el("span", { text: this.views.front
        ? t("The mesh stands here, under the picture it was lifted from.")
        : t("Drop one anywhere, or press the Front slot. One object on a plain ground lifts best.") }));
    if (nothing && this.running) this.empty.hidden = true;
  }

  // ---- the file --------------------------------------------------------------------------

  paintOut() {
    const final = Object.values(this.results).find((record) => record.final);
    const turning = this.turning;
    this.out.classList.toggle("waiting", !final);
    this.out.replaceChildren(
      el("div", { class: "mmc-lf-file" }, [
        el("div", { class: "mmc-lf-glyph", text: "GLB" }),
        el("div", { class: "mmc-lf-fileword" }, [
          el("div", { class: "mmc-lf-filename", text: final ? final.mesh.filename : `${this.name ?? "mesh"}.glb` }),
          el("div", { class: "mmc-lf-filepath", text: final
            ? t("{size} MB in output/{folder}", { size: (final.bytes / 1048576).toFixed(1), folder: SHELF })
            : t("Lands in output/{folder}", { folder: SHELF }) }),
        ]),
      ]),
      el("div", { class: "mmc-lf-doors" }, [
        el("button", {
          class: "mmc-lf-door", disabled: !final,
          onclick: () => revealFolder("output", SHELF).catch((error) => this.toast(String(error.message || error))),
        }, [el("b", { text: t("Show in folder") }), el("span", { text: t("The GLB, beside the renders") })]),
        el("button", {
          class: "mmc-lf-door", disabled: !final || !!turning,
          onclick: () => this.turntable(),
        }, [
          el("b", { text: turning ? t("Rendering {n}%", { n: turning }) : t("Turntable clip") }),
          el("span", { text: t("One orbit, written to the input folder to cite with @") }),
        ]),
      ]),
    );
  }

  /** One orbit of the finished mesh, rendered here and written as a clip. */
  async turntable() {
    const final = Object.values(this.results).find((record) => record.final);
    if (!final || !this.stage || this.turning) return;
    this.turning = 0;
    this.paintOut();
    try {
      if (this.viewing !== final.stage) await this.look(final.stage);
      const blobs = await this.stage.turntable({
        onFrame: (done, of) => {
          const n = Math.round((done / of) * 90);
          if (n !== this.turning) { this.turning = n; this.paintOut(); }
        },
      });
      const token = Array.from(crypto.getRandomValues(new Uint32Array(4)),
                               (word) => word.toString(16).padStart(8, "0")).join("");
      for (let start = 0; start < blobs.length; start += 24) {
        await blockoutFrames(token, blobs.slice(start, start + 24)
          .map((blob, offset) => ({ index: start + offset, blob })));
      }
      this.turning = 95;
      this.paintOut();
      const written = await blockoutWrite({ token, fps: 24, op: "turntable" });
      this.toast(t("Turntable written to input/{path}", { path: written.path }));
    } catch (error) {
      this.toast(String(error.message || error));
    } finally {
      this.turning = null;
      if (this.overlay.isConnected) this.paintOut();
    }
  }

  toast(text) {
    this.toastBox.textContent = text;
    this.toastBox.classList.add("show");
    clearTimeout(this.toastTimer);
    this.toastTimer = setTimeout(() => this.toastBox.classList.remove("show"), 3200);
  }
}

// Game Forge: a game's assets, kept in one project, checked and exported.
//
// The design is `specs/continuity-game-forge-spec.md`; the server half is
// `creator/forge/`, and this is one of its two clients. The other is the CLI
// (`skills/continuity-forge/forge.py`), and **the bench may do nothing the CLI
// cannot**: every press here is one call to a `/continuity/forge/*` route, the
// same table `tests/test_forge_parity.py` holds the CLI against. Nothing is
// computed here that the server does not also say.
//
// **Built for the artist, not for the manifest.** The first bench was the
// other benches' room — one rail of stops down the left — and everything the
// forge has went into that rail: the project's look and engines, the asset
// list, the add form and the selected asset's recipe as raw JSON, one column
// deep enough to scroll twice. A person making a game's art asks three things
// in turn, so the room is three places in a row:
//
//   - **the shelf** (left): the game's things, grouped the way an artist
//     thinks of them (characters, sprites, tiles), each with its picture;
//   - **the light box** (middle): the thing you are on, pixel-true, with the
//     check and the export at its foot because they are about what is on it;
//   - **the inspector** (right): what the thing is — its masters and its
//     recipe as a form in plain words, the rarely touched fields folded away.
//
// What the whole *project* is — its look, the style sentence, the palette, the
// engines — is set up once and seldom touched, so it is a drawer behind the
// project's name, not a third of every screen. And the pose stage is a page of
// its own (`forge/posepage.js`): posing a mannequin wants the middle of the
// room to be a 3D viewport, not a picture.
//
// **The light box shows pixels as pixels.** A contact sheet of a 16×16 sprite
// or a check overlay is pixel art, and pixel art scaled by a fraction is a
// smear with uneven pixels. So the glass shows it at a whole-number zoom, with
// no smoothing, and only shrinks — smoothly — what is larger than the glass.
// The shelf's thumbnails are drawn the same way.
//
// **Looking is an act the project records.** Opening an asset draws its
// contact sheet, and the server counts that as somebody having looked
// (`review.sheet`); `status` stops calling the asset "not looked at". That is
// true here — the sheet is on the glass — and it is the same call the CLI's
// `sheet` makes for an agent.
//
// Making is the one press that runs a model. It queues the asset's renders on
// ComfyUI's queue (`/make`) and the bench asks after them (`/jobs`) every few
// seconds while any are out: asking is what brings a finished take into its
// asset, so nothing waits on a socket the CLI would not have. Building,
// checking and exporting are arithmetic on the masters, and wait for nothing.

import { el, icon, mark, spinner, dragsFiles, mountOverlay, keepScroll, dismissable, placeNear } from "./dom.js";
import { forgeCall, forgeFileUrl, upload } from "./api.js";
import { openPicker } from "./picker.js";
import { PosePage } from "./forge/posepage.js";
import { t } from "./i18n.js";

/** Where a picture brought in from this machine lands before the import moves
 *  it into the project — the input folder's forge shelf, as the CLI does. */
export const SUBFOLDER = "forge";

/** The project shelf, for the drawer's last line (`outputs.FORGE`). */
const SHELF = "output/continuity/forge/";

/** Where an asset stands, as the shelf's tooltip says it. */
const STATUS = {
  planned: () => t("Planned: nothing made yet"),
  made: () => t("Made, not yet exported everywhere"),
  exported: () => t("Exported to every engine"),
  stale: () => t("Changed since it was made"),
};

/** The kinds the shelf groups by, in the order a game is usually drawn, and
 *  what each group is called. Material, texture and sound are the 3D and
 *  audio steps' (spec §12), not yet made here. */
const KINDS = {
  character: { group: () => t("Characters"), one: () => t("Character") },
  sprite: { group: () => t("Sprites"), one: () => t("Sprite") },
  tile: { group: () => t("Tiles"), one: () => t("Tile") },
  tileset: { group: () => t("Tilesets"), one: () => t("Tileset") },
  background: { group: () => t("Backgrounds"), one: () => t("Background") },
  icon: { group: () => t("Icons and items"), one: () => t("Icon or item") },
  ui: { group: () => t("Interface"), one: () => t("Interface piece") },
};

/** A recipe field's name as an artist would say it. The schema's own
 *  description is the field's tooltip; a field missing here shows its key. */
const LABELS = {
  prompt: () => t("Description"),
  size: () => t("Master size"),
  references: () => t("Made from"),
  seed: () => t("Seed"),
  family: () => t("Model"),
  post: () => t("Post-steps"),
  pivot: () => t("Anchor"),
  layer: () => t("Layer"),
  alpha: () => t("Transparent"),
  targets: () => t("Per-engine overrides"),
  notes: () => t("Notes"),
  costumes: () => t("Costumes"),
  expressions: () => t("Expressions"),
  items: () => t("Held items"),
  directions: () => t("Directions"),
  of: () => t("Animates"),
  frame: () => t("Frame size"),
  animations: () => t("Animations"),
  sheet: () => t("Sheet layout"),
  tile: () => t("Tile size"),
  seamless: () => t("Wraps"),
  tiles: () => t("Tiles"),
  terrain: () => t("Terrain set"),
  layers: () => t("Parallax layers"),
  wrap: () => t("Wraps sideways"),
  icon: () => t("Icon size"),
  set: () => t("Pieces"),
  nine_slice: () => t("9-slice borders"),
};

/** Fields every kind has that an artist seldom touches: folded under More.
 *  The description and the kind's own fields stay out in the open. */
const MORE = new Set(["size", "references", "seed", "family", "post", "pivot", "layer", "alpha", "targets", "notes"]);

/** What cannot be changed on an asset once it is made. */
const FIXED = new Set(["name", "kind"]);

/** The bench, or null. One at a time: it is the room. */
let open = null;

/**
 * Open the forge.
 *
 * @param {object} [options]
 * @param {Function} [options.back]  where the wordmark goes once the bench is
 *   closed; absent, the wordmark is not a door.
 * @param {string} [options.project]  a project to open on
 * @returns {Promise<void>}  resolves when the bench is closed
 */
export function openForge(options = {}) {
  open?.close();
  return new Promise((resolve) => {
    open = new Forge(options, resolve);
    open.mount();
  });
}

/** A field's value as the form shows it, and back. Sizes and points are two
 *  numbers; names are a comma list; an emptied number is "the default". */
function shown(value) {
  if (value == null) return "";
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

/** "8 assets", or nothing when the listing does not say. */
function assetCount(n) {
  if (n == null) return null;
  return n === 1 ? t("1 asset") : t("{n} assets", { n });
}

class Forge {
  constructor(options, resolve) {
    this.resolve = resolve;
    this.back = options.back ?? null;
    this.name = options.project ?? null;
    this.catalogue = null;     // {kinds, modes, targets}
    this.projects = [];
    this.project = null;       // project.json, as the server keeps it
    this.rows = [];            // status rows
    this.schemas = {};         // kind -> its recipe's JSON schema
    this.page = "assets";      // "assets" | "poses"
    this.asset = null;         // the selected asset's name
    this.view = "sheet";       // what is on the glass: "sheet" | "check"
    this.target = null;        // the engine the foot checks and exports
    this.sheet = null;         // {asset, path, at}
    this.report = null;        // the last check of `target`: {target, byAsset}
    this.exported = null;      // the last export's answer
    this.working = null;       // what is running, as a sentence, or null
    this.error = null;
    this.draft = { name: "", mode: "pixel", targets: ["generic"] };
    this.raw = null;           // the recipe as JSON text, while it is being edited as such
    this.more = false;         // whether the inspector's More is open
    this.removing = false;     // the first press of Remove
    this.drawer = false;       // the project's settings, open
    this.poses = null;         // the pose page, while it is mounted
    this.takesTimer = null;    // the next look at takes on the queue
  }

  // ---- the room ---------------------------------------------------------------

  mount() {
    this.here = el("span", { class: "mmc-fg-crumb" });
    this.tabs = el("div", { class: "mmc-fg-tabs", role: "tablist", "aria-label": t("Forge pages") });
    this.settingsButton = el("button", {
      class: "mmc-fg-barbutton", title: t("The project's look, palette and engines"),
      onclick: () => this.toggleDrawer(),
    }, [icon("sliders", 15), el("span", { text: t("Project") })]);
    this.room = el("div", { class: "mmc-fg-room" });
    this.drawerEl = el("aside", { class: "mmc-fg-drawer", "aria-label": t("Project settings") });
    this.sheetEl = el("div", { class: "mmc-bn mmc-fg" }, [
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
        el("span", { class: "mmc-bn-here", text: t("Game Forge") }),
        this.here,
        el("span", { class: "mmc-bn-gap" }),
        this.tabs,
        el("span", { class: "mmc-bn-gap" }),
        this.settingsButton,
        el("button", { class: "mmc-close", text: "✕", title: t("Close the bench"), onclick: () => this.close() }),
      ]),
      el("div", { class: "mmc-fg-body" }, [this.room, this.drawerEl]),
    ]);
    // A file over the room is a master for the asset on the glass — the same
    // gesture the other benches take, and here it means import. On the pose
    // page a file is a clip, and that page takes it.
    this.overlay = el("div", {
      class: "mmc-overlay mmc-bn-over",
      ondragover: (event) => {
        if (!dragsFiles(event) || !this.dropTarget()) return;
        event.preventDefault();
        this.overlay.classList.add("dropping");
      },
      ondragleave: (event) => { if (event.target === this.overlay || !this.overlay.contains(event.relatedTarget)) this.overlay.classList.remove("dropping"); },
      ondrop: (event) => {
        if (!dragsFiles(event)) return;
        event.preventDefault();
        this.overlay.classList.remove("dropping");
        const files = [...(event.dataTransfer?.files ?? [])];
        if (!files.length) return;
        if (this.page === "poses") this.poses?.dropped(files);
        else if (this.selected()) this.importFiles(files);
      },
    }, [this.sheetEl]);
    this.unmount = mountOverlay(this.overlay, () => {
      if (this.drawer) { this.toggleDrawer(false); return; }
      this.close();
    });
    this.watcher = new ResizeObserver(() => this.fitGlass());
    this.render();
    this.load();
  }

  dropTarget() {
    return this.page === "poses" ? Boolean(this.poses) : Boolean(this.selected());
  }

  close() {
    if (open === this) open = null;
    clearTimeout(this.takesTimer);
    this.poses?.unmount();
    this.poses = null;
    this.watcher?.disconnect();
    this.unmount?.();
    this.resolve?.();
  }

  alive() { return this.overlay.isConnected; }

  /** Run one call with the bench saying what it is doing, and keep the
   *  server's sentence when it refuses. -> the answer, or null. */
  async run(sentence, call) {
    this.working = sentence;
    this.error = null;
    this.paintStatus();
    try {
      return await call();
    } catch (error) {
      this.error = error.message || String(error);
      return null;
    } finally {
      this.working = null;
      if (this.alive()) this.render();
    }
  }

  // ---- loading ----------------------------------------------------------------

  async load() {
    await this.run(t("Reading the projects"), async () => {
      const [catalogue, listing] = await Promise.all([
        forgeCall("/capabilities", {}, { get: true }),
        forgeCall("/projects", {}, { get: true }),
      ]);
      this.catalogue = catalogue;
      this.projects = listing.projects;
    });
    if (this.name && this.alive()) this.openProject(this.name);
  }

  async openProject(name) {
    const answer = await this.run(t("Opening {name}", { name }), () =>
      forgeCall("/show", { project: name }, { get: true }));
    if (!answer) return;
    const switched = name !== this.project?.name;
    this.name = name;
    this.project = answer.project;
    this.rows = answer.status.assets;
    if (!this.project.targets.includes(this.target)) this.target = this.project.targets[0];
    this.report = null;
    this.exported = null;
    if (switched) {
      this.poses?.unmount();
      this.poses = null;
      this.mounted = null;
      this.asset = null;
    }
    if (!this.rows.some((row) => row.name === this.asset)) this.asset = this.rows.find((r) => r.status !== "planned")?.name ?? this.rows[0]?.name ?? null;
    await this.loadSchemas();
    this.render();
    if (this.asset) this.look();
    this.watchTakes();
  }

  /** Each kind's recipe schema, once: the inspector's form is drawn from it. */
  async loadSchemas() {
    const kinds = [...new Set(this.rows.map((row) => row.kind))].filter((kind) => !this.schemas[kind]);
    const answers = await Promise.all(kinds.map((kind) =>
      forgeCall("/schema", { kind }, { get: true }).catch(() => null)));
    kinds.forEach((kind, i) => { if (answers[i]) this.schemas[kind] = answers[i]; });
  }

  /** The project and its status again, after anything that changed them. */
  async refresh() {
    const answer = await forgeCall("/show", { project: this.name }, { get: true }).catch(() => null);
    if (!answer || !this.alive()) return;
    this.project = answer.project;
    this.rows = answer.status.assets;
    await this.loadSchemas();
    this.render();
    this.watchTakes();
  }

  // ---- making -------------------------------------------------------------------

  /** Whether `kind` is one `/make` renders, as the server says. */
  makes(kind) {
    return (this.catalogue?.makes ?? []).includes(kind);
  }

  /** Queue renders: `{assets}` or `{missing: true}`. What could not be made
   *  is said, not dropped. */
  async make(body, sentence) {
    const answer = await this.run(sentence, () => forgeCall("/make", { project: this.name, ...body }));
    if (!answer) return;
    if (answer.skipped.length) {
      this.error = t("Skipped: {list}", { list: answer.skipped.map((s) => `${s.asset} (${s.why})`).join("; ") });
    }
    await this.refresh();
  }

  /** While a take is out, look again in a few seconds. */
  watchTakes() {
    clearTimeout(this.takesTimer);
    if (!this.alive() || !this.rows.some((row) => row.making)) return;
    this.takesTimer = setTimeout(() => this.pollTakes(), 3000);
  }

  async pollTakes() {
    const out = this.rows.filter((row) => row.making).map((row) => row.making);
    const answer = await forgeCall("/jobs", { project: this.name, takes: out.join(",") }, { get: true }).catch(() => null);
    if (!this.alive()) return;
    const ended = (answer?.takes ?? []).filter((take) => take.state !== "queued");
    if (!ended.length) { this.watchTakes(); return; }
    const said = ended.flatMap((take) => [
      ...(take.state === "failed" ? [`${take.asset}: ${take.problem}`] : []),
      ...(take.warnings ?? []).map((warning) => `${take.asset}: ${warning.problem}`),
    ]);
    if (said.length) this.error = said.join(" ");
    await this.refresh();
    if (ended.some((take) => take.asset === this.asset && take.state === "done")) this.look();
  }

  leaveProject() {
    this.poses?.unmount();
    this.poses = null;
    this.name = this.project = this.asset = this.sheet = this.report = this.exported = null;
    this.rows = [];
    this.drawer = false;
    this.page = "assets";
    this.render();
    this.run(t("Reading the projects"), async () => {
      this.projects = (await forgeCall("/projects", {}, { get: true })).projects;
    });
  }

  selected() { return this.rows.find((row) => row.name === this.asset) ?? null; }

  recipe() { return this.project?.assets.find((r) => r.name === this.asset) ?? null; }

  targetLabel(id) {
    return this.catalogue?.targets.find((target) => target.id === id)?.label ?? id;
  }

  // ---- what the presses do ------------------------------------------------------

  async createProject() {
    const { name, mode, targets } = this.draft;
    const answer = await this.run(t("Making {name}", { name }), () =>
      forgeCall("/new", { project: name.trim(), mode, targets }));
    if (!answer) return;
    this.draft = { name: "", mode: "pixel", targets: ["generic"] };
    this.projects.push({ name: answer.project.name, mode, targets, assets: 0 });
    this.openProject(answer.project.name);
  }

  async toggleTarget(id) {
    const on = this.project.targets.includes(id);
    const answer = await this.run(on ? t("Removing an engine") : t("Adding an engine"), () =>
      forgeCall(on ? "/target/rm" : "/target/add", { project: this.name, target: id }));
    if (!answer) return;
    this.project = answer.project;
    if (!this.project.targets.includes(this.target)) this.target = this.project.targets[0];
    this.report = null;
    this.refresh();
  }

  async setStyle(changes, sentence = t("Saving the look")) {
    const answer = await this.run(sentence, () => forgeCall("/style", { project: this.name, style: changes }));
    if (answer) this.refresh();
  }

  async addAsset(kind, name) {
    const answer = await this.run(t("Adding {name}", { name }), () =>
      forgeCall("/add", { project: this.name, asset: { kind, name: name.trim() } }));
    if (!answer) return false;
    this.choose(answer.asset.name);
    await this.refresh();
    return true;
  }

  choose(name) {
    if (this.asset === name) return;
    this.asset = name;
    this.raw = null;
    this.removing = false;
    this.sheet = null;
    if (this.view === "check" && !this.report) this.view = "sheet";
    this.render();
    this.look();
  }

  /** One or more recipe fields changed. A failed edit puts the field back. */
  async editRecipe(changes) {
    const answer = await this.run(t("Saving {name}", { name: this.asset }), () =>
      forgeCall("/edit", { project: this.name, asset: this.asset, changes }));
    if (!answer) return false;
    await this.refresh();
    return true;
  }

  async saveRaw() {
    let changes;
    try {
      changes = JSON.parse(this.raw);
    } catch (error) {
      this.error = t("That is not JSON: {why}", { why: error.message });
      this.render();
      return;
    }
    if (await this.editRecipe(changes)) { this.raw = null; this.render(); }
  }

  async removeAsset() {
    if (!this.removing) {
      this.removing = true;
      this.paintInspector();
      return;
    }
    this.removing = false;
    const name = this.asset;
    const answer = await this.run(t("Removing {name}", { name }), () =>
      forgeCall("/rm", { project: this.name, asset: name }));
    if (!answer) return;
    this.asset = this.sheet = null;
    await this.refresh();
  }

  /** Local files: uploaded to the input folder's forge shelf, then imported. */
  importFiles(files) {
    return this.importInto(async () => {
      const paths = [];
      for (const file of files) paths.push((await upload(file, SUBFOLDER)).path);
      return paths;
    });
  }

  async browse() {
    const chosen = await openPicker({ kinds: ["image", "renders"], kind: "image" });
    if (chosen?.length && this.alive()) this.importInto(() => chosen.map((asset) => asset.path));
  }

  /** Make the files `paths()` names the selected asset's masters, then show them. */
  async importInto(paths) {
    const name = this.asset;
    const answer = await this.run(t("Bringing pictures into {name}", { name }), async () =>
      forgeCall("/import", { project: this.name, asset: name, files: await paths() }));
    if (!answer) return;
    await this.refresh();
    this.look();
  }

  /** Draw the selected asset's contact sheet onto the glass. */
  async look() {
    const row = this.selected();
    if (!row || row.status === "planned") { this.sheet = null; this.render(); return; }
    const name = this.asset;
    const answer = await this.run(t("Laying out the contact sheet"), () =>
      forgeCall("/sheet", { project: this.name, asset: name }));
    if (!answer || this.asset !== name) return;
    this.sheet = { asset: name, path: answer.path, at: Date.now() };
    this.refresh();
  }

  async check() {
    const target = this.target;
    const answer = await this.run(t("Checking against {target}", { target: this.targetLabel(target) }), () =>
      forgeCall("/check", { project: this.name, target }));
    if (!answer) return;
    const report = answer.targets[0];
    const byAsset = {};
    for (const row of report.assets) byAsset[row.asset] = { ...row, at: Date.now() };
    for (const skip of report.skipped) byAsset[skip.asset] = { asset: skip.asset, skipped: skip, problems: [] };
    this.report = { target, count: answer.count, byAsset };
    this.view = "check";
    this.render();
  }

  async exportTarget() {
    const target = this.target;
    const answer = await this.run(t("Exporting to {target}", { target: this.targetLabel(target) }), () =>
      forgeCall("/export", { project: this.name, target }));
    if (!answer) return;
    this.exported = answer;
    await this.refresh();
  }

  setPage(page) {
    if (this.page === page) return;
    this.page = page;
    this.error = null;
    this.render();
  }

  toggleDrawer(on = !this.drawer) {
    this.drawer = on;
    this.paintDrawer();
  }

  // ---- painting -------------------------------------------------------------------

  render() {
    if (!this.alive()) return;
    this.paintBar();
    this.paintDrawer();
    if (!this.project) {
      this.poses?.unmount();
      this.poses = null;
      this.room.replaceChildren(this.startPage());
      this.mounted = "start";
      return;
    }
    if (this.page === "poses") {
      if (this.mounted !== "poses") {
        this.watcher.disconnect();
        this.poses ??= new PosePage(this);
        this.room.replaceChildren(this.poses.root);
        this.poses.show();
        this.mounted = "poses";
      }
      this.poses.paintStatus();
      return;
    }
    if (this.mounted !== "assets") {
      this.poses?.hide();
      this.buildAssetsPage();
      this.mounted = "assets";
    }
    this.paintShelf();
    this.paintGlassbar();
    this.paintGlass();
    this.paintProblems();
    this.paintFoot();
    this.paintOut();
    this.paintInspector();
  }

  paintBar() {
    this.here.replaceChildren(...(this.project ? [
      el("span", { class: "mmc-bn-slash", text: "/" }),
      el("button", {
        class: "mmc-fg-switch", title: t("Open another project"), "aria-haspopup": "menu",
        onclick: (event) => this.projectMenu(event.currentTarget),
      }, [el("span", { text: this.project.name }), icon("chevron", 12)]),
    ] : []));
    this.tabs.replaceChildren(...(this.project ? [
      ["assets", t("Assets")], ["poses", t("Poses")],
    ].map(([id, label]) => el("button", {
      class: `mmc-fg-tab${this.page === id ? " on" : ""}`, role: "tab", "aria-selected": this.page === id,
      onclick: () => this.setPage(id),
    }, [label])) : []));
    this.settingsButton.hidden = !this.project;
    this.settingsButton.classList.toggle("on", this.drawer);
  }

  projectMenu(anchor) {
    const pop = el("div", { class: "mmc-pop mmc-fg-menu", role: "menu" }, [
      el("div", { class: "mmc-pop-title", text: t("Projects") }),
      ...this.projects.map((project) => el("button", {
        class: `mmc-fg-menurow${project.name === this.name ? " on" : ""}`, role: "menuitem",
        onclick: () => { close(); if (project.name !== this.name) this.openProject(project.name); },
      }, [
        el("span", { class: "mmc-fg-menuname", text: project.name }),
        el("span", { class: "mmc-fg-menunote", text: project.mode ?? "" }),
      ])),
      el("button", {
        class: "mmc-fg-menurow mmc-fg-menunew", role: "menuitem",
        onclick: () => { close(); this.leaveProject(); },
      }, [icon("plus", 14), el("span", { text: t("Start a new game") })]),
    ]);
    document.body.append(pop);
    placeNear(pop, anchor, { above: false });
    const close = dismissable(pop);
  }

  // ---- the start page ---------------------------------------------------------------

  startPage() {
    const catalogue = this.catalogue;
    const draft = this.draft;
    const games = this.projects.length
      ? el("div", { class: "mmc-fg-games" }, this.projects.map((project) =>
          el("button", { class: "mmc-fg-game", onclick: () => this.openProject(project.name) }, [
            el("span", { class: "mmc-fg-gamename", text: project.name }),
            el("span", { class: "mmc-fg-gamenote", text: [
              project.mode,
              assetCount(project.assets),
            ].filter(Boolean).join(", ") }),
          ])))
      : el("p", { class: "mmc-fg-quiet", text: t("No games yet. Start one here, or with forge.py new.") });
    const name = el("input", {
      class: "mmc-bn-text mmc-fg-bigname", value: draft.name, placeholder: t("my-game"),
      "aria-label": t("Project name"), spellcheck: "false",
      oninput: (event) => { draft.name = event.target.value; make.disabled = !draft.name.trim(); },
      onkeydown: (event) => { if (event.key === "Enter" && draft.name.trim()) this.createProject(); },
    });
    const make = el("button", { class: "mmc-bn-run", disabled: !draft.name.trim(), onclick: () => this.createProject() },
      [t("Start the game")]);
    const redraw = () => this.room.replaceChildren(this.startPage());
    return el("div", { class: "mmc-fg-start" }, [
      el("section", { class: "mmc-fg-startcol" }, [
        el("h2", { class: "mmc-fg-h", text: t("Your games") }),
        games,
      ]),
      el("section", { class: "mmc-fg-startcol mmc-fg-new" }, [
        el("h2", { class: "mmc-fg-h", text: t("Start a new game") }),
        el("label", { class: "mmc-fg-field" }, [el("span", { class: "mmc-fg-label", text: t("Name") }), name]),
        catalogue ? el("div", { class: "mmc-fg-field" }, [
          el("span", { class: "mmc-fg-label", text: t("How it looks") }),
          this.choiceList(catalogue.modes, (m) => m.id === draft.mode,
            (m) => { draft.mode = m.id; redraw(); }, (m) => m.id, (m) => m.help, "radio"),
        ]) : null,
        catalogue ? el("div", { class: "mmc-fg-field" }, [
          el("span", { class: "mmc-fg-label", text: t("Exports to") }),
          this.choiceList(catalogue.targets.filter((target) => target.id !== "gltf"),
            (target) => draft.targets.includes(target.id),
            (target) => {
              const on = draft.targets.includes(target.id);
              if (on && draft.targets.length === 1) return;
              draft.targets = on ? draft.targets.filter((id) => id !== target.id) : [...draft.targets, target.id];
              redraw();
            }, (target) => target.label, (target) => target.help, "checkbox"),
        ]) : null,
        el("div", { class: "mmc-fg-startfoot" }, [this.statusLine(), el("span", { class: "mmc-bn-gap" }), make]),
      ]),
    ]);
  }

  /** Rows to choose from, each a name and what it means: the look a game has
   *  and the engines it goes to are decisions, and a decision wants its
   *  consequence beside it, not in a tooltip. */
  choiceList(items, isOn, press, label, help, role) {
    return el("div", { class: "mmc-fg-choices", role: role === "radio" ? "radiogroup" : "group" },
      items.map((item) => el("button", {
        class: `mmc-fg-choice ${role}${isOn(item) ? " on" : ""}`, role, "aria-checked": isOn(item),
        onclick: () => press(item),
      }, [
        el("span", { class: "mmc-fg-tick", "aria-hidden": "true" }),
        el("span", { class: "mmc-fg-choicetext" }, [
          el("span", { class: "mmc-fg-choicename", text: label(item) }),
          el("span", { class: "mmc-fg-choicehelp", text: help(item) }),
        ]),
      ])));
  }

  // ---- the drawer ------------------------------------------------------------------

  paintDrawer() {
    this.drawerEl.classList.toggle("open", Boolean(this.drawer && this.project));
    this.settingsButton?.classList.toggle("on", this.drawer);
    if (!this.drawer || !this.project) { this.drawerEl.replaceChildren(); return; }
    const project = this.project;
    const style = project.style;
    const clause = el("textarea", {
      class: "mmc-bn-text mmc-fg-prose", rows: "3", spellcheck: "true",
      placeholder: t("16-bit pixel art, limited palette, crisp dark outlines"),
      "aria-label": t("Style sentence"),
      onchange: (event) => {
        if (event.target.value.trim() !== (style.clause ?? "")) this.setStyle({ clause: event.target.value });
      },
    });
    clause.value = style.clause ?? "";
    const catalogue = this.catalogue;
    this.drawerEl.replaceChildren(
      el("div", { class: "mmc-fg-drawerhead" }, [
        el("h2", { class: "mmc-fg-h", text: project.name }),
        el("button", { class: "mmc-fg-iconbutton", title: t("Close"), onclick: () => this.toggleDrawer(false) },
          [icon("close", 16)]),
      ]),
      el("div", { class: "mmc-fg-drawerbody" }, [
        el("div", { class: "mmc-fg-field" }, [
          el("span", { class: "mmc-fg-label", text: t("Style sentence") }),
          el("span", { class: "mmc-fg-hint", text: t("Every description in this game ends with it.") }),
          clause,
        ]),
        this.paletteField(style),
        style.mode === "pixel" ? this.gridField(style) : null,
        catalogue ? el("div", { class: "mmc-fg-field" }, [
          el("span", { class: "mmc-fg-label", text: t("How it looks") }),
          this.choiceList(catalogue.modes, (m) => m.id === style.mode,
            (m) => { if (m.id !== style.mode) this.setStyle({ mode: m.id }); }, (m) => m.id, (m) => m.help, "radio"),
        ]) : null,
        catalogue ? el("div", { class: "mmc-fg-field" }, [
          el("span", { class: "mmc-fg-label", text: t("Exports to") }),
          this.choiceList(catalogue.targets, (target) => project.targets.includes(target.id),
            (target) => this.toggleTarget(target.id), (target) => target.label, (target) => target.help, "checkbox"),
        ]) : null,
        el("p", { class: "mmc-fg-where" }, [
          el("span", { text: t("Kept in") }),
          el("span", { class: "mmc-bn-path", text: `${SHELF}${project.name}/` }),
        ]),
      ]),
    );
  }

  /** The palette as swatches. A swatch is pressed to take it out; the last
   *  well adds a colour. Empty means the model's own colours. */
  paletteField(style) {
    const palette = style.palette ?? [];
    const save = (next) => this.setStyle({ palette: next }, t("Saving the palette"));
    const add = el("input", {
      type: "color", class: "mmc-fg-addcolour", value: "#888888", "aria-label": t("Add a colour"),
      title: t("Add a colour"), onchange: (event) => save([...palette, event.target.value.toLowerCase()]),
    });
    return el("div", { class: "mmc-fg-field" }, [
      el("span", { class: "mmc-fg-label", text: t("Palette") }),
      el("span", { class: "mmc-fg-hint", text: palette.length
        ? t("{n} colours. Press one to take it out.", { n: palette.length })
        : t("None yet: the pictures keep their own colours.") }),
      el("div", { class: "mmc-fg-swatches" }, [
        ...palette.map((colour, i) => el("button", {
          class: "mmc-fg-swatch", style: { "--swatch": colour }, title: t("Take out {colour}", { colour }),
          "aria-label": t("Take out {colour}", { colour }),
          onclick: () => save(palette.filter((_, j) => j !== i)),
        })),
        el("label", { class: "mmc-fg-swatch mmc-fg-wellnew", title: t("Add a colour") }, [icon("plus", 14), add]),
      ]),
    ]);
  }

  gridField(style) {
    const input = el("input", {
      class: "mmc-bn-text mmc-fg-num", type: "number", min: "1", max: "256", step: "1",
      value: style.grid ?? "", placeholder: t("auto"), "aria-label": t("Pixel size"),
      onchange: (event) => {
        const value = event.target.value === "" ? null : Number(event.target.value);
        this.setStyle({ grid: value }, t("Saving the pixel size"));
      },
    });
    return el("label", { class: "mmc-fg-field" }, [
      el("span", { class: "mmc-fg-label", text: t("Pixel size") }),
      el("span", { class: "mmc-fg-hint", text: t("How many master pixels make one pixel of the art.") }),
      el("span", { class: "mmc-fg-inline" }, [input, el("span", { class: "mmc-fg-unit", text: t("px") })]),
    ]);
  }

  // ---- the assets page ------------------------------------------------------------

  buildAssetsPage() {
    this.shelf = keepScroll(el("nav", { class: "mmc-fg-shelf", "aria-label": t("Assets") }));
    this.glassbar = el("div", { class: "mmc-fg-glassbar" });
    this.box = el("div", { class: "mmc-bn-box mmc-fg-box" });
    this.problems = el("div", { class: "mmc-fg-problems" });
    this.status = el("div", { class: "mmc-fg-status", role: "status" });
    this.foot = el("div", { class: "mmc-fg-foot" });
    this.out = el("div", { class: "mmc-bn-out" });
    this.inspector = keepScroll(el("aside", { class: "mmc-fg-inspector", "aria-label": t("The asset") }));
    this.room.replaceChildren(
      this.shelf,
      el("main", { class: "mmc-fg-middle" }, [this.glassbar, this.box, this.problems, this.foot, this.out]),
      this.inspector,
    );
    this.watcher.disconnect();
    this.watcher.observe(this.box);
  }

  paintShelf() {
    const groups = new Map();
    for (const row of this.rows) {
      if (!groups.has(row.kind)) groups.set(row.kind, []);
      groups.get(row.kind).push(row);
    }
    const order = [...Object.keys(KINDS), ...groups.keys()];
    const kinds = [...new Set(order)].filter((kind) => groups.has(kind));
    const made = this.rows.filter((row) => row.status !== "planned").length;
    const missing = this.rows.filter((row) => row.status === "planned" && !row.making && this.makes(row.kind)).length;
    this.shelf.replaceChildren(
      el("div", { class: "mmc-fg-shelfhead" }, [
        el("span", { class: "mmc-fg-count", text: this.rows.length
          ? t("{made} of {n} made", { made, n: this.rows.length }) : t("Nothing yet") }),
        missing ? el("button", {
          class: "mmc-fg-add", disabled: Boolean(this.working),
          title: t("Render every planned asset that can be made from its recipe"),
          onclick: () => this.make({ missing: true }, t("Queueing what is missing")),
        }, [t("Make {n}", { n: missing })]) : null,
        el("button", { class: "mmc-fg-add", onclick: (event) => this.newAssetMenu(event.currentTarget) },
          [icon("plus", 14), el("span", { text: t("New") })]),
      ]),
      ...(this.rows.length ? kinds.map((kind) => el("section", { class: "mmc-fg-group" }, [
        el("h3", { class: "mmc-fg-grouphead" }, [
          el("span", { text: KINDS[kind]?.group() ?? kind }),
          el("span", { class: "mmc-fg-groupcount", text: String(groups.get(kind).length) }),
        ]),
        el("div", { class: "mmc-fg-items", role: "listbox", "aria-label": KINDS[kind]?.group() ?? kind },
          groups.get(kind).map((row) => this.shelfRow(row))),
      ])) : [el("p", { class: "mmc-fg-quiet", text: t("Add the first thing your game needs: a hero, a tile, an icon.") })]),
    );
  }

  shelfRow(row) {
    const checked = this.report?.byAsset[row.name];
    const count = checked?.problems.length ?? 0;
    const on = row.name === this.asset;
    const unseen = row.status !== "planned" && !row.viewed;
    const first = row.masters[0];
    return el("button", {
      class: `mmc-fg-item${on ? " on" : ""}${unseen ? " unseen" : ""}`,
      role: "option", "aria-selected": on,
      title: unseen ? t("{status}. Nobody has looked at it since.", { status: STATUS[row.status]() }) : STATUS[row.status](),
      onclick: () => this.choose(row.name),
    }, [
      el("span", { class: `mmc-fg-thumb${first ? "" : " empty"}` }, first ? [el("img", {
        alt: "", draggable: false, loading: "lazy",
        src: forgeFileUrl(this.name, `assets/${row.kind}/${row.name}/masters/${first}`, row.made),
      })] : []),
      el("span", { class: "mmc-fg-itemname", text: row.name }),
      count ? el("span", { class: "mmc-fg-bad", text: String(count),
        title: t("{n} problems for {target}", { n: count, target: this.targetLabel(this.report.target) }) }) : null,
      row.making ? spinner() : el("span", { class: `mmc-fg-mark ${row.status}`, "aria-hidden": "true" }),
    ]);
  }

  newAssetMenu(anchor) {
    const kinds = (this.catalogue?.kinds ?? []).filter((kind) => KINDS[kind.id]);
    let chosen = kinds[0]?.id ?? "sprite";
    const name = el("input", {
      class: "mmc-bn-text", placeholder: t("hero-walk"), spellcheck: "false", "aria-label": t("Asset name"),
      oninput: () => { add.disabled = !name.value.trim(); },
      onkeydown: (event) => { if (event.key === "Enter" && name.value.trim()) commit(); },
    });
    const add = el("button", { class: "mmc-bn-run mmc-fg-small", disabled: true, onclick: () => commit() }, [t("Add")]);
    const list = el("div", { class: "mmc-fg-kinds", role: "radiogroup", "aria-label": t("Kind") });
    const paint = () => list.replaceChildren(...kinds.map((kind) => el("button", {
      class: `mmc-fg-kind${kind.id === chosen ? " on" : ""}`, role: "radio", "aria-checked": kind.id === chosen,
      title: kind.help, onclick: () => { chosen = kind.id; paint(); name.focus(); },
    }, [
      el("span", { class: "mmc-fg-kindname", text: KINDS[kind.id].one() }),
      el("span", { class: "mmc-fg-kindhelp", text: kind.help }),
    ])));
    paint();
    const pop = el("div", { class: "mmc-pop mmc-fg-newpop" }, [
      el("div", { class: "mmc-pop-title", text: t("What is it?") }),
      list,
      el("div", { class: "mmc-fg-newname" }, [name, add]),
    ]);
    const commit = async () => {
      if (await this.addAsset(chosen, name.value)) close();
    };
    document.body.append(pop);
    placeNear(pop, anchor, { above: false });
    const close = dismissable(pop);
    name.focus();
  }

  paintGlassbar() {
    const row = this.selected();
    if (!row || row.status === "planned") { this.glassbar.replaceChildren(); return; }
    const checked = this.report?.byAsset[row.name];
    const count = checked?.problems.length ?? 0;
    const views = [
      { id: "sheet", label: t("Contact sheet") },
      { id: "check", label: this.report ? t("Problems ({n})", { n: count }) : t("Problems") },
    ];
    this.glassbar.replaceChildren(
      el("div", { class: "mmc-fg-seg", role: "tablist" }, views.map((view) => el("button", {
        class: `mmc-fg-segbutton${view.id === this.view ? " on" : ""}`, role: "tab", "aria-selected": view.id === this.view,
        onclick: () => {
          this.view = view.id;
          if (view.id === "check" && !this.report) { this.check(); return; }
          this.render();
        },
      }, [view.label]))),
      el("span", { class: "mmc-bn-gap" }),
      el("span", { class: "mmc-fg-zoom", "aria-live": "polite" }),
    );
  }

  paintGlass() {
    const row = this.selected();
    let content;
    let bare = true;
    if (!row && !this.rows.length) {
      content = this.invite("plus", t("Nothing in this game yet"),
        t("Press New to add its first asset."));
    } else if (!row) {
      content = this.invite("gallery", t("Pick something from the shelf"), null);
    } else if (row.making && row.status === "planned") {
      content = el("div", { class: "mmc-bn-drop" }, [
        spinner(),
        el("p", { class: "mmc-bn-dropline", text: t("Rendering {name}", { name: row.name }) }),
        el("p", { class: "mmc-bn-dropnote", text: t("On ComfyUI's queue. It lands here when it is done.") }),
      ]);
    } else if (row.status === "planned" && this.makes(row.kind)) {
      content = this.invite("star", t("Press Make to render {name} from its recipe", { name: row.name }),
        t("Or drop pictures here."));
    } else if (row.status === "planned") {
      content = this.invite("download", t("Drop pictures here to make {name}", { name: row.name }),
        t("Characters, sprites and icons need a transparent background."));
    } else if (this.view === "check") {
      const checked = this.report?.byAsset[row.name];
      if (checked?.overlay) {
        content = this.picture(checked.overlay, checked.at);
        bare = false;
      } else if (checked?.skipped) {
        content = this.invite("close", checked.skipped.why, t("Nothing was checked."));
      } else if (checked) {
        content = this.invite("star", t("Nothing to fix for {target}", { target: this.targetLabel(this.report.target) }),
          t("It fits every limit this engine has."));
      } else {
        content = this.invite("gallery", t("Not checked yet"), t("Press Check to test it against {target}.",
          { target: this.targetLabel(this.target) }));
      }
    } else if (this.sheet?.asset === row.name) {
      content = this.picture(this.sheet.path, this.sheet.at);
      bare = false;
    } else {
      content = el("div", { class: "mmc-bn-drop" }, [spinner()]);
    }
    this.box.classList.toggle("bare", bare);
    this.box.replaceChildren(content);
  }

  invite(glyph, line, note) {
    return el("div", { class: "mmc-bn-drop" }, [
      icon(glyph, 40),
      el("p", { class: "mmc-bn-dropline", text: line }),
      note ? el("p", { class: "mmc-bn-dropnote", text: note }) : null,
    ]);
  }

  picture(path, at) {
    return el("img", {
      class: "mmc-fg-glass", alt: "", draggable: false,
      src: forgeFileUrl(this.name, path, at),
      onload: () => this.fitGlass(),
    });
  }

  /**
   * Size the picture on the glass: the largest whole-number zoom that fits,
   * so every pixel of a sprite is the same number of screen pixels; or, for a
   * picture bigger than the glass, a smooth shrink to fit.
   */
  fitGlass() {
    const img = this.box?.querySelector(".mmc-fg-glass");
    if (!img?.naturalWidth) return;
    const room = this.box.getBoundingClientRect();
    const ratio = window.devicePixelRatio || 1;
    const across = (room.width - 32) * ratio / img.naturalWidth;
    const down = (room.height - 32) * ratio / img.naturalHeight;
    const fit = Math.min(across, down);
    const zoom = fit >= 1 ? Math.floor(fit) : fit;
    img.classList.toggle("shrunk", zoom < 1);
    img.style.width = `${img.naturalWidth * zoom / ratio}px`;
    img.style.height = `${img.naturalHeight * zoom / ratio}px`;
    const readout = this.glassbar?.querySelector(".mmc-fg-zoom");
    if (readout) readout.textContent = zoom >= 1 ? t("{n}× zoom", { n: zoom }) : t("{n}% of its size", { n: Math.round(zoom * 100) });
  }

  paintProblems() {
    const row = this.selected();
    const checked = row && this.view === "check" ? this.report?.byAsset[row.name] : null;
    if (!checked?.problems.length) { this.problems.replaceChildren(); return; }
    this.problems.replaceChildren(el("ul", { class: "mmc-fg-list" }, checked.problems.map((problem) =>
      el("li", {}, [
        el("span", { class: "mmc-fg-wherein", text: [problem.frame, problem.at ? `(${problem.at.join(", ")})` : null]
          .filter(Boolean).join(" ") }),
        el("span", { class: "mmc-fg-what", text: problem.problem }),
        el("code", { class: "mmc-fg-code", text: problem.code }),
      ]))));
  }

  paintFoot() {
    const targets = (this.catalogue?.targets ?? []).filter((target) => this.project.targets.includes(target.id));
    const busy = Boolean(this.working);
    const made = this.rows.some((row) => row.status !== "planned");
    const select = el("select", {
      class: "mmc-bn-text mmc-fg-select", "aria-label": t("Engine"),
      onchange: (event) => {
        this.target = event.target.value;
        if (this.report?.target !== this.target) { this.report = null; if (this.view === "check") this.check(); }
        this.render();
      },
    }, targets.map((target) => el("option", { value: target.id, selected: target.id === this.target, text: target.label })));
    this.foot.replaceChildren(
      this.statusLine(),
      el("span", { class: "mmc-bn-gap" }),
      el("span", { class: "mmc-fg-footlabel", text: t("For") }),
      select,
      el("button", { class: "mmc-bn-second", disabled: busy || !made, onclick: () => this.check(),
        title: t("Test every asset against this engine's limits") }, [t("Check")]),
      el("button", { class: "mmc-bn-run", disabled: busy || !made, onclick: () => this.exportTarget() },
        [t("Export")]),
    );
  }

  /** What is running, or what went wrong, in one line. Repainted on its own
   *  while a call is in the air so nothing under the pointer moves. */
  statusLine() {
    const line = el("span", { class: "mmc-fg-statusline", role: "status" });
    this.fillStatus(line);
    return line;
  }

  fillStatus(line) {
    if (this.working) line.replaceChildren(spinner(), el("span", { text: this.working }));
    else if (this.error) line.replaceChildren(el("span", { class: "mmc-bn-bad", text: this.error }));
    else line.replaceChildren();
  }

  paintStatus() {
    if (!this.alive()) return;
    for (const line of this.overlay.querySelectorAll(".mmc-fg-statusline")) this.fillStatus(line);
  }

  paintOut() {
    const done = this.exported;
    const showing = Boolean(done && done.target === this.target);
    this.out.classList.toggle("on", showing);
    if (!showing) { this.out.replaceChildren(); return; }
    const notes = [];
    if (done.skipped.length) {
      notes.push(t("skipped: {list}", { list: done.skipped.map((s) => `${s.asset} (${s.why})`).join("; ") }));
    }
    if (done.problems.length) notes.push(t("{n} problems; press Check to see them", { n: done.problems.length }));
    this.out.replaceChildren(
      el("div", { class: "mmc-bn-outword" }, [
        el("span", { class: "mmc-bn-outname", text: t("{n} files written for {target}", {
          n: done.written.length, target: this.targetLabel(done.target) }) }),
        notes.length ? el("span", { class: "mmc-bn-outnote", text: notes.join(". ") }) : null,
      ]),
      el("span", { class: "mmc-bn-gap" }),
      el("span", { class: "mmc-bn-path", text: `${SHELF}${this.name}/build/${done.target}/` }),
    );
  }

  // ---- the inspector -----------------------------------------------------------

  paintInspector() {
    const recipe = this.recipe();
    const row = this.selected();
    if (!recipe || !row) {
      this.inspector.replaceChildren(el("p", { class: "mmc-fg-quiet", text: t("Nothing picked.") }));
      return;
    }
    const picker = el("input", { type: "file", accept: "image/*", multiple: true, hidden: true,
      onchange: (event) => { const files = [...event.target.files]; if (files.length) this.importFiles(files); } });
    const schema = this.schemas[recipe.kind];
    const fields = Object.keys(schema?.properties ?? {}).filter((key) => !FIXED.has(key));
    const open = fields.filter((key) => !MORE.has(key));
    const folded = fields.filter((key) => MORE.has(key));
    this.inspector.replaceChildren(...[
      el("header", { class: "mmc-fg-inhead" }, [
        el("h2", { class: "mmc-fg-title", text: recipe.name }),
        el("span", { class: "mmc-fg-kindtag", text: KINDS[recipe.kind]?.one() ?? recipe.kind }),
        el("span", { class: `mmc-fg-state ${row.status}`, text: STATUS[row.status]() }),
      ]),
      el("section", { class: "mmc-fg-insection" }, [
        el("h3", { class: "mmc-fg-subhead", text: t("Masters") }),
        row.masters.length
          ? el("div", { class: "mmc-fg-masters" }, row.masters.map((file) => el("span", { class: "mmc-fg-thumb big", title: file }, [
              el("img", { alt: file, draggable: false, loading: "lazy",
                src: forgeFileUrl(this.name, `assets/${row.kind}/${row.name}/masters/${file}`, row.made) }),
            ])))
          : el("p", { class: "mmc-fg-hint", text: this.makes(recipe.kind)
              ? t("No pictures yet. Make them from the recipe, or bring them in:")
              : t("No pictures yet. Drop them anywhere on the bench, or bring them in:") }),
        this.makes(recipe.kind) ? el("button", {
          class: "mmc-bn-run mmc-fg-make", disabled: Boolean(this.working || row.making),
          title: t("Render it on ComfyUI from the recipe and the project's look"),
          onclick: () => this.make({ assets: [recipe.name] }, t("Queueing {name}", { name: recipe.name })),
        }, row.making ? [spinner(), el("span", { text: t("Rendering") })]
           : [row.status === "planned" ? t("Make") : t("Make again")]) : null,
        el("div", { class: "mmc-fg-pair" }, [
          el("button", { class: "mmc-bn-verb", onclick: () => picker.click() },
            [icon("download", 15), el("span", { text: t("From disk") })]),
          el("button", { class: "mmc-bn-verb", onclick: () => this.browse() },
            [icon("gallery", 15), el("span", { text: t("From ComfyUI") })]),
        ]),
        picker,
      ]),
      schema ? el("section", { class: "mmc-fg-insection" }, [
        el("h3", { class: "mmc-fg-subhead", text: t("Recipe") }),
        ...(this.raw != null ? [this.rawEditor(recipe)] : open.map((key) => this.fieldFor(recipe, key, schema.properties[key]))),
      ]) : null,
      schema && this.raw == null ? el("details", {
        class: "mmc-fg-more", open: this.more,
        ontoggle: (event) => { this.more = event.target.open; },
      }, [
        el("summary", { text: t("More settings") }),
        ...folded.map((key) => this.fieldFor(recipe, key, schema.properties[key])),
        el("button", { class: "mmc-fg-link", onclick: () => {
          const editable = Object.fromEntries(Object.entries(recipe).filter(([key]) => !FIXED.has(key)));
          this.raw = JSON.stringify(editable, null, 2);
          this.paintInspector();
        } }, [t("Edit the whole recipe as JSON")]),
      ]) : null,
      el("div", { class: "mmc-fg-inend" }, [
        el("button", { class: `mmc-fg-link mmc-fg-remove${this.removing ? " armed" : ""}`, onclick: () => this.removeAsset() },
          [this.removing ? t("Press again to remove {name}. Its files are kept in .versions.", { name: recipe.name })
                         : t("Remove {name}", { name: recipe.name })]),
      ]),
    ].filter(Boolean));
  }

  rawEditor(recipe) {
    const editor = el("textarea", {
      class: "mmc-bn-text mmc-fg-json", rows: String(Math.min(18, this.raw.split("\n").length + 1)),
      spellcheck: "false", "aria-label": t("Recipe as JSON"),
      oninput: (event) => { this.raw = event.target.value; },
    });
    editor.value = this.raw;
    return el("div", { class: "mmc-fg-field" }, [
      editor,
      el("div", { class: "mmc-fg-pair" }, [
        el("button", { class: "mmc-bn-verb", onclick: () => { this.raw = null; this.paintInspector(); } }, [t("Back to the form")]),
        el("button", { class: "mmc-bn-verb", onclick: () => this.saveRaw() }, [t("Save {name}", { name: recipe.name })]),
      ]),
    ]);
  }

  /** One recipe field as a control, from its schema. Every control saves on
   *  its own change; the server says what is wrong and the field is redrawn
   *  from the recipe it keeps. */
  fieldFor(recipe, key, spec) {
    const label = LABELS[key]?.() ?? key.replace(/_/g, " ");
    const value = recipe[key];
    const save = (next) => this.editRecipe({ [key]: next }).then((ok) => { if (!ok) this.paintInspector(); });
    const head = el("span", { class: "mmc-fg-label", title: spec.description ?? "", text: label });
    const wrap = (control, extra = null) => el("label", { class: "mmc-fg-field" }, [head, control, extra]);
    const number = (val, attrs, onchange) => el("input", {
      class: "mmc-bn-text mmc-fg-num", type: "number", value: val ?? "", ...attrs, onchange,
    });

    if (key === "animations") return this.animationsField(recipe, head);
    // Which character a sprite animates: one of the project's characters, so
    // a pick, not a name typed and hoped for.
    if (key === "of") {
      const characters = this.rows.filter((row) => row.kind === "character").map((row) => row.name);
      if (value && !characters.includes(value)) characters.push(value);
      return wrap(el("select", { class: "mmc-bn-text mmc-fg-select", onchange: (event) => save(event.target.value) }, [
        el("option", { value: "", text: t("Nothing in particular"), selected: !value }),
        ...characters.map((name) => el("option", { value: name, text: name, selected: name === value })),
      ]));
    }
    // The model that makes it: a still family this machine has, or the
    // project's own.
    if (key === "family") {
      const families = (this.catalogue?.families ?? []).filter((f) => f.still).map((f) => f.id);
      if (value && !families.includes(value)) families.push(value);
      return wrap(el("select", { class: "mmc-bn-text mmc-fg-select", onchange: (event) => save(event.target.value || null) }, [
        el("option", { value: "", selected: !value, text: t("The project's ({family})", { family: this.project.style.family }) }),
        ...families.map((id) => el("option", { value: id, text: id, selected: id === value })),
      ]));
    }
    if (key === "post") {
      return wrap(el("input", {
        class: "mmc-bn-text", value: shown(value), spellcheck: "false",
        placeholder: t("The look's own steps"),
        onchange: (event) => save(event.target.value.split(",").map((s) => s.trim()).filter(Boolean)),
      }));
    }
    // A character faces one way, four, or eight; the schema allows the numbers
    // between because it bounds, but only these three are drawn.
    if (key === "directions") {
      const now = value ?? spec.default ?? 1;
      return el("div", { class: "mmc-fg-field" }, [head, el("div", { class: "mmc-bn-opts" }, [1, 4, 8].map((n) =>
        el("button", { class: `mmc-bn-opt${now === n ? " on" : ""}`, "aria-pressed": now === n, onclick: () => save(n) },
          [n === 1 ? t("One way") : t("{n} ways", { n })])))]);
    }
    if (spec.type === "boolean") {
      return el("label", { class: "mmc-fg-check", title: spec.description ?? "" }, [
        el("input", { type: "checkbox", checked: value ?? spec.default ?? false,
          onchange: (event) => save(event.target.checked) }),
        el("span", { text: label }),
      ]);
    }
    if (spec.enum) {
      return el("div", { class: "mmc-fg-field" }, [head, el("div", { class: "mmc-bn-opts" }, spec.enum.map((choice) =>
        el("button", {
          class: `mmc-bn-opt${(value ?? spec.default) === choice ? " on" : ""}`, "aria-pressed": (value ?? spec.default) === choice,
          onclick: () => save(choice),
        }, [choice])))]);
    }
    if (spec.type === "string") {
      const long = key === "prompt" || key === "notes";
      const input = el(long ? "textarea" : "input", {
        class: `mmc-bn-text${long ? " mmc-fg-prose" : ""}`, rows: long ? "3" : null, spellcheck: long ? "true" : "false",
        placeholder: key === "prompt" ? t("What it is, in plain words") : spec.description ?? "",
        onchange: (event) => save(event.target.value),
      });
      input.value = value ?? "";
      return wrap(input, key === "prompt" && this.project.style.clause
        ? el("span", { class: "mmc-fg-hint", text: t("…then the style sentence: {clause}", { clause: this.project.style.clause }) })
        : null);
    }
    if (spec.type === "integer" || spec.type === "number") {
      return wrap(number(value, {
        min: spec.minimum, max: spec.maximum, step: spec.type === "integer" ? "1" : "any",
        placeholder: spec.default != null ? String(spec.default) : t("auto"),
      }, (event) => save(event.target.value === "" ? null : Number(event.target.value))));
    }
    if (spec.type === "array" && spec.items?.type !== "string" && spec.items?.type !== "object" && spec.maxItems === 2) {
      const pair = value ?? spec.default ?? [null, null];
      const integer = spec.items.type === "integer";
      const a = number(pair[0], { step: integer ? "1" : "any", min: integer ? "1" : null, placeholder: "—" }, () => commit());
      const b = number(pair[1], { step: integer ? "1" : "any", min: integer ? "1" : null, placeholder: "—" }, () => commit());
      const commit = () => {
        if (a.value === "" && b.value === "") { save(null); return; }
        if (a.value === "" || b.value === "") return;
        save([Number(a.value), Number(b.value)]);
      };
      return el("div", { class: "mmc-fg-field" }, [head, el("span", { class: "mmc-fg-inline" }, [
        a, el("span", { class: "mmc-fg-unit", text: integer ? "×" : "," }), b,
      ])]);
    }
    if (spec.type === "array" && spec.items?.type === "string") {
      return wrap(el("input", {
        class: "mmc-bn-text", value: shown(value), placeholder: t("comma, separated, names"), spellcheck: "false",
        onchange: (event) => save(event.target.value.split(",").map((s) => s.trim()).filter(Boolean)),
      }));
    }
    // Objects and lists of them: JSON, the one honest control for free shape.
    const input = el("textarea", {
      class: "mmc-bn-text mmc-fg-json", rows: "3", spellcheck: "false",
      onchange: (event) => {
        try { save(JSON.parse(event.target.value || "null")); } catch (error) {
          this.error = t("That is not JSON: {why}", { why: error.message });
          this.paintStatus();
        }
      },
    });
    input.value = value == null ? "" : JSON.stringify(value, null, 1);
    return wrap(input);
  }

  /** A sprite's animations as rows: name, frames, speed, loop. The one list
   *  of objects an artist edits often enough to deserve its own control. */
  animationsField(recipe, head) {
    const list = (recipe.animations ?? []).map((a) => ({ name: "", frames: 4, fps: 8, loop: true, ...a }));
    const save = (next) => this.editRecipe({ animations: next }).then((ok) => { if (!ok) this.paintInspector(); });
    const rows = list.map((anim, i) => {
      const set = (field, value) => { const next = list.map((a) => ({ ...a })); next[i][field] = value; save(next); };
      return el("div", { class: "mmc-fg-anim" }, [
        el("input", { class: "mmc-bn-text", value: anim.name, placeholder: t("walk"), spellcheck: "false",
          "aria-label": t("Animation name"), onchange: (event) => set("name", event.target.value.trim()) }),
        el("input", { class: "mmc-bn-text mmc-fg-num", type: "number", min: "1", value: anim.frames,
          "aria-label": t("Frames"), title: t("Frames"), onchange: (event) => set("frames", Number(event.target.value)) }),
        el("input", { class: "mmc-bn-text mmc-fg-num", type: "number", min: "1", max: "60", value: anim.fps,
          "aria-label": t("Frames a second"), title: t("Frames a second"), onchange: (event) => set("fps", Number(event.target.value)) }),
        el("label", { class: "mmc-fg-loop", title: t("Loops") }, [
          el("input", { type: "checkbox", checked: anim.loop !== false, onchange: (event) => set("loop", event.target.checked) }),
          el("span", { text: t("loop") }),
        ]),
        el("button", { class: "mmc-fg-iconbutton", title: t("Take out {name}", { name: anim.name || t("this animation") }),
          onclick: () => save(list.filter((_, j) => j !== i)) }, [icon("close", 12)]),
      ]);
    });
    return el("div", { class: "mmc-fg-field" }, [
      head,
      rows.length ? el("div", { class: "mmc-fg-anims" }, [
        el("div", { class: "mmc-fg-animhead", "aria-hidden": "true" }, [
          el("span", { text: t("Name") }), el("span", { text: t("Frames") }), el("span", { text: t("fps") }),
        ]),
        ...rows,
      ]) : null,
      el("button", { class: "mmc-fg-link", onclick: () => {
        const taken = new Set(list.map((a) => a.name));
        const name = ["walk", "idle", "run", "attack", "jump", "hurt"].find((n) => !taken.has(n)) ?? `anim${list.length + 1}`;
        save([...list, { name, frames: 4, fps: 8, loop: true }]);
      } }, [t("Add an animation")]),
    ]);
  }
}

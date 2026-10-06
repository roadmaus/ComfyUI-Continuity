// Game Forge: a game's assets, kept in one project, checked and exported.
//
// The design is `specs/continuity-game-forge-spec.md`; the server half is
// `creator/forge/`, and this is one of its two clients. The other is the CLI
// (`skills/continuity-forge/forge.py`), and **the bench may do nothing the CLI
// cannot**: every press here is one call to a `/continuity/forge/*` route, the
// same table `tests/test_forge_parity.py` holds the CLI against. Nothing is
// computed here that the server does not also say.
//
// **The room is the benches' room** (`styles/bench.js`): the bar, the rail
// with its stops hung off a film edge, the light box, the foot that runs the
// job. A third layout would be a third thing to learn.
//
// **The rail is the manifest.** The project's asset list is what a game's art
// *is* here — the queue of what is missing and the record of what is made — so
// it is the spine of the rail rather than a dropdown above a picture. Each row
// carries one mark for where it stands (a ring planned, a dot made, a square
// exported, a dashed ring stale: the pack's mark for "real, but not what it
// was"), a name set heavier when nobody has looked at it since it was made,
// and, after a check, the number of problems it has on the target in the foot.
//
// **The light box shows pixels as pixels.** A contact sheet of a 16×16 sprite
// or a check overlay is pixel art, and pixel art scaled by a fraction is a
// smear with uneven pixels. So the glass shows it at a whole-number zoom, with
// no smoothing, and only shrinks — smoothly — what is larger than the glass.
//
// **Looking is an act the project records.** Opening an asset draws its
// contact sheet, and the server counts that as somebody having looked
// (`review.sheet`); `status` stops calling the asset "not looked at". That is
// true here — the sheet is on the glass — and it is the same call the CLI's
// `sheet` makes for an agent.
//
// Nothing here runs a model: building, checking and exporting are arithmetic
// on the masters, so no press waits for the queue.

import { el, icon, mark, spinner, dragsFiles, mountOverlay, keepScroll } from "./dom.js";
import { forgeCall, forgeFileUrl, upload } from "./api.js";
import { openPicker } from "./picker.js";
import { t } from "./i18n.js";

/** Where a picture brought in from this machine lands before the import moves
 *  it into the project — the input folder's forge shelf, as the CLI does. */
const SUBFOLDER = "forge";

/** The project shelf, for the line at the foot of the rail (`outputs.FORGE`). */
const SHELF = "output/continuity/forge/";

/** The status marks, by status. The words are the row's tooltip; the mark is
 *  what the eye runs down. */
const STATUS = {
  planned: () => t("Planned — nothing made yet"),
  made: () => t("Made — not exported to every target"),
  exported: () => t("Exported to every target"),
  stale: () => t("Stale — the recipe changed after its files were made"),
};

/** The manifest's one-line summary, a phrase per status. */
const COUNTED = {
  planned: (n) => t("{n} planned", { n }),
  made: (n) => t("{n} made", { n }),
  exported: (n) => t("{n} exported", { n }),
  stale: (n) => t("{n} stale", { n }),
};

/** The fields a recipe editor shows: the whole recipe less what cannot change. */
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

class Forge {
  constructor(options, resolve) {
    this.resolve = resolve;
    this.back = options.back ?? null;
    this.name = options.project ?? null;
    this.catalogue = null;     // {kinds, modes, targets}
    this.projects = [];
    this.project = null;       // project.json, as the server keeps it
    this.rows = [];            // status rows
    this.asset = null;         // the selected asset's name
    this.view = "sheet";       // what is on the glass: "sheet" | "check"
    this.target = null;        // the target the foot checks and exports
    this.sheet = null;         // {asset, path, at}
    this.report = null;        // the last check of `target`: {target, byAsset}
    this.exported = null;      // the last export's answer
    this.working = null;       // what is running, as a sentence, or null
    this.error = null;
    this.draft = { name: "", mode: "pixel", targets: ["generic"] };
    this.adding = { kind: "sprite", name: "" };
    this.recipeText = null;    // the recipe editor's text while it differs
    this.removing = false;     // the first press of Remove
  }

  // ---- the room ---------------------------------------------------------------

  mount() {
    this.stops = el("div", { class: "mmc-bn-stops" });
    this.where = el("div", { class: "mmc-bn-where" });
    this.rail = keepScroll(el("div", { class: "mmc-bn-rail" }, [this.stops, this.where]));
    this.views = el("div", { class: "mmc-fg-views" });
    this.box = el("div", { class: "mmc-bn-box mmc-fg-box" });
    this.problems = el("div", { class: "mmc-fg-problems" });
    this.foot = el("div", { class: "mmc-bn-foot mmc-fg-foot" });
    this.out = el("div", { class: "mmc-bn-out" });
    this.work = el("div", { class: "mmc-bn-work" },
      [this.views, this.box, this.problems, this.foot, this.out]);
    // The project, once one is open: one more step on the same path.
    this.here = el("span", { class: "mmc-fg-crumb" });
    this.sheetEl = el("div", { class: "mmc-bn" }, [
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
        el("button", { class: "mmc-close", text: "✕", title: t("Close the bench"), onclick: () => this.close() }),
      ]),
      el("div", { class: "mmc-bn-room" }, [this.rail, this.work]),
    ]);
    // A file over the room is a master for the asset on the glass — the same
    // gesture the other benches take, and here it means import.
    this.overlay = el("div", {
      class: "mmc-overlay mmc-bn-over",
      ondragover: (event) => {
        if (!dragsFiles(event) || !this.selected()) return;
        event.preventDefault();
        this.overlay.classList.add("dropping");
      },
      ondragleave: (event) => { if (event.target === this.overlay) this.overlay.classList.remove("dropping"); },
      ondrop: (event) => {
        if (!dragsFiles(event)) return;
        event.preventDefault();
        this.overlay.classList.remove("dropping");
        const files = [...(event.dataTransfer?.files ?? [])];
        if (files.length && this.selected()) this.importFiles(files);
      },
    }, [this.sheetEl]);
    this.unmount = mountOverlay(this.overlay, () => this.close());
    this.watcher = new ResizeObserver(() => this.fitGlass());
    this.watcher.observe(this.box);
    this.render();
    this.load();
  }

  close() {
    if (open === this) open = null;
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
    this.paintFoot();
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
    this.name = name;
    this.project = answer.project;
    this.rows = answer.status.assets;
    if (!this.project.targets.includes(this.target)) this.target = this.project.targets[0];
    this.report = null;
    this.exported = null;
    if (!this.rows.some((row) => row.name === this.asset)) this.asset = null;
    this.render();
    if (this.asset) this.look();
  }

  /** The project and its status again, after anything that changed them. */
  async refresh() {
    const answer = await forgeCall("/show", { project: this.name }, { get: true }).catch(() => null);
    if (!answer || !this.alive()) return;
    this.project = answer.project;
    this.rows = answer.status.assets;
    this.render();
  }

  leaveProject() {
    this.name = this.project = this.asset = this.sheet = this.report = this.exported = null;
    this.rows = [];
    this.render();
    this.run(t("Reading the projects"), async () => {
      this.projects = (await forgeCall("/projects", {}, { get: true })).projects;
    });
  }

  selected() { return this.rows.find((row) => row.name === this.asset) ?? null; }

  recipe() { return this.project?.assets.find((r) => r.name === this.asset) ?? null; }

  // ---- what the presses do ------------------------------------------------------

  async createProject() {
    const { name, mode, targets } = this.draft;
    const answer = await this.run(t("Making {name}", { name }), () =>
      forgeCall("/new", { project: name.trim(), mode, targets }));
    if (!answer) return;
    this.draft = { name: "", mode: "pixel", targets: ["generic"] };
    this.projects.push({ name: answer.project.name });
    this.openProject(answer.project.name);
  }

  async toggleTarget(id) {
    const on = this.project.targets.includes(id);
    const answer = await this.run(on ? t("Removing a target") : t("Adding a target"), () =>
      forgeCall(on ? "/target/rm" : "/target/add", { project: this.name, target: id }));
    if (!answer) return;
    this.project = answer.project;
    if (!this.project.targets.includes(this.target)) this.target = this.project.targets[0];
    this.report = null;
    this.refresh();
  }

  async saveClause(text) {
    if (text.trim() === (this.project.style.clause ?? "")) return;
    const answer = await this.run(t("Saving the style"), () =>
      forgeCall("/style", { project: this.name, style: { clause: text } }));
    if (answer) this.refresh();
  }

  async addAsset() {
    const { kind, name } = this.adding;
    const answer = await this.run(t("Adding {name}", { name }), () =>
      forgeCall("/add", { project: this.name, asset: { kind, name: name.trim() } }));
    if (!answer) return;
    this.adding = { kind, name: "" };
    this.asset = answer.asset.name;
    this.sheet = null;
    await this.refresh();
  }

  async saveRecipe() {
    let changes;
    try {
      changes = JSON.parse(this.recipeText);
    } catch (error) {
      this.error = t("The recipe is not JSON: {why}", { why: error.message });
      this.render();
      return;
    }
    const answer = await this.run(t("Saving the recipe"), () =>
      forgeCall("/edit", { project: this.name, asset: this.asset, changes }));
    if (!answer) return;
    this.recipeText = null;
    await this.refresh();
    this.look();
  }

  async removeAsset() {
    if (!this.removing) {
      this.removing = true;
      this.paintRail();
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
    const answer = await this.run(t("Importing into {name}", { name }), async () =>
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
    const answer = await this.run(t("Drawing the sheet"), () =>
      forgeCall("/sheet", { project: this.name, asset: name }));
    if (!answer || this.asset !== name) return;
    this.sheet = { asset: name, path: answer.path, at: Date.now() };
    this.refresh();
  }

  async check() {
    const target = this.target;
    const answer = await this.run(t("Checking {target}", { target: this.targetLabel(target) }), () =>
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

  targetLabel(id) {
    return this.catalogue?.targets.find((target) => target.id === id)?.label ?? id;
  }

  // ---- painting -------------------------------------------------------------------

  render() {
    if (!this.alive()) return;
    this.here.replaceChildren(...(this.project ? [
      el("span", { class: "mmc-bn-slash", text: "/" }),
      el("span", { class: "mmc-bn-here", text: this.project.name }),
    ] : []));
    this.paintRail();
    this.paintViews();
    this.paintGlass();
    this.paintProblems();
    this.paintFoot();
    this.paintOut();
  }

  stop(name, children) {
    return el("div", { class: "mmc-bn-stop" }, [
      el("div", { class: "mmc-bn-stopname", text: name }), ...children]);
  }

  paintRail() {
    const stops = this.project
      ? [this.projectStop(), this.manifestStop(), this.recipe() ? this.assetStop() : null]
      : [this.projectsStop(), this.newProjectStop()];
    this.stops.replaceChildren(...stops.filter(Boolean));
    this.where.replaceChildren(
      el("b", { text: t("Kept in the output folder") }),
      el("span", { class: "mmc-bn-path", text: SHELF + (this.project ? `${this.project.name}/` : "") }));
  }

  projectsStop() {
    if (!this.projects.length) {
      return this.stop(t("Projects"), [el("p", { class: "mmc-bn-empty",
        text: t("No projects yet. Make one below, or with forge.py new.") })]);
    }
    return this.stop(t("Projects"), [el("div", { class: "mmc-bn-list" }, this.projects.map((project) =>
      el("button", { class: "mmc-bn-pick", onclick: () => this.openProject(project.name) }, [
        el("span", { class: "mmc-bn-pickname", text: project.name }),
        project.assets != null
          ? el("span", { class: "mmc-fg-count", text: t("{n} assets", { n: project.assets }) })
          : null,
      ])))]);
  }

  newProjectStop() {
    const catalogue = this.catalogue;
    if (!catalogue) return null;
    const draft = this.draft;
    const name = el("input", {
      class: "mmc-bn-text", value: draft.name, placeholder: t("my-game"),
      "aria-label": t("Project name"), spellcheck: "false",
      oninput: (event) => { draft.name = event.target.value; make.disabled = !draft.name.trim(); },
      onkeydown: (event) => { if (event.key === "Enter" && draft.name.trim()) this.createProject(); },
    });
    const make = el("button", { class: "mmc-bn-verb", disabled: !draft.name.trim(), onclick: () => this.createProject() },
      [icon("plus", 15), el("span", { text: t("Make the project") })]);
    return this.stop(t("New project"), [
      name,
      this.field(t("Look"), this.opts(catalogue.modes, (m) => m.id === draft.mode,
        (m) => { draft.mode = m.id; this.paintRail(); }, (m) => m.help)),
      this.field(t("Exports to"), this.opts(catalogue.targets, (target) => draft.targets.includes(target.id),
        (target) => {
          const on = draft.targets.includes(target.id);
          if (on && draft.targets.length === 1) return;
          draft.targets = on ? draft.targets.filter((id) => id !== target.id) : [...draft.targets, target.id];
          this.paintRail();
        }, (target) => target.help, (target) => target.label)),
      make,
    ]);
  }

  field(label, control) {
    return el("div", { class: "mmc-fg-field" }, [el("span", { class: "mmc-fg-label", text: label }), control]);
  }

  /** Word stops: `items` with an id, which are on, what pressing one does. */
  opts(items, isOn, press, title = () => null, label = (item) => item.id) {
    return el("div", { class: "mmc-bn-opts" }, items.map((item) =>
      el("button", {
        class: `mmc-bn-opt${isOn(item) ? " on" : ""}`, title: title(item), "aria-pressed": isOn(item),
        onclick: () => press(item),
      }, [label(item)])));
  }

  projectStop() {
    const project = this.project;
    const style = project.style;
    const clause = el("textarea", {
      class: "mmc-bn-text mmc-fg-clause", rows: "3", spellcheck: "false",
      placeholder: t("The sentence every prompt in this project ends with"),
      "aria-label": t("Style clause"),
      onchange: (event) => this.saveClause(event.target.value),
    });
    clause.value = style.clause ?? "";
    const mode = this.catalogue?.modes.find((m) => m.id === style.mode);
    return this.stop(project.name, [
      el("p", { class: "mmc-bn-note", title: mode?.help ?? "",
        text: t("{mode} — {help}", { mode: style.mode, help: mode?.help ?? "" }) }),
      this.field(t("Exports to"), this.opts(this.catalogue?.targets ?? [],
        (target) => project.targets.includes(target.id), (target) => this.toggleTarget(target.id),
        (target) => target.help, (target) => target.label)),
      this.field(t("Style"), clause),
      el("button", { class: "mmc-fg-leave", onclick: () => this.leaveProject() }, [t("Another project")]),
    ]);
  }

  manifestStop() {
    const counts = {};
    for (const row of this.rows) counts[row.status] = (counts[row.status] ?? 0) + 1;
    const summary = Object.keys(STATUS).filter((status) => counts[status])
      .map((status) => COUNTED[status](counts[status])).join(", ");
    const list = this.rows.length
      ? el("div", { class: "mmc-bn-list mmc-fg-manifest", role: "listbox", "aria-label": t("Assets") },
          this.rows.map((row) => this.assetRow(row)))
      : el("p", { class: "mmc-bn-empty",
          text: t("Nothing planned yet. Add an asset below, or apply a plan with forge.py plan.") });
    const adding = this.adding;
    const name = el("input", {
      class: "mmc-bn-text", value: adding.name, placeholder: t("asset-name"), spellcheck: "false",
      "aria-label": t("Asset name"),
      oninput: (event) => { adding.name = event.target.value; add.disabled = !adding.name.trim(); },
      onkeydown: (event) => { if (event.key === "Enter" && adding.name.trim()) this.addAsset(); },
    });
    const add = el("button", { class: "mmc-bn-verb", disabled: !adding.name.trim(), onclick: () => this.addAsset() },
      [icon("plus", 15), el("span", { text: t("Add the {kind}", { kind: adding.kind }) })]);
    const kinds = (this.catalogue?.kinds ?? []).filter((k) => !["material", "texture", "sound"].includes(k.id));
    return this.stop(t("Assets"), [
      this.rows.length ? el("p", { class: "mmc-fg-summary", text: summary }) : null,
      list,
      el("div", { class: "mmc-fg-add" }, [
        this.opts(kinds, (k) => k.id === adding.kind, (k) => { adding.kind = k.id; this.paintRail(); },
          (k) => k.help),
        name, add,
      ]),
    ]);
  }

  assetRow(row) {
    const checked = this.report?.byAsset[row.name];
    const count = checked?.problems.length ?? 0;
    const on = row.name === this.asset;
    return el("button", {
      class: `mmc-bn-pick mmc-fg-row${on ? " on" : ""}${row.status !== "planned" && !row.viewed ? " unseen" : ""}`,
      role: "option", "aria-selected": on,
      title: row.status !== "planned" && !row.viewed
        ? t("{status}. Nobody has looked at it since it was made.", { status: STATUS[row.status]() })
        : STATUS[row.status](),
      onclick: () => {
        if (this.asset === row.name) return;
        this.asset = row.name;
        this.recipeText = null;
        this.removing = false;
        this.sheet = null;
        if (this.view === "check" && !this.report) this.view = "sheet";
        this.render();
        this.look();
      },
    }, [
      el("span", { class: `mmc-fg-mark ${row.status}`, "aria-hidden": "true" }),
      el("span", { class: "mmc-bn-pickname", text: row.name }),
      count ? el("span", { class: "mmc-fg-bad", text: String(count),
        title: t("{n} problems for {target}", { n: count, target: this.targetLabel(this.report.target) }) }) : null,
      el("span", { class: "mmc-fg-kind", text: row.kind }),
    ]);
  }

  assetStop() {
    const recipe = this.recipe();
    const row = this.selected();
    const editable = Object.fromEntries(Object.entries(recipe).filter(([key]) => !FIXED.has(key)));
    const text = this.recipeText ?? JSON.stringify(editable, null, 2);
    const editor = el("textarea", {
      class: "mmc-bn-text mmc-fg-recipe", rows: String(Math.min(16, text.split("\n").length)),
      spellcheck: "false", "aria-label": t("Recipe"),
      oninput: (event) => {
        this.recipeText = event.target.value;
        save.disabled = this.recipeText === JSON.stringify(editable, null, 2);
      },
    });
    editor.value = text;
    const save = el("button", { class: "mmc-bn-verb", disabled: this.recipeText == null,
      onclick: () => this.saveRecipe() }, [icon("edit", 15), el("span", { text: t("Save the recipe") })]);
    const picker = el("input", { type: "file", accept: "image/*", multiple: true, hidden: true,
      onchange: (event) => { const files = [...event.target.files]; if (files.length) this.importFiles(files); } });
    return this.stop(recipe.name, [
      el("p", { class: "mmc-bn-note", text: row.masters.length
        ? t("{n} masters, seed {seed}, made with {family}", { n: row.masters.length, seed: row.seed, family: row.family })
        : t("No masters yet. Drop pictures on the bench, or import them.") }),
      el("div", { class: "mmc-fg-pair" }, [
        el("button", { class: "mmc-bn-verb", onclick: () => picker.click() },
          [icon("download", 15), el("span", { text: t("Import files") })]),
        el("button", { class: "mmc-bn-verb", onclick: () => this.browse() },
          [icon("gallery", 15), el("span", { text: t("From ComfyUI") })]),
      ]),
      picker,
      this.field(t("Recipe"), editor),
      save,
      el("button", { class: `mmc-fg-remove${this.removing ? " armed" : ""}`, onclick: () => this.removeAsset() },
        [this.removing ? t("Press again to remove {name}; its files are kept in .versions",
                           { name: recipe.name })
                       : t("Remove {name}", { name: recipe.name })]),
    ]);
  }

  paintViews() {
    const row = this.selected();
    if (!row) { this.views.replaceChildren(); return; }
    const checked = this.report?.byAsset[row.name];
    const count = checked?.problems.length ?? 0;
    this.views.replaceChildren(
      this.opts([
        { id: "sheet", label: t("Contact sheet") },
        { id: "check", label: this.report
            ? t("Problems on {target}: {n}", { target: this.targetLabel(this.report.target), n: count })
            : t("Problems") },
      ], (view) => view.id === this.view, (view) => {
        this.view = view.id;
        if (view.id === "check" && !this.report) { this.check(); return; }
        this.render();
      }, () => null, (view) => view.label));
  }

  paintGlass() {
    const row = this.selected();
    let content;
    let bare = true;
    if (!this.project) {
      content = this.invite("cube", t("Open a project, or make one"),
        t("A project keeps a game's assets, its look and the engines it exports to."));
    } else if (!row) {
      content = this.invite("gallery", t("Pick an asset from the list"),
        t("Its contact sheet goes here: the masters, then what each target makes of them."));
    } else if (row.status === "planned") {
      content = this.invite("download", t("Drop pictures here to make them {name}'s masters", { name: row.name }),
        t("Sprites, characters and icons need transparency in the picture."));
    } else if (this.view === "check") {
      const checked = this.report?.byAsset[row.name];
      if (checked?.overlay) {
        content = this.picture(checked.overlay, checked.at);
        bare = false;
      } else if (checked?.skipped) {
        content = this.invite("close", checked.skipped.why, t("Nothing was checked."));
      } else if (checked) {
        content = this.invite("star", t("No problems for {target}", { target: this.targetLabel(this.report.target) }),
          t("It fits every budget this target has."));
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
    const img = this.box.querySelector(".mmc-fg-glass");
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
  }

  paintProblems() {
    const row = this.selected();
    const checked = row && this.view === "check" ? this.report?.byAsset[row.name] : null;
    if (!checked?.problems.length) { this.problems.replaceChildren(); return; }
    this.problems.replaceChildren(el("ul", { class: "mmc-fg-list" }, checked.problems.map((problem) =>
      el("li", {}, [
        el("span", { class: "mmc-fg-where", text: [problem.frame, problem.at ? `(${problem.at.join(", ")})` : null]
          .filter(Boolean).join(" ") }),
        el("span", { class: "mmc-fg-what", text: problem.problem }),
        el("code", { class: "mmc-fg-code", text: problem.code }),
      ]))));
  }

  paintFoot() {
    if (!this.alive()) return;
    if (!this.project) { this.foot.replaceChildren(this.status()); return; }
    const targets = (this.catalogue?.targets ?? []).filter((target) => this.project.targets.includes(target.id));
    const busy = Boolean(this.working);
    const made = this.rows.some((row) => row.status !== "planned");
    this.foot.replaceChildren(
      this.opts(targets, (target) => target.id === this.target, (target) => {
        this.target = target.id;
        if (this.report?.target !== target.id) { this.report = null; if (this.view === "check") this.check(); }
        this.render();
      }, (target) => target.help, (target) => target.label),
      this.status(),
      el("span", { class: "mmc-bn-gap" }),
      el("button", { class: "mmc-bn-second", disabled: busy || !made, onclick: () => this.check() },
        [t("Check")]),
      el("button", { class: "mmc-bn-run", disabled: busy || !made, onclick: () => this.exportTarget() },
        [t("Export to {target}", { target: this.targetLabel(this.target) })]),
    );
  }

  status() {
    if (this.working) {
      return el("span", { class: "mmc-fg-status" }, [spinner(), el("span", { text: this.working })]);
    }
    if (this.error) return el("span", { class: "mmc-bn-bad", text: this.error });
    return el("span", { class: "mmc-fg-status" });
  }

  paintOut() {
    const done = this.exported;
    this.out.classList.toggle("on", Boolean(done && done.target === this.target));
    if (!done || done.target !== this.target) { this.out.replaceChildren(); return; }
    const notes = [];
    if (done.skipped.length) {
      notes.push(t("skipped: {list}", { list: done.skipped.map((s) => `${s.asset} (${s.why})`).join("; ") }));
    }
    if (done.problems.length) notes.push(t("{n} problems; press Check to see them", { n: done.problems.length }));
    this.out.replaceChildren(
      el("div", { class: "mmc-bn-outword" }, [
        el("span", { class: "mmc-bn-outname", text: t("{n} files written to {path}", {
          n: done.written.length, path: `build/${done.target}/` }) }),
        notes.length ? el("span", { class: "mmc-bn-outnote", text: notes.join(". ") }) : null,
      ]),
      el("span", { class: "mmc-bn-gap" }),
      el("span", { class: "mmc-bn-path", text: `${SHELF}${this.name}/build/${done.target}/` }),
    );
  }
}

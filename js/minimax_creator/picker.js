// The asset picker modal: tabs, search, upload, a grid of the input folder, and
// a slot counter that stops you selecting more than the model accepts.

import { el, ICONS, svg, icon, mountOverlay, dismissable } from "./dom.js";
import { listAssets, listingTruncated, viewUrl, stillUrl, upload, moveAsset,
         deleteAsset, loadPickerPrefs, savePickerPrefs } from "./api.js";
import { openTrim, trimLabel } from "./trim.js";
import { t } from "./i18n.js";

// "renders" is a tab, not a kind: it browses the output folder instead of a
// slice of the input one, and the files under it keep their own kinds — a
// picked render is attached as the video it is.
//
// Everything else about it is the same folder: shelves, stars, organize mode,
// drag-to-move and delete all work there exactly as they do on the input tabs,
// because a finished render needs filing more than an uploaded clip does. The
// only thing the gallery cannot do is take an upload, since renders arrive by
// being rendered. `activeAssets` is what keeps that one implementation: it is
// the list the current tab is looking at, and every organize path goes through
// it rather than reaching for `this.assets`.
const KIND_LABEL = { image: "Image", video: "Video", audio: "Audio", renders: "Renders" };
const ACCEPT = { image: "image/*", video: "video/*", audio: "audio/*" };
// What a configured video cell says about itself, short enough for the badge.
const TRACK_BADGE = { "picture+sound": "sound", "picture": "silent", "sound": "sound only" };
// How many cells the grid materialises per batch. A folder of hundreds of
// files used to become hundreds of cells and thumbnail requests at once, which
// froze the browser; now a sentinel at the bottom fetches the next batch as it
// scrolls into view.
const PAGE_SIZE = 60;
// Where lazy scrolling stops and pages begin. Within a page cells still arrive
// in PAGE_SIZE batches; past it a pager appears, because a ten-thousand-file
// folder should be jumped through, not scrolled end to end.
const PER_PAGE = 240;

/** The small chevron the shelf row points with: sideways between crumbs, and
 *  on a chip that has folders inside it. CSS turns it. */
function chevron(cls) {
  const mark = icon("chevron", 12);
  mark.classList.add(cls);
  return mark;
}

/**
 * @param {object} options
 * @param {string[]} options.kinds        tabs to show, in order
 * @param {string} options.kind           tab to open on
 * @param {(kind:string)=>{used:number,max:number,filesLeft:number}} options.capacity
 * @param {boolean} options.single        pick exactly one (start/end frame)
 * @param {string} options.only           show only this kind, on every tab the
 *   renders one included — a swap has to be the kind whose handle it inherits
 * @param {boolean} options.viewOnly      browse and play, select nothing — the
 *   Timeline's gallery, which has no segment to attach a pick to
 * @returns {Promise<Array|null>} chosen assets, or null if cancelled
 */
export function openPicker(options) {
  return new Promise((resolve) => {
    new Picker(options, resolve).mount();
  });
}

class Picker {
  constructor(options, resolve) {
    this.options = options;
    this.resolve = resolve;
    this.kind = options.kind || options.kinds[0];
    this.query = "";
    this.selected = [];   // asset rows, in click order
    this.assets = [];
    this.renders = [];    // the output folder, only fetched when the tab exists
    this.loaded = false;
    // Which shelf the grid shows: "all", "fav", or an input subfolder. Shelves
    // are shared across tabs — a folder is a place, not a kind.
    this.shelf = "all";
    // Set once the first listing has landed and the remembered folder has been
    // opened; every later reload leaves the shelf alone.
    this.restored = false;
    this.prefs = { favorites: [], folders: [], renderFolders: [], lastShelf: {} };
    // path -> {trim, track}. Set only for files the user opened the segment
    // editor on; everything else is attached whole and silent, as before.
    this.settings = new Map();
    // Organize mode: clicks mark files for moving or deleting instead of
    // picking them. Its own list, because `selected` means "attach to the
    // node" and is bounded by slots — marking is bounded by nothing.
    this.organize = false;
    this.marked = [];   // paths, in click order
    // Lazy grid state: which page is open, how many of its rows have cells,
    // and the cells themselves by path so a click can update one instead of
    // rebuilding all.
    this.page = 0;
    this.visibleCount = PAGE_SIZE;
    this.cells = new Map();
  }

  mount() {
    this.grid = el("div", { class: "mmc-grid" });
    this.search = el("input", {
      class: "mmc-search",
      type: "search",
      placeholder: t("Search..."),
      oninput: (event) => {
        this.query = event.target.value.toLowerCase();
        this.page = 0;
        this.visibleCount = PAGE_SIZE;
        this.renderGrid();
      },
    });

    // One kind is a title, not a choice: a lone tab-button (the timeline's
    // view-only gallery is all renders) would be a control that does nothing.
    // Same static head the timeline modal has. selectTab still walks this
    // list, and setAttribute works the same on a span.
    this.tabs = this.options.kinds.length === 1
      ? [el("span", { class: "mmc-tab", "aria-selected": "true", text: t(KIND_LABEL[this.kind]) })]
      : this.options.kinds.map((kind) =>
          el("button", {
            class: "mmc-tab",
            "aria-selected": kind === this.kind,
            onclick: () => this.selectTab(kind),
            text: t(KIND_LABEL[kind]),
          }));

    this.slots = el("span", { class: "mmc-slots" });
    // Children come from renderFoot: picking and organizing want different rows.
    this.foot = el("div", { class: "mmc-modal-foot" });
    // Floats bottom-left, mirroring the foot; renderPager fills it, and hides
    // it entirely while everything fits on one page.
    this.pager = el("div", { class: "mmc-pager" });

    this.shelfRow = el("div", { class: "mmc-shelves" });
    this.modal = el("div", { class: "mmc-modal" }, [
      el("div", { class: "mmc-modal-head" }, [
        ...this.tabs,
        el("button", { class: "mmc-close", text: "✕", onclick: () => this.close(null) }),
      ]),
      el("div", { class: "mmc-modal-bar" }, [
        this.search,
        el("button", {
          class: "mmc-organize",
          "aria-pressed": false,
          title: t("Select files to move between folders or delete"),
          onclick: () => this.setOrganize(!this.organize),
        }, [icon("folder", 14), el("span", { text: t("Organize") })]),
        el("button", { class: "mmc-upload", text: t("+  Upload {kind}", { kind: t(KIND_LABEL[this.kind].toLowerCase()) }), onclick: () => this.pickFile() }),
      ]),
      this.shelfRow,
      this.grid,
      this.pager,
      this.foot,
    ]);
    this.uploadButton = this.modal.querySelector(".mmc-upload");
    this.organizeButton = this.modal.querySelector(".mmc-organize");
    if (this.kind === "renders") this.uploadButton.style.display = "none";
    this.modal.style.position = "relative";

    this.overlay = el("div", {
      class: "mmc-overlay",
      onpointerdown: (event) => { if (event.target === this.overlay) this.close(null); },
    }, [this.modal]);

    this.unmount = mountOverlay(this.overlay, () => this.close(null));

    this.renderFoot();
    this.load();
    setTimeout(() => this.search.focus(), 30);
  }

  async load({ force = false } = {}) {
    try {
      // All three at once. The two folders have nothing to say to each other,
      // and waiting for input to come back before asking for output made a slow
      // disk twice as slow for no reason (#4).
      const [assets, renders, prefs] = await Promise.all([
        listAssets({ force }),
        this.options.kinds.includes("renders") ? listAssets({ force, root: "output" }) : [],
        loadPickerPrefs(),
      ]);
      this.assets = assets;
      this.renders = renders;
      this.prefs = prefs;
      // A mark on a file the listing no longer has is a mark on nothing.
      this.marked = this.marked.filter((p) => this.activeAssets().some((a) => a.path === p));
      this.loaded = true;
      // First listing: open where this root was last left. Only the first, and
      // only if nothing has been clicked — a reload after a move must not drag
      // the user back out of the folder they are working in.
      if (!this.restored) {
        this.restored = true;
        this.shelf = this.rememberedShelf();
      }
    } catch (error) {
      this.assets = [];
      this.renders = [];
      this.loaded = true;
      this.loadError = error.message;
    }
    this.renderShelves();
    this.renderGrid();
  }

  selectTab(kind) {
    if (kind === this.kind) return;
    const previous = this.kind;
    this.kind = kind;
    // Selections do not survive a tab change: they go into different slots.
    this.selected = [];
    for (const tab of this.tabs) tab.setAttribute("aria-selected", String(tab.textContent === t(KIND_LABEL[kind])));
    // Nothing uploads into the output folder: renders arrive by being rendered.
    // Organizing them is another matter — see the note at the top of the file.
    this.uploadButton.style.display = kind === "renders" ? "none" : "";
    if (kind !== "renders") this.uploadButton.textContent = t("+  Upload {kind}", { kind: t(KIND_LABEL[kind].toLowerCase()) });
    // Shelves are shared between the input tabs — a folder is a place, not a
    // kind — but the output folder is a different place, so crossing that line
    // opens where that root was last left rather than on a shelf that is not
    // there.
    if ((kind === "renders") !== (previous === "renders")) {
      this.shelf = this.rememberedShelf();
      this.marked = [];
    }
    this.page = 0;
    this.visibleCount = PAGE_SIZE;
    this.renderShelves();
    this.renderGrid();
    this.renderFoot();
  }

  // ---- shelves -------------------------------------------------------------

  isFav(path) {
    return this.prefs.favorites.includes(path);
  }

  toggleFav(asset) {
    const favorites = this.isFav(asset.path)
      ? this.prefs.favorites.filter((p) => p !== asset.path)
      : [...this.prefs.favorites, asset.path];
    this.prefs = { ...this.prefs, favorites };
    savePickerPrefs(this.prefs);
    this.renderShelves();
    // On the favorites shelf a star changes what is visible; anywhere else it
    // only changes the one cell.
    if (this.shelf === "fav") this.renderGrid();
    else this.refreshCell(asset);
  }

  /** The listing the current tab is browsing. The one place that knows the
   *  renders tab reads a different folder; everything organize-related goes
   *  through it, which is why there is only one implementation of any of it. */
  activeAssets() {
    return this.kind === "renders" ? this.renders : this.assets;
  }

  /** The label the upload button wears when it is not uploading. */
  uploadLabel() {
    return t("+  Upload {kind}", { kind: t(KIND_LABEL[this.kind].toLowerCase()) });
  }

  /** Take the rows an upload just produced into the input listing, newest
   *  first, which is the order the server sorts in. Uploads only ever land in
   *  input, so `renders` is not touched and does not have to be re-read. */
  absorb(added) {
    this.assets = [...added, ...this.assets.filter((a) => !added.some((b) => b.path === a.path))];
    this.renderShelves();
    this.renderGrid();
  }

  /** Which hand-made shelf names belong to the folder being browsed. Two lists
   *  because they are two folders: a shelf typed while filing renders should
   *  not appear as an empty chip over the input folder, where nothing can ever
   *  land on it. `folders` keeps its name so prefs saved before the gallery
   *  could be organized load unchanged. */
  folderKey() {
    return this.kind === "renders" ? "renderFolders" : "folders";
  }

  /** Which root the tab is browsing. The shelf is remembered per root, not per
   *  kind: the image and video tabs share a folder, so they share the place in
   *  it they were left. */
  rootKey() {
    return this.kind === "renders" ? "renders" : "input";
  }

  /** Open where the picker was last left. A remembered folder that has since
   *  been renamed, emptied out or deleted is not a place any more, so the
   *  fallback is the whole folder rather than an empty grid nobody asked for. */
  rememberedShelf() {
    const shelf = this.prefs.lastShelf?.[this.rootKey()] ?? "all";
    if (shelf === "all" || shelf === "fav") return shelf;
    return this.folders().includes(shelf) ? shelf : "all";
  }

  /** Write the shelf down as the place to open on next time. Through the same
   *  prefs file the stars go in, so it follows the ComfyUI user across browsers
   *  rather than living in one machine's localStorage. */
  rememberShelf() {
    const key = this.rootKey();
    if (this.prefs.lastShelf?.[key] === this.shelf) return;
    this.prefs = { ...this.prefs, lastShelf: { ...this.prefs.lastShelf, [key]: this.shelf } };
    savePickerPrefs(this.prefs);
  }

  /** Every place a file can live: real subfolders seen in the listing (any
   *  kind — a folder is shared) plus shelves made by hand that are still
   *  empty. A nested path brings its ancestors with it — a render written to
   *  "2026-08/take3" makes "2026-08" a place too, even though no file sits
   *  directly in it. Sorted. */
  folders() {
    const seen = new Set();
    const add = (path) => {
      const parts = path.split("/");
      for (let i = 1; i <= parts.length; i++) seen.add(parts.slice(0, i).join("/"));
    };
    for (const name of this.prefs[this.folderKey()] ?? []) add(name);
    for (const asset of this.activeAssets()) if (asset.subfolder) add(asset.subfolder);
    return [...seen].sort((a, b) => a.localeCompare(b));
  }

  /** The folders one step inside `parent` — "" is the root. The shelf row
   *  shows a level at a time, not the whole tree flattened: an output folder
   *  dated by day and cut by take has hundreds of leaves, and all of them at
   *  once is a wall of chips with a gallery hiding behind it. */
  childFolders(parent) {
    const prefix = parent ? `${parent}/` : "";
    return this.folders().filter((folder) =>
      folder !== parent && folder.startsWith(prefix) && !folder.slice(prefix.length).includes("/"));
  }

  /** Is `subfolder` that folder or anywhere under it? Browsing a folder shows
   *  everything it holds, however deep — the child chips narrow from there, so
   *  no folder is ever an empty room with the files one level down. */
  under(subfolder, folder) {
    if (!folder) return true;
    const sub = subfolder || "";
    return sub === folder || sub.startsWith(`${folder}/`);
  }

  /** The folder being browsed. "all" and the star are shelves, not places, so
   *  both sit at the root. */
  here() {
    return this.shelf === "all" || this.shelf === "fav" ? "" : this.shelf;
  }

  setShelf(shelf) {
    this.shelf = shelf;
    this.rememberShelf();
    this.page = 0;
    this.visibleCount = PAGE_SIZE;
    this.renderShelves();
    this.renderGrid();
  }

  renderShelves() {
    if (!this.loaded || this.loadError) {
      this.shelfRow.style.display = "none";
      return;
    }
    this.shelfRow.style.display = "";
    // The renders tab is not a kind, so it counts everything the output folder
    // holds; an input tab counts only its own kind, because that is the slice
    // its grid is showing.
    const scoped = this.kind === "renders"
      ? (this.options.only ? this.renders.filter((a) => a.kind === this.options.only) : this.renders)
      : this.assets.filter((a) => a.kind === this.kind);
    const count = (test) => scoped.filter(test).length;
    const here = this.here();

    // Any chip or crumb can be dropped on: dragging a cell onto a place moves
    // the file there, and that is as true of the parent above as of a child.
    const droppable = (node, target) => {
      node.addEventListener("dragover", (event) => {
        if (!this.dragging) return;
        event.preventDefault();
        node.classList.add("drop");
      });
      node.addEventListener("dragleave", () => node.classList.remove("drop"));
      node.addEventListener("drop", (event) => {
        event.preventDefault();
        node.classList.remove("drop");
        this.moveTo(target);
      });
      return node;
    };

    const chip = ({ key, label, title, iconName, n, deep, drops = true }) => {
      const node = el("button", {
        class: "mmc-shelf",
        "aria-selected": this.shelf === key,
        title: title || label,
      }, [
        ...(iconName ? [icon(iconName, 13)] : []),
        ...(label ? [el("span", { class: "mmc-shelf-name", text: label })] : []),
        ...(n ? [el("span", { class: "mmc-shelf-n", text: String(n) })] : []),
        // A chip that has folders of its own says so, so the row reads as a
        // way in rather than a flat list of filters.
        ...(deep ? [chevron("mmc-shelf-into")] : []),
      ]);
      node.addEventListener("click", () => this.setShelf(key));
      return drops ? droppable(node, key) : node;
    };

    // The trail: where you are, and every step back out. Always present, so
    // leaving a folder is one click however deep it goes.
    const crumbs = el("div", { class: "mmc-crumbs" });
    const crumb = (key, label, current) => {
      const node = el("button", {
        class: "mmc-crumb", "aria-selected": current, title: label,
        onclick: () => this.setShelf(key),
      }, [el("span", { text: label })]);
      return droppable(node, key);
    };
    crumbs.appendChild(crumb("all", t("All"), this.shelf === "all"));
    const parts = here ? here.split("/") : [];
    parts.forEach((part, i) => {
      crumbs.appendChild(chevron("mmc-crumb-sep"));
      crumbs.appendChild(crumb(parts.slice(0, i + 1).join("/"), part, i === parts.length - 1));
    });

    // One line, scrolled sideways when it needs to be: the row keeps its
    // height no matter how many folders a level holds, and the gallery keeps
    // the rest of the modal.
    const strip = el("div", { class: "mmc-shelf-strip" });
    if (!here) {
      strip.appendChild(chip({
        key: "fav", label: "", title: t("favorites"), iconName: "star",
        n: count((a) => this.isFav(a.path)), drops: false,
      }));
    }
    for (const folder of this.childFolders(here)) {
      strip.appendChild(chip({
        key: folder, label: folder.slice(here ? here.length + 1 : 0), title: folder, iconName: "folder",
        n: count((a) => this.under(a.subfolder, folder)),
        deep: this.childFolders(folder).length > 0,
      }));
    }
    strip.addEventListener("scroll", () => this.markStripEdges(strip));
    // A trackpad swipes sideways on its own; a wheel only ever sends deltaY,
    // and without this the row is unreachable for anyone using one.
    strip.addEventListener("wheel", (event) => {
      if (event.deltaX || !event.deltaY) return;
      event.preventDefault();
      strip.scrollLeft += event.deltaY;
    }, { passive: false });

    this.shelfRow.replaceChildren(crumbs, strip, this.newShelfChip(here));
    requestAnimationFrame(() => this.markStripEdges(strip));
  }

  /** Fade the end the row runs past, and only that end — a strip that fits
   *  shows no fade at all, so the cue always means "there is more". */
  markStripEdges(strip) {
    if (!strip.isConnected) return;
    const slack = strip.scrollWidth - strip.clientWidth;
    strip.classList.toggle("more-l", strip.scrollLeft > 2);
    strip.classList.toggle("more-r", slack > 2 && strip.scrollLeft < slack - 2);
  }

  /** The trailing "+" that flips into a name field. A new shelf is only a
   *  remembered name until a file lands on it — the directory itself is
   *  created by the first upload or move. It lands inside the folder being
   *  browsed, so the row makes the tree it navigates. */
  newShelfChip(parent = "") {
    const add = el("button", { class: "mmc-shelf mmc-shelf-new", text: "+", title: t("New shelf") });
    add.addEventListener("click", () => {
      const field = el("input", {
        class: "mmc-shelf-input", type: "text", placeholder: t("shelf name"),
        onkeydown: (event) => {
          event.stopPropagation();
          if (event.key === "Escape") this.renderShelves();
          if (event.key !== "Enter") return;
          const typed = field.value.trim().replace(/^\/+|\/+$/g, "");
          if (!typed || /(^|\/)\.|\\/.test(typed)) { this.warn(t("Shelf names cannot start with a dot.")); return; }
          const name = parent ? `${parent}/${typed}` : typed;
          const key = this.folderKey();
          if (!this.prefs[key].includes(name)) {
            this.prefs = { ...this.prefs, [key]: [...this.prefs[key], name] };
            savePickerPrefs(this.prefs);
          }
          this.setShelf(name);
        },
        onblur: () => this.renderShelves(),
      });
      add.replaceWith(field);
      field.focus();
    });
    return add;
  }

  /** Drop a dragged cell onto a shelf. In organize mode a marked cell carries
   *  the whole marked set with it — drag and the Move to… menu are two doors
   *  to the same room. */
  async moveTo(folder) {
    const dragged = this.dragging;
    this.dragging = null;
    if (!dragged) return;
    const batch = this.organize && this.marked.includes(dragged.path)
      ? this.activeAssets().filter((asset) => this.marked.includes(asset.path))
      : [dragged];
    await this.moveMany(batch, folder === "all" ? "" : folder);
  }

  /** Move files into a subfolder of the folder they are in ("" is its root),
   *  carrying each one's
   *  star, segment settings, mark and selection over to its new path. Per-file
   *  failures (a name collision, say) skip that file rather than the batch. */
  async moveMany(batch, target) {
    const failures = [];
    for (const asset of batch) {
      if ((asset.subfolder || "") === target) continue;
      try {
        const path = await moveAsset(asset.path, target);
        const rename = (p) => (p === asset.path ? path : p);
        this.prefs = { ...this.prefs, favorites: this.prefs.favorites.map(rename) };
        if (this.settings.has(asset.path)) {
          this.settings.set(path, this.settings.get(asset.path));
          this.settings.delete(asset.path);
        }
        this.marked = this.marked.map(rename);
        for (const chosen of this.selected) {
          if (chosen.path === asset.path) { chosen.path = path; chosen.subfolder = target; }
        }
      } catch (error) {
        failures.push(t("{name}: {error}", { name: asset.name, error: error.message }));
      }
    }
    savePickerPrefs(this.prefs);
    await this.load({ force: true });
    this.renderFoot();
    if (failures.length) {
      this.warn(failures.length === 1 ? failures[0]
        : t("{count} files stayed put — {first}", { count: failures.length, first: failures[0] }));
    }
  }

  // ---- organize mode -------------------------------------------------------

  setOrganize(on) {
    if (this.organize === on) return;
    this.organize = on;
    this.marked = [];
    this.organizeButton.setAttribute("aria-pressed", String(on));
    this.renderGrid();
    this.renderFoot();
  }

  mark(asset) {
    const at = this.marked.indexOf(asset.path);
    if (at >= 0) this.marked.splice(at, 1);
    else this.marked.push(asset.path);
    this.syncSelected();
    this.renderFoot();
  }

  markedAssets() {
    return this.activeAssets().filter((asset) => this.marked.includes(asset.path));
  }

  /** The Move to… popover: every shelf, the root, and a field for a new one.
   *  Picking a destination moves the whole marked set. */
  moveMenu() {
    const menu = el("div", { class: "mmc-move-menu" });
    const go = (target) => { close(); this.moveMany(this.markedAssets(), target); };
    menu.appendChild(el("button", { class: "mmc-move-opt", onclick: () => go("") },
      [icon("image", 13), el("span", {
        text: this.kind === "renders" ? t("Output folder (root)") : t("Input folder (root)") })]));
    // The whole tree, but read as a tree: each folder under the one it sits in,
    // named by its own last step. A flat column of full paths is unreadable
    // once the output folder is a few days deep.
    for (const folder of this.folders()) {
      const depth = folder.split("/").length - 1;
      const option = el("button", { class: "mmc-move-opt", title: folder, onclick: () => go(folder) },
        [icon("folder", 13), el("span", { text: folder.slice(folder.lastIndexOf("/") + 1) })]);
      option.style.paddingLeft = `${10 + depth * 14}px`;
      menu.appendChild(option);
    }
    // The same rules as newShelfChip: a name that needs rewriting is refused.
    const field = el("input", {
      class: "mmc-shelf-input", type: "text", placeholder: t("New folder…"),
      onkeydown: (event) => {
        event.stopPropagation();
        if (event.key === "Escape") { close(); return; }
        if (event.key !== "Enter") return;
        const name = field.value.trim().replace(/^\/+|\/+$/g, "");
        if (!name || /(^|\/)\.|\\/.test(name)) { this.warn(t("Folder names cannot start with a dot.")); return; }
        go(name);
      },
    });
    menu.appendChild(field);
    this.modal.appendChild(menu);
    const close = dismissable(menu);
  }

  /** Delete is irreversible, so the button asks once: the first press arms it,
   *  the second (within a few seconds) fires. */
  confirmDelete() {
    if (!this.deleteButton || !this.marked.length) return;
    if (!this.deleteArmed) {
      this.deleteArmed = true;
      this.deleteButton.textContent = t("Really delete {count}?", { count: this.marked.length });
      this.deleteButton.classList.add("armed");
      this.armTimer = setTimeout(() => this.renderFoot(), 5000);
      return;
    }
    this.deleteMarked();
  }

  async deleteMarked() {
    this.deleteButton.disabled = true;
    this.deleteButton.textContent = t("Deleting…");
    const failures = [];
    for (const asset of this.markedAssets()) {
      try {
        await deleteAsset(asset.path);
        this.settings.delete(asset.path);
        this.prefs = { ...this.prefs, favorites: this.prefs.favorites.filter((p) => p !== asset.path) };
        this.selected = this.selected.filter((chosen) => chosen.path !== asset.path);
        this.marked = this.marked.filter((p) => p !== asset.path);
      } catch (error) {
        failures.push(t("{name}: {error}", { name: asset.name, error: error.message }));
      }
    }
    savePickerPrefs(this.prefs);
    await this.load({ force: true });
    this.renderFoot();
    if (failures.length) {
      this.warn(failures.length === 1 ? failures[0]
        : t("{count} files not deleted — {first}", { count: failures.length, first: failures[0] }));
    }
  }

  visible() {
    const onShelf = this.shelf === "all" ? () => true
      : this.shelf === "fav" ? (asset) => this.isFav(asset.path)
        : (asset) => this.under(asset.subfolder, this.shelf);
    // "renders" is a tab and not a kind, so it shows every kind the output
    // folder holds — a still and the clip it seeded are both renders. Unless
    // the caller is replacing one file with another, where anything but that
    // kind is a pick it would have to refuse.
    const only = this.options.only;
    const onKind = only ? (asset) => asset.kind === only
      : this.kind === "renders" ? () => true : (asset) => asset.kind === this.kind;
    return this.activeAssets().filter((asset) =>
      onKind(asset) && onShelf(asset)
      && (!this.query || asset.path.toLowerCase().includes(this.query)));
  }

  /** The slot a selection will actually take. A video kept for its soundtrack
   *  alone costs an audio slot and no video one — the same rule state.js and
   *  compile.py bucket by — so the counter has to follow it across tabs. */
  targetKind(asset) {
    return this.settings.get(asset.path)?.track === "sound" ? "audio" : asset.kind;
  }

  claimed(kind) {
    return this.selected.filter((asset) => this.targetKind(asset) === kind).length;
  }

  /**
   * Does what is selected fit in `kind`'s bucket, with `extra` more files on top?
   * `extra: 1` asks whether one more can be added; `0` re-checks a selection that
   * has just moved between buckets.
   */
  fits(kind, extra = 0) {
    if (this.options.single) return this.selected.length + extra <= 1;
    const { used, max, filesLeft } = this.options.capacity(kind);
    // filesLeft is the shared total and reads the same whichever bucket is
    // asked, so every selection counts against it, not just this bucket's.
    return used + this.claimed(kind) + extra <= max && this.selected.length + extra <= filesLeft;
  }

  room(kind) {
    return this.fits(kind, 1);
  }

  renderGrid() {
    this.observer?.disconnect();
    this.observer = null;
    this.cells.clear();
    this.grid.replaceChildren();
    this.pages = 1;
    this.renderPager();
    if (!this.loaded) {
      this.grid.appendChild(el("div", { class: "mmc-empty", text: t("Loading…") }));
      return;
    }
    if (this.loadError) {
      this.grid.appendChild(el("div", { class: "mmc-empty", text: t("Could not read the input folder: {error}", { error: this.loadError }) }));
      return;
    }
    const rows = this.visible();
    if (!rows.length) {
      this.grid.appendChild(el("div", {
        class: "mmc-empty",
        text: this.query
          ? (this.kind === "renders"
              ? t("No renders matching “{query}”.", { query: this.query })
              : t("No {kind} files matching “{query}”.", { kind: t(this.kind), query: this.query }))
          : this.shelf === "fav"
            ? t("No favorites yet — hover a file and hit the star.")
            : this.shelf !== "all"
              ? this.kind === "renders"
                ? t("Nothing on this shelf yet — drag renders here, or point a node's output folder at it.")
                : t("Nothing on this shelf yet — drag files here, or upload while it is open.")
              : this.kind === "renders"
                ? t("Nothing in the output folder yet — queue a render.")
                : t("No {kind} files in the input folder yet — upload one.", { kind: t(this.kind) }),
      }));
      return;
    }
    // Clamp rather than reset: a delete that empties the last page should land
    // on the new last page, not back at the first.
    this.pages = Math.ceil(rows.length / PER_PAGE);
    this.page = Math.min(this.page, this.pages - 1);
    this.gridRows = rows.slice(this.page * PER_PAGE, (this.page + 1) * PER_PAGE);
    this.renderPager();
    this.appendCells(0);
  }

  setPage(page) {
    if (page === this.page || page < 0 || page >= this.pages) return;
    this.page = page;
    this.visibleCount = PAGE_SIZE;
    this.renderGrid();
    this.grid.scrollTop = 0;
  }

  /** The page numbers worth a button: first, last, and the current page's
   *  neighbours, with a gap marker over each run left out. */
  pageList() {
    const want = new Set([0, this.pages - 1, this.page - 1, this.page, this.page + 1]);
    const list = [];
    for (let i = 0; i < this.pages; i++) {
      if (want.has(i)) list.push(i);
      else if (list[list.length - 1] !== "gap") list.push("gap");
    }
    return list;
  }

  renderPager() {
    if (this.pages <= 1) {
      this.pager.style.display = "none";
      return;
    }
    this.pager.style.display = "";
    const button = (label, page, { current = false, disabled = false } = {}) =>
      el("button", {
        class: "mmc-page", text: label,
        "aria-current": current,
        disabled: disabled || null,
        onclick: () => this.setPage(page),
      });
    this.pager.replaceChildren(
      button("‹", this.page - 1, { disabled: this.page === 0 }),
      ...this.pageList().map((p) => p === "gap"
        ? el("span", { class: "mmc-page-gap", text: "…" })
        : button(String(p + 1), p, { current: p === this.page })),
      button("›", this.page + 1, { disabled: this.page === this.pages - 1 }),
    );
  }

  /** Materialise cells from `from` up to `visibleCount`. When rows remain, a
   *  sentinel cell watches the grid's own scrollport and appends the next
   *  batch as it comes into view — already-built cells are never touched, so
   *  their thumbnails are never re-fetched. */
  appendCells(from) {
    const to = Math.min(this.visibleCount, this.gridRows.length);
    for (const asset of this.gridRows.slice(from, to)) {
      const cell = this.cell(asset);
      this.cells.set(asset.path, cell);
      this.grid.appendChild(cell);
    }
    if (to >= this.gridRows.length) {
      // The very end of the listing: if the server capped it, this is the one
      // place a browsing user can be told the folder holds more.
      const root = this.kind === "renders" ? "output" : "input";
      if (this.page === this.pages - 1 && listingTruncated(root)) {
        this.grid.appendChild(el("div", {
          class: "mmc-grid-note",
          text: t("The folder holds more — only the newest {count} files are listed.", { count: this.activeAssets().length }),
        }));
      }
      return;
    }
    const sentinel = el("div", { class: "mmc-grid-sentinel" });
    this.grid.appendChild(sentinel);
    this.observer = new IntersectionObserver((entries) => {
      if (!entries.some((entry) => entry.isIntersecting)) return;
      this.observer.disconnect();
      sentinel.remove();
      this.visibleCount = to + PAGE_SIZE;
      this.appendCells(to);
    }, { root: this.grid, rootMargin: "300px" });
    this.observer.observe(sentinel);
  }

  /** Rebuild one cell in place — for a change that lives inside it, like its
   *  star or segment badge. Cells not yet materialised have nothing to show. */
  refreshCell(asset) {
    const old = this.cells.get(asset.path);
    if (!old) return;
    const fresh = this.cell(asset);
    this.cells.set(asset.path, fresh);
    old.replaceWith(fresh);
  }

  /** Reflect the selection (or, organizing, the marks) onto the cells already
   *  in the DOM. This is what a click changes — rebuilding the whole grid for
   *  it re-created every cell and re-fired every thumbnail request, which is
   *  what made large folders freeze. */
  syncSelected() {
    for (const [path, cell] of this.cells) {
      const chosen = this.organize
        ? this.marked.includes(path)
        : this.selected.some((a) => a.path === path);
      cell.setAttribute("aria-selected", String(chosen));
    }
  }

  cell(asset) {
    const chosen = this.organize
      ? this.marked.includes(asset.path)
      : this.selected.some((a) => a.path === asset.path);
    // A div rather than a button: the segment badge is itself a button, and a
    // button inside a button is not something the DOM is willing to lay out.
    const cell = el("div", {
      class: "mmc-cell",
      role: "button",
      tabindex: "0",
      "aria-selected": chosen,
      title: t("{path} — double-click to view", { path: asset.path }),
      // Double-clicks are detected by hand rather than with dblclick: the
      // second click re-toggles first, so viewing leaves the selection exactly
      // where it stood, and viewOnly grids get a single-click view.
      onclick: () => {
        const now = Date.now();
        const double = this.lastClick
          && this.lastClick.path === asset.path && now - this.lastClick.at < 400;
        this.lastClick = double ? null : { path: asset.path, at: now };
        if (this.organize) {
          this.mark(asset);
          if (double) this.view(asset);
          return;
        }
        if (this.options.viewOnly) {
          if (!double) this.view(asset);
          return;
        }
        this.toggle(asset);
        if (double) this.view(asset);
      },
      onkeydown: (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        if (this.organize) this.mark(asset);
        else this.toggle(asset);
      },
    });

    // Which route shows this file is `api.stillUrl`'s to know — the same
    // question the preset library's cards ask, answered in one place.
    const still = stillUrl(asset);
    if (still) {
      // Filenames reach the DOM only as attributes/text, never as markup.
      const thumb = el("img", { src: still, loading: "lazy", alt: asset.name });
      // A clip the decoder cannot open answers 404, and the cell falls back to
      // the same icon tile audio uses rather than showing a broken image.
      if (asset.kind === "video") {
        thumb.addEventListener("error", () => thumb.replaceWith(this.fallback(asset, "video")));
      }
      cell.appendChild(thumb);
    } else {
      cell.appendChild(this.fallback(asset, "audio"));
    }

    cell.appendChild(el("div", { class: "mmc-check" }));
    // No segment badge while organizing: configuring a segment selects the
    // file for attachment, which is exactly not what a mark means.
    if (asset.kind !== "image" && !this.organize) cell.appendChild(this.badge(asset));
    if (asset.kind !== "audio") cell.appendChild(el("div", { class: "mmc-cell-name", text: asset.name }));

    // Stars and dragging on every tab, renders included: a finished clip is the
    // thing most worth starring, and where a render was *written* is not where
    // it has to stay — the keeper gets dragged out of the dated folder it
    // landed in and onto a shelf of its own.
    const starred = this.isFav(asset.path);
    cell.appendChild(el("button", {
      class: `mmc-cell-star${starred ? " on" : ""}`,
      title: starred ? t("Remove from favorites") : t("Add to favorites"),
      onclick: (event) => { event.stopPropagation(); this.toggleFav(asset); },
    }, [icon("star", 13)]));

    // A file's home is worth a caption whenever the row above does not already
    // say it: the full path out on All, and the part below here when the grid
    // is showing what a folder holds further down.
    const here = this.here();
    const home = asset.subfolder || "";
    if (home && home !== here) {
      cell.appendChild(el("div", {
        class: "mmc-cell-home",
        text: here ? home.slice(here.length + 1) : home,
      }));
    }

    // Organizing is dragging: the cell rides to a shelf chip. The chips take
    // it from `this.dragging` — dataTransfer only carries strings.
    cell.draggable = true;
    cell.addEventListener("dragstart", (event) => {
      this.dragging = asset;
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", asset.path);
      this.modal.classList.add("dragging");
    });
    cell.addEventListener("dragend", () => {
      this.dragging = null;
      this.modal.classList.remove("dragging");
    });
    return cell;
  }

  /** The icon tile a cell shows when there is no picture to show: every audio
   *  file, and a video whose first frame could not be decoded. */
  fallback(asset, kind) {
    return el("div", { class: "mmc-cell-fallback" }, [svg(ICONS[kind], 26), el("span", { text: asset.name })]);
  }

  /** The segment/sound button on a video or audio cell. Hidden until the cell is
   *  hovered or selected unless it has something to say, so a grid of untouched
   *  files stays as quiet as it was before. */
  badge(asset) {
    const setting = this.settings.get(asset.path);
    const parts = [];
    if (setting?.trim) parts.push(trimLabel(setting));
    // Only once the editor has been used: until then the track is still the
    // default, and the badge would be claiming a decision nobody made.
    if (setting?.track && asset.kind === "video") parts.push(t(TRACK_BADGE[setting.track]));
    return el("button", {
      class: `mmc-cell-trim${parts.length ? " set" : ""}`,
      title: asset.kind === "video"
        ? t("Use only part of this clip, bring its soundtrack along, or take the sound on its own")
        : t("Use only part of this file"),
      onclick: (event) => { event.stopPropagation(); this.editSegment(asset); },
    }, [icon("scissors", 12), el("span", { text: parts.join(" · ") || t("Segment") })]);
  }

  async editSegment(asset) {
    const setting = this.settings.get(asset.path) || {};
    const result = await openTrim({
      path: asset.path,
      kind: asset.kind,
      trim: setting.trim ?? null,
      // undefined until the editor has been opened once: the track switch shows
      // the default rather than a stale "picture".
      track: setting.track,
      showTrack: asset.kind === "video",
    });
    if (!result) return;
    // Stored even when it matches the default, because "the user looked at this
    // and left the sound off" has to outrank the on-by-default rule.
    this.settings.set(asset.path, result);
    const selected = this.selected.some((a) => a.path === asset.path);
    // Switching to sound-only moves the file between buckets, and the one it
    // lands in may be full. Say so and put the choice back rather than letting a
    // selection through that compile.py would refuse.
    if (selected && !this.fits(this.targetKind(asset))) {
      this.settings.set(asset.path, { ...result, track: setting.track });
      this.refreshCell(asset);   // the segment still changed, even if the track did not
      this.warn(t("No {kind} slot left for {name}.", { kind: t(this.targetKind(asset)), name: asset.name }));
      return;
    }
    this.refreshCell(asset);
    // Configuring a file is how you say you want it: select it if it wasn't.
    if (!selected) this.toggle(asset);
    else this.renderFoot();
  }

  /** A transient line in the footer, where the slot counter already is — the
   *  picker has no other place to answer back. */
  warn(message) {
    this.slots.textContent = message;
    this.slots.classList.add("full");
    clearTimeout(this.warnTimer);
    this.warnTimer = setTimeout(() => this.renderFoot(), 4000);
  }

  /** Full size, in an overlay above the modal: a video plays with the
   *  browser's controls and its sound, an image just gets the room the grid
   *  cell could not give it. Opened by double-click on any tab. */
  view(asset) {
    let unmount;
    const media = asset.kind === "audio"
      ? el("audio", { class: "mmc-light-audio", src: viewUrl(asset.path), controls: true, autoplay: true })
      : asset.kind === "video"
        ? el("video", { class: "mmc-light-media", src: viewUrl(asset.path), controls: true, autoplay: true, loop: true })
        : el("img", { class: "mmc-light-media", src: viewUrl(asset.path), alt: asset.name });
    const overlay = el("div", {
      class: "mmc-overlay",
      onpointerdown: (event) => { if (event.target === overlay) unmount(); },
    }, [
      el("div", { class: "mmc-light" }, [media, el("div", { class: "mmc-light-name", text: asset.name })]),
    ]);
    unmount = mountOverlay(overlay, () => unmount());
  }

  toggle(asset) {
    if (this.options.viewOnly) return;
    const at = this.selected.findIndex((a) => a.path === asset.path);
    if (at >= 0) this.selected.splice(at, 1);
    else if (this.options.single) this.selected = [asset];
    else if (this.room(this.targetKind(asset))) this.selected.push(asset);
    else return;  // at capacity: the counter already says why
    this.syncSelected();
    this.renderFoot();
  }

  renderFoot() {
    clearTimeout(this.warnTimer);
    clearTimeout(this.armTimer);
    this.deleteArmed = false;
    // viewOnly has nothing to commit, but organizing still needs its buttons.
    this.foot.style.display = this.options.viewOnly && !this.organize ? "none" : "";

    if (this.organize) {
      this.slots.classList.remove("full");
      this.slots.textContent = this.marked.length
        ? t("{count} marked", { count: this.marked.length })
        : t("Click files to mark them");
      this.deleteButton = el("button", {
        class: "mmc-del", text: t("Delete"), disabled: !this.marked.length,
        onclick: () => this.confirmDelete(),
      });
      this.foot.replaceChildren(
        this.slots,
        el("button", {
          class: "mmc-ghost", text: t("Move to…"), disabled: !this.marked.length,
          onclick: () => this.moveMenu(),
        }),
        this.deleteButton,
        el("button", { class: "mmc-add", text: t("Done"), onclick: () => this.setOrganize(false) }),
      );
      return;
    }

    this.deleteButton = null;
    this.addButton = el("button", { class: "mmc-add", text: t("Add"), onclick: () => this.commit() });
    this.foot.replaceChildren(
      this.slots,
      el("button", { class: "mmc-ghost", text: t("Cancel"), onclick: () => this.close(null) }),
      this.addButton,
    );
    if (this.options.single) {
      this.slots.textContent = this.selected.length ? t("1 selected") : t("Pick one");
      this.slots.classList.remove("full");
    } else {
      // The renders tab has no bucket of its own — a picked render is a video
      // and counts where a video counts.
      const bucket = this.kind === "renders" ? "video" : this.kind;
      const { used, max } = this.options.capacity(bucket);
      const filled = used + this.claimed(bucket);
      // A clip taken for its sound alone is not in this tab's bucket, so it is
      // reported against the one it does land in rather than silently omitted.
      const elsewhere = this.selected.length - this.claimed(bucket);
      const audio = this.options.capacity("audio");
      this.slots.textContent = t("{filled} / {max} slots filled", { filled, max })
        + (elsewhere ? t(" · {used} / {max} audio", { used: audio.used + this.claimed("audio"), max: audio.max }) : "");
      this.slots.classList.toggle("full", filled >= max);
    }
    this.addButton.disabled = this.selected.length === 0;
  }

  pickFile() {
    const input = el("input", { type: "file", accept: ACCEPT[this.kind], multiple: !this.options.single });
    input.style.display = "none";
    input.addEventListener("change", async () => {
      const files = Array.from(input.files || []);
      input.remove();
      if (!files.length) return;
      this.uploadButton.disabled = true;
      this.uploadButton.textContent = t("Uploading…");
      // An upload lands on the shelf being looked at — that is what makes a
      // shelf a place rather than a filter.
      const into = this.shelf === "all" || this.shelf === "fav" ? "" : this.shelf;
      try {
        const added = [];
        for (const file of files) added.push(await upload(file, into));
        // "Uploading…" stops when the uploading does. It used to stay up for the
        // re-listing that followed, so a finished upload read as a stuck one and
        // got reported as one (#4).
        this.uploadButton.textContent = this.uploadLabel();
        // Each row came back complete, so the grid redraws from what is already
        // known. A file neither the browser nor core can classify has no kind to
        // draw a cell with, and that one case reads the folder properly.
        if (added.every((asset) => asset.kind)) this.absorb(added);
        else await this.load({ force: true });
      } catch (error) {
        this.grid.replaceChildren(el("div", { class: "mmc-empty", text: t("Upload failed: {error}", { error: error.message }) }));
      } finally {
        this.uploadButton.disabled = false;
        this.uploadButton.textContent = this.uploadLabel();
      }
    });
    document.body.appendChild(input);
    input.click();
  }

  commit() {
    if (!this.selected.length) return;
    this.close(this.selected.map((asset) => ({ ...asset, ...(this.settings.get(asset.path) || {}) })));
  }

  close(result) {
    clearTimeout(this.warnTimer);
    clearTimeout(this.armTimer);
    this.observer?.disconnect();
    this.unmount();
    this.resolve(result);
  }
}

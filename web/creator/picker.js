// The asset picker modal: tabs, search, upload, a grid of the input folder, and
// a slot counter that stops you selecting more than the model accepts.

import { el, ICONS, svg, icon, mountOverlay, dismissable } from "./dom.js";
import { listAssets, listingTruncated, listedFolders, makeFolder, removeFolder,
         viewUrl, stillUrl, upload, moveAsset,
         deleteAsset, loadPickerPrefs, savePickerPrefs, buildPlate,
         cutPanel } from "./api.js";
import { openTrim, trimLabel } from "./trim.js";
import { openSubjectView, greyField } from "./subject.js";
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
const KIND_LABEL = { image: "Image", video: "Video", audio: "Audio",
                     renders: "Renders", guides: "Guide" };
const ACCEPT = { image: "image/*", video: "video/*", audio: "audio/*",
                 guides: "video/*" };

// Where the ControlNet bench writes, and so the whole of what the guide tab
// shows. Mirrors `control.SUBFOLDER`.
//
// A tab and not a kind, exactly as "renders" is one: that tab browses a
// different *folder* while its files keep their own kinds, and this browses a
// different *corner* of the input folder while its files stay videos. Both are
// the same idea — a tab is a place to look, a kind is what a file is — and
// making the guide a fourth kind would have meant teaching the caps, the
// grammar and compile.py about a kind that does not exist.
const GUIDE_SUBFOLDER = "continuity/control";
const isGuide = (asset) =>
  asset.kind === "video" && (asset.subfolder || "").startsWith(GUIDE_SUBFOLDER);
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
 *   how many slots the caller's buckets have left. **Optional.** Omitted means
 *   the caller is not bounded by reference slots at all — the sound lane is
 *   bounded by the length of the piece, not by a bucket — and the picker then
 *   counts what is selected instead of pricing it against a maximum. It used to
 *   be read unconditionally, so a caller that had no slots to report crashed the
 *   modal on mount rather than being told it had to invent some.
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
    this.prefs = { favorites: [], lastShelf: {} };
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

    // ---- the sheet ---------------------------------------------------------
    //
    // `options.plate` is the family's answer to "how is a sheet made"
    // (`state.plateSpec`): the backdrop its panels sit on, whether a fresh pick
    // starts out cut, the matte model, the canvas — plus `sheet: true` on a
    // family whose image references *are* one composite sheet (LTX 2.5), and
    // the panels of a sheet already attached, which is what makes pairing
    // survive reopening the picker.
    this.plate = options.plate || null;
    // path -> whether that picture is cut out of its background. Absent means
    // the family's default, so a picture the user has not touched follows the
    // family and one they have touched stays where they put it.
    this.cuts = new Map((options.plate?.panels ?? [])
      .map((panel) => [panel.path, Boolean(panel.cut)]));
    // path -> [x, y, w, h] fractions of the canvas: where the user put that
    // panel in the sheet editor. Absent means the grid cell, which is where
    // every panel sat before arranging existed.
    this.rects = new Map((options.plate?.panels ?? [])
      .filter((panel) => panel.rect).map((panel) => [panel.path, [...panel.rect]]));
    // path -> [{x, y, include}]: the SAM clicks that said which subject the
    // scissors mean. Fractions of the source picture, so they survive resizes.
    this.points = new Map((options.plate?.panels ?? [])
      .filter((panel) => panel.points?.length)
      .map((panel) => [panel.path, panel.points.map((point) => ({ ...point }))]));
    // The connected group: paths, in layout order. On a sheet family every
    // selected image is a panel and this stays empty; elsewhere it is what
    // Connect built, and it holds until the sheet is taken off the piece.
    this.sheet = this.plate?.sheet ? [] : (this.plate?.panels ?? []).map((p) => p.path);
    this.committing = false;   // a commit that has to build the sheet first, in flight
    // path -> {key, url, pending}: the grid's own cut previews, from the same
    // in-memory route the sheet stage reads. A cell whose scissors are on shows
    // the cutout itself — the chip's promise is the picture, not a state.
    this.cutUrls = new Map();
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
      // A drag that ends anywhere but a shelf chip stops here. Left to bubble,
      // it reaches ComfyUI's own document drop handler, which reads the drag as
      // a file to import and tries to write a file named after the thumbnail's
      // URL into the input folder.
      ondragover: (event) => event.preventDefault(),
      ondrop: (event) => { event.preventDefault(); event.stopPropagation(); },
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
        // Re-opened on a card that already carries a sheet: the pictures it
        // was made of come back selected and paired, in the order they are
        // laid out, so changing one panel is changing one panel rather than
        // building the sheet again from nothing. A source that has since been
        // deleted simply is not there — the sheet keeps the panel until the
        // selection is committed, which is the same bargain every attached
        // file has.
        this.selected = (this.plate?.panels ?? [])
          .map((panel) => this.assets.find((a) => a.path === panel.path)
                       ?? this.renders.find((a) => a.path === panel.path))
          .filter(Boolean);
      }
    } catch (error) {
      this.assets = [];
      this.renders = [];
      this.loaded = true;
      this.loadError = error.message;
    }
    this.renderShelves();
    this.renderGrid();
    this.renderFoot();
    // Sent here to edit an attached sheet (the card's "Edit sheet…" and
    // "Combine…"):
    // the editor is the point, so it opens itself over the grid.
    if (this.plate?.edit && !this.editOpened && this.sheetPanels().length) {
      this.editOpened = true;
      this.openSheet();
    }
  }

  selectTab(kind) {
    if (kind === this.kind) return;
    const previous = this.kind;
    this.kind = kind;
    // Selections do not survive a tab change: they go into different slots.
    // The sheet does not either — its panels were part of the selection.
    this.selected = [];
    this.sheet = [];
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

  /** Which root the tab is browsing, as the server names it. */
  rootName() {
    return this.kind === "renders" ? "output" : "input";
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

  /** Every place a file can live, as the disk has them.
   *
   *  One source, and it is the filesystem: the listing walks the root and says
   *  which directories are under it, empty ones included. Nothing is added from
   *  memory — a shelf the picker remembers and the disk does not is a shelf that
   *  outlives the folder it named, which is exactly what went wrong (#40).
   *
   *  A nested path still brings its ancestors, because a walk can miss one an
   *  asset path implies: the subfolders of the files are folded in for the same
   *  reason, so a listing and its rows can never disagree about where a file is.
   *  Sorted. */
  folders() {
    const seen = new Set();
    const add = (path) => {
      const parts = path.split("/");
      for (let i = 1; i <= parts.length; i++) seen.add(parts.slice(0, i).join("/"));
    };
    for (const name of listedFolders(this.rootName())) add(name);
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
      : this.kind === "guides" ? this.assets.filter(isGuide)
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

    const drop = this.emptyShelfChip(here);
    this.shelfRow.replaceChildren(crumbs, strip, this.newShelfChip(here),
                                  ...(drop ? [drop] : []));
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

  /** The trailing "+" that flips into a name field. A new shelf is the folder:
   *  the name goes straight to `mkdir` and the next listing finds it there.
   *
   *  It used to be a name the picker remembered until a file landed on it, which
   *  is how a shelf came to outlive its directory (#40). Making it now costs one
   *  round trip and means the row is never showing a place that is not there.
   *
   *  It lands inside the folder being browsed, so the row makes the tree it
   *  navigates. */
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
          this.addShelf(parent ? `${parent}/${typed}` : typed);
        },
        onblur: () => this.renderShelves(),
      });
      add.replaceWith(field);
      field.focus();
    });
    return add;
  }

  /** The "throw this shelf away" chip, or null where there is nothing to throw.
   *
   *  Only over an empty folder, and only the one being browsed. A shelf used to
   *  be a name nobody could get rid of because nobody could see it; it is a
   *  directory now, and a directory somebody made by mistake has to be
   *  removable from where they made it. Full ones are a file manager's job —
   *  the server refuses those, and this does not offer them.
   *
   *  Asks once, the way Delete does: the press is irreversible and it sits at
   *  the end of a row you click along. */
  emptyShelfChip(here) {
    if (!here) return null;
    if (this.childFolders(here).length) return null;
    if (this.activeAssets().some((asset) => this.under(asset.subfolder, here))) return null;
    const label = el("span", { text: t("Remove shelf") });
    const node = el("button", {
      class: "mmc-shelf mmc-shelf-drop",
      title: t("Remove this empty folder from the disk."),
      onclick: () => {
        if (node.classList.contains("armed")) { this.dropShelf(here); return; }
        node.classList.add("armed");
        label.textContent = t("Really remove?");
        setTimeout(() => { if (node.isConnected) this.renderShelves(); }, 5000);
      },
    }, [icon("close", 13), label]);
    return node;
  }

  /** Make the folder, then open it. A refusal — a name the server will not take,
   *  a read-only disk — leaves the row exactly as it was and says why, which is
   *  the honest answer now that a shelf is a thing that can fail to exist. */
  async addShelf(name) {
    try {
      await makeFolder(this.rootName(), name);
    } catch (error) {
      this.warn(error.message);
      this.renderShelves();
      return;
    }
    await this.load({ force: true });
    this.setShelf(name);
  }

  /** Throw away the shelf being browsed, which the server allows only while it
   *  is empty. Back up to its parent afterwards — the place you were is gone. */
  async dropShelf(name) {
    try {
      await removeFolder(this.rootName(), name);
    } catch (error) {
      this.warn(error.message);
      return;
    }
    const parent = name.includes("/") ? name.slice(0, name.lastIndexOf("/")) : "all";
    await this.load({ force: true });
    this.setShelf(parent);
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
    // "All" leaves out the derived shelves — the `_plates` composites the
    // picker itself writes. A sheet is made *of* the grid's pictures, and a
    // folder of them mixed back in offers every old sheet as a panel for the
    // next one. They stay reachable on their own shelf.
    const onShelf = this.shelf === "all"
      ? (asset) => !(asset.subfolder || "").split("/")[0].startsWith("_")
      : this.shelf === "fav" ? (asset) => this.isFav(asset.path)
        : (asset) => this.under(asset.subfolder, this.shelf);
    // "renders" is a tab and not a kind, so it shows every kind the output
    // folder holds — a still and the clip it seeded are both renders. Unless
    // the caller is replacing one file with another, where anything but that
    // kind is a pick it would have to refuse.
    const only = this.options.only;
    const onKind = only ? (asset) => asset.kind === only
      : this.kind === "renders" ? () => true
      // The guide tab is a place, not a kind: every clip the bench has traced,
      // and nothing else in the input folder.
      : this.kind === "guides" ? isGuide
      : (asset) => asset.kind === this.kind;
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
    let count = this.selected.filter((asset) => this.targetKind(asset) === kind).length;
    // A connected group attaches as one file, so it claims one image slot —
    // except on a sheet family, where the slots *are* panels and every picture
    // costs one. Mirrors how the two grammars count: H3's `Grammar.refuse`
    // counts attachments, `LTX25Grammar.refuse` counts panels.
    const group = this.sheetFamily() ? 0 : this.sheetPanels().length;
    if (kind === "image" && group > 1) count -= group - 1;
    return count;
  }

  /** How many files the selection will attach as — the group is one of them. */
  claimedFiles() {
    const group = this.sheetFamily() ? 0 : this.sheetPanels().length;
    return this.selected.length - (group > 1 ? group - 1 : 0);
  }

  /**
   * Does what is selected fit in `kind`'s bucket, with `extra` more files on top?
   * `extra: 1` asks whether one more can be added; `0` re-checks a selection that
   * has just moved between buckets.
   */
  fits(kind, extra = 0) {
    if (this.options.single) return this.selected.length + extra <= 1;
    // No buckets to price against — see `openPicker`'s `capacity`.
    if (!this.options.capacity) return true;
    const { used, max, filesLeft } = this.options.capacity(kind);
    // filesLeft is the shared total and reads the same whichever bucket is
    // asked, so every selection counts against it, not just this bucket's.
    return used + this.claimed(kind) + extra <= max && this.claimedFiles() + extra <= filesLeft;
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
    // A cut cell shows the cutout itself, on the family's own backdrop — the
    // scissors' promise is a picture, and this is it. The original stands in
    // until the matte lands; `previewCut` swaps the cell when it does.
    const held = this.chipPossible(asset) && this.cutOf(asset)
      ? this.cutUrls.get(asset.path) : null;
    if (held?.url) {
      cell.classList.add("cutout");
      cell.style.background = greyField(this.plate.backdrop);
    }
    if (still) {
      // Filenames reach the DOM only as attributes/text, never as markup.
      const thumb = el("img", { src: held?.url ?? still, loading: "lazy", alt: asset.name });
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
    // Paired: this picture is a panel of the connected sheet, and the number is
    // where it sits — the same numbering the sheet editor and the card use.
    if (!this.organize && this.sheet.includes(asset.path)) {
      const number = this.sheetPanels().findIndex((a) => a.path === asset.path);
      if (number >= 0) {
        cell.appendChild(el("div", { class: "mmc-cell-sheet", text: `⧉ ${number + 1}` }));
      }
    }
    // The scissors, on the picture itself. One press cuts the whole subject
    // out and the cell shows the cutout; a second, smaller button — there only
    // once something is cut — opens the subject view for the picture the
    // whole-subject matte is wrong about. This is the door the sheet editor
    // used to be the only way through.
    if (this.chipPossible(asset)) {
      const on = this.cutOf(asset);
      cell.appendChild(el("button", {
        class: `mmc-cell-cut${on ? " on" : ""}${
          on && this.points.get(asset.path)?.length ? " pts" : ""}`,
        "aria-pressed": String(on),
        title: on
          ? t("{name} is cut out: the subject is lifted off its background onto the flat "
            + "field the panels sit on, so the room it was photographed in stops "
            + "conditioning the render alongside it. Click to keep the background.",
              { name: asset.name })
          : t("{name} is used whole, background and all. Click to lift the subject off it "
            + "— which is what you want when you are citing a person or an object and not "
            + "the place they were photographed in.", { name: asset.name }),
        onclick: (event) => { event.stopPropagation(); this.setCut(asset, !on); },
      }, [icon("scissors", 12)]));
      if (on) {
        cell.appendChild(el("button", {
          class: "mmc-cell-subject",
          title: t("Choose the subject — where the whole-subject cut grabs the wrong "
                 + "thing, click the one you mean"),
          onclick: (event) => { event.stopPropagation(); this.chooseSubject(asset); },
        }, [icon("subject", 12)]));
      }
      if (held?.pending) cell.appendChild(el("div", { class: "mmc-plate-scan" }));
    }
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
      // Passed straight through from whoever opened the picker: a file is
      // trimmed here before it is attached, and the card it is about to be
      // attached to is the one it will be read against.
      cardSeconds: this.options.cardSeconds,
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

  // ---- the sheet ------------------------------------------------------------
  //
  // What used to happen invisibly at render time — the subject lifted off its
  // background, the pictures laid out as one composite — happens in the open.
  // The scissors live on the grid cells themselves; the modal here is for
  // *combining* pictures, opened by Combine… (or, on a sheet family, on the
  // way out through Add). It shows the picture the model will actually be
  // handed and rebuilds it as you work. `creator/plate.py` does the making.

  /** Whether this family's image references *are* the panels of one composite
   *  sheet (LTX 2.5). There the whole image selection is the sheet and the
   *  compiler refuses loose seconds; elsewhere (H3) a sheet is something
   *  Connect builds out of part of the selection, and it rides as one
   *  reference among the others. */
  sheetFamily() {
    return Boolean(this.plate?.sheet);
  }

  /** Whether a sheet can be made in this session at all. Not while organizing,
   *  not for a single-pick caller (a keyframe is one frame of the video, not a
   *  sheet of references), and only on the tabs pictures live on. */
  sheetsPossible() {
    if (!this.plate || this.organize || this.options.single || this.options.viewOnly) return false;
    return this.kind === "image" || this.kind === "renders";
  }

  /** The images selected, in click order. Renders count: a character you
   *  generated last night is a better reference than a photograph of somebody
   *  else. */
  selectedImages() {
    return this.selected.filter((asset) => asset.kind === "image");
  }

  /** The panels of the sheet, as asset rows in layout order. On a sheet family
   *  that is every selected image; elsewhere it is the connected group —
   *  `this.sheet`'s order, minus anything since deselected. */
  sheetPanels() {
    const images = this.selectedImages();
    if (this.sheetFamily()) return images;
    const byPath = new Map(images.map((asset) => [asset.path, asset]));
    return this.sheet.map((path) => byPath.get(path)).filter(Boolean);
  }

  /** Whether this picture is cut out. The family's default until somebody says
   *  otherwise about this particular file. */
  cutOf(asset) {
    return this.cuts.has(asset.path) ? this.cuts.get(asset.path) : Boolean(this.plate?.cut);
  }

  /** Whether a cell wears the scissors chip: a picture, on a caller that can
   *  build a plate, in a session that is picking rather than organizing or
   *  browsing. A keyframe caller (`single`) does not — a start frame is a
   *  frame of the video, and cutting it out would condition on a hole. */
  chipPossible(asset) {
    return Boolean(this.plate) && asset.kind === "image"
      && !this.organize && !this.options.viewOnly && !this.options.single;
  }

  /** The chip's press: cut this picture, or stop. Cutting a picture is wanting
   *  it — an unselected cell selects on the way, and a press that finds no
   *  slot left goes nowhere, with the counter already saying why. */
  setCut(asset, on) {
    if (!this.selected.some((a) => a.path === asset.path)) {
      this.toggle(asset);
      if (!this.selected.some((a) => a.path === asset.path)) return;
    }
    this.cuts.set(asset.path, on);
    this.previewCut(asset);
    this.renderFoot();
  }

  /** The subject view, from a cell: the clicks that say which subject this
   *  picture's scissors mean. Accepting cuts the picture with them; cancel
   *  changes nothing, clicks included. */
  async chooseSubject(asset) {
    const got = await openSubjectView({
      plate: this.plate, path: asset.path, name: asset.name,
      points: this.points.get(asset.path) ?? [],
    });
    if (!got) return;
    if (got.points.length) this.points.set(asset.path, got.points);
    else this.points.delete(asset.path);
    this.cuts.set(asset.path, true);
    this.previewCut(asset);
  }

  /** Fetch the cutout a cut cell shows, from the same in-memory route the
   *  sheet stage reads. One matte per press, no debounce — the runs of clicks
   *  that need one happen in the subject view, which has its own. */
  previewCut(asset) {
    if (!this.cutOf(asset)) { this.refreshCell(asset); return; }
    const key = JSON.stringify([asset.path, this.points.get(asset.path) ?? []]);
    const have = this.cutUrls.get(asset.path) ?? {};
    if (have.key === key || have.pending === key) { this.refreshCell(asset); return; }
    this.cutUrls.set(asset.path, { ...have, pending: key });
    this.refreshCell(asset);
    cutPanel({ model: this.plate.model, segment: this.plate.segment,
               panels: [this.panelPayload(asset)] })
      .then((url) => {
        const now = this.cutUrls.get(asset.path);
        if (!now || now.pending !== key) { URL.revokeObjectURL(url); return; }
        if (now.url) URL.revokeObjectURL(now.url);
        this.cutUrls.set(asset.path, { key, url });
        this.refreshCell(asset);
      })
      .catch((error) => {
        const now = this.cutUrls.get(asset.path);
        if (!now || now.pending !== key) return;
        this.cutUrls.set(asset.path, { key: now.key, url: now.url });
        this.warn(error.message);
        this.refreshCell(asset);
      });
  }

  /** Whether `panels` add up to a file that has to be built at all.
   *
   *  One picture, used whole, *is* the reference — there is no layout to make
   *  and no matte to take, so attaching it is attaching it, and writing a
   *  byte-identical copy into `_plates/` would be a second file to keep track
   *  of for nothing. Everything else is a plate: two pictures need laying out,
   *  and one that is cut needs making. */
  sheetNeeded(panels = this.sheetPanels()) {
    return panels.length > 1
      || (panels.length === 1
          && (this.cutOf(panels[0]) || this.rects.has(panels[0].path)));
  }

  /** One panel as the plate routes read it: path, scissors, and — only where
   *  they exist — the arrangement and the clicks. The rect is rounded to the
   *  1e-4 the server hashes at, so a re-accepted sheet finds its own file. */
  panelPayload(asset) {
    const points = this.points.get(asset.path) ?? [];
    const rect = this.rects.get(asset.path);
    return {
      path: asset.path,
      cut: this.cutOf(asset),
      ...(rect ? { rect: rect.map((v) => Math.round(v * 1e4) / 1e4) } : {}),
      ...(this.cutOf(asset) && points.length ? { points } : {}),
    };
  }

  /** Redraw the pairing badges on the cells named — after the group changes,
   *  the numbers behind it change too. Cells not materialised have nothing to
   *  show and `refreshCell` skips them. */
  refreshSheetCells(paths) {
    for (const path of paths) {
      const asset = this.selected.find((a) => a.path === path)
        ?? this.activeAssets().find((a) => a.path === path);
      if (asset) this.refreshCell(asset);
    }
  }

  /** The answer a built sheet closes with: the composite the card attaches,
   *  and the pictures it was laid out from. `Editor.attachAssets` turns it
   *  into the one entry. */
  sheetAnswer(built, panels) {
    return {
      plate: true,
      kind: "image",
      path: built.path,
      name: built.path.split("/").pop(),
      panels: panels.map((asset) => this.panelPayload(asset)),
    };
  }

  /**
   * The sheet editor: a stage the shape of the shot's canvas, with the panels
   * on it where they will actually sit. Drag a panel to place it, take its
   * corner to resize it, reorder the citations in the strip below, scissors
   * per panel. Choosing *which* subject a panel's scissors mean is the subject
   * view's job — opened from the toolbar for the picked panel — so a click on
   * the stage only ever means layout.
   *
   * The preview is composited here in the browser, from per-panel cutouts the
   * server serves out of memory. Nothing touches the input folder until the
   * sheet is confirmed — Accept on a sheet family, Add on the others — and
   * Cancel forgets everything done here, files included, because there are
   * none.
   *
   * On a sheet family OK *commits*: the sheet is the card's one image
   * reference, so confirming what it looks like is the end of the pick.
   * Elsewhere OK saves the group back into the session — the panels stay
   * selected and paired, and Add is still to come, with whatever loose
   * references ride alongside.
   */
  openSheet() {
    // The group being edited: the sheet as it stands, plus any images selected
    // since — which is how pictures are added to an existing sheet.
    const inSheet = new Set(this.sheet);
    let order = this.sheetFamily()
      ? [...this.selectedImages()]
      : [...this.sheetPanels(),
         ...this.selectedImages().filter((a) => !inSheet.has(a.path))];
    // This session's scissors, layout and clicks, committed only by OK — so
    // Cancel really cancels, and cancels everything.
    const cuts = new Map(this.cuts);
    const rects = new Map([...this.rects].map(([path, r]) => [path, [...r]]));
    const points = new Map([...this.points]
      .map(([path, list]) => [path, list.map((point) => ({ ...point }))]));
    const cut = (asset) =>
      cuts.has(asset.path) ? cuts.get(asset.path) : Boolean(this.plate?.cut);
    const needed = () => order.length > 1
      || (order.length === 1 && (cut(order[0]) || rects.has(order[0].path)));

    const W = this.plate.width || 1280, H = this.plate.height || 704;
    let picked = order[0]?.path ?? null;   // the panel the toolbar acts on
    let saving = false, buildError = "";
    let drag = null;                       // strip reorder source index
    let fetchTimer = null;
    // path -> {key, url, pending}: the cut-out panels as object URLs from the
    // server's memory, revoked when the cutout changes and on the way out.
    const urls = new Map();

    const round4 = (v) => Math.round(v * 1e4) / 1e4;
    const clampTo = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

    // The grid cell a panel without a rect sits in — `plate.grid`'s walk in
    // fractions, so the stage agrees with the bake to the pixel.
    const gridRect = (index, count) => {
      const cols = Math.ceil(Math.sqrt(Math.max(1, count)));
      const rows = Math.ceil(count / cols);
      return [(index % cols) / cols, Math.floor(index / cols) / rows,
              1 / cols, 1 / rows];
    };
    const rectOf = (asset) =>
      rects.get(asset.path) ?? gridRect(order.indexOf(asset), order.length);

    const payload = (asset) => ({
      path: asset.path,
      cut: cut(asset),
      ...(rects.has(asset.path)
        ? { rect: rects.get(asset.path).map(round4) } : {}),
      ...(cut(asset) && points.get(asset.path)?.length
        ? { points: points.get(asset.path) } : {}),
    });

    // ---- the cutouts, fetched as they are asked for ------------------------
    const wantKey = (asset) => JSON.stringify(
      [asset.path, points.get(asset.path) ?? []]);
    const srcOf = (asset) => (cut(asset) && urls.get(asset.path)?.url)
      || viewUrl(asset.path, { preview: true });
    const fetchCuts = () => {
      for (const asset of order) {
        if (!cut(asset)) continue;
        const key = wantKey(asset);
        const have = urls.get(asset.path) ?? {};
        if (have.key === key || have.pending === key) continue;
        urls.set(asset.path, { ...have, pending: key });
        cutPanel({ model: this.plate.model, segment: this.plate.segment,
                   panels: [payload(asset)] })
          .then((url) => {
            const now = urls.get(asset.path);
            if (!now || now.pending !== key) { URL.revokeObjectURL(url); return; }
            if (now.url) URL.revokeObjectURL(now.url);
            urls.set(asset.path, { key, url });
            buildError = "";
            render();
          })
          .catch((error) => {
            const now = urls.get(asset.path);
            if (!now || now.pending !== key) return;
            urls.set(asset.path, { key: now.key, url: now.url });
            buildError = error.message;
            render();
          });
      }
    };
    // Fetch after the change settles: a run of clicks is many mattes, and only
    // where it ends is a picture anybody is waiting on.
    const schedule = () => {
      clearTimeout(fetchTimer);
      fetchTimer = setTimeout(fetchCuts, 250);
      render();
    };

    // ---- the stage ---------------------------------------------------------
    const stage = el("div", { class: "mmc-plate-stage" });
    stage.style.aspectRatio = W + " / " + H;
    stage.style.maxWidth = "min(100%, calc(48vh * " + (W / H) + "))";
    stage.style.background = greyField(this.plate.backdrop);

    // Select without redrawing: a redraw under a live pointer capture would
    // end the drag it belongs to. The full render comes when the gesture does.
    const pick = (asset, box) => {
      if (picked === asset.path) return;
      picked = asset.path;
      for (const other of stage.querySelectorAll(".mmc-st-panel.picked")) {
        other.classList.remove("picked");
      }
      box?.classList.add("picked");
      renderTools();
    };

    const startMove = (event, box, asset, grip) => {
      const stageRect = stage.getBoundingClientRect();
      const from = rectOf(asset);
      const sx = event.clientX, sy = event.clientY;
      const target = grip || box;
      target.setPointerCapture(event.pointerId);
      const onMove = (ev) => {
        const dx = (ev.clientX - sx) / Math.max(1, stageRect.width);
        const dy = (ev.clientY - sy) / Math.max(1, stageRect.height);
        let r;
        if (grip) {
          // Resize from the corner; the picture inside keeps its own aspect.
          r = [from[0], from[1],
               clampTo(from[2] + dx, 0.04, 2), clampTo(from[3] + dy, 0.04, 2)];
        } else {
          // Move. A sliver has to stay on the canvas, or there is nothing left
          // to take hold of and bring back.
          r = [clampTo(from[0] + dx, 0.03 - from[2], 0.97),
               clampTo(from[1] + dy, 0.03 - from[3], 0.97), from[2], from[3]];
        }
        rects.set(asset.path, r);
        box.style.left = (r[0] * 100) + "%";
        box.style.top = (r[1] * 100) + "%";
        box.style.width = (r[2] * 100) + "%";
        box.style.height = (r[3] * 100) + "%";
      };
      const done = () => {
        target.removeEventListener("pointermove", onMove);
        render();
      };
      target.addEventListener("pointermove", onMove);
      target.addEventListener("pointerup", done, { once: true });
      target.addEventListener("pointercancel", done, { once: true });
    };

    const panelEl = (asset, index) => {
      const r = rectOf(asset);
      const box = el("div", {
        class: "mmc-st-panel" + (asset.path === picked ? " picked" : ""),
        title: t("{name} — drag to place, corner to resize", { name: asset.name }),
      });
      box.style.left = (r[0] * 100) + "%";
      box.style.top = (r[1] * 100) + "%";
      box.style.width = (r[2] * 100) + "%";
      box.style.height = (r[3] * 100) + "%";
      box.style.zIndex = String(index + 1);
      box.appendChild(el("img", { class: "mmc-st-img", src: srcOf(asset),
                                  alt: asset.name, draggable: "false" }));
      box.appendChild(el("span", { class: "mmc-st-no", text: String(index + 1) }));
      const grip = el("div", { class: "mmc-st-grip", title: t("Resize") });
      grip.addEventListener("pointerdown", (event) => {
        event.stopPropagation();
        event.preventDefault();
        pick(asset, box);
        startMove(event, box, asset, grip);
      });
      box.appendChild(grip);
      if (cut(asset) && urls.get(asset.path)?.pending) {
        box.appendChild(el("div", { class: "mmc-plate-scan" }));
      }
      box.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        pick(asset, box);
        startMove(event, box, asset, null);
      });
      return box;
    };

    // ---- the toolbar -------------------------------------------------------
    //
    // The picked panel's own tools, then the stage's. The stage is only ever
    // about layout now: choosing which subject a panel's scissors mean is the
    // subject view's job, one picture at a time, where a click cannot also
    // mean a drag — the armed click mode this row used to carry is what made
    // the old editor confusing.
    const pickedAsset = () => order.find((asset) => asset.path === picked) ?? null;
    const which = el("span", { class: "mmc-plate-which" });
    const cutButton = el("button", {
      class: "mmc-ghost mmc-tool",
      "aria-pressed": "false",
      title: t("Lift this panel's subject off its background — or put the background back"),
      text: t("Cut out"),
      onclick: () => {
        const asset = pickedAsset();
        if (!asset) return;
        cuts.set(asset.path, !cut(asset));
        schedule();
      },
    });
    const subjectButton = el("button", {
      class: "mmc-ghost mmc-tool",
      title: t("Choose the subject — where the whole-subject cut grabs the wrong "
             + "thing, click the one you mean"),
      text: t("Choose the subject…"),
      onclick: async () => {
        const asset = pickedAsset();
        if (!asset) return;
        const got = await openSubjectView({
          plate: this.plate, path: asset.path, name: asset.name,
          points: points.get(asset.path) ?? [],
        });
        if (!got) return;
        if (got.points.length) points.set(asset.path, got.points);
        else points.delete(asset.path);
        cuts.set(asset.path, true);
        schedule();
      },
    });
    const autoButton = el("button", {
      class: "mmc-ghost mmc-tool",
      title: t("Put every panel back in its grid cell"),
      text: t("Auto-arrange"),
      onclick: () => { rects.clear(); schedule(); },
    });
    const tools = el("div", { class: "mmc-plate-tools" },
                     [which, cutButton, subjectButton, autoButton]);

    const caliper = el("div", { class: "mmc-plate-caliper" });
    const say = el("div", { class: "mmc-plate-say" });
    const strip = el("div", { class: "mmc-plate-strip" });
    const okButton = el("button", { class: "mmc-add", onclick: () => finish() });

    const cell = (asset, index) => {
      const on = cut(asset);
      const scissors = el("button", {
        class: `mmc-pl-cut${on ? " on" : ""}`,
        "aria-pressed": String(on),
        title: on
          ? t("{name} is cut out: the subject is lifted off its background onto the flat "
            + "field the panels sit on, so the room it was photographed in stops "
            + "conditioning the render alongside it. Click to keep the background.",
              { name: asset.name })
          : t("{name} is used whole, background and all. Click to lift the subject off it "
            + "— which is what you want when you are citing a person or an object and not "
            + "the place they were photographed in.", { name: asset.name }),
        onclick: (event) => {
          event.stopPropagation();
          cuts.set(asset.path, !on);
          schedule();
        },
      }, [icon("scissors", 12)]);

      const box = el("div", {
        class: `mmc-pl-cell${on ? " cut" : ""}${asset.path === picked ? " picked" : ""}`,
        title: t("{name} — drag to rearrange, click to select", { name: asset.name }),
        onclick: () => { picked = asset.path; render(); },
      }, [
        el("img", { class: "mmc-pl-thumb", src: viewUrl(asset.path, { preview: true }), alt: asset.name }),
        el("span", { class: "mmc-pl-no", text: String(index + 1) }),
        scissors,
        el("button", {
          class: "mmc-pl-x", text: "✕",
          title: t("Take {name} off the sheet", { name: asset.name }),
          onclick: (event) => {
            event.stopPropagation();
            order = order.filter((a) => a.path !== asset.path);
            // On a sheet family every selected image is a panel, so off the
            // sheet is out of the selection; elsewhere the picture goes back
            // to being an ordinary loose pick.
            if (this.sheetFamily()) {
              this.selected = this.selected.filter((a) => a.path !== asset.path);
              this.syncSelected();
              this.renderFoot();
            }
            if (!order.length) { shut(); return; }
            schedule();
          },
        }),
      ]);
      // Drag to rearrange. The panel numbering is the citation — `panel 3` in
      // the caption is cell 3 of this strip — so the order is worth a gesture.
      box.draggable = true;
      box.addEventListener("dragstart", (event) => {
        drag = index;
        event.dataTransfer.effectAllowed = "move";
        // An inert payload: Firefox refuses to start a drag with none, and a
        // real one (a URL) is what ComfyUI's drop handler would try to import
        // if the drop ever escaped the modal.
        event.dataTransfer.setData("text/plain", "");
      });
      box.addEventListener("dragover", (event) => {
        event.preventDefault();
        if (drag === null || drag === index) return;
        const [moved] = order.splice(drag, 1);
        order.splice(index, 0, moved);
        drag = index;
        schedule();
      });
      box.addEventListener("dragend", () => { drag = null; });
      return box;
    };

    const render = () => {
      stage.replaceChildren(...order.map(panelEl));

      // The caliper: what the sheet is, in numbers — panels, the canvas it
      // will bake at (the canvas the shot generates at), what has been cut.
      const parts = order.length > 1 ? [t("{count} panels", { count: order.length })] : [];
      parts.push(`${W} × ${H}`);
      const cutCount = order.filter(cut).length;
      if (cutCount) parts.push(t("{count} cut out", { count: cutCount }));
      if (rects.size) parts.push(t("arranged by hand"));
      caliper.textContent = parts.join("  ·  ");

      say.textContent = buildError;
      say.classList.toggle("bad", Boolean(buildError));
      say.style.display = say.textContent ? "" : "none";

      renderTools();
      strip.replaceChildren(...order.map(cell));
      okButton.textContent = saving ? t("Laying it out…")
        : this.sheetFamily()
          ? (order.length > 1 ? t("Add sheet") : t("Add"))
          : t("Use this sheet");
      okButton.disabled = !order.length || saving;
    };
    const renderTools = () => {
      const asset = pickedAsset();
      const on = Boolean(asset && cut(asset));
      which.textContent = asset ? t("Panel {n}", { n: order.indexOf(asset) + 1 }) : "";
      cutButton.disabled = !asset;
      // A text button says what pressing it does, so the state lives in the
      // label rather than in chrome the ghost style does not have.
      cutButton.textContent = on ? t("Keep the background") : t("Cut out");
      cutButton.setAttribute("aria-pressed", String(on));
      subjectButton.disabled = !asset;
      autoButton.disabled = !rects.size;
    };

    const finish = async () => {
      if (saving) return;
      this.cuts = cuts;
      this.rects = rects;
      this.points = points;
      if (!needed()) {
        if (this.sheetFamily()) {
          shut();
          // A lone uncut picture *is* the reference: attached as itself.
          this.close([{ ...order[0], ...(this.settings.get(order[0].path) || {}) }]);
          return;
        }
        // A group of one uncut picture is not a sheet — it dissolves back into
        // a loose pick, which is also how a sheet is dismantled on purpose.
        const before = this.sheet;
        this.sheet = [];
        shut();
        this.refreshSheetCells([...new Set(before)]);
        this.renderFoot();
        return;
      }
      if (this.sheetFamily()) {
        // Accept is the approval, so this is the one moment a file is made.
        saving = true;
        buildError = "";
        render();
        try {
          const built = await buildPlate({ ...this.plate,
            panels: order.map((asset) => this.panelPayload(asset)) });
          shut();
          this.close([this.sheetAnswer(built, order)]);
        } catch (error) {
          saving = false;
          buildError = error.message;
          render();
        }
        return;
      }
      // Elsewhere the group holds in the session and Add writes the file.
      const before = this.sheet;
      this.sheet = order.map((a) => a.path);
      shut();
      this.refreshSheetCells([...new Set([...before, ...this.sheet])]);
      this.renderFoot();
    };

    const sheetEl = el("div", { class: "mmc-plate-edit" }, [
      el("div", { class: "mmc-plate-title", text: t("Combine into one sheet") }),
      el("div", { class: "mmc-plate-stage-wrap" }, [stage]),
      say,
      tools,
      caliper,
      strip,
      el("div", { class: "mmc-plate-foot" }, [
        el("button", { class: "mmc-ghost", text: t("Cancel"), onclick: () => shut() }),
        okButton,
      ]),
    ]);
    const overlay = el("div", {
      class: "mmc-overlay",
      onpointerdown: (event) => { if (event.target === overlay) shut(); },
      // Same seal as the picker's own overlay: a panel dropped outside the
      // strip must not fall through to ComfyUI's file-import drop handler.
      ondragover: (event) => event.preventDefault(),
      ondrop: (event) => { event.preventDefault(); event.stopPropagation(); },
    }, [sheetEl]);
    const remove = mountOverlay(overlay, () => shut());
    const shut = () => {
      clearTimeout(fetchTimer);
      for (const held of urls.values()) {
        if (held.url) URL.revokeObjectURL(held.url);
      }
      urls.clear();
      remove();
    };
    schedule();
  }

  toggle(asset) {
    if (this.options.viewOnly) return;
    const at = this.selected.findIndex((a) => a.path === asset.path);
    if (at >= 0) this.selected.splice(at, 1);
    else if (this.options.single) this.selected = [asset];
    else if (this.room(this.targetKind(asset))) this.selected.push(asset);
    else return;  // at capacity: the counter already says why
    // Deselecting a paired picture takes it off the sheet too — the sheet is
    // made of selected pictures — and the badges behind it renumber.
    if (at >= 0 && this.sheet.includes(asset.path)) {
      this.sheet = this.sheet.filter((path) => path !== asset.path);
      this.refreshSheetCells([asset.path, ...this.sheet]);
    }
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
      // Mark everything in sight — what makes clearing a shelf of hundreds of
      // stale files (a `_plates` folder full of old sheets, say) one press
      // instead of hundreds.
      const inView = this.visible();
      const allMarked = inView.length
        && inView.every((asset) => this.marked.includes(asset.path));
      this.foot.replaceChildren(
        this.slots,
        el("button", {
          class: "mmc-ghost", disabled: !inView.length,
          text: allMarked ? t("Unmark all") : t("Mark all"),
          onclick: () => {
            this.marked = allMarked ? []
              : [...new Set([...this.marked, ...inView.map((asset) => asset.path)])];
            this.renderGrid();
            this.renderFoot();
          },
        }),
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
    const panels = this.sheetFamily() ? [] : this.sheetPanels();
    // Named after what pressing it produces. On a sheet family the whole image
    // selection is one sheet — that is the family's grammar, not a choice — so
    // the button says so, and pressing it goes through the sheet editor where
    // the composite is looked at before it lands.
    this.addButton = el("button", {
      class: "mmc-add",
      text: this.sheetFamily() && this.selectedImages().length > 1 ? t("Add sheet") : t("Add"),
      onclick: () => this.commit(),
    });
    const row = [
      this.slots,
      el("button", { class: "mmc-ghost", text: t("Cancel"), onclick: () => this.close(null) }),
      this.addButton,
    ];
    // Combine: lay the selected pictures out as one sheet, which then attaches
    // as a single reference and stays paired until it is taken off the piece.
    // Only where that is a choice — a sheet family has no button because its
    // selection is the sheet already. Cutting is not why anybody comes here
    // any more: the scissors live on the cells.
    if (this.sheetsPossible() && !this.sheetFamily()) {
      const joinable = new Set([...panels.map((a) => a.path),
                               ...this.selectedImages().map((a) => a.path)]).size;
      row.splice(2, 0, el("button", {
        class: "mmc-ghost mmc-connect",
        text: panels.length ? t("Edit sheet…") : t("Combine…"),
        title: t("Lay the selected pictures out as one sheet — arrange them on the shot's "
               + "canvas and attach the result as a single reference."),
        disabled: !(panels.length || joinable >= 2),
        onclick: () => this.openSheet(),
      }));
    }
    this.foot.replaceChildren(...row);
    if (this.options.single) {
      this.slots.textContent = this.selected.length ? t("1 selected") : t("Pick one");
      this.slots.classList.remove("full");
    } else if (!this.options.capacity) {
      // Nothing to fill, so nothing is reported as filling it: a caller with no
      // buckets gets a count. "0 / ∞ slots filled" would be a control pretending
      // to be a limit.
      this.slots.textContent = this.selected.length
        ? t("{count} selected", { count: this.selected.length })
        : t("Pick as many as you like");
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
    // The group is one of the slots, and the counter says which.
    if (panels.length > 1) {
      this.slots.textContent += t(" · sheet of {count}", { count: panels.length });
    }
    this.addButton.disabled = this.selected.length === 0 || this.committing;
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

  async commit() {
    if (!this.selected.length || this.committing) return;
    // On a sheet family the image selection *is* the sheet, and a *layout* is
    // confirmed by being looked at: two or more pictures still leave through
    // the editor. A lone cut picture no longer does — its cell has been
    // showing the cutout since the scissors were pressed, so there is nothing
    // left for the editor to reveal.
    if (this.sheetFamily() && this.selectedImages().length > 1) {
      this.openSheet();
      return;
    }
    const panels = this.sheetFamily() ? [] : this.sheetPanels();
    const grouped = new Set(panels.map((asset) => asset.path));
    const loose = this.selected.filter((asset) => !grouped.has(asset.path));
    // A loose picture the scissors touched closes as a plate of one — the cut
    // baked exactly once, here, the way a sheet's is on Accept. The rest
    // attach as themselves.
    const cut = loose.filter((asset) => this.chipPossible(asset) && this.sheetNeeded([asset]));
    const plain = loose.filter((asset) => !cut.includes(asset))
      .map((asset) => ({ ...asset, ...(this.settings.get(asset.path) || {}) }));
    if (!cut.length && (!panels.length || !this.sheetNeeded(panels))) {
      this.close(plain);
      return;
    }
    // Each group closes as one thing, because it is one thing: the file the
    // server wrote, and the pictures it was laid out from — `Editor.attachAssets`
    // turns each into one reference. Usually the file exists already (the
    // sheet editor or the chip's preview built its panels), so these awaits
    // are mostly stats; they are awaited anyway because the selection may have
    // changed since — a panel deselected from the grid.
    this.committing = true;
    this.renderFoot();
    try {
      const answers = [];
      if (panels.length && this.sheetNeeded(panels)) {
        const built = await buildPlate({ ...this.plate,
          panels: panels.map((asset) => this.panelPayload(asset)) });
        answers.push(this.sheetAnswer(built, panels));
      }
      for (const asset of cut) {
        const built = await buildPlate({ ...this.plate,
          panels: [this.panelPayload(asset)] });
        answers.push(this.sheetAnswer(built, [asset]));
      }
      this.close([...answers, ...plain]);
    } catch (error) {
      this.committing = false;
      this.renderFoot();
      this.warn(error.message);
    }
  }

  close(result) {
    clearTimeout(this.warnTimer);
    clearTimeout(this.armTimer);
    for (const held of this.cutUrls.values()) {
      if (held.url) URL.revokeObjectURL(held.url);
    }
    this.cutUrls.clear();
    this.observer?.disconnect();
    this.unmount();
    this.resolve(result);
  }
}

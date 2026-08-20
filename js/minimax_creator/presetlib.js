// The preset library: the window you save a setup into and get it back from.
//
// It is the picker's window with a different grid in it — scope tabs where the
// kind tabs are, shelves where the shelves are, search where the search is —
// because a user who has opened the asset picker once has already learned this
// one. What differs is the cell: a preset's content is structure rather than a
// picture, so a 140px square would waste the middle of every one, and the card is
// wide with a line of prose and a line of numbers under its hero.
//
// **The hero is the strip.** The node face already draws the piece as blocks at
// their real relative lengths, merged shots closed up under one casing; that
// drawing *is* the shape of the piece and it is generated from data the preset
// already holds. Where the preset carries a cover — the render it was saved from
// — the cover takes the band and the lane is redrawn as a ruler across its foot,
// so the shape stays legible without competing with the picture.
//
// Nothing here stores an image. A cover is a filename in the output folder and a
// block's picture is a filename the preset had to hold anyway; both are served by
// routes that shipped long before presets did.
//
// **The Style tab is the one exception, and it is a catalogue rather than a
// shelf.** Its rows are the vendored H3 Style Atlas — shipped, read-only, stills
// included — so its cards draw pictures this pack has on disk and its bar has
// nothing to save. It is a fourth scope because that is exactly what it is: a
// style is a thing a preset can be *of*, applicable to all three nodes and
// capturable off none of them. The module that builds those rows is imported the
// first time the tab is opened, and never at boot.
//
// **The Cast tab is a roster.** Its rows are people rather than setups — one
// member each, their pictures named rather than handled, so casting them into a
// piece attaches the files as it goes. Nothing is captured off a node *here*:
// somebody is kept from the star on their own card on the cast shelf, which is
// where they are being looked at, and this tab is where they are found again. See
// `presets.captureSubject`.

import { el, icon, mountOverlay } from "./dom.js";
import { t } from "./i18n.js";
import { renderMeta, stillUrl, viewUrl } from "./api.js";
import { openPicker } from "./picker.js";
import { BUILTIN } from "./presets/builtin.js";
import * as P from "./presets.js";

const SHELF_ALL = "all";
const SHELF_FAV = "fav";

// Cards are materialised a batch at a time behind a sentinel — the picker's own
// deal for the same problem. The Style tab is 941 rows, and rebuilding all of
// them on every keystroke of the search is a tab that stutters.
const PAGE_SIZE = 60;

/**
 * Open the library.
 *
 * @param {object} options
 * @param {object} options.target  what a preset can be applied to:
 *   `{scope, label, capture(), apply(body, keys, fromScope), arch()}`. Null opens
 *   the library read-only, which is what the node context menu does when there is
 *   nothing sensible to apply to.
 * @param {string} [options.scope]  which tab to open on, where the caller knows
 *   better than the target does — the cast shelf's own way in wants the roster,
 *   not the piece the roster would be applied to.
 * @returns {Promise<void>}
 */
export function openPresetLibrary(options) {
  return new Promise((resolve) => new PresetLibrary(options, resolve).mount());
}

/** What stands in for a face on a member kept in words alone. Follows `takes`,
 *  the same four `cast.js` draws — a person glyph over a described loft says the
 *  wrong thing. */
const CAST_GLYPH = { person: "face", object: "weights", scene: "image", style: "effect" };

/** What each file lends them, as the caption under it. The shelf's own four
 *  answers, shortened — a caption is read beside the picture it belongs to, so
 *  it can say "voice" where a menu row has to say the whole sentence. These are
 *  `ROLES[].label` in `cast.js`, which is the row of words this pack already
 *  uses for the same four answers. */
const CAST_SLOT_LABEL = {
  from: "looks", motion: "moves", voice: "voice", replaces: "their place",
};

/** mm:ss, which is how a length is read off a strip. */
function clock(seconds) {
  const whole = Math.max(0, Math.round(seconds || 0));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

class PresetLibrary {
  constructor({ target = null, scope = null }, resolve) {
    this.target = target;
    this.resolve = resolve;
    // Opens on the scope the node can actually take, because that is what you
    // came for — unless the caller asked for a tab by name, which is what a
    // "From the library" button on a shelf is doing. The tabs are still there to
    // browse the rest.
    this.scope = scope ?? target?.scope ?? "piece";
    this.query = "";
    this.shelf = SHELF_ALL;
    this.rows = [];
    this.selected = null;      // the row the inspector is showing
    this.body = null;          // its sections, once fetched
    this.keys = new Set();     // which of them are ticked
    this.problem = null;
    this.busy = false;
    // The shipped catalogue, read on first sight of its tab. Kept apart from
    // `rows` rather than folded into it: nothing that writes a user's library
    // should ever have nine hundred read-only rows in its hands.
    this.styles = [];
    this.stylesLoading = false;
    this.atlas = null;
    // The grid, materialised in batches — see `appendCards`.
    this.gridRows = [];
    this.visibleCount = PAGE_SIZE;
    this.cards = new Map();
    this.observer = null;
    // Which preset's Delete is armed, if any — the picker's two-press confirm.
    this.armed = null;
  }

  mount() {
    this.grid = el("div", { class: "mmc-preset-grid" });
    this.inspector = el("aside", { class: "mmc-preset-insp" });
    this.problemLine = el("div", { class: "mmc-preset-problem", style: { display: "none" } });

    this.search = el("input", {
      class: "mmc-search",
      type: "search",
      placeholder: t("Search presets…"),
      oninput: (event) => { this.query = event.target.value.toLowerCase(); this.renderGrid(); },
      onkeydown: (event) => event.stopPropagation(),
    });

    this.tabs = P.SCOPES.map((scope) => el("button", {
      class: "mmc-tab",
      "aria-selected": scope === this.scope,
      text: t(P.SCOPE_LABEL[scope]),
      onclick: () => this.selectScope(scope),
    }));

    // The chips go in the picker's scrolling strip: a library filed into more
    // folders than fit scrolls sideways rather than growing rows downwards and
    // pushing the grid off the modal.
    this.shelfRow = el("div", { class: "mmc-shelf-strip" });
    this.bar = el("div", { class: "mmc-modal-bar" });
    this.renderBar();

    this.modal = el("div", { class: "mmc-modal" }, [
      el("div", { class: "mmc-modal-head" }, [
        ...this.tabs,
        el("button", { class: "mmc-close", text: "✕", title: t("Close"), onclick: () => this.close() }),
      ]),
      this.bar,
      el("div", { class: "mmc-shelves" }, [this.shelfRow]),
      this.problemLine,
      el("div", { class: "mmc-preset-split" }, [this.grid, this.inspector]),
    ]);
    this.modal.style.position = "relative";

    this.overlay = el("div", {
      class: "mmc-overlay",
      onpointerdown: (event) => { if (event.target === this.overlay) this.close(); },
    }, [this.modal]);

    this.unmount = mountOverlay(this.overlay, () => this.close());
    this.renderInspector();
    this.load();
  }

  /**
   * The bar under the tabs: the search, and the verbs that make a preset.
   *
   * Rebuilt per scope rather than built once, for the Style tab's sake — the
   * catalogue is shipped and read-only, so Save, Import and *From a render* have
   * nothing to act on there and are gone rather than dimmed. The search element
   * itself is carried across, so switching tabs does not drop what was typed in
   * it or the caret sitting in it.
   */
  renderBar() {
    const catalogue = this.scope === "style";
    const roster = this.scope === "cast";
    this.search.placeholder = catalogue
      ? t("Search styles…")
      : roster ? t("Search the cast…") : t("Search presets…");
    // Nothing on the Cast tab is captured off a node, so the two verbs that read
    // one are gone rather than dimmed: a member is kept from the ★ on their own
    // card, and a render holds a workflow rather than a person. Import stays —
    // a roster is exactly the thing you carry between machines.
    this.bar.replaceChildren(this.search, ...(catalogue ? [] : [
      el("button", {
        class: "mmc-organize",
        title: t("Read a .json of presets exported from another machine"),
        onclick: () => this.importFile(),
      }, [icon("folder", 14), el("span", { text: t("Import") })]),
      // Not conditional on a target, unlike the button beside it: this reads a
      // file rather than a node, so it works in the read-only library the
      // context menu opens — and on a machine whose renders came from somewhere
      // else entirely.
      ...(roster ? [] : [el("button", {
        class: "mmc-organize",
        title: t("Take a preset from the workflow embedded in a finished render"),
        onclick: () => this.saveFromRender(),
      }, [icon("gallery", 14), el("span", { text: t("From a render") })])]),
      // Absent rather than disabled where there is nothing to save: the library
      // opened from a context menu has no node behind it.
      ...(this.target && !roster ? [el("button", {
        class: "mmc-upload",
        text: t("+  Save current setup"),
        onclick: () => this.saveCurrent(),
      })] : []),
    ]));
  }

  async load() {
    try {
      const stored = await P.listPresets({ force: true });
      // Builtins last within their scope: a shipped starter is a suggestion and
      // your own work is the library.
      this.rows = [...stored, ...BUILTIN];
    } catch (error) {
      this.rows = [...BUILTIN];
      this.say(t("Could not read the library — {error}", { error: error.message }));
    }
    this.renderShelves();
    this.renderGrid();
  }

  close() {
    this.observer?.disconnect();
    this.observer = null;
    this.unmount();
    this.resolve();
  }

  say(problem) {
    this.problem = problem;
    this.problemLine.textContent = problem ?? "";
    this.problemLine.style.display = problem ? "" : "none";
  }

  selectScope(scope) {
    if (scope === this.scope) return;
    this.scope = scope;
    this.selected = null;
    this.body = null;
    // A shelf is a place, not a scope — but "starred" and a hand-made folder
    // both survive the move, so only the selection is dropped.
    for (const [index, tab] of P.SCOPES.entries()) {
      this.tabs[index].setAttribute("aria-selected", String(tab === scope));
    }
    this.renderBar();
    this.renderShelves();
    this.renderGrid();
    this.renderInspector();
    if (scope === "style") this.readAtlas();
  }

  /**
   * Read the shipped style catalogue, once.
   *
   * A dynamic import rather than one at the top of the file: the atlas is a
   * sixth of a megabyte of descriptors, and a user who never opens this tab
   * should never pay for it. It arrives with its own vocabulary registered —
   * see `setStyleVocabulary` — which is what lets applying a second style swap
   * the first one out instead of stacking on it.
   */
  async readAtlas() {
    if (this.styles.length || this.stylesLoading) return;
    this.stylesLoading = true;
    this.renderGrid();
    try {
      const module = await import("./presets/stylelib.js");
      this.styles = module.styleRows();
      this.atlas = module.ATLAS;
    } catch (error) {
      this.say(t("Could not read the style atlas — {error}", { error: error.message }));
    }
    this.stylesLoading = false;
    if (this.scope !== "style") return;
    this.renderShelves();
    this.renderGrid();
  }

  // ---- shelves --------------------------------------------------------------

  /** The rows this tab is showing at all — a user's library, or the catalogue. */
  pool() {
    return this.scope === "style" ? this.styles : this.rows;
  }

  folders() {
    return [...new Set(this.pool().filter((row) => row.scope === this.scope && row.folder)
      .map((row) => row.folder))].sort();
  }

  renderShelves() {
    const shelves = [
      [SHELF_ALL, t("All")],
      // Nothing in the catalogue can be starred — a shipped row is the same for
      // everybody and has nowhere to keep one — so the shelf that would always
      // be empty is not offered. The atlas's eight media groups take its place,
      // and they arrive as folders, which is what a shelf already is.
      ...(this.scope === "style" ? [] : [[SHELF_FAV, t("★ Starred")]]),
      ...this.folders().map((folder) => [folder, folder]),
    ];
    if (!shelves.some(([key]) => key === this.shelf)) this.shelf = SHELF_ALL;
    this.shelfRow.replaceChildren(...shelves.map(([key, label]) => el("button", {
      class: "mmc-shelf",
      "aria-pressed": key === this.shelf,
      text: label,
      onclick: () => { this.shelf = key; this.renderGrid(); },
    })));
  }

  visible() {
    return this.pool().filter((row) => {
      if (row.scope !== this.scope) return false;
      if (this.shelf === SHELF_FAV && !row.starred) return false;
      if (this.shelf !== SHELF_ALL && this.shelf !== SHELF_FAV && row.folder !== this.shelf) return false;
      if (!this.query) return true;
      return `${row.name} ${row.note ?? ""} ${row.folder ?? ""}`.toLowerCase().includes(this.query);
    });
  }

  // ---- the grid -------------------------------------------------------------

  renderGrid() {
    this.observer?.disconnect();
    this.observer = null;
    this.cards.clear();
    this.gridRows = this.visible();
    this.visibleCount = PAGE_SIZE;
    if (!this.gridRows.length) {
      this.grid.replaceChildren(el("div", { class: "mmc-preset-empty", text: this.emptyWords() }));
      return;
    }
    this.grid.replaceChildren();
    this.appendCards(0);
  }

  /** Materialise cards from `from` up to `visibleCount`; where rows remain, a
   *  sentinel watches the grid's own scrollport and appends the next batch as it
   *  comes into view. Cards already built are never touched, so their stills are
   *  never re-fetched — the picker's arrangement, for the picker's reason. */
  appendCards(from) {
    const to = Math.min(this.visibleCount, this.gridRows.length);
    for (const row of this.gridRows.slice(from, to)) {
      const holder = this.renderCard(row);
      this.cards.set(row.id, holder.firstElementChild);
      this.grid.appendChild(holder);
    }
    if (to >= this.gridRows.length) return;
    const sentinel = el("div", { class: "mmc-grid-sentinel" });
    this.grid.appendChild(sentinel);
    this.observer = new IntersectionObserver((entries) => {
      if (!entries.some((entry) => entry.isIntersecting)) return;
      this.observer.disconnect();
      this.observer = null;
      sentinel.remove();
      this.visibleCount = to + PAGE_SIZE;
      this.appendCards(to);
    }, { root: this.grid, rootMargin: "300px" });
    this.observer.observe(sentinel);
  }

  /** Move the selection ring without rebuilding the grid. Selecting is the one
   *  thing that happens constantly, and a rebuild would throw away every card
   *  scrolled to past the first batch — on the Style tab, most of them. */
  markSelected() {
    for (const [id, card] of this.cards) {
      card.setAttribute("aria-selected", String(this.selected?.id === id));
    }
  }

  emptyWords() {
    if (this.scope === "style" && this.stylesLoading) return t("Reading the style atlas…");
    if (this.query) return t("Nothing here matches “{query}”.", { query: this.query });
    if (this.shelf === SHELF_FAV) return t("No starred presets yet. The star on a card puts it here.");
    if (this.scope === "style") return t("The style atlas could not be read.");
    if (this.scope === "cast") {
      return t("Nobody kept yet. Cast somebody on a node, then press the ★ on their "
             + "card to keep them here — they come back with their pictures.");
    }
    if (this.target?.scope === this.scope) {
      return t("No presets yet. Set this node up the way you want it, then Save current setup.");
    }
    return t("No presets of this kind yet.");
  }

  renderCard(row) {
    // The card and its star are siblings in a wrapper rather than the star being
    // inside the card: a button inside a button is invalid, and the inner one's
    // clicks are the browser's to route however it likes.
    const holder = el("div", { class: "mmc-preset-holder" });
    // A style card carries the descriptor where a preset card carries its
    // section chips: the descriptor *is* the content, and a row of chips saying
    // "style" under nine hundred cards on the Style tab would say nothing. The
    // opening clauses are the name and the rest of the sentence is set under it,
    // so the whole thing is readable and no half of it is printed twice.
    const style = row.scope === "style";
    // A member's card carries no chips either, and for the style card's reason:
    // "cast" under every row of a roster says nothing. Their name is a handle
    // rather than a title, so it is written the way it is written in a prompt —
    // with the @ on it, in the face the prompt box uses.
    const cast = row.scope === "cast";
    const card = el("button", {
      class: "mmc-preset-card",
      "aria-selected": this.selected?.id === row.id,
      "data-builtin": row.builtin && !style ? "" : null,
      "data-style": style ? "" : null,
      "data-cast": cast ? "" : null,
      onclick: () => this.select(row),
    }, [
      this.renderHero(row),
      el("p", { class: "mmc-preset-name", text: cast ? `@${row.name}` : row.name }),
      ...(style && row.rest ? [el("p", { class: "mmc-style-rest", text: row.rest })] : []),
      el("p", { class: "mmc-preset-facts", text: this.factsLine(row) }),
      ...(style || cast ? [] : [el("div", { class: "mmc-preset-chips" }, [
        ...(row.sections ?? []).map((key) => el("span", {
          class: `mmc-preset-chip mmc-tag-${P.SECTION[key]?.hue ?? 0}`,
          text: t(P.SECTION[key]?.label ?? key).toLowerCase(),
        })),
        ...(row.builtin ? [el("span", { class: "mmc-preset-chip plain", text: t("built-in") })] : []),
      ])]),
    ]);
    holder.append(card);
    // Not on a builtin: a shipped starter is the same for everybody and has
    // nowhere to keep a star.
    if (!row.builtin) {
      holder.append(el("button", {
        class: "mmc-preset-star",
        "aria-pressed": row.starred === true,
        title: row.starred ? t("Remove from Starred") : t("Add to Starred"),
        onclick: () => this.toggleStar(row),
      }, [icon("star", 14)]));
    }
    return holder;
  }

  /**
   * The hero, in its three states — see the stylesheet. Each is the fallback of
   * the one before it: a cover, else the pictured lane, else the bare shape.
   */
  renderHero(row) {
    // A style's picture is a file this pack ships, addressed directly — there is
    // no output folder behind it and no thumbnail route to resolve it through,
    // which is the one place the library's "nothing here stores an image" rule
    // does not hold. Where the descriptor was read off several clips, the first
    // fills the band and the others are counted in the corner; all of them are
    // in the inspector, which is where there is room to look at them.
    if (row.scope === "style") {
      const hero = el("div", { class: "mmc-preset-hero" });
      const [first, ...more] = row.thumbs ?? [];
      if (first) {
        hero.append(el("img", {
          class: "mmc-preset-cover",
          onerror: (event) => event.target.remove(),
          src: first, alt: "", loading: "lazy",
        }));
      }
      if (more.length) hero.append(el("em", { class: "mmc-style-more", text: `+${more.length}` }));
      return hero;
    }
    // A member's picture is one of their own references — an *input* file, not a
    // render — so it is addressed directly rather than through the still route.
    // A cover set by hand still wins: somebody who picked a frame of them walking
    // picked it because it is the better likeness.
    if (row.scope === "cast" && !row.cover) {
      const hero = el("div", { class: "mmc-preset-hero mmc-cast-hero" });
      if (row.portrait) {
        hero.append(el("img", {
          class: "mmc-preset-cover",
          onerror: (event) => { event.target.remove(); hero.append(this.renderCastGlyph(row)); },
          src: viewUrl(row.portrait, { preview: true }), alt: "", loading: "lazy",
        }));
      } else {
        hero.append(this.renderCastGlyph(row));
      }
      return hero;
    }
    const cover = stillUrl(row.cover);
    const hero = el("div", { class: "mmc-preset-hero", "data-cover": cover ? "" : null });
    if (cover) {
      hero.append(el("img", {
        class: "mmc-preset-cover",
        // A render since deleted is a 404, and the card falls back to the lane
        // underneath rather than showing a broken picture. The same honest
        // fallback a missing block has. Before `src`, because `el` sets props in
        // order and a listener attached after the request is a listener that can
        // miss it.
        onerror: (event) => {
          event.target.remove();
          hero.removeAttribute("data-cover");
        },
        src: cover, alt: "", loading: "lazy",
      }));
    }
    // A member with a cover is their cover and nothing else — there is no lane
    // behind a person to draw under it.
    if (row.scope === "cast") return hero;
    if (row.scope === "prestage") {
      if (!cover) hero.append(this.renderCanvasFigure(row));
      return hero;
    }
    if (row.scope === "shot") {
      if (!cover) hero.append(this.renderSolo(row));
      return hero;
    }
    hero.append(this.renderLane(row, { pictured: !cover }));
    return hero;
  }

  /** Their glyph, where no picture of them exists — a member kept in words alone,
   *  or one whose file has since been deleted off this machine. */
  renderCastGlyph(row) {
    return el("div", { class: "mmc-cast-hero-blank" },
              [icon(CAST_GLYPH[row.facts?.takes ?? "person"] ?? "face", 26)]);
  }

  renderLane(row, { pictured }) {
    const runs = row.lane?.runs ?? [];
    const frames = new Map((row.frames ?? []).map((frame) => [frame.at, frame]));
    return el("div", { class: "mmc-preset-lane" }, runs.map((run) => {
      const seconds = run.blocks.reduce((total, block) => total + block.seconds, 0);
      return el("div", {
        class: "mmc-preset-pass",
        // A pass is as wide as it is long, and a block inside it is as wide as
        // its share of the pass — the reading the node's own reel gives.
        style: { flex: String(seconds) },
      }, run.blocks.map((block) => {
        const cell = el("i", {
          class: "mmc-preset-blk",
          "data-clip": block.clip ? "" : null,
          style: { flex: String(block.seconds) },
        });
        const picture = pictured ? stillUrl(frames.get(block.at)) : null;
        if (picture) {
          cell.append(el("img", {
            src: picture, alt: "", loading: "lazy",
            onerror: (event) => event.target.remove(),
          }));
        }
        return cell;
      }));
    }));
  }

  renderSolo(row) {
    const seconds = row.facts?.seconds ?? 0;
    // Against a nominal twenty-second card, so a 12 s shot is visibly longer
    // than a 6 s one without a 90 s one running off the end.
    const share = Math.max(0.14, Math.min(1, seconds / 20));
    const block = el("i", {
      class: "mmc-preset-blk",
      "data-clip": row.facts?.clip ? "" : null,
      style: { width: `${Math.round(share * 100)}%` },
    });
    const picture = stillUrl((row.frames ?? [])[0]);
    if (picture) {
      block.append(el("img", { src: picture, alt: "", loading: "lazy",
                               onerror: (event) => event.target.remove() }));
    }
    return el("div", { class: "mmc-preset-solo" }, [
      block,
      el("em", { text: t("{n} s", { n: +seconds.toFixed(1) }) }),
    ]);
  }

  renderCanvasFigure(row) {
    const [w, h] = String(row.canvas?.aspect ?? row.facts?.aspect ?? "16:9").split(":").map(Number);
    const ratio = w && h ? w / h : 16 / 9;
    const frame = el("span", { style: { width: `${Math.round(84 * ratio)}px` } });
    const picture = stillUrl(row.canvas?.picture);
    if (picture) {
      frame.append(el("img", { src: picture, alt: "", loading: "lazy",
                               onerror: (event) => event.target.remove() }));
    }
    return el("div", { class: "mmc-preset-canvas" }, [frame]);
  }

  factsLine(row) {
    const facts = row.facts ?? {};
    // What they are, then what they were built out of. Shared with the `@` menu,
    // which offers the same people mid-sentence — see `presets.castFactsLine`.
    if (row.scope === "cast") return P.castFactsLine(facts);
    if (row.scope === "style") {
      const clips = facts.clips ?? 0;
      return [facts.category,
              t(clips === 1 ? "{count} clip" : "{count} clips", { count: clips })]
        .filter(Boolean).join(" · ");
    }
    if (row.scope === "prestage") {
      return [facts.arch, facts.aspect, facts.quality].filter(Boolean).join(" · ");
    }
    if (row.scope === "shot") {
      return [
        facts.clip ? t("clip") : t("shot"),
        t("{n} s", { n: +(facts.seconds ?? 0).toFixed(1) }),
        facts.feather ? t("feather {n}", { n: facts.feather }) : null,
        facts.checkpoint && facts.checkpoint !== "auto" ? facts.checkpoint : null,
      ].filter(Boolean).join(" · ");
    }
    const shots = facts.shots ?? 0;
    return [
      t(shots === 1 ? "{count} shot" : "{count} shots", { count: shots }),
      clock(facts.seconds),
      facts.passes && facts.passes !== shots
        ? t("{count} passes", { count: facts.passes }) : null,
      facts.route && facts.route !== "auto" ? facts.route : null,
      facts.aspect,
    ].filter(Boolean).join(" · ");
  }

  // ---- the inspector --------------------------------------------------------

  async select(row) {
    this.selected = row;
    this.body = null;
    // An armed Delete belongs to the preset it was armed on; moving away is
    // changing your mind about it.
    this.armed = null;
    this.say(null);
    this.markSelected();
    this.renderInspector();
    const body = await P.loadBody(row);
    // A second click while the first was in flight: only paint for the row that
    // is still selected.
    if (this.selected?.id !== row.id) return;
    this.body = body;
    // Everything applicable, ticked. "Everything" is the right default; being
    // able to take part of it is what stops the library going unused the moment
    // you have a prompt worth keeping.
    this.keys = new Set(Object.keys(body ?? {}).filter((key) => this.crossable(key, row).ok));
    this.renderInspector();
  }

  crossable(key, row) {
    if (!this.target) return { ok: false, why: t("Nothing to apply this to — open the library from a node.") };
    return P.crossable(key, row.scope, this.target.scope, {
      arch: row.facts?.arch ?? null,
      targetArch: this.target.arch?.() ?? null,
    });
  }

  renderInspector() {
    const row = this.selected;
    if (!row) {
      this.inspector.replaceChildren(el("div", { class: "mmc-preset-insp-hint", text:
        this.target
          ? t("Pick a preset to see what is in it and choose what to apply.")
          : t("Pick a preset to see what is in it.") }));
      return;
    }
    if (!this.body) {
      this.inspector.replaceChildren(
        el("div", { class: "mmc-preset-insp-title", text: row.name }),
        el("div", { class: "mmc-preset-insp-hint", text: t("Reading…") }));
      return;
    }
    if (row.scope === "style") { this.renderStyleInspector(row); return; }

    const applicable = [...this.keys].length;
    this.inspector.replaceChildren(
      // A builtin's name is not editable — it is the same for everybody, and
      // "Save as…" from one is how you get a copy that is yours.
      row.builtin
        ? el("div", { class: "mmc-preset-insp-title", text: row.name })
        : el("input", {
            class: "mmc-preset-insp-name",
            value: row.name,
            "aria-label": t("Preset name"),
            onkeydown: (event) => {
              event.stopPropagation();
              if (event.key === "Enter") event.target.blur();
            },
            onchange: (event) => this.rename(row, event.target.value),
          }),
      this.renderMeta(row),
      ...(row.scope === "cast" ? [this.renderCastBody(row)] : []),
      el("div", { class: "mmc-preset-rows" }, this.renderSectionRows(row)),
      ...(this.target ? [el("button", {
        class: "mmc-preset-apply",
        disabled: !applicable || this.busy,
        // A member is cast, not applied. The verb is the one the shelf uses for
        // the same act, and it says where they land — which is the question
        // somebody with two nodes open actually has.
        text: applicable
          ? (row.scope === "cast"
              ? t("Cast @{handle} into {label}",
                  { handle: this.body?.cast?.handle ?? row.name, label: this.target.label })
              : t("Apply to {label} ({count})", { label: this.target.label, count: applicable }))
          : t("Nothing here fits this node"),
        onclick: () => this.apply(row),
      })] : []),
      el("div", { class: "mmc-preset-insp-acts" }, [
        el("button", {
          class: "mmc-preset-danger",
          text: t("Export"),
          onclick: () => P.exportPresets([row], [this.body]),
        }),
        // Two presses, the picker's own deal for the same irreversible verb —
        // rather than a browser confirm() this page cannot style or place.
        ...(row.builtin ? [] : [el("button", {
          class: `mmc-preset-danger${this.armed === row.id ? " armed" : ""}`,
          text: this.armed === row.id ? t("Really delete?") : t("Delete"),
          onclick: () => {
            if (this.armed === row.id) { this.remove(row); return; }
            this.armed = row.id;
            this.renderInspector();
          },
        })]),
      ]),
    );
  }

  /**
   * A style, in the inspector.
   *
   * Its own renderer rather than a handful of branches through the preset one,
   * because almost none of that panel applies: there is no name to edit, no
   * cover to set, nothing to export and nothing to delete. What is left is the
   * descriptor — the whole of it, selectable, because it is the text that is
   * about to go into the prompt — every still the atlas read it off, and Apply.
   *
   * The stills are the panel's argument. A descriptor is a paragraph of English
   * and two of them can read almost identically; the frames are what tell
   * "grainy 16mm exploitation print" from "faded 35mm exploitation print" at a
   * glance, and here there is room for all of them rather than the one the card
   * had space for.
   */
  renderStyleInspector(row) {
    const clips = row.data?.style?.clips ?? [];
    const applicable = this.keys.size;
    this.inspector.replaceChildren(
      el("div", { class: "mmc-preset-insp-title", text: row.name }),
      ...(row.rest ? [el("p", { class: "mmc-style-full", text: row.rest })] : []),
      el("p", { class: "mmc-preset-insp-meta", text: this.factsLine(row) }),
      el("div", { class: "mmc-style-shots" }, (row.thumbs ?? []).map((url, index) =>
        el("figure", {}, [
          el("img", { onerror: (event) => event.target.remove(),
                      src: url, alt: "", loading: "lazy" }),
          el("figcaption", { text: clips[index] ?? "" }),
        ]))),
      el("div", { class: "mmc-preset-rows" }, this.renderSectionRows(row)),
      ...(this.target ? [el("button", {
        class: "mmc-preset-apply",
        disabled: !applicable || this.busy,
        text: applicable
          ? t("Apply to {label}", { label: this.target.label })
          : t("Nothing here fits this node"),
        onclick: () => this.apply(row),
      })] : []),
      // The atlas is somebody else's work and the dataset under it is somebody
      // else's again. Both are named where a style is used, not only in a readme.
      el("p", { class: "mmc-style-credit", text:
        t("Style Atlas by hoodtronik · dataset {dataset} by ostris",
          { dataset: this.atlas?.dataset ?? "minimax_h3_1k" }) }),
    );
  }

  /**
   * Who they are, in the inspector: their references at a size you can recognise
   * somebody at, each captioned with what it lends them, and their description
   * under them.
   *
   * The captions are the panel's argument. Four thumbnails of the same person say
   * nothing about why there are four; "their looks / their looks / they move like
   * this / this is their voice" is the definition itself, written out — and it is
   * the thing to check before casting them into a piece that already has a
   * different clip doing their movement.
   */
  renderCastBody(row) {
    const member = this.body?.cast ?? {};
    const files = member.files ?? [];
    const description = String(member.description ?? "").trim();
    return el("div", { class: "mmc-cast-insp" }, [
      ...(files.length ? [el("div", { class: "mmc-cast-insp-files" }, files.map((file) =>
        el("figure", {}, [
          (file.kind ?? "image") === "image"
            ? el("img", {
                onerror: (event) => event.target.replaceWith(icon("image", 18)),
                src: viewUrl(file.filename, { preview: true }), alt: "", loading: "lazy",
              })
            : el("span", { class: "mmc-cast-insp-glyph" },
                 [icon(file.kind === "audio" ? "audio" : "video", 18)]),
          el("figcaption", { text: t(CAST_SLOT_LABEL[file.slot] ?? file.slot) }),
        ])))] : []),
      ...(description ? [el("p", { class: "mmc-cast-insp-desc", text: description })] : []),
      ...(files.length || description ? [] : [el("p", {
        class: "mmc-preset-insp-hint",
        text: t("Nothing behind them — they are a name and nothing else."),
      })]),
    ]);
  }

  renderMeta(row) {
    const meta = el("p", { class: "mmc-preset-insp-meta" });
    const when = new Date(row.updated ?? row.created ?? Date.now());
    meta.append(el("span", { text: t("Updated {date}", { date: when.toLocaleDateString() }) }));
    if (row.builtin) return meta;
    meta.append(el("br"));
    meta.append(el("span", {
      // The bare filename: the folder is the output prefix's business and the
      // ` [output]` annotation is machinery, not something to read.
      text: row.cover
        ? t("Cover: {name} · ", { name: row.cover.path.replace(/ \[\w+\]$/, "").split("/").pop() })
        : t("No cover · "),
    }));
    meta.append(el("button", {
      text: row.cover ? t("Change") : t("Set"),
      onclick: () => this.pickCover(row),
    }));
    if (row.cover) {
      meta.append(el("span", { text: " · " }));
      meta.append(el("button", { text: t("Clear"), onclick: () => this.setCover(row, null) }));
    }
    return meta;
  }

  renderSectionRows(row) {
    return (row.sections ?? []).map((key) => {
      const section = P.SECTION[key];
      const cross = this.crossable(key, row);
      const on = this.keys.has(key);
      return el("button", {
        class: "mmc-preset-row",
        "aria-checked": on,
        disabled: !cross.ok,
        // A section that cannot cross is shown and disabled with the reason on
        // it, never hidden: a missing row is a bug the user reports.
        title: cross.ok ? "" : t(cross.why),
        onclick: () => {
          if (on) this.keys.delete(key); else this.keys.add(key);
          this.renderInspector();
        },
      }, [
        el("span", { class: "mmc-preset-box" }),
        el("span", { class: "mmc-preset-text" }, [
          el("b", { text: t(section?.label ?? key) }),
          el("span", { text: cross.ok ? this.describeSection(key) : t(cross.why) }),
        ]),
      ]);
    });
  }

  /** What this section actually holds, read off the body — so the row says "3
   *  LoRAs" rather than repeating the same sentence about what a LoRA is. */
  describeSection(key) {
    const body = this.body ?? {};
    const section = P.SECTION[key];
    switch (key) {
      case "look": {
        const look = body.look ?? {};
        return [look.aspect, look.short_edge ? t("{n} short edge", { n: look.short_edge }) : null,
                look.upscale === "two_pass" ? t("two-pass") : null].filter(Boolean).join(" · ");
      }
      case "weights": {
        const weights = body.weights ?? {};
        if (weights.arch) return t("{arch}, its own files", { arch: weights.arch });
        const files = Object.keys(weights).filter((field) => typeof weights[field] === "string"
          && field !== "dtype" && field !== "route").length;
        return [t(files === 1 ? "{count} file" : "{count} files", { count: files }),
                weights.route && weights.route !== "auto" ? t("routed {route}", { route: weights.route }) : null]
          .filter(Boolean).join(" · ");
      }
      case "speed": {
        const row = body.speed?.row ?? {};
        return [row.steps ? t("{n} steps", { n: row.steps }) : null,
                row.sampler_name, row.scheduler,
                body.speed?.turbo?.on ? t("turbo") : null].filter(Boolean).join(" · ");
      }
      case "prompt": {
        const text = (body.prompt?.prompt ?? "").trim();
        return text ? text.slice(0, 90) : t("empty");
      }
      case "loras": {
        const count = (body.loras ?? []).length;
        return t(count === 1 ? "{count} LoRA" : "{count} LoRAs", { count });
      }
      case "refs": {
        const refs = body.refs;
        const count = Array.isArray(refs)
          ? refs.length
          : (refs?.refs?.length ?? 0) + (refs?.init ? 1 : 0);
        return t(count === 1 ? "{count} file" : "{count} files", { count });
      }
      case "strip": {
        const segments = body.strip?.segments ?? [];
        const seams = segments.filter((segment) => segment.continue).length;
        return [t(segments.length === 1 ? "{count} card" : "{count} cards", { count: segments.length }),
                seams ? t("{count} continuations", { count: seams }) : null].filter(Boolean).join(" · ");
      }
      case "cast": {
        const member = body.cast ?? {};
        const files = (member.files ?? []).length;
        return [
          `@${member.handle ?? "subject"}`,
          t(files === 1 ? "{count} file" : "{count} files", { count: files }),
          t("added to the cast"),
        ].join(" · ");
      }
      case "shot": {
        const shot = body.shot ?? {};
        return [t("{n} s", { n: shot.duration_s ?? 0 }),
                shot.continue ? t("continues") : t("hard cut"),
                shot.merge ? t("merged") : null].filter(Boolean).join(" · ");
      }
      default:
        return t(section?.hint ?? "");
    }
  }

  // ---- the verbs ------------------------------------------------------------

  async apply(row) {
    if (this.busy) return;
    this.busy = true;
    try {
      this.target.apply(this.body, [...this.keys], row.scope);
      this.close();
    } catch (error) {
      this.busy = false;
      this.say(t("Could not apply it — {error}", { error: error.message }));
      this.renderInspector();
    }
  }

  /**
   * Save what the node is set to right now.
   *
   * Saved first and named after, rather than asked for a name up front: the
   * preset is the work, the name is a label on it, and there is nowhere better
   * to type one than the field the inspector already has. So it lands under the
   * first line of its own prompt, opens selected, and the name field takes focus
   * with the text selected — type over it or leave it.
   *
   * No `prompt()` and no `confirm()` anywhere in here. Nothing else in this pack
   * uses a browser dialog, and a modal the page cannot style is exactly the kind
   * of seam a library is supposed to hide.
   */
  async saveCurrent() {
    return this.commit(this.target.capture(), this.target.scope);
  }

  /**
   * Take a preset from a finished render instead of from a node.
   *
   * The other half of "a preset is a setup you can put back": the first half
   * assumes the setup is still on a node, and by the time you know a render was
   * the good one you have usually moved on. Both save nodes embed the workflow
   * that made the file, so the setup was never actually lost — it was in the
   * render, and this is the reader.
   *
   * The gallery is the picker, exactly as *Set cover…* opens it. There is no new
   * window here and nothing to learn: pick the render you liked, and its setup is
   * in the library with that render already on the card.
   */
  async saveFromRender() {
    const chosen = await openPicker({
      kinds: ["renders"],
      kind: "renders",
      capacity: () => ({ used: 0, max: 1, filesLeft: 1 }),
    });
    if (!chosen?.length) return;
    const asset = chosen[0];
    try {
      const captured = P.captureFromRender(await renderMeta(asset.path), asset);
      const saved = await this.commit(captured, captured.scope);
      // Said after the save rather than instead of it: the preset is a real one
      // off a real node, it may simply be off the other one of two.
      if (saved && captured.ambiguous) {
        this.say(t("That workflow holds {count} nodes this could have come from — this is node {node}.",
                   { count: captured.ambiguous, node: captured.node }));
      }
    } catch (error) {
      this.say(error.message);
    }
  }

  /** Store one capture, show it, and put the caret in its name. Both save verbs
   *  end here, so a preset made either way is the same preset. */
  async commit(captured, scope) {
    try {
      const row = await P.savePreset({
        name: captured.defaultName || t("Untitled preset"),
        scope,
        data: captured.data,
        cover: captured.cover ?? null,
      });
      this.rows = [row, ...this.rows];
      this.scope = row.scope;
      for (const [index, tab] of P.SCOPES.entries()) {
        this.tabs[index].setAttribute("aria-selected", String(tab === this.scope));
      }
      this.say(null);
      this.renderBar();
      this.renderShelves();
      this.renderGrid();
      await this.select(row);
      // The name is the one thing still to decide, so the caret is already in it.
      const field = this.inspector.querySelector?.(".mmc-preset-insp-name");
      field?.focus();
      field?.select?.();
      return row;
    } catch (error) {
      this.say(error.message);
      return null;
    }
  }

  async toggleStar(row) {
    try {
      const updated = await P.updatePreset(row.id, { starred: !row.starred, updated: row.updated });
      this.rows = this.rows.map((entry) => (entry.id === row.id ? updated : entry));
      if (this.selected?.id === row.id) this.selected = updated;
      this.renderShelves();
      this.renderGrid();
    } catch (error) {
      this.say(error.message);
    }
  }

  async rename(row, name) {
    const trimmed = name.trim();
    if (!trimmed || trimmed === row.name) return;
    try {
      const updated = await P.updatePreset(row.id, { name: trimmed });
      this.rows = this.rows.map((entry) => (entry.id === row.id ? updated : entry));
      this.selected = updated;
      this.renderGrid();
    } catch (error) {
      this.say(error.message);
    }
  }

  /** Set the cover from the gallery — the same window the rail's Gallery tool
   *  opens, because picking a render is exactly what it is for. */
  async pickCover(row) {
    const chosen = await openPicker({
      kinds: ["renders"],
      kind: "renders",
      capacity: () => ({ used: 0, max: 1, filesLeft: 1 }),
    });
    if (!chosen?.length) return;
    const picked = chosen[0];
    // The picker's row *is* the shape a cover is stored in — see
    // `coverFromResult`. Copied field for field rather than rebuilt.
    this.setCover(row, { path: picked.path, kind: picked.kind, mtime: picked.mtime });
  }

  async setCover(row, cover) {
    try {
      // The frames go with it: with a cover the lane is a ruler and draws no
      // pictures, and clearing one has to put them back.
      const updated = await P.updatePreset(row.id, {
        cover,
        ...P.describe(this.body ?? {}, row.scope, { cover }),
      });
      this.rows = this.rows.map((entry) => (entry.id === row.id ? updated : entry));
      this.selected = updated;
      this.renderGrid();
      this.renderInspector();
    } catch (error) {
      this.say(error.message);
    }
  }

  async remove(row) {
    try {
      await P.deletePreset(row.id);
      this.armed = null;
      this.rows = this.rows.filter((entry) => entry.id !== row.id);
      this.selected = null;
      this.body = null;
      this.renderShelves();
      this.renderGrid();
      this.renderInspector();
    } catch (error) {
      this.say(error.message);
    }
  }

  importFile() {
    const input = el("input", { type: "file", accept: ".json,application/json",
                                style: { display: "none" } });
    input.addEventListener("change", async () => {
      const file = input.files?.[0];
      input.remove();
      if (!file) return;
      try {
        const saved = await P.importPresets(file);
        this.say(null);
        await this.load();
        if (saved.length) this.select(saved[0]);
      } catch (error) {
        this.say(t("Could not import — {error}", { error: error.message }));
      }
    });
    document.body.appendChild(input);
    input.click();
  }
}

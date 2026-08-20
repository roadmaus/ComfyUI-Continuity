// The prompt box: rich text where every @reference is an atomic chip.
//
// The chip is the whole point of this UI. H3 addresses references by ordinal
// label — <Picture 2>, <Video 1> — and getting those right by hand is the real
// difficulty of prompting the model. Typing "@" and picking a file is how a
// person says "use *this* one for her face" without ever seeing a label.
//
// The DOM is kept deliberately flat: only text nodes and chip spans, never the
// <div>/<br> soup contenteditable produces on its own. Enter inserts a literal
// "\n" (the box is white-space: pre-wrap) and paste is forced to plain text, so
// getValue() is a simple walk and round-trips exactly with what compile.py
// parses.

import { el, floatAbove, icon, keepScroll, mountOverlay } from "./dom.js";
import { t } from "./i18n.js";
import { listAssets, viewUrl } from "./api.js";
import { tagIndex } from "./state.js";

const TRIGGER = /@([\w-]*)$/;
const MAX_SUGGESTIONS = 40;

// What counts as a line of its own when the browser has put one in the box.
// Nothing here is ever built by this class — see `getValue`, which is where
// they are read back out as the newlines they stand for.
const BLOCK = new Set(["DIV", "P", "LI", "TR", "BLOCKQUOTE", "PRE", "H1", "H2", "H3", "H4", "H5", "H6"]);

/**
 * The window a node face opens: one overlay, whatever the caller puts in it.
 *
 * It holds a whole node body — `CreatorEditor.openEditor` and
 * `PreStageEditor.openEditor` both build a second editor over the same state
 * and hand it here. So this knows nothing about prompts: it is a titled
 * overlay with a close, and the body inside it is the same body the face is.
 *
 * @returns {() => void} close it from outside
 */
export function openEditorSheet({ title, subtitle = "", content, onClose }) {
  const close = () => {
    unmount();
    onClose?.();
  };
  const overlay = el("div", {
    class: "mmc-overlay",
    onpointerdown: (event) => { if (event.target === overlay) close(); },
  }, [
    el("div", { class: "mmc-modal mmc-editor-sheet" }, [
      el("div", { class: "mmc-modal-head" }, [
        el("span", { class: "mmc-tab", "aria-selected": "true", text: title }),
        ...(subtitle ? [el("span", { class: "mmc-editor-sheet-sub", text: subtitle })] : []),
        el("button", { class: "mmc-close", text: "✕", title: t("Close"), onclick: close }),
      ]),
      el("div", { class: "mmc-editor-sheet-body" }, content),
    ]),
  ]);
  const unmount = mountOverlay(overlay, close);
  return close;
}

/** Focus a box and put the caret after everything in it — where the writing
 *  was when the face handed it over. */
export function focusEnd(element) {
  element.focus();
  const range = document.createRange();
  range.selectNodeContents(element);
  range.collapse(false);
  const selection = window.getSelection();
  selection?.removeAllRanges();
  selection?.addRange(range);
}

// What a click belongs to instead of to the prompt: a control that answers for
// itself, and the two regions of the panel that are not the writing area — the
// pill row and the rewrite below it, which has boxes of its own.
const NOT_THE_PROMPT =
  "button, input, select, textarea, a, summary, [contenteditable], .mmc-pills, .mmc-refined";

export class PromptBox {
  /**
   * @param {object} hooks
   * @param {()=>object} hooks.getState      current creator state
   * @param {(text:string)=>void} hooks.onInput   prompt text changed
   * @param {(row:object)=>string|null} hooks.onAttach  attach an input-folder file, -> handle
   * @param {(kind:string)=>string|null} hooks.attachBlocked  why attaching is impossible, or null
   * @param {()=>object[]} [hooks.getPool]   the piece's reference pool, for a
   *   timeline segment: citable by handle, never attached — writing the chip is
   *   what attaches it at queue time
   * @param {()=>object[]} [hooks.getCast]   the piece's cast. Cited exactly as a
   *   pool asset is, and recognised differently: a subject's name is only a
   *   citation because somebody declared it, so the chips are built from this
   *   list rather than from a shape
   * @param {()=>string} [hooks.attachedLabel]  what to call `getState().assets`
   *   in the menu. The timeline's global prompt is written against the piece's
   *   own pool rather than a card's attachments, and "Attached" would name it
   *   as something it is not.
   * @param {(over:boolean)=>void} [hooks.onOverflow]  the text stopped fitting
   *   the box, or started fitting it again. What a node face does about that is
   *   its own business — see `CreatorEditor.onPromptOverflow`.
   */
  constructor(hooks) {
    this.hooks = hooks;
    this.menu = null;

    this.root = el("div", {
      class: "mmc-prompt",
      contenteditable: "true",
      spellcheck: "false",
      role: "textbox",
      "aria-multiline": "true",
      "data-placeholder": t("Describe your video, use @ to reference images, videos, audio, or elements"),
    });

    this.root.addEventListener("input", () => this.onEdit());
    this.root.addEventListener("keydown", (event) => this.onKeyDown(event), true);
    this.root.addEventListener("paste", (event) => this.onPaste(event));
    // Text dragged in, held to the same rule as text pasted in. Left to the
    // browser this is the one editing route into the box that arrives as
    // markup — a drop carries `text/html` and the default handler inserts it
    // whole, wrappers and all, into a box whose every other route is plain
    // text. See `onPaste`, which this is the same handler as.
    this.root.addEventListener("drop", (event) => this.onPaste(event));
    this.root.addEventListener("blur", () => setTimeout(() => this.closeMenu(), 120));

    // The graph canvas swallows keys and drags otherwise.
    for (const name of ["keyup", "pointerdown", "pointerup"]) {
      this.root.addEventListener(name, (event) => event.stopPropagation());
    }
    // The wheel is not just swallowed: a box that has overflowed has to scroll
    // on it, and stopping the event alone left the text where it was while the
    // canvas zoomed anyway. See `keepScroll` — it hands the gesture back at
    // either end of the text, so zooming over a short prompt still works.
    keepScroll(this.root);

    // The box's own disclosure, shown only while a rewrite stands in for it.
    // `frame` is what a caller mounts; `root` stays the editable, because
    // everything else in here — the caret, the chips, the @ menu — is about
    // the editable and nothing about the wrapper.
    this.superseded = false;
    this.excerpt = el("span", { class: "mmc-prompt-excerpt" });
    this.head = el("summary", { class: "mmc-prompt-head" }, [
      icon("chevron", 12),
      el("span", { class: "mmc-prompt-head-name", text: t("your prompt") }),
      this.excerpt,
    ]);
    // What the compiler will write in front of the description, where the
    // `define_refs` setting is on and this prompt cites references. Inside the
    // fold and above the box, because it is part of the same prompt: it folds
    // away with it, and it reads in the order the model reads it. Filled by the
    // owner — see `CreatorEditor.renderScopes` — and empty otherwise, which is
    // every prompt on a machine that leaves the setting alone.
    this.scopeHost = el("div", { class: "mmc-scopes" });
    this.frame = el("details", { class: "mmc-prompt-fold" },
                    [this.head, this.scopeHost, this.root]);
    this.frame.open = true;
    this.frame.addEventListener("toggle", () => this.syncExcerpt());
    this.frame.addEventListener("pointerdown", (event) => event.stopPropagation());
  }

  /**
   * Treat an element's dead space as part of the box.
   *
   * A contenteditable is only clickable where its box is, and its box is the
   * text's slot rather than the panel it sits in — so the panel's own padding
   * and the gaps between its rows look like the writing area and are not. A
   * click landing on one of them did nothing at all, which reads as a dead
   * node rather than as a near miss.
   *
   * The box itself is not involved: it stops its own pointerdown, so anything
   * arriving here is outside it and the caret goes to the end, which is where
   * someone clicking past the text is asking to write. Controls and the panel's
   * other regions are left alone — see `NOT_THE_PROMPT`.
   *
   * This is also the belt to the layout's braces. The box fills its slot again
   * (see the `::details-content` rule in styles/editor.js) and it should; this
   * is what means a future engine getting that wrong costs a few pixels of
   * padding rather than the whole panel.
   */
  claim(element) {
    element.addEventListener("pointerdown", (event) => {
      // Nothing to focus while a rewrite stands in for the box: it is folded
      // away, and pulling the caret into a hidden box would be a click that
      // scrolls the panel for no reason.
      if (!this.frame.open) return;
      if (event.target.closest(NOT_THE_PROMPT)) return;
      event.preventDefault();
      focusEnd(this.root);
    });
  }

  // ---- value <-> DOM -------------------------------------------------------

  /**
   * The box, as the text `compile.py` parses.
   *
   * The DOM in here is meant to be flat — text nodes and chips, nothing else —
   * and everything this class does keeps it that way: Enter inserts a literal
   * "\n" rather than letting the browser wrap a line in a <div>, paste and drop
   * are forced to plain text. But "meant to be" is not "guaranteed": undo
   * restores the engine's own snapshot rather than ours, and Ctrl+B and friends
   * are the browser's commands on a contenteditable and wrap what is selected.
   *
   * So this reads whatever is actually there rather than what should be. It
   * used to walk the top level only, which was fine for the text — a wrapper's
   * `textContent` still carries it — and quietly wrong for everything that is
   * not text: a chip inside a wrapper came out as its label, and the *line
   * break a block wrapper is* came out as nothing at all. That is a paragraph
   * boundary disappearing from a prompt on a keystroke nobody would connect to
   * it, and the state is written from here on every one of them, so the loss is
   * saved as soon as it happens.
   */
  getValue() {
    let text = "";
    const walk = (parent) => {
      for (const node of parent.childNodes) {
        if (node.nodeType === Node.TEXT_NODE) {
          text += node.nodeValue;
        } else if (node.dataset?.handle) {
          text += `@${node.dataset.handle}`;
        } else if (node.tagName === "BR") {
          text += "\n";
        } else {
          // A block the engine put there is a line, and the newline it stands
          // for is the thing that would otherwise vanish. Not before the first
          // one: the browser wraps the *whole* content as readily as the tail
          // of it, and that must not grow a leading blank line.
          if (BLOCK.has(node.tagName) && text && !text.endsWith("\n")) text += "\n";
          walk(node);
        }
      }
    };
    walk(this.root);
    return text;
  }

  setValue(text) {
    if (this.getValue() === text) return;
    this.root.replaceChildren(...this.build(text));
    this.syncExcerpt();
    this.reportOverflow();
  }

  /** Whether the text has outgrown the box it is in. Measured rather than
   *  counted: how much fits is the node's height, the font and the wrapping,
   *  and none of those is a number this could hold. */
  overflowing() {
    return this.root.scrollHeight - this.root.clientHeight > 4;
  }

  reportOverflow() {
    this.hooks.onOverflow?.(this.overflowing());
  }

  /** Text -> [text nodes, chip spans]. Only handles with a live asset — the
   *  state's own or the piece's pool — and names the piece's cast declares
   *  become chips; the rest stay as plain text so the dangling-handle warning
   *  sees them.
   *
   *  The file half of the pattern is tried first, so `@img-1` is one handle and
   *  never the word "img". A name nobody cast matches the second half, finds no
   *  subject and stays prose — which is the promise the cast is built on. */
  build(text) {
    const known = new Set([
      ...this.hooks.getState().assets.map((a) => a.handle),
      ...(this.hooks.getPool?.() ?? []).map((a) => a.handle),
    ]);
    const cast = new Set((this.hooks.getCast?.() ?? []).map((s) => s.handle));
    const out = [];
    let at = 0;
    const pattern = /@([A-Za-z]+-\d+|[A-Za-z][A-Za-z0-9_]*)/g;
    let match;
    while ((match = pattern.exec(text)) !== null) {
      const handle = match[1];
      if (!known.has(handle) && !cast.has(handle)) continue;
      if (match.index > at) out.push(document.createTextNode(text.slice(at, match.index)));
      out.push(this.chip(handle, cast.has(handle)));
      at = match.index + match[0].length;
    }
    if (at < text.length) out.push(document.createTextNode(text.slice(at)));
    return out;
  }

  chip(handle, subject = false) {
    return el("span", {
      class: `mmc-ref${subject ? " mmc-ref-cast" : ""} mmc-tag-${tagIndex(handle)}`,
      contenteditable: "false",
      "data-handle": handle,
      text: `@${handle}`,
    });
  }

  /**
   * Dim the box while a rewrite stands in for it — and fold it away.
   *
   * `compile.refined_body` replaces this text outright rather than adding to it,
   * so with a rewrite switched on the sentence in here is not queued at all —
   * it is only what the rewrite was written from. Nothing on screen said so, and
   * a full-brightness box in the middle of the panel reads as the thing being
   * sent.
   *
   * Dimming said it but did not make room for the rewrite that *is* queued: two
   * full descriptions of the same shot, stacked, doubled the node's height and
   * pushed the one that matters below the fold. So the box now folds into its
   * own first line the moment a rewrite takes over, and the chevron opens it
   * again — it is still editable, because editing it is how you ask for a new
   * rewrite. Only the transition folds it: a second refine leaves a box you
   * deliberately opened open.
   */
  setSuperseded(on) {
    on = !!on;
    const changed = on !== this.superseded;
    this.superseded = on;
    this.frame.classList.toggle("superseded", on);
    // Never folded while this is the prompt being queued: there would be
    // nothing standing in for it and no way back to the thing you are writing.
    if (changed || !on) this.frame.open = !on;
    this.root.classList.toggle("superseded", on);
    const why = t("Not queued while the rewrite below is on — that is what the model reads. "
                + "Edit this and refine again, or revert the rewrite, to send it.");
    this.root.title = on ? why : "";
    this.head.title = on ? why : "";
    this.syncExcerpt();
  }

  /** The folded row shows the sentence's own first line, so the box can be
   *  recognised without opening it. Newlines collapse: it is one line of room. */
  syncExcerpt() {
    if (!this.excerpt) return;
    // From the state rather than by walking the box: `onInput` has already put
    // the typed text there, and the state is what a rewrite is compared against.
    const text = (this.hooks.getState().prompt ?? "").replace(/\s+/g, " ").trim();
    this.excerpt.textContent = text || t("No prompt yet");
    this.excerpt.classList.toggle("empty", !text);
  }

  /** Re-run the text through build(): an asset was added or removed, so some
   *  chips may need to become plain text or vice versa. Skipped while focused
   *  so it never yanks the caret mid-sentence. */
  refresh() {
    if (document.activeElement === this.root) return;
    this.root.replaceChildren(...this.build(this.hooks.getState().prompt ?? ""));
    this.syncExcerpt();
  }

  // ---- editing -------------------------------------------------------------

  onEdit() {
    this.hooks.onInput(this.getValue());
    this.syncExcerpt();
    this.reportOverflow();
    const trigger = this.triggerRange();
    if (trigger) this.openMenu(trigger.query);
    else this.closeMenu();
  }

  /** Text in from outside the box, always plain. Serves both `paste` and
   *  `drop` — the same event shape under two names, `dataTransfer` for the one
   *  and `clipboardData` for the other. */
  onPaste(event) {
    event.preventDefault();
    const source = event.clipboardData ?? event.dataTransfer;
    const text = source?.getData("text/plain") ?? "";
    // A drop lands where it was dropped, not where the caret was: the selection
    // at that moment is still the text being dragged, so inserting at it would
    // put the text back where it came from. Best effort — an engine without
    // `caretRangeFromPoint` falls through to the caret, which is where a paste
    // goes anyway.
    if (event.dataTransfer) this.caretAt(event);
    this.insertText(text.replace(/\r\n?/g, "\n"));
    this.onEdit();
  }

  /** Put the caret where a pointer event landed. */
  caretAt(event) {
    const range = document.caretRangeFromPoint?.(event.clientX, event.clientY);
    if (!range || !this.root.contains(range.startContainer)) return;
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
  }

  onKeyDown(event) {
    if (this.menu && ["ArrowDown", "ArrowUp", "Enter", "Tab", "Escape"].includes(event.key)) {
      event.preventDefault();
      event.stopPropagation();
      if (event.key === "Escape") this.closeMenu();
      else if (event.key === "Enter" || event.key === "Tab") this.choose(this.active);
      else this.move(event.key === "ArrowDown" ? 1 : -1);
      return;
    }
    event.stopPropagation();

    if (event.key === "Enter") {
      // Keep the DOM flat: no <div> wrappers from the browser's own handling.
      event.preventDefault();
      this.insertText("\n");
      this.onEdit();
    }
  }

  /** The "@query" immediately before the caret, or null. */
  triggerRange() {
    const selection = window.getSelection();
    if (!selection?.rangeCount || !selection.isCollapsed) return null;
    const range = selection.getRangeAt(0);
    const node = range.startContainer;
    if (node.nodeType !== Node.TEXT_NODE || !this.root.contains(node)) return null;
    const match = TRIGGER.exec(node.nodeValue.slice(0, range.startOffset));
    if (!match) return null;
    return { node, start: range.startOffset - match[0].length, end: range.startOffset, query: match[1] };
  }

  insertText(text) {
    const selection = window.getSelection();
    if (!selection?.rangeCount) return;
    const range = selection.getRangeAt(0);
    range.deleteContents();
    const node = document.createTextNode(text);
    range.insertNode(node);
    range.setStartAfter(node);
    range.collapse(true);
    selection.removeAllRanges();
    selection.addRange(range);
  }

  /** Swap the typed "@query" for a chip, followed by a space. */
  insertChip(handle) {
    const trigger = this.triggerRange();
    const selection = window.getSelection();
    const range = document.createRange();
    if (trigger) {
      range.setStart(trigger.node, trigger.start);
      range.setEnd(trigger.node, trigger.end);
      range.deleteContents();
    } else if (selection?.rangeCount) {
      range.setStart(selection.getRangeAt(0).startContainer, selection.getRangeAt(0).startOffset);
      range.collapse(true);
    } else {
      this.root.appendChild(this.chip(handle));
      this.root.appendChild(document.createTextNode(" "));
      this.hooks.onInput(this.getValue());
      return;
    }
    const chip = this.chip(handle);
    const space = document.createTextNode(" ");
    range.insertNode(space);
    range.insertNode(chip);
    const after = document.createRange();
    after.setStart(space, 1);
    after.collapse(true);
    selection.removeAllRanges();
    selection.addRange(after);
    this.hooks.onInput(this.getValue());
  }

  // ---- suggestion menu -----------------------------------------------------

  async openMenu(query) {
    this.query = query.toLowerCase();
    if (!this.menu) {
      this.menu = el("div", { class: "mmc-mention" });
      // Above whatever is open: the same prompt box is the node's body and a
      // timeline segment's editor, and in the second case it is inside a modal.
      floatAbove(this.menu);
      document.body.appendChild(this.menu);
      this.active = 0;
    }
    this.place();
    this.renderMenu();          // attached assets are known immediately
    try {
      this.library = await listAssets();
    } catch {
      this.library = [];
    }
    if (this.menu) this.renderMenu();
  }

  closeMenu() {
    this.menu?.remove();
    this.menu = null;
    this.active = 0;
    this.rows = null;
    this.signature = null;
  }

  place() {
    const selection = window.getSelection();
    if (!selection?.rangeCount || !this.menu) return;
    const rect = selection.getRangeAt(0).getBoundingClientRect();
    const anchor = rect.width || rect.height ? rect : this.root.getBoundingClientRect();
    const box = this.menu.getBoundingClientRect();
    const height = box.height || 260;
    const top = anchor.top - height - 8 > 8 ? anchor.top - height - 8 : anchor.bottom + 8;
    this.menu.style.left = `${Math.max(8, Math.min(anchor.left, window.innerWidth - 340))}px`;
    this.menu.style.top = `${Math.max(8, Math.min(top, window.innerHeight - height - 8))}px`;
  }

  /** The cast first, then attached assets, then the piece's pool, then the
   *  input folder. The cast leads because a subject is what a sentence is
   *  usually about, and because citing one is how her files get here at all. */
  options() {
    const state = this.hooks.getState();
    const cast = (this.hooks.getCast?.() ?? [])
      .filter((subject) => subject.handle)
      .filter((subject) => !this.query
        || subject.handle.toLowerCase().includes(this.query)
        || String(subject.description ?? "").toLowerCase().includes(this.query))
      .map((subject) => ({ kind: "cast", handle: subject.handle, subject }));
    const attached = state.assets
      .filter((asset) => !this.query || asset.handle.toLowerCase().includes(this.query)
        || asset.filename.toLowerCase().includes(this.query))
      .map((asset) => ({ kind: "attached", handle: asset.handle, path: asset.filename, mediaKind: asset.kind }));

    // The pool is citable, never attached: choosing one only writes the chip,
    // and the citation is what carries the file into this generation at queue
    // time. Hidden while references are blocked here (a start/end frame is
    // set), because the chip would queue a checkpoint clash.
    const own = new Set(state.assets.map((a) => a.handle));
    const pool = this.hooks.attachBlocked("reference") ? []
      : (this.hooks.getPool?.() ?? [])
        .filter((asset) => !own.has(asset.handle))
        .filter((asset) => !this.query || asset.handle.toLowerCase().includes(this.query)
          || asset.filename.toLowerCase().includes(this.query))
        .map((asset) => ({ kind: "pool", handle: asset.handle, path: asset.filename, mediaKind: asset.kind }));

    const used = new Set(state.assets.map((a) => a.filename));
    const library = (this.library ?? [])
      .filter((row) => !used.has(row.path))
      .filter((row) => !this.query || row.path.toLowerCase().includes(this.query))
      .slice(0, MAX_SUGGESTIONS)
      .map((row) => ({ kind: "library", path: row.path, mediaKind: row.kind, row }));

    return { cast, attached, pool, library };
  }

  renderMenu() {
    if (!this.menu) return;
    const { cast, attached, pool, library } = this.options();
    this.flat = [...cast, ...attached, ...pool, ...library];
    if (this.active >= this.flat.length) this.active = Math.max(0, this.flat.length - 1);

    // openMenu() renders once immediately and again when the library resolves,
    // and every keystroke re-renders too. Rebuilding identical rows would throw
    // away the highlight and re-fire mouseenter under a stationary pointer, so
    // only rebuild when the list actually differs.
    const signature = this.flat.map((option) => option.handle ?? option.path).join("\u0000");
    if (this.rows?.length && signature === this.signature) return;
    this.signature = signature;

    this.menu.replaceChildren();
    this.rows = [];
    if (!this.flat.length) {
      this.menu.appendChild(el("div", { class: "mmc-mention-empty", text: t("Nothing matches.") }));
      return;
    }

    // A subject's thumbnail is the first picture she is made of — the point of
    // the row is to recognise her, and her own face does that where a glyph
    // cannot. Looked up through the pool because that is where a cast's files
    // live; a subject built only out of a clip or a vacancy keeps the glyph.
    const faceOf = (subject) => {
      const pool = [...(this.hooks.getPool?.() ?? []),
                    ...(this.hooks.getState().assets ?? [])];
      for (const handle of subject.from ?? []) {
        const asset = pool.find((a) => a.handle === handle);
        if (asset?.kind === "image") return asset.filename;
      }
      return null;
    };

    let index = 0;
    const row = (option) => {
      const here = index++;
      const face = option.kind === "cast" ? faceOf(option.subject) : null;
      const thumb = option.mediaKind === "image" || face
        ? el("img", {
            class: "mmc-mention-thumb",
            src: viewUrl(face ?? option.path, { preview: true }), alt: "",
          })
        : el("span", {
            class: "mmc-mention-thumb",
            text: option.kind === "cast" ? "☺" : option.mediaKind === "video" ? "▶" : "♪",
          });

      // Attached assets are known by their handle; a library file is known by
      // its name, and only earns a second line when it lives in a subfolder —
      // repeating the same string twice told the user nothing. A subject's
      // second line is what she is, which is the whole of what the cast knows
      // about her that her name does not say.
      const made = option.kind === "cast"
        ? (option.subject.description
           || [...(option.subject.from ?? []), option.subject.motion, option.subject.voice]
                .filter(Boolean).map((h) => "@" + h).join(", "))
        : null;
      const title = option.handle ? `@${option.handle}` : option.path.split("/").pop();
      const subtitle = option.kind === "cast" ? made
        : option.handle ? option.path : (option.row?.subfolder || "");

      const item = el("button", {
        class: "mmc-mention-row",
        "aria-selected": here === this.active,
        title: option.kind === "cast" ? `@${option.handle}` : option.path,
        onmouseenter: () => this.highlight(here),
        onclick: (event) => { event.preventDefault(); this.choose(here); },
      }, [
        thumb,
        el("span", { class: "mmc-mention-text" }, [
          el("span", {
            class: `mmc-mention-handle${option.handle ? ` mmc-tag-${tagIndex(option.handle)}` : ""}`,
            text: title,
          }),
          ...(subtitle ? [el("span", { class: "mmc-mention-sub", text: subtitle })] : []),
        ]),
      ]);
      // Keep focus in the box: a blurred contenteditable loses its caret, and
      // without a caret there is nowhere to insert the chip.
      item.addEventListener("pointerdown", (event) => event.preventDefault());
      this.rows.push(item);
      return item;
    };

    if (cast.length) {
      this.menu.appendChild(el("div", { class: "mmc-mention-head", text: t("Cast") }));
      for (const option of cast) this.menu.appendChild(row(option));
    }
    if (attached.length) {
      this.menu.appendChild(el("div", {
        class: "mmc-mention-head",
        text: this.hooks.attachedLabel?.() ?? t("Attached"),
      }));
      for (const option of attached) this.menu.appendChild(row(option));
    }
    if (pool.length) {
      this.menu.appendChild(el("div", { class: "mmc-mention-head", text: t("Piece references") }));
      for (const option of pool) this.menu.appendChild(row(option));
    }
    if (library.length) {
      const blocked = this.hooks.attachBlocked("reference");
      this.menu.appendChild(el("div", {
        class: "mmc-mention-head",
        text: blocked ? t("Input folder — unavailable while a start/end frame is set") : t("Input folder"),
      }));
      for (const option of library) this.menu.appendChild(row(option));
    }
    this.place();
  }

  /**
   * Move the highlight without rebuilding the rows.
   *
   * Re-rendering here is what broke both arrow keys and clicks: the rebuilt row
   * under the pointer immediately fired mouseenter and stole the selection
   * back, and a row replaced between pointerdown and click never fired click at
   * all.
   */
  highlight(index, { scroll = false } = {}) {
    if (!this.rows?.length) return;
    this.active = index;
    this.rows.forEach((row, at) => row.setAttribute("aria-selected", String(at === index)));
    if (scroll) this.rows[index]?.scrollIntoView({ block: "nearest" });
  }

  move(delta) {
    if (!this.flat?.length) return;
    this.highlight((this.active + delta + this.flat.length) % this.flat.length, { scroll: true });
  }

  choose(index) {
    const option = this.flat?.[index];
    if (!option) return;
    if (option.kind === "cast" || option.kind === "attached" || option.kind === "pool") {
      // Both already have a handle; for a pool asset the chip *is* the
      // attachment — the citation carries it into this generation at queue time.
      this.closeMenu();
      this.insertChip(option.handle);
      return;
    }
    // A library file has no handle yet: attaching it is what creates one.
    const handle = this.hooks.onAttach(option.row);
    this.closeMenu();
    if (handle) this.insertChip(handle);
  }
}

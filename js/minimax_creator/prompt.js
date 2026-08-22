// The prompt box: rich text where every @reference is an atomic chip.
//
// The chip is the whole point of this UI. H3 addresses references by ordinal
// label — <Picture 2>, <Video 1> — and getting those right by hand is the real
// difficulty of prompting the model. Typing "@" and picking a file is how a
// person says "use *this* one for their face" without ever seeing a label.
//
// The DOM is kept deliberately flat: only text nodes and chip spans, never the
// <div>/<br> soup contenteditable produces on its own. Enter inserts a literal
// "\n" (the box is white-space: pre-wrap) and paste is forced to plain text, so
// getValue() is a simple walk and round-trips exactly with what compile.py
// parses.

import { el, floatAbove, icon, keepScroll, mountOverlay } from "./dom.js";
import { t } from "./i18n.js";
import { castFactsLine, listPresets, loadBody } from "./presets.js";
import { listAssets, viewUrl } from "./api.js";
import { tagIndex } from "./state.js";

const TRIGGER = /@([\w-]*)$/;
/* The other opening. `@` cites what is already in this piece; `/` is the layer
   above it — where a thing comes *from*: the style atlas, the cast library, the
   input folder. Only at the start of a word, or "input/clip" and "and/or" would
   summon a menu mid-sentence. */
const COMMAND = /\/([\w-]*)$/;
const MAX_SUGGESTIONS = 40;

/* The two fields a description lands in — `contextir.BODY_FIELDS`. Whichever of
   them a compiled prompt carries is the block holding what you actually wrote,
   which is the one thing the panel marks. */
const BODY_FIELDS = new Set(["integrated_multimodal_description", "detailed_description"]);

/**
 * A compiled prompt -> the blocks it is made of.
 *
 * `contextir.compose` joins its sections with a blank line and writes each one
 * as `field: prose`; the instruction line is the exception and carries no
 * field, because it is not a section. Pulling them apart again is presentation
 * and nothing else — the compiler stays the only thing that decides what goes
 * in, and this only decides how it is set.
 */
export function compiledBlocks(text) {
  return String(text || "").split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter(Boolean)
    .map((block) => {
      const named = /^([a-z][a-z_]*):\s*([\s\S]*)$/.exec(block);
      if (!named) return { key: "", value: block, mine: false };
      return { key: named[1], value: named[2].trim(), mine: BODY_FIELDS.has(named[1]) };
    });
}

/* The three sources `/` offers, in the order a shot is usually built: the look
   it is in, who is in it, then what it points at. `door` is the row that opens
   the window this source really lives in — a catalogue of 941 stills has no
   honest 300px version, so the Style branch is that row and nothing else. */
const SOURCES = [
  { branch: "style", label: "Style", sub: "941 shipped looks — type to search them",
    iconName: "effect" },
  { branch: "cast", label: "Cast", sub: "somebody from the cast library", iconName: "face" },
  { branch: "refs", label: "References", sub: "a picture, a clip or a sound to point at",
    iconName: "image" },
];

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
  "button, input, select, textarea, a, summary, [contenteditable], .mmc-pills, .mmc-refined,"
  + " .mmc-compiled";

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
   * @param {(member:object)=>string|null} [hooks.castFromLibrary]  cast one
   *   kept member into the piece and answer with the name they landed under.
   *   Absent where there is no piece to cast them into — a card's editor is one
   *   shot of a piece whose cast is owned a level up — and the roster is left
   *   out of the menu with it.
   * @param {()=>string} [hooks.attachedLabel]  what to call `getState().assets`
   *   in the menu. The timeline's global prompt is written against the piece's
   *   own pool rather than a card's attachments, and "Attached" would name it
   *   as something it is not.
   * @param {(over:boolean)=>void} [hooks.onOverflow]  the text stopped fitting
   *   the box, or started fitting it again. What a node face does about that is
   *   its own business — see `CreatorEditor.onPromptOverflow`.
   * @param {(handle:string)=>void} [hooks.onCastChip]  a subject's name in the
   *   sentence was clicked. The name is where a subject is used, so it
   *   is also the obvious place to ask what they are made of — see
   *   `CreatorEditor.openCastMember`, which summons the shelf onto them.
   * @param {(row:object)=>string|null} [hooks.castStyle]  cast one atlas
   *   look into the piece and answer with the handle it landed under. Absent
   *   where there is no piece to cast it into — the same rule `castFromLibrary`
   *   follows — and the Style rows are left out of the `/` menu with it.
   * @param {(scope:string)=>void} [hooks.openLibrary]  open the preset library
   *   on a scope — the `/` menu's door onto the style atlas and the cast
   *   library. Absent where there is no node for a preset to land on, and the
   *   rows are left out of the menu with it.
   * @param {()=>void} [hooks.onBrowse]  open the file picker — the `/` menu's
   *   door onto the input folder, for a file whose name you do not know.
   * @param {(handles:string[])=>void} [hooks.onUncited]  chips that were in the
   *   box a keystroke ago and are not in it now. Deleting a chip is how this
   *   redesign takes a reference or a cast member out of a shot, so the host has
   *   to hear about it — see `CreatorEditor.dropCited`.
   */
  constructor(hooks) {
    this.hooks = hooks;
    this.menu = null;
    // Where the typed "@query" that opened the menu sits, as a character offset
    // into `getValue`. `dismissMenu` erases it; `onEdit` keeps it current.
    this.typed = null;
    // The handles the box is showing as chips, as of the last time anything
    // wrote to it. `onEdit` diffs against this to find the ones a keystroke just
    // deleted — see `censusChips`.
    this.chipped = new Set();

    this.root = el("div", {
      // The second class is the affordance: a cast chip is only worth a pointer
      // where clicking it opens somebody, and that is the host's answer
      // rather than the box's.
      class: `mmc-prompt${hooks.onCastChip ? " mmc-prompt-castable" : ""}`,
      contenteditable: "true",
      spellcheck: "false",
      role: "textbox",
      "aria-multiline": "true",
      // Both openings, because the second one was invisible: the box answers
      // "/" with the cast library, the input folder and the style atlas, and
      // nothing on screen said so — a placeholder that named only "@" read as
      // the complete list of what the box does.
      "data-placeholder": t("Describe your video — @ cites what is attached, / brings in cast, files and looks"),
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
    // The grace period is for the click that is landing on a menu row: that
    // closes the menu itself, and a dismissal arriving after it would erase the
    // name it just wrote. `dismissMenu` no-ops once the menu is gone.
    this.root.addEventListener("blur", () => setTimeout(() => this.dismissMenu(false), 120));
    // A subject's name, opened on. The chip is contenteditable="false", so a
    // click on it had nowhere to put a caret and did nothing — which makes the
    // gesture free, and it is the right one besides: the name in the sentence is
    // where somebody is *used*, so it is the shortest way to ask what they are
    // made of. One click rather than two, because the chip already wears the
    // pointer and a pointer that wants two presses is a pointer that lies.
    //
    // Only cast chips: a reference's chip has its own row of controls sitting
    // directly above the box. And deleting one is unaffected — a chip is removed
    // with the caret and Backspace, the same as it always was.
    this.root.addEventListener("click", (event) => {
      const chip = this.castChip(event);
      if (!chip) return;
      event.preventDefault();
      this.hooks.onCastChip?.(chip.dataset.handle);
    });
    // A press on a name is a command, and a command is not a selection. Left to
    // the browser, a click on a contenteditable="false" chip selects the whole
    // node — the name turns into a blue block and stays one until you click
    // somewhere else, which is a lot of noise for a press whose whole visible
    // result is a panel opening under it.
    //
    // Cancelled at mousedown, because that is where the selection is made.
    // Cancelling it there does not cancel the click, which is what carries the
    // gesture — see the listener above. It does mean a press on a name no
    // longer puts the caret beside it; that is the right trade for a chip you
    // are pressing on purpose, and the text either side of it is a character
    // away.
    //
    // Only the names, and only where they open somebody. A file's chip is not a
    // control, so selecting it is the ordinary thing to be doing with it.
    this.root.addEventListener("mousedown", (event) => {
      if (this.castChip(event)) event.preventDefault();
    });

    // The graph canvas swallows keys and drags otherwise, and answers a copy
    // or a cut in here by taking one of the graph — the same document listener
    // and the same blind spot as the paste one; see `onPaste`. Today a text
    // selection talks it out of that, and a selection is what a copy is, but
    // that is their guard holding rather than ours.
    for (const name of ["keyup", "pointerdown", "pointerup", "copy", "cut"]) {
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

    // ---- what the model reads -----------------------------------------------
    //
    // The sentence you write is not the prompt that is queued. The compiler
    // wraps it in the guide's sections, defines every reference the tokenizer
    // will be shown, states what becomes of each one and summarises the job —
    // and none of that was visible anywhere, so the way to find out what had
    // been sent was to read the console or guess.
    //
    // It is shown *under* the sentence rather than in place of it. The first
    // attempt was a pair of tabs that swapped the two, and swapping was the
    // mistake: the compiled prompt contains your sentence, so putting them in
    // the same rectangle one at a time asks you to hold the first in your head
    // to see what the second added — and for a shot with nothing to declare the
    // two look near enough identical that the feature reads as broken. Stacked,
    // the difference is the thing on screen.
    //
    // Read-only, and derived: a caret in here would be a caret in something the
    // next keystroke rewrites. The way to change it is to change the sentence.
    this.compiledOpen = false;
    // One request at a time per box. `refreshCompiled` is called on every edit
    // and on every render, and the first version fired a fetch for each of them
    // and dropped every answer but the newest — which, while renders kept
    // arriving, was never any of them, so the panel stayed empty forever. In
    // flight, a new ask sets `dirty` and is served by one more fetch when the
    // current one lands.
    this.compiledBusy = false;
    this.compiledDirty = false;

    this.compiledStatus = el("span", { class: "mmc-compiled-status" });
    this.compiledDoc = el("div", { class: "mmc-compiled-doc" });
    keepScroll(this.compiledDoc);
    this.compiledRail = el("button", {
      class: "mmc-compiled-rail", type: "button", "aria-expanded": false,
      onclick: (event) => {
        event.preventDefault();
        event.stopPropagation();
        this.setCompiledOpen(!this.compiledOpen);
      },
    }, [
      icon("chevron", 12),
      el("span", { class: "mmc-compiled-title", text: t("What the model reads") }),
      this.compiledStatus,
    ]);
    // Only where somebody can answer for the finished prompt. A host that
    // cannot compile the piece gets the box it always had rather than a rail
    // that opens onto an apology. Empty, the CSS takes it out of the layout.
    this.compiled = el("div", { class: "mmc-compiled" },
                       hooks.compiled ? [this.compiledRail, this.compiledDoc] : []);
    this.compiled.addEventListener("pointerdown", (event) => event.stopPropagation());

    this.head = el("summary", { class: "mmc-prompt-head" }, [
      icon("chevron", 12),
      el("span", { class: "mmc-prompt-head-name", text: t("your prompt") }),
      this.excerpt,
    ]);
    this.frame = el("details", { class: "mmc-prompt-fold" },
                    [this.head, this.root, this.compiled]);
    this.frame.open = true;
    this.frame.addEventListener("toggle", () => this.syncExcerpt());
    this.frame.addEventListener("pointerdown", (event) => event.stopPropagation());
  }

  /**
   * Open or close the compiled prompt.
   *
   * Opening draws the waiting state first and asks second, so the rail never
   * expands onto nothing: whatever the fetch does, there is already a shape
   * under it saying that a shape is coming.
   */
  setCompiledOpen(open) {
    this.compiledOpen = !!open && !!this.hooks.compiled;
    this.compiled.classList.toggle("open", this.compiledOpen);
    this.compiledRail.setAttribute("aria-expanded", String(this.compiledOpen));
    if (!this.compiledOpen) {
      this.compiledDoc.replaceChildren();
      this.compiledStatus.textContent = "";
      this.compiled.classList.remove("problem");
      return;
    }
    this.drawWaiting();
    this.refreshCompiled();
  }

  /**
   * Re-read the finished prompt, if it is open.
   *
   * Called by the host whenever the piece changes — a chip attached, somebody
   * cast, a word typed — because all of those change the prompt without going
   * anywhere near the box. A no-op while the rail is closed, so the host can
   * call it on every edit without thinking about it.
   */
  async refreshCompiled() {
    if (!this.compiledOpen || !this.hooks.compiled) return;
    if (this.compiledBusy) { this.compiledDirty = true; return; }
    this.compiledBusy = true;
    this.compiledDirty = false;
    this.compiled.classList.add("loading");

    let answer;
    try {
      answer = await this.hooks.compiled();
    } catch (problem) {
      // A host that throws is a fact about this pack, not about the prompt, so
      // it is reported in the panel rather than left as an unhandled rejection
      // with an empty box under it — which is what the first version did.
      answer = { problem: String(problem?.message || problem) };
    }
    this.compiledBusy = false;
    this.compiled.classList.remove("loading");
    if (!this.compiledOpen) return;
    if (this.compiledDirty) return this.refreshCompiled();
    this.drawCompiled(answer || {});
  }

  /** Three bars where the sections will be. Shown while the first answer is
   *  outstanding, and again for nothing else — a re-read of an open panel
   *  keeps the text that is on screen and dims it, because replacing prose you
   *  are reading with bars on every keystroke is worse than a stale word. */
  drawWaiting() {
    this.compiled.classList.remove("problem");
    this.compiledStatus.textContent = t("compiling…");
    this.compiledDoc.replaceChildren(...[76, 92, 58].map((width) =>
      el("div", { class: "mmc-compiled-bar", style: { width: `${width}%` } })));
  }

  /**
   * Draw one compiled prompt.
   *
   * The text arrives as the compiler wrote it — blank-line separated blocks,
   * each one `field: prose` bar the instruction line, which has no field
   * because it is not a section. Splitting it back apart is presentation and
   * nothing else: the keys are shown as keys and the prose as prose, so a
   * document is legible as a document instead of as one long paragraph in the
   * same face and size as the box above it.
   *
   * The block holding your own sentence is marked, and it is the only thing in
   * here that is marked. That is the question the panel exists to answer — what
   * did the compiler add — and one accent answers it without a legend.
   */
  drawCompiled({ problem = "", note = "", text = "", message = "" } = {}) {
    this.compiled.classList.toggle("problem", !!problem);

    if (problem) {
      this.compiledStatus.textContent = t("could not compile");
      this.compiledDoc.replaceChildren(el("p", { class: "mmc-compiled-problem", text: problem }));
      return;
    }

    this.compiledStatus.textContent = note;
    // The panel talking rather than a prompt to show: a clip that generates
    // nothing has no wire keys, and dressing our sentence in one would be
    // inventing a field the model is never handed.
    if (message) {
      this.compiledDoc.replaceChildren(el("p", { class: "mmc-compiled-note", text: message }));
      return;
    }

    const blocks = compiledBlocks(text);
    if (!blocks.length) {
      this.compiledDoc.replaceChildren(el("p", {
        class: "mmc-compiled-empty",
        text: t("Nothing is queued for this shot yet. Write a sentence above."),
      }));
      return;
    }

    const declared = blocks.filter((block) => block.key && !block.mine).length;
    this.compiledDoc.replaceChildren(
      ...blocks.map(({ key, value, mine }) => el("div", {
        class: `mmc-compiled-block${mine ? " mine" : ""}`,
      }, [
        el("div", { class: "mmc-compiled-key" }, [
          // The blocks with no field are the guide's alignment statements —
          // `contextir.instruction` and the preamble `ref_frame_alignment`
          // writes. They carry no wire key because they are not sections, so
          // the panel names them for what they say.
          el("span", { text: key || t("frame alignment") }),
          ...(mine ? [el("span", { class: "mmc-compiled-mine", text: t("yours") })] : []),
        ]),
        el("p", { class: "mmc-compiled-value", text: value }),
      ])),
      // Said plainly, because "it looks the same as what I typed" is the right
      // reading of this case and not a bug: a shot with no cast and no
      // references has nothing to define, so the compiler wraps the sentence
      // and adds nothing to it.
      ...(declared ? [] : [el("p", {
        class: "mmc-compiled-note",
        text: t("Nothing else is added — this shot has nothing to define, so your "
              + "sentence is the whole prompt."),
      })]),
    );
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
    this.censusChips();
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

  /** The cast chip an event landed on, if it landed on one that opens somebody.
   *  One answer for the two listeners that ask, so a press and the selection it
   *  must not make can never disagree about what was pressed. */
  castChip(event) {
    if (!this.hooks.onCastChip) return null;
    const chip = event.target?.closest?.(".mmc-ref-cast[data-handle]");
    return chip && this.root.contains(chip) ? chip : null;
  }

  chip(handle, subject = false) {
    return el("span", {
      class: `mmc-ref${subject ? " mmc-ref-cast" : ""} mmc-tag-${tagIndex(handle)}`,
      contenteditable: "false",
      "data-handle": handle,
      // Said on the chip, because a gesture nobody can see is a gesture nobody
      // finds. The pointer is the other half of it — see .mmc-prompt-castable.
      title: subject && this.hooks.onCastChip
        ? t("Edit @{handle}", { handle })
        : undefined,
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
    const text = this.hooks.getState().prompt ?? "";
    const built = this.build(text);
    // Nothing to do where nothing changed, and this is not an optimisation.
    //
    // A press is a pointerdown and a click on *the same element*. The host
    // re-renders for its own reasons — a pill moved, a probe answered, a commit
    // landed — and every one of those used to replace the box's children, so the
    // chip a press had started on was detached before the browser could finish
    // the click on it. No click event, no error, nothing in the console: a name
    // in the sentence that simply does not open, broken by an edit nowhere near
    // this file. That is why the gesture has kept coming back broken.
    //
    // Compared as the finished nodes rather than as the source text, because
    // what makes a handle a chip is not in the text: the cast and the pool
    // decide it, and either can change while the sentence does not.
    if (!this.sameAs(built)) this.root.replaceChildren(...built);
    // A handle that stopped being a chip because its asset was detached from the
    // asset row is not a deletion the user made *here*, and re-noting the census
    // after the rebuild is what keeps `onEdit` from reporting it as one.
    this.censusChips();
    this.syncExcerpt();
  }

  /** Whether the box already holds exactly what `built` would put in it: the
   *  same run of text and chips, in the same order, with the same handles. */
  sameAs(built) {
    const have = [...this.root.childNodes];
    if (have.length !== built.length) return false;
    return built.every((want, index) => {
      const got = have[index];
      if (got.nodeType !== want.nodeType) return false;
      if (want.nodeType === 3) return got.textContent === want.textContent;
      return got.className === want.className
          && got.dataset?.handle === want.dataset?.handle;
    });
  }

  /**
   * Note which handles the box is currently showing as chips.
   *
   * Chips rather than text, and the DOM rather than the string, because a chip
   * is the only thing in here that is deleted whole: it is contenteditable=false,
   * so the caret cannot get inside one and a Backspace against it takes the name
   * with it. Diffing the *text* instead would have called every keystroke in the
   * middle of a hand-typed "@ref-1" a deletion, and detached the file on the way
   * past.
   */
  censusChips() {
    this.chipped = new Set(
      [...this.root.querySelectorAll("[data-handle]")].map((node) => node.dataset.handle));
  }

  // ---- editing -------------------------------------------------------------

  onEdit() {
    const before = this.chipped;
    this.censusChips();
    this.hooks.onInput(this.getValue());
    // After `onInput`, so the host is asked "is this handle still written
    // anywhere" about the text as it now stands rather than as it was.
    const gone = [...before].filter((handle) => !this.chipped.has(handle));
    if (gone.length) this.hooks.onUncited?.(gone);
    this.syncExcerpt();
    this.reportOverflow();
    const trigger = this.triggerRange();
    if (trigger) {
      // Measured every keystroke, because dismissal has to erase it and by then
      // there may be no live selection to measure from — see `dismissMenu`.
      const spot = this.triggerSpot();
      this.typed = spot && { ...spot, text: trigger.mode + trigger.query };
      this.openMenu(trigger.query, trigger.mode);
    } else this.closeMenu();
  }

  /** Text in from outside the box, always plain. Serves both `paste` and
   *  `drop` — the same event shape under two names, `dataTransfer` for the one
   *  and `clipboardData` for the other. */
  onPaste(event) {
    event.preventDefault();
    // And kept off the canvas. ComfyUI pastes nodes from a `document` listener
    // that decides the event is "on the graph" by asking whether the target is
    // an <input> or a <textarea>; a contenteditable is neither, and preventing
    // the default is not enough either — unlike its drop handler, the paste one
    // never looks at `defaultPrevented`. So every Ctrl+V at a collapsed caret
    // in here also dealt out whatever is in `litegrapheditor_clipboard`, which
    // is localStorage and remembers the last copied nodes across restarts and
    // workflows forever. That is the pile of duplicates found stacked on the
    // node after a session of writing prompts. Stopping here is enough: their
    // listener is on `document` and does not capture.
    event.stopPropagation();
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
    // Out of a branch and back to the sources — the arrow that put you in it,
    // reversed. Only while one is open and only in the `/` menu; everywhere
    // else the left arrow is the caret's, which is what it must stay.
    if (this.menu && this.mode === "/" && this.branch && event.key === "ArrowLeft") {
      event.preventDefault();
      event.stopPropagation();
      this.branch = null;
      this.active = 0;
      this.signature = null;
      this.renderMenu();
      return;
    }
    // The right arrow is the other half of it, on a source row. A leaf row has
    // nothing to go into, so there it stays the caret's.
    if (this.menu && this.mode === "/" && event.key === "ArrowRight"
        && this.flat?.[this.active]?.kind === "branch") {
      event.preventDefault();
      event.stopPropagation();
      this.choose(this.active);
      return;
    }
    if (this.menu && ["ArrowDown", "ArrowUp", "Enter", "Tab", "Escape"].includes(event.key)) {
      event.preventDefault();
      event.stopPropagation();
      if (event.key === "Escape") this.dismissMenu();
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

  /** The "@query" or "/query" immediately before the caret, or null. `mode` is
   *  which of the two it was — everything downstream of here (the menu, the
   *  chip that replaces the typed text) is the same machinery either way. */
  triggerRange() {
    const selection = window.getSelection();
    if (!selection?.rangeCount || !selection.isCollapsed) return null;
    const range = selection.getRangeAt(0);
    const node = range.startContainer;
    if (node.nodeType !== Node.TEXT_NODE || !this.root.contains(node)) return null;
    const text = node.nodeValue.slice(0, range.startOffset);
    let mode = "@";
    let match = TRIGGER.exec(text);
    if (!match) {
      match = COMMAND.exec(text);
      // A slash inside a word is a path or a conjunction, not an opening. The
      // `@` above needs no such guard: nothing in prose writes one mid-word.
      if (match && match.index > 0 && !/\s/.test(text[match.index - 1])) match = null;
      mode = "/";
    }
    if (!match) return null;
    return { node, start: range.startOffset - match[0].length, end: range.startOffset,
             query: match[1], mode };
  }

  /**
   * Where the typed `@query` sits in the *string* `getValue` produces, rather
   * than in the DOM.
   *
   * `insertChip` works off the live selection, which is right for everything
   * that happens in one turn of the event loop — attaching a file from this
   * menu is a synchronous call and the caret is exactly where it was left. It is
   * wrong for anything that has to wait: casting somebody out of the library
   * reads their definition off disk first, and by the time that answers, the box
   * has been rebuilt underneath — `render` calls `refresh`, `refresh` calls
   * `build`, and every text node the caret pointed into is gone. The range then
   * points at a detached node, the chip is inserted into nothing, and what is
   * left on screen is the bare "@" that was typed.
   *
   * So the spot is measured now, as a character offset, and the name is written
   * into the text afterwards. An offset survives a rebuild; a node does not.
   *
   * The walk mirrors `getValue`'s, because it is the same string being counted.
   */
  triggerSpot() {
    const trigger = this.triggerRange();
    if (!trigger) return null;
    let at = 0;
    let found = null;
    const walk = (parent) => {
      for (const node of parent.childNodes) {
        if (found !== null) return;
        if (node === trigger.node) { found = at + trigger.start; return; }
        if (node.nodeType === Node.TEXT_NODE) at += node.nodeValue.length;
        else if (node.dataset?.handle) at += node.dataset.handle.length + 1;
        else if (node.tagName === "BR") at += 1;
        else {
          if (BLOCK.has(node.tagName) && at) at += 1;
          walk(node);
        }
      }
    };
    walk(this.root);
    return found === null ? null : { at: found, length: trigger.end - trigger.start };
  }

  /** Put `@handle ` where `spot` was, in the text. With no spot — the box was
   *  rebuilt out from under the measurement — the name goes on the end, which is
   *  what every other "write their name in for me" in this pack does. */
  writeName(before, spot, handle) {
    const text = spot
      ? `${before.slice(0, spot.at)}@${handle} ${before.slice(spot.at + spot.length)}`
      : `${before}${before && !/\s$/.test(before) ? " " : ""}@${handle} `;
    this.setValue(text);
    this.hooks.onInput(text);
    this.placeCaret((spot ? spot.at : text.length - handle.length - 2) + handle.length + 2);
  }

  /** The caret at a character offset into the box. `setValue` builds a flat
   *  list of text nodes and chips, so one pass over the top level finds it. */
  placeCaret(index) {
    let at = 0;
    for (const node of this.root.childNodes) {
      const length = node.nodeType === Node.TEXT_NODE
        ? node.nodeValue.length
        : node.dataset?.handle ? node.dataset.handle.length + 1 : 1;
      if (node.nodeType === Node.TEXT_NODE && index <= at + length) {
        const range = document.createRange();
        range.setStart(node, Math.max(0, index - at));
        range.collapse(true);
        const selection = window.getSelection();
        selection?.removeAllRanges();
        selection?.addRange(range);
        this.root.focus();
        return;
      }
      at += length;
    }
    focusEnd(this.root);
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
      this.censusChips();
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
    this.censusChips();
    this.hooks.onInput(this.getValue());
  }

  // ---- suggestion menu -----------------------------------------------------

  /**
   * The style catalogue, read once and shared by every box on the page.
   *
   * A sixth of a megabyte of descriptors, so it is not read at boot and not read
   * on `@` — only when a `/` is actually asking about looks. The module cache
   * makes every read after the first free, which is why this can be called from
   * a keystroke.
   */
  async readStyles() {
    if (PromptBox.styles) return PromptBox.styles;
    PromptBox.styles ??= (async () => {
      try {
        const module = await import("./presets/stylelib.js");
        return module.styleRows();
      } catch {
        // The catalogue is vendored, so this is a broken install rather than a
        // network away. The branch draws its door and nothing else, which is
        // what it did before the rows existed.
        return [];
      }
    })();
    const rows = await PromptBox.styles;
    // Kept where every box can read it without awaiting: `commandOptions` runs
    // inside a render, and a render cannot wait for a module.
    PromptBox.loadedStyles = rows;
    if (this.menu) { this.signature = null; this.renderMenu(); }
    return rows;
  }

  /** The looks, if they have arrived. `readStyles` re-renders when they do. */
  styles() {
    return PromptBox.loadedStyles;
  }

  async openMenu(query, mode = "@") {
    this.query = query.toLowerCase();
    // Switching openings is switching menus: the branch you had drilled into
    // belongs to the `/` you have just deleted, and the highlight belongs to a
    // list that no longer exists.
    if (this.mode !== mode) {
      this.mode = mode;
      this.branch = null;
      this.active = 0;
      this.signature = null;
    }
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
    // Two reads, both started at once and each painted as it lands. The roster
    // is a small file in this user's own data and usually cached, so it is
    // waited for first; the input folder is a walk of a directory and can take
    // as long as it takes.
    // The looks, as soon as a slash is asking about them: inside the branch, or
    // against any query at all, since a query searches every source at once.
    if (mode === "/" && (this.branch === "style" || this.query)) this.readStyles();
    const files = listAssets().catch(() => []);
    const roster = this.hooks.castFromLibrary
      ? listPresets().then((rows) => rows.filter((row) => row.scope === "cast"))
          .catch(() => [])
      : Promise.resolve([]);
    this.roster = await roster;
    if (this.menu) this.renderMenu();
    this.library = await files;
    if (this.menu) this.renderMenu();
  }

  /**
   * Close the menu and take the typed "@query" or "/query" with it.
   *
   * Dismissing is the answer "none of these": the trigger was the way to ask,
   * and nothing was cast, so what is left of it is a stray "/" in a sentence
   * that has to queue as prose. The door option has always erased it for the
   * same reason — see `choose`. Only an *explicit* dismissal does this. Editing
   * the trigger away yourself also closes the menu, through `onEdit`, and that
   * path calls `closeMenu` directly: there is nothing left to erase, and the
   * text either side of where it was is yours.
   *
   * The spot is the offset cached each keystroke rather than a live range: on
   * blur the selection has already gone, and a DOM range would not survive
   * `setValue` anyway. Stale offsets are refused by re-reading what sits there.
   */
  dismissMenu(refocus = true) {
    if (!this.menu) return;
    const spot = this.typed;
    this.closeMenu();
    if (!spot) return;
    const text = this.getValue();
    if (text.slice(spot.at, spot.at + spot.length) !== spot.text) return;
    const next = text.slice(0, spot.at) + text.slice(spot.at + spot.length);
    this.setValue(next);
    this.hooks.onInput(next);
    // Not on the blur path: `placeCaret` focuses the box, and pulling focus back
    // out of whatever the click just went to is worse than a lost caret.
    if (refocus) this.placeCaret(spot.at);
  }

  closeMenu() {
    this.menu?.remove();
    this.menu = null;
    this.active = 0;
    this.rows = null;
    this.signature = null;
    this.branch = null;
    this.mode = null;
    this.typed = null;
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

  /**
   * The cast first, then the roster, then attached assets, the piece's pool and
   * the input folder.
   *
   * The cast leads because a subject is what a sentence is usually about, and
   * because citing one is how their files get here at all. The roster is second
   * for the same reason a beat later: typing `@ann` in a piece that has never
   * met Anna is somebody asking for *their*, and the answer is to cast them — with
   * everything behind them — rather than to say the name matches nothing.
   *
   * Somebody already cast here is dropped from the roster half. They are in the
   * list above under the name they actually has, and offering the kept copy
   * beside them would be offering to cast a second Anna.
   */
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

    const here = new Set((this.hooks.getCast?.() ?? []).map((subject) => subject.handle));
    // Out while references are blocked here — a start or end frame is set — for
    // the reason the pool and the input folder are out: casting them attaches
    // their pictures, and a keyframe shot that also carries references is a node
    // that refuses to queue. They are still on the shelf, where the refusal can
    // be explained.
    const roster = this.hooks.attachBlocked("reference") ? [] : (this.roster ?? [])
      .filter((row) => !here.has(row.name))
      .filter((row) => !this.query
        || row.name.toLowerCase().includes(this.query)
        || (row.note ?? "").toLowerCase().includes(this.query))
      .map((row) => ({ kind: "roster", handle: row.name, row }));

    const used = new Set(state.assets.map((a) => a.filename));
    const library = (this.library ?? [])
      .filter((row) => !used.has(row.path))
      .filter((row) => !this.query || row.path.toLowerCase().includes(this.query))
      .slice(0, MAX_SUGGESTIONS)
      .map((row) => ({ kind: "library", path: row.path, mediaKind: row.kind, row }));

    return { cast, roster, attached, pool, library };
  }

  /**
   * What `/` offers: the sources, and then one source's contents.
   *
   * `@` answers "cite something this piece already has". `/` is the question
   * before it — where does a thing come from — which is why it is a layer over
   * the same rows rather than a second menu of its own. Both halves of the
   * cast branch are already here: the roster is what `@` shows when you type a
   * name nobody has cast, and the input folder is what it shows when you type a
   * filename. What `/` adds is being able to ask without knowing the name.
   *
   * Typing filters across every source at once, so `/cla` finds Clara and
   * clay-turntable.png without choosing a branch first — the branches are a
   * lens, not a gate, and picking the wrong one costs nothing.
   *
   * Every branch ends in a chip or in a door. Style is only a door: it is 941
   * stills, chosen by looking at them, and a list of descriptors in a dropdown
   * would be the catalogue with its pictures taken away.
   */
  commandOptions() {
    const groups = [];
    const asked = this.query;
    const branch = this.branch;

    const sources = SOURCES
      .filter((source) => !branch)
      .filter((source) => !asked || source.label.toLowerCase().includes(asked)
        || source.branch.includes(asked))
      .map((source) => ({ kind: "branch", ...source }));
    if (sources.length) groups.push({ head: t("Bring in"), options: sources });

    // Bare `/` is the three sources and nothing else: the question has not been
    // asked yet, and forty filenames under it would answer one nobody put. A
    // query searches every source at once — the branches are a lens, not a gate
    // — and drilling into one narrows to it.
    const wants = (name) => branch === name || (!branch && !!asked);

    if (wants("cast") && this.hooks.castFromLibrary) {
      const here = new Set((this.hooks.getCast?.() ?? []).map((subject) => subject.handle));
      const rows = (this.roster ?? [])
        .filter((row) => !here.has(row.name))
        .filter((row) => !asked || row.name.toLowerCase().includes(asked)
          || (row.note ?? "").toLowerCase().includes(asked))
        .map((row) => ({ kind: "roster", handle: row.name, row }));
      const doors = this.hooks.openLibrary
        ? [{ kind: "door", door: "cast", label: t("Open the cast library"),
             sub: t("build somebody, or edit who is kept") }]
        : [];
      if (rows.length || (branch && doors.length)) {
        groups.push({ head: t("Cast library — cast them with their files"),
                      options: [...rows, ...doors] });
      }
    }

    if (wants("refs")) {
      const used = new Set(this.hooks.getState().assets.map((a) => a.filename));
      const rows = this.hooks.attachBlocked("reference") ? [] : (this.library ?? [])
        .filter((row) => !used.has(row.path))
        .filter((row) => !asked || row.path.toLowerCase().includes(asked))
        .slice(0, MAX_SUGGESTIONS)
        .map((row) => ({ kind: "library", path: row.path, mediaKind: row.kind, row }));
      const blocked = this.hooks.attachBlocked("reference");
      const doors = this.hooks.onBrowse
        ? [{ kind: "door", door: "browse", label: t("Browse files"),
             sub: t("the picker, with previews and trimming") }]
        : [];
      if (rows.length || (branch && doors.length)) {
        groups.push({
          head: blocked ? t("Input folder — unavailable while a start/end frame is set")
                        : t("Input folder"),
          options: [...rows, ...doors],
        });
      }
    }

    if (wants("style") && this.hooks.castStyle) {
      // The whole descriptor is searched, not just the lead: "grindhouse",
      // "needle-felted" and "anamorphic" are all in the middle of one, and the
      // library's own search reads the same field for the same reason.
      const looks = (this.styles() ?? [])
        .filter((row) => !asked
          || row.name.toLowerCase().includes(asked)
          || String(row.note ?? "").toLowerCase().includes(asked)
          || String(row.folder ?? "").toLowerCase().includes(asked))
        .slice(0, MAX_SUGGESTIONS)
        .map((row) => ({ kind: "style", handle: null, row }));
      // The door stays, at the foot of the looks rather than in place of them:
      // a row here is the descriptor and one frame, and choosing between six
      // needle-felted entries is still a thing you do by looking at all of them.
      const doors = this.hooks.openLibrary
        ? [{ kind: "door", door: "style", label: t("Open the style atlas"),
             sub: t("all 941, with every frame each one was cut from") }]
        : [];
      if (looks.length || branch) {
        groups.push({ head: t("Style"), options: [...looks, ...doors] });
      }
    }

    return groups;
  }

  /** The groups the menu is showing, head and rows, in the order they read.
   *  Two shapes over one renderer: `@` cites what is here, `/` says where a
   *  thing comes from — see `options` and `commandOptions`. */
  groups() {
    if (this.mode === "/") return this.commandOptions();
    const { cast, roster, attached, pool, library } = this.options();
    return [
      { head: t("Cast"), options: cast },
      { head: t("Cast library — cast them with their files"), options: roster },
      { head: this.hooks.attachedLabel?.() ?? t("Attached"), options: attached },
      { head: t("Piece references"), options: pool },
      { head: this.hooks.attachBlocked("reference")
          ? t("Input folder — unavailable while a start/end frame is set")
          : t("Input folder"),
        options: library },
    ].filter((group) => group.options.length);
  }

  renderMenu() {
    if (!this.menu) return;
    const groups = this.groups();
    this.flat = groups.flatMap((group) => group.options);
    if (this.active >= this.flat.length) this.active = Math.max(0, this.flat.length - 1);

    // openMenu() renders once immediately and again when the library resolves,
    // and every keystroke re-renders too. Rebuilding identical rows would throw
    // away the highlight and re-fire mouseenter under a stationary pointer, so
    // only rebuild when the list actually differs.
    const signature = this.flat
      .map((option) => `${option.kind}:${
        option.handle ?? option.path ?? option.branch ?? option.door ?? option.row?.id}`)
      .join("\u0000");
    if (this.rows?.length && signature === this.signature) return;
    this.signature = signature;

    this.menu.replaceChildren();
    this.rows = [];
    if (!this.flat.length) {
      this.menu.appendChild(el("div", { class: "mmc-mention-empty", text: t("Nothing matches.") }));
      return;
    }

    // A subject's thumbnail is the first picture they are made of — the point of
    // the row is to recognise them, and their own face does that where a glyph
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
      // A kept member's face is in their index row: it is one of their own
      // pictures, named at the moment they were kept, so the menu draws them
      // without reading a body it does not otherwise need.
      const face = option.kind === "cast" ? faceOf(option.subject)
        : option.kind === "roster" ? option.row.portrait : null;
      // The two `/` rows draw a rail glyph rather than a picture: a source is
      // not a thing with a thumbnail, and a blank tile beside it would read as
      // a file whose preview failed.
      const thumb = option.kind === "branch" || option.kind === "door"
        ? el("span", { class: "mmc-mention-thumb mmc-mention-glyph" },
             [icon(option.iconName ?? "star", 15)])
        // A look's frame is a file this pack ships out of its own web folder —
        // there is no output behind it and no thumb route to resolve it
        // through, so the URL stylelib built is the src.
        : option.kind === "style"
        ? el("img", { class: "mmc-mention-thumb", src: option.row.thumbs?.[0] ?? "", alt: "" })
        : option.mediaKind === "image" || face
        ? el("img", {
            class: "mmc-mention-thumb",
            src: viewUrl(face ?? option.path, { preview: true }), alt: "",
          })
        : el("span", {
            class: "mmc-mention-thumb",
            text: option.kind === "cast" || option.kind === "roster" ? "☺"
              : option.mediaKind === "video" ? "▶" : "♪",
          });

      // Attached assets are known by their handle; a library file is known by
      // its name, and only earns a second line when it lives in a subfolder —
      // repeating the same string twice told the user nothing. A subject's
      // second line is what they are, which is the whole of what the cast knows
      // about them that their name does not say.
      const made = option.kind === "cast"
        ? (option.subject.description
           || [...(option.subject.from ?? []), option.subject.motion, option.subject.voice]
                .filter(Boolean).map((h) => "@" + h).join(", "))
        : null;
      const title = option.kind === "branch" || option.kind === "door"
        ? t(option.label)
        // The lead names the medium — "Claymation", "2D cutout-paper stop-motion
        // animation" — and is what somebody typing "clay" is looking for. The
        // rest of the descriptor is the second line.
        : option.kind === "style" ? option.row.lead
        : option.handle ? `@${option.handle}` : option.path.split("/").pop();
      const subtitle = option.kind === "branch" || option.kind === "door" ? t(option.sub)
        : option.kind === "style" ? (option.row.rest || option.row.folder)
        : option.kind === "cast" ? made
        : option.kind === "roster" ? castFactsLine(option.row.facts)
        : option.handle ? option.path : (option.row?.subfolder || "");

      const item = el("button", {
        class: `mmc-mention-row${option.kind === "branch" ? " mmc-mention-branch" : ""}${
          option.kind === "style" ? " mmc-mention-style" : ""}`,
        "aria-selected": here === this.active,
        title: option.kind === "branch"
          ? t("Show what is in {label}", { label: t(option.label) })
          : option.kind === "style"
          ? t("Cast this look — its frame is attached and its name written here. "
            + "Replaces whatever look the piece already had.")
          : option.kind === "door" ? t(option.sub)
          : option.kind === "roster"
          ? t("Cast @{handle} here — their references are attached as they land.",
              { handle: option.handle })
          : option.kind === "cast" ? `@${option.handle}` : option.path,
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
        // A branch goes deeper; a door leaves. Said with the glyph rather than
        // with words, because the row already has two lines of them.
        ...(option.kind === "branch" ? [el("span", { class: "mmc-mention-more", text: "›" })] : []),
      ]);
      // Keep focus in the box: a blurred contenteditable loses its caret, and
      // without a caret there is nowhere to insert the chip.
      item.addEventListener("pointerdown", (event) => event.preventDefault());
      this.rows.push(item);
      return item;
    };

    // The way back out of a branch, at the top where the thing it undoes is.
    // Left arrow does it too — see `onKeyDown` — but a menu opened with the
    // mouse has to be closable with it.
    if (this.mode === "/" && this.branch) {
      this.menu.appendChild(el("button", {
        class: "mmc-mention-back",
        onmouseenter: () => this.highlight(this.active),
        onclick: (event) => {
          event.preventDefault();
          this.branch = null;
          this.active = 0;
          this.signature = null;
          this.renderMenu();
        },
      }, [el("span", { text: "‹" }), el("span", { text: t("everything") })]));
    }
    for (const group of groups) {
      if (!group.options.length) continue;
      this.menu.appendChild(el("div", { class: "mmc-mention-head", text: group.head }));
      for (const option of group.options) this.menu.appendChild(row(option));
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

  async choose(index) {
    const option = this.flat?.[index];
    if (!option) return;
    // Drilling in, not picking: the typed text stays exactly as it is, because
    // it is still the query — this only narrows what is being searched.
    if (option.kind === "branch") {
      this.branch = option.branch;
      this.active = 0;
      this.signature = null;
      // Entering the Style branch is the other way to ask for the catalogue —
      // `openMenu` only sees the ones that arrive with a query typed after the
      // slash, and drilling in with an empty one is the commoner gesture.
      if (this.branch === "style") this.readStyles();
      this.renderMenu();
      return;
    }
    // A door leaves the box for the window the source really lives in. The
    // typed "/" goes with it: it was the way to ask, and the asking is done.
    if (option.kind === "door") {
      const trigger = this.triggerRange();
      if (trigger) {
        const range = document.createRange();
        range.setStart(trigger.node, trigger.start);
        range.setEnd(trigger.node, trigger.end);
        range.deleteContents();
        this.hooks.onInput(this.getValue());
      }
      this.closeMenu();
      if (option.door === "browse") this.hooks.onBrowse?.();
      else this.hooks.openLibrary?.(option.door);
      return;
    }
    // A look, cast where you asked for it. The same member the library's own
    // "Cast this frame as a look" builds — the frame is cited and the subject
    // lands on the piece — but the name goes where the caret is instead of at
    // the front of the sentence, because here you said where you wanted it.
    //
    // Measured before anything else, for the reason the roster is: casting
    // redraws the body, and the box is rebuilt with it.
    if (option.kind === "style") {
      const spot = this.triggerSpot();
      const before = this.getValue();
      this.closeMenu();
      try {
        const handle = await this.hooks.castStyle(option.row);
        if (handle) this.writeName(before, spot, handle);
      } catch {
        // That style names no frame. The typed "/claymation" is left as it was
        // typed, which is prose and queues as prose.
      }
      return;
    }
    if (option.kind === "roster") {
      // Measured before anything else happens — see `triggerSpot`. Casting them
      // attaches files and redraws the body they were cast into, and the box is
      // rebuilt with it; a caret would not survive that and an offset does.
      const spot = this.triggerSpot();
      const before = this.getValue();
      // The menu goes second: what happens next is a read and a write, and a
      // list still standing over a sentence that is being changed reads as a
      // list that did not take the click.
      this.closeMenu();
      try {
        const body = await loadBody(option.row);
        const member = body?.cast;
        if (!member) return;
        const handle = await this.hooks.castFromLibrary(member);
        if (handle) this.writeName(before, spot, handle);
      } catch {
        // Their body could not be read, or the host refused them. The typed "@ann"
        // is left exactly as it was typed, which is prose and queues as prose —
        // nothing has been half-cast.
      }
      return;
    }
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

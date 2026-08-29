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
import { LANGUAGES, settings as refineSettings } from "./refine.js";
import { tagIndex } from "./state.js";

const TRIGGER = /@([\w-]*)$/;
/* The other opening. `@` cites what is already in this piece; `/` is the layer
   above it — where a thing comes *from*: the style atlas, the cast library, the
   input folder. Only at the start of a word, or "input/clip" and "and/or" would
   summon a menu mid-sentence. */
const COMMAND = /\/([\w-]*)$/;
/* The third opening, and the only one nobody presses a key to summon.
   `@` and `/` are questions you ask; this one answers something already
   written. H3 has two grammars for quoted words and no way to tell them apart
   by shape — §4.4's `<d>` tag is a line somebody says, §4.5's plain double
   quotes are a sign or a subtitle the camera can see — so the closing quote is
   the only honest place to ask which of the two you meant.

   Anchored to the caret and to a *closing* quote, so it fires on words that
   exist rather than on the promise of some. Curly quotes are matched because a
   keyboard may produce them; what is written back is always the straight pair
   the guide spells. */
/* The quote characters are escaped rather than typed. A bare `"` inside a
   character class reads as the start of a string literal to anything that
   scans this file without parsing it — tests/test_family_leaks.py is one —
   and the rest of the line disappears into it. */
const QUOTED = /[\u0022\u201c]([^\u0022\u201c\u201d\n]{1,400})[\u0022\u201d]$/;
const MAX_SUGGESTIONS = 40;

/* A finished spoken line, as `sayText` writes one and `build` reads one back.

   Every piece of it is the guide's: `(S@anna)` is the speaker token
   `subjects.substitute_speakers` resolves to `<Subject 1> (S1)`, the lead-in
   between it and the tag is the identity, action and delivery §4.4 keeps
   *outside* `<d>`, and the tail is the lips-closed sentence a voiceover is
   required to be followed by. */
const SPOKEN = new RegExp(
  "\\(S(@[A-Za-z][A-Za-z0-9_]*(?:\\s*,\\s*@[A-Za-z][A-Za-z0-9_]*)*)\\)"
  + "\\s([^<>\n]{0,60}?)"
  + "<d>\\[([^\\]\n]{1,24})\\]\\s?([^<>\n]*?)</d>"
  + "(\\s*while their lips remain completely closed\\.)?", "g");

/* How a line is delivered: the verb outside the tag, in the guide's own forms.

   `lead` ends in the punctuation §4.4's examples end in — a colon before a
   statement, a comma before one that leans on the clause around it — and
   `together` is what the same verb becomes when a compound `(S1,S2)` says it,
   which is the example the guide gives for two speakers at once.

   Voiceover is the one that is not just a verb. §4.4 fixes both halves of it:
   the exact phrase, and a sentence immediately after the tag saying the lips
   stay shut. Getting that pair right by hand is most of why this menu exists. */
const DELIVERY = [
  { id: "says", lead: "says:", together: "say together:", label: "says" },
  { id: "asks", lead: "asks:", together: "ask together:", label: "asks" },
  { id: "replies", lead: "replies,", together: "reply together,", label: "replies" },
  { id: "whispers", lead: "whispers,", together: "whisper together,", label: "whispers" },
  { id: "shouts", lead: "shouts,", together: "shout together,", label: "shouts" },
  { id: "sings", lead: "sings,", together: "sing together,", label: "sings" },
  { id: "voiceover", lead: "says in an off-screen voiceover:",
    together: "say in an off-screen voiceover:", label: "voiceover",
    tail: " while their lips remain completely closed." },
];
const SAYS = DELIVERY[0];

/* The lead-in somebody has already written in front of their own quote.
 *
 * "@vera is saying" and then the words is how a person actually types this, and
 * the line the menu writes says who is speaking all over again — so without
 * this the result is `<Subject 1> is saying <Subject 1> (S1) says:`. The
 * citation and the verb are the two halves of what the chip is about to write,
 * so where they are already there they are what it replaces.
 *
 * Only a name the cast declares, and only a verb that is one of these. Anything
 * else in front of a quote is a sentence, and a sentence is not this tool's to
 * eat — "@vera looks at the sign reading" keeps every word of itself. */
const VERBS = {
  say: "says", says: "says", saying: "says", said: "says",
  ask: "asks", asks: "asks", asking: "asks", asked: "asks",
  reply: "replies", replies: "replies", replying: "replies", replied: "replies",
  answer: "replies", answers: "replies", answering: "replies", answered: "replies",
  whisper: "whispers", whispers: "whispers", whispering: "whispers", whispered: "whispers",
  shout: "shouts", shouts: "shouts", shouting: "shouts", shouted: "shouts",
  yell: "shouts", yells: "shouts", yelling: "shouts", yelled: "shouts",
  sing: "sings", sings: "sings", singing: "sings", sang: "sings",
};
const LEAD = /@([A-Za-z][A-Za-z0-9_]*)(?:\s+(?:is\s+|are\s+|then\s+)*([a-z]+))?[\s,:]*$/;

/* The quote menu's own row kinds. `branch` is not among them — the `/` menu's
   source rows are branches too, and they are drawn by the chain that has always
   drawn them; a quote-menu branch is told apart by the mode it is in. */
const SAY_ROWS = new Set(["say", "onscreen", "pick", "saycast", "newvoice", "words"]);

/**
 * The line a choice and a set of words come to, in the form §4.4 spells it.
 *
 * Speaker token, then the delivery, then the tag holding only the language and
 * the words — and, for a voiceover, the sentence that has to follow it. The
 * quotes are dropped: inside `<d>` they would be two more characters for the
 * model to read out.
 *
 * A plain function rather than a method, because it is called on the way out:
 * the menu closes before the box is rewritten, and by then there is no choice
 * left on the instance to read.
 */
function sayLine(say, words) {
  const how = DELIVERY.find((d) => d.id === say.delivery) ?? SAYS;
  // `lead` is prose somebody wrote themselves — the guide's own example of one
  // is "exclaims with light annoyance," — carried through an edit untouched.
  // Picking a delivery from the list is what clears it, because that is the
  // gesture that means "use this instead".
  const lead = say.lead || (say.who.length > 1 ? how.together : how.lead);
  return `(S${say.who.map((handle) => "@" + handle).join(",")}) ${lead} `
    + `<d>[${say.language}] ${String(words).trim()}</d>${how.tail ?? ""}`;
}

/** A voice description -> a handle for the member it becomes. `styleHandle`'s
 *  twin, and the same three-word rule: enough of what was typed to recognise
 *  them in the sentence, and nothing that is not a name. */
function voiceHandle(description) {
  const words = String(description ?? "").toLowerCase()
    .replace(/[^a-z0-9\s-]/g, " ")
    .split(/[\s-]+/).filter(Boolean).slice(0, 3);
  const handle = words.join("_") || "voice";
  return (/^[a-z]/.test(handle) ? handle : `voice_${handle}`).slice(0, 32)
    .replace(/_+$/, "") || "voice";
}

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
   * @param {(handles:string[])=>void} [hooks.onCited]  chips that are in the box
   *   now and were not a keystroke ago. The other half of `onUncited`: deleting
   *   a mention mutes the reference, so writing one back has to bring it live
   *   again — see `CreatorEditor.liveCited`.
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
    //
    // Focus landing *inside* the menu is not the box being left: the quote
    // menu's "describe a voice" is a text field, and focusing it blurs the box,
    // so without this exception the field was torn down 120ms after it appeared
    // and there was no way to type a word into it.
    this.root.addEventListener("blur", () => setTimeout(() => {
      if (this.menu?.contains(document.activeElement)) return;
      this.dismissMenu(false);
    }, 120));
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
      // A spoken line first: it is a chip that holds a name, so the cast test
      // below would answer for the name inside it and open somebody instead of
      // the line they are saying.
      const said = event.target?.closest?.("[data-say]");
      if (said && this.root.contains(said)) {
        event.preventDefault();
        this.editSaid(said);
        return;
      }
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
      if (this.castChip(event) || event.target?.closest?.("[data-say]")) event.preventDefault();
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
        } else if (node.dataset?.say !== undefined) {
          // Before the handle branch and before the walk: a spoken line holds
          // names inside it, and descending would come back with the speaker
          // twice and the tag not at all.
          text += node.dataset.say;
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
    const cast = new Set((this.hooks.getCast?.() ?? []).map((s) => s.handle));
    const out = [];
    let at = 0;
    SPOKEN.lastIndex = 0;
    let said;
    while ((said = SPOKEN.exec(text)) !== null) {
      const who = said[1].split(",").map((h) => h.trim().slice(1));
      // A speaker nobody cast is left as the text it is, exactly as an
      // uncited `@name` is: the compiler refuses it by name, and a chip drawn
      // over it would hide the one thing that needs fixing.
      if (!who.every((handle) => cast.has(handle))) continue;
      if (said.index > at) out.push(...this.buildRefs(text.slice(at, said.index)));
      out.push(this.sayChip(said, who));
      at = said.index + said[0].length;
    }
    if (at < text.length) out.push(...this.buildRefs(text.slice(at)));
    return out;
  }

  /**
   * A spoken line, drawn as the one thing it is.
   *
   * Not a `.mmc-ref` pill. A reference chip is a *label* — it stands in for a
   * file, and looking like a token is the whole of its job. A line of dialogue
   * is not a label for anything: it is words that are heard, sitting inside a
   * sentence about what is seen. So it keeps the speaker's tag colour and gives
   * up the pill, and what marks it instead is a rule down its left edge — the
   * same mark `.mmc-compiled-block.mine` already uses in this pack to say "this
   * part of the text is yours". Here it says: this part is heard.
   *
   * Dashed for a voiceover, because that is the difference the mark is for. A
   * voice in the room and a voice over the picture are the same words and a
   * different sound, and a broken line is what that difference looks like.
   *
   * The delivery and the language show only when they are not the ordinary
   * answer. A chip that prints "EN" on every line of an English film has said
   * nothing, and the room it takes is room the words needed.
   */
  sayChip(match, who) {
    const [source, , lead, language, words, tail] = match;
    const said = lead.trim();
    // Prose that is not one of the seven is prose somebody wrote by hand —
    // "exclaims with light annoyance," is the guide's own example of it — so
    // the chip shows what is actually there rather than rounding it to `says`.
    const delivery = DELIVERY.find((d) => said === d.lead || said === d.together);
    const how = delivery ? t(delivery.label) : said.replace(/[:,]\s*$/, "");
    const over = !!tail || delivery?.id === "voiceover";
    return el("span", {
      class: `mmc-say${over ? " mmc-say-over" : ""} mmc-tag-${tagIndex(who[0])}`,
      contenteditable: "false",
      "data-say": source,
      "data-speakers": who.join(","),
      title: t("{who} {how} — {language}", {
        who: who.map((h) => "@" + h).join(", "), how, language }),
    }, [
      el("span", { class: "mmc-say-who", text: who.map((h) => "@" + h).join(" ") }),
      ...(delivery === SAYS ? [] : [el("span", { class: "mmc-say-how", text: how })]),
      ...(language === "English" ? []
        : [el("span", { class: "mmc-say-lang", text: language.slice(0, 2).toUpperCase() })]),
      el("span", { class: "mmc-say-words", text: `“${words}”` }),
    ]);
  }

  /** The half of `build` that was all of it: text -> [text nodes, ref chips]. */
  buildRefs(text) {
    const attached = [...this.hooks.getState().assets,
                      ...(this.hooks.getPool?.() ?? [])];
    const known = new Set(attached.map((a) => a.handle));
    // Muted files, so the chip can say it. A name in the sentence whose picture
    // is out of the run reads as a picture being used, and the row saying
    // otherwise is two floors away from the word that is wrong.
    const off = new Set(attached.filter((a) => a.enabled === false).map((a) => a.handle));
    const cast = new Set((this.hooks.getCast?.() ?? []).map((s) => s.handle));
    const out = [];
    let at = 0;
    const pattern = /@([A-Za-z]+-\d+|[A-Za-z][A-Za-z0-9_]*)/g;
    let match;
    while ((match = pattern.exec(text)) !== null) {
      const handle = match[1];
      if (!known.has(handle) && !cast.has(handle)) continue;
      if (match.index > at) out.push(document.createTextNode(text.slice(at, match.index)));
      out.push(this.chip(handle, cast.has(handle), off.has(handle)));
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

  chip(handle, subject = false, muted = false) {
    return el("span", {
      class: `mmc-ref${subject ? " mmc-ref-cast" : ""}${muted ? " mmc-ref-off" : ""} mmc-tag-${tagIndex(handle)}`,
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
          && got.dataset?.handle === want.dataset?.handle
          && got.dataset?.say === want.dataset?.say;
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
    const seen = [...this.root.querySelectorAll("[data-handle]")]
      .map((node) => node.dataset.handle);
    // The speakers inside a spoken line count as cited, and have to: a line is
    // the *only* place @vera appears once the menu has absorbed the lead-in
    // they were written in, so without this converting a quote read as that
    // name being deleted — their pictures were detached and they were left on
    // the piece standing for nothing. The chip carries the handles separately
    // because its own `data-say` is the source text, which is what `getValue`
    // reads back.
    for (const chip of this.root.querySelectorAll("[data-speakers]")) {
      for (const handle of chip.dataset.speakers.split(",")) seen.push(handle);
    }
    this.chipped = new Set(seen);
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
    // Both directions off the same census, because both are the same gesture:
    // the mention is what puts a picture in the shot, so a chip that reappears
    // — retyped, pasted, undone back into place — is the reference asking to be
    // sent again.
    const back = [...this.chipped].filter((handle) => !before.has(handle));
    if (back.length) this.hooks.onCited?.(back);
    this.syncExcerpt();
    this.reportOverflow();
    const trigger = this.triggerRange();
    if (trigger) {
      // Measured every keystroke, because dismissal has to erase it and by then
      // there may be no live selection to measure from — see `dismissMenu`.
      const spot = this.triggerSpot();
      // `typed` is what an explicit dismissal erases. A `@` or a `/` is a key
      // pressed to summon a list, so taking it back with the list is right; a
      // quote is the words themselves, and eating those would be answering
      // "none of these" by deleting the sentence.
      this.typed = trigger.mode === '"' ? null
        : spot && { ...spot, text: trigger.mode + trigger.query };
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
    if (this.menu && this.mode !== "@" && this.branch && event.key === "ArrowLeft") {
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
    // Who says it is the one dial worth a key of its own: it is the only one
    // with no sensible default in a piece that has no cast, and the only one
    // anybody changes line to line.
    if (this.menu && this.mode === '"' && !this.branch && event.key === "ArrowRight"
        && this.flat?.[this.active]?.kind === "say") {
      event.preventDefault();
      event.stopPropagation();
      this.branch = "speaker";
      this.active = 0;
      this.signature = null;
      this.renderMenu();
      return;
    }
    if (this.menu && this.mode !== "@" && event.key === "ArrowRight"
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
    if (!match) {
      match = QUOTED.exec(text);
      mode = '"';
    }
    if (!match) return null;
    return { node, start: range.startOffset - match[0].length, end: range.startOffset,
             query: match[1], mode };
  }

  /**
   * The `@name` — and the speech verb after it, if there is one — that the text
   * before a quote already ends with. Null where there is none.
   *
   * A name only, because a name is the only thing here that means something:
   * `@vera` is a citation because somebody declared Vera, and the same promise
   * that keeps prose from being reinterpreted keeps this from reaching into a
   * sentence it was not invited into. A bare pronoun and a verb is not enough
   * to act on — it says how, but the whole question is who.
   */
  leadIn(before) {
    const match = LEAD.exec(before);
    if (!match) return null;
    const cast = new Set((this.hooks.getCast?.() ?? []).map((subject) => subject.handle));
    if (!cast.has(match[1])) return null;
    // A word after the name that is not one of the verbs is a sentence carrying
    // on, and the name in it is being used for something else.
    if (match[2] && !VERBS[match[2]]) return null;
    return { start: match.index, who: match[1], delivery: match[2] ? VERBS[match[2]] : null };
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
        else if (node.dataset?.say !== undefined) at += node.dataset.say.length;
        else if (node.dataset?.handle) at += node.dataset.handle.length + 1;
        else if (node.tagName === "BR") at += 1;
        else {
          if (BLOCK.has(node.tagName) && at) at += 1;
          walk(node);
        }
      }
    };
    walk(this.root);
    if (found === null) return null;
    let spot = found;
    let length = trigger.end - trigger.start;
    // A quote reaches back over the lead-in somebody already wrote in front of
    // it, because that is what the line is about to say again. Measured here
    // and not in `triggerRange`: `@vera` in front of a quote is a *chip*, so
    // the text node the caret is in does not contain it, and the only place the
    // sentence exists whole is the string this is already counting in.
    if (trigger.mode === '"') {
      const lead = this.leadIn(this.getValue().slice(0, spot));
      if (lead) {
        length += spot - lead.start;
        return { at: lead.start, length, lead };
      }
    }
    return { at: spot, length };
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
        : node.dataset?.say !== undefined ? node.dataset.say.length
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
      this.say = null;
    }
    if (mode === '"') {
      // The words are the trigger, so editing them inside the quotes is
      // editing what the line will say — read every keystroke. The choices
      // around them are read once and then kept, because they are answers.
      this.said = query;
      this.say ??= this.defaultSay(this.triggerSpot()?.lead);
    }
    if (!this.menu) {
      this.menu = el("div", { class: "mmc-mention" });
      // Above whatever is open: the same prompt box is the node's body and a
      // timeline segment's editor, and in the second case it is inside a modal.
      floatAbove(this.menu);
      document.body.appendChild(this.menu);
      this.active = 0;
      this.watchAway();
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
    // Nothing in the quote menu is a file. The roster below still is — casting
    // somebody is how a line gets a speaker in a piece that has none.
    const files = mode === '"' ? Promise.resolve(this.library ?? [])
      : listAssets().catch(() => []);
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

  /**
   * A press anywhere else is "not this", and Escape is the same answer typed.
   *
   * The `blur` path in the constructor only fires while the box has focus, and
   * a menu reopened on a written line never gives it any — the chip is
   * `contenteditable="false"` and its press is cancelled, on purpose, so that
   * pressing a line does not select it. That left the menu with no way out
   * except answering it, which is the one thing a menu must not be.
   *
   * A press in the sentence closes it too, but without taking anything with it.
   * The two are different answers: leaving the box is "never mind", and the
   * half-typed `@an` that was the way to ask goes with the asking — which is
   * what blurring has always done. Clicking somewhere else in the same sentence
   * is not leaving, it is writing; the caret is going where you put it and the
   * words you typed are still yours.
   *
   * `onEdit` cannot be the one to notice: it runs on input, and a click is not
   * input, so a menu left standing over a caret three words away had no way to
   * find out it had been abandoned.
   */
  watchAway() {
    this.away = (event) => {
      if (this.menu?.contains(event.target)) return;
      if (this.root.contains(event.target)) this.closeMenu();
      else this.dismissMenu(false);
    };
    this.awayKey = (event) => {
      if (event.key !== "Escape" || !this.menu) return;
      // A field in the menu answers its own Escape and knows not to write what
      // is in it. Closing over its head would leave that to the blur.
      if (this.menu.querySelector("input")) return;
      event.stopPropagation();
      this.dismissMenu(false);
    };
    // Deferred, or the press that opened the menu closes it again.
    setTimeout(() => {
      if (!this.menu) return;
      document.addEventListener("pointerdown", this.away, true);
      document.addEventListener("keydown", this.awayKey, true);
    }, 0);
  }

  closeMenu() {
    if (this.away) {
      document.removeEventListener("pointerdown", this.away, true);
      document.removeEventListener("keydown", this.awayKey, true);
      this.away = null;
      this.awayKey = null;
    }
    this.menu?.remove();
    this.menu = null;
    this.active = 0;
    this.rows = null;
    this.signature = null;
    this.branch = null;
    this.mode = null;
    this.typed = null;
    this.say = null;
    this.said = "";
    this.editing = null;
    this.anchor = null;
    this.asking = false;
  }

  place() {
    if (!this.menu) return;
    const selection = window.getSelection();
    // Editing a written line has no caret to measure from — the chip it is
    // about is the anchor, and it is where the eye already is.
    const rect = this.anchor ?? (selection?.rangeCount
      ? selection.getRangeAt(0).getBoundingClientRect() : null);
    if (!rect) return;
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

  // ---- the quote menu ------------------------------------------------------

  /**
   * What a quote defaults to: the first person in the cast, saying it plainly,
   * in whatever language the piece is being written in.
   *
   * The first person rather than none, because a piece with one member in it
   * has already answered the question, and a menu that asks it again is a menu
   * you have to dismiss. Where nobody is cast there is no answer to guess, and
   * the Spoken row says so instead of pretending.
   *
   * The language follows the refiner's setting — that is where this piece
   * already said which language it is written in, and asking twice would let
   * the two disagree.
   */
  defaultSay(lead = null) {
    const cast = (this.hooks.getCast?.() ?? []).filter((subject) => subject.handle);
    return {
      // What the sentence already says, where it says it. Anybody who wrote
      // "@vera is saying" has answered both of these questions once, and being
      // asked them again is the menu not having read what it is standing over.
      who: lead ? [lead.who] : cast.length ? [cast[0].handle] : [],
      language: refineSettings().language || "English",
      delivery: lead?.delivery ?? SAYS.id,
    };
  }

  /** The chosen delivery, as an entry of `DELIVERY`. */
  sayHow() {
    return DELIVERY.find((d) => d.id === this.say?.delivery) ?? SAYS;
  }

  /**
   * The two things quoted words can be, and the three dials behind the first.
   *
   * Both rows are the guide's, which is the whole reason the second one exists:
   * §4.5 reserves plain double quotes for text the camera can actually see — a
   * sign, a banner, a subtitle — so a menu that silently turned every quote
   * into speech would be overwriting one grammar with the other. On screen is
   * therefore a real answer and not a way out, and choosing it writes nothing,
   * because the quotes already are the syntax.
   */
  sayOptions() {
    const say = this.say;
    if (this.branch === "speaker") return this.speakerOptions();
    if (this.branch === "language") {
      // No glyph and no second line. Eleven identical globes over eleven words
      // that already say what they are is decoration, and the tag each one
      // writes is the word itself: `<d>[French] …`.
      return [{ head: t("The language these words are in"), options: LANGUAGES.map((name) => ({
        kind: "pick", pick: { language: name }, label: t(name),
        on: name === say.language,
      })) }];
    }
    if (this.branch === "delivery") {
      // A second line only where there is something the first does not say.
      // `says` under "says" is a row telling you twice and teaching you nothing;
      // the two that differ from their own label are the two worth the space.
      const plural = say.who.length > 1;
      // A lead-in this menu did not write is the one in force, so it is in the
      // list — at the top, marked, and left exactly as it was typed. Leaving it
      // out would have made the list say the line is delivered some way it is
      // not, and picking anything would have thrown the words away silently.
      const own = say.lead
        ? [{ kind: "pick", pick: { lead: say.lead }, label: say.lead.replace(/[:,]\s*$/, ""),
             on: true, sub: t("as you wrote it") }]
        : [];
      return [{ head: t("How the line is delivered"), options: own.concat(DELIVERY.map((how) => ({
        kind: "pick", pick: { delivery: how.id, lead: null }, label: t(how.label),
        on: !say.lead && how.id === say.delivery,
        sub: how.id === "voiceover"
          ? t("off-screen, and the lips stay closed — both halves are written for you")
          : plural ? how.together : "",
      }))) }];
    }
    const named = say.who.map((handle) => "@" + handle).join(" and ");
    // Only over a line that is already written. While a quote is being typed
    // the words are still in the box under the caret, and a field standing in
    // front of them would be a second place to type the same thing.
    const line = this.editing
      ? [{ head: t("The line"), options: [
          { kind: "words", iconName: "pen", label: `“${this.said}”`,
            sub: t("change what is said") },
        ] }]
      : [];
    return line.concat([{ head: t("What these words are"), options: [
      { kind: "say", iconName: "speech",
        label: say.who.length ? t("Spoken by {who}", { who: named }) : t("Spoken"),
        sub: say.who.length
          ? this.sayHow().tail
            ? t("an off-screen voiceover, in {language}", { language: say.language })
            : t("{how}, in {language}", { how: t(this.sayHow().label), language: say.language })
          : t("nobody is cast here yet — pick who says it") },
      { kind: "onscreen", iconName: "placard", label: t("Written in the picture"),
        // Over a written line the row is not a statement about syntax any
        // more, it is an undo: it takes the line out of the audio and leaves
        // the words on screen, which is the other thing §4.5 says quotes are.
        sub: this.editing
          ? t("take it out of the audio and leave the words on screen")
          : t("a sign, a banner, a subtitle — the quotes are already the syntax") },
    ] }]);
  }

  /**
   * Who says it: the cast first, then the library, then somebody new.
   *
   * The same three sources the `@` menu offers, for the same reason and in the
   * same order — but a speaker is not a citation, so picking one sets the line
   * rather than writing a name into the sentence. The last row is the one this
   * menu needs that no other does: a voice can be somebody the piece has never
   * seen, and §4.4 asks for their age, timbre and pace anyway, so describing
   * them *is* casting them. They land as a member with no files, which is a
   * subject the compiler has always been able to define.
   */
  speakerOptions() {
    const say = this.say;
    const cast = (this.hooks.getCast?.() ?? []).filter((subject) => subject.handle)
      .map((subject) => ({
        kind: "pick", pick: { who: [subject.handle] }, subject,
        label: `@${subject.handle}`, on: say.who.includes(subject.handle),
        sub: subject.description || t("in the cast"),
      }));
    // Everybody at once is one compound `(S1,S2)`, which is 4.4's own form for
    // a line two people say together. Only worth offering once there are two.
    const together = cast.length > 1 && say.who.length === 1
      ? [{ kind: "pick", pick: { who: cast.map((row) => row.subject.handle) }, iconName: "speech",
           label: t("All of them, together"),
           sub: t("one compound ID over every name — (S1,S2)") }]
      : [];
    const here = new Set((this.hooks.getCast?.() ?? []).map((subject) => subject.handle));
    const roster = !this.hooks.castFromLibrary ? [] : (this.roster ?? [])
      .filter((row) => !here.has(row.name))
      .slice(0, MAX_SUGGESTIONS)
      .map((row) => ({ kind: "saycast", row, label: `@${row.name}`,
                       sub: castFactsLine(row.facts) }));
    const groups = [];
    if (cast.length || together.length) {
      groups.push({ head: t("In this piece"), options: [...cast, ...together] });
    }
    if (roster.length) groups.push({ head: t("Cast library"), options: roster });
    groups.push({ head: t("Somebody new"), options: [
      { kind: "newvoice", iconName: "face", label: t("Describe a voice"),
        sub: t("age, timbre, pace — they join the cast with no files") },
    ] });
    return groups;
  }

  /**
   * The groups the menu is showing, head and rows, in the order they read.
   *
   * Two shapes over one renderer: `@` cites what is here, `/` says where a
   * thing comes from — see `options` and `commandOptions`.
   *
   * **What is attached comes first.** The cast used to, on the argument that a
   * person is the more important citation — but that is an argument about the
   * prompt rather than about the moment `@` is typed. What somebody has just
   * dropped on this card is the thing they are reaching for, and it was under a
   * list of everybody in the piece; the cast is second because citing somebody
   * is the next most common thing, and the two libraries and the pool are the
   * cases where you are going to type a few letters anyway.
   */
  groups() {
    if (this.mode === '"') return this.sayOptions();
    if (this.mode === "/") return this.commandOptions();
    const { cast, roster, attached, pool, library } = this.options();
    return [
      { head: this.hooks.attachedLabel?.() ?? t("Attached"), options: attached },
      { head: t("Cast"), options: cast },
      { head: t("Cast library — cast them with their files"), options: roster },
      { head: t("Piece references"), options: pool },
      { head: this.hooks.attachBlocked("reference")
          ? t("Input folder — unavailable while a start/end frame is set")
          : t("Input folder"),
        options: library },
    ].filter((group) => group.options.length);
  }

  renderMenu() {
    if (!this.menu) return;
    // The menu has become a field and is no longer a list. `openMenu` renders
    // once immediately and again as the roster and the input folder land, so
    // without this a field opened before those answered was replaced by rows
    // mid-sentence — and what had been typed into it went with them.
    if (this.asking) return;
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
      // The quote menu's rows answer a different question from every other row
      // in here — they are choices, not results — so they are drawn by their
      // own hand rather than by six more branches of the chain below.
      if (SAY_ROWS.has(option.kind)) return this.sayRow(option, here);
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
    if (this.mode !== "@" && this.branch) {
      this.menu.appendChild(el("button", {
        class: "mmc-mention-back",
        onmouseenter: () => this.highlight(this.active),
        // As above, and this one has always needed it: the way back out of a
        // `/` branch could only ever be taken with the left arrow, because
        // pressing it blurred the box and dismissed the menu under the press.
        onpointerdown: (event) => event.preventDefault(),
        onclick: (event) => {
          event.preventDefault();
          this.branch = null;
          this.active = 0;
          this.signature = null;
          this.renderMenu();
        },
      }, [el("span", { text: "‹" }),
          el("span", { text: this.mode === '"' ? t("back to the line") : t("everything") })]));
    }
    for (const group of groups) {
      if (!group.options.length) continue;
      this.menu.appendChild(el("div", { class: "mmc-mention-head", text: group.head }));
      for (const option of group.options) this.menu.appendChild(row(option));
    }
    if (this.mode === '"' && !this.branch) this.menu.appendChild(this.sayBar());
    this.place();
  }

  /**
   * One row of the quote menu: a glyph, a name, and what it means.
   *
   * The same skeleton every other row in this menu has — that is the point, it
   * is one menu — with one thing added that no other row needs. A choice can
   * already be the one in force, and saying so is the difference between a list
   * of options and a list of settings: `on` draws the mark, so drilling in to
   * change the language shows which language you are changing it from.
   */
  sayRow(option, here) {
    const face = option.subject && this.subjectFace(option.subject);
    const item = el("button", {
      class: `mmc-mention-row mmc-say-row${option.kind === "branch" ? " mmc-mention-branch" : ""}${
        !face && !option.iconName && !option.subject && !option.row ? " mmc-say-bare" : ""}`,
      "aria-selected": here === this.active,
      "aria-checked": option.on === undefined ? undefined : !!option.on,
      onmouseenter: () => this.highlight(here),
      onclick: (event) => { event.preventDefault(); this.choose(here); },
    }, [
      // No tile where there is nothing to put in it. A list of eleven languages
      // is a list of words, and a column of placeholders beside them would be
      // saying that each one is a thing with a picture.
      face
        ? el("img", { class: "mmc-mention-thumb", src: viewUrl(face, { preview: true }), alt: "" })
        : option.iconName
        ? el("span", { class: "mmc-mention-thumb mmc-mention-glyph" }, [icon(option.iconName, 15)])
        : option.subject || option.row
        ? el("span", { class: "mmc-mention-thumb", text: "☺" })
        : option.kind === "pick" ? null
        : el("span", { class: "mmc-mention-thumb", text: "☺" }),
      el("span", { class: "mmc-mention-text" }, [
        el("span", {
          class: `mmc-mention-handle${
            option.label?.startsWith("@") ? ` mmc-tag-${tagIndex(option.label.slice(1))}` : ""}`,
          text: option.label,
        }),
        ...(option.sub ? [el("span", { class: "mmc-mention-sub", text: option.sub })] : []),
      ]),
      ...(option.kind === "branch" ? [el("span", { class: "mmc-mention-more", text: "›" })] : []),
    ]);
    item.addEventListener("pointerdown", (event) => event.preventDefault());
    this.rows.push(item);
    return item;
  }

  /** A cast member's own first picture, for the row that offers them. */
  subjectFace(subject) {
    const pool = [...(this.hooks.getPool?.() ?? []), ...(this.hooks.getState().assets ?? [])];
    for (const handle of subject.from ?? []) {
      const asset = pool.find((a) => a.handle === handle);
      if (asset?.kind === "image") return asset.filename;
    }
    return null;
  }

  /**
   * The three dials, under the two answers, showing what Enter would write.
   *
   * Not rows. Rows are things you choose between, and these are not
   * alternatives to Spoken — they are what Spoken currently means, which makes
   * them a readout that happens to be pressable. Keeping them off the arrow
   * keys is what leaves Enter as the whole gesture in the ordinary case: one
   * cast member, saying it plainly, in the language the piece is written in.
   */
  sayBar() {
    const say = this.say;
    const dial = (branch, text, wide = false) => el("button", {
      class: `mmc-say-dial${wide ? " wide" : ""}`,
      title: t("Change this"),
      onmouseenter: () => this.highlight(this.active),
      // The same guard every row in this menu carries, and for a harder reason
      // than the caret: leaving the box blurs it, and a blurred box dismisses
      // the menu (see the `blur` listener in the constructor). Without this the
      // press tears the menu down 120ms before the click would have landed on
      // it, and pressing any of these three does nothing at all.
      onpointerdown: (event) => event.preventDefault(),
      onclick: (event) => {
        event.preventDefault();
        this.branch = branch;
        this.active = 0;
        this.signature = null;
        this.renderMenu();
      },
    }, [el("span", { text })]);
    const named = say.who.map((handle) => "@" + handle).join(" ");
    return el("div", { class: "mmc-say-bar" }, [
      dial("speaker", named || t("nobody yet"), true),
      dial("language", say.language),
      dial("delivery", t(this.sayHow().label)),
      el("span", { class: "mmc-say-more", text: "›" }),
    ]);
  }

  /**
   * Reopen the quote menu on a line that is already written.
   *
   * The chip is `contenteditable="false"`, so a click on it had nowhere to put
   * a caret and did nothing — the same free gesture a cast chip took, and the
   * right one for the same reason: the line in the sentence is where the
   * choices *are*, so it is the shortest way to change one. Without it a
   * finished line could only be changed by deleting it whole and typing the
   * quote again.
   *
   * Everything the menu needs comes back out of the text the chip stands for,
   * because that text is the only thing that was ever stored.
   */
  editSaid(chip) {
    SPOKEN.lastIndex = 0;
    const match = SPOKEN.exec(chip.dataset.say);
    if (!match) return;
    // Whatever was open belongs to a different question. Closed first, and the
    // mode set by hand afterwards, because `openMenu` clears the choice on a
    // change of mode — which is right when a quote is being typed and wrong
    // here, where the choice is the thing being carried in.
    this.closeMenu();
    const [, names, lead, language, words] = match;
    const said = lead.trim();
    const known = DELIVERY.find((d) => said === d.lead || said === d.together);
    this.say = {
      who: names.split(",").map((handle) => handle.trim().slice(1)),
      language,
      delivery: known?.id ?? SAYS.id,
      // Kept verbatim where this menu did not write it — see `sayLine`.
      lead: known ? null : said,
    };
    // Where the chip sits in the text, so choosing rewrites it in place rather
    // than adding a second line beside it.
    let at = 0;
    for (const node of this.root.childNodes) {
      if (node === chip) {
        this.editing = { at, length: chip.dataset.say.length };
        break;
      }
      at += node.nodeType === Node.TEXT_NODE ? node.nodeValue.length
        : node.dataset?.say !== undefined ? node.dataset.say.length
        : node.dataset?.handle ? node.dataset.handle.length + 1 : 1;
    }
    if (!this.editing) return;
    // The menu opens over the line rather than over the caret: there is no
    // caret, and the line is what is being changed.
    this.anchor = chip.getBoundingClientRect?.() ?? null;
    this.mode = '"';
    this.branch = null;
    this.active = 0;
    this.signature = null;
    this.openMenu(words, '"');
  }

  /**
   * Where a chosen line goes: the quote that summoned the menu, or the line
   * being edited. One answer, because every path that writes needs the same
   * one and the two are the same kind of thing — a span of text to replace.
   */
  sayTarget() {
    return this.editing ?? this.triggerSpot();
  }

  /**
   * Put a finished line where the quote was.
   *
   * Through the text and an offset rather than through the live selection, for
   * the reason `writeName` is: casting somebody reads a body off disk and
   * redraws the box, and by the time that answers the node the caret pointed
   * into is gone.
   */
  writeSaid(before, spot, line) {
    const text = spot
      ? `${before.slice(0, spot.at)}${line}${before.slice(spot.at + spot.length)}`
      : `${before}${before && !/\s$/.test(before) ? " " : ""}${line}`;
    this.setValue(text);
    this.hooks.onInput(text);
    this.placeCaret((spot ? spot.at : text.length - line.length) + line.length);
  }

  /**
   * Describe a voice, and be describing somebody: the menu becomes one field.
   *
   * §4.4 asks for the age, timbre, pace or accent of a speaker the first time
   * they are heard, so the words that answer "who is this" are the same words
   * the cast wants as a description. They land as a member with no files — a
   * subject the compiler has always been able to define, and the only shape a
   * voice with no picture could have.
   */
  askVoice() {
    // Held now, because casting closes this menu and the choice goes with it.
    const before = this.getValue();
    const spot = this.sayTarget();
    const say = this.say;
    const said = this.said;
    this.ask({
      head: t("Who is speaking"),
      placeholder: t("a young woman, quiet and breathy"),
      hint: t("They join the cast with no files, and the line is written to them."),
      done: (description) => {
        const handle = this.hooks.castVoice?.({ takes: "person", description,
                                                handle: voiceHandle(description) });
        if (!handle) return;
        this.writeSaid(before, spot, sayLine({ ...say, who: [handle] }, said));
      },
    });
  }

  /**
   * The words themselves, in a field, with the line rewritten around them.
   *
   * The chip is `contenteditable="false"` — it has to be, or a caret inside it
   * would be a caret inside `<d>[English]` — so the one thing the sentence
   * cannot do is let you fix a typo in what somebody says. This is that, and it
   * is why the row exists at the top of the menu rather than as a fourth dial:
   * the words are not a setting, they are the line.
   */
  askWords() {
    const before = this.getValue();
    const spot = this.sayTarget();
    const say = this.say;
    this.ask({
      head: t("What is said"),
      value: this.said,
      hint: t("Only the words. Who says them, and how, stay as they are."),
      done: (words) => this.writeSaid(before, spot, sayLine(say, words)),
    });
  }

  /**
   * The menu, become the one field that asks a question it cannot answer with
   * a list. Everything else in it is gone: there is no list any more.
   *
   * `done` is called with the trimmed text and never with nothing — a field
   * left empty is a question not answered, and answering it with an empty line
   * would write `<d>[English] </d>` into the prompt.
   */
  ask({ head, hint, value = "", placeholder = "", done }) {
    if (!this.menu) return;
    this.asking = true;
    const field = el("input", {
      class: "mmc-say-field", type: "text", spellcheck: "false", placeholder,
    });
    field.value = value;
    let closed = false;
    const finish = () => {
      if (closed) return;
      closed = true;
      const text = field.value.trim();
      this.closeMenu();
      if (text) done(text);
    };
    this.menu.replaceChildren(
      el("div", { class: "mmc-mention-head", text: head }),
      el("div", { class: "mmc-say-ask" }, [
        field,
        el("div", { class: "mmc-mention-sub", text: hint }),
      ]));
    this.rows = [];
    this.flat = [];
    field.addEventListener("keydown", (event) => {
      event.stopPropagation();
      if (event.key === "Enter") { event.preventDefault(); finish(); }
      // Escape is "leave it as it was", so it closes without writing.
      if (event.key === "Escape") { event.preventDefault(); closed = true; this.closeMenu(); }
    });
    field.addEventListener("blur", finish);
    field.focus();
    // Selected, so the first keystroke replaces a line you came here to redo
    // rather than appending to it. The caret is one arrow key away.
    field.select?.();
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
    // On screen writes nothing, and that is the answer rather than a way out of
    // one: §4.5's syntax for a sign, a banner or a subtitle is plain double
    // quotes, so the words are already in the form the model reads. The row
    // exists to say so — otherwise the only way to learn it is to wonder why
    // the quote did not become speech.
    if (option.kind === "onscreen") {
      // Over a written line it is an undo, and has to write: the words go back
      // to being a plain quoted string, which is what §4.5 asks for and what
      // they were before the menu wrapped them. Under a quote being typed
      // there is nothing to write — they are already in that form.
      if (this.editing) {
        const before = this.getValue();
        const spot = this.editing;
        const words = this.said;
        this.closeMenu();
        this.writeSaid(before, spot, `"${words}"`);
        return;
      }
      this.closeMenu();
      this.root.focus();
      return;
    }
    if (option.kind === "words") {
      this.askWords();
      return;
    }
    if (option.kind === "newvoice") {
      this.askVoice();
      return;
    }
    // A dial, answered. The branch closes behind it: it was opened to ask one
    // question, and it has been answered.
    if (option.kind === "pick") {
      this.say = { ...this.say, ...option.pick };
      this.branch = null;
      this.active = 0;
      this.signature = null;
      this.renderMenu();
      return;
    }
    // Somebody off the shelf, cast so they can speak. Their files come with
    // them, as they do everywhere else casting happens — the difference is only
    // that their name goes into the line rather than into the sentence.
    if (option.kind === "saycast") {
      const spot = this.sayTarget();
      const before = this.getValue();
      const say = this.say;
      const said = this.said;
      this.closeMenu();
      try {
        const body = await loadBody(option.row);
        const member = body?.cast;
        if (!member) return;
        const handle = await this.hooks.castFromLibrary(member);
        if (handle) this.writeSaid(before, spot, sayLine({ ...say, who: [handle] }, said));
      } catch {
        // Their body could not be read. The quoted words are left exactly as
        // they were typed, which is prose and queues as prose.
      }
      return;
    }
    if (option.kind === "say") {
      // Nobody to say it. The question the row could not answer is the branch
      // behind it, so pressing it opens that instead of writing a line with an
      // empty speaker token in it.
      if (!this.say.who.length) {
        this.branch = "speaker";
        this.active = 0;
        this.signature = null;
        this.renderMenu();
        return;
      }
      const spot = this.sayTarget();
      const before = this.getValue();
      const line = sayLine(this.say, this.said);
      this.closeMenu();
      this.writeSaid(before, spot, line);
      return;
    }
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

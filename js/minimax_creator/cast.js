// The cast: who is in the piece, as against which files are attached to it.
//
// H3's reference guide separates the two. `<Picture N>` is a file the tokenizer
// is shown; `<Subject N>` is reusable visible content the target video contains,
// and section 2.2 says outright that an image used only to define a character
// gets no picture entry of its own. So a person is not a picture: they are
// declared here, cited in prose by name, and `@anna` becomes `<Subject 1>` at
// queue time exactly as `@ref-1` becomes `<Picture 1>`.
//
// One shelf, mounted twice — on the node's own face and in the Timeline window —
// because there is one node and a cast belongs to the piece either way. What
// differs between the two is only what the host hands it: which files are
// available to build somebody out of, and where a citation of them can be
// counted.
//
// ---- what the redesign is for ------------------------------------------------
//
// The first version of this shelf was two lines of look-alike ghost chips, and
// the one gesture the whole feature exists for — hang a reference on a person —
// was a bare "+" between them that nobody found. It also refused to open at all
// until a reference had been attached, which put the feature out of reach of
// exactly the generation that most needs it: a text-only one, where a name is
// the only thing keeping the same person in shot 1 and shot 9.
//
// So the references are the card now. Each one is a real thumbnail wearing its
// own identity hue, with a badge saying what that file lends them — their looks,
// their movement, their voice, or the place they take. One tile, one menu, four
// answers, and the "+" beside them is a tile of the same size rather than a
// character in a row of text.
//
// The card wears their hue on its left edge, and it is the same hue `@anna` wears
// as a chip in the sentence — the pack's existing "this chip is that picture"
// device, pointed at a person instead of a file.
//
// ---- and what the second pass is for -----------------------------------------
//
// That card is the right card for the person you are working on and the wrong
// one for the other five. A cast of six drew six of them, every field of every
// one, and the shelf became several screens of boxes you scroll past — on a node
// face that is 300px of scrollport holding one and a half people.
//
// So a member is a *line* until you open them: face, name, what they are made of,
// and where they walk on, which is the whole of what you check a cast for. One
// is open at a time, because editing somebody is something you do to one person,
// and the open one is the card that was always here.
//
// The other half of the same problem is that everybody was built from scratch,
// every time, on every node. Somebody worth casting is worth keeping — so the
// star on their open card writes them into the cast library, filenames rather than
// handles, and *From the library* on the shelf head brings them back into a piece
// that never had their pictures attached. Both directions are the host's to
// perform (`keep` and `library` below): a shelf does not know where a roster
// lives, and there are two hosts.

import { viewUrl } from "./api.js";
import { dismissable, el, icon, placeNear } from "./dom.js";
import { t } from "./i18n.js";
import * as S from "./state.js";

/** The four things a file can lend a subject, and what tells them apart on
 *  sight. `from` takes several files; the other three take one each, which is
 *  why picking one of them off a tile moves the handle rather than adding it. */
const ROLES = [
  {
    key: "from", glyph: "face", label: "looks",
    lead: "Their looks come from this",
    note: "Face, build and clothing are taken from it; its background, light and "
        + "pose are not. Several pictures of the same person are one subject.",
    fits: (asset) => asset.kind !== "audio" && asset.track !== "sound",
  },
  {
    key: "motion", glyph: "play", label: "moves",
    lead: "They move like this",
    note: "Their movement is taken from the clip and their appearance stays their "
        + "pictures'. This is how a face from a still walks like somebody in a clip.",
    fits: (asset) => asset.kind === "video" && asset.track !== "sound",
  },
  {
    key: "voice", glyph: "audio", label: "voice",
    lead: "This is their voice",
    note: "Bound as their voice-timbre reference — its words and background sound "
        + "are not copied. They take a speaker ID in cast order.",
    fits: (asset) => asset.kind === "audio" || asset.track === "sound",
  },
  {
    key: "replaces", glyph: "swap", label: "their place",
    lead: "They take somebody's place in this",
    note: "The clip's framing, camera work and action are kept and its occupant "
        + "is replaced by them — the whole of “swap this person for that one”.",
    fits: (asset) => asset.kind === "video" && asset.track !== "sound",
  },
];

const ROLE = Object.fromEntries(ROLES.map((role) => [role.key, role]));

/** What stands in for a face where no picture can supply one. Follows `takes`,
 *  because a person glyph over a described loft says the wrong thing. */
const BLANK_FACE = { person: "face", object: "weights", scene: "image", style: "effect" };

/** What each `takes` word means, in the words somebody casting would use. The
 *  four values themselves are `subjects.TAKES` and are shown as they are — the
 *  same four an asset's own chip wears, so the two rows agree — and this is the
 *  line under them in the menu. */
const TAKES_NOTE = {
  person: "Keeps the likeness — face, hair, build, clothing — and drops the "
        + "picture's background, palette, pose and action.",
  object: "Keeps the thing itself and drops the surroundings, lighting and "
        + "arrangement it was photographed in.",
  scene: "Keeps the place, its surfaces and its light, and drops whoever was "
       + "standing in it.",
  style: "Keeps the medium, palette, light and rendering, and drops the source's "
       + "own subject and layout.",
};

/** The relationship markers, said as what happens rather than as the output
 *  value. The value itself is the subtitle: it is what goes into the prompt,
 *  and somebody comparing against MiniMax's guide has to be able to find it. */
const MARKER_LABEL = {
  derive: "decide for me",
  fully_preserved: "kept whole",
  partially_preserved: "partly kept",
  transferred: "moved onto them",
  reused: "reused as is",
};

const MARKER_NOTE = {
  derive: "Kept whole, or moved onto them where they take somebody's place.",
  fully_preserved: "Everything the definition claims is carried into the video.",
  partially_preserved: "Some of it is carried over and the rest is free to change.",
  transferred: "What they are made of lands on somebody else's place in a clip.",
  reused: "The reference is used as it stands, not re-interpreted.",
};

/** A popover of rows, each of which may be a picture and two lines rather than
 *  a word. `openChoicePopover` takes strings, which is right for a sampler and
 *  wrong for "which of these four files is their voice". */
function openMenu(anchor, { title, sections }) {
  const pop = el("div", { class: "mmc-pop mmc-pop-scroll mmc-cast-menu" },
                 title ? [el("div", { class: "mmc-pop-title", text: title })] : []);
  let close = () => {};
  for (const section of sections) {
    if (!section.rows.length) continue;
    if (section.head) pop.appendChild(el("div", { class: "mmc-cast-menu-head", text: section.head }));
    for (const row of section.rows) {
      pop.appendChild(el("button", {
        class: "mmc-opt",
        "aria-checked": Boolean(row.checked),
        onclick: () => { close(); row.onPick(); },
      }, [
        el("span", { class: "mmc-opt-label" }, [
          ...(row.lead ? [row.lead] : []),
          el("span", { class: "mmc-cast-menu-text" }, [
            el("span", { text: row.label }),
            ...(row.note ? [el("span", { class: "mmc-cast-menu-note", text: row.note })] : []),
          ]),
        ]),
        el("span", { class: "mmc-radio" }),
      ]));
    }
  }
  document.body.appendChild(pop);
  placeNear(pop, anchor);
  close = dismissable(pop);
  pop.querySelector('[aria-checked="true"]')?.scrollIntoView({ block: "center" });
}

/** A file's thumbnail at whatever size the caller draws it, wearing the file's
 *  own identity hue. The same ring the asset row and the prompt chip wear, which
 *  is the whole point of it being here. */
function assetThumb(asset, className = "mmc-asset-thumb") {
  if (!asset) return el("span", { class: `${className} mmc-cast-missing`, text: "?" });
  if (asset.kind === "image") {
    return el("img", {
      class: `${className} mmc-tag-${S.tagIndex(asset.handle)}`,
      src: viewUrl(asset.filename, { preview: true }), alt: "",
    });
  }
  return el("span", { class: `${className} mmc-tag-${S.tagIndex(asset.handle)}` },
            [icon(asset.kind === "video" ? "video" : "audio", 15)]);
}

/**
 * The shelf itself. Built once, redrawn in place, and told nothing about where
 * it is mounted beyond the six things it cannot work out for itself.
 *
 * `getCast`/`setCast`   the piece's subject list. Live, so an edit in one
 *                       surface is visible in the other without a round trip.
 * `getAssets`           the files a subject may be built out of, here. On the
 *                       node face that is the shot's own attachments; in the
 *                       Timeline window it is the piece's pool.
 * `addAsset`            open the picker and attach what comes back, returning
 *                       the new entry — so casting somebody never requires
 *                       having attached their pictures first.
 * `whereCited`          `{ text, cited }` — where this subject walks on. Only
 *                       the host knows whether there are shots to count.
 * `cite`                write `@name` into the prompt. The one-click answer to
 *                       "I cast them and nothing happened".
 * `touch`               persist a keystroke and nothing else. The card holds
 *                       the caret while somebody types a name into it, so this
 *                       must not redraw anything.
 * `commit`              persist a structural change — somebody added, removed,
 *                       or a file moved between slots — and let the host redraw
 *                       whatever else was reading the cast.
 * `keep`                 write one subject into the cast library, given them and
 *                       the files they are built out of here. Absent where there
 *                       is nowhere to keep them, and the star is absent with it.
 * `library`              open the roster so somebody can be taken out of it.
 *                       The host owns this because casting them lands files on a
 *                       node, which is the host's node and not the shelf's.
 */
export class CastShelf {
  constructor({ getCast, setCast, getAssets, addAsset, whereCited, cite, touch, commit,
                keep = null, library = null }) {
    this.getCast = getCast;
    this.setCast = setCast;
    this.getAssets = getAssets;
    this.addAsset = addAsset;
    this.whereCited = whereCited;
    this.cite = cite;
    this.touch = touch ?? commit;
    this.commit = commit;
    this.keep = keep;
    this.library = library;
    // Which member is open, by reference rather than by name: a name is the one
    // field being typed into while the card is open, and a shelf that tracked it
    // by name would close them on the first keystroke.
    this.opened = null;
    // The last member kept, so their star can say so, and whatever went wrong the
    // last time somebody was kept, said on their card rather than swallowed.
    this.kept = null;
    this.note = null;
    this.root = el("div", { class: "mmc-cast" });
  }

  /** A structural change: somebody joined or left, or a file moved between their
   *  slots. The host redraws what else was reading the cast, and the shelf
   *  redraws itself — nothing here is holding a caret. */
  save() {
    this.commit?.();
    this.render();
  }

  /**
   * Whether somebody is typing inside this shelf right now.
   *
   * A name written into a card is written straight through to the blob, and
   * writing to the blob is what redraws the node — so a shelf that rebuilt
   * itself whenever it was asked to would rebuild the field under the caret
   * between one letter and the next, and the focus would go with it. You could
   * type exactly one character.
   *
   * The `touch`/`commit` split above is half the answer and is not enough on its
   * own: the host's *own* redraw arrives through a chain this shelf never sees.
   * So the shelf refuses to redraw while it holds the caret, and redraws on the
   * way out instead. That is the same bargain the prompt box and the refine
   * panel already make — the state is always current, and what is on screen
   * catches up the moment the field is left.
   */
  typing() {
    const active = this.root.ownerDocument?.activeElement
                ?? globalThis.document?.activeElement;
    if (!active || !this.root.contains?.(active)) return false;
    // A *field*, not merely something focused. A pressed button is inside the
    // shelf too — browsers focus one on the way down — and treating that as
    // typing would mean every ✕, every chevron and every menu pick left the card
    // it just changed sitting on screen unchanged. What this guard exists for is
    // a caret, and a caret lives in one of these three.
    return active.tagName === "INPUT" || active.tagName === "TEXTAREA"
        || active.isContentEditable === true;
  }

  /**
   * Redraw once the field being left has finished being left.
   *
   * Not straight from `blur`: a pointer press inside the shelf blurs the field
   * before the click it is part of lands, so redrawing there would detach the
   * button under the pointer and the click would land on nothing — which is
   * every ✕, every tile and every menu on the card whenever a field happened to
   * have the caret. A turn of the event loop is enough for the click to finish
   * first, and if the focus only moved to another field in the same shelf the
   * check below leaves the DOM alone.
   */
  renderSoon() {
    clearTimeout(this.pending);
    this.pending = setTimeout(() => { if (!this.typing()) this.render(); }, 0);
  }

  /** What is wrong with this subject, in one sentence, or "". `state`'s own
   *  check, handed the files that exist *here* — a subject built out of a card's
   *  attachment is fine on that card and dangling on the next one, and this is
   *  the surface that can say so. */
  problem(subject) {
    return S.subjectProblem({ subjects: this.getCast(), assets: this.getAssets() }, subject);
  }

  render() {
    // Never under the caret — see `typing`. The state is already current; the
    // card catches up when the field is left.
    if (this.typing()) return;
    const cast = this.getCast();
    // A member removed elsewhere must not keep the shelf open on nobody.
    if (this.opened && !cast.includes(this.opened)) this.opened = null;
    this.root.replaceChildren(
      el("div", { class: "mmc-cast-head" }, [
        el("span", { class: "mmc-tl-field-name", text: t("Cast") }),
        el("span", {
          class: "mmc-cast-hint",
          text: t("Who is in it. Name them once here, write @anna in the prompt, "
                + "and whatever is behind them rides in with them."),
        }),
        // The roster, where the host can reach it. First of the two, because
        // somebody you have already built is the better answer than building them
        // again — which is the whole reason the library has a Cast tab.
        ...(this.library ? [el("button", {
          class: "mmc-ghost mmc-cast-new",
          title: t("Take somebody out of the cast library — they arrive with their "
                 + "pictures, and they are attached as they land."),
          onclick: () => this.library(),
        }, [icon("star", 13), el("span", { text: t("From the library") })])] : []),
        el("button", {
          class: "mmc-ghost mmc-cast-new",
          title: t("Cast somebody — a person, an object, a place or a look. Give them "
                 + "pictures to be built out of, or just describe them: a name with a "
                 + "description behind it is what keeps them the same person in shot 1 "
                 + "and in shot 9."),
          onclick: () => this.addSubject(),
        }, [el("span", { text: "+" }), el("span", { text: t("Add someone") })]),
      ]),
      ...(cast.length
        ? [el("div", { class: "mmc-cast-list" }, cast.map((s) => this.card(s)))]
        : [el("button", {
            class: "mmc-cast-empty",
            onclick: () => this.addSubject(),
          }, [
            el("span", { class: "mmc-cast-empty-title", text: t("Nobody cast yet") }),
            el("span", {
              class: "mmc-cast-empty-note",
              text: t("A person, an object, a place or a look that comes back shot "
                    + "after shot. Cast them once and write @anna."),
            }),
          ])]),
    );
  }

  // ---- one card --------------------------------------------------------------

  /**
   * One member, open or shut.
   *
   * Shut is the ordinary state and it is one line: their face, their name, what they
   * are made of, and where they walk on. Open is the whole editor — the card the
   * shelf used to draw for everybody at once.
   *
   * That is the change this pass is for. A cast of one reads fine as a stack of
   * tall cards; a cast of six is 900 pixels of fields, of which five sets are
   * being scrolled past rather than read. What you do with a cast most of the
   * time is *check* it — are they in this shot, is their voice still hanging on them —
   * and a line answers that where a card buries it. One at a time is open,
   * because editing somebody is a thing you are doing to one person.
   */
  card(subject) {
    const problem = this.problem(subject);
    const where = this.whereCited(subject);
    const open = this.opened === subject;
    const hue = `mmc-tag-${S.tagIndex(subject.handle || "x")}`;
    const state = problem ? " bad" : where.cited ? "" : " idle";

    return el("div", {
      class: `mmc-cast-card ${hue}${state}${open ? " open" : ""}`,
    }, open ? this.openCard(subject, problem, where) : [this.shutRow(subject, problem, where)]);
  }

  /** Their line. Everything on it is a readout — the one button is the line
   *  itself, which opens them — so nothing here can be clicked by accident on the
   *  way to somewhere else. */
  shutRow(subject, problem, where) {
    return el("div", { class: "mmc-cast-row" }, [
      el("button", {
        class: "mmc-cast-grip",
        "aria-expanded": "false",
        title: t("Open @{handle}", { handle: subject.handle }),
        onclick: () => { this.opened = subject; this.render(); },
      }, [
        this.face(subject),
        el("span", { class: "mmc-cast-line-ident" }, [
          el("span", { class: "mmc-cast-line-name" }, [
            el("span", { class: "mmc-asset-handle", text: "@" }),
            el("span", { text: subject.handle || t("unnamed") }),
          ]),
          el("span", { class: "mmc-cast-line-takes", text: t(subject.takes ?? "person") }),
        ]),
        this.miniRefs(subject),
        // What is wrong with them outranks where they walk on: a card that
        // cannot queue is the thing to deal with first, and it is the reason
        // this line is not the same colour as the others.
        el("span", {
          class: `mmc-cast-line-state${problem ? " bad" : ""}`,
          // Titled as well as printed: a refusal is a sentence and the line has
          // room for about half of one.
          title: problem ? t(problem) : "",
          text: problem ? t(problem) : where.cited ? where.text : t("not in the prompt yet"),
        }),
        el("span", { class: "mmc-cast-chev" }, [icon("chevron", 14)]),
      ]),
      el("button", {
        class: "mmc-asset-x", text: "✕",
        title: where.cited
          ? t("Remove @{handle} — the prompt still writes their name, and will "
            + "refuse to queue until it is edited out.", { handle: subject.handle })
          : t("Remove @{handle}", { handle: subject.handle }),
        onclick: () => this.remove(subject),
      }),
    ]);
  }

  /** Their files at a glance, small enough to be a texture rather than a row of
   *  controls: what a shut line has to say is "two pictures and a voice", and
   *  the three that are not their looks wear their colour to say which. */
  miniRefs(subject) {
    const assets = this.getAssets();
    const tiles = [];
    for (const handle of subject.from ?? []) tiles.push([handle, "from"]);
    for (const key of ["motion", "voice", "replaces"]) {
      if (subject[key]) tiles.push([subject[key], key]);
    }
    if (!tiles.length) {
      return el("span", {
        class: "mmc-cast-line-words",
        text: String(subject.description ?? "").trim()
          ? t("in words") : t("nothing behind them"),
      });
    }
    return el("span", { class: "mmc-cast-minis" }, tiles.slice(0, 5).map(([handle, role]) => {
      const asset = assets.find((a) => a.handle === handle);
      const tile = el("span", {
        class: `mmc-cast-mini${asset ? "" : " missing"} mmc-cast-mini-${role}`,
      }, [assetThumb(asset, "mmc-cast-mini-thumb")]);
      return tile;
    }));
  }

  /** The editor, which is the card this shelf always drew — with the way out of
   *  it, and the way to keep them, on the end of its own top line. */
  openCard(subject, problem, where) {
    const hue = `mmc-tag-${S.tagIndex(subject.handle || "x")}`;
    return [
      el("div", { class: "mmc-cast-top" }, [
        this.face(subject),
        el("div", { class: "mmc-cast-ident" }, [
          el("div", { class: "mmc-cast-namerow" }, [
            el("span", { class: `mmc-asset-handle ${hue}`, text: "@" }),
            this.nameField(subject),
            el("button", {
              class: "mmc-cast-takes",
              title: t("What of their references is the reference, and what the label "
                     + "means where there are none. Same four an attached file takes."),
              text: t(subject.takes ?? "person"),
              onclick: (event) => this.pickTakes(event.currentTarget, subject),
            }),
          ]),
          this.descriptionField(subject),
        ]),
        el("div", { class: "mmc-cast-side" }, [
          this.whereButton(subject, where),
          // Keeping them is the second thing you do after building somebody worth
          // keeping, so it is on their card rather than in a menu — and it is a
          // star, which is the mark this pack already uses for "this goes in the
          // library".
          ...(this.keep ? [el("button", {
            class: `mmc-cast-keepme${this.kept === subject ? " on" : ""}`,
            title: this.kept === subject
              ? t("@{handle} is in the cast library.", { handle: subject.handle })
              : t("Keep @{handle} in the cast library — they come back with their "
                + "pictures, into any piece.", { handle: subject.handle }),
            disabled: subject.handle ? undefined : true,
            onclick: () => this.keepSubject(subject),
          }, [icon("star", 13)])] : []),
          el("button", {
            class: "mmc-cast-shut",
            title: t("Close @{handle}", { handle: subject.handle }),
            "aria-expanded": "true",
            onclick: () => { this.opened = null; this.renderSoon(); },
          }, [icon("chevron", 14)]),
          el("button", {
            class: "mmc-asset-x", text: "✕",
            title: where.cited
              ? t("Remove @{handle} — the prompt still writes their name, and will "
                + "refuse to queue until it is edited out.", { handle: subject.handle })
              : t("Remove @{handle}", { handle: subject.handle }),
            onclick: () => this.remove(subject),
          }),
        ]),
      ]),
      this.refStrip(subject),
      ...(subject.replaces ? [this.replacesField(subject)] : []),
      ...(problem ? [el("div", { class: "mmc-cast-bad", text: t(problem) })] : []),
      ...(this.note?.subject === subject
        ? [el("div", { class: "mmc-cast-bad", text: this.note.text })] : []),
    ];
  }

  remove(subject) {
    if (this.opened === subject) this.opened = null;
    this.setCast(this.getCast().filter((s) => s !== subject));
    this.save();
  }

  /** Keep them in the library, as they stand on this node. The host owns the
   *  writing — a shelf does not know where a roster is kept — and what comes
   *  back is either nothing or a sentence about why not. */
  async keepSubject(subject) {
    const problem = this.problem(subject);
    if (problem) {
      this.note = { subject, text: t(problem) };
      this.render();
      return;
    }
    try {
      await this.keep(subject, this.getAssets());
      this.kept = subject;
      this.note = null;
    } catch (error) {
      this.note = { subject, text: t("Could not keep them — {error}",
                                     { error: error.message ?? error }) };
    }
    this.render();
  }

  /** Their face, where one of their pictures can supply it: the first still they are
   *  built out of. A subject made of a clip alone, or of words alone, keeps the
   *  glyph — there is no picture of them to show, and inventing one would be
   *  showing a file that says nothing about their looks. */
  face(subject) {
    const assets = this.getAssets();
    const still = (subject.from ?? [])
      .map((handle) => assets.find((a) => a.handle === handle))
      .find((a) => a?.kind === "image");
    if (still) {
      return el("img", {
        class: "mmc-cast-face", alt: "",
        src: viewUrl(still.filename, { preview: true }),
      });
    }
    // The glyph follows what they are: a person glyph over a described *place*
    // says the wrong thing, and the card's whole job is saying what they are.
    return el("span", { class: "mmc-cast-face mmc-cast-face-blank" },
              [icon(BLANK_FACE[subject.takes ?? "person"] ?? "face", 22)]);
  }

  nameField(subject) {
    const field = el("input", {
      class: "mmc-cast-name",
      value: subject.handle ?? "",
      spellcheck: "false",
      placeholder: t("name"),
      title: t("The name you write in the prompt. Letters, digits and underscores — "
             + "no hyphen, which is what tells a name from a file's handle."),
      oninput: (event) => {
        subject.handle = event.target.value.trim();
        this.touch?.();
      },
      // Redrawn on blur rather than on every keystroke: the field holds the
      // caret, and rebuilding the card mid-word would take it away.
      onblur: () => this.renderSoon(),
    });
    field.addEventListener("pointerdown", (event) => event.stopPropagation());
    return field;
  }

  descriptionField(subject) {
    const bare = !S.subjectFiles(subject).length && !subject.replaces;
    const field = el("input", {
      class: "mmc-cast-desc",
      value: subject.description ?? "",
      // Two placeholders, because the field is doing two different jobs. With
      // pictures behind them it fills in what a picture cannot say; with nothing
      // behind them it *is* the definition, and the box has to ask for enough.
      placeholder: bare
        ? t("describe them — this is all the model will know")
        : t("what a picture cannot say"),
      title: bare
        ? t("Nothing else is behind them, so this is their whole definition. Written "
          + "into the prompt as what @{handle} is.", { handle: subject.handle })
        : t("Folded into their definition after the files they are built out of — they "
          + "are nervous, the cardigan is theirs. What the model cannot see for "
          + "itself goes here."),
      oninput: (event) => {
        subject.description = event.target.value;
        this.touch?.();
      },
      onblur: () => this.renderSoon(),
    });
    field.addEventListener("pointerdown", (event) => event.stopPropagation());
    return field;
  }

  replacesField(subject) {
    const field = el("input", {
      class: "mmc-cast-desc mmc-cast-replaces",
      value: subject.replaces_what ?? "",
      placeholder: t("who they replace in that clip — the person at the counter"),
      title: t("Written into the retention line, so the model knows who is going."),
      oninput: (event) => { subject.replaces_what = event.target.value; this.touch?.(); },
      onblur: () => this.renderSoon(),
    });
    field.addEventListener("pointerdown", (event) => event.stopPropagation());
    return el("div", { class: "mmc-cast-line" }, [
      el("span", { class: "mmc-cast-of", text: t("in place of") }),
      field,
    ]);
  }

  /** Where they walk on. A button rather than a readout when they walk on
   *  nowhere: the commonest way to lose an afternoon with this feature is to
   *  cast somebody and never write their name, so the thing that says so is also
   *  the thing that fixes it. */
  whereButton(subject, where) {
    if (where.cited || !this.cite) {
      return el("span", { class: "mmc-cast-where", text: where.text });
    }
    return el("button", {
      class: "mmc-cast-where mmc-cast-where-idle",
      text: t("not in the prompt yet"),
      title: t("Nothing cites @{handle}, so they are in no shot. Click to write their "
             + "name into the prompt.", { handle: subject.handle }),
      disabled: subject.handle ? undefined : true,
      onclick: () => { this.cite(subject); this.render(); },
    });
  }

  // ---- the references --------------------------------------------------------

  /** Every file behind them, one tile each, in the order the definition will cite
   *  them: their looks, then their movement, then their voice, then the place they
   *  take. A handle in two slots gets two tiles, which is honest — it is
   *  lending them two different things. */
  refStrip(subject) {
    const assets = this.getAssets();
    const tiles = [];
    for (const handle of subject.from ?? []) {
      tiles.push(this.refTile(subject, handle, "from", assets));
    }
    for (const key of ["motion", "voice", "replaces"]) {
      if (subject[key]) tiles.push(this.refTile(subject, subject[key], key, assets));
    }
    return el("div", { class: "mmc-cast-refs" }, [
      ...tiles,
      el("button", {
        class: "mmc-cast-add",
        title: t("Hang a file on @{handle} — a picture they look like, a clip they "
               + "move like, a sound that is their voice, or a clip they take "
               + "somebody's place in.", { handle: subject.handle }),
        onclick: (event) => this.pickReference(event.currentTarget, subject),
      }, [el("span", { text: "+" })]),
      ...(tiles.length ? [] : [el("span", {
        class: "mmc-cast-refs-none",
        text: t("no files — described in words alone"),
      })]),
      el("button", {
        class: "mmc-cast-keep",
        title: t("The reference guide's own relationship marker, written into the "
               + "retention line. Left to decide, it is kept whole — or moved onto "
               + "them, where they take somebody's place."),
        // Prefixed, because "kept whole" alone at the end of a row of pictures
        // reads as a stray label rather than as a setting with a value.
        text: t("what is kept: {value}",
                { value: t(MARKER_LABEL[subject.relationship ?? "derive"]) }),
        onclick: (event) => this.pickMarker(event.currentTarget, subject),
      }),
    ]);
  }

  refTile(subject, handle, role, assets) {
    const asset = assets.find((a) => a.handle === handle);
    return el("button", {
      class: `mmc-cast-ref${asset ? "" : " missing"}`,
      title: asset
        ? t("@{handle} — {what}. Click to change what it lends them, or take it off.",
            { handle, what: t(ROLE[role].lead).toLowerCase() })
        : t("@{handle} is not attached here any more, so this card cannot queue "
          + "until it is put back or taken off them.", { handle }),
      onclick: (event) => this.pickRole(event.currentTarget, subject, handle, role),
    }, [
      assetThumb(asset, "mmc-cast-ref-thumb"),
      // No badge on a picture that only says what they look like. That is what
      // four out of five tiles are, and a badge on every one of them is a badge
      // that means nothing — where a badge on the fifth means "this one is not
      // their looks", which is the only thing worth reading off the row at a
      // glance. The tooltip says it either way.
      ...(role === "from" ? [] : [el("span", {
        class: `mmc-cast-badge mmc-cast-badge-${role}`,
      }, [icon(ROLE[role].glyph, 11)])]),
    ]);
  }

  /** The menu behind a tile: the roles this file can play, and the way off them.
   *  Roles are filtered by what the file actually is — a still cannot be a
   *  voice, and offering it as one would be offering a queue-time error. */
  pickRole(anchor, subject, handle, current) {
    const asset = this.getAssets().find((a) => a.handle === handle);
    const rows = ROLES
      .filter((role) => !asset || role.fits(asset) || role.key === current)
      .map((role) => ({
        label: t(role.lead),
        note: t(role.note),
        checked: role.key === current,
        onPick: () => { this.setRole(subject, handle, current, role.key); },
      }));
    rows.push({
      label: t("Take it off @{handle}", { handle: subject.handle }),
      onPick: () => { this.clearRole(subject, handle, current); this.save(); },
    });
    openMenu(anchor, { title: `@${handle}`, sections: [{ rows }] });
  }

  /** Move a handle between slots. `from` is a list and the other three hold one
   *  each, so taking over one of them displaces whatever was in it — which is
   *  the truthful outcome: they have one voice. */
  setRole(subject, handle, current, next) {
    if (current === next) return;
    this.clearRole(subject, handle, current);
    if (next === "from") subject.from = [...(subject.from ?? []), handle];
    else subject[next] = handle;
    // The file is a different kind of reference now — a clip that was their looks
    // and is now their movement is a motion reference — so the narrowing follows
    // it across, unless somebody set that themselves. See `state.inheritTake`.
    S.inheritTake(subject, next, this.getAssets().find((a) => a.handle === handle));
    this.save();
  }

  clearRole(subject, handle, role) {
    if (role === "from") subject.from = (subject.from ?? []).filter((h) => h !== handle);
    else delete subject[role];
    if (role === "replaces") delete subject.replaces_what;
  }

  /** The "+" tile: everything attached that is not already on them, then the way
   *  to attach something that is not. A pick lands in the slot its kind fits —
   *  a sound is a voice, anything else is their looks — and the tile's own menu is
   *  where that is changed, so the common case is one click. */
  pickReference(anchor, subject) {
    const used = new Set([...(subject.from ?? []), subject.motion, subject.voice,
                          subject.replaces].filter(Boolean));
    const rows = this.getAssets()
      .filter((asset) => !used.has(asset.handle))
      .map((asset) => ({
        lead: assetThumb(asset, "mmc-cast-menu-thumb"),
        label: `@${asset.handle}`,
        note: asset.filename,
        onPick: () => {
          const key = ROLES.find((role) => role.fits(asset))?.key ?? "from";
          if (key === "from") subject.from = [...(subject.from ?? []), asset.handle];
          else subject[key] = asset.handle;
          // Hung on somebody, so narrowed to what they are — a picture of @anna is
          // a person reference, and the row that says so is the same row the
          // model is handed. See `state.inheritTake`.
          S.inheritTake(subject, key, asset);
          this.save();
        },
      }));
    const sections = [{ head: rows.length ? t("Attached here") : "", rows }];
    if (this.addAsset) {
      sections.push({
        rows: [{
          lead: el("span", { class: "mmc-cast-menu-thumb mmc-cast-menu-plus", text: "+" }),
          label: t("Attach a file…"),
          note: t("Adds it to this shot and hangs it on them"),
          onPick: async () => {
            const asset = await this.addAsset();
            if (!asset) return;
            const key = ROLES.find((role) => role.fits(asset))?.key ?? "from";
            if (key === "from") subject.from = [...(subject.from ?? []), asset.handle];
            else subject[key] = asset.handle;
            S.inheritTake(subject, key, asset);
            this.save();
          },
        }],
      });
    }
    openMenu(anchor, {
      title: t("What does @{handle} get?", { handle: subject.handle }),
      sections,
    });
  }

  // ---- the two small menus ---------------------------------------------------

  pickTakes(anchor, subject) {
    openMenu(anchor, {
      title: t("@{handle} is a", { handle: subject.handle }),
      sections: [{
        rows: S.SUBJECT_TAKES.map((key) => ({
          label: t(key),
          note: t(TAKES_NOTE[key]),
          checked: key === (subject.takes ?? "person"),
          onPick: () => {
            const before = subject.takes ?? "person";
            subject.takes = key;
            // Their pictures were person references because they were a person. They
            // are a place now, so they are scene references — and a file
            // somebody narrowed to something else themselves is left alone.
            S.inheritTakes(subject, this.getAssets(), { over: before });
            this.save();
          },
        })),
      }],
    });
  }

  pickMarker(anchor, subject) {
    openMenu(anchor, {
      title: t("What becomes of @{handle}", { handle: subject.handle }),
      sections: [{
        rows: ["derive", ...S.SUBJECT_MARKERS].map((key) => ({
          label: t(MARKER_LABEL[key]),
          // The output value itself, because it is what goes into the prompt and
          // is the word to search MiniMax's guide for.
          note: key === "derive" ? t(MARKER_NOTE[key]) : `${key} — ${t(MARKER_NOTE[key])}`,
          checked: key === (subject.relationship ?? "derive"),
          onPick: () => {
            if (key === "derive") delete subject.relationship;
            else subject.relationship = key;
            this.save();
          },
        })),
      }],
    });
  }

  /** Cast somebody new. Named for the first free `subject`, `subject_2`… — a
   *  placeholder rather than a guess, because the name is the thing the user
   *  will type and only they know what it should be. */
  addSubject() {
    const cast = this.getCast();
    const taken = new Set(cast.map((s) => s.handle));
    let handle = "subject";
    for (let n = 2; taken.has(handle); n += 1) handle = `subject_${n}`;
    const subject = { handle, from: [], takes: "person" };
    this.setCast([...cast, subject]);
    // Open, because somebody just cast is somebody about to be described. They are
    // the only one open — see `card`.
    this.opened = subject;
    this.save();
    // Straight into the name, which is the first thing to change about them.
    const fields = this.root.querySelectorAll(".mmc-cast-name");
    const last = fields[fields.length - 1];
    last?.focus();
    last?.select();
  }
}

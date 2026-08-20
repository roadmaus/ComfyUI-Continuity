// The cast: who is in the piece, as against which files are attached to it.
//
// H3's reference guide separates the two. `<Picture N>` is a file the tokenizer
// is shown; `<Subject N>` is reusable visible content the target video contains,
// and section 2.2 says outright that an image used only to define a character
// gets no picture entry of its own. So a person is not a picture: she is
// declared here, cited in prose by name, and `@anna` becomes `<Subject 1>` at
// queue time exactly as `@ref-1` becomes `<Picture 1>`.
//
// One shelf, mounted twice — on the node's own face and in the Timeline window —
// because there is one node and a cast belongs to the piece either way. What
// differs between the two is only what the host hands it: which files are
// available to build somebody out of, and where a citation of her can be
// counted.
//
// ---- what the redesign is for ------------------------------------------------
//
// The first version of this shelf was two lines of look-alike ghost chips, and
// the one gesture the whole feature exists for — hang a reference on a person —
// was a bare "+" between them that nobody found. It also refused to open at all
// until a reference had been attached, which put the feature out of reach of
// exactly the generation that most needs it: a text-only one, where a name is
// the only thing keeping the same woman in shot 1 and shot 9.
//
// So the references are the card now. Each one is a real thumbnail wearing its
// own identity hue, with a badge saying what that file lends her — her looks,
// her movement, her voice, or the place she takes. One tile, one menu, four
// answers, and the "+" beside them is a tile of the same size rather than a
// character in a row of text.
//
// The card wears her hue on its left edge, and it is the same hue `@anna` wears
// as a chip in the sentence — the pack's existing "this chip is that picture"
// device, pointed at a person instead of a file.

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
    lead: "Her looks come from this",
    note: "Face, build and clothing are taken from it; its background, light and "
        + "pose are not. Several pictures of the same person are one subject.",
    fits: (asset) => asset.kind !== "audio" && asset.track !== "sound",
  },
  {
    key: "motion", glyph: "play", label: "moves",
    lead: "She moves like this",
    note: "Her movement is taken from the clip and her appearance stays her "
        + "pictures'. This is how a face from a still walks like somebody in a clip.",
    fits: (asset) => asset.kind === "video" && asset.track !== "sound",
  },
  {
    key: "voice", glyph: "audio", label: "voice",
    lead: "This is her voice",
    note: "Bound as her voice-timbre reference — its words and background sound "
        + "are not copied. She takes a speaker ID in cast order.",
    fits: (asset) => asset.kind === "audio" || asset.track === "sound",
  },
  {
    key: "replaces", glyph: "swap", label: "her place",
    lead: "She takes somebody's place in this",
    note: "The clip's framing, camera work and action are kept and its occupant "
        + "is replaced by her — the whole of “swap this person for that one”.",
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
  transferred: "moved onto her",
  reused: "reused as is",
};

const MARKER_NOTE = {
  derive: "Kept whole, or moved onto her where she takes somebody's place.",
  fully_preserved: "Everything the definition claims is carried into the video.",
  partially_preserved: "Some of it is carried over and the rest is free to change.",
  transferred: "What she is made of lands on somebody else's place in a clip.",
  reused: "The reference is used as it stands, not re-interpreted.",
};

/** A popover of rows, each of which may be a picture and two lines rather than
 *  a word. `openChoicePopover` takes strings, which is right for a sampler and
 *  wrong for "which of these four files is her voice". */
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
 *                       having attached her pictures first.
 * `whereCited`          `{ text, cited }` — where this subject walks on. Only
 *                       the host knows whether there are shots to count.
 * `cite`                write `@name` into the prompt. The one-click answer to
 *                       "I cast her and nothing happened".
 * `touch`               persist a keystroke and nothing else. The card holds
 *                       the caret while somebody types a name into it, so this
 *                       must not redraw anything.
 * `commit`              persist a structural change — somebody added, removed,
 *                       or a file moved between slots — and let the host redraw
 *                       whatever else was reading the cast.
 */
export class CastShelf {
  constructor({ getCast, setCast, getAssets, addAsset, whereCited, cite, touch, commit }) {
    this.getCast = getCast;
    this.setCast = setCast;
    this.getAssets = getAssets;
    this.addAsset = addAsset;
    this.whereCited = whereCited;
    this.cite = cite;
    this.touch = touch ?? commit;
    this.commit = commit;
    this.root = el("div", { class: "mmc-cast" });
  }

  /** A structural change: somebody joined or left, or a file moved between her
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
    return !!active && !!this.root.contains?.(active);
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
    this.root.replaceChildren(
      el("div", { class: "mmc-cast-head" }, [
        el("span", { class: "mmc-tl-field-name", text: t("Cast") }),
        el("span", {
          class: "mmc-cast-hint",
          text: t("Who is in it. Name them once here, write @anna in the prompt, "
                + "and whatever is behind her rides in with her."),
        }),
        el("button", {
          class: "mmc-ghost mmc-cast-new",
          title: t("Cast somebody — a person, an object, a place or a look. Give her "
                 + "pictures to be built out of, or just describe her: a name with a "
                 + "description behind it is what keeps her the same person in shot 1 "
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
                    + "after shot. Cast her once and write @anna."),
            }),
          ])]),
    );
  }

  // ---- one card --------------------------------------------------------------

  card(subject) {
    const problem = this.problem(subject);
    const where = this.whereCited(subject);
    const hue = `mmc-tag-${S.tagIndex(subject.handle || "x")}`;

    return el("div", {
      class: `mmc-cast-card ${hue}${problem ? " bad" : where.cited ? "" : " idle"}`,
    }, [
      el("div", { class: "mmc-cast-top" }, [
        this.face(subject),
        el("div", { class: "mmc-cast-ident" }, [
          el("div", { class: "mmc-cast-namerow" }, [
            el("span", { class: `mmc-asset-handle ${hue}`, text: "@" }),
            this.nameField(subject),
            el("button", {
              class: "mmc-cast-takes",
              title: t("What of her references is the reference, and what the label "
                     + "means where there are none. Same four an attached file takes."),
              text: t(subject.takes ?? "person"),
              onclick: (event) => this.pickTakes(event.currentTarget, subject),
            }),
          ]),
          this.descriptionField(subject),
        ]),
        el("div", { class: "mmc-cast-side" }, [
          this.whereButton(subject, where),
          el("button", {
            class: "mmc-asset-x", text: "✕",
            title: where.cited
              ? t("Remove @{handle} — the prompt still writes her name, and will "
                + "refuse to queue until it is edited out.", { handle: subject.handle })
              : t("Remove @{handle}", { handle: subject.handle }),
            onclick: () => {
              this.setCast(this.getCast().filter((s) => s !== subject));
              this.save();
            },
          }),
        ]),
      ]),
      this.refStrip(subject),
      ...(subject.replaces ? [this.replacesField(subject)] : []),
      ...(problem ? [el("div", { class: "mmc-cast-bad", text: t(problem) })] : []),
    ]);
  }

  /** Her face, where one of her pictures can supply it: the first still she is
   *  built out of. A subject made of a clip alone, or of words alone, keeps the
   *  glyph — there is no picture of her to show, and inventing one would be
   *  showing a file that says nothing about her looks. */
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
    // The glyph follows what she is: a person glyph over a described *place*
    // says the wrong thing, and the card's whole job is saying what she is.
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
      // pictures behind her it fills in what a picture cannot say; with nothing
      // behind her it *is* the definition, and the box has to ask for enough.
      placeholder: bare
        ? t("describe her — this is all the model will know")
        : t("what a picture cannot say"),
      title: bare
        ? t("Nothing else is behind her, so this is her whole definition. Written "
          + "into the prompt as what @{handle} is.", { handle: subject.handle })
        : t("Folded into her definition after the files she is built out of — she "
          + "is nervous, the cardigan is hers. What the model cannot see for "
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
      placeholder: t("who she replaces in that clip — the man at the counter"),
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

  /** Where she walks on. A button rather than a readout when she walks on
   *  nowhere: the commonest way to lose an afternoon with this feature is to
   *  cast somebody and never write her name, so the thing that says so is also
   *  the thing that fixes it. */
  whereButton(subject, where) {
    if (where.cited || !this.cite) {
      return el("span", { class: "mmc-cast-where", text: where.text });
    }
    return el("button", {
      class: "mmc-cast-where mmc-cast-where-idle",
      text: t("not in the prompt yet"),
      title: t("Nothing cites @{handle}, so she is in no shot. Click to write her "
             + "name into the prompt.", { handle: subject.handle }),
      disabled: subject.handle ? undefined : true,
      onclick: () => { this.cite(subject); this.render(); },
    });
  }

  // ---- the references --------------------------------------------------------

  /** Every file behind her, one tile each, in the order the definition will cite
   *  them: her looks, then her movement, then her voice, then the place she
   *  takes. A handle in two slots gets two tiles, which is honest — it is
   *  lending her two different things. */
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
        title: t("Hang a file on @{handle} — a picture she looks like, a clip she "
               + "moves like, a sound that is her voice, or a clip she takes "
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
               + "her, where she takes somebody's place."),
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
        ? t("@{handle} — {what}. Click to change what it lends her, or take it off.",
            { handle, what: t(ROLE[role].lead).toLowerCase() })
        : t("@{handle} is not attached here any more, so this card cannot queue "
          + "until it is put back or taken off her.", { handle }),
      onclick: (event) => this.pickRole(event.currentTarget, subject, handle, role),
    }, [
      assetThumb(asset, "mmc-cast-ref-thumb"),
      // No badge on a picture that only says what she looks like. That is what
      // four out of five tiles are, and a badge on every one of them is a badge
      // that means nothing — where a badge on the fifth means "this one is not
      // her looks", which is the only thing worth reading off the row at a
      // glance. The tooltip says it either way.
      ...(role === "from" ? [] : [el("span", {
        class: `mmc-cast-badge mmc-cast-badge-${role}`,
      }, [icon(ROLE[role].glyph, 11)])]),
    ]);
  }

  /** The menu behind a tile: the roles this file can play, and the way off her.
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
   *  the truthful outcome: she has one voice. */
  setRole(subject, handle, current, next) {
    if (current === next) return;
    this.clearRole(subject, handle, current);
    if (next === "from") subject.from = [...(subject.from ?? []), handle];
    else subject[next] = handle;
    this.save();
  }

  clearRole(subject, handle, role) {
    if (role === "from") subject.from = (subject.from ?? []).filter((h) => h !== handle);
    else delete subject[role];
    if (role === "replaces") delete subject.replaces_what;
  }

  /** The "+" tile: everything attached that is not already on her, then the way
   *  to attach something that is not. A pick lands in the slot its kind fits —
   *  a sound is a voice, anything else is her looks — and the tile's own menu is
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
          this.save();
        },
      }));
    const sections = [{ head: rows.length ? t("Attached here") : "", rows }];
    if (this.addAsset) {
      sections.push({
        rows: [{
          lead: el("span", { class: "mmc-cast-menu-thumb mmc-cast-menu-plus", text: "+" }),
          label: t("Attach a file…"),
          note: t("Adds it to this shot and hangs it on her"),
          onPick: async () => {
            const asset = await this.addAsset();
            if (!asset) return;
            const key = ROLES.find((role) => role.fits(asset))?.key ?? "from";
            if (key === "from") subject.from = [...(subject.from ?? []), asset.handle];
            else subject[key] = asset.handle;
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
          onPick: () => { subject.takes = key; this.save(); },
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
    this.setCast([...cast, { handle, from: [], takes: "person" }]);
    this.save();
    // Straight into the name, which is the first thing to change about her.
    const fields = this.root.querySelectorAll(".mmc-cast-name");
    const last = fields[fields.length - 1];
    last?.focus();
    last?.select();
  }
}

// What each family gets when it renders a cast member.
//
// A member is universal — a name, a description, the files they are made of
// — and everything derived from those is one family's: a saved reference is a
// latent in one VAE's space, a LoRA is weights for one architecture, and
// whether a family should be handed their pictures at all is a question with
// a different answer on Ideogram (which reads none) and on Krea 2 (which reads
// them through an adapter). The first version of this card had a ledger that
// counted for the piece's family, a submenu that offered the others, and a
// "wears" line that named no family at all — so a member on an H3 piece could
// not say what a Klein still should get, and could not be saved for Klein at
// all once their H3 mods existed.
//
// So the derived half of a member is drawn *per family*: one tab a family,
// and under the open tab one sentence saying what that family is handed —
// "When Flux 2 Klein renders @anna it gets their 2 pictures wearing
// anna_klein" — where every noun in the sentence is the control. The status
// line under it is the one fact about that family that changes what to do:
// save once for the token win, hang the adapter, or nothing to set up.
//
// One panel, two hosts. The shelf (a card on a node, or in the Timeline
// window) and the library sheet draw the same tabs; what differs is where a
// member's files live and where an encode lands, which the host supplies as
// callbacks. The panel itself owns only which tab is open, and writes `send`
// straight onto the member (`state.wearOn`).

import { el, icon } from "./dom.js";
import { t } from "./i18n.js";
import { loraBase } from "./loras.js";
import { cost, everyFamilyRows, familyModeRows, modIn, modRow, modeWord, remakeRows, shortTokens } from "./refmod.js";
import * as S from "./state.js";
import { openMenu } from "./cast.js";

/**
 * @param host
 *   families()                every `refmod.castFamilies` entry, the piece's first
 *   looks(subject)            their looks as entries: `{handle?, filename, kind, ref_size, mods}`
 *   canvas()                  the generation's `{width, height}`, or null
 *   busy()                    `{subject?, mode, count, progress, family, remake}` while encoding, or null
 *   note(subject)             what went wrong the last time, or null
 *   canSave()                 whether this host can encode at all (a VAE and a queue)
 *   save(subject, mode, family)       encode their pictures for one family, or for a list of them
 *   remake(subject, mode, mods, family)  write those mods again, in either mode
 *   clear(subject, family, paths)  forget their renditions for that family —
 *                             every one, or only `paths` — leaving the files
 *   library(path)             open the roster on a saved file, or null
 *   hangLora(subject, family, reveal)   the LoRA manager on their row for that family
 *   loraMenu(anchor, subject, family, entry)  the chip's own menu
 *   touch(), commit()         what changed without / with a save
 *   redraw()                  draw the host again (the panel is part of its card)
 */
export class WearsPanel {
  constructor(host) {
    this.host = host;
    // Which family's tab is open, by id. Absent is the piece's own.
    this.open = null;
  }

  family() {
    const families = this.host.families();
    return families.find((family) => family.id === this.open) ?? families[0] ?? null;
  }

  /** What `family` actually gets for `subject`, given what they hold for it:
   *  the send word in force, and why. Mirrors `subjects.sent` and
   *  `chat.still_piece` — the same three answers, read the same way. */
  effective(subject, family, entries) {
    const chosen = S.sendFor(subject, family.id);
    if (!family.reads.pictures) return "words";
    if (family.adapter && !this.adapterOn(subject, family)) return "needs-adapter";
    if (chosen === "words") return "words";
    const space = family.refmod ? family.space : null;
    const saved = space ? entries.filter((entry) => modIn(entry, space)).length : 0;
    if (chosen === "pictures") return "pictures";
    if (chosen === "saved") return saved ? "saved" : "pictures";
    // Left to decide: the rendition where there is one, the picture otherwise.
    return saved && saved === entries.filter((e) => e.kind !== "video").length ? "saved" : "pictures";
  }

  /** Whether the adapter a family needs to read a picture is among what they
   *  wear on it. By the family's own hints, which name the adapter files. */
  adapterOn(subject, family) {
    const hints = (family.adapterHints ?? []).map((hint) => String(hint).toLowerCase());
    return S.subjectLoras(subject, family.id).some((entry) =>
      entry.enabled !== false && hints.some((hint) => entry.name.toLowerCase().includes(hint)));
  }

  render(subject) {
    const families = this.host.families();
    if (!families.length) return null;
    const family = this.family();
    return el("div", { class: "mmc-wears" }, [
      this.head(subject, families),
      el("div", { class: "mmc-wears-rail", role: "tablist" },
         families.map((one) => this.tab(subject, one, one.id === family?.id))),
      this.panel(subject, family),
    ]);
  }

  head(subject, families) {
    const entries = this.host.looks(subject).filter((entry) => !S.isRefMod(entry));
    const keepers = families.filter((family) => family.refmod);
    const offer = this.host.canSave() && !this.host.busy() && entries.length && keepers.length;
    return el("div", { class: "mmc-wears-head" }, [
      el("span", { class: "mmc-wears-legend", text: t("What each family gets") }),
      ...(offer ? [el("button", {
        class: "mmc-wears-act amber",
        title: t("Encode their pictures once, for any family that keeps saved references, "
               + "and the render reads the file instead. Offered whatever has been saved "
               + "already — a second family can be saved after the first."),
        onclick: (event) => this.saveMenu(event.currentTarget, subject, keepers, entries),
      }, [icon("cube", 12), el("span", { text: t("Save as RefMod ▾") })])] : []),
    ]);
  }

  /** The whole picture, from the head of the rail: every family that keeps
   *  saved references, its state, and its modes. Never a one-time question. */
  saveMenu(anchor, subject, keepers, entries) {
    const onKnown = () => this.host.redraw();
    const sections = keepers.map((family) => {
      const saved = entries.filter((entry) => modIn(entry, family.space)).length;
      const state = saved === entries.length
        ? t("saved") : saved ? t("{saved} of {count} saved", { saved, count: entries.length }) : t("not saved");
      // What is saved already can be encoded again from here too — a size
      // already made is the one a bad encode needs redoing in (issue #121).
      const mods = saved ? entries.map((entry) => modIn(entry, family.space)).filter(Boolean)
        .map((path) => modRow(path, onKnown)).filter(Boolean) : [];
      const again = family.vae
        ? remakeRows(mods, (remode, paths) => this.host.remake(subject, remode, paths, family)) : [];
      return {
        head: `${t(family.label)} · ${state}`,
        rows: [...familyModeRows(entries, family, (mode, one) => this.host.save(subject, mode, one), onKnown),
               ...again.map((row) => ({ ...row, label: t("Re-encode saved · {label}", { label: row.label }) }))],
      };
    });
    const every = everyFamilyRows(entries, keepers, (mode, list) => this.host.save(subject, mode, list), onKnown);
    if (every.length) sections.unshift({ head: t("Every family"), rows: every });
    openMenu(anchor, {
      title: t("Save @{handle}'s pictures as RefMods → refmods/cast/{handle}", { handle: subject.handle }),
      sections,
    });
  }

  tab(subject, family, selected) {
    const entries = this.host.looks(subject);
    const mode = this.effective(subject, family, entries);
    const worn = S.subjectLoras(subject, family.id).length;
    const dot = { pictures: "pic", saved: "mod", words: "words", "needs-adapter": "off" }[mode];
    return el("button", {
      class: "mmc-wears-tab", role: "tab", "aria-selected": String(selected),
      title: t("What {family} is handed for @{handle}.", { family: t(family.label), handle: subject.handle }),
      onclick: () => { this.open = family.id; this.host.redraw(); },
    }, [
      el("span", { class: `mmc-wears-dot ${dot}` }),
      ...(worn ? [el("span", { class: "mmc-wears-dot lora" })] : []),
      el("span", { text: t(family.label) }),
      ...(family.here ? [el("span", { class: "mmc-wears-here", text: t("this piece") })] : []),
    ]);
  }

  panel(subject, family) {
    if (!family) return null;
    const entries = this.host.looks(subject);
    const mode = this.effective(subject, family, entries);
    const worn = S.subjectLoras(subject, family.id);
    return el("div", { class: "mmc-wears-panel" }, [
      this.sentence(subject, family, entries, mode, worn),
      el("div", { class: "mmc-wears-rows" }, [
        ...worn.map((entry) => this.loraRow(subject, family, entry)),
        el("div", { class: "mmc-wears-row" }, [
          el("div", { class: "mmc-wears-row-what" }, [
            el("span", { class: "mmc-wears-row-lead",
                         text: worn.length ? t("Hang another LoRA") : t("Hang a LoRA on them") }),
            el("span", { class: "mmc-wears-row-note",
                         text: t("Weights for {family}. It goes on the model in every shot their name is in, "
                               + "with its trigger words in front of that shot's prompt.",
                               { family: t(family.label) }) }),
          ]),
          el("button", {
            class: "mmc-wears-act",
            onclick: () => this.host.hangLora(subject, family, null),
          }, [icon("effect", 12), el("span", { text: t("+ LoRA") })]),
        ]),
      ]),
      this.status(subject, family, entries, mode),
    ]);
  }

  /** "When Flux 2 Klein renders @anna it gets their 2 pictures wearing
   *  anna_klein." Every noun is the control. */
  sentence(subject, family, entries, mode, worn) {
    const stills = entries.filter((entry) => entry.kind !== "video").length;
    const clips = entries.length - stills;
    const line = el("div", { class: "mmc-wears-sentence" }, [
      el("span", { class: "k", text: t("When {family} renders ", { family: t(family.label) }) }),
      el("span", { class: `mmc-asset-handle mmc-tag-${S.tagIndex(subject.handle || "x")}`, text: `@${subject.handle}` }),
      el("span", { class: "k", text: ` ${t("it gets")} ` }),
      this.sendChoice(subject, family, entries, mode, stills, clips),
    ]);
    if (worn.length) {
      line.appendChild(el("span", { class: "k", text: ` ${t("wearing")} ` }));
      worn.forEach((entry, index) => {
        line.appendChild(el("button", {
          class: `mmc-wears-choice lora${entry.enabled === false ? " off" : ""}`,
          title: t("{name} — press to change its words or its weight, mute it, or take it off them.",
                   { name: entry.name }),
          onclick: (event) => this.host.loraMenu(event.currentTarget, subject, family, entry),
        }, [el("span", { text: loraBase(entry) }),
            ...(entry.triggers?.length ? [el("span", { class: "words", text: ` “${entry.triggers.join(", ")}”` })] : [])]));
        if (index < worn.length - 1) line.appendChild(el("span", { class: "k", text: ` ${t("and")} ` }));
      });
    }
    line.appendChild(el("span", { class: "k",
      text: family.reads.voice && S.subjectFiles(subject).length && subject.voice
        ? t(", and their voice where they speak.") : "." }));
    return line;
  }

  sendChoice(subject, family, entries, mode, stills, clips) {
    const what = {
      pictures: clips
        ? t(stills === 1 ? "their picture and {clips} clip" : "their {stills} pictures and {clips} clip", { stills, clips })
        : t(stills === 1 ? "their picture" : "their {stills} pictures", { stills }),
      saved: t("their saved reference"),
      words: t("their description only"),
      "needs-adapter": t("their description only"),
    }[mode];
    const text = stills || clips ? what : t("their description only");
    const fixed = !family.reads.pictures || !(stills || clips);
    return el("button", {
      class: `mmc-wears-choice${mode === "saved" ? " saved" : ""}${fixed ? " fixed" : ""}`,
      ...(fixed ? { disabled: "" } : {}),
      title: fixed ? "" : t("What {family} is handed for their looks.", { family: t(family.label) }),
      onclick: (event) => { if (!fixed) this.sendMenu(event.currentTarget, subject, family, entries); },
    }, [el("span", { text })]);
  }

  sendMenu(anchor, subject, family, entries) {
    const chosen = S.sendFor(subject, family.id);
    const space = family.refmod ? family.space : null;
    const saved = space ? entries.filter((entry) => modIn(entry, space)).length : 0;
    const pick = (send) => {
      const row = S.wearOn(subject, family.id);
      if (send) row.send = send; else delete row.send;
      S.tidyWears(subject);
      this.host.commit();
      this.host.redraw();
    };
    const rows = [
      { label: t("Decide for me"), checked: chosen === null,
        note: t("Their saved reference where the pictures carry one for this family, the pictures otherwise."),
        onPick: () => pick(null) },
      { label: t("Their pictures"), checked: chosen === "pictures",
        note: t("Encoded every render. Works anywhere they render."),
        onPick: () => pick("pictures") },
      ...(family.refmod ? [{
        label: t("Their saved reference"), checked: chosen === "saved",
        note: saved
          ? t("Already encoded for {family} — read off disk.", { family: t(family.label) })
          : t("Not encoded for {family} yet — pick this, then save them from the button above.",
              { family: t(family.label) }),
        onPick: () => pick("saved") }] : []),
      { label: t("Their description only"), checked: chosen === "words",
        note: t("Nothing but the words. Cheapest; least faithful."),
        onPick: () => pick("words") },
    ];
    openMenu(anchor, { title: t("What {family} gets for @{handle}", { family: t(family.label), handle: subject.handle }),
                       sections: [{ rows }] });
  }

  loraRow(subject, family, entry) {
    const off = entry.enabled === false;
    const words = (entry.triggers ?? []).join(", ");
    return el("button", {
      class: `mmc-wears-row mmc-wears-lora${off ? " off" : ""}`,
      title: t("{name} — press to change its words or its weight, mute it, or take it off them.",
               { name: entry.name }),
      onclick: (event) => this.host.loraMenu(event.currentTarget, subject, family, entry),
    }, [
      el("div", { class: "mmc-wears-row-what" }, [
        el("span", { class: "mmc-wears-row-lead mono", text: loraBase(entry) }),
        el("span", { class: "mmc-wears-row-note",
                     text: words ? t("trigger words {words}", { words }) : t("no trigger words") }),
      ]),
      el("span", { class: "mmc-wears-weight" }, [
        el("b", { text: Number(entry.strength ?? 1).toFixed(2) }),
        el("span", { text: off ? t("muted") : t("weight") }),
      ]),
    ]);
  }

  /** The one fact about this family that changes what to do. */
  status(subject, family, entries, mode) {
    const busy = this.host.busy();
    const note = this.host.note(subject);
    const line = el("div", { class: "mmc-wears-status" });
    const say = (text, cls = "") => line.appendChild(el("span", { class: cls, text }));
    const act = (text, onclick, cls = "") => line.appendChild(el("button", {
      class: `mmc-wears-act ${cls}`.trim(), onclick }, [el("span", { text })]));
    const onKnown = () => this.host.redraw();
    const stills = entries.filter((entry) => entry.kind !== "video");
    const canSave = this.host.canSave();

    if (busy && (busy.family?.id ?? this.host.families()[0]?.id) === family.id) {
      line.classList.add("busy");
      say(t(busy.remake ? (busy.count === 1 ? "Re-encoding {count} RefMod…" : "Re-encoding {count} RefMods…")
            : busy.mode === "stack" ? "Stacking {count} files into one…"
            : busy.count === 1 ? "Encoding {count} picture…" : "Encoding {count} pictures…", { count: busy.count }), "amber");
      line.appendChild(el("span", { class: "mmc-wears-bar" },
                          [el("i", { style: { width: `${Math.round((busy.progress ?? 0) * 100)}%` } })]));
    } else if (mode === "needs-adapter") {
      say("⚠", "warn");
      say(t("{family} only reads pictures through its reference adapter. Hang it on them and their pictures go through.",
            { family: t(family.label) }));
      act(t("Hang the adapter"), () => this.host.hangLora(subject, family, null));
    } else if (!family.reads.pictures) {
      say(t("{family} takes no reference pictures. Their description is all it can be told.", { family: t(family.label) }));
    } else if (!stills.length && !entries.length) {
      say(t("No pictures behind them — their description is what {family} gets.", { family: t(family.label) }));
    } else if (mode === "words") {
      say(t("Their description alone is sent. Their pictures stay for the other families.", { family: t(family.label) }));
    } else if (!family.refmod) {
      say("✓", "ok");
      say(t("{family} reads their pictures directly. Nothing to save; nothing to set up.", { family: t(family.label) }));
    } else {
      const c = cost(entries, this.host.canvas?.(), onKnown, family.space);
      const mods = entries.map((entry) => modIn(entry, family.space)).filter(Boolean)
        .map((path) => modRow(path, onKnown)).filter(Boolean);
      const fresh = c.pictures + c.clips;
      if (c.missing.length) {
        // A rendition whose file has gone: the render refuses it by name, and
        // until it is forgotten nothing here can be saved over it.
        say("⚠", "warn");
        say(t(c.missing.length === 1
          ? "{count} saved reference for {family} is not in models/refmods any more — the render will refuse it."
          : "{count} saved references for {family} are not in models/refmods any more — the render will refuse them.",
              { count: c.missing.length, family: t(family.label) }));
        if (this.host.clear) {
          act(t("Forget the missing"), () => this.host.clear(subject, family, c.missing), "amber");
        }
      } else if (mode === "saved" || (!fresh && c.mods)) {
        say("✓", "ok");
        const modes = [...new Set(c.rows.map(modeWord))].join("/");
        say(t(c.mods === 1 ? "Saved as a RefMod for {family} · {mode} · {tokens} tokens"
                           : "Saved as {count} RefMods for {family} · {mode} · {tokens} tokens",
              { count: c.mods, family: t(family.label), mode: modes || "…",
                tokens: c.exact ? c.modTokens.toLocaleString() : "…" }));
        this.modsAct(act, subject, family, entries, mods, canSave);
        if (this.host.library && mods[0]) act(t("Show in library"), () => this.host.library(mods[0].path), "quiet");
      } else if (c.mods && fresh) {
        say(t("{mods} saved, {fresh} encoded every render — ≈{tokens} tokens.",
              { mods: c.mods, fresh, tokens: shortTokens(c.picTokens + c.modTokens) }));
        if (canSave) act(t("Save the rest ▾"), (event) => this.saveOne(event.currentTarget, subject, family, entries), "amber");
        this.modsAct(act, subject, family, entries, mods, canSave);
        if (S.sendFor(subject, family.id) !== "saved") {
          act(t("Use the saved ones"), () => { S.wearOn(subject, family.id).send = "saved"; this.host.commit(); this.host.redraw(); }, "quiet");
        }
      } else if (mode === "pictures" && c.mods) {
        say(t("A saved reference exists for {family} but the pictures are sent instead.", { family: t(family.label) }));
        act(t("Use the saved one"), () => { S.wearOn(subject, family.id).send = "saved"; this.host.commit(); this.host.redraw(); });
        this.modsAct(act, subject, family, entries, mods, canSave);
      } else {
        const what = [c.pictures ? t(c.pictures === 1 ? "{count} picture" : "{count} pictures", { count: c.pictures }) : null,
                      c.clips ? t(c.clips === 1 ? "{count} clip" : "{count} clips", { count: c.clips }) : null]
          .filter(Boolean).join(" + ");
        say(t("{what} encoded every render — ≈{tokens} tokens. Saving them once reads the file instead.",
              { what, tokens: shortTokens(c.picTokens) + (c.clips ? "+" : "") }));
        if (canSave) act(t("Save for {family} ▾", { family: t(family.label) }),
                        (event) => this.saveOne(event.currentTarget, subject, family, entries), "amber");
      }
    }
    if (note) line.appendChild(el("span", { class: "mmc-wears-note", text: note }));
    return line;
  }

  /** The saved references' own menu: encode them again — in the other mode,
   *  or the same one from the picture — or forget them and start over. Drawn
   *  wherever a member has saved references for this family, whole or in
   *  part; forgetting needs no VAE, so it is offered where encoding is not. */
  modsAct(act, subject, family, entries, mods, canSave) {
    const remake = canSave
      ? remakeRows(mods, (remode, paths) => this.host.remake(subject, remode, paths, family)) : [];
    // Only a rendition hung on a picture can be forgotten: a look that *is*
    // a mod — imported, or a stack — is taken off from its tile instead.
    const hung = entries.some((entry) => entry?.mods?.[family.space]);
    const forget = this.host.clear && hung ? [{
      label: t("Forget the saved references"),
      note: t("Their pictures are sent to {family} again, and can be saved afresh. The files "
            + "stay in models/refmods, where other pieces may still use them — delete them "
            + "from the library.", { family: t(family.label) }),
      onPick: () => this.host.clear(subject, family, null),
    }] : [];
    if (!remake.length && !forget.length) return;
    act(t(remake.length ? "Re-encode ▾" : "Saved references ▾"), (event) => openMenu(event.currentTarget, {
      title: t("@{handle}'s saved references for {family}", { handle: subject.handle, family: t(family.label) }),
      sections: [...(remake.length ? [{ head: t("Encode again"), rows: remake }] : []),
                 ...(forget.length ? [{ head: t("Start over"), rows: forget }] : [])],
    }), "quiet");
  }

  saveOne(anchor, subject, family, entries) {
    const sources = entries.filter((entry) => !S.isRefMod(entry));
    openMenu(anchor, {
      title: t("Save for {family}", { family: t(family.label) }),
      sections: [{ rows: familyModeRows(sources, family, (mode, one) => this.host.save(subject, mode, one),
                                        () => this.host.redraw()) }],
    });
  }
}


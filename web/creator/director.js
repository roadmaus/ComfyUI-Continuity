// Director's plan card, and the arithmetic it draws from.
//
// A plan is a small document of typed rows (`creator/director.py`): the beats,
// who and what is in the piece, and the shot list. The model writes the words
// and code writes the numbers — how many seconds each beat and shot gets, where
// a shot over the limit is cut into continuation clips, and what the run will
// render in what order. This module draws that document as a card in the chat's
// transcript, and lets the person change it in place.
//
// **The numbers are worked out here as well as on the server.** `allot`,
// `allotPlan`, `clips` and `rows` below are `director.py`'s, line for line,
// under `tests/test_director_mirror.py`, the deal `state.js` has with
// `compile.py`. That is what lets a weight changed on the card show its new
// seconds at once. What is *allowed* is not mirrored: an edit goes to
// `director/edit`, which holds a typed change to the same readers a model's
// reply went through, and the card shows the plan that comes back or the
// sentence that refused it. Python is authoritative.
//
// **The card is the plan's only editor.** The plan lives on the assistant
// message that drew it and is saved with the chat (`chatstore.js`). A chat
// holds one live plan; a card whose plan was replaced by a later brief stays
// in the transcript as a record, drawn but not editable.

import { el, icon } from "./dom.js";
import { t } from "./i18n.js";

// ---- the rules, mirrored ---------------------------------------------------------

/** A beat's rough share of the piece (`director.WEIGHTS`). */
export const WEIGHTS = { short: 1, medium: 2, long: 3 };
export const CONTINUES = ["cut", "pin", "new"];
export const KINDS = ["person", "place", "thing"];
export const SHOT_LIMIT = 15;
export const MIN_SECONDS = 1;
const PREP = "prep";
const RUN = "run";
const CITE_RE = /@([A-Za-z][A-Za-z0-9_]*)\b(?!-)/g;

/** The sentence a refusal is said in. `director.PlanError`'s counterpart. */
export class PlanError extends Error {}

/** Share `total` whole seconds out by `weights` -> a list that sums to it.
 *  Largest remainder, floors lifted, as `director.allot`. */
export function allot(total, weights, floors = null) {
  const count = weights.length;
  if (!count) return [];
  floors = floors ? [...floors] : Array(count).fill(MIN_SECONDS);
  const floorSum = floors.reduce((a, b) => a + b, 0);
  if (total < floorSum) {
    throw new PlanError(`${total} seconds cannot hold ${count} parts of at least `
      + `${Math.max(...floors)} seconds each; make it longer or use fewer shots.`);
  }
  const weightSum = weights.reduce((a, b) => a + b, 0);
  const sum = weightSum || count;
  const exact = weights.map((w) => (weightSum ? total * (w || 0) / sum : total / count));
  const out = exact.map((x, i) => Math.max(floors[i], Math.floor(x)));
  const total_ = () => out.reduce((a, b) => a + b, 0);
  const argmax = (indices, key) => {
    let best = null;
    let bestKey = null;
    for (const i of indices) {
      const k = key(i);
      if (best === null || compare(k, bestKey) > 0) { best = i; bestKey = k; }
    }
    return best;
  };
  const all = [...Array(count).keys()];
  while (total_() < total) out[argmax(all, (i) => [exact[i] - out[i], -i])] += 1;
  while (total_() > total) {
    const over = all.filter((i) => out[i] > floors[i]);
    out[argmax(over, (i) => [out[i] - exact[i], out[i], -i])] -= 1;
  }
  return out;
}

/** Python's tuple comparison, for `max(key=...)`: the first index that
 *  differs decides. Python's `max` keeps the first of equal keys, and so does
 *  `argmax` above by only taking a strictly greater one. */
function compare(a, b) {
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) return a[i] > b[i] ? 1 : -1;
  }
  return 0;
}

/** The longest one clip may run: the plan's limit, under the rail's video
 *  family's own ceiling. */
export function limitOf(plan) {
  const ceiling = plan.rail?.max_seconds;
  const limit = Math.trunc(Number(plan.shot_limit) || SHOT_LIMIT);
  return ceiling ? Math.max(1, Math.min(limit, Math.trunc(ceiling))) : limit;
}

/** The shortest one clip may run: the rail's video family's floor. */
export function floorOf(plan) {
  return Math.max(MIN_SECONDS, Math.ceil(plan.rail?.min_seconds || MIN_SECONDS));
}

/** `{beat id: seconds, shot id: seconds}`, adding up to the plan's length. */
export function allotPlan(plan) {
  const floor = floorOf(plan);
  const beats = plan.beats ?? [];
  const shotsOf = (beat) => plan.shots.filter((s) => s.beat === beat.id);
  const counts = beats.map((b) => shotsOf(b).length);
  const beatSeconds = allot(Math.trunc(plan.seconds), beats.map((b) => WEIGHTS[b.weight] ?? 2),
                            counts.map((c) => Math.max(1, c) * floor));
  const out = {};
  beats.forEach((beat, at) => {
    out[beat.id] = beatSeconds[at];
    const count = counts[at];
    const shares = count ? allot(beatSeconds[at], Array(count).fill(1), Array(count).fill(floor)) : [];
    shotsOf(beat).forEach((shot, i) => { out[shot.id] = shares[i]; });
  });
  return out;
}

/** The clips the run renders, in strip order -> `[{id, shot, part, parts,
 *  seconds, continues}]`. A shot over the limit is cut into parts, every one
 *  after the first a `pin` of the one before. */
export function clips(plan) {
  const seconds = allotPlan(plan);
  const limit = limitOf(plan);
  const floor = floorOf(plan);
  const out = [];
  for (const shot of plan.shots) {
    const total = seconds[shot.id];
    const parts = Math.max(1, Math.ceil(total / limit));
    const shares = parts > 1 ? allot(total, Array(parts).fill(1), Array(parts).fill(floor)) : [total];
    shares.forEach((share, i) => {
      const at = i + 1;
      out.push({ id: parts === 1 ? shot.id : `${shot.id}.${at}`, shot: shot.id, part: at, parts,
                 seconds: share, continues: at === 1 ? shot.continues : "pin" });
    });
  }
  if (out.length) out[0].continues = "new";
  return out;
}

const entityNamed = (plan, name) =>
  plan.entities.find((e) => e.name === String(name).toLowerCase()) ?? null;

const renders = (entity) => "new" in (entity.source ?? {});

function citedEntities(plan, text) {
  const out = [];
  for (const match of String(text ?? "").matchAll(CITE_RE)) {
    const entity = entityNamed(plan, match[1]);
    if (entity && !out.includes(entity)) out.push(entity);
  }
  return out;
}

/** Every renderable row, in the order it may render — `director.rows`. */
export function rows(plan) {
  const out = [];
  for (const entity of plan.entities) {
    if (renders(entity)) out.push({ id: entity.id, kind: "sheet", phase: PREP, entity: entity.id, deps: [] });
  }
  const shots = Object.fromEntries(plan.shots.map((s) => [s.id, s]));
  const keyframePhase = plan.keyframes ?? true ? PREP : RUN;
  let previous = null;
  const clipRows = [];
  for (const clip of clips(plan)) {
    const shot = shots[clip.shot];
    const sheets = citedEntities(plan, shot.action).filter(renders).map((e) => e.id);
    const deps = [...sheets];
    if (clip.part === 1 && (clip.continues === "cut" || clip.continues === "new")) {
      const key = `kf.${clip.id}`;
      out.push({ id: key, kind: "keyframe", phase: keyframePhase, clip: clip.id, shot: shot.id,
                 deps: [...sheets] });
      deps.push(key);
    }
    if (previous) deps.push(previous);
    clipRows.push({ id: clip.id, kind: "clip", phase: RUN, clip: clip.id, shot: shot.id,
                    seconds: clip.seconds, continues: clip.continues, deps });
    previous = clip.id;
  }
  return [...out, ...clipRows];
}

// ---- the card ------------------------------------------------------------------

/** What the card says about a plan's arithmetic, or the sentence that says
 *  why there is none. A plan the server validated always has one; a plan read
 *  back from a hand-edited file may not, and the card still draws its words. */
function arithmetic(plan) {
  try {
    return { seconds: allotPlan(plan), clips: clips(plan), rows: rows(plan), error: null };
  } catch (error) {
    return { seconds: {}, clips: [], rows: [], error: String(error.message || error) };
  }
}

// What the card calls the plan's words. Their own keys, because the bare words
// are already translated elsewhere in the pack with other meanings ("medium"
// is a kind of file there).
const WEIGHT_LABEL = { short: "Short beat", medium: "Medium beat", long: "Long beat" };
const JOIN_LABEL = { new: "New scene", cut: "New angle", pin: "Carries on" };
const KIND_LABEL = { person: "Person", place: "Place", thing: "Thing" };

const JOIN_HELP = {
  new: "A real cut: a time skip or a new scene.",
  cut: "The same moment, from a new camera angle.",
  pin: "The same camera, carrying straight on.",
};

const SOURCE_HELP = {
  person: "A character sheet will be made for them to approve.",
  place: "An establishing view will be made to approve.",
  thing: "A reference picture will be made to approve.",
};

/**
 * A piece of text the person can change by pressing it.
 *
 * Shown as text, so a plan reads as a plan rather than as a form; pressed, it
 * is a textarea the size of what it held. Enter (without Shift) or leaving it
 * keeps the change, Escape drops it. The commit is deferred a tick on blur: the
 * room repaints the transcript while renders run, and a repaint that takes the
 * focus away and gives it straight back (`chat.js paintLog`) is not the person
 * leaving the field.
 */
function editable(value, { live, onCommit, cls = "", multiline = true, placeholder = "", label = "" }) {
  const shown = el("span", {
    class: `mmc-dr-text ${cls}${value ? "" : " empty"}`,
    text: value || placeholder,
    title: live ? t("Press to change") : null,
    tabindex: live ? "0" : null,
    role: live ? "button" : null,
    "aria-label": live && label ? label : null,
  });
  if (!live) return shown;
  const start = () => {
    const area = el(multiline ? "textarea" : "input", {
      class: `mmc-dr-input ${cls}`, rows: multiline ? "1" : null, "aria-label": label || null,
    });
    area.value = value;
    let done = false;
    const finish = (keep) => {
      if (done) return;
      done = true;
      const next = area.value.replace(/\s+/g, " ").trim();
      area.replaceWith(shown);
      if (keep && next !== value) onCommit(next);
    };
    const fit = () => {
      if (!multiline) return;
      area.style.height = "auto";
      area.style.height = `${area.scrollHeight}px`;
    };
    area.addEventListener("input", fit);
    area.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); finish(true); }
      else if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); finish(false); }
    });
    area.addEventListener("blur", () => setTimeout(() => {
      if (area.isConnected && document.activeElement === area) return;
      finish(true);
    }, 0));
    shown.replaceWith(area);
    area.focus();
    area.setSelectionRange(area.value.length, area.value.length);
    fit();
  };
  shown.addEventListener("click", start);
  shown.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); start(); }
  });
  return shown;
}

/** A small choice — a weight, a join — as a native select over its words. */
function choice(value, options, { live, onCommit, label, words, help = {} }) {
  const say = (word) => t(words[word] ?? word);
  if (!live) return el("span", { class: "mmc-dr-tag", text: say(value), title: help[value] ? t(help[value]) : null });
  const select = el("select", {
    class: "mmc-dr-select", "aria-label": label, title: help[value] ? t(help[value]) : label,
    onchange: () => { if (select.value !== value) onCommit(select.value); },
  }, options.map((option) => el("option", { value: option, text: say(option) })));
  select.value = value;
  return select;
}

const seconds = (n) => (Number.isFinite(n) ? t("{n} s", { n }) : "—");

/** A shot's clips, said: "2 clips: 8 s + 7 s", only where it was cut. */
function partsOf(shot, made) {
  const parts = made.filter((c) => c.shot === shot.id);
  if (parts.length < 2) return null;
  return el("span", {
    class: "mmc-dr-parts",
    title: t("Longer than one clip can run, so the run carries it on in parts with the camera held."),
    text: t("{count} clips: {parts}", { count: parts.length,
                                         parts: parts.map((c) => seconds(c.seconds)).join(" + ") }),
  });
}

/** An entity's source, said: who plays them, or what will be made. */
function sourceOf(entity) {
  const cited = entity.source?.cited;
  if (cited) {
    return el("span", { class: "mmc-dr-source cited", text: t("cast: @{name}", { name: cited }),
                        title: t("Somebody you cited, used as they are.") });
  }
  return el("span", { class: "mmc-dr-source", text: t("to make"), title: t(SOURCE_HELP[entity.kind] ?? "") });
}

/**
 * The piece's length drawn to scale: a strip the width of the card, cut into
 * the beats, each beat into its shots, each shot into the clips the run will
 * make of it. It is the arithmetic above made visible, so a weight changed on a
 * beat moves the cuts on the strip before the server answers, and a shot too
 * long for one clip shows its seam. A strip and not a chart because the thing
 * it stands for is an editor's timeline, read left to right at one glance.
 * Pointing at a shot on the strip lights its row in the list and the other way
 * round (`linkShots`); it is drawn for eyes only, since every number on it is
 * also in the list as text.
 */
function strip(doc, sums) {
  if (sums.error || !sums.clips.length) return null;
  return el("div", { class: "mmc-dr-strip", "aria-hidden": "true" }, doc.beats.map((beat, at) => {
    const shots = doc.shots.filter((shot) => shot.beat === beat.id);
    return el("div", { class: "mmc-dr-sbeat", style: { flexGrow: String(sums.seconds[beat.id] || 1) } }, [
      el("div", { class: "mmc-dr-sbar" }, shots.map((shot) => el("div", {
        class: "mmc-dr-sshot", "data-shot": shot.id, title: shot.action,
        style: { flexGrow: String(sums.seconds[shot.id] || 1) },
      }, sums.clips.filter((c) => c.shot === shot.id).map((c) => el("span", {
        class: "mmc-dr-sclip", style: { flexGrow: String(c.seconds) },
      }))))),
      el("div", { class: "mmc-dr-slabel" }, [
        el("span", { class: "mmc-dr-num", text: String(at + 1) }),
        el("span", { text: seconds(sums.seconds[beat.id]) }),
      ]),
    ]);
  }));
}

/** A shot pointed at, on the strip or in the list, lit in both places. */
function linkShots(card) {
  const light = (id) => {
    for (const node of card.querySelectorAll("[data-shot]")) node.classList.toggle("hot", node.dataset.shot === id);
  };
  card.addEventListener("pointerover", (event) => light(event.target.closest?.("[data-shot]")?.dataset.shot ?? null));
  card.addEventListener("pointerleave", () => light(null));
  return card;
}

/**
 * The plan, as a card in the transcript.
 *
 * `plan` is the message's `{doc, warnings, pending, error}`: the document, the
 * doubts the planning calls kept rather than threw away, an edit on its way to
 * the server, and the sentence the last one was refused with. `hooks.live`
 * says whether this is the chat's plan (editable) or a record of one replaced
 * since; `hooks.edit(row, fields)` sends one row's change; `hooks.family(id)`
 * names a family for the rail line.
 */
export function planCard(plan, hooks = {}) {
  const doc = plan.doc;
  const live = Boolean(hooks.live) && !plan.pending;
  const sums = arithmetic(doc);
  const edit = (row, fields) => hooks.edit?.(row, fields);
  const family = hooks.family ?? ((id) => id);

  const header = el("div", { class: "mmc-dr-head" }, [
    el("div", { class: "mmc-dr-titleline" }, [
      el("span", { class: "mmc-dr-mark", title: t("Plan") }, [icon("clapperboard", 16)]),
      editable(doc.title, { live, cls: "mmc-dr-title", multiline: false, label: t("Title"),
                            onCommit: (title) => edit("header", { title }) }),
    ]),
    el("div", { class: "mmc-dr-facts" }, [
      live
        ? el("label", { class: "mmc-dr-length", title: t("How long the whole piece runs, in seconds.") }, [
            el("input", {
              class: "mmc-dr-number", type: "number", min: "1", max: "600", step: "1",
              value: String(doc.seconds), "aria-label": t("Length in seconds"),
              onchange: (event) => {
                const next = Math.round(Number(event.target.value));
                if (Number.isFinite(next) && next !== doc.seconds) edit("header", { seconds: next });
              },
            }),
            el("span", { class: "mmc-dr-unit", text: t("seconds") }),
          ])
        : el("span", { text: seconds(doc.seconds) }),
      el("span", { text: t("{count} shots", { count: doc.shots.length }) }),
      sums.clips.length !== doc.shots.length
        ? el("span", { class: "mmc-dr-quiet", text: t("({count} clips)", { count: sums.clips.length }) })
        : null,
      el("span", {
        class: "mmc-dr-quiet mmc-dr-rail",
        title: t("The families this plan renders on: the room's still and video choices when it was made."),
        text: [family(doc.rail?.still), family(doc.rail?.video), doc.rail?.aspect].filter(Boolean).join(" · "),
      }),
    ].filter(Boolean)),
    el("div", { class: "mmc-dr-look" }, [
      el("span", { class: "mmc-dr-key", text: t("Look") }),
      editable(doc.look, { live, placeholder: t("No look — the rail's style applies."),
                           label: t("Look"), onCommit: (look) => edit("header", { look }) }),
    ]),
    doc.assumptions?.length
      ? el("div", { class: "mmc-dr-assumed" }, [
          el("span", { class: "mmc-dr-key", text: t("Assumed") }),
          el("ul", {}, doc.assumptions.map((line) => el("li", { text: line }))),
        ])
      : null,
  ].filter(Boolean));

  const beats = el("div", { class: "mmc-dr-section" }, [
    el("div", { class: "mmc-dr-heading", text: t("Beats and shots") }),
    ...doc.beats.map((beat, at) => el("div", { class: "mmc-dr-beat" }, [
      el("div", { class: "mmc-dr-beatline" }, [
        el("span", { class: "mmc-dr-num", text: String(at + 1) }),
        editable(beat.text, { live, label: t("Beat {n}", { n: at + 1 }),
                              onCommit: (text) => edit(beat.id, { text }) }),
        choice(beat.weight, Object.keys(WEIGHTS), {
          live, label: t("How much of the piece this beat takes"), words: WEIGHT_LABEL,
          onCommit: (weight) => edit(beat.id, { weight }),
        }),
        el("span", { class: "mmc-dr-secs", text: seconds(sums.seconds[beat.id]) }),
      ]),
      ...doc.shots.filter((shot) => shot.beat === beat.id).map((shot) => el("div", { class: "mmc-dr-shot", "data-shot": shot.id }, [
        doc.shots[0] === shot
          ? el("span", { class: "mmc-dr-tag", text: t(JOIN_LABEL.new), title: t("The first shot opens the piece.") })
          : choice(shot.continues, CONTINUES, {
              live, label: t("How this shot follows the one before"), help: JOIN_HELP, words: JOIN_LABEL,
              onCommit: (continues) => edit(shot.id, { continues }),
            }),
        el("div", { class: "mmc-dr-action" }, [
          editable(shot.action, { live, label: t("Shot"), onCommit: (action) => edit(shot.id, { action }) }),
          partsOf(shot, sums.clips),
        ].filter(Boolean)),
        el("span", { class: "mmc-dr-secs", text: seconds(sums.seconds[shot.id]) }),
      ])),
    ])),
  ]);

  const entities = doc.entities.length
    ? el("div", { class: "mmc-dr-section" }, [
        el("div", { class: "mmc-dr-heading", text: t("Who and what") }),
        ...doc.entities.map((entity) => el("div", { class: "mmc-dr-entity" }, [
          el("span", { class: "mmc-dr-name", text: `@${entity.name}` }),
          el("span", { class: "mmc-dr-tag", text: t(KIND_LABEL[entity.kind] ?? entity.kind) }),
          sourceOf(entity),
          entity.source?.cited
            ? el("span", { class: "mmc-dr-text empty" })
            : editable(entity.description, { live, label: t("What @{name} looks like", { name: entity.name }),
                                             onCommit: (description) => edit(entity.id, { description }) }),
        ])),
      ])
    : null;

  const sheets = sums.rows.filter((r) => r.kind === "sheet").length;
  const frames = sums.rows.filter((r) => r.kind === "keyframe" && r.phase === PREP).length;
  const foot = el("div", { class: "mmc-dr-foot" }, [
    el("label", {
      class: "mmc-dr-check",
      title: t("An opening still for every shot that does not carry straight on, to approve before any video is made. Off, the run makes them unseen."),
    }, [
      el("input", {
        type: "checkbox", checked: doc.keyframes !== false, disabled: live ? null : true,
        onchange: (event) => edit("header", { keyframes: event.target.checked }),
      }),
      el("span", { text: t("Storyboard first") }),
    ]),
    el("span", { class: "mmc-bn-gap" }),
    el("span", {
      class: "mmc-dr-quiet",
      text: sheets + frames
        ? t("{prep} to approve, then {clips} clips", { prep: sheets + frames, clips: sums.clips.length })
        : t("{clips} clips to render", { clips: sums.clips.length }),
    }),
  ]);

  const notes = [
    ...(plan.warnings ?? []).map((line) => el("div", { class: "mmc-dr-warn", text: line })),
    sums.error ? el("div", { class: "mmc-dr-error", text: sums.error }) : null,
    plan.error ? el("div", { class: "mmc-dr-error", role: "alert", text: plan.error }) : null,
    hooks.live ? null : el("div", { class: "mmc-dr-quiet", text: t("Replaced by a later plan.") }),
  ].filter(Boolean);

  return linkShots(el("div", {
    class: `mmc-ch-msg mmc-ch-bot mmc-dr-card${hooks.live ? "" : " mmc-dr-old"}${plan.pending ? " busy" : ""}`,
    "aria-busy": plan.pending ? "true" : null,
  }, [header, strip(doc, sums), beats, entities, ...notes, foot].filter(Boolean)));
}

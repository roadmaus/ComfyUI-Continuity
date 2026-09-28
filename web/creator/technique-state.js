// Technique prose is ordinary prompt text, not another compiler language.
// Keep provenance beside it so a chip can remove only text this tool wrote.
// A manual edit invalidates automatic removal rather than guessing which
// matching words belong to us. None of this module reads files or owns UI.

const VERSION = 1;
const undoHistory = new WeakMap();
const MAX_UNDO = 20;
const copy = (value) => value === undefined ? undefined : JSON.parse(JSON.stringify(value));
const validOwner = (owner) => !!owner && typeof owner === "object" && !Array.isArray(owner);
const textOf = (owner) => typeof owner?.prompt === "string" ? owner.prompt : "";
const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);

export const TECHNIQUE_WARNINGS = Object.freeze({
  original: "The original example may specify its own people, places and timing. Review it before applying.",
  guidance: "This is the source's prompt guidance, not a scene-specific rewrite. Edit the preview to fit your shot.",
  missing: "No prompt guidance is available for this technique. Use the original example or write your own instruction.",
  placeholders: "Some source placeholders are still present. Fill them in before applying.",
  duration: "This text contains a duration. Check that it matches your segment; applying it does not change segment length.",
  transition: "This technique may need two shots or editing. Applying text does not change segment boundaries or seam settings.",
  subject: "Choose a valid existing @handle before replacing the subject placeholder.",
});

/** Preserve source wording. Only unmistakable placeholders, and only explicit
 *  user choices, are substituted. Original mode is always a verbatim copy. */
export function buildTechniqueText(detail, { mode = "technique", subject = "", duration = null } = {}) {
  const warnings = [];
  const prompt = detail?.prompt ?? {};
  let text = "";
  if (mode === "original") {
    text = typeof prompt.example === "string" ? prompt.example : "";
    if (text.trim()) warnings.push(TECHNIQUE_WARNINGS.original);
  } else {
    text = (Array.isArray(prompt.guidance) ? prompt.guidance : [])
      .filter((part) => typeof part === "string" && part.trim()).join("\n\n");
    warnings.push(text.trim() ? TECHNIQUE_WARNINGS.guidance : TECHNIQUE_WARNINGS.missing);
    if (subject) {
      // Handle spelling is the user's choice; never invent @subject simply
      // because a catalogue entry happens to mention a person.
      if (/^@[\p{L}\p{N}_-]+$/u.test(subject)) {
        text = text.replace(/\[\s*subject\s*\]|\{\{?\s*subject\s*\}?\}/gi, () => subject);
      } else warnings.push(TECHNIQUE_WARNINGS.subject);
    }
    if (typeof duration === "number" && Number.isFinite(duration) && duration > 0) {
      text = text.replace(/\[\s*duration\s*\]|\{\{?\s*duration\s*\}?\}/gi, () => String(duration));
    }
  }
  if (/\[[^\]\n]{1,100}\]|\{\{?[^{}\n]{1,100}\}?\}/.test(text)) warnings.push(TECHNIQUE_WARNINGS.placeholders);
  if (/\b\d+(?:\.\d+)?\s*(?:s\b|sec(?:ond)?s?\b)|\b\d+(?:\.\d+)?-seconds?\b/i.test(text)) {
    warnings.push(TECHNIQUE_WARNINGS.duration);
  }
  if (/edit|transition/i.test(`${detail?.categoryId ?? ""} ${detail?.categoryTitle ?? ""}`)) {
    warnings.push(TECHNIQUE_WARNINGS.transition);
  }
  return { text, warnings: [...new Set(warnings)] };
}

/** Read untrusted workflow metadata without retaining unknown fields. Stale
 *  records are deliberately kept as provenance, never as removable spans. */
function tracking(owner) {
  const raw = owner?.techniques;
  if (!raw || raw.version !== VERSION || typeof raw.source !== "string" || !Array.isArray(raw.items)) {
    return { version: VERSION, source: textOf(owner), items: [] };
  }
  const ids = new Set();
  const items = [];
  for (const item of raw.items) {
    if (!item || typeof item.id !== "string" || !item.id || ids.has(item.id)
        || typeof item.text !== "string" || !item.text.trim()) continue;
    ids.add(item.id);
    const prefix = typeof item.prefix === "string" && /^\n{0,2}$/.test(item.prefix) ? item.prefix : "";
    const start = Number.isSafeInteger(item.start) && item.start >= 0 ? item.start : -1;
    const end = Number.isSafeInteger(item.end) && item.end >= start ? item.end : -1;
    const exact = start >= 0 && end === start + prefix.length + item.text.length
      && raw.source.slice(start, end) === prefix + item.text;
    items.push({ id: item.id, title: typeof item.title === "string" ? item.title : item.id,
      mode: item.mode === "original" ? "original" : "technique", text: item.text,
      prefix, start, end, stale: item.stale === true || !exact || raw.source !== textOf(owner),
      ...(typeof item.sourceUrl === "string" ? { sourceUrl: item.sourceUrl } : {}),
    });
  }
  // Corrupt overlapping spans cannot both be owned. Refuse automatic edits
  // to all participants, even when their individual substrings look valid.
  const overlapping = new Set();
  for (let i = 0; i < items.length; i++) {
    for (let j = i + 1; j < items.length; j++) {
      if (!items[i].stale && !items[j].stale
          && items[i].start < items[j].end && items[j].start < items[i].end) {
        overlapping.add(i);
        overlapping.add(j);
      }
    }
  }
  for (const index of overlapping) items[index].stale = true;
  return { version: VERSION, source: raw.source, items };
}

export function getAppliedTechniques(owner) {
  return tracking(owner).items.map((item) => ({ ...item }));
}

/** Used by the existing state serializers. No field for workflows which have
 *  never used the library; no media or catalogue pages inside creator_data. */
export function serializeTechniques(owner) {
  const state = tracking(owner);
  return state.items.length ? { techniques: copy(state) } : {};
}

export function activeRefinement(owner) {
  const refined = owner?.refined;
  return !!refined && typeof refined === "object" && refined.enabled !== false
    && ((typeof refined.body === "string" && !!refined.body.trim())
      || (refined.sections && typeof refined.sections === "object" && Object.keys(refined.sections).length > 0));
}

function refinementGuard(owner, allowRefined) {
  return activeRefinement(owner) && !allowRefined
    ? { ok: false, reason: "refined-active", requiresRefineAcknowledgement: true } : null;
}

function snapshot(owner) {
  return { prompt: textOf(owner), hadPrompt: own(owner, "prompt"), techniques: copy(owner.techniques),
    hadTechniques: own(owner, "techniques"), refined: copy(owner.refined), hadRefined: own(owner, "refined") };
}

function remember(owner, before, changedRefined) {
  const history = undoHistory.get(owner) ?? [];
  history.push({ before, afterPrompt: textOf(owner), afterTechniques: JSON.stringify(owner.techniques),
    changedRefined, afterRefined: JSON.stringify(owner.refined) });
  undoHistory.set(owner, history.slice(-MAX_UNDO));
}

function write(owner, prompt, items, before, allowRefined) {
  const changedRefined = allowRefined && activeRefinement(owner);
  owner.prompt = prompt;
  if (items.length) owner.techniques = { version: VERSION, source: prompt, items };
  else delete owner.techniques;
  // Do not erase a rewrite, its source, analysis sections or Revert backup.
  // An acknowledged application selects the user's editable prompt instead.
  if (changedRefined) owner.refined.enabled = false;
  remember(owner, before, changedRefined);
  return { ok: true, warnings: [], ...(changedRefined ? { refinedDisabled: true } : {}) };
}

function shifted(items, removed, change) {
  return items.map((item) => item.id !== removed && !item.stale && item.start >= change.end
    ? { ...item, start: item.start + change.delta, end: item.end + change.delta } : { ...item });
}

/** Append or replace this catalogue entry's last exact tracked block. Never
 *  replace the whole prompt, audio, settings, source handles or seam state. */
export function applyTechnique(owner, { item, text, mode = "technique", allowRefined = false } = {}) {
  if (!validOwner(owner)) return { ok: false, reason: "invalid-target" };
  if (owner.prompt != null && typeof owner.prompt !== "string") return { ok: false, reason: "invalid-target" };
  if (!item || typeof item.id !== "string" || !item.id.trim()) return { ok: false, reason: "invalid-technique" };
  if (typeof text !== "string" || !text.trim()) return { ok: false, reason: "empty-text" };
  const state = tracking(owner);
  const previous = state.items.find((entry) => entry.id === item.id);
  if (previous?.stale) return { ok: false, reason: "text-changed" };
  const guard = refinementGuard(owner, allowRefined);
  if (guard) return guard;
  const prompt = textOf(owner);
  const before = snapshot(owner);
  const title = typeof item.title === "string" && item.title ? item.title : item.id;
  const common = { id: item.id, title, mode: mode === "original" ? "original" : "technique", text,
    stale: false, ...(typeof item.sourceUrl === "string" ? { sourceUrl: item.sourceUrl } : {}) };
  if (previous) {
    const replacement = previous.prefix + text;
    const next = prompt.slice(0, previous.start) + replacement + prompt.slice(previous.end);
    const items = shifted(state.items, previous.id, { end: previous.end, delta: replacement.length - (previous.end - previous.start) })
      .map((entry) => entry.id === previous.id
        ? { ...common, prefix: previous.prefix, start: previous.start, end: previous.start + replacement.length } : entry);
    if (next === prompt && previous.title === common.title && previous.mode === common.mode
        && previous.sourceUrl === common.sourceUrl && !activeRefinement(owner)) {
      return { ok: true, unchanged: true, warnings: [] };
    }
    return write(owner, next, items, before, allowRefined);
  }
  const prefix = !prompt || prompt.endsWith("\n\n") ? "" : prompt.endsWith("\n") ? "\n" : "\n\n";
  const next = prompt + prefix + text;
  const added = { ...common, prefix, start: prompt.length, end: next.length };
  return write(owner, next, [...state.items, added], before, allowRefined);
}

export function removeTechnique(owner, id, { allowRefined = false } = {}) {
  if (!validOwner(owner)) return { ok: false, reason: "invalid-target" };
  const state = tracking(owner);
  const entry = state.items.find((item) => item.id === id);
  if (!entry) return { ok: false, reason: "not-found" };
  if (entry.stale) return { ok: false, reason: "text-changed" };
  const guard = refinementGuard(owner, allowRefined);
  if (guard) return guard;
  const prompt = textOf(owner);
  let next = prompt.slice(0, entry.start) + prompt.slice(entry.end);
  let items = shifted(state.items.filter((item) => item.id !== id), id,
    { end: entry.end, delta: entry.start - entry.end });
  // If an empty prompt acquired several blocks, removing its first block
  // also releases the next block's now-unneeded separator — not user prose.
  const first = items.find((item) => !item.stale && item.start === 0 && item.prefix);
  if (first) {
    const width = first.prefix.length;
    next = next.slice(width);
    items = shifted(items, first.id, { end: width, delta: -width }).map((item) => item.id === first.id
      ? { ...item, prefix: "", end: item.end - width } : item);
  }
  return write(owner, next, items, snapshot(owner), allowRefined);
}

/** Undo is local to this editor session. Workflow provenance is persistent,
 *  but an old session must never undo a later person's manual changes. */
export function undoTechnique(owner) {
  if (!validOwner(owner)) return { ok: false, reason: "invalid-target" };
  const history = undoHistory.get(owner);
  const entry = history?.at(-1);
  if (!entry) return { ok: false, reason: "nothing-to-undo" };
  if (textOf(owner) !== entry.afterPrompt || JSON.stringify(owner.techniques) !== entry.afterTechniques
      || (entry.changedRefined && JSON.stringify(owner.refined) !== entry.afterRefined)) {
    return { ok: false, reason: "text-changed" };
  }
  for (const [key, had] of [["prompt", "hadPrompt"], ["techniques", "hadTechniques"]]) {
    if (entry.before[had]) owner[key] = copy(entry.before[key]);
    else delete owner[key];
  }
  if (entry.changedRefined) {
    if (entry.before.hadRefined) owner.refined = copy(entry.before.refined);
    else delete owner.refined;
  }
  history.pop();
  return { ok: true, warnings: [] };
}

export function canUndoTechnique(owner) {
  const entry = undoHistory.get(owner)?.at(-1);
  return !!entry && textOf(owner) === entry.afterPrompt && JSON.stringify(owner.techniques) === entry.afterTechniques
    && (!entry.changedRefined || JSON.stringify(owner.refined) === entry.afterRefined);
}

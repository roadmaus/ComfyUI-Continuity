// A Technique edits only its explicit prompt owner, never a preset's broad
// "prompt" section (which also owns audio/refinement fields). Keep application
// transactions separate from modal browsing and from model compilation.
import { el, icon } from "./dom.js";
import { t } from "./i18n.js";
import { openTechniqueLibrary } from "./techniques.js";
import { applyTechnique, removeTechnique, undoTechnique, getAppliedTechniques, activeRefinement, canUndoTechnique } from "./technique-state.js";

const legacyGlobalBlock = (piece, kind) => kind === "global" && (piece?.segments ?? [])
  // compile.refined_scope only supersedes the global text when a body is active;
  // section-only data must not needlessly block an otherwise valid global edit.
  .some(segment => typeof segment.refined?.body === "string" && !!segment.refined.body.trim()
    && segment.refined.enabled !== false && segment.refined.scope !== "shot");
const LEGACY = "An older active refinement already contains the global prompt. Turn it off or refine that segment again before changing global techniques.";
const STALE = "This prompt target has changed. Reopen the technique library.";
const CLIP = "This segment is a supplied clip and has no generated prompt.";
const targetIds = new WeakMap();
let nextTargetId = 0;
const targetId = owner => {
  if (!targetIds.has(owner)) targetIds.set(owner, `prompt-${++nextTargetId}`);
  return targetIds.get(owner);
};

export function techniqueTarget({ owner, piece = owner, kind = "segment", id, label,
  subjects = () => piece?.subjects ?? owner?.cast ?? [], onChange, isCurrent = () => true }) {
  const valid = () => isCurrent() && (kind !== "segment" || !piece?.segments || piece.segments.includes(owner));
  const blocked = () => !valid() ? STALE : kind === "segment" && owner.kind === "clip" ? CLIP
    : legacyGlobalBlock(piece, kind) ? LEGACY : "";
  const run = operation => {
    const reason = blocked();
    if (reason) return { ok: false, reason };
    const before = owner.prompt ?? "";
    const result = operation();
    if (result.ok) {
      const warnings = onChange?.({ before, after: owner.prompt ?? "", owner, kind });
      if (Array.isArray(warnings) && warnings.length) result.warnings = [...(result.warnings ?? []), ...warnings];
    }
    return result;
  };
  return {
    id: id ?? targetId(owner), get label() { return typeof label === "function" ? label() : label; }, kind, owner,
    isValid: valid,
    blockedReason: () => blocked() ? t(blocked()) : "",
    getText: () => owner.prompt ?? "",
    get subjects() { return subjects().map(row => ({ handle: row.handle, label: `@${row.handle}` })); },
    get duration() { return kind === "segment" && Number.isFinite(owner.duration_s) ? owner.duration_s : null; },
    requiresRefineAcknowledgement: () => activeRefinement(owner),
    warning: () => blocked() ? t(blocked())
      : activeRefinement(owner) ? t("An active refinement replaces this written prompt during generation.") : "",
    apply: options => run(() => applyTechnique(owner, options)),
    remove: id => run(() => removeTechnique(owner, id)),
    undo: () => run(() => undoTechnique(owner)),
    canUndo: () => !blocked() && canUndoTechnique(owner),
    applied: () => getAppliedTechniques(owner),
  };
}

/** One target inventory for every entry point. IDs follow owner objects, never
 * array positions or the currently open editor; a reorder changes only labels.
 * The optional owner is the standalone editor's state, not a second global. */
export function techniqueTargetsForPiece({ piece, owner = piece, subjects, onChange, isCurrent }) {
  const shared = { piece, subjects, onChange, isCurrent };
  if (!Array.isArray(piece?.segments)) return [techniqueTarget({ ...shared, owner,
    kind: "segment", label: t("This prompt") })];
  return [techniqueTarget({ ...shared, owner: piece, kind: "global", label: t("Global prompt — all segments") }),
    ...piece.segments.map(segment => techniqueTarget({ ...shared, owner: segment, kind: "segment",
      label: () => t("Segment {n}", { n: piece.segments.indexOf(segment) + 1 }),
    }))];
}

export function techniqueButton(open, { small = false } = {}) {
  return el("button", {
    type: "button", class: small ? "mmc-pill" : "mmc-tool",
    title: t("Browse cinematic techniques and preview what will be added to this prompt"), onclick: open,
  }, small ? [icon("video", 15), el("span", { text: t("Techniques") })]
    : [el("span", { class: "mmc-tool-icon" }, [icon("video")]), el("span", { text: t("Techniques") })]);
}

/** Chips describe real tracked text in the owner. A user edit invalidates the
 * tracking instead of authorizing a broad search-and-delete in their prose. */
export function renderTechniqueBar(host, target, { open, button = false } = {}) {
  if (!host) return;
  const rows = target.applied();
  const undoable = target.canUndo();
  host.hidden = !button && !rows.length && !undoable;
  const status = el("span", { class: "mmc-technique-note", role: "status" });
  const report = result => {
    if (!result?.ok) status.textContent = t(result?.reason || "The technique could not be changed.");
  };
  const nodes = [];
  if (button) nodes.push(techniqueButton(() => open?.(), { small: true }));
  for (const row of rows) {
    nodes.push(el("span", { class: `mmc-technique-chip${row.stale ? " stale" : ""}` }, [
      el("button", { type: "button", text: row.title || row.id,
        title: row.stale ? t("This technique's text was edited. It will not be removed automatically.") : row.text,
        onclick: () => open?.(row.id),
      }),
      el("button", { type: "button", text: "×", disabled: !!row.stale,
        title: t("Remove this technique's tracked text"), "aria-label": t("Remove {name}", { name: row.title || row.id }),
        onclick: () => report(target.remove(row.id)),
      }),
    ]));
  }
  // Undo also needs to remain reachable after removing the final chip. The
  // shared transaction helper decides whether intervening edits make it unsafe.
  if (rows.length || undoable) nodes.push(el("button", {
    type: "button", class: "mmc-pill", text: t("Undo technique change"),
    disabled: !undoable,
    onclick: () => report(target.undo()),
  }));
  host.replaceChildren(...nodes, status);
}

export { openTechniqueLibrary };

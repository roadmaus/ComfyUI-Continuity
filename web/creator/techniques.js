// A read-only catalogue until the user explicitly applies the editable preview.
// Source prose is text, never HTML. Browsing cannot replace a preset, audio,
// references, seam state, or another prompt field behind the active editor.
import { el, mountOverlay } from "./dom.js";
import { t, getLocale } from "./i18n.js";
import { buildTechniqueText } from "./technique-state.js";

const DATA_ROOT = new URL("./techniques/", import.meta.url);
const BOOKMARK_KEY = "continuity-technique-bookmarks-v1";
const VIEW_KEY = "continuity-technique-view-v1";
const PAGE_SIZE = 48;
let catalogCache = null;
let structureCache = null;
const detailCache = new Map();
const translatedCatalogCache = new Map();
const translatedDetailCache = new Map();
let activeClose = null;
let remembered = {};
let sessionBookmarks = null;

function readStored(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key) ?? "null") ?? fallback; }
  catch { return fallback; }
}
function store(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); return true; }
  catch { return false; }
}

// Catalogue files can only refer to files inside this shipped directory.
// Even a malformed manifest cannot turn a hover into an external request.
function localUrl(path) {
  if (typeof path !== "string" || !path || /[\\?#]/.test(path)) return null;
  try {
    const url = new URL(path, DATA_ROOT);
    return url.origin === DATA_ROOT.origin && url.pathname.startsWith(DATA_ROOT.pathname)
      && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}
async function loadJson(path, signal) {
  const url = localUrl(path);
  if (!url) throw new Error(t("Invalid local catalogue path."));
  const response = await fetch(url, { signal, credentials: "same-origin" });
  if (!response.ok) throw new Error(t("The local file could not be loaded ({status}).", { status: response.status }));
  return response.json();
}
function stopVideo(video) {
  if (!video) return;
  video.pause();
  video.removeAttribute("src");
  video.load();
}
function previewSpeed(video) {
  video.defaultPlaybackRate = 1.2;
  video.playbackRate = 1.2;
}
function configurePreview(video) {
  previewSpeed(video);
  video.addEventListener("loadedmetadata", () => previewSpeed(video));
  video.addEventListener("play", () => previewSpeed(video));
  return video;
}

/** Targets own all prompt mutations. Opening from a segment supplies that
 * segment as target; opening the catalogue alone remains genuinely read-only. */
export function openTechniqueLibrary({ target = null, targets = [], getTargets = null, initialCategory = null, initialTechnique = null } = {}) {
  activeClose?.();
  const previousFocus = document.activeElement;
  const controller = new AbortController();
  function readTargets() {
    const entries = typeof getTargets === "function" ? getTargets() : [target, ...targets];
    return [...new Map((Array.isArray(entries) ? entries : []).filter((entry) => entry?.id && typeof entry.apply === "function")
      .map((entry) => [entry.id, entry])).values()];
  }
  let availableTargets;
  try { availableTargets = readTargets(); } catch { availableTargets = []; }
  let currentTarget = availableTargets.find((entry) => entry.id === target?.id) ?? availableTargets[0] ?? null;
  const storedBookmarks = sessionBookmarks ?? readStored(BOOKMARK_KEY, []);
  const bookmarks = new Set(Array.isArray(storedBookmarks) ? storedBookmarks.filter((id) => typeof id === "string") : []);
  sessionBookmarks = [...bookmarks];
  const view = { ...readStored(VIEW_KEY, {}), ...remembered };
  const locale = getLocale();
  // Explanations now follow the UI locale automatically. In particular, ignore
  // the former persisted English-only toggle rather than hiding an active mode.
  let translatedCatalog = null;
  let translatedDetail = null;
  let category = initialCategory ?? view.category ?? "";
  let query = typeof view.query === "string" ? view.query : "";
  let onlyBookmarks = Boolean(view.onlyBookmarks);
  let visibleCount = Math.max(PAGE_SIZE, Math.min(480, Number(view.visibleCount) || PAGE_SIZE));
  let catalog = null;
  let structure = null;
  let filtered = [];
  let selected = null;
  let selectedId = initialTechnique ?? view.selectedId ?? null;
  let detailOpen = false;
  let listScroll = Number(view.scroll) || 0;
  let listFocusId = selectedId;
  const history = [];
  let mode = "technique";
  let applying = false;
  let closed = false;
  let selectionVersion = 0;
  let detailController = null;
  let hoverTimer = null;
  let hoverVideo = null;
  const detailVideos = new Set();
  const playback = new Map();
  const drafts = new Map();
  const substitutionState = new Map();
  const draftKey = () => `${currentTarget?.id ?? "browse"}:${selected?.id ?? ""}:${mode}`;
  const substitutionKey = () => `${currentTarget?.id ?? "browse"}:${selected?.id ?? ""}`;
  let unmount = () => {};

  const status = el("div", { class: "mmc-tech-status", role: "status", "aria-live": "polite" });
  const announce = (message, error = false) => {
    if (closed) return;
    status.textContent = message;
    status.dataset.error = String(error);
  };
  function stopHover() {
    clearTimeout(hoverTimer);
    hoverTimer = null;
    if (hoverVideo) { stopVideo(hoverVideo); hoverVideo.remove(); hoverVideo = null; }
  }
  function releaseDetails() {
    for (const video of detailVideos) { video.autoplay = false; stopVideo(video); }
    detailVideos.clear();
    playback.clear();
  }
  function startDetailVideo(video, manual = false) {
    const state = playback.get(video);
    if (!state || closed || !detailOpen || document.hidden || !video.isConnected || state.blocked && !manual) return;
    if (state.pending) { state.resumeRequested = true; return; }
    state.pending = true;
    state.interrupted = false;
    state.resumeRequested = false;
    previewSpeed(video);
    video.play().then(() => {
      if (!playback.has(video) || closed || document.hidden || !detailOpen) { video.pause(); return; }
      state.blocked = false;
      state.button.hidden = true;
    }).catch((error) => {
      if (!playback.has(video) || closed || !detailOpen || document.hidden) return;
      // pause() during a hidden tab can reject an outstanding play() only
      // after the tab has become visible again. That is not a policy denial.
      if (error?.name === "AbortError" && state.interrupted) { state.resumeRequested = true; return; }
      state.blocked = true;
      state.button.hidden = false;
    }).finally(() => {
      state.pending = false;
      const resume = state.resumeRequested && !state.blocked;
      state.resumeRequested = false;
      state.interrupted = false;
      if (resume && playback.has(video) && video.paused && !document.hidden) startDetailVideo(video);
    });
  }
  const onVisibility = () => {
    if (document.hidden) {
      stopHover();
      for (const video of detailVideos) {
        const state = playback.get(video);
        if (state?.pending) state.interrupted = true;
        video.pause();
      }
    }
    else if (detailOpen) for (const video of detailVideos) startDetailVideo(video);
  };
  function remember() {
    remembered = { category, query, onlyBookmarks, selectedId: detailOpen ? listFocusId : selectedId, visibleCount, scroll: detailOpen ? listScroll : listView.scrollTop };
    store(VIEW_KEY, remembered);
  }
  function exitFullscreen() {
    if (!document.fullscreenElement || !overlay.contains(document.fullscreenElement)) return false;
    document.exitFullscreen?.().catch(() => {});
    return true;
  }
  function close() {
    if (closed) return;
    remember();
    closed = true;
    controller.abort();
    detailController?.abort();
    stopHover();
    releaseDetails();
    document.removeEventListener("visibilitychange", onVisibility);
    exitFullscreen();
    unmount();
    if (activeClose === close) activeClose = null;
    if (previousFocus?.isConnected) previousFocus.focus?.({ preventScroll: true });
  }

  const closeButton = el("button", { type: "button", class: "mmc-close", text: "×", title: t("Close"), "aria-label": t("Close"), onclick: close });
  const count = el("span", { class: "mmc-tech-count", "aria-live": "polite" });
  const search = el("input", { type: "search", class: "mmc-search", value: query,
    placeholder: t("Search techniques, descriptions or aliases…"), "aria-label": t("Search techniques"),
    oninput: () => { query = search.value; resetGrid(); } });
  const bookmarkedButton = el("button", { type: "button", text: `☆ ${t("Bookmarks")}`, onclick: () => { onlyBookmarks = !onlyBookmarks; resetGrid(); } });
  const categoryButtons = el("div", { class: "mmc-tech-categories", role: "group", "aria-label": t("Technique categories") });
  const filters = el("div", { class: "mmc-tech-filters" }, [categoryButtons]);
  const grid = el("div", { class: "mmc-tech-grid", "aria-label": t("Techniques") });
  const detailBody = el("div", { class: "mmc-tech-detail-body" }, [
    el("p", { class: "mmc-tech-empty", text: t("Select a technique to preview its examples and original instructions.") }),
  ]);
  const targetSelect = el("select", { "aria-label": t("Apply to"), onfocus: () => refreshTargets(), onpointerdown: () => refreshTargets(), onchange: () => {
    currentTarget = availableTargets.find((entry) => entry.id === targetSelect.value) ?? null;
    refineAcknowledgement.checked = false;
    renderSubstitutions();
    renderApplication();
  } }, availableTargets.map((entry) => el("option", { value: entry.id, text: entry.label ?? entry.id })));
  if (currentTarget) targetSelect.value = currentTarget.id;
  const preview = el("textarea", { class: "mmc-tech-preview", rows: "5", spellcheck: false,
    "aria-label": t("Editable insertion preview"), oninput: () => {
      if (selected) drafts.set(draftKey(), preview.value);
      updateApplyButton();
    } });
  const warnings = el("div", { class: "mmc-tech-warnings", role: "note" });
  const subjectSelect = el("select", { "aria-label": t("Subject placeholder"), onchange: () => {
    rememberSubstitutions();
    if (selected) drafts.delete(draftKey());
    renderApplication();
  } });
  const durationInput = el("input", { type: "number", min: "0.1", step: "0.1", "aria-label": t("Duration placeholder (seconds)"),
    oninput: () => { rememberSubstitutions(); if (selected) drafts.delete(draftKey()); renderApplication(); } });
  const substitutions = el("div", { class: "mmc-tech-substitutions" }, [
    el("label", {}, [el("span", { text: t("Subject placeholder") }), subjectSelect]),
    el("label", {}, [el("span", { text: t("Duration placeholder (seconds)") }), durationInput]),
  ]);
  const refineAcknowledgement = el("input", { type: "checkbox", onchange: updateApplyButton });
  const refineLabel = el("label", { class: "mmc-tech-refine-ack", hidden: true }, [refineAcknowledgement,
    el("span", { text: t("Apply to the written prompt and turn off the active refinement (keep its text)") })]);
  const techniqueMode = el("button", { type: "button", text: t("Technique only"), onclick: () => { mode = "technique"; renderApplication(); } });
  const originalMode = el("button", { type: "button", text: t("Original example"), onclick: () => { mode = "original"; renderApplication(); } });
  const modeDescription = el("div", { class: "mmc-tech-muted" });
  const resetOriginal = el("button", { type: "button", class: "mmc-tech-reset-original", text: t("Reset to source example"),
    title: t("Replace this edited example with the unchanged source example."), hidden: true,
    onclick: () => {
      if (!selected || mode !== "original") return;
      drafts.delete(draftKey());
      renderApplication();
    } });
  const applyButton = el("button", { type: "button", class: "mmc-tech-apply", text: t("Add to prompt"), disabled: true,
    onclick: async () => {
      if (applying || !selected || !preview.value.trim()) return;
      if (!refreshTargets()) {
        announce(t("This prompt target has changed. Reopen the technique library."), true);
        return;
      }
      const blocked = targetBlockedReason();
      if (blocked) { announce(t(blocked), true); return; }
      // Capture the exact approved text and target. An async commit must not
      // accidentally use another selection made while it was in flight.
      const approved = { item: selected, text: preview.value, mode, allowRefined: refineAcknowledgement.checked };
      const destination = currentTarget;
      applying = true;
      updateApplyButton();
      try {
        const result = await destination.apply(approved);
        if (result === false || result?.ok === false) throw new Error(t(result?.reason ?? "The prompt was not changed."));
        const notice = t("Added to {target}. Existing prompt text was preserved.", { target: destination.label ?? destination.id });
        announce([notice, ...(Array.isArray(result?.warnings) ? result.warnings : [])].filter(Boolean).join(" "));
        if (!closed) {
          refineAcknowledgement.checked = false;
          renderApplication();
        }
      } catch (error) {
        announce(t("Could not apply technique — {error}", { error: error?.message ?? String(error) }), true);
      } finally { applying = false; if (!closed) updateApplyButton(); }
    } });
  const copyButton = el("button", { type: "button", class: "mmc-tech-copy", text: t("Copy prompt"), disabled: true,
    onclick: () => copyText(preview.value, preview) });
  const applicationControls = el("div", { class: "mmc-tech-application-controls" }, [
    el("label", { class: "mmc-tech-target", hidden: !availableTargets.length }, [el("span", { text: t("Apply to") }), targetSelect]),
    el("div", { class: "mmc-tech-modes", role: "group", "aria-label": t("Prompt content") }, [techniqueMode, originalMode]),
    modeDescription,
    el("div", { class: "mmc-tech-muted", text: t("Review or edit the English text before adding it. Nothing is applied automatically.") }),
    preview, resetOriginal, substitutions, warnings, refineLabel,
  ]);
  const application = el("div", { class: "mmc-tech-application", hidden: true }, [
    applicationControls,
  ]);
  const backButton = el("button", { type: "button", class: "mmc-tech-back", text: `← ${t("Back to library")}`, onclick: showList });
  const previousButton = el("button", { type: "button", class: "mmc-tech-previous", text: `← ${t("Previous technique")}`, hidden: true, onclick: previousDetail });
  const detailName = el("strong", { class: "mmc-tech-detail-name" });
  const detailBookmark = el("button", { type: "button", class: "mmc-tech-detail-bookmark", text: "☆", hidden: true,
    onclick: () => {
      if (!selected) return;
      toggleBookmark(selected.id);
      renderGrid();
      renderDetailBookmark();
    } });
  const inspector = el("div", { class: "mmc-tech-inspector", "aria-label": t("Technique details"), hidden: true }, [
    el("div", { class: "mmc-tech-detail-nav" }, [backButton, previousButton, detailName, detailBookmark]), detailBody,
    el("div", { class: "mmc-tech-application-footer" }, [copyButton, applyButton]),
  ]);
  const listView = el("div", { class: "mmc-tech-list", onscroll: stopHover }, [el("div", { class: "mmc-tech-search" }, [search]), filters, grid]);
  const dialog = el("div", { class: "mmc-modal mmc-tech-modal", role: "dialog", "aria-modal": true,
    "aria-label": t("Technique library"), tabindex: "-1" }, [
    el("div", { class: "mmc-modal-head" }, [el("strong", { text: t("Technique library") }), count, closeButton]),
    listView, inspector, status,
  ]);
  const overlay = el("div", { class: "mmc-overlay mmc-tech-overlay", onpointerdown: (event) => { if (event.target === overlay) close(); } }, [dialog]);

  // Guards preserve native video-control tab stops, unlike trapping Tab on
  // the <video> host. Escape belongs only to the newest Continuity overlay.
  function focusEdge(last) {
    const candidates = [...dialog.querySelectorAll("button:not(:disabled), input, select, textarea, a[href], video[controls]")]
      .filter((element) => !element.closest("[hidden]") && element.getClientRects().length);
    (candidates[last ? candidates.length - 1 : 0] ?? dialog).focus();
  }
  dialog.prepend(el("span", { class: "mmc-tech-focus-guard", tabindex: "0", onfocus: () => focusEdge(true) }));
  dialog.append(el("span", { class: "mmc-tech-focus-guard", tabindex: "0", onfocus: () => focusEdge(false) }));
  unmount = mountOverlay(overlay, () => {
    if (exitFullscreen()) return;
    if (detailOpen) { if (history.length) previousDetail(); else showList(); } else close();
  });
  document.addEventListener("visibilitychange", onVisibility);
  activeClose = close;
  search.focus({ preventScroll: true });

  function updateApplyButton() {
    applyButton.disabled = applying || !currentTarget || !selected || !preview.value.trim() || Boolean(targetBlockedReason())
      || needsRefineAcknowledgement() && !refineAcknowledgement.checked;
    applyButton.textContent = applying ? t("Applying…") : t("Add to prompt");
    applyButton.hidden = !availableTargets.length;
    copyButton.disabled = !selected || !preview.value.trim();
    resetOriginal.hidden = !selected || mode !== "original" || preview.value === (selected.prompt?.example ?? "");
  }
  function targetBlockedReason() {
    try { return typeof currentTarget?.blockedReason === "function" ? currentTarget.blockedReason() : null; }
    catch { return "This prompt target has changed. Reopen the technique library."; }
  }
  function refreshTargets() {
    const previousId = currentTarget?.id;
    try { availableTargets = readTargets(); } catch { availableTargets = []; }
    const refreshed = availableTargets.find((entry) => entry.id === previousId);
    let valid = Boolean(refreshed);
    try { if (refreshed?.isValid && !refreshed.isValid()) valid = false; } catch { valid = false; }
    // Keep a stale selected object for its draft identity, never silently apply
    // to a different surviving segment when a deletion/replacement occurred.
    if (valid) currentTarget = refreshed;
    targetSelect.replaceChildren(...availableTargets.map((entry) => el("option", { value: entry.id, text: entry.label ?? entry.id })));
    if (!valid && previousId) targetSelect.prepend(el("option", { value: previousId, text: currentTarget.label ?? previousId, disabled: true }));
    targetSelect.value = previousId ?? "";
    if (!valid && previousId) announce(t("This prompt target has changed. Reopen the technique library."), true);
    return valid;
  }
  function translatedSummary(item) {
    const value = translatedCatalog?.items?.[item.id]?.description;
    return typeof value === "string" && value.trim() ? value : null;
  }
  async function loadTranslatedCatalog(source) {
    if (locale === "en") return null;
    const key = `${locale}:${source.capturedAt}`;
    try {
      const data = translatedCatalogCache.get(key) ?? await loadJson(`translations/${locale}/catalog.json`, controller.signal);
      if (data?.version !== 1 || data.locale !== locale || data.sourceCapturedAt !== source.capturedAt || !data.items || typeof data.items !== "object") return null;
      translatedCatalogCache.set(key, data);
      return data;
    } catch { return null; } // Original catalogue remains usable offline/in partial packages.
  }
  async function loadTranslatedDetail(source, signal) {
    if (locale === "en" || !translatedCatalog) return null;
    const key = `${locale}:${source.id}:${source.sourceHtmlSha256}`;
    try {
      const data = translatedDetailCache.get(key) ?? await loadJson(`translations/${locale}/${source.detail}`, signal);
      // Source hashes prevent an old translation from being silently attached
      // to a newer article whose block indices no longer describe the same text.
      if (data?.version !== 1 || data.locale !== locale || data.id !== source.id || !source.sourceHtmlSha256
        || data.sourceHtmlSha256 !== source.sourceHtmlSha256 || !Array.isArray(data.sections)) return null;
      translatedDetailCache.delete(key);
      translatedDetailCache.set(key, data);
      while (translatedDetailCache.size > 40) translatedDetailCache.delete(translatedDetailCache.keys().next().value);
      return data;
    } catch { return null; }
  }
  function needsRefineAcknowledgement() {
    try { return Boolean(currentTarget?.requiresRefineAcknowledgement?.()); }
    catch { return true; } // A failed gate must never silently consent.
  }
  function renderSubstitutions() {
    const subjects = currentTarget?.subjects ?? [];
    const safeSubjects = Array.isArray(subjects) ? subjects.filter((entry) => typeof entry?.handle === "string" && entry.handle) : [];
    subjectSelect.replaceChildren(el("option", { value: "", text: t("Keep original placeholder") }),
      ...safeSubjects.map((entry) => el("option", { value: entry.handle.startsWith("@") ? entry.handle : `@${entry.handle}`,
        text: entry.label ?? (entry.handle.startsWith("@") ? entry.handle : `@${entry.handle}`) })));
    const saved = substitutionState.get(substitutionKey());
    subjectSelect.value = saved && [...subjectSelect.options].some((option) => option.value === saved.subject) ? saved.subject : "";
    let duration;
    try { duration = typeof currentTarget?.duration === "function" ? currentTarget.duration() : currentTarget?.duration; }
    catch { duration = null; }
    durationInput.value = saved ? saved.duration : currentTarget?.kind === "segment" && Number.isFinite(duration) && duration > 0 ? String(duration) : "";
  }
  function rememberSubstitutions() {
    if (selected) substitutionState.set(substitutionKey(), { subject: subjectSelect.value, duration: durationInput.value });
  }
  function renderApplication() {
    application.hidden = !selected;
    if (!selected) return;
    const guidance = (selected.prompt?.guidance ?? []).join("\n");
    subjectSelect.closest("label").hidden = !/\[\s*subject\s*\]|\{\{?\s*subject\s*\}?\}/i.test(guidance);
    durationInput.closest("label").hidden = !/\[\s*duration\s*\]|\{\{?\s*duration\s*\}?\}/i.test(guidance);
    substitutions.hidden = mode !== "technique" || subjectSelect.closest("label").hidden && durationInput.closest("label").hidden;
    const options = { mode, subject: subjectSelect.value,
      duration: durationInput.value && Number(durationInput.value) > 0 ? Number(durationInput.value) : null };
    let built;
    try { built = buildTechniqueText(selected, options); }
    catch (error) { built = { text: "", warnings: [error?.message ?? String(error)] }; }
    preview.value = drafts.get(draftKey()) ?? built.text ?? "";
    techniqueMode.setAttribute("aria-pressed", String(mode === "technique"));
    originalMode.setAttribute("aria-pressed", String(mode === "original"));
    modeDescription.textContent = t(mode === "original"
      ? "Source example — a specific scene with its own people, place and action."
      : "Technique guidance — general camera instructions to adapt to your shot.");
    const advice = [...(built.warnings ?? [])];
    let targetWarning;
    try { targetWarning = typeof currentTarget?.warning === "function" ? currentTarget.warning() : currentTarget?.warning; }
    catch { targetWarning = null; }
    if (targetWarning) advice.push(targetWarning);
    warnings.replaceChildren(...[...new Set(advice)].map((message) => el("p", { text: t(message) })));
    warnings.hidden = !advice.length;
    refineLabel.hidden = !needsRefineAcknowledgement();
    updateApplyButton();
  }
  function resetGrid() { visibleCount = PAGE_SIZE; listView.scrollTop = 0; renderGrid(); }
  function showList() {
    if (closed || !detailOpen) return;
    // A late detail/translation response must not navigate back into a detail
    // after the user has already returned to the catalogue.
    selectionVersion++;
    detailController?.abort();
    stopHover();
    releaseDetails();
    detailOpen = false;
    selected = null;
    translatedDetail = null;
    history.length = 0;
    previousButton.hidden = true;
    selectedId = listFocusId;
    inspector.hidden = true;
    listView.hidden = false;
    count.hidden = false;
    listView.scrollTop = listScroll;
    const previousCard = [...grid.querySelectorAll(".mmc-tech-card")].find((button) => button.dataset.technique === selectedId);
    (previousCard ?? search).focus({ preventScroll: true });
    announce(t("Hover over a card to preview. Select it to read the full original content."));
  }
  function captureDetail() {
    return { id: selectedId, scroll: detailBody.scrollTop, mode, targetId: currentTarget?.id, target: currentTarget,
      subject: subjectSelect.value, duration: durationInput.value,
      focusKey: document.activeElement?.dataset?.navKey ?? null };
  }
  function navigateDetail(item) {
    if (!item || item.id === selectedId) return;
    if (selected) history.push(captureDetail());
    selectItem(item, { internal: true });
  }
  function previousDetail() {
    const saved = history.pop();
    const item = saved && catalog?.items.find((entry) => entry.id === saved.id);
    if (item) selectItem(item, { internal: true, restore: saved });
    else showList();
  }
  function toggleBookmark(id) {
    if (bookmarks.has(id)) bookmarks.delete(id); else bookmarks.add(id);
    sessionBookmarks = [...bookmarks];
    if (!store(BOOKMARK_KEY, sessionBookmarks)) announce(t("Bookmarks are kept for this session; browser storage is unavailable."), true);
  }
  function renderDetailBookmark() {
    detailBookmark.hidden = !selected;
    if (!selected) return;
    detailBookmark.textContent = bookmarks.has(selected.id) ? "★" : "☆";
    detailBookmark.setAttribute("aria-pressed", String(bookmarks.has(selected.id)));
    detailBookmark.setAttribute("aria-label", t("Bookmark {name}", { name: selected.title }));
  }
  function renderCategories() {
    const button = (id, title, total) => el("button", { type: "button", text: total === undefined ? title : `${title} · ${total}`,
      "aria-pressed": category === id, onclick: () => { category = id; renderCategories(); resetGrid(); } });
    categoryButtons.replaceChildren(button("", t("All categories")), bookmarkedButton,
      ...catalog.categories.map((entry) => button(entry.id, t(entry.title), entry.count)));
  }
  function startHover(item, hero) {
    stopHover();
    const url = localUrl(item.video);
    if (!url || applying || globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    hoverTimer = setTimeout(() => {
      if (closed || detailOpen || !hero.isConnected) return;
      const video = configurePreview(el("video", { src: url, loop: true, playsinline: true, preload: "none", "aria-hidden": true }));
      video.muted = true;
      hoverVideo = video;
      hero.append(video);
      video.play().catch(() => { if (hoverVideo === video) stopHover(); });
    }, 180);
  }
  function card(item) {
    const hero = el("div", { class: "mmc-tech-card-hero" });
    const thumbnail = localUrl(item.thumbnail);
    if (thumbnail) {
      const image = el("img", { src: thumbnail, alt: "", loading: "lazy", decoding: "async", onerror: () => {
        image.hidden = true;
        hero.append(el("span", { text: t("Preview unavailable") }));
      } });
      hero.append(image);
    }
    else hero.append(el("span", { text: t("Preview unavailable") }));
    const localizedDescription = translatedSummary(item);
    const open = el("button", { class: "mmc-tech-card", type: "button", "aria-pressed": selectedId === item.id,
      onclick: () => selectItem(item), onpointerenter: () => startHover(item, hero), onpointerleave: stopHover,
      onfocus: () => startHover(item, hero), onblur: stopHover }, [hero,
      el("strong", { text: item.title }), el("span", { class: "mmc-tech-muted", text: t(item.categoryTitle) }),
      el("span", { class: "mmc-tech-description", text: localizedDescription ?? item.description ?? "", lang: localizedDescription ? locale : "en" }),
      locale !== "en" && !localizedDescription ? el("span", { class: "mmc-tech-language", text: t("English explanation") }) : null,
    ]);
    open.dataset.technique = item.id;
    const star = el("button", { class: "mmc-tech-star", type: "button", text: bookmarks.has(item.id) ? "★" : "☆",
      "aria-label": t("Bookmark {name}", { name: item.title }), "aria-pressed": bookmarks.has(item.id),
      onclick: () => {
        toggleBookmark(item.id);
        if (onlyBookmarks) renderGrid();
        else { star.textContent = bookmarks.has(item.id) ? "★" : "☆"; star.setAttribute("aria-pressed", String(bookmarks.has(item.id))); }
      } });
    return el("div", { class: "mmc-tech-card-holder" }, [open, star]);
  }
  function renderGrid() {
    if (!catalog || closed) return;
    stopHover();
    const words = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    filtered = catalog.items.filter((item) => (!category || item.categoryId === category) && (!onlyBookmarks || bookmarks.has(item.id))
      && words.every((word) => `${item.title} ${(item.aliases ?? []).join(" ")} ${item.description ?? ""} ${translatedSummary(item) ?? ""} ${item.categoryTitle} ${t(item.categoryTitle)}`.toLocaleLowerCase().includes(word)));
    bookmarkedButton.setAttribute("aria-pressed", String(onlyBookmarks));
    count.textContent = t("{shown} / {total} techniques", { shown: filtered.length, total: catalog.items.length });
    grid.replaceChildren(...filtered.slice(0, visibleCount).map(card));
    if (!filtered.length) grid.append(el("p", { class: "mmc-tech-empty", text: t("No matching techniques. Try another category or search.") }));
    if (visibleCount < filtered.length) grid.append(el("button", { class: "mmc-tech-more", type: "button",
      text: t("Show {count} more", { count: Math.min(PAGE_SIZE, filtered.length - visibleCount) }),
      onclick: () => {
        const nextIndex = visibleCount;
        const scroll = listView.scrollTop;
        visibleCount += PAGE_SIZE;
        renderGrid();
        listView.scrollTop = scroll;
        grid.querySelectorAll(".mmc-tech-card")[nextIndex]?.focus({ preventScroll: true });
      } }));
  }
  function mediaElement(entry, { hero = false } = {}) {
    const url = localUrl(entry.path);
    if (!url) return null;
    const error = el("figcaption", { text: t("Preview unavailable. The file may be missing, or this browser may not support its format."), hidden: true });
    let media;
    if (entry.kind === "video") {
      media = configurePreview(el("video", { src: url, autoplay: true, loop: true, playsinline: true, preload: "metadata", "aria-label": entry.alt || selected?.title || t("Technique preview") }));
      media.muted = true;
      media.defaultMuted = true;
      const poster = localUrl(entry.poster);
      if (poster) media.poster = poster;
      detailVideos.add(media);
      media.addEventListener("play", () => {
        stopHover();
        if (closed || document.hidden || !detailOpen || !detailVideos.has(media)) media.pause();
      });
    } else media = el("img", { src: url, alt: entry.alt ?? "", loading: "lazy", decoding: "async" });
    media.addEventListener("error", () => {
      error.hidden = false;
      const poster = localUrl(entry.poster);
      if (entry.kind === "video" && poster && !media.hidden) {
        media.hidden = true;
        media.after(el("img", { src: poster, alt: entry.alt ?? "", class: "mmc-tech-poster-fallback" }));
      }
    });
    const figure = el("figure", { class: hero ? "mmc-tech-media mmc-tech-hero" : "mmc-tech-media" }, [media, error,
      entry.alt ? el("figcaption", { class: "mmc-tech-caption", text: entry.alt }) : null]);
    if (entry.kind === "video") {
      const start = el("button", { type: "button", class: "mmc-tech-play", text: t("Play preview"),
        title: t("Automatic playback was blocked. Start the silent preview manually."), hidden: true,
        onclick: (event) => { event.stopPropagation(); startDetailVideo(media, true); } });
      playback.set(media, { button: start, pending: false, blocked: false, interrupted: false, resumeRequested: false });
      figure.append(start);
    }
    return figure;
  }
  async function copyText(text, field) {
    try { await navigator.clipboard.writeText(text); announce(t("Copied prompt.")); }
    catch {
      field?.focus(); field?.select();
      announce(t("Clipboard unavailable. The prompt is selected; use your copy shortcut."), true);
    }
  }
  function resolveTechnique(url, sourceUrl) {
    try {
      const resolved = new URL(url, sourceUrl);
      const origin = new URL(catalog.sourceUrl).origin;
      if (resolved.origin !== origin || resolved.username || resolved.password) return null;
      const path = resolved.pathname.replace(/\/$/, "");
      return catalog.items.find((item) => new URL(item.sourceUrl).pathname.replace(/\/$/, "") === path) ?? null;
    } catch { return null; }
  }
  function techniqueLink(item, text, navKey, className = "mmc-tech-inline-link") {
    return el("button", { type: "button", class: className, text, "aria-label": item.title,
      "data-technique-link": item.id, "data-nav-key": navKey, onclick: () => navigateDetail(item) });
  }
  function renderDetail(detail) {
    releaseDetails();
    const article = el("div", { class: "mmc-tech-article" });
    const translation = translatedDetail;
    const candidate = structure?.items?.[detail.id];
    const arrangement = candidate?.sourceHtmlSha256 === detail.sourceHtmlSha256 ? candidate : null;
    let translatedFields = 0;
    let sourceFields = 0;
    const localized = (original, value) => {
      if (typeof original !== "string" || !original.trim()) return original;
      sourceFields++;
      if (typeof value === "string" && value.trim()) { translatedFields++; return value; }
      return original;
    };
    const byIndex = (entries, index) => Array.isArray(entries) ? entries.find((entry) => entry?.index === index) : null;
    const shownMedia = new Set();
    const appendMedia = (parent, entry, options) => {
      if (!entry?.path || shownMedia.has(entry.path)) return;
      const node = mediaElement(entry, options);
      if (node) {
        parent.append(node); shownMedia.add(entry.path);
        // Only supplemental source-wrapper evidence may attach a poster. It
        // remains a fallback on the video rather than a second large image.
        if (entry.kind === "video" && localUrl(entry.poster)) shownMedia.add(entry.poster);
      }
      return node;
    };
    const appendLinkedText = (parent, text, block, record, navKey) => {
      const ranges = record?.sourceText === text && Array.isArray(record.ranges) ? record.ranges : [];
      let offset = 0;
      if (ranges.length) {
        for (const [index, range] of ranges.entries()) {
          const item = catalog.items.find((entry) => entry.id === range.targetId);
          if (!item || !Number.isInteger(range.start) || !Number.isInteger(range.end) || range.start < offset
            || range.end <= range.start || text.slice(range.start, range.end) !== range.text) continue;
          parent.append(text.slice(offset, range.start), techniqueLink(item, range.text, `${navKey}:${index}`));
          offset = range.end;
        }
        parent.append(text.slice(offset));
        return;
      }
      parent.append(text);
      // Localized prose no longer shares source offsets. Keep it untouched and
      // expose exact known destinations as small adjacent internal links.
      const destinations = new Map();
      for (const link of block.links ?? []) {
        const item = resolveTechnique(link.url, detail.sourceUrl);
        if (item) destinations.set(item.id, item);
      }
      if (destinations.size) parent.append(el("span", { class: "mmc-tech-inline-related" }, [...destinations.values()]
        .map((item, index) => techniqueLink(item, item.title, `${navKey}:${index}`))));
    };
    const groupedCard = (group, text, language, navKey) => {
      const item = group.targetId && catalog.items.find((entry) => entry.id === group.targetId);
      const box = el("div", { class: `mmc-tech-group-card${item ? " mmc-tech-group-navigable" : ""}`,
        "data-source-card": group.kind, "data-card-title": group.title,
        onclick: item ? (event) => { if (!event.target.closest("button")) navigateDetail(item); } : undefined });
      if (group.media) appendMedia(box, group.media);
      const newline = text.indexOf("\n");
      const description = newline >= 0 ? text.slice(newline + 1)
        : text.startsWith(group.title) ? text.slice(group.title.length).trim() : text;
      const body = el("div", { class: "mmc-tech-group-text" }, [
        item ? techniqueLink(item, group.title, navKey, "mmc-tech-card-link") : el("strong", { text: group.title }),
        el("p", { text: description || group.description, lang: language }),
      ]);
      box.append(body);
      return box;
    };
    const hero = arrangement?.primary ?? (detail.video ? { kind: "video", path: detail.video, alt: detail.title }
      : detail.thumbnail ? { kind: "image", path: detail.thumbnail, alt: detail.title } : null);
    const heading = el("div", { class: "mmc-tech-detail-title" }, [el("h2", { text: detail.title })]);
    article.append(heading, el("p", { class: "mmc-tech-muted", text: t(detail.categoryTitle) }));
    const detailTranslationNote = el("p", { class: "mmc-tech-language", hidden: locale === "en", role: "note" });
    article.append(detailTranslationNote);
    if (detail.aliases?.length) article.append(el("p", { class: "mmc-tech-muted" }, [
      el("strong", { text: `${t("Also known as")}: ` }), String(detail.aliases.join(" · ")),
    ]));
    if (hero) appendMedia(article, hero, { hero: true });
    if (detail.description) article.append(el("p", { text: localized(detail.description, translation?.description),
      lang: translation?.description ? locale : "en" }));
    // Keep prompt review in the same reading flow, before long instructions.
    // Only the body scrolls; the thin action bar never hides this editor.
    article.append(application);
    // Source frame strips precede the article's first semantic section. Keep
    // their source position rather than collecting them after the FAQ.
    if (arrangement?.strip) appendMedia(article, arrangement.strip);
    for (const section of detail.sections ?? []) {
      const sectionTranslation = translation?.sections.find((entry) => entry?.id === section.id);
      const sectionArrangement = arrangement?.sections?.[section.id];
      const container = el("section", { class: "mmc-tech-source-section", "data-section": section.id });
      if (section.title) container.append(el("h3", { text: localized(section.title, sectionTranslation?.title) }));
      let list = null;
      let representedPrompt = false;
      for (const [blockIndex, block] of (section.blocks ?? []).entries()) {
        // Card titles and their adjacent descriptions can be separate DOM
        // nodes in the source. A display-only newline keeps that boundary;
        // the archived block.text remains untouched for source comparison.
        const original = typeof block.displayText === "string" ? block.displayText : typeof block.text === "string" ? block.text : "";
        if (section.id === "prompt" && ((detail.prompt?.guidance ?? []).includes(original) || original === detail.prompt?.example)) {
          representedPrompt = true;
          continue;
        }
        // Prompt prose is deliberately excluded from explanation translation,
        // including when it appears in the article as a guidance paragraph.
        const translatedBlock = section.id === "prompt" ? null : byIndex(sectionTranslation?.blocks, blockIndex)?.text;
        const text = section.id === "prompt" ? original : localized(original, translatedBlock);
        const language = translatedBlock ? locale : "en";
        if (!text) continue;
        const group = sectionArrangement?.cards?.find((entry) => entry.blockIndex === blockIndex);
        if (group) {
          list = null;
          container.append(groupedCard(group, text, language, `${section.id}:${blockIndex}:card`));
          continue;
        }
        const record = sectionArrangement?.inlineLinks?.find((entry) => entry.blockIndex === blockIndex);
        let node;
        if (block.type === "list-item") {
          if (!list) { list = el("ul"); container.append(list); }
          node = el("li", { lang: language }); list.append(node);
        } else {
          list = null;
          node = el(block.type === "heading" ? "h4" : block.type === "quote" ? "blockquote" : "p", { lang: language });
          container.append(node);
        }
        appendLinkedText(node, text, block, record, `${section.id}:${blockIndex}`);
      }
      if (representedPrompt) container.append(el("button", { type: "button", class: "mmc-tech-reset-original", text: t("Review prompt above"),
        onclick: () => { application.scrollIntoView({ block: "center" }); preview.focus({ preventScroll: true }); } }));
      for (const [index, media] of (section.media ?? []).entries()) appendMedia(container, { ...media,
        alt: media.alt === detail.title ? media.alt : localized(media.alt, byIndex(sectionTranslation?.media, index)?.alt) });
      article.append(container);
    }
    // Assets not attached to a heading still remain available, rather than
    // silently dropping a film strip or illustrative image from the archive.
    const extras = el("section", { class: "mmc-tech-source-section" }, [el("h3", { text: t("Additional source media") })]);
    for (const [index, media] of (detail.media ?? []).entries()) {
      const alt = media.alt === detail.title ? media.alt : localized(media.alt, byIndex(translation?.media, index)?.alt);
      if (Array.isArray(arrangement?.articleMediaPaths) && !arrangement.articleMediaPaths.includes(media.path)) continue;
      appendMedia(extras, { ...media, alt });
    }
    if (extras.children.length > 1) article.append(extras);
    const recommended = (arrangement?.recommendedIds ?? []).map((id) => catalog.items.find((item) => item.id === id)).filter(Boolean);
    if (recommended.length) article.append(el("section", { class: "mmc-tech-source-section" }, [
      el("h3", { text: t("Related techniques") }), el("div", { class: "mmc-tech-recommended" },
        recommended.map((item, index) => techniqueLink(item, item.title, `related:${index}`, "mmc-tech-card-link"))),
    ]));
    detailTranslationNote.textContent = translatedFields === 0 ? t("English explanation — translation is not available yet.")
      : translatedFields < sourceFields ? t("Partly translated; missing explanations are shown in English.")
      : t("Translated explanation. Prompts and technique names remain in English.");
    detailTranslationNote.dataset.translation = translatedFields === 0 ? "missing"
      : translatedFields < sourceFields ? "partial" : "complete";
    detailTranslationNote.hidden = locale === "en" || translatedFields > 0 && translatedFields === sourceFields;
    detailBody.replaceChildren(article);
    detailBody.scrollTop = 0;
    renderDetailBookmark();
    renderApplication();
    for (const video of detailVideos) startDetailVideo(video);
  }
  async function selectItem(item, { internal = false, restore = null } = {}) {
    if (closed) return;
    stopHover();
    releaseDetails();
    detailController?.abort();
    detailController = new AbortController();
    const version = ++selectionVersion;
    if (!detailOpen) { listScroll = listView.scrollTop; listFocusId = item.id; }
    if (!internal) history.length = 0;
    detailOpen = true;
    listView.hidden = true;
    inspector.hidden = false;
    count.hidden = true;
    detailName.textContent = item.title;
    detailBookmark.hidden = true;
    previousButton.hidden = !history.length;
    backButton.focus({ preventScroll: true });
    selectedId = item.id;
    selected = null;
    translatedDetail = null;
    refineAcknowledgement.checked = false;
    application.hidden = true;
    updateApplyButton();
    for (const button of grid.querySelectorAll(".mmc-tech-card")) button.setAttribute("aria-pressed", String(button.dataset.technique === selectedId));
    detailBody.replaceChildren(el("p", { class: "mmc-tech-empty", text: t("Loading technique…") }));
    try {
      const detail = detailCache.get(item.id) ?? await loadJson(item.detail, detailController.signal);
      if (closed || version !== selectionVersion) return;
      if (!detail || detail.id !== item.id || !Array.isArray(detail.sections)) throw new Error(t("Invalid technique detail file."));
      detailCache.delete(item.id);
      detailCache.set(item.id, detail);
      while (detailCache.size > 20) detailCache.delete(detailCache.keys().next().value);
      const explanation = await loadTranslatedDetail(detail, detailController.signal);
      if (closed || version !== selectionVersion) return;
      translatedDetail = explanation;
      selected = detail;
      renderSubstitutions();
      if (restore) {
        currentTarget = availableTargets.find((entry) => entry.id === restore.targetId) ?? restore.target ?? null;
        if (currentTarget) targetSelect.value = currentTarget.id;
        mode = restore.mode;
        renderSubstitutions();
        if ([...subjectSelect.options].some((option) => option.value === restore.subject)) subjectSelect.value = restore.subject;
        durationInput.value = restore.duration;
        rememberSubstitutions();
      }
      renderDetail(detail);
      if (restore) {
        detailBody.scrollTop = restore.scroll;
        const restoreFocus = [...detailBody.querySelectorAll("[data-nav-key]")].find((node) => node.dataset.navKey === restore.focusKey);
        restoreFocus?.focus({ preventScroll: true });
      }
      announce(availableTargets.length ? t("Choose an insertion mode and review the preview before applying.") : t("Browse-only view. Open Techniques from a prompt to apply a technique."));
    } catch (error) {
      if (closed || version !== selectionVersion || error.name === "AbortError") return;
      detailBody.replaceChildren(el("p", { text: t("Could not load technique — {error}", { error: error.message ?? error }) }),
        el("button", { type: "button", text: t("Retry"), onclick: () => selectItem(item, { internal: true, restore }) }));
    }
  }
  async function loadCatalog() {
    grid.replaceChildren(el("p", { class: "mmc-tech-empty", text: t("Loading technique catalogue…") }));
    try {
      const data = catalogCache ?? await loadJson("catalog.json", controller.signal);
      if (closed) return;
      if (data?.version !== 1 || !Array.isArray(data.categories) || !Array.isArray(data.items)) throw new Error(t("Invalid technique catalogue."));
      catalog = data;
      catalogCache = data;
      const [translated, layout] = await Promise.all([loadTranslatedCatalog(data),
        structureCache ? Promise.resolve(structureCache) : loadJson("structure.json", controller.signal).catch(() => null)]);
      translatedCatalog = translated;
      structure = layout?.version === 1 && layout.sourceCapturedAt === data.capturedAt && layout.offsetEncoding === "utf16" ? layout : null;
      if (structure) structureCache = structure;
      if (closed) return;
      if (category && !data.categories.some((entry) => entry.id === category)) category = "";
      if (initialTechnique) {
        const initial = data.items.find((entry) => entry.id === initialTechnique);
        if (initial) { category = initial.categoryId; query = ""; search.value = ""; onlyBookmarks = false; }
      }
      renderCategories();
      renderGrid();
      listView.scrollTop = Number(view.scroll) || 0;
      // Reopening the library normally starts with its full-width list. Only
      // an explicit applied-technique/deep link opens a detail immediately.
      const previous = initialTechnique && catalog.items.find((entry) => entry.id === initialTechnique);
      if (previous) selectItem(previous);
      else announce(t("Hover over a card to preview. Select it to read the full original content."));
    } catch (error) {
      if (closed || error.name === "AbortError") return;
      count.textContent = "";
      grid.replaceChildren(el("p", { text: t("Could not load local technique catalogue — {error}", { error: error.message ?? error }) }),
        el("button", { type: "button", text: t("Retry"), onclick: loadCatalog }));
      announce(t("No catalogue was loaded. Check that the complete test package was extracted."), true);
    }
  }
  renderSubstitutions();
  loadCatalog();
  return close;
}

// Every word this UI says, said in the viewer's language.
//
// The language is not a setting of this pack. ComfyUI already asks the question
// — Settings → Comfy → Locale — and a second dropdown that could disagree with
// the first would make "which language am I in" a two-part answer. So this
// reads the frontend's own `Comfy.Locale` and follows it, falling back to the
// browser's tongue when the setting store has no answer (a fresh install, or
// the test harness's stub `app`).
//
// The key *is* the English sentence. Not `settings.done` or `editor.addImage`:
// the string the code always carried, looked up verbatim in a per-language
// dictionary. Three things fall out of that. A key with no translation shows
// the English rather than a bare `settings.done` token, so a half-finished
// dictionary degrades to the UI this pack always had. The dictionaries under
// `locales/` read as English → translation pairs a native speaker can review
// without the source open. And the code stays legible — `t("Add image")` says
// what the button says, where a key would say only where to look it up.
//
// The cost of that choice is a contract: the English string in the code and the
// key in the dictionary must match to the character. Editing a sentence here
// orphans its translations until the dictionaries catch up — which is the
// honest outcome, since the old translation described a sentence that no
// longer exists.
//
// Interpolation is `{name}` slots filled from a params object, not template
// literals — `t("Really delete {count}?", { count })` — because word order is
// the one thing a translation must be free to change, and a string already
// glued together leaves it nowhere to move.
//
// Translated at the moment of rendering, never at module load: these modules
// are imported while the app is still booting, before the setting store has
// answered, and a constant translated then would be English forever. The
// lookup is a map hit per call, which is nothing against building a DOM node.

// The app is read off `globalThis` rather than imported from scripts/app.js —
// deliberately. Half the pack's modules are imported standalone by the mirror
// tests (outputs.js against outputs.py, canvas.js against canvas.py), where
// ComfyUI's modules do not exist and a static import anywhere in the chain
// would be the one thing that breaks them. The frontend has published itself
// as `window.app` for years; where nothing has, t() speaks English.
import { ja } from "./locales/ja.js";
import { ko } from "./locales/ko.js";
import { zh } from "./locales/zh.js";

// `zh` answers for zh-TW too until someone contributes a Traditional
// dictionary — Simplified is the wrong script for Taiwan, but it is nearer
// than English.
const DICTIONARIES = { ja, ko, zh, "zh-TW": zh };

/** The dictionary for the frontend's current locale, or null for English.
 *  Read per call rather than cached: the setting can change under a running
 *  page, and everything this pack draws is rebuilt often enough to follow. */
function dictionary() {
  let locale;
  try {
    locale = globalThis.app?.extensionManager?.setting?.get?.("Comfy.Locale");
  } catch {
    locale = null;
  }
  locale ||= (typeof navigator !== "undefined" && navigator.language) || "en";
  return DICTIONARIES[locale] ?? DICTIONARIES[locale.split("-")[0]] ?? null;
}

/**
 * The one gate every user-facing string walks through.
 *
 * @param {string} text    the English string, verbatim — it is also the key
 * @param {object} [params] values for `{name}` slots, filled after lookup so
 *                          the translation orders them as its grammar wants
 */
export function t(text, params) {
  const translated = dictionary()?.[text] ?? text;
  if (!params) return translated;
  return translated.replace(/\{(\w+)\}/g, (slot, name) =>
    name in params ? String(params[name]) : slot);
}

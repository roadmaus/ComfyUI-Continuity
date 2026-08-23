// The families, as the server declares them — the frontend's one source of
// family knowledge.
//
// Everything a control needs to know about a family — its weight slots, its
// canvas rules, its sampler widgets, what its pre-stage still is called — is
// declared once, in Python, next to the code that renders it, and served at
// `/minimax_creator/families`. This module loads that catalog and every other
// frontend module reads it from here; a family constant spelled anywhere else
// in `web/creator/` is a leak (the phase-5 grep in docs/PLAN-multi-family.md
// is the audit).
//
// Loaded with top-level await, deliberately: importers see a resolved catalog
// or they do not load at all. A UI drawn from a catalog that "has not arrived
// yet" would need a placeholder state in every control, and a server that
// cannot answer this route could not queue a render either — failing the
// extension load, loudly, in the console, is the honest outcome.
//
// The mirror suites run this file under bare node, where ComfyUI's `api`
// module does not exist. They inject the catalog — the same JSON, dumped from
// `families/manifest.catalog()` by `tests/layout.py` — as
// `globalThis.__MMC_FAMILIES` before importing; the fetch is only reached in
// a real browser (and in the packed suites, whose stub serves the route).
// Strings in the catalog are English and are translation *keys*: render them
// through `t()`, the same as a string written in source.

const catalog = globalThis.__MMC_FAMILIES ?? await (async () => {
  const { api } = await import("../../../scripts/api.js");
  const response = await api.fetchApi("/minimax_creator/families");
  if (!response.ok) {
    throw new Error(`/minimax_creator/families answered ${response.status}`);
  }
  return response.json();
})();

if (!Array.isArray(catalog?.families) || !catalog.families.length) {
  throw new Error("/minimax_creator/families served no catalog");
}

/** Every family, in the registry's order. */
export const FAMILIES = catalog.families;

/** The pre-stage's arch pill vocabulary: arch id -> family id. The arch ids
 *  are frozen in saved blobs (`"minimax"` stays H3's alias). */
export const STILL_ARCHES = catalog.still_arches;
export const DEFAULT_STILL_ARCH = catalog.default_still_arch;

/** One family's manifest, by id. Unknown ids are a bug, not a state. */
export function family(id) {
  const found = FAMILIES.find((entry) => entry.id === id);
  if (!found) throw new Error(`unknown family ${JSON.stringify(id)}`);
  return found;
}

/** The family a pre-stage arch resolves to. */
export const stillFamily = (arch) => family(STILL_ARCHES[arch]);

/** The video family. One today; the timeline binds to it the way the loop
 *  binds to `registry.video()`. */
export const VIDEO = FAMILIES.find((entry) => entry.produces.includes("video"));

// The families, as the server declares them — the frontend's one source of
// family knowledge.
//
// Everything a control needs to know about a family — its weight slots, its
// canvas rules, its sampler widgets, what its pre-stage still is called — is
// declared once, in Python, next to the code that renders it, and served at
// `/continuity/families`. This module loads that catalog and every other
// frontend module reads it from here; a family constant spelled anywhere else
// in `web/creator/` is a leak, and `tests/test_family_leaks.py` is the grep
// that says so.
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
  const response = await api.fetchApi("/continuity/families");
  if (!response.ok) {
    throw new Error(`/continuity/families answered ${response.status}`);
  }
  return response.json();
})();

if (!Array.isArray(catalog?.families) || !catalog.families.length) {
  throw new Error("/continuity/families served no catalog");
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

/** Which families render video, and which one a piece that names none is.
 *  Both served rather than worked out here: the compiler validates a piece's
 *  `family` against exactly this list and reads an absent one as exactly this
 *  default, and a pill offering a different set would offer a choice the
 *  backend does not accept. Mirrors `registry.video_families()` /
 *  `registry.DEFAULT_VIDEO`. */
export const VIDEO_FAMILIES = catalog.video_families;
export const DEFAULT_VIDEO_FAMILY = catalog.default_video_family;

/** The manifest of the family a piece renders with.
 *
 *  Unlike `family()` this forgives: an unknown id is the default, not a throw,
 *  because the id comes out of a saved blob rather than out of the code, and
 *  `compile.piece_family` forgives it on the same terms. Call this wherever the
 *  argument is `piece.family`; call `family()` where it is an id the code
 *  itself produced. */
export const videoFamily = (id) =>
  family(VIDEO_FAMILIES.includes(id) ? id : DEFAULT_VIDEO_FAMILY);

/** The default video family's manifest, under the name every reader bound to
 *  the one video family this pack shipped still imports. Family-aware readers
 *  take `videoFamily(piece.family)` instead. */
export const VIDEO = videoFamily(DEFAULT_VIDEO_FAMILY);

/** The upscale backends that belong to no family — ReDetail re-renders a
 *  finished pass through LTX 2.5's weights whatever family made it. Served
 *  beside the families for exactly that reason: listing its files inside H3's
 *  manifest would read as H3 having grown a transformer. */
export const UPSCALERS = catalog.upscalers ?? [];

/** One backend's manifest, by the id `piece.upscale` names. Undefined where
 *  the mode is a family's own pass — `two_pass` and `direct` are not
 *  backends, they are what the family does by itself. */
export const upscaler = (id) => UPSCALERS.find((entry) => entry.id === id);

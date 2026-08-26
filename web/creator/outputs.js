// Where a render lands under ComfyUI/output — the mirror of `outputs.py`.
//
// The duplication is the same deal `canvas.js` has with `canvas.py`: the field
// tells you what is wrong while you are typing, and shows the folder the files
// will actually land in, which cannot wait for a queue round-trip. `outputs.py`
// is authoritative and refuses the same strings at execute time; a hand-edited
// blob never reaches this file at all. `tests/test_outputs_mirror.py` asserts
// the two still agree.

import { t } from "./i18n.js";

// The two shelves everything lands under. Where a *family* lands inside them is
// composed on the Python side and served in its manifest (`output`), because
// the save node and the settings page must show one answer, not two spellings
// of it. These are here for the mirror test, which is what holds the two files
// together at all.
export const RENDERS = "minimax/renders";
export const STILLS = "minimax/stills";

// What core's `compute_vars` expands, in the order the hint lists them.
export const TOKENS = ["%year%", "%month%", "%day%", "%hour%", "%minute%", "%second%",
                       "%width%", "%height%"];

// Windows cannot create these, and a workflow shared from a Mac should not
// produce a folder its Windows half cannot write into. Mirrors outputs.ILLEGAL.
// eslint-disable-next-line no-control-regex
const ILLEGAL = /[<>:"|?*\u0000-\u001f]/;

/**
 * A typed prefix -> `{prefix}` or `{error}`. Never both.
 *
 * Returning the error rather than throwing it is what lets the field show the
 * reason under a value the user is still editing instead of clearing it.
 *
 * @param {string} raw
 * @param {string} fallback   the node's default, used when the field is empty
 */
export function cleanPrefix(raw, fallback) {
  const text = String(raw ?? "").trim().replace(/\\/g, "/");
  if (!text) return { prefix: fallback };

  if (text.startsWith("/") || /^[A-Za-z]:/.test(text)) {
    return { error: t("Absolute paths are not allowed — this is relative to ComfyUI's "
                    + "output folder. Use --output-directory to move that.") };
  }

  // A trailing slash names a folder; keep the default's filename stem.
  const whole = text.endsWith("/") ? text + fallback.split("/").pop() : text;

  const parts = whole.split("/");
  for (const part of parts) {
    if (!part) return { error: t("Empty folder name.") };
    if (part === "." || part === "..") return { error: t("'.' and '..' are not allowed.") };
    if (part.startsWith(".")) return { error: t("Folder names cannot start with a dot.") };
    if (ILLEGAL.test(part)) return { error: t('A name cannot contain any of < > : " | ? *') };
    if (part.endsWith(" ") || part.endsWith(".")) {
      return { error: t("A name cannot end with a space or a dot.") };
    }
  }
  return { prefix: parts.join("/") };
}

/** The folder half of a prefix — what the gallery will file the result under.
 *  "" means the root of the output folder. */
export function folderOf(prefix) {
  const cut = prefix.lastIndexOf("/");
  return cut === -1 ? "" : prefix.slice(0, cut);
}

/** The filename half: the stem every file in that folder is numbered off. */
export function stemOf(prefix) {
  return prefix.slice(prefix.lastIndexOf("/") + 1);
}

/**
 * What the first file will be called, with the tokens filled in from the clock
 * — the whole point of the preview line under the field, since `%month%` on its
 * own does not tell anyone whether they are getting `08` or `August`.
 *
 * The counter is core's, per folder and per stem, so `_00001_` is only right
 * for the first render into an empty one. Shown as an example, labelled as one.
 */
export function examplePath(prefix, { extension = "mp4", width = 1344, height = 768 } = {}) {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const filled = prefix
    .replaceAll("%year%", String(now.getFullYear()))
    .replaceAll("%month%", pad(now.getMonth() + 1))
    .replaceAll("%day%", pad(now.getDate()))
    .replaceAll("%hour%", pad(now.getHours()))
    .replaceAll("%minute%", pad(now.getMinutes()))
    .replaceAll("%second%", pad(now.getSeconds()))
    .replaceAll("%width%", String(width))
    .replaceAll("%height%", String(height));
  return `${filled}_00001_.${extension}`;
}

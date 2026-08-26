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
export const RENDERS = "continuity/renders";
export const STILLS = "continuity/stills";

// What core's `compute_vars` expands, in the order the hint lists them. The
// split is real and the chip row draws it: the first six come off the clock at
// the moment the file is written, the last two off the frame being written.
export const CLOCK_TOKENS = ["%year%", "%month%", "%day%", "%hour%", "%minute%", "%second%"];
export const FRAME_TOKENS = ["%width%", "%height%"];
export const TOKENS = [...CLOCK_TOKENS, ...FRAME_TOKENS];

// One token, whole. Used to find them inside typed or pasted text — the field
// draws each one as a single tile, so it has to know where one starts and ends
// rather than treating `%` as a character like any other.
const TOKEN_RE = new RegExp(TOKENS.join("|"), "g");

/** The word a token wears on screen. The `%` is core's syntax, not something a
 *  reader of a folder name should have to look at. */
export function tokenLabel(token) {
  return token.replaceAll("%", "");
}

/**
 * What every token expands to right now.
 *
 * One table, because the preview line under the field and the chip that inserts
 * the token have to agree about whether `%month%` is `08` or `August`, and a
 * chip that says one thing while the line below says another is worse than no
 * chip at all.
 */
export function tokenValues({ width = 1344, height = 768, now = new Date() } = {}) {
  const pad = (n) => String(n).padStart(2, "0");
  return {
    "%year%": String(now.getFullYear()),
    "%month%": pad(now.getMonth() + 1),
    "%day%": pad(now.getDate()),
    "%hour%": pad(now.getHours()),
    "%minute%": pad(now.getMinutes()),
    "%second%": pad(now.getSeconds()),
    "%width%": String(width),
    "%height%": String(height),
  };
}

/**
 * A prefix split into the literal text and the whole tokens inside it, in order.
 *
 * `[{ text }]` and `[{ token }]` parts, never a part that is both. This is what
 * lets the field draw a token as one object: the caret can sit either side of a
 * tile but there is no position *inside* one, which is the whole reason
 * `minima%sssyear%%month%x` was typeable at all.
 */
export function splitTokens(text) {
  const parts = [];
  let at = 0;
  for (const match of String(text ?? "").matchAll(TOKEN_RE)) {
    if (match.index > at) parts.push({ text: text.slice(at, match.index) });
    parts.push({ token: match[0] });
    at = match.index + match[0].length;
  }
  if (at < text.length) parts.push({ text: text.slice(at) });
  return parts;
}

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
  const values = tokenValues({ width, height });
  const filled = prefix.replaceAll(TOKEN_RE, (token) => values[token]);
  return `${filled}_00001_.${extension}`;
}

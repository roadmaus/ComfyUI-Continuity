// How a vendored catalogue frame is addressed, once a look has been cast.
//
// Every other picture in this pack is a file under ComfyUI/input, named by an
// input-relative path, and that is the only address `media.resolve` knows. A
// style's frame is the one picture that is *already* on disk before anyone asks
// for it — a thousand of them, shipped in `./atlas/full/` — so casting a look
// used to copy the frame into `input/style_refs/` for no reason but to give it
// an address of the kind everything downstream expected. The copies were
// permanent, one per look ever cast, and they turned up as a shelf in the picker
// and as rows in every core LoadImage combo on the canvas.
//
// So a look's frame gets an address of its own instead: `atlas:000123`, the
// clip's id and nothing else. Two functions resolve it — `api.viewUrl` for the
// browser and `media.resolve` for the graph — and both are the single door their
// side already went through, which is the whole reason a second species of path
// stays affordable. Nothing else parses one.
//
// Old `style_refs/...` paths in saved presets and workflows are ordinary input
// paths and keep working untouched; this is what *new* casts write.
//
// One module rather than a constant on each side, because the browser half of
// the pair also needs to know where the pictures sit, and that is here.

/** What every catalogue reference starts with. */
export const ATLAS_SCHEME = "atlas:";

/** A clip id is digits — the atlas names them `000001`. Anything else is not
 *  ours, and `atlasUrl` must never build a path out of it. */
const CLIP_RE = /^\d+$/;

/** The address of one clip's full-size frame. */
export const atlasRef = (clip) => `${ATLAS_SCHEME}${clip}`;

/** Is this filename one of ours rather than an input path? */
export function isAtlasRef(path) {
  return typeof path === "string" && path.startsWith(ATLAS_SCHEME);
}

/** The frame's URL in the extension's own web folder, or null if the reference
 *  names no clip this pack ships. Off `import.meta.url`, so the installed folder
 *  name stays the browser's business — the same trick `stylelib.js` uses for the
 *  card pictures. */
export function atlasUrl(path) {
  if (!isAtlasRef(path)) return null;
  const clip = path.slice(ATLAS_SCHEME.length);
  if (!CLIP_RE.test(clip)) return null;
  return new URL(`./atlas/full/${clip}.webp`, import.meta.url).href;
}

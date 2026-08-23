// Talking to the server: list the input folder, upload into it, build view URLs.

import { api } from "../../../scripts/api.js";
import { t } from "./i18n.js";
import { atlasUrl, isAtlasRef } from "./presets/atlasref.js";
import { applyTextScale, applySurfaceLift, applyTheme } from "./styles.js";

const cache = new Map();   // root -> {at, assets}
const CACHE_MS = 4000;

/** The media listing: `root: "input"` (the default) is the upload folder,
 *  `root: "output"` is finished renders — the picker's gallery tab. */
export async function listAssets({ force = false, root = "input" } = {}) {
  const hit = cache.get(root);
  if (!force && hit && Date.now() - hit.at < CACHE_MS) return hit.assets;
  const response = await api.fetchApi(`/minimax_creator/assets?root=${encodeURIComponent(root)}`);
  if (!response.ok) throw new Error(t("asset listing failed ({status})", { status: response.status }));
  const body = await response.json();
  const assets = body.assets ?? [];
  cache.set(root, { at: Date.now(), assets, truncated: body.truncated === true });
  return assets;
}

/** Whether the last listing of `root` hit the server's cap — the folder holds
 *  more files than came back. Read after listAssets; false before any call. */
export function listingTruncated(root = "input") {
  return cache.get(root)?.truncated === true;
}

/** Drop a cached listing. One root by name, or all of them when called bare —
 *  which is what a move or a delete wants, since an annotated filename can name
 *  either folder and the caller does not unpack it to find out. */
export function invalidate(root) {
  if (root) cache.delete(root); else cache.clear();
}

/** Put a row into a cached listing without asking the server for it again.
 *  A no-op when that root has not been listed yet: there is no listing to be
 *  newest in, and the next real one will find the file on disk anyway. */
function remember(root, asset) {
  const hit = cache.get(root);
  if (!hit) return;
  hit.assets = [asset, ...hit.assets.filter((a) => a.path !== asset.path)];
}

/** Move one file into another subfolder of the root it already lives in — the
 *  picker's drag-onto-a-shelf. Resolves to the file's new path, annotated as it
 *  came in, so a moved render is still addressable as a render.
 *
 *  Which root is not a parameter: `filename` carries its own ` [output]` when
 *  it is a gallery path, and the server reads the root off that rather than
 *  trusting a second field that could disagree with it. */
export async function moveAsset(filename, subfolder) {
  const response = await api.fetchApi("/minimax_creator/move", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename, subfolder }),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || t("move failed ({status})", { status: response.status }));
  invalidate();
  return body.path;
}

/** Delete one file, from whichever of the two folders it names. Organize
 *  mode's other action, and the only irreversible one in the picker. */
export async function deleteAsset(filename) {
  const response = await api.fetchApi("/minimax_creator/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename }),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || t("delete failed ({status})", { status: response.status }));
  invalidate();
}

// ---- picker preferences -----------------------------------------------------
//
// Favorites, hand-made shelves, and the folder each root was last left in.
// Stored per ComfyUI user via the userdata API, so they follow the user across
// browsers; localStorage is the fallback for frontends without it. One object:
// {favorites: [path], folders: [name], renderFolders: [name],
//  lastShelf: {input, renders}}.
//
// Two folder lists because the picker browses two folders — `folders` is the
// input one and keeps its name so prefs written before the gallery could be
// organized load unchanged. Favorites need no such split: a gallery path
// carries its ` [output]` annotation, so the two roots cannot collide.

const PREFS_FILE = "minimax_creator.picker.json";
const PREFS_KEY = "mmc-picker-prefs";
let prefsCache = null;

const names = (value) => (Array.isArray(value) ? value.filter((p) => typeof p === "string") : []);
const shelfName = (value) => (typeof value === "string" ? value : "all");

function normalizePrefs(raw) {
  return {
    favorites: names(raw?.favorites),
    folders: names(raw?.folders),
    renderFolders: names(raw?.renderFolders),
    // Where the picker was last left, one per root. The picker checks the
    // folder is still there before opening on it — a remembered place can be
    // renamed or emptied between sessions.
    lastShelf: {
      input: shelfName(raw?.lastShelf?.input),
      renders: shelfName(raw?.lastShelf?.renders),
    },
  };
}

export async function loadPickerPrefs() {
  if (prefsCache) return prefsCache;
  let raw = null;
  try {
    const response = await api.getUserData(PREFS_FILE);
    if (response.status === 200) raw = await response.json();
  } catch {
    try { raw = JSON.parse(localStorage.getItem(PREFS_KEY) ?? "null"); } catch { /* fresh */ }
  }
  prefsCache = normalizePrefs(raw);
  return prefsCache;
}

export function savePickerPrefs(prefs) {
  prefsCache = normalizePrefs(prefs);
  const body = JSON.stringify(prefsCache);
  try { localStorage.setItem(PREFS_KEY, body); } catch { /* quota; userdata still tries */ }
  // Fire and forget: a star should feel instant, and losing one write is
  // recoverable in a way a blocked click is not.
  try { api.storeUserData(PREFS_FILE, prefsCache, { stringify: true }); } catch { /* offline */ }
}

// ---- settings ---------------------------------------------------------------
//
// Not the userdata API the picker prefs above go through, and the difference
// matters: these are read by the save node while a prompt executes, which has no
// request behind it and so no ComfyUI user. `settings.py` owns the one file both
// ends read, and these two routes are the only way in from here.

/** Every setting, with the keys this build does not know about dropped. */
export async function loadSettings() {
  const response = await api.fetchApi("/minimax_creator/settings");
  if (!response.ok) throw new Error(t("settings failed ({status})", { status: response.status }));
  return (await response.json()).settings ?? {};
}

/** Store some settings and resolve to the whole stored object — what the server
 *  actually wrote, which is what the page then shows. */
export async function saveSettings(patch) {
  const response = await api.fetchApi("/minimax_creator/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || t("settings failed ({status})", { status: response.status }));
  return body.settings ?? {};
}

/** What the reference cache is holding on disk: `{ entries, bytes }`.
 *
 *  Its own route rather than a key in the settings blob, for the reason the
 *  route says: the settings are what this machine was told, and this is what
 *  came of it. */
export async function loadLatentCache() {
  const response = await api.fetchApi("/minimax_creator/latent_cache");
  if (!response.ok) throw new Error(t("cache failed ({status})", { status: response.status }));
  return await response.json();
}

/** Delete every cached reference; resolves to the emptied `{ entries, bytes }`. */
export async function clearLatentCache() {
  const response = await api.fetchApi("/minimax_creator/latent_cache/clear", { method: "POST" });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || t("cache failed ({status})", { status: response.status }));
  return body;
}

// The settings page re-fetches on every opening — the server is the only copy
// it trusts. The node bodies cannot do that: the sampler row is drawn
// synchronously on every render, and some of what it draws (the shift pills'
// visibility) is a setting. So this holds the last answer the server gave —
// primed once when the first body mounts, kept current by the settings page
// writing every reply through `noteSettings`. Until the first answer lands the
// fallbacks are in force, which are the server's own defaults.
let uiSettings = null;
let uiSettingsPrimed = null;

export function uiSetting(key, fallback) {
  return uiSettings && key in uiSettings ? uiSettings[key] : fallback;
}

/** The settings page's replies come through here, so the cache is never older
 *  than the last thing the page showed.
 *
 *  Three of these settings are not read by anyone: the text scale, the surface
 *  lift and the theme are things the stylesheet needs, not things a body draws.
 *  They are written onto the document here rather than by the page that sets
 *  them, because this is every route the settings take — the first prime, the
 *  page, the shortcut below — and the alternative is three call sites that have
 *  to agree. */
export function noteSettings(settings) {
  uiSettings = settings;
  applyTextScale(settings?.text_scale);
  applySurfaceLift(settings?.surface_lift);
  applyTheme(settings?.theme);
}

/**
 * Write one setting through from somewhere that is not the settings page — the
 * sampler row's lead-in stepper, so far.
 *
 * Painted first and corrected after, the same deal the page has: the cache is
 * noted optimistically so the pill moves under the pointer, and the server's
 * own answer replaces it. A refusal puts the old value back, because a value
 * the server would not store must not be left on a pill looking set.
 *
 * There is one copy of these settings and this is a shortcut into it, not a
 * second store: other open nodes read the new value the next time they redraw.
 */
export async function patchSettings(patch) {
  const previous = uiSettings;
  noteSettings({ ...(uiSettings ?? {}), ...patch });
  try {
    noteSettings(await saveSettings(patch));
    return true;
  } catch {
    uiSettings = previous;
    return false;
  }
}

/** Fetch the settings once, ever; `onReady` fires when the cache holds them —
 *  immediately, after the first caller's fetch has already landed. */
export function primeSettings(onReady) {
  uiSettingsPrimed = uiSettingsPrimed ?? loadSettings().then(noteSettings).catch(() => {});
  if (onReady) uiSettingsPrimed.then(onReady);
}

let modelsAt = 0;
let modelsCache = null;
let modelsInFlight = null;

/**
 * What the weights control can offer: `{files: {field: [name]}, dtypes,
 * preview_override}`.
 *
 * Every node body asks for this the moment it is built, and a graph can hold a
 * dozen of them, so concurrent callers share one request rather than each
 * walking the model folders. Cached longer than the asset listing: models are
 * downloaded occasionally where input files arrive constantly, and the answer is
 * behind a control you have to open before it matters.
 */
export async function listModels({ force = false } = {}) {
  if (!force && modelsCache && Date.now() - modelsAt < 60000) return modelsCache;
  if (!force && modelsInFlight) return modelsInFlight;
  modelsInFlight = (async () => {
    try {
      const response = await api.fetchApi("/minimax_creator/models");
      if (!response.ok) throw new Error(t("model listing failed ({status})", { status: response.status }));
      modelsCache = await response.json();
      modelsAt = Date.now();
      return modelsCache;
    } finally {
      modelsInFlight = null;
    }
  })();
  return modelsInFlight;
}

/** Core's /view, pointed at output rather than input — how a finished render is
 *  played back in the node body. Takes a `SavedResult` verbatim, which is what
 *  the `executed` message carries. */
export function outputUrl({ filename, subfolder = "", type = "output" }) {
  return api.apiURL(`/view?${new URLSearchParams({ filename, subfolder, type })}`);
}

// Keyed by folder: switching between two folders and back is a normal thing to
// do while hunting for a LoRA, and re-walking a few thousand files for it is not.
const loraCache = new Map();   // folder -> {at, body}

/**
 * One folder of models/loras, each row carrying whatever the sidecars beside it
 * know — CiviMeta, Lora Manager, `.civitai.info`, A1111, or nothing but a
 * preview image. `folder` is a relative path, "" for everything; the reply also
 * carries the folder list, so the manager never has to ask for it separately.
 *
 * `force` is the Rescan button, and it clears the server's caches as well as
 * this one: the server holds a directory listing briefly and a row for as long
 * as nothing beside the file changes, neither of which notices a sidecar edited
 * in place. A button that says "look again" has to reach that far.
 *
 * @returns {Promise<{loras: object[], folders: {path: string, count: number}[],
 *                    folder: string, matched: number, truncated: boolean}>}
 */
export async function listLoras({ folder = "", force = false } = {}) {
  const hit = loraCache.get(folder);
  if (!force && hit && Date.now() - hit.at < CACHE_MS) return hit.body;
  const query = new URLSearchParams({ folder });
  if (force) query.set("refresh", "1");
  const response = await api.fetchApi(`/minimax_creator/loras?${query}`);
  if (!response.ok) throw new Error(t("LoRA listing failed ({status})", { status: response.status }));
  const body = await response.json();
  if (force) loraCache.clear();
  loraCache.set(folder, { at: Date.now(), body });
  return body;
}

/** The card's image or clip, from wherever the server found one — a sidecar's
 *  gallery, a `.preview.png` beside the file, or a thumbnail embedded in the
 *  safetensors header. 404s into the card's fallback when there is nothing. */
export function loraPreviewUrl(name) {
  return api.apiURL(`/minimax_creator/lora_preview?name=${encodeURIComponent(name)}`);
}

const detailCache = new Map();   // name -> {at, detail}

/**
 * Everything the detail sheet shows for one LoRA: the merged sidecar record
 * with its showcase and generation recipes, and the safetensors header either
 * way. Cached briefly — closing and reopening the same sheet is a normal way
 * to read, and nothing in it changes at that cadence.
 */
export async function loraDetail(name) {
  const hit = detailCache.get(name);
  if (hit && Date.now() - hit.at < 60000) return hit.detail;
  const response = await api.fetchApi(`/minimax_creator/lora_detail?name=${encodeURIComponent(name)}`);
  if (!response.ok) throw new Error(t("detail failed ({status})", { status: response.status }));
  const detail = await response.json();
  detailCache.set(name, { at: Date.now(), detail });
  return detail;
}

/** One showcase file by its index in the detail's list; `thumb` asks for the
 *  filmstrip-sized WebP, which falls back to the media file server-side. */
export function loraShowcaseUrl(name, item, { thumb = false } = {}) {
  const params = new URLSearchParams({ name, item: String(item) });
  if (thumb) params.set("thumb", "1");
  return api.apiURL(`/minimax_creator/lora_showcase?${params}`);
}

const PROBES = new Map();   // path -> Promise<{hasAudio, duration, width, height}>

/**
 * What the container header says: `{hasAudio: true|false|null, duration}`, both
 * null when the question could not be answered.
 *
 * `hasAudio` decides whether a reference video is attached with its sound on,
 * and it has to be a server question: `mozHasAudio` is Firefox-only and
 * `audioTracks` is not in Chrome, so there is no portable way to ask the media
 * element. `duration` is the segment editor's fallback for when the browser
 * cannot decode the clip itself. `width`/`height` are the picture's own size,
 * which a clip card stores so the timeline's aspect can come off the footage
 * without the backend opening the file.
 */
export function probe(path) {
  if (!PROBES.has(path)) PROBES.set(path, ask(path));
  return PROBES.get(path);
}

/** Just the soundtrack question, for callers that want nothing else. */
export async function probeAudio(path) {
  return (await probe(path)).hasAudio;
}

async function ask(path) {
  try {
    const response = await api.fetchApi(`/minimax_creator/probe?filename=${encodeURIComponent(path)}`);
    const body = await response.json();
    return {
      hasAudio: typeof body.has_audio === "boolean" ? body.has_audio : null,
      duration: Number.isFinite(body.duration) ? body.duration : null,
      width: Number.isFinite(body.width) ? body.width : null,
      height: Number.isFinite(body.height) ? body.height : null,
    };
  } catch {
    return { hasAudio: null, duration: null, width: null, height: null };
  }
}

/**
 * The workflow a finished render carries inside itself.
 *
 * Both save nodes embed it — the MP4 in its container tags, the PNG in its text
 * chunks — so that a render dropped onto the canvas rebuilds the node that made
 * it. Nothing in the browser can read either, hence the route.
 *
 * Resolves to `{prompt, workflow}`, both parsed and either possibly null. The
 * useful one is `prompt`: it is the API form, whose inputs are keyed by *name*,
 * where `workflow.nodes[].widgets_values` is a positional array that shifts
 * under the node whenever a widget is added. Not cached — this is one request
 * when a render is picked, and it is read for its exact bytes on disk.
 */
export async function renderMeta(path) {
  const response = await api.fetchApi(
    `/minimax_creator/render_meta?filename=${encodeURIComponent(path)}`);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.error || t("could not read that render ({status})", { status: response.status }));
  }
  if (body.error) throw new Error(body.error);
  return { prompt: body.prompt ?? null, workflow: body.workflow ?? null };
}

/**
 * Core's /view, the same URL LoadImage previews use.
 *
 * Takes the input-relative path ("3d/foo.png"), not an asset row: only the path
 * survives into creator_data, so a reloaded workflow has nothing else to go on.
 */
export function viewUrl(path, { preview = false } = {}) {
  // A cast look's frame is not in the input folder and never was: it is a file
  // this pack ships, served out of WEB_DIRECTORY. Answered here rather than at
  // each of the dozen call sites, for the reason `media.resolve` answers it on
  // the other side — one door in, so a second species of path costs two
  // branches instead of thirty. See `presets/atlasref.js`.
  if (isAtlasRef(path)) return atlasUrl(path);
  // A gallery path carries ComfyUI's folder annotation ("clip.mp4 [output]").
  // The servers that take a filename parse it themselves; core's /view takes
  // the folder as a parameter instead, so it is split off here.
  const annotated = /^(.*) \[(input|output|temp)\]$/.exec(String(path));
  const clean = annotated ? annotated[1] : String(path);
  const at = clean.lastIndexOf("/");
  const params = new URLSearchParams({
    filename: at < 0 ? clean : clean.slice(at + 1),
    subfolder: at < 0 ? "" : clean.slice(0, at),
    type: annotated ? annotated[2] : "input",
  });
  // Core re-encodes to webp when asked. It does not downscale, but a 4000px
  // PNG served as q70 webp is a fraction of the bytes, and a picker showing
  // thirty of them at 140px has no use for the originals.
  if (preview) params.set("preview", "webp;70");
  return api.apiURL(`/view?${params}`);
}

/**
 * A server-decoded still of one clip.
 *
 * The grid used to hang a <video preload="metadata"> in every cell and let the
 * browser seek for a frame. That is one media download per cell through a
 * six-connection budget, megabytes each to paint 140 px, and it needs the
 * browser to have an H.264 decoder at all — which a distro Chromium often does
 * not. This is a few KB of JPEG instead.
 *
 * `version` is the asset's mtime, which is what makes the URL safe to cache
 * forever: re-uploading the file changes the URL rather than staling the image.
 */
export function thumbUrl(path, version) {
  const params = new URLSearchParams({ filename: path });
  if (version) params.set("v", String(version));
  return api.apiURL(`/minimax_creator/thumb?${params}`);
}

/**
 * The URL that shows one media file as a still picture, or null for a file that
 * has none.
 *
 * The two routes above answer for different kinds and the choice is not
 * cosmetic: an image is core's `/view` re-encoded to webp, while a clip has to
 * come through this pack's thumb route, because an `<img>` pointed at an `.mp4`
 * renders nothing at all. Audio has no picture and gets an icon from whoever is
 * drawing.
 *
 * One implementation, because every grid in this pack asks the same question —
 * the picker's cells, the gallery, the preset library's cards. Takes an asset row
 * as the listing produces it (`{path, kind, mtime}`), which is also the shape
 * anything storing a reference to one should keep it in.
 */
export function stillUrl(asset) {
  if (!asset?.path) return null;
  if (asset.kind === "video") return thumbUrl(asset.path, asset.mtime);
  if (asset.kind === "image") return viewUrl(asset.path, { preview: true });
  return null;
}

/**
 * Waveform peaks for the segment editor, normalised to 0..1, or null when there
 * is nothing to draw. Decoded server-side and cached there by mtime.
 */
export async function fetchPeaks(path) {
  try {
    const response = await api.fetchApi(`/minimax_creator/peaks?filename=${encodeURIComponent(path)}`);
    if (!response.ok) return null;
    const body = await response.json();
    return Array.isArray(body.peaks) ? Float32Array.from(body.peaks) : null;
  } catch {
    return null;
  }
}

// Which tab a file belongs on. The listing route asks core's mimetype table the
// same question; a File already carries the browser's answer, and the extension
// covers what it leaves blank (.mkv and .flac come back empty in some
// browsers). Null when neither knows, which is the caller's cue to list the
// folder properly rather than invent a row — though a file core cannot classify
// either is one no listing was going to show.
const EXTENSIONS = {
  image: ["png", "jpg", "jpeg", "webp", "gif", "bmp", "tif", "tiff", "avif"],
  video: ["mp4", "webm", "mkv", "mov", "avi", "m4v", "mpg", "mpeg", "wmv"],
  audio: ["mp3", "wav", "flac", "ogg", "opus", "m4a", "aac", "wma"],
};

function kindOf(file, name) {
  const top = (file.type || "").split("/")[0];
  if (top === "image" || top === "video" || top === "audio") return top;
  const extension = name.slice(name.lastIndexOf(".") + 1).toLowerCase();
  for (const [kind, list] of Object.entries(EXTENSIONS)) {
    if (list.includes(extension)) return kind;
  }
  return null;
}

/**
 * Upload into the input folder. Core's /upload/image is what LoadVideo and
 * LoadAudio post to as well, despite the name — there is no separate endpoint.
 *
 * Resolves to a listing row rather than to a name, because the upload response
 * plus the File already say everything a grid cell reads, and the row goes
 * straight into the cached input listing. Walking the folder again to be told
 * what we just put there is what made a two-megabyte upload take minutes on a
 * machine with a large output folder (#4) — and it re-listed *output* too, which
 * an upload into input cannot have changed.
 */
export async function upload(file, subfolder = "") {
  const form = new FormData();
  form.append("image", file);
  if (subfolder) form.append("subfolder", subfolder);
  const response = await api.fetchApi("/upload/image", { method: "POST", body: form });
  if (!response.ok) throw new Error(t("upload failed ({status})", { status: response.status }));
  const body = await response.json();
  const name = body.name;
  const into = body.subfolder || "";
  const kind = kindOf(file, name);
  const asset = {
    path: into ? `${into}/${name}` : name,
    name,
    subfolder: into,
    kind,
    size: file.size,
    // Seconds, as the listing route reports it. The server's own mtime will be
    // a shade later; nothing reads this but the newest-first sort.
    mtime: Date.now() / 1000,
  };
  if (kind) remember("input", asset); else invalidate("input");
  return asset;
}

// ---- the prompt the model actually reads -------------------------------------
//
// The box shows two things: the sentence you typed, and the sectioned prompt the
// compiler builds out of it. The second one comes from the server because it is
// the compiler that builds it — a mirror of `contextir.compose` in here would be
// a second opinion, and it would agree right up until the disagreement was the
// thing worth seeing. `state.js` used to hold such a mirror for the scope band
// and it drifted from `contextir._DEFINE` twice.
//
// One request at a time, and the caller enforces it — see
// `PromptBox.refreshCompiled`. This function used to drop every answer but the
// newest by sequence number, which is the right rule for a racing UI and the
// wrong one here: the panel asks again on every render, so while renders kept
// arriving the newest ask was never the one that had landed and the panel stayed
// empty. Serialising at the caller means there is never a stale answer to drop.

/**
 * Compile `creatorData` and answer with one entry per pass.
 *
 * Never throws and never answers with nothing: a server that is unreachable or
 * a blob that will not compile comes back as `problem` text for the panel to
 * show, because an empty panel says the feature is broken when the truth is
 * that the piece is half-typed.
 *
 * @param {object} creatorData  the node's blob, exactly as it is saved
 * @returns {Promise<{passes: object[], cards?: object, problem?: string}>}
 */
export async function compiledPrompt(creatorData) {
  let body;
  try {
    const response = await api.fetchApi("/minimax_creator/compiled_prompt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ creator_data: creatorData }),
    });
    body = await response.json().catch(() => ({}));
    if (!response.ok) {
      body = { passes: [], problem: body.error
               || t("could not compile ({status})", { status: response.status }) };
    }
  } catch (problem) {
    // The server being unreachable is not a fact about the prompt, so it is
    // reported as a problem in the panel rather than thrown at the editor.
    body = { passes: [], problem: String(problem?.message || problem) };
  }
  return body;
}

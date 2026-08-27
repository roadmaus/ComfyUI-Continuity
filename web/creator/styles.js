// Injected once. Everything is scoped under .mmc-root (or .mmc-overlay for the
// modal, which portals to document.body) so nothing leaks into the graph canvas.
//
// The CSS itself lives in styles/, one module per area of the UI, each exporting
// a single template literal. Concatenation order below is cascade order — keep
// base first (it owns the :root tokens) and the rest in place unless a rule is
// meant to override an earlier section.

import { css as base } from "./styles/base.js";
import { css as stage } from "./styles/stage.js";
import { css as editor } from "./styles/editor.js";
import { css as popovers } from "./styles/popovers.js";
import { css as picker } from "./styles/picker.js";
import { css as loras } from "./styles/loras.js";
import { css as overlays } from "./styles/overlays.js";
import { css as settings } from "./styles/settings.js";
import { css as timeline } from "./styles/timeline.js";
import { css as cast } from "./styles/cast.js";
import { css as refine } from "./styles/refine.js";
import { css as prestage } from "./styles/prestage.js";
import { css as presets } from "./styles/presets.js";
import { css as fullscreen } from "./styles/fullscreen.js";
import { css as control } from "./styles/control.js";

const CSS = [
  base,
  stage,
  editor,
  popovers,
  picker,
  loras,
  overlays,
  settings,
  timeline,
  // After the timeline's: the shelf is mounted inside both the node body and
  // the timeline window, and a couple of its rules narrow what each of those
  // says about the elements it wraps.
  cast,
  refine,
  prestage,
  // After the picker's: the library reuses its modal, tabs and shelves and
  // overrides the grid inside them.
  presets,
  // After the picker's too: the bench rides on the picker's overlay and undoes
  // the three things a centred modal wants that a whole room does not.
  control,
  // Last: the shell hosts every body in the pack and lifts the caps the node
  // face put on them, so its rules have to win over the sections that set them.
  fullscreen,
].join("");

/* What the settings hold that the stylesheet cannot: how large the text is
 * drawn. It is one custom property (--mmc-type, documented in styles/base.js)
 * and it goes on the document element rather than on any of the pack's roots —
 * the popovers, the picker and the modals all portal to document.body, so a
 * scale set on a node body would stop at the edge of that body.
 *
 * Clamped here as well as on the server: this runs off whatever the settings
 * file happens to hold, and a hand-edited 12 would draw one word across the
 * whole screen with no way left on it to say otherwise.
 */
export function applyTextScale(scale) {
  const value = Number(scale);
  const safe = Number.isFinite(value) ? Math.min(1.6, Math.max(0.8, value)) : 1;
  document.documentElement.style.setProperty("--mmc-type", String(safe));
}

/* How far the surface ladder steps off the ground it is on -- one multiplier
 * over every rung, documented as --mmc-lift in styles/base.js.
 *
 * On the document element for the reason the text scale is: the popovers, the
 * picker and the modals all portal to document.body, and a value set on a node
 * body would stop at the edge of that body. It has to be here rather than
 * anywhere lower for a second reason as well -- a var() inside a :root
 * declaration resolves against :root, so a lift set on a descendant would leave
 * every surface at the value :root had already computed.
 *
 * Clamped here as well as on the server, on the same reasoning as the scale: a
 * hand-edited 40 would flatten every surface into the ink and leave no control
 * on screen legible enough to say otherwise.
 */
export function applySurfaceLift(lift) {
  const value = Number(lift);
  const safe = Number.isFinite(value) ? Math.min(2, Math.max(0.4, value)) : 1;
  document.documentElement.style.setProperty("--mmc-lift", String(safe));
}

/* Whether the pack keeps a dark ground of its own, and where.
 *
 * Two facts decide it, and neither one is enough alone, which is why they are
 * held here rather than written straight onto the document by whoever learns
 * them: the preference, which arrives from the server, and whether the
 * fullscreen editor is up, which only fullscreen.js knows.
 *
 * The "where" is the whole of what this setting turned out to be. A node body
 * is part of a node, and ComfyUI draws the node -- its title, its chrome, the
 * padding around whatever a custom node puts inside it -- in the host's own
 * palette. Pinning the body dark on a light desk therefore does not produce a
 * dark editor; it produces a dark island in a white card, which reads as
 * something broken rather than something chosen. The fullscreen shell has no
 * such problem: it covers the viewport, so there is no host chrome left for it
 * to disagree with, and it is the surface where a dark ground was the point --
 * a frame judged against white is judged against the wrong thing.
 *
 * On the document element rather than on the shell's own root, even though the
 * shell is the only thing it applies to, because the popovers and the picker
 * portal to document.body: while the shell is up they belong to it, and a class
 * set on the shell would stop at the edge of the shell.
 *
 * A class rather than a set of properties, because what it turns on is a whole
 * block of tokens *and* the light-accent correction it has to turn off -- see
 * .mmc-force-dark in styles/base.js. Anything the server does not recognise
 * reads as "follow", which is the default and what the stylesheet does unaided.
 */
let pinDark = false;
let shellOpen = false;

function syncTheme() {
  document.documentElement.classList.toggle("mmc-force-dark", pinDark && shellOpen);
}

export function applyTheme(theme) {
  pinDark = theme === "dark";
  syncTheme();
}

/** fullscreen.js, on the way in and the way out. */
export function noteFullscreen(open) {
  shellOpen = !!open;
  syncTheme();
}

export function installStyles() {
  if (document.getElementById("mmc-styles")) return;
  const tag = document.createElement("style");
  tag.id = "mmc-styles";
  tag.textContent = CSS;
  document.head.appendChild(tag);
}

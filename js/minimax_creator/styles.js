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
  // Last: the shell hosts every body in the pack and lifts the caps the node
  // face put on them, so its rules have to win over the sections that set them.
  fullscreen,
].join("");

export function installStyles() {
  if (document.getElementById("mmc-styles")) return;
  const tag = document.createElement("style");
  tag.id = "mmc-styles";
  tag.textContent = CSS;
  document.head.appendChild(tag);
}

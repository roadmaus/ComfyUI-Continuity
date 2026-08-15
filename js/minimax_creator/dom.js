// Tiny DOM helpers and the icon set. No framework — the node body is small
// enough that hand-built elements stay clearer than a template layer.

export function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    // ARIA states are strings, not HTML boolean attributes: `aria-selected` has
    // to read "true"/"false", so a boolean is spelled out rather than dropped
    // (false) or emptied (true) by the rules below. CSS keys off those words.
    if (key.startsWith("aria-") && typeof value === "boolean") {
      node.setAttribute(key, String(value));
      continue;
    }
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "style") Object.assign(node.style, value);
    else if (key.startsWith("on")) node.addEventListener(key.slice(2).toLowerCase(), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of [].concat(children)) {
    if (child) node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

/**
 * Copy the frame a <video> is sitting on onto a canvas, sizing the backing
 * store to the clip's own aspect and capping it — neither a 230 px card nor a
 * 46vh modal has any use for a 4K canvas.
 *
 * Drawing instead of showing the element is the point. A <video> in the page is
 * composited by the browser rather than painted into it, and that path hands
 * back a black rectangle on a good many Linux setups; drawImage() reads the
 * decoded frame directly and cannot be composited away.
 */
export function drawFrame(canvas, video, maxHeight = 720) {
  if (!canvas || !video?.videoWidth) return;
  const scale = Math.min(1, maxHeight / video.videoHeight);
  const width = Math.max(2, Math.round(video.videoWidth * scale));
  const height = Math.max(2, Math.round(video.videoHeight * scale));
  // Assigning either dimension clears the canvas, so only do it when the size
  // actually changed — otherwise every frame starts with a wipe.
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  canvas.getContext("2d").drawImage(video, 0, 0, width, height);
}

// The only innerHTML in the package, and it is fed exclusively from the ICONS
// constants below — never from a filename or anything else off disk. There is
// deliberately no generic `html` prop on el() for the same reason: asset names
// are user-controlled and must only ever reach the DOM as text.
export function svg(paths, size = 22) {
  const holder = document.createElement("span");
  holder.innerHTML = `<svg viewBox="0 0 24 24" width="${size}" height="${size}">${paths}</svg>`;
  return holder.firstElementChild;
}

export const ICONS = {
  image: `<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/>`,
  video: `<rect x="2" y="6" width="14" height="12" rx="2.5"/><path d="M16 10.5L22 7v10l-6-3.5z"/>`,
  audio: `<path d="M4 10v4M8 6v12M12 3v18M16 7v10M20 10v4"/>`,
  effect: `<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M18.5 15.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z"/>`,
  clock: `<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.2 1.9"/>`,
  frameIn: `<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M8 12h8M12 8v8"/>`,
  frameOut: `<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M8 12h8"/>`,
  model: `<circle cx="12" cy="12" r="9"/><path d="M12 7a5 5 0 015 5 3 3 0 01-3 3h-1.5a1.5 1.5 0 000 3H12a8 8 0 110-11z"/>`,
  // The weights on disk: a stack of files. `model` above is a palette, which is
  // a fine 22px rail glyph and an unreadable blob at the 16px a pill draws it
  // at — which is the size this one has to work at and the only size it is used.
  weights: `<path d="M12 3l8 4.2-8 4.2-8-4.2z"/><path d="M4 12l8 4.2 8-4.2"/><path d="M4 16.6l8 4.2 8-4.2"/>`,
  res: `<path d="M4 8V5a1 1 0 011-1h3M16 4h3a1 1 0 011 1v3M20 16v3a1 1 0 01-1 1h-3M8 20H5a1 1 0 01-1-1v-3"/>`,
  play: `<path d="M8 5.5l11 6.5-11 6.5z"/>`,
  pause: `<path d="M8 5v14M16 5v14"/>`,
  scissors: `<circle cx="6" cy="6" r="2.4"/><circle cx="6" cy="18" r="2.4"/><path d="M8 7.4L20 18M8 16.6L20 6"/>`,
  dice: `<rect x="3" y="3" width="18" height="18" rx="4"/><circle cx="8.5" cy="8.5" r="1.2"/><circle cx="15.5" cy="15.5" r="1.2"/><circle cx="12" cy="12" r="1.2"/>`,
  // Back round to where it was: the seed the last queue ran on, put back. An
  // arrow returning to its own start, which is what the button does — beside
  // `dice`, whose whole job is the opposite.
  rewind: `<path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1"/><path d="M3 4v5h5"/>`,
  sliders: `<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>`,
  // The seam between two shots: the second picks up where the first left off.
  link: `<path d="M9 12h6"/><path d="M11 8H8a4 4 0 000 8h3M13 8h3a4 4 0 010 8h-3"/>`,
  steps: `<path d="M4 19h4v-5h4V9h4V4h4"/>`,
  bolt: `<path d="M13 2L4.5 13.5H11L9.5 22 19.5 10H13z"/>`,
  timeline: `<path d="M3 12h18"/><rect x="3" y="8" width="7" height="8" rx="2"/><rect x="13" y="8" width="8" height="8" rx="2"/>`,
  // Lucide's `brain`, verbatim. Drawn for a 2.0 stroke and rendered here at the
  // package's 1.6 like every other icon — matching its neighbours matters more
  // than matching its origin.
  brain: `<path d="M12 18V5"/><path d="M15 13a4.17 4.17 0 0 1-3-4 4.17 4.17 0 0 1-3 4"/><path d="M17.598 6.5A3 3 0 1 0 12 5a3 3 0 1 0-5.598 1.5"/><path d="M17.997 5.125a4 4 0 0 1 2.526 5.77"/><path d="M18 18a4 4 0 0 0 2-7.464"/><path d="M19.967 17.483A4 4 0 1 1 12 18a4 4 0 1 1-7.967-.517"/><path d="M6 18a4 4 0 0 1-2-7.464"/><path d="M6.003 5.125a4 4 0 0 0-2.526 5.77"/>`,
  // Writing, as against bringing: the two ways a timeline card can exist. Drawn
  // for the empty strip's choices, where "a shot you write" needed a glyph that
  // was not another rectangle.
  pen: `<path d="M4 20l4.6-1.1 9.6-9.6a2.1 2.1 0 10-3-3L5.6 15.9z"/><path d="M14.4 5.6l4 4"/>`,
  // Out of the box and into the window: the corner control on a node face.
  expand: `<path d="M14 4h6v6"/><path d="M20 4l-7 7"/><path d="M10 20H4v-6"/><path d="M4 20l7-7"/>`,
  chevron: `<path d="M6 9l6 6 6-6"/>`,
  star: `<path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.9-5.2-2.8-5.2 2.8 1-5.9-4.3-4.1 5.9-.9z"/>`,
  folder: `<path d="M3 7.5A2.5 2.5 0 015.5 5h3.8l2 2.2h7.2A2.5 2.5 0 0121 9.7v6.8a2.5 2.5 0 01-2.5 2.5h-13A2.5 2.5 0 013 16.5z"/>`,
  // A grid of frames: the gallery is the one place in the node that shows many
  // renders at once, and the rail already spends `image` on "Add image".
  gallery: `<rect x="3" y="3" width="7.5" height="7.5" rx="1.8"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="1.8"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="1.8"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.8"/>`,
  // Lucide's `settings`, verbatim — drawn for a 2.0 stroke and rendered here at
  // the package's 1.6, the same deal `brain` above gets. `sliders` is spoken
  // for: the timeline wears it for "Edit timeline".
  gear: `<path d="M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915"/><circle cx="12" cy="12" r="3"/>`,
};

export function icon(name, size = 22) {
  return svg(ICONS[name], size);
}

/**
 * Lift a transient layer above every overlay currently open.
 *
 * A popover cannot have a fixed z-index. The same aspect pill opens the same
 * popover from the node body, where it only has to clear the graph canvas, and
 * from a timeline segment editor, where it has to clear a modal — and modals are
 * stacked by DOM depth (see `mountOverlay`), so how high is high enough is not
 * known until the moment it opens.
 */
export function floatAbove(node) {
  node.style.zIndex = String(1400 + document.querySelectorAll(".mmc-overlay").length * 10 + 5);
}

/**
 * Let a box inside a node body scroll instead of zooming the graph.
 *
 * A wheel over a node body is the canvas's zoom gesture, and a DOM widget that
 * merely *has* an overflow does not take it back — so a long prompt was a box
 * you could not read: the text scrolled nowhere and ComfyUI zoomed out under
 * the pointer. This scrolls the element itself and swallows the event, but only
 * while the element has somewhere to go: at either end, and in a box short
 * enough not to overflow at all, the wheel is the canvas's again and zoom keeps
 * working exactly where nothing would have scrolled anyway.
 *
 * Not passive — the whole point is `preventDefault`.
 */
export function keepScroll(element) {
  element.addEventListener("wheel", (event) => {
    const room = element.scrollHeight - element.clientHeight;
    if (room <= 0) return;
    const next = Math.max(0, Math.min(room, element.scrollTop + event.deltaY));
    if (next === element.scrollTop) return;
    element.scrollTop = next;
    event.preventDefault();
    event.stopPropagation();
  }, { passive: false });
  return element;
}

/**
 * Make an asset chip's thumbnail the way to swap the file behind it.
 *
 * The thumbnail is the part of the chip that *is* the file, so it is where
 * "point this at something else" belongs. Removing and re-adding renumbers the
 * handle, which means rewriting every sentence in the prompt that names it —
 * for the common act of trying the same reference with a different picture,
 * that is the whole edit for none of the change.
 */
export function swappable(thumb, { title, onclick }) {
  thumb.classList.add("mmc-asset-swap");
  thumb.title = title;
  thumb.setAttribute("role", "button");
  thumb.setAttribute("tabindex", "0");
  thumb.addEventListener("click", onclick);
  thumb.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    onclick(event);
  });
  return thumb;
}

/** Close-on-outside-click / Escape, shared by every popover. */
export function dismissable(node, onClose) {
  floatAbove(node);
  const away = (event) => {
    if (!node.contains(event.target)) close();
  };
  const key = (event) => {
    if (event.key === "Escape") { event.stopPropagation(); close(); }
  };
  function close() {
    document.removeEventListener("pointerdown", away, true);
    document.removeEventListener("keydown", key, true);
    node.remove();
    onClose?.();
  }
  // Deferred so the click that opened the popover does not immediately shut it.
  setTimeout(() => {
    document.addEventListener("pointerdown", away, true);
    document.addEventListener("keydown", key, true);
  }, 0);
  return close;
}

/**
 * Portal a full-screen overlay to <body> and give it a place in the stack.
 *
 * Overlays nest arbitrarily — the timeline opens a segment editor, which opens
 * the picker, which opens the clip's segment editor — so neither a fixed
 * z-index nor a single "topmost" class can order them. Depth is DOM order
 * instead: the newest overlay is the last `.mmc-overlay` under <body>, and so is
 * both the highest and the one Escape belongs to. Every listener is registered
 * in the capture phase and stands down unless it is currently last.
 *
 * @returns {() => void} unmount
 */
export function mountOverlay(overlay, onEscape) {
  overlay.style.zIndex = String(1400 + document.querySelectorAll(".mmc-overlay").length * 10);
  const onKey = (event) => {
    if (event.key !== "Escape") return;
    const open = document.querySelectorAll(".mmc-overlay");
    if (open[open.length - 1] !== overlay) return;
    event.stopPropagation();
    onEscape();
  };
  document.addEventListener("keydown", onKey, true);
  document.body.appendChild(overlay);
  return () => {
    document.removeEventListener("keydown", onKey, true);
    overlay.remove();
  };
}

/** Anchor a popover to a pill, kept inside the viewport. */
export function placeNear(popover, anchor, { above = true } = {}) {
  const place = () => {
    // The pill this hangs off may be gone: a popover whose rows commit — the
    // face pass's, the two-pass section's — re-renders the node under itself,
    // and the button that was clicked is replaced by an identical one in the
    // same place. A detached element measures (0, 0, 0, 0), so re-placing
    // against it would throw the popover into the top-left corner. Its current
    // position is still the right one, so the answer is to leave it there.
    if (anchor.isConnected === false) return;
    const rect = anchor.getBoundingClientRect();
    const box = popover.getBoundingClientRect();
    const left = Math.max(8, Math.min(rect.left, window.innerWidth - box.width - 8));
    const top = above && rect.top - box.height - 8 > 8
      ? rect.top - box.height - 8
      : Math.min(rect.bottom + 8, window.innerHeight - box.height - 8);
    popover.style.left = `${left}px`;
    popover.style.top = `${Math.max(8, top)}px`;
  };
  place();
  // A popover is not a fixed-size thing: the refiner's lists arrive after
  // placement, and its folds open on click. Whenever the box changes size it
  // is placed again, so growth slides it up against the viewport edge — where
  // the max-height on .mmc-pop turns whatever still does not fit into its own
  // scrollbar — instead of running past the bottom of a 1080p screen.
  const observer = new ResizeObserver(() => {
    if (!popover.isConnected) { observer.disconnect(); return; }
    place();
  });
  observer.observe(popover);
}

// The pill popovers — aspect ratio, short edge, and the output folder.
//
// They live here rather than on CreatorEditor because each is a property of a
// *generation* in the Creator node and of the *timeline* in the Timeline node,
// and both need the same controls over the same fields. The PreStage uses the
// output one too, over its own default.

import { el, icon, dismissable, placeNear } from "./dom.js";
import { t } from "./i18n.js";
import { ASPECT_PRESETS, MIN_SHORT_EDGE, MAX_SHORT_EDGE, NATIVE_SHORT_EDGE, CANVAS_MULTIPLE } from "./canvas.js";
import { UPSCALE_MODES, DEFAULT_REFINE_DENOISE, MIN_REFINE_DENOISE, MAX_REFINE_DENOISE,
         twoPass, sampleEdge, emptyFace, MIN_FACE_CANVAS, MAX_FACE_CANVAS,
         MIN_FACE_DENOISE, MAX_FACE_DENOISE } from "./state.js";

/**
 * A −/value/+ pill. The same shape as the duration control, because a number
 * you nudge should look the same everywhere in the node.
 *
 * @param {object} spec
 * @param {number} spec.value
 * @param {(value:number) => void} spec.onChange
 * @param {string} [spec.iconName]   drawn between the two steppers
 * @param {(value:number) => string} [spec.format]
 */
export function stepperPill({ value, onChange, min = -Infinity, max = Infinity, step = 1,
                              iconName, format = String, title, width = "34px" }) {
  const clamp = (next) => Math.min(max, Math.max(min, Math.round(next * 1e6) / 1e6));
  const arrow = (label, delta) => el("button", {
    class: "mmc-step", text: label,
    disabled: clamp(value + delta) === value || undefined,
    onclick: () => onChange(clamp(value + delta)),
  });
  return el("div", { class: "mmc-pill mmc-pill-group", title }, [
    arrow("−", -step),
    ...(iconName ? [icon(iconName, 16)] : []),
    el("span", { text: format(value), style: { minWidth: width, textAlign: "center" } }),
    arrow("+", step),
  ]);
}

/**
 * A pill that opens a list of choices. Used for anything whose options come
 * from the backend — samplers, schedulers — where there is nothing to draw but
 * the name.
 */
export function openChoicePopover(anchor, { title, options, value, onPick }) {
  const pop = el("div", { class: "mmc-pop mmc-pop-scroll" },
    title ? [el("div", { class: "mmc-pop-title", text: title })] : []);
  for (const option of options) {
    pop.appendChild(el("button", {
      class: "mmc-opt",
      "aria-checked": option === value,
      onclick: () => { close(); onPick(option); },
    }, [
      el("span", { class: "mmc-opt-label" }, [el("span", { text: option })]),
      el("span", { class: "mmc-radio" }),
    ]));
  }
  document.body.appendChild(pop);
  placeNear(pop, anchor);
  const close = dismissable(pop);
  pop.querySelector('[aria-checked="true"]')?.scrollIntoView({ block: "center" });
}

/** A frame drawn at the ratio itself, so portrait and landscape are legible
 *  without reading the numbers. Sized to fit `long` on its long edge; the box
 *  is square, which keeps every glyph on the same baseline and left edge.
 *
 *  The pill wears the same glyph one size down, matching the 16px icon on the
 *  resolution pill beside it — the chip is what you look at while the list is
 *  closed, so telling 9:16 from 16:9 there is worth more than in the list. */
export function aspectGlyph(ratio, long = 18) {
  const width = ratio >= 1 ? long : long * ratio;
  const height = ratio >= 1 ? long / ratio : long;
  return el("span", { class: "mmc-aspect-glyph", style: { width: `${long}px`, height: `${long}px` } }, [
    el("span", { style: { width: `${width}px`, height: `${height}px` } }),
  ]);
}

/** The glyph as a pill wears it. */
export const PILL_GLYPH = 16;

/**
 * @param {HTMLElement} anchor  the pill to hang the popover off
 * @param {object} target       anything with an `aspect` field — a state or a timeline
 * @param {() => void} commit   called once, after a choice
 */
export function openAspectPopover(anchor, target, commit) {
  const pop = el("div", { class: "mmc-pop" }, [el("div", { class: "mmc-pop-title", text: t("Aspect Ratio") })]);
  for (const [label, ratio] of ASPECT_PRESETS) {
    pop.appendChild(el("button", {
      class: "mmc-opt",
      "aria-checked": target.aspect === label,
      onclick: () => { target.aspect = label; close(); commit(); },
    }, [
      el("span", { class: "mmc-opt-label" }, [aspectGlyph(ratio), el("span", { text: label })]),
      el("span", { class: "mmc-radio" }),
    ]));
  }
  document.body.appendChild(pop);
  placeNear(pop, anchor);
  const close = dismissable(pop);
}

/**
 * The short-edge control, shared by every node that has one.
 *
 * The one rule that matters here: *nothing inside this may change size while
 * the thumb is down*. A range input maps the pointer's x onto the width of its
 * own track, so a readout that grows by a digit, or a note that wraps onto a
 * second line and widens the popover, moves the track out from under the
 * pointer mid-drag and the value jumps. That is why the readout is tabular, the
 * note holds two lines whatever it says, and the popover is a fixed width
 * rather than one fitted to its text.
 *
 * The steppers are the other half of the answer: on the pre-stage's 512–2048
 * range a step is two pixels of track, which no hand can hit. Arrow keys do the
 * same thing once the slider has focus; the buttons say so out loud.
 *
 * @param {object} spec
 * @param {number} spec.value
 * @param {number} [spec.mark]        a value worth marking on the track
 * @param {string} [spec.markLabel]   what it is — "native", "default"
 * @param {(edge:number) => void} spec.apply    write the value onto the target
 * @param {() => {size:string, note:string, warn?:boolean}} spec.describe
 * @param {() => void} spec.commit    called on release, not on every pixel
 */
export function edgeSlider({ min, max, step, value, mark, markLabel, apply, describe, commit }) {
  const edge = el("span", { class: "mmc-edge" });
  const size = el("span");
  const note = el("div", { class: "mmc-native" });
  const read = el("div", { class: "mmc-slider-read" }, [
    el("span", {}, [edge, el("span", { class: "mmc-edge-unit", text: "px" })]),
    size,
  ]);
  const slider = el("input", {
    type: "range", min, max, step, value,
    "aria-label": t("Short edge in pixels"),
    // The graph canvas reads a pointerdown anywhere on the node as the start of
    // a node drag, and would carry the whole node off under the thumb.
    onpointerdown: (event) => event.stopPropagation(),
  });

  const snap = (n) => Math.min(max, Math.max(min, Math.round((n - min) / step) * step + min));

  const paint = () => {
    const current = Number(slider.value);
    edge.textContent = String(current);
    const shown = describe();
    size.textContent = shown.size;
    note.textContent = shown.note;
    note.classList.toggle("over", Boolean(shown.warn));
    down.disabled = current <= min;
    up.disabled = current >= max;
    marker?.classList.toggle("on", current === mark);
  };

  /** Set from a button — the slider itself feeds `input` instead. */
  const set = (next) => {
    slider.value = String(snap(next));
    apply(Number(slider.value));
    paint();
    commit();
  };

  const stepper = (label, delta) => el("button", {
    class: "mmc-step", text: label,
    title: t(delta < 0 ? "Down {step} px" : "Up {step} px", { step }),
    "aria-label": t(delta < 0 ? "Smaller by {step} pixels" : "Larger by {step} pixels", { step }),
    onclick: () => set(Number(slider.value) + delta * step),
  });
  const down = stepper("−", -1);
  const up = stepper("+", 1);

  const marker = mark > min && mark < max
    ? el("button", {
        class: "mmc-slider-mark",
        title: t("{label} — {mark} px", { label: t(markLabel), mark }),
        onclick: () => set(mark),
      }, [el("span", { text: t(markLabel) })])
    : null;
  // A custom property has to go through setProperty; Object.assign drops it.
  marker?.style.setProperty("--p", String((mark - min) / (max - min)));

  slider.addEventListener("input", () => { apply(Number(slider.value)); paint(); });
  slider.addEventListener("change", () => commit());

  // A hand-edited creator_data can hold an edge off the step grid; the input
  // silently snaps it, and the readout would otherwise disagree with the size
  // beside it. Written back without committing — the next change carries it.
  if (Number(slider.value) !== value) apply(Number(slider.value));

  const body = el("div", { class: "mmc-slider-body" }, [
    read,
    el("div", { class: "mmc-slider-row" }, [
      down,
      el("div", { class: "mmc-slider-track" }, [slider, marker]),
      up,
    ]),
    note,
  ]);
  // For content living under the slider in the same popover: repainting the
  // readout is the only way it can react to its own edits, because `describe`
  // is where the caller redraws it.
  body.repaint = paint;
  paint();
  return body;
}

/**
 * @param {HTMLElement} anchor
 * @param {object} target             anything with a `short_edge` field
 * @param {() => {width:number, height:number}} geometry  recomputed as the slider moves
 * @param {() => void} commit         called on release, not on every pixel
 */
export function openResolutionPopover(anchor, target, geometry, commit) {
  // The two-pass section. Past the native edge it is the choice the warning
  // asks for — two passes or one, off-distribution. At or under native there
  // is no warning to answer, but the first pass can still be lowered under
  // the slider, which is the same trade at a smaller size: faster sampling,
  // refined up. Lowering the edge there *is* choosing two passes.
  const section = el("div");

  const renderSection = () => {
    const { width, height } = geometry();
    const over = target.short_edge > NATIVE_SHORT_EDGE;
    const cap = Math.min(NATIVE_SHORT_EDGE, target.short_edge);
    const option = (mode, label, sub) => el("button", {
      class: "mmc-opt",
      "aria-checked": target.upscale === mode,
      onclick: () => {
        target.upscale = mode;
        body.repaint();          // redraws this section and the note above it
        commit();
      },
    }, [
      el("span", { class: "mmc-opt-label mmc-opt-col" }, [
        el("span", { text: label }),
        el("span", { class: "mmc-opt-sub", text: sub }),
      ]),
      el("span", { class: "mmc-radio" }),
    ]);
    const rows = [];
    if (over) {
      rows.push(
        option(UPSCALE_MODES[0], t("two passes"),
               t("{edge} px first, refined up to {width} × {height}",
                 { edge: sampleEdge(target), width, height })),
        option("direct", t("direct"),
               t("one pass at {width} × {height} — off-distribution", { width, height })));
    }
    // The first-pass edge, whenever there is room under the slider for one and
    // the mode is not pinned to a single pass.
    if (cap > MIN_SHORT_EDGE && (!over || target.upscale !== "direct")) {
      rows.push(el("div", { class: "mmc-refine-row" }, [
        el("span", { class: "mmc-refine-label", text: t("sampled at") }),
        stepperPill({
          value: sampleEdge(target),
          min: MIN_SHORT_EDGE, max: cap, step: CANVAS_MULTIPLE, width: "56px",
          title: t("The short edge the first pass samples at. At the slider's size it is "
               + "the only pass; under it, a second pass refines up to the slider."),
          format: (n) => `${n} px`,
          onChange: (next) => {
            target.sample_edge = next;
            // Under native the stepper is the opt-in, so it also picks the mode.
            if (!over) target.upscale = UPSCALE_MODES[0];
            body.repaint(); commit();
          },
        }),
      ]));
    }
    if (twoPass(target)) {
      rows.push(el("div", { class: "mmc-refine-row" }, [
        el("span", { class: "mmc-refine-label", text: t("refine") }),
        stepperPill({
          value: Number(target.refine_denoise ?? DEFAULT_REFINE_DENOISE),
          min: MIN_REFINE_DENOISE, max: MAX_REFINE_DENOISE, step: 0.05, width: "40px",
          title: t("How much of the schedule the second pass re-runs. Lower keeps more "
               + "of the first pass; higher resolves more detail and drifts further from it."),
          format: (n) => n.toFixed(2),
          onChange: (next) => { target.refine_denoise = next; body.repaint(); commit(); },
        }),
      ]));
    }
    section.className = rows.length ? "mmc-twopass" : "";
    section.replaceChildren(...rows);
  };

  const body = edgeSlider({
    min: MIN_SHORT_EDGE, max: MAX_SHORT_EDGE, step: CANVAS_MULTIPLE,
    value: target.short_edge, mark: NATIVE_SHORT_EDGE, markLabel: "native",
    apply: (edge) => { target.short_edge = edge; },
    describe: () => {
      renderSection();
      const { width, height } = geometry();
      const over = target.short_edge > NATIVE_SHORT_EDGE;
      if (twoPass(target)) {
        return {
          size: `${width} × ${height}`,
          warn: false,
          note: t("Sampled at {edge} px, then a second pass refines up to this size.",
                  { edge: sampleEdge(target) }),
        };
      }
      return {
        size: `${width} × ${height}`,
        warn: over,
        note: over
          ? t("Above the trained {edge} px short edge — off-distribution, not just slower.",
              { edge: NATIVE_SHORT_EDGE })
          : target.short_edge === NATIVE_SHORT_EDGE
            ? t("Native. What the open weights were trained at.")
            : t("{ratio}× smaller short edge than native — faster, softer.",
                { ratio: (NATIVE_SHORT_EDGE / target.short_edge).toFixed(1) }),
      };
    },
    commit,
  });
  const pop = el("div", { class: "mmc-pop mmc-slider" }, [body, section]);
  document.body.appendChild(pop);
  placeNear(pop, anchor);
  dismissable(pop);
}


/**
 * The face pass, as a pill on the sampler row.
 *
 * H3 draws a face badly in proportion to how small the head is in frame, and
 * no canvas size reaches that: an upscaler re-resolves what was drawn, and what
 * was drawn was a smudge. What this switches on is a second, small generation
 * per pass — the face cropped out frame by frame, re-drawn where it fills the
 * picture, composited back.
 *
 * It sits with the accelerators because it is the same kind of statement they
 * are: a thing done to the render rather than a thing the piece *is*. Off reads
 * as off, unlit, for the same reason theirs do — a render with it on is not a
 * plain render, and that is worth seeing at a glance.
 *
 * @param {object} spec
 * @param {object} spec.target  the piece or timeline, mutated in place
 * @param {() => void} spec.commit
 */
export function facesPill({ target, commit }) {
  const face = target.face ?? emptyFace();
  return el("button", {
    class: `mmc-pill${face.on ? " accel-on" : ""}`,
    title: face.on
      ? t("The face pass is on: every pass has its face re-drawn at {edge} px and "
        + "composited back. Needs a SAM3 checkpoint in the weights control.",
          { edge: face.canvas })
      : t("The face pass is off. Switch it on for shots where the head is small in "
        + "frame — that is where H3 draws a face worst, and it is not something a "
        + "bigger canvas fixes."),
    onclick: (event) => openFacesPopover(event.currentTarget, { target, commit }),
  }, [el("span", { text: face.on ? t("faces") : t("faces off") })]);
}

/** On or off, and — on — the two knobs. The card switches are on the cards. */
export function openFacesPopover(anchor, { target, commit }) {
  const pop = el("div", { class: "mmc-pop mmc-faces-pop" });
  const body = el("div");

  const render = () => {
    const face = target.face ?? (target.face = emptyFace());
    const rows = [
      el("div", { class: "mmc-pop-title", text: t("Face pass") }),
      el("button", {
        class: "mmc-opt",
        "aria-checked": !face.on,
        onclick: () => { face.on = false; render(); commit(); },
      }, [
        el("span", { class: "mmc-opt-label mmc-opt-col" }, [
          el("span", { text: t("off") }),
          el("span", { class: "mmc-opt-sub", text: t("one pass per shot, as it always was") }),
        ]),
        el("span", { class: "mmc-radio" }),
      ]),
      el("button", {
        class: "mmc-opt",
        "aria-checked": face.on,
        onclick: () => { face.on = true; render(); commit(); },
      }, [
        el("span", { class: "mmc-opt-label mmc-opt-col" }, [
          el("span", { text: t("on") }),
          el("span", { class: "mmc-opt-sub",
                       text: t("re-draw the face after each pass") }),
        ]),
        el("span", { class: "mmc-radio" }),
      ]),
    ];
    if (face.on) {
      rows.push(el("div", { class: "mmc-refine-row" }, [
        el("span", { class: "mmc-refine-label", text: t("crop at") }),
        stepperPill({
          value: face.canvas,
          min: MIN_FACE_CANVAS, max: MAX_FACE_CANVAS, step: CANVAS_MULTIPLE, width: "56px",
          title: t("The canvas each face crop is generated at. Bigger is more faithful "
               + "and costs the square of it — the face fills this either way, so most "
               + "of what a larger one buys is the hair around it."),
          format: (n) => `${n} px`,
          onChange: (next) => { face.canvas = next; render(); commit(); },
        }),
      ]));
      rows.push(el("div", { class: "mmc-refine-row" }, [
        el("span", { class: "mmc-refine-label", text: t("redraw") }),
        stepperPill({
          value: Number(face.denoise),
          min: MIN_FACE_DENOISE, max: MAX_FACE_DENOISE, step: 0.05, width: "40px",
          title: t("How much of the schedule the face crop re-runs — the ceiling, not "
               + "the amount: it is scaled down frame by frame by how large the face "
               + "already is. Higher synthesises more and drifts further from the head "
               + "that is there."),
          format: (n) => n.toFixed(2),
          onChange: (next) => { face.denoise = next; render(); commit(); },
        }),
      ]));
      rows.push(el("div", { class: "mmc-pop-note",
                            text: t("Costs a second, smaller generation per pass, and "
                                  + "needs a SAM3 checkpoint picked under weights.") }));
    }
    body.replaceChildren(...rows);
  };

  render();
  pop.appendChild(body);
  document.body.appendChild(pop);
  placeNear(pop, anchor);
  dismissable(pop);
}

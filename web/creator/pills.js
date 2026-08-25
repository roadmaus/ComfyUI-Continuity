// The pill popovers — aspect ratio, short edge, and the output folder.
//
// They live here rather than on CreatorEditor because each is a property of a
// *generation* in the Creator node and of the *timeline* in the Timeline node,
// and both need the same controls over the same fields. The PreStage uses the
// output one too, over its own default.

import { el, icon, dismissable, placeNear } from "./dom.js";
import { t } from "./i18n.js";
import { rulesFor } from "./canvas.js";
import { UPSCALE_MODES, DEFAULT_REFINE_DENOISE, MIN_REFINE_DENOISE, MAX_REFINE_DENOISE,
         twoPass, sampleEdge, emptyFace, isClip, pieceFamily, refineOf,
         redetailTarget, MIN_FACE_CANVAS, MAX_FACE_CANVAS,
         MIN_FACE_DENOISE, MAX_FACE_DENOISE } from "./state.js";
import { UPSCALERS } from "./manifest.js";

/**
 * Closely related controls as one pill, divided by hairlines.
 *
 * Two pills side by side read as two independent features; one pill with a
 * divider through it reads as two halves of the same setting. So the sampler
 * and its scheduler share a pill, and so do the two ends of a shot, the canvas
 * and its short edge, and Spectrum and its blend — where the blend joining the
 * pill it belongs to is also the answer to a control that used to *appear*
 * beside it when you switched Spectrum on.
 *
 * Members are drawn rather than passed, because every one of them has to be
 * able to stand alone: the shifts are hidden one at a time, the blend only
 * exists while Spectrum is on, and a set of one is a pill, not a pill with a
 * divider and nothing on the other side of it.
 *
 * @param {Array<((seg:boolean) => HTMLElement)|null|false>} members
 * @returns {HTMLElement|null} null when nothing is on offer
 */
export function pillSet(members, { className = "" } = {}) {
  const drawn = members.filter(Boolean);
  if (!drawn.length) return null;
  if (drawn.length === 1) return drawn[0](false);
  return el("div", { class: `mmc-pill mmc-pill-set${className ? ` ${className}` : ""}` },
            drawn.map((draw) => draw(true)));
}

/** The class a pill wears in either form. `extra` is appended to both — a
 *  modifier like `accel-on` is styled for the pill and for the segment. */
export const pillClass = (seg, extra = "") => `${seg ? "mmc-pill-seg" : "mmc-pill"}${extra}`;

/** A control that is switched on or off rather than set to a value. Lit either
 *  way when it is on — filled as a segment, blue-outlined as a pill. */
export const accelClass = (seg, on) => pillClass(seg, on ? " accel-on" : "");

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
                              iconName, format = String, title, width = "34px",
                              className = "", seg = false }) {
  const clamp = (next) => Math.min(max, Math.max(min, Math.round(next * 1e6) / 1e6));
  const arrow = (label, delta) => el("button", {
    class: "mmc-step", text: label,
    disabled: clamp(value + delta) === value || undefined,
    onclick: () => onChange(clamp(value + delta)),
  });
  const base = seg ? "mmc-pill-seg mmc-pill-seg-group" : "mmc-pill mmc-pill-group";
  return el("div", { class: `${base}${className ? ` ${className}` : ""}`, title }, [
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
 *
 * `label` renames an option for the list without touching it, for the case
 * where the option *is* a wire value: a family's manifest may say that
 * `distilled` reads "built-in", and what is picked and stored is still
 * `distilled`. Identity by default, so a caller with nothing to rename passes
 * nothing.
 */
export function openChoicePopover(anchor, { title, options, value, onPick, extra,
                                            label = String }) {
  const pop = el("div", { class: "mmc-pop mmc-pop-scroll" },
    title ? [el("div", { class: "mmc-pop-title", text: title })] : []);
  for (const option of options) {
    pop.appendChild(el("button", {
      class: "mmc-opt",
      "aria-checked": option === value,
      onclick: () => { close(); onPick(option); },
    }, [
      el("span", { class: "mmc-opt-label" }, [el("span", { text: label(option) })]),
      el("span", { class: "mmc-radio" }),
    ]));
  }
  // A section under a rule for a switch that modifies the choice above rather
  // than being one of them — the seam's boundary pin is the case it exists
  // for. `extra` is built by the caller and closes the popover itself, which
  // is what every option row does.
  if (extra) pop.appendChild(extra(() => close()));
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
 * @param {object} [sources]    offered when the piece holds pictures the ratio
 *   can be taken from: `{ auto: {ratio, sub}, donors: [{value, label, tag,
 *   ratio, sub}] }`. Picking a donor writes its `value` to
 *   `target.aspect_source`; a preset writes `"pill"`; Auto removes the field.
 *   `ratio` may be null while a probe is still out — the glyph then draws the
 *   frame square and says nothing it does not know.
 */
export function openAspectPopover(anchor, target, commit, sources = null) {
  // The ratios this family offers. The same six today for both, and read off
  // the piece anyway: an aspect envelope is a property of what the weights saw,
  // and the list is the manifest's to declare.
  const presets = rulesFor(pieceFamily(target)).aspects;
  const donors = sources?.donors?.length ? sources.donors : null;
  const current = target.aspect_source ?? "auto";
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const pick = (value) => {
    if (value === undefined) delete target.aspect_source;
    else target.aspect_source = value;
    close();
    commit();
  };

  const pop = el("div", { class: "mmc-pop" },
    [el("div", { class: "mmc-pop-title", text: t("Aspect Ratio") })]);

  if (donors) {
    // The ratio's source before its value: every attached picture is offered,
    // drawn at its own shape, so choosing a source is done by looking at
    // frames rather than at numbers.
    pop.appendChild(el("button", {
      class: "mmc-opt",
      "aria-checked": current === "auto",
      title: t("The standing rule: a start frame decides, then supplied footage, then the preset."),
      onclick: () => pick(undefined),
    }, [
      el("span", { class: "mmc-opt-label" }, [
        aspectGlyph(sources.auto?.ratio ?? 16 / 9),
        el("span", { text: t("Auto") }),
        ...(sources.auto?.sub
          ? [el("span", { class: "mmc-opt-sub", text: sources.auto.sub })] : []),
      ]),
      el("span", { class: "mmc-radio" }),
    ]));
    for (const donor of donors) {
      pop.appendChild(el("button", {
        class: "mmc-opt",
        "aria-checked": same(current, donor.value),
        onclick: () => pick(donor.value),
      }, [
        el("span", { class: "mmc-opt-label" }, [
          aspectGlyph(donor.ratio ?? 1),
          donor.tag == null
            ? el("span", { text: donor.label })
            : el("span", { class: `mmc-ref mmc-tag-${donor.tag}`, text: donor.label }),
          ...(donor.sub ? [el("span", { class: "mmc-opt-sub", text: donor.sub })] : []),
        ]),
        el("span", { class: "mmc-radio" }),
      ]));
    }
    pop.appendChild(el("div", { class: "mmc-pop-title", text: t("Preset") }));
  }

  for (const [label, ratio] of presets) {
    pop.appendChild(el("button", {
      class: "mmc-opt",
      "aria-checked": target.aspect === label
        && (!donors || current === "pill" || current === "auto"),
      onclick: () => {
        target.aspect = label;
        // With pictures on offer, choosing a preset is choosing it *over*
        // them — written down as "pill" so a clip or keyframe cannot quietly
        // outrank a choice the user just made. With nothing on offer the
        // preset already rules and the blob stays exactly as it always was.
        pick(donors ? "pill" : undefined);
      },
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
 * What the resolution pill says, for the two hosts that draw one.
 *
 * Written once because the two hosts were drawing the same three-way answer
 * separately and had to be told about the backend twice. The sub-line's shape
 * is the honest one in all three cases: what was sampled, an arrow, and what
 * comes out — with the arrow left off only where those are the same number.
 *
 * @param {object} target  the piece or timeline
 * @param {{width:number, height:number, ratio:number}} geometry  the resolved canvas
 * @returns {{title: string, sub: string}}
 */
export function resolutionPillText(target, geometry) {
  const finished = redetailTarget(target, geometry.ratio);
  if (finished) {
    return {
      title: t("Sampled at a {edge} px short edge, then re-rendered ×{factor} to "
             + "{width} × {height}. Fine detail is invented rather than recovered.",
               { edge: sampleEdge(target), factor: finished.scale,
                 width: finished.width, height: finished.height }),
      sub: `${sampleEdge(target)} → ${finished.width} × ${finished.height}`,
    };
  }
  if (twoPass(target)) {
    return {
      title: t("Sampled at a {edge} px short edge, refined up to {width} × {height} "
             + "by a second pass.",
               { edge: sampleEdge(target), width: geometry.width,
                 height: geometry.height }),
      sub: `${sampleEdge(target)} → ${geometry.width} × ${geometry.height}`,
    };
  }
  return {
    title: t("Short edge. Lower is faster; 768 is what the open weights were trained at."),
    sub: `${geometry.width} × ${geometry.height}`,
  };
}

/**
 * @param {HTMLElement} anchor
 * @param {object} target             anything with a `short_edge` field
 * @param {() => {width:number, height:number}} geometry  recomputed as the slider moves
 * @param {() => void} commit         called on release, not on every pixel
 */
export function openResolutionPopover(anchor, target, geometry, commit) {
  // Every number on this slider is the piece's family's — where native sits,
  // where the ceiling is, what the axes snap to. They were H3's constants,
  // which was right while there was one family and is a slider marked "native"
  // at the wrong place the moment there are two.
  const rules = rulesFor(pieceFamily(target));
  const NATIVE_SHORT_EDGE = rules.nativeShortEdge;
  const MIN_SHORT_EDGE = rules.minShortEdge;
  const MAX_SHORT_EDGE = rules.maxShortEdge;
  const CANVAS_MULTIPLE = rules.multiple;
  // What the second pass *is*, which is not the same thing in both families:
  // H3 re-encodes the request at the target canvas and samples again, LTX runs
  // a trained latent upscaler at a factor the model fixed. `factor` is what
  // separates them — where there is one, the second pass's size is the first
  // pass's times it and the slider only decides *whether* there is one.
  const refine = refineOf(pieceFamily(target));
  const factor = refine && typeof refine === "object" ? refine.factor : null;
  const secondPass = (edge) => (factor ? edge * factor : target.short_edge);

  // The upscale backends that are not the family's own — one entry today,
  // ReDetail. A backend re-renders the *finished* pass rather than refining a
  // latent, which is why it can carry an H3 render through LTX 2.5's weights,
  // and why the size it delivers is the model's factor rather than the slider's
  // number. `UPSCALERS` is empty on an install serving no backend, and this
  // whole row goes with it.
  const backend = UPSCALERS[0] ?? null;
  // Explicitly `backend` and not the piece's own choice: the row offering the
  // finish has to print the size before it is chosen, and asking for the size
  // of a backend nobody has picked is how this returned null and took the
  // whole popover down with it.
  const finish = (which = null) => redetailTarget(target, geometry().ratio,
                                                  which ?? undefined);

  // The finish section. Past the native edge it is the choice the warning asks
  // for — two passes, one off-distribution pass, or a backend. At or under
  // native there is no warning to answer, but there is still a choice worth
  // offering: the first pass can be lowered under the slider (faster sampling,
  // refined up — lowering the edge there *is* choosing two passes), and a
  // backend can take the render past what this family samples at all.
  const section = el("div");

  const renderSection = () => {
    const { width, height } = geometry();
    const over = target.short_edge > NATIVE_SHORT_EDGE;
    const cap = Math.min(NATIVE_SHORT_EDGE, target.short_edge);
    const option = (mode, label, sub,
                    { checked = null, pick = null, disabled = false } = {}) =>
      el("button", {
        class: "mmc-opt",
        disabled,
        "aria-checked": checked ?? target.upscale === mode,
        onclick: () => {
          (pick ?? (() => { target.upscale = mode; }))();
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
               factor
                 ? t("{edge} px first, then the ×{factor} latent upscaler to {target} px",
                     { edge: sampleEdge(target), factor,
                       target: secondPass(sampleEdge(target)) })
                 : t("{edge} px first, refined up to {width} × {height}",
                     { edge: sampleEdge(target), width, height })),
        option("direct", t("direct"),
               t("one pass at {width} × {height} — off-distribution", { width, height })));
    } else if (backend) {
      // Under native the two family modes deliver the same picture — the slider
      // is reachable in one pass — so offering both would be two names for one
      // thing. What is worth contrasting here is the render against the
      // backend, and the row keeps whichever of the two the blob already holds.
      rows.push(option(UPSCALE_MODES[0],
                       twoPass(target) ? t("two passes") : t("one pass"),
                       twoPass(target)
                         ? t("{edge} px first, refined up to {width} × {height}",
                             { edge: sampleEdge(target), width, height })
                         : t("{width} × {height}, as sampled", { width, height }),
                       { checked: target.upscale !== "redetail",
                         pick: () => {
                           if (target.upscale === "redetail") {
                             target.upscale = UPSCALE_MODES[0];
                           }
                         } }));
    }
    if (backend) {
      const target_size = finish(backend);
      // Supplied footage is spliced at the size it already is and is never
      // decoded, so a strip carrying any cannot have its passes doubled — the
      // muxer holds a reel's parts to one geometry. `compile.timeline_payloads`
      // refuses it; the row says so first, because finding out at queue time
      // costs a click and an error message to learn something the strip already
      // knew.
      const spliced = (target.segments ?? []).some(isClip);
      rows.push(option("redetail", t(backend.label),
                       spliced
                         ? t("not while the strip carries a clip — spliced footage is "
                           + "not re-rendered")
                         : t("×{factor} to {width} × {height} — re-rendered, not sharpened",
                             { factor: target_size.scale, width: target_size.width,
                               height: target_size.height }),
                       { disabled: spliced,
                         pick: () => {
                           target.upscale = "redetail";
                           // The slider becomes the *sampled* edge under a
                           // backend, and the backend never samples past
                           // native — so a slider left above it would be a
                           // control doing nothing. Snapping it down is what
                           // keeps every other readout on the strip meaning
                           // the canvas that was actually rendered.
                           if (target.short_edge > NATIVE_SHORT_EDGE) {
                             target.short_edge = NATIVE_SHORT_EDGE;
                           }
                         } }));
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
          title: factor
            ? t("How much of the schedule the second pass re-runs over the upscaled "
              + "latent. Lower keeps more of the first pass; higher resolves more "
              + "detail and drifts further from it.")
            : t("How much of the schedule the second pass re-runs. Lower keeps more "
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
      // A backend delivers twice what was sampled, so the slider is no longer
      // the size that comes out — the readout shows what does. The note carries
      // one thing and only one: this is a repaint, and a face or a logo does
      // not survive one. What was sampled and by how much it grew are the row's
      // job below, and saying either twice would cost the warning its line.
      const finished = finish();
      if (finished) {
        return {
          size: `${finished.width} × ${finished.height}`,
          warn: false,
          note: t("Fine detail is invented rather than recovered — faces and logos "
                + "come back changed."),
        };
      }
      if (twoPass(target)) {
        return {
          size: `${width} × ${height}`,
          warn: false,
          // With a fixed factor the slider does not choose the delivered size —
          // the upscaler does — so the note says what actually comes out rather
          // than pointing at a number the second pass will overshoot or miss.
          note: factor
            ? t("Sampled at {edge} px, then the ×{factor} latent upscaler takes it to {target} px.",
                { edge: sampleEdge(target), factor,
                  target: secondPass(sampleEdge(target)) })
            : t("Sampled at {edge} px, then a second pass refines up to this size.",
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
          min: MIN_FACE_CANVAS, max: MAX_FACE_CANVAS,
          step: rulesFor(pieceFamily(target)).multiple, width: "56px",
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

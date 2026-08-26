// The subject view: one picture, and the clicks that say which subject the
// scissors mean.
//
// The whole-subject matte (BiRefNet) needs no clicks and is right most of the
// time; this view exists for the picture it is wrong about — two people and
// only one of them cited, a prop in a cluttered room. Clicking is always live
// here, because there is nothing else a click on the picture could mean: no
// panels to drag, no layout to arrange. That is the difference from the sheet
// stage, where a click had to be armed first and the arming was the confusing
// part.

import { el, mountOverlay } from "./dom.js";
import { viewUrl, cutPanel } from "./api.js";
import { t } from "./i18n.js";

/** One backdrop level as a CSS colour. The plate's field is a grey level
 *  because both families want a neutral one — see `creator/cutout.py` — and the
 *  preview has to sit on the same grey the panels were composited onto, or the
 *  cut-out edges read as a halo that is not in the file. */
export function greyField(level) {
  const step = Math.round(Math.max(0, Math.min(1, Number(level) || 0)) * 255);
  return "rgb(" + step + "," + step + "," + step + ")";
}

/**
 * Choose the subject of one picture. Resolves `{ points }` on accept — the
 * caller cuts the picture with them — or null on cancel, which leaves whatever
 * the caller had exactly as it was.
 *
 * @param {object} options
 * @param {object} options.plate    `state.plateSpec`'s answer: backdrop, matte
 *                                  model, and the SAM 3 checkpoint a click asks
 * @param {string} options.path     the source picture, as the plate routes read it
 * @param {string} options.name     what the title calls it
 * @param {Array}  options.points   the clicks so far, `[{x, y, include}]`
 */
export function openSubjectView({ plate, path, name, points: given = [] }) {
  return new Promise((resolve) => {
    const points = given.map((point) => ({ ...point }));
    let keeping = true;          // what the next click means: keep, or drop
    let held = null;             // the current preview as an object URL
    let pending = null;          // the key being fetched, if any
    let error = "";
    let fetchTimer = null;

    const round4 = (v) => Math.round(v * 1e4) / 1e4;
    const key = () => JSON.stringify(points);

    // ---- the preview -------------------------------------------------------
    //
    // Always the cutout: accepting this view *is* cutting, so the picture shown
    // is the picture accepting would make. Served from the server's memory the
    // way the sheet stage's panels are; nothing is written here.
    const img = el("img", { class: "mmc-subject-img", alt: name, draggable: "false",
                            src: viewUrl(path, { preview: true }) });
    const stage = el("div", { class: "mmc-subject-stage" });
    stage.style.background = greyField(plate.backdrop);
    img.addEventListener("load", () => {
      // The stage is the picture's own shape, so a click's place on the stage
      // is its place on the picture. Height-capped the way the sheet stage is:
      // through max-width, because aspect-ratio would let max-height crop.
      const w = img.naturalWidth || 4, h = img.naturalHeight || 3;
      stage.style.aspectRatio = w + " / " + h;
      stage.style.maxWidth = "min(100%, calc(60vh * " + (w / h) + "))";
    });
    const fetchCut = () => {
      const want = key();
      if (pending === want) return;
      pending = want;
      render();
      cutPanel({ model: plate.model, segment: plate.segment,
                 panels: [{ path, cut: true,
                            ...(points.length ? { points } : {}) }] })
        .then((url) => {
          if (pending !== want) { URL.revokeObjectURL(url); return; }
          if (held) URL.revokeObjectURL(held);
          held = url;
          pending = null;
          error = "";
          img.src = url;
          render();
        })
        .catch((problem) => {
          if (pending !== want) return;
          pending = null;
          error = problem.message;
          render();
        });
    };
    // Fetch after the change settles: a run of clicks is many mattes, and only
    // where it ends is a picture anybody is waiting on.
    const schedule = () => {
      clearTimeout(fetchTimer);
      fetchTimer = setTimeout(fetchCut, 250);
      render();
    };

    // ---- the clicks --------------------------------------------------------
    //
    // The stage's aspect is the picture's own, so a click's place on the stage
    // is its place on the picture — no content box to subtract, unlike a panel
    // contain-fitted into a sheet cell.
    stage.addEventListener("pointerdown", (event) => {
      if (event.target.closest(".mmc-st-dot")) return;
      const at = stage.getBoundingClientRect();
      const x = (event.clientX - at.left) / Math.max(1, at.width);
      const y = (event.clientY - at.top) / Math.max(1, at.height);
      if (x < 0 || x > 1 || y < 0 || y > 1) return;
      points.push({ x: round4(x), y: round4(y),
                    include: keeping !== (event.shiftKey || event.altKey) });
      schedule();
    });

    const dots = () => points.map((point, at) => {
      const dot = el("button", {
        class: "mmc-st-dot" + (point.include ? "" : " out"),
        title: point.include
          ? t("A click on the subject — press to take it back")
          : t("A click on what to leave out — press to take it back"),
        onpointerdown: (event) => event.stopPropagation(),
        onclick: (event) => {
          event.stopPropagation();
          points.splice(at, 1);
          schedule();
        },
      });
      dot.style.left = (point.x * 100) + "%";
      dot.style.top = (point.y * 100) + "%";
      return dot;
    });

    // ---- the controls ------------------------------------------------------
    //
    // What the next click means, said out loud instead of hidden in a modifier
    // key. Shift stays as the shortcut for a single drop without switching.
    const keepButton = el("button", {
      class: "mmc-ghost mmc-tool",
      title: t("Clicks mark the subject to keep"),
      text: t("Keep"),
      onclick: () => { keeping = true; render(); },
    });
    const dropButton = el("button", {
      class: "mmc-ghost mmc-tool",
      title: t("Clicks mark what to leave out — shift-click does one without switching"),
      text: t("Drop"),
      onclick: () => { keeping = false; render(); },
    });
    const resetButton = el("button", {
      class: "mmc-ghost mmc-tool",
      title: t("Forget every click and go back to the whole-subject cut"),
      text: t("Start over"),
      onclick: () => { points.length = 0; keeping = true; schedule(); },
    });
    const say = el("div", { class: "mmc-plate-say" });
    const okButton = el("button", {
      class: "mmc-add", text: t("Use this cutout"),
      onclick: () => shut({ points: points.map((point) => ({ ...point })) }),
    });

    const scan = el("div", { class: "mmc-plate-scan" });
    const render = () => {
      stage.replaceChildren(img, ...dots(), ...(pending ? [scan] : []));
      keepButton.classList.toggle("on", keeping);
      keepButton.setAttribute("aria-pressed", String(keeping));
      dropButton.classList.toggle("on", !keeping);
      dropButton.setAttribute("aria-pressed", String(!keeping));
      resetButton.disabled = !points.length;
      say.textContent = error || (points.length
        ? t("Click anything else that should go — or press a dot to take it back.")
        : t("The whole subject is cut out. Click the subject you mean if the cut grabbed the wrong thing."));
      say.classList.toggle("bad", Boolean(error));
    };

    const body = el("div", { class: "mmc-plate-edit mmc-subject" }, [
      el("div", { class: "mmc-plate-title" }, [
        el("span", { text: t("Choose the subject") }),
        el("span", { class: "mmc-subject-name", text: name }),
      ]),
      el("div", { class: "mmc-plate-stage-wrap" }, [stage]),
      say,
      el("div", { class: "mmc-plate-tools" },
         [el("div", { class: "mmc-subject-pol" }, [keepButton, dropButton]), resetButton]),
      el("div", { class: "mmc-plate-foot" }, [
        el("button", { class: "mmc-ghost", text: t("Cancel"), onclick: () => shut(null) }),
        okButton,
      ]),
    ]);
    const overlay = el("div", {
      class: "mmc-overlay",
      onpointerdown: (event) => { if (event.target === overlay) shut(null); },
      // Same seal as the picker's overlays: nothing dropped here may fall
      // through to ComfyUI's file-import drop handler.
      ondragover: (event) => event.preventDefault(),
      ondrop: (event) => { event.preventDefault(); event.stopPropagation(); },
    }, [body]);
    const remove = mountOverlay(overlay, () => shut(null));
    const shut = (answer) => {
      clearTimeout(fetchTimer);
      pending = null;
      if (held) URL.revokeObjectURL(held);
      held = null;
      remove();
      resolve(answer);
    };
    schedule();
  });
}

// The rail's Clear tool: empty what was written, keep the machine.
//
// A node accumulates two different kinds of thing. One half is the piece —
// the prompt, the references, the shots — and it is finished the moment the
// render is. The other half is where the checkpoints are on this disk, which
// LoRAs are patched onto them, the turbo switch, the canvas the project is
// shot at: set once, and retyping it is not part of starting the next scene.
// Everything else in the node keeps the two apart already; this is the one
// control that acts on the difference. See `S.CLEARED_KEYS` for the line.
//
// Irreversible, and one press away from the three add tools it sits beside, so
// it asks: the first press arms, the second clears, and anything else at all —
// five seconds, Escape, a click elsewhere on the page — puts it back.

import { el, icon } from "./dom.js";
import { t } from "./i18n.js";

/** How long an armed Clear stays armed. The picker's Delete waits the same. */
const ARM_MS = 5000;

/**
 * @param {object} spec
 * @param {boolean} spec.written  whether there is anything to clear. A piece
 *   still as it was dropped disables the tool rather than offering to empty
 *   what is already empty.
 * @param {() => void} spec.run   empty the piece and commit.
 */
export function clearButton({ written, run }) {
  let armed = null;   // the disarm callback while armed, null while idle

  const label = el("span", { text: t("Clear") });
  const button = el("button", {
    class: "mmc-tool mmc-tool-danger",
    disabled: written ? undefined : true,
    title: written
      ? t("Empty the prompts, the references and the shots — everything you wrote for "
        + "this scene. The weights, the LoRAs, the canvas and the sampler stay as they are.")
      : t("Nothing written yet."),
    onclick: () => {
      if (armed) { armed(); run(); return; }
      arm();
    },
  }, [el("span", { class: "mmc-tool-icon" }, [icon("eraser")]), label]);

  function arm() {
    label.textContent = t("Really clear?");
    button.classList.add("armed");
    // Also what takes the two listeners below off a button the rail has already
    // rebuilt away underneath: they outlive the element, but never the timer.
    const timer = setTimeout(() => disarm(), ARM_MS);
    // Capture, so a press that lands on another control disarms this one before
    // that control acts rather than after it. The button's own press is the one
    // exception — it is the second press, and it is what arming is waiting for.
    const elsewhere = (event) => { if (!button.contains(event.target)) disarm(); };
    const escape = (event) => { if (event.key === "Escape") disarm(); };
    document.addEventListener("pointerdown", elsewhere, true);
    document.addEventListener("keydown", escape, true);
    armed = () => {
      clearTimeout(timer);
      document.removeEventListener("pointerdown", elsewhere, true);
      document.removeEventListener("keydown", escape, true);
      armed = null;
    };
  }

  function disarm() {
    armed?.();
    label.textContent = t("Clear");
    button.classList.remove("armed");
  }

  return button;
}

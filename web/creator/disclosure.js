// Timeline-only section folding. This is presentation state, never creator_data.
import { el } from "./dom.js";

let nextSection = 0;

/** Keep the real editor/list mounted while hiding it. Actions live beside the
 * toggle, not inside it: adding a reference must not also fold its shelf. */
export function createDisclosure({ title, hint = "", content, actions = [], inlineActions = [], onBeforeCollapse }) {
  const id = `mmc-tl-section-${++nextSection}`;
  const titleId = `${id}-title`;
  const body = el("div", { id, class: "mmc-tl-section-body" }, content ? [content] : []);
  const name = el("span", { id: titleId, class: "mmc-tl-section-title", text: title });
  const detail = el("span", { class: "mmc-tl-section-hint", text: hint });
  detail.hidden = !hint;
  const arrow = el("span", { class: "mmc-tl-section-arrow", "aria-hidden": "true" });
  let opened = true;
  const toggle = el("button", {
    type: "button", class: "mmc-tl-section-toggle", "aria-controls": id,
    "aria-expanded": "true", "aria-labelledby": titleId,
    onclick: () => setOpen(!opened),
  }, [arrow, el("span", { class: "mmc-tl-section-copy" }, [name, detail])]);
  // Opt-in title-adjacent actions stay real sibling buttons. Do not place them
  // inside the disclosure button or stretch their click target across the row.
  const inlineNodes = inlineActions.filter(Boolean);
  const inlineHost = el("div", { class: "mmc-tl-section-inline-actions" }, inlineNodes);
  const actionHost = el("div", { class: "mmc-tl-section-actions" }, actions);
  const head = el("div", { class: "mmc-tl-section-head" }, [toggle, ...(inlineNodes.length ? [inlineHost] : []), actionHost]);
  if (inlineNodes.length) {
    head.classList.add("mmc-tl-section-head-inline");
    head.onclick = (event) => {
      // The remaining row still folds the section. Native buttons handle their
      // own pointer/keyboard activation; bubbling must never activate both.
      if (event.defaultPrevented || event.target.closest?.(
        "button, a, input, select, textarea, [role=button], [contenteditable]",
      )) return;
      toggle.focus();
      setOpen(!opened);
    };
  }
  const root = el("section", { class: "mmc-tl-section" }, [head, body]);

  function setOpen(next) {
    const value = Boolean(next);
    if (opened && !value) {
      onBeforeCollapse?.();
      // Keyboard/programmatic folding must not strand focus inside hidden UI.
      if (body.contains(document.activeElement)) toggle.focus();
    }
    opened = value;
    body.hidden = !opened;
    toggle.setAttribute("aria-expanded", String(opened));
    arrow.textContent = opened ? "⌄" : "›";
  }
  setOpen(true);
  return {
    root, head, body, toggle, titleId, setOpen, isOpen: () => opened,
    setText(nextTitle, nextHint = "") {
      name.textContent = nextTitle;
      detail.textContent = nextHint;
      detail.hidden = !nextHint;
    },
    setActions(...nodes) { actionHost.replaceChildren(...nodes.filter(Boolean)); },
  };
}

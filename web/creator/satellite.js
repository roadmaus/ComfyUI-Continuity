// The satellite: a second card beside the node that exists only while there is
// a picture.
//
// It looks like a sibling node and is nothing of the sort. A real second node
// would be a thing the user has to add, wire, arrange and not delete; this is a
// DOM element on document.body that re-derives its screen position from the
// node's graph position every frame, so it pans, zooms and drags as if it were
// on the canvas without ever being in the graph. Nothing about it serializes.
//
// It hosts the Stage unchanged — the stage already knows how to be absent until
// a frame arrives, and its onVisibility hook is exactly the "appear beside the
// node now" signal. While the stage is hidden the satellite is display:none and
// the follow loop is off, so an idle canvas pays nothing for this.

import { app } from "../../../scripts/app.js";
import { el } from "./dom.js";

/** Gap between the node's right edge and the card, in graph units. */
const GAP = 14;

export class Satellite {
  /**
   * @param {object} spec
   * @param {import("../../../scripts/app.js").LGraphNode} spec.node  followed by
   *   position and height; the card mirrors the node's full height, title
   *   included, so the two read as a pair.
   * @param {import("./stage.js").Stage} spec.stage  already built by the node
   *   body, which keeps owning its gallery callback and its destroy.
   * @param {"right"|"left"} [spec.side]  which edge of the node the card hangs
   *   off. The PreStage puts its result on the left so the desk reads
   *   *still ← pre-stage · creator → video* and the two cards never collide.
   */
  constructor({ node, stage, side = "right" }) {
    this.node = node;
    this.stage = stage;
    this.side = side;
    this.raf = 0;
    // The column hosting the picture while the fullscreen editor is up, or null
    // on the canvas. See `dock`.
    this.docked = null;
    this.root = el("div", { class: `mmc-satellite${side === "left" ? " mmc-satellite-left" : ""}` }, [stage.root]);
    document.body.appendChild(this.root);

    // The stage tells its owner when it has something to show; out here that
    // owner is the satellite, not the node body.
    stage.onVisibility = (showing) => this.setShowing(showing);
    this.setShowing(stage.showing());
  }

  /**
   * Hand the picture to a host that is not the canvas — the fullscreen editor,
   * which has a column for it and no node to hang it off.
   *
   * The follow loop is the whole of what a satellite is, and there is nothing
   * for it to follow once the canvas is behind a shell: the node's graph
   * position says nothing about where a fixed column is. So docking stops the
   * loop and moves the stage element; the host shows and hides itself off the
   * same signal the card used, which is why `setShowing` keeps being the one
   * place that answers "is there a picture".
   *
   * @param {HTMLElement} host  where the stage element goes while docked
   */
  dock(host) {
    this.docked = host;
    cancelAnimationFrame(this.raf);
    this.root.classList.remove("showing");
    host.appendChild(this.stage.root);
    this.setShowing(this.stage.showing());
  }

  /** Take the picture back onto the canvas. */
  undock() {
    if (!this.docked) return;
    this.docked = null;
    this.root.appendChild(this.stage.root);
    this.setShowing(this.stage.showing());
  }

  setShowing(showing) {
    // Docked, the class belongs to the host column rather than to the card, and
    // there is nothing to follow — an early return here rather than a branch at
    // every call site, since the stage goes on reporting exactly as it did.
    if (this.docked) {
      this.docked.classList.toggle("showing", showing);
      return;
    }
    // Collapsed and subgraph checks live in follow(): both can change without
    // anything telling us, so they are re-read every frame rather than here.
    this.root.classList.toggle("showing", showing);
    cancelAnimationFrame(this.raf);
    if (showing) this.follow();
  }

  /** One frame of shadowing the node. Reading the transform beats hooking every
   *  way a canvas can move — drag, pan, zoom, arrange — none of which report. */
  follow() {
    const canvas = app.canvas;
    const node = this.node;
    // Inside a subgraph view, or with the node collapsed, there is no card to
    // sit beside. Keep looping: both states end without an event we can hear.
    const away = canvas.graph !== node.graph || node.flags?.collapsed;
    this.root.style.visibility = away ? "hidden" : "";
    if (!away) {
      const rect = canvas.canvas.getBoundingClientRect();
      const scale = canvas.ds.scale;
      const [ox, oy] = canvas.ds.offset;
      const title = globalThis.LiteGraph?.NODE_TITLE_HEIGHT ?? 30;
      // Left-side cards anchor on their right edge: the card's width is
      // content-derived (the picture decides it), so it cannot be subtracted in
      // graph units here — translateX(-100%) lets the browser do it after
      // layout, and the transform-origin keeps the scale growing away from the
      // node rather than through it.
      const left = this.side === "left";
      const x = left
        ? (node.pos[0] - GAP + ox) * scale + rect.left
        : (node.pos[0] + node.size[0] + GAP + ox) * scale + rect.left;
      const y = (node.pos[1] - title + oy) * scale + rect.top;
      // Scaled as a whole rather than sized in screen pixels: every length
      // inside the card is then a graph unit, exactly like the node beside it.
      this.root.style.transformOrigin = left ? "top right" : "top left";
      this.root.style.transform = left
        ? `translate(${x}px, ${y}px) translateX(-100%) scale(${scale})`
        : `translate(${x}px, ${y}px) scale(${scale})`;
      this.root.style.height = `${node.size[1] + title}px`;
    }
    this.raf = requestAnimationFrame(() => this.follow());
  }

  destroy() {
    cancelAnimationFrame(this.raf);
    // Docked, the stage is somebody else's child and removing the card would
    // leave it behind — a picture of a node that no longer exists.
    this.stage.root.remove();
    this.docked = null;
    this.root.remove();
  }
}

"""The smallest DOM the frontend touches, shared by the tests that mount it.

Hand-written rather than jsdom so the suite keeps its "no dependencies" rule;
every method here is one the pack actually calls, and an unimplemented one fails
loudly rather than silently.

Here rather than inside one test because two of them mount the frontend now —
`test_js_bodies` boots all four node bodies, `test_cast_editor` drives the
library's cast sheet — and a second copy of a shim is a second thing to keep in
step with the pack.
"""

DOM = """
class Node {
  constructor(tag) {
    // Custom properties go through setProperty, not through the plain assignment
    // every other style write in the pack uses — the fullscreen plate's size is
    // one, so the bag needs the two methods as well as the keys.
    this.style = {
      setProperty(name, value) { this[name] = String(value); },
      removeProperty(name) { delete this[name]; },
      getPropertyValue(name) { return this[name] ?? ""; },
    };
    this.tagName = tag; this.children = []; this.attrs = {};
    this.className = ""; this.textContent = ""; this.listeners = {};
    // Backed by className, not stubbed. Half the pack says what state a thing is
    // in by putting a class on it and the other half reads that class back —
    // the fullscreen shell's view and its summoned cast shelf both do — and a
    // no-op classList made every one of those look like it had never been set.
    const names = () => String(this.className).split(" ").filter(Boolean);
    this.classList = {
      contains: (name) => names().includes(name),
      add: (...add) => { this.className = [...new Set([...names(), ...add])].join(" "); },
      remove: (...gone) => {
        this.className = names().filter((name) => !gone.includes(name)).join(" ");
      },
      toggle: (name, force) => {
        const on = force === undefined ? !names().includes(name) : !!force;
        if (on) this.classList.add(name); else this.classList.remove(name);
        return on;
      },
    };
    this.dataset = {};
  }
  // A real input takes its starting value from the attribute, and the pack sets
  // it that way — el() has no special case for `value`.
  setAttribute(k, v) {
    this.attrs[k] = v;
    if (k === "value") this._value = v;
    // A real element mirrors data-* into dataset, and the prompt box reads its
    // chips back out of `dataset.handle` — without this the box round-trips to
    // empty text here and nowhere else.
    if (k.startsWith("data-")) this.dataset[k.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = v;
  }
  getAttribute(k) { return this.attrs[k]; }
  removeAttribute(k) { delete this.attrs[k]; }
  addEventListener(t, fn) { (this.listeners[t] ??= []).push(fn); }
  removeEventListener() {}
  /** A fragment is emptied into the parent rather than added to it, which is
   *  what a real one does and what the callers are counting on: the LoRA grid
   *  builds a chunk of cards in one and expects the grid to end up holding the
   *  cards, not a wrapper around them. */
  appendChild(c) {
    if (c.tagName === "#fragment") {
      for (const kid of c.children.splice(0)) this.appendChild(kid);
      return c;
    }
    this.children.push(c); c.parent = this; return c;
  }
  append(...c) { c.forEach((x) => this.appendChild(x)); }
  // The old children are detached, as a real one detaches them: `isConnected`
  // is read off the parent chain, and a node left pointing at its former parent
  // would answer that it is still in the document.
  //
  // And a browser has nowhere to put the focus once the element holding it has
  // left, so it puts it nowhere — which is the failure the refine panel's boxes
  // exist to survive: one rebuilt under the caret stops taking what is typed.
  replaceChildren(...c) {
    const dropped = (n) => {
      if (globalThis.document.activeElement === n) globalThis.document.activeElement = null;
      (n.children ?? []).forEach(dropped);
    };
    this.children.forEach((x) => {
      if (x.parent === this) x.parent = null;
      dropped(x);
    });
    this.children = [];
    c.forEach((x) => this.appendChild(x));
  }
  insertBefore(n) { return this.appendChild(n); }
  /** Swap this node for another where it stands, keeping the position. The LoRA
   *  manager rebuilds one card in place on every edit — redrawing the grid would
   *  throw away the scroll and every chunk appended to reach it — so a shim
   *  without this cannot get past the first click in that window. */
  replaceWith(next) {
    if (!this.parent) return;
    const at = this.parent.children.indexOf(this);
    this.parent.children[at] = next;
    next.parent = this.parent;
    this.parent = null;
  }
  // A drag takes the pointer so it keeps arriving here once it has left the
  // element. Nothing to emulate — the tests deliver the moves themselves — but
  // the call is real and an element without it throws on pointerdown.
  setPointerCapture() {}
  releasePointerCapture() {}
  cloneNode() { return new Node(this.tagName); }
  remove() {
    if (!this.parent) return;
    this.parent.children = this.parent.children.filter((c) => c !== this);
    this.parent = null;
  }
  normalize() {}
  /** Real, and it has to be: the prompt box asks whether the chip a click landed
   *  on is still one of its own, and the cast shelf asks whether the caret is
   *  inside itself before it redraws. A stub answering "no" turns the first into
   *  a chip that does nothing and the second into a shelf that always redraws —
   *  and both of those are shipped bugs this shim used to hide. */
  contains(node) {
    for (let at = node; at; at = at.parent) if (at === this) return true;
    return false;
  }
  /** Enough of a selector match for what the pack actually asks: a
   *  comma-separated list of alternatives, each one a tag name and/or any
   *  number of classes and bare attribute tests joined without a combinator —
   *  `button`, `.mmc-pills`, `[contenteditable]`, `.mmc-ref-cast[data-handle]`.
   *  Descendant and child combinators are still not modelled; nothing in the
   *  pack asks `closest` or `querySelectorAll` for one.
   *
   *  The compound form is not decoration. `.mmc-ref-cast[data-handle]` is the
   *  selector the prompt box uses to decide that a click landed on somebody's
   *  name, and while this only understood the two halves separately the shim
   *  answered "no" to it — so the one gesture in the box that opens a cast
   *  member could not be tested at all, which is why it kept being broken by
   *  changes elsewhere and nothing noticed. */
  matches(selector) {
    const classes = String(this.className).split(" ");
    return selector.split(",").map((s) => s.trim()).filter(Boolean).some((one) => {
      const parts = one.match(/^[a-zA-Z][\\w-]*|\\.[\\w-]+|\\[[^\\]]+\\]/g) ?? [];
      // A selector this cannot take apart must not match everything.
      if (!parts.length || parts.join("") !== one) return false;
      return parts.every((part) => {
        if (part.startsWith(".")) return classes.includes(part.slice(1));
        if (part.startsWith("[")) {
          const [, name, value] = /^\\[([^=\\]]+)(?:=["']?([^"'\\]]*)["']?)?\\]$/.exec(part) ?? [];
          if (!name) return false;
          return value === undefined ? name in this.attrs : String(this.attrs[name]) === value;
        }
        return this.tagName?.toLowerCase() === part;
      });
    });
  }
  closest(selector) {
    let node = this;
    while (node) {
      if (node.matches?.(selector)) return node;
      node = node.parent;
    }
    return null;
  }
  /** Whether this node is in the document, walked the way the real one is —
   *  `placeNear` asks, because a popover whose anchor was re-rendered under it
   *  must not be placed against a detached element. */
  get isConnected() {
    let node = this;
    while (node.parent) node = node.parent;
    return node === globalThis.document.body || node === globalThis.document.head
        || node === globalThis.document.documentElement;
  }
  focus() { globalThis.document.activeElement = this; }
  // A text field's caret. Nothing here models one; these exist because the pack
  // reads and restores the caret around an input it rewrites as you type, and a
  // shim without them turns that into a throw.
  get selectionStart() { return this._caret ?? String(this.value).length; }
  get selectionEnd() { return this.selectionStart; }
  setSelectionRange(start) { this._caret = start; }
  select() {}
  blur() { if (globalThis.document.activeElement === this) globalThis.document.activeElement = null; }
  /** Every descendant matching `selector`, through the same `matches` above.
   *  Real rather than stubbed, because the pack reads its own rendered DOM back
   *  in places where the answer is the feature: the prompt box counts the chips
   *  it is showing to work out which one a keystroke just deleted, and a stub
   *  answering "none" made every deletion invisible to it. */
  querySelectorAll(selector) {
    const found = [];
    const walk = (node) => {
      for (const child of node.children ?? []) {
        if (child.matches?.(selector)) found.push(child);
        walk(child);
      }
    };
    walk(this);
    return found;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] ?? null; }
  getBoundingClientRect() { return { top: 0, left: 0, width: 100, height: 100, bottom: 0, right: 0 }; }
  scrollIntoView() {}
  get firstChild() { return this.children[0] ?? null; }
  get childNodes() { return this.children; }
  get nodeType() { return this.tagName === "#text" ? 3 : 1; }
  /** Enough of a parse for `svg()`, which is how every glyph in the pack is
   *  made: one element written into a throwaway holder and taken straight back
   *  out of it. Without a child to take back, `firstElementChild` answered
   *  undefined and every icon silently became nothing — and the shell's empty
   *  frame, which hands the same holder's child to `replaceChildren`, threw. */
  set innerHTML(v) {
    this._html = String(v);
    this.children = [];
    const tag = this._html.trim().match(/^<([a-zA-Z][a-zA-Z0-9-]*)/)?.[1];
    if (!tag) return;
    const child = new Node(tag);
    // The markup as written, kept whole: nothing here parses attributes, and a
    // harness that serializes this tree back to HTML needs the original.
    child._outer = this._html;
    child.parent = this;
    this.children.push(child);
  }
  get innerHTML() { return this._html ?? ""; }
  get firstElementChild() { return this.children.find((c) => c.nodeType === 1) ?? null; }
  // A text node's text, under the name the DOM gives it. `PromptBox.getValue`
  // walks the box with this, which is how what was typed becomes the prompt in
  // the state — without it the box round-trips to `undefined` here.
  get nodeValue() { return this.textContent; }
  set nodeValue(v) { this.textContent = v; }
  set value(v) { this._value = v; }
  get value() { return this._value ?? ""; }
  /** Everything rendered under this node, flattened — what the checks read. */
  get text() {
    return [this.textContent, ...this.children.map((c) => c.text ?? "")].join(" ");
  }
}
globalThis.document = {
  // Uppercase, as an HTML element's `tagName` really is — the prompt box tells
  // a <br> and a block wrapper apart by it.
  createElement: (tag) => new Node(String(tag).toUpperCase()),
  createElementNS: (ns, tag) => new Node(tag),
  createTextNode: (t) => Object.assign(new Node("#text"), { textContent: t }),
  // Emptied into whatever it is appended to — see Node.appendChild.
  createDocumentFragment: () => new Node("#fragment"),
  body: new Node("body"),
  head: new Node("head"),
  documentElement: new Node("html"),
  getElementById: () => null,
  // The document's own, over the tree that is actually in it. `mountOverlay`
  // counts the open ones to stack the next; before this it always counted none.
  querySelector: (selector) => globalThis.document.body.querySelector(selector),
  querySelectorAll: (selector) => globalThis.document.body.querySelectorAll(selector),
  addEventListener() {}, removeEventListener() {},
};
// Ranges and selections: the prompt box places its own caret — putting it at
// the end of the text is how the window takes over from a full box on the face.
// Enough of the API to be called, not enough to model a caret; nothing here
// asks where the caret ended up.
globalThis.document.createRange = () => ({
  selectNodeContents() {}, collapse() {}, setStart() {}, setEnd() {},
  setStartAfter() {}, deleteContents() {}, insertNode() {},
  getBoundingClientRect: () => ({ top: 0, left: 0, width: 0, height: 0, bottom: 0, right: 0 }),
});
globalThis.window = { addEventListener() {}, removeEventListener() {},
                      getComputedStyle: () => ({}), innerWidth: 1600, innerHeight: 900,
                      devicePixelRatio: 1,
                      getSelection: () => ({ rangeCount: 0, isCollapsed: true,
                                             removeAllRanges() {}, addRange() {},
                                             getRangeAt: () => document.createRange() }) };
// The node-type constants the pack compares against — `getValue` asks whether
// each child of the prompt box is a text node or a chip.
globalThis.Node = { ELEMENT_NODE: 1, TEXT_NODE: 3 };
globalThis.requestAnimationFrame = () => {};
globalThis.cancelAnimationFrame = () => {};
// The timeline lane measures itself to decide how much of each block's label
// fits — see TimelineBody.fitLane. Nothing in this DOM has a width, so the
// measure bails and the observer has nothing to report; it exists so that
// registering one is not a crash.
// Recorded rather than inert: what a popover does when it *grows* is the thing
// worth testing — see the placement check.
globalThis.__observers = [];
globalThis.ResizeObserver = class {
  constructor(fn) { this.fn = fn; globalThis.__observers.push(this); }
  observe() {} unobserve() {} disconnect() { this.dead = true; }
  fire() { if (!this.dead) this.fn([]); }
};
// The LoRA grid hands a card's showcase clip a src only once it nears the
// viewport: a folder of hundreds each opening a connection at once is the
// media-element cap and the six-per-host budget both blown in one scroll.
// Nothing here has a viewport, so nothing ever intersects — this exists so that
// registering one is not a crash, which is what kept that window out of the
// suite entirely. Recorded like the resize ones, so a test can fire it by hand.
globalThis.IntersectionObserver = class {
  constructor(fn) { this.fn = fn; globalThis.__observers.push(this); }
  observe() {} unobserve() {} disconnect() { this.dead = true; }
  fire(entries = []) { if (!this.dead) this.fn(entries); }
};
// Backed by a Map rather than absent. Every localStorage access in the pack is
// wrapped against a browser that denies it outright, so leaving it undefined
// did not throw — it quietly sent all of them down the denied branch, which is
// the one path those features are least interesting on.
globalThis.localStorage = (() => {
  const store = new Map();
  return {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => { store.set(k, String(v)); },
    removeItem: (k) => { store.delete(k); },
    clear: () => { store.clear(); },
  };
})();
globalThis.Image = class { set src(v) {} };
globalThis.fetch = async () => ({ ok: true, json: async () => ({}) });
export const NodeClass = Node;
"""

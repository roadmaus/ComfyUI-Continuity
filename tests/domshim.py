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
    this.tagName = tag; this.children = []; this.style = {}; this.attrs = {};
    this.className = ""; this.textContent = ""; this.listeners = {};
    this.classList = { add: () => {}, remove: () => {}, toggle: () => {}, contains: () => false };
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
  appendChild(c) { this.children.push(c); c.parent = this; return c; }
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
  cloneNode() { return new Node(this.tagName); }
  remove() {
    if (!this.parent) return;
    this.parent.children = this.parent.children.filter((c) => c !== this);
    this.parent = null;
  }
  normalize() {}
  contains() { return false; }
  /** Enough of a selector match for `PromptBox.claim`, which asks whether a
   *  click landed on something that answers for itself. Tag names and single
   *  class names only — the one selector it is given is a list of those. */
  matches(selector) {
    return selector.split(",").map((s) => s.trim()).some((one) => {
      if (one.startsWith(".")) return String(this.className).split(" ").includes(one.slice(1));
      if (one.startsWith("[")) return one.slice(1, -1) in this.attrs;
      return this.tagName?.toLowerCase() === one;
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
  querySelector() { return null; }
  querySelectorAll() { return []; }
  getBoundingClientRect() { return { top: 0, left: 0, width: 100, height: 100, bottom: 0, right: 0 }; }
  scrollIntoView() {}
  get firstChild() { return this.children[0] ?? null; }
  get childNodes() { return this.children; }
  get nodeType() { return this.tagName === "#text" ? 3 : 1; }
  set innerHTML(v) { this._html = v; }
  get innerHTML() { return this._html ?? ""; }
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
  body: new Node("body"),
  head: new Node("head"),
  documentElement: new Node("html"),
  getElementById: () => null,
  querySelector: () => null,
  querySelectorAll: () => [],
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
globalThis.Image = class { set src(v) {} };
globalThis.fetch = async () => ({ ok: true, json: async () => ({}) });
export const NodeClass = Node;
"""

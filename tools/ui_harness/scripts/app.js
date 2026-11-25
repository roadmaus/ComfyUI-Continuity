// Stand-in for ComfyUI's scripts/app.js: a graph that holds nodes and an
// extension registry the harness page reads the pack's hooks back out of.
const graph = {
  _nodes: [],
  setDirtyCanvas() {},
  add(node) { this._nodes.push(node); node.graph = this; },
  remove(node) { this._nodes = this._nodes.filter((n) => n !== node); },
};
export const app = {
  graph,
  canvas: { setDirty() {}, ds: { scale: 1, offset: [0, 0] }, canvas: document.createElement("canvas") },
  extensions: [],
  registerExtension(extension) { this.extensions.push(extension); },
  extensionManager: { setting: { get: () => false } },
  async queuePrompt() {},
  async graphToPrompt() { return { output: {}, workflow: {} }; },
};
globalThis.app = app;

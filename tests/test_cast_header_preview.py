"""Cast header previews and blank-space collapse leave editing controls alone."""

import domshim
import layout
from harness import check


layout.skip_without_node()

SCRIPT = domshim.DOM + r'''
import { CastShelf } from "./web/creator/cast.js";
import { viewUrl } from "./web/creator/api.js";
import { thumbCrop } from "./web/creator/state.js";

globalThis.app = { extensionManager: { setting: { get: () => "en" } } };
const keyListeners = new Set();
const addListener = document.addEventListener.bind(document);
const removeListener = document.removeEventListener.bind(document);
document.addEventListener = (type, listener, ...args) => {
  if (type === "keydown") keyListeners.add(listener);
  addListener(type, listener, ...args);
};
document.removeEventListener = (type, listener, ...args) => {
  if (type === "keydown") keyListeners.delete(listener);
  removeListener(type, listener, ...args);
};
const subjects = [
  { handle: "subject", takes: "person", from: ["ref-1"], description: "studio portrait" },
  { handle: "prop", takes: "object", from: ["clip-1", "ref-2"], description: "a lamp" },
  { handle: "words", takes: "scene", from: [], description: "a bright studio" },
  { handle: "motion", takes: "person", from: ["clip-1"], description: "a walking figure" },
  { handle: "missing", takes: "person", from: ["ref-missing"], description: "an unavailable reference" },
];
const assets = [
  { handle: "ref-1", kind: "image", filename: "lighting/portrait.png [input]", role: "reference",
    crop: { x: 0.1, y: 0.1, w: 0.8, h: 0.8 } },
  { handle: "ref-2", kind: "image", filename: "lighting/lamp.png [input]", role: "reference" },
  { handle: "clip-1", kind: "video", filename: "lighting/walk.mp4 [input]", role: "reference" },
];
let commits = 0;
let touches = 0;
const shelf = new CastShelf({ getCast: () => subjects, setCast() {}, getAssets: () => assets,
  addAsset() {}, whereCited: () => ({ cited: true, text: "in prompt" }), cite() {},
  touch: () => { touches++; }, commit: () => { commits++; },
});
document.body.appendChild(shelf.root);
shelf.render();
const fire = (node, type) => {
  if (!node) throw new Error("Missing target for " + type);
  const chain = [];
  for (let at = node; at; at = at.parent) chain.push(at);
  const event = { target: node, currentTarget: node, stopped: false,
    stopPropagation() { this.stopped = true; }, preventDefault() {} };
  for (const at of chain) {
    event.currentTarget = at;
    for (const listener of at.listeners?.[type] ?? []) listener(event);
    if (event.stopped) break;
  }
  return event.stopped;
};
const settle = async () => {
  for (let i = 0; i < 4; i++) await new Promise((done) => setTimeout(done, 0));
};
const viewer = () => document.body.querySelector(".mmc-light");
const closeViewer = () => fire(viewer().parent, "pointerdown");
const topFace = () => shelf.root.querySelector(".mmc-cast-top").querySelector(".mmc-cast-face");
let bubbled = 0;
shelf.root.addEventListener("dblclick", () => { bubbled++; });
const out = { members: [], empty: [] };
const before = JSON.stringify({ subjects, assets });

for (const [handle, expected] of [["subject", assets[0]], ["prop", assets[1]]]) {
  shelf.openMember(handle);
  const face = topFace();
  let preventsBlur = false;
  for (const listener of face.listeners?.mousedown ?? []) {
    listener({ preventDefault() { preventsBlur = true; } });
  }
  fire(face, "click");
  const single = { preview: Boolean(viewer()), opened: shelf.opened.handle };
  const beforeBubble = bubbled;
  const keysBefore = keyListeners.size;
  const stopped = fire(face, "dblclick");
  await settle();
  const overlay = viewer();
  out.members.push({ handle, single, stopped, preventsBlur, bubbled: bubbled - beforeBubble,
    count: document.body.querySelectorAll(".mmc-light").length,
    source: overlay?.querySelector(".mmc-light-media")?.attrs.src,
    expected: viewUrl(expected.filename, { crop: thumbCrop(expected) }),
    caption: overlay?.querySelector(".mmc-light-name")?.textContent,
    opened: shelf.opened.handle,
  });
  if (overlay) {
    fire(overlay.querySelector(".mmc-light-media"), "pointerdown");
    out.members.at(-1).insideKeepsOpen = Boolean(viewer());
    if (handle === "prop") {
      for (const listener of [...keyListeners]) listener({ key: "Escape", stopPropagation() {} });
    } else closeViewer();
  }
  out.members.at(-1).closed = !viewer();
  out.members.at(-1).keysRemoved = keyListeners.size === keysBefore;
}

// A member added after the shelf was built uses the same header behavior.
const appended = { handle: "location", takes: "scene", from: ["ref-3"], description: "another studio" };
subjects.push(appended);
assets.push({ handle: "ref-3", kind: "image", filename: "lighting/location.png [input]", role: "reference" });
shelf.openMember("location");
fire(topFace(), "dblclick");
await settle();
out.appended = { source: viewer()?.querySelector(".mmc-light-media")?.attrs.src,
                 expected: viewUrl(assets.at(-1).filename), opened: shelf.opened.handle };
if (viewer()) closeViewer();
subjects.pop(); assets.pop();

for (const handle of ["words", "motion", "missing"]) {
  shelf.openMember(handle);
  const face = topFace();
  fire(face, "click"); fire(face, "dblclick");
  await settle();
  out.empty.push({ handle, blank: face.classList.contains("mmc-cast-face-blank"),
                   preview: Boolean(viewer()), opened: shelf.opened.handle });
}

shelf.openMember("subject");
const lower = shelf.root.querySelector(".mmc-cast-top").parent.querySelector(".mmc-cast-ref");
fire(lower.querySelector(".mmc-cast-ref-thumb"), "click");
const menu = document.body.querySelector(".mmc-cast-menu");
out.lower = { hasRoleMenu: Boolean(menu), previewAfterClick: Boolean(viewer()),
  doubleClickHandler: Boolean(lower.listeners?.dblclick?.length),
  thumbDoubleClickHandler: Boolean(lower.querySelector(".mmc-cast-ref-thumb").listeners?.dblclick?.length) };
fire(lower.querySelector(".mmc-cast-ref-thumb"), "dblclick");
await settle();
out.lower.previewAfterDoubleClick = Boolean(viewer());
menu?.remove();

// A collapsed picture also reserves its own click; the surrounding grip opens the member.
shelf.opened = null;
shelf.render();
const collapsed = shelf.root.querySelectorAll(".mmc-cast-card")[1];
fire(collapsed.querySelector(".mmc-cast-face"), "click");
out.collapsedImageClick = { opened: shelf.opened?.handle ?? null, preview: Boolean(viewer()) };
fire(collapsed.querySelector(".mmc-cast-face"), "dblclick");
out.collapsedImageDoubleClick = { opened: shelf.opened?.handle ?? null,
  count: document.body.querySelectorAll(".mmc-light").length,
  source: viewer()?.querySelector(".mmc-light-media")?.attrs.src };
if (viewer()) closeViewer();
fire(collapsed.querySelector(".mmc-cast-grip"), "click");
out.collapsedGrip = { opened: shelf.opened?.handle, preview: Boolean(viewer()) };

// Both ways out share the same close state, for the first and later members.
out.collapse = [];
for (const handle of ["subject", "prop"]) {
  for (const selector of [".mmc-cast-collapse-area", ".mmc-cast-shut"]) {
    shelf.openMember(handle);
    const top = shelf.root.querySelector(".mmc-cast-top");
    const button = top.querySelector(selector);
    shelf.changing = { subject: shelf.opened };
    const attrs = { title: button.attrs.title, expanded: button.attrs["aria-expanded"] };
    fire(button, "click");
    await settle();
    out.collapse.push({ handle, selector, attrs,
      opened: shelf.opened?.handle ?? null, changing: shelf.changing,
      expandedCards: shelf.root.querySelectorAll(".mmc-cast-top").length });
  }
}

// The blank area is a native sibling button, not an ancestor click listener.
shelf.openMember("subject");
const top = shelf.root.querySelector(".mmc-cast-top");
const area = top.querySelector(".mmc-cast-collapse-area");
out.area = { tag: area.tagName, type: area.attrs.type, label: area.attrs["aria-label"],
  parent: area.parent.className, children: area.children.length };
out.editing = [];
for (const selector of [".mmc-cast-name", ".mmc-cast-desc", ".mmc-cast-takes"]) {
  fire(top.querySelector(selector), "click");
  await settle();
  out.editing.push({ selector, opened: shelf.opened?.handle });
  document.body.querySelector(".mmc-cast-menu")?.remove();
}
fire(top, "click");
out.topBackground = shelf.opened?.handle;
out.unchanged = before === JSON.stringify({ subjects, assets });
out.writes = { commits, touches };
console.log(JSON.stringify(out));
'''

with layout.pack(skip=("atlas",)) as target:
    got = layout.in_pack(SCRIPT, target)

for member in got["members"]:
    handle = member["handle"]
    check(f"@{handle} header single-click does not preview or switch members",
          member["single"], {"preview": False, "opened": handle})
    check(f"@{handle} header double-click opens one viewer on its representative image",
          [member["count"], member["source"], member["opened"]], [1, member["expected"], handle])
    check(f"@{handle} header double-click stays within the thumbnail",
          [member["stopped"], member["bubbled"]], [True, 0])
    check(f"@{handle} first mouse-down does not trigger a blur redraw", member["preventsBlur"], True)
    check(f"@{handle} viewer names the member and closes cleanly",
          [member["caption"], member["insideKeepsOpen"], member["closed"], member["keysRemoved"]],
          [f"@{handle}", True, True, True])
check("newly added members also preview their own image", got["appended"],
      {"source": got["appended"]["expected"], "expected": got["appended"]["expected"], "opened": "location"})
check("members without an available still safely keep their blank header", got["empty"],
      [{"handle": handle, "blank": True, "preview": False, "opened": handle} for handle in ("words", "motion", "missing")])
check("lower reference thumbnails retain their role-menu interaction", got["lower"],
      {"hasRoleMenu": True, "previewAfterClick": False, "doubleClickHandler": False,
       "thumbDoubleClickHandler": False, "previewAfterDoubleClick": False})
check("collapsed picture single-click does not expand or preview", got["collapsedImageClick"], {"opened": None, "preview": False})
check("collapsed picture double-click previews without expanding", got["collapsedImageDoubleClick"],
      {"opened": None, "count": 1, "source": got["members"][1]["expected"]})
check("the surrounding collapsed grip still expands the member", got["collapsedGrip"], {"opened": "prop", "preview": False})
for result in got["collapse"]:
    handle = result["handle"]
    check(f"@{handle} {result['selector']} closes without changing the cast", result,
          {"handle": handle, "selector": result["selector"],
           "attrs": {"title": f"Close @{handle}", "expanded": "true"},
           "opened": None, "changing": None, "expandedCards": 0})
check("the blank header area is an explicitly named native sibling button", got["area"],
      {"tag": "BUTTON", "type": "button", "label": "Close @subject",
       "parent": "mmc-cast-namerow", "children": 0})
check("name, description and type controls do not collapse the card", got["editing"],
      [{"selector": selector, "opened": "subject"}
       for selector in (".mmc-cast-name", ".mmc-cast-desc", ".mmc-cast-takes")])
check("the surrounding header is not a blanket collapse target", got["topBackground"], "subject")
check("previewing does not mutate cast members or attached assets", got["unchanged"], True)
check("previewing never commits or touches the workflow", got["writes"], {"commits": 0, "touches": 0})

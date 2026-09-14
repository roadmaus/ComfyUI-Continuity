"""Cast thumbnails must say when their attached files are out of the run.

A cast member can still own a muted file. The reference row showed that state,
but the cast shelf drew the same file as live, hiding why a cited identity had
no picture at compilation. Exercise the real tile across media and cast roles;
this is presentation only, not another route around reference-cap checks.

    python3 tests/test_cast_reference_mute.py
"""

import layout
from harness import check, passed

layout.skip_without_node()

from domshim import DOM  # noqa: E402

CHECK = r"""
globalThis.app = { extensionManager: { setting: { get: () => "en" } } };
const { CastShelf } = await import("./web/creator/cast.js");
const subject = {
  handle: "anna",
  from: ["ref-1"],
  notes: { "ref-1": "a reference note" },
  triggers: { "ref-1": "walking" },
};
let clicks = 0;
const shelf = {
  pickRole(anchor, who, handle, role) {
    if (anchor.tagName === "BUTTON" && who === subject && handle === "ref-1" && role) clicks++;
  },
};
const has = (tile, name) => tile.classList.contains(name);
const descendant = (tile, name) => tile.querySelector(`.${name}`);
const cases = [
  ["image", "face.png", "from"],
  ["image", "pose.png", "motion"],
  ["video", "walk.mp4", "motion"],
  ["video", "scene.mp4", "replaces"],
  ["audio", "voice.wav", "voice"],
  ["image", "refmod:face", "from"],
];
const out = { cases: [] };
for (const [kind, filename, role] of cases) {
  const asset = { handle: "ref-1", kind, filename, role: "reference", enabled: false };
  const before = JSON.stringify(asset);
  const tile = CastShelf.prototype.refTile.call(shelf, subject, asset.handle, role, [asset]);
  tile.listeners.click[0]({ currentTarget: tile });
  out.cases.push({
    name: `${kind}/${role}/${filename}`,
    off: has(tile, "off"), missing: has(tile, "missing"),
    badge: Boolean(descendant(tile, "mmc-cast-muted")),
    explains: tile.getAttribute("title").includes("@ref-1 — muted"),
    wake: has(tile, "wakes") && Boolean(descendant(tile, "wake")),
    note: tile.getAttribute("title").includes("a reference note"),
    role: role === "from" || Boolean(descendant(tile, `mmc-cast-badge-${role}`)),
    untouched: before === JSON.stringify(asset),
  });
  // Re-rendering after the host unmutes removes the marker and explanation.
  delete asset.enabled;
  const live = CastShelf.prototype.refTile.call(shelf, subject, asset.handle, role, [asset]);
  out.cases.at(-1).live = !has(live, "off") && !descendant(live, "mmc-cast-muted")
    && !live.getAttribute("title").includes("muted");
}
const missing = CastShelf.prototype.refTile.call(shelf, subject, "ref-1", "from", []);
out.missing = has(missing, "missing") && !has(missing, "off")
  && !descendant(missing, "mmc-cast-muted")
  && missing.getAttribute("title").includes("not attached here any more");
out.clicks = clicks;
console.log(JSON.stringify(out));
"""

with layout.pack() as target:
    report = layout.in_pack(DOM + CHECK, target)

check("all reference kinds/roles exercised", len(report["cases"]), 6)
for case in report["cases"]:
    label = case.pop("name")
    check(label, case, {
        "off": True, "missing": False, "badge": True, "explains": True,
        "wake": True, "note": True, "role": True, "untouched": True, "live": True,
    })
check("missing file keeps its separate explanation", report["missing"], True)
check("muted tiles still open the role menu", report["clicks"], 6)
passed("muted cast references stay visibly muted across media and roles")

"""PreStage's picture actions must reach the same still compiler after save.

Exercises the real chip handlers and serializer in the shared DOM harness,
then compiles their payloads without loading models or starting ComfyUI.
"""
import layout
from domshim import DOM
from harness import check, passed

layout.skip_without_node()

SCRIPT = r'''
const S = await import("./web/creator/state.js");
const { PreStageBody, PreStageEditor } = await import("./web/creator/prestage.js");
const { applyPick, asPick } = await import("./web/creator/picture.js");
const out = {};
const make = (extra = {}) => S.parsePreStage(JSON.stringify({
  arch: "flux2klein", prompt: "Draw a portrait", aspect: "1:1", short_edge: 1024,
  refs: [{ handle: "ref-1", filename: "portrait.png" }], ...extra,
}));
const body = (state) => Object.assign(Object.create(PreStageBody.prototype), {
  state, commit() {}, reveal() {}, editor: { probeInit() {} },
});
const editor = (state) => Object.assign(Object.create(PreStageEditor.prototype), {
  state, sizes: new Map(), commit() {}, cropMark: () => document.createElement("button"),
  flash(message) { this.notice = message; },
});
const payload = (state) => JSON.parse(S.serializePreStage(state));
const all = (root) => [root, ...root.children.flatMap(all)];
const editButtons = (host) => host.state.refs.flatMap((ref, i) =>
  all(host.renderRefChip(ref, i)).filter(n => n.classList.contains("mmc-asset-role-pick")));
const cast = { handle: "anna", from: ["ref-1"], description: "a woman" };
const castRef = { handle: "ref-1", filename: "anna.png", mods: { flux2: "refmod:cast/anna.flux2" } };
const guide = { handle: "ref-2", filename: "guide.png", role: "guide", guide: "depth" };
const plain = { handle: "ref-3", filename: "scene.png" };
const crop = { x: 0, y: 0, w: 0.5, h: 1, turn: 90, mirror: "h" };

// A real output chip press opts into editing and forgets the old rendition,
// framing and cut-out provenance; the handle remains the prompt's handle.
{
  const state = make({ refs: [{ handle: "ref-1", filename: "old.png",
    crop, panels: [{ filename: "old-source.png", cut: true }],
    mods: { flux2: "refmod:cast/old.flux2" } }] });
  const host = body(state);
  host.renderAgainChip("new.png [output]").listeners.click[0]();
  out.again = { payload: payload(state), source: S.preStageSource(state),
    edits: S.preStageEditsFirst(state) };
}
// Cast and guide pictures are never the picture replaced by the edit loop.
// The explicit edit action puts its target before guides, matching the
// compiler's first-plain-reference contract without reordering ordinary loads.
for (const [name, refs] of Object.entries({
  castFirst: [castRef, plain], guideFirst: [castRef, guide, plain],
  castOnly: [castRef], guideOnly: [guide], empty: [],
})) {
  const state = make({ refs, subjects: refs.includes(castRef) ? [cast] : [] });
  const host = editor(state);
  const buttons = editButtons(host);
  out[name] = { before: payload(state), buttons: buttons.length };
  if (buttons.length) {
    buttons[0].listeners.click[0]();
    out[name].toggled = { payload: payload(state), source: S.preStageSource(state) };
    editButtons(host)[0].listeners.click[0]();
    out[name].disabled = S.preStageEditsFirst(state);
  }
  body(state).takeBack("new.png [output]");
  out[name].after = payload(state);
  out[name].source = S.preStageSource(state);
}
// A full pool made only of protected pictures cannot take a new plain one.
// Refuse without changing claims, files, or reference count.
{
  const state = make({ arch: "qwenedit", edition: "2511",
    refs: [castRef, guide, { handle: "ref-3", filename: "ben.png" }],
    subjects: [cast, { handle: "ben", from: ["ref-3"], description: "a man" }] });
  const host = body(state);
  host.editor = editor(state);
  out.fullProtected = { before: payload(state) };
  host.takeBack("new.png [output]");
  out.fullProtected.after = payload(state);
  out.fullProtected.notice = host.editor.notice ?? null;
}
// An explicit init still owns partial denoise; reuse replaces that init,
// rather than leaving an old image in charge of the new result's canvas.
{
  const state = make({ init: { filename: "old-init.png", denoise: 0.35, crop } });
  body(state).takeBack("new.png [output]");
  out.explicitInit = payload(state);
}
// Cancel/no-op is not involved: these are accepted picture-editor answers.
// Both init and reference framing must survive the exact commit serializer.
{
  const state = make({ init: { filename: "source.png", denoise: 0.65 } });
  applyPick(state.init, asPick({ source: "source.png", crop }));
  applyPick(state.refs[0], asPick({ source: "portrait.png", crop }));
  out.framing = { live: state, saved: payload(state) };
  out.framing.reopened = payload(S.parsePreStage(S.serializePreStage(state)));
}
// Cut-out metadata belongs to the source, not only to the built PNG, so the
// editor can reopen on it after save. Includes a guide and the init path.
{
  const panels = [{ filename: "source.png", cut: true,
    points: [{ x: 0.2, y: 0.4, include: true }], crop }];
  const state = make({ refs: [{ ...guide, filename: "cut.png", panels, crop }],
    init: { filename: "cut.png", denoise: 0.5, panels, crop } });
  out.cutout = payload(S.parsePreStage(S.serializePreStage(state)));
}
// Every offered quality survives commit and reopen, including the preset
// called "default", which is not necessarily the node's current default.
out.qualities = {};
for (const quality of S.PRESTAGE_IDEOGRAM_QUALITIES) {
  const state = make({ arch: "ideogram4", refs: [], quality });
  out.qualities[quality] = { expectedSteps: S.PRESTAGE_IDEOGRAM_STEPS[quality],
    payload: payload(state), restored: S.parsePreStage(S.serializePreStage(state)).quality };
}
out.legacyQuality = S.parsePreStage(JSON.stringify({ arch: "ideogram4" })).quality;
// Reaching the ordinary cap shows the refusal rather than throwing.
{
  const host = editor(make({ arch: "qwenedit", edition: "2511",
    refs: [1, 2, 3].map(n => ({ handle: `ref-${n}`, filename: `p${n}.png` })) }));
  try { await host.addRefs(); }
  catch (error) { out.capError = `${error.name}: ${error.message}`; }
  out.capNotice = host.notice ?? null;
}
console.log(JSON.stringify(out));
'''

with layout.pack(skip=["atlas"]) as target:
    got = layout.in_pack(DOM + SCRIPT, target)

pkg = layout.load("canvas", "registry", "contextir", "subjects", "compile",
                  "compile_image", "flux2klein_still", "ideogram4_still")
ci = pkg.compile_image


def compile_image(data, family=None):
    return ci.compile_prestage(data, family or pkg.flux2klein_still,
                               image_size_lookup=lambda _: (1600, 800))


again = got["again"]
compiled = compile_image(again["payload"])
check("output edit is explicitly enabled", again["edits"], True)
check("output edit follows the new picture", again["source"], "new.png [output]")
check("output edit keeps its cited handle", again["payload"]["refs"][0]["handle"], "ref-1")
check("old renditions are not compiled for a new picture", compiled.mods, {})
check("old framing is not applied to a new output", compiled.framing, {})
check("old cut-out source is not attached to a new output",
      again["payload"]["refs"][0].get("panels"), None)
check("output edit promotes the new picture in the compiler", compiled.init,
      {"filename": "new.png [output]", "denoise": 1.0})

for name in ("castFirst", "guideFirst", "castOnly", "guideOnly", "empty"):
    row = got[name]
    check(f"{name}: exactly the first eligible picture has an edit switch", row["buttons"],
          1 if name in ("castFirst", "guideFirst") else 0)
    if "toggled" in row:
        toggled = compile_image(row["toggled"]["payload"])
        check(f"{name}: switch and compiler target agree", toggled.init,
              {"filename": "scene.png", "denoise": 1.0})
        check(f"{name}: switch source", row["toggled"]["source"], "scene.png")
        check(f"{name}: switch can be turned back off", row["disabled"], False)
    after = row["after"]
    original_protected = [r for r in row["before"].get("refs", [])
                          if r.get("role") == "guide" or r["filename"] == "anna.png"]
    for ref in original_protected:
        check(f"{name}: preserve {ref['filename']}",
              next((r for r in after["refs"] if r["handle"] == ref["handle"]), None), ref)
    check(f"{name}: output is the source", row["source"], "new.png [output]")
    check(f"{name}: compiler agrees with output source", compile_image(after).init,
          {"filename": "new.png [output]", "denoise": 1.0})

check("explicit init keeps partial denoise but uses the new output",
      compile_image(got["explicitInit"]).init, {"filename": "new.png [output]", "denoise": 0.35})
check("explicit init preserves the reference pool", got["explicitInit"]["refs"][0]["filename"],
      "portrait.png")
check("a full protected pool is not overwritten or overfilled", got["fullProtected"]["after"],
      got["fullProtected"]["before"])
check("a full protected pool explains the refusal",
      "At most 3" in (got["fullProtected"]["notice"] or ""), True)

live = compile_image(got["framing"]["live"])
for path in ("saved", "reopened"):
    actual = compile_image(got["framing"][path])
    check(f"{path}: framing reaches the compiler", actual.framing, live.framing)
    check(f"{path}: cropped canvas reaches the compiler",
          (actual.width, actual.height), (live.width, live.height))
for asset in (got["cutout"]["init"], got["cutout"]["refs"][0]):
    check("cutout source and clicks survive reopen", asset.get("panels"), [{
        "filename": "source.png", "cut": True, "points": [{"x": 0.2, "y": 0.4, "include": True}],
        "crop": {"x": 0, "y": 0, "w": 0.5, "h": 1, "turn": 90, "mirror": "h"},
    }])
for quality, row in got["qualities"].items():
    check(f"{quality}: selection survives reopen", row["restored"], quality)
    check(f"{quality}: selected steps reach the compiler",
          compile_image(row["payload"], pkg.ideogram4_still).schedule["steps"], row["expectedSteps"])
check("old blobs still receive the family's current quality default", got["legacyQuality"],
      pkg.ideogram4_still.DEFAULT_IDEOGRAM_QUALITY)
check("reference cap does not throw", got.get("capError"), None)
check("reference cap explains the refusal", "At most 3" in (got["capNotice"] or ""), True)
passed("all PreStage picture-action and serialization regressions passed")

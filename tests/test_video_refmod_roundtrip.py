"""Saved renditions survive the video's shared-pool and one-pass boundaries.

Real JS state/serialization and the merge action feed the Python compiler;
only the existing DOM/API host is stubbed. No files, models or GPU are read.
"""

from pathlib import Path

import layout
from domshim import DOM
from harness import check

layout.skip_without_node()
compiler = layout.load("canvas", "contextir", "subjects", "compile").compile

SCRIPT = r'''
const S = await import('./web/creator/state.js');
const { Timeline } = await import('./web/creator/timeline.js');
const snapshot = piece => JSON.parse(S.serializeTimeline(piece));
const picture = {handle:'img-1', kind:'image', role:'reference', filename:'anna.png',
  mods:{h3_video:'refmod:cast/anna', flux2:'refmod:cast/anna.flux2'}};
const make = (segments, extra={}) => S.parseTimeline(JSON.stringify({
  version:2, family:'h3', aspect:'16:9', short_edge:768, segments, ...extra}));
const shot = (prompt, assets) => ({prompt, duration_s:6, assets});
const piece = make([shot('@anna walks.', [picture])], {
  subjects:[{handle:'anna', from:['img-1'], wears:{h3:{send:'saved'}}}]});
const out = {single:snapshot(piece)};
// Adding a second card promotes Cast attachments into the project pool.
piece.segments.push(S.continuingSegment(piece));
piece.segments[1].prompt = '@anna sits.';
S.syncTimeline(piece);
out.pooled = snapshot(piece);

for (const [name, second] of [
  ['oneSource', null],
  ['differentRenditions', {...picture, mods:{h3_video:'refmod:cast/anna-other'}}],
  ['sameRenditions', {...picture,
    mods:{flux2:'refmod:cast/anna.flux2', h3_video:'refmod:cast/anna'}}],
  ['rawAndSaved', {...picture, mods:{}}],
]) {
  const timeline = make([shot('@img-1 walks.', [picture]),
    shot(second ? '@img-1 sits.' : 'The camera follows.', second ? [second] : [])]);
  out[name+'Separate'] = snapshot(timeline);
  Timeline.prototype.mergeAt.call({timeline, commit(){}}, 1);
  out[name+'Merged'] = snapshot(timeline);
}
console.log(JSON.stringify(out));
'''

with layout.pack(skip=["atlas"]) as target:
    # The private class is exposed only in the disposable harness copy. The
    # merge action itself, and all state/serializer/compiler code, is unchanged.
    module = Path(target, "web", "creator", "timeline.js")
    module.write_text(module.read_text(encoding="utf-8").replace(
        "class Timeline {", "export class Timeline {", 1), encoding="utf-8")
    blobs = layout.in_pack(DOM + SCRIPT, target)


def plans(name):
    return [compiler.compile_segment(p) for p in compiler.timeline_payloads(blobs[name])]


def renditions(name):
    return [[a.mod_for("h3_video") for a in plan.ref_images] for plan in plans(name)]


check("one local Cast reference selects its saved H3 rendition",
      renditions("single"), [["refmod:cast/anna"]])
check("the UI keeps both spaces when it promotes the Cast photo",
      blobs["pooled"]["assets"][0]["mods"],
      {"h3_video": "refmod:cast/anna", "flux2": "refmod:cast/anna.flux2"})
check("both pooled shots still select the saved H3 rendition",
      renditions("pooled"), [["refmod:cast/anna"], ["refmod:cast/anna"]])
check("pool injection also preserves the other family's rendition",
      [p.ref_images[0].mod_for("flux2") for p in plans("pooled")],
      ["refmod:cast/anna.flux2", "refmod:cast/anna.flux2"])
check("ordinary local reference works before merge",
      renditions("oneSourceSeparate"), [["refmod:cast/anna"], []])
check("ordinary local reference survives the merge",
      renditions("oneSourceMerged"), [["refmod:cast/anna"]])
check("a merged reference retains its other family's rendition",
      plans("oneSourceMerged")[0].ref_images[0].mod_for("flux2"), "refmod:cast/anna.flux2")
check("separate shots choose their own saved renditions",
      renditions("differentRenditionsSeparate"),
      [["refmod:cast/anna"], ["refmod:cast/anna-other"]])
check("same photo with different renditions must not alias on merge",
      renditions("differentRenditionsMerged"),
      [["refmod:cast/anna", "refmod:cast/anna-other"]])
check("distinct saved renditions get distinct prompt labels",
      all(label in plans("differentRenditionsMerged")[0].body
          for label in ("<Picture 1>", "<Picture 2>")), True)
check("equal maps deduplicate regardless of dictionary insertion order",
      renditions("sameRenditionsMerged"), [["refmod:cast/anna"]])
check("the raw photo and its saved rendition are different inputs",
      renditions("rawAndSavedMerged"), [["refmod:cast/anna", None]])

# Legacy no-mod serialization/cache keys retain their old shape; a written map
# is a copy, so changing a payload cannot alter the source Asset in place.
plain = {"handle": "img-1", "kind": "image", "role": "reference", "filename": "anna.png"}
asset = compiler._parse_assets([plain])[0]
check("no-mod asset keeps its old blob shape", compiler._asset_dict(asset), plain)
saved = compiler._parse_assets([{**plain, "mods": {"h3_video": "refmod:cast/anna"}}])[0]
written = compiler._asset_dict(saved)
check("asset parse/write/parse retains the rendition", compiler._parse_assets([written])[0].mods,
      saved.mods)
if "mods" in written:
    written["mods"]["h3_video"] = "refmod:cast/somebody-else"
check("serialized maps do not alias the original asset", saved.mod_for("h3_video"),
      "refmod:cast/anna")
video = {"handle": "vid-1", "kind": "video", "role": "reference", "filename": "walk.mp4",
         "track": "picture", "mods": {"h3_video": "refmod:cast/walk"}}
parsed_video = compiler._parse_assets([video])[0]
check("video reference rendition survives the same boundary",
      compiler._parse_assets([compiler._asset_dict(parsed_video)])[0].mods, video["mods"])
direct = {**plain, "filename": "refmod:cast/anna"}
check("standalone RefMod keeps its legacy serialization",
      compiler._asset_dict(compiler._parse_assets([direct])[0]), direct)

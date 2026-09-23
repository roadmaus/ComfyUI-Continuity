"""Changing a reference's source invalidates its saved renditions.

Real editor swap/state serialization and H3 compilation, with only the file
picker answer and browser host stubbed. No model weights or GPU are needed.
"""
import layout
from domshim import DOM
from harness import check, passed

layout.skip_without_node()

SCRIPT = r"""
const S = await import('./web/creator/state.js');
const { CreatorEditor } = await import('./web/creator/editor.js');
const mods = {h3_video: 'refmod:old-person', flux2: 'refmod:old-person.flux2'};
const out = {};
for (const [label, kind, pick] of [
  ['image', 'image', {path:'new-person.png', kind:'image'}],
  ['video', 'video', {path:'new-walk.mp4', kind:'video', track:'picture',
                    trim:{start:1,end:3}, crop:{x:0,y:0,w:0.5,h:1}}],
  ['cancelled', 'image', null],
  ['unchanged', 'image', {path:'old-person.png',kind:'image'}],
]) {
  const handle = kind === 'image' ? 'img-1' : 'vid-1';
  const state = S.parseState(JSON.stringify({
    prompt:`@${handle} walks through the room`, duration_s:5,
    assets:[{handle,kind,role:'reference',
      filename:kind==='image'?'old-person.png':'old-walk.mp4',mods,
      ...(kind==='video'?{track:'picture+sound',trim:{start:0,end:2}}:{})},
      {handle:'img-2',kind:'image',role:'reference',filename:'other.png',mods}]
  }));
  const editor = new CreatorEditor({state,nodeId:()=>1});
  globalThis.__picked = pick ? [pick] : [];
  await editor.replaceAsset(state.assets[0]);
  out[label] = JSON.parse(S.serializeState(state));
}
const piece = S.parseTimeline(JSON.stringify({version:2,prompt:'@ref-1',
  assets:[{handle:'ref-1',kind:'video',role:'reference',filename:'walk.mp4',
           track:'picture+sound',trim:{start:0,end:2},mods}],
  subjects:[{handle:'anna',from:['ref-1'],motion:'ref-1',description:'a woman'}],
  segments:[{prompt:'@anna stands still',duration_s:5}, {prompt:'the room',duration_s:5}]}));
S.stillForClip(piece,piece.assets[0],'selected-frame.png',{x:0,y:0,w:0.5,h:1});
out.frame = JSON.parse(S.serializeTimeline(piece));
console.log(JSON.stringify(out));
"""

with layout.pack(extra_stubs={
    "../pack/web/creator/picker.js":
    "export async function openPicker(){return globalThis.__picked;}\n"
    "export class Picker {}\n",
}, skip=["atlas"]) as target:
    got = layout.in_pack(DOM + SCRIPT, target)

compiler = layout.load("compile", package="swap_mod_contract").compile
for kind, filename in (("image", "new-person.png"), ("video", "new-walk.mp4")):
    row = got[kind]["assets"][0]
    check(f"{kind}: new file survives serialization", row["filename"], filename)
    check(f"{kind}: all old-family renditions are dropped", row.get("mods"), None)
    check(f"{kind}: other references keep their renditions",
          got[kind]["assets"][1]["mods"],
          {"h3_video": "refmod:old-person", "flux2": "refmod:old-person.flux2"})
    compiled = compiler.compile_request(got[kind])
    asset = (compiled.ref_images if kind == "image" else compiled.ref_videos)[0]
    check(f"{kind}: H3 encodes the new source instead of the old mod",
          (asset.filename, asset.mod_for("h3_video")), (filename, None))
check("replacement keeps the new clip's trim", got["video"]["assets"][0]["trim"],
      {"start": 1, "end": 3})
check("replacement keeps the new clip's framing", got["video"]["assets"][0]["crop"],
      {"x": 0, "y": 0, "w": 0.5, "h": 1})
for label in ("cancelled", "unchanged"):
    row = got[label]["assets"][0]
    check(f"{label}: old source is untouched", row["filename"], "old-person.png")
    check(f"{label}: valid existing renditions survive", row.get("mods"),
          {"h3_video": "refmod:old-person", "flux2": "refmod:old-person.flux2"})
row = got["frame"]["assets"][0]
check("frame extraction keeps the pool handle and selected source",
      (row["handle"], row["kind"], row["filename"]),
      ("ref-1", "image", "selected-frame.png"))
check("frame extraction removes video renditions", row.get("mods"), None)
check("frame extraction removes video-only settings",
      (row.get("trim"), row.get("track")), (None, None))
check("frame extraction preserves appearance ownership",
      got["frame"]["subjects"][0]["from"], ["ref-1"])
check("frame extraction releases motion ownership",
      got["frame"]["subjects"][0].get("motion"), None)
passed("reference swaps and clip-to-still changes forget only obsolete renditions")

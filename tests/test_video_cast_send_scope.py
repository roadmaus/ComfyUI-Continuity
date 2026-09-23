"""A stored member's family send choice only affects shots citing that member.

The real Wears menu and timeline serializer supply the main regression cases;
pure compiler controls cover the final prose and ownership-pruning contract.
No GPU, installed ComfyUI, model files or server are needed.
"""

from copy import deepcopy

import layout
from domshim import DOM
from harness import FAILURES, check

layout.skip_without_node()
compiler = layout.load("canvas", "contextir", "subjects", "compile").compile

SCRIPT = r'''
const S = await import('./web/creator/state.js');
const { WearsPanel } = await import('./web/creator/wears.js');
const { castFamilies } = await import('./web/creator/refmod.js');
const family = castFamilies('h3', '')[0];
const image = {handle:'ref-1', kind:'image', role:'reference', filename:'anna.png',
  mods:{h3_video:'refmod:cast/anna', flux2:'refmod:cast/anna.flux2'}};
const snapshot = state => JSON.parse(S.serializeTimeline(state));
function make(subjects, prompt, count=2) {
  return S.parseTimeline(JSON.stringify({version:2, family:'h3', aspect:'16:9', short_edge:768,
    assets:[image], subjects, segments:[{prompt, duration_s:6},
      ...(count===2 ? [{prompt:'An empty room.', duration_s:6}] : [])]}));
}
function choose(state, who, label) {
  const member = state.subjects.find(s=>s.handle===who);
  const panel = new WearsPanel({commit(){}, redraw(){}});
  panel.sendMenu(document.createElement('button'), member, family,
    S.castAssets(state).filter(a=>member.from.includes(a.handle)));
  const button = [...document.querySelectorAll('.mmc-opt')].find(b =>
    b.querySelector('.mmc-cast-menu-text')?.children[0]?.textContent===label);
  if (!button) throw new Error('Menu choice missing: '+label);
  button.listeners.click[0]();
}
const out = {};
const unused = make([{handle:'anna', from:['ref-1']}], 'An empty room.');
choose(unused, 'anna', 'Their description only');
out.unusedWords = snapshot(unused);
const shared = make([{handle:'anna', from:['ref-1'], description:'a woman'},
  {handle:'bob', from:['ref-1'], description:'a man'}], '@anna walks.', 1);
choose(shared, 'anna', 'Their saved reference');
out.before = snapshot(shared);
choose(shared, 'bob', 'Their pictures');
out.after = snapshot(shared);
console.log(JSON.stringify(out));
'''

with layout.pack(skip=["atlas"]) as target:
    blobs = layout.in_pack(DOM + SCRIPT, target)


def first(piece):
    return compiler.compile_segment(compiler.timeline_payloads(piece)[0])


def succeeds(label, fn):
    try:
        return fn()
    except compiler.CompileError as exc:
        FAILURES.append(f"{label}: unexpected refusal: {exc}")


def refused(label, fn):
    try:
        fn()
    except compiler.CompileError as exc:
        check(label, "@anna is sent as words alone" in str(exc), True)
    else:
        FAILURES.append(f"{label}: expected the cited words-only refusal")


unused = succeeds("an uncited words-only member cannot block an unrelated shot",
                  lambda: first(blobs["unusedWords"]))
if unused:
    check("unused photo-only member is not in compiled Cast", unused.cast, [])
    check("unused member's owned reference is still pruned", unused.ref_images, [])
before, after = first(blobs["before"]), first(blobs["after"])
check("only Anna walks on, before and after Bob's menu change",
      [[s.handle for s in p.cast] for p in (before, after)], [["anna"], ["anna"]])
check("uncited Bob cannot override Anna's saved reference",
      after.ref_images[0].mod_for("h3_video"), before.ref_images[0].mod_for("h3_video"))
check("another family's rendition is untouched", after.ref_images[0].mod_for("flux2"),
      "refmod:cast/anna.flux2")

PHOTO = {"handle": "img-1", "kind": "image", "role": "reference", "filename": "anna.png",
         "mods": {"h3_video": "refmod:cast/anna", "flux2": "refmod:cast/anna.flux2"}}
WORDS = {"handle": "anna", "from": ["img-1"], "seeded": True,
         "features": [{"attr": "face"}], "wears": {"h3": {"send": "words"}}}


def request(prompt="An empty room.", **extra):
    return {"prompt": prompt, "duration_s": 6, "assets": [deepcopy(PHOTO)],
            "subjects": [deepcopy(WORDS)], **extra}


# The same effective prose that selects/prunes Cast must select send behavior:
# refined text replaces the typed prompt; sound fields and kept sections count.
refused("cited words-only member still needs an actual description",
        lambda: compiler.compile_request(request("@anna walks.")))
for name, extra in (
    ("soundscape", {"soundscape": "@anna is heard"}),
    ("music", {"music": "@anna sings"}),
    ("refined body", {"refined": {"body": "@anna walks."}}),
    ("refined section", {"refined": {"sections": {"subject_definitions": "@anna waits"}}}),
):
    refused(f"{name} counts as an active citation",
            lambda extra=extra: compiler.compile_request(request(**extra)))
for name, data in (
    ("refined body replaces typed citation", request("@anna walks.",
        refined={"body": "An empty room."})),
    ("disabled rewrite cannot activate Cast", request(refined={"enabled": False,
        "body": "@anna walks.", "sections": {"subject_definitions": "@anna waits"}})),
    ("foreign family's section cannot activate H3 Cast", request(refined={
        "sections": {"reference_sheet": "@anna waits"}})),
):
    compiled = succeeds(name, lambda data=data: compiler.compile_request(data))
    if compiled:
        check(name + " leaves no Cast", compiled.cast, [])
        check(name + " prunes owned picture", compiled.ref_images, [])

direct = succeeds("direct file citation survives an unused words-only owner",
                  lambda: compiler.compile_request(request("@img-1 is the reference.")))
if direct:
    check("direct citation does not activate its owner", direct.cast, [])
    check("direct citation keeps its saved rendition", direct.ref_images[0].mod_for("h3_video"),
          "refmod:cast/anna")

data = request("@anna walks.")
data["subjects"][0]["description"] = "a woman in a blue coat"
compiled = compiler.compile_request(data)
check("described words-only member remains usable", [s.handle for s in compiled.cast], ["anna"])
check("described words-only member still prunes their picture", compiled.ref_images, [])
data["subjects"][0]["wears"]["h3"]["send"] = "pictures"
compiled = compiler.compile_request(data)
check("cited pictures choice still drops H3's rendition", compiled.ref_images[0].mod_for("h3_video"), None)
check("cited pictures choice preserves other spaces", compiled.ref_images[0].mod_for("flux2"),
      "refmod:cast/anna.flux2")
check("compilation never mutates the saved input", data["assets"][0]["mods"], PHOTO["mods"])

data = request()
data["assets"].append({"handle": "img-2", "kind": "image", "role": "reference", "filename": "room.png"})
compiled = succeeds("pruning retains unrelated attached references",
                    lambda: compiler.compile_request(data))
if compiled:
    check("only the absent member's owned file is cut", [a.handle for a in compiled.ref_images], ["img-2"])

# A global citation reaches the per-shot compiler after timeline lifting, and
# another video family's words-only choice follows the same active-Cast rule.
global_piece = deepcopy(blobs["unusedWords"])
global_piece["prompt"] = "@anna walks."
refused("the piece's global prose activates the member too", lambda: first(global_piece))
data = request()
data["subjects"][0]["wears"] = {"ltx25": {"send": "words"}}
compiled = succeeds("an uncited LTX member also costs no shot anything",
                    lambda: compiler.compile_request(data, family="ltx25"))
if compiled:
    check("LTX ownership pruning is retained", compiled.ref_images, [])
data["prompt"] = "@anna walks."
refused("a cited LTX member retains words-only validation",
        lambda: compiler.compile_request(data, family="ltx25"))

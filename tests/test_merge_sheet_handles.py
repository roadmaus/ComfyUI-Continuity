"""Merged sheets keep unique handles and all aliases still cite their panels.

Pure compiler tests; filenames are declarative and no images/models are loaded.
"""

import layout
from harness import check

compiler = layout.load("compile").compile


def sheet(filename="sheet.png", handles=("img-1", "img-2")):
    return {"handle": "plate-1", "kind": "image", "role": "reference",
            "filename": filename, "cut": True,
            "panels": [{"handle": handles[0], "filename": "person.png",
                        "takes": "person", "cut": True, "rect": [0, 0, .5, 1]},
                       {"handle": handles[1], "filename": "room.png", "takes": "scene"}]}


def shot(asset, **rest):
    first, second = [p["handle"] for p in asset["panels"]]
    return {"duration_s": 3, "prompt": f"@{first} walks through @{second}.",
            "assets": [asset], **rest}


def merged(segments, **rest):
    payload = compiler.group_payload({"segments": segments, **rest})
    raw = payload["request"]["assets"]
    handles = [handle for asset in raw
               for handle in [asset["handle"], *[p["handle"] for p in asset.get("panels", [])]]]
    check("all merged owner/panel handles are unique", len(handles), len(set(handles)))
    compiled = compiler.compile_segment(payload)
    check("no unresolved asset citations remain", "@" in compiled.body, False)
    return payload, compiled


# The first sheet owner used to be renamed img-1 on top of its own img-1 panel.
original = sheet()
unmerged = compiler.compile_segment({"request": shot(original)})
payload, compiled = merged([shot(original), {"duration_s": 3, "prompt": "They turn."}])
check("one sheet remains one image", len(compiled.ref_images), 1)
check("source sheet was not mutated", original, sheet())
check("same panel metadata after renaming",
      [{k: v for k, v in p.items() if k != "handle"}
       for p in payload["request"]["assets"][0]["panels"]],
      [{k: v for k, v in p.items() if k != "handle"} for p in original["panels"]])
check("owner cut flag survives", payload["request"]["assets"][0]["cut"], True)
check("unmerged panel labels still exist", set(unmerged.labels), {"plate-1", "img-1", "img-2"})

# A noncolliding panel keeps its handle, preserving existing payloads/cache keys.
payload, _ = merged([shot(sheet(handles=("p-1", "p-2")))])
check("noncolliding panel names stay stable",
      [p["handle"] for p in payload["request"]["assets"][0]["panels"]], ["p-1", "p-2"])

# Different sheets can reuse card-local panel names without becoming duplicates.
payload, compiled = merged([shot(sheet("first.png", ("p-1", "p-2"))),
                            shot(sheet("second.png", ("p-1", "p-2")))])
check("distinct sheet files stay distinct", len(compiled.ref_images), 2)
for index, asset in enumerate(payload["request"]["assets"]):
    for panel in asset["panels"]:
        check(f"sheet {index} panel cited after merge",
              f"@{panel['handle']}" in payload["request"]["prompt"], True)
    first, second = [compiled.labels[p["handle"]] for p in asset["panels"]]
    check(f"shot {index} still cites its own panel pair",
          f"{first} walks through {second}" in compiled.body, True)

# The same sheet with different local aliases is one reference, but both shots
# must be rewritten to its retained panel names (not left citing the discarded alias).
payload, compiled = merged([shot(sheet(handles=("p-1", "p-2"))),
                            shot(sheet(handles=("q-1", "q-2")))])
check("same sheet is deduplicated", len(compiled.ref_images), 1)
check("discarded aliases are remapped", "@q-" in payload["request"]["prompt"], False)
check("both shots cite the retained first panel", payload["request"]["prompt"].count("@p-1"), 2)

for field in ("soundscape", "music"):
    payload, _ = merged([shot(sheet(handles=("p-1", "p-2")), **{field: "@p-1 sings."}),
                         shot(sheet(handles=("q-1", "q-2")), **{field: "@q-1 sings."})])
    check(f"{field} aliases agree after deduplication", payload["request"][field], "@p-1 sings.")

refined = shot(sheet())
refined["prompt"] = "unused typed prompt"
refined["refined"] = {"body": "@img-1 faces @img-2.", "enabled": True}
payload, compiled = merged([refined])
first, second = [compiled.labels[p["handle"]]
                 for p in payload["request"]["assets"][0]["panels"]]
check("refined body follows panel remapping", f"{first} faces {second}" in compiled.body, True)

# Same composite filename is not enough when its panel interpretation differs.
for field, value in (("takes", "object"), ("filename", "other-person.png"),
                     ("rect", [.5, 0, .5, 1]), ("cut", False)):
    different = sheet(handles=("q-1", "q-2"))
    different["panels"][0][field] = value
    payload, _ = merged([shot(sheet(handles=("p-1", "p-2"))), shot(different)])
    check(f"different panel {field} is not silently discarded", len(payload["request"]["assets"]), 2)

# Pool handles are reserved even when first cited after card-local allocations.
pooled = {"handle": "img-1", "kind": "image", "filename": "global.png"}
payload, _ = merged([shot(sheet(handles=("p-1", "p-2"))),
                     {"duration_s": 3, "prompt": "@img-1 remains."}], assets=[pooled])
check("a late pool citation keeps its global handle",
      next(a["handle"] for a in payload["request"]["assets"] if a["filename"] == "global.png"), "img-1")

pooled_sheet = sheet("global-sheet.png")
pooled_sheet["handle"] = "ref-1"
payload, _ = merged([shot(sheet("local-sheet.png", ("p-1", "p-2"))),
                     {"duration_s": 3, "prompt": "@ref-1 remains."}], assets=[pooled_sheet])
check("pool panel names are reserved as well",
      [p["handle"] for a in payload["request"]["assets"] if a["handle"] == "ref-1" for p in a["panels"]],
      ["img-1", "img-2"])

override = sheet("override.png")
override["handle"] = "ref-1"
payload, _ = merged([{"duration_s": 3, "prompt": "@ref-1 opens."},
                     shot(override)], assets=[pooled_sheet])
check("a card-local pool override keeps its different sheet",
      [a["filename"] for a in payload["request"]["assets"]], ["global-sheet.png", "override.png"])

# Reversing the order must not let an override steal a globally cited identity.
for later in ([], [{"duration_s": 3, "prompt": "@ref-1 remains the original."}]):
    payload, _ = merged([shot(override, prompt="@ref-1 is this card's override."), *later],
                         assets=[pooled_sheet], prompt="Global reference: @ref-1.")
    request = payload["request"]
    original = next(a for a in request["assets"] if a["filename"] == "global-sheet.png")
    changed = next(a for a in request["assets"] if a["filename"] == "override.png")
    check("global original keeps the reserved identity", original["handle"], "ref-1")
    check("earlier local override gets a distinct identity", changed["handle"] != "ref-1", True)
    check("global prose still names the original", "Global reference: @ref-1." in request["prompt"], True)
    check("card prose follows the override", f"@{changed['handle']} is this card's override." in request["prompt"], True)

other_pool = {"handle": "ref-2", "kind": "image", "filename": "other-global.png"}
payload, _ = merged([{"duration_s": 3, "prompt": "@ref-2 remains."}],
                     assets=[other_pool, pooled_sheet], prompt="@ref-1 is the global reference.")
check("ordinary pool ordering is unchanged", [a["handle"] for a in payload["request"]["assets"]],
      ["ref-2", "ref-1"])

ambiguous = sheet(handles=("anna", "p-2"))
ambiguous["handle"] = "ref-1"
for case in ({"assets": [ambiguous],
              "segments": [{"duration_s": 3, "prompt": "@ref-1 and @anna"}]},
             {"segments": [shot(sheet(handles=("p-1", "p-2"))),
                           shot(sheet(handles=("anna", "p-2")))]}):
    try:
        compiler.group_payload({**case, "subjects": [{"handle": "anna", "description": "a woman"}]})
    except compiler.CompileError as error:
        check("panel/cast collision is explained", "both a subject and an attached file" in str(error), True)
    else:
        check("panel/cast collision must fail safely even on dedup", True, False)

payload = compiler.group_payload({"segments": [shot(sheet(handles=("p-1", "p-2")))],
                                  "subjects": [{"handle": "img_1", "description": "a woman"}]})
check("valid subject IDs are not rewritten", payload["request"]["subjects"][0]["handle"], "img_1")

# A cast referring to a local sheet panel follows that panel's merged name too.
payload = compiler.group_payload({
    "segments": [shot(sheet(), prompt="@anna turns beside @img-2.")],
    "subjects": [{"handle": "anna", "from": ["img-1"],
                  "notes": {"img-1": "the face"}}]})
first_panel = payload["request"]["assets"][0]["panels"][0]["handle"]
check("cast source follows panel rename", payload["request"]["subjects"][0]["from"], [first_panel])
check("cast notes follow panel rename", payload["request"]["subjects"][0]["notes"], {first_panel: "the face"})

# LTX's shared payload/reference-plan boundary uses panel labels, not picture
# ordinals. Test that boundary without loading the optional plate renderer.
for segments in ([shot(sheet())], [shot(sheet(handles=("p-1", "p-2"))),
                                   shot(sheet(handles=("q-1", "q-2")))]):
    request = compiler.group_payload({"family": "ltx25", "segments": segments})["request"]
    assets = compiler._parse_assets(request["assets"])
    plan = compiler.plan_references(assets, [], [], compiler.grammar.of("ltx25"))
    body = compiler._substitute(request["prompt"], compiler._labels_from_plan(plan), assets)
    check("LTX aliases retain one sheet", len(assets), 1)
    check("LTX aliases still cite the same panel pair",
          body.count("panel 1 walks through panel 2"), len(segments))

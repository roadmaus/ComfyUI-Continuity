"""Krea 2's pictures in the chat room: the edit LoRA the turn needs is put on.

    python tests/test_chat_krea2edit.py

Krea 2 reads a picture only through one of the Krea 2 Edit V2 LoRAs, and the
room has no LoRA stack to hang one on. So the room reads the `loras` folder
(`chat.edit_adapters`) and puts on the one the turn's pictures want: General
Edit to change a picture cited plain, in place; Identity Edit to restage the
person in a cast member's picture or one cited :person, the scene first and
the person last. Every blob here is then compiled by the real Krea 2 compile,
so what the room builds is what the node would render.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import layout  # noqa: E402
from harness import FAILURES, check, passed  # noqa: E402

passed("the chat room wears the Krea 2 edit LoRA a turn's pictures need")

_pkg = layout.load("prompting", "chat", "compile", "compile_image", "krea2_still")
chat, ci, k2 = _pkg.chat, _pkg.compile_image, _pkg.krea2_still

# Krea 2 as its manifest serves it, from the module the manifest reads.
KREA2 = {
    "id": "krea2", "label": "Krea 2", "produces": ["still"], "weights": [],
    "canvas": {"aspects": {"16:9": 1.77, "1:1": 1.0}},
    "capabilities": {"refs": {
        "needs_lora": True, "edits_first": False,
        "edit": {"kinds": [list(pair) for pair in k2.EDIT_KINDS],
                 "legacy": k2.LEGACY_EDIT_LORA.pattern}}},
    "prompt": {"max_refs": k2.REFS_LIMIT},
}
EDIT = {"id": "qwenedit", "label": "Qwen Image Edit", "produces": ["still"], "weights": [],
        "capabilities": {"refs": {"needs_lora": False, "edits_first": True}},
        "prompt": {"max_refs": 3}}
CATALOG = {"families": [KREA2, EDIT]}

IDENTITY = "krea2_identity_edit_v2.safetensors"
GENERAL = "krea2_general_edit_v2.safetensors"
BOTH = ["style.safetensors", "krea2_general_edit_v2_r64.safetensors", GENERAL,
        IDENTITY, "krea2_identity_edit_v1_1.safetensors"]

LEDGER = [
    {"handle": "img-1", "kind": "still", "filename": "continuity/chat/her.png", "text": "a woman"},
    {"handle": "img-2", "kind": "still", "filename": "continuity/chat/cafe.png", "text": "a cafe"},
]
CAST = [{"name": "anna", "takes": "person", "from": ["img-1"], "description": "red coat"}]


def rail(loras, **extra):
    return {"still_family": "krea2", "still_arch": "krea2", "video_family": "h3",
            "aspect": "1:1", "still_edge": 1024,
            "still_pictures": chat.still_pictures(KREA2, CATALOG, loras), **extra}


def still(action, loras=BOTH, base=None, cast=()):
    action = chat.validate({"act": "render", "kind": "still", **action}, LEDGER,
                           cast=[m["name"] for m in cast])
    return chat.still_piece(action, LEDGER, rail(loras), base=base, cast=list(cast))


def compiled(blob):
    return ci.compile_prestage(blob, k2, lambda name: (1600, 900))


# ---- what is on the disk ------------------------------------------------------

check("each kind's file is found, the full-rank V2 one first and v1.1 never",
      chat.edit_adapters(KREA2, BOTH), {"general": GENERAL, "identity": IDENTITY})
check("...a rank-reduced cut where it is the only one",
      chat.edit_adapters(KREA2, ["krea2_general_edit_v2_r64.safetensors"]),
      {"general": "krea2_general_edit_v2_r64.safetensors"})
check("...and nothing on a family that reads its pictures itself",
      chat.edit_adapters(EDIT, BOTH), {})

pictures = chat.still_pictures(KREA2, CATALOG, BOTH)
check("with General Edit on disk a plain picture is changed on Krea 2 itself",
      {k: pictures[k] for k in ("takes", "native", "edits")},
      {"takes": True, "native": True, "edits": True})
only_identity = chat.still_pictures(KREA2, CATALOG, [IDENTITY])
check("with Identity Edit alone it restages people but changes no picture",
      {k: only_identity[k] for k in ("takes", "native", "edits")},
      {"takes": True, "native": False, "edits": False})
check("with neither, the answer it always gave",
      {k: chat.still_pictures(KREA2, CATALOG, [])[k] for k in ("takes", "native", "edits")},
      {"takes": True, "native": False, "edits": False})

# ---- where a still goes ---------------------------------------------------------

EDIT_RAIL = {"edit_family": "qwenedit", "edit_arch": "qwenedit"}


def where(action, loras, cast=()):
    action = chat.validate({"act": "render", "kind": "still", **action}, LEDGER,
                           cast=[m["name"] for m in cast])
    return chat.still_arch_for(action, LEDGER, rail(loras, **EDIT_RAIL), cast)


check("a picture to change stays on Krea 2 when General Edit is on disk",
      where({"prompt": "bluer", "from": ["img-1"]}, BOTH), "krea2")
check("...and goes to the edit family when only Identity Edit is",
      where({"prompt": "bluer", "from": ["img-1"]}, [IDENTITY]), "qwenedit")
check("a cast member stays on Krea 2 either way",
      where({"prompt": "@anna at dusk"}, [IDENTITY], CAST), "krea2")

# ---- the blob a turn becomes -------------------------------------------------------

changed = still({"prompt": "make the coat white", "from": ["img-1"]})
check("a picture cited plain is changed with General Edit, worn by the room",
      ([e["name"] for e in changed["loras"]], changed.get("ref_lora")), ([GENERAL], GENERAL))
check("...in place: first, on its own canvas",
      (changed.get(chat.EDIT_FIRST_FIELD), "aspect" in changed), (True, False))
payload = compiled(changed)
check("...which the Krea 2 compile reads as an edit of that picture",
      (payload.refs, payload.init), (["continuity/chat/her.png"],
                                     {"filename": "continuity/chat/her.png", "denoise": 1.0}))
check("...on the General Edit dials", k2.edit_dials(payload.schedule, payload.loras, 1),
      {"kind": "general", "boost": 4.0, "place": "aligned", "boost_a": 1.0, "place_a": "aligned"})

member = still({"prompt": "@anna reading in a cafe at night"}, cast=CAST)
check("a cast member is restaged with Identity Edit",
      ([e["name"] for e in member["loras"]], member.get("ref_lora"),
       chat.EDIT_FIRST_FIELD in member), ([IDENTITY], IDENTITY, False))
check("...drawn on the shape the room asked for", member.get("aspect"), "1:1")
check("...and compiles", compiled(member).refs, ["continuity/chat/her.png"])

scene = still({"prompt": "put @anna into @img-2", "from": ["img-2"]}, cast=CAST)
check("a cast member put into a scene: the scene first, the person last",
      [r["handle"] for r in scene["refs"]], ["img-2", "img-1"])
check("...with Identity Edit, not an edit of the scene",
      (scene.get("ref_lora"), chat.EDIT_FIRST_FIELD in scene), (IDENTITY, False))
pair = compiled(scene)
check("...on the composite dials", k2.edit_dials(pair.schedule, pair.loras, 2),
      {"kind": "identity", "boost": 2.5, "place": "beside", "boost_a": 1.0, "place_a": "aligned"})

cited = still({"prompt": "her on a beach", "from": ["img-2", "img-1:person"]})
check("a picture cited :person is the person, whatever order it was cited in",
      ([r["handle"] for r in cited["refs"]], cited.get("ref_lora")), (["img-2", "img-1"], IDENTITY))
check("Identity Edit alone restages, and the room says nothing of an edit",
      still({"prompt": "her on a beach", "from": ["img-1:person"]}, [IDENTITY]).get("ref_lora"),
      IDENTITY)

pinned = still({"prompt": "make the coat white", "from": ["img-1"]},
               base={"arch": "krea2", "loras": [{"name": IDENTITY, "strength": 1.0}]})
check("an edit LoRA already pinned is the one read, and none is added",
      ([e["name"] for e in pinned["loras"]], "ref_lora" in pinned,
       chat.EDIT_FIRST_FIELD in pinned), ([IDENTITY], False, False))
check("...which the compile accepts", compiled(pinned).arch, "krea2")

bare = still({"prompt": "a fox in the snow"})
check("a still with no pictures wears nothing",
      ([e["name"] for e in bare["loras"]], "ref_lora" in bare), ([], False))
check("...and nothing changes for a disk with no edit LoRA",
      [e["name"] for e in still({"prompt": "@anna at dusk"}, [], cast=CAST)["loras"]], [])

# ---- what the model is told -----------------------------------------------------------

card = chat.machine_card("krea2", "h3", CATALOG, {"by_folder": {}}, {}, loras=BOTH)
check("the card lets the model cite pictures, two of them",
      ('Up to 2 pictures may be cited' in card, "cannot be given" in card), (True, False))
check("...says the first plain one is changed",
      "The first is the picture being changed" in card, True)
check("...and how a person is restaged",
      "cited :person, or a cast member named, is put somewhere new" in card, True)
person_only = chat.machine_card("krea2", "h3", CATALOG, {"by_folder": {}}, {}, loras=[IDENTITY])
check("with Identity Edit alone it says a picture cannot be changed",
      ("cannot change a picture" in person_only, "put somewhere new" in person_only), (True, True))
check("with neither, the card it always printed",
      chat.machine_card("krea2", "h3", CATALOG, {"by_folder": {}}, {}, loras=[]),
      chat.machine_card("krea2", "h3", CATALOG, {"by_folder": {}}, {}))
check("the system prompt's edit block follows General Edit",
      (chat.changes_pictures(rail(BOTH)), chat.changes_pictures(rail([IDENTITY]))), (True, False))


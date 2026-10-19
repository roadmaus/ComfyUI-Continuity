"""The chat render route builds over the node on the canvas.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_chat_route.py

`tests/test_chat.py` pins the pure half — what a turn's action becomes over a
base blob. This is the route's half, which needs the node classes: that the
base the room sends is read and refused as it should be, that the node's own
widget values ride into the prompt over the family's defaults, and that a
render built for a clip carries the piece's sampler row, stack and turbo
switch rather than anything re-derived here. Nothing is queued and no model
folder has to hold a file: the listing and the machine's picks are stood in.

Skips itself with a message if ComfyUI cannot be imported.
"""

import asyncio
import importlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.basename(ROOT)

COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
BASE = os.environ.get("COMFYUI_BASE", COMFY)


def _boot():
    sys.path.insert(0, COMFY)
    sys.argv = ["main.py", "--base-directory", BASE]
    import nodes
    import server

    loop = asyncio.new_event_loop()
    try:
        # Core 2026-09 hands the server an asset manager; older cores take none.
        from app.assets.manager import default_asset_manager
        server.PromptServer(loop, default_asset_manager())
    except (ImportError, TypeError):
        server.PromptServer(loop)
    asyncio.set_event_loop(loop)
    loop.run_until_complete(nodes.init_extra_nodes(init_custom_nodes=False))

    sys.path.insert(0, os.path.dirname(ROOT))
    return nodes


try:
    _boot()
except Exception as exc:  # noqa: BLE001
    print(f"skipped: ComfyUI not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)

importlib.import_module(PACKAGE)
route = importlib.import_module(f"{PACKAGE}.creator.routes.chat")
chat = importlib.import_module(f"{PACKAGE}.creator.chat")
core_models = importlib.import_module(f"{PACKAGE}.creator.models")

from harness import FAILURES, check, passed


def refuses(label, call, *fragments):
    try:
        call()
    except chat.ActionError as problem:
        for fragment in fragments:
            if fragment not in str(problem):
                FAILURES.append(f"{label}: {str(problem)!r} does not mention {fragment!r}")
    else:
        FAILURES.append(f"{label}: did not refuse")


# ---- the base --------------------------------------------------------------

PIECE = {"version": 2, "prompt": "", "family": "h3", "models": {},
         "loras": [{"name": "h3_lightx2v.safetensors", "strength": 0.6, "enabled": True}],
         "turbo": {"on": True, "lora": "h3_lightx2v.safetensors"},
         "sampling": {"steps": 6, "cfg": 1.0, "sampler_name": "euler", "scheduler": "beta"},
         "segments": [{"prompt": "one"}, {"prompt": "two"}]}
PRE = {"version": 1, "arch": "krea2", "prompt": "", "init": None, "refs": [],
       "loras": [], "turbo": {}, "models": {"krea2": {}, "dtype": "default"},
       "sampling": {"steps": 8, "cfg": 1.0}}

check("a piece is read as sent", route._base({"piece": PIECE, "widgets": {"seed": 7}}, False),
      (PIECE, {"seed": 7}))
check("and a blob still as a string is parsed",
      route._base({"piece": json.dumps(PRE)}, True), (PRE, {}))
refuses("no base is refused, not defaulted", lambda: route._base(None, False), "no node")
refuses("a still over a piece is refused", lambda: route._base({"piece": PIECE}, True), "not a pre-stage")
refuses("a clip over a pre-stage is refused", lambda: route._base({"piece": PRE}, False), "not a piece")

check("the rail names the piece's family", route._families_of(PIECE, False), {"video_family": "h3"})
check("and the pre-stage's arch as its family", route._families_of(PRE, True), {"still_family": "krea2"})
refuses("a pre-stage on the H3 branch cannot draw the room's picture",
        lambda: route._families_of({**PRE, "arch": "minimax"}, True), "MiniMax H3", "image model")

# ---- the widgets ------------------------------------------------------------

node = route._nodes()["MiniMaxH3Creator"]
family = route.manifest.describe("h3")
defaults = route._node_widgets(node, family, {})
own = route._node_widgets(node, family, {"seed": 42, "steps": 6, "sampler_name": "euler",
                                          "control_after_generate": "fixed", "nonsense": 1,
                                          "cfg": ["not", "a", "number"]})
check("the node's own values ride over the family's",
      (own["seed"], own["steps"], own["sampler_name"]), (42, 6, "euler"))
check("a name the schema does not declare is dropped",
      ("nonsense" in own, "control_after_generate" in own), (False, False))
check("and a value of the wrong shape leaves the default standing", own["cfg"], defaults["cfg"])
check("nothing else moved", {k: v for k, v in own.items() if k not in ("seed", "steps", "sampler_name")},
      {k: v for k, v in defaults.items() if k not in ("seed", "steps", "sampler_name")})

# ---- the build, over a machine with every file --------------------------------

FILES = {
    "diffusion_models": ["h3_fl2va.safetensors", "h3_ref2va.safetensors"],
    "text_encoders": ["qwen3.safetensors"], "vae": ["video_vae.safetensors", "audio_vae.safetensors"],
    "loras": ["h3_lightx2v.safetensors"],
}
STORED = {"h3": {"fl2va": "h3_fl2va.safetensors", "ref2va": "h3_ref2va.safetensors",
                 "clip": "qwen3.safetensors", "vae": "video_vae.safetensors",
                 "audio_vae": "audio_vae.safetensors"}}
_real_available = core_models.available
core_models.available = lambda: {"by_folder": FILES, "files": {}, "installed": {}}
try:
    action = chat.validate({"act": "render", "kind": "video", "prompt": "a fox", "seconds": 4}, [])
    rail = route._rail({"aspect": "16:9", "video_edge": 768, "video_family": "h3"})
    built = route._build(action, [], rail, STORED, (PIECE, {"seed": 42, "steps": 20}))
finally:
    core_models.available = _real_available

if "problem" in built:
    FAILURES.append(f"the build over a full machine was refused: {built['problem']}")
else:
    inputs = built["prompt"][chat.NODE]["inputs"]
    blob = json.loads(inputs["creator_data"])
    check("the render is a one-node prompt for the Creator, under the chat's own id",
          (list(built["prompt"]), built["prompt"][chat.NODE]["class_type"]), ([chat.NODE], "MiniMaxH3Creator"))
    check("the seed is the node's widget", inputs["seed"], 42)
    check("the blob carries the piece's row, stack and switch",
          (blob["sampling"], blob["loras"], blob["turbo"]),
          (PIECE["sampling"], PIECE["loras"], PIECE["turbo"]))
    check("the strip became one card with the turn's prompt",
          [card["prompt"] for card in blob["segments"]], ["a fox"])
    check("the machine's picks filled the piece's empty weights",
          blob["models"]["fl2va"], "h3_fl2va.safetensors")
    check("and the piece handed back is the one queued", built["piece"], blob)

# A shot on the strip, with somebody on the piece's cast: the room's strip
# goes with the request, the cast is the node's own, and the dry run takes the
# piece they make — the kept shot held on its take, the new card continuing
# from it, the member and their shelf picture standing.
LEDGER = [{"handle": "ref-1", "kind": "image", "filename": "anna.png", "text": "anna.png"},
          {"handle": "vid-1", "kind": "clip", "filename": "one.mp4 [output]", "text": "one"}]
CAST_PIECE = {**PIECE,
              "subjects": [{"handle": "anna", "takes": "person", "from": ["ref-1"],
                            "description": "a red coat"}],
              "assets": [{"handle": "ref-1", "kind": "image", "role": "reference",
                          "filename": "anna.png"}]}
STRIP = [{"chat_handle": "vid-1", "prompt": "one", "assets": [], "loras": [], "duration_s": 4,
          "checkpoint": "auto", "hold": True,
          "take": {"filename": "one.mp4 [output]", "duration_s": 4, "width": 1280, "height": 720,
                   "has_audio": True}}]
CAST = chat.cast_entries(CAST_PIECE)
core_models.available = lambda: {"by_folder": FILES, "files": {}, "installed": {}}
try:
    action = chat.validate({"act": "render", "kind": "video", "prompt": "@anna turns away",
                            "after": "vid-1", "seconds": 4}, LEDGER, strip=["vid-1"], cast=["anna"])
    built = route._build(action, LEDGER, rail, STORED, (CAST_PIECE, {"seed": 1}), STRIP, CAST)
finally:
    core_models.available = _real_available
if "problem" in built:
    FAILURES.append(f"the strip build was refused: {built['problem']}")
else:
    blob = built["piece"]
    check("the kept shot is in front, held on its take, and the new card follows it",
          [(c.get("chat_handle"), c.get("hold"), c.get("continue")) for c in blob["segments"]],
          [("vid-1", True, None), (None, None, True)])
    check("the piece's cast stands",
          [(s["handle"], s["from"]) for s in blob["subjects"]], [("anna", ["ref-1"])])
    check("and her picture is on the piece's shelf",
          [a["handle"] for a in blob["assets"]], ["ref-1"])

# ---- a Krea 2 still with a picture ------------------------------------------
#
# Krea 2 reads a picture only through a Krea 2 Edit LoRA and the room has no
# stack, so the build reads the `loras` folder and wears the one the turn
# wants — here Identity Edit, for a cast member put into a scene picture.

KREA_FILES = {"diffusion_models": ["krea2_raw.safetensors"], "text_encoders": ["qwen3vl_4b.safetensors"],
              "vae": ["qwen_image_vae.safetensors"]}
KREA_STORED = {"krea2": {"model": "krea2_raw.safetensors", "clip": "qwen3vl_4b.safetensors",
                         "vae": "qwen_image_vae.safetensors"}}
KREA_LEDGER = [{"handle": "pic-1", "kind": "still", "filename": "anna.png", "text": "anna"},
               {"handle": "pic-2", "kind": "still", "filename": "cafe.png", "text": "a cafe"}]
KREA_CAST = [{"name": "anna", "takes": "person", "from": ["pic-1"], "description": "a red coat"}]
_real_loras = route._loras
core_models.available = lambda: {"by_folder": KREA_FILES, "files": {}, "installed": {}}
route._loras = lambda: ["krea2_identity_edit_v2.safetensors", "krea2_general_edit_v2.safetensors"]
try:
    rail = route._rail({"aspect": "1:1", "still_edge": 1024, "still_family": "krea2"})
    action = chat.validate({"act": "render", "kind": "still", "prompt": "put @anna into @pic-2",
                            "from": ["pic-2"]}, KREA_LEDGER, cast=["anna"])
    built = route._build(action, KREA_LEDGER, rail, KREA_STORED, (PRE, {"seed": 3}), cast=KREA_CAST)
    route._loras = lambda: []
    without = route._build(action, KREA_LEDGER, rail, KREA_STORED, (PRE, {"seed": 3}), cast=KREA_CAST)
finally:
    core_models.available = _real_available
    route._loras = _real_loras
if "problem" in built:
    FAILURES.append(f"the Krea 2 still with a picture was refused: {built['problem']}")
else:
    blob = built["piece"]
    check("a Krea 2 still with a picture wears Identity Edit, off the disk",
          ([e["name"] for e in blob["loras"]], blob.get("ref_lora")),
          (["krea2_identity_edit_v2.safetensors"], "krea2_identity_edit_v2.safetensors"))
    check("...the scene first and the person last",
          [r["filename"] for r in blob["refs"]], ["cafe.png", "anna.png"])
check("with no edit LoRA on disk the same turn is refused in the compile's words",
      "Krea 2 Edit LoRA" in (without.get("problem") or ""), True)

# ---- the magic prompt ---------------------------------------------------------
#
# The second generation a still on Ideogram gets when the room's switch is on.
# The backend is stood in: what is pinned is who is asked what, the one re-ask,
# and that the caption a turn wrote is what the render reads.

GOOD = json.dumps({"aspect_ratio": "16:9", "high_level_description": "A red fox.",
                   "compositional_deconstruction": {"background": "Snow.", "elements": [
                       {"type": "obj", "bbox": [1, 2, 3, 4], "desc": "Red fox."}]}})
asked = []


def stand_in(*replies):
    queue = list(replies)

    def ask(model, system, message, images, **kw):
        asked.append({"system": system, "message": message, **kw})
        return queue.pop(0)
    return lambda block: (ask, None)


IDEO_RAIL = route._rail({"still_family": "ideogram4", "aspect": "1:1"})
IDEO_RAIL = {**IDEO_RAIL, "still_pictures": {"takes": False, "refusal": "no"}}
MEMBER = [{"name": "anna", "takes": "person", "from": [], "description": "a red coat"}]
still_action = {**chat.validate({"act": "render", "kind": "still", "prompt": "@anna in snow"},
                                [], cast=["anna"]), "arch": "ideogram4"}
block = {"model": "m", "max_tokens": 4096}
_real_backend = route.refine_routes._backend
try:
    route.refine_routes._backend = stand_in("not json", GOOD)
    caption = route._magic(block, still_action, [], IDEO_RAIL, MEMBER)
    check("a still on Ideogram is captioned after one re-ask",
          (len(asked), json.loads(caption)["high_level_description"]), (2, "A red fox."))
    check("the magic prompt is the whole system prompt, and the member is words",
          (asked[0]["system"].startswith("You convert"),
           "User idea: a red coat in snow" in asked[0]["message"],
           "TARGET IMAGE ASPECT RATIO: 1:1" in asked[0]["message"]), (True, True, True))
    check("at the refiner's budget and upstream's temperature",
          (asked[0]["max_tokens"], asked[0]["temperature"]), (4096, 1.0))
    check("the re-ask says what was wrong, without the broken reply",
          ("held no JSON object" in asked[1]["message"], "not json" in asked[1]["message"]),
          (True, False))
    check("the boxes are dropped unless kept",
          "bbox" in caption, False)
    asked.clear()
    route.refine_routes._backend = stand_in(GOOD)
    check("and kept when the switch says so",
          "bbox" in route._magic({**block, "magic_bboxes": True}, still_action, [], IDEO_RAIL, MEMBER),
          True)
    asked.clear()
    route.refine_routes._backend = stand_in("no", '{"high_level_description": "a "bad" one"}')
    refuses("two failures refuse the turn, saying where the second broke",
            lambda: route._magic(block, still_action, [], IDEO_RAIL, MEMBER),
            "magic prompt", "did not parse", 'a "⟨HERE⟩bad')
    asked.clear()
    route.refine_routes._backend = stand_in()
    check("a still on a family with no magic prompt asks nothing",
          (route._magic(block, {**still_action, "arch": "krea2"}, [], IDEO_RAIL, MEMBER), asked),
          (None, []))
finally:
    route.refine_routes._backend = _real_backend

IDEO_PRE = {**PRE, "arch": "ideogram4", "models": {"ideogram4": {}, "dtype": "default"}}
carried = route._with_caption(still_action, GOOD, IDEO_PRE, True)
check("the render takes the turn's caption, tidied",
      carried["caption"].startswith('{"high_level_description"'), True)
check("an action with none is left as it was",
      route._with_caption(still_action, None, IDEO_PRE, True), still_action)
refuses("a caption over a base that reads prose is refused",
        lambda: route._with_caption(still_action, GOOD, PRE, True), "does not read one")
refuses("a caption that is not JSON is refused",
        lambda: route._with_caption(still_action, "a fox", IDEO_PRE, True), "not a JSON object")

# ---- a render asked for again -----------------------------------------------
#
# Retake and Try again replay an action the turn stamped. The arch on it is the
# rail's at that moment, and the pill may have moved since: a still made on
# Krea, the room switched to Qwen, Retake pressed, must draw on Qwen.

fox = chat.validate({"act": "render", "kind": "still", "prompt": "a fox"}, [])
on_krea = {**fox, "arch": "krea2"}
QWEN_RAIL = {**route._rail({"still_family": "qwen21"}), "edit_arch": None}
check("a stamp follows the rail, not the arch the action was made on",
      route._stamp({}, on_krea, [], QWEN_RAIL, [], held=on_krea)["arch"], "qwen21")
check("a clip is left as it was", route._stamp({}, {**fox, "kind": "video"}, [], QWEN_RAIL, []),
      {**fox, "kind": "video"})

captioned = {**still_action, "caption": GOOD}
magic_on = {**block, "magic": True}
IDEO_STAMP = {**IDEO_RAIL, "edit_arch": None}
try:
    route.refine_routes._backend = stand_in()
    check("the same arch keeps the caption it was written, asking nothing",
          (route._stamp(magic_on, captioned, [], IDEO_STAMP, MEMBER, held=captioned)["caption"], asked),
          (GOOD, []))
    check("moved off Ideogram, the caption is dropped",
          "caption" in route._stamp(magic_on, captioned, [], QWEN_RAIL, MEMBER, held=captioned), False)
    check("and with the switch off, too",
          "caption" in route._stamp(block, captioned, [], IDEO_STAMP, MEMBER, held=captioned), False)
    route.refine_routes._backend = stand_in(GOOD)
    moved = route._stamp(magic_on, {**still_action, "arch": "krea2"}, [], IDEO_STAMP, MEMBER,
                         held={**still_action, "arch": "krea2"})
    check("moved onto Ideogram with the switch on, a caption is written",
          (moved["arch"], len(asked), "caption" in moved), ("ideogram4", 1, True))
finally:
    route.refine_routes._backend = _real_backend
    asked.clear()

_real_stamp_rail = route._stamp_rail
route._stamp_rail = lambda block: (IDEO_STAMP, None)
try:
    body = {"action": {**fox, "arch": "krea2"}, "settings": magic_on, "ledger": [], "piece": {}}
    check("without the model, a caption owed is said rather than written",
          route._again(body, write=False), None)
    route._stamp_rail = lambda block: (QWEN_RAIL, None)
    check("and a stamp that owes none answers inline",
          route._again(body, write=False)["arch"], "qwen21")
    refuses("an action that renders nothing is refused",
            lambda: route._again({**body, "action": {"act": "say", "say": "hi"}}), "nothing to render")
finally:
    route._stamp_rail = _real_stamp_rail

passed("the chat render route builds over the node on the canvas")

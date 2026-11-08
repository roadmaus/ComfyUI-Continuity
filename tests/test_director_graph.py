"""Director's graph dry run: every clip of a planned piece, built and compiled
the way the run builds it, on each video family, without sampling.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_director_graph.py

`tests/test_director_replay.py` drives a run through a fake renderer. This one
keeps the fake queue and history but puts the run's real build in front of
it (`routes.director._build_step`): each step's action is held to
`chat.validate` against the run's ledger, strip and cast, patched into a
Creator piece over the room's base, and compiled as a dry run by
`chat_routes._build`, exactly as a clip the person typed would be. So a plan
whose second shot cannot continue from the first — a strip the run did not
keep, a citation the ledger does not hold, a length off the family's frame
grid — fails here, by name, instead of an hour into a render.

The machine is faked to have every file each family needs, as
`test_chat_route.py` fakes it; nothing is loaded and nothing samples.

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
        from app.assets.manager import default_asset_manager
        server.PromptServer(loop, default_asset_manager())
    except (ImportError, TypeError):
        server.PromptServer(loop)
    asyncio.set_event_loop(loop)
    loop.run_until_complete(nodes.init_extra_nodes(init_custom_nodes=False))
    sys.path.insert(0, os.path.dirname(ROOT))


try:
    _boot()
except Exception as exc:  # noqa: BLE001
    print(f"skipped: ComfyUI not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)

importlib.import_module(PACKAGE)
route = importlib.import_module(f"{PACKAGE}.creator.routes.director")
chat = importlib.import_module(f"{PACKAGE}.creator.chat")
director = importlib.import_module(f"{PACKAGE}.creator.director")
calls = importlib.import_module(f"{PACKAGE}.creator.director_calls")
run_mod = importlib.import_module(f"{PACKAGE}.creator.director_run")
core_models = importlib.import_module(f"{PACKAGE}.creator.models")
settings = importlib.import_module(f"{PACKAGE}.creator.settings")

from harness import FAILURES, check  # noqa: E402


def fence(obj):
    return "```json\n" + json.dumps(obj) + "\n```"


REPLIES = [
    fence({"questions": [], "assumptions": []}),
    fence({"title": "Night Train", "seconds": 24, "look": "sodium light, grain"}),
    fence({"beats": [{"text": "@george wakes in the carriage.", "weight": "short"},
                     {"text": "He passes the conductor and finds the cab empty.", "weight": "long"}]}),
    fence({"entities": [{"name": "carriage", "kind": "place", "description": "an old train carriage"},
                        {"name": "conductor", "kind": "person", "description": "a woman in a blue cap"}]}),
    fence({"shots": [{"action": "@george wakes up inside @carriage.", "continues": "new"}]}),
    fence({"shots": [{"action": "@george walks the length of @carriage past @conductor.", "continues": "pin"},
                     {"action": "@conductor opens the cab door: nobody.", "continues": "cut"}]}),
]

FILES = {
    "diffusion_models": ["h3_fl2va.safetensors", "h3_ref2va.safetensors", "ltx-2.5-distilled.safetensors"],
    "text_encoders": ["minimax_qwen3.safetensors", "gemma4-12b-with-proj.safetensors"],
    "vae": ["h3_video_vae.safetensors", "h3_audio_vae.safetensors",
            "ltx-2.5-video-vae.safetensors", "ltx-2.5-audio-vae.safetensors"],
}
STORED = {
    "h3": {"fl2va": "h3_fl2va.safetensors", "ref2va": "h3_ref2va.safetensors",
           "clip": "minimax_qwen3.safetensors", "vae": "h3_video_vae.safetensors",
           "audio_vae": "h3_audio_vae.safetensors"},
    "ltx25": {"dit": "ltx-2.5-distilled.safetensors", "clip": "gemma4-12b-with-proj.safetensors",
              "vae": "ltx-2.5-video-vae.safetensors", "audio_vae": "ltx-2.5-audio-vae.safetensors"},
}


# The approved pictures are real files: an opening frame decides the clip's
# canvas, so the compiler reads its size. Small, in a folder of their own
# under the output directory, and gone when the suite ends.
import shutil  # noqa: E402

import folder_paths  # noqa: E402
from PIL import Image  # noqa: E402

PICTURES = "continuity-director-dryrun"
PICTURE_DIR = os.path.join(folder_paths.get_output_directory(), PICTURES)


def picture(handle):
    os.makedirs(PICTURE_DIR, exist_ok=True)
    Image.new("RGB", (1280, 720), (40, 60, 80)).save(os.path.join(PICTURE_DIR, f"{handle}.png"))
    return f"{PICTURES}/{handle}.png [output]"


def prepared(family, keyframes):
    """The piece planned for a room on `family`, every prep row landed and
    approved, and the room's ledger and piece after the approvals: the
    conductor's sheet cast as a member, the carriage's a picture in the
    ledger."""
    rail = route.rail_of({"still_family": "krea2", "video_family": family, "aspect": "16:9"})
    replies = list(REPLIES)
    plan = calls.plan_piece("a 24 second piece: @george on a night train", rail,
                            lambda *_: replies.pop(0),
                            cast=[{"name": "george", "description": "a tall man"}],
                            keyframes=keyframes)["plan"]
    ledger, piece = [], {"subjects": [{"handle": "george", "takes": "person", "from": ["ref-1"],
                                       "description": "a tall man"}],
                         "assets": [{"handle": "ref-1", "kind": "image", "role": "reference",
                                     "filename": "george.png"}]}
    while director.prep_steps(plan):
        for row in director.prep_steps(plan):
            plan, mark = director.start(plan, row)
            handle = f"pic-{len(ledger) + 1}"
            ledger.append({"handle": handle, "kind": "still", "filename": picture(handle),
                           "text": row, "aspect": "16:9", "turn": 1})
            plan = director.approve(director.land(plan, row, handle, mark), row)
            entity = next((e for e in plan["entities"] if e["id"] == row), None)
            if entity and entity["kind"] == "person":
                piece["subjects"].append({"handle": entity["name"], "takes": "person", "from": [handle]})
                piece["assets"].append({"handle": handle, "kind": "image", "role": "reference",
                                        "filename": picture(handle)})
    return plan, ledger, piece


# What a family cannot render of this piece yet, and the words it says so in.
# LTX 2.5 reads one composite reference sheet, laid out in the picker, and a
# shot citing a person and a place sends it two pictures (spec §12.3). When
# the run learns to lay the sheet out, this entry goes and the family runs
# the whole piece like H3.
KNOWN = {"ltx25": "reads one reference image"}


class DryRun:
    """`drive`'s io with the run's real build in front of a fake queue."""

    def __init__(self):
        self.built, self.n = [], 0

    async def build(self, run, step):
        built = route._build_step(run, step)
        self.built.append((step, built))
        return built

    async def enqueue(self, _prompt):
        self.n += 1
        return f"p{self.n}"

    async def wait(self, _prompt_id):
        step, built = self.built[-1]
        segment = len(built["piece"]["segments"])
        return "landed", {chat.NODE: {
            "mmc_video": [{"filename": f"reel_{self.n}.mp4", "subfolder": "", "type": "output"}],
            "mmc_takes": [{"segment": segment, "filename": f"take_{self.n}.mp4", "subfolder": "",
                           "duration_s": step["action"]["seconds"], "width": 1280, "height": 720,
                           "has_audio": True}]}}

    def save(self, _run):
        pass

    def tell(self, *_):
        pass

    def stopping(self):
        return False


_available, _load = core_models.available, settings.load
core_models.available = lambda: {"by_folder": FILES, "files": {}, "installed": {}}
settings.load = lambda: {**_load(), "weights": STORED}
try:
    for family in ("h3", "ltx25"):
        for keyframes in (False, True):
            label = f"{family}, storyboard {'on' if keyframes else 'off'}"
            plan, ledger, piece = prepared(family, keyframes)
            todo = director.run_steps(plan)
            run = run_mod.begin("graph", plan, ledger=ledger, strip=[], piece=piece,
                                rail={"aspect": "16:9", "video_family": family, "seed_policy": "fixed"},
                                # The base as `chat.js renderBase` builds it: a blank
                                # piece of the room's family wearing the chat's cast.
                                base={"piece": {"version": 2, "family": family, "models": {},
                                                "loras": [], "segments": [],
                                                "subjects": piece["subjects"],
                                                "assets": piece["assets"]},
                                      "widgets": {"seed": 11}},
                                handles=[f"clip-{n}" for n in range(1, len(todo) + 1)])
            rehearsed = run_mod.rehearse(run, route._build_step)
            if family in KNOWN:
                check(f"{label}: Run refuses at the press, by name, before anything is queued",
                      bool(rehearsed) and KNOWN[family] in rehearsed, True)
                check(f"{label}: and the rehearsal spent nothing of the run", run["handles"][0], "clip-1")
                continue
            check(f"{label}: the rehearsal passes", rehearsed, None)
            io = DryRun()
            run = asyncio.run(run_mod.drive(run, io))
            check(f"{label}: every clip builds and compiles", (run["state"], run["error"]), ("done", None))
            blobs = [json.loads(b["prompt"][chat.NODE]["inputs"]["creator_data"])
                     for _s, b in io.built if "prompt" in b]
            check(f"{label}: each is a one-node Creator prompt on the room's family",
                  {(b["family"], next(iter(p["prompt"].values()))["class_type"])
                   for b, (_s, p) in zip(blobs, io.built)}, {(family, "MiniMaxH3Creator")})
            check(f"{label}: the clips chain on the strip, the kept shots held",
                  [[bool(c.get("hold")) for c in b["segments"]] for b in blobs],
                  [[False], [True, False], [True, True, False]])
            check(f"{label}: the pin carries on across its seam and the cut does not",
                  [b["segments"][-1].get("continue") for b in blobs], [None, True, None])
            check(f"{label}: the cut opens on its own frame only while the storyboard is on",
                  [a["role"] for a in blobs[2]["segments"][-1]["assets"] if a["role"] == "first_frame"],
                  ["first_frame"] if keyframes else [])
            check(f"{label}: the seed is the room's", {s["seed"] for s, _b in io.built}, {11})
            first = blobs[0]["segments"][0]["assets"]
            opens = [a["role"] for a in first if a["role"] == "first_frame"]
            check(f"{label}: the first shot opens on its frame only while the storyboard is on",
                  opens, ["first_frame"] if keyframes else [])
            check(f"{label}: the place rides as a scene reference",
                  [a.get("takes") for a in first if a["role"] == "reference"], ["scene"])
            check(f"{label}: the cast is the chat's, the conductor among them",
                  sorted(s["handle"] for s in blobs[-1]["subjects"]), ["conductor", "george"])
finally:
    core_models.available, settings.load = _available, _load
    shutil.rmtree(PICTURE_DIR, ignore_errors=True)

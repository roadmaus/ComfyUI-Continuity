"""What the refiner asks about, when the strip is passes rather than cards.

Refining is per card — the rewrite is stored on the card, and one card is what
the user pressed the button on — but a card's *request* is its pass's payload,
because a run of merged segments compiles to one generation. So the two lists
`_plan` walks have different lengths the moment anything is merged, and reading
one with the other's index is exactly the bug this pins: it raised IndexError on
the last card of any merged strip, and quietly handed the wrong pass's payload
to the cards before it.

    python tests/test_refine_plan.py

Runs standalone: no torch, no ComfyUI, no model. `media`, `preview`,
`refine_local` and `refine_skill` are stubs — nothing here reaches a file or a
sampler, and `_plan` is the whole of what is under test.
"""

import importlib.util
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    """`refine_routes`, with everything it imports for the model or the disk stubbed."""
    web = types.ModuleType("aiohttp.web")
    for name in ("get", "post", "json_response", "Response"):
        setattr(web, name, lambda *a, **k: None)
    aiohttp = types.ModuleType("aiohttp")
    aiohttp.web = web
    # The module registers its endpoints at import time, so the decorators have
    # to be there — they take a handler and are never called.
    def route(*a, **k):
        return lambda handler: handler

    server = types.ModuleType("server")
    server.PromptServer = types.SimpleNamespace(
        instance=types.SimpleNamespace(
            routes=types.SimpleNamespace(get=route, post=route)))
    sys.modules.setdefault("aiohttp", aiohttp)
    sys.modules.setdefault("aiohttp.web", web)
    sys.modules.setdefault("server", server)

    package = types.ModuleType("mmc")
    package.__path__ = [ROOT]
    sys.modules["mmc"] = package
    for name in ("canvas", "contextir", "compile", "refine"):
        spec = importlib.util.spec_from_file_location(
            f"mmc.{name}", os.path.join(ROOT, f"{name}.py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"mmc.{name}"] = module
        spec.loader.exec_module(module)
    for name in ("media", "preview", "refine_local", "refine_skill"):
        stub = types.ModuleType(f"mmc.{name}")
        sys.modules[f"mmc.{name}"] = stub
    # No attachments in any case below, so nothing asks a size of it; present
    # because `_plan` passes it into every compile.
    sys.modules["mmc.media"].image_size = None
    spec = importlib.util.spec_from_file_location(
        "mmc.refine_routes", os.path.join(ROOT, "refine_routes.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules["mmc.refine_routes"] = module
    spec.loader.exec_module(module)
    return module


routes = _load()
compiler = sys.modules["mmc.compile"]

from harness import FAILURES, check, passed


def strip(flags, render="chained", **extra):
    """A timeline blob: one card per merge flag, five seconds each."""
    return {
        "version": 2, "render": render, "prompt": "the piece", "aspect": "16:9",
        "segments": [
            {"prompt": f"shot {index + 1}", "duration_s": 5, "assets": [], "loras": [],
             **({"merge": True} if merge else {})}
            for index, merge in enumerate(flags)
        ],
        **extra,
    }


def plan(flags, kind="timeline", index=None, render="chained"):
    body = {"kind": kind, "data": strip(flags, render=render)}
    if index is not None:
        body["index"] = index
    mode, shots, images, piece, single, pool, footage, cast = routes._plan(body)
    return {"mode": mode, "shots": shots, "piece": piece, "single": single}


# ---- one shot per card, whatever the passes are ------------------------------
#
# The card is the unit of refining: three cards is three rewrites to write and
# three places to store them, and merging two of them changes which generation
# reads them, not how many there are to write.

for flags in ([False], [False, False, False], [False, True, False],
              [False, True, True], [False, False, True, False, True]):
    got = plan(flags)
    check(f"shots for {flags}", len(got["shots"]), len(flags))
    check(f"indices for {flags}", [s["index"] for s in got["shots"]],
          list(range(len(flags))))

# A strip saved before the merge flags existed is the one pass it was saved as,
# and still has one rewrite per card — the case that raised on card 2.
got = plan([False, False, False], render="single")
check("one-pass shots", len(got["shots"]), 3)
check("one-pass is single", got["single"], True)
check("merged strip is single", plan([False, True, True])["single"], True)
check("mixed strip is not single", plan([False, True, False])["single"], False)
check("chained strip is not single", plan([False, False])["single"], False)

# ---- a card's length is its own inside a pass -------------------------------
#
# A pass's compile is five seconds of one card or fifteen of three; either way
# what a card is worth is what the user gave it, and only a card that is its own
# generation takes the length that will actually be sampled.

check("merged card seconds", [s["seconds"] for s in plan([False, True, True])["shots"]],
      [5.0, 5.0, 5.0])
# Its own pass, so the compiled length: five seconds asked for is the frame
# count the sampler will actually run, said in seconds.
lone = plan([False, False])["shots"]
check("lone card seconds", [s["seconds"] for s in lone],
      [lone[0]["seconds"]] * 2)
check("lone card is the sampled length", 5.0 < lone[0]["seconds"] < 5.5, True)

# ---- the seam belongs to the card that opens the pass -----------------------
#
# `continues` says "this shot starts on the previous generation's last frame".
# Inside a run there is no such frame — the run is continuous — so it is the
# head of a pass, and only ever a head, that can carry it.

seamed = strip([False, True, False])
seamed["segments"][2]["continue"] = True
_, shots, _, _, _, _, _, _ = routes._plan({"kind": "timeline", "data": seamed})
check("seam on the pass head", [s["continues"] for s in shots], [False, False, True])

# The flag on a merged card describes a seam that no longer exists: it was
# merged away, and reporting it would tell the model to write a shot opening on
# a frame the sampler will never hand it.
inner = strip([False, True, True])
inner["segments"][1]["continue"] = True
_, shots, _, _, _, _, _, _ = routes._plan({"kind": "timeline", "data": inner})
check("no seam inside a pass", [s["continues"] for s in shots], [False, False, False])

# ---- one card at a time, at any index --------------------------------------
#
# The index is a card's, so every card is refinable alone however the strip is
# merged — including the ones past the end of the payload list, which is where
# this broke.

for flags in ([False, True, True], [False, False, True, False, True]):
    for index in range(len(flags)):
        got = plan(flags, kind="segment", index=index)
        check(f"segment {index} of {flags} shots", len(got["shots"]), 1)
        check(f"segment {index} of {flags} index", got["shots"][0]["index"], index)
        check(f"segment {index} of {flags} text",
              got["shots"][0]["text"], f"shot {index + 1}")

got = plan([False, False, True], render="single", kind="segment", index=2)
check("last card of a one-pass strip", got["shots"][0]["index"], 2)

# A card that is not there is still refused, and by number.
try:
    plan([False, True], kind="segment", index=5)
except Exception as exc:  # noqa: BLE001 — CompileError, without importing it
    check("no such segment", "there is no segment 6" in str(exc), True)
else:
    FAILURES.append("no such segment: did not raise")

# ---- the piece rides beside the shots, never joined into them ---------------
#
# The global prompt is handed over once; a shot's text stays the card's own so
# that the timeline's global box is still editing something after a refine.

got = plan([False, True, True])
check("piece", got["piece"], "the piece")
check("shot text is the card's", [s["text"] for s in got["shots"]],
      ["shot 1", "shot 2", "shot 3"])
check("mode", got["mode"], "T2VA")

# ---- the retired target, and who gets asked for cuts -------------------------
#
# `creator` was a lone generation's own refine target while a lone generation was
# its own node. A workflow saved then still posts under it, carrying a version-1
# blob, and it has to come back as the one card that blob now is.

legacy = {"kind": "creator", "data": {
    "version": 1, "prompt": "a lighthouse", "duration_s": 6,
    "aspect": "16:9", "short_edge": 768, "assets": [], "loras": [], "models": {}}}
mode, shots, _, piece, single, pool, footage, _ = routes._plan(routes._target(legacy))
check("a retired creator target is one card of a piece", len(shots), 1)
check("...carrying the blob's own prompt", shots[0]["text"], "a lighthouse")
# Empty rather than the shot's own sentence: on a lifted blob the prompt sits
# where a piece keeps its standing description, and reading it as both would hand
# the model the same text twice — once as what this card inherits and once as the
# card. `as_piece` puts it on the shot; `_plan` has to lift before it reads.
check("...with nothing above it to inherit from", piece, "")
check("...read as a segment", routes._target(legacy)["kind"], "segment")
check("...at index 0", routes._target(legacy)["index"], 0)
check("a target that was never the retired one is handed back as it is",
      routes._target({"kind": "timeline", "data": {}}), {"kind": "timeline", "data": {}})

# Who is asked to divide the clip into shots. It used to be "the Creator node",
# which was the same question only while a piece of one card could not exist
# under any other name. It is the card count now, so a one-card strip is asked
# too — it never was, and a twenty-second single card came back as one uncut
# shot for it.
check("a piece of one card has no cut times of its own",
      len(compiler.timeline_segments(strip([False]))), 1)
check("a piece of several already has them",
      len(compiler.timeline_segments(strip([False, True, True]))), 3)


passed("ok")

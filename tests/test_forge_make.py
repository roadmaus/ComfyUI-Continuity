"""Game Forge's make: a recipe as render requests, takes on disk, and the
renders collected back into the asset's masters.

Runs standalone — `python3 tests/test_forge_make.py` — with numpy and PIL but
no ComfyUI: the host is a stand-in that records each render request and, when
told to, writes the PNG the save node would have written where the request's
`output_prefix` says.

What is pinned is what an agent relies on: what each kind adds to the prompt
(the model sheet, the alpha sentence, the style pictures cited by number); a
kind or recipe that cannot be made is refused with a code before anything is
queued; a take waits while its render is on the queue, fails with the queue's
sentence, and otherwise becomes the masters at the recipe's size; and a recipe
edited while its render was out comes back stale.
"""

import importlib.util
import os
import re
import sys
import tempfile
import types

import numpy as np
from PIL import Image

import layout
from harness import FAILURES, check, passed

passed("all forge make tests passed")

package = types.ModuleType("forgepkg")
package.__path__ = [os.path.join(layout.PY_ROOT, "forge")]
sys.modules["forgepkg"] = package
for name in ("problems", "kinds", "targets", "style", "project", "manifest", "make", "api"):
    spec = importlib.util.spec_from_file_location(f"forgepkg.{name}",
                                                  os.path.join(layout.PY_ROOT, "forge", f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"forgepkg.{name}"] = module
    spec.loader.exec_module(module)
ForgeError = sys.modules["forgepkg.problems"].ForgeError
project = sys.modules["forgepkg.project"]
style = sys.modules["forgepkg.style"]
make = sys.modules["forgepkg.make"]
api = sys.modules["forgepkg.api"]

with open(os.path.join(layout.PY_ROOT, "outputs.py"), encoding="utf-8") as handle:
    shelf = re.search(r'^FORGE = "([^"]+)"', handle.read(), re.M).group(1)
check("make's shelf is outputs.FORGE", make.FORGE_SHELF, shelf)

ASPECTS = {"16:9": 16 / 9, "1:1": 1.0, "4:5": 4 / 5, "9:16": 9 / 16, "21:9": 21 / 9}


class Stand:
    """ComfyUI, as far as make can tell: a queue of prompt ids, and a save node
    that writes where it is told."""

    def __init__(self, base):
        self.base = base
        self.bodies = []
        self.states = {}
        self.refuse = None

    def render(self, body):
        if self.refuse:
            raise ForgeError(self.refuse, "make.refused")
        self.bodies.append(body)
        prompt_id = f"p{len(self.bodies)}"
        self.states[prompt_id] = ("queued", None)
        return {"prompt_id": prompt_id, "speed": "native"}

    def land(self, index, rgba):
        """Write render `index`'s picture as the save node would."""
        prefix = self.bodies[index]["output_prefix"]
        rel = prefix[len(make.FORGE_SHELF) + 1:]
        folder, stem = rel.rsplit("/", 1)
        where = os.path.join(self.base, folder)
        Image.fromarray(rgba, "RGBA").save(os.path.join(where, f"{stem}_00001_.png"))
        self.states[f"p{index + 1}"] = ("done", None)

    def host(self):
        families = lambda: [{"id": "qwen21", "still": True,
                             "canvas": {"aspects": ASPECTS, "min_short_edge": 512, "max_short_edge": 2048}},
                            {"id": "h3", "still": False}]
        return api.Host(self.base, families=families, render=self.render,
                        prompt_state=lambda pid: self.states.get(pid, ("unknown", None)))


def refused(label, fn, code):
    try:
        fn()
    except ForgeError as exc:
        check(f"{label}: code", exc.code, code)
        return exc
    FAILURES.append(f"{label}: was not refused")
    return None


def cutout(width, height):
    rgba = np.zeros((height, width, 4), np.uint8)
    rgba[height // 4:3 * height // 4, width // 4:3 * width // 4] = (200, 120, 40, 255)
    return rgba


base = tempfile.mkdtemp(prefix="forge-make-")
stand = Stand(base)
host = stand.host()
project.create(base, "keep", style={"clause": "Hand-painted, warm light", "seed": 7})
project.merge_plan(base, "keep", {"assets": [
    {"kind": "character", "name": "hero", "prompt": "a lantern-bearer in a green cloak"},
    {"kind": "background", "name": "hall", "prompt": "a vaulted stone hall", "size": [1920, 1080]},
    {"kind": "icon", "name": "potions", "prompt": "a glass potion bottle icon", "set": ["red-potion", "blue_potion"]},
    {"kind": "icon", "name": "chest", "prompt": "a wooden treasure chest", "size": [256, 320]},
    {"kind": "tile", "name": "grass", "prompt": "grass"},
    {"kind": "sprite", "name": "hero-walk", "of": "hero"},
    {"kind": "background", "name": "sky", "layers": 3},
]})
keep = project.load(base, "keep")
find = lambda name: project.find(keep, name)

# ---- the prompt each kind asks for ------------------------------------------------------

hero = make.plan(host, base, keep, find("hero"))
check("a character is one render", len(hero), 1)
words = hero[0]["body"]["prompt"]
check("a character is a model sheet", make.SHEET in words, True)
check("its words come first", words.startswith("a lantern-bearer in a green cloak."), True)
check("the style clause is in it", "Hand-painted, warm light." in words, True)
check("a character with alpha asks for it", words.endswith(make.ALPHA), True)
check("a square master is 1:1", hero[0]["body"]["aspect"], "1:1")
check("the seed is the asset's", hero[0]["body"]["seed"], style.seed(find("hero"), keep["style"]))
check("native unless asked", hero[0]["body"]["fast"], False)
check("a still", hero[0]["body"]["still"], True)

hall = make.plan(host, base, keep, find("hall"))[0]["body"]
check("a background has no alpha sentence", make.ALPHA in hall["prompt"], False)
check("a background is not a sheet", make.SHEET in hall["prompt"], False)
check("1920x1080 is 16:9", hall["aspect"], "16:9")
check("its short edge is its height", hall["short_edge"], 1080)

potions = make.plan(host, base, keep, find("potions"))
check("a set is one render per name", [r["stem"] for r in potions], ["01-red-potion", "02-blue_potion"])
check("each render names its item first", potions[1]["body"]["prompt"].startswith("blue potion. a glass potion"),
      True)
check("a set shares one seed", len({r["body"]["seed"] for r in potions}), 1)
check("a 256x320 master is the nearest aspect, 4:5",
      make.plan(host, base, keep, find("chest"))[0]["body"]["aspect"], "4:5")
check("a small master renders at the family's smallest edge",
      make.plan(host, base, keep, find("chest"))[0]["body"]["short_edge"], 512)

refused("a seamless tile", lambda: make.plan(host, base, keep, find("grass")), "make.seamless")
refused("a sprite", lambda: make.plan(host, base, keep, find("hero-walk")), "make.kind")
refused("a parallax stack", lambda: make.plan(host, base, keep, find("sky")), "make.layers")
refused("a video family", lambda: make.plan(host, base, keep, {**find("hero"), "family": "h3"}), "make.family")
refused("a family that is not here", lambda: make.plan(host, base, keep, {**find("hero"), "family": "nope"}),
        "make.family")

# References: the recipe's own first, so a prompt citing @pic-1 means its own;
# the style's after them, cited by the sentence make adds. A project file is
# named as ComfyUI's annotated output; anything else is an input name.
os.makedirs(os.path.join(base, "keep", "style"), exist_ok=True)
Image.fromarray(cutout(8, 8), "RGBA").save(os.path.join(base, "keep", "style", "look.png"))
project.set_style(base, "keep", {"references": ["style/look.png", "board.png"],
                                 "loras": [{"name": "painted.safetensors", "strength": 0.6}]})
keep = project.load(base, "keep")
body = make.plan(host, base, keep, {**find("hero"), "references": ["hero-face.png"]})[0]["body"]
check("pictures in order, all references",
      body["pictures"], [{"filename": "hero-face.png", "as": "ref"},
                         {"filename": "continuity/forge/keep/style/look.png [output]", "as": "ref"},
                         {"filename": "board.png", "as": "ref"}])
check("the style pictures are cited after the recipe's", "the art style of @pic-2 and @pic-3." in body["prompt"],
      True)
check("the style's LoRAs ride", body["loras"], [{"name": "painted.safetensors", "strength": 0.6}])
project.set_style(base, "keep", {"references": [], "loras": []})
keep = project.load(base, "keep")

# ---- start: what is queued, what is refused ---------------------------------------------

refused("nothing named", lambda: make.start(host, base, "keep"), "request.missing")
refused("a named asset that cannot be made queues nothing",
        lambda: make.start(host, base, "keep", ["hero", "grass"]), "make.seamless")
check("...and nothing was queued", stand.bodies, [])

dry = make.start(host, base, "keep", missing=True, dry_run=True)
check("a dry run queues nothing", stand.bodies, [])
check("a dry run says what it would queue", [t["asset"] for t in dry["takes"]], ["hero", "hall", "potions", "chest"])
check("missing skips what cannot be made, with codes",
      [(s["asset"], s["code"]) for s in dry["skipped"]],
      [("grass", "make.seamless"), ("hero-walk", "make.kind"), ("sky", "make.layers")])

answer = make.start(host, base, "keep", ["hero", "potions"])
check("two takes", [t["asset"] for t in answer["takes"]], ["hero", "potions"])
check("three renders", len(stand.bodies), 3)
hero_take = answer["takes"][0]
check("a render lands in its take",
      stand.bodies[0]["output_prefix"], f"continuity/forge/keep/takes/hero/{hero_take['take']}/hero")
refused("making it again while it is out", lambda: make.start(host, base, "keep", ["hero"]), "make.busy")
status = api.status(host, {"project": "keep"})
check("status says which take is out", {r["name"]: r["making"] for r in status["assets"]}["hero"],
      hero_take["take"])
check("...and it is still planned", {r["name"]: r["status"] for r in status["assets"]}["hero"], "planned")

# ---- collecting -------------------------------------------------------------------------

check("a queued render is waited for", api.jobs(host, {"project": "keep"})["takes"][0]["state"], "queued")
stand.land(0, cutout(1024, 1024))
jobs = {t["asset"]: t for t in api.jobs(host, {"project": "keep"})["takes"]}
check("a landed take is done", jobs["hero"]["state"], "done")
check("its masters", jobs["hero"]["masters"], ["hero.png"])
check("a set waits for every render", jobs["potions"]["state"], "queued")
rows = {r["name"]: r for r in api.status(host, {"project": "keep"})["assets"]}
check("the asset is made", rows["hero"]["status"], "made")
check("and no longer being made", rows["hero"]["making"], None)

stand.land(1, cutout(1024, 1024))
stand.land(2, cutout(1024, 1024))
jobs = {t["asset"]: t for t in api.jobs(host, {"project": "keep"})["takes"]}
check("a set's masters sort in its order", jobs["potions"]["masters"], ["01-red-potion.png", "02-blue_potion.png"])

# A recipe edited while its render is on the queue: the masters stand for the
# recipe the render was made from, so the asset comes back stale.
make.start(host, base, "keep", ["chest"])
project.edit_asset(base, "keep", "chest", {"prompt": "an iron-bound chest"})
stand.land(3, cutout(1024, 1280))
rows = {r["name"]: r for r in api.status(host, {"project": "keep"})["assets"]}
check("edited while out: stale", rows["chest"]["status"], "stale")
master = np.asarray(Image.open(os.path.join(base, "keep", "assets", "icon", "chest", "masters", "chest.png")))
check("a master is fitted to the recipe's size", master.shape, (320, 256, 4))
check("...with its alpha", int(master[..., 3].min()), 0)

# A background is cropped to its shape, not padded with nothing.
make.start(host, base, "keep", ["hall"])
stand.land(4, np.full((1088, 1920, 4), 255, np.uint8))
api.jobs(host, {"project": "keep"})
master = np.asarray(Image.open(os.path.join(base, "keep", "assets", "background", "hall", "masters", "hall.png")))
check("a scene is cropped to its size", master.shape, (1080, 1920, 4))

# An opaque picture where alpha was asked for lands, and says so.
make.start(host, base, "keep", ["hero"])
stand.land(5, np.full((1024, 1024, 4), 255, np.uint8))
take = api.jobs(host, {"project": "keep", "asset": "hero"})["takes"][-1]
check("an opaque render is a warning", [w["code"] for w in take["warnings"]], ["make.opaque"])

# The queue's own word on a failure is the take's.
make.start(host, base, "keep", ["hero"])
stand.states["p7"] = ("failed", "KSampler: out of memory")
take = api.jobs(host, {"project": "keep", "asset": "hero"})["takes"][-1]
check("a failed render fails the take", (take["state"], take["code"], take["problem"]),
      ("failed", "make.failed", "KSampler: out of memory"))

make.start(host, base, "keep", ["hero"])
stand.states["p8"] = ("unknown", None)
check("a render the queue forgot is lost", api.jobs(host, {"project": "keep", "asset": "hero"})["takes"][-1]["code"],
      "make.lost")

make.start(host, base, "keep", ["hero"])
stand.states["p9"] = ("done", None)
check("a render that finished elsewhere is astray",
      api.jobs(host, {"project": "keep", "asset": "hero"})["takes"][-1]["code"], "make.astray")

stand.refuse = "Qwen Image 2.1 is missing its VAE."
refusal = refused("the render route's refusal", lambda: make.start(host, base, "keep", ["hero"]), "make.refused")
check("...in its own words", refusal.problem if refusal else None, "Qwen Image 2.1 is missing its VAE.")
stand.refuse = None

refused("an unknown take", lambda: api.jobs(host, {"project": "keep", "takes": "nope"}), "take.missing")
check("takes by id", len(api.jobs(host, {"project": "keep", "takes": hero_take["take"]})["takes"]), 1)

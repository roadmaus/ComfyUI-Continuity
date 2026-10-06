"""Game Forge's check and exports, through the same handlers the routes serve.

    python3 tests/test_forge_export.py

A project is made on a temporary folder, masters imported from pictures drawn
here, and every v1 export (spec §9.1–9.5) written and read back: the Aseprite
JSON's frames, tags and pivot slice; Godot's `SpriteFrames` and `TileSet`;
Tiled's `.tsx` and `.tmj`; LÖVE's Lua table; and the Game Boy's indexed PNGs,
whose palette order and transparent index are what rgbgfx, png2asset and GB
Studio actually read. Then `check`'s codes and overlay, `sheet` marking an
asset looked at, and `status` moving from made to exported to stale.

Needs numpy and PIL; no ComfyUI.
"""

import importlib
import json
import os
import re
import sys
import tempfile
import types

import layout
from harness import FAILURES, check, skip

try:
    import numpy as np
    from PIL import Image
except ImportError:
    skip("numpy or PIL is not installed")

package = types.ModuleType("forgepkg")
package.__path__ = [os.path.join(layout.PY_ROOT, "forge")]
sys.modules["forgepkg"] = package
api = importlib.import_module("forgepkg.api")
targets = importlib.import_module("forgepkg.targets")

work = tempfile.mkdtemp(prefix="forge-export-")
base = os.path.join(work, "forge")
inputs = os.path.join(work, "input")
os.makedirs(inputs)
host = api.Host(base, lambda name: os.path.join(inputs, name))


def call(method, path, params, want=200):
    status, answer = api.call(host, method, api.PREFIX + path, params)
    if status != want:
        FAILURES.append(f"{method} {path}: status {status}, {answer}")
    return answer


def save(name, rgba):
    Image.fromarray(rgba, "RGBA").save(os.path.join(inputs, name))


def project_file(rel):
    return os.path.join(base, "game", *rel.split("/"))


# A walk: four figures on one 1024×256 sheet, each a little higher than the
# last, so the baseline has work to do. Red body, pale face, transparent air.
walk = np.zeros((256, 1024, 4), np.uint8)
for i in range(4):
    top = 40 + 6 * i
    walk[top:top + 180, i * 256 + 90:i * 256 + 166] = (200, 40, 40, 255)
    walk[top + 20:top + 40, i * 256 + 100:i * 256 + 156] = (250, 220, 180, 255)
save("walk.png", walk)
# A tileset of two tiles on one sheet: a flat dark tile and a checked one.
grass = np.zeros((512, 1024, 4), np.uint8)
grass[..., 3] = 255
grass[:, :512, :3] = (30, 60, 40)
grass[:, 512:, :3] = (230, 240, 210)
grass[::128, 512:, :3] = (30, 60, 40)
save("grass.png", grass)
# A scene: two flat bands, which pixelize into very few unique tiles.
scene = np.zeros((1080, 1920, 4), np.uint8)
scene[..., 3] = 255
scene[:540, :, :3] = (220, 240, 210)
scene[540:, :, :3] = (40, 80, 60)
save("scene.png", scene)
# An opaque picture for an asset that wants transparency.
save("box.png", np.full((64, 64, 4), 128, np.uint8) | np.array([0, 0, 0, 255], np.uint8))

every = ["generic", "godot4", "tiled", "love", "gb", "gbc", "gbstudio"]
call("POST", "/new", {"project": "game", "mode": "pixel", "targets": every})
call("POST", "/plan", {"project": "game", "plan": {"assets": [
    {"kind": "sprite", "name": "hero-walk", "frame": [16, 16],
     "animations": [{"name": "walk", "frames": 4, "fps": 8, "loop": True}]},
    {"kind": "tileset", "name": "grass", "tiles": ["ground", "checks"], "tile": [8, 8]},
    {"kind": "background", "name": "field"},
    {"kind": "icon", "name": "crate"},
    {"kind": "icon", "name": "later"},
]}})
call("POST", "/import", {"project": "game", "asset": "hero-walk", "files": ["walk.png"]})
call("POST", "/import", {"project": "game", "asset": "grass", "files": ["grass.png"]})
call("POST", "/import", {"project": "game", "asset": "field", "files": ["scene.png"]})
call("POST", "/import", {"project": "game", "asset": "crate", "files": ["box.png"]})

# ---- exports -----------------------------------------------------------------------

done = {t: call("POST", "/export", {"project": "game", "target": t}) for t in every}
generic = done["generic"]
check("a planned asset is skipped, with a code", [(s["asset"], s["code"]) for s in generic["skipped"]],
      [("crate", "matte.opaque"), ("later", "export.planned")])
check("generic writes a sheet and its JSON per asset", generic["written"], [
    "build/generic/hero-walk.png", "build/generic/hero-walk.json", "build/generic/grass.png",
    "build/generic/grass.json", "build/generic/field.png", "build/generic/field.json"])

sheet_json = json.load(open(project_file("build/generic/hero-walk.json")))
frames = sheet_json["frames"]
check("one Aseprite frame per frame", [f["filename"] for f in frames], ["walk_0", "walk_1", "walk_2", "walk_3"])
check("each at the frame size", {(f["frame"]["w"], f["frame"]["h"]) for f in frames}, {(16, 16)})
check("its duration from the animation's fps", {f["duration"] for f in frames}, {125})
check("the animation is a frame tag", sheet_json["meta"]["frameTags"],
      [{"name": "walk", "from": 0, "to": 3, "direction": "forward"}])
keys = sheet_json["meta"]["slices"][0]["keys"]
check("one pivot key for the animation", (len(keys), keys[0]["frame"]), (1, 0))
sheet = np.asarray(Image.open(project_file("build/generic/hero-walk.png")).convert("RGBA"))
check("the sheet's size is in the meta", (sheet.shape[1], sheet.shape[0]),
      (sheet_json["meta"]["size"]["w"], sheet_json["meta"]["size"]["h"]))
bottoms = []
for f in frames:
    r = f["frame"]
    cell = sheet[r["y"]:r["y"] + r["h"], r["x"]:r["x"] + r["w"]]
    bottoms.append(int(np.flatnonzero(cell[..., 3].any(1))[-1]))
check("every frame stands on one foot line", len(set(bottoms)), 1)
check("the pivot is on it", keys[0]["pivot"]["y"], bottoms[0] + 1)
colours = {tuple(c) for c in sheet[sheet[..., 3] > 0][:, :3].tolist()}
check("a pixel project's frames hold only palette colours", len(colours) <= 4, True)

tres = open(project_file("build/godot4/hero-walk.tres")).read()
check("Godot gets SpriteFrames", tres.startswith('[gd_resource type="SpriteFrames" load_steps=6 format=3]'), True)
check("pointing at its sheet beside it", '[ext_resource type="Texture2D" path="hero-walk.png" id="1_sheet"]' in tres,
      True)
check("one region per frame", len(re.findall(r"region = Rect2\(", tres)), 4)
check("and the animation's name and speed", ('"name": &"walk"' in tres, '"speed": 8.0' in tres), (True, True))
tileset = open(project_file("build/godot4/grass.tres")).read()
check("a tileset is a Godot TileSet", 'type="TileSetAtlasSource"' in tileset, True)
check("at the tile size", "texture_region_size = Vector2i(8, 8)" in tileset, True)
check("with every tile in it", re.findall(r"^\d+:\d+/0 = 0$", tileset, re.M), ["0:0/0 = 0", "1:0/0 = 0"])
check("its margins are the extrusion", "margins = Vector2i(1, 1)" in tileset, True)

tsx = open(project_file("build/tiled/grass.tsx")).read()
check("Tiled gets a tileset", 'tilewidth="8" tileheight="8"' in tsx and 'tilecount="2"' in tsx, True)
check("margin and spacing match the extruded sheet", ('margin="1"' in tsx, 'spacing="2"' in tsx), (True, True))
check("tiles carry their names", 'value="checks"' in tsx, True)
tmj = json.load(open(project_file("build/tiled/field.tmj")))
check("a background is a Tiled map of image layers", [l["type"] for l in tmj["layers"]], ["imagelayer"])
check("whose image is written beside it", os.path.isfile(project_file("build/tiled/" + tmj["layers"][0]["image"])),
      True)

lua = open(project_file("build/love/hero-walk.lua")).read()
check("LÖVE gets a Lua table", lua.rstrip().endswith("return sheet"), True)
check("with Lua's 1-based frames", '["walk"] = { from = 1, to = 4, fps = 8, loop = true }' in lua, True)
check("and a quads builder", "love.graphics.newQuad(f.x, f.y, f.w, f.h, sw, sh)" in lua, True)

gb = Image.open(project_file("build/gb/hero-walk.png"))
check("a Game Boy sprite is an indexed PNG", gb.mode, "P")
check("index 0 is its transparent colour", gb.info.get("transparency"), 0)
indices = np.asarray(gb)
check("three shades and transparent at most", int(indices.max()) <= 3, True)
check("frames in one strip", gb.size, (64, 16))
palette = gb.getpalette()[:12]
dmg = [c for h in targets.DMG_PALETTE for c in (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))]
check("its shades are light to dark, skipping the second-darkest", palette[3:], dmg[0:3] + dmg[3:6] + dmg[9:12])
field = Image.open(project_file("build/gb/field.png"))
check("a Game Boy background is indexed, four shades light to dark", (field.mode, field.getpalette()[:12]),
      ("P", dmg))
check("cut at a whole number of tiles", (field.size[0] % 8, field.size[1] % 8), (0, 0))
check("with no transparency", "transparency" in field.info, False)

studio = Image.open(project_file("build/gbstudio/assets/sprites/hero-walk.png"))
check("GB Studio sprites go to assets/sprites, keyed on its green",
      studio.getpalette()[:3], [0x65, 0xff, 0x00])
used = {tuple(studio.getpalette()[3 * i:3 * i + 3]) for i in np.unique(np.asarray(studio))}
allowed = {(0x65, 0xff, 0x00), (0xe0, 0xf8, 0xcf), (0x86, 0xc0, 0x6c), (0x07, 0x18, 0x21)}
check("and use only the colours GB Studio allows a sprite", used <= allowed, True)
check("backgrounds go to assets/backgrounds",
      os.path.isfile(project_file("build/gbstudio/assets/backgrounds/field.png")), True)
check("tilesets to assets/tilesets", os.path.isfile(project_file("build/gbstudio/assets/tilesets/grass.png")), True)

gbc = Image.open(project_file("build/gbc/field.png"))
rgb = gbc.getpalette()[:3 * len(np.unique(np.asarray(gbc)))]
check("Game Boy Color colours are already RGB555", all(round(round(v / 255 * 31) * 255 / 31) == v for v in rgb), True)

# ---- status follows the exports --------------------------------------------------

status = {row["name"]: row for row in call("GET", "/status", {"project": "game"})["assets"]}
check("exported to every target", status["hero-walk"]["status"], "exported")
check("an asset that could not be built is only made", status["crate"]["status"], "made")
call("POST", "/edit", {"project": "game", "asset": "hero-walk", "changes": {"frame": [16, 24]}})
status = {row["name"]: row for row in call("GET", "/status", {"project": "game"})["assets"]}
check("an edited recipe stales its export", status["hero-walk"]["status"], "stale")
check("and the manifest says so", "| stale |" in open(project_file("MANIFEST.md")).read(), True)

# ---- check -------------------------------------------------------------------------

# A sprite with four colours in one 8×8 tile breaks the three a sprite tile has.
# Not on a DMG, whose conversion only has three shades for sprites to begin
# with, but on a GBC, which quantises to the style's four.
loud = np.zeros((256, 256, 4), np.uint8)
loud[..., 3] = 255
for i, colour in enumerate([(250, 250, 250), (180, 180, 180), (90, 90, 90), (10, 10, 10)]):
    loud[:, i * 32:(i + 1) * 32, :3] = colour
loud[:4, :4, 3] = 0  # a sprite master has transparency, or the matte step refuses it
save("loud.png", loud)
call("POST", "/add", {"project": "game", "asset": {"kind": "sprite", "name": "loud", "frame": [8, 8]}})
call("POST", "/import", {"project": "game", "asset": "loud", "files": ["loud.png"]})
report = call("POST", "/check", {"project": "game", "target": "gbc", "assets": ["loud"]})
row = report["targets"][0]["assets"][0]
check("check names the code and the tile", [(p["code"], p.get("at")) for p in row["problems"]],
      [("budget.colours", [0, 0])])
check("counts what it found", report["count"], 1)
check("and draws it", row["overlay"], "build/gbc/check/loud.png")
on_dmg = call("POST", "/check", {"project": "game", "target": "gb", "assets": ["loud"]})
check("on a DMG the conversion already keeps it to three shades", on_dmg["count"], 0)
check("the overlay is there", os.path.isfile(project_file(row["overlay"])), True)
clean = call("POST", "/check", {"project": "game", "target": "godot4", "assets": ["loud"]})
check("the same sprite is fine for Godot", clean["count"], 0)
call("POST", "/check", {"project": "game", "target": "snes"}, want=400)

# ---- sheet and post ----------------------------------------------------------------

looked = call("POST", "/sheet", {"project": "game", "asset": "grass"})
check("a contact sheet has the masters and a row per target", looked["rows"], ["masters"] + every)
check("written under build/sheets", os.path.isfile(project_file(looked["path"])), True)
status = {row["name"]: row for row in call("GET", "/status", {"project": "game"})["assets"]}
check("looking at it counts as looking", status["grass"]["viewed"], True)

posted = call("POST", "/post", {"project": "game", "asset": "hero-walk", "steps": ["baseline"],
                                "target": "generic"})
check("post runs the steps named, and the conversion", posted["steps"], ["pixelize", "baseline"])
check("and keeps the frames as variants", posted["files"][0],
      "assets/sprite/hero-walk/variants/post/generic/walk_0.png")
call("POST", "/post", {"project": "game", "asset": "hero-walk", "steps": ["sharpen"]}, want=400)

tiny = np.zeros((8, 8, 4), np.uint8)
tiny[2:6, 2:6] = 255
save("tiny.png", tiny)
call("POST", "/add", {"project": "game", "asset": {"kind": "icon", "name": "tiny", "icon": [16, 16]}})
call("POST", "/import", {"project": "game", "asset": "tiny", "files": ["tiny.png"]})
refusal = call("POST", "/post", {"project": "game", "asset": "tiny", "steps": ["pixelize"]}, want=400)
check("a master smaller than its pixel size is refused, not upscaled", refusal.get("code"), "build.size")

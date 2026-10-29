"""Render modes and engine targets.

A **mode** is the look a project is made in, and it decides the post-chain an
asset gets when its recipe names none (spec §5.2, §6). A **target** is a
profile: an export writer, the limits to check against, and the conversions it
needs from the masters (§5.3). A target only ever reads masters; it never
changes one, which is what lets the same project export to Godot and to GB
Studio at once.

The limits are data, not code, so `check` can draw a violation with the number
that was broken and an agent can read the budget before it plans.
"""

from .problems import ForgeError

MODES = {
    "painted": {"help": "painted, soft edges, full colour",
                "chain": ["matte", "bleed", "baseline", "colormatch", "constraints", "atlas"]},
    "flat": {"help": "flat vector shapes, hard edges",
             "chain": ["matte", "bleed", "baseline", "colormatch", "constraints", "atlas"]},
    "toon": {"help": "cel-shaded, inked outlines",
             "chain": ["matte", "bleed", "baseline", "colormatch", "constraints", "atlas"]},
    "pixel": {"help": "pixel art on a grid and a palette, converted from a large master",
              "chain": ["matte", "baseline", "colormatch", "pixelize", "constraints", "atlas"]},
    "pbr": {"help": "physically based materials and textures for 3D",
            "chain": ["pbr", "constraints"]},
}

# Sounds get the audio chain whatever the project's look.
SOUND_CHAIN = ["trim", "loop", "loudness"]

TARGETS = {
    "generic": {
        "label": "Generic (PNG + Aseprite JSON)",
        "help": "a PNG sheet with Aseprite-format JSON: what Phaser, LÖVE, Unity importers and Godot plugins read",
        "limits": {"atlas": 2048},
    },
    "godot4": {
        "label": "Godot 4",
        "help": "SpriteFrames and TileSet .tres beside the PNGs",
        "limits": {"atlas": 2048},
    },
    "tiled": {
        "label": "Tiled",
        "help": "tilesets as .tsx and maps as .tmj",
        "limits": {"atlas": 2048},
    },
    "love": {
        "label": "LÖVE",
        "help": "the Aseprite JSON plus a Lua quads table",
        "limits": {"atlas": 2048},
    },
    "gb": {
        "label": "Game Boy (DMG)",
        "help": "indexed PNGs that png2asset and rgbgfx take as they are; 4 shades, 8×8 tiles",
        "pixel": True,
        "limits": {"screen": [160, 144], "tile": 8, "shades": 4, "sprite_colours": 3,
                   "sprite_sizes": [[8, 8], [8, 16]], "sprites": 40, "sprites_per_line": 10,
                   "bg_tiles": 256, "map_tiles": [32, 32], "flips": False},
    },
    "gbc": {
        "label": "Game Boy Color",
        "help": "indexed PNGs in RGB555; 8 background palettes of 4, 8 sprite palettes of 3 + transparent",
        "pixel": True,
        "limits": {"screen": [160, 144], "tile": 8, "shades": 4, "sprite_colours": 3,
                   "sprite_sizes": [[8, 8], [8, 16]], "sprites": 40, "sprites_per_line": 10,
                   "bg_tiles": 512, "bg_palettes": 8, "sprite_palettes": 8, "rgb555": True,
                   "map_tiles": [32, 32], "flips": True},
    },
    "gbstudio": {
        "label": "GB Studio",
        "help": "GB Studio's asset folders; about 192 unique background tiles a scene",
        "pixel": True,
        "limits": {"screen": [160, 144], "tile": 8, "shades": 4, "sprite_colours": 3,
                   "sprite_sizes": [[8, 8], [8, 16]], "sprites": 40, "sprites_per_line": 10,
                   "bg_tiles": 192, "map_tiles": [32, 32], "flips": False,
                   "max_size": 2040, "max_area": 1048320},
    },
    "gltf": {
        "label": "glTF / PBR",
        "help": "base colour sRGB, ORM linear, OpenGL normals; textured GLB",
        "limits": {"power_of_two": True, "padding": [2, 8], "texture": 8192},
        "switches": {"flavour": ["gltf", "unreal", "unity_hdrp", "godot"]},
    },
}

# How frames sit on a sheet, per target (§6.7): a one-pixel extrusion keeps a
# filtered sample at a frame's border from reading its neighbour. A Game Boy
# sheet has none, because its tiles must stay on the 8-pixel grid.
PACK = {"extrude": 1, "spacing": 0}
PACK_ON_GRID = {"extrude": 0, "spacing": 0}


def pack(target):
    return PACK_ON_GRID if "tile" in TARGETS[target]["limits"] else PACK


# GB Studio matches these four exactly, and keys sprite transparency on a fifth
# (gbstudio.dev, Assets → Backgrounds and Sprites). Its sprites cannot use the
# second-darkest shade.
GBSTUDIO_PALETTE = ["#e0f8cf", "#86c06c", "#306850", "#071821"]
GBSTUDIO_TRANSPARENT = "#65ff00"

# The Game Boy's four greens, light to dark — the default palette of a pixel
# project that targets one, and only a default: the style may name its own.
DMG_PALETTE = ["#e0f8d0", "#88c070", "#346856", "#081820"]


def require_mode(mode):
    if mode not in MODES:
        raise ForgeError(f"{mode!r} is not a render mode; the modes are " + ", ".join(MODES),
                         "project.mode", mode=mode)
    return MODES[mode]


def require_target(target):
    if target not in TARGETS:
        raise ForgeError(f"{target!r} is not a target; the targets are " + ", ".join(TARGETS),
                         "project.target", target=target)
    return TARGETS[target]


def chain(mode, recipe):
    """The post-steps an asset gets: its own list, else its mode's chain."""
    if recipe.get("post"):
        return list(recipe["post"])
    if recipe["kind"] == "sound":
        return list(SOUND_CHAIN)
    return list(MODES[mode]["chain"])


def catalogue():
    """Every mode and target, for `forge.py modes` / `targets`."""
    return {"modes": [{"id": key, **value} for key, value in MODES.items()],
            "targets": [{"id": key, **value} for key, value in TARGETS.items()]}

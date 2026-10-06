"""What an asset of each kind is.

An asset is a recipe plus the files it produced (spec §1). This module is the
recipe's shape: the fields every kind shares, the ones each kind adds, their
defaults and bounds. It is the single source for three things that must agree —
what `normalise` accepts, what `schema` prints for an agent (`forge.py schema
<kind>`, so no agent guesses a field name), and which fields count towards an
asset going stale.

A field is a small record rather than a JSON-schema document because the
validation and the schema are both generated from it; writing the schema by
hand would be a second copy to drift.
"""

import re

from .problems import ForgeError

_ANIMATION = re.compile(r"\A[A-Za-z0-9_-]{1,32}\Z")


class Field:
    """One recipe field.

    `type` is one of `str`, `int`, `float`, `bool`, `enum`, `size` (two
    positive ints, width and height), `point` (two numbers), `names` (a list
    of strings), `object` (a JSON object, passed through), `objects` (a list
    of them). `cost` is false for fields that do not change what is made —
    notes, export overrides — so editing them never marks an asset stale.
    """

    def __init__(self, name, type, default, help, choices=None, low=None, high=None, cost=True):
        self.name = name
        self.type = type
        self.default = default
        self.help = help
        self.choices = choices
        self.low = low
        self.high = high
        self.cost = cost

    def schema(self):
        base = {
            "str": {"type": "string"},
            "int": {"type": "integer"},
            "float": {"type": "number"},
            "bool": {"type": "boolean"},
            "enum": {"type": "string", "enum": list(self.choices or ())},
            "size": {"type": "array", "items": {"type": "integer", "minimum": 1},
                     "minItems": 2, "maxItems": 2},
            "point": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
            "names": {"type": "array", "items": {"type": "string"}},
            "object": {"type": "object"},
            "objects": {"type": "array", "items": {"type": "object"}},
        }[self.type]
        out = {**base, "description": self.help}
        if self.default is not None:
            out["default"] = self.default
        if self.low is not None:
            out["minimum"] = self.low
        if self.high is not None:
            out["maximum"] = self.high
        return out

    def clean(self, value, where):
        """`value` as this field holds it, or a ForgeError naming `where`."""
        def refuse(sentence):
            raise ForgeError(f"{where}: {self.name} {sentence}", "recipe.field",
                             field=self.name)

        kind = self.type
        if kind == "str":
            if not isinstance(value, str):
                refuse("must be text")
            return value.strip()
        if kind == "enum":
            if value not in self.choices:
                refuse("must be one of " + ", ".join(self.choices))
            return value
        if kind == "bool":
            if not isinstance(value, bool):
                refuse("must be true or false")
            return value
        if kind in ("int", "float"):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                refuse("must be a number")
            if kind == "int":
                if value != int(value):
                    refuse("must be a whole number")
                value = int(value)
            if self.low is not None and value < self.low:
                refuse(f"must be at least {self.low}")
            if self.high is not None and value > self.high:
                refuse(f"must be at most {self.high}")
            return value
        if kind in ("size", "point"):
            if (not isinstance(value, (list, tuple)) or len(value) != 2
                    or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in value)):
                refuse("must be two numbers, [x, y]")
            if kind == "size":
                if any(v != int(v) or v < 1 for v in value):
                    refuse("must be two whole numbers above zero, [width, height]")
                if self.high is not None and any(v > self.high for v in value):
                    refuse(f"must be at most {self.high} on each side")
                return [int(v) for v in value]
            return [float(v) if v != int(v) else int(v) for v in value]
        if kind == "names":
            if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
                refuse("must be a list of names")
            return [v.strip() for v in value if v.strip()]
        if kind == "object":
            if not isinstance(value, dict):
                refuse("must be an object")
            return value
        if kind == "objects":
            if not isinstance(value, list) or any(not isinstance(v, dict) for v in value):
                refuse("must be a list of objects")
            return value
        raise AssertionError(kind)


POST_STEPS = ("matte", "bleed", "baseline", "colormatch", "pixelize", "constraints", "atlas", "pbr",
              "trim", "loop", "loudness")

# What every asset has. `post` empty means "the render mode's chain" (§6);
# `seed` absent means the project's seed for this name, so it is fixed anyway.
COMMON = (
    Field("prompt", "str", "", "what to make, in plain words; the style clause is added after it"),
    Field("size", "size", None, "the master's size in pixels, [width, height]; the kind's default if left out",
          high=8192),
    Field("references", "names", [], "pictures this asset is made from, by name (project files or ComfyUI input/)"),
    Field("seed", "int", None, "fixed seed; derived from the project seed and the name if left out", low=0,
          high=2 ** 32 - 1),
    Field("family", "str", None, "the still family that makes it; the project's default if left out"),
    Field("post", "names", [], "post-steps in order; the render mode's chain if left empty"),
    Field("pivot", "point", None, "the anchor, as a fraction of the frame [x, y]; feet-centre if left out"),
    Field("layer", "int", 0, "depth order, back to front", low=-1000, high=1000),
    Field("alpha", "bool", True, "whether the master carries transparency; tiles, backgrounds and "
          "materials default to no"),
    Field("targets", "object", {}, "per-target overrides, {target: {...}}; export only", cost=False),
    Field("notes", "str", "", "anything a person or agent should know; never changes what is made", cost=False),
)

_SHEETS = ("grid", "row")

KINDS = {
    "character": {
        "help": "a model sheet and its variants: costumes, expressions, held items, directions",
        "size": [1024, 1024],
        "fields": (
            Field("costumes", "names", [], "costume variants, each an edit of the sheet"),
            Field("expressions", "names", [], "expression variants, face-only edits"),
            Field("items", "names", [], "held-item variants"),
            Field("directions", "int", 1, "facing directions: 1, 4 or 8", low=1, high=8),
        ),
    },
    "sprite": {
        "help": "animation frames for a character or object, generated together in one grid per animation",
        "size": [1024, 1024],
        "fields": (
            Field("of", "str", "", "the character asset this sprite animates, if any"),
            Field("frame", "size", [32, 32], "one frame's size at the target", high=1024),
            Field("animations", "objects", [], "[{name, frames, fps, loop}], e.g. walk, idle, attack"),
            Field("directions", "int", 1, "facing directions: 1, 4 or 8", low=1, high=8),
            Field("sheet", "enum", "grid", "how frames are laid out in the exported sheet", choices=_SHEETS),
        ),
    },
    "tile": {
        "help": "one seamless tile",
        "size": [1024, 1024],
        "alpha": False,
        "fields": (
            Field("tile", "size", [16, 16], "the tile's size at the target", high=1024),
            Field("seamless", "enum", "both", "which axes wrap", choices=("both", "x", "y", "none")),
        ),
    },
    "tileset": {
        "help": "a set of tiles that belong together: a terrain, a trim sheet, a wall set",
        "size": [1024, 1024],
        "alpha": False,
        "fields": (
            Field("tile", "size", [16, 16], "one tile's size at the target", high=1024),
            Field("tiles", "names", [], "the tiles, by name, in sheet order"),
            Field("terrain", "bool", False, "a terrain set: edges and corners between two grounds"),
            Field("seamless", "enum", "both", "which axes wrap", choices=("both", "x", "y", "none")),
        ),
    },
    "background": {
        "help": "a scene, optionally sliced into parallax layers by depth",
        "size": [1920, 1080],
        "alpha": False,
        "fields": (
            Field("layers", "int", 1, "parallax layers, back to front", low=1, high=12),
            Field("wrap", "bool", False, "whether the layers tile on x"),
        ),
    },
    "icon": {
        "help": "an icon or item, or a set of them generated together for a shared look",
        "size": [1024, 1024],
        "fields": (
            Field("icon", "size", [32, 32], "one icon's size at the target", high=1024),
            Field("set", "names", [], "the icons in the set, by name; one icon if empty"),
        ),
    },
    "ui": {
        "help": "a panel, button or frame",
        "size": [1024, 1024],
        "fields": (
            Field("nine_slice", "size", None, "border widths for 9-slice export, [horizontal, vertical]",
                  high=1024),
            Field("set", "names", [], "the pieces in the set, by name"),
        ),
    },
    "material": {
        "help": "a seamless PBR material: base colour, normal, height, roughness, metallic",
        "size": [1024, 1024],
        "alpha": False,
        "fields": (
            Field("texel_density", "float", None, "texels per metre; the project's if left out", low=1),
            Field("maps", "names", ["base", "normal", "height", "roughness", "metallic", "ao"],
                  "the maps to derive"),
        ),
    },
    "texture": {
        "help": "a texture for a 3D model that already has UVs",
        "size": [2048, 2048],
        "alpha": False,
        "fields": (
            Field("mesh", "str", "", "the mesh, a GLB or OBJ in the project or on the lift shelf"),
            Field("views", "int", 6, "cameras to generate from", low=4, high=8),
        ),
    },
    "sound": {
        "help": "a sound effect, ambience or music cue",
        "size": None,
        "fields": (
            Field("sound", "enum", "impact", "what kind of sound, which sets its defaults",
                  choices=("ui", "footstep", "impact", "ambience", "music", "bark", "foley")),
            Field("seconds", "float", None, "length; the sound kind's default if left out", low=0.05, high=600),
            Field("variations", "int", 1, "numbered variations to make", low=1, high=32),
            Field("loop", "bool", False, "whether it loops seamlessly"),
            Field("bars", "int", None, "music only: loop length in bars", low=1, high=256),
            Field("engine", "str", None, "the audio engine; the kind's default if left out"),
            Field("for", "str", "", "foley only: the sprite asset whose animation it scores"),
        ),
    },
}


def names():
    return list(KINDS)


def fields(kind):
    return COMMON + KINDS[kind]["fields"]


def require(kind):
    if kind not in KINDS:
        raise ForgeError(f"{kind!r} is not a kind of asset; the kinds are " + ", ".join(KINDS),
                         "asset.kind", kind=kind)
    return KINDS[kind]


def schema(kind):
    """A JSON schema for one kind's recipe, as `forge.py schema` prints it."""
    spec = require(kind)
    props = {"name": {"type": "string", "description": "the asset's name: lowercase letters, digits, - and _",
                      "pattern": "^[a-z0-9][a-z0-9_-]{0,63}$"},
             "kind": {"type": "string", "const": kind}}
    props.update({f.name: f.schema() for f in fields(kind)})
    if spec["size"]:
        props["size"]["default"] = spec["size"]
    props["alpha"]["default"] = spec.get("alpha", True)
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": f"forge {kind}", "description": spec["help"],
            "type": "object", "required": ["name", "kind"],
            "additionalProperties": False, "properties": props}


def normalise(entry, where=None):
    """A recipe as it is kept: every field present, defaults filled, bounds held.

    Unknown fields are refused rather than dropped — an agent that misspelt
    `frames` as `frame_count` must hear about it, not find the default.
    """
    if not isinstance(entry, dict):
        raise ForgeError("an asset must be a JSON object", "recipe.shape")
    kind = entry.get("kind")
    spec = require(kind)
    name = entry.get("name")
    where = where or f"{kind} {name!r}"
    known = {f.name: f for f in fields(kind)}
    unknown = sorted(set(entry) - set(known) - {"name", "kind"})
    if unknown:
        raise ForgeError(f"{where}: no field called {', '.join(unknown)} on a {kind} "
                         f"(see `forge.py schema {kind}`)", "recipe.unknown", fields=unknown)
    out = {"name": name, "kind": kind}
    for field in fields(kind):
        value = entry.get(field.name)
        if value is None:
            default = field.default
            if field.name in ("size", "alpha"):
                default = spec.get(field.name, default)
            out[field.name] = list(default) if isinstance(default, list) else (
                dict(default) if isinstance(default, dict) else default)
        else:
            out[field.name] = field.clean(value, where)
    if kind in ("character", "sprite") and out["directions"] not in (1, 4, 8):
        raise ForgeError(f"{where}: directions must be 1, 4 or 8", "recipe.field", field="directions")
    if kind == "sprite":
        for animation in out["animations"]:
            # The name becomes a frame tag in Aseprite JSON, a string in a Godot
            # .tres and a Lua key, and part of file names: held to a plain word so
            # no writer has to escape it.
            if not isinstance(animation.get("name"), str) or not _ANIMATION.match(animation["name"]):
                raise ForgeError(f"{where}: every animation needs a name of letters, digits, - and _ "
                                 "(at most 32)", "recipe.field", field="animations")
            fps = animation.get("fps", 12)
            if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not 1 <= fps <= 120:
                raise ForgeError(f"{where}: animation {animation['name']!r} needs an fps from 1 to 120",
                                 "recipe.field", field="animations")
            if not isinstance(animation.get("loop", True), bool):
                raise ForgeError(f"{where}: animation {animation['name']!r}: loop must be true or false",
                                 "recipe.field", field="animations")
            frames = animation.get("frames", 1)
            if isinstance(frames, bool) or not isinstance(frames, int) or not 1 <= frames <= 64:
                raise ForgeError(f"{where}: animation {animation['name']!r} needs 1 to 64 frames",
                                 "recipe.field", field="animations")
    return out


def costly(recipe):
    """The part of a recipe that decides what is made: what staleness is about."""
    free = {f.name for f in fields(recipe["kind"]) if not f.cost}
    return {k: v for k, v in recipe.items() if k not in free}

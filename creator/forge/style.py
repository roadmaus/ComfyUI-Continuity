"""What every asset in a project agrees on.

Not a prompt suffix (spec §5.2): a clause appended to every prompt — the
lua-25d-game skill's one fixed style paragraph — plus reference pictures, LoRAs,
a seed, and a render mode that brings its own settings (a grid and a palette for
`pixel`, a texel density for `pbr`).
"""

import re
import zlib

from . import targets
from .problems import ForgeError

_HEX = re.compile(r"\A#[0-9a-fA-F]{6}\Z")

DEFAULT = {
    "mode": "painted",
    "clause": "",
    "references": [],
    "loras": [],
    "seed": 1,
    "family": "qwen21",
    "palette": [],
    "grid": None,
    "texel_density": None,
}


def normalise(style, base=None):
    """`style` merged over `base` (the project's current style, or the default)
    and checked. Fields not given keep `base`'s value — `forge.py style` edits
    one thing at a time."""
    if not isinstance(style, dict):
        raise ForgeError("a style must be a JSON object", "style.shape")
    unknown = sorted(set(style) - set(DEFAULT))
    if unknown:
        raise ForgeError("no style field called " + ", ".join(unknown) + "; the fields are "
                         + ", ".join(DEFAULT), "style.unknown", fields=unknown)
    out = {**DEFAULT, **(base or {}), **style}
    targets.require_mode(out["mode"])
    if not isinstance(out["clause"], str):
        raise ForgeError("the style clause must be text", "style.field", field="clause")
    out["clause"] = out["clause"].strip()
    if not isinstance(out["references"], list) or any(not isinstance(r, str) for r in out["references"]):
        raise ForgeError("style references must be a list of picture names", "style.field", field="references")
    loras = []
    for lora in out["loras"] or []:
        if isinstance(lora, str):
            lora = {"name": lora, "strength": 1.0}
        if (not isinstance(lora, dict) or not isinstance(lora.get("name"), str)
                or isinstance(lora.get("strength", 1.0), bool)
                or not isinstance(lora.get("strength", 1.0), (int, float))):
            raise ForgeError("a style LoRA is a name, or {name, strength}", "style.field", field="loras")
        loras.append({"name": lora["name"], "strength": float(lora.get("strength", 1.0))})
    out["loras"] = loras
    seed = out["seed"]
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2 ** 32:
        raise ForgeError("the style seed must be a whole number from 0 to 2³²−1", "style.field", field="seed")
    if not isinstance(out["family"], str) or not out["family"]:
        raise ForgeError("the style family must name a still family", "style.field", field="family")
    palette = out["palette"] or []
    if not isinstance(palette, list) or any(not isinstance(c, str) or not _HEX.match(c) for c in palette):
        raise ForgeError("a palette is a list of colours written #rrggbb", "style.field", field="palette")
    if len(palette) > 256:
        raise ForgeError("a palette holds at most 256 colours", "style.field", field="palette")
    out["palette"] = [c.lower() for c in palette]
    grid = out["grid"]
    if grid is not None and (isinstance(grid, bool) or not isinstance(grid, int) or not 1 <= grid <= 256):
        raise ForgeError("the pixel grid is a whole number of master pixels per art pixel, 1 to 256",
                         "style.field", field="grid")
    density = out["texel_density"]
    if density is not None and (isinstance(density, bool) or not isinstance(density, (int, float))
                                or density <= 0):
        raise ForgeError("texel density is texels per metre, above zero", "style.field", field="texel_density")
    return out


def prompt(recipe, style):
    """The full prompt for an asset: its own words, then the style clause.

    The order is the skill's: what this thing is first, the paragraph every
    asset shares last, so a reader of the manifest sees the difference first.
    """
    words = recipe.get("prompt", "").strip().rstrip(".")
    clause = style.get("clause", "").strip()
    if words and clause:
        return f"{words}. {clause}"
    return words or clause


def seed(recipe, style):
    """An asset's seed: its own if it has one, else fixed from the project seed
    and its name — so an asset nobody gave a seed is still made the same way
    twice, and two assets do not share one by accident."""
    if recipe.get("seed") is not None:
        return recipe["seed"]
    return (style["seed"] * 2654435761 + zlib.crc32(recipe["name"].encode())) % 2 ** 32

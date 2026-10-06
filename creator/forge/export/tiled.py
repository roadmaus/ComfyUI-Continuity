"""Tiled: `.tsx` tilesets and `.tmj` maps (§3.7, §9.3).

A tile or tileset becomes a `.tsx` beside its PNG, each tile carrying its name
as a property. A background becomes a `.tmj` map of image layers, back to
front, with Tiled's parallax factors set so the far layers move least and a
wrapping background repeats on x. Other kinds get the generic PNG + Aseprite
JSON, which Tiled has no use for but the game does.

Margin and spacing are the sheet's extrusion, as `atlas.grid` lays it out:
margin `extrude`, spacing `2·extrude + spacing`.
"""

import json
from xml.sax.saxutils import quoteattr

from .. import project as projects
from . import aseprite

TILED_VERSION = "1.10"


def tsx(built, packed, image_name, extrude, spacing):
    height, width = built.frames[0].shape[:2]
    sheet_h, sheet_w = packed.sheet.shape[:2]
    columns = packed.columns or len(packed.rects)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             f'<tileset version="{TILED_VERSION}" name={quoteattr(built.recipe["name"])} '
             f'tilewidth="{width}" tileheight="{height}" spacing="{2 * extrude + spacing}" '
             f'margin="{extrude}" tilecount="{len(packed.rects)}" columns="{columns}">',
             f' <image source={quoteattr(image_name)} width="{sheet_w}" height="{sheet_h}"/>']
    for i, name in enumerate(built.names):
        lines += [f' <tile id="{i}">', "  <properties>",
                  f'   <property name="name" value={quoteattr(name)}/>', "  </properties>", " </tile>"]
    lines.append("</tileset>")
    return "\n".join(lines) + "\n"


def tmj(built, layer_files):
    """A map of image layers. Tiled wants a tile size even with no tile
    layers; 16 is a neutral one and the map is sized to cover the picture."""
    height, width = built.frames[0].shape[:2]
    tile = 16
    count = len(layer_files)
    layers = []
    for i, (name, filename) in enumerate(zip(built.names, layer_files)):
        factor = round((i + 1) / count, 3)
        layer = {"id": i + 1, "name": name, "type": "imagelayer", "image": filename,
                 "x": 0, "y": 0, "offsetx": 0, "offsety": 0, "opacity": 1, "visible": True,
                 "parallaxx": factor, "parallaxy": 1}
        if built.recipe.get("wrap"):
            layer["repeatx"] = True
        layers.append(layer)
    return {"type": "map", "version": TILED_VERSION, "orientation": "orthogonal",
            "renderorder": "right-down", "infinite": False,
            "width": -(-width // tile), "height": -(-height // tile), "tilewidth": tile, "tileheight": tile,
            "nextlayerid": count + 1, "nextobjectid": 1, "compressionlevel": -1,
            "layers": layers, "tilesets": []}


def write(project, built):
    from ..post import image
    from . import layout, tile_sheet

    kind = built.recipe["kind"]
    name = built.recipe["name"]
    if kind in ("tile", "tileset"):
        packed, pack = tile_sheet(built)
        if packed is None:
            return None
        return {f"{name}.png": image.png(packed.sheet),
                f"{name}.tsx": tsx(built, packed, f"{name}.png", pack["extrude"], pack["spacing"])}
    if kind == "background":
        out, layer_files = {}, []
        for i, (layer, frame) in enumerate(zip(built.names, built.frames)):
            filename = projects.safe_file(f"{name}_{i:02d}_{layer}") + ".png"
            out[filename] = image.png(frame)
            layer_files.append(filename)
        out[f"{name}.tmj"] = json.dumps(tmj(built, layer_files), indent=1) + "\n"
        return out
    packed = layout(built)
    return None if packed is None else aseprite.files(built, packed)

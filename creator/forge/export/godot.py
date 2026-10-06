"""Godot 4: `SpriteFrames` and `TileSet` as text resources (§3.7, §9.2).

Both are `.tres` text a person could write by hand, so they are written here
rather than through an engine. The texture is referenced by a path *relative
to the .tres* — Godot resolves a relative `ext_resource` path against the
resource's own folder — so the export folder can be dropped anywhere under
`res://` and still load.

A sprite gets a `SpriteFrames` (one animation per tag, speed from its fps);
a tile or tileset a `TileSet` with one atlas source whose margins and
separation are the sheet's extrusion. Every other kind, and every sprite
alongside its `.tres`, gets the generic PNG + Aseprite JSON, which carries
the pivots `SpriteFrames` has no place for.

Pixel art also wants nearest filtering and no mipmaps; in Godot 4 that is the
project's (or the node's) `texture_filter`, not something a resource can say.
"""

from . import aseprite


def _rect(x, y, w, h):
    return f"Rect2({x}, {y}, {w}, {h})"


def sprite_frames(built, packed, image_name):
    subs = []
    for i, (x, y, w, h) in enumerate(packed.rects):
        subs.append(f'[sub_resource type="AtlasTexture" id="AtlasTexture_{i}"]\n'
                    f'atlas = ExtResource("1_sheet")\nregion = {_rect(x, y, w, h)}\n')
    tags = built.tags or [{"name": "default", "from": 0, "to": len(packed.rects) - 1, "fps": 12, "loop": True}]
    animations = []
    for tag in tags:
        frames = ", ".join(f'{{\n"duration": 1.0,\n"texture": SubResource("AtlasTexture_{i}")\n}}'
                           for i in range(tag["from"], tag["to"] + 1))
        animations.append(f'{{\n"frames": [{frames}],\n"loop": {"true" if tag["loop"] else "false"},\n'
                          f'"name": &"{tag["name"]}",\n"speed": {float(tag["fps"])}\n}}')
    head = f'[gd_resource type="SpriteFrames" load_steps={2 + len(subs)} format=3]\n'
    ext = f'[ext_resource type="Texture2D" path="{image_name}" id="1_sheet"]\n'
    body = "[resource]\nanimations = [" + ", ".join(animations) + "]\n"
    return "\n".join([head, ext] + subs + [body])


def tile_set(built, packed, image_name, extrude, spacing):
    width, height = built.frames[0].shape[1], built.frames[0].shape[0]
    columns = packed.columns or len(packed.rects)
    cells = "\n".join(f"{i % columns}:{i // columns}/0 = 0" for i in range(len(packed.rects)))
    return (f'[gd_resource type="TileSet" load_steps=3 format=3]\n\n'
            f'[ext_resource type="Texture2D" path="{image_name}" id="1_sheet"]\n\n'
            f'[sub_resource type="TileSetAtlasSource" id="TileSetAtlasSource_0"]\n'
            f'texture = ExtResource("1_sheet")\n'
            f'margins = Vector2i({extrude}, {extrude})\n'
            f'separation = Vector2i({2 * extrude + spacing}, {2 * extrude + spacing})\n'
            f'texture_region_size = Vector2i({width}, {height})\n'
            f'{cells}\n\n'
            f'[resource]\n'
            f'tile_size = Vector2i({width}, {height})\n'
            f'sources/0 = SubResource("TileSetAtlasSource_0")\n')


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
                f"{name}.tres": tile_set(built, packed, f"{name}.png", pack["extrude"], pack["spacing"])}
    packed = layout(built)
    if packed is None:
        return None
    out = aseprite.files(built, packed)
    if kind == "sprite":
        out[f"{name}.tres"] = sprite_frames(built, packed, f"{name}.png")
    return out

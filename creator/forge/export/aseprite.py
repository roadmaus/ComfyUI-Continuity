"""PNG sheet + Aseprite JSON, and LÖVE's Lua table (§3.7, §9.1, §9.4).

Aseprite's "array" JSON is the one sprite-sheet format that Phaser, LÖVE
libraries, Unity importers and Godot plugins all read, so it is the generic
export and rides along with every other target's sheet. Animations are
`frameTags`; pivots are a `pivot` slice, keyed only on the frames where the
pivot changes, as Aseprite writes them.
"""

import json

from ..post import image


def sheet_json(built, packed, image_name):
    durations = built.durations()
    frames = []
    for name, (x, y, w, h), duration in zip(built.names, packed.rects, durations):
        frames.append({"filename": name, "frame": {"x": x, "y": y, "w": w, "h": h}, "rotated": False,
                       "trimmed": False, "spriteSourceSize": {"x": 0, "y": 0, "w": w, "h": h},
                       "sourceSize": {"w": w, "h": h}, "duration": duration})
    tags = []
    for tag in built.tags:
        entry = {"name": tag["name"], "from": tag["from"], "to": tag["to"], "direction": "forward"}
        if not tag["loop"]:
            entry["repeat"] = "1"
        tags.append(entry)
    keys, last = [], None
    for i, ((x, y), (_, _, w, h)) in enumerate(zip(built.pivots, packed.rects)):
        if (x, y, w, h) != last:
            keys.append({"frame": i, "bounds": {"x": 0, "y": 0, "w": w, "h": h}, "pivot": {"x": x, "y": y}})
            last = (x, y, w, h)
    height, width = packed.sheet.shape[:2]
    return {"frames": frames,
            "meta": {"app": "Continuity Game Forge", "version": "1", "image": image_name,
                     "format": "RGBA8888", "size": {"w": width, "h": height}, "scale": "1",
                     "frameTags": tags, "layers": [],
                     "slices": [{"name": "pivot", "color": "#0000ffff", "keys": keys}]}}


def files(built, packed):
    """`{name}.png` and `{name}.json`."""
    name = built.recipe["name"]
    data = sheet_json(built, packed, f"{name}.png")
    return {f"{name}.png": image.png(packed.sheet), f"{name}.json": json.dumps(data, indent=1) + "\n"}


def write_generic(project, built):
    from . import layout

    packed = layout(built)
    return None if packed is None else files(built, packed)


def _lua_string(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def lua(built, packed):
    name = built.recipe["name"]
    height, width = packed.sheet.shape[:2]
    lines = [f"-- {name}: written by Continuity's Game Forge from the project's masters.",
             "-- Regenerate it with an export rather than editing it.",
             "local sheet = {",
             f"  image = {_lua_string(name + '.png')}, width = {width}, height = {height},",
             "  frames = {"]
    for frame, (x, y, w, h), duration, (px, py) in zip(built.names, packed.rects, built.durations(),
                                                       built.pivots):
        lines.append(f"    {{ name = {_lua_string(frame)}, x = {x}, y = {y}, w = {w}, h = {h}, "
                     f"duration = {duration / 1000:g}, pivot = {{ {px}, {py} }} }},")
    lines += ["  },", "  animations = {"]
    for tag in built.tags:
        # Lua tables index from 1.
        lines.append(f"    [{_lua_string(tag['name'])}] = {{ from = {tag['from'] + 1}, to = {tag['to'] + 1}, "
                     f"fps = {tag['fps']:g}, loop = {'true' if tag['loop'] else 'false'} }},")
    lines += ["  },", "}", "",
              "-- One love.graphics.newQuad per frame, in frame order.",
              "function sheet.quads(image)",
              "  local quads, sw, sh = {}, image:getDimensions()",
              "  for i, f in ipairs(sheet.frames) do",
              "    quads[i] = love.graphics.newQuad(f.x, f.y, f.w, f.h, sw, sh)",
              "  end",
              "  return quads",
              "end",
              "",
              "return sheet", ""]
    return "\n".join(lines)


def write_love(project, built):
    from . import layout

    packed = layout(built)
    if packed is None:
        return None
    out = files(built, packed)
    out[f"{built.recipe['name']}.lua"] = lua(built, packed)
    return out

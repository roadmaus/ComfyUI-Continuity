#!/usr/bin/env python3
"""Draw a patch layout to a PNG, standard library only.

    python3 tools/render_layout.py shape.obj layout.json out.png [--view x,y,z] [--arms]

Triangles take their region's colour (non-disk regions are drawn striped
grey), edges between singularities are black, other separatrices
orange, repair traces purple, sharp edges dark blue, singularities green (+¼,
three separatrices) or red (−¼, five). `--arms` draws the cross field.
"""

import json
import math
import sys

from render import cross, dot, read_obj, sub, unit, write_png

PALETTE = [
    (141, 211, 199), (255, 255, 179), (190, 186, 218), (251, 128, 114), (128, 177, 211),
    (253, 180, 98), (179, 222, 105), (252, 205, 229), (217, 217, 217), (188, 128, 189),
    (204, 235, 197), (255, 237, 111), (166, 206, 227), (178, 223, 138), (251, 154, 153),
]


def main():
    obj, lay_path, dst = sys.argv[1], sys.argv[2], sys.argv[3]
    view = (0.55, -1.0, 0.65)
    if "--view" in sys.argv:
        view = tuple(float(x) for x in sys.argv[sys.argv.index("--view") + 1].split(","))
    arms = "--arms" in sys.argv
    size = 900
    verts, faces = read_obj(obj)
    with open(lay_path) as handle:
        lay = json.load(handle)
    region = lay["region"]

    forward = unit(view)
    right = unit(cross((0.0, 0.0, 1.0), forward))
    up = cross(forward, right)
    lo = [min(v[k] for v in verts) for k in range(3)]
    hi = [max(v[k] for v in verts) for k in range(3)]
    centre = tuple((lo[k] + hi[k]) / 2 for k in range(3))
    radius = max(math.dist(v, centre) for v in verts)
    scale = size * 0.46 / radius

    def project(p):
        d = sub(p, centre)
        return (size / 2 + dot(d, right) * scale, size / 2 - dot(d, up) * scale, dot(d, forward))

    # Which regions are disks, for colouring the rest as failures.
    from collections import defaultdict
    rv, re, rf = defaultdict(set), defaultdict(set), defaultdict(int)
    for f, face in enumerate(faces):
        r = region[f]
        rf[r] += 1
        for k in range(3):
            a, b = face[k], face[(k + 1) % 3]
            rv[r].add(a)
            re[r].add((min(a, b), max(a, b)))
    disk = {r: len(rv[r]) - len(re[r]) + rf[r] == 1 for r in rf}

    # Neighbouring regions never share a colour: greedy colouring of the
    # region adjacency, biggest regions first.
    owner = {}
    neighbours = defaultdict(set)
    for f, face in enumerate(faces):
        for k in range(3):
            e = (min(face[k], face[(k + 1) % 3]), max(face[k], face[(k + 1) % 3]))
            if e in owner and region[owner[e]] != region[f]:
                neighbours[region[f]].add(region[owner[e]])
                neighbours[region[owner[e]]].add(region[f])
            owner[e] = f
    colour_of = {}
    for r in sorted(rf, key=lambda r: -rf[r]):
        taken = {colour_of.get(o) for o in neighbours[r]}
        colour_of[r] = next(c for c in range(len(PALETTE) + 50) if c not in taken) % len(PALETTE)

    pixels = bytearray([250, 250, 248] * size * size)
    zbuf = [-1e30] * (size * size)
    light = unit((0.4, -0.6, 0.7))

    def put(x, y, c, z=None):
        if 0 <= x < size and 0 <= y < size:
            i = y * size + x
            if z is not None:
                if z < zbuf[i] - 1e-3 * scale:
                    return
            pixels[i * 3:i * 3 + 3] = bytes(c)

    for f, face in enumerate(faces):
        pts = [verts[i] for i in face]
        normal = unit(cross(sub(pts[1], pts[0]), sub(pts[2], pts[0])))
        if dot(normal, forward) <= 0:
            continue
        shade = 0.6 + 0.4 * max(0.0, dot(normal, light))
        r = region[f]
        base = PALETTE[colour_of[r]] if disk[r] else (150, 150, 150)
        colour = tuple(int(c * shade) for c in base)
        screen = [project(p) for p in pts]
        xs = [s[0] for s in screen]
        ys = [s[1] for s in screen]
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = screen
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(den) < 1e-12:
            continue
        for y in range(max(0, int(min(ys))), min(size - 1, int(max(ys)) + 1) + 1):
            for x in range(max(0, int(min(xs))), min(size - 1, int(max(xs)) + 1) + 1):
                px, py = x + 0.5, y + 0.5
                w0 = ((y1 - y2) * (px - x2) + (x2 - x1) * (py - y2)) / den
                w1 = ((y2 - y0) * (px - x2) + (x0 - x2) * (py - y2)) / den
                w2 = 1 - w0 - w1
                if w0 < 0 or w1 < 0 or w2 < 0:
                    continue
                z = w0 * z0 + w1 * z1 + w2 * z2
                i = y * size + x
                if z > zbuf[i]:
                    zbuf[i] = z
                    c = colour
                    if not disk[r] and (x + y) % 8 < 2:
                        c = (110, 110, 110)
                    pixels[i * 3:i * 3 + 3] = bytes(c)

    def visible(p):
        x, y, z = project(p)
        xi, yi = int(x), int(y)
        if not (0 <= xi < size and 0 <= yi < size):
            return False
        return z >= zbuf[yi * size + xi] - 0.02 * radius

    def line(a, b, c, width=1):
        pa, pb = project(a), project(b)
        steps = int(max(abs(pb[0] - pa[0]), abs(pb[1] - pa[1]))) + 1
        for s in range(steps + 1):
            t = s / steps
            p3 = tuple(a[k] + (b[k] - a[k]) * t for k in range(3))
            if not visible(p3):
                continue
            x, y = pa[0] + (pb[0] - pa[0]) * t, pa[1] + (pb[1] - pa[1]) * t
            for dx in range(-(width // 2), width // 2 + 1):
                for dy in range(-(width // 2), width // 2 + 1):
                    put(int(x) + dx, int(y) + dy, c)

    if arms:
        for p, a, b in lay["arms"]:
            L = radius * 0.012
            for v in (a, b):
                line(tuple(p[k] - v[k] * L for k in range(3)), tuple(p[k] + v[k] * L for k in range(3)), (90, 90, 90))
    for a, b in lay["features"]:
        line(a, b, (20, 40, 140), 2)
    # Edges (singularity to singularity) black, separatrices grown into the
    # layout dark orange, repair traces purple.
    kinds = lay.get("trace_kinds", ["edge"] * len(lay["traces"]))
    ink = {"edge": (0, 0, 0), "separatrix": (200, 90, 0), "repair": (120, 40, 160)}
    for trace, kind in zip(lay["traces"], kinds):
        for a, b in zip(trace, trace[1:]):
            line(a, b, ink.get(kind, (0, 0, 0)), 3)
    for x, y, z, index in lay["singularities"]:
        if visible((x, y, z)):
            sx, sy, _ = project((x, y, z))
            c = (20, 160, 60) if index > 0 else (210, 30, 30)
            for dx in range(-5, 6):
                for dy in range(-5, 6):
                    if dx * dx + dy * dy <= 25:
                        put(int(sx) + dx, int(sy) + dy, c)

    write_png(dst, size, size, pixels)


if __name__ == "__main__":
    main()

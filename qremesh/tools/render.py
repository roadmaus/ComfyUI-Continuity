#!/usr/bin/env python3
"""Draw an OBJ's polygons to a PNG, standard library only.

    python3 tools/render.py out/quads.obj out/quads.png [--view x,y,z]

Faces facing away are culled, the rest painted back to front: quads grey,
triangles orange, five- and six-sided faces red. Vertices whose valence is
not four get a blue dot, so singularities can be counted by eye.
"""

import math
import struct
import sys
import zlib


def read_obj(path):
    verts, faces = [], []
    with open(path) as handle:
        for line in handle:
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "v":
                verts.append(tuple(float(x) for x in parts[1:4]))
            elif parts[0] == "f":
                faces.append([int(p.split("/")[0]) - 1 for p in parts[1:]])
    return verts, faces


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def unit(a):
    n = math.sqrt(dot(a, a)) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)


def write_png(path, width, height, pixels):
    raw = b"".join(b"\x00" + bytes(pixels[y * width * 3:(y + 1) * width * 3]) for y in range(height))

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    with open(path, "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n")
        handle.write(chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)))
        handle.write(chunk(b"IDAT", zlib.compress(raw, 6)))
        handle.write(chunk(b"IEND", b""))


def main():
    src, dst = sys.argv[1], sys.argv[2]
    view = (0.35, -1.0, 0.45)
    if "--view" in sys.argv:
        view = tuple(float(x) for x in sys.argv[sys.argv.index("--view") + 1].split(","))
    size = 900
    verts, faces = read_obj(src)

    forward = unit(view)  # camera looks along -forward
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

    valence = {}
    for face in faces:
        for k in range(len(face)):
            a, b = face[k], face[(k + 1) % len(face)]
            edge = (min(a, b), max(a, b))
            valence.setdefault(edge, 0)
    degree = {}
    for a, b in valence:
        degree[a] = degree.get(a, 0) + 1
        degree[b] = degree.get(b, 0) + 1

    pixels = bytearray([250, 250, 248] * size * size)
    light = unit((0.4, -0.6, 0.7))
    drawn = []
    for face in faces:
        pts = [verts[i] for i in face]
        normal = (0.0, 0.0, 0.0)
        for k in range(len(pts)):
            normal = tuple(n + c for n, c in zip(normal, cross(pts[k], pts[(k + 1) % len(pts)])))
        normal = unit(normal)
        if dot(normal, forward) <= 0:
            continue
        shade = 0.55 + 0.45 * max(0.0, dot(normal, light))
        base = {4: (200, 200, 196), 3: (240, 150, 60)}.get(len(face), (220, 60, 60))
        colour = tuple(int(c * shade) for c in base)
        screen = [project(p) for p in pts]
        depth = sum(s[2] for s in screen) / len(screen)
        drawn.append((depth, screen, colour))
    drawn.sort(key=lambda d: d[0])

    def put(x, y, c):
        if 0 <= x < size and 0 <= y < size:
            i = (y * size + x) * 3
            pixels[i:i + 3] = bytes(c)

    def line(a, b, c):
        steps = int(max(abs(b[0] - a[0]), abs(b[1] - a[1]))) + 1
        for s in range(steps + 1):
            t = s / steps
            put(int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), c)

    for _, screen, colour in drawn:
        ys = [p[1] for p in screen]
        for y in range(max(0, int(min(ys))), min(size - 1, int(max(ys))) + 1):
            xs = []
            for k in range(len(screen)):
                (x0, y0), (x1, y1) = screen[k][:2], screen[(k + 1) % len(screen)][:2]
                if (y0 <= y + 0.5 < y1) or (y1 <= y + 0.5 < y0):
                    xs.append(x0 + (y + 0.5 - y0) * (x1 - x0) / (y1 - y0))
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                for x in range(max(0, int(xs[k])), min(size - 1, int(xs[k + 1])) + 1):
                    put(x, y, colour)
        for k in range(len(screen)):
            line(screen[k], screen[(k + 1) % len(screen)], (40, 40, 40))

    for i, d in degree.items():
        if d != 4:
            x, y, z = project(verts[i])
            if dot(sub(verts[i], centre), forward) > 0:
                for dx in range(-2, 3):
                    for dy in range(-2, 3):
                        put(int(x) + dx, int(y) + dy, (30, 90, 230))

    write_png(dst, size, size, pixels)


if __name__ == "__main__":
    main()

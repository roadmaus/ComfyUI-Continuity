"""A saved reference is read off its header, and compiles as an ordinary picture.

`creator/refmod.py` reads the sibling pack's safetensors format with the stdlib
alone, so this runs without torch or ComfyUI:

    python3 tests/test_refmod.py

Two claims. The reader accepts exactly the files the format describes — a
`latent` of `[1, 24, T, H, W]` under `refmod_meta` — and refuses, by name, the
ones it cannot use: a newer format version, an audio mod, an odd grid, a
metadata block that disagrees with the tensor. And `compile.py` treats a mod as
the reference it is: it takes a `<Picture N>` like a photograph, a cast member
can be built out of it, and the things a mod cannot do (be a keyframe, be
trimmed, be cut, carry a soundtrack) are refused with a sentence.
"""

import json
import os
import struct
import tempfile

import layout
from harness import FAILURES, check, passed

_pkg = layout.load("canvas", "h3_declare", "contextir", "subjects", "refmod", "compile",
                   package="mmc")
compiler, refmod = _pkg.compile, _pkg.refmod

ROOT = tempfile.mkdtemp(prefix="mmc-refmods-")


def write_mod(name, meta, shape=(1, 24, 1, 16, 16), key=refmod.META_KEY, dtype="F16"):
    """A safetensors file by hand: 8-byte header length, JSON table, zeros."""
    count = 1
    for dim in shape:
        count *= dim
    width = 2 if dtype == "F16" else 4
    table = {"latent": {"dtype": dtype, "shape": list(shape), "data_offsets": [0, count * width]}}
    if meta is not None:
        table["__metadata__"] = {key: json.dumps(meta)}
    body = json.dumps(table).encode("utf-8")
    path = os.path.join(ROOT, *name.split("/")) + refmod.EXT
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(struct.pack("<Q", len(body)))
        handle.write(body)
        handle.write(b"\0" * count * width)
    return path


def refused(label, fn, fragment):
    try:
        fn()
    except refmod.RefModError as exc:
        if fragment.lower() not in str(exc).lower():
            FAILURES.append(f"{label}: error {str(exc)!r} does not mention {fragment!r}")
    except Exception as exc:  # noqa: BLE001
        FAILURES.append(f"{label}: raised {type(exc).__name__} instead of RefModError: {exc}")
    else:
        FAILURES.append(f"{label}: expected a RefModError, got none")


# ---- names ----------------------------------------------------------------------

check("the scheme is recognised", refmod.is_mod("refmod:cast/anna"), True)
check("...and a picture is not a mod", refmod.is_mod("anna.png"), False)
check("a name loses its scheme", refmod.name_of("refmod:cast/anna"), "cast/anna")
check("...its extension", refmod.name_of("refmod:anna.safetensors"), "anna")
check("...and Windows separators", refmod.name_of("refmod:cast\\anna"), "cast/anna")
for bad in ("refmod:", "refmod:../anna", "refmod:cast/../../etc", "refmod:."):
    refused(f"{bad!r} is refused", lambda bad=bad: refmod.name_of(bad), "not a RefMod name")

# ---- the header --------------------------------------------------------------

good = write_mod("cast/anna", {"name": "anna", "kind": "image", "mode": "training",
                               "description": "a woman in a green coat",
                               "_format_version": 4})
meta = refmod.header(good)
check("an image mod reads", (meta["kind"], meta["latent_t"], meta["latent_h"], meta["latent_w"]),
      ("image", 1, 16, 16))
check("...with its token cost", meta["tokens"], 64)
check("...its mode", meta["mode"], "training")
check("...and its words", meta["description"], "a woman in a green coat")

clip = write_mod("walk", {"kind": "video", "mode": "encode"}, shape=(1, 24, 3, 32, 48))
meta = refmod.header(clip)
check("a video mod reads", (meta["kind"], meta["latent_t"], meta["tokens"]), ("video", 3, 3 * 16 * 24))
check("a mode alias is folded", refmod.header(write_mod("alias", {"kind": "image", "mode": "Full Reference"}))["mode"],
      "encode")
check("an old file with no version is version 1",
      refmod.header(write_mod("old", {"kind": "image"}))["format_version"], 1)

refused("a newer format is refused",
        lambda: refmod.header(write_mod("new", {"kind": "image", "_format_version": 5})), "newer")
refused("an audio mod is refused",
        lambda: refmod.header(write_mod("voice", {"kind": "audio"}, shape=(1, 32, 2, 40))), "audio")
refused("...under the sibling's audio key too",
        lambda: refmod.header(write_mod("voice2", {"kind": "audio"}, shape=(1, 32, 2, 40),
                                        key="audio_refmod_meta")), "audio")
refused("an odd grid is refused",
        lambda: refmod.header(write_mod("odd", {"kind": "image"}, shape=(1, 24, 1, 15, 16))), "not even")
refused("an image mod with several frames is refused",
        lambda: refmod.header(write_mod("multi", {"kind": "image"}, shape=(1, 24, 4, 16, 16))), "frames")
refused("a wrong channel count is refused",
        lambda: refmod.header(write_mod("chan", {"kind": "image"}, shape=(1, 16, 1, 16, 16))), "not [1, 24")
refused("a file with no metadata is refused",
        lambda: refmod.header(write_mod("bare", None)), "no RefMod metadata")
refused("a missing file is refused", lambda: refmod.header(os.path.join(ROOT, "nope.safetensors")), "nope")
with open(os.path.join(ROOT, "junk.safetensors"), "wb") as handle:
    handle.write(b"PNG\r\n\x1a\n" + b"\0" * 20)
refused("a file that is not safetensors is refused",
        lambda: refmod.header(os.path.join(ROOT, "junk.safetensors")), "not a safetensors")

# ---- the pooled grid -----------------------------------------------------------

check("a square source pools to the dial", refmod.grid_for(64, 64, 16), (16, 16))
check("a tall source keeps its aspect", refmod.grid_for(96, 64, 24), (24, 16))
check("a wide source keeps its aspect", refmod.grid_for(48, 96, 16), (8, 16))
check("...rounded to even", refmod.grid_for(90, 64, 16), (16, 12))
check("a grid never exceeds the source", refmod.grid_for(8, 8, 32), (8, 8))

# ---- compiling with one ----------------------------------------------------------


def build(prompt="", assets=(), **rest):
    data = {"prompt": prompt, "assets": list(assets), "duration_s": 6,
            "aspect": "16:9", "short_edge": 768}
    data.update(rest)
    return compiler.compile_request(data, image_size_lookup=lambda _f: (1500, 1000))


def expect_error(label, fn, fragment):
    try:
        fn()
    except compiler.CompileError as exc:
        if fragment.lower() not in str(exc).lower():
            FAILURES.append(f"{label}: error {str(exc)!r} does not mention {fragment!r}")
    except Exception as exc:  # noqa: BLE001
        FAILURES.append(f"{label}: raised {type(exc).__name__} instead of CompileError: {exc}")
    else:
        FAILURES.append(f"{label}: expected a CompileError, got none")


def mod(handle, kind="image", **rest):
    return {"handle": handle, "kind": kind, "role": "reference",
            "filename": f"refmod:cast/{handle}", **rest}


def picture(handle, **rest):
    return {"handle": handle, "kind": "image", "role": "reference",
            "filename": f"{handle}.png", **rest}


compiled = build("@img-1 and @img-2 walk in", [picture("img-1"), mod("img-2")])
check("a mod is a picture in the plan",
      [(step["op"], step["asset"].handle, step["label"]) for step in compiled.plan],
      [("image", "img-1", "<Picture 1>"), ("image", "img-2", "<Picture 2>")])
check("...and knows it is a mod", [a.mod for a in compiled.ref_images], [False, True])
check("a video mod is a video in the plan",
      [step["label"] for step in build("@vid-1", [mod("vid-1", "video")]).plan], ["<Video 1>"])
check("a video mod carries no soundtrack",
      build("@vid-1", [mod("vid-1", "video")]).ref_videos[0].track, "picture")

cast = build("@anna smiles", [mod("img-1")],
             subjects=[{"handle": "anna", "from": ["img-1"], "takes": "person"}])
check("a member can be built out of a mod",
      [s.sources for s in cast.cast], [("img-1",)])
check("...and their definition cites it",
      "<Subject 1> is the person in <Picture 1>" in cast.prompt, True)

expect_error("a mod cannot open a shot",
             lambda: build("", [dict(mod("img-1"), role="first_frame")]), "no frame to open")
expect_error("...or be a guide",
             lambda: build("", [dict(mod("vid-1", "video"), role="guide")]), "nothing to aim")
expect_error("a mod cannot be trimmed",
             lambda: build("@vid-1", [mod("vid-1", "video", trim={"start": 0, "end": 1})]), "trimmed")
expect_error("...or cut", lambda: build("@img-1", [mod("img-1", cut=True)]), "already encoded")
expect_error("...or lend a soundtrack",
             lambda: build("@vid-1", [mod("vid-1", "video", track="picture+sound")]), "no soundtrack")
expect_error("an audio mod is refused",
             lambda: build("@aud-1", [mod("aud-1", "audio")]), "audio RefMod")
expect_error("a bad name is refused",
             lambda: build("@img-1", [{"handle": "img-1", "kind": "image", "role": "reference",
                                       "filename": "refmod:../x"}]), "not a RefMod name")

# ---- the file itself ---------------------------------------------------------------
#
# Rename, delete, describe and adopt work through `folder_paths` for the roots,
# so a stub answering with ROOT stands in for ComfyUI here.

import sys
import types

_fp = types.ModuleType("folder_paths")
_fp.models_dir = ROOT
_fp.add_model_folder_path = lambda *_a, **_k: None
_fp.get_folder_paths = lambda _name: [ROOT]
_fp.is_within_directory = lambda root, path: os.path.realpath(path).startswith(os.path.realpath(root))
sys.modules["folder_paths"] = _fp

_moved_src = write_mod("cast/mover", {"kind": "image", "mode": "training", "description": "before"})
with open(os.path.splitext(_moved_src)[0] + ".png", "wb") as _h:
    _h.write(b"png")
_new = refmod.move("refmod:cast/mover", "people/moved")
check("a mod moves with its picture",
      (os.path.isfile(_new), os.path.isfile(os.path.splitext(_new)[0] + ".png"),
       os.path.isfile(_moved_src)), (True, True, False))
check("...and the row says where it is", refmod.row_for(_new, "people/moved")["subfolder"], "people")
write_mod("people/taken", {"kind": "image"})
refused("a move never overwrites", lambda: refmod.move("refmod:people/moved", "people/taken"), "already there")

refmod.rewrite_meta(_new, description="after")
_meta = refmod.header(_new)
check("the description is rewritten in place", _meta["description"], "after")
check("...and the tensor still reads", (_meta["tokens"], _meta["kind"]), (64, "image"))
with open(_new, "rb") as _h:
    (_len,) = struct.unpack("<Q", _h.read(8))
check("...with the header padded to eight", _len % 8, 0)

_tmp = write_mod("_incoming", {"kind": "image", "mode": "encode"})
_adopted, _ = refmod.adopt(_tmp, "cast/adopted")
check("an upload is adopted under its name", os.path.isfile(_adopted) and not os.path.exists(_tmp), True)
_junk = os.path.join(ROOT, "junk.tmp")
with open(_junk, "wb") as _h:
    _h.write(b"not a safetensors file at all")
refused("...and a file that is not a mod is refused", lambda: refmod.adopt(_junk, "cast/junk"), "safetensors")
check("...and deleted", os.path.exists(_junk), False)

refmod.remove("refmod:people/moved")
check("a deleted mod is gone with its picture",
      (os.path.exists(_new), os.path.exists(os.path.splitext(_new)[0] + ".png")), (False, False))
check("a foreign mod is marked", refmod.row_for(_adopted, "cast/adopted")["foreign"], True)

passed("all RefMod contract tests passed")

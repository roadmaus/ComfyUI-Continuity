"""Can this file's own header say whether it has a vision tower in it?

Runs standalone — `python tests/test_visionweights.py` — with no torch and no
ComfyUI, which is the property `visionweights.py` is written to keep.

What is worth pinning here is the three-valued answer. `True` and `False` are
the easy half. `None` is the one a caller can get wrong: it means *the file did
not say*, and a caller that folds it into `False` grounds renders over an
unreadable byte instead of over a real mistake. So every way of not knowing —
a missing file, a pickle, a truncated header — is checked to come back `None`
and not `False`.

Both containers are built here rather than fixtured, because the point of the
module is that it reads the real layouts: a safetensors header is a JSON blob
behind a length field, and a GGUF tensor table sits behind a metadata block that
has to be walked because it is variable-width.
"""

import json
import os
import struct
import tempfile

import layout

from harness import FAILURES, check

visionweights = layout.load("visionweights").visionweights

WORK = tempfile.mkdtemp(prefix="mmc-vision-")


def path(name):
    return os.path.join(WORK, name)


# ---- fixtures ---------------------------------------------------------------

def safetensors(name, keys, junk=None):
    """A file with a real safetensors header and no tensor data behind it —
    nothing here reads past the header, which is the whole point."""
    header = {key: {"dtype": "F16", "shape": [1], "data_offsets": [0, 2]}
              for key in keys}
    header["__metadata__"] = {"format": "pt"}
    blob = json.dumps(header).encode()
    with open(path(name), "wb") as handle:
        handle.write(struct.pack("<Q", len(blob)))
        handle.write(blob if junk is None else blob[:junk])
    return path(name)


def _gguf_string(text):
    raw = text.encode()
    return struct.pack("<Q", len(raw)) + raw


def gguf(name, keys):
    """A GGUF v3 file: the two metadata shapes that are actually awkward — a
    string value and an array of fixed-width ones — and then the tensor table
    the reader is after."""
    out = [b"GGUF", struct.pack("<I", 3), struct.pack("<QQ", len(keys), 2)]
    out.append(_gguf_string("general.architecture") + struct.pack("<I", 8)
               + _gguf_string("qwen3vl"))
    # An array of 4096 u32s: the merge table's shape, and the one the reader
    # must seek past rather than read one item at a time.
    out.append(_gguf_string("tokenizer.ggml.token_type") + struct.pack("<I", 9)
               + struct.pack("<IQ", 4, 4096) + b"\0" * (4 * 4096))
    for key in keys:
        out.append(_gguf_string(key) + struct.pack("<I", 1)      # one dimension
                   + struct.pack("<Q", 16)                       # its length
                   + struct.pack("<I", 0) + struct.pack("<Q", 0))  # dtype, offset
    with open(path(name), "wb") as handle:
        handle.write(b"".join(out))
    return path(name)


TEXT_ONLY = ["model.embed_tokens.weight", "model.layers.0.self_attn.q_proj.weight"]
WITH_TOWER = TEXT_ONLY + ["visual.blocks.0.attn.qkv.weight",
                          "visual.merger.linear_fc2.weight"]
# The transformers-shaped export, which core's `sd.py` renames on the way in.
NESTED_TOWER = TEXT_ONLY + ["model.visual.deepstack_merger_list.0.norm.weight"]


# ---- what the file said ------------------------------------------------------

check("a safetensors encoder with a vision tower",
      visionweights.has_vision(safetensors("vl.safetensors", WITH_TOWER)), True)
check("...spelled the transformers way as well",
      visionweights.has_vision(safetensors("nested.safetensors", NESTED_TOWER)), True)
check("the text-only cut of the same weights",
      visionweights.has_vision(safetensors("text.safetensors", TEXT_ONLY)), False)
check("a GGUF encoder with a vision tower",
      visionweights.has_vision(gguf("vl.gguf", WITH_TOWER)), True)
check("...and the text-only cut of one",
      visionweights.has_vision(gguf("text.gguf", TEXT_ONLY)), False)


# ---- what the file did not say -----------------------------------------------
#
# Every one of these must be None. A caller turns False into a refusal, and a
# refusal earned by an unreadable byte is worse than the render it prevented.

check("a file that is not there", visionweights.has_vision(path("gone.safetensors")), None)
check("no filename at all", visionweights.has_vision(None), None)
check("a pickle, which would have to be executed to be read",
      visionweights.has_vision(safetensors("weights.bin", WITH_TOWER)), None)
check("a header whose length field outruns the file",
      visionweights.has_vision(safetensors("cut.safetensors", WITH_TOWER, junk=20)),
      None)

with open(path("empty.safetensors"), "wb") as handle:
    handle.write(b"")
check("an empty file", visionweights.has_vision(path("empty.safetensors")), None)

with open(path("notgguf.gguf"), "wb") as handle:
    handle.write(b"NOPE" + b"\0" * 64)
check("something with the extension and none of the format",
      visionweights.has_vision(path("notgguf.gguf")), None)

with open(path("vl.gguf"), "rb") as source, open(path("short.gguf"), "wb") as handle:
    handle.write(source.read(64))
check("a GGUF that stops in the middle of its metadata",
      visionweights.has_vision(path("short.gguf")), None)

"""Does this text encoder file carry a vision tower?

Every family in this pack that reads reference images reads them through a
VL encoder — Qwen2.5-VL for Qwen Image Edit, Qwen3-VL for Krea 2 — and the same
weights ship in two cuts. The text-only cut loads without complaint, tokenizes
the sentence without complaint, and then has nothing to encode the pictures
with: `clip.tokenize(prompt, images=[...])` walks into a vision tower that is
not there. What comes out the far end is a render that ignored every reference
it was given, which is the one failure mode this pack exists to make impossible.

Nothing here loads a model. A safetensors header is a JSON blob at the front of
the file and a GGUF tensor table is a list of names near it, so the question
"are the vision weights in this file" is answered by reading a few kilobytes.

The answer is three-valued on purpose. `True` and `False` are what the file
said; `None` is *this file did not say* — it is missing, unreadable, or in a
container this module does not parse — and a caller must not turn that into a
refusal. Refusing on what we could not read would ground renders over an
unreadable byte rather than over a real mistake, and the loader downstream is
the one that gets to complain about a file it cannot open.

`tests/test_visionweights.py` builds both containers in a temporary directory
and runs this standalone; nothing here imports ComfyUI.
"""

import json
import os
import struct

# What a vision tower is called in every VL encoder ComfyUI loads through
# `CLIPLoader`: `visual.` at the top level, or `model.visual.` in the
# transformers-shaped export core's `sd.py` renames on the way in. Substring
# rather than prefix so both spellings answer to one needle.
VISION_KEY = "visual."

# A header longer than this is not a header, it is a corrupt length field about
# to become an allocation. `lorameta` guards its own reads the same way and for
# the same reason.
MAX_HEADER = 64 * 1024 * 1024

# GGUF value type ids -> struct format, for the fixed-width ones. The variable
# ones (string, array) are handled by name in `_skip_value`.
_GGUF_FIXED = {
    0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i",
    6: "<f", 7: "<B", 10: "<Q", 11: "<q", 12: "<d",
}
_GGUF_STRING = 8
_GGUF_ARRAY = 9


def has_vision(path):
    """True / False / None — see the module docstring on the third answer."""
    if not path or not os.path.isfile(path):
        return None
    suffix = os.path.splitext(path)[1].lower()
    try:
        if suffix == ".gguf":
            names = _gguf_tensor_names(path)
        elif suffix in (".safetensors", ".sft"):
            names = _safetensors_tensor_names(path)
        else:
            # .bin and .pt are pickles, and reading one to answer a question
            # about it means executing it. Not this module's business.
            return None
    except (OSError, ValueError, struct.error, UnicodeDecodeError):
        return None
    if names is None:
        return None
    return any(VISION_KEY in name for name in names)


def _safetensors_tensor_names(path):
    with open(path, "rb") as handle:
        prefix = handle.read(8)
        if len(prefix) < 8:
            return None
        (length,) = struct.unpack("<Q", prefix)
        if not 0 < length <= MAX_HEADER:
            return None
        header = json.loads(handle.read(length))
    if not isinstance(header, dict):
        return None
    return [key for key in header if key != "__metadata__"]


def _gguf_tensor_names(path):
    """The tensor names out of a GGUF file's table.

    The table sits behind the metadata block, and the metadata block is
    variable-width, so there is no seeking past it — every key/value has to be
    walked. It is a few hundred entries and they are read once.
    """
    with open(path, "rb") as handle:
        if handle.read(4) != b"GGUF":
            return None
        version, = struct.unpack("<I", _read(handle, 4))
        if version not in (2, 3):
            # v1 counted in 32 bits. Nothing writes it any more, and guessing
            # at a layout is how a reader starts inventing tensor names.
            return None
        tensor_count, kv_count = struct.unpack("<QQ", _read(handle, 16))
        if tensor_count > 1_000_000 or kv_count > 1_000_000:
            return None
        for _ in range(kv_count):
            _skip_string(handle)
            _skip_value(handle, struct.unpack("<I", _read(handle, 4))[0])
        names = []
        for _ in range(tensor_count):
            names.append(_read_string(handle))
            dims, = struct.unpack("<I", _read(handle, 4))
            if dims > 8:
                return None
            _read(handle, 8 * dims)         # the shape
            _read(handle, 4 + 8)            # dtype and offset
    return names


def _read(handle, count):
    """`count` bytes, or a short read said out loud — a truncated file must not
    read as a file with no vision weights in it."""
    chunk = handle.read(count)
    if len(chunk) < count:
        raise ValueError("truncated GGUF")
    return chunk


def _read_string(handle):
    length, = struct.unpack("<Q", _read(handle, 8))
    if length > MAX_HEADER:
        raise ValueError("implausible GGUF string")
    return _read(handle, length).decode("utf-8", "replace")


def _skip_string(handle):
    length, = struct.unpack("<Q", _read(handle, 8))
    if length > MAX_HEADER:
        raise ValueError("implausible GGUF string")
    _read(handle, length)


def _skip_value(handle, kind):
    if kind == _GGUF_STRING:
        _skip_string(handle)
        return
    if kind == _GGUF_ARRAY:
        item, count = struct.unpack("<IQ", _read(handle, 12))
        if count > 100_000_000:
            raise ValueError("implausible GGUF array")
        if item in _GGUF_FIXED:
            # Fixed-width items are one seek rather than `count` reads: the
            # tokenizer's merge table is a million of them.
            handle.seek(struct.calcsize(_GGUF_FIXED[item]) * count, os.SEEK_CUR)
            return
        for _ in range(count):
            _skip_value(handle, item)
        return
    fmt = _GGUF_FIXED.get(kind)
    if fmt is None:
        raise ValueError(f"unknown GGUF value type {kind}")
    _read(handle, struct.calcsize(fmt))

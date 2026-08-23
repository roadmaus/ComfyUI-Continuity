"""The files an LTX 2.5 piece was pointed at.

H3's `models.Weights` is a dataclass with a field per slot, which was the right
shape while the slot table was a constant: five names, spelled in the loader, in
the checker and in the frontend. It is the wrong shape for a second family,
because the *keys* are the family's — a filename under `dit` means nothing to a
family whose checkpoint slot is called `fl2va` — so this reads the blob against
the slot table instead of against a field list.

Everything the render loop asks of a weights object is here and is only three
things (`families/base.py`): `routed(payload)`, `get(name)` and `device(name)`.
`routed` hands the payload straight back — a standing route is a choice among a
family's routed slots, and LTX 2.5 ships one transformer, so there is nothing to
choose and nothing to stamp.

Attribute access is kept for the slot names because `links.vae` is how every
reader spells it, and the emit hook wires by slot name.
"""

from ... import models as core
from . import models


class Weights:
    """The blob's `models` block, read against LTX 2.5's slot table."""

    def __init__(self, picked=None, dtype=core.DEFAULT_DTYPE, devices=None):
        self._picked = {name: picked.get(name) if picked else None
                        for name in models.SLOTS}
        self.dtype = dtype
        self.devices = dict(devices or {})

    @classmethod
    def from_blob(cls, data):
        """A missing or partial block is every field unset rather than an error:
        a node nobody has set up yet is the normal state of a fresh one, and a
        piece switched to this family from another one arrives with the previous
        family's keys, which are not these and read as nothing picked."""
        block = (data or {}).get("models")
        if not isinstance(block, dict):
            block = {}
        picked = {name: _clean(block.get(name)) for name in models.SLOTS}
        dtype = block.get("dtype")
        devices = {}
        raw = block.get("devices")
        if isinstance(raw, dict):
            for name, slot in models.SLOTS.items():
                # Only the slots that become a loader with a MultiGPU wrapper —
                # the same list the manifest's `device` flag draws.
                if slot.loader not in core.MULTIGPU:
                    continue
                chosen = _clean(raw.get(name))
                if chosen:
                    devices[name] = chosen
        return cls(picked,
                   dtype=dtype if isinstance(dtype, str) and dtype else core.DEFAULT_DTYPE,
                   devices=devices)

    def routed(self, payload):
        """Unchanged. One transformer means no route to stamp."""
        return payload

    def get(self, name):
        return self._picked.get(name)

    def device(self, name):
        return self.devices.get(name) or None

    def __getattr__(self, name):
        try:
            return self.__dict__["_picked"][name]
        except KeyError:
            raise AttributeError(name) from None


def _clean(value):
    """A filename, or None. Blank and non-string both mean unset."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def check(weights, audio=True, upscale=False):
    """Refuse now if a file this render needs was never picked.

    `upscale` is the one conditional slot a *pass* asks for rather than the
    machine: the second stage is the piece's choice, and the upscaler is only
    a missing file when that choice was made. The duration head is never
    checked here — it answers a question the seconds pill asks before a queue,
    not one a render asks during it.
    """
    needed = [name for name in models.REQUIRED
              if audio or not models.SLOTS[name].audio]
    if upscale:
        needed.append("upscaler")
    for name in needed:
        if weights.get(name):
            continue
        raise ValueError(
            f"{models.LABEL[name].capitalize()} has not been picked. "
            f"Open the node's 'weights' control and choose a file from "
            f"models/{models.FOLDERS[name]}."
        )

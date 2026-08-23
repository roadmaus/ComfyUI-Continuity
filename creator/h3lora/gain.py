"""How much does a LoRA actually change the model?

``strength`` is not a unit.  Measured across the local collection of 26 H3
content LoRAs the perturbation induced at strength 1.0 spans **65x** (0.080% to
5.21% of the base weights), and neither rank nor file size predicts it: a
rank-128 adapter sits at 0.26% while a rank-16 one sits at 0.39%.  So a strength
that was right for one LoRA carries no information about the next, and the user
is left hunting for a sweet spot per file.

This module measures the thing ``strength`` should have been proportional to,

    rel = sqrt( sum_l ||dW_l||_F^2 / sum_l ||W_l||_F^2 )

so that the node can rescale every LoRA onto one comparable unit.

Doing that naively is hopeless -- ``dW = B @ A`` is up to 28672 x 5376 and there
are ~260 of them per file -- but the Frobenius norm never needs the product:

    ||B A||_F^2 = tr(A^T B^T B A) = tr((B^T B)(A A^T)) = sum((B^T B) * (A A^T)^T)

and both factors are only r x r.  Measuring a 2.4 GB rank-128 adapter costs a
few seconds of which almost all is disk.

The base norms ``||W_l||`` come from a constant per module group rather than the
checkpoint.  Measured on the int8 ConvRot bake, base weight RMS is uniform to
within ~2x inside a group and the four linear groups agree to 20% of each other
(qkv 0.134, out 0.140, fc1 0.156, fc2 0.157), so a table is worth far more than
the 20 GB read it replaces.

adaLN is deliberately excluded from the measurement.  Its basis is
checkpoint-dependent -- the same adapter shipped dense and curve8 has a 5.7x
different adaLN norm -- so it is not comparable across files, and it is where
distillation LoRAs keep the schedule change that must not be normalised away.
"""

from __future__ import annotations

import logging
import math
import os

import torch

from . import keymap

LOG = logging.getLogger("h3.powerlorastack")

# Median RMS of the base weights per module group, i.e. ||W||_F / sqrt(out*in).
# Measured over all 260 2-D layers of a local h3 fl2va pruned int8 convrot bake.
_BASE_RMS = {
    "qkv": 0.1336,
    "out": 0.1395,
    "fc1": 0.1562,
    "fc2": 0.1574,
    "other": 0.1620,
}

# Median ``rel`` over the 27 non-distillation H3 LoRAs in models/loras/h3.
# This is the anchor that makes strength 1.0 mean "the usual amount of change"
# rather than "whatever this trainer happened to emit".  Chosen as the median
# rather than a hand-picked target so the calibration agrees with trainer
# defaults on ordinary files and only moves the outliers.
REFERENCE_REL = 0.00292

# Never boost: a LoRA measuring below the reference may be quiet on purpose
# (EMA-averaged distillation adapters sit an order of magnitude below content
# ones and are correct at 1.0), whereas one measuring far above it is
# essentially never correct at 1.0.  Trimming is the safe direction.
MIN_FACTOR = 0.05
MAX_FACTOR = 1.0

_DOWN = (".lora_down.weight", ".lora_A.weight", ".lora_A.default.weight", ".lora_A")
_UP = (".lora_up.weight", ".lora_B.weight", ".lora_B.default.weight", ".lora_B")

_cache: dict[tuple, dict] = {}


def _group(module: str) -> str:
    if "qkv" in module:
        return "qkv"
    if "out_proj" in module:
        return "out"
    if "fc1" in module:
        return "fc1"
    if "fc2" in module:
        return "fc2"
    return "other"


def _skip(module: str) -> bool:
    """adaLN is not comparable across checkpoints; see the module docstring."""
    return "adaln" in module


def _f32(t):
    t = t.to(torch.float32)
    return t.reshape(t.shape[0], -1) if t.ndim > 2 else t


def _lowrank_fro2(B, A) -> float:
    """||B @ A||_F^2 without forming the product."""
    B, A = _f32(B), _f32(A)
    return max(float(((B.T @ B) * (A @ A.T).T).sum()), 0.0)


def _kron_fro2(w1, w2) -> float:
    """||w1 (x) w2||_F^2 == ||w1||^2 ||w2||^2 -- Kronecker norms factorise."""
    return float(_f32(w1).norm() ** 2) * float(_f32(w2).norm() ** 2)


class _Accum:
    """Sums delta energy against the base energy of the layers it lands on."""

    def __init__(self):
        self.delta2 = 0.0
        self.base2 = 0.0
        self.layers = 0
        self.ranks: set[int] = set()
        self.kinds: set[str] = set()

    def add(self, module: str, delta2: float, out: int, inp: int, kind: str, rank=None):
        rms = _BASE_RMS.get(_group(module), _BASE_RMS["other"])
        self.delta2 += delta2
        self.base2 += (rms ** 2) * out * inp
        self.layers += 1
        self.kinds.add(kind)
        if rank:
            self.ranks.add(int(rank))

    def result(self, name: str) -> dict:
        rel = math.sqrt(self.delta2 / self.base2) if self.base2 > 0 else None
        return {
            "name": name,
            "rel": rel,
            "layers": self.layers,
            "ranks": sorted(self.ranks),
            "kinds": sorted(self.kinds),
            # exact-duplicate fingerprint: two files with the same layer count
            # and the same total delta energy are the same adapter
            "fingerprint": None if rel is None else f"{self.layers}:{self.delta2:.10g}",
            "factor": factor_for(rel),
        }


def factor_for(rel):
    """Strength multiplier that puts ``rel`` onto the reference unit."""
    if not rel or rel <= 0:
        return 1.0
    return max(MIN_FACTOR, min(MAX_FACTOR, REFERENCE_REL / rel))


def _pairs(keys):
    """Group canonical keys into ``{module: {'down','up','alpha',...}}``."""
    mods: dict[str, dict] = {}
    for key in keys:
        body, suffix = keymap.split_suffix(key)
        if body is None:
            continue
        slot = None
        if suffix in _DOWN:
            slot = "down"
        elif suffix in _UP:
            slot = "up"
        elif suffix == ".alpha":
            slot = "alpha"
        elif suffix in (".lokr_w1", ".lokr_w2", ".lokr_w1_a", ".lokr_w1_b",
                        ".lokr_w2_a", ".lokr_w2_b", ".diff"):
            slot = suffix[1:]
        if slot:
            mods.setdefault(body, {})[slot] = key
    return mods


def _measure(mods, get, name: str) -> dict:
    """``mods`` from :func:`_pairs`, ``get(key) -> tensor``."""
    acc = _Accum()
    for module, slots in mods.items():
        if _skip(module):
            continue
        try:
            alpha_key = slots.get("alpha")
            if "down" in slots and "up" in slots:
                A = get(slots["down"])
                B = get(slots["up"])
                rank = A.shape[0]
                scale = float(get(alpha_key).reshape(-1)[0]) / rank if alpha_key else 1.0
                out, inp = B.shape[0], A.reshape(A.shape[0], -1).shape[1]
                acc.add(module, (scale ** 2) * _lowrank_fro2(B, A), out, inp, "lora", rank)
            elif "lokr_w2" in slots or "lokr_w2_a" in slots:
                w1 = (get(slots["lokr_w1"]) if "lokr_w1" in slots
                      else _f32(get(slots["lokr_w1_a"])) @ _f32(get(slots["lokr_w1_b"])))
                w2 = (get(slots["lokr_w2"]) if "lokr_w2" in slots
                      else _f32(get(slots["lokr_w2_a"])) @ _f32(get(slots["lokr_w2_b"])))
                w1, w2 = _f32(w1), _f32(w2)
                # LoKr's alpha divides by the rank of the factored side
                scale = 1.0
                if alpha_key and "lokr_w2_a" in slots:
                    scale = float(get(alpha_key).reshape(-1)[0]) / get(slots["lokr_w2_b"]).shape[0]
                out = w1.shape[0] * w2.shape[0]
                inp = w1.shape[1] * w2.shape[1]
                acc.add(module, (scale ** 2) * _kron_fro2(w1, w2), out, inp, "lokr")
            elif "diff" in slots:
                d = _f32(get(slots["diff"]))
                acc.add(module, float(d.norm() ** 2), d.shape[0], d.shape[1], "diff")
        except Exception as exc:                      # one odd layer must not
            LOG.debug("gain: skipped %s (%s)", module, exc)   # sink the file
    return acc.result(name)


def measure_state_dict(normalized_sd: dict, name: str = "", path: str = "") -> dict:
    """Measure an already-loaded, key-normalised LoRA.

    Used on the apply path, where the tensors are in memory anyway, so this
    costs only the r x r arithmetic.

    MMC: `path` caches the answer on the file, as `measure_file` does. "Only the
    r x r arithmetic" is still tens of GFLOP on a full H3 adapter, and this pack
    applies the same stack once per segment — where upstream's node applies it
    once per queue. What is measured is the file, so a second segment is asking
    a question already answered.
    """
    key = None
    if path:
        try:
            st = os.stat(path)
            key = (path, st.st_mtime_ns, st.st_size, "sd")
        except OSError:
            key = None
        hit = _cache.get(key) if key else None
        if hit is not None:
            return hit
    info = _measure(_pairs(normalized_sd.keys()), lambda k: normalized_sd[k], name)
    if key is not None:
        _cache[key] = info
    return info


def measure_file(path: str) -> dict:
    """Measure a LoRA on disk, streaming it.  Cached on (path, mtime, size)."""
    try:
        st = os.stat(path)
    except OSError as exc:
        return {"name": os.path.basename(path), "error": str(exc), "rel": None,
                "factor": 1.0, "layers": 0}
    key = (path, st.st_mtime_ns, st.st_size)
    hit = _cache.get(key)
    if hit is not None:
        return hit

    name = os.path.basename(path)
    try:
        from safetensors import safe_open
        with safe_open(path, framework="pt", device="cpu") as f:
            info = _measure(_pairs(f.keys()), f.get_tensor, name)
    except Exception as exc:
        info = {"name": name, "error": str(exc), "rel": None, "factor": 1.0, "layers": 0}
    _cache[key] = info
    return info

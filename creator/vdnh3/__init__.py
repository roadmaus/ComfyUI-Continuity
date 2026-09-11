"""VDN-H3 — Video Delta Net hybrid attention for MiniMax H3, vendored from
ComfyUI-VDN-H3.

Upstream: <https://github.com/Saganaki22/ComfyUI-VDN-H3>, Apache-2.0,
revision `7271c64` (2026-09-07). Its LICENSE sits beside this file.
`tools/vendor_vdnh3.py` copies the upstream modules, re-roots their imports
into this package and reapplies whatever `tools/vdnh3.patch` holds.

The architecture, the training and the checkpoints are OpenVDN's
(<https://github.com/OpenVDN/vdn-minimax-h3>, Apache-2.0; the weights under
the MiniMax H3 Community License). Upstream here is the port of that work onto
ComfyUI's own MiniMax-H3 model, as runtime patches over a loaded MODEL: nearby
frames keep exact softmax attention inside a window, everything further away
goes through a linear-attention branch whose cost is constant in clip length,
and two LoRA adapters — stage-B "default" and the 8-step DMD "turbo" — sit on
the base. No core file is modified and nothing beyond torch is needed.

**Why this is copied and not called.** The accelerators `accel.py` wires in are
somebody else's *nodes*, off by default, and the argument there is that a copy
of their tuning goes stale. VDN is not a node's worth of tuning; it is the
model. A stage under `models/vdn` is only a render if the port that reads it is
present, and the port is 2,700 lines of pure PyTorch with no dependency this
ComfyUI does not already have — the same shape `mlxdlss/` was, and the same
answer: a second install step buys nothing but a second thing to go wrong.

**What is here, and what is not.** The library: `spec` (checkpoint discovery
and the lazy branch loader), `adapters` (the released adapters re-keyed onto
ComfyUI's fused QKV), `apply` (bypass and merge through core's own LoRA
machinery), `branch` (the delta-rule linear attention), `window` (the chunked
softmax window) and `hybrid` (the forward that ties them). `nodes.py` too,
because its `_apply_vdn` is the one function that turns a stage directory into
a patched model, and that is what `creator/vdn.py` calls; the two node classes
in it are upstream's product and are not registered by this pack. Not here:
the example workflow, the int8 quantizer and upstream's test suite.

**What this pack decides for the user.** One knob, the stage. Everything else
is upstream's validated default: `merge` for the adapters (bypass measurably
degrades the 8-step stages), `auto` for where the branch weights live and
whether scratch is retained, `grouped` for the softmax backend. The trained
window is never deviated from.

Imported lazily by `vdn.py`: every module here imports torch and ComfyUI at
module level, and `vdn` is read by the manifest and the compilers, which the
pure test suites load with no torch at all.
"""

# The upstream commit this copy was taken from. Stamped by the vendoring script.
REVISION = "7271c648d7c2ff61ae1a7342dd9761e4545a34c3"

__all__ = ["REVISION"]

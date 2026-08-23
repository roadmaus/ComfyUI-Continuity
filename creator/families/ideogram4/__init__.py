"""Ideogram 4.0: a 9.3B single-stream DiT behind Qwen3-VL-8B, sampled on its
own resolution-shifted schedule with a *pair* of checkpoints — the
unconditional branch is a separate model.

A still-only family. What lives here is the architecture's own: its preset
table (the official V4 qualities, mu and std included), the dual-model guider
with the late CFG drop, and the custom-schedule sampler that carries them. The
flow those feed is the shared image-still layer in `compile_image.py` /
`render_image.py`.

No imports here, for the reason `families/__init__.py` gives.
"""

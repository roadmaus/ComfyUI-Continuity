"""Krea 2: a 12.9B DiT behind a Qwen3-VL-4B text encoder, sampling like an
ordinary CFG model — RAW undistilled, Turbo an 8-step distillation at cfg 1.

A still-only family. What lives here is what the architecture's training
decided: its checkpoint fields, its sampler-row presets, and the
reference branch through the Krea 2 Edit V2 LoRAs and the vendored Krea2Edit
nodes they were trained on (`edit.py`). The flow those
constants feed — blob to payload, payload to graph — is the shared image-still
layer in `compile_image.py` / `render_image.py`, which every image family rides.

No imports here, for the reason `families/__init__.py` gives.
"""

"""Qwen Image Edit: the 20B Qwen-Image DiT post-trained to edit rather than to
draw from nothing, behind a Qwen2.5-VL-7B encoder that reads the pictures as
well as the sentence.

A still-only family, and the only one here whose subject is a picture that
already exists. Krea 2 and Ideogram 4.0 answer a sentence; this one answers a
sentence *about* up to three images — "the same woman, the same coat, now
facing the door" — which is the pre-stage's actual job and the reason this
family is in the pack at all. The rest of the flow is the shared image-still
layer in `compile_image.py` / `render_image.py`, which every image family rides.

No imports here, for the reason `families/__init__.py` gives.
"""

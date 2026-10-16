"""MOSS-Image: OpenMOSS's 5B single-stream DiT behind a stock Qwen3.5-9B text
encoder, decoding through the Flux 2 VAE — text-to-image only.

A still-only family, and the plainest graph in the pack: no reference
conditioning of any kind, no distilled checkpoint core can sample, and a
schedule core detects on its own. What lives here is the sampler row the model
card ships and the one piece of guidance it adds — layer 22 skipped on the
unconditional pass. The rest of the flow is the shared image-still layer in
`compile_image.py` / `render_image.py`, which every image family rides.

No imports here, for the reason `families/__init__.py` gives.
"""

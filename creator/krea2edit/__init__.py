"""Krea2Edit — the reference path of the Krea 2 Identity Edit and General Edit
LoRAs, vendored from ComfyUI-Krea2Edit.

Upstream: <https://github.com/lbouaraba/comfyui-krea2edit>, Apache-2.0,
revision `13ef60f` (2026-10-16). Its LICENSE sits beside this file.
`tools/vendor_krea2edit.py` copies upstream's one module in as `nodes.py` and
reapplies whatever `tools/krea2edit.patch` holds.

The LoRAs are Lars Bouaraba's (<https://huggingface.co/conradlocke/krea2-identity-edit>),
under the Krea 2 Identity Edit V2 License and the Krea 2 Community License —
free for personal and non-commercial use. Nothing of the weights is here.

**What upstream is.** The LoRAs were trained with two conditionings that core
does not build: the reference VAE-encoded at the *output's* grid and laid into
the token sequence as clean frames (RoPE frame 1, 2, …), and the instruction
encoded by Qwen3-VL *with the picture in view*, under the training's own
system prompt and with no `Picture N:` labels. `Krea2EditModelPatch` is the
first — a DIFFUSION_MODEL wrapper that rebuilds Krea 2's forward as
`[text | refs | target]` — with the training-matched `fit` geometry, the
`ref_boost` attention dial and V2's reference placement. `Krea2EditGroundedEncode`
is the second. Core's Qwen-edit encoder, which is what this pack reached for
before, gets the layout roughly right and every other part of the recipe wrong,
and none of it errors: the render just holds the person less well.

**Why this is copied and not called.** It is the model's reading of a picture,
not a node's worth of tuning: without it the LoRA has nothing trained to read.
It is 540 lines of PyTorch over core's own Krea 2 submodules with nothing to
install, which is `vdnh3/`'s shape and gets `vdnh3/`'s answer. The two node
classes in `nodes.py` are upstream's product and are not registered by this
pack — a user who also has upstream installed would otherwise get the same
node id twice. `creator/families/krea2/edit.py` holds the two internal nodes
the graph builds, each one call into the classes here.

**What this pack decides for the user.** `fit` geometry always (V2 and v1.2 are
trained on it), `target_latent` always wired (upstream's fix for the VAE
landing mid-sampling on a tight card), `grounding_px` at the 768 every row of
the model card uses, and `bag of features` left out — experimental, with no
recommended use. Placement and the likeness dial are the user's, defaulted per
LoRA from the card.

Imported lazily: `nodes.py` imports torch and ComfyUI at module level, and the
family package is read by the manifest and the compilers, which the pure test
suites load with no torch at all.
"""

# The upstream commit this copy was taken from, and the release it carries.
# Stamped by the vendoring script.
REVISION = "13ef60f20828949becada815d3cbc371eb5ccaab"
VERSION = "2.0.0"

__all__ = ["REVISION", "VERSION"]

"""H3-safe LoRA loading, vendored from ComfyUI-H3-PowerLoraStack.

Upstream: <https://github.com/cicalooo/ComfyUI-H3-PowerLoraStack>, Apache-2.0,
revision `fc1bba6` (2026-08-09). Its LICENSE sits beside this file. `MODIFIED`
below is the whole of what this copy changes; every other line is upstream's.

**Why this is vendored and not called.** The rest of this pack's optional
machinery — the caches, Spectrum, sage, the preview decoder — is *wired in*
rather than copied, and `accel.py` argues that case at length: those packs are
accelerators, they are off by default, and a copy of somebody else's tuning goes
stale silently the first time they retune it.

None of that argument survives here, because this is not an accelerator and it
is not optional. It is what loading a LoRA onto a quantized H3 checkpoint has to
do to be *correct*:

- ComfyUI's stock path dequantizes, adds the delta and requantizes with a
  recalculated codebook. That round trip is not idempotent — it injects roughly
  1.5% relative weight noise, where a typical H3 LoRA delta is 0.01–0.08% of the
  weight. The adapter is replaced by rounding noise, and the merge is also two
  orders of magnitude slower than the branch it replaces.
- H3 ships in two adaLN forms, dense and curve. A LoRA trained against one has
  the wrong `lora_A` width for the other, and ComfyUI drops those pairs — which
  on a distillation LoRA is most of the adapter.
- H3 LoRAs ship under five different key conventions, and `qkv_proj` is not two
  tokens.

A user without this installed would get all three of those silently, which is
exactly the failure a "when the pack is present" integration is worst at: the
render finishes, and nothing says the LoRA did not arrive. So it ships in the
box and it is the default path — see `lora.py`.

Only the library is taken: the four nodes, their web UI, the auto-balance HTTP
route and the format inspector are upstream's product and are not vendored. Take
them from upstream if you want them; they operate on `MODEL` and compose with
what this pack builds.

Re-sync with `python3 tools/vendor_h3lora.py <path to an upstream clone>`, which
copies these modules, restamps the revision above and re-applies MODIFIED as a
patch — so an upstream fix arrives without hand-merging, and a local change that
upstream has since made unnecessary fails loudly rather than being carried
forever.

MODIFIED — local deltas, each marked `# MMC:` at its site:

- `adaln.py` — the dense-target basis is cached per source table rather than
  once per stack (upstream AUDIT_REPORT H1: the second curve LoRA of a stack was
  silently rebased onto the first one's basis), and table-to-table fitting moves
  both tables to the CPU first (H5: it raised on CUDA tables).
- `apply.py` — an entry may carry a preloaded `weights` state dict, so the file
  this pack already holds in memory is not read off disk again per segment; and
  an entry may carry its own `modality`, overriding the stack-level argument.
  Whether an adapter belongs on the soundtrack is a property of the file — H3
  runs audio and video through one tower, so a LoRA trained on clips with poor
  audio drags the sound of every render it is in — and upstream's one setting
  for the whole stack cannot say that about one file out of six.
"""

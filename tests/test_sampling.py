"""`sampling.resolve`: what the row is, and which half of the node said so.

    python3 tests/test_sampling.py

The row moved off the widgets and into the blob so a second model family can
declare its own controls — see `sampling.py`. What that module has to get right
is the seam between the two stores, because everything already queued is on the
far side of it: a workflow saved before the move carries no `sampling` block and
must render at its widgets, and one saved by an older frontend may carry a block
missing whatever was added since.

So the fallback is per field rather than per block, and most of what is below is
about that. `tests/test_golden_graph.py` covers the other half — that a blob row
and a widget row reach the same graph, and that neither reaches the segment
node's cache key.
"""

import sys

import layout
from harness import FAILURES, check, passed

passed("all sampling tests passed")

sampling = layout.load("accel", "sampling").sampling

# What the node is actually called with when nobody has touched a pill: the
# schema's own defaults, which is what a fresh node hands `resolve`.
WIDGETS = {
    "seed": 100, "steps": 20, "cfg": 1.0,
    "sampler_name": "res_multistep", "scheduler": "simple",
    "shift_video": sampling.SHIFT_DEFAULTS[0], "shift_audio": sampling.SHIFT_DEFAULTS[1],
    "block_cache": "off", "spectrum": False, "spectrum_blend": 0.5,
    "sage": False, "attention": "default", "chunk_ffn": False,
    "fp16_accumulation": False,
}


def resolve(blob=None, **widgets):
    data = {} if blob is None else {"sampling": blob}
    return sampling.resolve(data, {**WIDGETS, **widgets})


def expect_error(label, fn, fragment):
    try:
        fn()
    except sampling.SamplingError as exc:
        if fragment not in str(exc):
            FAILURES.append(f"{label}: error {str(exc)!r} does not mention {fragment!r}")
    except Exception as exc:  # noqa: BLE001
        FAILURES.append(f"{label}: raised {type(exc).__name__} rather than SamplingError")
    else:
        FAILURES.append(f"{label}: expected an error mentioning {fragment!r}, got none")


# ---- no block at all ---------------------------------------------------------
#
# Every workflow saved before the row moved. This is the case that must never
# break, because it is the one nobody will re-save before queueing it.

sampler, accel_settings = resolve(None, steps=13, cfg=3.0, sampler_name="euler")
check("no block: steps come off the widget", sampler.steps, 13)
check("no block: cfg comes off the widget", sampler.cfg, 3.0)
check("no block: the sampler comes off the widget", sampler.sampler_name, "euler")
check("no block: the shifts come off the widgets",
      (sampler.shift_video, sampler.shift_audio), sampling.SHIFT_DEFAULTS)
check("no block: the accelerators come off the widgets", accel_settings.any, False)

sampler, accel_settings = resolve(None, block_cache="fast", chunk_ffn=True)
check("no block: the cache comes off the widget", accel_settings.block_cache, "fast")
check("no block: chunked ffn comes off the widget", accel_settings.chunk_ffn, True)

# The seed is not in the block and never will be — `control_after_generate` is a
# real widget's linked control and a JSON field cannot carry it.
check("the seed is always the widget's", resolve(None, seed=4242)[0].seed, 4242)
check("...even when the block tries to name one",
      resolve({"steps": 4}, seed=4242)[0].seed, 4242)

# ---- a partial block ---------------------------------------------------------
#
# What an older frontend wrote. The fields it knew about win; the ones added
# since fall through, which is what makes adding a field later cost nothing.

sampler, accel_settings = resolve({"steps": 8}, steps=20, cfg=2.0, block_cache="easy")
check("a named field wins", sampler.steps, 8)
check("...and an absent one still falls through", sampler.cfg, 2.0)
check("...including into the accelerators", accel_settings.block_cache, "easy")

# ---- a full block ------------------------------------------------------------

sampler, accel_settings = resolve(
    {"steps": 6, "cfg": 1.5, "sampler_name": "euler", "scheduler": "beta",
     "shift_video": 6.0, "shift_audio": 2.0, "block_cache": "safe",
     "spectrum": True, "spectrum_blend": 0.25, "attention": "sage",
     "chunk_ffn": True, "fp16_accumulation": True},
    # Every widget saying something else, to prove none of it is read.
    steps=99, cfg=9.9, sampler_name="ddim", scheduler="karras",
    shift_video=1.0, shift_audio=1.0, block_cache="tea", spectrum=False,
    spectrum_blend=0.9, attention="kitchen", chunk_ffn=False,
    fp16_accumulation=False)
check("the whole row reads off the block",
      (sampler.steps, sampler.cfg, sampler.sampler_name, sampler.scheduler,
       sampler.shift_video, sampler.shift_audio),
      (6, 1.5, "euler", "beta", 6.0, 2.0))
check("...and so does the whole accelerator half",
      (accel_settings.block_cache, accel_settings.spectrum, accel_settings.spectrum_blend,
       accel_settings.attention, accel_settings.chunk_ffn, accel_settings.fp16_accumulation),
      ("safe", True, 0.25, "sage", True, True))
check("a moved shift is a shift", sampler.shifted(), True)
check("...and the defaults are not", resolve(None)[0].shifted(), False)

# ---- the deprecated sage switch ---------------------------------------------
#
# It predates both the `attention` list and this module, so it is widget-only on
# purpose: a blob naming an attention has said what it wants.

check("the old switch still runs sage", resolve(None, sage=True)[1].attention, "sage")
check("...but only while the list is at its default",
      resolve(None, sage=True, attention="kitchen")[1].attention, "kitchen")
check("...and a block that names one settles it",
      resolve({"attention": "default"}, sage=True)[1].attention, "default")

# ---- what will not be run ----------------------------------------------------
#
# The blob is hand-editable, so these are reachable by a person rather than only
# by a corrupt file — and a row that cannot be sampled should say so before a
# loader is built, not after the first pass.

expect_error("a non-object block", lambda: resolve([1, 2, 3]), "must be an object")
expect_error("fractional steps", lambda: resolve({"steps": 2.5}), "whole number")
expect_error("zero steps", lambda: resolve({"steps": 0}), "at least 1")
expect_error("cfg as a word", lambda: resolve({"cfg": "high"}), "must be a number")
expect_error("an unknown cache", lambda: resolve({"block_cache": "turbo"}), "must be one of")
expect_error("an unknown attention", lambda: resolve({"attention": "flash"}), "must be one of")
expect_error("a flag as a number", lambda: resolve({"chunk_ffn": 1}), "true or false")
expect_error("an empty sampler name", lambda: resolve({"sampler_name": ""}), "must be a name")

# `True` is an int in Python, which is the trap `settings.clean` names twice.
expect_error("steps as a boolean", lambda: resolve({"steps": True}), "whole number")
expect_error("cfg as a boolean", lambda: resolve({"cfg": True}), "must be a number")

# A key this pack does not know is dropped rather than refused: it is what a blob
# written by a *newer* frontend looks like, and refusing it would make a
# round-trip through an older install fatal instead of lossy.
check("an unknown key is ignored", resolve({"video_cfg": 3.0})[0].steps, 20)

# An explicit null is "nothing stored", not "the value null" — the shape the
# frontend writes when a control is cleared.
check("a null field falls through", resolve({"steps": None}, steps=11)[0].steps, 11)

"""The motion fix's planner, without a model: the token clock, the profile, the
holds, the round trip through smear and recover, and what is left alone.

    python3 tests/test_derope.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import layout  # noqa: E402

# Through `layout.load` rather than the package: importing the real one runs
# `__init__.py`, which wants ComfyUI, and the planner needs only numpy.
derope = layout.load("derope").derope
from harness import FAILURES, check, passed  # noqa: E402


# ---- the token clock ----------------------------------------------------------

check("a 17-frame group is five tokens covering (1, 4, 4, 4, 4)",
      [derope.token_start(t) for t in range(7)], [0, 1, 5, 9, 13, 17, 18])
check("frame -> token is the inverse",
      [derope.frame_token(f) for f in range(19)],
      [0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 6])
check("every token start maps back to itself",
      all(derope.frame_token(derope.token_start(t)) == t for t in range(60)), True)
check("token count on the grid", [derope.token_count(n) for n in (5, 22, 39, 56, 124)],
      [2, 7, 12, 17, 37])
check("legal ceil snaps up to 17k+5", [derope.legal_ceil(n) for n in (5, 6, 22, 23, 31, 39, 40)],
      [5, 22, 22, 39, 39, 39, 56])


# ---- the profile --------------------------------------------------------------

rng = np.random.default_rng(7)
calm = rng.normal(size=(1, 24, 37, 4, 6)) * 0.01 + np.linspace(0, 1, 37)[None, None, :, None, None]
burst = calm.copy()
burst[:, :, 18:22] += rng.normal(size=(1, 24, 4, 4, 6)) * 3.0
prof_calm = derope.jerk_profile(calm)
prof_burst = derope.jerk_profile(burst)
check("the profile is one value per token", prof_burst.shape, (37,))
check("a burst is where the profile peaks", 16 <= int(np.argmax(prof_burst)) <= 23, True)
check("a burst stands out more than a calm clip does",
      derope.contrast(prof_burst) > derope.contrast(prof_calm), True)
check("too short to difference is all zeros", derope.jerk_profile(calm[:, :, :3]).tolist(),
      [0.0, 0.0, 0.0])


# ---- the holds ----------------------------------------------------------------

tok = derope.token_holds(prof_burst)
check("the hot tokens are held at the peak", int(tok.max()), derope.D_MAX)
check("the ramp keeps neighbours within one", int(np.abs(np.diff(tok)).max()) <= 1, True)
check("the calm tail is not held", int(tok[-1]), 1)

flat = np.zeros(12)
flat[[3, 7]] = 5.0
bridged = derope.token_holds(flat, q=0.9, d_max=2, bridge=8, ramp=False)
check("a short valley between two hot tokens is bridged", bridged[3:8].tolist(), [2] * 5)
unbridged = derope.token_holds(flat, q=0.9, d_max=2, bridge=0, ramp=False)
check("...and not with the bridge off", unbridged[3:8].tolist(), [2, 1, 1, 1, 2])

holds = derope.frame_holds(np.array([1, 3, 1, 1, 1, 1, 1]), count=10, head=0)
check("frame holds read the token that covers the frame", holds, [1, 3, 3, 3, 3, 1, 1, 1, 1, 1])
check("a head trim shifts the clock",
      derope.frame_holds(np.array([1, 3, 1, 1, 1, 1, 1]), count=6, head=4), [3, 1, 1, 1, 1, 1])
check("past the last token, the last token",
      derope.frame_holds(np.array([1, 2]), count=8, head=0), [1, 2, 2, 2, 2, 2, 2, 2])

check("the ends are protected at 1",
      derope.protect_ends([4, 4, 4, 4, 4, 4, 4, 4], 2), [1, 1, 4, 4, 4, 4, 1, 1])
check("a pass shorter than twice the protection is all 1s",
      derope.protect_ends([4, 4, 4], 2), [1, 1, 1])

padded = derope.pad_to_grid([1, 1, 2, 2, 1])
check("the pad lives in the last hold and lands on the grid",
      (padded, sum(padded)), ([1, 1, 2, 2, 16], 22))


# ---- smear and recover round-trip ----------------------------------------------

plan_holds = [1, 1, 3, 3, 2, 1, 1]
order = derope.smear_index(plan_holds)
check("the smear repeats each frame by its hold", order, [0, 1, 2, 2, 2, 3, 3, 3, 4, 4, 5, 6])
back = derope.recover_index(plan_holds)
check("recovery takes the first of every group", back, [0, 1, 2, 5, 8, 10, 11])
check("smear then recover is the identity", [order[i] for i in back], list(range(7)))

frozen = derope.frozen_tokens(derope.pad_to_grid([1] * 5 + [3] * 8 + [1] * 5), frozenset(range(5)))
check("tokens made only of protected frames are frozen", frozen, [0, 1])
check("a token straddling the protected edge is not",
      2 in derope.frozen_tokens([1] * 6 + [3] * 8 + [1] * 5, frozenset(range(6))), False)


# ---- the plan -----------------------------------------------------------------

# 37 tokens is a 124-frame clip; the plan is per delivered frame.
plan = derope.plan(prof_burst, count=124, head=0)
check("a burst gets a plan", plan is not None, True)
check("...on the grid", plan.dilated, derope.legal_ceil(plan.dilated))
check("...with its ends protected",
      (plan.holds[:derope.PROTECT], plan.holds[-derope.PROTECT:][:-1]),
      ([1] * derope.PROTECT, [1] * (derope.PROTECT - 1)))
check("...and the first token frozen", 0 in plan.frozen, True)
check("...the world length is the pass", plan.world, 124)
check("...the peak is the hold, not the grid pad", plan.peak, derope.D_MAX)
check("...priced against the tokens the pass was sampled at", plan.sampled_tokens, 37)
check("the report prices the pass", "frames held" in plan.report and "time per step" in plan.report, True)

check("the plan does not gate: a calm profile still plans its fastest quarter",
      derope.plan(prof_calm, count=124) is not None, True)
check("a pass too short to hold anything outside its ends is left alone",
      derope.plan(prof_burst, count=8, protect=4), None)


# ---- the gate, off the frames ------------------------------------------------
#
# Measured 2026-09-12: a static fern and a spinning kick had profile contrasts
# of 1.36 and 1.15 — the wrong way round — so the gate reads motion magnitude
# off the delivered frames instead.

still = np.full((12, 96, 128, 3), 120, dtype=np.uint8)
still[:, 20:60, 30:70] = 200
moving = still.copy()
for t in range(12):
    moving[t] = 120
    moving[t, 20:60, 30 + 6 * t:70 + 6 * t] = 200
check("a static clip barely moves", derope.pixel_motion(still), (0.0, 0.0))
mean_m, peak_m = derope.pixel_motion(moving)
check("a moving block moves", (mean_m > derope.GATE, peak_m >= mean_m), (True, True))
check("floats on 0..1 read the same as bytes",
      derope.pixel_motion(moving.astype(np.float64) / 255.0), (mean_m, peak_m))
check("a one-frame clip is still", derope.pixel_motion(moving[:1]), (0.0, 0.0))
check("an empty pass is left alone", derope.plan(prof_burst, count=0), None)

passed("the de-rope planner holds where the latent jerks and round-trips exactly")

"""The motion fix's planner: where a pass moves too fast for the model, and the
slowed-down clock it is drawn again on.

**The defect.** H3 smears bursty motion — a backflip, a sword arc, a whip-fast
turn — and the cause is structural rather than a matter of steps or seeds. One
latent time token spans four pixel frames, and at high motion speed those four
frames need four distinct poses that a single token cannot hold. Re-denoising
the affected span does not help: the missing poses were never generated.

**The fix, at test time.** Give the model the room it lacks. The finished pass
is retimed onto a longer clock by *holding* (repeating) frames where the
motion is too fast, that slowed copy is encoded and sampled again from partway
down the schedule — video-to-video, so the choreography is kept and the
rendering is re-rolled — and the original clock is recovered by dropping the
held frames. The frames that come back are pixel-for-pixel generated frames,
never interpolated. Which frames to hold is read off the pass's own latent:
the third difference over time of the latent values, per token, is large where
a token was asked to carry more motion than it can. No extra model.

matlowai's Motion Lab (ComfyUI-MAINodes) worked this out and measured the
dials this module ships as defaults — the hot quantile, the peak hold, the
bridge rule and the ramp. Their pack is GPL-3 and this one is not, so nothing
of it is copied: what is here is written from the published description of
the method, and it is deliberately the small core of it. The parts that are
not here — the RoPE clock patches, the manual and painted hold maps, the
windowed re-render for long clips, the audio time-stretch — are either not
needed on a strip of short cards or are separate features.

**Every function here is pure numpy over plain lists**, so the planning is
unit-tested without a model. `motionfix.py` is the node that runs the plan.

**The token clock.** Legal H3 clip lengths are 17k+5 frames, and each group of
17 frames is five tokens covering (1, 4, 4, 4, 4) frames — every fifth token is
a singleton sitting on a multiple of 17. The tail +5 of a clip is the next
group's first two tokens. `token_start` and `frame_token` are the two
directions of that map; the phase normalisation in `jerk_profile` divides out
the bias the uneven spans put on the differences, so tokens are comparable.
"""

from dataclasses import dataclass, field

import numpy as np

FRAME_STEP = 17
FRAME_OFFSET = 5

# The dials, with the defaults the method was measured at. `Q` is the jerk
# quantile that counts as hot (higher = tighter spans, cheaper); `D_MAX` the
# peak hold on the hottest tokens (4 is the measured sweet spot — 2 and 3 save
# time and start to smear again); `BRIDGE` the longest valley, in tokens,
# between two hot spans of one burst that is filled to the peak rather than
# left as a dip (a dip inside a burst is where mid-burst artifacts come back);
# `INJECT` how much of the schedule the second pass runs over the slowed init
# (0.5–0.8 keeps the init's choreography and re-rolls the rendering; lower
# keeps the init's own smear, higher invents its own choreography).
Q = 0.75
D_MAX = 4
BRIDGE = 8
INJECT = 0.5
# The quantile can rank but cannot abstain: on a calm pass it would still hold
# the fastest quarter and pay the second pass for nothing — worse than nothing,
# measured: a static fern re-drawn through the pass came back sharper and
# moving unnaturally. The gate is not the profile's contrast (peak over mean
# of the phase-normalised profile), which measured 1.36 on that fern and 1.15
# on a spinning kick — normalising per phase throws away the magnitude, and
# on a 2 s card the ranking is all that is left. It is the magnitude itself,
# read off the delivered frames: the peak frame-to-frame change of the clip
# at thumbnail scale, on the 0-255 scale (`pixel_motion`). Measured 4.1 on
# the kick and 1.8 on the fern; a pass under this is left alone.
GATE = 2.5
# Thumbnail width the motion is measured at. Small enough that a burst is a
# few pixels of change and sensor-level noise is averaged away.
GATE_WIDTH = 32
# Frames at either end of the pass that are never held, whose tokens are
# frozen through the second pass, and whose pixels are put back verbatim: the
# join with the pass before this one and the run the pass after it continues
# from stay exactly as they were delivered, so the fix cannot become a seam
# step of its own (issue #41).
PROTECT = 5

# Per-step cost is not linear in the token count — attention dominates — so a
# 2.5x longer clip is roughly 4.9x the time per step. Measured exponent.
COST_EXP = 1.7


def token_start(t):
    """The first pixel frame of latent time token `t`."""
    group, phase = divmod(int(t), 5)
    return group * FRAME_STEP + (0 if phase == 0 else 4 * (phase - 1) + 1)


def frame_token(f):
    """The latent time token that covers pixel frame `f`."""
    group, rest = divmod(int(f), FRAME_STEP)
    return group * 5 + (0 if rest == 0 else (rest - 1) // 4 + 1)


def token_count(frames):
    """Latent time tokens for a clip of `frames` pixel frames on the grid."""
    return 2 if frames <= FRAME_OFFSET else (frames - FRAME_OFFSET) // FRAME_STEP * 5 + 2


def legal_ceil(n):
    """`n` snapped up to the 17k+5 grid."""
    n = max(int(n), FRAME_OFFSET)
    return FRAME_OFFSET + FRAME_STEP * (-(-(n - FRAME_OFFSET) // FRAME_STEP))


def jerk_profile(video):
    """Per-token motion overload off a video latent `[B, C, T, h, w]` -> `(T,)`.

    The absolute third difference of the latent values over time, averaged over
    everything but time, edge-padded back to `T`, and normalised per token
    phase so the (1, 4, 4, 4, 4) spans do not bias the ranking.
    """
    v = np.asarray(video, dtype=np.float64)
    if v.ndim != 5:
        raise ValueError(f"expected a [B, C, T, h, w] video latent, got {v.shape}")
    frames = v.shape[2]
    if frames < 4:
        return np.zeros(frames)
    j = np.abs(np.diff(v, n=3, axis=2)).mean(axis=(0, 1, 3, 4))
    prof = np.pad(j, (1, frames - len(j) - 1), mode="edge")
    for phase in range(5):
        mean = prof[phase::5].mean() if len(prof[phase::5]) else 0.0
        if mean > 0:
            prof[phase::5] /= mean
    return prof


def pixel_motion(frames, width=GATE_WIDTH):
    """How much a clip moves, off its own frames `[T, H, W, C]` (uint8 or
    0..1 float) -> `(mean, peak)` of the mean absolute frame-to-frame change,
    on the 0-255 scale, at a `width`-pixel greyscale thumbnail.

    Block-averaged rather than resampled, so a fast limb a few pixels wide
    still moves the thumbnail and film grain does not.
    """
    v = np.asarray(frames)
    if v.ndim != 4:
        raise ValueError(f"expected [T, H, W, C] frames, got {v.shape}")
    v = v.astype(np.float64)
    if v.max() <= 1.0:
        v = v * 255.0
    v = v[..., :3].mean(axis=-1)                       # grey
    factor = max(1, v.shape[2] // width)
    h, w = (v.shape[1] // factor) * factor, (v.shape[2] // factor) * factor
    v = v[:, :h, :w].reshape(v.shape[0], h // factor, factor, w // factor, factor).mean(axis=(2, 4))
    if v.shape[0] < 2:
        return 0.0, 0.0
    d1 = np.abs(np.diff(v, axis=0)).mean(axis=(1, 2))
    return float(d1.mean()), float(d1.max())


def contrast(profile):
    """Peak over mean — how much the profile stands out from its own floor."""
    profile = np.asarray(profile, dtype=np.float64)
    if not len(profile):
        return 0.0
    return float(profile.max() / max(float(profile.mean()), 1e-8))


def token_holds(profile, q=Q, d_max=D_MAX, bridge=BRIDGE, ramp=True):
    """Per-token hold counts off a profile: `d_max` on the hot tokens, bridged
    and ramped, 1 everywhere else."""
    prof = np.asarray(profile, dtype=np.float64)
    if not len(prof):
        return np.zeros(0, dtype=int)
    threshold = np.quantile(prof, q)
    tok = np.where(prof >= threshold, d_max, 1).astype(int)
    if bridge:
        hot = np.where(tok == d_max)[0]
        for a, b in zip(hot[:-1], hot[1:]):
            if 1 < b - a <= bridge:
                tok[a:b + 1] = d_max
    if ramp:
        # Relax until neighbours differ by at most one: hard steps in the hold
        # curve jitter.
        for _ in range(d_max - 1):
            left = np.concatenate([[1], tok[:-1]])
            right = np.concatenate([tok[1:], [1]])
            tok = np.maximum(tok, np.maximum(left, right) - 1)
    return tok


def frame_holds(tok, count, head=0):
    """Token holds -> a hold per delivered frame. `head` is how many frames
    were trimmed off the front of the latent before the pass was written, so
    delivered frame `f` is latent frame `f + head`."""
    last = len(tok) - 1
    return [int(tok[min(frame_token(f + head), last)]) for f in range(count)]


def protect_ends(holds, n):
    """The first and last `n` frames held at 1 whatever the profile said."""
    holds = list(holds)
    for i in range(min(n, len(holds))):
        holds[i] = 1
        holds[-1 - i] = 1
    return holds


def pad_to_grid(holds):
    """The last hold widened so the slowed clip lands on the 17k+5 grid. The
    padding frames are more copies of the last frame, which recovery drops."""
    holds = list(holds)
    holds[-1] += legal_ceil(sum(holds)) - sum(holds)
    return holds


def smear_index(holds):
    """Which delivered frame each slowed frame is a copy of."""
    return [i for i, h in enumerate(holds) for _ in range(h)]


def recover_index(holds):
    """Which slowed frame each delivered frame is taken back from: the first of
    every hold group."""
    starts, at = [], 0
    for h in holds:
        starts.append(at)
        at += h
    return starts


def frozen_tokens(holds, protected):
    """The slowed clip's tokens every frame of which is a copy of a protected
    delivered frame — the ones the second pass is not allowed to move."""
    source = smear_index(holds)
    dilated = len(source)
    frozen = []
    for t in range(token_count(dilated)):
        span = range(token_start(t), min(token_start(t + 1), dilated))
        if len(span) and all(source[d] in protected for d in span):
            frozen.append(t)
    return frozen


@dataclass(frozen=True)
class Plan:
    """What the node runs: the hold per delivered frame (grid-padded), which
    frames are protected, which slowed tokens are frozen, and the price."""
    holds: list
    protected: frozenset
    frozen: list
    contrast: float
    # The peak hold before the grid pad widened the last one, and the token
    # count the pass was sampled at (its whole latent, trim included) — the
    # honest denominator for the price, since that is the step the card paid.
    peak: int
    sampled_tokens: int
    world: int = field(init=False)
    dilated: int = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "world", len(self.holds))
        object.__setattr__(self, "dilated", sum(self.holds))

    @property
    def held(self):
        return sum(1 for h in self.holds if h > 1)

    @property
    def report(self):
        tokens = token_count(self.dilated) / max(self.sampled_tokens, 1)
        return (f"{self.held} of {self.world} frames held, peak x{self.peak}, "
                f"{self.world} -> {self.dilated} frames "
                f"({self.dilated / max(self.world, 1):.2f}x, about "
                f"{tokens ** COST_EXP:.1f}x the time per step), "
                f"{len(self.frozen)} tokens frozen, contrast {self.contrast:.2f}")


def plan(profile, count, head=0, *, q=Q, d_max=D_MAX, bridge=BRIDGE, ramp=True,
         protect=PROTECT):
    """The plan for a `count`-frame delivered pass off its latent's profile, or
    None where there is nothing to hold outside its protected ends. Whether
    the pass is calm enough to skip is the caller's question (`pixel_motion`
    against the gate), asked before this is."""
    if count <= 0:
        return None
    seen = contrast(profile)
    holds = protect_ends(frame_holds(token_holds(profile, q, d_max, bridge, ramp),
                                     count, head), protect)
    if not any(h > 1 for h in holds):
        return None
    peak = max(holds)
    holds = pad_to_grid(holds)
    protected = frozenset(list(range(min(protect, count)))
                          + list(range(max(0, count - protect), count)))
    return Plan(holds=holds, protected=protected,
                frozen=frozen_tokens(holds, protected), contrast=seen,
                peak=peak, sampled_tokens=len(np.asarray(profile)))

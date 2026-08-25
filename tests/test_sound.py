"""The sound lane's arithmetic: where a block lands, and which pass gets it.

Two things are being checked and they fail differently.

`timeline_windows` is where a pass sits in the finished piece. Its old caller
only ever wanted the total, so a bug in the per-pass offsets would have shown up
as nothing at all until a score drifted a shot to the left halfway through a
piece — which is exactly the failure nobody debugs from the symptom.

`sound.for_window` is what one pass is handed. The case worth writing down is
the feathered seam: two passes sample the same instants, and they have to be
handed the *same* stretch of the same file for the frames they share or the
overlap the reel trims is an overlap between two different pieces of music.

    python3 tests/test_sound.py
"""

import layout
from harness import FAILURES, check, passed

_pkg = layout.load("canvas", "h3_declare", "contextir", "compile", "sound")
compiler = _pkg.compile
sound = _pkg.sound
H3 = _pkg.h3_declare.RULES


def piece(cards, **rest):
    """A timeline blob of `cards` — each `(seconds, merge, continue, feather)`."""
    segments = []
    for seconds, merge, cont, feather in cards:
        segments.append({"duration_s": seconds, "merge": merge,
                         "continue": cont, "feather": feather, "prompt": "x"})
    return {"segments": segments, "family": "h3", **rest}


# ---- where a pass lands ------------------------------------------------------

# Three five-second cards, generated separately, no seams: the passes are laid
# end to end and every one starts where the last ended.
PLAIN = piece([(5, False, False, 1)] * 3)
windows = compiler.timeline_windows(PLAIN)
check("plain: three passes", len(windows), 3)
check("plain: offsets are cumulative",
      [(w.at, w.frames) for w in windows],
      [(0, 124), (124, 124), (248, 124)])
check("plain: nothing is trimmed, so sampled == delivered",
      [(w.sampled_at, w.sampled) for w in windows],
      [(0, 124), (124, 124), (248, 124)])
check("plain: the total is what timeline_frames says",
      sum(w.frames for w in windows), compiler.timeline_frames(PLAIN))

# The same strip with a 22-frame feathered seam on cards 2 and 3. Each of those
# passes re-generates 22 frames it inherits and the reel trims them off, so the
# piece is 44 frames shorter than the three generations add up to — and each
# seamed pass *starts sampling* 22 frames before it starts delivering.
SEAMED = piece([(5, False, False, 1), (5, False, True, 22), (5, False, True, 22)])
windows = compiler.timeline_windows(SEAMED)
check("seamed: delivered offsets close the gaps the trim leaves",
      [(w.at, w.frames) for w in windows],
      [(0, 124), (124, 102), (226, 102)])
check("seamed: a pass samples from before it delivers",
      [(w.sampled_at, w.sampled) for w in windows],
      [(0, 124), (102, 124), (204, 124)])
check("seamed: the total still matches timeline_frames",
      sum(w.frames for w in windows), compiler.timeline_frames(SEAMED))
# The invariant that makes a seam free for sound: the frames pass N re-generates
# are the frames pass N-1 delivered, on one clock.
check("seamed: pass 2's lead-in covers pass 1's tail",
      windows[1].sampled_at + 22, windows[0].at + windows[0].frames)


# ---- reading the lane --------------------------------------------------------

def blocks(*specs):
    return sound.parse([{"filename": f, "at_s": at, "in_s": i, "out_s": o}
                        for f, at, i, o in specs], H3, 10_000)


def _try(fn):
    """What `fn` raised, or None. The type is the assertion, so nothing is
    swallowed — a suite that caught only `SoundError` would report a TypeError
    as a passing refusal."""
    try:
        fn()
    except Exception as exc:      # noqa: BLE001
        return exc
    return None


one = blocks(("score.mp3", 0.0, 0.0, 12.0))
check("parse: seconds become piece frames", (one[0].at, one[0].frames), (0, 288))

tiny = _try(lambda: blocks(("a.wav", 0, 0, 0.1)))
check("parse: a block shorter than the floor is refused",
      isinstance(tiny, sound.SoundError), True)


# Two files that overlap by a second. One stretch of a piece has one soundtrack,
# so this is refused rather than mixed behind the user's back.
over = _try(lambda: blocks(("a.wav", 0, 0, 5.0), ("b.wav", 4.0, 0, 5.0)))
check("parse: overlapping blocks are refused", isinstance(over, sound.SoundError), True)
check("parse: the refusal names both files",
      "a.wav" in str(over) and "b.wav" in str(over), True)

past = _try(lambda: sound.parse(
    [{"filename": "a.wav", "at_s": 0, "in_s": 0, "out_s": 5.0}], H3, 24))
check("parse: a block running past the piece is refused",
      isinstance(past, sound.SoundError), True)


# ---- the band ----------------------------------------------------------------

# A score over the first half, nothing after it. The band covers the whole piece
# either way: what is not supplied is generated, and the lane says so.
lane = blocks(("score.mp3", 1.0, 0.0, 4.0))
parts = sound.band(lane, 240)
check("band: covers the piece with no holes",
      [(p.at, p.frames) for p in parts], [(0, 24), (24, 96), (120, 120)])
check("band: the gaps are the unsupplied ones",
      [p.supplied for p in parts], [False, True, False])
check("band: it adds up to the piece",
      sum(p.frames for p in parts), 240)


# ---- what a pass is handed ---------------------------------------------------

windows = compiler.timeline_windows(SEAMED)
# One continuous cue over the whole strip.
cue = blocks(("score.mp3", 0.0, 0.0, 20.0))

first = sound.for_window(cue, windows[0], H3)
second = sound.for_window(cue, windows[1], H3)
check("for_window: pass 1 opens the file at its head", first[0].in_s, 0.0)
check("for_window: pass 1 is handed its whole generation",
      (first[0].at, first[0].frames), (0, 124))
check("for_window: pass 2 starts at frame 0 of its own clock", second[0].at, 0)
check("for_window: pass 2 is handed its whole generation too",
      (second[0].at, second[0].frames), (0, 124))
# The seam invariant, said in the file's own units: pass 2 picks the cue up 102
# frames in, which is exactly where pass 1 stopped delivering. The 22 frames the
# two share are the same 22 frames of score.
check("for_window: pass 2 picks up where pass 1 stopped delivering",
      round(second[0].in_s, 6), round(102 / H3.fps, 6))
check("for_window: the shared frames are the same stretch of the file",
      round(second[0].in_s + 22 / H3.fps, 6),
      round(first[0].in_s + 124 / H3.fps, 6))

# A cue that only covers the middle pass leaves the others with nothing, and
# nothing is what they must be handed — not silence, which the model would then
# be asked to reproduce.
short = blocks(("hit.wav", 6.0, 0.0, 2.0))
check("for_window: a pass the cue never reaches gets no blocks",
      [len(sound.for_window(short, w, H3)) for w in windows], [0, 1, 0])
check("covers: answers the same question without building the list",
      [sound.covers(short, w) for w in windows], [False, True, False])

# ---- through the compiler ----------------------------------------------------
#
# The lane reaches a segment node as a key on its payload, and the payload string
# is that node's cache key — so what is asserted here is both that the sound
# arrives and that it arrives *narrowly*. A lane written onto every payload would
# make one drag re-run the whole strip.

blob = dict(SEAMED, sound=[{"filename": "score.mp3", "at_s": 0.0,
                            "in_s": 0.0, "out_s": 13.0}])
payloads = compiler.timeline_payloads(blob)
check("payloads: every pass is handed its own stretch",
      [len(p.get("sound") or []) for p in payloads], [1, 1, 1])
check("payloads: pass 2 opens the file where pass 1 stopped delivering",
      round(payloads[1]["sound"][0]["in_s"], 4), round(102 / H3.fps, 4))
check("payloads: the block carries its own duration, not just its frames",
      round(payloads[0]["sound"][0]["seconds"], 4), round(124 / H3.fps, 4))

# A cue over the first shot alone leaves the rest of the strip byte-identical to
# a piece with no lane at all — which is what keeps the cache useful, and is the
# reason `_stamp_sound` writes nothing rather than an empty list.
short_blob = dict(SEAMED, sound=[{"filename": "hit.wav", "at_s": 0.0,
                                  "in_s": 0.0, "out_s": 2.0}])
with_lane = compiler.timeline_payloads(short_blob)
without = compiler.timeline_payloads(SEAMED)
check("payloads: an uncovered pass is untouched",
      [p == q for p, q in zip(with_lane[1:], without[1:])], [True, True])
check("payloads: the covered one is not", with_lane[0] == without[0], False)

# A clip is played, not sampled — there is no latent to fix part of, so nothing
# is stamped on it however far a cue reaches over it.
CLIPPED = piece([(5, False, False, 1)])
CLIPPED["segments"].append({"kind": "clip", "filename": "b.mp4",
                            "duration_s": 4, "trim": {"start": 0, "end": 4}})
clipped = compiler.timeline_payloads(
    dict(CLIPPED, sound=[{"filename": "score.mp3", "at_s": 0.0,
                          "in_s": 0.0, "out_s": 8.5}]))
check("payloads: supplied footage is never handed a block",
      "sound" in clipped[1], False)

passed("the sound lane lands where it should, and a seam costs it nothing")

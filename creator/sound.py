"""Sound laid against the piece, rather than cited by a shot.

Every audio this pack had until now was a *reference*: a file attached to one
card, cited by `@handle`, given a take, and described to the model in prose.
That is the right shape for "sound like this" and the wrong one for "this is
the sound" — a score the picture is cut to is not a property of shot three, it
is a property of the piece, and it runs across the seams between shots without
noticing them.

So a piece grows a **lane**: files placed at a time on the finished piece's own
clock, trimmed to a window of themselves, and handed to whichever passes they
cover. Pure, like `compile.py` and `canvas.py` — no torch, no ComfyUI, no
disk — because the frontend mirrors this arithmetic in `sound.js` and both
halves have to agree about where a block lands before a loader exists.

**What a lane block *is*, to the model.** The families this pack renders are
joint audio-video models: they sample a packed AV latent and there is no
soundless mode. So supplying sound is not mixing a track under a finished
video, it is **fixing part of the latent before sampling** — the audio stream
is written with the encoded waveform and masked to zero, which is core's
`noise_mask` convention for "keep this, do not denoise it" (`LTXVConcatAVLatent`
builds exactly such a mask, and `comfy/samplers.py` handles a nested one). The
picture is then generated *against* that sound rather than beside it.

That is why the vocabulary here is the one the pack already had. `AUDIO_TAKES`
has carried `copy` — "the signal itself becomes the video's own audio" — since
before anything could honour it, and a lane block is a `copy` that finally
happens. The other four takes stay what they were: imitation, described in
prose, encoded as a reference block where the family has a place for one.

**Gaps are not silence.** A stretch of the lane nobody covered is a stretch the
model scores, because an AV model always writes sound. That is worth stating in
code as well as in the UI: `band` returns the gaps as parts of the same list,
marked `supplied=False`, rather than returning only the blocks and leaving every
reader to work out what the holes mean. A reader that forgets ends up calling a
gap "silence" in a tooltip, which is the one wrong thing to say about it.

**Seams cost nothing here, and that is the point.** A feathered seam
re-generates its inherited run at the head of the next pass, so two passes
sample the same instants twice. `compile.timeline_windows` gives both of them
the same piece-clock coordinates for those frames, so both are handed the *same
stretch of the same file* — the overlap agrees because it was cut from one
source, not because anything crossfaded it. `families/ltx25/segment.py` used to
log that a sound seam reached it and was not conditioned on; a lane is the
answer to that note.
"""

from dataclasses import dataclass, replace

from . import canvas

# The shortest block worth having, in seconds. Matches `trim.js`'s MIN_SEGMENT:
# a handle that can be dragged into nothing is a trap rather than a control, and
# the two surfaces must agree or the lane can make a block the trim modal
# refuses to reopen.
MIN_SECONDS = 0.25


def at_frame(seconds, rules):
    """A time on the piece's clock -> the frame it lands on.

    **Not `canvas.frames_for_seconds`,** and the difference is the whole reason
    this exists rather than being imported. That one snaps to the *legal
    generation counts* — 17n+5 on H3, 8n+1 on LTX — because it answers "how long
    may one pass be". A lane position answers a different question: where in the
    finished file a cue starts, and the finished file is frames laid end to end
    with no grid on them at all. Snapping a block's start to the generation grid
    would move a downbeat by up to a third of a second for no reason anybody
    could see.
    """
    return max(0, round(float(seconds) * rules.fps))


class SoundError(ValueError):
    """A lane that cannot be read. Raised with the block named where there is
    one to name — a refusal about "the sound" is unactionable on a lane of six."""


@dataclass(frozen=True)
class Block:
    """One placement: a window of a file, at a time on the piece's clock.

    `at`/`frames` are frames rather than seconds because the piece's clock is a
    frame grid — `timeline_windows` answers in frames, and a block stored in
    seconds would land a half-frame off its own pass on every family whose fps
    does not divide its durations. `in_s` stays seconds because it addresses the
    *file*, which has no frame grid of ours.
    """
    filename: str
    at: int             # first frame it covers, on the piece's clock
    frames: int         # how many frames of the piece it covers
    in_s: float         # where the window opens in the file
    #: Which card this block belongs to, or None for one laid free on the lane.
    #: A `copy` reference attached to shot three is pinned to shot three's
    #: extent — it is not placed in time, it is attached to a shot, and the two
    #: are different statements that must not turn into each other by dragging.
    segment: int | None = None

    @property
    def end(self):
        return self.at + self.frames

    def seconds(self, rules):
        return canvas.seconds_for_frames(self.frames, rules)


@dataclass(frozen=True)
class Part:
    """One stretch of the finished piece's soundtrack — supplied or generated.

    The band is every one of these end to end with no holes, which is what makes
    a gap legible as "the model writes this" rather than as an absence.
    """
    at: int
    frames: int
    block: Block | None = None      # None where nothing was laid down

    @property
    def supplied(self):
        return self.block is not None

    @property
    def end(self):
        return self.at + self.frames


def parse(raw, rules, total_frames, where="the sound lane"):
    """The blob's `sound` list -> `Block`s, in play order.

    Refuses what the model cannot be handed rather than clamping it silently:
    an overlap has no meaning on one audio stream (two files cannot both be the
    sound at 0:04), and a block past the end of the piece is a file the user
    thinks they laid down and that nothing will ever read.
    """
    blocks = []
    for position, entry in enumerate(raw or []):
        name = f"{where}: block {position + 1}"
        filename = str(entry.get("filename") or "")
        if not filename:
            raise SoundError(f"{name} names no file")
        try:
            at_s = float(entry.get("at_s") or 0.0)
            in_s = float(entry.get("in_s") or 0.0)
            out_s = float(entry.get("out_s"))
        except (TypeError, ValueError):
            raise SoundError(
                f"{name} ({filename}) has no readable in/out point") from None
        if out_s - in_s < MIN_SECONDS:
            raise SoundError(
                f"{name} ({filename}) is {out_s - in_s:.2f} s long — the "
                f"shortest a block goes is {MIN_SECONDS} s")
        if at_s < 0:
            raise SoundError(f"{name} ({filename}) starts before the piece does")

        at = at_frame(at_s, rules)
        frames = max(1, at_frame(out_s - in_s, rules))
        blocks.append(Block(filename=filename, at=at, frames=frames, in_s=in_s))

    blocks.sort(key=lambda block: (block.at, block.filename))
    for earlier, later in zip(blocks, blocks[1:]):
        if later.at < earlier.end:
            raise SoundError(
                f"{where}: {earlier.filename} and {later.filename} overlap. One "
                f"stretch of the piece has one soundtrack — move one of them, "
                f"or trim the first so it ends where the second begins")
    if blocks and blocks[-1].end > total_frames:
        last = blocks[-1]
        raise SoundError(
            f"{where}: {last.filename} runs past the end of the piece. Trim it, "
            f"move it earlier, or lengthen the piece to reach it")
    return blocks


def band(blocks, total_frames):
    """Every block and every gap between them, end to end. -> `Part`s.

    The whole length of the piece is covered, always. A caller that wants only
    what was supplied filters on `part.supplied`; a caller that draws the lane
    draws all of it, which is what makes "the model scores this stretch" a thing
    the surface says rather than a thing a user infers from a hole.
    """
    parts = []
    at = 0
    for block in blocks:
        if block.at > at:
            parts.append(Part(at=at, frames=block.at - at))
        parts.append(Part(at=block.at, frames=block.frames, block=block))
        at = block.end
    if at < total_frames:
        parts.append(Part(at=at, frames=total_frames - at))
    return parts


def for_window(blocks, window, rules):
    """What one pass is handed: the blocks covering it, on the pass's own clock.

    Clipped to the pass's **sampled** range, not its delivered one — a feathered
    seam re-generates the run it inherits, and those frames need the sound that
    belongs to them or the pass would sample a stretch of picture against the
    wrong stretch of track and the seam would land on a jump. `sampled_at` is in
    piece coordinates precisely so this clip is a subtraction rather than a
    second clock (see `compile.timeline_windows`).

    A block clipped at its head opens later in the file than it was trimmed to,
    so `in_s` moves with the cut. That is the arithmetic worth reading twice:
    the window into the file and the window into the piece are two different
    windows, and only one of them is what the user dragged.
    """
    out = []
    start, stop = window.sampled_at, window.sampled_at + window.sampled
    for block in blocks:
        at = max(block.at, start)
        end = min(block.end, stop)
        if end - at < 1:
            continue
        # How far into the block this pass picks it up, in the file's own
        # seconds — the head clip, converted once.
        skipped = canvas.seconds_for_frames(at - block.at, rules)
        out.append(replace(block, at=at - start, frames=end - at,
                           in_s=block.in_s + skipped))
    return out


def covers(blocks, window):
    """Whether any supplied sound reaches this pass at all.

    Asked before a segment node reaches for an audio VAE decode it may not need:
    a piece with a score over its first shot and nothing after it should not pay
    to encode silence for the other five.
    """
    start, stop = window.sampled_at, window.sampled_at + window.sampled
    return any(min(block.end, stop) - max(block.at, start) >= 1
               for block in blocks)

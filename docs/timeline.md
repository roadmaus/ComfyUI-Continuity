# Timelines

## Adding shots

Under the prompt there is a band labeled **Write the next shot**. Click it and
the piece has two shots, and the node's face becomes a timeline lane,
proportional to the shots' durations. Delete back down to one shot and the
single-shot face comes back. There is no mode to switch.

Each card on the strip is a whole generation with its own prompt, references,
LoRAs, and even its own family: a strip can be H3 throughout, or a pre-stage
on Krea 2 feeding start frames into shots on LTX 2.5.

## Chained vs one pass

- **Chained** (the default) renders each segment and joins them. Seams between
  segments are yours to control, below.
- **One pass** compiles the same cards into a single generation, since both
  video families take a shot list natively. No seam at all, and music or
  dialogue carries across cuts. The tradeoff: one pass means one checkpoint,
  one LoRA stack, one seed and one soundscape for the whole piece, and it can
  only hold what one context window holds. Cards that disagree about those are
  refused with a message rather than silently merged.

## Seams

In chained mode, a seam can continue from any earlier segment's last frame, at
a single frame or as a blend that carries real motion and phase-locked sound
across the cut. How wide a blend can be depends on the family. Picture and
sound cross a cut independently: a hard cut whose score keeps playing, and a
match cut that resets the room tone, are both one switch away.

## Seams and drift

Every continued shot comes out a little brighter and a little harder than
the one it continues, and the next seam starts from that, so the change
walks down a strip. Measured on an 8-hop turbo strip, about three quarters
of it arrives as a step at each cut rather than inside the shots. Three
per-machine settings on the gear's Rendering tab act on it:

- **Turbo lead-in** (on by default, four steps). A turbo LoRA collapses the
  schedule, and the opening steps are where a shot is decided. This runs
  those steps on the base weights with the LoRA held off, then hands the
  rest of the same schedule to the distilled model. Measured: the step at
  each cut falls from +2.86 with it off to about +1.0 at four steps, and
  the texture ratchet falls with it. The cost is those four steps at the
  base weights' speed. Off is the old behaviour.
- **Seam handoff**. What a blended seam hands the next shot. *The latent*
  (default) slices the run off what the sampler made, so nothing is decoded
  and encoded again on the way. *Levelled* pulls that slice back to the
  first shot's tone before the model reads it. *Masked* writes the slice
  into the next shot's own latent and holds it there while the rest is
  sampled, so the model continues the frames it made rather than
  generating new ones under guidance; measured to remove the step at the
  cut on a single sampler, and about twice as fast, but not yet measured
  together with the lead-in. *The frames* is the road every render took
  before any of these, kept for comparison.
- **Seam restore** (per seam, on the blend pill). Re-draws the frames a
  seam hands over against the source shot's own references before the next
  shot continues from them. Helps on raw H3 with a good reference, hurts on
  turbo and low step counts. Off by default.

None of this is zero yet. If you find a setting or a method that measures
better on your strips, open an issue with the per-cut numbers.

## Piece-level fields

The timeline itself carries:

- A **global prompt**: a standing description every segment inherits.
- **Piece references**: files attached to the piece rather than a card,
  addressed as `@ref-1`, `@ref-2`, and so on. Cite one in the global prompt
  and it rides into every segment; cite it in one card and it rides into that
  card alone.
- **Soundscape** and **music**: the two fields that describe the whole piece
  rather than one shot. A segment leaving them empty inherits them.
- **Global LoRAs**, merged in front of each segment's own.

## Locked takes

Every card has a padlock. Locked cards are not rendered, so you can shoot a
long strip one pass at a time, keep the takes you like, and re-shoot only the
card you are working on. Each pass is written as its own file under `takes/`.

## Cutting in your own footage

A clip you already have can be a card on the strip, not just a reference. It
has a length, a place in the order and a seam on each side, and it compiles to
no generation at all: the finished piece simply contains it. Use it for
footage the piece should include as-is.

## While it renders

The progress display shows which segment is sampling ("Segment 2 of 5"), with
a live preview. Cached segments (unchanged since the last render) are skipped
by ComfyUI's own cache, so tweaking shot 4 doesn't re-render shots 1 through 3.

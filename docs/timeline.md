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

# Changelog

## Unreleased

**A piece can be shot a pass at a time.** Every card on the strip carries a
padlock: unlocked is in the next render, locked is not. Write the whole piece,
lock the cards you are not ready for, and render the first one alone; look at
it, render it again if it is wrong, and when it is right lock *it* and unlock
the next. The next render generates that card continuing from the file the first
one already made — segment 1 is never sampled twice. A locked card keeps
everything set on it and is simply not generated, so the strip stays the plan it
always was.

Every render of more than one pass now writes each pass as its own file under a
`takes/` shelf beside the finished video, and hands it back to the card that
made it. That is what a locked card plays instead of being sampled: a take is
spliced into the reel exactly as supplied footage is, and the seam after it
inherits its last frame the same way. A card with an unruled-on take says **take
ready**; locking the card is what keeps it. Edit a card whose take is kept and it
says **kept · edited** — the take still plays, and the card no longer describes
it.

The padlock says a card is out of the render; what the card looks like says what
the lock is holding — solid because the film exists, perforated (the mark this
strip already used for film that has not been through the gate) because it has
not been shot — and a chip names it, **kept** or **not shot**. The bar says what
the next queue will make, *6.0 s next* against the piece's length, and the lane
on the node body shows the same picture at a tenth the size. A lock belongs to a
pass rather than a card, since a pass is one generation and there is no half of
one to lock.

**A card may carry its own seed.** New on the seed pill in a card's editor, and
absent on every card until it is rolled there — a piece is one look and the seed
is the handle on it. Retaking is what needs the exception: re-rolling the node's
seed to shoot one card again moves the number that made the take already locked
in on another, so a take's seed is a fact about the take. The pill says which of the
two numbers is in force, and names the one the card's take was made on.

Asked for in [#17](https://github.com/roadmaus/ComfyUI-MiniMax-Creator/issues/17).

**Clear starts the next scene without taking the setup with it.** A new rail
tool, last in the cluster the add tools are in. It empties what you wrote for
this scene — the prompt, the soundscape and the score, any rewrite over them,
the reference pool, and the strip, which goes back to one blank shot. It leaves
everything you set up once: where the checkpoints are, which LoRAs are patched
onto them, the turbo switch, the canvas, the face pass, the render mode and the
whole sampler row. Irreversible, and one press away from three tools you press
often, so it asks: the first press arms it, the second clears, and five seconds,
Escape or a click anywhere else puts it back. On a piece with nothing in it the
tool is simply unavailable.

## 2.3

Asked for in [#16](https://github.com/roadmaus/ComfyUI-MiniMax-Creator/issues/16).

**Sage attention is a pill on the sampler row.** H3's own attention, run
quantized — int8 queries and keys, fp8 or fp16 values — through Kijai's
`MiniMax H3 Mem Eff Sage Attention Patch` in
[ComfyUI-KJNodes](https://github.com/kijai/ComfyUI-KJNodes). It is the first
accelerator here that is not a trade of fidelity for skipped steps: it changes
what one attention call costs, so it wants *less* VRAM rather than more, and it
composes with every cache and with Spectrum instead of ruling any of them out.
It goes on first, innermost of the patches, so everything else wraps a model
whose attention is already quantized. Off by default, and switched on without
the pack or the `sageattention` library installed it says so before anything is
queued, the way the other accelerators do. NVIDIA only.

## 2.2.1

All from [#12](https://github.com/roadmaus/ComfyUI-MiniMax-Creator/issues/12).

**A piece reference in use is no longer reported as unused.** The reference
shelf says where each one is cited, and it was redrawn only by a full render of
the strip modal — so writing `@ref-1` into a card left the chip on "cited
nowhere yet" for the whole of the edit that cited it, which is the one moment
anybody is reading it. It keeps up with the card now. The other half is the case
that was actually filed: attaching the same picture to a card in its own right
works, and gives the file a handle of the card's own, so the copy on the shelf
is left uncited and the shelf said so — a reference plainly on screen in that
card, reported as used nowhere. The chip now names the card and the handle it
wears there.

**A rewrite writes what it returned and nothing else.** Where the node face owns
the two audio fields, they were taken from the reply unconditionally, so a reply
with nothing to say about the soundscape blanked one you had typed — in a box
you were looking at. The strip has always taken those two only when the reply
carries them; the face agrees with it now.

**The prompt box is read as it is.** Its DOM is meant to be flat, and everything
the box does keeps it that way, but undo restores the engine's own snapshot and
Ctrl+B is the browser's command on a contenteditable. Reading the top level only
meant a wrapper the engine put there cost the line break it stands for, and a
reference chip inside one came back as its own label — written into the state on
the same keystroke. Text dragged into the box is now held to the plain-text rule
that pasted text already was.

## 2.2

**[The face pass](README.md#faces).** H3 draws a face badly in proportion to how
small the head is in frame, and no upscaler reaches that — an upscaler
re-resolves what was drawn, and what was drawn was a smudge. The **faces** pill
on the sampler row switches on a second, small generation per pass: the face is
tracked frame by frame, cropped to fill its own canvas, re-drawn by H3 itself at
a denoise scaled to how large it already is, and pasted back under a feathered
mask. It needs a SAM3 checkpoint, which ships with ComfyUI core; nothing else to
install. Asked for in
[#9](https://github.com/roadmaus/ComfyUI-MiniMax-Creator/issues/9).

**The seed that made this.** `control_after_generate` rolls the seed the moment a
queue goes out, so the number that made the shot on screen is gone from the UI by
the time you decide you want it. The sampler row remembers what was actually
sent and grows a button that puts it back.

**One seed for the piece.** A timeline used to run segment k on `seed + k`, so
the number on the node named the first shot's noise and nothing else: no shot
after it could be reproduced from what the UI showed, and re-ordering the strip
re-rolled every shot below the card you moved. The seed you set now carries
through every segment — chained or single, and through the refine and face
passes inside them.

One fix rides along: the rewrite box no longer loses the caret after every
character ([#11](https://github.com/roadmaus/ComfyUI-MiniMax-Creator/issues/11)).
Typing in it re-rendered the panel that owned it, which rebuilt the very box
being typed into; it is refreshed in place now. The soundscape and score fields
had it too.

### Coming from 2.1

Nothing to do. The face pass ships off, and a piece with it off renders exactly
what it rendered before.

## 2.1

**[Presets](README.md#presets).** A setup you can put back — the whole node, or
the sections of it you tick. Saved off a node you have dialled in, or read back
out of a render you already made, since the file carries the workflow that made
it. The library is on the rail beside Gallery and Settings.

Two fixes ride along. The settings page no longer resets the fields you did not
touch ([#8](https://github.com/roadmaus/ComfyUI-MiniMax-Creator/issues/8)): a
save is a patch over the file now, so naming a video folder stops putting the
stills folder back. And the picker reads what it needs off the directory entry
instead of asking the filesystem three more times per file
([#4](https://github.com/roadmaus/ComfyUI-MiniMax-Creator/issues/4)) — which is
free on Linux and macOS and was not free at all on Windows, where a large output
folder made an upload look like it had hung. An upload also stops re-listing
anything: the file it just wrote is a row it already has, and the renders folder
was never involved.

### Coming from 2.0

Nothing to do. Presets are additive, and a node with no preset saved behaves
exactly as it did.

## 2.0

The headline is that there is one node now instead of two. Update, restart, open
your workflows — they load and render the same. Nothing about a saved piece has
to be redone; see
[Upgrading from the two-node version](README.md#upgrading-from-the-two-node-version)
for what happens to a Timeline node you already placed.

- **One node, one shot or twenty.** The Creator grew the strip rather than
  handing it to a second node. **Write the next shot** under the prompt turns the
  face into a timeline; deleting cards back down to one brings the shot back.
  A Creator render always was a one-segment timeline underneath — the split only
  ever lived in the UI.
- **Two flow clocks on the sampler row.** H3 samples picture and sound on
  separate schedules, and the row now carries both as **shift** pills. They ship
  hidden (Settings → **Nodes**) because most rows never leave the checkpoints'
  own 12/3, at which no shift node is emitted at all; a value off that schedule
  shows its pill regardless. **turbo** presets them to what the LoRA family it
  engages was distilled against, and puts them back on release.
- **Three cache implementations on one pill.** FirstBlockCache and TeaCache from
  the community, plus core's own EasyCache, which needs nothing installed. One
  cache at a time.
- **References citable in the PreStage prompt.** `@ref-2` becomes `Picture 2` —
  the label core's Qwen-edit encoder writes in front of that slot.
- **The render overlay counts passes**, not segments — *Pass 3 of 5* — matching
  what the strip calls them.

# Changelog

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

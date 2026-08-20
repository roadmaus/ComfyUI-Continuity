# Changelog

## 2.10

**A turbo lead-in.** Every H3 distillation LoRA trades the same thing away: the
frames stay good and the model stops listening, because a turbo LoRA buys its
speed by collapsing the schedule and the opening steps are where a shot's
composition and motion are actually decided. **Settings → Nodes → Turbo lead-in**
hands those steps back — one or two of them sample on the checkpoint with the
distillation held off it, then the leftover noise goes to the distilled model and
the rest of the same schedule runs as it always did.

One run, not two: one seed, one step count, one set of sigmas, and the lead-in's
steps come out of the count on the node rather than being added to it. It engages
only where the turbo switch has engaged a LoRA, only when the schedule is long
enough to give steps away from, and only on shots actually wearing that LoRA;
anywhere else the graph is exactly the one this pack built before. The step caches
sit out the lead-in — reusing the opening of a schedule is the thing it exists to
stop — while sage attention stays, since it skips no steps. The refine and face
passes are unchanged: they resume partway down the schedule and the split is not
in them.

**The turbo pill, rebuilt around it.** The switch used to spell the engaged
file's whole name on the sampler row — forty characters of
`minimax_h3_turbo_v4_step600_ema_pruned_comfyui`, the widest thing on the row by
a factor of four, for a decision made once the day the file was downloaded. The
pill reads `turbo` now and names the file in its tooltip, in the picker beside it
and in the weights popover, which is where choosing one already happened.

The room that frees goes to the lead-in, which is settable there: a stepper
reading `lead 2/8` — the steps given back over the steps the run has — sitting
beside the quality stops, next to the `good 8` that set the eight. The fraction
is the whole point, since two of four is half the render on the base weights and
two of eight is a quarter. It writes the same settings file the page does, a
shortcut into one answer rather than a second copy of it.

## 2.9

**A cast.** You can say who is in the video now, and not only which files are
attached. A subject is declared on the piece — a name, the references behind it,
what of them is the reference — and cited in prose as `@anna`, the same chip
everything else uses. It becomes `<Subject N>` at queue time.

That is the split H3's reference guide draws and this pack did not: `<Picture N>`
is a file, `<Subject N>` is who the video contains, and an image that only says
what somebody looks like is meant to be cited *inside* a subject's definition
rather than acting as itself. Four photographs are now one person; a face from a
still can walk like somebody in a clip; an audio reference can be bound as a
subject's voice, speaker ID and all; and a subject can stand in the place of the
person in a reference clip, which is "swap this person for that one" said the way
the guide says it — the `transferred` marker, the clip's own framing and camera
work kept.

Having the facts written down makes two sections derivable that previously could
only ever come from the refiner: `subject_definitions` and `retention_analysis`
are now written by the compiler on the direct path, with the shots each subject
appears in read off the finished description. A claimed picture no longer gets a
definition sentence of its own — it is cited inside the subject that claims it,
which is the guide's rule. Refine is handed the cast pinned: it writes the film
around your subjects and is told to define and renumber none of them.

Citing a subject carries her files into that shot the way citing a piece
reference already carried that file, so a shot that never names her costs
nothing. And a name is a citation only because it was declared: `@anna` in a
piece with no Anna in it is prose and stays prose, so nothing already written
changes meaning.

**The cast shelf, rebuilt, and on the node itself.** It only ever appeared in
the Timeline window, and it refused to open at all until a reference had been
attached — so the one prompt that most needs a cast, a text-only one where a
name is all that keeps the same woman in shot 1 and in shot 9, could not have
one. Cast is on the rail now, beside Add image, on every node; the same shelf is
still in the Timeline window, and it is literally the same shelf.

A subject can be a name and a description with nothing behind her, and the two
sections she makes derivable are emitted in the base modes too — a `<Subject 1>`
written into a description the prompt never defines is a label pointing at
nothing. The base form is otherwise untouched, and a piece with nobody cast
compiles to exactly the bytes it always did.

The card itself is new. What a file lends a subject — her looks, her movement,
her voice, the place she takes — used to be four ghost chips, with the way to
add one a "+" character among them that nobody found. They are thumbnails now,
each wearing the file's own identity hue, each badged with what it lends her,
and one menu behind a tile moves it between the four. The card wears her hue on
its left edge, the same hue `@anna` wears as a chip in the sentence. A subject
nobody has written into a prompt says so, and the readout that says it is the
button that fixes it.

The name and description fields hold the caret, which they did not at first: a
keystroke in a cast field is written straight through to the blob, and writing
to the blob is what redraws the node — so the field was rebuilt between one
letter and the next and you could type exactly one character. The shelf refuses
to redraw while it holds the caret and catches up on the way out, the same
bargain the prompt box and the refine panel already make. Leaving a field defers
its redraw by a turn of the event loop, so a ✕ or a tile clicked while a field
has the caret is not pulled out from under the pointer.

## 2.8

**A start frame beside its references.** Frames and references used to lock
each other out — attaching one greyed the other, and a strip could not merge a
keyframe shot with a reference shot. The lock is gone at every level: a
generation takes a start frame, an end frame *and* references (images, video,
audio) in one request, a globally cited piece reference rides into a keyframe
segment, a reference shot can end on a clip, and one pass holds all of it. The
frames ride as guides pinned at the clip's own first and last frame — the same
mechanism the continuation seam has always used, which Ref2VA reads alongside
its references — presented after the references so every `<Picture N>` a
cached prompt already has stays put, with an alignment line naming the
ordinals the frames took. Forcing the FL2VA slot onto a reference generation
is honoured now too, instead of refused: the slot names what you loaded into
it, and merges of the two trainings exist.

**The aspect ratio, from any input.** The canvas used to take its shape from
the start frame or the first clip whether you liked it or not — the ratio pill
went dead the moment a keyframe existed. The pill is always live now, and its
popover starts with the ratio's *source*: Auto (the rule that always held),
then every attached picture the piece holds — frames, reference images and
videos, clip cards' footage, pool references — each drawn at its own shape,
with the presets beneath them to force over the lot. Choosing a preset while
pictures are on offer writes the choice down, so footage can no longer quietly
outrank a ratio you just picked.

## 2.7.1

**A stage that can hold still.** Every preview used to start playing the moment
it existed, and on a canvas with a dozen finished renders that is a dozen
looping clips decoding for nobody. Settings → Nodes now offers Preview
playback: leave it on Plays itself and nothing changes; set it to Waits for
play and the stage holds a clip's first frame, still, with the browser's
controls to start it — sound on hover and looping unchanged once it is. Covers
the finished render and the animated step previews alike, and it is
per-machine like the rest of the settings file: the workflow says what the
piece is, not how your canvas behaves.

## 2.7

**Any template pins onto any request.** The refiner used to refuse a pinned
REF2VA template on a request without @ references, and a base template on one
with them — a first frame plus an always-REF2VA pin got an error instead of a
rewrite, even though the checkpoint handles that prompt fine. Both refusals are
gone: every pin is honoured, and a pin across the reference boundary comes back
with a hint in the result panel saying it may degrade quality, alongside the
rewrite rather than instead of it.

## 2.6

**Shoot one card, then the next.** Building a piece one expensive generation at
a time meant locking five cards to shoot the sixth, then unlocking one and
locking another for every step after it. A card's number on the strip is now the
way to say it: click the 4 and card 4 is the only thing generated, everything
else locked and left exactly as it is. Because a card locked with a take is a
card playing that take, clicking the next number keeps what you just shot and
carries the strip forward — one click per card, for the whole piece. Clicking a
number inside a merged run shoots the run, a pass being one generation. On a
strip that is a single generation the numbers stay what they were, there being
no "only" to ask for.

**Lock all, and unlock all.** The two ends of that, which going card by card
never reaches: lock everything and the next render generates nothing and writes
the piece out of the takes it already has, which is how a piece shot in parts is
finished. Unlock everything to put the whole strip back in the pot. They sit on
the bar beside Refine all, appear once the strip is shooting in parts, and Lock
all goes dead while there is nothing shot to assemble from.

**A take can be turned down.** Looking at a take and deciding against it is half
of shooting in parts, and the only way to say so was to render over it. The chip
that names a take — kept, take ready, kept · edited — now carries a ✕ that
forgets it: the card goes back to not shot, and the file stays under output/,
because this is a card saying the take is not the one rather than a file being
deleted. It is out of sight until the card is under the pointer, so a strip of
finished takes still reads as film.

**A card shot by itself is still a card of a piece.** Shooting one segment,
keeping what came back and moving on to the next is the whole point of the lock
— and it never worked. The take a render writes out was written only where the
render had more than one pass in it, which a strip with five cards locked and
one open does not: the take never landed, so the card could not be kept, so the
next render was one pass again, and the strip never got off the ground. Every
place that asked "is there one pass here" was really asking "is this render the
whole piece", and those stopped being the same question the day a card could be
held back. So a card shot alone now writes its take, says which card it is while
it renders, and is named by its own number in anything it raises — while a strip
genuinely generated in one go is still one generation with one take, which is
the render.

**A seam cannot inherit from a card that is not in the render.** A locked card
with nothing to play is dropped from the render, which moved the card behind it
up and left its seam pointing at whoever now sat in front of it. Shooting card 6
with cards 4 and 5 still unshot opened it on card 3's last frame and said
nothing about it — a shot that looks right until the piece is assembled. It is
refused now, naming the card it wanted and the two ways on: shoot that card
first, or turn off the seam and start fresh. Which is also the rule for shooting
out of order, finally stated — a card behind a cut shoots whenever you like, and
a card behind a seam waits for the one it continues from. The strip says it
while the cards are still in front of you rather than at the queue.

**A named seam source follows the card it names.** Pointing a seam at a
particular earlier card recorded that card's number on the strip, and the
render read it as a position in the render — the same number until something
earlier was held back, and a different card after that. It is rebased now, so a
seam keeps meaning the card it was aimed at however much of the strip is
locked.

**A card compiles to the same generation however it is shot.** Four things the
strip records about a card — the seed it ran on, the take it has, whether it is
locked, and its number — were being folded into the description handed to the
model, which is what the segment's cache is keyed on. Nothing about the picture
changed when they did, so re-rolling a seed re-encoded the references it was not
changing, and shooting one card of six re-encoded all six. They are kept out of
it now: the conditioning behind a card is reused whenever the card still says
the same thing.

## 2.5

**A folder browses as a folder.** The row of places above the gallery used to
list every subfolder the input or output folder held, flattened — a nested path
was its own chip, and the row wrapped until an output folder filed by day and
take was more chips than gallery, with the pictures pushed off the bottom of
the modal. It is one line now, whatever is in there: a trail on the left saying
where you are, and beside it the folders one step inside, scrolled sideways
when there are more than fit. Clicking a folder goes in, and the grid shows
everything under it however deep, so the chips narrow rather than dead-end.
Leaving is one click on any step of the trail, dragging a file onto a step
moves it there, and the "+" makes its new shelf inside the folder you are
looking at. The preset library's shelves scroll on one line too, and the
Move to… menu reads as the tree it is.

**The picker opens where you left it.** Each root remembers its own folder — one
for the input tabs, which share a folder and so share the place in it, and one
for the gallery — and the next opening lands there with the trail already
showing, instead of at the top of a folder you then have to find your way down
again. It rides in the same prefs file the stars do, so it follows the ComfyUI
user rather than one browser, and a remembered folder that has since been
renamed or removed quietly falls back to the whole folder.

## 2.4

**A reference's scope can now reach the model, not just the refiner.** The
`full · person · object · scene · style` dial has always been prose or nothing —
H3 has no reference-conditioning switch, and the DiT is handed the same tensor
whatever the chip says — but until now the only thing that read it was Refine's
glossary, so a piece queued without a rewrite had the setting quietly do
nothing. Settings → Nodes → **Reference scopes in the prompt** turns on a second
reader: the compiler writes one sentence per reference in front of the
description, saying what that file lends and what it does not. The sentences are
shown in the prompt box above your own text, so what gets sent is readable while
you are still setting the chips. Off by default, and dropped entirely when a
refined reference form is what is queued — that form defines its own labels in
`subject_definitions` and scopes them in `retention_analysis`, and two
descriptions of one reference is worse than none.

**Audio references get the dial too.** `full · voice · music · ambience · copy`,
which are the roles H3's reference guide gives an `<Audio N>`. `voice` carries a
timbre and a delivery onto whoever speaks without carrying the words, `music`
and `ambience` reference a style or a texture without reusing the recording, and
`copy` says the signal itself is the video's own audio — the difference between
an `audio reference` task-type prefix and an `audio reuse` one, and between
`reference` and `fully_copy` in the retention lines. A clip taken for its
soundtrack alone scopes here rather than with the pictures, which is a change:
it used to be refused a scope outright on the grounds that it had no picture
left to narrow, and it turns out the thing it does have is a sound.

**A reference clip now says what it lends.** The scope dial that reference
images have had — `full · person · object · scene · style` — is on video chips
too, with four more values that only a moving picture has. `motion` lends the
action alone and carries it onto whoever the prompt puts in the shot. `camera`
lends the move, the cuts and the pacing, with nothing visible in the clip
appearing. `edit` says the clip *is* the video being edited, which is how you
replace one subject and keep everything else. `continue` picks the video up
where the clip ends. Each one becomes a different label in the rewrite: the
content takes and `motion` mine the clip for a `<Subject N>`, while `camera`,
`edit` and `continue` ask for the `<Video N>` entry, retention marker and
task-type prefix H3's reference form gives whole-video relationships. The dial
opens as a menu now rather than cycling, on the card's chip and on the
timeline pool's alike, and a clip taken for its sound alone has no dial — there
is no picture left to scope.

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

**941 looks on a style tab in the preset library.** A fourth scope beside piece,
shot and pre-stage, holding every distinct visual style in the `ostris/minimax_h3_1k`
dataset as indexed by hoodtronik's [Style Atlas](https://github.com/hoodtronik/minimax-h3-style-atlas)
— grouped into eight media categories, each card a still off the clip the phrase
was read from. These are the exact strings H3 was captioned with rather than
adjectives we thought of, so applying one puts a phrase the model has seen a
thousand frames of at the front of your prompt. It *swaps* rather than replaces:
a style already leading the prompt comes out as the new one goes in, so six looks
tried on one shot is six prompts and not six stacked paragraphs. Nothing else
moves, and it lands on a piece, a card or a PreStage alike. Vendored — the index
and one still per clip, about 5 MB, no video and nothing fetched at runtime — and
`tools/vendor_style_atlas.py` re-reads a fresh clone when upstream grows.

**A trimmed clip and an unnarrowed one no longer say the same word.** An
untrimmed video reference read `@vid-1 full sound on full max` — "full" for the
whole duration, and "full" again two pills along for a reference nobody has
scoped. The duration one is "whole" now, which is what the trim editor's own
tooltip has always called it.

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

# Changelog

## 2.15

**A look you cast is a look you can click.** Three things were wrong with it and
all three were silent. The atlas was only read when its tab was *pressed*, so
opening the library straight onto Style — which is what the new `/` door does
every time — left the grid on its empty line, and that line said "The style atlas
could not be read" about a read nobody had started. A look is cast under a handle
that has to open on a letter, and a quarter of the atlas opens on a number, so
"2D cutout-paper stop-motion" arrived as `@subject` while the button that cast it
promised `@2d_cutout_paper` in its own tooltip. And nothing wrote the name into
the sentence: the tooltip told you to go and type it yourself, so there was no
chip to click even when the name was right.

Now the frame casts itself in: `@look_2d_cutout_paper` leads the prompt as a
chip, on the prompt the node is actually showing. Click it to edit the look,
delete it to take the look off the node — picture and all. And casting a second
look replaces the first rather than stacking on it, which is the promise the old
descriptor-swap made and this had quietly stopped keeping.


**A name is a door, in every box that draws one.** Clicking somebody's name in
the sentence opens their card — that was true on the Creator's face and nowhere
else, so the Timeline window's standing prompt and a card of the strip both drew
chips that changed the cursor and then did nothing. A card's editor was worse
than dead: it looked the piece's subjects up on the segment, found none, and
deleting a chip there took nobody out of anything. Both are wired now, and a
card knows whose cast it is holding. A style is a subject like any other — it
opens the same shelf and leaves the same way, by deleting its name.

**One reference, one door.** A reference chip used to carry four small buttons —
what of the file is the reference, what part of the clip, its soundtrack, its
encode size — and the simple fullscreen view hid any of them still holding a
default. That is exactly the answer you are trying to leave, so a picture
attached in that view could not be made a style reference at all. The chip now
says only what somebody *set*, and its handle opens a card with all of it: the
same card on a node face and in either fullscreen view.

**`/` — where a thing comes from.** `@` cites what this piece already has. `/`
is the layer above it: the style atlas, the cast library, the input folder.
Typing after it searches all three at once, so `/cla` finds Clara, Claymation
*and* clay-turntable.png without choosing a branch first; the arrow keys go in
and back out. Every row ends in a chip.

The Style branch searches all 941 looks by their whole descriptor — so
"grindhouse", "needle-felted" and "anamorphic" find their entries from the
middle of one — and each row carries the frame it was cut from, so you are
still choosing by looking. Picking one uploads that frame, casts the look, and
writes its name where you typed the slash. The atlas is read the first time a
slash asks about looks and never again, and the way into the full catalogue is
still the last row of the branch.

**The Sampling settings toggle works on the Timeline and the pre-stage.** The
simple view folds the sampler row away by a class on its host, and only the
Creator body carried one: the Timeline mounted its bar straight onto the root and
the pre-stage's host had no class at all. Pressing the button on either did
nothing, which is what the screenshot showed.

## 2.14

**The node can have the whole window now.** Settings → MiniMax H3 → Editor →
Fullscreen, or Ctrl+Shift+M, and the Creator's face stops being a rectangle on a
canvas and becomes the screen: the body in a column at its own width, the picture
beside it at its own size rather than scaled to the zoom, and the PreStage — when
one is spawned — in a column of its own to the left, still the direction the
hand-off runs. Escape and the button in the corner go back to the graph.

Nothing is duplicated to do it. The body is the same element the node mounts, the
blob is the same hidden widget, and the node stays in the graph the whole time —
so the piece is still what `graphToPrompt` serializes and still what the server
runs, and the workflow you save from fullscreen is the workflow you always had.
The node's own title is the piece's name, because LiteGraph already lets you
rename it and already saves it, and inventing a second name would have meant two
that could disagree.

**The title bar wears the pack's own mark.** It was drawing `timeline`, a rail
glyph that means "the strip" everywhere else it appears, next to the words
MiniMax H3. It is the icon the Comfy registry lists the pack under now — the
same artwork, inlined rather than fetched, so the shell does not go to GitHub to
draw its own corner.

**A Render button, and a Cancel.** ComfyUI's are behind the shell, so the piece
grows its own at the foot of its column, and the button is the queue readout as
well — it turns into the step count while it samples and puts a Cancel beside
itself. Both call exactly what the toolbar calls, `queuePrompt` and `interrupt`;
neither reimplements a queue. The Gallery and the Settings page are *not* in the
title bar: they have been in the body's own rail all along, and a second copy
would be two doors into one room.

**Two views over the one shell.** The switch is in the title bar. *Full* is the
desk described above — the pre-stage, the shot and the picture side by side,
which is what a piece built out of parts actually looks like. *Simple* is the
other half of the day: one card, for when the piece is one prompt and everything
else is in the way. Nothing that the render reads is hidden in it — the rail,
the references, the cast and the shot's own pills are all still there; the
sampler row is folded, because it is the row you set once and then stop looking
at, and *Sampling settings* beside Render brings it back. Which view you were
last in survives a reload.

**And the simple view opens as you use it.** The card sits in the middle of an
empty window while you write, and the moment you press Render the picture column
opens beside it and the card slides left to make room. It is the same two regions
the desk has, in the same places — writing on the left, picture on the right —
with the difference that the right-hand one is not there until there is something
in it. Nothing appears at a new address, either: the card is on rails between two
positions in one centred row, so opening the column *is* the movement, and there
is no second layout to keep in step with the first. Reduced motion gets the two
positions and nothing between them.

**And it stays simple once you have used it.** Cast somebody, attach a clip,
narrow a reference, and the card that was one prompt in the middle of a window
became four rows of chips over a paragraph of explanation. Every one of those is
right on a node face, where it is the only place the thing can be said, and
wrong in a view whose whole point is that there is one thing on screen. Three
things go, and none of them is a control you cannot reach:

*The cast shelf, and the Cast tool with it.* Everything the drawer does is
already somewhere else and better placed in this view. Casting somebody is the
@ menu's roster — it reads the cast library, and picking a name there attaches
their pictures and writes the name into the sentence in one gesture, which is
shorter than finding them in a drawer, casting them, and then going to cite
them. Building or editing somebody is the library's Cast tab, which has New cast
member, the sheet for their description and their files, Export and Delete, and
sits two tiles along the rail under Presets. And taking somebody out is deleting
their chip: `compile.py` cuts the cast down to the subjects the text actually
cites, so a member nobody writes is not in the render. What was left was a
drawer listing people you can read off the sentence you wrote.

The one thing none of those covers is editing the copy of somebody that lives in
*this* piece — the library sheet edits the library's copy, and casting them again
makes a second person rather than updating the first. So **click their name in
the prompt** and the shelf arrives on them alone, with nobody else open; their
own chevron takes it away again. The chip is `contenteditable="false"`, so a
click on it had nowhere to put a caret and did nothing before, which makes the
gesture free as well as right: the name in the sentence is where somebody is
used, so it is the shortest way to ask what they are made of. It wears the
pointer and lifts under it, everywhere the gesture actually lands — a card's
editor is one shot of a piece whose cast is owned a level up, and there the chip
stays a chip. Deleting one is unchanged: caret, Backspace.

*And the cast's own pictures stay out of the reference row.* Casting somebody
attaches their files, so one person in a shot grew a chip saying what the @name
in the sentence already says — and in this view the sentence is the only place a
subject is written, which made the chip a second and worse copy of it. The row is
what *you* attached now: the frames, the footage, the references. Empty of those,
it goes with them rather than leaving a gap where it was.

*The band that spells out what each reference narrows to*, and the shelf's
standing sentences with it. They describe what the controls beside them already
say, and none is the only place a fact is written. (That band is opt-in in
Settings to begin with.)

*Any narrowing nobody changed.* A reference chip's four — the trim, the
soundtrack switch, what the file is taken for, the reference canvas — now say
whether they are still holding their default, and the simple view shows only
what somebody chose. So `@vid-1 whole sound on full max` is `@vid-1`, and a clip
you trimmed to eight seconds still says so.

The dashed "write the next shot" rule goes too: growing a strip is the timeline's
gesture and the Timeline pill is still in the row. Everything dropped is one
press away in the full view, and none of it is dropped from the render — these
are display rules over the same bodies, drawing the same blob.

**A pre-stage is a step there, not a second panel.** There is no room beside one
column for another one, and there should not be — the pair is a sequence, make
the still and then make the video out of it — so a switch at the top of the card
says which half you are writing and the card shows it. Both nodes stay in the
graph; the step changes what is in front of you *and* what Render makes. Grabbing a frame or sending a still to the shot moves the card
to the shot on its own, because that hand-off is the whole reason the pair
exists. The switch is also the only pre-stage control the simple view has now:
pressing *Pre-stage* when there is none spawns one and takes you to it, and the
✕ on the step you are standing on removes it. The amber pill in the shot's own
row that used to do the spawning is gone from this view — two controls over one
node was one place too many to look. The desk keeps it.

**Render makes one thing, not both.** A PreStage is an output node of the same
graph the shot is in, so queueing the graph runs the pair — which is right for
ComfyUI's own Run button, and wrong for a button at the foot of one column that
reads as being about that column. Touching the still's prompt and pressing
Render made a still nobody had asked for, and there was no way to remake the
still without also remaking the clip built on it. Each press now names its node,
through ComfyUI's own partial execution. In the simple view Render runs the step
you are standing on; on the desk, where both are on screen, the pre-stage column
grows its own *Render still* under the thing it makes. Queue both and they queue
in the order you pressed them, which is the order the hand-off runs.

**And the desk itself is laid out again.** Three regions used to be three
stripes, ruled edge to edge by hairlines and all weighted the same, which is a
window with no place to start reading. They are cards on a ground now, and only
one of them is raised: the shot you are writing. The pre-stage sits quieter
beside it because it is the step before — a card on the ground where the shot is
lifted onto a surface, rather than a rail, a prompt and a sampler row lying loose
on the desk with nothing round them — and the picture's dock has room around it
instead of a border ending in mid-air. Each column says what it is at the top,
because both faces are built out of the same parts and, unlabelled, the first
thing the eye met on the left was a second copy of the toolbar it was already
reading on the right. Read across, the desk is pre-stage, then shot, then the
picture they make.

The dock's empty frame is also drawn for a Creator and a Timeline now, and not
only for a pre-stage. It never was: the body those two nodes wear could not
answer what canvas it was about to render at, so the whole picture column stayed
blank until the first render landed in it. The box you type into is the one
recessed surface in the room — cut into the card rather than laid on it — so the
eye finds the writing without anything having to be coloured to say so.

The pills are the same pills, in the same colours, with two things taken away
that were only ever noise on a screen: a lit chip keeps its colour in its text
and its border and gives its tinted fill back, so the one saturated area left in
the window is Render; and the sampler's numbers are ruled off from the shot's,
which is most of what made a dozen chips in one heap unreadable. On a node face,
where two or three are on at once and the rail is most of the width, nothing
changes.

**Every render this session made, up the scroll.** The stage is one box and
`execution_start` clears it, which is right on a canvas — a card beside a node
still showing last week's render while this week's samples would be a card that
lies — and exactly wrong in a window with room for both, because the reason you
queue a second take is to look at it beside the first. The picture column is a
reel now: oldest at the top, the live stage at the bottom nearest the writing,
and it scrolls itself down whenever something arrives, so what just happened is
where you were already looking and history is a scroll rather than a mode. Past
takes do not play themselves — ten clips going at once is not history — and
nothing is copied: an entry points at the same file the Gallery opens, so
closing the editor loses the list and not one render.

**A finished video no longer lands on top of the tool rail.** The card is
`position: relative`, and the writing column below it was not, so anything that
got out of the picture column was painted over the rail rather than under it.
The reel's own scroll is the containment; the column is positioned as well, so a
leak would at worst be visible instead of covering a control.

**Add a card and you can get back.** Growing a strip moves the cast's pictures
into the reference pool — they are on card 1 otherwise, where no other card can
see them — and there was no way back down. So a Creator that had ever held two
cards kept a pool forever, and a pool is one of the fields a shot's face has no
row for: the node stayed folded into the strip summary with the toggle drawn
dead over "the reference pool", naming a field nothing on that face could empty.
Shrinking back to one shot now moves them home, handles and citations and all —
the promotion run backwards, with the same filter, so a reference attached to the
whole piece on purpose still belongs to the piece and still holds the strip.

**One height for everything pill-shaped.** The route badge was padding-sized, the
strip's open button was 32px and the pills around both were 38px, which read as
three unrelated things in a row rather than as a row. `--mmc-pill-h` is the one
number now, and the next control cannot quietly be a fourth.

**A docked render is not cut off any more.** The card carries a flex direction
but never `display: flex` — on a satellite it does not need one, because the
card's height is the node's and the picture is sized off that height alone. In a
column the card is sized by the column instead, and without the flex the row
inside it had an auto height that no percentage could resolve against, so the
picture went to its own pixel size and the card's `overflow: hidden` took off
whatever stuck out. The row is a flex row in the dock now, and it is allowed to
be narrower than what is in it.

The caps the face wears — two rows of chips, then scroll; ten lines of prompt,
then scroll — lift inside it. They were there because a node face is a preview
that must not grow the node, which is not true of a screen. And the frame the
dock draws before the first render is a frame you can see now: a hairline at
rgba(255,255,255,.16) across a third of a large screen is a line you have to go
looking for, and a dock that reads as empty is the thing that element exists to
prevent.

**Render queues; it no longer locks.** The button disabled itself the moment it
was pressed, so lining up three takes and going to make coffee — the whole reason
ComfyUI's own Queue button does not do that — was refused. It stays pressable
while a render runs. What it says meanwhile is a status, not a lock: *Sampling*,
the step count, and how many are behind it.

**And Cancel is heard.** Interrupting a render left the button reading *Sampling*
forever, with no way back to a button short of closing the editor. The stage was
listening for the two ways a run can end, `executed` and `execution_error`, and a
cancelled one sends neither — it sends `execution_interrupted`, which nothing was
listening for. It is now, and the stage clears rather than leaving the last
sampled frame up: that frame is a step of a video that was never finished, and a
stage still showing it reads as a render that landed.

**Deleting a mention deletes what it named.** The @ menu is how a file is
attached in this redesign and how somebody is cast — picking one writes the chip
and creates the thing in one gesture — so the chip *is* the attachment, and
deleting it has to be the way back out. It was not. The file stayed on the
reference row and the member stayed on the cast shelf, both of them invisible to
somebody who had just taken them out of the shot.

Worse for a plain reference: an uncited cast member is cut at queue time and its
pictures with it, but `@img-1` is in `assets`, and everything in `assets` is
encoded and shown to the model whether or not a word of the prompt mentions it.
So deleting the name left a picture conditioning the render exactly as hard as
one the prompt still named. Both are now taken out with the chip.

Only what is no longer written anywhere: a handle the same shot still cites from
its soundscape, or another card of the same piece still cites, stays — the
deletion was of one occurrence, not of the reference. The piece's reference pool
is untouched by this, because it never needed it: an uncited pool asset is
already not injected into any generation. And the diff is over *chips* rather
than over text, so typing your way through a hand-written `@ref-1` never detaches
anything on the way past — a chip is `contenteditable="false"` and is the one
thing in the box that can only be deleted whole.

## 2.13

**A LoRA can be switched off now, instead of only thrown away.** The stack was a
row of names with one control on it — the ✕ — so the ordinary question "is this
LoRA the reason it looks like that" cost the strength you dialled in, the
checkpoint you pinned it to and the trigger words you edited, every time you
asked it. The name is the switch now: click it and the LoRA is out of the run,
off the checkpoint, its trigger words off the front of the prompt, and everything
you set up still sitting on it; click it again and it is back. The flag has been
in the blob and in `compile.py` since the beginning — nothing in the interface
ever wrote it. Muting the file the turbo switch owns counts as turbo off, which
is what it is.

**And swapped for another, in the same slot.** The shuffle button beside the ✕
opens the LoRA grid as a one-shot picker: one click and the file you pick takes
that entry's place, keeping its position in the patch order, its checkpoint and
its muted state, and taking strength and trigger words from its own sidecar —
0.6 on a character LoRA and 0.6 on a distill are not the same number. Which
makes trying the other version of a style two clicks rather than a removal, a
search and a re-dial.

**The timeline had no LoRAs in it at all.** The strip window drew a pill counting
the stack and nothing naming it, so on a piece with a global LoRA there was no
mute, no strength and no filename anywhere on screen — the only way to find out
what was patched onto every segment was to open the manager over it and read the
lit cards. It draws the same chips the Creator face does, under the bar, and the
node's own strip face carries the names beside the count. One implementation of
that chip now, shared by all three faces, rather than two near-copies and a hole.

**Clear takes the cast with it.** It emptied the prompt, the references and the
shots and left the people behind — a shelf of subjects no `@handle` in the piece
named any more, each of them still pointing at reference files the same press had
just deleted, and all of them still riding down onto the blank card the piece
went back to. The cast is written alongside the prose that cites it and goes with
it.

## 2.12.2

**Deleting a cast member no longer saves them on the way out.** The sheet flushes
on close, and the flush ran against the row that had just been deleted — writing
their body file back and then reading an index row that was gone.

## 2.12.1

**Pasting a prompt no longer pastes a node.** ComfyUI decides a paste belongs to
the graph by asking whether it landed on an `<input>` or a `<textarea>`. The
prompt box is neither — it is a contenteditable, because the `@` references are
atomic chips a textarea cannot hold — so every Ctrl+V at a caret in there also
dealt out whatever was last copied on the canvas. That clipboard lives in
localStorage and outlasts restarts, workflows and subgraphs, so what landed was
often a node copied weeks ago, once per paste, stacked on the Creator and only
found on the way out of the editor. The box now keeps its own paste to itself,
and its copy and cut with it. One consequence worth knowing: pasting an image
while the caret is in a prompt box no longer builds a LoadImage node, because
that went the same way. Thanks to @MrUSBEN for the report (#22).

## 2.12

**Every LoRA now loads the way a quantized H3 needs loading.** The stock path is
dequantize, add the delta, requantize with a recalculated codebook — a round trip
that is not idempotent. It injects about 1.5% relative weight noise where a
typical H3 LoRA delta is 0.01–0.08% of the weight, so on the int8 and w4a8 bakes
most people run, the adapter was being replaced by rounding noise. It is also two
orders of magnitude slower than not doing it. Two more things went wrong without
saying so: H3 ships in a dense and a curve adaLN form, and a LoRA trained against
one has the wrong `lora_A` width for the other, so ComfyUI dropped those pairs —
on a distillation LoRA that is most of the adapter — and the five key conventions
H3 LoRAs are published under do not all survive being split on underscores.

So this pack now ships cicalooo's
[ComfyUI-H3-PowerLoraStack](https://github.com/cicalooo/ComfyUI-H3-PowerLoraStack)
library (Apache-2.0) and loads through it. Quantized layers get an exact runtime
low-rank branch — `y = W_q(x) + B @ A @ x`, the quantized kernel untouched, about
1.5% more FLOPs at rank 64 — instead of a merge. adaLN is changed of basis rather
than dropped. Keys resolve against the model's own key set. A stack of several
LoRAs fuses into one pair per layer rather than one per file. There is nothing to
install and nothing to switch on: it is the path, the way it should have been all
along. Everything the loader did is in the console — what merged, what branched,
what the adaLN port managed, and how far each file's real perturbation is from
the strength you gave it, which is the number that says a LoRA is being run at
five times the strength its author meant.

Vendored rather than wired in, which is the opposite of what this pack does with
the caches and Spectrum, and for the opposite reason: those are accelerators, off
by default, and a copy of somebody else's tuning goes stale. This is not optional
and not tuning — it is what correct looks like — and a user who did not install a
pack would have got all three failures silently, with a finished render and no
sign anything was wrong. Two open findings from upstream's own audit are fixed in
the copy: a shared adaLN basis that handed the second curve LoRA of a stack the
first one's fit, and a table-to-table fit that raised on a model whose table was
on the GPU. `h3lora/__init__.py` says what changed and `tools/vendor_h3lora.py`
re-syncs it, patch and all.

**The attention pill is a list now.** Sage was a switch, and switches are the
wrong shape for a slot that holds one thing: a model has one attention, and core
now ships its own int8 kernel through `ModelAttentionBackend`. So the pill offers
**default**, **sage** and **kitchen**, and picking one is what turns the other
off. Kitchen needs nothing installed — no NVIDIA-only package, no build step —
and appears only on a ComfyUI whose build can actually run it; asked for on one
that cannot, it says so rather than quietly sampling on pytorch attention, which
is the render you did not ask for, finished. A workflow saved with the old switch
on still runs sage, once, and then the list is what decides.

**Two more pills, both about what a step costs rather than how many run.**
**low vram** splits H3's feed-forward over the packed sequence (KJNodes' Chunk
FFN), which lowers the peak a render has to fit in and is the only accelerator
here that trades nothing at all — activations are quantized per token, so
chunking is arithmetic rearrangement and the frames are the ones you would have
had. **fast math** lets cuBLAS accumulate fp16 matmuls in fp16 while this model
runs (KJNodes' fp16 accumulation) and puts the flag back afterwards — and it is
worth saying where that reaches, because it is narrower than it sounds: fp16
matmuls only. The released H3 checkpoints run bf16, and their quantized layers
go through comfy-kitchen's own kernels rather than cuBLAS, so on the bakes
nearly everybody runs there is nothing for it to change. It is on the row for
the fp16 model that would use it, and its tooltip says all of this rather than
leaving it to a stopwatch. Both compose with every cache, with Spectrum, and
with either attention backend, and both survive the turbo lead-in — they skip
nothing, so there is nothing for the lead-in to protect. They are named for what
you get rather than for how they are built; the packs' own names are in the
tooltips, where somebody looking for them will find them.

**And the sampler row has a length now.** It has grown a cache, Spectrum, an
attention backend, a turbo switch with a lead-in inside it and those two, which
is a lot of row to read past on the way to the seed. **Settings → Nodes →
Advanced controls** decides how much of it a node draws: **Standard** is the
row most renders use, **Everything** adds the turbo lead-in, low vram and fast
math, and the turbo lead-in section to that page. It hides, it never disables —
a control already switched on keeps its pill either way, which is the rule the
shift pills and the custom quality row already live by, so turning it off can
never change what a render does.

**A style is a look now, not somebody else's scene.** The Style tab's 941
descriptors are the opening clause of a dataset caption, split at the first
action beat — so a third of them carried the clip's cast and setting into your
prompt along with the medium. Seventy-two shipped a literal `(S1)`, the dataset's
own subject token; a hundred and sixty-one were cut off mid-word at 250
characters, because that is where the atlas page truncates. Asking for LEGO also
asked for a chef minifig and a stovetop fire. The clause chain is now walked and
stopped at the first clause that is about *something* rather than about how it
looks — 333 of the 941 are shorter, none came out empty, no `(S1)` survives and
the truncations are down to eighteen. It is a cut, never a rewrite: nothing is
invented and no clause is reordered, the verbatim descriptor is still what the
search reads, and the inspector shows it under **What the clip's own caption
said**. A prompt written before this still gets its long descriptor swapped out
when you apply a style over it.

**And a style has a picture you can actually use.** The card stills are 192px —
enough to tell one look from another, not a reference. So one frame per clip is
now vendored at the clip's own resolution, 512 to 1088 across, and **Cast this
frame as a look** attaches it as a `takes: "style"` subject with the distilled
descriptor as its description. This is the answer to "where do I find a still of
a 1972 educational puppet show": you do not, the atlas has one. Both sizes are
cut from the same frame of the same clip at vendor time, so the card and the
reference are one moment rather than two. Nothing streams — the frames are on
disk and the whole catalogue works with the machine offline, which is why they
are vendored rather than fetched on demand.

**A cast member is made where you look for them.** Keeping somebody used to mean
four surfaces: attach a picture to a node, add a subject on that node's shelf,
point the subject at the picture, press **★**. Three of those are about a node,
and a member is deliberately not about a node — their files are stored by
filename precisely so they outlive the graph they were built on. So the roster
makes its own. **+ New cast member** opens an editor over the grid: their face
and handle, what they are, their files as tiles you press to say what each one
lends them, and their description as a box rather than the line the inspector had
room for. Nothing there reads a node, and there is no Save — the row exists from
the moment you press New, so every edit is a change to something already in the
library. The **★** on a node still works; there are two ways in now rather than
one. Their description reaches their card too, so a roster of twelve is scanned
by who somebody *is* rather than by how many files are behind them.

**Removing somebody takes their pictures with them.** Casting attaches files —
the `+` on their card does it, and so does taking them out of the library — so
the **✕** undid half of what it was undoing, and the node quietly accumulated a
picture every time you changed your mind, each one needing to be found on the
asset row and removed by hand. Now it takes what that member alone was built out
of. Not a picture a second member is also built out of, not a file a prompt
writes by hand as `@img-2`, and never the piece's pool from inside one card of a
strip.

## 2.11

**A cast you can keep.** A subject was built by hand on every node they appeared
on, which is how the same person becomes three slightly different people across a
project. The **★** on their card writes them into a cast library — their name, their
words, their retention marker and their references *by filename* — and **From the
library** on the shelf head brings them back into a piece that never had their
pictures attached. Their files attach as they land, as *ordinary references*: an
image of them is an image reference in the reference row under `img-2`, sizeable
and removable like anything else you attached. On a piece of one shot they land
on that shot; on a strip they go to the piece's pool, which is the one list
several cards can cite. A file already attached is used rather than attached
twice.

They have a tab of their own in the preset library, the fourth one: a roster, one
card per person, their own picture as the hero and *person · 2 pictures · voice*
under it. Select them and the panel shows every reference at a size you can
recognise somebody at, captioned with what it lends them, over **Cast @anna into
this piece**. Nothing is captured off a node there — a person is kept from the
card you are looking at them on — so the tab has no *Save current setup* and no
*From a render*, while Import and Export work as they do everywhere else.

Keeping them twice keeps them *over* the standing copy: a name is who somebody is,
and there is one of them. Casting them into a piece that already has an `@anna`
lands them as `@anna_2` instead, because two subjects of one name is a piece where
the name means neither.

**And the way in is the sentence.** Type `@ann` in any prompt and the roster is
in the menu under **Cast library**, below whoever is already cast — their own face
on the row, and *person · 2 pictures · voice* under their name. Picking them casts
them and writes their name in one press: their files attach as references, and their
name is written in at the `@` you typed. The name goes in by character offset
rather than by caret — casting them rebuilds the box the caret was sitting in, and
a caret does not survive that where an offset does. Somebody already cast here is
left out of that half of the menu — they are in the list above under the name they
actually have. A card's prose offers them too, and casts them into the piece the card
belongs to; a PreStage has no piece behind its prompt, so it is offered nobody.

**A file hung on somebody is narrowed to what they are.** A picture given to @anna
as their looks was still scoped `full` — "what the target video takes from it is
what the picture actually shows" — which is the opposite of what a person
reference means, and it was a second setting nobody knew they had to change. It
follows the slot now: their looks take what they are (person, object, scene or
style), their movement clip takes `motion`, their voice takes `voice`, and the clip
they take somebody's place in takes `edit`. A dial set by hand is left alone, and
the only thing that moves one afterwards is changing what *they* are — their pictures
follow them from `person` to `scene` and a hand-set dial still does not. A piece
written before this is repaired as it loads.

**The shelf is a call sheet now.** Every member drew a full card, so a cast of six
was several screens of fields, of which five sets were being scrolled past rather
than read — on a node face, a 300px scrollport holding one and a half people. A
member is a *line* until you open them: their face, their name, what they are made of,
and where they walk on, which is the whole of what a cast gets checked for. One is
open at a time, and the open one is the card that was always there. What is wrong
with somebody is on their shut line too, in red, so a card that cannot queue is
visible without opening anybody.

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

Citing a subject carries their files into that shot the way citing a piece
reference already carried that file, so a shot that never names them costs
nothing. And a name is a citation only because it was declared: `@anna` in a
piece with no Anna in it is prose and stays prose, so nothing already written
changes meaning.

**The cast shelf, rebuilt, and on the node itself.** It only ever appeared in
the Timeline window, and it refused to open at all until a reference had been
attached — so the one prompt that most needs a cast, a text-only one where a
name is all that keeps the same person in shot 1 and in shot 9, could not have
one. Cast is on the rail now, beside Add image, on every node; the same shelf is
still in the Timeline window, and it is literally the same shelf.

A subject can be a name and a description with nothing behind them, and the two
sections they make derivable are emitted in the base modes too — a `<Subject 1>`
written into a description the prompt never defines is a label pointing at
nothing. The base form is otherwise untouched, and a piece with nobody cast
compiles to exactly the bytes it always did.

The card itself is new. What a file lends a subject — their looks, their movement,
their voice, the place they take — used to be four ghost chips, with the way to
add one a "+" character among them that nobody found. They are thumbnails now,
each wearing the file's own identity hue, each badged with what it lends them,
and one menu behind a tile moves it between the four. The card wears their hue on
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

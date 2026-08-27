# Changelog

## Unreleased

**Qwen Image Edit joins the pre-stage, and it is the one that edits.**

The pre-stage could draw a picture from a sentence, twice over — Krea 2 and
Ideogram 4.0 — and it could not do the thing this pack is named after: take the
frame you already have and change one thing about it. Qwen Image Edit is a fifth
family and does exactly that. Attach the last frame of shot 1, write "the coat
is red now", and what comes back is the same person in the same room, on the
same canvas, ready to be shot 9's start frame.

It reads up to three pictures on the base weights — no adapter first, which is
the difference from Krea 2's reference path — and the first of them is not a
reference at all. It is the picture being changed, so it sets the canvas and the
render starts from it rather than from noise; the chip says `editing` where the
others say `style`, and the aspect pill reads "from image" without an init image
being attached. Cite the other two from the prompt as `@handle` the way you
always have; they arrive as `Picture 2` and `Picture 3`, the labels the encoder
itself writes.

Everything it emits is core's — the Qwen encoder Krea 2 already borrows, pointed
at the weights it was built for. Three files: the 2511 or 2509 checkpoint, the
Qwen2.5-VL 7B encoder, and the Qwen image VAE Krea 2 already loads. The turbo
pill is a Lightning LoRA and only a LoRA, since there is no distilled checkpoint
to swap to. The schedule shift core does not detect for these weights is put
back, and the unconditional branch is a second pass of the edit encoder over the
same pictures rather than a zeroed copy of the first — a zeroed copy keeps the
reference latents but hands the model a text stream of zeros in place of the
encoder's reading of the pictures, which is not the unconditional this edit
post-training was fitted against. At cfg 1 it *is* the zeroed copy, because a distilled run never
evaluates a negative and a 7B encoder pass for a tensor nothing reads is most of
a four-step render.

Switching the model pill now writes the arriving family's own sampler row rather
than Krea 2's for everyone.

**References are checked for the things that fail quietly.**

Every way a reference image can be attached and then not read has been made a
refusal rather than a worse picture.

Krea 2 asked only that the LoRA stack was not empty. It asks now *which* entry
reads the references, on a pill beside the layout pill, because a stack holding
a style LoRA and nothing that reads pictures passed the old check and rendered
as though no reference had been attached at all. A reference render on Krea 2's
RAW row also builds its unconditional the way Qwen Image Edit's does — the same
pictures with nothing asked of them — instead of a zeroed copy, which is the row
these adapters were trained against. And Turbo now refuses a removal: distilled
at cfg 1 there is no guidance to push against the reference, so it re-draws the
subject it was asked to delete. Take the switch off and let RAW do it.

Qwen Image Edit has an edition pill. The encoder has three image slots on every
edition, but the first Qwen-Image-Edit weights were post-trained on one picture
— and nothing in the checkpoint says which release it is, so the filename is
guessed from and the pill is where you correct it. A picture past what the
edition reads is drawn struck through rather than silently dropped, and the
compile refuses it by name.

The text encoder is checked for its vision tower before a render with pictures
in it starts. Both VL encoders ship in a text-only cut that loads without
complaint, tokenizes the sentence without complaint, and then has nothing to
encode the references with — a render that ignored every picture it was given
and looked like a prompting problem. Safetensors and GGUF alike, read from the
header rather than by loading anything, and a file that cannot be read is not
held against you.

Krea 2 also warns when a reference's shape does not match the canvas: those
adapters were trained on pairs whose aspects agreed, and what they preserve
falls off when they do not.

**An attached picture is called what it is, and the first one need not be the
subject.**

On Qwen Image Edit the second and third chips said `style`, which names the one
property those weights do not read an attached picture for — an edit model is
being told what is *in* the picture. They say `Picture 2` and `Picture 3` now,
which is both what the encoder writes in front of them and what the prompt cites
them by; `style reference` stays on Krea 2, where an attached image really does
contribute its look. The prompt placeholder, the window subtitle and the refusal
messages follow the same split.

And `editing` on the first chip is a button. These are Qwen-Image weights
post-trained rather than replaced, so "here are three pictures, now draw a
fourth" is a render they can do — and promoting the first picture to the thing
being edited was quietly taking it away, because attaching a picture was what
turned the render into an edit of it. Click the word and the render draws onto
an empty canvas at the aspect pill's shape, with every picture merely cited. An
init image still overrides both, since it is the only way to ask for a partial
denoise.

**Qwen Image Edit's built-in ControlNet is reachable, and a guide lands where
it is followed.**

2509 and 2511 have ControlNet post-trained into the weights: a depth pass, an
edge map or a pose skeleton arriving in an ordinary image slot is followed, with
nothing to load and no strength to set. Core's own blueprints for both editions
are three plain image inputs and no control input, which is why there was
nothing to wire — and why the bug was invisible. Every guide the tracing bench
made went to the **init image**, and an edge map in the init slot is a picture
being restyled at denoise 0.65: what came back was a tidied edge map.

A guide sent to a pre-stage on those editions is now a picture, chipped `guide`,
with the canvas taking its shape. On Krea 2, Ideogram and the first Qwen edition
it is still the init image, because that is the only slot those weights have
that means "start from this arrangement" — and a guide handed to the first Qwen
edition is refused outright rather than quietly edited. A tracing outside the
three the weights were trained on (`lines`, `blocks`, a raw frame) is flagged on
the chip: it will be read as a picture of a drawing, not as something to aim at.

**Sending to the pre-stage opens the pre-stage.**

A picture handed over used to land in a blob nobody was looking at, and the
press that sends it is followed every time by writing the instruction that goes
with it. `↻ edit` and the bench's *Send to pre-stage* now put the pre-stage in
front: the step, inside the fullscreen shell, and the window on the canvas. The
bench closes behind the send, since the guide exists to be written a prompt
around.

**The finished still can go back in.**

Three chips on a result send it *on* — to the shot, as a start frame, an end
frame or a reference. There is a fourth now and it is the loop: `↻ edit` puts
the render you are looking at back into the pre-stage as the next one's subject.
You edited a picture, the edit is right about one thing and wrong about another,
and what you want to change now is the thing on screen. The way round used to be
the picker, four presses away, hunting for your own output among everything else
in the folder.

Where it lands is the arch's own answer to "the picture this render is about":
the first picture slot on a family that edits — replaced, keeping its handle, so
a prompt citing `@ref-1` is still citing what is in front of it — the init image
on one that draws, the request's start frame on the H3 branch. It draws whether
or not the node has a shot attached, which is the one chip here that never
needed one.

While wiring it: the ControlNet bench's **Send to pre-stage** button has never
appeared. It looks for `takeGuide` on the node's body and the method was one
class further in, so the target was silently dropped every time. It is on the
body now.

**A strip of footage as one picture, and back again.**

The observation Qwen-Video-Edit is built on is that an image editor will edit a
*contact sheet* of frames as though it were one picture, and hold the subject
across the tiles — and the half of that which needs no training, no projections
and no second VAE is a grid, an edit, and a pair of scissors. So the pre-stage's
rail has a **Contact sheet** tool: hand it a clip and it lays nine frames out as
one gutterless picture, hand it a sheet and it cuts the frames back out into the
input folder in order. In between is an ordinary Qwen Image Edit render with the
sheet as the picture being changed.

Gutterless on purpose: a seam is one more thing for the model to reproduce, and
a bare grid makes the cut on the way out the same arithmetic as the lay on the
way in — which matters, because the edited sheet comes back on a /16 canvas that
need not divide by three. There is no server half; a browser already decodes
video and already draws to a canvas, and every frame this touches was on its way
to the input folder anyway.

**The LoRA grid groups a model's versions, and the strength slider fits the LoRA.**

A LoRA you have retrained four times was four cards: four near-identical
thumbnails under four identical titles, with nothing on any of them saying that
the other three existed. Its files are one card now, and the version is a row of
pills wearing only the part of the filename its siblings do not share — `v1`
against `v2` against `v2_lite`, which is the part you are actually choosing
between. Civitai's model id groups them wherever a sidecar carries one; a folder
of hand-trained files falls back to the filename, taking off the version tails
people write there anyway, and stays inside one folder while it does it, because
two people's `style_v1` are two different LoRAs.

Two things it deliberately does not group. Wan's split LoRAs publish a high-noise
file and a low-noise one under one model id, and those go in a stack *together* —
a card offering a choice between them would hide half of what you need — so a
name saying which half it is keeps its own card, and so does a t2v beside its
i2v.

Clicking a pill while one of that model's versions is in the stack is a swap in
place: same slot, same weight, same checkpoint, different file. The trigger words
come from the file now loaded, because a retrain renames them. The pin beside the
pills keeps one version as the one that model opens on, which is a fact about
your collection rather than about this piece, so it outlives the window. The
detail sheet grew the same choice as an **On this disk** list you can land on —
the sheet redraws around whichever version you pick, so the showcase and the
recipe are what you compare rather than two filenames — with the sidecar's full
published list below it.

**And the weight's range now follows the LoRA.** Slider LoRAs are trained as a
signed axis and are meant to be driven to ±10 and past it; the track ran -1 to 2,
so half of what those files can do was unreachable and the other half was four
pixels of travel. The row carries the span as a control — ±2, ±5, ±10, ±25, each
one about eighty notches wide, so the drag feels the same at every scale — and it
is picked for you: a file whose own name says slider opens at ±10, one your last
setup left at 6.5 opens wide enough to show 6.5, everything else opens at ±2,
where an ordinary LoRA's whole useful range finally gets the full track. The
weight beside it is typed rather than read, which is the one control that reaches
any value at all; typing past the track widens the span instead of clipping what
you asked for.

**A ControlNet bench, and two quick links on the wordmark's dashboard.**

The bench is a room of its own, reached from the dashboard the wordmark opens.
Footage goes in — dropped on it, or picked out of the input folder — and a guide
comes out: **Edges** (Canny), **Lines** (a difference-of-Gaussians drawing),
**Blocks**, **Luma** and **Blur**, plus **As shot** for a clip that needs only
cutting or its soundtrack stripped.

**Depth** and **Pose** are there too, and they are model work rather than
arithmetic: Depth Anything 3 and SDPose, both of which ComfyUI already ships in
`comfy_extras`. The bench loads what core loads and draws the skeleton with
core's own `KeypointDraw`, which is where the DWPose colour tables the pose
ControlNets were trained on actually live — a skeleton in a palette of its own is
one a ControlNet reads as a different pose. Neither downloads anything: the file is
picked on the same weights pill the pre-stage and the shot wear — same popover,
same chooser — and a tracing whose files are missing says which files and which
folder rather than going quiet. The bench has no piece to save a pick into, so
the pick is remembered per machine in the user settings beside `weights`: which
file on this disk is the depth model is a fact about the disk, and being asked
again every time the bench opens is being asked forever. Depth measures its near and far once and
holds them for the rest of the cut, because normalising each frame against its
own extremes is the usual reason a depth-guided render flickers.

Nothing about the other five queues. Those tracings are arithmetic over pixels,
written against numpy and `scipy.ndimage` so the pack still declares no
dependencies of its own, and the server answers a single preview frame fast
enough that the picture redraws while a threshold is under the pointer — and
fast enough that a running clip is traced *as it plays*, one request in the air
at a time, so the two halves of the wipe stay the same moment. A guide already
written plays there instead, held against the footage frame for frame, and comes
off the glass the moment a dial moves it out of date. The two pictures share one
rectangle with a draggable seam rather than sitting side by side, because the
question being asked is whether the tracing follows the frame it came from, and
that is invisible until they are on top of each other.

A video source can be cut before it is traced, and its sound kept or stripped.
The cut is the reference trim editor's own bar — `trim.js` grew a `mountTrim`
that puts it inline instead of in a modal — so the handles, the rigid-window
drag, the arrow keys, the looping transport and the waveform behind them are the
same code the picker has always opened, and the playhead you scrub is what the
light box is showing. On the way out the cut keeps the source's own timestamps
rather than counting frames out at the container's average rate: every phone clip
is variable-rate, and counting made a two-second cut into a three-second file
that played slow.

What comes out is a file in `input/continuity/control/`. **Send to pre-stage**
makes it the still's init image; **Send to the shot** attaches it as a reference.
Neither is required, and neither is wiring the bench owns — the file is in the
picker either way.

The dashboard also grows a **Go to** group above the tools: Pre-stage and Shot,
each one press to that half of the piece alone in the middle of the screen.
Pressing Pre-stage when the piece has none spawns it on the way. It was three
presses in two places before — the view switch in the bar, then the step switch
on the card, which is not even drawn until the view is simple.

**Both image models now sample the way their authors said to.** Four things were
wrong in the pre-stage, and each of them was quiet — nothing errored, the
pictures were just worse than the weights can do.

*Ideogram's low-guidance polish tail.* Every official preset ends on a fixed
number of steps at guidance 3 instead of 7 — three of Quality's 48, two of
Default's 20, one of Turbo's 12 — and this pack asked for it as a flat 30% of
the trajectory, which is the approximation the shipped ComfyUI template makes.
On a 1K canvas that gave Quality *seven* polish steps instead of three; on a 2K
canvas it gave Turbo none at all, because Ideogram's schedule carries a
resolution term and the boundary moves with it. The tail is now resolved against
the sigmas the render will really run, so "the last three steps" is three steps
at any preset and any canvas.

*Krea 2 RAW's timestep shift.* Krea derives RAW's shift from the canvas — the
`--y1 0.5 / --y2 1.15` ramp in its own inference code — and pins it only for
Turbo, which was distilled against a constant. ComfyUI detects one architecture
for both files and so gives both of them Turbo's pin, which left RAW sampling a
1K canvas on a schedule meant for a 2K distilled render. RAW gets its ramp back
on every render; Turbo keeps the pin, and emits no shift node at all because the
pin is what the checkpoint already detected.

*Style references need an adapter, and now say so.* Krea 2's base weights read
no reference at all: core hands the DiT no default reference method because it
never learned one. Every way of reading a reference on this model is a LoRA —
`krea2_style_reference` for style, an ai-toolkit edit LoRA for edits — and
attaching images without one was conditioning that never reached the sampler.
That is refused now rather than rendered, and because the published adapters
disagree about how reference tokens are laid into the sequence (pinned at
timestep zero, or indexed like any other frame) the layout is a pill on the
references row rather than a constant.

*Turbo is a LoRA too.* Krea ships its distillation twice — as its own checkpoint
and as an SVD extraction of the same weight difference — and the pill now offers
both: the LoRA route keeps RAW resident across a flick of the switch and lets a
content LoRA ride along. Ideogram, which ships no distilled checkpoint at all,
gets the pill for the first time: a distillation LoRA over the ordinary
checkpoint takes it to a handful of steps at cfg 1, where the unconditional
checkpoint is no longer loaded and the polish tail has no guidance left to drop.
The switch is per architecture, so flipping the model pill no longer carries one
family's file onto the other; blobs written before the split are read as Krea
2's, which is the only side that had one.

**A pre-stage render previews beside the node, not on it.** The two image
architectures — Krea 2 and Ideogram 4.0 — sampled behind ComfyUI's own
previewer, whose frames the frontend paints onto the canvas node itself: under
the stage card that should be showing them, and invisible in the fullscreen
editor. They now carry the same KJNodes preview override the video render and
the H3 still already did, which broadcasts the frames the stage reads and
suppresses core's overlay. As everywhere else it is optional: without the pack
installed nothing is emitted and the render is identical.

**Fixed: the strip's reel went blank after turning the card.** In the fullscreen
editor's simple view, switching between Pre-stage and Shot left every block on
the timeline reel unlabelled — no shot number, no length — until the node was
resized. The reel decides what it can print by measuring how wide its blocks
came out, and it was asking for the *painted* width: the card is rotated on its
vertical axis while it turns, so a measurement taken during the turn found every
block a few pixels wide and stripped the labels off all of them. A turn changes
nothing the reel's resize observer reports, so nothing ever asked again. It
measures the laid-out width now, which is the question it meant to ask.

**The wordmark is the door.** In the fullscreen editor, pressing **Continuity**
in the title bar turns the room over to the dashboard: the editor's tools, as
cards, over the whole width under the title bar. One card today — the preset
library, the same one the rail's Presets button opens — beside a marked-out
place for the tools still to come, which is where they will appear. Pressing
the mark again, pressing Escape, or opening a card puts the piece back exactly
as you left it. No keystroke is claimed for it: every pack on the canvas wants
⌘K, so the dashboard is the mark's alone. Nothing else about the window changes,
and no new chrome stands open while you work.

**The pack is called Continuity.** "MiniMax Creator" named the only thing it
could render when it was written; it now renders on four families — MiniMax H3,
LTX 2.5, Krea 2 and Ideogram 4.0 — and a fifth is a directory with a declaration
in it. Continuity is the script supervisor's job: the same person, the same prop
and the same light in shot 1 and in shot 9, which is the cast, the piece
references and the seams, and the one thing that stays true whichever family
renders the frames.

**Nothing you have made moves.** Saved workflows load untouched — the node class
ids never changed, only what they are called on the canvas — and your presets,
picker favourites, LoRA memory, refiner settings and machine settings are all
read under their old names on the first open and written back under the new one.
An install that had typed its own output folder keeps writing there; only the
untouched default moves from `output/minimax/` to `output/continuity/`. The one
casualty is the fullscreen setting and any custom keybinding for it, which go
back to their defaults; Ctrl+Shift+M is unchanged. `docs/RENAME.md` is the whole
manifest, including what is frozen forever and why.

The pack also has a new home — `github.com/roadmaus/ComfyUI-Continuity` — and a
new Comfy Registry entry, `continuity`. An existing clone keeps pulling through
GitHub's redirect.

**Every family files its renders and stills under its own name.** A piece shot
on LTX 2.5 was written to `output/minimax/renders/H3_00021_.mp4` — the wrong
shelf and another architecture's name on the file — because where a render
landed was one constant for the whole pack, decided when H3 was the only thing
in it. It is decided by whatever rendered it now: renders go to
`continuity/renders/<family>/`, stills to `continuity/stills/<family>/`, and a
piece shot a pass at a time keeps its takes in that family's own `takes/` folder.

Settings → Folders has a row per family to match, so a family can be sent
anywhere without moving the others. A machine that had typed its own folder
keeps it: the old single setting is read as an answer for every family of its
kind, which is what it was, and only the untouched default gives way to the new
layout.

**The first card of a piece can now be kept.** A render of one generation used
to be told there was nothing to keep — its take *was* the render, so writing the
same frames out a second time would have been one file to keep and one to
delete. True about the file and wrong about the card: a piece shot a pass at a
time starts as one card generated whole, and that card came back with no take on
it, so locking it left nothing to play and the only way to add a second shot was
to shoot the first one again. The save node now reports the render itself as
that card's take. Nothing extra is written and nothing on disk moves.

**The turbo LoRA reads as the switch's on the strip's rail.** Thrown on, it is an
ordinary entry in the piece's stack — which is the point, and it stays one — but
the piece rail drew it like a file you had picked, forty characters of
`..._turbo_v4_step600_ema_pruned` beside the pill that had just dropped the
filename for exactly that reason. It wears the switch's bolt and the word
"turbo" now, with the file in the tooltip. The shot face never showed it: its
rail is the segment's stack, and turbo's LoRA belongs to the piece.

**The LoRA manager remembers what you set it to.** A strength you arrived at by
trying it, and the two words out of a sidecar's nine that actually did anything,
used to live on the entry in creator_data — which is to say they lived until the
✕, and the next piece started again from the file's own guess. They are kept per
file now, and adding a LoRA anywhere picks up where you left it. A card whose
settings came from you rather than from its sidecar says so, and a file nobody
has used yet still starts from whatever its sidecar recorded.

Trigger words are kept the same way, including the ones that are switched off.
A word you type is part of that LoRA's vocabulary from then on: switch it off and
the chip stays, so turning it back on is a click rather than retyping it. The ✕
on a chip of your own is what forgets one for good.

**Opening the manager from a chip goes to that LoRA.** It lands on the card, in
whatever folder the file is in, and marks it for a moment. Before this the window
opened on the folder you happened to be in last, scrolled to the top, with no
hint of which of several hundred cards you had just clicked.

**Star a LoRA, and save whole stacks.** The scope picker now offers two shelves
above the folder list — Favorites and Recently used — and the shelves are read by
name rather than by walking a folder, so a starred file stays reachable even in a
folder past the listing cap. A file that has been renamed or deleted since you
starred it is named as missing rather than quietly dropped.

A stack you have built is kept under the manager's own Stacks tab, as a preset
holding nothing but its LoRAs: it is the same body the preset library writes, so
it lists, exports and cross-applies there like anything else you have kept. Apply
one over the current stack with Replace, or merge it into what is already on the
node with Add.

**LTX 2.5 reads references.** The second video family used to refuse every
attachment, because a citation reached its text encoder as a bare `<Picture 1>`
with no picture behind it. It has a reference grammar now, and it is Lightricks'
own: pick up to nine stills and the picker lays them out as an Ingredients
reference sheet — panels on a black background — which the render hands to the
transformer as a guide through the `Ingredients` IC-LoRA, with the caption
written in two parts, `Reference sheet: …` then `Generated video: …`.

The whole of the reference system is the one you already had. The same chips,
the same handles, the same cast, the same pool, the same refiner panel. What
changes is the words: a reference is `panel 1` of the sheet rather than
`<Picture 1>` of a presentation, and a start frame is `the first frame` rather
than an ordinal, because Gemma reads captions and an ordinal there is a token
sequence standing where a noun phrase belongs. H3 is untouched — same ordinals,
same Context-IR, byte-identical graphs.

Videos and sounds are still turned away on this family, and the refusal says why
rather than counting to nothing: a clip has no panel to be. Lay it on the
piece's sound lane, or put the piece on H3, which reads both. The rail offers
the tools the family can actually use, so an LTX piece draws "Add image" alone.

Pick the Ingredients IC-LoRA under the weights control. Every canvas axis has to
divide by the adapter's own downscale factor times 32; a canvas that does not is
refused before anything loads, naming the pill to move.

**The sheet is made while you pick, and you see it before it lands.** On LTX
2.5 the image selection *is* the sheet — that is the family's grammar, one
composite per shot — so pressing Add opens the sheet editor: the composite
exactly as the model will be handed it, on the black field the adapter was
trained against, with the panels in a strip below. Drag a panel to rearrange
(the numbering is the citation — `panel 3` in the caption is cell 3 of the
grid), press the scissors to cut one out of its background or keep it whole,
take one off with the ✕, and confirm. A card on this family carries one image
reference and the render loads that file; a request carrying loose seconds is
refused rather than composed behind your back.

On H3 nothing is welded together for you: multi-select attaches separate
references, as it always did, and each is encoded on its own. The new Connect
button in the picker's foot is how a sheet happens there — select two or more
pictures, press it, and the same editor lays them out on mid grey. The result
attaches as ONE reference, storyboard-style, costing one of H3's slots however
many panels are on it, and rides alongside the loose references. The paired
pictures stay connected: reopen the picker and they come back selected and
numbered, ready to be edited, extended, or dismantled, while you keep adding
other references around them.

The scissors are core's BiRefNet matte — no prompt, no box, no click. A
reference image is a photograph, and a photograph is mostly not the thing it is
a reference *of*: cite somebody's portrait for their face and the model is also
handed the room they stood in. Panels start cut on LTX 2.5, where they are
ingredients rather than photographs, and whole on H3, where every piece ever
saved was rendered against whole pictures.

What lands on the card is one reference: the sheet, as a real file in the input
folder, with the pictures it was laid out from listed on its card. Those keep
their handles, so `@img-2` still means the second panel and the cast still
claims it — `panel 2` in an LTX caption, `panel 2 of <Picture 1>` in H3's. Open
the sheet's name to change what a panel reads as, or Edit sheet… to build it
again — also offered on a plain picture, which is a sheet of one nobody has
added to yet, and where the scissors on a lone H3 reference live.

Pick a background-removal model under weights; it is loaded the first time you
press the scissors and held for the session. Nothing about a cutout or a layout
happens at render time any more — the graph loads no matte and composes no
sheet, and a selection you have built before comes back without a second pass.

**The sheet editor is a stage now, and nothing is written until you accept.**
The editor used to show a server-built composite and rebuild it — as a real
file in `input/_plates/` — on every click, so an afternoon of picking left the
folder full of discarded previews and the All shelf full of half-made sheets.
Both halves are gone. The preview is composited in the browser, from per-panel
cutouts the server serves straight out of memory, and the composite is written
exactly once: when Accept (or Add, for a Connect group) commits it. Cancel
leaves no file anywhere, `_plates/` no longer appears on the All shelf (its own
shelf still holds it), and Organize grew a Mark all button — which is also how
the sheets an earlier version littered are cleared in one press.

The stage is the shot's own canvas, and the panels on it are where they will
actually sit. Drag one to place it, take its corner to resize it, reorder the
citations in the strip below; Auto-arrange puts everything back on the grid.
The arrangement is part of the sheet's identity — the same panels laid out
differently are a different file — and part of its caption: an unarranged
`panel 3` is still described by its grid cell, a dragged one by where it
landed, against thirds of the canvas, so "panel 1 is the person top right"
stays a sentence the model can check against the picture in front of it.

**Click the subject and SAM 3 cuts exactly that out.** BiRefNet's matte is
salient-object — hand it a picture of two people and it lifts both. The editor
now has "Click to choose the subject": click the thing you mean and the panel's
matte comes from SAM 3's point path instead, shift-click marks what to leave
out, every click is a dot you can press to take back, and the mask is feathered
a couple of pixels so a hard edge does not read as a sticker. Clicks are part
of the sheet's name too, and they ride with the panel, so reopening the editor
starts from them. Pick a SAM 3 checkpoint under weights — on H3 it is the same
file the face pass already uses; without one the scissors still work
whole-subject, and the first click tells you what is missing.

**The refiner writes the prompt this piece's model was trained to read, not
always H3's.** The Refine button was written when H3 was the only family, and it
stayed H3's after there were two: whatever the piece's model pill said, the
route compiled the request as H3, derived an H3 mode name for it, and rewrote
the prose into Context-IR — section headers, `[Shot 2]` markers, cut timestamps
and `<Picture 1>` ordinals. On LTX 2.5 every one of those is a token sequence
Lightricks trained the weights never to see, sitting exactly where a description
belongs, so refining a piece on that family made its prompt worse rather than
better.

The refiner has come apart into the half that is the harness and the half that
is a statement about a checkpoint. The harness — `@handle` storage, the citation
and quoted-span checks, the ChatML turns, the reply budget, the grounding pass
over attached pictures — is shared and unchanged. Each family now brings its own
templates, mode names, reply contract and glossary, and the button follows the
piece's model pill the moment it moves.

LTX 2.5's is written from Lightricks' own prompting guide: one flowing
present-tense paragraph with no headers, labels or markers of any kind; the shot
established before the scene and the scene before the people; emotion as a
physical cue; camera movement said relative to the subject and resolved after
the move; dialogue in quotation marks in the sentence that speaks it; sound as
heard events. A cut is prose here — "A hard cut transitions to…", the framing
re-established after it, the sound said to continue or drop — so this family is
never asked for cut times, and a lone card that wants several shots writes them
into its one description.

The template pill offers each family's own list, and a pin is kept per family: a
`REF2VA` pinned on an H3 piece no longer rides along into an LTX request as a
name its refiner has never heard of. An existing pin is kept for the family it
was made against.

**Clear empties the sound lane, and a track can be taken back off by hand.** A
laid track is the piece's own sound — the shots under it are generated against
it — so a Clear that left it behind handed the next scene the last one's
soundtrack, and did it silently: nothing on the emptied piece said where that
music was coming from. It also meant a piece with only a lane on it read as
nothing to clear. The files themselves are untouched; what goes is where they
were laid, which is writing like the rest of it.

Taking one off was a keystroke — Delete on a focused block — and a keystroke
nobody has been told about is not a control. Every block now carries a ✕ in its
bottom-right corner, drawn at rest and faint like the trim grips beside it, for
the same reason those are: a handle you only meet once you are on top of it says
it too late.

**A card opened from the strip is a card of *that piece*.** The segment editor
was built without being told which piece it belonged to, so it fell back to the
card itself — and a card carries no family. Every family-derived control in that
window was therefore drawn as the default family: no auto-duration switch on a
piece whose weights have a duration head, H3's mode names over an LTX card, a
weights pill for routes LTX does not have, and attach tools for references the
compiler would refuse at queue time. The strip underneath had all of it right,
which is how the same segment came to read `FL2V` on the card and `FL2VA` in the
window over it.

**Where a family reads no attached references, the attach tools are gone rather
than greyed.** A disabled button says "this is a thing you could do here"; on
LTX 2.5 it is not one, and no amount of waiting will make it one — the refusal
is about what the model reads. The piece's reference shelf goes with them, and
stays only where files are already on it, so a piece carried over from H3 can
still be emptied. Greying is kept for the case it was meant for: a full card on
a family that does take them.

**A shot that cites a reference no longer claims to open on it.** Since the
compiler started asking a family how to read a request, the prompt was composed
as though nothing had been cited — so a reference generation was written in a
keyframe mode and picked up the guide's base-mode alignment line, "at 0.00
seconds `<Picture 1>` is fully referenced". On that road `<Picture 1>` is the
first *reference*, not a frame the shot opens on: the seam is never presented to
the text encoder there, and an attached start frame is presented after the
references and already named, at the ordinal it really took, by the line under
it. So the prompt told the model to open the shot on the character sheet.

It bit hardest in a timeline, where the transformer was simultaneously handed
the previous shot's own last frames as pinned guides: the picture the text asked
for and the picture the guides asked for were different, and whatever came out
of that argument was decoded, inherited by the next seam, and argued over again.
A cast-driven chain drifted further from itself with every card.

**The LTX 2.5 sampler row is five pills at rest instead of thirteen, and it is
written in words rather than in the names of the nodes behind it.** Settings →
Nodes → Advanced controls never reached this row: the flag was read past the
point where a declared family peels off to its own renderer, so "Standard" and
"Everything" drew the same thing. It is read per control now, off an `advanced`
key each family sets in its own manifest — so which controls are the last few
percent is that family's statement rather than a list in the frontend. The rule
the H3 row already lived by holds: a control you have set keeps its pill
whatever the setting says, because in force means visible.

Separately, and worth more: on the trained curve the row was drawing five pills
the render does not read, one of them lit. `requires` grew a value form, so
`steps`, the noise curve and the stop-early pair appear only on the `custom`
recipe that builds a schedule out of them. A control that is not read is not a
setting in force, it is a leftover, and the one pill that looked switched on was
the one that could not be doing anything.

The names go with it. `video cfg` and `audio cfg` are **prompt strength** and
**sound strength**; `max shift`/`base shift` are one pill reading **noise curve
0.95 to 2.05**; `stretch sigmas` and `terminal` are **stop early at 0.10**;
`schedule: distilled` is **recipe built-in**. Combos say what they are a choice
about instead of showing a bare value — `sampler res_multistep`, not
`res_multistep` alone. A guidance slider sitting on the value at which it does
nothing reads **detail guidance off** rather than `detail guidance 0.0`, the way
every switch on the row already read. And the `FL2V` badge says **start → end**;
Lightricks' codename moves to the tooltip, since with one transformer there is
no checkpoint for it to be naming. Every technical term stays in the help text,
where somebody searching for it will find it. Nothing on the wire changed: the
options a family stores and sends are the options, renamed only for the pill.

The face pass pill no longer appears on a family that declares no such pass —
it is H3's crop-and-repair loop, and on LTX 2.5 it was a switch for something
that could never run. A piece that somehow carries one switched on keeps the
pill, so it can be switched off.

**LTX 2.5 now samples on the curve its checkpoint was distilled against, and
renders come out a different class of picture for it.** The family was building
its schedule with `LTXVScheduler` and pairing it with the `ModelSamplingLTXV`
patch — the recipe LTX 2.3 shipped, and the wrong one here. A step-distilled
transformer is not merely a model that takes fewer steps: the distillation is
done against one trajectory, and 2.5's is a constant Lightricks ships rather
than a curve anybody computes. Both of their own 2.5 workflows and ComfyUI's own
template feed nine fixed sigmas through `ManualSigmas` and emit neither of those
two nodes. What this pack was computing instead descended evenly and then jumped
0.572 straight to 0.1, skipping the stretch below 0.42 where the picture's
detail resolves; the trained curve spends four of its eight steps almost in
place at the top and does the whole denoise in four large drops. The second
stage was wrong the same way, and is now the tail Lightricks ships for it —
three steps from 0.85, where the upscaled latent re-enters the trajectory the
first stage left. The sampler default moves to `euler_ancestral` with them,
which is what both stages of both official graphs select: the noise an ancestral
step adds back is part of what eight steps were distilled with.

Which of the two curves a piece is on is a new **recipe** control at the head of
the LTX sampler row, because it is genuinely a choice — the `dev` transformer in
the same slot *is* sampled the old way, at ~20 steps and cfg 3/7, and picking
`custom` brings `LTXVScheduler`, the shift pair and the model patch back along
with the pills that describe them. On the trained curve none of those are read,
and neither is the resolution popover's refine denoise, there being no fraction
to take of a schedule whose every value the distillation fixed. Nothing about H3
moved — its goldens are byte-identical.

**A still handed to LTX 2.5 is compressed before it conditions anything.** Every
official image-to-video graph for this model resizes the frame to a 1536 px
longest edge and runs it through `LTXVPreprocess` on the way to the guide, and
conditions it at 0.7 rather than pinning it at 1.0. This pack was passing the
image through clean and pinned. The compression is the load-bearing half: it is
what makes a still look like the guide frames the model was trained to continue
from, every one of which came out of a compressed clip, and a clean one is
off-distribution in a way that shows up as an opening second that sits still and
a pass that drifts soft behind it. Seams are untouched at full strength — the
frames a continuing shot inherits are the pass in front's own, already at this
canvas and already out of this VAE, and putting encode artefacts into them would
be inventing damage rather than matching training.

**A take on the editor's shelf goes up on the picture, and the newest one is
nearest it.** The shelf under the fullscreen editor grew left to right, so the
render you had just made was at the far end of a row that only ever got longer —
the one take anybody reaches for was the one that kept moving away. It reads
outward from the plate now: leftmost is what was on the picture a moment ago,
and the further right you look the older it gets. Each thumbnail also carried a
transport of its own, which is eight scrub bars over eight pictures too small to
scrub; the whole cell is the press instead, and pressing it puts that render on
the plate at full size. Nothing is still until it is pointed at, and then it
plays — along a shelf of takes of the same shot, with the same truncated
filename, motion is what tells one from another.

The take is shown in a layer *over* the plate rather than written into it, which
is why this works in the middle of a render: the sampler goes on sampling
underneath at full speed, and when it lands it lands on the picture you will
come back to instead of over the thing you were looking at. The way back is the
room around the picture, the same thumbnail again, the chip in the corner, or
Escape — which now dismisses the take before it closes the editor. The take
travels between its cell and the plate rather than cross-fading, so which one is
up is said by the movement instead of by a label; a system set to reduced motion
gets the fade.

**A render whose sound does not land on the audio encoder's frame boundary now
writes.** AAC's frame is a fixed 1024 samples and libavcodec refuses any other
length anywhere but the end of the stream — as a bare `avcodec_send_frame()
returned 22`, four frames deep in PyAV, naming nothing. Every part's sound is
cut to the length of its own picture, so landing on a boundary was the
exception: a 6 s shot at 24 fps is 288000 samples, which is 281 frames and a
remainder of 256. Nothing was wrong with the audio and nothing was wrong with
the family — some PyAV builds absorb the short frame and some return the error,
which is why this survived every render made on a box whose PyAV does. The
samples a part ends on are carried into the next part's first frame now, and the
last of them go out with the flush, where a short frame is the one thing that is
allowed.

**A shot's length can be handed to the model from the strip, not only from the
shot.** The duration head's "auto" was on the seconds pill in a shot's own
editor and nowhere else, so setting it on a strip of eight meant opening eight
cards — in the one view where the lengths are actually laid out side by side,
the seconds were a readout. They are the switch now, on any family that has a
duration head, and a card on auto wears the same `~` its estimate already wears
on the strip's total and inside the editor. Not on a shot inside a merged pass:
what is sampled there is the pass's total, so a per-shot switch would be
offering the model a number nothing reads.

**The model leads every node's pill row.** Which architecture renders a piece
was in two different places and neither was findable: on the pre-stage it stood
mid-row between the frame pills and the canvas, and on the video nodes it was
inside the sampler row, behind the Sampling settings disclosure, between the
face pass and the weights. It is a sampler setting nowhere — it decides what
every other pill on the body *means*: which routes exist, what the seconds round
to, which checkpoints the routing pill cycles. So it now opens the row that says
what the render is, in the same slot on all four faces — a shot, a strip's
summary, the strip window's bar, and both pre-stages, where the slot names an
image architecture instead of a video family. The weights pill stays on the
sampler row: those are file paths, set once when a checkpoint is installed.

**A preset keeps the whole sampler row, whichever family's row it is.** The list
of settings a preset carried was written down rather than read off the family,
and it was H3's list from before three of H3's own controls existed: the
attention pick, low VRAM and fast math were dropped by every preset that
claimed to keep the row, and it carried the retired `sage` switch, which is the
one thing the pack exists to *clear*. On LTX 2.5 it kept `steps` and the sampler
name — the two settings both families spell the same — and dropped the cfg pair,
the sigma curve, the stretch and the new guidance. On an Ideogram 4 pre-stage it
carried a step count that architecture does not have and missed the quality that
is most of what its row is. All four lists are one derivation now, off the same
manifest the controls are drawn from.

**And a preset no longer quietly puts one family's settings on another's piece.**
A row and a set of weights belong to the family they were captured on — both
video families spell `steps` and `sampler_name` and mean different things by
them, and no weight slot is shared at all — so those two sections are now
refused across families, with a reason naming both. Everything else on the
preset crosses as it always did. Applying a preset's weights also reads them
under the target piece's own slot names, where before it read them under H3's:
on an LTX 2.5 piece that meant every file the preset was keeping came back
empty.

**LTX 2.5 renders can be guided for detail and for lip-sync, and the pills say
what that costs.** Two of Lightricks' own patches, off by default and drawn in
their own group beside the sampler row rather than among the accelerators —
because they are the opposite trade. Detail guidance re-runs each step with the
chosen transformer blocks' self-attention degraded and steers away from it,
which sharpens spatial detail and steadies motion; a/v sync re-runs each step
with the audio-to-video attention severed and pushes toward the coupled
prediction, which is what tightens lip-sync. Each is an extra forward pass per
step, so on the distilled weights either roughly doubles the time of the stage
it runs on and both roughly triple it — which is in the tooltip, since it is the
only thing worth deciding on. A pill is lit exactly while it is costing that,
and a piece that leaves them alone builds the same graph it always did.

**Every render has a live preview again, not just an H3 one pointed at taeh3.**
The preview override was only ever emitted when a tiny decoder had been picked,
which made a decoder look like the thing that turns previews on. It is not: it
is a quality setting *inside* KJNodes' node, and the node itself is the only
thing that previews these renders at all — ComfyUI ships with previews off, and
where they are switched on the frontend paints them onto the canvas node rather
than into the body. So an LTX 2.5 piece, and any H3 piece whose owner had not
downloaded taeh3, sampled for ten minutes behind an empty box. The node is now
emitted whenever KJNodes is installed, on both families and on both of LTX's
sampling stages. Without a decoder it draws latent2rgb — colour without detail,
animated across the clip — and on LTX through KJNodes' own LTX previewer, which
knows to crop off the guide frames the sampler appended. Picking taeh3 still
does what it always did, on the family that has one.

**And the stage card holds the picture at the card's size, whatever size the
picture is.** The card declared a column but never `display: flex`, so the media
row had an automatic height, the picture's `height: 100%` had nothing to resolve
against, and it fell back to the decoded file's own size — while the card's
width sat on its 240px floor because shrink-to-fit reads an image's intrinsic
width and ignores any cap on its height. Neither showed while the only preview
in the pack decoded at roughly the render's own shape. A latent2rgb frame is the
latent — 30×17 on an LTX canvas — and it landed in the corner of a full-height
card as a postage stamp. The card is a flex column now and takes its shape from
the media it was handed, which is the mechanism `Stage.setAspect` already fed the
fullscreen dock. The dock had the other half of the same fault: it took the
picture's shape *and its size* from what was inside it, so the full-size frame it
holds while you wait handed over to a 30×17 card adrift in the column. It is the
largest box of the picture's shape the column will hold now, at whatever the
corner grip is set to.

**The sampler row a pill writes is the one the render reads.** Two faults with
one shape. The store's field list was H3's, written down, so an LTX 2.5 piece
kept `steps` and lost the rest of its row on the way through — `video_cfg`, the
sigma pair, the stretch — dropped on load and on save both, which meant a pill
moved on that family changed the render until the workflow was saved and then
quietly stopped. The list is each family's own declarations now, derived from
the manifest, so a family added to the pack turns up in the store without
anyone editing the browser half. And the row on the piece's face was drawn
against a second `{value, set}` pair over the node's widgets, left behind when
the row moved into the blob: the turbo switch wrote its six steps and euler
where the render takes them from while the row went on showing twenty and
res_multistep, so the switch looked inert and a step count dialled after it was
overruled by a blob it never wrote. One pair now, the blob's.

**Switching families keeps the weights, and only H3 routes.** Three faults, one
root: the weights layer knew which family a piece renders with and the routing
layer did not. A piece moved to LTX 2.5 reported two weights missing when every
file it loads had been picked — it was being asked for `fl2va` and `ref2va`,
which are H3's checkpoints and not slots LTX has — and a LoRA whose checkpoint
claim LTX cannot read was taken to claim both of them, so the H3 distillation
the turbo switch had thrown went on being patched onto a 22B LTX transformer
with no switch left on the row that owned it. A family that ships one
transformer now routes between nothing, on both sides of the pack: nothing is
derived, nothing may be pinned, nothing is required, and a LoRA claims nothing —
which means every enabled entry is patched onto the one set of weights there is.
The turbo switch's own LoRA leaves with the switch when the family changes, and
the switch is drawn only for a family that declares a distillation.

**LoRAs on LTX 2.5.** Which loader patches a family's LoRAs is now the family's
own: H3 keeps the vendored stack it needs — the stock loader is wrong on the
quantized checkpoints most people run it on — and every other family goes
through ComfyUI's own, which is what LTX's adapters want. LTX 2.5 takes LTX
2.3's LoRAs, so those work here. Nothing checks a file to decide whether it
belongs, because that is not knowable from the file; but a LoRA that patched
nothing at all now says so and stops the render, instead of leaving you to
wonder why it made no difference.

**The sampler row is the family's too.** `steps` and `sampler` are spelled the
same on both families and mean different things — 20 res_multistep steps is H3's
row and 8 euler ones is the distilled LTX transformer's — so a row left in place
across a switch was quietly sampling the new family at the old one's numbers. It
is now set aside with the weights and handed back the same way, and the turbo
switch is released into it on the way out: switching a family off is switching
its turbo off, and that means putting the row it overwrote back.

**The weights are remembered, per family.** Picking six files was a chore paid
twice — once per new node, and once more every time a piece was switched between
architectures, which threw away the block for the family being left. A piece now
sets that block aside under its family's id and takes it back on return, and
this machine remembers the last block picked for each family beside its other
preferences. A node fills an *empty* row from that memory and never a row the
workflow answered, so a saved piece still says what it rendered on.

**The upscale pill has a third answer, and it is not the family's own.**
ReDetail finishes a piece by re-rendering every decoded pass through LTX 2.5's
pixel spatial upscaler at twice the canvas — an H3 render included, which is the
point: the backend is the piece's choice and the family is not. Pick it on the
resolution popover and the render samples once at the native edge and comes out
at double it, past anything either family samples at on its own.

It is a repaint rather than a polish. The model invents the fine detail as it
goes, so it is right for soft or generated footage and wrong wherever a face has
to stay the same person or a logo the same logo — the popover says so where the
choice is made, not in a release note. The pass runs after the whole reel, so a
seam still inherits the frames that were rendered rather than the ones that were
re-invented; a strip carrying supplied footage is refused, because a clip is
spliced at the size it already is and the parts of one reel have to match.

Its weights are their own block under the weights popover, headed by the backend
that loads them: a second architecture beside the one the piece renders with. A
piece already rendering on LTX 2.5 fills one row rather than five — the render's
own transformer, encoder and VAEs answer, and only the IC-LoRA is new. Nothing
is loaded until a render actually reaches the pass. Built from ComfyUI's own LTX
nodes, so no third-party pack is needed; the graph and its measurements come
from [Bambushu's ReDetail](https://github.com/Bambushu/redetail).

**LTX 2.5 renders.** The second video family samples now, rather than being
described and refused. Pick it on the model pill in front of the weights and the
node loads Lightricks' 22B transformer, Gemma 4 with LTX's projections and the
two VAEs; picture and soundtrack come out of one packed latent, guided apart by
separate CFG scales. The row is the family's own — 8 steps at cfg 1/1 on the
distilled transformer, a sigma curve with a stretch and a terminal — because a
node's widget list is static per class and LTX's controls are not a subset of
H3's. The frame grid is 8n+1 at 24 fps and the native canvas is 960 × 544, both
off the model card.

Attach a first or last frame and it becomes a real guide on the 8-frame grid;
chain shots and the seam's inherited run rides in the same way. **References are
carried in the prompt text and encoded from nothing** — a guide is a keyframe,
and pinning a character sheet at frame zero is not what citing a reference means.
The grammar that replaces H3's ordinal citations here is IC-LoRAs, and choosing
it is the next phase's work; the render proceeds and says so in the log rather
than refusing.

**The upscale pill runs Lightricks' own second stage on an LTX piece.** Not the
H3 refine, which re-encodes the request at a larger canvas: LTX ships a trained
x2 latent upscaler, so the piece samples at the native edge, the upscaler takes
the video latent up, and a tail of the schedule runs again. The factor is the
model's, so the resolution slider chooses *whether* there is a second stage
rather than how big it is, and the pill says which.

**The controls ask the piece which family it is.** The weights popover, the
sampler row, the LoRA manager, the resolution and aspect pills and the mode
badge all read the piece's family instead of the one family this pack used to
have. A family that ships one transformer draws no route control, no per-LoRA
checkpoint choice and no mode → checkpoint arrow, because there is nothing for
any of them to say. Nothing about an H3 piece moves: the graphs it builds are
byte-identical, and a workflow saved before any of this names no family and is
H3 for good.

**A shot on LTX 2.5 can be as long as it wants to be.** The seconds pill grows
an "auto" switch on a family that has weights to answer with — LTX's duration
head, picked in the weights popover — and the model reads the shot's own prompt
and chooses its length while it renders, inside the trained 1–20 s. It cannot be
asked any earlier: the prediction runs the transformer's caption connectors over
the encoded prompt, so it needs the whole model loaded. So the number on the
pill becomes an estimate while auto is on, wears a `~`, and is what the strip's
bar and the queue's length guard go on counting with. H3 has no such weights and
so is not offered the switch.

**A seam blends at the width its own model can encode.** The picker's short,
medium and long are the runs a family's video VAE takes standalone, which on H3
is 5, 22 and 39 frames and on LTX 2.5 is 9, 17 and 25. This matters more than it
sounds: LTX crops a guide to its own grid silently, so an H3-shaped blend
reached it as a single frame while the strip went on subtracting five — a seam
that had quietly stopped being a seam. The strip's length readouts, the queue
guard and the reference-length match now all ask the piece which family it is,
for the same reason.

**Merging cards on LTX 2.5 is native multishot, and now reads like it.** One
generation holding several shots is what Lightricks means by multishot — this
pack has always had the control, as `merge` and one-pass mode. What it did not
have was the right *description*: every family's merged pass was assembled in
H3's Context-IR form, so LTX received `[Shot 1] … [Shot 2] At 00:05.000, …`,
which is markup its captions are defined by never containing. A merged LTX pass
is one flowing paragraph now, its shots in play order, with nothing invented —
you name the cut yourself ("a hard cut transitions to…"), which is what the
model was taught to read. Nothing about an H3 pass changes. Past four cuts in
one generation the pass wears the same off-distribution mark a too-long
duration does, because four is what Lightricks' guidance prefers.

**A blended seam no longer pins the frame it lands on.** Blending a seam hands
the previous shot's last run of motion to the model as context; on top of that,
the text encoder was also being shown that run's final frame and told to arrive
at it exactly — a still pinned against the motion meant to carry through. Worse,
it only happened on shots without references, so the same seam behaved
differently depending on what else was attached to the card. A blend now speaks
for itself. If you want the old behaviour — the blend *and* a hard statement
about where it lands — the seam's blend picker has a switch for it, and an
unblended seam is unchanged, since there the frame is the whole seam.

One knock-on worth knowing about: a blended seam with an end frame attached now
correctly describes one picture to the model instead of claiming two.

Requires a ComfyUI new enough to ship the LTX-AV nodes; without them the node
says so by name instead of failing three hooks deep.

## 2.26

**A long reference does not take the card down with it.** A reference video is
`latent_t` copies of its own grid, not one, so ten seconds at `max` is around two
hundred thousand conditioning tokens — longer than the clip being generated, and
every row of it rides through every sampling step. At that length the widest
tensor in the model is the first projection of each block's SwiGLU, gigabytes of
it, and a branched LoRA held three of them at once: the layer's own output, a
delta of the same shape, and the sum that allocated a third. That third
allocation is what ended a render on a 32 GB card, on the second sampler pass
where the branch bank is attached, having got through the first pass on the same
shapes. The branch now adds into the tensor the layer already returned, so it
costs the rank-width intermediate and nothing else. Unscheduled branches stay
bit-identical; a scheduled one moves by the last bit, because the add happens
inside the matmul now instead of after it.

What that cannot do is make the sequence shorter, and a long reference at `max`
still costs what it costs. Accelerators → chunked feed-forward splits the same
arithmetic over the sequence and is free — it is arithmetic rearrangement, not a
trade — and `match` on the reference itself is the other half of the answer.

**Recommended: a ComfyUI carrying H3's seven special tokens.** The released
tokenizer declares `<d>`, `</d>`, `<|cutoff|>`, `<|lyrics_start|>`,
`<|lyrics_end|>`, `<|caption_start|>` and `<|caption_end|>` in its config and
nowhere else, and ComfyUI did not add them, so the dialogue tags this pack writes
were tokenized as two pieces of ordinary text apiece rather than as the token the
model was trained on. [PR #15808](https://github.com/comfyanonymous/ComfyUI/pull/15808),
merged 2026-08-22, adds them. Nothing here needs to change to get it — the prompt
is handed to ComfyUI as text and tokenized there — but it is worth updating for,
and worth knowing that it changes results: a prompt carrying dialogue or lyrics
renders differently afterwards on the same seed, in the direction of correctness.
A prompt with no `<d>` in it is unaffected. There is no minimum version and this
is not a floor; a ComfyUI without the PR runs everything here correctly, it just
spells the dialogue tags worse.


**A duplicated segment does not copy the cast into the piece's references.** It
never did — but that is what it looked like, and it was reported twice. A piece
of one shot keeps its cast's photographs on that shot's own row; the moment a
second card exists they move onto the piece, because card 2 cannot see card 1's
row. Duplicating a segment is the ordinary way to get that second card, so two
new entries appeared on the reference shelf at the press of the copy button,
wearing fresh `@ref-N` handles, reading "cited nowhere yet", directly above a
cast shelf still showing the same two faces. Nothing was duplicated and nothing
was billed twice, and none of that was visible.

Those entries now say what they are: marked with their own colour down the left
edge, named for the member they belong to, and reporting which shots write that
name rather than which prompt writes the handle. Removing one says whose face it
takes with it. Marked rather than hidden, because a shelf that draws only some
of what a piece carries is not an answer to what a piece carries.

**A cast of five is five colours.** The identity hue — the colour a chip in the
prompt shares with the file on the asset row and the card on the shelf — is
worked out from the handle, and it was worked out by counting: `img-2` is the
second hue, `ref-4` the fourth. A cast member's name counts nothing, so every
member in every piece fell to the same first colour, and the shelf's five
coloured edges were one colour five times. Names are now spread over the same
eight by their letters. Files keep exactly the colours they had, because those
are in every piece already; only the names move, and a member keeps theirs
across a reload.

## 2.25

**A reference is encoded once, not once per prompt.** Attaching a video or a
cast member means decoding it and pushing it through the VAE, and on a
high-resolution source that is most of the wait before the first sampling step.
None of it depends on the prompt — but a generation caches on its whole request,
so editing one word paid for all of it again. References are now kept between
renders, keyed on the file, the canvas they were encoded at and the VAE that
encoded them; the prompt, the seed, the sampler, the LoRAs and the other
references are all free to move. A cached reference is never opened, either:
the decode is deferred, so a hit does not touch the disk the clip is on.

That makes `max` affordable. It was the better-looking setting you paid for on
every render, and `match` was the answer; now it is paid for once per canvas and
the choice goes back to being about quality.

The store survives a restart. It lives under ComfyUI's user directory, beside
the settings file and the picker's thumbnail cache, and not under temp, which
core empties on startup — a cache wiped by a restart would pay for `max` again
every morning, and the whole argument is that the reference has not changed. It
drops what nothing has read in a month, or whatever is least recently read once
it passes its ceiling.

It cannot change what a render produces — only how long it takes. Settings →
General → Reference cache turns it off, empties it, and sets its two limits: how
long an unread reference is kept, and how large the store may get. Both rails
travel a list of stops rather than a range, because nobody is choosing between
30 days and 31 — and the size rail carries a gauge of what the store is actually
holding, drawn against the thumb, so a ceiling is set against a real number
instead of a guess. Past the thumb is over, and says what the next render drops.

**The terminal says what the references are doing.** A reference being decoded
and encoded is most of the wait before the first sampling step, and it used to
happen in silence — which also meant there was no way to tell a working cache
from a broken one. Each reference now says whether it was reused and from where,
or that it is about to be encoded and then what that cost, and each generation
ends with one line saying how many of each. A miss announces itself before it
runs, not after, because the point is to explain a wait while it is happening:

    [MiniMax] @vid-1 video (max): encoding, nothing cached
    [MiniMax] @vid-1: decoding beach-plate.mp4
    [MiniMax] @vid-1 video (max): encoded in 24.3 s, cached 40 MB
    [MiniMax] @cast-2 image (max): reused from disk (18 MB)
    [MiniMax] @vid-1 soundtrack: reused from disk (420 KB)
    [MiniMax] references: 2 reused (18 MB), 1 encoded in 24.3 s

**Cached references survive a restart, which is what they were for.** They did
not. A reference's key includes the VAE that encoded it, and that was worked out
by reading the loaded object — including `downscale_ratio`, which on the H3
video VAE is a tuple holding a lambda. Its text is a memory address, so every
restart gave every video and image reference a new key and none of them could
ever come back off the disk. The audio VAE sets that attribute to the plain
number 800, so reference *sound* hit every time, which is what made the failure
visible at all. A checkpoint is now identified by its file, stamped like any
other, and its name travels down the graph beside the socket it is on.

**A fresh node opens on a seed of its own.** The default was 0, and this node
pins the after-generate control to "fixed" — so 0 was not a starting point, it
was the seed every first render anyone made ran on. Now a node dropped on a
canvas draws its own. Not a "better" seed: golden seeds are found by ranking a
thousand of them against one model's own output and the winners differ from
model to model, so there is no number to borrow for H3. Every seed is one noise
sample. What was wrong with 0 is that it was everybody's. A saved workflow is
untouched — its seed lands after the node is built.

**Settings' third tab is called General.** It carries a Rendering group as well
as a Nodes one, so "Nodes" was the name of half of it.

## 2.24

**A shot can be made as long as the sound or the footage it is generated
against.** A card's length and a reference's never met: the pill set one, the
segment editor set the other, and the difference was spent silently — every
reference video is cut down to the card's own frame count on the way to the
model, and a music cue longer than the shot is sent whole against a shot that
ends before it does. The duration pill now says how long the reference runs and
sets the card to it in one press, the segment editor draws the card's length on
the clip and cuts to it from the other side, and the reference card says which
of the two is happening. Every clip counts, a cast member's voice and the clip
they stand in for included; where a card carries several, the one offered is the
one its length leads — a line of dialogue over a long plate the shot only takes
a look from.

**A matched card carries the length the model can actually make.** Frame counts
come 17 apart, which is 0.708 s, and whole seconds do not cover that grid: the
nearest card to a 6.6 s cue is 6.58 s, and rounding to 7 lands two thirds of a
second late. Matching writes the real duration, the pill shows its two decimals,
and a step from there returns to whole seconds.

## 2.23

**A reference the sentence stops naming is muted, not binned.** Deleting `@img-1`
used to take the file, the handle, the narrowing and the trim with it. It stays
on the row now, dimmed and out of the run — the same switch a LoRA carries, with
a glyph beside the ✕ to work it by hand on any reference.

**The reference row is the same row in both fullscreen views.** The simple view
hid the cast's own pictures; a row that draws only some of what is attached is
not an answer you can trust once a file can be sitting there muted.

**Pressing a name in the prompt opens the cast drawer again after the card is
rebuilt.** Which view a card is drawn in was remembered on the editor, which is
rebuilt whenever the segment under it changes — so in the simple view the press
put up a drawer that view hides, and only a round trip through the full view
cured it. The body remembers it now.

**The next shot is a pill in the pill row.** Growing a piece a second shot was a
dashed rule across the whole body, which the simple view hid outright — leaving
the face people write single shots on with no way to add one. It is `+ Add shot`
in the tail of the row, on both faces.

## 2.22

**Duplicating a card no longer leaves a second copy of a cast member's picture
behind.** A cast member's files live on the card while a piece is one shot, and
move into the project references the moment it grows a second one — they have to
be somewhere every card can see them. Duplicating the only shot does both at
once: the copy makes the piece a strip, and the move that follows only ever
looked at card 1. So the original's picture was promoted to `@ref-3` and the
clone kept a second copy of the same file under the handle the original had
worn, claimed by no member, invisible in the cast shelf and paid for again at
queue time. The copy now follows the file it is a copy of, and prose that named
it follows the rename. Reported in #27.

**The fullscreen editor's Render button reaches its node on every ComfyUI
frontend.** The button queues one node rather than the whole graph, and the
argument that says which node means two different things depending on which
frontend reads it: 1.47 and 1.49 and later take `{queueNodeIds: [...]}`, while
1.44, 1.45 and 1.48 take the whole argument *as* the list and forward it to the
server untouched. On those the server looked for the node id among the keys of
an object, counted no output nodes, and refused the prompt — "The prompt has no
outputs", about a graph whose output node was on screen. It is sent as a bare
array now, which is the one shape all of them read alike. Reported in #27.

**And a refused prompt gives the button back.** ComfyUI catches a refusal
itself — it puts the dialog up and answers as though nothing went wrong — so the
row went on saying "Sampling" over a render that was never queued, and the only
thing left to press was Cancel. The row now spends its optimism on the queue
actually accepting something.

**The turbo lead-in says what it needs instead of failing deep in the sampler.**
Its second sitting starts with the noise switched off, and ComfyUI before
2026-08-11 built that noise from the picture alone — H3's soundtrack was not in
it, and the first step died on a tensor size that named neither the lead-in nor
the fix. The render now stops before anything loads, with the version to update
to and the setting to turn off.

## 2.21

**This pack takes its colours from ComfyUI's palette instead of drawing its own
dark one over the top of it.** Every colour in the pack was a literal — around
three hundred of them across the stylesheet — written for a dark desk and drawn
unchanged on a light one, so the Appearance settings had no say over any node
this pack puts on the canvas. All of them now derive from two variables ComfyUI
writes for whatever palette is in force: the ground it draws chrome on and the
colour it writes text in. Surfaces, borders, the quiet weights of text and the
films over video are mixed from those two, in oklab rather than sRGB so that a
step that reads as one step off near-black still reads as one step off
near-white. Because the palette variables are written for *every* palette and
not only for light and dark, this is not a light mode — it is Nord, Solarized,
Github, Arc, and any palette you built yourself. The amber accent, the three
role hues and the eight reference hues stay the pack's own: they identify
something rather than describe the palette. The one concession is that the amber
is drawn a shade deeper on a pale palette, because amber on white is not a
colour a word can be written in.

**The Appearance tab has a text size.** One multiplier over every size in the
pack — the node faces, the fullscreen editor, the timeline, the picker, and the
settings page itself, which is why the words move as you choose. A multiplier
rather than a set of named sizes because the sizes were never a scale: fifteen
distinct values, each chosen against the thing beside it. Text and the controls
that carry it move with it; the room around them and the picture do not, which
is the line between a text size and a magnifier. Nothing of ComfyUI's own moves
with it.

**It also has a surface separation.** The surface ladder is proportional to a
palette's own contrast, and some palettes have very little to be proportional
to: on Github, Nord and Solarized the four surfaces came out close enough
together to read as two. One multiplier pushes all four rungs further off the
ground or pulls them closer, and it works on any palette, including ones that do
not exist yet.

**And a colour setting, for the one case following the desk gets wrong.** A
frame judged against white is judged against the wrong thing, which is why the
tools that cut and grade are dark. "Dark in fullscreen" keeps a dark ground for
the fullscreen editor whatever the desk is set to. It stops there deliberately:
a node body sits inside a node ComfyUI draws in its own palette, so pinning the
body dark on a light desk does not give you a dark editor, it gives you a dark
island in a white card. Node faces keep following the palette.

## 2.20

**Casting a look no longer files a copy of its frame in your input folder.** The
style atlas ships its thousand frames inside the pack, but casting one used to
fetch the picture back out of the browser and upload it into
`ComfyUI/input/style_refs/` — purely so it would have the kind of address the
rest of the pack understands, which is a path under input/. The copies were
permanent and one per look ever cast: a shelf of catalogue frames in the picker,
and a row in every core LoadImage combo on the canvas, for a file that was
already on disk twice. A look's frame is now cited where the pack ships it,
`atlas:000123`, and two resolvers know that address — one for the browser and
one for the graph. Frames cast before this keep working: they are ordinary input
files and nothing stopped reading them, so the old `style_refs` folder is yours
to delete once no saved workflow points into it.

## 2.19

**The tool rail is a set of columns rather than a row of tiles with a gap
between them.** A tool is a square with a label under it, and the label is the
wider of the two — "Add image" is half again the width of the box above it — so
a gap tuned to the squares left barely two pixels between one word and the next,
and the rail read as one run of prose with pictures over it. Every tool now
occupies a column of the same width, wide enough that the space between two
labels is space. The squares keep their rhythm; the words get their own.

**In the window the rail is a grid, and it wraps by tool.** Two things were
wrong with it as a wrapping row. Each row spaced its own contents, so a row of
eight and a row of three shared no vertical line anywhere. And the two clusters —
what writes this shot, and what outlives it — were unbreakable blocks, so the
machine's three fell to a line of their own the moment the column narrowed,
leaving a hole across the end of the row above them. Fixed tracks and clusters
set to display:contents answer both. The one-line rail on the simple card keeps
its hairline between the clusters; a rail that wraps by design cannot mark
anything with one, so it does not try.

**The refiner's chevron stays in its corner at every tile size.** It was placed
by two offsets that suited the node face's 56px square, and the window draws a
44px one — so in the shell it hung out past the tile's right edge, over the gap
beside it. The tile is a token now (`--mmc-tool-tile`), the chevron is measured
from it, and the three places that draw a smaller tile set the token rather than
a width.

**On the simple card the cast drawer is gone until you ask for it, and gone
again when you ask twice.** Clicking a name in the sentence is the only thing
that puts it there, and clicking the same name takes it away — that second press
had stopped working. The body the card borrows is the node's own, `nodeId` and
all, so the question "is the drawer a row of me?" was answered by asking whether
there was a node behind it, which is yes for both views and true of only one.
The card says which view it is now, and the answer decides both halves of the
gesture. While the drawer was up-but-hidden it also kept the gap either side of
it: a host with a hidden row in it is still a row of the column, so the card
carried the drawer's space without the drawer. Empty hosts stopped costing a gap
generally, which is where the rest of the slack over the prompt came from.

**The prompt box says what "/" does.** It answers a slash with the cast
library, the input folder and the style atlas — somewhere to bring a thing in
from, where "@" cites what is already attached — and nothing on screen said so.
The placeholder named one opening and read as the complete list of what the box
does; it names both now.

**And the pre-stage and the shot are the same height.** They were two cards
centred on the ground, each as tall as its own contents, so the step before the
shot ended somewhere up the side of it and the pair read as debris rather than
as a row. They are wrapped in a row of their own now, which is only as tall as
the taller of them: same top edge, same bottom edge. The difference goes above
the button rather than below it, so Render still and Render sit on one line.

## 2.18

**A subject is a list of features now, and each one can be changed on its own.**
The reference guide writes a subject as a named list — "with thick white fur,
pointed ears, a dark nose, and a curved tail" — and names those same features
again in `retention_analysis`. A cast card holds that list, and every line in it
is either kept or has an arrow in it:

    long dark hair                 kept
    a blue cardigan             →  a red waxed jacket
    a thin silver necklace         kept

That is the answer to a question the node had no answer for: what if the clothing
should be different. The cardigan is named in the definition, because section 4.1
is "the referenced content is still used, but some defined characteristics are
changed" and a characteristic has to be defined before it can be changed, and the
retention line says which are retained and what the changed one became.

**The relationship marker is derived instead of picked.** All features kept is
`fully_preserved`; any feature changed is `partially_preserved`; taking somebody's
place is `attribute_transfer`. It was a menu of four words that changed nothing
but the word — picking *partly kept* wrote `partially_preserved` above a sentence
saying everything was retained, which is a marker you can set and a sentence that
ignores you. The override survives as the only way to reach `weak_reference`,
which nothing can infer from the cast.

**Nothing negative is written into `retention_analysis` any more.** Those lines
used to end "...and the source picture's background, palette, lighting, pose and
action are not", which is a sentence borrowed from what the compiler writes for a
*file*. Section 4.1 closes by saying not to treat what the target video adds as a
loss of reference fidelity, and there is not one negative clause in any of the
guide's four retention examples. `<Subject N>` means content abstracted from a
reference asset — section 2.1 — so the abstraction is already in the label, and
`<Picture N>` is the label that denotes a file and needs saying which parts of it
count.

**"Takes the place of" is a row on the card, not a menu item behind a thumbnail.**
Writing *@vera should replace the bench in @vid-1* in the prompt does nothing
structural: it lands in `detailed_description` and the two retention lines beside
it go on saying the subject is preserved whole and the clip is preserved whole,
with nothing connecting them. The row is offered on every open card whenever the
piece holds a clip to edit or continue, and filling it in is what produces the
`attribute_transfer` line — their features transferred onto the bench in
`<Video 1>`, whose framing, camera work and action are kept.

**A name in the sentence opens, and closes, whoever it names — and this time it
is tested.** Clicking `@vera` or `@lego_brickfilm` in the prompt has been meant
to open them on the cast shelf for several releases and has kept coming back
dead. The handler was never the problem: `PromptBox.refresh` rewrote the box's
children on every render, so the chip a press started on was detached before the
browser could finish the click on it. A press is a pointerdown and a click on the
same element, and any render at all — a pill moved, a probe answered, a commit
landed — took that element away mid-press. No error, nothing in the console, a
chip that simply does nothing. The box now leaves itself alone when the chips it
would build are the ones already in it.

Nothing caught it because the test drove `openCastMember` directly rather than
performing the press, and because the DOM shim under those tests could not match
`.mmc-ref-cast[data-handle]` and answered `false` to `contains` — so the two
guards the real handler runs were both unreachable. Both are fixed, and the
suite now presses the chip, checks that a render leaves it the same element, and
checks that a look opens the same way a person does.

Pressing the same name again shuts the card. The press is its own undo, rather
than leaving you to find the chevron on a card you opened by clicking a name.

And pressing a name no longer selects it. A click on a `contenteditable="false"`
chip is a node selection as far as the browser is concerned, so the name turned
into a blue block and stayed one until you clicked somewhere else — a lot of
noise for a press whose visible result is a panel opening under it. The selection
is cancelled at mousedown, where it is made, which leaves the click that carries
the gesture untouched. A file's chip is not a control and goes on selecting
normally.

Refine is told the features too. Left out, the rewrite would describe the blue
cardigan the reference has while the retention line beside it says the cardigan
is a red waxed jacket — two sections of one prompt disagreeing about one person.

## 2.17

**The prompt box shows what is actually sent.** The sentence you type has never
been the prompt H3 reads — the compiler wraps it in the reference guide's
sections — and until now the only way to find out what that came to was to read
the console. There is a rail under the box now — *what the model reads* — and it
opens onto the finished prompt for the pass this shot lands in, set out section
by section under the field names the model is handed. It comes from the compiler
itself rather than being rebuilt in the frontend, so there is no version of this
where the two disagree. On a timeline it follows the merge — cards merged into
one pass share one prompt — and it says which pass you are looking at.

It opens *under* your sentence, not in place of it. The first cut of this was a
pair of tabs that swapped the two, which was wrong three ways: the tabs sat on
the box's own `<summary>`, so a click that missed one folded the whole prompt
away; the panel re-read on every render and dropped every answer but the newest,
which while renders kept arriving was never the one that had landed, so it stayed
empty; and swapping meant that on a shot with nothing to declare — where the
compiler correctly adds nothing but a wrapper — the second view looked like the
first and read as broken. Stacked, the block holding your own sentence is marked
and everything around it is what the compiler added, which is the question the
panel exists to answer. A shot with nothing to declare says so in as many words.

This replaces the scope band, and the setting that gated it. *Reference scopes
in the prompt* is gone: every reference is defined and scoped now, always. It
was off by default, which meant the ordinary render handed the tokenizer three
files and told the model what none of them were for — and section 2 of the guide
is the whole rebuttal, since a label the prompt never defines is a label
pointing at nothing. There is no reading on which the old default was the better
prompt, so there is no longer a switch for it.

**A reference generation is written in the reference form, whether or not you
refine.** The three sections that are not the description — `subject_definitions`,
`summary`, `retention_analysis` — used to arrive only from a rewrite, so a piece
queued without one went out as a bare sentence with `<Picture 1>` substituted
into it: no wrapper, no definitions, nothing saying what kind of job it was. All
three are derived from what you already declared. The task-type prefix comes off
the clips' scope dials (`edit` is `video editing`, a camera reference is
`reference generation`, and the guide says so itself); the definitions come off
the chips; the retention markers come off what each label was declared to lend.
Every label defined now gets a retention line, which section 4.1 asks for and
nothing wrote.

What this does not do is write the guide's 350–500 words of shot description. No
rule turns one sentence into that. It builds the document; Refine still writes
the prose, and a refined section replaces the derived one.

**The form follows what the piece holds, not which checkpoint it routed to.** It
used to be built only for REF2VA, so a cast in a text-only generation got two of
the sections with the base form's body field — a hybrid neither guide describes.
People run reference-form prompts against T2VA and get what they asked for; the
weights do not police the field name. A piece with something to declare is now
written in the form built for declaring things, whatever it is about to be
encoded as. A bare sentence with nothing to declare still gets the base form.

**Two of the four retention markers were not in the guide.** The cast path wrote
`transferred` and `reused`; the guide's fixed set is `fully_preserved`,
`partially_preserved`, `attribute_transfer` and `weak_reference`. So the one
field whose vocabulary the guide spells in English in every language was being
handed a token the weights never saw — and on exactly the case that needs it
most, since a subject who stands in for somebody derives that marker. The
refiner's glossary and `prompts/modes/ref2va.txt` always had the right four;
this is the third copy agreeing with them.

**Somebody can stand in for a person in more than one clip.** *They take
somebody's place in this* held a single file, so the same person in a medium
shot and a close-up could not be said: the second clip could only be attached
and left undefined. Both ways of working around it misfired — left at the
default scope the clip compiled to "is a reference video" and nothing else, and
set to `edit` it produced two sentences each claiming to be the whole source of
the edit. The slot takes a list now, the summary names every source in one
sentence, and each clip keeps its own definition and retention line. Two related
fixes fell out of it: the whole-video relationships are defined the way section
2.3 defines them (`<Video 1> is a source video for the target video edit.`)
rather than by borrowing the summary's opening line, and citing a subject
carries every clip they stand in for into that shot — it was adding the list
itself to a set of handles, so it carried none of them and the generation was
refused for a file the citation should have brought with it.

## 2.16

**The picture stopped moving.** The fullscreen editor kept every finished render
and the live stage in one scrolling column, so where the picture you were waiting
for sat was a function of how many you had already made: centred while the column
was empty, shoved to the floor by the first take, further down with every one
after it. The thing you were watching was the thing that would not hold still.

The two no longer share an axis. The picture region takes the whole height and
centres what is in it, always, and history runs left to right along a shelf under
the *window* — under the writing as much as under the picture, which is what keeps
the two level. A shelf inside the picture's own column would have taken its height
out of the picture and not out of the card, and they would have sat half a shelf
apart for as long as there was any history at all. It is reserved from the first
press rather than grown on the second take, for the same reason.

**And the clock keeps its place when it stops.** The elapsed readout counted up
through the render and then vanished at the moment it became the answer. It now
holds the total, in the same corner, in the same type — and every past take on the
shelf is captioned with what it cost, which is the one thing about a finished
render you cannot see by looking at it. The filename moved to the tooltip: along
a row of thumbnails it was the same truncated stem eight times over.

**A corner you can pull.** The live picture has a grip at its top right — drag to
size it between 40% and full, with a little gravity at 50, 75 and 100; double-click
for full; arrow keys for five points at a time. It grows and shrinks about its own
centre, so nothing else in the window moves, and the size is remembered the way the
Simple/Full switch is. The bottom edge of a render is spoken for three times over —
the progress rule, the readout, a finished clip's own transport — so the handle is
at the top, where there was nothing.

**One row, one kind of object.** The readout over the picture used to hold two
vocabularies: Gallery was a pill and everything beside it was bare text on a
gradient scrim, so a finished render carried a dark band across its bottom third
to make three words legible. Every chip now brings its own small ground and the
scrim is gone — the picture ends where the picture ends. The card the picture sits
in was carrying a shadow written for the canvas while the card beside it carried
another, so the two objects in the window sat at two different heights; they
match now, radius included, and the outline drawn before the first render is the
same shape as the picture that replaces it.

**Portrait renders got their own shape back.** A card that hugs a contained image
is not something CSS can work out on its own — a parent's shrink-to-fit width
comes from the image's intrinsic width and ignores any cap on its height — so a
portrait render sat in the middle of a box as wide as the file, letterboxed by
its own frame. The stage now measures the media when it loads and hands the ratio
over, which is the one fact the stylesheet could not derive.

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

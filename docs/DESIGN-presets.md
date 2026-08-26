# Presets

A preset is a setup you can put back. This says what one is, where it lives, what
happens when you apply it, and what the library that holds them looks like.

## What the node system actually holds today

Three blobs and a row of widgets, and any preset design that forgets the widgets
is wrong from the first line.

**`creator_data` / `timeline_data`** (piece, version 2) — `prompt`, `soundscape`,
`music`, `refined`, `aspect`, `short_edge`, `upscale`, `sample_edge`,
`refine_denoise`, `loras`, `assets` (the reference pool), `audio_tail_s`,
`models`, `turbo`, `render`, `output_prefix`, `segments[]`. A segment is an
ordinary state — prompt, assets, loras, duration, checkpoint pin — plus the seam
flags (`merge`, `continue`, `continue_audio`, `continue_from`, `feather`), or a
`kind: "clip"` card naming footage.

**`prestage_data`** (version 1) — `arch`, `prompt`, `aspect`, `short_edge`,
`init`, `refs`, `loras`, `turbo`, `quality`, `output_prefix`,
`models.{krea2,ideogram4,minimax}`, `minimax.{frames,latent_index,request}`,
`peer`.

**The sampler row is not in either blob.** `seed`, `steps`, `cfg`,
`sampler_name`, `scheduler`, `shift_video`, `shift_audio`, `block_cache`,
`spectrum`, `spectrum_blend` are stock widgets that `sampling.js` hides and
redraws as pills; `graphToPrompt` reads them from `node.widgets`. A "preset that
includes everything" that stored only the blob would drop the turbo schedule, the
step count and the block cache — which is most of what anyone tunes.

The pack already solved this exact problem once. `stashPreStage` in
`web/creator.js` writes `{blob, sampling}` — the serialised state plus a
sweep of every non-blob widget by name. **A preset is that pair, named and kept.**
Nothing new has to be invented for the capture side; it has to be generalised
from one node to three and given somewhere to live.

## What a preset is

A preset is two records. The **index row** is everything a card draws, and the
**body** is what applying it writes.

```jsonc
// the row, in continuity.presets.json
{
  "id": "pm7k2f1a3b",           // opaque, time-ordered, generated once
  "name": "Portal walk — long tail",
  "scope": "piece",             // piece | shot | prestage
  "note": "", "folder": "",     // a one-line note, and a user-made shelf
  "starred": false,
  "created": 1755100000, "updated": 1755100000,
  "version": 1,
  "sections": ["look", "weights", "speed", "prompt", "loras", "refs", "strip"],
  // The card's picture half, derived by `describe()` at save time so the grid
  // never fetches a body to paint a screen.
  "cover": { "path": "renders/H3_00214_.mp4 [output]", "v": 1755100000 },
  "lane":  { "runs": [ { "blocks": [ { "at": 0, "seconds": 6, "clip": false } ] } ] },
  "frames": [],                 // empty whenever there is a cover
  "facts": { "shots": 8, "passes": 5, "seconds": 134, "aspect": "16:9",
             "short_edge": 720, "route": "ref2va" }
}

// the body, in continuity.preset.<id>.json — only captured sections present
{ "version": 1, "id": "pm7k2f1a3b", "data": {
  "look":    { "aspect": "16:9", "short_edge": 720, "upscale": "two_pass" },
  "weights": { "fl2va": "…", "clip": "…", "route": "ref2va", "dtype": "fp8_e4m3fn" },
  "speed":   { "turbo": { … }, "row": { "steps": 20, "cfg": 1.0,
               "sampler_name": "res_multistep", "block_cache": "off" } },
  "prompt":  { "prompt": "…", "soundscape": "…", "music": "…", "refined": null },
  "loras":   [ { "name": "…", "strength": 0.8 } ],
  "refs":    [ { "handle": "ref-1", "kind": "image", "filename": "…" } ],
  "strip":   { "render": "chained", "audio_tail_s": 1.0, "segments": [ … ] }
} }
```

`speed` keeps the sampler row under its own `row` key rather than spread beside
`turbo`, because the row is written through `widgetIO` and the turbo block is
written into the blob — two destinations, and mixing them in one flat object
would mean deciding which was which by name at apply time.

### Sections, and why the preset is cut into them

"Everything" is the right default and the wrong only option. A preset that always
replaces the whole node is a preset you stop using the moment you have a prompt
worth keeping — you want *that look* on *this shot*, and a library whose only verb
is "overwrite my work" gets used twice.

So a preset stores whatever was captured, and applying it is per-section. The
sections are not arbitrary: each one is a set of fields that always move together
and that the node already treats as one thing.

| Section | What is in it | Owner today |
|---|---|---|
| **look** | `aspect`, `short_edge`, `upscale`, `sample_edge`, `refine_denoise`, `face` | the piece / the pre-stage |
| **weights** | the whole `models` block — files, `dtype`, `route`, `devices` | the piece |
| **speed** | `turbo` + every sampler widget | the node (blob + widgets) |
| **prompt** | `prompt`, `soundscape`, `music`, `refined` | the piece / the shot |
| **loras** | the global LoRA stack | the piece |
| **refs** | the reference pool (`assets`) / the pre-stage's `refs` and `init` | the piece |
| **strip** | `segments[]`, `render`, `audio_tail_s` | the piece |
| **shot** | `duration_s`, `checkpoint`, and the seam flags | one card |

The last is the one the first draft of this did not have. A card scope needs a
name for what is left when you take the prompt, the references and the LoRAs off
a segment, and "Timing & seam" is what that is: how long this card runs and what
happens in front of it. It exists only in the shot scope, where `strip` cannot.

Two fields are deliberately **never** captured: `seed` and `output_prefix`. A seed
is the one number that has to be different next time — `control_after_generate`
exists to make sure of it — and a preset that restores one turns "run it again"
into "run the same frame again". `output_prefix` is a per-machine preference that
`settings.py` already draws the line around; carrying one person's folder names
into another person's library would undo that whole argument.

`peer` is not captured either. It is a live node id.

## The three scopes

**`piece`** — a Creator/Timeline. All seven sections available.

**`shot`** — one card off a strip. `prompt`, `refs`, `loras`, `speed`-minus-turbo,
plus `duration_s`, `checkpoint` and the seam flags. Applies to any card of any
strip, and it is the scope that makes the library worth opening mid-edit: "a 6 s
continuation with feather 22 and these two LoRAs" is a thing you build once and
want twenty times.

**`prestage`** — a PreStage node. `look`, `prompt`, `refs`, `loras`, `speed`, and
its own `arch` + `quality` + per-arch `models` block.

### What crosses between them

The sections are the same *idea* in every scope but not the same *fields*, and
pretending otherwise is where this design could go wrong. The honest matrix:

| | → piece | → shot | → prestage |
|---|---|---|---|
| **look** | ✓ | — (the piece owns the canvas) | ✓ |
| **weights** | ✓ | — | only from a `minimax`-arch pre-stage, whose `request` *is* a creator request |
| **speed** | ✓ | sampler row only | ✓ (fewer widgets: no shifts, no cache) |
| **prompt** | ✓ | ✓ | ✓ |
| **loras** | ✓ | ✓ | ✓ |
| **refs** | ✓ | ✓ | pool ↔ `refs`, and the piece's keyframes ↔ `init` |
| **strip** | ✓ | — | — |

A section that cannot cross is **shown and disabled with the reason on it**, not
hidden. "Weights — this pre-stage runs Krea 2, and these are H3 checkpoints" is
information; a missing row is a bug the user reports.

## Where they live

**`api.storeUserData` / `getUserData`, exactly like the picker's favourites.** Not
a server route. `settings.py` opens by explaining when a route is required: the
save node reads settings *while a queued prompt executes*, and an execution has
no request behind it and therefore no ComfyUI user. Nothing about a preset is ever
read at execute time — a preset's whole life is over before the queue button is
pressed — so the condition that forced `settings.py` onto disk does not hold here,
and the userdata API is what the pack already uses for per-user UI state.

Two levels, because a library has to draw before it has read everything:

- `continuity.presets.json` — the **index**: one row per preset holding
  everything a card draws. A few hundred bytes each.
- `continuity.preset.<id>.json` — the **body**, fetched when a card is
  opened or applied.

Flat filenames rather than a `presets/` subfolder. The userdata API takes a path
and would almost certainly serve one, but a flat prefix needs nothing from it that
the picker's single file has not already proven works, and there is no directory
to create, list or clean up.

One file for both would mean rewriting a 24-shot timeline's worth of JSON every
time somebody stars something, and re-downloading every preset in the library to
draw one row of cards. The split is the picker's own lazy-grid reasoning applied
to a smaller grid.

Losing the index is recoverable: it is rebuildable by listing the bodies. Losing a
body is not, which is the normal deal for user data and the reason export exists.

**Starter presets ship as a JS module**, not as files on disk. `presets/builtin.js`
exporting a frozen array. They need no route to read, they cannot be corrupted by
a half-written file, and they cost one import. They are marked `builtin: true`,
render with a quieter card, and cannot be overwritten — "Save as…" from one makes
an ordinary user preset.

**Export and import are browser-side.** A preset (or the whole library) downloads
as JSON via a Blob URL and imports through a file input. No server, and it is the
answer to the one real weakness of userdata storage: presets do not follow a
workflow to another machine.

## The library

### The card's hero is the strip, and the strip carries the pictures

**The lane.** The timeline body already draws `renderLane` — blocks at their real
relative lengths, merged shots closed up under one casing, seams between them — at
a tenth size on the node face. That drawing *is* the shape of the piece, it is
generated from the data the preset already holds, and it is the one picture in
this pack that nothing else in the world looks like.

**And the blocks are filled with the real thumbnails, where there are any.** A
preset stores filenames — keyframes, pool references, clip cards — and every one
of them already resolves through routes this pack ships: `thumbUrl` for a clip's
server-decoded still, `viewUrl(path, {preview: true})` for an image as a q70 webp.
So a block that has a picture *is* that picture, at the width its seconds earn,
and the lane becomes a filmstrip of the piece rather than an abstraction of it.
Nothing new is stored: the card is drawn from filenames the preset had to hold
anyway.

Which picture, per block, first hit wins:

1. a **clip** card — its own thumb, through `/continuity/thumb`
2. the segment's **`first_frame`** asset
3. its **`last_frame`**
4. the first **reference image** the segment cites — its own `assets`, then the
   piece pool it cites by `@handle`
5. **nothing** — and then it is the flat block, exactly as drawn before

The fifth case is not a failure mode, it is the ordinary text-only shot, and a
whole text-only piece draws exactly the abstract lane. A filename this machine
does not have takes the same path: the request 404s and the block falls back
flat. The picture is derived decoration and its absence costs the card nothing —
the proportions, the seams and the facts line say everything load-bearing.

- A **piece** preset draws its lane, pictured where it can be. Lane height goes to
  ~52 px so a thumbnail reads at all; at 30 px it would be mush.
- A **shot** preset draws one block at the width its duration earns against the
  card — its keyframe or its reference, large enough to actually see.
- A **pre-stage** preset has no strip, so it draws the canvas: a rectangle at its
  true aspect, filled with `init` if there is one, else its first `refs` image.
  A still's shape is a still's characteristic artifact the way a strip is a
  piece's — and now it holds the still.

```
┌──────────────────────────────────────┐
│ [img][img]░[  img  ][img]░▓▓▓   ★   │  lane, true proportions, thumbs in it
│                                      │
│ Portal walk — long tail              │  15px / 600 / -0.01em
│ 24 shots · 2:14 · ref2va · 16:9      │  ui-monospace, 11px, dim
│ ▪ look  ▪ strip  ▪ loras  ▪ speed    │  section chips, tag hues
└──────────────────────────────────────┘
```

### The cover

A preset can also carry **one render as its cover** — the picture of what this
setup actually produced, as against the lane's picture of what it *is*. Both are
true and they are different things, so the card holds both rather than choosing.

**It is set automatically, and the rule needs no heuristic.** `stage.js` already
holds the finished render: the `executed` message stamped with this node's id
lands in `this.result = {url, name, isImage, saved}`, and `saved` is the
`{filename, subfolder, type}` shape the gallery listing itself produces. So at
save time the body hands over whatever is on its stage, and **the cover is the
render the preset was saved from** — you dial a setup in, you like what came out,
you press Save, and the thing you are looking at is the thing on the card. There
is nothing to guess and no "best frame" to pick.

Set by hand as well, through machinery that already exists:

- **Set cover…** opens `openPicker({kinds: ["renders"]})` — the gallery, the same
  window the rail's Gallery tool opens. Pick a render, done.
- **Update cover from last render** when a preset predates its best output.
- **Clear cover**, and the card falls back to the lane.

Never automatic *after* the first time. Saving fills an empty cover; nothing
silently replaces one you chose, because a card you recognise changing under you
is worse than a card that is one render out of date.

A cover is a video as often as a still, and it needs no special case:
`/continuity/thumb` takes an annotated `[output]` path — the routes resolve
through `exists_annotated_filepath` — so a clip cover is a few KB of
server-decoded JPEG, exactly as a picker cell is, and no `<video>` goes in the
grid.

**A cover is not a section.** It is never applied, never restored to a node, and
never sent anywhere: it is how the card is recognised. Applying a preset does
nothing to it, and a preset that names a render since deleted 404s and falls back
to the lane — the same honest fallback the blocks have.

### The hero, in three states

One band, fixed height, so the grid keeps its rhythm whatever a card holds:

1. **Cover set** — the cover fills the band, and the lane is redrawn as a thin
   ruler across its bottom edge: proportions and seams still legible at a glance,
   over the picture rather than instead of it.
2. **No cover** — the pictured lane at full band height, blocks filled by the
   priority above.
3. **Neither** — the abstract lane, the flat blocks, the text-only piece.

Each is the fallback of the one before it. There is one component here, not three
card designs.

**What this costs, and the two caps on it.** The index row has to carry the paths
or every card would need its body fetched before it could draw — so it holds
`cover: {path, v}` and a small `frames: [{at, path, v}]` list, block index to
filename plus mtime. `v` is what makes the thumb URL immutable-cacheable exactly
as the picker's is. `frames` is skipped entirely on a card with a cover, since the
ruler draws no pictures — one request instead of six. Otherwise capped
at the first **six** pictured blocks per card: past that the blocks are too narrow
to read and it is thirty requests to say so. And the grid lazy-loads below the
fold, the same sentinel the picker's already uses — a library of a hundred presets
must not open by asking for six hundred thumbnails.

Nothing is stored as *bytes* anywhere in this: a cover is a filename in the output
folder, a block's picture is a filename the preset already held, and both are
served by routes that shipped before presets existed.

Wide cards, `minmax(280px, 1fr)`, not the picker's 140 px squares — the content is
a line of prose and a line of numbers, and a square would waste the middle of
every one.

### Type and colour

House tokens throughout — `--mmc-surface`, `--mmc-line`, `--mmc-dim`, the modal's
`#161616` and 22 px radius — because a library that looked like a different
product would be the loudest thing in the pack.

Two deliberate departures, both earned:

- **A monospace utility face** (`ui-monospace, SFMono-Regular, Menlo`) for the
  facts line, the lane ruler and every duration. `2:14 · 24 shots · ref2va` is
  instrument reading, not prose, and it is the register the pack has never had a
  face for. Available offline, costs nothing.
- **The name set larger and tighter than anything else in the pack** (15 px / 600
  / −0.01 em against the 11–13 px everything else runs at). The library is a
  place, not a popover, and the type scale should say so before you read a word.

**Section chips take the existing tag hues**, one fixed hue per section —
`look → --mmc-tag-0`, `strip → 1`, `prompt → 2`, `loras → 3`, `weights → 4`,
`speed → 5`, `refs → 6`. The pack already assigns identity by hue and trains the
eye on it in the prompt box; a chip row becomes scannable for free, and no eighth
colour has to be invented.

Nothing takes the amber accent. `--mmc-accent` means *on* in this pack — turbo
engaged, a pill in force — and a card is not a state.

### Layout

```
┌─ Presets ─────────────────── Piece · Shot · Pre-stage ───────── ✕ ─┐
│ [ search......................ee ]        [ + Save current setup ] │
│ All · ★ Starred · Looks · Client work                              │
│ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                    │
│ │ card        │ │ card        │ │ card        │                    │
│ └─────────────┘ └─────────────┘ └─────────────┘                    │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

Scope tabs where the picker's kind tabs are, shelves where the picker's shelves
are, search where the picker's search is. A user who has opened the asset picker
once has already learned this window.

Clicking a card opens an **inspector** on the right of the same modal — not a
second overlay. It holds the editable name, the cover controls, and the section
list as checkboxes, each reading what that section actually holds — "2 LoRAs", "6
cards · 1 continuation", "20 steps · res_multistep · simple" — rather than
repeating what a LoRA is. Sections that cannot cross are dimmed with their reason
in place of the reading. The Apply button names its target and its count: **Apply
to this piece (5)**. Everything applicable is ticked on open, so the common case
is one click and the checkboxes are only in the way of nobody.

**No browser dialogs anywhere**, because nothing else in this pack has one and a
modal the page cannot style is the seam a library exists to hide. *Save current
setup* saves immediately under the first line of its own prompt and puts the caret
in the inspector's name field — the preset is the work and the name is a label on
it, so there is no reason to ask for the label first. *Delete* arms on the first
press and goes on the second, which is the picker's own deal for the same
irreversible verb.

### Applying, and getting back

Apply writes the blob widget and the sampler widgets. Both are recorded by
ComfyUI's own graph change tracking, so **Ctrl+Z is the undo** — worth confirming
on the target frontend before shipping, and worth doing nothing else about if it
holds. A snapshot layer of our own would be a second undo stack for the user to
learn and for us to keep in step with the first one.

The one thing apply must do beyond writing fields: **re-run the normalisers.**
`syncTimeline` prunes seams that the restored durations can no longer afford,
`normalizeCheckpoint` drops a pin the restored references make illegal, and
`parseModels` is what turns a stored block into a full one. Apply goes through
`parse* → mutate → sync* → serialize*`, never straight into the widget, so a
preset cannot put a node into a state the editor could not have produced.

Missing files are reported, not repaired. A preset naming a LoRA or a checkpoint
this machine does not have applies anyway and the affected chips render as
missing — which is exactly what a saved workflow from another machine already
does, and the same message says it.

## Taken from a render

Saving the current setup assumes the setup is still on a node. By the time you
know which render was the good one, you have usually moved on — three prompts
later, a different LoRA, the strip rebuilt. The setup is not gone, though: **both
save nodes embed the workflow that made the file**, the MP4 in its container tags
and the PNG in its text chunks, for the same reason core's savers do. So the
second way to make a preset is to point at a render and say *that one*.

Nothing is stored for this. It was in the files all along.

### The `prompt` tag, not the `workflow` tag

Both are written and they are not equally useful.

`workflow` is the canvas graph, and a node's settings are in it as
`widgets_values` — a **positional** array. This pack has already changed the
length of that row once, when the two flow shifts were added, so a render from
before that carries nine entries where the node now declares eleven and every
value after the gap lands one slot out: `steps` read as `shift_video`, silently,
with no error anywhere. It is also a stub for anything queued over the API, where
the graph is synthesised from the request and holds one node and no links.

`prompt` is the API form — `{"2": {"class_type": …, "inputs": {"steps": 20,
"cfg": 1.0, …}}}` — **keyed by name**, which is what `widgetIO` is keyed by too.
A widget the render predates is simply absent rather than shifting its
neighbours. That is the tag this reads, and the other is not consulted.

Which makes the capture side almost nothing: a read-only `widgetIO` over
`inputs`, the blob through `parseTimeline` → `syncTimeline`, and then
`capturePiece` exactly as a live node's capture calls it. A render whose blob is
a version-1 lone shot — the shape a Creator wrote before pieces had strips — is
promoted by `asPiece` on the way through, so an old render gives an ordinary
one-card piece with its writing and its references on the card, where they were.

`seed` is in the tag, plainly, and is not carried. The rule does not bend for
having the number to hand.

### The route this needed

One, and it is the only Python in the feature: `/continuity/render_meta`
opens the file and hands back the two tags parsed. The browser cannot read either
— an MP4's container tags are not reachable from JS at all, and no client-side
box parser is worth shipping for this. Two readers behind it, chosen by
extension rather than by trying one and catching, because `av` cannot see a PNG's
text chunks and PIL cannot open an MP4: a fallback chain would only turn "the
wrong reader" into "no metadata", which is the answer for a file that genuinely
has none.

This does not weaken the argument for keeping the rest of the feature off the
server. `settings.py` is a route because the save node reads it *while a prompt
executes*; this reads a file a finished execution already wrote, and a preset's
whole life is still over before the queue button is pressed.

A file with no tags is not an error. It comes back `{prompt: null, workflow:
null}` with a 200 — saved under `--disable-metadata`, or written by something
else entirely — and the library says which of those it is.

### Which node, when a workflow holds more than one

The render's own kind settles most of it: an MP4 came from a piece node and a PNG
from a pre-stage, so the ordinary PreStage → Creator pairing is never ambiguous.
Two Creators in one graph is, and nothing in either tag says which of them wrote
this file. The lowest node id wins, so one file always gives the same preset —
**and the library says so after saving**, rather than choosing quietly. The
preset is real either way; it may simply be off the other one.

### The cover comes free, and comes right

The render you picked is the cover. That is not a convenience, it is the
definition the cover section already argues for: the picture of what this setup
produces. The picker's row is `{path, kind, mtime}`, which is the shape a cover
is stored in, so it is copied field for field and no adapter exists.

The button sits beside *Save current setup* and, unlike it, is **not conditional
on a target** — it reads a file, not a node, so it works in the read-only library
the context menu opens, and on a machine whose renders came from somewhere else.
It opens `openPicker({kinds: ["renders"]})`, the same window *Set cover…* opens.
There is no new window in this and nothing new to learn.

## Where it hangs off the existing UI

- **`renderRail()`** on the timeline body and on the pre-stage body gains a
  **Presets** tool. On the timeline it joins the machine's cluster beside Gallery
  and Settings; on the pre-stage, whose rail has one group, it goes last.
- **`CreatorEditor`** gains a `presetTarget` option, drawn as the same tool in its
  right-hand cluster. That one option covers three cases at once: the piece's own
  face (which passes the *piece's* target, not its one shot's), the strip's card
  editor (which passes that card's), and the pre-stage's H3 branch.
- **`getExtraMenuOptions`** in `web/creator.js` already stamps a menu item
  on all three node ids; **Presets…** joins *Copy JSON* for nearly free, reading
  its target late off the mounted body — so a node whose body has not been built
  opens the library read-only rather than not at all.

One thing the wiring had to add: the timeline modal owns no sampler widgets — the
sampler belongs to the node, not to one shot — so `openTimeline` now takes an
`io` thunk from the body that opened it. Without it a card's preset could carry
its prompt and its seam but not the row it was dialled at.

**Where a target comes from, and why the node owns it.** Each body exposes a
`presetTarget()` returning `{scope, label, capture, apply, arch}`. The pre-stage's
lives on `PreStageBody` rather than on its editor for the same reason its arch
pill does: applying a preset can change the architecture, and the body that draws
one architecture cannot draw another — so the apply ends in `mount()`, which is
the same remount the pill does.

## Files

| New | |
|---|---|
| `web/creator/presets.js` | capture, apply, the section table, the storage pair |
| `web/creator/presetlib.js` | the library modal and the inspector |
| `web/creator/presets/builtin.js` | the shipped starters |
| `web/creator/styles/presets.js` | its stylesheet chunk, registered in `styles.js` |

| Touched | |
|---|---|
| `web/creator/timeline.js` | the rail tool, the piece and shot targets, `io` into the modal |
| `web/creator/prestage.js` | the rail tool and the pre-stage target |
| `web/creator/editor.js` | the `presetTarget` option and its rail tool |
| `web/creator.js` | the context-menu item |
| `web/creator/styles.js` | the new chunk, after the picker's |
| `web/creator/api.js` | `renderMeta`, the one call to the one route |
| `server_routes.py` | `/continuity/render_meta` and its two readers |
| `web/creator/locales/{ja,ko,zh}.js` | 81 new strings, in all three |

One route of Python, and only because a browser cannot open a file. Nothing here
is read at execute time, nothing here changes what is queued, and the backend has
no opinion about a preset that it does not already have about the blob the preset
restores.

## Tests

`tests/test_presets.py`, beside `test_js_bodies.py` and sharing its stub tree
minus the DOM — nothing in it renders anything.

- **Round trip.** Capture a piece with something in every section, apply all of it
  to a node with nothing in common, serialise: identical to the captured blob. The
  sampler row is checked with it, because it is not in the blob and a preset that
  dropped it would still pass a blob comparison — and the seed is checked to still
  be the target's.
- **A section left out is a section left alone.** Applying only `look` must not
  move the prompt, the strip, or the row.
- **Defaults reset.** The trap a naive merge falls into: the blob omits a field at
  its default, so a preset whose look never left native has to *put back* a node
  that did rather than silently leave it.
- **Seams normalise.** The same shot preset applied to card 1 has its continuation
  pruned (nothing in front of it) and applied to card 2 keeps it.
- **Cross-scope.** Every refusal is asserted to be a refusal *and* to carry a
  reason longer than a stub — a disabled row with nothing on it is the failure
  mode this design set out to avoid. The one legal weights crossing (a pre-stage
  on the H3 branch) is asserted in both directions.
- **Pre-stage → shot**, the direction the node pairing exists for: init becomes a
  start frame, style refs become references, handles cannot collide.
- **Shot/piece → pre-stage**, the direction back: the start frame becomes the
  init, references are re-handled and capped at three, and a video reference is
  dropped rather than half-applied.
- **The H3 branch's weights** are captured from the still's own request, reach a
  piece, and come back — the one legal weights crossing, asserted end to end
  rather than only at the `crossable` gate.
- **The card.** Merged cards draw under one casing without losing a block, the
  lane's block widths are the real durations, and a card with a cover collects no
  block pictures.
- **Storage and starters.** Save, list, read back, star, delete; and every shipped
  starter describes itself, holds only sections its scope can take, and names no
  file.
- **From a render.** The fixture is a real render's `prompt` tag, shortened only
  in its prompt text, and it is the awkward case on purpose: a version-1 lone-shot
  blob, and a row from before the flow shifts existed. It has to come back as the
  piece it was rendered from, with the shifts *absent* rather than shifted — which
  is the whole of why the `prompt` tag is read and not the `workflow` tag — and
  with the seed left where the target had it, though the tag carries one. Then
  which node wins in a paired graph, that two of a kind are reported rather than
  guessed, and that each of the three refusals says which reason it is.

There is no Python mirror to keep in step, which is the one nice thing about a
feature that lives almost entirely on the near side of the queue.

## What building it changed

Three things the design above got wrong, kept here because the reasons outlive
the corrections.

1. **A shot needed a seventh section.** `duration_s`, `checkpoint` and the seam
   flags had nowhere to live: they are not `prompt`, not `refs`, and `strip` is
   the piece's. `shot` — "Timing & seam" — is what is left of a card once the
   writing is off it.
2. **`feather` is a grid, not a number.** `state.feather()` only honours
   `FEATHER_GRID` (1, 5, 22, 39); anything else reads back as the classic single
   frame. A preset carrying 8 stored fine, applied fine, and quietly did nothing —
   which the round-trip test caught and a hand check would not have.
3. **The inspector's rows collided with its own text.** `.mmc-preset-row span` beat
   `.mmc-preset-box`'s `display: grid` at equal specificity, and the tick rendered
   off-centre. The wrapper has a class of its own now. Worth naming because it is
   the failure the stylesheet is most likely to repeat.
4. **A pre-stage keeps its weights in two places, and the H3 ones are not in the
   `models` block.** `serializePreStage` fills that block for the two *image*
   architectures only; the H3 branch's checkpoints live in
   `minimax.request.models`, because that request is an ordinary creator request.
   Capturing the wrong one looked correct — the section appeared, the chip
   counted, the apply ran — and carried nothing, so applying it *blanked* the
   target's weights. Exactly the failure the matrix above promised would work.
5. **References crossing into a pre-stage need new handles and the encoder's
   cap.** A handle is not decoration: `renderRefChip`'s remove button filters on
   `r.handle !== ref.handle`, so refs arriving without one all share `undefined`
   and removing any one chip removes every one of them. And a piece may hold nine
   reference images where Krea 2's edit path has three slots — a preset must not
   be able to produce a state the editor could not, which is the rule the
   normalisers exist for and the one place nothing was normalising.

Both of the last two were found by review rather than by use, and both now have a
test that fails without the fix.

## Open questions

1. **Does Ctrl+Z actually cover a programmatic widget write** on the frontend
   versions this pack supports? Apply writes both the blob widget and the sampler
   widgets, so in principle both are tracked; it has not been confirmed on a live
   canvas. If it does not hold, apply needs a one-deep "Undo apply" rather than a
   general snapshot layer.
2. **Should a preset be droppable onto the canvas** to spawn a configured node,
   rather than only applied to one that exists? It is the obvious next verb and it
   is a different interaction (drag out of the modal), so it is worth being a
   second pass.
3. **A shot preset has no automatic cover.** It is saved from a card, not from a
   node with a stage, and the piece's last render is the whole piece rather than
   that shot. It can be given one by hand from the gallery like any other; whether
   that is worth more than the block picture already on the card is a question for
   after some use.

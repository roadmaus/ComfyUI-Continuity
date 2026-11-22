# Continuity — the reel's deep tools

Spec for the second pass of the timeline redesign. Design and decisions, not
code. Written 2026-11-22 against `claude/laughing-edison-qnn86e`, after the
reel replaced the timeline modal (`web/creator/timeline.js`, `Timeline`).

## 1. Where things stand

The reel is one window: one line of header (length, what the next render will
do, **Shoot**), the script on the left (the cast and references as faces and
frames, then the scene, its sound and score, then a paragraph a shot), the
player over one inspector on the right, and the piece at its real length
underneath. Nothing selected means the piece is selected. Everything is
written, watched or selected; nothing is a shelf, a disclosure or a pill bar.

Some editors are whole apps of their own, and the first pass left them as they
were, opening as sheets over the reel:

| Tool | Opened from the reel by | Lives in |
|---|---|---|
| LoRA library and manager | Look, Edit / Add a LoRA | `loras.js` `openLoras` |
| File picker | Add to the piece, a shot's Pictures `+`, Replace the file | `picker.js` `openPicker` |
| A cast member's card | Open their card; Someone new | `cast.js` `CastShelf` |
| A shot's rarer tools | More for this shot; double-click a card | `editor.js` `CreatorEditor` in `openEditorSheet` |
| What a storyboard carries over | A sheet holds, What carries over | `Timeline.storyboardHold` |
| Frame and resolution pickers | Frame, Resolution | `pills.js` popovers |
| Rewrite settings | Refine every shot's chevron | `refine.js` |

They work, and they look like the old pack. This spec is how each becomes part
of the reel.

## 2. Principles, carried over from the reel

1. **One place per thing.** A setting is edited where it is shown. If the
   inspector shows a value, the inspector is where it changes.
2. **Inspector first, sheet second.** Anything that fits in rows goes in the
   inspector for the selection it belongs to. A sheet is only for work that
   needs room to look at many things at once (a library, a folder of files)
   and it opens beside the reel, not over it: the reel stays visible and the
   choice lands where you can see it.
3. **Say it when it differs.** Defaults are not labelled. A tag, a colour or a
   line of text appears only when something is not what it would be by default.
4. **Nothing hides without a reason.** A control that cannot apply stays,
   disabled, with one plain sentence of why.
5. **Same vocabulary.** Shot, join, pass, take, kept, reshoot, cast, reference,
   look, scene, sound, score.

## 3. The tools

### 3.1 Look (LoRAs)

Today: the piece inspector's Look row shows the stack as chips that switch on
and off; strength and order, swapping a file and the library are the manager
sheet. A shot's own stack only shows as names; adding one opens the shot
editor.

Target:

- **Look row, inline.** Each chip gets a strength scrubber (drag on the chip,
  or arrow keys while focused), a context menu (swap file, remove, move
  earlier/later) and the trigger words as a quiet second line when the family
  uses them. The turbo LoRA is drawn as the switch's, not as a file.
- **Shot Look row** is the same control on the shot's own stack, with the
  piece's stack shown above it dimmed, so it is clear what the shot adds.
- **The library** opens as a side sheet anchored to the inspector: search,
  folders, preview images and metadata on the left, the current stack on the
  right; picking adds to whichever stack (piece or shot) opened it.
- Pins (family LoRAs the pack keeps on) are chips with a pin glyph and no
  remove.

### 3.2 Files (the picker)

Today: every "add a file" opens the picker modal.

Target:

- **Drop anywhere.** A file dropped on the script becomes a reference of the
  piece; on a shot's row, that shot's; on the reel's sound thread, a laid
  track at the drop time; on a face, another picture of that member.
- **The picker as a side sheet** with the input folder, recent renders and the
  style atlas as three sources, a big preview, and "Use as" choices that match
  where it was opened from (a reference, a start frame, an end frame, a voice).
  Video and audio show the trim window inline before they are added.
- The cast row's `+` keeps its three answers (someone from the library,
  someone new, a file) and drop is the shortcut for the third.

### 3.3 A cast member

Today: the inspector shows their pictures and where they are used; their card
(looks, wears, voice, saved pictures as latents, rename, remove) is the cast
sheet.

Target, all in the inspector when a face is selected:

- **Header**: their handle, editable in place (renaming rewrites every
  citation, as today), what they are (person, thing, place, look) as a
  segmented control.
- **Pictures**: the strip of their files with drag to reorder, each with a
  menu (crop or cut out, taken for, detail, remove). The first is their face
  in the row.
- **Wears**: one line of text, the same as the card's.
- **Voice**: a sound file or "describe a voice"; plays inline.
- **Kept for**: this piece / the library (the roster save), with the library
  state said in one line.
- **Saved pictures** (refmod latents): a compact list of families they are
  saved for, with a "save for this model" action and its progress inline.
- **Used in**: the shot numbers as links that select those shots.
- Removing them asks once, in place, and says what goes with them.

### 3.4 A shot's rarer tools

Today: "More for this shot" opens the full shot editor (references with roles,
start and end frames, screens, routing and checkpoint, presets, the shot's own
refine, what the model reads).

Target, as sections of the shot inspector that appear only when used, plus one
"Add" menu at the bottom of the inspector that lists what is not used yet:

- **Frames**: start frame and end frame as two thumbnails with clear/replace.
  A start frame disables continuing the join in front, which the join already
  says; the shot says it too.
- **Pictures**: references with their role (taken for) and detail, as in 3.3.
- **Screens**: each screen as a row (where it is, what plays on it).
- **Model route**: shown only when the shot overrides the piece; otherwise one
  line in the Add menu.
- **Rewrite**: the shot's own refine, with its result shown in the script row
  as a second, dimmed paragraph that can be switched on and off, instead of
  hidden in a sheet.
- **What the model reads**: stays a sheet (it is a long read), opened from the
  inspector footer.
- **Presets**: save this shot / apply a preset, from the inspector footer, as a
  small popover list rather than the full library.

### 3.5 Storyboard: what carries over

Today: Firm / Partial / Loose in the piece inspector; the wording of what
carries over opens as a sheet.

Target: an inline text line under "A sheet holds", with "Use the default"
beside it when it has been changed. No sheet.

### 3.6 Frame, resolution and rewrite settings

Today: popovers from the piece inspector.

Target: the frame presets as a segmented control with the canvas size said
beside it; "From a picture" opens a small list of the pictures the piece has
(start frames, references, clips) inline. Resolution as a segmented control of
the family's legal short edges, with the two-pass upscale as a switch and its
settings revealed under it. Rewrite settings (model, template, language) as
rows revealed under the Rewrite row by its chevron.

## 4. The rest of the reel (phases 3 to 5)

These were planned before this spec and are listed so nothing is lost.

- **Whole-piece player.** The player plays the piece end to end, with the reel
  as its scrubber and a playhead on it. Click on the reel to seek.
- **Loop a join.** Selecting a join offers "Loop this join": the player plays
  about three seconds around the cut on repeat, with the blend drawn on its
  own small timeline, so the blend is judged while it is changed.
- **Stacked takes.** A reshoot keeps the old take. The shot's inspector shows
  every take as a strip; the player compares two side by side; choosing one
  keeps it. Needs `take` to become a list with a migration in `state.js` and
  `compile.py`.
- **Shooting live.** The reel fills pass by pass while a render runs, and the
  player plays what is done. Needs a per-pass message from the backend; today
  takes arrive when the node finishes.
- **Laid tracks on the thread.** Drag to move, drag the ends to trim, as the
  old lane did, directly on the reel's sound thread.
- **The node face as a mini reel.** The node shows the filmstrip at true
  proportions and the next-render line; clicking a shot opens the reel on it.

## 5. Order

1. Look inline (3.1) and frame/resolution/rewrite inline (3.6): small, and the
   piece inspector is the first thing everyone sees.
2. Cast member in the inspector (3.3) and drop anywhere (3.2).
3. Whole-piece player and loop a join (4).
4. The shot's rarer tools (3.4) and what carries over (3.5).
5. Stacked takes, shooting live, tracks on the thread, node face (4).

# Continuity — the blockout bench, rebuilt

Spec for replacing the blockout bench with a bench that directs a whole piece
in 3D. Design and decisions, not code. Written 2026-11-24 against
`preview/blockout-three-ways`, which sits on `claude/laughing-edison-qnn86e`
(the reel).

The reference is `docs/proposals/blockout/blockout-bench.html`: one
self-contained page, open it in a browser. It is built from the pack's own
tokens and the reel's and the bench's own CSS, copied from this branch, so what
it shows is what the result should look like. **Its JavaScript is a stand-in
and is not to be ported**: it has its own state object, its takes are graded
clay renders, and Shoot is a timer. Where this spec and the prototype disagree,
this spec wins. Where neither says, ask.

## 1. The idea

Today the blockout bench stages one shot. You build a set, walk a camera
through it, write a guide clip into `input/continuity/blockout/`, and attach
that file to a shot by hand. The set and the shot do not know each other.

The new bench stages the piece. It is **its own window, opened where the
blockout bench is opened today, and it replaces that bench completely**. It
works the way the reel works (a script of shots, joins, kept takes, reshoots,
one Shoot) with a 3D stage as its main surface. **The reel is not changed.**

The bench and the reel are two windows on the same piece: the same shots, the
same takes. A shot staged and shot in the bench is a kept take in the reel. A
shot written in the reel is in the bench's script, with no staging until it is
given one.

Other tools (Intangible, Higgsfield's 3D workspace, Autodesk Flow Studio,
Blender bridges) stop at exporting a reference clip. None tie the set to takes
and joins. That is what this bench adds.

## 2. What it is

1. **A set per scene.** A hard cut starts a scene, as it already does for the
   keystone. A scene has a set: walls, blocks, posts and people. A hard cut may
   also keep the set it had (same room, new angle); the join says which.
2. **A staging per shot.** The shot camera's marks, and marks for each person:
   where they stand, which way they are turned, how far they are tipped, how
   far off the floor. Between two marks a person goes from one to the other.
3. **The set is shared, the blocking is not.** Moving a wall or a table changes
   the set and so every shot of its scene. Moving a person changes only the shot
   you are on.
4. **The glass has four views.** *Stage* (clay, grid, camera, names),
   *Guide* (the pass exactly as the file will hold it), *Still* (one frame
   rendered by an image model from the depth pass, to check the look), *Take*.
5. **Three columns over a strip.** The script on the left, the stage in the
   middle, one inspector on the right, and the piece at its real length
   underneath. Nothing selected means the piece is selected.

## 3. Rules

### 3.1 What releases a take

These are the reel's rules (`docs/timeline.md`, Kept takes and reshooting),
with staging added. They live in the shared state, not in either window, so the
reel shows the same tags without knowing about the stage.

- A change to a shot's camera marks, a person's marks in that shot, its guide
  pass or how firmly the guide holds releases that shot's take, and the shots
  that follow it across a continuing join, as any other change to the shot does.
- A change to a set (a piece moved, turned, resized, renamed, added or removed)
  releases every shot staged on it.
- Free look, selecting, scrubbing and switching views release nothing.

A shot's stamp (`creator/timeline.py`, `stamps`) must include its staging and
its set, so the backend agrees about what changed.

### 3.2 A new shot starts where the last one ended

Enter at the end of a shot makes the next one on the same set, with the camera
where it stopped and everyone on their last marks, as a continuing join.

### 3.3 A continuing join has to line up

At a continuing join the frames handed over come from the previous shot's end.
If the next shot's first marks put the camera or a person somewhere else, the
guide contradicts those frames. The join says so (camera distance, turn, who
moved and how far, a change of posture) and offers *Start shot N where shot N−1
ends*. The join's circle on the strip wears the accent while it does not line up.

### 3.4 Orientation

Every piece can be turned on three axes and lifted, as the bench's Turn and
Move already allow. Keep the bench's handles (the three rings, the axis drags,
15° snap), not the prototype's simplified drag. Two things the prototype adds
and that should stay:

- **A piece rests by itself.** Whichever way up it is, its lowest point sits at
  its height off the floor, so a figure laid flat never sinks into it.
- **The staging sentence says the posture.** From the angle and the height:
  *lying on the floor*, *leaning*, *upside down*, *1.4 m off the ground*, and
  *ends standing* when it changes within the shot. The words carry the action;
  the guide only places the body.

No rig, no joints, no pose library. A lying or flying person is a block laid
flat or lifted. Whether H3 reads that as intended is not yet measured (see 8).

### 3.5 What a shot sends to the render

- **The guide.** A clip along the shot camera's path, `Math.round(seconds × fps)`
  frames on the family's grid, at the family's native canvas, in the pass the
  shot asks for. It reaches the model through the existing guide path
  (`creator/guide.py`, `attachGuide` in `state.js`): an asset with role `guide`
  and the switch on. H3 takes it through the ControlNet-Union branch, LTX 2.5
  through the Union Control IC-LoRA. A family whose manifest has no
  `capabilities.control` gets the words only, and the Guide row says why.
- **The words.** The staging sentence and the camera sentence, from the bench's
  own `stagingSentence` and `moveSentence`, placed where the bench's Copy would
  have pasted them. Refine must keep them.
- **How firmly.** *Firmly* is strength 1.0, *Loosely* 0.6. Default firm. For a
  shot whose people change posture or leave the floor, suggest loose.

The guide is derived, not a file the user manages. Write it under
`input/continuity/blockout/` keyed by the shot's staging stamp, reuse it when
the stamp matches, and sweep the ones no shot points at. Because it is an
ordinary guide asset on the shot, the reel renders a staged shot correctly
without any change.

## 4. What the old bench did that must still work

The new bench replaces `openBlockout` and everything behind it. Nothing the old
one did may be lost:

- **A guide for a still.** Opened from the pre-stage, or with one mark, it
  writes a picture, not a clip. The new bench opened without a timeline is a
  piece of one shot: no strip, no joins, and *Write the guide* in place of Shoot.
- **The four passes**: As staged, Depth, Blocks, Lines.
- **The starting arrangements**: Two-shot, Corridor, Interview, Street corner,
  Bare floor. They become ways to start a set.
- **Plays and Called**, the staging prose, and Copy.
- **The saved scene.** A `.json` beside an old guide still opens: its `objects`
  become a set, its `marks` and `duration` a first shot.
- **The targets it could send to** (`guideTargets()` in `fullscreen.js`).

## 5. Where it lives

| Thing | Today | Target |
|---|---|---|
| Entry | The Blockout card in `fullscreen.js`, `openBlockout({ targets, cast, family, back })` | The same card and the same call open the new bench, now also handed the piece |
| Scene format | `blockout.js` `scene()` / `restore()`: `objects`, `marks`, `shot`, `view`, `duration`, `aspect`, `pass` | Split: `objects` become the set; `marks` and per-person marks become the shot's staging |
| Renderer | `blockout.js` software rasterizer | Reused as is. One renderer draws the stage, the guide and the strip's cards |
| Sentences | `blockout.js` `stagingSentence`, `moveSentence` | Reused, plus posture (3.4) |
| The piece | `state.js` segments, `hold`, `takeOn` | The piece gains `sets`; a segment gains `set` and `staging`. A piece without them behaves as now |
| Script, strip, inspector rows, takes, undo, Shoot | `web/creator/timeline.js` `Timeline`, `styles/timeline.js` | Shared with the bench. Lift what both windows need out of `Timeline` so neither copies the other; the reel's behaviour and look must not change |
| Guide | `attachGuide`, `creator/guide.py`, `ContinuityGuideFrames` | Unchanged. The bench attaches the derived clip for the shot |
| Stamps | `creator/timeline.py` `stamps` | Include set and staging |

Name: the prototype's window is titled *Blockout* because it replaces that
bench. `stage.js` and `director.js` already exist in `web/creator/` and mean
other things, so do not reuse those names for the module.

A clip segment has no staging. A shot merged into a pass with others keeps its
own staging; the pass's guide is the stagings end to end.

## 6. The window, piece by piece

Follow the prototype for layout and wording.

- **Header.** The bench's name, the piece's length, undo and redo, what the
  next render will do, *Open the timeline* (the reel, on the same piece), Shoot.
- **Script column.** The reel's script, a size smaller: the cast as faces and
  the sets as frames, the scene with its Sound and Score, a paragraph per shot,
  *Write the next shot*. A hard cut says which set it goes to. A shot's tag sits
  under its words.
- **The glass** (the bench's `.mmc-bo-hud`). Top left: Stage, Guide, Still,
  Take, then Move, Turn, Lift (`1` `2` `3`). Top right: Free look / Through the
  lens. Bottom: play with the shot's time, the four adds, *Put the camera here*.
- **Through the lens.** Every gesture writes a camera mark at the playhead.
- **Inspector.** Rows as drawn for: the piece (Model, Frame, Guide, Sets), a
  set (Name, On it, Add), a shot (Length, Camera, Marks, Lens, Staging, Guide,
  Guide holds, Seed, what the model is given), a join (Continues, Blend,
  Staging or Set), a piece of the set (Plays or Called, Place, Turned, Tipped,
  In this shot or Size).
- **The strip.** The reel's, with a lane of set brackets above the film, a
  playhead, and a shot with no take showing its guide on its card, dimmed,
  tagged *Not shot yet · its guide*. Drag across a shot to scrub it.

## 7. Out of scope for the first pass

- Still (the image-model preview). Draw the switch, disabled, with its reason.
- Playing the whole piece end to end with real takes.
- Importing meshes, sets lifted from a take as splats, poseable figures.
- Any change to the reel's own window.

## 8. Not measured yet

Do these on a real machine before calling it done, and write the numbers into
`docs/timeline.md` the way seams and the keystone are written up:

1. Depth guide through the ControlNet branch, firm against loose, on a walk.
2. A block laid flat and a block lifted 1.5 m, each with and without the
   posture in the words. Does H3 draw a lying and an airborne person.
3. The guide together with the masked seam handoff and the keystone, on a
   three-shot continuing strip.
4. The guide together with a storyboard sheet. Both hold the camera.

Outside reports so far cover only the reference-video route (Ref2VA with a
Blender blockout): order, occlusion and relative height held, exact positions
drifted toward the centre, and a small turn on the spot was not followed. That
is one run per case and is not the route this spec uses.

## 9. Order

1. The format: sets on the piece, staging on the segment, old scenes read in,
   stamps, and the release rules (3.1) with tests. No UI.
2. Lift the shared parts out of `Timeline` (script, strip, inspector rows,
   takes, Shoot) with the reel's tests still green and its screenshots
   unchanged.
3. The bench's window on those parts: three columns, the glass with Stage and
   Guide on the bench's renderer, the guide derived and attached at render time.
4. Staging on the glass: Move, Turn and Lift with the bench's handles, the
   camera through the lens, the inspector rows, sets and their lane.
5. The join check and its fix, a new shot starting where the last one ended,
   posture in the sentence.
6. Everything in section 4, then remove the old bench and update
   `docs/tools.md`.
7. The measurements in 8.

One commit per step. Browser tests for the bench beside
`tests/browser/test-timeline-reel.cjs`.

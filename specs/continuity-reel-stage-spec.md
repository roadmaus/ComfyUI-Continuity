# Continuity — the stage in the reel

Spec for directing shots in 3D inside the reel. Design and decisions, not code.
Written 2026-11-24 against `preview/blockout-three-ways`, which sits on
`claude/laughing-edison-qnn86e` (the reel).

The reference is `docs/proposals/blockout/reel-stage.html`: one self-contained
page, open it in a browser. It is built from the pack's own tokens and the
reel's own CSS, copied from this branch, so what it shows is what the result
should look like. **Its JavaScript is a stand-in and is not to be ported**: it
has its own state object, its takes are graded clay renders, and Shoot is a
timer. Where this spec and the prototype disagree, this spec wins. Where
neither says, ask.

## 1. The idea

Today the blockout bench is a separate room. You build a set, walk a camera
through it, write a guide clip into `input/continuity/blockout/`, and attach
that file to a shot by hand. The set and the shot do not know each other.

The stage puts the set under the piece. A scene has one set. A shot is a camera
move and a blocking on that set, as long as the shot. The guide is made from
the staging at render time, and changing the staging is changing the shot, so
kept takes, reshoots and joins work on it with the rules the reel already has.

Other tools (Intangible, Higgsfield's 3D workspace, Autodesk Flow Studio,
Blender bridges) stop at exporting a reference clip. None tie the set to takes
and joins. That part is ours and is the reason to do this in the reel and not
beside it.

## 2. What it is, in the reel's own terms

1. **A set per scene.** A hard cut starts a scene, as it already does for the
   keystone. A scene has a set: walls, blocks, posts and people. A hard cut may
   also keep the set it had (same room, new angle); the join says which.
2. **A staging per shot.** The shot camera's marks, and marks for each person:
   where they stand, which way they are turned, how far they are tipped, how
   far off the floor. Between two marks a person goes from one to the other.
3. **The set is shared, the blocking is not.** Moving a wall or a table changes
   the set and so every shot of its scene. Moving a person changes only the shot
   you are on.
4. **The player has four views.** *Stage* (clay, grid, camera, names),
   *Guide* (the pass exactly as the file will hold it), *Still* (one frame
   rendered by an image model from the depth pass, to check the look), *Take*.
5. **Write and Direct.** At the player's height the stage is too small to work
   in. *Direct* is a second layout of the same window: the stage where the
   script was, the selected shot's own line under it, the inspector and the reel
   where they are. Selection, undo and the header are the same in both.

## 3. Rules

### 3.1 What releases a take

Added to the rules in `docs/timeline.md` (Kept takes and reshooting):

- A change to a shot's camera marks, a person's marks in that shot, its guide
  pass or how firmly the guide holds releases that shot's take, and the shots
  that follow it across a continuing join, as any other change to the shot does.
- A change to a set (a piece moved, turned, resized, renamed, added or removed)
  releases every shot staged on it.
- Free look, selecting, scrubbing and switching views release nothing.

A shot's stamp (`creator/timeline.py`, `stamps`) must include its staging and
its set, so the backend agrees with the reel about what changed.

### 3.2 A new shot starts where the last one ended

Enter at the end of a shot makes the next one on the same set, with the camera
where it stopped and everyone on their last marks, as a continuing join.

### 3.3 A continuing join has to line up

At a continuing join the frames handed over come from the previous shot's end.
If the next shot's first marks put the camera or a person somewhere else, the
guide contradicts those frames. The join says so (camera distance, turn, who
moved and how far, a change of posture) and offers *Start shot N where shot N−1
ends*. The join's circle on the reel wears the accent while it does not line up.

### 3.4 Orientation

Every piece can be turned on three axes and lifted, as the bench's Turn and
Move already allow. Use the bench's handles (the three rings, the axis drags,
15° snap), not the prototype's simplified drag. Two things the prototype adds
and that should stay:

- **A piece rests by itself.** Whichever way up it is, its lowest point sits at
  its height off the floor, so a figure laid flat never sinks into it.
- **The staging sentence says the posture.** From the angle and the height:
  *lying on the floor*, *leaning*, *upside down*, *1.4 m off the ground*, and
  *ends standing* when it changes within the shot. The words carry the action;
  the guide only places the body.

No rig, no joints, no pose library. A lying or flying person is a block laid
flat or lifted. Whether H3 reads that as intended is not yet measured (see 7).

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
the stamp matches, and sweep the ones no shot points at.

## 4. Where it lives

| Thing | Today | Target |
|---|---|---|
| Scene format | `blockout.js` `scene()` / `restore()`: `objects`, `marks`, `shot`, `view`, `duration`, `aspect`, `pass` | Split: `objects` become the set; `marks` and per-person marks become the shot's staging. One format, read by both the bench and the reel |
| Renderer | `blockout.js` software rasterizer | Reused as is. One renderer draws the stage, the guide and the reel's cards |
| Sentences | `blockout.js` `stagingSentence`, `moveSentence` | Reused, plus posture (3.4) |
| The piece | `state.js` segments, `hold`, `takeOn` | The piece gains `sets`; a segment gains `set` and `staging`. Migration: a piece without them has no sets and behaves as now |
| Guide | `attachGuide`, `creator/guide.py`, `ContinuityGuideFrames` | Unchanged. The reel attaches the derived clip for the shot |
| Stamps | `creator/timeline.py` `stamps` | Include set and staging |
| The reel | `web/creator/timeline.js` `Timeline`, `styles/timeline.js` | Player views, Direct layout, set lane, playhead, join check, inspector rows |
| The bench | `openBlockout` | Stays for a guide that belongs to no piece. Opening it from a shot opens the reel's Direct on that shot instead |

A clip segment has no staging. A shot merged into a pass with others keeps its
own staging; the pass's guide is the stagings end to end.

## 5. The window, piece by piece

Follow the prototype for layout and wording. The parts that are new to the reel:

- **Header.** A *Write / Direct* switch after the piece's length.
- **Script.** Sets sit in the cast row as frames, after the faces. A hard cut
  says which set it goes to.
- **Player HUD** (the bench's `.mmc-bo-hud`). Top left: Stage, Guide, Still,
  Take. In Direct, beside it: Move, Turn, Lift (`1` `2` `3`), and on the right
  Free look / Through the lens. Bottom: play with the shot's time, the four
  adds, *Put the camera here*.
- **Through the lens.** Every gesture writes a camera mark at the playhead.
- **Inspector.** Rows as drawn for: the piece (Model, Frame, Guide, Sets), a
  set (Name, On it, Add), a shot (Length, Camera, Marks, Lens, Staging, Guide,
  Guide holds, Seed, what the model is given), a join (Continues, Blend,
  Staging or Set), a piece of the set (Plays or Called, Place, Turned, Tipped,
  In this shot or Size).
- **The reel.** A lane of set brackets above the film. It uses the pass
  bracket's look and will collide with multi-shot passes: give sets their own
  lane above passes. A shot with no take shows its guide on its card, dimmed,
  tagged *Not shot yet · its guide*. A playhead across the film.

## 6. Out of scope for the first pass

- Still (the image-model preview). Draw the switch, disabled, with its reason.
- Playing the whole piece end to end with real takes (phase 3 of the reel spec).
- Importing meshes, splats lifted from a take, poseable figures.
- Writing a new shot from Direct. Switch to Write for that.

## 7. Not measured yet

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

## 8. Order

1. The format: sets on the piece, staging on the segment, migration, stamps,
   and the release rules (3.1) with tests. No UI.
2. The player's Stage and Guide views on the bench's renderer, read-only, and
   the guide derived and attached at render time.
3. Direct: the layout, Move / Turn / Lift with the bench's handles, the camera
   through the lens, the inspector rows.
4. The reel: set lane, guide cards, playhead, the join check and its fix.
5. A new shot starting where the last one ended (3.2), posture in the sentence.
6. The measurements in 7, and the docs.

One commit per step. Extend `tests/browser/test-timeline-reel.cjs` in each.

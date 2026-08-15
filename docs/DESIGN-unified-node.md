# One node

Merging `MiniMaxH3Creator` and `MiniMaxH3Timeline` into a single node whose face
grows from one shot to a strip.

The visual language does not change. Everything below is built out of vocabulary
this package already has — the perforation rail, the reel, the pill row, the
amber accent — because the two faces being merged were already drawn in it.

---

## 1. The thesis

A Creator render is already a one-segment timeline. `render.py` exists to say so,
`compile._timeline_canvas` step 1 says *"payload 1 is compiled exactly as a lone
generation would be"*, and `tests/test_creator_graph.py` asserts the two nodes
emit the same graph. The split is a fact about the UI, not about the work.

So the merge is not "add a mode to the Creator". It is: **the piece is always a
strip of shots, and a single shot is a strip with one card on it.** The face
follows the strip. There is no switch to find, no mode to be in, and no wrong one
to be in.

## 2. The rule that picks the face

> **The face is the smallest one that can show everything this piece has set.**

Derived on every render, never stored, never toggled:

```
single-shot face   ⟸  segments.length === 1
                      && no global prompt
                      && no pool assets
                      && no global LoRAs
                      && no soundscape or music
                      && not pinned to the piece view
strip face         ⟸  anything else
```

Plus one pin. A piece of one shot can be shown either way, and a **Timeline**
toggle on the pill row says which — kept in `node.properties`, not in the blob,
because it is a preference about this node and not something the render reads.

That toggle is not a convenience. Without it the piece-level fields are
*unreachable*: the standing prompt, the reference pool and the global LoRAs can
only be set on the strip face, and the only other way to the strip face is to
set one of them. You would need a second shot before you could write the
standing description the second shot is for. The pin only ever adds the strip —
it cannot take one away — so the guarantee below is not something a preference
can switch off.

The three extra clauses are what make it safe rather than merely tidy. A one-card
piece that carries a global prompt has something the single-shot face cannot
draw, and a face that cannot draw a field it still queues is a trap. Under this
rule the face can never hide state — which is also why no "collapse" button is
needed. Emptying the piece-level fields collapses it; that is the same gesture as
setting them, run backwards.

## 3. State A — one shot

Today's Creator face, unchanged, plus one band.

```
┌─ MiniMax H3 Creator ────────────────────────────────────┐
│  ▢ image   ▢ video   ▢ audio   ▢ LoRA     ▢ Gallery  ▢ ⚙ │   .mmc-rail
│  ⟨@img-1 start⟩ ⟨@vid-1 ref⟩                             │   .mmc-assets
│ ┌───────────────────────────────────────────────── [⤢] ┐ │
│ │ A slow push through the reeds at dawn, @img-1         │ │   .mmc-panel
│ │                                                       │ │
│ │ ⟨16:9⟩ ⟨768⟩ ⟨6 s⟩ ⟨pre-stage⟩            FL2VA ▸    │ │   .mmc-pills
│ └───────────────────────────────────────────────────────┘ │
│  ┄┄┄  ┄┄┄  ┄┄┄  ┄┄┄  ┄┄┄  ┄┄┄  ┄┄┄  ┄┄┄  ┄┄┄  ┄┄┄  ┄┄┄   │ ← NEW
│                    +  Write the next shot                 │ ←
│  ⟨seed 4211 ⟳⟩ ⟨20 steps⟩ ⟨res_multistep⟩ ⟨simple⟩ ⟨⚡⟩  │   sampling
└───────────────────────────────────────────────────────────┘
```

**Placement is the argument.** The band sits between the panel and the sampler
row, because `TimelineBody.render`'s own comment sets the order: *"the rail, what
you are asking for, then how it is run."* A second shot is part of what you are
asking for. It also sits *after* the shot, which is where the next shot goes.

**The band is unexposed film.** `.mmc-tl-empty::before` already draws a
perforation rail with `repeating-linear-gradient(90deg, var(--mmc-surface-3) 0
8px, transparent 8px 20px)` and it already means exactly this — the leader is the
unexposed stretch at the head of a reel. Here it is the unexposed stretch *after*
the exposed one. No new metaphor, no new token, four new lines of CSS.

It is quiet on purpose: `--mmc-dim` at 12px lifting to `--mmc-text` on hover, no
border, no fill. Most renders are one shot, and a control that shouted would be
wrong nine times out of ten.

## 4. State B — a strip

Today's Timeline face, unchanged. Nothing is redrawn; it simply becomes the other
half of one node.

```
┌─ MiniMax H3 Creator ────────────────────────────────────┐
│  ▢ image   ▢ video   ▢ audio   ▢ LoRA     ▢ Gallery  ▢ ⚙ │
│ ┌───────────────────────────────────────────────────────┐ │
│ │ Dawn on the estuary. Handheld, long lenses.           │ │
│ │ ▐1  6s▌▐2  6s▌▐▬▬▬ 3 · 4  12s ▬▬▬▌▐5  5s▌            │ │   .mmc-tl-lane
│ │ ⟨▤ chained · 5 segments⟩ ⟨◷ 29.0 s⟩ ⟨16:9 1366×768⟩   │ │
│ │ ⟨✦ 2 LoRAs⟩ ⟨▢ 1 piece ref⟩          [⚙ Edit timeline]│ │
│ └───────────────────────────────────────────────────────┘ │
│  ⟨seed 4211 ⟳⟩ ⟨20 steps⟩ ⟨res_multistep⟩ ⟨simple⟩       │
└───────────────────────────────────────────────────────────┘
```

The sampler row already knows about this transition: `sampling.js` takes
`perSegment` — *"true when there is more than one generation, which changes what
the seed and step counts mean."* The merged node feeds it the same boolean the
face rule computes. That control was designed for this before the merge existed.

## 5. The promotion moment

The single riskiest second in the whole design: the user has been writing in the
face's prompt box, clicks the band, and their writing surface is replaced by a
summary. Get this wrong and the feature is hated.

**So the face does not mutate behind them. The strip opens over it.**

```
click "Write the next shot"
   │
   ├─ segments.push(continuingSegment())     — the strip's own default seam
   ├─ openTimeline({ focus: 1 })             — the modal, card 2 already open
   │
   └─ on close: the face re-renders as State B
```

You watch your shot become card 1 while card 2 opens for writing. The promotion
is narrated by a window arriving, in the place the new thing lives, rather than
by the face silently becoming something else. When you close the modal the face
has changed — and you have already seen why.

Two rules for the move itself:

- **The prompt goes to `segments[0].prompt`, never to the global prompt.** The
  global prompt is *"the standing description every segment inherits"*; promoting
  one shot's description to a standing one would silently change what card 2
  generates. The global box stays empty and says so in copy that already exists.
- **The new card is `continuingSegment()`** — live seam on both tracks, medium
  feather. That is already the strip's own default for an appended card, and the
  face must not invent a second answer to the same question.

## 6. The demotion

Delete cards in the strip until one remains; clear the piece-level fields if you
set any. Close. The face is the editor again, text intact.

No control, no confirmation, no announcement. The strip is where cards live, so
removing a card is done where cards are. A dedicated "back to one shot" button
would be a second way to say a thing the strip already says.

## 7. Copy

The vocabulary is fixed by the strip's own leader, which offers **write a shot**
and **cut in a clip**. The band inherits it:

| Surface | Words |
|---|---|
| band | `+  Write the next shot` |
| band tooltip | `Add a second shot and open the strip. One shot or twenty, it is the same node.` |
| band, when the piece is at `MAX_SEGMENTS` | `+  Write the next shot` disabled, tooltip names the bound |
| node | `MiniMax H3 Creator` — one name, whatever the strip looks like |

Active voice, the action keeps its name into the strip (the strip's own add tile
says the same thing), and nothing on the band mentions "timeline mode" — because
there isn't one.

## 8. What is deliberately not added

- **No segmented control.** A `single ⁄ timeline` switch would be a control whose
  only job is to change which controls are visible, and it would let the user be
  in the wrong one. The count already answers it.
- **No "cut in a clip" on the band.** It is a real entry point, but two tiles on
  the face is the accessory to remove. It is one click deeper, in the strip,
  where the other one is.
- **No lane on the single-shot face.** One shot's lane is one block, which says
  nothing that the pills do not.
- **No second toggle for the way back.** The **Timeline** pill is one control
  with two states, in the same place and with the same word on both faces —
  the shape `pre-stage` already has. Two opposite buttons would be two controls
  for one question.
- **No transition animation on the face swap.** The modal opening *is* the
  transition. Motion in this package is `.12s ease` on background and border and
  nothing else; a face that slid would be the one animated thing in the pack.

## 9. The blob

One widget, timeline-shaped, always:

```jsonc
{
  "version": 2,
  "prompt": "",            // piece level — empty on a single-shot piece
  "soundscape": "", "music": "",
  "aspect": "16:9", "short_edge": 768,
  "upscale": "two_pass", "sample_edge": 768, "refine_denoise": 0.5,
  "assets": [],            // the pool. NOT a single shot's attachments
  "loras": [],
  "models": {}, "turbo": {},
  "segments": [ { /* prompt, assets, loras, duration_s, checkpoint, refined … */ } ]
}
```

`emptySegment()` is already `emptyState()` minus `version` plus two seam flags,
and `serializeCommon` is already shared. So creator → piece is a field partition,
not a conversion. Three placements to get right:

1. `creator.assets` → `segments[0].assets`. **Not** the pool: top-level assets
   mean *reference pool, cited by handle* here, and a keyframe cannot live there.
2. `creator.soundscape` / `music` / `refined` → `segments[0]`. That is the
   placement that round-trips when the piece collapses back to one card.
3. `aspect`, `short_edge`, `upscale`, `sample_edge`, `refine_denoise`, `models`,
   `turbo` → piece level, under the same names they already have.

### Migration

- **v1 blobs lift on read.** No `segments` key → wrap as one segment and hoist
  the seven piece-level fields. Must run *ahead of* `compile.timeline_segments`,
  which currently raises `"this timeline has nothing on it"` on that input. Same
  lift in `state.parseTimeline`. It is the exact inverse of the partition above,
  so one table drives both directions.
- **Node id stays `MiniMaxH3Creator`.** Older, and it is what you are doing
  whether the piece is one shot or twelve.
- **`MiniMaxH3Timeline` stays registered with `is_deprecated=True`** — hidden
  from the node search, still loads saved workflows. The frontend mounts the same
  body on it, so a legacy node behaves identically. Both classes already declare
  the same nine inputs in the same order (`creator_node.py:86` says this was
  deliberate), which is what makes the alias one class and no divergence.
- **Widget keeps the name `creator_data`.** ComfyUI restores `widgets_values`
  positionally so a rename would load, but the name is in the README, the
  right-click menu, and every `CompileError` string. Not worth the churn.

## 10. What the merge lets us delete

Not a side effect — this is half the reason to do it.

| Where | Goes |
|---|---|
| `creator_node.py` | The class body. `execute` becomes `timeline_payloads` on the lifted blob; the file keeps the extension registration and little else (~110 lines) |
| `creator_node.fingerprint_inputs` | Its private mtime walker; `timeline._stamps` is the survivor (~25 lines) |
| `DEFAULT_DATA` ×2 | One |
| `state.js` | `serializeState` collapses into the piece-level serializer — it is already `serializeCommon` + canvas + models + turbo, which is what `serializeTimeline` writes. `parseState`/`emptyState` stop being a blob format and become the segment format under their own names |
| `minimax_creator.js` | Three branches in `nodeCreated` → two; the `CREATOR` and `else` branches of `loadedGraphNode` unify onto `body.reload()`; one entry each out of `MIN_SIZE`/`WIDGET`/`SIDE` |
| `refine_routes.py` | `kind` drops to `segment`/`timeline`; the `kind == "creator"` early return goes. `cuts = shot_limit(seconds) if kind == "creator"` becomes `if len(segments) == 1` — which is *more* correct: a one-card timeline gets no cut request today and should |
| `tests/test_creator_graph.py` | Its headline assertion ("both nodes emit the same graph") becomes tautological. Replaced by a v1-blob-lifts-to-one-segment test, or the merge silently deletes the coverage that made it safe |

### One refactor worth doing alongside

`CreatorEditor`, `TimelineBody` and `PreStageBody` each implement their own
`adoptWeights`, `widgetIO`, `commit`-with-`Turbo.sync`, `destroy` and
`loadCatalog(...)` — three copies of the same five methods. The merge takes it to
two, which is the moment to lift them into one `NodeBody` base rather than the
moment to leave two. Behaviour-neutral; do it as its own commit so the merge diff
stays readable.

## 11. Risks

- **Discoverability of the band.** It is quiet by design, and quiet things get
  missed. The mitigation is that the band is the only thing between the prompt
  and the sampler row, on a face people already read top to bottom. If it turns
  out to be missed, the fix is the copy, not the volume.
- **The face rule surprising someone.** Setting a global prompt on a one-card
  piece flips the face to the strip. That is correct — the field is only editable
  there — but it happens *inside* the strip modal, so it is seen.
- **`compile_still.py:97` builds "the same segment payload MiniMaxH3Creator
  builds."** It is `compile_request`-shaped and survives untouched, since a
  segment is still a request. Same for `prestage.py` and `hires.py`, which pair
  with either node already. Worth a test, not worth a redesign.

## 12. Order of work

1. Blob lift, both sides, with the partition table as the single source (`state.js`, `compile.py`) — plus the v1 test.
2. Backend merge: one node class, `MiniMaxH3Timeline` deprecated alias.
3. `NodeBody` base extracted from the three bodies. Behaviour-neutral commit.
4. Face rule + the band + the promotion move.
5. `refine_routes` kind collapse and the `cuts` correction.
6. README: `## The node` and `## Timeline` become one section.

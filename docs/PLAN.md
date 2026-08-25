# Plan

Where this is going and why. The README describes what the code *is*; this is
the reasoning behind it and what is left.

## The goal

A Krea-style single-prompt experience for MiniMax H3 inside ComfyUI. One node,
one prompt box, media attached by `@` mention. Not a graph of director nodes.

## Why the `@` chip is the whole design

H3 is not prompted with free text. It expects a structured Context-IR in which
every reference is addressed by an ordinal label — `<Picture 2>`, `<Video 1>`,
`<Audio 1>`, `<Subject 3>` — and the Ref2VA form has six mandatory sections
including a `retention_analysis` with fixed markers.

Producing those labels by hand, in the order the tokenizer presents them, is the
actual difficulty of using the model. The `@` chip removes it: you attach media
and write "use @img-2 for her face", and the labels are assigned and substituted
for you. Everything else in this package exists to support that one gesture.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Backend | Local open weights | Runs offline through core's `nodes_minimax_h3`. No API key, no uploads. Costs 2K output and the hosted Context-IR preprocessor. |
| Surface | One node with a DOM body | Stays inside the graph, composes with other nodes, saves in the workflow. Matches how LTX Director is built. |
| `@` source | The ComfyUI input folder | "Add image" uploads via `/upload/image`, which writes to `input/` — so attaching and `@`-browsing are the same store. No separate asset database. |
| Duration | Whole seconds in the UI | The user asked for `6 s` on the pill. The 17n+5 grid is handled behind it; downstream sees the true value. |
| Checkpoints | Two MODEL inputs, routed | FL2VA and Ref2VA are different checkpoints. What you attach picks the mode; the mode picks which input is passed through. A new timeline pins its route to Ref2VA rather than auto: tested, Ref2VA is the stronger training — it handles text-only and keyframe payloads perfectly alongside references, a superset of what FL2VA was trained for — and one route means a strip mixing reference and plain cards runs on one set of weights. The pill still overrides it; a saved timeline keeps whatever it stored, and a models block without a route reads back as auto, exactly as it ran. The Creator node keeps auto. |
| Clip segments | Optional `trim`, one editor, two entry points | Whole clip stays the default and the grid stays a grid. The picker cell and the attached chip open the same modal, so the segment is chosen the same way before or after attaching. Cutting in `media.py` rather than asking for a pre-trimmed file keeps the input folder the only asset store. |
| Video sound | `track`: picture, picture+sound, or sound — sound on by default, probed | A clip chosen for its motion is usually wanted for its sound too. But the default is only right when there is a soundtrack to bind, and no browser reports that portably — hence `/minimax_creator/probe`, which reads the container header. A silent clip attaches silent instead of failing at queue time on a choice the user never made. Explicitly choosing a track in the segment editor outranks the default. |
| Sound without the picture | The same `track` field, routed into `ref_audios` by `compile.py` | A soundtrack you want to cite is often attached to a clip whose look you do not — a voice, a room tone, a piece of scoring. Making that a third value of the field that already decided picture-vs-picture-and-sound keeps one axis with three points instead of two booleans that can contradict each other. It is a bucketing question, not a loading one: the decoder already reads an audio stream out of an mp4, so the whole feature is which list the asset lands in, decided once in `compile.py` and mirrored by `state.js` so the slot counters agree. The clip keeps its `vid-N` handle — the handle names the file, not the bucket — so switching the picture back on never rewrites the prompt. |
| LoRAs | Managed in the node, patched onto the routed checkpoint | The node already decides which of the two checkpoints comes out, so it is the only place that knows what a LoRA would be patching. A LoRA trained against FL2VA does nothing on Ref2VA and says nothing about it — `load_lora` only logs the keys it could not place — so each entry names the checkpoints it claims, and one that lands somewhere it matches no keys is refused rather than quietly generating an unchanged video. |
| Trigger words | Copied onto the entry, prefixed at compile time, printed in the node | The sidecar is a cache, not a contract: it can be wrong, absent, or on a different machine, so the entry owns the literal words and a sidecar word is just a chip switched on. Prefixing is what every LoRA is documented against, but it edits a prompt the user cannot see edited — hence the line under the chips. `prompt_override` still bypasses the lot. |
| LoRA cards | Every sidecar layout the ecosystem writes, read through one merged record (`lorameta.py`) | A collection is rarely one program's output: the same folder holds files pulled by CiviMeta, by Civitai Helper years ago, by ComfyUI-Lora-Manager, and files somebody trained and dropped in bare. Reading only one layout meant most people's folders rendered as blank cards next to a `.preview.png` that was sitting right there. The record's field names are this pack's own rather than any one tool's, because CiviMeta's `meta.json` is *its* normalisation of Civitai — `name` is the model — while a raw `.civitai.info` is a model-version where `name` is the version, and reading the second through the first would put "v2.0" on every card and look fine. Merged per field, not per source: a website knows the title, a user who typed an activation text knows the triggers. Probing is one `scandir` per folder rather than one `stat` per guess, which is the difference between a listing and fifty thousand syscalls. |
| Prompt shape | A Context-IR skeleton composed at compile time, additive only | H3-Base was trained on H3-Context-IR's output, not on sentences: a mode instruction line, then `integrated_multimodal_description` / `overall_soundscape` / `non_diegetic_music`. We cannot write the prose without an LLM (that is phase 5) but the field names, the ordering, the `[Shot 1]` marker and the `S.SS` alignment line are mechanical, and emitting them is the difference between in- and out-of-distribution. `contextir.py` only ever *adds* what is absent, so a hand-written or refined prompt that already carries its own sections comes through untouched — and Ref2VA, whose six-section form we cannot synthesise, is only checked for the two audio fields it shares. |
| Sound and music | Two global fields on the timeline, per-segment override | `overall_soundscape` and `non_diegetic_music` are the two Context-IR fields that describe the whole piece rather than a shot — a cut is not where the room tone changes — so the timeline owns them and a segment leaving them empty inherits rather than clearing. An empty box emits *nothing*: `N/A` is the guide's way of saying "deliberately none", which is a real statement and not what a blank field means. |
| Global LoRAs | On the timeline, merged in front of each segment's own | A turbo LoRA is a property of the run, not of shot 3. Merged in `compile.merge_loras` before anything compiles, so `active_loras` and `collect_triggers` see one stack and the weights and the trigger words cannot disagree. A segment naming the same file replaces the global entry rather than stacking it twice at two strengths. |
| Piece references | A reference pool on the timeline (`assets`, handles `ref-N`), injected cite-gated | A character sheet cited in shots 2 and 5 used to mean attaching the file twice under two handles. The pool attaches it once; a segment writing `@ref-1` anywhere `compile` will substitute (prompt, rewrite, sections, its own audio fields) gets the asset injected in front of its own list — and only that segment, so an uncited pool leaves every payload byte-identical (cache). A citation in the *global prompt* is a citation in every segment — the join carries it, which is the attach-once, applies-everywhere gesture — and the global audio fields inherit the same way; the one clash (a keyframe segment, FL2VA vs Ref2VA) is refused naming the global prompt and the segment. In one pass the citing shots inject and the dedup merges them to one `<Picture N>`; pool assets keep their `ref-N` handle through the merge, because the global prompt is prepended un-renamed. The refiner lists the pool once ("ATTACHED TO THE PIECE"), dedups its pictures across shots, and every shot's handle set knows the pool so a rewrite may introduce a citation. Frontend mirrors the pool onto each segment as `state.pool` (like the canvas), which makes `hasReferences`/`mode`/routing pool-aware through one seam. |
| Segment progress | `render.emit` stamps `progress: {index}` onto multi-segment payloads; the segment node broadcasts `mmc_segment` as it executes; the stage shows "Segment N of M" | A long strip's step count says nothing about where in the piece the sampler is. The announce comes from the segment node because it is the one node that runs exactly when its segment's work begins — and a cached segment never executes, so the chip names the segment actually being made. Index only, never the total, so appending a segment cannot invalidate earlier segments' cache keys; the frontend knows the strip length and says "of M" itself. |
| Turbo switch | A pill on the sampler row that drives the ordinary LoRA stack | The H3 turbo LoRAs (larryvrh's v4 EMA, the lightx2v distill and Kijai's conversions of it) are a run-level speed choice: 4/6/8 steps for draft/medium/good against a native 20, euler + beta because the joint audio latent warbles on res_multistep at those counts. The switch owns no second stack — engaged, the file is a normal `loras` entry the manager and the chip can disable, and `turbo.sync` reconciles on every commit so removing it anywhere gives the saved sampler row back. Which file it engages is machine configuration and lives in the weights popover; strength is guessed from the filename (lightx2v ~0.6, larryvrh 1.0) and the manager's slider overrides it. The flow shifts are part of the same contract: H3 runs picture and sound on two clocks, the row carries them as two shift pills (`shift_video`/`shift_audio` widgets, `MiniMaxH3SigmaShift` in the graph), the switch presets the picked family's card values with the rest of the row (lightx2v distills against video 6) and restores them on release — and at the checkpoints' own 12/3 no shift node is emitted at all, so an untouched row builds the graph it always did. Merged turbo checkpoints — distillation baked into the weights — engage with *no LoRA at all* ("no LoRA · merged checkpoint" in the picker, remembered as `turbo.merged`): the switch then owns only the sampler row, and the user picking it is trusted to know their checkpoint. compile.py never sees the `turbo` block. |
| Sound across a seam | The previous segment's audio tail as a `ref_audio` block, on FL2VA | The model card lists FL2VA's inputs as text and frames only, but the packed sequence has `ref_audio` rows and the weights read them — the same conditioning LTX takes. So a seam can carry the room tone, key and tempo instead of restarting them. Core cannot express it unaided: `MiniMaxH3.extra_conds` rebuilds `cond_video_latents` from the reference list and wipes the keyframe latents doing it, so `payload.py` installs a diffusion-model wrapper that puts them back in layout order. A repair, not a behaviour — with only one of the two present it reproduces exactly what core computed. |
| Seam switches | Two, independent | Picture and sound cross a cut separately: a hard cut whose score keeps playing and a match cut that resets the room tone are both ordinary. Two switches say that; one control with three states would have to invent an ordering between them. |
| Audio tail length | 1 s, capped at 4 | Reference audio costs `40 × seconds × 2` rows through every sampling step, *and* advances the layout's RoPE cursor — so a long tail pushes the target's time origin off the keyframe, which stays pinned at the text, and the inherited start frame stops reading as frame 0. A second is also all a seam needs: what crosses a cut is the ambience and the tempo, not the phrase. |
| Past-native rendering | Two passes by default, chosen in the resolution popover | H3-Regenerate-2K stays API-only, so above 768 the local weights are off-distribution — and the UI already said so in orange, with no exit. The choice lives on that warning and nowhere else: past 768 the popover offers "two passes" (sample at native, then a refine pass — `hires.py` — interpolates the video latent up, re-noises it to `refine_denoise` and samples again against conditioning rebuilt at the target size) or "direct" (the old render, warning and all). At or under native there is no choice to draw. The audio half is never re-noised — the flow schedule lerps noise in, so handing the sampler zero audio noise and pre-dividing by `1 − σ₀` carries the first pass's soundtrack through exactly (exact because the AV latent format is scale-only). Technique after Tr1dae's LatentUpscaler, implemented fresh: theirs is a canvas node with an audio_denoise knob; ours is a graph-emitted pass with no knob to get wrong. The still branch pins "direct" — it upscales through the single-image VAE and has no refine pass. When the Regenerate-2K weights land, they replace the refine pass behind the same two options. |
| Default cfg | 1.0 | The released checkpoints are CFG-distilled — guidance is in the weights. Real guidance on top of that burns the picture and doubles the sampling cost. It stays an ordinary widget: a default, not a constraint. |
| Chained vs one pass | A toggle on the timeline, chained by default | H3's own prompt format is already a shot list with cut times (`[Shot 2] At 00:05.000, the camera cuts to…`), so the same strip of cards reads two ways: one generation each, joined — or one generation whose description holds all of them. One pass has no seam to cross, so continuity, sound and colour carry because they were never broken, and every rough edge below is a property of chaining rather than of the timeline. It is a toggle and not a replacement because chained is still the only way to pass what one context window will hold, and because the two modes lose different things. `compile.single_payload` flattens the timeline into one ordinary request and the graph loop runs once; nothing downstream knows which mode it is in. |
| What one pass collapses | Merged, or refused where merging would be a guess | A single pass has one mode, one checkpoint, one LoRA stack, one seed and one soundscape. References merge across shots by file — the same face cited in shot 1 and shot 4 is one `<Picture N>`, which is the point — and handles, which are allocated per segment, are rewritten onto the merged pool before labels are assigned. The rest is refused rather than resolved: shots that disagree about the checkpoint or the soundscape, a start frame anywhere but shot 1, an end frame anywhere but the last. Picking a winner between two deliberate settings is the kind of quiet decision this package does not make. |
| What bounds a timeline | Frames, and a card cap that only catches a corrupt blob | There used to be one number, `MAX_SEGMENTS = 24`, and it claimed to be the work bound: "low enough that a malformed blob does not run for a day". It was never that in either direction, and merging is what made it obvious. A card stopped being a generation, so 24 cards merged end to end is *one* pass — nothing to guard — while 24 unmerged cards of a minute each is 24 generations of 1445 frames, which is exactly the runaway. Cards do not measure work; neither do passes, since a pass is anything from 5 to 1445 frames. Frames do, so `MAX_TIMELINE_MINUTES` (half an hour of finished video, converted to the piece's family's own frames — a frame is 1/`fps` of a second and not an amount of time) is checked in `timeline_payloads` against `compile.timeline_frames` — counted per pass, because a run of three five-second cards is one 362-frame generation and not three 124-frame ones, and less what each feathered seam re-generates and `SeamTrim` drops. `MAX_SEGMENTS` stays, raised to 240 and demoted to what it always actually was: the bound that stops a garbage list being walked at all. The frontend asks `state.addSegmentRefusal`, which weighs the card that *would* be added and puts the reason in the button's tooltip, so a control goes dead on the click queueing would have refused rather than letting the strip reach a state `compile.py` throws on. What this cost was the assumption that a ten-minute piece is not a real timeline. A supplied clip counts at its own length rather than being snapped to the 17n+5 grid — nothing samples it — and it made the bound honest in a second way: the reel is what stopped the finished piece having to exist as one tensor, so the bound is now a statement about length rather than a number that would have run the machine out of memory a long way before reaching it. |
| What a crowded lane shows | Labels dropped one at a time, then edge code | The node body's lane is proportional and unscrolled, so forty-seven shots are twenty-four pixels each and the labels a five-shot lane wears draw over each other. Three readings out of one markup, picked by `TimelineBody.fitLane` measuring the blocks it actually drew rather than counting them — the same strip is roomy on a wide node and crowded on a narrow one, and a three-second shot beside a twenty is a quarter of its width, so what fits is asked per block. The length goes first (a band drawn to scale is already a picture of the lengths), then the number, and once no block can hold one the row closes into a single band with the numbering moved to an edge row beneath it at a cadence that keeps the numerals clear of each other. In that band the emphasis inverts: a strip whose seams nearly all continue is one unbroken take, so continuing is drawn as the ordinary case and the *hard cut* is the break — marking what every block has in common is marking nothing. Two proportionality bugs fell out of it: a merged pass's border and padding were stealing four pixels a run, and `flex-basis: auto` let a block's own label buy it width, which at this scale was most of a block. |
| Refining | A button, not a queue-time step | What the DiT actually reads has to be visible *before* five minutes of sampling, not inferable from the result afterwards. A rewrite inside `execute` would also differ between two runs of the same queue, so ComfyUI's cache would miss every time and there would be nothing to hand-correct. Pressing a button puts the rewrite in the blob, where it saves with the workflow, diffs, and can be edited, switched off without being thrown away, or reverted. |
| What the LLM writes | The prose, and — in a lone generation — where the cuts go | The instruction line, `[Shot N]`, the *written form* of the cut times and the `S.SS` figure are computed by `contextir.py` off the real frame count. So the reply is JSON — one body per shot plus the audio fields — and `compose` assembles it exactly as it assembles a typed prompt. The model never sees a format it could break, and a 7B is enough for what is left. Where the cuts *land* is a separate question, and on the Creator node it is the model's: one card carries one duration and nothing in it divides a clip, so otherwise a twenty-second prompt is one uncut shot exactly like a six-second one. Given the duration the model returns 1..N bodies with the second each starts on (`refine.shot_limit`, one shot per two seconds, capped), and `plan_cuts` makes the numbers monotonic and makes them fit — a shot with no room merges into the one before it rather than being dropped. A timeline keeps the automatic times: its cards *are* the shots, their cuts are the running sum of the durations the user set, and a model second-guessing them would move a cut off the frame the next card starts on. |
| How references survive a rewrite | Stored as `@handles`, never as ordinals | Ordinals are assigned by `plan_references` at queue time and move whenever an asset is added, removed or switched track. A rewrite with `<Picture 2>` baked in would go quietly stale and bind to the wrong tensor — the one failure this package is built around. Keeping handles means `_substitute` runs on a refined prompt exactly as on a typed one, so re-labelling is automatic and one-pass handle renaming keeps working. The model is shown both forms and `normalize_handles` converts back whatever it wrote. |
| Per-mode templates, not the guides | One distilled template per mode, each ending in a worked example | The refiner used to embed the whole official guide — four to five thousand tokens of someone else's finished-document spec sitting between the rules and the request — and a 4B that had just read it treated the user's sentence as conversation: it answered, dropped names, rewrote. Each mode now gets `prompts/modes/<mode>.txt`: the same rules distilled to what that mode needs, plus one request-and-reply pair written in the reply's own JSON shape with `@handles`. The pair is what actually teaches "expand, don't answer"; writing it in the contract's shape (not the guides' `<Picture N>` document form) means the one thing imitated is the one thing wanted. Content bleed — the old reason for stripping the guides' cases — is handled by fencing each example with an ownership sentence and giving it a deliberately non-default scene. The shared craft (camera vocabulary, `<d>` form, the two audio fields) lives once in `prompts/modes/craft.txt`. The official guides stay on disk for the skill package, which ships them verbatim. Which template runs is the derived mode — the mode *is* the template — with a pin in the refiner's settings on the weights-route pattern (`refine.choose_template`): auto by default, the four base templates swap freely, REF2VA follows references in both directions and refuses a mismatched pin. The reply carries `template`/`forced`, the panel chips it (`i2va`, or `t2va (pinned)`), and the blob keeps it beside `model` so a reloaded workflow still says which form its stored prose is in. |
| What a reference image takes | A scope on the chip: `full · person · object · scene · style` | "Her from @img-1" used to retain the whole picture — background, palette, pose — because nothing said the person alone was the reference. The narrowing cannot live on the encode path (the DiT is handed the whole tensor regardless); it lives where H3's own format expresses it, the prose: `Asset.takes` flows into the refiner's glossary as a scoped description plus a retention order ("define the subject as the person alone and retain nothing else from this picture"), and the REF2VA template teaches narrow-by-default subjects even on `full`. Stored only when not `full` so old blobs read unchanged; refused on keyframes and audio, where it would quietly mean nothing — a keyframe is bound whole by the alignment line. A clip takes the same scope and four more; see the row below. |
| What a reference video takes | The same scope on the clip's chip, plus the four roles only a moving picture has: `motion · camera · edit · continue` | H3 has no video-conditioning switch — Ref2VA takes the file as context and every distinction between "use its camera" and "use who is in it" lives in the prose. The reference guide draws the line itself: content mined out of a clip is a `<Subject N>` like any other, while `<Video N>` is reserved for whole-video relationships — editing it, continuing it, or borrowing its camera, cuts and rhythm — and the guide is explicit that a clip lending only camera movement is `reference generation`, not `video editing`. So the chip is the same `Asset.takes` field an image already had, with a per-kind vocabulary: the four content takes and `motion` tell the refiner to define a subject and give the clip no `<Video N>` entry (motion additionally marked `attribute_transfer`), while `camera`, `edit` and `continue` ask for the `<Video N>` entry, the retention marker and the task-type prefix that go with each. Subject replacement is `edit` plus a picture of the replacement — two chips, no new field. Refused on a clip taken for its sound alone, which has no picture left to scope, and on audio and keyframes, where it already meant nothing. |
| What a reference audio takes | The same chip, with the guide's own audio roles: `full · voice · music · ambience · copy` | `<Audio N>` is the one label whose roles the guide states as a *relationship to the signal* rather than as content: copied in whole or part, or referenced for timbre, style, texture or beat. That split is the whole of the vocabulary, because it is what decides both ends of the form — the task-type prefix (`audio reuse` against `audio reference`) and the retention marker (`fully_copy` against `reference`) — and neither can be derived from the file. A clip set to *sound only* scopes here rather than with the pictures: it reaches `ref_audios`, takes an `<Audio N>`, and never has its picture encoded, so the picture vocabulary would be narrowing a file that is not there. It used to be refused a scope on exactly that reasoning, which had the right premise and the wrong conclusion — what it has left is a sound. |
| Where the narrowing is actually read | The refiner's glossary always; the prompt itself behind one global setting | `Asset.takes` never reaches the encode path — `encode.py` hands the DiT the same tensor whatever the chip says, and H3 has no reference-conditioning input to carry the difference — so a scope is prose or it is nothing. Refine was the only reader, which made the dial a setting that silently did nothing on any piece queued without a rewrite. `contextir.reference_preamble` is the second reader: one sentence per label, in `plan_references`' own order, written into the slot `AUDIO_SEAM_LINE` already occupied and for the same stated reason — a label the prompt never defines is a label pointing at nothing. It stays a *floor*, like the rest of that module: skipped where the body already carries `subject_definitions` or `retention_analysis`, and skipped entirely once the refiner supplies the real sections, because two descriptions of one reference is worse than none. Global rather than per-piece, which is the one place this pack lets a machine setting change what is queued: it is a statement about how you prompt, not about this shot, and the settings page says so outright. The sentences are mirrored in `state.js` so the prompt box can show them live — with `@handles`, since ordinals move at queue time — and `tests/test_scopes_mirror.py` is what stops the two copies drifting into a chip that promises prose nothing sends. |
| The request behind a fence | `<request>…</request>`, and the rules point at it | Raw, the user's sentence is the last conversational-looking text in the turn and a small model answers it. Fenced, it is a quotation the rules can name: "typed at a video generator, not at you". Two code-side checks back the prose promise up: `dropped_quotes` reports any text the request put in quotation marks that the rewrite fails to carry (the one fidelity promise checkable mechanically), and the default temperature is 0.3 — rewriting is a fidelity task, and at 0.7 a small model paraphrases the very words it was told to keep. |
| Fidelity over improvement | Everything named survives and is expanded | The point is a lazy prompt becoming a working one, not a better idea than the user's. "Shot on a small-frame camera" stays in the prose *and* gains the grain, depth of field and highlight rolloff that format actually has. A named style opens shot 1 and governs every later one. Where the request and the guide disagree, the request decides content and the guide decides form. Enforced by the system prompt rather than by code, which is why the panel shows the rewrite as an editable draft next to the sentence it came from. |
| Sound, music, speech | Soundscape always; music only when asked; speech written out | The three asymmetries the guide leaves implicit. A scene always makes noise, so `overall_soundscape` is always written — from the request when it says anything, from what the place and the action would sound like when it does not. A score is a deliberate addition, so `non_diegetic_music` is left empty unless the request asks for music, and empty means "the model decides" rather than the guide's `N/A`, which means "deliberately none". And "she says something" is not a prompt H3 can voice, so the refiner writes the actual line, in the `<d>` form, at roughly two to three words per second so it finishes inside the shot. |
| Whole-timeline refine | One call for every card, the global prompt included | Continuity across a cut is only kept by a rewrite that wrote both sides of it: shot 4 keeps the look, the people and the light shot 1 established because the same call saw them, not because anything copied them forward. Each card's own attachments are listed under it in the message, since handles are per segment and two cards both have an `@img-1`. The global prompt is material too: shown once as THE PIECE rather than joined into every shot's request, returned as its own field (`global_prompt`), and stored back into the timeline's own box. The rewrites are shot-scoped (`refined.scope: "shot"`) and compile joins the global in front of each exactly as it joins it in front of typed text — which keeps the box a live input after refining, where the old absorbed-join rewrites (unmarked blobs, still honoured) left it editing nothing. A single-card refine shows the piece as read-only context instead: the other cards' rewrites were written against it. Reference cards carry their own `subject_definitions`/`summary`/`retention_analysis` inside their shot entries (`reply_shape`'s `ref_shots`) — each chained card is its own generation over its own reference pool — so neither an all-reference strip nor one mixing reference and plain cards is refused any more: a strip with references anywhere is written under the REF2VA template (the superset form, and Ref2VA is the stronger checkpoint), plain cards keeping their own mode notes. One pass keeps the one top-level section set; its shots share a merged pool. |
| Where the refiner runs | A ComfyUI text encoder, and nothing else | It shipped with an Ollama backend beside this one and no longer has it. A second process holds a second copy of the weights in VRAM ComfyUI can neither see nor reclaim, and on a machine already streaming H3's own 25 GB encoder off system RAM that is the difference between a rewrite and a coffee break — so the backend that was there for compatibility was costing the thing the refiner is for. A Qwen3-VL loaded through `comfy.sd.load_clip` is an ordinary entry in the model list: the sampler evicts it when it needs the VRAM, and `CLIP.generate` is core's own sampling loop, so the whole path is a tokenize and a call. What it cost to drop Ollama is the grammar, which compiled the reply schema and guaranteed the shape; core samples plain logits, so the shape is written into the instruction as words (`reply_shape`) and the assistant turn is prefilled with `{`, which removes the place "Here is the rewrite:" would have gone. In practice a 2B holds the shape that way, so the guarantee was not what was carrying it. H3's own encoder is *not* a candidate and is refused by name: truncated to 50 of 64 layers, no final norm, no `lm_head`, so there is nothing to decode with. |
| Refiner settings | `localStorage`, not the blob | Which text encoder is on this disk is a fact about this computer. In `creator_data` it would ship to whoever opens the workflow next, and nudging the temperature would invalidate the node's cache. |
| Audio slots | Refused in the UI, not at queue time | Audio is capped at three, soundtracks included, so the sound switch on both the chip and the segment editor checks capacity and says no. `compile.py` still enforces it; the UI just says so while there is still something to change. |
| Pre-stage surface | A second zero-socket node, spawned by a pill | The pipeline consumes stills — keyframes, references, style sheets — and had no way to make one. `MiniMaxH3PreStage` is the Creator's architecture verbatim (blob, DOM body, expanded subgraph, satellite result card) because it is driven the same way; the pill spawns and removes it because a pre-stage is a property of the shot being set up, not a node to hunt the menu for. First `LiteGraph.createNode` in the repo. Its result card floats on its *left*, so the desk reads *still ← pre-stage · creator → video*. |
| Pre-stage peer linkage | Derived by scan; the blob's `peer` id is a hint | Ids renumber on paste, so a stored id is never a contract. The pill's on/off state is re-derived from which PreStage claims this node's id; an orphan whose peer no longer resolves is adopted by the node it was visibly beside, and deleting the PreStage by hand needs no bookkeeping at all. |
| Local image models | Krea 2 + Ideogram 4.0, both native in core | Same statement as the first row, for stills: open weights, no API key, no uploads. Loaders, CLIP types (`krea2` / `ideogram4`), the reference conditioning and the Ideogram scheduler are all core's — `render_image.py` emits the official templates' wiring and reimplements nothing. Two sampler shapes: Krea through `KSampler`; Ideogram through its own resolution-shifted sigmas, `SamplerCustomAdvanced`, and a *dual-model* guider, because it ships its unconditional branch as a second checkpoint (cfg 7, dropped to 3 over the last 30%). |
| Ideogram prompts | Plain natural language, no JSON schema | Ideogram 4 was trained on structured JSON captions and its hosted magic-prompt expands text into them — but for art-directed, human-focused work a clean sentence prompt reads better than the schema, so the schema is deliberately not modelled at all. |
| Ideogram references | Refused with a message | `Ideogram4.extra_conds` reads no reference conditioning, and a render that silently ignored the attached images is the failure this package exists to avoid. The message names the fix: switch the model pill to Krea 2, or clear the references. |
| Krea style references | Core's Qwen-edit encoder, three slots | The official reference workflow's wiring: `TextEncodeQwenImageEditPlus` (which feeds the references to the text encoder *and* VAE-encodes them into the conditioning's reference latents) plus the `index_timestep_zero` method node, with the shift moved onto `ModelSamplingFlux(1.15, 0.5)` on that branch only. The three-reference cap is that node's shape, not taste. |
| Image turbo | A checkpoint swap under the H3 pill's contract | Krea 2 Turbo *is* a distilled checkpoint, so "the switch drives the LoRA stack" does not transfer — but the contract does: the pill saves the sampler row once per throw, restores it exactly on release, and owns no second stack. The LoRAs are untouched either way (Krea LoRAs train on RAW and apply on Turbo). Ideogram has no turbo pill; its speed axis is the official preset table (48/20/12 steps), which owns the schedule shape as well as the count. |
| Pre-stage hand-off | By file, through chips on the result card | The still saves under `output/minimax/prestage/` and the chips write `sub/name.png [output]` into the peer's blob — the same annotated-path currency the gallery attach uses, so there is one store and no copy. Start/end/reference land under the peer's own capacity and exclusivity rules, refused with the peer's own words. On a timeline the roles land where one pass would put them: start opens shot 1, end closes the last shot. |
| Queueing both nodes | Comfy's cache, not an ordering | One Queue runs both output nodes, and an untouched pre-stage is a cache hit — its blob and widgets are the key. The hand-off is by file, so there is deliberately no execution edge to get wrong; "queue selected" is the escape hatch for running one alone. |
| Machine preferences | A settings page, server-side, out of the blob | A workflow says what the piece *is*; how this computer writes it is a different question, and output quality is the first thing on that side of the line. Two people opening the same `.json` should get the same shot without also having to agree on how many megabytes it takes — so the value is not in `creator_data` and not a widget. It cannot go through the frontend's userdata API either, the way the picker's favorites do: the save node reads it while a queued prompt executes, and an execution has no request behind it and therefore no ComfyUI user, so page and node would be reading two different files. One JSON beside `user/`, a GET/POST pair in `server_routes.py`, and `settings.py` as the only thing that knows the path. `render.emit_tail` reads it once and passes it into the save node as an ordinary input — an output node whose inputs are unchanged is a cache hit, so a save node that read the preference itself would keep writing the quality it was built with. `settings.py` decides what is *allowed* (libx264's whole scale, so a hand-edited file is honoured and shown as `Custom`); `settings.js` decides what is *offered* (four points on it, each wearing its real CRF, because the rest of this package shows the exact filename and the exact pixel size under the friendly word). The page's third tab, Nodes, holds UI preferences: the sampler row's two flow-shift pills ship hidden (`show_shift_pills`, default false) because most rows never leave the checkpoints' own schedule — the widgets keep working underneath, and a value *off* that schedule shows its pill whatever the setting says, the same in-force-means-visible rule as the Custom CRF row. The bodies read it from a cache in `api.js`, primed once on the first mount and kept current by the page's own replies. |
| How the passes become one file | A reel of references, written part by part | They used to be *concatenated*: `MiniMaxH3TimelineJoin` folded them pairwise and the save node was handed the tensor that came out. Every intermediate of a pairwise fold is a node output and ComfyUI keeps node outputs for the whole execution, so the running totals were all alive at once — O(N²) in the length of the piece, and about 81 GB of intermediates on a ten-pass 768p strip on top of the 15 GB of passes. Worse, the default `RAMPressureCache` evicts current-generation entries over 512 MB when memory runs short, and re-running an evicted join means re-running what fed it, which upstream of a join is a KSampler. Nothing about an mp4 needs any of it: a container is written frame by frame, so the passes only have to be reachable in order, never adjacent in memory. `MiniMaxH3Reel` carries a list of references that copies nothing and `mux.py` walks it into one open container, so the peak is the passes themselves and the fold costs a list. Writing the container here rather than through core's `VideoFromComponents` — which takes a single tensor, and so would mean building the very thing this avoids — also retired the CRF version gate, since `save_to` only learned `crf` in ComfyUI 0.29. The work bound was never a memory bound (43 200 frames is 535 GB held); this is what starts making it an honest one. |
| A part's sound against its own picture | Cut or padded to the frame count, per part | Laid end to end, a part whose sound runs 30 ms short does not lose 30 ms — it moves everything after it by 30 ms, and the drift accumulates down the reel. A generated part's two halves are the same span by construction, so this only ever fires on the rounding between a frame count and a sample count, and on a supplied clip with no soundtrack at all, which holds its own time open with silence. |
| Supplied footage | A card on the strip, not an asset on a card | A reference clip is something a generation *looks at*; footage cut into the piece is part of the finished video. It has a length, a place in the order and a seam on each side of it, which is what a shot has and what an attachment does not — so it is a card, and everything that walks the strip counts it. It compiles to a payload with no request in it: no prompt, no mode, no checkpoint, no LoRAs. It cannot be merged into a pass and cannot make a strip one pass, because there is no generation there to merge into. |
| What a clip costs | A path and a window, never a tensor | The reel already accepts parts that are not adjacent in memory, so a clip does not have to be decoded into it at all: `mux._write_clip` demuxes, conforms and re-encodes it a frame at a time into the container that is already open, and a five-minute source costs what a five-second one does. Decoding it to hand the encoder something to re-encode would be 12.4 MB a frame — 35 GB for two minutes — to say nothing at all. What the *seams* need out of it is a separate, bounded decode of its own window: one frame at the head, at most 39 at the tail. A clip nothing continues from is never decoded. Conformed through one ffmpeg filter chain (`fps`, then `scale`+`crop`, then `setsar`) because frame-rate conversion and the cover-crop are things it has correct and we would be reinventing; anamorphic sources are scaled by their storage size, which is the one case this gets wrong. |
| Where the aspect comes from | The first pass's own answer, then the first clip, then the pill — unless the user names a source (`aspect_source`: any attached picture on any card, a clip, a pool reference, or the pill forced over them) | Footage was shot at the size it was shot at, and cropping it to a preference throws away picture that cannot be got back; a ratio pill *is* a preference, so a clip outranks it. It does not outrank a keyframe on segment 1 — that rule already existed and every timeline without footage still follows it, so the order only ever adds a step that used to fall through to the pill. The scale stays the slider's: generated video stops at 896 and is off-distribution past 768, so a 1080p source is played at the render's size and the card says so. `canvas_from_image` is the same call a keyframe goes through, so the clamp and the area cap are the ones that already exist — but `from_image` stays false, because nothing in the generation is being matched to a still and `encode.py` reads that flag to decide whether a keyframe may be stretched onto the canvas or has to be cropped into it. |
| The seam in front of a clip | The same switches, running the other way | Everywhere else the seam says what the card *after* the cut starts from. A clip is not conditioned on anything, so the only thing a seam there can say is what the card *before* it ends on: the clip's opening frame, and its opening sound. The switches stay where the cut is — the strip draws them there, and moving the clip moves them — and only their sentence changes; what changes underneath is which payload they land on. Mechanically it is an ordinary last-frame keyframe fed from a tensor, so it lands on the same four modes a pair of attached stills does — and on a shot carrying references it rides as a pinned guide on Ref2VA, the same road the continuation seam takes. |
| Blending into a clip | The same grid, end-aligned, and it is exact | `_context_keyframes` pins guides at any frame index, so the only question was whether an end-aligned run lands on the VAE's temporal grid. It does, and not by luck: the feather grid is the standalone-encodable runs (17m+5) and a generation is 17n+5 frames, so a run ending on the last frame *begins* at frame 17(n−m) — a whole number of seventeen-frame cycles from the origin, and therefore in phase with the five-step pattern. So the tail blend is the head blend with an offset. The sound crosses with it because `AUDIO_END_KEY` already took any pixel-frame coordinate. What it costs is symmetrical too: the blended run is re-generated and trimmed off the *end* of the generated segment rather than the front of the clip — trimming the clip would edit footage the user chose. |
| Who is in the shot | A cast of `<Subject N>`s above the assets, cited by `@handle` like anything else | H3's reference guide splits identity from provenance: `<Subject N>` is the reusable visible content and `<Picture N>`/`<Video N>` are the files it came off, and §2.2 is explicit that an image used only to define a character must *not* get a standalone picture entry — it is cited inside that subject's definition. Everything here addressed the files, so a person was `<Picture 1>` and the prose said `<Picture 1>` walked across the room. That is off-spec, and it also cannot say the three things the guide's own examples say: that four photos are one dog, that a face comes from a still and a walk from a clip, and that a subject *replaces* someone already in a reference video. So a subject becomes a thing the user declares — a name, the files behind it, what to take from them — and the compiler emits the two sections it now has the facts to write. |
| What a family is | A directory under `families/` with a declaration in it, and nothing outside it | The pack shipped with one family, so "what H3 is" and "what the pack does" were the same statement and were written in the same places: six tables in `registry.py` keyed by family id, the frame grids in `canvas.py`, H3's slot table inside the shared loader machinery, its segment node beside the family-neutral reel, its node id in the extension's list. Adding LTX 2.5 meant editing all of them before its own package would run, and nothing said when one had been missed. Each family carries its own `declare.py` now — id, label, order, what it produces, its prompt pipeline, its LoRA stack, its duration slot, its routed checkpoints, its segment node, its canvas rules — and the registry walks the package for them; a subpackage with no declaration is an error naming the directory. The readings that used to be per-family are shared instead: `models.Weights` reads a blob against any slot table, `models.Links` builds exactly the loaders a render opens (an optional slot lazily, since it is a pass and not a component), `models.check` refuses one nobody filled, `families/row.py` validates a sampler row from declared field kinds. What is left in a family package is what a checkpoint's training decided — how a payload becomes conditioning and a latent, and what a sampler subgraph looks like — which is the part that cannot be a declaration. The thing that kept going wrong while this was half done was silent substitution: every `canvas.py` function defaulted its rules to H3's and there were module constants beside them, so a caller that forgot to thread the piece through ran one family's arithmetic over another's weights and still worked. The defaults and the constants are gone on both sides; the reel takes the rate it trims sound at, the preview takes the rate it plays at, and a call site that means H3 says so. |
| Frame extraction | Client-side, through the trim editor's own scrubbing | `framegrab.js` is the trim editor's canvas + `seeked` + `drawFrame` machinery with a different ending: the playhead frame is painted at the clip's own resolution and uploaded through core's `/upload/image`, landing on an `input/prestage_frames/` shelf. Zero server half. |

## Phases

- [x] **1 — Backend, headless.** `canvas.py`, `compile.py`, `media.py`,
  `encode.py`, the node. Driven by hand-written `creator_data` so the reference
  ordering was provable before any UI existed.
- [x] **2 — Asset route and picker.** `/minimax_creator/assets`, the picker
  modal, the tool rail, the pill row, state serialisation.
- [x] **3 — `@` chips.** Contenteditable prompt, mention menu, attach-on-select.
- [x] **4 — LoRAs.** `lora.py`, the listing and preview routes, the manager
  modal. Took over the rail's dead "Add effect" slot.
- [x] **5 — Refiner.** `refine.py`, `refine_routes.py`, `js/…/refine.js`. A
  local Context-IR rewrite through a ComfyUI text encoder, against MiniMax's own guides, with
  the attached images shown to a vision model. Optional; `prompt_override` is
  still the manual escape hatch.
- [x] **6 — Pre-stage.** `compile_image.py`, `render_image.py`, `prestage.py`,
  `js/…/prestage.js`, `js/…/framegrab.js`. A left-side image node (Krea 2 /
  Ideogram 4.0, both local open weights) spawned by a pill on the Creator or
  Timeline; stills land back as start/end frames or references through chips on
  its result card. Same body architecture, same picker, same LoRA manager.

- [x] **7 — H3 stills (experimental).** `compile_still.py`,
  `render_still.py`, `MiniMaxH3StillLatent`, a third arch on the pre-stage's
  model pill. A still made by the *video* model: the pre-stage compiles a
  request in exactly the Creator's shape, emits the same
  `MiniMaxH3TimelineSegment` → `KSampler` line, then takes one temporal slice of
  the sampled latent and decodes it with the experimental single-image H3 VAE
  (`minimax_h3_t1_image_vae_*`, a merged checkpoint that loads through the
  ordinary `VAELoader`).

  Why it earns its place: no second model family is loaded, the still lands on
  the exact canvas the shot will render at, and everything a shot can attach a
  still can attach — nine reference images, three clips, three sounds, a start
  frame, an end frame, LoRAs, the taeh3 preview. The only pre-stage control it
  does not use is the img2img denoise, because H3's image conditioning is a
  pinned keyframe rather than a partly-denoised latent.

  Why it is a *slice*: the H3 VAE is causal on the 17k+5 ↔ 5k+2 grid, so latent
  frame 0 is a function of pixel frame 0 alone, and that is exactly the tensor
  encoding a single image produces — the one the T=1 decoder was fitted to.
  Core already handles the round trip (`comfy/sd.py` returns 1 latent frame for
  1 image and special-cases `frames == 1` in the memory estimate).

  **What the pills are for.** The DiT's trained range is 124–362 frames, so
  sampling 5 is far off distribution temporally even though the latent is in
  distribution spatially. How short the clip can be and which latent frame reads
  best are properties of the weights rather than of this code, and the weights
  keep changing — so both are pills (`5f · 2 latent`, `latent 0`) rather than
  constants. The sweep that answered them the first time has been removed.

- [x] **8 — Supplied clips.** A timeline card that is not a generation: footage
  the user already has, cut into the strip with the seams working on both sides
  of it.

  The chained path already has the shape for it. Everything downstream of a
  pass read one currency — the decoded `(images, audio)` pair — so a clip card
  is a pass that produces one without a sampler in front of it, and the
  last-frame, audio-tail and feather machinery never asked where a tensor came
  from. (Phase 9 below changed that currency to a file, and a clip became the
  second kind of one.) What is new is a card with no request in it, the
  seam pointing *backwards*, and the memory.

  - [x] **The tail.** `mux.py` and `MiniMaxH3Reel`, replacing the pairwise join.
    Nothing to do with clips on its own, and the thing that makes the rest
    affordable — see the decision row. Done first and alone so the change is
    provable against the existing suite.
  - [x] **The clip card.** A reel part that names a file, and a payload with no
    request in it. `MiniMaxH3ClipReel` adds it; `mux._write_clip` splices it.
    The aspect comes off the first clip — see the decision row.
  - [x] **The seams, both ways.** `MiniMaxH3ClipFrames` / `MiniMaxH3ClipAudio`
    read the head or the tail of the clip's own window, so a generation after
    it continues from it and a generation before it ends on it. Blend and sound
    work at both ends; the trim grew a `tail`.
  - [x] **What it refuses, and where.** Merging and one-pass are refused in
    `timeline_runs` and prevented in `syncTimeline`; the backwards seam is a
    dead control naming the shot that blocks it; the refiner skips clip cards
    but is told where they fall.

  **Where the memory actually goes.** Under the reel, a supplied clip never
  becomes part of the timeline's tensor stream: it owes the seams its first
  frame and its last blended run, and it owes the file its own packets. That is
  why the tail was worth doing first — without the reel there was nowhere to
  put a part that is not a tensor, and a two-minute clip would have been 35 GB.

  **Not done.** The clip is always transcoded, even when it already matches the
  render's codec and canvas and could be stream-copied — a real optimisation
  and a second path to get wrong, so it is deliberately absent from the first
  cut. And the frontend's clip work has no tests of its own; see below.

- [x] **9 — The passes go to disk.** `spill.py`, and the decode moved inside
  `MiniMaxH3Reel`. The reel took away the *intermediates*; this takes away the
  passes themselves.

  The reel already meant nothing concatenated, but every pass still had to
  survive from its own decode until the save node ran, because the file is
  written from all of them at the end. ComfyUI keeps a node's output for the
  whole execution, so any node that *returns* a decoded pass holds it: a minute
  of 768p video is 18 GB of float32 resident at once. On a box streaming a
  staged model out of host RAM — 40 GB of it, in the report that prompted this
  — that is an OOM kill after an hour of sampling, on a render that was going
  to work.

  So the decode happens inside the reel node and the tensors never leave it:
  `spill.py` writes 8-bit frames and float32 sound straight out, and what
  travels the wire is a path and a frame count. `mux.py` memmaps the parts back
  a frame at a time, and a seam reads its own width out of the same file.
  Peak memory is one pass, whatever the strip is. 8-bit costs the file nothing
  — it is what the encoder was always given — and it is what a keyframe
  attached from a PNG has always been.

  What went with it: `MiniMaxH3LastFrame`, `MiniMaxH3AudioTail` and
  `MiniMaxH3SeamTrim`. All three took tensors that no longer exist as node
  outputs; `MiniMaxH3PassFrames`, `MiniMaxH3PassAudio` and the reel node's own
  `head`/`tail` do the same jobs against the spill. A supplied clip is
  unchanged and now simply the second kind of file part.

  **Not done: the resume this makes possible.** Spills live under ComfyUI's
  temp, which core wipes on restart, so a crashed render still costs every pass.
  Naming a spill by a hash of what determines its pixels — payload, sampling,
  weights, and the key of the pass it continues from — and looking for it in
  `render.emit` before emitting the sampler would make a re-run skip everything
  that has not changed. That is a store with a real invalidation problem in it
  and it wants deciding on its own, not smuggling in behind a memory fix.

- [x] **10 — The cast.** `subjects.py`, and the two prompt sections it makes
  derivable. What the decision row above is about.

  **The shape.** A subject is declared on the piece, beside the reference pool:
  a handle, the reference assets that define it, one `takes` word saying what of
  them is the reference, and optionally a description, a clip its motion comes
  from, an audio reference that is its voice, and the person in a reference
  video it stands in for. It is cited in prose as `@anna` exactly as an asset
  is, and `_substitute` turns it into `<Subject N>` at queue time — so the whole
  chip, mention-menu, refined-body-stores-handles machinery carries it with no
  changes at all. Handles share one namespace with the assets, because the user
  types one `@`.

  **Why it is above the assets rather than a field on one.** `takes` says what
  of a *file* to keep; a subject says who is in the video. Those differ whenever
  a subject is more than one file (four photos of the same dog — the guide's own
  example), when it is more than one *kind* of file (appearance from a still,
  motion from a clip), and when it is nobody in any file (a subject that only
  exists to say what the woman in `@vid-1` is replaced by). None of those fit on
  an asset. `takes` stays where it is for an unclaimed reference and moves onto
  the subject for a claimed one — the retention decision the guide wants is
  per-subject, so a subject built from a photo and a clip states it once.

  **What it makes derivable.** `subject_definitions` and `retention_analysis`,
  in the guide's own forms, from the direct path — sections that until now only
  ever arrived from the refiner because they cannot be got out of a sentence.
  With a cast they can: the definition line is the subject's sources and its
  description, the retention line is its marker and what that marker covers, and
  a replacement is the marker `transferred` plus the sentence naming who it
  replaced. The `<Picture N>` a claimed asset still owns is cited *inside* the
  definition and gets no `_DEFINE` sentence of its own — §2.2's rule, and the
  reason `define_refs` now governs only the unclaimed.

  - [x] **The module.** `subjects.py`: parse, validate against the asset list,
    and write the two sections. No disk, no ComfyUI, like `compile.py` and
    `contextir.py`.
  - [x] **Labels and citation.** `<Subject N>` in cast order over the subjects
    a generation actually carries; `@anna` in a shot's prose pulls anna's files
    into that segment the way a pool citation already pulls its own.
  - [x] **The refiner is handed the cast.** Pinned, not suggested: the numbering
    and the definitions arrive fixed, the rewrite cites them, and `stray` grows
    a `<Subject N>` arm so it cannot rename or renumber anybody.
  - [x] **The band.** A cast card under the assets: add, name, hang files on
    her, pick the take, write the description, bind a voice, name who she
    replaces. `cast.js`, one shelf mounted twice — the node's own face and the
    Timeline window — because there is one node and a cast belongs to the piece
    either way.
  - [x] **Everywhere, not only where there are references.** The first cut of
    the shelf lived only in the Timeline window and refused to open until a
    reference had been attached, which put it out of reach of exactly the
    generation that most needs it. A subject may now be a name and a description
    with nothing else behind her, and `contextir.compose` emits
    `subject_definitions` and `retention_analysis` in the base modes too — a
    `<Subject 1>` the prompt never defines is a label pointing at nothing, the
    same failure `AUDIO_SEAM_LINE` exists to prevent. The base form is otherwise
    untouched: the body stays in `integrated_multimodal_description`, and a piece
    with nobody cast compiles to the bytes it always did.

  **Decided: numbering is declaration order.** `<Subject N>` follows the cast
  list, not the order the subjects appear in the video, and the speaker IDs
  `(Sx)` a voice binding produces follow the same order. The guide numbers
  speakers by actual vocal event, which nothing here can know before the video
  exists — so the cast list is ordered and reorderable, and the user owns the
  answer instead of the compiler guessing it.

  **Decided: the references are the card.** The four things a file can lend a
  subject — her looks, her movement, her voice, the place she takes — were four
  ghost chips indistinguishable from every other ghost chip in the pack, and the
  way to add one was a "+" character among them. They are thumbnails now, each
  wearing its own identity hue, each with a badge naming what it lends her, and
  one menu behind the tile switches between the four. Her looks are the default
  and wear no badge: a badge on four tiles out of five is a badge that means
  nothing.

  **Not done: `<Subject N>` for a whole-video relationship.** A clip taken
  `edit`, `camera` or `continue` is a `<Video N>` statement about the target
  video and has no subject in it; those takes stay off the cast.

## Known rough edges in a chained timeline

Diagnosed, not yet fixed, and worth knowing before blaming the prompt. All four
are consequences of decoding and re-encoding between segments, so **none of them
exist in one-pass mode** — which is the strongest argument for the toggle, and
the reason to reach for it first on anything a single generation can hold.

- **The seam duplicates a frame.** Segment N+1 is conditioned to open on segment
  N's last frame, and the reel keeps both, so every join holds the
  same moment twice. It reads as a hitch. Dropping the first frame of a
  continuing segment is a two-line change but it moves the finished clip's length
  off the sum of the pills, which is a decision, not a cleanup.
- **The sound seam is new and unproven.** The previous segment's audio tail now
  rides into the next one as a `ref_audio` block — see the decision row above —
  but this is the one part of the package that is not doing what the model card
  documents, so it wants looking at rather than trusting. Two things to watch:
  whether the sound actually carries, and whether the inherited start frame still
  lands, since the audio reference pushes the target's RoPE origin away from the
  keyframe cond rows. If the second one bites, the tail length is the dial.
- **Only on the base modes so far.** A Ref2VA segment fills `minimax_refs` from
  its own ordered plan, so the inherited sound needs an `<Audio N>` inside that
  numbering rather than a line of its own. Refused with a message rather than
  dropped.
- **Roundtrip drift compounds.** Decode → last frame → re-encode is exactly what
  core's own I2VA path does, so one hop is faithful; six of them are not. Exposure
  and colour walk.

## How the refiner is put together

`contextir.py` emits the *skeleton* — the instruction line, the field names, the
shot markers, the cut times. It cannot write the prose, and the prose is most of
what makes a Context-IR prompt work. The refiner is the prose, and it fits into
the slot `compose` was already leaving empty: because `compose` only ever adds
what is missing, a rewrite passes through it exactly as a hand-written prompt
does.

MiniMax do not open-source the hosted preprocessor but do publish what it emits
(`skills/h3-prompt-writing`: `base-en.txt`, `ref-en.txt`), shipped verbatim in
`prompts/` — copied rather than imported from the sibling `MiniMax-H3-LLM`
package, which may not be installed.

The path, end to end:

1. The frontend posts the blob it is already holding to `/minimax_creator/refine`
   — the whole `creator_data`, or the whole `timeline_data` plus which card.
2. `refine_routes.py` **compiles** it. That is where the mode, the reference
   slots and the ordinal each handle will be given come from; there is no second
   description of the request anywhere.
3. It opens what is attached — reference images at full size, one cached still
   per clip, downscaled to 1024 px — and builds the glossary that says what each
   handle holds and what it will become.
4. `refine.py` sends the rules, the shared craft, that mode's template with its
   worked example, the glossary, the pictures and the user's sentence behind a
   `<request>` fence — the shape asked for in words and the reply prefilled with
   `{`, so a small model returns the right shape rather than the right shape
   wrapped in an apology.
5. Ordinals in the reply are converted back to handles, the result is checked
   for labels nothing backs, and the prose goes into `refined` in the blob.
6. `compile.refined_body` substitutes it at queue time exactly as it substitutes
   a typed prompt.

It could not have been a node in the graph: a refiner node would need the
composed prompt as input and hand it back, which is a cycle. Hence a button
inside the node — and `prompt_override`, unchanged, for anyone driving their own
rewriter.

**What it does not do yet.** It looks at one still per reference clip rather
than several, so it can say what a clip contains but not how it moves. It cannot
hear audio at all — a reference soundtrack is announced and described from the
request. And it is a language model: everything it writes is a draft in an
editable box, sitting next to the sentence it came from, for exactly that reason.

## Deliberately not doing

- **Effect presets.** There are none in the open weights. The rail slot that
  said so now opens the LoRA manager, which is the community's version of the
  same idea.
- **Splitting a LoRA off the audio stream.** Only `audio_patch_proj` and
  `audio_out` are audio-specific in the H3 DiT; every block is shared across the
  packed `[text | refs | audio | video]` sequence. So there is no mask that would
  make a LoRA video-only, and a switch claiming to be one would be lying. What a
  LoRA was trained on stays a fact about the LoRA, not something to enforce here.
- ~~**Frames + references together.** Different checkpoints, one pass. Refused
  rather than silently dropping one. The hosted API can do it; the weights
  cannot.~~ *Done since 2.8: a segment's own start/end frames ride as pinned
  guides on Ref2VA — the mechanism the continuation seam proved — presented
  after the references so their `<Picture N>`s hold, with an alignment line
  naming the ordinals the frames took. The seam into a clip rides the same
  road, and the FL2VA pin against references is honoured too (the slots name
  inputs; merges of the two checkpoints exist).*
- **2K output.** `H3-Regenerate-2K` is hosted-only. The slider stops at 896 and
  marks anything past the trained 768 short edge as off-distribution.
- **A shim that lets the node load without H3.** It would register a node that
  cannot generate. The raw `ModuleNotFoundError` names the missing module.

## Environment

**Requires ComfyUI >= 0.30.0** for `comfy_extras/nodes_minimax_h3` and
`comfy/ldm/minimax`.

Read core source from the tree that actually *runs*. A Desktop install executes
its own bundled ComfyUI, and a second checkout kept alongside it for reading is
a different revision within a release or two — close enough to look right and
wrong about the thing you are checking. The two drift.

`--base-directory` is a separate question from which tree runs: it is only where
`custom_nodes`, `input`, `models` and `output` live, and on a Desktop install it
usually is not the source tree. The graph tests take both as environment
variables for that reason — `COMFYUI_PATH` for the tree to import, `COMFYUI_BASE`
for the base directory when it differs.

## Testing

`python3 tests/test_compile.py` and `python3 tests/test_refine.py` — no torch
and no ComfyUI. Verify a change to the ordering contract by mutating
`plan_references()` and confirming the suite fails; a test that cannot fail is
not protecting anything. The same applies to `refine.normalize_handles`, whose
failure mode is a prompt that still compiles and binds to the wrong tensor.

`tests/test_mux.py` and `tests/test_spill.py` need the ComfyUI venv but no
install — they load `mux.py` and `spill.py` by path, since writing a container
and writing a pass need av, torch and numpy and nothing else. `spill.directory`
is the one thing either wants from ComfyUI, and the harness answers it.
It writes real reels and reads the mp4 back, because a container written part by
part fails by *playing wrong* rather than by raising: both halves of `_fit` and
the running sample cursor were mutated to confirm the suite catches them.

The reference *encode* path has not yet been run against real weights. Neither
has a clip seam: the graph is built and checked, but what a pinned run of
somebody else's footage does to a generation's last second is a question for
the weights.

**The report cannot drift any more.** The suites used to be flat scripts, each
appending to its own `FAILURES` list with a hand-placed `if FAILURES:
sys.exit(1)` block — and in four files that block had drifted above sections
added later, silently discarding every assertion below it (about 130 lines in
`test_compile.py` at the worst, including the whole reference-pool and passes
sections). `tests/harness.py` now owns the list and reports from `atexit`:
there is no block to keep at the bottom, so nothing can land below it, a crash
suppresses the success line instead of printing it under the traceback, and
`skip()` exits clean for a missing environment. Still open: `test_compile.py`
is ~1500 lines and wants splitting by concern — a mechanical follow-up now
that the harness is shared.

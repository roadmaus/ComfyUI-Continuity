# Continuity — Director (the chat's agent mode)

Spec for a new mode of the chat room. High level: architecture and decisions,
not code. Written 2026-11-08 against `main` at `b057927`, after reading the
chat (`creator/chat.py`, `routes/chat.py`, `web/creator/chat.js`,
`tools/chat_bench.py`) and Mago Studio's *Mago Director* (§3). Revised the same
day: Director uses the room's selected families for everything, the finished
piece lands in the chat like any other render, missing sheets and props are
rendered for approval before the run, and an approved plan runs end to end on
one command.

## 1. Summary

The chat room is good at one thing at a time: a still, a clip, a change to
either, a next shot on the strip. Each turn the model makes one decision and
the harness carries everything else. What it cannot do is take a sentence like
*"a 40-second spot: a lighthouse keeper finds a message in a bottle, rain,
moody"* and get from there to a finished piece by itself. That needs the cast,
the places and the props, then a shot list longer than one clip, then the
renders in the right order, each one citing what came before.

**Director** is that mode, and it feels like the chat because it is the chat.
The person says what they want to see. The room answers with a **plan** card:
the beats, who and what is in it (anyone you cite with `@` is used as they
are, as in any turn), and the shot list with timings. Whatever the piece
needs that does not exist yet (a character sheet, a place, a prop) is rendered
as ordinary render cards for the person to approve, redo or change by talking,
exactly as they would any still in the room. When everything is approved, one
command runs the rest: the keyframes and the clips, chained on the strip, with
no stops. The finished piece shows up in the chat as the last card, playing the
joined film, the same way a strip already does today.

**The shape, in one paragraph.** A plan is a small document of typed rows
(beats, entities, shots). The model fills it in through many small calls. Each
call makes one decision against a fixed schema, the same bargain the chat
already makes. Code owns everything that is arithmetic or bookkeeping:
durations, splitting, handles and dependency order. The
families are not a decision at all: Director renders on whatever the room's
rail has selected. Every plan row becomes the action the chat already knows
how to render, so a run is a sequence of ordinary chat renders that nobody had
to type.

## 2. Non-negotiables

- **It is the chat.** Same room, same transcript, same ledger and handles,
  same render cards, same strip. Director adds a plan card and a Run command;
  it does not add a screen. After a run, "make shot 3 darker" is an ordinary
  turn, because shot 3 is a clip in the ledger.
- **The room's families, for everything.** Stills on the rail's still family,
  changes to a picture on its edit family (the same `still_arch_for` /
  `pick_edit_family` rules a typed turn follows), clips on its video family,
  sampled on the rows the room already follows (`chatnode.js`: the node's row,
  the chat's own, or the family defaults). The plan never picks a family. If
  the rail's family is not ready, Director says which file is missing, like a
  turn does.
- **Nothing renders without the person seeing it first.** The plan is text
  until the person asks for the missing pieces. Sheets and props are rendered
  for approval. Only an approved plan runs.
- **Iterate first, then one command.** Before the run, every row can be
  changed, by talking or on the card, as often as the person likes. Once every
  prep row is approved, one command runs the whole remaining pipeline without
  stopping, unless something fails.
- **Any model, one code path.** Director runs on whatever the room is pointed
  at: the in-process refiner, Ollama, LM Studio, llama.cpp, vLLM, OpenRouter,
  and the hosted APIs over their OpenAI-compatible endpoints. Every model call
  goes through `routes/chat._ask`. A 2B model is the floor this is tested
  against (§12), not the model it is built for.
- **The model never does arithmetic or bookkeeping.** Durations, shot
  splitting, handle numbering, citation checks and dependency order are
  code. A model that says a 40-second film has shots of 12, 12,
  12 and 12 seconds is corrected by code, not re-asked.
- **No quiet fallbacks.** A missing weight, a failed step or a model that
  cannot be reached stops the run with a sentence that says which. The run
  never renders a different family, length or reference than the plan says
  without telling the person.

## 3. What Mago Director does

Mago Studio (AGPL-3.0, so ideas only — this pack is MIT) ships a
script-to-movie pipeline. Read from `desktop/main/scriptProjects/` and its
architecture doc:

1. **Script tab.** An agent chat helps write a screenplay: one forced tool call
   per turn, read back out of JSON, one repair re-ask.
2. **Cast.** The screenplay goes through structured calls. Sluglines
   (`INT./EXT.`) are split by regex first, so the model never segments. A short
   script is one call. A long one is a **structure** call (characters,
   environments, props, sequences), then a **prompts** call that writes one
   text-to-image prompt per entry. An optional **atomic shots** pass runs in
   batches, and if it fails it degrades to an error field rather than throwing
   away the casting that already worked.
3. **Assets.** One reference sheet per character, one empty establishing plate
   per environment, one isolated shot per prop. The person reviews them on an
   Assets tab before shots are made.
4. **Storyboard** (optional). A numbered sketch grid per shot, rendered img2img
   from a blank panel template and attached as a reference so the video follows
   its composition.
5. **Shots.** H3 per shot, kept to a 5–15 s window. A shot can continue from
   the one before it by last frame, key frames or last chunk. A last-frame
   continuation opens as a **cut** (new angle on the same moment), a **pin**
   (same camera) or **off**, each with fixed continuity wording appended.
6. **Timeline.** Pin the best take per shot, export the cut.

Around that: **render-spec fingerprints**, so a Generate press re-renders only
shots whose inputs changed; **resumable runs**, where an unreachable model
pauses rather than fails and queued steps survive a restart; and a project-wide
**visual style** kept apart from what each prompt describes.

Their text model is Qwen3.8 27B, and the design leans on it: the casting prompt
alone is about 9 KB with large nested schemas. That does not hold on a small
model. **What we take:** the stage order, assets reviewed before shots,
deterministic pre-processing before any model call, structure-then-prompts,
cut/pin continuity wording, fingerprints, resumability, degrade-don't-discard,
and style kept apart from content. **Where we differ:** no screenplay (the
person describes, they do not write a script), no separate project screen (it
all happens in the chat), many small calls instead of few large ones, reuse by
citing (`@george`) rather than re-casting, and the room's selected families instead of a fixed
engine.

## 4. What the pack already has

Most of Director is already built. The new part is the plan, the prep loop and
the run.

| Need | Already there |
|---|---|
| One model call on any backend | `routes/chat._ask` over `refine_routes._backend`: in-process refiner on the queue, or `refine_remote` (OpenAI-compatible) answered on the socket |
| Tolerant parse, strict validate, one re-ask | `chat.parse`, `chat.validate`, `chat.reask`, `chat.judge` |
| Turning an action into a render | `chat/render`: blob patch, weight picks, dry-run compile, one-node prompt on the queue |
| The room's families and rows | the rail (still, edit, video), `chatnode.js` (whose row each side samples on), `chat.machine_card`, `missing_weights` |
| Changing a picture | the room's edit path: a plain citation goes to the edit family when there is one (`changes_pictures`, `edit.txt` / `redraw.txt`) |
| Handles and the ledger | `pic-N` / `clip-N` / `snd-N`, `chat.ledger_block`, saved per chat by `chatstore.js` |
| Shots that follow each other, played as one film | the strip: `after`, `replaces`. Each strip render builds the joined piece and its card plays it (`chat.js`, `land`) |
| Cast as citation | `@anna` → `<Subject N>` at queue time; the chat's own cast; the roster in the preset library's Cast tab |
| Styles | the vendored H3 Style Atlas (Style tab) and style presets |
| Prompt expansion | the verbosity dial and the rich-prompt path (`needs_rich_expansion`) |
| GPU work on the queue | `jobs.py` |
| A bench for prompt wording | `tools/chat_bench.py` |

**What is missing:** the plan as a document, the calls that fill it in, the
plan card, the prep loop's approve/redo state, turns that change the plan, and a
run that outlives the browser tab.

## 5. How it goes

```
 ┌──────────────── iterate as long as you like ────────────────┐
 brief ─▶ plan card ─▶ prep: sheets, props (and keyframes) ─▶ all approved ─▶ RUN ─▶ clips on the strip ─▶ the piece, in the chat
          ▲   talk or edit   ▲   approve · redo · change by talking   │          one command, no stops
          └──────────────────┴──────────────────────────────────────────┘
```

Three phases, all in the transcript: **plan** (text only), **prep** (the
renders a person must approve), **run** (everything else, one command).

### 5.1 Getting into Director

- **The person asks for it.** A *Plan* toggle on the composer sends the message
  as a brief.
- **The room suggests it.** Code, not the model, notices a request one render
  cannot satisfy: a length over the shot limit, or more than one shot named.
  The turn then answers with a *"Plan this as a piece?"* card instead of a
  render. The model is not given a third `act`: on a small model, every choice
  added to the turn schema costs accuracy on the two that are already there
  (`creator/chat.py`'s header explains why).

A chat holds at most one plan at a time. A new brief while one exists asks
whether to replace it.

### 5.2 Plan

All model calls, no renders. Each call is one decision against a schema:

- **Brief.** Is anything blocking? If so, at most two questions in the room. If
  not, the call writes its assumptions into the plan header, where the person
  sees and corrects them. A director that interviews you before every piece is
  worse than one that makes a reasonable call you can overrule.
- **Basics.** `{title, seconds, look}`. `seconds` is what the person asked for,
  or a default. `look` is a short description of the visual style. Aspect is
  the rail's, not the model's.
- **Beats.** An ordered list of 1–8 beats (one for a piece that is a single moment), each a sentence of what happens and
  a rough weight (short, medium, long). Code turns the weights into seconds
  that add up to the target.
- **Entities.** `[{name, kind: person|place|thing, description, beats}]`.
  Visual description only: no plot, no camera. People the person cited with
  `@` are passed in as already cast and not listed again.
- **Shots, per beat.** `[{action, continues}]`. `action` is the shot's prompt in
  the room's prompt-box language, citing `@cast` members and entities.
  `continues` is `cut` (same moment, new angle), `pin` (same camera, carries
  straight on) or `new` (a real cut, time skip or new scene).
- **Code** then:
  - gives each shot its seconds from its beat's share;
  - splits any shot over the **shot limit** into continuation shots (15 s by
    default, clamped to the rail's video family's `max_seconds`);
  - sets `after` from `continues`, so the shots chain on the strip the way the
    chat already chains them;
  - picks each shot's opening picture: the previous shot's last frame for
    `pin`, a keyframe (§5.3) for `cut` and `new`;
  - checks that every citation resolves;
  - appends the fixed continuity wording for `cut` and `pin`.

The plan card appears in the transcript (§9). Rows can be edited on the card,
or changed by talking (§5.4).

### 5.3 Prep

Prep makes what the piece needs and does not have, for the person to approve.
The person starts it from the plan card (*Make the missing pieces*), or by
saying so.

- **Sheets and props.** One still per new entity, on the rail's still family: a
  person as a clean, front-facing, neutral-background reference; a place as an
  empty establishing view; a thing as an isolated reference shot. Mago's wording
  for the three is a starting point. Each is an ordinary render card in the
  transcript, with *Approve* and *Redo* beside the card's usual actions.
- **Keyframes** (a toggle on the plan card, *Storyboard first*). One opening
  still per `cut`/`new` shot, made from the shot prompt with its cast and
  entities cited, after the sheets they cite are approved. Off by default for
  a video family that is sent references (H3 and LTX 2.5 both are, read off
  the manifest's `reference.max.image`): such a family opens a shot from the
  people, places and things it cites, and a still drawn first by the still
  family only pins every shot to a worse picture of the same people (found on
  the first real run, 2026-11-08). On by default for a family that takes no
  references. Off means none at all: the clip cites its sheets directly.
- **On approval** a person's sheet becomes a member of the chat's cast, and a
  place or a thing becomes a reference the shots cite (`:scene`, `:object`).
  People and pictures the person cited are approved from the start.
- **Change by talking.** "Make the keeper older" is a plan turn (§5.4) that
  edits the keeper's row, and the sheet is changed on the room's ordinary edit
  path, as a typed change to that picture would be. The new picture replaces
  the old as the entity's candidate and needs approving again. Anything that
  cited the old one (keyframes) is marked stale.

### 5.4 Iterating on the plan

While a plan is open, a message in the room is a **plan turn**: one call,
shown the plan with its row ids, that answers one of three things:

- `{act: "edit", row, change}`: change one row (a beat, an entity, a shot, or
  the header). The row's own call runs again with the change, or, for a
  rendered sheet or keyframe, the change goes down the edit path (§5.3).
- `{act: "replan"}`: rewrite from the beats down, for a change that touches
  everything ("make it 20 seconds", "set it at night").
- `{act: "say", say}`: answer a question about the plan.

Every change recomputes what code owns (seconds, splits, `after`) and marks
anything downstream stale through its fingerprint (§6).

The turn call is shown the plan in the card's own words (`the piece`, `beat
2`, `shot 3`, `@keeper`), never the ids. A length change ("make it 20
seconds") is an edit of the piece: code shares the new length out, and plans
again from the beats only when the shots cannot fit it. A replan keeps every
entity the plan holds, with its sheet, and asks only for what is new. Beats
and shots get new ids, so their old clips have no row left to be stale
against and their records go.

### 5.5 Run

When every prep row is approved, the plan card's **Run** button is enabled, and
"run it", "go" or `/run` in the composer does the same. One command runs
everything left:

1. Clips, in strip order, each an ordinary strip render with `after` set. A
   `pin` shot waits for its predecessor's last frame; a chain renders in order.
2. Nothing else. The strip already joins the shots: the last clip's card plays
   the whole film, and that card is the finished piece.

No gates during the run. It stops only on a failure: a render error, a missing
file, or a model that cannot be reached. The failure is said in the room,
everything done so far stays, and **Run** continues from the first unfinished
step. **Stop** cancels through ComfyUI's own Cancel.

During the run the clip cards land in the transcript one by one, as they would
if the person typed each shot. When the last one lands, the room says one line
(the piece, its length, its shot count).

### 5.6 After the run

The room is an ordinary chat over everything the run made. "Make shot 3
darker" is a normal turn with `replaces`, and the strip rebuilds the joined
piece. The plan card stays in the transcript as a record. Editing it and
pressing **Run** again re-renders only the rows whose fingerprints changed and
their dependents.

## 6. The plan

One JSON document, saved with the chat. The model writes fields of it; code
owns its shape. A sketch, not the final schema:

```json
{
  "version": 1,
  "brief": "a 40-second spot: a lighthouse keeper finds a message in a bottle…",
  "assumptions": ["no dialogue"],
  "title": "The Bottle",
  "seconds": 40,
  "look": "overcast, desaturated teal, 35mm grain",
  "rail": {"still": "krea2", "edit": "qwenedit", "video": "h3", "aspect": "16:9"},
  "shot_limit": 15,
  "keyframes": true,
  "beats": [{"id": "b1", "text": "the keeper climbs the stairs at dusk", "weight": "medium", "seconds": 8}],
  "entities": [
    {"id": "e1", "name": "keeper", "kind": "person", "description": "…",
     "source": {"cited": "@george"}, "state": "approved"},
    {"id": "e2", "name": "lighthouse", "kind": "place", "description": "…",
     "source": {"new": {"prompt": "…"}}, "handle": "pic-3", "state": "pending"}
  ],
  "shots": [
    {"id": "s1", "beat": "b1", "action": "@keeper climbs the spiral stairs…",
     "seconds": 8, "continues": "new", "keyframe": "pic-5", "after": null,
     "state": "approved"}
  ]
}
```

- **`rail` is a snapshot, not a choice.** It records what the room had selected
  when each row was made. If the person changes the rail before the run, rows
  not yet rendered follow the new selection: code re-splits shots against the
  new video family's `max_seconds`, and the card says what moved. Approved
  sheets stay approved; they are pictures, not settings.
- **Ids, not positions.** Rows are named by id, so an edit or redo of one never
  renumbers another. Handles are filled in as rows render.
- **Row states:** `planned`, `rendering`, `pending` (rendered, awaiting
  approval), `approved`, `stale` (something it cites changed), `failed`. Run is
  enabled when no prep row is anything but `approved`.
- **Fingerprints, as Mago does.** Each renderable row hashes what it renders
  from: prompt, cited files, family, seed, seconds. A change marks the row and
  its dependents stale; nothing else re-renders.
- **Validated on both sides.** `creator/director.py` holds the rules, and the
  card re-checks them live in `web/creator/director.js`, under a mirror test,
  the same deal `state.js` has with `compile.py`.

## 7. Reuse is citing

Reuse works exactly as it does in a turn today: the person cites who and what
they want. `@george` in the brief is George from the chat's cast, brought in
with the `@` menu like always. A picture or clip cited from the ledger is used
as that picture. Director does not search the cast library or the style
catalogue on its own. The entity call is told who is cited and lists only what
is still missing, and only that gets a sheet in prep. Someone the person forgot
to cite can be cited in a plan turn later ("use @george for the keeper"), which
swaps the entity's source and drops its sheet.

The look is plain text from the basics call, or the person's own words. Code
appends it to every still and shot prompt, keeping style apart from content as
Mago does. The model never restates the style inside a prompt: a small model
drifts when it writes the same thing twelve times. A style the person picks on
the rail or cites applies the way it does to any turn.

## 8. Where state lives

The chat keeps its state in the browser and saves it per chat through the
userdata API (`chatstore.js`); the server is stateless by design (see the
header of `routes/chat.py`). Director keeps that for the plan and prep: the
plan is part of the chat's saved state, and prep renders are ordinary renders
the room queues and lands itself.

**The run is the exception.** It can take an hour and must survive a closed
tab, so the server drives it:

- **Run** sends the approved plan, the ledger entries it cites and the rail to
  a `director/run` route. The server keeps one run file,
  `continuity.director.<id>.json`, in the same user directory as the chats.
- A controller task in the server process puts the next ready step on the
  queue through the same build path `chat/render` uses, and advances on
  `executed`.
- The room, while open, follows the run on the socket and lands each clip
  exactly as it lands one it queued itself. A room opened later reads the run
  file and lands whatever finished while it was away, into the chat it belongs
  to (the room already lands late renders into the right chat: see `home` in
  `chat.js`).
- On server start, an unfinished run comes back **stopped**, never running: a
  restart is not consent to spend the GPU. **Run** continues it.

## 9. In the room

- **The plan card** sits in the transcript where the brief was sent. Header:
  title, length, look, the rail it renders on, assumptions. Then beats,
  entities (with their source and state) and shots (with timings, keyframe
  thumbnail and state). Rows are editable in place. The footer holds *Make the
  missing pieces*, the keyframes toggle, and **Run** with what it will render
  and an estimated time from past renders of those families on this machine.
- **Prep cards** are ordinary render cards with *Approve* and *Redo* added, and
  a small tag naming the plan row they belong to.
- **Run** turns the card's footer into progress: shot n of m, the current step,
  **Stop**.
- **The piece** is the last clip's card, playing the joined film, as the strip
  already does.
- i18n: every new string is an English sentence key, as everywhere else.

## 10. Architecture

- **`creator/director.py`** — pure: no ComfyUI, no disk. Plan schema and
  validation, seconds arithmetic, splitting, dependency order, row states,
  fingerprints, plan row → chat action, applying a plan turn's edit.
- **`creator/prompts/director/*.txt`** — one prompt file per call (`brief`,
  `basics`, `beats`, `entities`, `shots`, `sheet`, `turn`),
  each with one worked example. Stable wording, tuned on the bench, never
  assembled at runtime.
- **`creator/routes/director.py`** — `plan` (brief → plan; all the planning
  calls inside one job, answered on the socket like a chat turn), `turn` (a
  plan turn), `row` (redo one row's call), `run`, `stop`, `status`. Prep
  renders do not need a route of their own: they are `chat/render` calls with
  actions `director.py` built.
- **Model calls** all go through `_ask`. Where the backend enforces a schema
  (Ollama's `format`, OpenAI's `response_format: json_schema`), the call's
  schema is sent along. Elsewhere, including the in-process refiner, the reply
  is the fenced JSON with the tolerant parse and one re-ask. Native tool calls
  are not needed.
- **Frontend.** `web/creator/director.js` holds the plan card and its live
  rules (mirrored). `chat.js` gains the Plan toggle, plan turns, the
  Approve/Redo actions on prep cards, and following a run. Styles go in a new
  `web/creator/styles/director.js`, owning its own `.mmc-*` classes.
  `chatstore.js` saves the plan with the chat.
- **Headless.** Because planning and running are server routes, a script can
  brief, approve and run without the browser. The end-to-end test uses this
  (§11), and it is a later extension of `skills/continuity-render`.

## 11. Testing

Built so the same tools run here on a small model and in the lab on large ones,
and print results that can be compared.

| Level | What | Model | Where |
|---|---|---|---|
| Pure suite | `tests/test_director.py`: schema, seconds arithmetic, splitting at the limit and at the rail family's `max_seconds`, re-split on a rail change, dependency order, row states and staleness, fingerprints, row → action, a plan turn's edit applied to the plan | none | anywhere |
| Mirror suite | `tests/test_director_mirror.py`: the card's live rules reproduce `director.py` | none | anywhere with `node` |
| Replay suite | `tests/test_director_replay.py`: recorded model replies and a fake renderer writing placeholder files. Drives plan → prep → approve → run: stale marking on a changed sheet, Run disabled until approved, restart → stopped, continue after a failure, only stale rows re-rendered. Fixtures for malformed JSON, a bad citation, a model that keeps asking questions | recorded | anywhere |
| Bench | `tools/director_bench.py --url … --model …`: planning and plan turns only, over `tests/director_briefs.jsonl` | any | this Mac (small), the lab (large) |
| Graph dry run | build every row's action from a benched plan and compile each blob without sampling, on each rail combination the machine can render | any | anywhere with ComfyUI |
| End to end | `tools/director_e2e.py "brief" --approve-all [--profile smoke]` against a running ComfyUI, through whatever backend and rail its settings name: plan, prep, approve everything, run | any | the lab; a smoke profile here |

**The bench** answers "how well does it hold up". For each brief and call it
records:

- valid on the first try, valid after the re-ask, or failed;
- seconds after code correction against the target;
- every citation resolves;
- cited cast members used, never given a new sheet (briefs citing `@` members
  are in the set on purpose);
- plan turns that pick the right row and act (a scripted list of changes per
  brief);
- wall time and tokens per call.

It prints a table and, with `--json`, a report file, so a 2B run on this Mac and
a 27B run in the lab sit side by side. The brief set covers a single 6 s shot, a
15 s shot exactly at the limit, a 40 s three-beat piece, one citing a cast
member, one with an attached picture, and one vague
enough to need a question.

**This Mac:** Ollama with `lfm3-omni` (2.2B) is the
floor. A prompt change is judged across every model benched, never tuned for
this one. The smoke profile uses the smallest still family, turbo, low
resolution and the shortest clips, with a two-shot 12 s brief, and should
finish in minutes.

**The lab** runs the same bench and the end-to-end test on real models and full
settings. The in-process refiner path is covered there by pointing the room's
settings at it.

## 12. Sequencing

1. `director.py`: plan schema, arithmetic, splitting, row states, row → action,
   with the pure suite.
2. Prompt files for basics, beats, entities and shots, and `director_bench.py`.
   Bench on this Mac. **This decides how small the calls have to be before
   anything else is built:** if the floor model cannot produce usable beats or
   shots, more moves into code first.
3. The plan route and the plan card: read-only, then editable, saved with the
   chat.
4. Prep: sheets and props as render cards, Approve/Redo, cast and references on
   approval, change by talking, staleness. Then keyframes.
5. Plan turns (§5.4) and their bench cases.
6. The run: route, run file, controller, landing in the room, restart →
   stopped. The replay suite. The graph dry run.
7. `director_e2e.py`, the smoke profile here, then the lab.
8. Docs: a Director section in `docs/tools.md`, and the CHANGELOG.

### 12.1 What the step-2 bench decided (2026-11-08)

`tools/director_bench.py` against `lfm3-omni` (2.2B) on Ollama, six briefs,
three seeds with the schema sent and two without. With the schema, every
plan completed, 113 of 116 calls valid on the first try and the rest after
one re-ask, at about 12 s per plan. Without it, 11 of 12 briefs gave a plan
(one with a warning) and one failed on a broken object. The vague
brief never got a question (0 of 5): the floor model plans anything rather
than ask.

The floor model *copies* what it is shown, and that decided the shape of the
calls more than any count did. It copied the worked examples' content (a
bakery's brick oven turned up in a train carriage), the previous shot when
shown it, and the first beat's text when shown the beat list. So, moved into
code or out of the messages (`creator/director_calls.py`):

- worked examples tell a story no brief tells, and an entity neither the
  brief nor the beats mention is dropped (`invented` in the bench);
- the shots call is shown only the brief, the names and *this* beat — not
  the other beats, not the shot before;
- a plain mention of an entity ("the bottle") is cited by code;
- a shot that mostly repeats an earlier one, or cites a name the plan does
  not hold, is a *doubt*: re-asked once, then kept with a warning (the `@`
  comes off an unknown name), never a discarded plan;
- an object the model forgot to close is closed;
- an entity named after an attached handle (`@pic-1` read as a person) is
  dropped, and accents fold in names (`café` is `cafe`);
- a piece can be one beat (`MIN_BEATS` is 1), for the single-shot brief.

What the bench still shows on the floor and code cannot fix: entity kinds
are often wrong (rain as a thing, a crowd as a place), and the look line
sometimes names people or places despite the prompt. Both are worth reading
on the lab's models before more moves into code.

### 12.2 What the step-5 bench showed (2026-11-08)

Fourteen scripted plan turns over five briefs (`turns` in
`tests/director_briefs.jsonl`), on `lfm3-omni` with the schema, two seeds.
At first, 6 of 12 measurable turns picked the right act and row. The misses
were mostly things the person's words say plainly, so code now reads them
first (`director_calls.overrule`), as it reads a length out of a brief: a beat
or shot named by number or position ("the last beat", "shot 3"), a title
("call it …") and a length. With that, 12 of 13 and 13 of 14, with code
correcting the call on 4. Also moved into code:

- a rewritten row that comes back as it was is a *doubt*: re-asked once, then
  kept with a warning. The floor model copies the row it is shown about as
  often as it changes it;
- a row that names somebody from the cast is re-asked, since they are used as
  they are and their row has nothing to change. On the floor model it was the
  row picked for "he" in a message about a shot;
- without a schema the model drops the act on an answer (`{"say": …}`), which
  code reads as a say, unless it only repeats the message;
- a turn whose own call fails twice tells the person to name the row the way
  the card does, instead of quoting the sentence the model was re-asked with.

What code cannot fix: the floor model never once answered `replan` for "set
it on a sunny summer morning". It edits a person, or answers instead. Worth
reading on the lab's models before the prompt changes. Someone the entity call
left out (the waitress, on one seed) cannot be added by a turn. They can
only be described in the beats.

## 13. Risks

- **Small models plan badly.** Mitigated by small calls, schemas and code-owned
  arithmetic, and measured by the bench before the UI is built (§12 step 2). If
  the floor is too low, the honest answer is a note in the room that a larger
  model plans better, not a second code path.
- **Continuity across shots drifts.** Same faces through cast citations, same
  place through `:scene` references, same moment through `pin`. Approved
  keyframes catch the rest before video. Mago's experience suggests the cut/pin
  wording matters more than it looks.
- **The rail's families may not suit every step.** A still family with no edit
  family behind it redraws instead of changing in place, so "make the keeper
  older" can move more than asked. That is the room's behaviour today, and
  Director inherits it rather than working around it.
- **Long runs and VRAM.** An in-process refiner and the samplers share a GPU.
  The run makes no model calls at all, so the two never overlap.
- **Server-side run state** is new for the chat. Keeping the run file the only
  state, and coming back stopped after a restart, keeps that surface small.

## 14. Not in v1

- Dialogue and voice per character (H3 can, but it is its own design).
- A separate sound or music pass.
- Several takes per shot with a picker.
- Sketch storyboards; keyframe stills do that job here.
- Planning from a screenplay document.
- Opening the piece on the canvas as a Creator node.
- Native tool calling as the primary path.

## 15. Open questions

- **Shot limit:** 15 s by default as a planning choice, under H3's and LTX's
  declared 60 s. Should the limit be per family?
- **The one-pass timeline:** H3 can render a multi-shot timeline in one pass
  with no seams (`compile.single_payload`). Should Run offer it for short
  pieces, at the cost of one checkpoint and one LoRA stack for the whole piece?
- **Approving in bulk:** should *Approve all* exist for prep, or should each
  sheet be looked at once?

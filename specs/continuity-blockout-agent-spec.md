# Continuity — the blockout's agent

Spec for putting the agent that stages a blockout into the bench. Design and
decisions, not code. Written 2026-11-25 against `claude/exciting-cori-srgc48`
at `07f3c27`, after reading what is built (`web/creator/stagehand.js`,
`creator/stagehand.py`, `routes/stagehand.py`, `tools/stagehand_bench.py`),
the refiner's settings (`web/creator/refine.js`, `creator/refine_remote.py`,
`settings.clean_refiner`) and the bench (`web/creator/staging.js`, `reel.js`).
Revised the same day after the mockup: the conversation is a window of its
own and a message can carry pictures. Revised again after reading how the chat
asks its model (`routes/chat._ask`): the agent runs on whatever the refiner
has selected, a server's model or one in ComfyUI.

A mockup of the window was made alongside this spec and is not in the
repository. This spec is written to stand without it.

## 1. Where things stand

The agent runs, and nobody can reach it. `stagehand.js` holds a conversation
with a chat model and 21 tools that stage a piece: objects and sets, the cast,
the film's text, shots, the camera, walks, and three ways of looking at the
result. `stagehand.py` passes each exchange to the refiner's server and logs
it. The bench runs both without a window.

A scripted run of every tool (24 calls, no model) did what each tool says, and
the pictures draw. What has not been done:

- Nothing in the bench opens it.
- It takes a model name from its caller. The bench tool passes one by hand.
- It has no system prompt, so the model is told nothing about what a blockout
  is or who it is talking to.
- It only talks to a server. With the refiner set to a model in ComfyUI it
  has nothing to ask.
- It has not been read on a real model in this branch.

This spec covers those five. The reel gets no agent here (§10).

## 2. Decisions

- **It is the refiner's model.** The agent runs on whatever the refiner's
  settings have selected, on either backend: a model on the server, or a text
  encoder in ComfyUI. It has no model choice, no URL and no key of its own.
  The window names the model and where it runs, and a click there opens the
  refiner's settings. That is how a person chooses any model they like.
- **Built for large models, open to any.** The header says so in one line:
  larger models, 27B and up. Nothing stops a smaller one being used.
- **One conversation, two ways of asking.** A server is asked with native
  tool calls, as built. A model in ComfyUI has no tool calling, so it is asked
  the way the chat asks: the tools are described in words and the reply is a
  fenced JSON object naming the calls. The server half translates, and the
  browser's loop and its tools are the same for both (§3.1).
- **A short system prompt, and it stays short.** It says what this is, who is
  on the other side, the frame of reference, and how a turn ends. It does not
  say how a scene should look. Taste stays the model's and the person's.
- **The person watches it happen.** Every tool call lands in the bench as it
  is answered: the object on the stage, the words in the script, the shot on
  the strip. Nothing is held back for the end of the message.
- **Pictures go both ways.** The person can send pictures with a message, as
  references for the set or a frame to match. The window shows the pictures
  the model looked at.
- **The piece is changed the way a hand changes it.** Every change goes
  through the bench's own commit: words follow the staging, a kept take whose
  shot changed is released, the node is written. The agent has no private
  path into the piece.
- **One message, one step back.** Whatever a message made the agent do is
  undone with one Undo.
- **It builds; it does not shoot.** No tool queues a render, reads a file or
  touches a setting. Shoot stays the person's.
- **No quiet fallbacks.** A server that refuses tools, a model that cannot see
  a picture, a reply cut off: each is said in the window in a sentence, with
  the server's own words where it gave some.

## 3. The model and the refiner's settings

The browser sends what a refine press and a chat turn send (`refineRequest`):
the backend's name, the model's, and the device. What the agent does with each
setting:

| Setting | On a server | In ComfyUI |
|---|---|---|
| Backend | Followed. | Followed. |
| Model | The server's selected model. | The selected text encoder. |
| URL and key | Read on the server from the credentials file. Never in the browser. | Not used. |
| Device | Not used. | Followed, and refused in the chat's words when it is gone. |
| Thinking | Followed: off asks for no reasoning, on leaves the server's default. | Followed, as `refine_local.chat` does it. |
| Eject | Once, after the last exchange of a message and after a Stop. | Not needed: the weights leave the GPU after every generation. |
| Temperature, seed | Not sent. The model's defaults stand. | The chat's cold default (0.3), a new seed each exchange. |
| Reply budget | Not sent. A reply that ends on `length` is an error said in the window. | A budget of its own, sized for a list of calls (§11). This backend reserves memory for the prompt plus the budget, so it cannot be left open. |
| Language, skill, templates | Not used. | Not used. |

**No model selected** is the one thing that disables the composer, in the
sentence the chat already uses for it, with a link to the refiner's settings.

**The header** names the model and where it runs ("qwen35_27b · in ComfyUI",
"Ternary-Bonsai-2-27B · on your server's host") and has a **Change** action that opens
the refiner's settings popover. Under it, always: "Designed for larger models,
27B and up." Nothing is sniffed off a model's name: the pack cannot know a
model's size from what a server calls it. A change of model applies from the
next message; a message already running finishes on the model it started
with.

### 3.1 Two ways of asking

The browser holds the conversation in one shape, the one a chat-completions
server speaks: messages, tool calls, tool answers. `creator/stagehand.py`
turns that into what each backend can take and turns the reply back, so
nothing in `stagehand.js` knows which backend answered.

**A server** gets the conversation as it is, with the tools as `tools`. This
is what is built.

**A model in ComfyUI** gets the fenced form, the chat's own bargain:

- The system text is the system prompt (§4) followed by the tools: each one's
  name and its docstring, as written in `stagehand.js`. One source for both
  ways of asking.
- The reply is a line of what it is about to do, then one object:
  `{"calls": [{"tool": "add_objects", "args": {…}}, …]}`, or
  `{"say": "…"}` when it is done or has a question. A reply with no object is
  read as a say, as the chat reads one.
- The object is found and read tolerantly (`refine.json_object`), an object
  the model forgot to close is closed, and a reply that cannot be read is
  re-asked once with the reason. A second failure ends the message with a
  sentence in the window.
- A call to a tool that does not exist, or with a wrong argument, is not
  re-asked. It goes to the tool, which answers with why, exactly as a native
  call does.
- What comes back to the browser is the same message a server would have
  sent, with the calls as `tool_calls`.
- The conversation is written as one prompt of several turns: the person's
  messages, the model's own replies, and each tool's answer as a turn of its
  own with its picture. `refine_local` gains a conversation form of `chat`
  for this; today it writes one system and one user turn.

**A server that refuses `tools`** (a runtime or a model without tool calling)
is asked again in the fenced form, and the window says so once: "This server
does not call tools; Stagehand is asking in plain JSON instead."

**A server that will not take a picture in a tool's answer.** llama.cpp
accepts one. I expect the hosted OpenAI door to refuse it; this is not
verified. When a server refuses the request for that reason, the exchange is
sent again with each picture moved into a user message straight after the
tool answers, and the session remembers to send them that way.

### 3.2 Where each exchange runs

As for a chat turn, and for the same reasons (`jobs.py`):

- **In ComfyUI**, each exchange is a job on ComfyUI's own queue. It waits
  behind a render that is running, a render waits behind it, the progress bar
  is the real one, and Cancel reaches it. The answer arrives on `executed`.
- **On a server**, an exchange is off the queue and answered on the socket
  (`jobs.answer_later`). The route as built holds the request open until the
  model has answered, which a long reply outlasts: the frontend gives up on a
  fetch after a minute.

Between two exchanges the tools run in the browser, so a message on a model
in ComfyUI is many short jobs and not one long one. The weights go back to
RAM after each and are copied to the GPU for the next. What that costs is not
measured (§11).

## 4. The system prompt

One file, `creator/prompts/stagehand/system.txt`, the same place every other
prompt in the pack lives. Stable wording, never assembled at runtime, so the
server's cache holds it and the tools behind it. `stagehand.turn` puts it in
front of the conversation it is handed and writes it into the log's first
entry beside the tools.

What it carries, and nothing else:

1. What a blockout is and what becomes of it.
2. Who is on the other side and what they see.
3. What a film is made of here: sets, shots, what a shot holds.
4. The frame of reference, once, instead of in every tool.
5. How to work: build, look, say what was done, ask only when stuck.

Proposed wording, to be read on the bench before it is frozen:

```
You are staging a film in a blockout bench: a rough 3D set of plain shapes and
ready models, with a camera and things that move. A video model is later given
each shot's blockout as a guide, together with the shot's text.

The person you are talking to has the bench open. They see the set and the
shots change as you work, can change anything by hand, and render the film
themselves. You cannot render.

A film has sets, which are places, and shots. A shot is on one set and has a
length, a text, a camera and the paths of whatever moves in it. Distances are
metres and angles are degrees. x runs to the right, z runs forward, y runs up,
the floor is at y 0, and something facing 0 looks along +z.

Each message comes with what the person has open and selected, with the scene
as it stands if it changed since you last read it, and sometimes with pictures
of what they have in mind. Do what was asked and
no more. Look at what you built before you say it is done: a picture shows what
a number does not. When you are done, say in a sentence or two what you did.
Ask a question only when you cannot go on without the answer.
```

What goes beside the person's message instead, because it changes
(`windowState` and `sceneText`, as built):

- the pictures the person attached to this message (§5.4);
- what the bench has open: the shot, the moment, the selected object or set;
- the frame's shape and the longest shot the piece's family renders;
- the scene, when it is not what the model last read.

Two additions to the scene's lines: a shot with a kept take says so, since
changing it means shooting it again, and a finished clip already says it is
one.

The coordinate sentences in `add_objects` and `move_object` stay. A tool's
docstring has to be readable on its own, and the bench has shown small models
read the tool before the prompt.

## 5. In the bench

### 5.1 Where it is

A button in the bench's header, **Stagehand**, opens a window over the
inspector's column, with a shadow and an edge so it reads as a window and not
as a panel of the bench. The script, the stage and the piece underneath stay
in view, so the person watches the set being built and the words being
written while the conversation runs beside them. The button closes it again,
and so does the window's own close. The inspector is under it, as it was.

Closing the window does not stop the agent. The button carries a pulsing dot
while it works, open or closed.

The window, top to bottom: the header, the transcript, the composer.

### 5.2 The header

- The name, **New conversation**, and close.
- The model and where it runs, with **Change** (§3).
- The line about size.

**New conversation** forgets what was said. It does not change the piece.

### 5.3 The transcript

- **The person's messages**, as typed, with the pictures they sent as
  thumbnails above the words.
- **The agent's words**, as text. Nothing it writes is drawn as markup.
- **What it did**, one quiet line per tool call, in the bench's vocabulary
  ("Added 9 objects to the set Kitchen", "Camera of shot 1", "Shot 2 is 5 s
  now"). A line opens to the tool's own answer. A call that was refused is
  drawn as that, with the reason the tool gave.
- **What it looked at**, as a small picture under the line of the call that
  made it. A click enlarges one. The person sees what the model was shown.
- **Errors**, as a sentence: the server's words where it gave some.

The newest line stays in view. While an exchange is out, the last line says
"Working". There is no token streaming in this pass; a model that builds a
set answers in tool calls every few seconds to a minute, and each lands as it
comes.

### 5.4 The composer

A picture button, a text box, and **Send**, which becomes **Stop** while the
agent works. Enter sends, Shift+Enter breaks the line.

**Pictures.** The button opens the file picker; a picture can also be dropped
on the window or pasted into the box. Up to four a message, each shown as a
chip above the box with a way to take it off again. A picture is scaled in
the browser to 1024 px on its long edge before it is sent, and goes to the
model as part of the person's message. It is a thing said in the
conversation: it is not added to the piece's references, and no shot cites
it. Making one a reference is the person's, in the bench, as today (§12).

With no model selected, the composer is disabled and the sentence under it
says so (§3).

### 5.5 Watching it work

Each tool call is applied and drawn before the next is answered
(`Stagehand.answer`, as built). What the person sees for each kind:

| The agent | In the bench |
|---|---|
| adds, copies, moves, turns, resizes an object | It is on the stage at once, lit for a moment so the eye finds it. |
| removes one | It is gone from the stage. |
| adds to the cast | Their face is in the script's cast row. |
| writes the film's text | The scene, sound or score in the script changes, lit for a moment. |
| adds or changes a shot | Its paragraph is in the script and its card on the strip, at its length. |
| places a camera, walks somebody | The camera and the path are drawn on the stage, and their lanes appear under the glass. |
| switches set | The glass goes to that set. |

The words arrive whole, since a tool call does. They are not typed out. A
highlight that fades is enough to show where they landed.

A pill on the glass says what it is doing, in the bench's words ("Stagehand:
placing the camera of shot 1"), read off the call being answered. It is there
with the window closed too.

The glass keeps the view the person has. It does not jump to whatever was
last touched, except to follow a change of set. The picture in the transcript
shows the agent's view.

### 5.6 What the agent knows about the window

- The set it works on starts as the set the glass shows.
- Its message carries what is open and selected (§4), so "move this to the
  window" and "make this shot longer" mean what the person is looking at.

### 5.7 While it works

The bench stays open for looking: orbit, play, scrub, select. Editing is
locked for as long as the agent works, and the line under the reel says why
("Stagehand is working. You can look around; editing waits until it is done
or stopped."). Two hands on one piece make an undo step nobody can name.
Shoot is disabled for the same reason and says so.

The lock ends the moment the work does, however it ends: the agent is done,
it failed, or the person pressed **Stop**. Nothing else has to be clicked.

**Stop** ends the work at once and gives the bench back. On a server, the
browser drops its request and the server closes its connection to the model,
so a server on the LAN stops generating. In ComfyUI, the job is cancelled the
way ComfyUI's own Cancel cancels it. What was done stays, as one step, and
the transcript says so. The conversation is left so that the next message can
go on from it (every call has its answer; `settle`, as built).

### 5.8 Undo

When a message is sent the bench holds the piece as it stood. Changes made
while the agent works are committed as they land and are not steps. When the
agent is done, stopped or failed, the held piece becomes one step. Undo takes
the whole message back; Redo brings it again.

The conversation is not rewound by an Undo. The next message carries the
scene as it now stands, as it does after any change by hand.

### 5.9 How a change lands

`apply` copies the changed piece into the piece the window holds, the way a
step back does, and calls the bench's `commit`. The node, the reel's window
on the same piece and the kept takes follow from that, as for a drag.

### 5.10 How long a conversation lives

For as long as the page does, per piece: closing the bench and opening it
again finds the conversation there, and an agent still working. It is not
saved with the workflow. The log on disk is the record (§7).

## 6. What a conversation costs

Every exchange sends the whole conversation, pictures included. A picture is
20 to 100 KB, and a message may run to 60 exchanges.

- **The agent's own pictures are thinned.** A request carries the newest six
  pictures the tools made. An older one is replaced, in what is sent, by a
  line of text ("an earlier picture of the set"). They are dropped three at a
  time so the front of the conversation changes rarely and a server's cache
  keeps holding. The transcript and the log keep every picture. Six and three
  are a first guess (§11).
- **The person's pictures are never thinned.** They are the brief. Four a
  message at 1024 px is what keeps them affordable.
- **In ComfyUI, earlier messages are folded.** That backend has no context
  setting: the prompt is embedded whole, and memory is reserved for all of it
  on the card the render wants. So of every message before the current one,
  the prompt keeps the person's words and the agent's closing words, and
  drops the calls between. Nothing is lost that the model needs: each message
  carries the scene as it stands. The current message's calls stay whole.
- **A context that has run out** is said in the window with the backend's own
  message, and **New conversation** is offered beside it.
- **The turn limit** stays at 60 exchanges a message. Reaching it is said,
  and the next message goes on.

## 7. The server half

- **`creator/stagehand.py`** stays pure and gains the translation of §3.1:
  the system text with the tools in it, the conversation as turns, and the
  reader that turns a fenced reply into a message with `tool_calls`. Tested
  without a model, as `chat.parse` is.
- **The route** takes `{session, backend, model, device, messages, tools,
  seen, client_id}` and answers the way a chat turn does: a job on the queue
  for a model in ComfyUI, an answer on the socket for a server (§3.2).
- **Stop** is a second route that takes the session: it closes the connection
  held for a server, or cancels the job in ComfyUI.
- **One exchange per session at a time.** A second is refused.
- **The log** stays as built: one folder per session under the user
  directory, every message once, pictures as files, the reply with its usage
  and timings. New: the system prompt in the first entry, which way the model
  was asked, the raw reply beside the message read out of it on the fenced
  form, a person's JPEG kept as a file the way a PNG is, and only the newest
  20 sessions are kept.
- **Nothing else moves to the server.** The conversation and the tools stay
  in the browser, where the piece and the renderer are.

## 8. The tools

The 21 tools stay as they are. Three changes belong to this pass because the
window makes them matter:

- A shot's length is checked against what the piece's family renders, not
  against a flat 60 seconds.
- `add_cast` and `plays` already check the cast; `describe_object` with a
  person who plays nobody says so in its answer, since the bench draws that
  differently.
- The scene's lines gain the kept take (§4).

Added after the first run in the window, where a kitchen was asked for and
built from walls: `use_set` takes `library`, which starts the new set as one of
the scene library's, with its furniture and people and without its camera
move. The names are listed in the tool, as the models are in `add_objects`.

From the same run, where "the camera should follow @marta" took five minutes
and was stopped: a look through a camera drew the people as two grey boxes
among grey boxes, and the model took them for furniture in front of the
people. Every look now numbers and colours the objects as the overview does.
A camera kept on somebody is listed turned as that makes it, not as its marks
were set, and `keep_camera_on` says that it only turns the camera.

Left for later, in the order I would take them: remove a set or a cast member, reorder shots, bend a path, the speed
curve. Each is a small tool over something the bench already does.

## 9. Testing

| Level | What | Model | Where |
|---|---|---|---|
| Server suite | `tests/test_stagehand.py`: the system prompt goes first and once, the log holds it, a request with no model is refused, a second exchange on a session is refused, old sessions are swept, a person's picture is logged as a file. The existing checks stay, with "nothing is put in front" becoming "only the prompt is" | none | anywhere |
| Fenced suite | In the same file: the tools written into the system text, a conversation written as turns with its pictures in order, earlier messages folded, and replies read back into calls. Fixtures for a say, several calls, no object at all, an object left open, prose around the fence, and a reply that is re-asked once and then given up on | recorded | anywhere |
| Tools suite | A scripted run of every tool through the real `stagehand.js`, in the browser the other browser checks use: each answer, each refusal, the piece that results, one undo step per message | none | anywhere with Playwright |
| Window checks | In `tests/browser/test-blockout-bench.cjs`: the window opens and closes over the inspector, the header names the refiner's model on either backend and Change opens its settings, disabled with no model selected, a scripted conversation draws its lines and pictures and each call shows on the stage and in the script before the next, a picture attached goes out with the message, editing is locked while it works and free again the moment it is done or stopped, Stop leaves one step | none | anywhere with Playwright |
| Bench | `tools/stagehand_bench.py` on real briefs. It learns to run on Chromium as well as Firefox, reads the backend and model from the refiner's settings unless given them, and takes `--fenced` to ask a server the way a model in ComfyUI is asked, so that form can be tuned without a GPU | any | the lab |

**What the bench is read for**, since nothing here can be scored by code:
whether the set is where the brief puts it (the pictures), whether the model
looks before it says it is done, how many calls are refused and whether the
next call puts them right, exchanges and tokens per brief, and what the
picture thinning costs. Six briefs to start: one room with two people, a
street with a car driving through, a change to an existing set ("move the
table to the window"), a second shot on the same set, a room built from an
attached picture, and one vague enough that a question is the right answer.
Each is run on a 27B-class model both ways of asking, and on the 2.2B floor,
so the header's line about size rests on something.

## 10. Not in this pass

- **The reel.** Built since, as a second place and not a second agent
  (2026-11-25): the conversation is told where it is, `reel` or `blockout`,
  and each has a prompt (`prompts/stagehand/reel.txt`) and a tool set of its
  own. The reel's tools write the film: cast, texts, shots, their order and
  their joins. None stages, and none renders. `open_blockout` is the one way
  from the reel into the bench, in the middle of a message; there is no tool
  back. Takes, look and Shoot are still not the agent's.
- Token streaming.
- A conversation saved with the piece.
- A model choice, a server or a key of its own.
- Native tool calls for a model in ComfyUI.
- A warning read off a model's name or size.
- A picture sent in the conversation becoming a reference of the piece.
- Moving or resizing the window.
- Tools that render, read files or change settings.

## 11. Not measured yet

- **The system prompt's wording.** Proposed, not benched. It is read on the
  lab's model before it is frozen, and judged across every model benched, as
  the Director's prompts are.
- **Picture thinning**: six kept and three dropped at a time is a guess.
- **Which servers refuse a picture in a tool's answer.** §3.1's fallback is
  built on an expectation; the bench says which providers need it.
- **The fenced form against native calls.** Whether the same model stages as
  well when asked in JSON, and how often a reply needs its re-ask.
- **The models in ComfyUI.** They run from 0.8B to 27B. Which of them stage
  anything usable is unknown; the chat's floor suggests the small ones will
  copy what they are shown.
- **The reply budget in ComfyUI**, and what moving the weights on and off the
  GPU for every exchange costs. If it is seconds each, holding the model for
  the length of a message is the next thing to build.
- **Folding earlier messages**: whether a model misses the calls it no longer
  sees.
- **Thinking.** Whether a model that reasons stages better or only slower.
- **27B and up.** The header's line is the design's intent. The bench on the
  floor model says how far below it the agent still stages something usable.
- **Building from a picture.** Whether a model places a room the way an
  attached picture shows it, or only names what is in it.

## 12. Open questions

- **A sent picture as a reference.** A picture attached for the agent is
  often one the render should be given too. A tool that adds it to the
  piece's references would do it, at the cost of the agent writing a file
  into the input folder, which §2 rules out today. Left to the person for
  now.

## 13. Order

1. The server half for a server: the backend and model from the request,
   thinking, eject, the system prompt, the answer on the socket, Stop, the
   log's sweep, with the server suite.
2. The tools suite on Chromium, and the three tool changes of §8.
3. The window: header with the model's name and Change, transcript, composer,
   the disabled state.
4. Apply through commit, each call drawn as it lands (§5.5), the one undo
   step, the lock while it works and its release.
5. The fenced form: the translation in `stagehand.py` with its suite, the
   bench's `--fenced` against a server, then the conversation form of
   `refine_local.chat` and the job on the queue.
6. Pictures in a message: attach, drop, paste, scale, send, log.
7. Picture thinning, folding, and the picture fallback of §3.1.
8. The bench: the prompt's wording, both ways of asking, the models in
   ComfyUI, then the numbers of §11.
9. Docs: a section in `docs/tools.md`, and the CHANGELOG.

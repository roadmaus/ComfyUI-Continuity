"""`/continuity/chat/*`: the doors the chat room knocks on.

The room is a conversation and a queue, and those are the two things the server
has to hold up. `chat/turn` asks the refiner model what to do about one user
message and answers `{say, action?, raw}`. `chat/render` takes the action it
answered with, turns it into a blob, compiles that blob as a dry run, and puts a
one-node prompt on ComfyUI's queue. `chat/again` is the small third: an action
a card already rendered, stamped again for the rail as it is now, so a retake
follows the pills (`_stamp`). Everything between them lives in the
browser: the conversation, the ledger of what has been made, the rail. This
module is stateless on purpose — the spec's §5.5 — so a reload starts fresh and
nothing here has a session to lose.

**The thinking is next door.** `creator/chat.py` owns the action schema, the
parse, the re-ask protocol, the machine card and the two blob patches, and it is
pure. What is here is the joining that cannot be: which files are on this disk,
what this machine last picked, what the compiler says about the result, and the
queue. That is the same line `refine_routes.py` draws against
`families/refine.py`, and it is why the whole protocol can be tested without a
server and tuned on `tools/chat_bench.py` without a browser.

**Two backends, one shape.** The remote refiner stays off the queue, exactly
as the refine button's does and for the same reason: it spends somebody else's
GPU, so there is nothing for it to queue behind. It replies `{"answer_id": …}`
at once and the turn follows on the socket as `mmc_answer`
(`jobs.answer_later`), since a turn can outlast the frontend's fetch timeout.
The in-process one is a 4B model on the card the render wants, so it rides the
queue as a `chat` job and the reply arrives on `executed` under
`ui.continuity`. The turn object is the same either way, and `queue.run()`
waits for whichever of the two the reply names, so one call site in the room
covers both backends. `/continuity/refine` says it the same way.

**The re-ask is a second call inside the same job**, never a round trip to the
browser. The room asked one question and is owed one answer; a correction the
person watches happen reads as a failure, and on the queued path it would be a
second wait behind whatever is running.

No native tool calls yet. Where a runtime reports tool support the same schema
is the one tool, but the fenced form is the fallback and the default, and it is
what both backends get here — the seam is `_ask` below, which is the one place
a reply is produced.
"""

import asyncio
import importlib
import json
import logging

from aiohttp import web

from server import PromptServer

from .. import chat, jobs, media, models as core_models, refine_local, refine_remote, refmod
from .. import refine_routes, refine_skill, server_routes, settings
from ..families import manifest, refine, registry
from ..guard import same_origin

log = logging.getLogger(__name__)


# ---- the machine card -------------------------------------------------------
#
# Cached because it is a join of three payloads — every family's manifest, a walk
# of the model directories, and the settings file — and the room asks for it on
# every turn of a conversation that may run for an hour.

_CARDS = {}
_CARDS_KEEP = 4


def machine(still_family, video_family, weights, turbo=False, edit=None):
    """What this machine can make, as the model reads it, and two answers the
    turn needs beside it -> `{card, edit_family, still_pictures}`.

    `card` is `chat.machine_card`. `edit_family` is the family a cited picture
    is changed on when the still family cannot read one — `edit` is the rail's
    own choice, or None for whichever is ready (`chat.pick_edit_family`) — and
    `still_pictures` is `chat.still_pictures` of the still family, the two
    things `chat.still_arch_for` reads. All three are one join of the catalog,
    the folder listing and the picks, so they are made and held together.

    Keyed on its own inputs rather than invalidated from `settings.save`. A hook
    there would catch the settings page and miss everything else that moves this
    answer — the weights popover patches the same file from the node, and the
    rail will patch it again from the room — whereas the key is exactly the
    facts the card is made of, so anything that changes one of them changes the
    key. `turbo` is one of them: with the switch thrown the render loads the
    Turbo checkpoint instead of the ordinary one, so which files are missing is
    a different answer. The listing is not in the key: a walk of the model
    folders on every turn is the cost this cache exists to avoid, and
    `settings.weights` moving is what a *picked* file changing looks like here.
    """
    key = json.dumps([still_family, video_family, weights, bool(turbo), edit],
                     sort_keys=True, default=str)
    held = _CARDS.get(key)
    if held is None:
        catalog = manifest.catalog()
        available = core_models.available()
        picked = chat.pick_edit_family(catalog, available, weights, edit)
        held = {
            "card": chat.machine_card(still_family, video_family, catalog, available,
                                      weights, turbo=bool(turbo),
                                      edit_family=picked["id"] if picked else None),
            "edit_family": picked["id"] if picked else None,
            "still_pictures": chat.still_pictures(
                manifest.describe(still_family), catalog),
        }
        while len(_CARDS) >= _CARDS_KEEP:
            _CARDS.pop(next(iter(_CARDS)))
        _CARDS[key] = held
    return held


# ---- the rail ---------------------------------------------------------------


def _arch_of(family):
    """The pre-stage pill's name for a family, or None where it makes no stills.

    "minimax" is H3's and is frozen in every saved blob, which is why the pill's
    vocabulary and the registry's ids are not the same words — see
    `registry.STILL_ARCHES`. The rail arrives naming families, because that is
    what the machine card and the settings block are keyed by, so the mapping
    happens once, here, and the pure half is handed the arch.
    """
    for arch, owner in registry.STILL_ARCHES.items():
        if owner == family:
            return arch
    return None


def _rail(raw):
    """The room's rail, filled in and with the still family's arch stamped on.

    Absent families fall back to the registry's own defaults, which is what a
    room with no node under it would be holding, and the same answer the node
    gives a freshly dropped blob.

    Both routes pass it the same object: `chat/render` calls it the rail and
    `chat/turn` sends it inside `settings` beside the backend and the model,
    because a turn has to be told the same things a render does — which
    families, and whether turbo is thrown — before it can say what this machine
    can make. The room reads both families off the nodes on the canvas (the
    piece's family, the pre-stage's arch) and sends them here by name.

    The still side is the *image* families and not every family that makes a
    still. H3's still branch is a video generation with one latent frame decoded
    as a picture, and its pre-stage blob is the Creator's own request under a
    `minimax` block rather than the shared image shape — a second blob for this
    room to patch, for a picture the video family can already be asked for
    directly. So the rail offers the families that draw a picture outright, and
    the room's own pill offers the same set.

    `edit_family` is the room's *Edits* choice: the image family a cited
    picture is changed on when the still family cannot read one, or nothing
    for whichever is ready. Read as a preference here and resolved by
    `machine`, which has the disk; `edit_arch` is stamped there.
    """
    rail = dict(raw or {})
    still = rail.get("still_family")
    if still not in registry.IMAGE_FAMILIES:
        still = registry.STILL_ARCHES[registry.DEFAULT_STILL_ARCH]
    video = rail.get("video_family")
    if video not in registry.video_families():
        video = registry.DEFAULT_VIDEO
    edit = rail.get("edit_family")
    rail["still_family"] = still
    rail["video_family"] = video
    rail["still_arch"] = _arch_of(still)
    rail["edit_family"] = edit if edit in registry.IMAGE_FAMILIES else None
    # The latent space the still family reads saved references in, or None:
    # what decides whether a member's mod file is a picture to it.
    rail["still_space"] = (registry.REFMOD.get(still) or {}).get("space")
    return rail


def _base(raw, still):
    """The node's blob and widgets the render is built over -> `(piece, widgets)`.

    `{piece, widgets}` as the room sends it: the pre-stage's `prestage_data` or
    the Creator's `creator_data`, parsed, and the node's sampler widgets by
    name — the seed above all, since the seed is the one number on the row that
    never moved into the blob. A base of the wrong kind is refused rather than
    rendered: a pre-stage blob has an `arch` and a piece has a `family`, and a
    still built over a clip's piece would carry a strip into `compile_prestage`.
    """
    raw = raw if isinstance(raw, dict) else {}
    piece = raw.get("piece")
    if isinstance(piece, str):
        try:
            piece = json.loads(piece)
        except ValueError:
            piece = None
    if not isinstance(piece, dict):
        raise chat.ActionError("the room sent no node to render with.")
    if still and "arch" not in piece:
        raise chat.ActionError("the still's base is not a pre-stage blob.")
    if not still and "arch" in piece:
        raise chat.ActionError("the clip's base is not a piece.")
    widgets = raw.get("widgets")
    return piece, dict(widgets) if isinstance(widgets, dict) else {}


def _families_of(piece, still):
    """The family a base names, as the rail spells it — so the render is built
    for the node that was sent and not for whatever the rail last said.

    A pre-stage names an arch, and the room can only draw a picture through
    an image arch: H3's still branch is a video generation under its own blob
    (`_rail` says why), so a pre-stage left on it is refused here, in the
    room's words, rather than built into the wrong compiler.
    """
    if not still:
        return {"video_family": piece.get("family")}
    family = registry.STILL_ARCHES.get(piece.get("arch"))
    if family not in registry.IMAGE_FAMILIES:
        raise chat.ActionError(
            "the pre-stage is on MiniMax H3, whose still the room cannot ask "
            "for. Pick an image model on it and ask again.")
    return {"still_family": family}


# ---- the weights ------------------------------------------------------------


def _picked(family, stored, available=None, own=None):
    """The files `family` renders with, as `{slot: filename}`.

    The node's own block (`own`) over this machine's remembered picks over the
    folder listing's own guess — the node's rule, `adoptWeights`, read back: a
    piece says what it rendered on, and memory only fills what it left empty.
    The remembered half is the
    same join `chat.setup_report` shows the room, so a family the room says is
    ready is a family this route renders: a machine that was never asked to
    pick (the family pill moved without a first run, a fresh install with one
    file per slot) still renders on the files it has. Filtered to the slots the
    family actually declares. `settings.clean_weights` stores a block as
    written — a slot id it has never heard of is kept, because what a slot
    *means* is the family's — so a block left behind by another family, or by
    a version of this one with a slot since renamed, would otherwise ride into
    the blob and read as nothing to every reader downstream.
    """
    ids = {slot["id"] for slot in family.get("weights") or []}

    def files(block):
        return {name: value for name, value in (block or {}).items()
                if name in ids and isinstance(value, str) and value.strip()}

    guessed = chat.guess_weights(family, available) if available is not None else {}
    return {**guessed, **files((stored or {}).get(family["id"])), **files(own)}


def _not_ready(family, picked, available, turbo=False):
    """The sentence a family with a required file missing gets, or None.

    The same reading the machine card takes, so what the model was told and what
    the render refuses cannot disagree — the card says a family is not ready and
    this is the refusal if the model asks for it anyway. `turbo` is the rail's
    switch, which moves the answer: with it thrown the Turbo checkpoint is the
    file this render loads, and without this the dry run would pass and
    `render_image.check` would refuse on the queue instead.
    """
    gone = chat.missing_weights(family, picked, available, turbo=turbo)
    if not gone:
        return None
    return (f"{family['label']} cannot render yet: no file is picked for "
            f"{chat.listed(gone)}. Choose {'it' if len(gone) == 1 else 'them'} "
            f"in the weights control and ask again.")


# ---- building the render ----------------------------------------------------


def _node_widgets(node, family, own):
    """Every widget a node's schema declares, at the values the room sent.

    A prompt built by hand carries the whole input list: ComfyUI validates a
    prompt against the schema, and a widget left off is a render that will not
    queue. The values are the schema's own defaults read off the schema — the
    node is the only honest source for what it declares — with the family's
    manifest laid over them, because a static schema can only wear one family's
    numbers and the manifest is where a family says what row it samples on,
    and the node's own widget values (`own`, as the room read them) over both.
    `sampling.py` argues the blob-over-widget split at length; this is the
    headless end of it, and the blob wins there too, so what the row is set
    to on the node is what samples here.

    The seed is among them and is always a widget. `control_after_generate` is
    the frontend's own linked control and there is nothing in a blob for it to
    be, which is why the seed is the one number on this row that never moved —
    and why the room rolls it on the node after a queue, the way the frontend
    does, rather than asking this route to.
    """
    values = {}
    for spec in node.define_schema().inputs:
        name = getattr(spec, "id", None) or getattr(spec, "name", None)
        default = getattr(spec, "default", None)
        if name and default is not None:
            values[name] = default
    for widget in family.get("widgets") or []:
        if widget.get("id") in values and widget.get("default") is not None:
            values[widget["id"]] = widget["default"]
    for name, value in (own or {}).items():
        if name in values and isinstance(value, (str, int, float, bool)):
            values[name] = value
    return values


def _nodes():
    """The two node classes a chat render is built around.

    Imported here rather than at module scope: both pull in ComfyUI, and route
    modules are imported while the server is still registering its routes.
    """
    from .. import creator_node, prestage

    return {"MiniMaxH3PreStage": prestage.MiniMaxH3PreStage,
            "MiniMaxH3Creator": creator_node.MiniMaxH3Creator}


def _build(action, ledger, rail, stored, base, strip=None, cast=None):
    """The blocking half of a render: patch, fill, dry run, build the prompt.

    -> `{"piece": blob, "prompt": one-node prompt}`, or `{"problem": sentence}`.
    A problem is the assistant's next line, verbatim, and is not an error: a
    duration off the frame grid and a checkpoint nobody picked are both ordinary
    things for a model to have asked for, and relaying the compiler's own
    sentence is what lets it say so and try again.

    `base` is `(piece, widgets)` — the chat's own piece as the room assembled
    it (`chat.js renderBase`) and `_base` parsed it, with the rail already
    naming its family; the widgets are the sampler row the room samples on. `strip`
    is the shots the room has joined so far, each with its take — the room's
    state, sent the way the ledger is. `cast` is the piece's subjects as the
    room read them, for a still: a picture has no cast, and a member cited
    in one becomes their picture (`chat.still_piece`). The
    render is that node asked for this prompt in this shape: its stack,
    its turbo switch, its sampler row and its weights are the ones on the
    canvas, and nothing here re-derives any of them. The room's gear is the
    node's own row over the same blob, so there is no second place they could
    have been set.

    The patched blob goes back with the prompt id so the browser can hold it
    without patching a second copy of its own. Two implementations of the same
    patch is exactly the drift this pack keeps writing about, and the server has
    to build the blob anyway to queue it.
    """
    still = action["kind"] == chat.KIND_STILL
    piece_in, widgets_in = base
    family = manifest.describe(rail["still_family"] if still else rail["video_family"])
    available = core_models.available()
    own = (piece_in.get("models") or {}).get(rail["still_arch"]) if still \
        else piece_in.get("models")
    picked = _picked(family, stored, available, own=own)

    # Whether the pre-stage's switch loads the Turbo checkpoint decides whether
    # that is a file this render needs.
    problem = _not_ready(family, picked, available,
                         turbo=still and chat.still_turbo_checkpoint(piece_in))
    if problem:
        return {"problem": problem}

    # What the pure half has to know about this family's pictures, which is the
    # catalog's answer and so the route's to look up. Only for a still: on a
    # clip every handle is a reference or the first frame, and the video
    # families read both.
    if still:
        rail = {**rail, "still_pictures": chat.still_pictures(family, manifest.catalog())}
    node_id, field, piece = chat.piece_of(action, ledger, rail, piece_in, strip, cast)

    if still:
        # Per-arch sub-blocks with one shared precision, which is the shape
        # `render_image.ImageWeights.from_blob` reads and the shape the pre-stage
        # writes: flipping the model pill must not forget the other side's files.
        piece["models"] = {**(piece.get("models") or {}),
                           piece["arch"]: picked,
                           "dtype": (piece.get("models") or {}).get("dtype")
                                    or ((stored or {}).get(family["id"]) or {}).get("dtype")
                                    or "default"}
    else:
        # Flat, and the whole block rather than the filenames alone:
        # `models.Weights.from_blob` reads the precision, the route and the
        # pinned devices out of the same dict. The node's block, with what the
        # machine remembers filling its empty rows.
        remembered = (stored or {}).get(family["id"]) or {}
        piece["models"] = {**remembered, **(piece.get("models") or {}), **picked}
        # Pins merge slot by slot: a request pinning one slot keeps the
        # machine's pins for the others rather than dropping them all.
        devices = {**(remembered.get("devices") or {}),
                   **((piece.get("models") or {}).get("devices") or {})}
        if devices:
            piece["models"]["devices"] = devices

    try:
        if still:
            registry.still(piece["arch"]).compile_still(piece, media.image_size)
        else:
            server_routes.compiled_passes(piece)
    except server_routes.COMPILE_FAILURES as refusal:
        return {"problem": str(refusal)}

    node = _nodes()[node_id]
    widgets = _node_widgets(node, family, widgets_in)
    # The blob last: the schema's own default for that widget is in `widgets`
    # too — every input is, which is the point — and it is the one the render is
    # replacing.
    # Keyed by `chat.NODE`, never by a number: a number is a canvas node's id
    # and ComfyUI would file this render on that node. See `chat.NODE`.
    return {"piece": piece, "node": node_id, "field": field,
            "prompt": {chat.NODE: {"class_type": node_id,
                                   "inputs": {**widgets,
                                              field: json.dumps(piece, indent=2)}}}}


def _no_model(block):
    """The 400 a request with no refiner model gets, or None. Said once."""
    if (block.get("model") or "").strip():
        return None
    if block.get("backend") == "remote":
        return web.json_response({"error":
            "No model chosen. Pick one of the server's models in the "
            "refiner's settings."
        }, status=400)
    return web.json_response({"error":
        "No text encoder chosen. Put a Qwen3-VL or Qwen3.5 text encoder in "
        "models/text_encoders and pick it in the refiner's settings."
    }, status=400)


def _with_caption(action, caption, piece, still):
    """The action with the caption the turn wrote for it, checked, or as it was.

    `chat.validate` reads only what a model may write, and a caption is
    never the model's: the turn's magic pass put it on the action and the
    room sends the action back whole. So it is read here, beside the base
    it has to fit — a caption is one family's format, and a base on another
    family would render it as prose.
    """
    if caption is None:
        return action
    module = _magic_module(piece.get("arch")) if still else None
    if module is None:
        raise chat.ActionError("that action carries a caption, and the still it "
                               "would render on does not read one.")
    tidied = module.tidy(caption) if isinstance(caption, str) else None
    if tidied is None:
        raise chat.ActionError("that action's caption is not a JSON object.")
    return {**action, "caption": tidied}


@PromptServer.instance.routes.post("/continuity/chat/render")
@same_origin
async def chat_render(request):
    """Render what the model asked for.

    -> `{"result": {prompt_id, piece}}` once the render is on the queue, or
    `{"result": {problem}}` when it cannot be — the envelope `queue.run()`
    reads, the same one the turn answers in.

    An ordinary queue item: Cancel reaches it, the progress bar is the real one,
    a render queued from the canvas ahead of it goes first, and what comes out
    is a file in the output folder with its blob in its metadata — citable from
    the picker like anything else this pack makes.

    The model's prompt is the render's prompt. Nothing rewrites it on the way
    to the queue: how much the model writes is the rail's verbosity dial, read
    on the turn, and a family's own way of prompting is a skill appended there.
    The one exception is also decided on the turn — a caption the family's
    magic prompt wrote (`_magic`) — and arrives here already written.
    """
    try:
        body = await request.json()
    except ValueError:
        return web.json_response({"error": "the request body was not JSON"}, status=400)

    strip = [c for c in body.get("strip") or [] if isinstance(c, dict)]
    # The piece's shelf and cast, off the blob the room sends beside the
    # base: the handles and the names an action may cite beyond the ledger.
    # For a clip the piece itself is the authority and the base carries the
    # same blob; for a still they are what `still_piece` expands.
    ledger, cast = _with_piece(body)
    try:
        action = chat.validate(body.get("action"), ledger,
                               strip=[c.get(chat.STRIP_KEY) for c in strip],
                               cast=[m.get("name") for m in cast])
        if action["act"] != chat.ACT_RENDER:
            raise chat.ActionError("that action says nothing to render")
        # The node under the room, and the rail naming its family — the render
        # is built for the node that was sent, whatever the rail last said.
        still = action["kind"] == chat.KIND_STILL
        base = _base(body.get("base"), still)
        rail = _rail({**(body.get("rail") or {}), **_families_of(base[0], still)})
        action = _with_caption(action, (body.get("action") or {}).get("caption"), base[0], still)
    except chat.ActionError as problem:
        return web.json_response({"error": str(problem)}, status=400)

    # Everything below this line touches disk — the settings file, the model
    # folders, the compiler's size lookups — and this loop is also the prompt
    # queue and the websocket.
    loop = asyncio.get_running_loop()
    try:
        built = await loop.run_in_executor(
            None, lambda: _build(action, ledger, rail,
                                 settings.load().get("weights") or {}, base,
                                 strip, cast))
    except chat.ActionError as problem:
        return web.json_response({"error": str(problem)}, status=400)
    except Exception as problem:  # noqa: BLE001
        return web.json_response({"error": f"{type(problem).__name__}: {problem}"},
                                 status=500)
    if "problem" in built:
        return web.json_response({"result": built})

    try:
        prompt_id = await jobs.enqueue(built["prompt"], body.get("client_id"))
    except jobs.JobError as problem:
        return web.json_response({"error": str(problem)}, status=500)
    return web.json_response({"result": {"prompt_id": prompt_id, "piece": built["piece"]}})


# ---- the turn ---------------------------------------------------------------


def _skill(block):
    """The user's own instructions for this room, or "". Raises `RefineError`.

    Only the `add` mode. A `.skill` set to *replace* the built-in prompting
    takes the whole system prompt over, and this room's system prompt is the
    contract that turns an answer into a render — replaced, there would be
    nothing to parse and nothing to queue. So it is refused by name rather than
    quietly downgraded to `add`, which would be running a different thing than
    the switch says.
    """
    name = str(block.get("skill") or "").strip()
    if not name:
        return ""
    skill = refine_skill.load(name)
    if (block.get("skill_mode") or skill["mode"]) != refine_skill.ADD:
        raise refine.RefineError(
            f"'{name}' is set to replace the built-in prompting, and the chat "
            f"cannot run it that way — its reply contract is what turns an "
            f"answer into a render. Set it to add to the built-in prompting, "
            f"or pick no skill here."
        )
    return refine_skill.instructions(skill)


def _ask(block, system, message):
    """One generation on whichever backend the room is pointed at.

    The one place a reply is produced, which is where a native tool call will
    land when the runtime reports it: the same schema as the one tool, with
    `parallel_tool_calls` off, and this fenced form as the fallback. Until then
    both backends get the fence.

    `prefill=""` rather than the harness's opening brace. The refiner's replies
    are a bare JSON object and beginning the assistant's turn inside it is what
    stops a small model answering the request instead of expanding it; here the
    reply is a line of plan *and then* an object, so a prefilled `{` would cut
    the plan off before it was written. `json_object` finds the brace either way.
    """
    ask, _look = refine_routes._backend(block)
    return ask(
        block.get("model") or "",
        system, message, [],
        # Choosing an action is a decision, not ideation: the default leans cold
        # so that "another one, bluer" stays a render rather than becoming a
        # conversation about one. The dial is still the user's.
        temperature=block.get("temperature", 0.3),
        seed=block.get("seed", -1),
        # The rail's own budget, not the refiner's `max_tokens` on the block:
        # a turn is a plan line and one object, and the in-process backend
        # reserves a KV cache of the prompt plus this.
        max_tokens=chat.reply_tokens(block.get("reply_tokens")),
        prefill="",
    )


def _magic_module(arch):
    """The family's magic-prompt module for a still arch, or None where the
    family's manifest does not say it reads a caption one can write."""
    family = registry.STILL_ARCHES.get(arch)
    if not family or not (manifest.describe(family).get("prompt") or {}).get("magic"):
        return None
    return importlib.import_module(f"..families.{family}.magic", __package__)


def _magic(block, action, ledger, rail, cast):
    """The caption a family's own magic prompt writes from this still's prose,
    or None where the still is not drawn on a family that has one.

    A second generation on the same backend and model as the turn, inside the
    same job: the room asked one question and waits for one answer. It is
    asked alone — the family's instruction as the whole system prompt, the
    prose as the whole message — because that is how the instruction was
    written to be run, and at the refiner's reply budget rather than the
    rail's, since a populated caption runs to thousands of tokens where a turn
    runs to hundreds. The prose is the cast expanded, `chat.still_prose`: the
    words the render would have read.

    One re-ask on a caption that will not do, quoting why, as the turn gets.
    A second failure refuses the turn in that sentence rather than rendering
    the plain wrap the switch was thrown to replace.

    The rail is the turn's own. A family with a magic prompt is sent no
    picture and is never an edit family, so a still drawn on one is drawn on
    the rail's still family and the rail already describes it.
    """
    module = _magic_module(action.get("arch"))
    if module is None:
        return None
    try:
        prose = chat.still_prose(action, ledger, rail, cast)
    except chat.ActionError:
        # The render refuses this still in these same words, under the
        # model's own line; there is no caption to write for it.
        return None
    ask, _look = refine_routes._backend(block)
    keep = bool(block.get("magic_bboxes"))
    message = module.user_message(prose, chat.still_aspect(action, rail))

    def once(text):
        return ask(block.get("model") or "", module.system_prompt(), text, [],
                   temperature=module.TEMPERATURE, seed=block.get("seed", -1),
                   max_tokens=refine.reply_tokens(block.get("max_tokens")))

    raw = once(message)
    try:
        return module.caption(raw, prose, keep)
    except module.MagicError as problem:
        log.debug("magic prompt re-asked: %s", problem)
        raw = once(module.reask(message, raw, problem))
    try:
        return module.caption(raw, prose, keep)
    except module.MagicError as problem:
        # Where a broken answer broke is for the person, never the log: the
        # reply is a piece's prompt (`_run`'s rule).
        where = f" It broke at: {problem.where}" if problem.where else ""
        raise chat.ActionError(
            f"the magic prompt could not write a caption twice: {problem}.{where}") from problem


def _with_piece(body):
    """The ledger as the room sent it, and the piece's cast.

    `body["piece"]` is the chat's own piece — the cast the conversation has
    brought in and the pool their files are on — as a dict or as JSON. Only
    the cast is read off it: the model is told who is cast and cites them by
    name, and the ledger is the room's alone. Nothing on the canvas is in
    either.
    """
    piece = body.get("piece")
    if isinstance(piece, str):
        try:
            piece = json.loads(piece)
        except ValueError:
            piece = None
    piece = piece if isinstance(piece, dict) else {}
    cast = chat.cast_entries(piece)
    # Which family each member's mod files are for, off their headers — the
    # route has the disk, the pure half does not. A file that will not read
    # is left unnamed and is nobody's picture.
    handles = {}
    for owner in [piece, *(piece.get("segments") or [])]:
        for asset in (owner.get("assets") or []) if isinstance(owner, dict) else []:
            if isinstance(asset, dict) and refmod.is_mod(asset.get("filename")):
                handles[str(asset.get("handle"))] = asset["filename"]
    for member in cast:
        spaces = {}
        for handle in member.get("from") or []:
            if handle in handles:
                try:
                    spaces[handle] = refmod.header(refmod.resolve(handles[handle]))["space"]
                except refmod.RefModError:
                    continue
        if spaces:
            member["spaces"] = spaces
    return list(body.get("ledger") or []), cast


def _last_user(messages):
    """The message this turn is answering — the newest user turn, or ""."""
    for message in reversed(messages or []):
        if isinstance(message, dict) and message.get("role") == "user":
            return str(message.get("text") or "")
    return ""


def _run(body):
    """The blocking half of a turn: build the context, ask, judge, maybe re-ask.

    -> `{say, action?, raw, reask?}`. `raw` is the reply the answer came out of
    and `reask` is the sentence that was quoted when there were two, so the room
    can show what happened rather than only what survived.
    """
    block = body.get("settings") or {}
    messages = body.get("messages") or []
    rail = _rail(block)
    # The room's strip and the piece's shelf and cast, as the model is told
    # them: the shots joined so far as `{handle, seconds}`, the shelf's files
    # as ledger lines beside the room's own, and the members off the node's
    # blob. The validator is given the same handles and names, so an "after"
    # or an "@anna" is judged against exactly what was shown.
    strip = [c for c in body.get("strip") or [] if isinstance(c, dict) and c.get("handle")]
    ledger, cast = _with_piece(body)
    on_strip = [c["handle"] for c in strip]
    names = [m["name"] for m in cast]

    rail, card = _stamp_rail(block)
    # The rail's verbosity dial rides in the same block as the skill: both are
    # about how the model writes, and `chat.system_prompt` places them.
    edits = chat.changes_pictures(rail)
    system = chat.system_prompt(_skill(block), verbosity=block.get("verbosity"),
                                edits=edits)
    message = chat.context(messages, ledger, card, strip=strip, cast=cast, edits=edits)
    asked = _last_user(messages)

    raw = _ask(block, system, message)
    verdict = chat.judge(raw, ledger, asked, strip=on_strip, cast=names)
    quoted = None
    if verdict["act"] == "reask":
        quoted = verdict["sentence"]
        # The reply itself is never logged: the room carries it as `raw`, and
        # the terminal is not the place for a piece's prompt. Only the
        # sentence the validator refused is noted, at debug, for a turn that
        # reads as the model declining twice.
        log.debug("chat turn re-asked: %s", quoted)
        raw = _ask(block, system, chat.reask(message, raw, quoted))
        verdict = chat.judge(raw, ledger, asked, second=True, strip=on_strip, cast=names)
        if verdict["act"] != chat.ACT_RENDER:
            log.debug("chat turn re-ask did not render; shown as prose")

    out = {"say": verdict.get("say") or "", "raw": raw}
    if quoted:
        out["reask"] = quoted
    if verdict["act"] == chat.ACT_RENDER:
        out["action"] = _stamp(block, verdict["action"], ledger, rail, cast)
    return out


def _stamp_rail(block):
    """The rail an action is stamped against, and the machine card. -> `(rail, card)`.

    Whether the pre-stage's switch loads the Turbo checkpoint is read off its
    blob by the room and sent as one flag, since the card only needs to know
    which files a still would load. The rail comes back carrying what
    `still_arch_for` reads: the still family's answer about pictures, and the
    arch a picture it cannot read goes to.
    """
    rail = _rail(block)
    known = machine(rail["still_family"], rail["video_family"],
                    settings.load().get("weights") or {},
                    turbo=bool(block.get("still_turbo_checkpoint")),
                    edit=rail.get("edit_family"))
    rail = {**rail, "still_pictures": known["still_pictures"],
            "edit_family": known["edit_family"],
            "edit_arch": _arch_of(known["edit_family"]) if known["edit_family"] else None}
    return rail, known["card"]


def _owes_caption(block, action, held):
    """Whether stamping `action` means writing a caption — a second generation.

    Only with the magic switch on, only on a family that has a magic prompt,
    and not when `held` (the action as it was last stamped) already carries a
    caption written for this same arch: a retake reads the caption its first
    take read, so "another one" is the same picture asked for again.
    """
    if not block.get("magic") or _magic_module(action.get("arch")) is None:
        return False
    return not (held.get("arch") == action.get("arch") and held.get("caption"))


def _stamp(block, action, ledger, rail, cast, held=None):
    """The harness's half of a render action, over the model's.

    Which image arch draws a still — the rail's, or its edit arch for a
    picture the rail's family cannot read — and the caption the family's magic
    prompt writes for it. Decided here and not in the room: the room builds
    the base for this arch (`chat.js renderBase`) and `chat/render` reads the
    family off that base, so the decision is carried to the queue, not
    re-derived on the way.

    Carried, but not frozen. The model chose *what* to render; which weights
    draw it is the rail's, and the rail can change between a turn and its
    retake — a still made on Krea, the pill moved to Qwen, Retake pressed.
    So `chat/again` stamps the same action again against the rail as it is
    now, and `held` is the action as it was last stamped, whose caption is
    kept where the arch did not move (`_owes_caption`). A caption on an arch
    that no longer reads one is dropped rather than refused at the render.
    """
    if action["kind"] != chat.KIND_STILL:
        return action
    held = held or {}
    action = {key: value for key, value in action.items() if key != "caption"}
    action["arch"] = chat.still_arch_for(action, ledger, rail, cast)
    if not block.get("magic") or _magic_module(action["arch"]) is None:
        return action
    caption = (held["caption"] if not _owes_caption(block, action, held)
               else _magic(block, action, ledger, rail, cast))
    return {**action, "caption": caption} if caption else action


def _again(body, write=True):
    """A render action stamped again against the rail as sent. -> the action.

    `write=False` stamps without the model and answers None where a caption
    would have to be written, so the route can do the cheap part inline and
    send only a turn that needs a generation to the backend.
    """
    block = body.get("settings") or {}
    held = body.get("action") if isinstance(body.get("action"), dict) else {}
    strip = [c for c in body.get("strip") or [] if isinstance(c, dict) and c.get("handle")]
    ledger, cast = _with_piece(body)
    action = chat.validate(held, ledger, strip=[c["handle"] for c in strip],
                           cast=[m["name"] for m in cast])
    if action["act"] != chat.ACT_RENDER:
        raise chat.ActionError("that action says nothing to render")
    rail, _card = _stamp_rail(block)
    if not write and action["kind"] == chat.KIND_STILL:
        arch = chat.still_arch_for(action, ledger, rail, cast)
        if _owes_caption(block, {**action, "arch": arch}, held):
            return None
    return _stamp(block, action, ledger, rail, cast, held)


def _run_job(body):
    """One turn, on the queue. See `creator/jobs.py`.

    The pack's own three become a message about the request, the way the refine
    job's do: the room puts the sentence in the conversation either way, and
    anything else is a bug reported as one.
    """
    try:
        return _run(body)
    except (refine.RefineError, chat.ActionError) as problem:
        raise jobs.JobError(str(problem)) from problem


jobs.register("chat", _run_job)


def _again_job(body):
    """`_again` with a caption to write, on the queue — `_run_job`'s terms."""
    try:
        return {"action": _again(body)}
    except (refine.RefineError, chat.ActionError) as problem:
        raise jobs.JobError(str(problem)) from problem


jobs.register("chat_again", _again_job)


@PromptServer.instance.routes.post("/continuity/chat/turn")
@same_origin
async def chat_turn(request):
    """Ask the model what to do about one message. -> the turn, or a `prompt_id`.

    Stateless: the browser sends the trimmed history, the ledger and the rail
    every time, and this builds one turn out of them. The remote backend answers
    `{"answer_id": id}` and puts the turn on `mmc_answer`; the in-process one is
    GPU work and rides the queue, answering `{"prompt_id": id}` and putting the
    same turn on `executed`. A local chat waits behind a running render — that
    is the cost of one GPU, and the room shows the queue position rather than
    pretending otherwise.
    """
    try:
        body = await request.json()
    except ValueError:
        return web.json_response({"error": "the request body was not JSON"}, status=400)

    block = body.get("settings") or {}
    remote = block.get("backend") == "remote"
    refused = _no_model(block)
    if refused is not None:
        return refused

    if remote:
        # Off the queue but not inside this request: a turn can outlast the
        # frontend's fetch timeout (issue #120). The turn arrives on the socket
        # as `mmc_answer`, which `queue.run()` waits for as it waits for the
        # queued path's `executed`, so the room has one call site and one
        # shape whichever backend it is pointed at.
        answer_id = jobs.answer_later(lambda: _run(body), body.get("client_id"),
                                      (refine.RefineError, chat.ActionError))
        return web.json_response({"answer_id": answer_id})

    try:
        prompt_id = await jobs.submit("chat", body, body.get("client_id"))
    except jobs.JobError as problem:
        return web.json_response({"error": str(problem)}, status=500)
    return web.json_response({"prompt_id": prompt_id})


@PromptServer.instance.routes.post("/continuity/chat/again")
@same_origin
async def chat_again(request):
    """An action a card already rendered, stamped for the rail as it is now.

    -> `{"result": {action}}`, or an `answer_id` or `prompt_id` whose
    `mmc_answer` or `executed` carries the same. What Retake and Try again ask
    before they queue: see `_stamp`. Most of the time nothing has to be
    generated and the answer is inline, off the loop for the disk reads; only a caption the magic prompt must write goes
    to the backend, remote off the queue and local on it, as a turn does.
    """
    try:
        body = await request.json()
    except ValueError:
        return web.json_response({"error": "the request body was not JSON"}, status=400)

    loop = asyncio.get_running_loop()
    block = body.get("settings") or {}
    remote = block.get("backend") == "remote"
    try:
        action = await loop.run_in_executor(None, _again, body, False)
        if action is None:
            refused = _no_model(block)
            if refused is not None:
                return refused
            if remote:
                # The caption is a call to the backend, which can outlast the
                # request as a turn can, so it is answered the same way.
                answer_id = jobs.answer_later(
                    lambda: {"action": _again(body)}, body.get("client_id"),
                    (refine.RefineError, chat.ActionError))
                return web.json_response({"answer_id": answer_id})
    except (refine.RefineError, chat.ActionError) as problem:
        return web.json_response({"error": str(problem)}, status=400)
    except Exception as problem:  # noqa: BLE001
        return web.json_response({"error": f"{type(problem).__name__}: {problem}"},
                                 status=500)
    if action is not None:
        return web.json_response({"result": {"action": action}})

    try:
        prompt_id = await jobs.submit("chat_again", body, body.get("client_id"))
    except jobs.JobError as problem:
        return web.json_response({"error": str(problem)}, status=500)
    return web.json_response({"prompt_id": prompt_id})


# ---- the first run ----------------------------------------------------------


def _local_refiner(names):
    """The text encoder the room would think with, out of the folder listing.

    The kinds ComfyUI can generate from are named in `refine_local.SUPPORTED`,
    smallest first; a file whose name says one of them is the answer, in that
    order, because the room's turn is a queue slot on the card the
    render wants. Nothing recognised means the person is offered the list.
    """
    for wanted in refine_local.SUPPORTED:
        needle = wanted.replace("_", "")
        for name in names:
            if needle in name.lower().replace("_", "").replace("-", ""):
                return name
    return ""


def _setup():
    """Everything the room's first three questions are asked against.

    One walk of the model folders and one knock on each loopback port, joined
    with what this machine has already picked — the same three payloads the
    machine card is a join of, read once and handed to the browser whole so
    the questions can be answered without a request per chip.
    """
    available = core_models.available()
    local = refine_local.list_models()
    stored = refine_remote.status()
    servers = refine_remote.probe_local()
    # The server somebody already set up, listed by the same shape as the
    # loopback ones so the room can offer it as a chip — but only when it
    # answers, and never a second time when it *is* one of the loopback ones.
    if stored.get("url") and stored["url"] not in {entry["url"] for entry in servers}:
        try:
            servers.append({"name": "", "url": stored["url"],
                            "models": refine_remote.list_models(
                                timeout=refine_remote.PROBE_TIMEOUT)})
        except refine.RefineError:
            pass
    return {
        "refiner": {
            "local": {"models": local, "model": _local_refiner(local)},
            "servers": servers,
            "stored": stored,
        },
        "families": chat.setup_report(manifest.catalog(), available,
                                      settings.load().get("weights") or {}),
    }


@PromptServer.instance.routes.get("/continuity/chat/setup")
async def chat_setup(request):
    """What the room's first run has to go on. See `_setup`.

    Off the event loop: it walks the model directories and knocks on two ports.
    """
    loop = asyncio.get_running_loop()
    try:
        return web.json_response(await loop.run_in_executor(None, _setup))
    except Exception as problem:  # noqa: BLE001
        return web.json_response({"error": f"{type(problem).__name__}: {problem}"},
                                 status=500)

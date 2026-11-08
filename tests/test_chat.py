"""The chat surface's contract: what the model may answer, and what it becomes.

    python tests/test_chat.py

Runs standalone — no torch, no ComfyUI, no network, no model. Everything under
test is `creator/chat.py`, which is pure for exactly this reason: the whole
protocol between a small local model and this pack's compiler is ordinary data,
and the failures it has to survive are the ones nobody can reproduce on demand.

Four things are pinned here, and each of them is a decision the spec argues for
rather than an implementation detail.

**The parse forgives transport and the validation forgives nothing.** A 4B model
leaks a `<think>` block, fences its object, writes a sentence in front of it, or
drops the fence entirely — none of those is a disagreement about the contract,
so all four have to come back as the same action. What the object *holds* is the
opposite: every refusal is a sentence naming the field, because that sentence is
quoted straight back to the model on the one re-ask and shown to a person if the
second attempt fails too.

**The protocol is two calls, never three.** A reply that will not validate earns
one re-ask; a `say` in answer to "make me a picture" earns one re-ask; a second
failure is the model's own prose in a bubble. A third round trip would be a room
that hangs on a model having a bad day.

**The card is the join nothing else makes.** Manifests, the files on disk and
this machine's picks each answer a third of "can I render this now", and a
family with a required file missing has to say so in the card so the model can
say so instead of trying.

**The blob patch is the only resolution there is.** `from` becomes references in
the order cited, a still cited by a clip is that clip's first frame, and a
handle the ledger has never heard of is refused before anything reaches the
compiler.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import layout  # noqa: E402
from harness import FAILURES, check, passed  # noqa: E402

chat = layout.load("prompting", "chat").chat


def refuses(label, call, *fragments):
    """The call raises an `ActionError` whose sentence carries every fragment."""
    try:
        call()
    except chat.ActionError as problem:
        for fragment in fragments:
            if fragment not in str(problem):
                FAILURES.append(f"{label}: said {str(problem)!r}, want {fragment!r} in it")
    except Exception as other:  # noqa: BLE001
        FAILURES.append(f"{label}: raised {other!r}, want an ActionError")
    else:
        FAILURES.append(f"{label}: did not refuse")


LEDGER = [
    {"handle": "img-1", "kind": "still", "aspect": "16:9", "turn": 1,
     "filename": "continuity/chat/fox.png",
     "text": "a red fox on a snowy ridge at dusk, low sun behind"},
    {"handle": "vid-1", "kind": "clip", "aspect": "16:9", "turn": 2,
     "filename": "continuity/chat/fox.mp4", "text": "the fox looks up"},
]

RAIL = {"still_family": "krea2", "still_arch": "krea2", "video_family": "h3",
        "aspect": "16:9", "still_edge": 1024, "video_edge": 768}


# ---- the parse forgives transport -------------------------------------------
#
# Four shapes of the same answer. Every one of these has been seen off a small
# model, and none of them is the model disagreeing about what to do.

ACTION = '{"act": "render", "kind": "still", "prompt": "a fox in the snow"}'
SHAPES = {
    "a plan line and a fence": f"A picture, nothing to reference.\n```json\n{ACTION}\n```",
    "a leaked think block": f"<think>\nthey want a picture\n</think>\nA picture.\n```\n{ACTION}\n```",
    "a bare object": ACTION,
    "a sentence in front of it": f"Sure, here is the action: {ACTION}",
}
for label, reply in SHAPES.items():
    _, action = chat.read(reply, LEDGER)
    check(f"{label} parses to the same action",
          (action["act"], action["kind"], action["prompt"]),
          ("render", "still", "a fox in the snow"))

check("the plan line is read back off the reply",
      chat.plan_of(SHAPES["a plan line and a fence"]),
      "A picture, nothing to reference.")
check("a reply that is all object has no plan line", chat.plan_of(ACTION), "")
check("the think block is not mistaken for one",
      chat.plan_of(SHAPES["a leaked think block"]), "A picture.")

refuses("prose with no object at all is a re-ask, not a crash",
        lambda: chat.read("I could make that for you if you like!", LEDGER),
        "no JSON object", "``` fence")


# ---- the validation forgives nothing ----------------------------------------
#
# One case per field, and each sentence has to name the field it is about: it is
# read by a model that cannot see this file and then by a person who cannot
# either.

refuses("an unknown act names the field",
        lambda: chat.validate({"act": "generate"}, LEDGER), '"act"', '"say" or "render"')
refuses("a missing act says what arrived",
        lambda: chat.validate({"kind": "still"}, LEDGER), '"act"', "nothing")
refuses("a render with no kind names the field",
        lambda: chat.validate({"act": "render", "prompt": "a fox"}, LEDGER),
        '"kind"', '"still" or "video"')
refuses("a render with no prompt says what a prompt is",
        lambda: chat.validate({"act": "render", "kind": "still"}, LEDGER),
        '"prompt"', "prompt box")
refuses("a say with nothing said is a turn with nothing in it",
        lambda: chat.validate({"act": "say", "say": "  "}, LEDGER), '"say"')
refuses("a say that is not text names the field",
        lambda: chat.validate({"act": "say", "say": {"text": "hi"}}, LEDGER), '"say"')
refuses("a from that is not a list names the field",
        lambda: chat.validate({"act": "render", "kind": "still", "prompt": "a fox",
                               "from": {"handle": "img-1"}}, LEDGER),
        '"from"', "list of handles")
refuses("seconds that is not a number names the field",
        lambda: chat.validate({"act": "render", "kind": "video", "prompt": "a fox",
                               "seconds": "a while"}, LEDGER),
        '"seconds"', "number of seconds")
refuses("an aspect that is not a name names the field",
        lambda: chat.validate({"act": "render", "kind": "still", "prompt": "a fox",
                               "aspect": [16, 9]}, LEDGER),
        '"aspect"', '"16:9"')

# The one validation that is about data rather than shape: a handle the ledger
# never issued is a reference to a file that does not exist, and it is refused
# here rather than three modules later at the compiler — with the handles that
# *would* have worked, since the model is about to be asked again.
refuses("an unknown handle is refused with the ones that exist",
        lambda: chat.validate({"act": "render", "kind": "still", "prompt": "a fox",
                               "from": ["img-9"]}, LEDGER),
        "@img-9", "img-1, vid-1")
refuses("and with an empty ledger it says so instead",
        lambda: chat.validate({"act": "render", "kind": "still", "prompt": "a fox",
                               "from": ["img-1"]}, []),
        "nothing has been made yet")

# Two spellings are read rather than refused. Both are what a model that has
# just read a ledger full of `@img-1` lines does, and neither leaves any doubt
# about what was meant — the point of the strictness above is fields whose
# meaning is actually unclear.
check("a lone handle is read as a list of one",
      chat.validate({"act": "render", "kind": "still", "prompt": "a fox",
                     "from": "img-1"}, LEDGER)["from"], ["img-1"])
check("a handle written with its @ is the same handle",
      chat.validate({"act": "render", "kind": "still", "prompt": "a fox",
                     "from": ["@img-1", "img-1"]}, LEDGER)["from"], ["img-1"])

# The slips a model makes writing a handle it has just read are read, not
# refused: a 27B wrote `pic--1:end` for the ledger's `pic-1` on its first try,
# and a refusal there is a second generation spent on a correction whose
# answer was never in doubt.
check("a doubled hyphen in a citation is the handle it meant",
      chat.validate({"act": "render", "kind": "video", "prompt": "she looks up",
                     "from": ["img--1:start"]}, LEDGER)["from"], ["img-1:start"])
check("and so is an underscore, a space or a capital",
      [chat.tidy_handle(t) for t in ("Img_1", "img - 1 : style", "@IMG-1")],
      ["img-1", "img-1:style", "img-1"])
check("the same slip in the prose is the ledger's handle, not a stranger's",
      chat.validate({"act": "render", "kind": "video", "prompt": "ends on @img--1 exactly",
                     "from": []}, LEDGER)["prompt"], "ends on @img-1 exactly")
check("a word that is not a handle is left for the validator to name",
      chat.tidy_handle("nobody"), "nobody")

check("a valid say carries its whole reply",
      chat.validate({"act": "say", "say": "The seed picks the noise."}, LEDGER),
      {"act": "say", "kind": None, "prompt": "", "from": [], "seconds": None,
       "aspect": None, "say": "The seed picks the noise.",
       "after": None, "replaces": None})


# ---- the one re-ask ---------------------------------------------------------

bad = chat.judge("I would be happy to help!", LEDGER, "a fox in the snow")
check("an unusable reply is a re-ask", bad["act"], "reask")
check("and the sentence quoted back is the validator's",
      "no JSON object" in bad["sentence"], True)

good = chat.judge(SHAPES["a plan line and a fence"], LEDGER, "a fox in the snow")
check("a usable render comes back as one", good["act"], "render")
check("with the plan line standing in for an unwritten say",
      good["say"], "A picture, nothing to reference.")

# The nudge. ChatGPT's contract is "do not ask for confirmation, just render",
# and a small model offering to generate something is the commonest way this
# surface disappoints — so a `say` in answer to a plain request buys one more go.
asked = chat.judge('{"act": "say", "say": "Would you like me to make that?"}',
                   LEDGER, "make me a picture of a fox")
check("a say where a render was expected is a re-ask", asked["act"], "reask")
check("and says so rather than quoting a field", asked["sentence"], chat.NUDGE)

chatted = chat.judge('{"act": "say", "say": "It picks the starting noise."}',
                     LEDGER, "what does the seed do?")
check("a say in answer to a question is just a say", chatted["act"], "say")

check("the nudge reads a request", chat.asks_for_render("now a clip of it"), True)
check("and its plural", chat.asks_for_render("can I have two pictures"), True)
check("and two-word phrases in it", chat.asks_for_render("make me something nice"), True)
# Whole words only: the list only ever *adds* a model call, so a word that fires
# on ordinary prose costs a wasted generation and hands the person a correction
# demanding a render they never asked for.
check("but not a word that merely contains one",
      chat.asks_for_render("the videographer was late"), False)
check("and not a turn that is only conversation",
      chat.asks_for_render("that came out lovely, thank you"), False)
# Two words were dropped from the list for being commoner in conversation than
# in a request: "still" is an adverb far more often than it is a noun, and
# "shot" is as much praise for one as a request for one. Both pushed a model
# that had correctly answered a question into a re-ask demanding a render.
check("an adverb is not a request for a picture",
      chat.asks_for_render("why is it still dark?"), False)
check("and praise for a shot is not a request for another",
      chat.asks_for_render("that shot of yours was lovely"), False)
check("what the list holds is written down, so dropping from it is deliberate",
      chat.RENDER_WORDS,
      ("picture", "image", "clip", "video", "render", "draw", "make me", "show me"))

# Second time round nothing is re-asked: the model has now been told exactly
# what was wrong and answered anyway, and a person reading its prose is more
# use than a third round trip.
fell_back = chat.judge("<think>hmm</think>I think I need more detail first.",
                       LEDGER, "make me a picture", second=True)
check("a second failure is a say", fell_back["act"], "say")
check("carrying the model's own words, without its reasoning",
      fell_back["say"], "I think I need more detail first.")
check("a nudged say is taken as written the second time",
      chat.judge('{"act": "say", "say": "I cannot do that."}', LEDGER,
                 "make me a picture", second=True)["act"], "say")

quoted = chat.reask("THE CONVERSATION\nuser: a fox", "not JSON", "your reply had no JSON")
check("the re-ask carries the original message", "user: a fox" in quoted, True)
check("what the model wrote", "not JSON" in quoted, True)
check("and why it could not be used", "your reply had no JSON" in quoted, True)
# The whole reply, object included: the fault is nearly always a field in the
# object, and a model corrected about a field it cannot see is guessing.
fenced = 'Opening on it.\n```json\n{"act": "render", "from": ["img--1"]}\n```'
quoted = chat.reask("user: a fox", "<think>hmm</think>" + fenced, '"from" is wrong')
check("the re-ask shows the model its own object", '"from": ["img--1"]' in quoted, True)
check("without its reasoning", "hmm" in quoted, False)


# ---- the machine card -------------------------------------------------------
#
# Fixtures rather than this install's real catalog: what is under test is the
# join, and a card that says "ready" only on a machine with 40 GB of weights on
# it would be a test that passes by being unrunnable.

CATALOG = {"families": [
    {"id": "krea2", "label": "Krea 2", "produces": ["still"],
     "weights": [
         {"id": "model", "folder": "diffusion_models", "title": "the checkpoint",
          "loads": True, "routed": False},
         {"id": "turbo_model", "folder": "diffusion_models",
          "title": "the Turbo checkpoint", "loads": True, "routed": False},
         {"id": "clip", "folder": "text_encoders", "title": "the text encoder",
          "loads": True, "routed": False},
         {"id": "vae", "folder": "vae", "title": "the VAE",
          "loads": True, "routed": False},
     ],
     "canvas": {"aspects": {"16:9": 1.77, "1:1": 1.0, "9:16": 0.56}},
     # Krea 2 as it really is: it reads references, but only through an adapter
     # in the pre-stage's LoRA stack, which this room has no way to fill.
     "capabilities": {"refs": {"needs_lora": True}}, "prompt": {"max_refs": 3}},
    {"id": "qwenedit", "label": "Qwen Image Edit", "produces": ["still"],
     "weights": [
         {"id": "model", "folder": "diffusion_models", "title": "the checkpoint",
          "loads": True, "routed": False},
         {"id": "clip", "folder": "text_encoders", "title": "the text encoder",
          "loads": True, "routed": False},
         {"id": "vae", "folder": "vae", "title": "the VAE",
          "loads": True, "routed": False},
     ],
     "canvas": {"aspects": {"16:9": 1.77, "1:1": 1.0, "9:16": 0.56}},
     "capabilities": {"refs": {"needs_lora": False, "edits_first": True}},
     "prompt": {"max_refs": 3}},
    {"id": "h3", "label": "MiniMax H3", "produces": ["still", "video"],
     "weights": [
         {"id": "fl2va", "folder": "diffusion_models", "title": "the FL2VA checkpoint",
          "loads": True, "routed": True},
         {"id": "ref2va", "folder": "diffusion_models", "title": "the Ref2VA checkpoint",
          "loads": True, "routed": True},
         {"id": "clip", "folder": "text_encoders", "title": "the text encoder",
          "loads": True, "routed": False},
         {"id": "vae", "folder": "vae", "title": "the video VAE",
          "loads": True, "routed": False},
         {"id": "audio_vae", "folder": "vae", "title": "the audio VAE",
          "loads": True, "routed": False},
         {"id": "sam3", "folder": "checkpoints", "title": "the face detector",
          "loads": False, "routed": False},
         {"id": "upscaler", "folder": "upscale_models", "title": "the x2 upscaler",
          "loads": True, "routed": False, "required": False},
     ],
     "canvas": {"aspects": {"16:9": 1.77, "1:1": 1.0, "9:16": 0.56},
                "fps": {"value": 24, "fixed": True},
                "frames": {"step": 17, "offset": 5, "trained_min": 124,
                           "trained_max": 362, "min_seconds": 1, "max_seconds": 60}},
     # A video family declares its caps in a reference block of its own rather
     # than beside the prompt, which is the other spelling `ref_limit` reads.
     "reference": {"max": {"image": 9, "video": 3, "audio": 3, "files": 12}},
     "capabilities": {"audio": {"supplied": True}}, "prompt": {}},
]}

KREA2, QWENEDIT, H3 = CATALOG["families"]
CATALOG_NO_EDIT = {"families": [KREA2, H3]}

ON_DISK = {"by_folder": {
    "diffusion_models": ["krea2.safetensors", "h3_fl2va.safetensors",
                         "qie.safetensors"],
    "text_encoders": ["qwen.safetensors", "minimax.safetensors"],
    "vae": ["krea2_vae.safetensors", "h3_vae.safetensors", "h3_audio.safetensors"],
    "checkpoints": [], "upscale_models": [],
}}

READY = {
    "krea2": {"model": "krea2.safetensors", "clip": "qwen.safetensors",
              "vae": "krea2_vae.safetensors"},
    "qwenedit": {"model": "qie.safetensors", "clip": "qwen.safetensors",
                 "vae": "krea2_vae.safetensors"},
    "h3": {"fl2va": "h3_fl2va.safetensors", "clip": "minimax.safetensors",
           "vae": "h3_vae.safetensors", "audio_vae": "h3_audio.safetensors"},
}

card = chat.machine_card("krea2", "h3", CATALOG, ON_DISK, READY)
check("a machine that is set up says nothing about being ready",
      "not ready" in card, False)
check("the card names what each kind is", '"still" is Krea 2' in card, True)
check("and that a clip carries its own sound", "with its own sound" in card, True)
check("the duration range is the family's canvas",
      "1 to 60 seconds" in card and "trained on 5 to 15" in card, True)
check("and so is the grid the compiler snaps to", "0.71s grid" in card, True)
check("a clip's reference limit is its grammar's, off the reference block",
      "Up to 9 pictures may be cited" in card, True)
check("a still cited by a clip is named as its first frame",
      'A still in "from" is the clip\'s first frame' in card, True)
# Both families offer the same shapes, which every family in this pack does, and
# printing eleven names twice would be a fifth of the card's whole budget.
check("one aspect table serves both where they agree",
      card.count("16:9, 1:1, 9:16"), 1)
# The point of the card being short: it rides in front of every turn.
check("the card stays inside its budget", len(card.split()) < 140, True)

# What a still family does with a cited picture, and why the card has to say it
# before the model cites one. Krea 2 is the default and reads references only
# through an adapter in the pre-stage's LoRA stack, which this room cannot
# reach — so "make it bluer" on a still would otherwise end, every time, in the
# compiler's refusal about a control the person cannot see.
check("a family whose references need an adapter says it takes none",
      'It cannot be given the pictures in "from"' in card, True)
check("and tells the model what to do instead",
      "say so if you are asked to change a picture" in card, True)
edits = chat.machine_card("qwenedit", "h3", CATALOG, ON_DISK, READY)
check("while one that reads pictures outright says how many",
      "Up to 3 pictures may be cited" in edits, True)
# On an edit family the compile starts the render from the first reference, so
# which one is cited first is the difference between changing a picture and
# drawing a new one beside it.
check("and an edit family says which one is being changed",
      "The first is the picture being changed" in edits, True)
# The compiler makes the canvas follow the init's shape on an edit, so an
# aspect on one is a number nothing reads — the model is told not to write it
# rather than left to wonder why the shape never moved.
check("and that it keeps its shape, so the model leaves the aspect out",
      'keeps its own shape, so leave "aspect" out' in edits, True)
check("which a family that only cites them does not",
      "being changed" in card, False)

# The still family cannot read a picture, but an edit family on the rail can:
# the card says a still *can* be given one, and by the edit family's count and
# rule — and never by its name. The model wrote "still" and cited a picture;
# which weights change it is the rail's business, the way a clip's checkpoint
# is, and `still_arch_for` below is what carries the picture there.
routed = chat.machine_card("krea2", "h3", CATALOG, ON_DISK, READY, edit_family="qwenedit")
check("with an edit family behind it, a still that reads no picture may be given one",
      "Up to 3 pictures may be cited" in routed and "cannot be given" not in routed, True)
check("with the edit family's own rule", "The first is the picture being changed" in routed, True)
check("and the still family still named as what draws a picture",
      '"still" is Krea 2' in routed, True)
check("but the edit family never named", "Qwen" in routed, False)
check("the card stays inside its budget with the edit line on it",
      len(routed.split()) < 160, True)
# Not ready is the one time the edit family is named: the file that is missing
# is that family's, and the person has to know whose weights to go and pick.
bare_edit = chat.machine_card("krea2", "h3", CATALOG, ON_DISK,
                              {**READY, "qwenedit": {}}, edit_family="qwenedit")
check("an edit family with a file missing is named with what it is missing",
      "Changing a picture is not ready: Qwen Image Edit has no file picked for" in bare_edit, True)
check("and the still family goes back to refusing pictures",
      "cannot be given" in bare_edit, True)
check("an edit family that is the still family is nothing extra to say",
      chat.machine_card("qwenedit", "h3", CATALOG, ON_DISK, READY, edit_family="qwenedit"),
      edits)

# Which family a picture is changed on: the rail's own choice, ready or not
# (the card says what it is missing), else the pack's default where it is
# ready, else the first that is ready, else the default or the first there is
# so the card can say what it would take, else none. The default is Flux 2
# Klein — `registry.DEFAULT_EDIT` — so a disk complete for both edit families
# edits on the same one every time, and the pill is where to say otherwise.
KLEIN = {**QWENEDIT, "id": "flux2klein", "label": "Flux 2 Klein",
         "weights": [{**slot, "folder": "klein_" + slot["folder"]} for slot in QWENEDIT["weights"]]}
KLEIN_FILES = {slot["id"]: f"klein_{slot['id']}.safetensors" for slot in KLEIN["weights"]}
KLEIN_ON_DISK = {"by_folder": {**ON_DISK["by_folder"],
                               **{slot["folder"]: [KLEIN_FILES[slot["id"]]] for slot in KLEIN["weights"]}}}
BOTH_READY = {**READY, "flux2klein": KLEIN_FILES}
# Qwen first in the catalog, so the default is a choice and not the order.
TWO_EDITS = {"families": [KREA2, QWENEDIT, KLEIN, H3]}
check("the edit families are the still-only ones whose first picture is the one changed",
      [f["id"] for f in chat.edit_families(TWO_EDITS)], ["qwenedit", "flux2klein"])
check("the pack's default is Flux 2 Klein", chat.pick_edit_family.__defaults__[1], "flux2klein")
check("the rail's own choice wins, ready or not",
      chat.pick_edit_family(TWO_EDITS, ON_DISK, {}, "qwenedit")["id"], "qwenedit")
check("with both ready, the default edits — not the first in the catalog",
      chat.pick_edit_family(TWO_EDITS, KLEIN_ON_DISK, BOTH_READY)["id"], "flux2klein")
check("with only the other ready, the one that is ready",
      chat.pick_edit_family(TWO_EDITS, ON_DISK, READY)["id"], "qwenedit")
check("with neither ready, the default, so the card says what it would take",
      chat.pick_edit_family(TWO_EDITS, {"by_folder": {}}, {})["id"], "flux2klein")
check("and none where no family edits", chat.pick_edit_family(CATALOG_NO_EDIT, ON_DISK, READY), None)
check("a choice the catalog does not list is no choice",
      chat.pick_edit_family(TWO_EDITS, KLEIN_ON_DISK, BOTH_READY, "krea2")["id"], "flux2klein")
check("read off the manifest, never off a family id",
      (chat.takes_refs(KREA2), chat.takes_refs(QWENEDIT), chat.takes_refs(H3)),
      (False, True, True))
check("a family that declares no limit at all has nothing said about it",
      chat.ref_limit({"prompt": {}}), None)

# The turbo checkpoint is required exactly when the pill is thrown. Left out
# either way, the dry run passes and `render_image.check` refuses on the queue —
# the one failure the card and the dry run exist between them to prevent.
check("with the pill thrown the Turbo checkpoint is required",
      chat.missing_weights(KREA2, READY["krea2"], ON_DISK, turbo=True),
      ["the Turbo checkpoint"])
check("and with it thrown the card says so where the model can read it",
      "no file is picked for the Turbo checkpoint" in
      chat.machine_card("krea2", "h3", CATALOG, ON_DISK, READY, turbo=True), True)
check("a machine that has the file is ready either way",
      chat.missing_weights(
          KREA2, {**READY["krea2"], "turbo_model": "krea2.safetensors"},
          ON_DISK, turbo=True), [])
# The switch is wired to the still side alone — see `video_piece` — so it must
# not start demanding files of the video family.
check("the switch does not reach the video family",
      "MiniMax H3 is not ready" in
      chat.machine_card("krea2", "h3", CATALOG, ON_DISK, READY, turbo=True), False)

# The turbo checkpoint is a choice — the pill is off unless somebody throws it —
# and a routed pair is a choice too: one of them on disk already renders
# something, and refusing a machine that has Ref2VA but not FL2VA would be
# refusing a machine that works.
check("an unpicked turbo checkpoint is not missing weights",
      chat.missing_weights(KREA2, READY["krea2"], ON_DISK), [])
check("nor is a second routed checkpoint",
      chat.missing_weights(H3, READY["h3"], ON_DISK), [])
check("nor a slot the family declares optional",
      "the x2 upscaler" in card, False)
check("nor one whose file some other node opens for itself",
      "the face detector" in card, False)

check("a family with no routed checkpoint at all cannot render",
      chat.missing_weights(H3,
                           {k: v for k, v in READY["h3"].items() if k != "fl2va"},
                           ON_DISK),
      ["the FL2VA checkpoint", "the Ref2VA checkpoint"])

# A pick is a filename somebody chose once, and the file can be gone since. Both
# halves are asked, because a stale pick otherwise fails at the loader minutes
# later instead of in the card, where the model could have said so.
check("a pick naming a file that is no longer there is missing",
      chat.missing_weights(KREA2,
                           {**READY["krea2"], "vae": "deleted.safetensors"}, ON_DISK),
      ["the VAE"])

bare = chat.machine_card("krea2", "h3", CATALOG, ON_DISK, {})
check("an unset machine says which family is not ready",
      "Krea 2 is not ready" in bare, True)
check("naming every one, by the name on the control that picks it",
      "no file is picked for the checkpoint, the text encoder and the VAE" in bare, True)
check("and telling the model to say so rather than try",
      "Say so instead of asking for a still" in bare, True)


# ---- the first run ----------------------------------------------------------
#
# The room's three questions are asked against one report: what each family
# would render with if nobody had picked anything, and what would still refuse
# it. The guess is the frontend's own, said again server-side — unique match on
# the manifest's hints, `avoid` ruling out the file that shares a stem.

HINTED = {"families": [
    {**KREA2, "weights": [
        {**KREA2["weights"][0], "hints": ["krea2"], "avoid": ["turbo"]},
        {**KREA2["weights"][1], "hints": ["turbo"]},
        {**KREA2["weights"][2], "hints": ["qwen"]},
        {**KREA2["weights"][3], "hints": ["krea2"]},
    ]},
    {**H3, "weights": [
        {**H3["weights"][0], "hints": ["fl2va"]},
        {**H3["weights"][1], "hints": ["ref2va"]},
        {**H3["weights"][2], "hints": ["minimax"]},
        {**H3["weights"][3], "hints": ["h3"], "avoid": ["audio"]},
        {**H3["weights"][4], "hints": ["audio"]},
        *H3["weights"][5:],
    ]},
]}
KREA2_HINTED, H3_HINTED = HINTED["families"]

check("a slot is guessed from the one file that answers to its hint",
      chat.guess_weights(KREA2_HINTED, ON_DISK),
      {"model": "krea2.safetensors", "clip": "qwen.safetensors",
       "vae": "krea2_vae.safetensors"})
check("avoid rules out the file that shares the stem",
      chat.guess_weights(H3_HINTED, ON_DISK)["vae"], "h3_vae.safetensors")
check("two candidates is a question, not a coin toss",
      "model" in chat.guess_weights(
          KREA2_HINTED, {"by_folder": {**ON_DISK["by_folder"],
                                       "diffusion_models": ["krea2_a.safetensors",
                                                            "krea2_b.safetensors"]}}),
      False)
check("a slot with no hints is never guessed",
      chat.guess_weights(KREA2, ON_DISK), {})

report = {entry["id"]: entry for entry in chat.setup_report(HINTED, ON_DISK, {})}
check("the report covers every family", sorted(report), ["h3", "krea2"])
check("a family the disk completes is ready", report["krea2"]["missing"], [])
check("with the turbo checkpoint's absence reported apart",
      report["krea2"]["turbo"], False)
check("a family the disk completes on one routed checkpoint is ready too",
      report["h3"]["missing"], [])
check("a family missing a file says which, by the control's title",
      chat.setup_report(HINTED, {"by_folder": {**ON_DISK["by_folder"], "vae": []}},
                        {})[1]["missing"],
      ["the video VAE", "the audio VAE"])
check("a remembered pick wins over the guess",
      chat.setup_report(HINTED, ON_DISK,
                        {"krea2": {"clip": "minimax.safetensors"}})[0]["picks"]["clip"],
      "minimax.safetensors")
check("but a remembered blank does not blank the guess",
      chat.setup_report(HINTED, ON_DISK, {"krea2": {"clip": ""}})[0]["picks"]["clip"],
      "qwen.safetensors")
slots = {slot["id"]: slot for slot in report["krea2"]["slots"]}
check("each slot carries its folder listing for choosing by hand",
      slots["vae"]["options"], ON_DISK["by_folder"]["vae"])
check("and whether it is required with the switch off",
      (slots["model"]["required"], slots["turbo_model"]["required"]), (True, False))
check("a routed checkpoint counts as required",
      {slot["id"] for slot in report["h3"]["slots"] if slot["required"]},
      {"fl2va", "ref2va", "clip", "vae", "audio_vae"})


# ---- the ledger -------------------------------------------------------------
#
# The whole of what the model knows about a render. Pixels never enter the text
# context: an edit is a fresh prompt plus the id of the earlier thing, which is
# what makes the id the load-bearing part of the line.

check("a render reads as its handle, kind, shape, turn and prompt",
      chat.ledger_line(LEDGER[0]),
      'img-1 · still · 16:9 · turn 1 · "a red fox on a snowy ridge at dusk, low sun behind"')
check("a line with nothing but a handle is still a line",
      chat.ledger_line({"handle": "img-4"}), "img-4")
check("an upload with a filename for a description keeps it",
      chat.ledger_line({"handle": "img-5", "kind": "still", "text": "cat.png"}),
      'img-5 · still · "cat.png"')
long_one = chat.ledger_line({"handle": "img-6", "text": "word " * 60})
check("a very long description is cut at a word", long_one.endswith('…"'), True)
check("and stays short enough that twenty of them are still a ledger",
      len(long_one) < 140, True)
check("an empty ledger says so rather than showing a heading over nothing",
      chat.ledger_block([]), "WHAT HAS BEEN MADE\nNothing yet.")
check("and a full one is one line per thing",
      chat.ledger_block(LEDGER).count("\n"), 2)
# The room's own things and nothing else: there is no node in this list. The
# last picture and the last clip wear a mark, because "it" nearly always means
# the newest thing and a model should not have to work that out from turns.
block = chat.ledger_block(LEDGER)
check("the latest picture and the latest clip are marked as such",
      ("img-1 · still · 16:9 · turn 1 · \"a red fox on a snowy ridge at dusk, low sun behind\" — the latest picture" in block,
       block.endswith("— the latest clip")), (True, True))
two = chat.ledger_block(LEDGER + [{"handle": "img-2", "kind": "still", "text": "bluer"}])
check("only the newest of a kind is marked",
      (two.count("the latest picture"), "img-2 · still · \"bluer\" — the latest picture" in two), (1, True))
check("a line marked as the node's is an ordinary line now: the ledger is the room's",
      "ON THE NODE" in chat.ledger_block([{"handle": "img-1", "kind": "image", "shelf": True}]), False)

# What each turn made is said on the turn, so "it" on the next line has a
# name — the ledger says what exists, this says which of it was just made.
made = chat._rendered({"role": "assistant", "made": "pic-2",
                       "action": {"act": "render", "kind": "still", "prompt": "a fox"}})
check("an assistant turn says which handle its render became",
      made.endswith("→ made pic-2"), True)
check("a turn whose render never landed says so",
      chat._rendered({"role": "assistant", "failed": True,
                      "action": {"act": "render", "kind": "still", "prompt": "a fox"}})
      .endswith("→ nothing was made"), True)
check("and a turn still rendering says neither",
      "→" in chat._rendered({"role": "assistant",
                              "action": {"act": "render", "kind": "still", "prompt": "a fox"}}), False)

# ---- the person's own citations are binding --------------------------------
#
# A handle the person typed is a decision. It goes into "from" whether or not
# the model repeated it, and a suffix the person gave it wins over the model's.
KNOWN = chat.known_handles(LEDGER)
plain = {"act": "render", "kind": "video", "prompt": "she looks up", "from": [], "say": ""}
check("a handle the person wrote is cited even when the model dropped it",
      chat.bind(plain, "animate @img-1 please", KNOWN)["from"], ["img-1"])
check("the person's role wins over the model's scope for the same handle",
      chat.bind({**plain, "from": ["img-1:style"]}, "@img-1:start she looks up", KNOWN)["from"],
      ["img-1:start"])
check("the model's own citations stand beside the person's",
      chat.bind({**plain, "from": ["vid-1:camera"]}, "like @img-1", KNOWN)["from"],
      ["vid-1:camera", "img-1"])
check("a handle the ledger does not know is prose, not a citation",
      chat.bind(plain, "@img-9 please", KNOWN)["from"], [])
check("a suffix a handle cannot wear is not written for it",
      chat.bind(plain, "@vid-1:start", KNOWN)["from"], ["vid-1"])
check("a say is left alone", chat.bind({"act": "say", "say": "hi"}, "@img-1", KNOWN),
      {"act": "say", "say": "hi"})
# And through the judge, which is where the room meets it.
bound = chat.judge('Opening on it.\n```json\n{"act": "render", "kind": "video", "prompt": "she looks up"}\n```',
                   LEDGER, "animate @img-1:start")
check("the judge binds what the person cited onto the model's action",
      bound["action"]["from"], ["img-1:start"])


# ---- the context and its budget ---------------------------------------------

HISTORY = []
for turn in range(1, 8):
    HISTORY.append({"role": "user", "text": f"turn {turn}"})
    HISTORY.append({"role": "assistant",
                    "action": {"act": "render", "kind": "still",
                               "prompt": f"a picture for turn {turn}"}})

kept = chat.trim(HISTORY)
check("the budget keeps five exchanges",
      sum(1 for m in kept if m["role"] == "user"), 5)
check("dropping the oldest first", kept[0]["text"], "turn 3")
check("and never an answer whose question is gone", kept[0]["role"], "user")

# The count is the rule; the character budget is the backstop. Five exchanges of
# a pasted paragraph and a long rewrite are both legitimate and both blow a
# token budget that a count alone cannot see.
huge = [{"role": "user", "text": "x" * 3000},
        {"role": "assistant", "say": "y" * 3000},
        {"role": "user", "text": "the short one"}]
check("an enormous exchange is dropped even inside the count",
      [m["text"] for m in chat.trim(huge) if m["role"] == "user"], ["the short one"])
check("but the turn being answered is never dropped",
      chat.trim([{"role": "user", "text": "z" * 9000}])[0]["role"], "user")

message = chat.context(HISTORY, LEDGER, card)
check("the machine leads", message.startswith("WHAT THIS MACHINE MAKES"), True)
check("the ledger follows it",
      message.index("WHAT HAS BEEN MADE") < message.index("THE CONVERSATION"), True)
check("the conversation is last, and the freshest turn is its last line",
      message.index("user: turn 7") > message.index("user: turn 6"), True)
check("an assistant turn reads back as the action it took, not as prose",
      '"prompt": "a picture for turn 7"' in message, True)
# Fields nobody set are left out: a wall of nulls is the same information at
# three times the length, on a model that is paying for every token of it.
check("with only the fields that were set", '"say"' in message, False)
check("and the last thing read is what to do about it",
      message.rstrip().endswith("``` fence, and nothing after it."), True)


# ---- the blob the action becomes --------------------------------------------

still = chat.still_piece(
    chat.validate({"act": "render", "kind": "still", "prompt": "the fox, bluer",
                   "from": ["img-1"], "aspect": "1:1"}, LEDGER), LEDGER, RAIL)
check("a still is a pre-stage blob of the rail's architecture", still["arch"], "krea2")
check("the model's prompt goes in as typed", still["prompt"], "the fox, bluer")
check("the selected rail aspect wins over the action's", still["aspect"], "16:9")
check("and the rail's is used when the action says nothing",
      chat.still_piece(chat.validate(
          {"act": "render", "kind": "still", "prompt": "a fox"}, LEDGER),
          LEDGER, RAIL)["aspect"], "16:9")
# ...and where nobody has an opinion the key is simply not written: both
# compilers read an absent one as their family's own default, and a number
# repeated here would be a third copy of one two modules already own.
bare_canvas = chat.still_piece(
    chat.validate({"act": "render", "kind": "still", "prompt": "a fox"}, LEDGER),
    LEDGER, {**RAIL, "aspect": None, "still_edge": None})
check("a shape nobody chose is left to the family",
      ("aspect" in bare_canvas, "short_edge" in bare_canvas), (False, False))
# The short edge is the kind's own: a still at the still edge, a clip at the
# clip edge, and a rail from before the split still lands its one number.
check("a still is drawn at the still edge", still["short_edge"], 1024)
check("a clip is sampled at the clip edge",
      chat.video_piece(chat.validate({"act": "render", "kind": "video", "prompt": "a fox"}, LEDGER),
                       LEDGER, RAIL)["short_edge"], 768)
check("the selected aspect applies to a clip even if the action disagrees",
      chat.video_piece(chat.validate({"act": "render", "kind": "video", "prompt": "a fox",
                                      "aspect": "16:9"}, LEDGER),
                       LEDGER, {**RAIL, "aspect": "3:4"})["aspect"], "3:4")
check("an older rail's one short edge is read for both",
      chat.still_piece(chat.validate({"act": "render", "kind": "still", "prompt": "a fox"}, LEDGER),
                       LEDGER, {**RAIL, "still_edge": None, "short_edge": 896})["short_edge"], 896)
check("a cited handle becomes a reference carrying its file",
      still["refs"], [{"handle": "img-1", "filename": "continuity/chat/fox.png"}])
# The promotion of a first reference to the thing being edited is
# `compile_image.compile_prestage`'s, on the families that declare
# `EDITS_FIRST_REF`, and citing in order is the whole of what this side has to
# do to make it right — a second copy of that rule here could only disagree.
edit = chat.still_piece(
    chat.validate({"act": "render", "kind": "still", "prompt": "make her coat white",
                   "from": ["img-1"]}, LEDGER), LEDGER,
    {**RAIL, "still_family": "qwenedit", "still_arch": "qwenedit"})
check("an edit family gets the picture being edited as its first reference",
      edit["refs"][0]["handle"], "img-1")
check("and no init, so the compile's own promotion is what decides",
      edit["init"], None)
check("the weights are left for the route, which is the half with a disk",
      still["models"], {})
check("a bare still has an empty turbo block and an empty stack",
      (still["turbo"], still["loras"]), ({}, []))

# ---- the node on the canvas is the base ---------------------------------------
#
# The room renders with the node: its blob is the base, and the turn writes the
# prompt, the citations and the shape over it. Everything else on the blob —
# the LoRA stack with the turbo LoRA in it, the turbo block, the sampler row,
# the weights, the passes — is the node's and stands, which is what makes the
# room's gear the node's row rather than a second one.

PRE = {"version": 1, "arch": "krea2", "prompt": "an old prompt", "init": {"filename": "x.png"},
       "refs": [{"handle": "old", "filename": "old.png"}],
       "loras": [{"name": "krea2_turbo_lora.safetensors", "strength": 1.0, "enabled": True}],
       "turbo": {"krea2": {"on": True, "lora": "krea2_turbo_lora.safetensors", "quality": "draft"}},
       "sampling": {"steps": 4, "cfg": 1.0}, "aspect": "4:3", "short_edge": 1536,
       "models": {"krea2": {"model": "krea2.safetensors"}, "dtype": "fp8_e4m3fn"},
       "neural": {"on": True}}
over = chat.still_piece(
    chat.validate({"act": "render", "kind": "still", "prompt": "the fox, bluer",
                   "from": ["img-1"], "aspect": "1:1"}, LEDGER), LEDGER, RAIL, PRE)
check("a still over the pre-stage keeps its stack, switch, row, weights and passes",
      (over["loras"], over["turbo"], over["sampling"], over["models"], over["neural"]),
      (PRE["loras"], PRE["turbo"], PRE["sampling"], PRE["models"], PRE["neural"]))
check("and takes the turn's prompt, citation and shape over the node's",
      (over["prompt"], over["refs"], over["init"], over["aspect"], over["short_edge"]),
      ("the fox, bluer", [{"handle": "img-1", "filename": "continuity/chat/fox.png"}],
       None, "16:9", 1024))
check("the base is copied, not written on",
      (PRE["prompt"], PRE["refs"][0]["handle"]), ("an old prompt", "old"))
check("the pre-stage's switch on the checkpoint is the file the card counts",
      (chat.still_turbo_checkpoint({"arch": "krea2", "turbo": {"krea2": {"on": True, "lora": ""}}}),
       chat.still_turbo_checkpoint(PRE),
       chat.still_turbo_checkpoint({"arch": "krea2", "turbo": {"on": True}}),
       chat.still_turbo_checkpoint({})),
      (True, False, True, False))

PIECE = {"version": 2, "prompt": "a film about a fox", "family": "h3",
         "models": {"model": "h3.safetensors", "route": "fl2va"},
         "loras": [{"name": "h3_lightx2v.safetensors", "strength": 0.6, "enabled": True}],
         "turbo": {"on": True, "lora": "h3_lightx2v.safetensors"},
         "sampling": {"steps": 6, "sampler_name": "euler", "scheduler": "beta"},
         "face": {"on": True}, "cast": [{"handle": "anna"}], "aspect": "9:16", "short_edge": 512,
         "segments": [{"prompt": "one"}, {"prompt": "two"}]}
quick = chat.video_piece(
    chat.validate({"act": "render", "kind": "video", "prompt": "the fox looks up"}, LEDGER),
    LEDGER, RAIL, PIECE)
check("a clip over the piece keeps its stack, switch, row, weights, passes and cast",
      (quick["loras"], quick["turbo"], quick["sampling"], quick["models"], quick["face"], quick["cast"]),
      (PIECE["loras"], PIECE["turbo"], PIECE["sampling"], PIECE["models"], PIECE["face"], PIECE["cast"]))
check("and its standing description", quick["prompt"], "a film about a fox")
check("the strip becomes one card carrying the turn's prompt",
      [card["prompt"] for card in quick["segments"]], ["the fox looks up"])
check("in the room's shape, not the node's", (quick["aspect"], quick["short_edge"]), ("16:9", 768))
check("the piece is copied, not written on", len(PIECE["segments"]), 2)
plain = chat.video_piece(
    chat.validate({"act": "render", "kind": "video", "prompt": "the fox looks up"}, LEDGER), LEDGER, RAIL)
check("a bare clip has an empty stack and the switch off",
      (plain["loras"], plain["turbo"]), ([], {"on": False, "lora": None}))

# A family whose references arrive through an adapter is given the picture:
# the adapter is a LoRA, a cast member can wear one for the family, and
# whether it is on the stack is the compiler's question (`check_refs`),
# refused there in the family's own words where it is not. The room used to
# refuse here, which made the adapter a thing nobody could ever hang.
ADAPTED = {**RAIL, "still_pictures": chat.still_pictures(KREA2, CATALOG)}
check("a family that reads pictures through an adapter takes one, though not as its own",
      {k: ADAPTED["still_pictures"][k] for k in ("takes", "native", "refusal")},
      {"takes": True, "native": False, "refusal": ""})
check("...and a picture cited to it rides in as a reference",
      chat.still_piece(chat.validate({"act": "render", "kind": "still", "prompt": "bluer",
                                      "from": ["img-1"]}, LEDGER), LEDGER, ADAPTED)["refs"],
      [{"handle": "img-1", "filename": "continuity/chat/fox.png"}])
check("a family that reads none at all still refuses, naming the ones that do",
      "do read pictures" in chat.still_pictures(
          {"id": "ideogram4", "label": "Ideogram 4", "produces": ["still"], "prompt": {"max_refs": 0}},
          CATALOG)["refusal"], True)
check("a still with nothing cited is made on that family all the same",
      chat.still_piece(chat.validate(
          {"act": "render", "kind": "still", "prompt": "a fox"}, LEDGER),
          LEDGER, ADAPTED)["refs"], [])
# The other way of reading no pictures: weights that take none at all.
check("a family whose weights read no picture says so differently",
      chat.refs_refusal({"label": "Ideogram 4", "prompt": {"max_refs": 0}}),
      "Ideogram 4 draws from words alone: it reads no attached picture at all.")
check("the rail's block says whether the first picture is the one being changed",
      (chat.still_pictures(KREA2, CATALOG)["edits"], chat.still_pictures(QWENEDIT, CATALOG)["edits"]),
      (False, True))

# ---- where a still goes ------------------------------------------------------
#
# The one decision this surface makes about families, and the harness makes it
# rather than the model: a still that cites a picture the still family cannot
# read goes to the rail's edit arch, when the rail has one. The model is never
# asked to name a family — it wrote "still" and cited a picture, which is all a
# person would have said.

EDIT_RAIL = {**RAIL, "edit_family": "qwenedit", "edit_arch": "qwenedit",
             "still_pictures": chat.still_pictures(KREA2, CATALOG)}
CAST = [{"name": "anna", "takes": "person", "from": ["img-1"], "description": "red coat"}]


def where(action, rail=EDIT_RAIL, cast=()):
    return chat.still_arch_for(
        chat.validate(action, LEDGER, cast=[m["name"] for m in cast]), LEDGER, rail, cast)


check("a still with nothing cited is drawn on the rail's own arch",
      where({"act": "render", "kind": "still", "prompt": "a fox"}), "krea2")
check("a still that cites a picture goes to the edit arch",
      where({"act": "render", "kind": "still", "prompt": "bluer", "from": ["img-1"]}), "qwenedit")
check("whatever the picture is cited for",
      where({"act": "render", "kind": "still", "prompt": "a fox", "from": ["img-1:style"]}), "qwenedit")
check("a clip cited is not a picture, and stays",
      where({"act": "render", "kind": "still", "prompt": "a fox", "from": ["vid-1"]}), "krea2")
# A member's picture is who they are, which a family reading through an
# adapter does read — a plain picture is one to change, which it cannot.
check("a cast member's picture stays on a family that reads it through its adapter",
      where({"act": "render", "kind": "still", "prompt": "@anna at dusk"}, cast=CAST), "krea2")
check("a family that reads pictures itself keeps them",
      where({"act": "render", "kind": "still", "prompt": "bluer", "from": ["img-1"]},
            {**EDIT_RAIL, "still_pictures": chat.still_pictures(QWENEDIT, CATALOG)}), "krea2")
check("and a rail with no edit arch leaves the still where it is, to be refused in words",
      where({"act": "render", "kind": "still", "prompt": "bluer", "from": ["img-1"]},
            {**EDIT_RAIL, "edit_arch": None}), "krea2")
check("a rail that says nothing about pictures is one whose family takes them",
      where({"act": "render", "kind": "still", "prompt": "bluer", "from": ["img-1"]},
            {**RAIL, "edit_arch": "qwenedit"}), "krea2")

# On an edit family the compiler starts the render from the first reference,
# so the order the pictures ride in is whether this changes a picture or draws
# beside one: the ones cited plain lead, the ones cited for something follow,
# and with none cited plain the render starts from an empty canvas. A picture
# being changed keeps its own shape, so the action's aspect is not written.
ON_EDIT = {"still_family": "qwenedit", "still_arch": "qwenedit", "aspect": "16:9",
           "still_edge": 1024, "still_pictures": chat.still_pictures(QWENEDIT, CATALOG)}
EDIT_LEDGER = LEDGER + [{"handle": "img-2", "kind": "still", "aspect": "1:1", "turn": 3,
                         "filename": "continuity/chat/street.png", "text": "a street"}]


def edited(action, cast=()):
    return chat.still_piece(chat.validate(action, EDIT_LEDGER, cast=[m["name"] for m in cast]),
                            EDIT_LEDGER, ON_EDIT, cast=cast)


changed = edited({"act": "render", "kind": "still", "prompt": "bluer", "from": ["img-1"], "aspect": "1:1"})
check("a picture cited plain is the one changed: first, from its own canvas",
      ([r["handle"] for r in changed["refs"]], changed[chat.EDIT_FIRST_FIELD]), (["img-1"], True))
check("and it keeps its own shape — the aspect is not written",
      "aspect" in changed, False)
beside = edited({"act": "render", "kind": "still", "prompt": "a fox in that look",
                 "from": ["img-1:style"], "aspect": "1:1"})
check("a picture cited for its look is only drawn from: a blank canvas, in the asked shape",
      (chat.EDIT_FIRST_FIELD in beside, beside["aspect"]), (False, "16:9"))
ordered = edited({"act": "render", "kind": "still", "prompt": "@img-2 in the look of @img-1",
                  "from": ["img-1:style", "img-2"]})
# A member's picture carries its saved renditions (`compile.Asset.mods`):
# the room reads them off the piece and writes them onto the still's
# reference, and the family rendering it takes the one in its own space. A
# member built out of a mod alone is their words — a still family loads
# pictures by name, and a mod is a latent.
MOD_PIECE = {"subjects": [{"handle": "kim", "from": ["img-9"], "description": "a green coat"},
                          {"handle": "lee", "from": ["img-8"], "description": "tall"}],
             "assets": [{"handle": "img-9", "kind": "image", "role": "reference", "filename": "kim.png",
                         "mods": {"h3_video": "refmod:cast/kim", "flux2": "refmod:cast/kim.flux2"}},
                        {"handle": "img-8", "kind": "image", "role": "reference",
                         "filename": "refmod:cast/lee"}]}
MOD_CAST = chat.cast_entries(MOD_PIECE)
check("the room reads a picture's renditions off the piece",
      MOD_CAST[0].get("mods"), {"img-9": {"h3_video": "refmod:cast/kim", "flux2": "refmod:cast/kim.flux2"}})
check("...and a mod-only member carries none", "mods" in MOD_CAST[1], False)
MOD_LEDGER = EDIT_LEDGER + [
    {"handle": "img-9", "kind": "still", "filename": "kim.png", "text": "kim"},
    {"handle": "img-8", "kind": "still", "filename": "refmod:cast/lee", "text": "lee"}]
with_mods = chat.still_piece(
    chat.validate({"act": "render", "kind": "still", "prompt": "@kim at dusk"}, MOD_LEDGER,
                  cast=["kim", "lee"]), MOD_LEDGER, ON_EDIT, cast=MOD_CAST)
check("a member's picture rides in with its renditions",
      with_mods["refs"], [{"handle": "img-9", "filename": "kim.png",
                           "mods": {"h3_video": "refmod:cast/kim", "flux2": "refmod:cast/kim.flux2"}}])
mod_only = chat.still_piece(
    chat.validate({"act": "render", "kind": "still", "prompt": "@lee at dusk"}, MOD_LEDGER,
                  cast=["kim", "lee"]), MOD_LEDGER, ON_EDIT, cast=MOD_CAST)
check("a member built out of a mod alone is their words in a still",
      (mod_only["refs"], mod_only["prompt"]), ([], "tall at dusk"))
# ...unless the still family reads that mod's space: a downloaded Klein set
# on a Klein still is their picture, and rides in as the reference it is.
ON_KLEIN = {**ON_EDIT, "still_family": "flux2klein", "still_arch": "flux2klein", "still_space": "flux2"}
klein_cast = [dict(MOD_CAST[0]), {**MOD_CAST[1], "spaces": {"img-8": "flux2"}}]
as_set = chat.still_piece(
    chat.validate({"act": "render", "kind": "still", "prompt": "@lee at dusk"}, MOD_LEDGER,
                  cast=["kim", "lee"]), MOD_LEDGER, ON_KLEIN, cast=klein_cast)
check("a mod in the still family's own space is a member's picture",
      (as_set["refs"], as_set["prompt"]),
      ([{"handle": "img-8", "filename": "refmod:cast/lee"}], "@img-8 (tall) at dusk"))
check("...and one in another family's stays their words",
      chat.still_piece(chat.validate({"act": "render", "kind": "still", "prompt": "@lee at dusk"},
                                     MOD_LEDGER, cast=["kim", "lee"]), MOD_LEDGER,
                       {**ON_KLEIN, "still_space": "h3_video"}, cast=klein_cast)["refs"], [])

# What the still family is sent for a member, and what they wear there: the
# member's row for that family and no other's (`subjects.Subject.wears`).
WORN_PIECE = {"family": "h3",
              "subjects": [{"handle": "kim", "from": ["img-9"], "description": "a green coat",
                            "wears": {"qwenedit": {"loras": [{"name": "kim_qwen.safetensors", "strength": 0.7,
                                                              "triggers": ["k1m"]}]},
                                      "h3": {"loras": [{"name": "kim_h3.safetensors", "strength": 1}]}}},
                           {"handle": "lee", "from": ["img-8"], "description": "tall",
                            "loras": [{"name": "lee_h3.safetensors", "strength": 1}]}],
              "assets": MOD_PIECE["assets"]}
WORN_CAST = chat.cast_entries(WORN_PIECE)
check("the room reads the wardrobe off the piece, a flat list filed under the piece's family",
      (sorted(WORN_CAST[0]["wears"]), WORN_CAST[1]["wears"]),
      (["h3", "qwenedit"], {"h3": {"loras": [{"name": "lee_h3.safetensors", "strength": 1}]}}))
worn_still = chat.still_piece(
    chat.validate({"act": "render", "kind": "still", "prompt": "@kim and @lee at dusk"}, MOD_LEDGER,
                  cast=["kim", "lee"]), MOD_LEDGER, ON_EDIT,
    base={"loras": [{"name": "pin.safetensors", "strength": 0.8}]}, cast=WORN_CAST)
check("a still wears the cited members' LoRAs for its own family, after the stack's",
      [e["name"] for e in worn_still["loras"]], ["pin.safetensors", "kim_qwen.safetensors"])
SENT_CAST = chat.cast_entries({**MOD_PIECE, "subjects": [
    {**MOD_PIECE["subjects"][0], "wears": {"qwenedit": {"send": "words"}}},
    {**MOD_PIECE["subjects"][0], "handle": "kay", "wears": {"qwenedit": {"send": "pictures"}}}]})
as_words = chat.still_piece(
    chat.validate({"act": "render", "kind": "still", "prompt": "@kim at dusk"}, MOD_LEDGER,
                  cast=["kim", "kay"]), MOD_LEDGER, ON_EDIT, cast=SENT_CAST)
check("sent as words, a member with pictures is their description in a still",
      (as_words["refs"], as_words["prompt"]), ([], "a green coat at dusk"))
as_pictures = chat.still_piece(
    chat.validate({"act": "render", "kind": "still", "prompt": "@kay at dusk"}, MOD_LEDGER,
                  cast=["kim", "kay"]), MOD_LEDGER, ON_EDIT, cast=SENT_CAST)
check("sent as pictures, the picture rides in without its renditions",
      as_pictures["refs"], [{"handle": "img-9", "filename": "kim.png"}])

check("the picture cited plain leads whatever order it was cited in",
      [r["handle"] for r in ordered["refs"]], ["img-2", "img-1"])
check("with the compiler's own scope kept on the other",
      ordered["refs"][1].get("takes"), "style")
member = edited({"act": "render", "kind": "still", "prompt": "@anna on @img-2"}, cast=CAST)
check("a member's picture is a reference, never the picture being changed",
      ([r["handle"] for r in member["refs"]], member[chat.EDIT_FIRST_FIELD]), (["img-2", "img-1"], True))
alone = edited({"act": "render", "kind": "still", "prompt": "@anna at dusk"}, cast=CAST)
check("and a member alone is drawn from, on a blank canvas",
      (chat.EDIT_FIRST_FIELD in alone, alone["aspect"]), (False, "16:9"))
fresh = edited({"act": "render", "kind": "still", "prompt": "a fox", "aspect": "1:1"})
check("a still with nothing cited on an edit family is an ordinary still",
      (chat.EDIT_FIRST_FIELD in fresh, fresh["aspect"], fresh["refs"]), (False, "16:9", []))
check("none of which a family that only cites pictures does",
      chat.EDIT_FIRST_FIELD in chat.still_piece(
          chat.validate({"act": "render", "kind": "still", "prompt": "x", "from": ["img-1:style"]}, LEDGER),
          LEDGER, {**RAIL, "still_pictures": {"takes": True, "edits": False}}), False)
# The field is the compiler's, spelled here because `compile_image` imports
# the neural backend and this module has to load on nothing.
with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "creator", "compile_image.py"), encoding="utf-8") as source:
    check("the edit-in-place field is spelled as the compiler spells it",
          f'EDIT_FIRST_FIELD = "{chat.EDIT_FIRST_FIELD}"' in source.read(), True)

# A rail that says nothing means a family that takes pictures, which is what
# every still family but Krea 2 and Ideogram 4 is.
check("a rail with nothing to say about pictures lets one through",
      chat.still_piece(chat.validate(
          {"act": "render", "kind": "still", "prompt": "a fox", "from": ["img-1"]},
          LEDGER), LEDGER, RAIL)["refs"][0]["handle"], "img-1")

refuses("a still cannot be given a clip",
        lambda: chat.still_piece(
            chat.validate({"act": "render", "kind": "still", "prompt": "a fox",
                           "from": ["vid-1"]}, LEDGER), LEDGER, RAIL),
        "@vid-1", "pictures")

clip = chat.video_piece(
    chat.validate({"act": "render", "kind": "video", "prompt": "she looks up",
                   "from": ["img-1", "vid-1"], "seconds": 5}, LEDGER), LEDGER, RAIL)
check("a clip is a piece of one shot", len(clip["segments"]), 1)
check("on the rail's family", clip["family"], "h3")
check("the piece's standing description stays empty — everything is on the card",
      clip["prompt"], "")
shot = clip["segments"][0]
check("the shot carries the model's prompt", shot["prompt"], "she looks up")
check("and the duration it asked for", shot["duration_s"], 5)
check("a still cited by a clip is the shot's first frame",
      (shot["assets"][0]["handle"], shot["assets"][0]["role"],
       shot["assets"][0]["kind"]),
      ("img-1", "first_frame", "image"))
check("and everything else is a reference",
      (shot["assets"][1]["role"], shot["assets"][1]["kind"]), ("reference", "video"))
check("a clip with nothing attached is a plain one",
      chat.video_piece(chat.validate(
          {"act": "render", "kind": "video", "prompt": "a fox"}, LEDGER),
          LEDGER, RAIL)["segments"][0]["assets"], [])
check("and runs for the Creator's own default when nobody said",
      chat.video_piece(chat.validate(
          {"act": "render", "kind": "video", "prompt": "a fox"}, LEDGER),
          LEDGER, {**RAIL, "seconds": None})["segments"][0]["duration_s"], 6)

# A shot opens once, so a second still has nowhere to be a keyframe.
two = chat.video_piece(
    {"act": "render", "kind": "video", "prompt": "a fox",
     "from": ["img-1", "img-2"], "seconds": None, "aspect": None, "say": ""},
    LEDGER + [{"handle": "img-2", "filename": "b.png"}], RAIL)
check("only the first still opens the shot",
      [a["role"] for a in two["segments"][0]["assets"]],
      ["first_frame", "reference"])

# The ledger and the browser disagreeing is the one failure that would put a
# render on the queue without the picture it was supposed to be of.
refuses("a handle the ledger has never issued is refused",
        lambda: chat.video_piece(
            {"act": "render", "kind": "video", "prompt": "a fox", "from": ["img-9"]},
            LEDGER, RAIL),
        "@img-9", "not in the ledger")
refuses("and so is one whose render has not landed yet",
        lambda: chat.video_piece(
            {"act": "render", "kind": "video", "prompt": "a fox", "from": ["img-3"]},
            LEDGER + [{"handle": "img-3"}], RAIL),
        "@img-3", "no file behind it")

check("which node runs which kind is answered in one place",
      (chat.piece_of({"act": "render", "kind": "still", "prompt": "a fox",
                      "from": []}, LEDGER, RAIL)[:2],
       chat.piece_of({"act": "render", "kind": "video", "prompt": "a fox",
                      "from": []}, LEDGER, RAIL)[:2]),
      (("MiniMaxH3PreStage", "prestage_data"),
       ("MiniMaxH3Creator", "creator_data")))

# The seed is a widget on the node and never a field in the blob — see
# `sampling.py`, which says why — so it rides in the base's widgets and
# nothing in either blob mentions it.
check("the seed is nowhere in the blob", "seed" in json.dumps(clip), False)


# ---- scopes, the cast and the strip ----------------------------------------
#
# The three things an action may point at beyond a bare handle, each carried
# as flat fields on the same one action — a nested tool is where a small
# model's JSON goes wrong, and one decision per turn is the whole design. The
# cast is the piece's own: the person brings somebody in with the node's `@`
# menu, and the model passes the name through for the compiler to expand.

ROOM = [{"handle": "img-1", "kind": "still", "filename": "a.png", "text": "anna's face"},
        {"handle": "img-2", "kind": "still", "filename": "b.png", "text": "a street"},
        {"handle": "vid-1", "kind": "clip", "filename": "c.mp4 [output]", "text": "shot one"},
        {"handle": "ref-1", "kind": "image", "filename": "shelf.png", "text": "shelf.png"}]

scoped = chat.validate({"act": "render", "kind": "video", "prompt": "a fox",
                        "from": ["img-2:style", "vid-1:camera"]}, ROOM)
check("a scope rides on the handle as a suffix", scoped["from"], ["img-2:style", "vid-1:camera"])
refuses("a scope a picture cannot be cited for is refused by name",
        lambda: chat.validate({"act": "render", "kind": "video", "prompt": "a fox",
                               "from": ["img-2:camera"]}, ROOM), "img-2:camera", "person")
check("a shelf line's kind is its own word, not its prefix",
      chat.known_handles(ROOM)["ref-1"], "image")
check("a handle cited in the prompt and left out of from is added",
      chat.validate({"act": "render", "kind": "video", "prompt": "@img-2 at dusk"}, ROOM)["from"],
      ["img-2"])
refuses("a name nobody has cast is refused with the cast",
        lambda: chat.validate({"act": "render", "kind": "video", "prompt": "@anna walks"},
                              ROOM, cast=["ben"]), "@anna", "@ben")
check("a name on the piece's cast passes through as written",
      chat.validate({"act": "render", "kind": "video", "prompt": "@anna waves"},
                    ROOM, cast=["anna"])["prompt"], "@anna waves")
check("the action has no cast field: the model casts nobody", "cast" in chat.FIELDS, False)

refuses("after names a shot on the strip, with the strip quoted back",
        lambda: chat.validate({"act": "render", "kind": "video", "prompt": "next",
                               "after": "vid-9"}, ROOM, strip=["vid-1"]), "vid-9", "vid-1")
refuses("a still is never on the strip",
        lambda: chat.validate({"act": "render", "kind": "still", "prompt": "x",
                               "after": "vid-1"}, ROOM, strip=["vid-1"]), "still")
following = chat.validate({"act": "render", "kind": "video", "prompt": "next",
                           "after": "@vid-1"}, ROOM, strip=["vid-1"])
check("after is read with or without its @", following["after"], "vid-1")

# What the model is told. Nothing when there is nothing: a block that says
# "no cast" is tokens spent on every turn of every room without one.
check("no strip and no cast add nothing to the context",
      chat.context([], ROOM, "CARD").count("THE "), 0)
told = chat.context([], ROOM, "CARD",
                    strip=[{"handle": "vid-1", "seconds": 5}],
                    cast=[{"name": "anna", "takes": "person", "from": ["img-1"], "description": "red coat"}])
check("the strip is one line in order", "vid-1 (5 s)" in told, True)
check("a member is one line", '@anna · person · from img-1 · "red coat"' in told, True)

# The blob. Over the chat's own piece: its cast and the pool their files are
# on stand, nothing else is read off it, and a shot named "after" keeps the
# strip in front of it, held on its takes, and opens the seam the node would.
RAIL = {"video_family": "h3", "still_arch": "krea2", "aspect": "16:9"}
OWN = {"family": "h3", "subjects": [{"handle": "anna", "takes": "person", "from": ["img-7"],
                                     "description": "red coat"}],
       "assets": [{"handle": "img-7", "kind": "image", "role": "reference", "filename": "anna.png",
                   "ref_size": "max"}],
       "loras": [{"name": "pin.safetensors", "strength": 0.8}],
       "turbo": {"on": True, "lora": "turbo.safetensors"},
       "sampling": {"steps": 8}}
check("the room reads the piece's cast off the blob, every file of theirs counted",
      chat.cast_entries({"subjects": [{"handle": "b", "from": ["ref-1"], "motion": "vid-1",
                                       "voice": "aud-1", "description": "x"}]}),
      [{"name": "b", "takes": "person", "from": ["ref-1", "vid-1", "aud-1"], "description": "x"}])
walk = chat.video_piece(chat.validate({"act": "render", "kind": "video",
                                       "prompt": "@anna walks past @img-2", "from": ["img-2"]},
                                      ROOM, cast=["anna"]), ROOM, RAIL, base=OWN)
check("the piece's cast stands", walk["subjects"], OWN["subjects"])
check("and the pool their files are on, untouched",
      walk["assets"], OWN["assets"])
check("the stack, the turbo block and the sampler row ride through — they are the room's",
      (walk["loras"], walk["turbo"], walk["sampling"]), (OWN["loras"], OWN["turbo"], OWN["sampling"]))
check("a still cited plain beside the member opens the shot",
      walk["segments"][0]["assets"][0]["role"], "first_frame")

# Where a cited picture goes is on its handle. `:start` and `:end` are the
# keyframes, `:ref` and every scope a reference, and a picture cited plain
# opens the shot only if nothing else does.
roles = chat.video_piece(chat.validate({"act": "render", "kind": "video", "prompt": "x",
                                        "from": ["img-2:end", "img-1:start", "vid-1:camera"]},
                                       ROOM), ROOM, RAIL, base={"aspect_source": "pill"})
check("start and end land as the shot's keyframes wherever they were cited",
      [(a["handle"], a["role"]) for a in roles["segments"][0]["assets"]],
      [("img-2", "last_frame"), ("img-1", "first_frame"), ("vid-1", "reference")])
check("a keyframe lets the Creator use the input's canvas, not a saved room pill",
      roles["aspect_source"], "auto")
check("a scope on a clip is what it is cited for",
      roles["segments"][0]["assets"][2].get("takes"), "camera")
asref = chat.video_piece(chat.validate({"act": "render", "kind": "video", "prompt": "x",
                                        "from": ["img-1:ref", "img-2"]}, ROOM), ROOM, RAIL)
check("a picture cited as ref is a reference, and the next plain one opens the shot",
      [(a["handle"], a["role"], a.get("takes")) for a in asref["segments"][0]["assets"]],
      [("img-1", "reference", None), ("img-2", "first_frame", None)])
refuses("two start frames are refused",
        lambda: chat.video_piece(chat.validate({"act": "render", "kind": "video", "prompt": "x",
                                                "from": ["img-1:start", "img-2:start"]}, ROOM),
                                 ROOM, RAIL), "two pictures", "start")
refuses("a clip cannot be a start frame",
        lambda: chat.validate({"act": "render", "kind": "video", "prompt": "x",
                               "from": ["vid-1:start"]}, ROOM), "vid-1:start")
refuses("a picture has no start frame",
        lambda: chat.still_piece(chat.validate({"act": "render", "kind": "still", "prompt": "x",
                                                "from": ["img-1:start"]}, ROOM), ROOM, RAIL),
        "img-1:start", "no start")
check("a picture cited as ref in a still is a plain reference",
      chat.still_piece(chat.validate({"act": "render", "kind": "still", "prompt": "x",
                                      "from": ["img-1:ref"]}, ROOM), ROOM, RAIL)["refs"],
      [{"handle": "img-1", "filename": "a.png"}])
check("what a picture may be cited as lists the roles after the scopes",
      chat.scopes_for("image")[-3:], ["start", "end", "ref"])

STRIP = [{"chat_handle": "vid-1", "prompt": "shot one", "assets": [], "duration_s": 5,
          "hold": True, "take": {"filename": "takes/one.mp4 [output]", "duration_s": 5}}]
after = chat.video_piece(chat.validate({"act": "render", "kind": "video", "prompt": "next",
                                        "after": "vid-1"}, ROOM, strip=["vid-1"]),
                         ROOM, RAIL, strip=STRIP)
check("after keeps the strip in front, held on its take",
      [c.get("hold") for c in after["segments"]], [True, None])
check("and the new card follows it live on both tracks, with the family's medium blend",
      {k: after["segments"][1].get(k) for k in ("continue", "continue_audio", "feather")},
      {"continue": True, "continue_audio": True, "feather": chat.default_feather("h3")})
check("an extension takes its canvas from the continued clip",
      after["aspect_source"], "auto")
check("the family's medium blend is the third width of its grid", chat.default_feather("h3"), 22)
replaced = chat.video_piece(chat.validate({"act": "render", "kind": "video", "prompt": "again",
                                           "replaces": "vid-1"}, ROOM, strip=["vid-1"]),
                            ROOM, RAIL, strip=STRIP)
check("replaces stands in the shot's place, and a first card has no seam",
      (len(replaced["segments"]), replaced["segments"][0].get("continue")), (1, None))
alone = chat.video_piece(chat.validate({"act": "render", "kind": "video", "prompt": "new"},
                                       ROOM, strip=["vid-1"]), ROOM, RAIL, strip=STRIP)
check("neither is a new film of one shot", len(alone["segments"]), 1)
refuses("a kept shot with no take is refused by name",
        lambda: chat.video_piece(
            chat.validate({"act": "render", "kind": "video", "prompt": "x", "after": "vid-1"},
                          ROOM, strip=["vid-1"]),
            ROOM, RAIL, strip=[{"chat_handle": "vid-1", "prompt": "one"}]),
        "@vid-1", "no finished take")

# A still has no cast: a member cited in one is their picture where the name
# stood, or their description where the family reads no picture.
ANNA = [{"name": "anna", "takes": "person", "from": ["img-1"], "description": "red coat"}]
STILL_RAIL = {"still_arch": "krea2", "aspect": "16:9", "still_pictures": {"takes": True}}
portrait = chat.still_piece(chat.validate({"act": "render", "kind": "still", "prompt": "@anna at dusk"},
                                          ROOM, cast=["anna"]), ROOM, STILL_RAIL, cast=ANNA)
check("in a still a member is their first picture, described",
      (portrait["prompt"], portrait["refs"]),
      ("@img-1 (red coat) at dusk", [{"handle": "img-1", "filename": "a.png"}]))
words = chat.still_piece(chat.validate({"act": "render", "kind": "still", "prompt": "@anna at dusk"},
                                       ROOM, cast=["anna"]), ROOM,
                         {**STILL_RAIL, "still_pictures": {"takes": False, "refusal": "no"}}, cast=ANNA)
check("and their description alone where the family takes no picture",
      (words["prompt"], words["refs"]), ("red coat at dusk", []))


# ---- the system prompt ------------------------------------------------------
#
# Read off the file rather than described in prose here: it is the one part of
# this that is tuned against a real model on the bench, and the things below are
# what the parser and the schema depend on it still saying.

SYSTEM = chat.system_prompt()
for field in chat.FIELDS:
    if f'"{field}"' not in SYSTEM:
        FAILURES.append(f"the system prompt never mentions the {field!r} field")
check("it asks for one line of plan then a fence",
      "one short line of plan" in SYSTEM and "``` fence" in SYSTEM, True)
check("it carries the worked exchanges: a still, a clip, a member cited, a next shot, a say",
      SYSTEM.count("Person:"), 6)
check("and teaches the prompt box's own three marks",
      all(mark in SYSTEM for mark in ("@pic-2", "{a|b}", "quoted words")), True)

# Changing a picture is one of two blocks, picked off the rail: an edit family
# takes an instruction over the picture it is shown, a family drawing from a
# reference reads only the words and needs the whole picture again.
EDITING = chat.system_prompt(edits=True)
check("the default is the redraw block: the whole picture written again",
      "drawn beside the old one" in SYSTEM and "changed in place" not in SYSTEM, True)
check("the edit block is an instruction with a keep clause, in the contract's shape",
      ("changed in place" in EDITING and "keep everything else unchanged" in EDITING
       and "drawn beside the old one" not in EDITING
       and EDITING.count("Person:") == SYSTEM.count("Person:") + 3), True)
check("both point at the same heading the contract names",
      all(block.count("CHANGING A PICTURE") == 2 for block in (SYSTEM, EDITING))
      and "under CHANGING A PICTURE" in SYSTEM, True)
edit_prompt = chat.parse(EDITING[EDITING.index("Person: put a red scarf"):
                                 EDITING.index("Person: now from above")])[1]["prompt"]
check("the edit block's worked prompt leads with the change and does not repaint the fox",
      edit_prompt.startswith("Add ") and "snowy" not in edit_prompt, True)
check("a rail whose still family edits, or has an edit family behind one that cannot read a picture, edits",
      [chat.changes_pictures(rail) for rail in (
          {"still_pictures": {"takes": True, "native": True, "edits": True}},
          {"still_pictures": {"takes": True, "native": False, "edits": False}, "edit_arch": "klein"},
          {"still_pictures": {"takes": False, "native": False, "edits": False}, "edit_family": "flux2klein"},
          {"still_pictures": {"takes": True, "native": False, "edits": False}},
          {"still_pictures": {"takes": True, "native": True, "edits": False}, "edit_arch": "klein"},
          {}, None)],
      [True, True, True, False, False, False, False])

check("the edit block's worked exchange shows the earlier prompt and does not repeat it",
      "(made pic-1)" in EDITING and "never repeat that prompt" in EDITING, True)
check("and a camera move is a change with nothing added",
      "Change the viewpoint" in EDITING and "never a thing\nin the picture" in EDITING, True)
check("a rail that edits closes the message on the instruction rule, the other on the plain line",
      (chat.context(HISTORY, LEDGER, "CARD", edits=True).endswith(chat.CLOSING_EDITS),
       chat.context(HISTORY, LEDGER, "CARD").endswith(chat.CLOSING),
       "earlier prompt written out again" in chat.CLOSING_EDITS
       and chat.CLOSING_EDITS.startswith(chat.CLOSING)), (True, True, True))

with_skill = chat.system_prompt("Write everything in the present tense.")
check("a skill set to add lands after the contract, never over it",
      with_skill.startswith(SYSTEM) and "present tense" in with_skill, True)
check("and says out loud that the reply's shape is not its to move",
      "not theirs to move" in with_skill, True)

# The verbosity dial: 0 is the prompt as tuned, byte for byte, and every third
# of the way up is one more fixed block — never a number the model is shown.
check("the dial's bottom is the system prompt untouched",
      [chat.system_prompt(verbosity=v) == SYSTEM for v in (0, 0.0, -1, None, "", "x", "0")],
      [True] * 7)
check("the dial is cut into thirds, the top the last block",
      [chat.verbosity_tier(v) for v in (0, 0.01, 1 / 3, 0.34, 2 / 3, 0.7, 1, 1.5, "0.5")],
      [0, 1, 1, 2, 2, 3, 3, 3, 2])
blocks = [chat.system_prompt(verbosity=tier / chat.TIERS) for tier in range(1, chat.TIERS + 1)]
check("every block lands after the contract, never over it",
      all(block.startswith(SYSTEM) for block in blocks), True)
check("each block is its own wording", len(set(blocks)), chat.TIERS)
check("every block fences what the person asked for, and defers a change to the block above",
      all("Never change what the person asked for" in block
          and "follows CHANGING A PICTURE above" in block
          and '"say" stays one short' in block for block in blocks), True)
check("and carries a worked exchange at its length, in the contract's own shape",
      all(block.count("Person:") == SYSTEM.count("Person:") + 1
          and block.count('"act": "render"') == SYSTEM.count('"act": "render"') + 1
          for block in blocks), True)
lengths = [len(chat.parse(block[len(SYSTEM):])[1]["prompt"]) for block in blocks]
check(f"the worked prompts grow with the dial: {lengths}",
      lengths == sorted(lengths) and len(set(lengths)) == chat.TIERS, True)
both = chat.system_prompt("Write everything in the present tense.", verbosity=1)
check("the verbosity block follows a skill, so its requested length wins",
      both.index("present tense") < both.rindex("HOW MUCH TO WRITE"), True)

rich = {"act": "render", "kind": "still", "prompt": "a fox at dusk", "from": []}
full = {**rich, "prompt": " ".join(["fox"] * chat.RICH_MIN_WORDS)}
check("rich verbosity re-asks a short new-render prompt",
      chat.needs_rich_expansion(rich, "a fox at dusk", verbosity=1), True)
check("a rich prompt with enough detail is accepted",
      chat.needs_rich_expansion(full, "a fox at dusk", verbosity=1), False)
check("direct image edits remain concise at rich verbosity",
      chat.needs_rich_expansion({**rich, "from": ["pic-1"]}, "make it blue", verbosity=1,
                                edits=True, ledger=[{"handle": "pic-1", "kind": "still"}]), False)
check("a new render on an edit-capable rail still expands at rich verbosity",
      chat.needs_rich_expansion(rich, "a fox at dusk", verbosity=1, edits=True), True)

passed("the chat surface parses, refuses, re-asks and patches as specified")

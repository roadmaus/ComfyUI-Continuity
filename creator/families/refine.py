"""What refining a prompt is, before any family says what a prompt looks like.

The refiner started as H3's, because H3 is the family that cannot be prompted
with a sentence: `families/h3/refine.py` hands a vision LLM the user's request,
a per-mode template distilled from MiniMax's guides, and pictures of whatever is
attached, and asks for the Context-IR prose back. Everything about that
arrangement read as H3's, so all of it lived in H3's package — and most of it
was never H3's at all.

Two halves came apart when a second family asked for the same button.

**This module is the half that is about the harness**, and it is the same
whatever writes the prose: the `@handle` representation and the conversion back
to it, the checks that report a citation pointing at nothing, the quoted-span
fidelity check, the ChatML turns and the prefill that stop a small model
answering the request instead of expanding it, the reply-length budget, the
image long edge, and the two field names — `what_i_see` and `global_prompt` —
that are about *this pack's* two questions rather than about any model's
training.

**The other half is the family's**, and it is `Prompting` below: which templates
exist, what a mode is called, what the reply object holds, how several shots
become one body. Those are statements about what a checkpoint was trained to
read, and two families do not share them any more than they share a sampler.

`refine_routes.py` is written against `Prompting` alone and reads nothing off a
family package directly, which is what makes the refine button follow the
piece's model pill. `of(family)` is the lookup, lazy for the reason everything
in `registry.py` is lazy: the pure suites load a family's prompting without a
server to boot.

No torch, no ComfyUI: request building and reply parsing are ordinary data and
are unit-tested that way. `refine_local.py` is what loads the model and
`refine_routes.py` is what knows about disk.
"""

import importlib
import re


class RefineError(RuntimeError):
    """The refiner could not produce a usable rewrite."""


# ---- what one call costs ----------------------------------------------------

# How long a reply may run, in tokens. Not a context size: nothing on this
# backend has one. `Qwen3VLSDTokenizer` is built with `max_length=99999999` and
# `pad_to_max_length=False`, so the prompt is never truncated however long it
# gets, and `BaseGenerate.generate` sizes its KV cache as `len(prompt) + this`.
# So this is purely the output budget — what decides whether a twelve-card
# rewrite finishes its last body or stops mid-sentence, and how much of the KV
# cache is reserved for text that has not been written yet.
NUM_PREDICT = 6144

# What the setting may be moved to. The floor is one short single-shot rewrite;
# the ceiling is where the cache reservation starts costing real VRAM for a
# reply no model is going to fill.
MIN_PREDICT = 1024
MAX_PREDICT = 32768

# Long side of an image handed to the LLM. It is looking at the picture to say
# what is in it, not to reproduce it, and a 4000px reference costs seconds of
# transfer and encode for nothing.
IMAGE_LONG_EDGE = 1024


def reply_tokens(value):
    """The user's reply-length setting, made usable. Junk falls back to default."""
    try:
        return max(MIN_PREDICT, min(MAX_PREDICT, int(value)))
    except (TypeError, ValueError):
        return NUM_PREDICT


# ---- the two fields that are the pack's, not a family's ---------------------

# The first thing the model writes when anything is attached, and the only field
# in a reply that is not part of the prompt.
#
# Reasoning is suppressed and the reply is prefilled with `{`, so without this
# the very first token generated is already the rewrite: the model can write a
# whole description having never attended to the pictures, and on a 4B one it
# does. Asking it to say what is in them first is a grounding pass paid for in
# about fifty tokens, and it happens *inside* the JSON object rather than before
# it so the prefill still holds.
#
# It is read back and shown in the panel rather than dropped, because "did it
# actually look at my images" is the question this whole field exists to answer.
SEEN_FIELD = "what_i_see"

# The piece's standing description, rewritten. Only a whole-timeline refine asks
# for it: the global prompt is placed ahead of every shot's own description at
# generation time, so what the shots share — the style, the world, the cast —
# belongs in it, said once, rather than copied into every body. It is written
# right after `SEEN_FIELD` so the establishing pass comes before the shots that
# inherit from it, and it is stored back into the same editable box it came
# from: the join stays a compile-time fact, not something baked into the prose.
PIECE_FIELD = "global_prompt"


# ---- cutting a lone card into shots -----------------------------------------
#
# Whether a family *offers* the choice is the family's (`Prompting.shot_limit`);
# the arithmetic of making the answer fit is arithmetic.

# The shortest a shot may be, and the most a rewrite may hold. The floor is what
# turns a duration into a shot ceiling: a six-second clip cannot be five cuts,
# and saying so in the grammar is better than clamping it afterwards.
MIN_SHOT_S = 2.0
MAX_SHOTS = 6


def shot_limit(seconds):
    """How many shots a clip of `seconds` may be cut into. 1 means "do not ask".

    Below two shots' worth of time there is no choice to offer, and the request
    falls back to the fixed single body every other path uses.
    """
    return max(1, min(MAX_SHOTS, int(float(seconds or 0) // MIN_SHOT_S)))


def plan_cuts(bodies, cuts, seconds):
    """`([body], [at]), duration -> [(at, body)]` — the model's cuts, made to fit.

    The model picks the times and this fixes them up: the first shot starts at 0
    whatever it said, every later cut is at least `MIN_SHOT_S` past the one
    before it, and the last one leaves that much video after it. A shot with no
    room left is merged into the shot before it rather than dropped, because its
    prose is the only copy of that part of the description — a truncated rewrite
    would lose a paragraph the user never sees go.
    """
    seconds = float(seconds or 0)
    out = []
    for index, body in enumerate(bodies):
        if not out:
            out.append([0.0, body])
            continue
        floor = out[-1][0] + MIN_SHOT_S
        ceiling = seconds - MIN_SHOT_S
        if floor > ceiling:
            out[-1][1] = f"{out[-1][1]} {body}".strip()
            continue
        try:
            at = float(cuts[index])
        except (TypeError, ValueError, IndexError):
            at = floor
        out.append([max(floor, min(at, ceiling)), body])
    return [(at, body) for at, body in out]


# ---- the glossary -----------------------------------------------------------

# Where a user's own instructions land inside a family's system prompt, and
# what they are allowed to move. They arrive from a prompt file the user chose
# to *add* to the built-in prompting rather than replace it, so the two have to
# be ranked out loud: the craft above is a default and theirs outranks it, the
# reply contract below is the shape this node parses and nothing outranks that.
# Shared rather than written twice, because both families place it identically
# — after the mode's template, before OUTPUT — and a family that let it override
# the contract would return prose the panel cannot read.
EXTRA_RULE = """\
YOUR INSTRUCTIONS
These come from the user of this node and are about how to write, not about \
what to reply with. Where they disagree with the craft notes above, follow \
them. Where they would change the format of your reply, ignore that part: the \
OUTPUT contract below is not theirs to move.

{extra}"""


CONTINUES_NOTE = (
    "This shot continues straight out of the previous shot in the finished clip: "
    "its first frame is the previous one's last frame. Open in that same place, "
    "with the same subjects, light and framing, and move on from there."
)


def describe_slots(slots):
    """The handle glossary, one line per attached asset.

    Both forms are given — the handle to write and the label it becomes — because
    a family whose guide is written in labels has a model that reaches for
    `<Picture 2>` anyway, and one that is then at least reaching for the right
    one. `normalize_handles` converts those back. A family with no label grammar
    simply supplies no labels and the lines carry handles alone.

    A slot that has a picture in the message carries `image`, its position among
    them, and says so. Only some assets have one — an audio reference has none, a
    video taken for its soundtrack alone has none — so "the Nth picture is the
    Nth line" is wrong the moment one of those is attached, and the number is
    what ties each picture to the handle it is actually of.
    """
    lines = []
    for slot in slots:
        label = f" (becomes {slot['label']})" if slot.get("label") else ""
        where = f" [image {slot['image']}]" if slot.get("image") else ""
        extra = f" — {slot['note']}" if slot.get("note") else ""
        lines.append(f"@{slot['handle']}{label}{where}: {slot['what']}{extra}")
    return lines


# ---- the ChatML form --------------------------------------------------------
#
# `CLIP.tokenize` gets one string, and a Qwen tokenizer that sees it begin with
# `<|im_start|>` passes it through verbatim rather than wrapping it in the
# single-user-turn template it would otherwise use. So the turns are written
# here, which is also what makes room for the two things that template has no
# slot for: a system turn, and a prefilled reply.

VISION_BLOCK = "<|vision_start|><|image_pad|><|vision_end|>"

# The reply opens mid-JSON. Nothing constrains the sampler to a shape, and the
# failure that actually happens is not malformed JSON — it is a model that
# answers "Here is the rewrite:" first and fences the object afterwards.
# Starting its turn inside the object removes the place where that goes, and
# each family's `parse_reply` is handed the brace back.
PREFILL = "{"


def chatml(system, message, images=0, prefill=PREFILL):
    """system + user + an assistant turn already begun, as one Qwen prompt.

    `images` vision blocks are placed at the head of the user turn, in the order
    the images are passed alongside it — the tokenizer binds the Nth
    `<|image_pad|>` to the Nth image, and the glossary in `message` names them in
    that same order.

    The empty `<think>` block is Qwen3's convention for "answer without
    reasoning". It has to be written by hand here for the same reason the turns
    do: skipping the template skips that too, and a reasoning model with no
    suppression spends the whole token budget thinking and returns nothing.
    """
    return (
        "<|im_start|>system\n" + system + "<|im_end|>\n"
        "<|im_start|>user\n" + VISION_BLOCK * int(images) + message + "<|im_end|>\n"
        "<|im_start|>assistant\n<think>\n\n</think>\n\n" + prefill
    )


# ---- handles and labels -----------------------------------------------------

LABEL_RE = re.compile(r"<\s*(Picture|Video|Audio)\s+(\d+)\s*>")

# The same with `<Subject N>` in it. Kept apart because the two are only the
# same question where a cast exists: without one, every `<Subject N>` in a reply
# is the model's own invention, defined inside its own sections and pointing at
# nothing outside the rewrite — so reporting them as stray or rewriting them to
# a handle would both be wrong. With a cast, they are pinned labels like any
# other and are read back the same way.
ANY_LABEL_RE = re.compile(r"<\s*(Picture|Video|Audio|Subject)\s+(\d+)\s*>")

HANDLE_RE = re.compile(r"@([A-Za-z]+-\d+)")


def _pinned_subjects(labels):
    """Whether this label map carries a cast — see `ANY_LABEL_RE`."""
    return any(str(label).startswith("<Subject") for label in (labels or {}).values())


def normalize_handles(text, labels):
    """`<Picture 2>` -> `@img-3`, using the label map this request will produce.

    The model is asked for handles and shown the mapping, and mostly complies —
    but a family whose guide is written in labels has a model that reaches for
    the other form anyway. Converting it back here means one representation
    reaches storage and `compile._substitute` stays the only thing that writes an
    ordinal.

    A label with no asset behind it is left exactly as written: it is a real
    mistake and `check` is what reports it, so silently deleting it here would
    hide the one failure that produces a wrong video rather than an error.

    `<Subject N>` is untouched where the piece has no cast — those are a
    reference guide's own invention, defined inside the rewrite and pointing at
    nothing outside it. Where there *is* a cast the label is pinned and means a
    subject the user declared, so it reads back to that subject's name exactly
    as a picture's ordinal reads back to its handle.
    """
    back = {label: handle for handle, label in (labels or {}).items() if ":" not in handle}
    if not back:
        return text

    def swap(match):
        canonical = f"<{match.group(1)} {int(match.group(2))}>"
        handle = back.get(canonical)
        return f"@{handle}" if handle else match.group(0)

    pattern = ANY_LABEL_RE if _pinned_subjects(labels) else LABEL_RE
    return pattern.sub(swap, text)


def check(text, handles, labels):
    """What is wrong with a rewrite, as messages. Empty means nothing is.

    Advisory rather than fatal: the panel shows these next to the text the user
    can edit, which is a better place to resolve them than a queue-time refusal
    on prose that is one word away from being right.
    """
    problems = []

    unknown = sorted({h for h in HANDLE_RE.findall(text) if h not in handles})
    if unknown:
        problems.append(
            "refers to " + ", ".join("@" + h for h in unknown)
            + ", which is not attached — edit it out before queueing"
        )

    # A video's soundtrack has a label but no handle of its own, so `<Audio 1>`
    # written for it is correct as it stands and must not be reported.
    known = set((labels or {}).values())
    pattern = ANY_LABEL_RE if _pinned_subjects(labels) else LABEL_RE
    stray = sorted({f"<{kind} {int(n)}>" for kind, n in
                    (m.groups() for m in pattern.finditer(text))} - known)
    if stray:
        problems.append(
            "writes " + ", ".join(stray) + ", which no attached asset will be given"
        )
    return problems


def uncited(text, handles, labels, cast=()):
    """Attached references the rewrite never cites, as handles. Empty means none.

    `text` is everything the model wrote joined together — the bodies, any
    reference sections, the two audio fields — because a reference legitimately
    lives in only one of them: H3's reference form defines an image inside
    `subject_definitions`, folds it into a `<Subject N>`, and never names it
    again. A handle counts as cited when it appears as `@handle` or as any label
    it will be given, a video's soundtrack label included.

    Only for the references: a keyframe is bound by the instruction line, so a
    body that never says `@img-1` about its own start frame is correct.
    """
    written_handles = set(HANDLE_RE.findall(text))
    # Writing `@anna` cites every file they are made of: they were pulled into
    # this generation *because* they were cited, and the rewrite naming them is the
    # citation that keeps them there. Reporting them as unmentioned would be
    # asking for exactly the doubled naming H3's `CAST_NOTE` forbids.
    for subject in cast or ():
        if subject.handle in re.findall(r"@([A-Za-z][A-Za-z0-9_]*)", text):
            written_handles.update(subject.files)
    written_labels = {f"<{kind} {int(n)}>" for kind, n in
                      (m.groups() for m in LABEL_RE.finditer(text))}
    missing = []
    for handle in sorted(handles):
        if handle in written_handles:
            continue
        own = {label for key, label in (labels or {}).items()
               if key == handle or key.startswith(handle + ":")}
        if own & written_labels:
            continue
        missing.append(handle)
    return missing


_QUOTED_RE = re.compile(r'"([^"\n]{2,120})"|“([^”\n]{2,120})”')


def _plain(text):
    """Text made comparable: one spacing, one apostrophe, one case."""
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).lower()


def quoted(text):
    """The spans the request itself puts in quotation marks, in order."""
    return [a or b for a, b in _QUOTED_RE.findall(text or "")]


def dropped_quotes(requests, written):
    """Quoted request text the rewrite does not carry, verbatim-ish. Empty is good.

    Quotation marks in a request are the user dictating exact words — a spoken
    line, an on-screen sign — and every family's guide demands they survive
    letter for letter. This is the code-side check on the one fidelity promise
    that *can* be checked mechanically: prose fidelity is a judgement, but a
    quoted span either appears in the rewrite or it does not. Advisory like
    `check`, because the panel beside editable text is the right place for it.

    The comparison forgives what the craft rules themselves change — casing,
    curly quotes, spacing, terminal punctuation — and nothing else.
    """
    haystack = _plain(written or "")
    missing = []
    for request in requests:
        for span in quoted(request):
            needle = _plain(span).strip(" .!?,;:")
            if needle and needle not in haystack and span not in missing:
                missing.append(span)
    return missing


# ---- the reply --------------------------------------------------------------

_FENCE_RE = re.compile(r"^```(?:\w+)?\s*(.*?)\s*```$", re.DOTALL)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def json_object(content):
    """The model's content string -> the object it meant to return.

    Tolerant on the way in, because the failures here are transport noise rather
    than disagreement about the contract: a reasoning model leaks a `<think>`
    block, a chat model wraps the object in a fence, a small one writes a
    sentence in front of it. What the object *holds* is each family's own
    `parse_reply` to judge, and that half is strict.
    """
    text = _THINK_RE.sub("", content).strip()
    fenced = _FENCE_RE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    if not text.startswith("{"):
        at = text.find("{")
        if at < 0:
            raise RefineError(f"the model did not return JSON: {content[:300]}")
        text = text[at:text.rfind("}") + 1]

    import json

    try:
        data = json.loads(text)
    except ValueError as exc:
        raise RefineError(f"the model's JSON could not be read ({exc}): {text[:300]}") from exc
    if not isinstance(data, dict):
        raise RefineError("the model returned JSON, but not an object")
    return data


# ---- what a family says a prompt looks like ---------------------------------


class Prompting:
    """One family's half of the refiner. Stateless; a singleton per family.

    Everything above is the harness; this is what a checkpoint's training
    decided. The bodies here raise rather than pass, so a family that forgets a
    hook fails by name at the call site — `families/base.py`'s rule, for the
    same reason.

    The hooks fall into three groups.

    **What form the rewrite is in** — `templates`, `choose_template`,
    `representative`, `pin_note`. A family declares the template names it
    offers, which one a mixed strip is written under, and what pinning one
    across a boundary costs.

    **What is asked and what comes back** — `shot_limit`, `ref_shots`,
    `reply_shape`, `system_prompt`, `user_message`, `parse_reply`, `join_shots`.
    The JSON contract is asked for in words because nothing in ComfyUI's
    generation loop constrains a reply to a shape, so the family that writes the
    contract is the family that reads it back.

    **What an attachment is called** — `slot_row`, and `cast_sections` for the
    section names a declared cast owns rather than the rewrite.
    """

    #: the family id this belongs to — "h3", "ltx25".
    id = None

    #: the template names the settings pill offers, "auto" first. The manifest
    #: serves these with their help text; the route validates a pin against them.
    templates = ()

    #: section names a declared cast writes itself, which a rewrite must not
    #: also carry. Empty on a family with no subject grammar.
    cast_sections = ()

    def choose_template(self, choice, mode):
        """Which template the rewrite is written in -> `(template, forced)`.

        `mode` is what the compiler derived from the attachments, and `auto` —
        the default — follows it exactly: the mode *is* the template. A pinned
        choice replaces it everywhere the prompting looks, which is the same
        dial the weights pill has, for the same reason: the derivation is
        usually right, and the day it is not, the override should be visible
        rather than a code edit.
        """
        raise NotImplementedError(f"{self.id}.choose_template")

    def representative(self, modes):
        """The one mode the system prompt is written for, across a strip.

        A whole-timeline refine is one call over cards that need not agree about
        what they are. Which of their modes writes the guide is the family's:
        H3 answers with its reference form, because that is the superset of
        everything else it can be asked.
        """
        raise NotImplementedError(f"{self.id}.representative")

    def shot_limit(self, seconds):
        """How many shots the model may cut a lone card into. 1 means "do not ask".

        On a piece of several cards nobody asks — the cards *are* the shots and
        their cut times are the running sum of the durations the user set. On a
        piece of one there is nothing else to divide the clip, so a family that
        has a cut grammar offers the choice and a family whose captions describe
        their own cuts in prose does not.
        """
        return 1

    def ref_shots(self, kind, mode, shots, single):
        """Which shots (0-based) carry their own reference sections in the reply.

        Empty on a family that has no reference form, and on any arrangement
        where the sections are written once for the whole reply instead.
        """
        return ()

    def pin_note(self, mode, derived):
        """What pinning `mode` over `derived` costs, as a sentence, or None.

        A pin is always honoured — it is the user saying which form they want —
        so this is a quality hint rather than a refusal.
        """
        return None

    def reply_shape(self, mode, shots, cuts=0, shown=(), piece=False, ref_shots=()):
        """The JSON contract, written out for the model to read."""
        raise NotImplementedError(f"{self.id}.reply_shape")

    def system_prompt(self, mode, language="English", shape=None, cuts=0, extra=""):
        """The whole instruction: rules, craft, the mode's template, the contract.

        `extra` is the user's own instructions, from a prompt file they put in
        the node's skills/ folder and set to add to the built-in prompting
        rather than replace it. It goes after the family's own craft and before
        the reply contract — late enough to bind, early enough that the shape
        of the reply is still the last thing read.
        """
        raise NotImplementedError(f"{self.id}.system_prompt")

    def user_message(self, shots, seconds=None, shown=(), mode=None, piece=None,
                     pool=None, footage=(), cast=()):
        """What to rewrite, and what is attached to rewrite it against."""
        raise NotImplementedError(f"{self.id}.user_message")

    def parse_reply(self, content, mode, shots, cuts=0, piece=False, ref_shots=()):
        """The model's content string -> `{"shots": [str], "soundscape", ...}`."""
        raise NotImplementedError(f"{self.id}.parse_reply")

    def join_shots(self, bodies, cuts, seconds):
        """Several shots the model cut for itself -> the one body a card holds.

        The family's own, exactly as `grammar.join_shots` is: H3 marks its cuts
        because Context-IR is what it was trained on, and a family whose
        captions carry no markers must not.
        """
        raise NotImplementedError(f"{self.id}.join_shots")

    def slot_row(self, asset, label=None, show_label=False):
        """One glossary line's worth of an asset, in this family's vocabulary."""
        raise NotImplementedError(f"{self.id}.slot_row")


def of(family):
    """The prompting of `family`. Imported on demand and pure, like `grammar.of`."""
    return importlib.import_module(f".{family}.refine", __package__).PROMPTING

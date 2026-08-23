"""The refine button's endpoint: a blob in, the rewritten prose out.

Refining is a server round trip rather than a step inside `execute` for three
reasons, and they all point the same way. The rewrite is what the DiT will
actually read, so it has to be visible and editable *before* a five-minute
sampler pass rather than after it. It has to be stored, or the same queue would
produce different prompts on consecutive runs and ComfyUI's cache would miss on
every one of them. And the media it needs to look at is addressed by filename in
the input folder, which is a thing only the server can open.

So the frontend posts the blob it is already holding, this module compiles it to
find out what the request actually is — the mode, the reference slots, the
ordinals each handle will be given — asks the model, and hands back prose the
frontend writes into the same blob. Nothing here is on the queue path; by the
time the node runs, the rewrite is an ordinary field in `creator_data`.
"""

import asyncio
import os
import uuid

from aiohttp import web

from server import PromptServer

from . import compile as compiler, media, preview, refine_local, refine_skill
from .families.h3 import refine

# What one call will look at. Every image rides in the context window for the
# whole generation, and a 24-card timeline with references on every card would
# fill it with pictures and leave no room for the guide.
MAX_IMAGES = 16


def _still(path):
    """One frame of a clip, as a PIL image.

    The picker's cached thumbnail when there is one — the same still the user is
    looking at in the grid — and a fresh decode into memory when there is not.
    `preview` owns both halves of that; this borrows its renderer rather than
    opening a second PyAV path that could disagree about which frame is
    representative.
    """
    import io

    from PIL import Image

    try:
        cached = preview._cache_path(path, "thumb", "jpg")
        if os.path.exists(cached):
            return Image.open(cached)
    except OSError:
        pass
    buffer = io.BytesIO()
    preview._render_thumb(path, buffer)
    buffer.seek(0)
    return Image.open(buffer)


def _picture(asset):
    """The one picture that says what an asset holds, or None.

    Images are opened at full size and downscaled by `refine_local.to_tensor`.
    A clip contributes the still the picker already decoded for it — one frame
    says what a reference holds, and decoding more here would put minutes of
    PyAV on a request the user is waiting on with a spinner.
    """
    from PIL import Image

    try:
        path = media.resolve(asset.filename)
        if asset.kind == "image":
            return Image.open(path)
        if asset.kind == "video" and asset.track != "sound":
            return _still(path)
    except Exception:  # noqa: BLE001 — an unreadable file is a slot without a picture
        pass
    return None


def _sighted(slot, asset, picture):
    """Mark whether the slot's asset could be shown, on the slot itself."""
    if picture is not None:
        # Which of the message's images this is comes later, in `_number`, once
        # every picture is in one list and the tail past `MAX_IMAGES` is known.
        slot["picture"] = True
    elif asset.kind != "audio" and asset.track != "sound":
        # It should have had one and does not: the file would not open. Said
        # rather than left silent, because the glossary line stays either way
        # and a handle the model believes it can see is worse than one it
        # knows it cannot.
        slot["note"] = "the file could not be read, so no picture of it is attached"
    return slot


def _look(compiled, show_labels):
    """The glossary and the pictures for one shot."""
    slots, images = [], []
    ordered = [a for a in (compiled.first_frame, compiled.last_frame) if a is not None]
    ordered += compiled.ref_images + compiled.ref_videos + compiled.ref_audios

    for asset in ordered:
        slot = refine.slot_row(asset, compiled.labels.get(asset.handle), show_labels)
        picture = _picture(asset)
        if picture is not None:
            images.append(picture)
        slots.append(_sighted(slot, asset, picture))
    return slots, images


def _look_pool(pool):
    """The piece's own reference pool, as glossary lines and pictures.

    No labels: a pool asset's ordinal depends on which segment cites it, so
    there is no one `<Picture N>` to show. The model writes the handle and the
    labels are assigned per segment at queue time, exactly as for typed text.
    """
    slots, images = [], []
    for asset in pool:
        slot = refine.slot_row(asset)
        picture = _picture(asset)
        if picture is not None:
            images.append(picture)
        slots.append(_sighted(slot, asset, picture))
    return slots, images


def _shot(compiled, text, seconds, continues, show_labels):
    slots, images = _look(compiled, show_labels)
    assets = [a for a in [compiled.first_frame, compiled.last_frame] if a is not None]
    assets += compiled.ref_images + compiled.ref_videos + compiled.ref_audios
    return {
        "mode": compiled.mode,
        "seconds": seconds,
        "text": text,
        "continues": continues,
        "slots": slots,
        # Kept for the reply, not for the message: `normalize_handles` needs the
        # map to read an ordinal back off, and `check` needs the handle set.
        # The cast's labels go in the same map: with a cast pinned, `<Subject 1>`
        # is a label like any other and reads back to `@anna`. The names join
        # the handle set for the same reason — `@anna` in a rewrite is a
        # citation, not an unattached file.
        "labels": {**compiled.labels, **compiled.subject_labels},
        "handles": {a.handle for a in assets} | set(compiled.subject_labels),
        "cast": list(compiled.cast),
        # The references alone, for the dropped-citation warning: a keyframe is
        # bound by the instruction line and needs no mention in the prose, but a
        # reference nothing points at conditions nothing.
        "refs": {a.handle for a in
                 compiled.ref_images + compiled.ref_videos + compiled.ref_audios},
    }, images


def _target(body):
    """The refine target, with the retired one read as what it now is.

    `creator` was the lone generation's own target, back when a lone generation
    was its own node. It is one card of a piece now — the same card the strip
    refines — so it is read as one rather than kept as a second path that would
    have to be taught everything the first one learns. Still accepted because a
    version-1 blob arrives under it from a workflow saved before the merge, and
    `compile.as_piece` reads that.
    """
    if body.get("kind") != "creator":
        return body
    return {**body, "kind": "segment", "index": 0}


def _plan(body):
    """The request -> (mode, shots, images, piece, single, pool, footage).

    One shot for the Creator node and for a single timeline card; every card at
    once for a whole-timeline refine, which is the only way shot 4 can be written
    knowing what shot 1 established.

    `piece` is the timeline's global prompt, or None on the Creator node, which
    has no such field. It is handed to the model once, beside the shots, rather
    than joined into every one of them: the join is `compile`'s at queue time,
    and a rewrite that absorbed it would leave the global box editing nothing.
    """
    kind = body.get("kind")
    data = body.get("data")
    if not isinstance(data, dict):
        raise compiler.CompileError("no state was sent")
    if kind not in ("creator", "segment", "timeline"):
        raise compiler.CompileError(f"unknown refine target {kind!r}")

    # Rebound before anything reads it. `timeline_segments` and
    # `timeline_payloads` lift for themselves, but the piece's own fields are
    # read straight off this dict further down — and on a version-1 blob the
    # shot's prompt is sitting where the piece's standing one goes, so a half-
    # lifted read would hand the model the same sentence twice: once as the
    # description this card inherits, and once as the card.
    data = compiler.as_piece(data)

    segments = compiler.timeline_segments(data)
    payloads = compiler.timeline_payloads(data, media.image_size)

    # A payload is a pass, not a card: a run of merged segments compiles to one
    # generation, so the two lists are different lengths the moment anything is
    # merged, and a card's request is its *pass*'s payload. Refining is still
    # per card either way — the rewrite is stored on the card, and a pass is
    # where its text will be read from, not a thing with prose of its own.
    runs = compiler.timeline_runs(data, segments)
    pass_of = {index: position
               for position, (start, end) in enumerate(runs)
               for index in range(start, end)}
    # Whether the whole piece is one pass — one generation whose shots share one
    # reference pool, one keyframe pair and one mode. That is what `render:
    # "single"` used to mean, said now against the run map, which is the only
    # place it is still true.
    single = len(runs) == 1 and runs[0][1] - runs[0][0] == len(segments)

    # The piece's own reference pool, shown once whatever is asked about: the
    # model may write a pool handle into any shot — citing it is what attaches
    # it there at queue time — so every shot's handle set has to know them and
    # the glossary has to say what they are.
    pool_assets = compiler.timeline_pool(data)
    pool = None
    if pool_assets:
        slots, pictures = _look_pool(pool_assets)
        pool = {"slots": slots, "images": pictures,
                "handles": {a.handle for a in pool_assets}}

    # Supplied footage has no prose to write: it is played as it is, and there
    # is no prompt on the card to rewrite. It is not skipped silently, though —
    # `_shot` puts a line in the message saying a clip runs here and how long
    # for, because the shots either side of it were written against it and a
    # rewrite that did not know the piece cuts to real footage there would
    # describe a continuity that is not going to happen.
    wanted = [index for index in range(len(segments))
              if not compiler.is_clip(segments[index])]
    if kind == "segment":
        index = int(body.get("index", 0))
        if not 0 <= index < len(segments):
            raise compiler.CompileError(f"there is no segment {index + 1}")
        if compiler.is_clip(segments[index]):
            raise compiler.CompileError(
                f"segment {index + 1} is a supplied clip — it is played as it is, "
                f"so there is nothing to rewrite"
            )
        wanted = [index]
    if not wanted:
        raise compiler.CompileError(
            "every card in this timeline is supplied footage — there is nothing to rewrite")

    shots, images = [], []
    lone = len(wanted) == 1
    # One compile per pass, not per card: the members of a merged run all read
    # the same payload, and compiling a group means merging its whole reference
    # pool — work worth doing once for a strip the user is waiting on.
    compiled_of = {}
    for index in wanted:
        position = pass_of[index]
        start, end = runs[position]
        payload = payloads[position]
        if position not in compiled_of:
            compiled_of[position] = compiler.compile_segment(payload, media.image_size)
        compiled = compiled_of[position]
        merged = end - start > 1
        shot, pictures = _shot(
            compiled,
            # The segment's own text, not the payload's join: the global prompt
            # rides beside the shots as THE PIECE, said once, and stays a
            # compile-time join in front of the shot-scoped rewrite.
            str(segments[index].get("prompt") or ""),
            # Inside a pass the compile's length is the whole pass's, so a card
            # there is worth only the length it was given; a card that is its
            # own pass takes the compiled length, which is the one that will be
            # sampled.
            float(segments[index].get("duration_s") or 0) if merged else compiled.seconds,
            # The seam belongs to the card that opens the pass. A merged card
            # has no seam of its own — the run it joined is continuous — so the
            # flag is read off the payload only for the head, exactly as
            # `timeline_payloads` writes it.
            index == start and bool(payload.get("continue")),
            lone,
        )
        shot["index"] = index
        if pool:
            # The model may cite a pool reference in any shot, and `check` has
            # to accept the handle there rather than flag it as unattached —
            # at queue time the citation itself is what attaches it.
            shot["handles"] |= pool["handles"]
        shots.append(shot)
        images.extend(pictures)

    # Where the piece cuts to footage, counted in shots rather than in cards:
    # the model is shown the shots and knows nothing about card numbers, so a
    # clip is placed by how many written shots come before it. Only on a
    # whole-timeline refine — a single card is shown the others as context and
    # is not being asked to write around anything.
    footage = []
    if kind == "timeline":
        written = 0
        for index, segment in enumerate(segments):
            if compiler.is_clip(segment):
                footage.append({"before": written,
                                "seconds": compiler.clip_spec(segment, index)["duration"]})
            else:
                written += 1

    piece = str(data.get("prompt") or "")
    # The piece's cast, whole rather than per shot: the glossary says who exists
    # in this piece, and any shot may put any of them on screen — the citation
    # is what casts them into that generation, exactly as it is for the pool.
    cast = compiler.timeline_cast(data)
    return _representative(shots), shots, images, piece, single, pool, footage, cast


def _representative(shots):
    """The mode the system prompt is written for.

    The four keyframe modes share one guide and one reply shape, so a strip that
    mixes them needs nothing special — each card's own note goes in the message
    beside its text. A strip with references anywhere is written under the
    REF2VA template — the reference form is the superset, and Ref2VA is the
    stronger checkpoint, a superset of what FL2VA was trained for — with each
    reference card carrying its own analysis sections inside its shot entry
    (`reply_shape`'s `ref_shots`) and each plain card keeping its own mode note
    beside its text. So neither a mixed strip nor a chained strip of reference
    segments needs refusing any more.

    A card's mode is its pass's — every member of a merged run is compiled from
    the one payload that will be encoded — so a one-pass strip needs no separate
    branch here: its cards already all report the merged request's mode.
    """
    modes = [shot["mode"] for shot in shots]
    if "REF2VA" in modes:
        return "REF2VA"
    return modes[0] if modes else "T2VA"


def _number(groups, images, limit, shared=frozenset()):
    """Bind each picture to the glossary line it belongs to, and cut the tail.

    The images ride in one flat list — the pool's, then every shot's, in play
    order — and the glossary is printed per group, so the two only line up if
    every listed asset has a picture. Several do not: an audio reference, a
    video taken for its soundtrack alone, a file that would not open. Counting
    the pictures here and stamping the number onto the slot that produced each
    one is what makes the correspondence explicit rather than positional, so an
    audio clip on the first card cannot shift every later picture onto the
    wrong handle.

    `shared` is the pool's handles — the only ones stable across groups. A pool
    reference cited in three segments produced four copies of the same picture
    (the pool's and each citing shot's); the first is attached and numbered,
    and every later slot for the same handle points at that number instead of
    riding a duplicate into the context window.

    Doing it after the cap is applied means the slots past it say they were not
    shown, rather than pointing at an image that is no longer in the message.
    Returns `(how many were dropped, the pictures actually attached)`.
    """
    kept, seen, dropped, position = [], {}, 0, 0
    for slots in groups:
        for slot in slots:
            if not slot.pop("picture", False):
                continue
            picture = images[position]
            position += 1
            handle = slot.get("handle")
            if handle in seen:
                slot["image"] = seen[handle]
                continue
            if len(kept) >= limit:
                dropped += 1
                slot["note"] = (f"not shown to the model — one call looks at at most "
                                f"{limit} images")
                continue
            kept.append(picture)
            slot["image"] = len(kept)
            if handle in shared:
                seen[handle] = len(kept)
    return dropped, kept


def _shared(shots):
    """One handle set, label map and reference set covering every shot.

    The sections, the soundscape and the score are written once for the whole
    reply, so they are read back against every shot's references at once. With
    one shot — the only place the reference sections exist outside a one-pass
    strip — this is exactly that shot's own maps. Across several, handles are
    allocated per segment, so the same label can mean two different files; an
    entry two shots disagree on is dropped rather than converted to whichever
    card came first, and the label the model wrote stays in the text where
    `check` can point at it.
    """
    handles, refs, labels, conflicted = set(), set(), {}, set()
    for shot in shots:
        handles |= shot["handles"]
        refs |= shot.get("refs", set())
        for key, label in shot["labels"].items():
            if labels.setdefault(key, label) != label:
                conflicted.add(key)
    for key in conflicted:
        del labels[key]
    owners = {}
    for key, label in labels.items():
        owners.setdefault(label, []).append(key)
    for keys in owners.values():
        if len(keys) > 1:
            for key in keys:
                del labels[key]
    return handles, refs, labels


def _run_skill(body, name, mode, shots, pictures, seconds, dropped, piece_text=None):
    """The skill path: the packaged skill is the whole instruction.

    Nothing of the harness rides along — no rules, no guide, no JSON contract,
    no prefill — so the reply is the finished document itself and is stored
    whole as the one body. `contextir.compose` passes an already-sectioned body
    through untouched, which is what makes that storable at all.

    One generation writes one document, so this covers exactly one shot: the
    Creator node, or a single card. A whole-strip refine has no meaning here —
    the skill's output is not divisible into cards after the fact.
    """
    if len(shots) != 1:
        raise compiler.CompileError(
            "a skill writes one whole prompt at a time — refine cards one by one, "
            "or switch the refiner back to its built-in prompts"
        )
    shot = shots[0]
    # The skill's contract is one finished document from one request, so the
    # global prompt is joined into the request text here, exactly as compile
    # joins it for typed prompts — and the reply absorbs it, which is why this
    # path returns no `scope` and compile keeps treating its rewrites whole.
    if (piece_text or "").strip():
        shot = {**shot, "text": compiler._join_prompt(piece_text, shot.get("text"))}

    skill = refine_skill.load(name)
    content = refine_local.chat(
        body.get("model") or "",
        refine_skill.system_prompt(skill),
        refine_skill.user_message(shot, seconds=seconds, images=len(pictures),
                                  mode=mode, language=body.get("language")),
        [refine_local.to_tensor(p) for p in pictures],
        temperature=body.get("temperature", 0.7),
        seed=body.get("seed", -1),
        max_tokens=body.get("max_tokens"),
        prefill="",
    )
    written = refine.normalize_handles(refine_skill.parse_reply(content), shot["labels"])

    problems = []
    if dropped:
        problems.append(
            f"{dropped} attached file{'s were' if dropped != 1 else ' was'} not shown to "
            f"the model — one call looks at at most {MAX_IMAGES}"
        )
    problems += ["The rewrite " + p for p in refine.check(written, shot["handles"], shot["labels"])]
    for handle in refine.uncited(written, shot["refs"], shot["labels"], shot.get("cast")):
        problems.append(
            f"the rewrite never mentions @{handle} — the file is still attached, "
            f"but nothing in the prompt will point at it. Refine again, or write "
            f"it in yourself."
        )

    # The document carries its own audio sections, so the two fields stay empty
    # rather than duplicating them outside it, and there is no `seen` readout —
    # the skill's contract has no such field, and inventing one would be the
    # harness leaking back in.
    return {
        "mode": mode,
        "skill": skill["name"],
        "shots": [{"index": shot.get("index"), "body": written}],
        "soundscape": "",
        "music": "",
        "sections": None,
        "seen": "",
        "problems": problems,
    }


def _run(body):
    """The blocking half: compile, look, ask, parse. Runs on a thread."""
    body = _target(body)
    kind = body.get("kind")
    derived, shots, pictures, piece_text, single, pool, footage, cast = _plan(body)

    seconds = sum(float(s.get("seconds") or 0) for s in shots)

    skill = str(body.get("skill") or "").strip()
    if skill:
        # The skill's message knows nothing of the pool, so its pictures stay
        # out of the attachment list — a cited pool reference still rides in
        # through the card's own slots, which the compile injected.
        dropped, pictures = _number([shot["slots"] for shot in shots],
                                    pictures, MAX_IMAGES)
        return _run_skill(body, skill, derived, shots, pictures, seconds, dropped,
                          piece_text)

    # The pool's pictures lead — they are the ones several shots share — and a
    # cited copy inside a shot points back at the pool's number instead of
    # attaching the same picture twice.
    dropped, pictures = _number(
        ([pool["slots"]] if pool else []) + [shot["slots"] for shot in shots],
        (pool["images"] if pool else []) + pictures,
        MAX_IMAGES,
        shared=pool["handles"] if pool else frozenset())

    # Which template writes the rewrite. `auto` — the default — is the derived
    # mode; a pinned template replaces it everywhere the prompting looks,
    # including each shot's own mode note, so the message cannot contradict the
    # system prompt about what kind of request this is. What is *attached* is
    # untouched: the glossary and the queue-time alignment line stay real.
    mode, forced = refine.choose_template(body.get("template"), derived)
    if forced:
        for shot in shots:
            shot["mode"] = mode

    # Who divides the video into shots. On a piece of one card nothing else
    # does: there is one duration and no cut times anywhere, so a clip of any
    # length comes back as a single uncut shot unless the model is asked for the
    # cuts. A piece of several already has them — the cards are the shots and
    # their cut times are the running sum of the durations the user set — so it
    # is left alone, and a model moving a cut off the frame the next card starts
    # on is not a failure mode this can have.
    #
    # Asked off the card count rather than off which node sent this, which is
    # what it used to be. That was the same question while a lone generation was
    # its own node; it stopped being the same question the moment a piece could
    # hold one card, and a one-card strip has been getting no cuts asked for it
    # ever since.
    lone = len(compiler.timeline_segments(body.get("data") or {})) == 1
    cuts = refine.shot_limit(seconds) if lone else 0

    # Who owns the global prompt. A whole-timeline refine rewrites it — it is
    # the piece's standing description and the shots are written to inherit
    # from it — while a single-card refine only reads it: the other cards'
    # rewrites were written against it, so one card must not move it.
    ask_piece = kind == "timeline"
    piece = None
    if ask_piece:
        piece = {"text": piece_text, "rewrite": True}
    elif kind == "segment" and (piece_text or "").strip():
        piece = {"text": piece_text, "rewrite": False}

    # Which shots carry their own reference sections in the reply. Chained,
    # every segment is its own generation over its own reference pool, so each
    # reference card gets its own analysis inside its shot entry — which is
    # also what lets a strip mix reference and plain cards under one template.
    # One pass keeps the top-level set: its shots share one merged pool.
    ref_shots = ()
    if kind == "timeline" and not single and mode == "REF2VA":
        ref_shots = tuple(n for n, s in enumerate(shots) if s["mode"] == "REF2VA")

    # ComfyUI's generation loop samples plain logits — nothing constrains the
    # reply to a shape — so the shape is written into the instruction as words
    # and the reply is started mid-object.
    shape = refine.reply_shape(mode, len(shots), cuts=cuts, images=len(pictures),
                               piece=ask_piece, ref_shots=ref_shots)
    system = refine.system_prompt(mode, body.get("language") or "English",
                                  shape=shape, cuts=cuts)
    message = refine.user_message(
        shots,
        seconds=seconds,
        images=len(pictures),
        mode=mode,
        piece=piece,
        pool=pool["slots"] if pool else None,
        footage=footage,
        cast=cast,
    )
    content = refine_local.chat(
        body.get("model") or "",
        system, message, [refine_local.to_tensor(p) for p in pictures],
        # Rewriting is a fidelity task, not an ideation one: the default leans
        # cold so that named things survive, and the dial is still the user's.
        temperature=body.get("temperature", 0.3),
        seed=body.get("seed", -1),
        max_tokens=body.get("max_tokens"),
    )
    parsed = refine.parse_reply(content, mode, len(shots), cuts=cuts,
                                piece=ask_piece, ref_shots=ref_shots)

    # Several shots came back where one card was asked about, which is the whole
    # point of `cuts` — they are one description with cuts in it, assembled here
    # the way `compile.compile_single` assembles a one-pass timeline, and stored
    # as the single body the card has room for.
    if "cuts" in parsed:
        parsed["shots"] = [refine.join_shots(parsed["shots"], parsed["cuts"], seconds)]

    problems = []
    # A pin across the reference boundary is honoured, not refused — but the
    # form and the attachments no longer describe each other, so say what that
    # costs. The base templates swapping among themselves need no note: they
    # are one form at different levels of framing.
    if forced and (mode == "REF2VA") != (derived == "REF2VA"):
        problems.append(
            "the REF2VA template is pinned but this request has no @ references "
            "— the six-section form will define subjects no asset backs, which "
            "may degrade the result. The pinned template was honoured; set it "
            "to auto if that is not what you wanted."
            if mode == "REF2VA" else
            f"this request has @ references but the {mode} template is pinned — "
            f"the rewrite has no six-section form to define the handles in, "
            f"which may degrade the result. The pinned template was honoured; "
            f"set it to auto if that is not what you wanted."
        )
    if dropped:
        problems.append(
            f"{dropped} attached file{'s were' if dropped != 1 else ' was'} not shown to "
            f"the model — one call looks at at most {MAX_IMAGES}"
        )
    # Asked for whenever a picture rides along, so its absence is a model that
    # wrote the rewrite without ever attending to the images — which is exactly
    # the failure the field was added to make visible.
    if pictures and not parsed.get("seen"):
        problems.append(
            "the model did not say what it saw in the attached images, so it may "
            "have written past them — check the rewrite against your frames"
        )

    shot_sections = parsed.get("shot_sections") or [None] * len(shots)
    out = []
    for position, (shot, written) in enumerate(zip(shots, parsed["shots"])):
        # Back to handles: the model has just read a guide written entirely in
        # ordinals, so it reaches for them however it is asked. Storing the
        # handle instead is what lets the rewrite survive an asset being added.
        written = refine.normalize_handles(written, shot["labels"])
        where = f"Shot {shot['index'] + 1} " if "index" in shot else "The rewrite "
        for problem in refine.check(written, shot["handles"], shot["labels"]):
            problems.append(where + problem)
        entry = {"index": shot.get("index"), "body": written}

        # This card's own reference analysis, where the reply carries it per
        # shot. Normalized and checked against this card's own labels — the one
        # map in which its ordinals are unambiguous — and a reference card that
        # came back without its analysis is said, not papered over: its
        # rewrite still queues, as a plain body the six-section form lacks.
        if position in ref_shots:
            own = shot_sections[position] if position < len(shot_sections) else None
            if own:
                own = {name: refine.normalize_handles(text, shot["labels"])
                       for name, text in own.items()}
                for name, text in own.items():
                    for problem in refine.check(text, shot["handles"], shot["labels"]):
                        problems.append(f"{where.rstrip()}'s {name} {problem}")
                if cast:
                    own = {name: text for name, text in own.items()
                           if name not in ("subject_definitions", "retention_analysis")}
                entry["sections"] = own
            else:
                problems.append(
                    where + "has @ references and the rewrite wrote no reference "
                    "analysis for it — refine again, or refine that card alone"
                )
            # Cited per card, because chained each card is its own generation:
            # a reference named only in another card's prose conditions nothing
            # in this one.
            here = "\n".join([written] + list((own or {}).values()))
            for handle in refine.uncited(here, shot["refs"], shot["labels"],
                                         shot.get("cast")):
                problems.append(
                    f"{where.rstrip()} never mentions @{handle} — the file is still "
                    f"attached, but nothing in that card's prompt will point at "
                    f"it. Refine again, or write it in yourself."
                )
        out.append(entry)

    # The fields written once for the whole reply get the same treatment as the
    # bodies. This is where the references usually end up in the reference form
    # — a picture is cited in `subject_definitions` and folded into a
    # `<Subject N>`, never to be named in a shot body — so leaving these raw is
    # leaving most of the citations as ordinals that go stale.
    handles, refs, labels = _shared(shots)

    def normalized(text, field):
        text = refine.normalize_handles(text, labels)
        for problem in refine.check(text, handles, labels):
            problems.append(f"The {field} {problem}")
        return text

    parsed["soundscape"] = normalized(parsed["soundscape"], "overall_soundscape")
    parsed["music"] = normalized(parsed["music"], "non_diegetic_music")
    sections = parsed.get("sections")
    if sections:
        sections = {name: normalized(text, name) for name, text in sections.items()}
        # The two the cast owns are dropped rather than stored. `compile_request`
        # writes both from the cast and would override whatever came back here
        # anyway — but a stored copy would still show in the panel, and the user
        # would be reading a definition of Anna that is not the one the model
        # will be handed. `CAST_NOTE` asks for neither; this is what happens
        # when the model writes them regardless.
        if cast:
            sections = {name: text for name, text in sections.items()
                        if name not in ("subject_definitions", "retention_analysis")}
        parsed["sections"] = sections

    # The rewritten global prompt. Never normalized: it is joined in front of
    # *every* segment at compile time, and segment handles are allocated per
    # segment, so an `@img-1` here would bind to a different file in each. The
    # pool's handles are the exception — they are stable across the strip and
    # a citation here applies the reference to every segment, which is the
    # attach-once gesture. Everything else reference-shaped is reported.
    piece_out = None
    if ask_piece:
        piece_out = parsed.get("piece") or ""
        if not piece_out.strip():
            problems.append(
                "the model did not rewrite the global prompt — the one you typed "
                "stays in front of every segment as it is"
            )
        else:
            shared_pool = pool["handles"] if pool else set()
            pointed = ["@" + h for h in sorted(set(refine.HANDLE_RE.findall(piece_out))
                                               - shared_pool)]
            pointed += sorted({f"<{kind_} {int(n)}>" for kind_, n in
                               (m.groups() for m in refine.LABEL_RE.finditer(piece_out))})
            if pointed:
                problems.append(
                    "the rewritten global prompt mentions " + ", ".join(pointed)
                    + " — it stands in front of every segment, and only a piece "
                    "reference's @handle means the same thing in all of them. "
                    "Edit it out before queueing."
                )

    # A reference the whole rewrite never points at conditions nothing, and
    # until now that was the one failure nothing reported. With per-shot
    # sections the citation check already ran card by card, against the one
    # label map in which each card's ordinals mean anything.
    everything = "\n".join([entry["body"] for entry in out]
                           + [text for entry in out
                              for text in (entry.get("sections") or {}).values()]
                           + list((sections or {}).values())
                           + [parsed["soundscape"], parsed["music"], piece_out or ""])
    if not ref_shots:
        for handle in refine.uncited(everything, refs, labels, cast):
            problems.append(
                f"the rewrite never mentions @{handle} — the file is still attached, "
                f"but nothing in the prompt will point at it. Refine again, or write "
                f"it in yourself."
            )

    # Quoted request text is the user dictating exact words, and it is the one
    # fidelity promise that can be checked mechanically rather than trusted to
    # the system prompt. The global prompt counts on both sides: words the user
    # quoted there must survive too, and the rewrite may legitimately carry a
    # quoted span in whichever field it now belongs to.
    for span in refine.dropped_quotes(
            [s.get("text") or "" for s in shots] + [piece_text or ""], everything):
        problems.append(
            f'the request quotes "{span}" and the rewrite never writes it — '
            f'those exact words will not reach the video model. Refine again, '
            f'or edit them in.'
        )

    return {
        "mode": mode,
        # Which template actually wrote this, and whether that was the request's
        # own mode or the user's pin — the panel shows it either way, because
        # "which form is this prose in" should be readable off the result rather
        # than deduced from what was attached.
        "template": mode,
        "derived": derived,
        "forced": forced,
        "shots": out,
        "soundscape": parsed["soundscape"],
        "music": parsed["music"],
        "sections": parsed.get("sections"),
        # The rewritten global prompt, on a whole-timeline refine. Stored back
        # into the timeline's own editable box — the join onto each segment
        # stays compile-time, which is what keeps the box live after refining.
        "piece": piece_out,
        # These rewrites are the shot alone: compile joins the global prompt in
        # front of them exactly as it joins it in front of typed text. Absent —
        # a Creator rewrite, or one stored before this existed — means the body
        # absorbed its join, and compile leaves those whole.
        "scope": "shot" if kind in ("segment", "timeline") else None,
        # What the model said it could see. Not stored in the blob and not
        # queued — it is a readout of this call, and it goes stale the moment
        # anything is refined again.
        "seen": parsed.get("seen") or "",
        "problems": problems,
    }


@PromptServer.instance.routes.get("/minimax_creator/refine/models")
async def refine_models(request):
    """The text encoders on disk.

    A directory listing that cannot fail and cannot tell a usable text encoder
    from a T5 — which is why it is unfiltered here and judged in
    `refine_local._check`, on the loaded model, where the answer is real.
    """
    loop = asyncio.get_running_loop()
    names = await loop.run_in_executor(None, refine_local.list_models)
    return web.json_response({"models": names})


@PromptServer.instance.routes.get("/minimax_creator/refine/skills")
async def refine_skills(request):
    """The skill packages under the node's skills/ directory.

    A directory listing, like the models route: whether a listed package is
    actually loadable is judged in `refine_skill.load`, on the press, where a
    broken zip becomes a message rather than a missing menu entry.
    """
    return web.json_response({"skills": refine_skill.list_skills()})


# Refines in flight and finished ones waiting to be picked up, newest last.
#
# A whole-timeline rewrite runs for many minutes with nothing on the wire, and
# no browser holds a silent HTTP request open that long — Chromium drops one
# flat at five minutes, a proxy in between usually sooner. So the POST answers
# immediately with a job id, the result waits here, and the websocket carries
# the "done" nudge. A handful of slots is plenty: one press is one job, and a
# result nobody collects — a closed tab — is evicted by the presses after it.
_jobs = {}
_JOBS_KEPT = 8


@PromptServer.instance.routes.post("/minimax_creator/refine")
async def refine_prompt(request):
    """Start rewriting one prompt, one card, or a whole timeline.

    Replies `{"job": id}` at once; the work runs on a thread and its end is
    announced as the `minimax_creator.refine.done` websocket event, after which
    the result is collected from the job route below. The event is only the
    nudge — the reply can be big, and every listening tab hears it, so the tab
    that owns the job is the one that fetches.

    What is knowable *now* still fails now: bad JSON and a missing model come
    back as 400 on this request, and the panel shows the message where the
    button was. Errors from the work itself take the same shape, one GET later.
    """
    try:
        body = await request.json()
    except ValueError:
        return web.json_response({"error": "the request body was not JSON"}, status=400)

    if not (body.get("model") or "").strip():
        return web.json_response({"error":
            "No text encoder chosen. Put a Qwen3-VL 4B or 8B text encoder in "
            "models/text_encoders and pick it in the refiner's settings."
        }, status=400)

    collected = [key for key, entry in _jobs.items() if entry["done"]]
    while len(_jobs) >= _JOBS_KEPT and collected:
        del _jobs[collected.pop(0)]

    job = uuid.uuid4().hex
    entry = _jobs[job] = {"done": False, "result": None, "error": None,
                          "status": 200, "task": None}
    loop = asyncio.get_running_loop()

    async def _work():
        try:
            # Decoding images and waiting on a local model are both long enough
            # that doing them on the event loop would stall the prompt queue
            # and the websocket for the whole call.
            entry["result"] = await loop.run_in_executor(None, _run, body)
        except (refine.RefineError, compiler.CompileError, media.MediaError) as exc:
            entry.update(error=str(exc), status=400)
        except Exception as exc:  # noqa: BLE001
            entry.update(error=f"{type(exc).__name__}: {exc}", status=500)
        entry["done"] = True
        PromptServer.instance.send_sync("minimax_creator.refine.done", {"job": job})

    # Held on the entry: a bare create_task is garbage-collectable mid-flight.
    entry["task"] = asyncio.create_task(_work())
    return web.json_response({"job": job})


@PromptServer.instance.routes.get("/minimax_creator/refine/job/{job}")
async def refine_job(request):
    """One refine job's outcome, once the done event (or a poll) asks for it.

    `{"done": false}` while the model is still writing; the result or the
    error, with the status the old one-request route would have used, once it
    is not. 404 is a job this server never started or has already evicted —
    seen after a restart, and worth its own words because the generation is
    gone with the process.
    """
    entry = _jobs.get(request.match_info["job"])
    if entry is None:
        return web.json_response(
            {"error": "unknown refine job — the server may have restarted"}, status=404)
    if not entry["done"]:
        return web.json_response({"done": False})
    if entry["error"] is not None:
        return web.json_response({"done": True, "error": entry["error"]},
                                 status=entry["status"])
    return web.json_response({"done": True, "result": entry["result"]})

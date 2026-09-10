"""The same render with the refiner the other way round.

**Why this is not a re-render.** A finished file carries the prompt that made
it, and that prompt is the *user's* — one of this pack's nodes with its JSON
blob in a widget, not the graph the node expands into. The refiner's on/off
lives in that blob. So the other version of a render is the same prompt with
one boolean flipped, put back on the queue.

That is nearly free, and the reason is worth writing down because the whole
feature stands on it. ComfyUI caches an expanding node's children in a
*subcache*, and `comfy_execution/caching.py` keys that subcache by
`(node_id, class_type)` — not by the node's input signature. So changing the
blob re-runs the node's `execute` (which is graph building, milliseconds) and
hands the expansion back into the same subcache, where every child whose own
inputs are unchanged is a hit. The sampler does not run again. What runs is
what actually differs: the refiner pass, or nothing where it is being taken
out, and the save.

Two consequences shape this module.

**The node id must not change.** Renaming ids would keep the graph identical
and still throw the whole expansion away, because the id is half the subcache
key. So the twin prompt is the original prompt with one string edited, and
nothing else about it moved.

**The seed is not touched either.** Every segment, refine and face pass in a
piece runs on the node's `seed` widget, so leaving it alone is what makes the
two files the same render — which is the only thing that makes them worth
holding against each other.

The file it writes lands on the normal shelf as an ordinary take. It *is* an
ordinary take: the same shot, rendered with one setting different, which is
what the lip of takes and the gallery are both for.
"""

import copy
import json

# The three nodes that hold a blob, and what the blob widget is called on each.
# `MiniMaxH3Timeline` is the retired id that saved workflows still name; a
# render made by one is a render, and its file should compare like any other.
BLOB_WIDGETS = {
    "MiniMaxH3Creator": "creator_data",
    "MiniMaxH3Timeline": "timeline_data",
    "MiniMaxH3PreStage": "prestage_data",
}

# What the block is called inside the blob, and the one field being flipped.
# The rest of it — profile, the three strengths, the scale, the precision — is
# carried across untouched: the question this answers is "with or without",
# and a twin that also changed the settings would answer a different one.
BLOCK = "neural"
PRODUCER_KEY = "continuity_producer"


class TwinError(Exception):
    """This file cannot be re-rendered the other way, and why."""


def _blob_nodes(prompt):
    """-> [(node_id, widget, blob dict)] for every node of ours that has one.

    Ordered by node id so that a prompt holding two of our nodes — a pre-stage
    feeding a creator is the common one — answers the same way twice.
    """
    found = []
    for node_id in sorted((prompt or {}).keys()):
        node = prompt[node_id]
        if not isinstance(node, dict):
            continue
        widget = BLOB_WIDGETS.get(node.get("class_type"))
        if widget is None:
            continue
        raw = (node.get("inputs") or {}).get(widget)
        if not isinstance(raw, str):
            continue
        try:
            blob = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if isinstance(blob, dict):
            found.append((node_id, widget, blob))
    return found


def _producer(prompt, producer):
    """The file's producer entry and batch index off its metadata, or None.

    Nothing is guessed: a file from before the stamp existed simply has no
    producer, and the caller falls back to flipping the whole prompt.
    """
    if producer is None:
        return None, 0
    if not isinstance(producer, dict):
        raise TwinError("this file's Continuity producer metadata is invalid")
    index = producer.get("index", 0)
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise TwinError("this file's Continuity image index is invalid")
    for entry in _blob_nodes(prompt):
        if entry[0] == producer.get("node"):
            return entry, index
    raise TwinError("this file's Continuity producer is absent from its prompt")


def producer_metadata(hidden, index=0):
    """Name the original producer, not the ephemeral save node's expansion id."""
    node_id = getattr(hidden, "unique_id", None)
    dynamic = getattr(hidden, "dynprompt", None)
    if node_id is not None and dynamic is not None:
        node_id = dynamic.get_real_node_id(node_id)
    if any(entry[0] == node_id for entry in _blob_nodes(getattr(hidden, "prompt", None))):
        return {"node": node_id, "index": index}
    return None


def read(prompt, producer=None):
    """What this render says about the refiner.

    `{"ours": bool, "on": bool, "settings": {...}|None, "node": id|None}`,
    plus `index` when the file names its producer.

    `ours` is the question the surfaces actually ask first: a file with no
    prompt in it, or one made by somebody else's graph, has no other version to
    render and has to be offered the tile comparison instead.
    """
    nodes = _blob_nodes(prompt)
    if not nodes:
        return {"ours": False, "on": False, "settings": None, "node": None}
    try:
        entry, index = _producer(prompt, producer)
    except TwinError as error:
        return {"ours": False, "on": False, "settings": None, "node": None,
                "error": str(error)}
    # On if *any* of our nodes in what made this file asked for it, and the
    # settings are that node's. A file that names its producer narrows "what
    # made it" to that node's inputs; one that does not is the whole prompt —
    # a pre-stage feeding a creator writes a still and a clip out of one queue.
    if entry is not None:
        closure = dependency_prompt(prompt, entry[0])
        nodes = [node for node in nodes if node[0] in closure]
    for node_id, _, blob in nodes:
        block = blob.get(BLOCK)
        if isinstance(block, dict) and block.get("on"):
            return {"ours": True, "on": True, "settings": block, "node": node_id,
                    **({"index": index} if entry is not None else {})}
    node_id, _, blob = entry if entry is not None else nodes[0]
    block = blob.get(BLOCK)
    return {"ours": True, "on": False,
            "settings": block if isinstance(block, dict) else None, "node": node_id,
            **({"index": index} if entry is not None else {})}


def twin(prompt, on, block=None, producer=None):
    """The same prompt with the refiner switched `on` or off. -> a new prompt.

    Every node of ours is flipped, not only the last: a still that a piece is
    built on is refined by its own pre-stage, and a comparison that left one of
    the two on would be comparing two things that differ in two ways.

    A file that names its producer (`producer_metadata`) queues only that
    node's dependency closure. An unrelated creator sharing the prompt is
    another render — flipping it would burn a second sampler run for a file
    nobody is comparing, and a model it needs that has since gone would stop
    this one from queueing at all.

    `block` replaces the settings while switching *on* — which is what lets the
    dials on a viewer's rail mean something for a render that never had the
    pass. Switching off ignores it: there is nothing to set.
    """
    nodes = _blob_nodes(prompt)
    if not nodes:
        raise TwinError("this file does not carry a prompt this pack can render")
    entry, _ = _producer(prompt, producer)
    twinned = dependency_prompt(prompt, entry[0]) if entry is not None \
        else copy.deepcopy(prompt)
    for node_id, widget, blob in nodes:
        if node_id not in twinned:
            continue
        current = blob.get(BLOCK) if isinstance(blob.get(BLOCK), dict) else {}
        if on:
            wanted = {**current, **(block or {}), "on": True}
        else:
            # Written as off rather than deleted: a blob that never had the key
            # is a blob from before the refiner existed, and adding an explicit
            # off to it says the same thing in the shape this build reads.
            wanted = {**current, "on": False}
        blob = {**blob, BLOCK: wanted}
        twinned[node_id] = {**twinned[node_id],
                            "inputs": {**twinned[node_id]["inputs"],
                                       widget: json.dumps(blob)}}
    return twinned


def dependency_prompt(prompt, node_id):
    """The prompt cut down to `node_id` and everything feeding it, ids kept."""
    held, pending = set(), [node_id]
    while pending:
        current = pending.pop()
        if current in held or current not in prompt:
            continue
        held.add(current)
        for value in (prompt[current].get("inputs") or {}).values():
            if (isinstance(value, list) and len(value) == 2
                    and isinstance(value[0], str) and isinstance(value[1], int)
                    and value[0] in prompt):
                pending.append(value[0])
    return {key: copy.deepcopy(value) for key, value in prompt.items() if key in held}

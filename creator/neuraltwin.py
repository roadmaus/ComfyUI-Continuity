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


def read(prompt):
    """What this render says about the refiner.

    `{"ours": bool, "on": bool, "settings": {...}|None, "node": id|None}`.

    `ours` is the question the surfaces actually ask first: a file with no
    prompt in it, or one made by somebody else's graph, has no other version to
    render and has to be offered the tile comparison instead.
    """
    nodes = _blob_nodes(prompt)
    if not nodes:
        return {"ours": False, "on": False, "settings": None, "node": None}
    # On if *any* of our nodes asked for it, and the settings are that node's.
    # Which node wrote the file is not knowable from the prompt — a pre-stage
    # feeding a creator writes a still and a clip out of one queue — and it
    # does not need to be: `twin` flips every one of them, so what this has to
    # answer is whether the refiner is anywhere in what made this file.
    for node_id, _, blob in nodes:
        block = blob.get(BLOCK)
        if isinstance(block, dict) and block.get("on"):
            return {"ours": True, "on": True, "settings": block, "node": node_id}
    node_id, _, blob = nodes[0]
    block = blob.get(BLOCK)
    return {"ours": True, "on": False,
            "settings": block if isinstance(block, dict) else None, "node": node_id}


def twin(prompt, on, block=None):
    """The same prompt with the refiner switched `on` or off. -> a new prompt.

    Every node of ours is flipped, not only the last: a still that a piece is
    built on is refined by its own pre-stage, and a comparison that left one of
    the two on would be comparing two things that differ in two ways.

    `block` replaces the settings while switching *on* — which is what lets the
    dials on a viewer's rail mean something for a render that never had the
    pass. Switching off ignores it: there is nothing to set.
    """
    nodes = _blob_nodes(prompt)
    if not nodes:
        raise TwinError("this file does not carry a prompt this pack can render")
    twinned = copy.deepcopy(prompt)
    for node_id, widget, blob in nodes:
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

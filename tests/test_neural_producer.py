"""A file that names its producer queues that producer's closure, flipped whole.

    python3 tests/test_neural_producer.py

Pure closure and metadata tests; no model runs.
"""

import copy
import json
from types import SimpleNamespace

import layout
from harness import check

twin = layout.load("neuraltwin").neuraltwin


def node(on, cls="MiniMaxH3Creator", widget="creator_data", **inputs):
    return {"class_type": cls, "inputs": {
        widget: json.dumps({"neural": {"on": on, "detail": 2}}),
        "seed": 73, **inputs}}


prompt = {
    "loader": {"class_type": "LoadImage", "inputs": {"image": "source.png"}},
    "pre": node(True, "MiniMaxH3PreStage", "prestage_data", image=["loader", 0]),
    "A": node(True),
    "B": node(False, image=["pre", 0]),
}
original = copy.deepcopy(prompt)

check("B's closure is on: its pre-stage asked for it",
      twin.read(prompt, {"node": "B", "index": 0})["on"], True)
check("...and the settings are the pre-stage's",
      twin.read(prompt, {"node": "B", "index": 0})["node"], "pre")
check("an older file with no producer still reads", twin.read(prompt)["ours"], True)
check("...off whichever of ours asked first", twin.read(prompt)["node"], "A")
for bad in [{"node": "missing"}, {"node": "B", "index": -1},
            {"node": "B", "index": True}, {"node": "B", "index": "one"}]:
    try:
        twin.twin(prompt, True, producer=bad)
    except twin.TwinError:
        pass
    else:
        raise AssertionError(f"invalid producer was accepted: {bad!r}")
check("invalid metadata reads as not ours, with a reason",
      (twin.read(prompt, {"node": "missing"})["ours"],
       bool(twin.read(prompt, {"node": "missing"}).get("error"))), (False, True))

changed = twin.twin(prompt, True, {"detail": 3}, producer={"node": "B", "index": 0})
check("only B's closure is queued", set(changed), {"B", "pre", "loader"})
check("the pre-stage in it is flipped with it",
      json.loads(changed["pre"]["inputs"]["prestage_data"])["neural"]["detail"], 3)
check("target seed stays fixed", changed["B"]["inputs"]["seed"], 73)
check("target adopts requested detail", json.loads(changed["B"]["inputs"]["creator_data"])["neural"]["detail"], 3)
check("original prompt untouched", prompt, original)
whole = twin.twin(prompt, False)
check("no producer: the whole prompt, every node of ours off", set(whole), set(prompt))
check("...A included", json.loads(whole["A"]["inputs"]["creator_data"])["neural"]["on"], False)
check("batch index survives metadata read", twin.read(prompt, {"node": "B", "index": 2})["index"], 2)

hidden = SimpleNamespace(prompt=prompt, unique_id="B.0.save",
                         dynprompt=SimpleNamespace(get_real_node_id=lambda node_id: "B"))
check("expanded save resolves back to its user node",
      twin.producer_metadata(hidden, 2), {"node": "B", "index": 2})
check("a direct save does not claim a random creator",
      twin.producer_metadata(SimpleNamespace(prompt=prompt, unique_id="save", dynprompt=None)), None)

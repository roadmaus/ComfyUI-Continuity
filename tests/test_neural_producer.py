"""A comparison belongs to the file's producer, not another output in its prompt.

    python3 tests/test_neural_producer.py

Pure producer selection, dependency closure and metadata tests; no model runs.
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

check("B is off even though A and PreStage are on",
      twin.read(prompt, {"node": "B", "index": 0})["on"], False)
check("ambiguous legacy file is not guessed", twin.read(prompt)["ours"], False)
check("ambiguous legacy file explains why", bool(twin.read(prompt).get("error")), True)
check("a single-producer legacy file remains supported",
      twin.read({"B": prompt["B"]})["node"], "B")
for bad in [None, {"node": "missing"}, {"node": "B", "index": -1},
            {"node": "B", "index": True}, {"node": "B", "index": "one"}]:
    try:
        twin.twin(prompt, True, producer=bad)
    except twin.TwinError:
        pass
    else:
        raise AssertionError(f"ambiguous/invalid producer was accepted: {bad!r}")

changed = twin.twin(prompt, True, {"detail": 3}, producer={"node": "B", "index": 0})
check("only B changed", changed["A"], prompt["A"])
check("upstream PreStage settings remain fixed", changed["pre"], prompt["pre"])
check("target seed stays fixed", changed["B"]["inputs"]["seed"], 73)
check("target adopts requested detail", json.loads(changed["B"]["inputs"]["creator_data"])["neural"]["detail"], 3)
check("original prompt untouched", prompt, original)
closure = twin.dependency_prompt(changed, "B")
check("only target and its upstream dependency chain are queued", set(closure), {"B", "pre", "loader"})
check("dependency values and node ids are preserved", closure["pre"], prompt["pre"])
check("batch index survives metadata read", twin.read(prompt, {"node": "B", "index": 2})["index"], 2)

hidden = SimpleNamespace(prompt=prompt, unique_id="B.0.save",
                         dynprompt=SimpleNamespace(get_real_node_id=lambda node_id: "B"))
check("expanded save resolves back to its user node",
      twin.producer_metadata(hidden, 2), {"node": "B", "index": 2})
check("a direct save does not claim a random creator",
      twin.producer_metadata(SimpleNamespace(prompt=prompt, unique_id="save", dynprompt=None)), None)

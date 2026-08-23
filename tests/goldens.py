"""Whole emitted graphs, frozen to a file.

Every other graph suite asserts *properties* — this node is wired to that one,
this input carries that value — and a property assertion is silent about
everything it does not look at. That is the right shape for a suite describing
what the wiring means, and the wrong shape for a refactor whose entire claim is
"nothing changed": a move that quietly dropped an input, reordered two nodes or
switched a default would pass every one of them.

So this is the complement, and it exists for the multi-family refactor. It
records the graph a blob expands to, in full, and compares the next run against
it byte for byte. A phase that changes a single emitted node fails here and
names the case.

    <comfy-venv>/bin/python3 tests/test_golden_graph.py       # compare
    UPDATE_GOLDENS=1 <comfy-venv>/bin/python3 tests/test_golden_graph.py

The second form rewrites the files, and the diff it produces is the thing to
review — a golden that changed without anybody meaning it to is exactly the
failure this catches, so an update commit that is not read is an update commit
that has thrown the net away.

**Node ids are normalised because GraphBuilder's are not stable.** Ids come out
as `{prefix}{n}` where the prefix carries a counter that increments once per
builder ever constructed in the process, so the same blob expanded twice gives
`.0.41.5` and then `.0.42.5`. Only the prefix moves; the suffix is the graph's
own numbering and is what identifies a node within it. Links are rewritten the
same way, so a golden compares topology and values and not the order the suites
happened to run in.
"""

import json
import os

GOLDEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")

UPDATE = os.environ.get("UPDATE_GOLDENS") == "1"


def _short(node_id):
    """A GraphBuilder id without the per-process counter in front of it."""
    return str(node_id).rsplit(".", 1)[-1]


def _rewrite(value, ids):
    """`value` with every node id in it replaced by its normalised form.

    A link is `[node_id, slot]`, which is indistinguishable from any other
    two-element list until you know the first element names a node — hence the
    `ids` set rather than a shape test. Widget values that happen to be strings
    are left alone unless they *are* one of this graph's ids.
    """
    if isinstance(value, list):
        return [_rewrite(item, ids) for item in value]
    if isinstance(value, dict):
        return {key: _rewrite(item, ids) for key, item in value.items()}
    if isinstance(value, str) and value in ids:
        return _short(value)
    return value


def canonical(graph):
    """The expansion, with ids normalised and everything else untouched."""
    ids = set(graph)
    short = {node_id: _short(node_id) for node_id in ids}
    if len(set(short.values())) != len(ids):
        # Never seen, and worth failing loudly rather than silently comparing
        # two nodes as one: a collision means the id shape assumed above has
        # changed and this whole module needs re-reading.
        raise AssertionError(f"node id suffixes are not unique: {sorted(ids)}")
    return {
        short[node_id]: {
            "class_type": node["class_type"],
            "inputs": _rewrite(node["inputs"], ids),
        }
        for node_id, node in graph.items()
    }


def _path(name):
    return os.path.join(GOLDEN_DIR, f"{name}.json")


def _dump(value):
    # Sorted and indented: the file is read as a diff far more often than it is
    # parsed, and an unsorted dump would show spurious moves.
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def compare(name, graph, failures):
    """Check `graph` against the golden of that name, or record it.

    Appends to `failures` rather than raising, so one run reports every case
    that moved instead of the first.
    """
    got = canonical(graph)
    path = _path(name)

    if UPDATE:
        os.makedirs(GOLDEN_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(_dump(got))
        return

    if not os.path.exists(path):
        failures.append(
            f"{name}: no golden recorded. Run with UPDATE_GOLDENS=1 and review "
            f"the file it writes."
        )
        return

    with open(path, encoding="utf-8") as handle:
        want = json.load(handle)

    if got == want:
        return

    failures.append(f"{name}: the emitted graph no longer matches its golden. "
                    + "; ".join(_differences(got, want)))


def _differences(got, want):
    """What moved, said in one line per node rather than as two whole dumps."""
    out = []
    for node_id in sorted(set(want) - set(got)):
        out.append(f"node {node_id} ({want[node_id]['class_type']}) is gone")
    for node_id in sorted(set(got) - set(want)):
        out.append(f"node {node_id} ({got[node_id]['class_type']}) is new")
    for node_id in sorted(set(got) & set(want)):
        mine, theirs = got[node_id], want[node_id]
        if mine["class_type"] != theirs["class_type"]:
            out.append(f"node {node_id} is now {mine['class_type']}, "
                       f"was {theirs['class_type']}")
            continue
        for key in sorted(set(mine["inputs"]) | set(theirs["inputs"])):
            a, b = mine["inputs"].get(key, "<absent>"), theirs["inputs"].get(key, "<absent>")
            if a != b:
                out.append(f"{node_id}.{theirs['class_type']}.{key}: "
                           f"{_brief(b)} -> {_brief(a)}")
    return out or ["no per-node difference found, which should be impossible"]


def _brief(value):
    """A value short enough to sit in a failure line.

    `segment_data` is the whole compiled request and is the field most likely to
    be the one that moved, so it cannot be printed and cannot be omitted either.
    Truncated, and the golden file is where the difference is actually read.
    """
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    return text if len(text) <= 80 else text[:77] + "..."

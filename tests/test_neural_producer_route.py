"""The twin route queues only the identified producer and its dependencies.

    python3 tests/test_neural_producer_route.py

Runs the actual route function with in-memory request, metadata and queue
boundaries. No server, user file, network or GPU execution is involved.
"""

import ast
import asyncio
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

from aiohttp import web

import layout
from harness import check

package = "neural_producer_route_test"
pkg = layout.load("neuraltwin", package=package)
twin = pkg.neuraltwin
prompt = {
    "A": {"class_type": "MiniMaxH3Creator", "inputs": {"creator_data": '{"neural":{"on":true}}'}},
    "B": {"class_type": "MiniMaxH3Creator", "inputs": {"creator_data": '{}', "image": ["loader", 0], "seed": 42}},
    "loader": {"class_type": "LoadImage", "inputs": {"image": "source.png"}},
    "unrelated": {"class_type": "NotInstalled", "inputs": {}},
}
embedded = {"prompt": prompt, twin.PRODUCER_KEY: {"node": "B", "index": 1}}
reads, validations, queued = [], [], []
routes_module = ModuleType(f"{package}.routes")
routes_module.__path__ = [str(Path(layout.PY_ROOT) / "routes")]
sys.modules[routes_module.__name__] = routes_module
server_routes = ModuleType(f"{package}.server_routes")


def read_embedded(path, keys):
    reads.append((path, keys))
    return {key: embedded.get(key) for key in keys}


server_routes._read_embedded = read_embedded
server_routes._input_path = lambda request: "in-memory-file.png"
sys.modules[server_routes.__name__] = server_routes
media = ModuleType(f"{package}.media")
media.resolve = lambda filename: filename
sys.modules[media.__name__] = media
pkg.media = media
execution = ModuleType("execution")


async def validate(prompt_id, graph, targets):
    validations.append((graph, targets))
    return True, None, targets, {}


execution.validate_prompt = validate
sys.modules["execution"] = execution
server = SimpleNamespace(number=1, prompt_queue=SimpleNamespace(put=queued.append))
source = Path(layout.PY_ROOT) / "routes" / "neural.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
functions = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
             and node.name in ("neural_of", "neural_twin")]
for node in functions:
    node.decorator_list = []
namespace = {"__package__": routes_module.__name__, "asyncio": asyncio, "json": json,
             "web": web, "neuraltwin": twin, "PromptServer": SimpleNamespace(instance=server)}
exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), namespace)


class Request:
    async def json(self):
        return {"filename": "in-memory-file.png", "on": True, "block": {"detail": 3}, "client_id": "test"}


async def run():
    response = await namespace["neural_of"](Request())
    info = json.loads(response.text)
    check("metadata endpoint chooses B, not earlier ON A", (info["node"], info["on"]), ("B", False))
    response = await namespace["neural_twin"](Request())
    answer = json.loads(response.text)
    check("queue request succeeds", response.status, 200)
    check("response identifies output and batch index", (answer["node"], answer["index"]), ("B", 1))
    check("only target is submitted for output validation", validations[0][1], ["B"])
    check("unrelated output and missing-node type removed", set(validations[0][0]), {"B", "loader"})
    check("queue preserves input link", queued[0][2]["B"]["inputs"]["image"], ["loader", 0])
    check("queue preserves seed", queued[0][2]["B"]["inputs"]["seed"], 42)
    check("queue targets only B", queued[0][4], ["B"])
    check("socket client id preserved", queued[0][3], {"client_id": "test"})
    check("metadata reader requests provenance", twin.PRODUCER_KEY in reads[0][1], True)
    embedded.pop(twin.PRODUCER_KEY)
    response = await namespace["neural_twin"](Request())
    check("ambiguous legacy request is rejected", response.status, 400)
    check("ambiguous request never reaches the queue", len(queued), 1)


asyncio.run(run())

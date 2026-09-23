"""A render whose save failed, or was cancelled, runs again on the next Run (#97).

The Creator and the PreStage are output nodes with no sockets that return their
render as an expansion, and core caches the parent the moment it resolves. With
nothing exported from the expansion that is straight after it expands, before a
single inner node has run: a save that then ran out of disk, or a Cancel, left
the parent cached as done, and the next Run with the same inputs reported
success and wrote nothing. `core.emit.expanded` exports every node that writes
a file, so the parent resolves only once they have all succeeded.

What is under test is core's executor and cache against our `expanded`, so both
are the real ones. The graph is a stand-in: an upstream node counting how often
it runs, where the sampler and decode would be, and a writer, registered under
the image save node's class id so `expanded` knows it for one, that fails the
first time it is asked. The real save node needs a real render to write.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_expansion_cache.py

Skips itself with a message if ComfyUI cannot be imported.
"""

import asyncio
import importlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.basename(ROOT)

COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
BASE = os.environ.get("COMFYUI_BASE", COMFY)


def _boot():
    sys.path.insert(0, COMFY)
    sys.argv = ["main.py", "--base-directory", BASE]
    import execution
    import nodes
    import server

    # The pack registers its routes at import, so it needs a server to exist.
    loop = asyncio.new_event_loop()
    try:
        from app.assets.manager import default_asset_manager
        server.PromptServer(loop, default_asset_manager())
    except (ImportError, TypeError):
        server.PromptServer(loop)
    asyncio.set_event_loop(loop)
    loop.run_until_complete(nodes.init_extra_nodes(init_custom_nodes=False))

    sys.path.insert(0, os.path.dirname(ROOT))
    return execution, nodes


try:
    execution, comfy_nodes = _boot()
    import comfy.model_management
    from comfy_execution.graph_utils import GraphBuilder
except Exception as exc:  # noqa: BLE001
    print(f"skipped: ComfyUI not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)

emit = importlib.import_module(f"{PACKAGE}.creator.core.emit")

from harness import check, passed

state = {}


class Work:
    """Where the sampler and the decode would be: expensive, and cacheable."""
    RETURN_TYPES = ("INT",)
    FUNCTION = "run"
    CATEGORY = "test"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"x": ("INT", {})}}

    def run(self, x):
        state["worked"] += 1
        return (x,)


class Writer:
    """The save node, which fails with `state["fail"]` the first time only."""
    OUTPUT_NODE = True
    RETURN_TYPES = ("BOOLEAN",)
    FUNCTION = "run"
    CATEGORY = "test"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"x": ("INT", {})}}

    def run(self, x):
        failure, state["fail"] = state["fail"], None
        if failure is not None:
            raise failure
        state["written"] += 1
        return (True,)


class Parent:
    """The Creator, reduced to what the executor sees of it."""
    OUTPUT_NODE = True
    RETURN_TYPES = ()
    FUNCTION = "run"
    CATEGORY = "test"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"x": ("INT", {})}}

    def run(self, x):
        state["expanded"] += 1
        graph = GraphBuilder()
        work = graph.node("TestExpansionWork", x=x)
        graph.node(emit.IMAGE_SAVE_NODE, x=work.out(0))
        return emit.expanded(graph)


comfy_nodes.NODE_CLASS_MAPPINGS.update({
    "TestExpansionWork": Work,
    emit.IMAGE_SAVE_NODE: Writer,
    "TestExpansionParent": Parent,
})


class Server:
    client_id = None
    last_node_id = None

    def send_sync(self, *args, **kwargs):
        pass


def twice(failure, cache_type):
    """Run the same prompt twice on one executor, the first failing with `failure`."""
    state.update(fail=failure, expanded=0, worked=0, written=0)
    executor = execution.PromptExecutor(
        Server(), cache_type=cache_type,
        cache_args={"lru": 0, "ram": 4.0, "ram_inactive": 16.0})
    prompt = {"1": {"class_type": "TestExpansionParent", "inputs": {"x": 1}}}
    results = []
    for prompt_id in ("first", "second"):
        asyncio.run(executor.execute_async(prompt, prompt_id, {}, ["1"]))
        results.append(executor.success)
    return results


# The two ways the issue gets there, under the default cache and the classic one.
for cache_type in (execution.CacheType.RAM_PRESSURE, execution.CacheType.CLASSIC):
    name = cache_type.name.lower()
    for why, failure in (
            ("a full disk", OSError(28, "No space left on device")),
            ("a Cancel", comfy.model_management.InterruptProcessingException())):
        results = twice(failure, cache_type)
        check(f"{name}: {why} fails the first run", results[0], False)
        check(f"{name}: after {why} the next Run expands again", state["expanded"], 2)
        check(f"{name}: ...and writes the file", (results[1], state["written"]), (True, 1))
        # What the reporter remembered as resuming: the work that did finish
        # stays cached, and only the part that failed runs again.
        check(f"{name}: ...without redoing the work that finished", state["worked"], 1)

# The other side: a render that did finish is still a cache hit on the next Run.
twice(None, execution.CacheType.CLASSIC)
check("a finished render is not rendered again",
      (state["expanded"], state["written"]), (1, 1))

passed("a failed or cancelled save leaves the next Run something to do")

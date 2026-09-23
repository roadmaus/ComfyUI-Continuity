"""The saved room keeps its turn, cancels its own prompt, and stays deleted.

The real room is opened and driven through its DOM, alongside the real store,
queue and imports. Only ComfyUI's API and the browser are stubbed; no server,
network, GPU or user data is needed.
"""
from pathlib import Path

import layout
from domshim import DOM
from harness import check, passed

layout.skip_without_node()
here = Path(__file__).parent
api = layout.STUBS["api.js"] + (here / "chat_lifecycle_api.mjs").read_text(encoding="utf-8")
script = DOM + (here / "chat_lifecycle.mjs").read_text(encoding="utf-8")
with layout.pack(skip=["atlas"], extra_stubs={"api.js": api}) as target:
    results = layout.in_pack(script, target)

check("every chat lifecycle scenario ran", len(results), 9)
for name, error in results.items():
    check(name, error, None)
passed("all 9 chat lifecycle scenarios passed")

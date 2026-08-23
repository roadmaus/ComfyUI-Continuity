"""What ComfyUI loads. The pack itself is `creator/`.

Everything used to sit here, at the root of the clone, which put thirty-four
modules in the same listing as the README, the tests, the docs and the vendored
tools — and gave the code no boundary to be inside of. It is a package now, and
this file is what ComfyUI still finds: the entry point it imports, the two
route modules that register themselves, and where the frontend lives.

Two things deliberately did *not* move. `locales/` stays at the root because
ComfyUI reads it from the custom-node directory itself rather than from any
module (`app/custom_node_manager.py`), so a translation filed under `creator/`
would be a translation nobody loads. And the node class ids inside are frozen
whatever the directories do — they are what saved workflows name.
"""

from .creator import refine_routes  # noqa: F401  (registers /minimax_creator/refine)
from .creator import server_routes  # noqa: F401  (registers /minimax_creator/assets)
from .creator.creator_node import comfy_entrypoint  # noqa: F401
from .creator.routes import families  # noqa: F401  (registers /minimax_creator/families)

WEB_DIRECTORY = "./web"

__all__ = ["comfy_entrypoint", "WEB_DIRECTORY"]

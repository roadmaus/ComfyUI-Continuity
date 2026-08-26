"""`/continuity/families`: the family manifests, served.

One GET, answering everything the frontend needs to know about what exists:
every family's manifest in the registry's order, and how the pre-stage's arch
pill maps onto families. The payload is `families/manifest.py`'s `catalog()`,
built from pure constants — nothing here touches disk or the event loop.

The route is why the manifests can drain `state.js` (phase 5): a frontend
that reads this at mount has no reason to carry the constants itself.
"""

from aiohttp import web
from server import PromptServer

from ..families import manifest


@PromptServer.instance.routes.get("/continuity/families")
async def list_families(request):
    return web.json_response(manifest.catalog())

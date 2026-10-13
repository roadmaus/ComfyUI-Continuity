"""`/continuity/download`: a file, a folder or a selection, to the browser's
own Downloads folder — see `downloads.py` for why the pack needs one.

A GET, so the frontend can hand the URL to an `<a download>` and the browser
streams it to disk: a 2 GB render never passes through the page. One `path`
naming a file is served as itself; anything more is zipped into a temporary
file first (a zip's central directory is written last, so it cannot be
streamed as it is built without a seekable target), sent, and removed.

A selection from the picker can be a few hundred paths, which is past what a
URL holds. Those are POSTed first and come back as a ticket: a short-lived
handle on the path list that the GET then names instead.
"""

import asyncio
import os
import secrets
import tempfile
import time
from urllib.parse import quote

from aiohttp import web
from server import PromptServer

from .. import downloads
from ..guard import same_origin

# A ticket is fetched within a second of being made; ten minutes is for a
# browser that asks where to save before it starts the request.
TICKET_SECONDS = 600
_tickets = {}   # ticket -> (made at, paths, name)
CHUNK = 1 << 20


def _disposition(filename):
    """`attachment` with the name both ways: plain for old clients, RFC 5987
    for a name with a character the plain form cannot carry."""
    plain = filename.encode("ascii", "replace").decode().replace('"', "_")
    return f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quote(filename)}"


def _take_ticket(ticket):
    now = time.monotonic()
    for stale in [k for k, (at, _, _) in _tickets.items() if now - at > TICKET_SECONDS]:
        del _tickets[stale]
    found = _tickets.get(ticket)
    if found is None:
        raise downloads.DownloadError("that download has expired; press Download again")
    return found[1], found[2]


@PromptServer.instance.routes.post("/continuity/download")
@same_origin
async def download_ticket(request):
    """{paths: [...], name?} -> {ticket}, after checking every path resolves,
    so a bad selection is refused here rather than as a broken download."""
    body = await request.json()
    paths = body.get("paths")
    if not isinstance(paths, list) or not paths or not all(isinstance(p, str) for p in paths):
        return web.json_response({"error": "paths must be a list of file names"}, status=400)
    try:
        for path in paths:
            downloads.resolve(path)
    except downloads.DownloadError as exc:
        return web.json_response({"error": str(exc)}, status=404)
    ticket = secrets.token_urlsafe(16)
    _tickets[ticket] = (time.monotonic(), paths, body.get("name"))
    return web.json_response({"ticket": ticket})


@PromptServer.instance.routes.get("/continuity/download")
async def download(request):
    """?path=…[&path=…][&name=…] or ?ticket=… -> the file, or a zip of them."""
    try:
        if "ticket" in request.query:
            paths, name = _take_ticket(request.query["ticket"])
        else:
            paths, name = request.query.getall("path", []), request.query.get("name")
        if len(paths) == 1 and os.path.isfile(target := downloads.resolve(paths[0])):
            return web.FileResponse(target, headers={
                "Content-Disposition": _disposition(name or os.path.basename(target))})
        entries = downloads.plan(paths)
        filename = downloads.zip_name(paths, entries, name)
    except downloads.DownloadError as exc:
        return web.json_response({"error": str(exc)}, status=404)

    loop = asyncio.get_running_loop()
    handle, archive = tempfile.mkstemp(prefix="continuity-", suffix=".zip")
    os.close(handle)
    try:
        await loop.run_in_executor(None, downloads.write_zip, entries, archive)
        # Streamed by hand rather than as a FileResponse: aiohttp prepares a
        # returned FileResponse again after the handler, by which time the
        # `finally` below has removed the file it would stat.
        response = web.StreamResponse(headers={
            "Content-Type": "application/zip", "Content-Disposition": _disposition(filename)})
        response.content_length = os.path.getsize(archive)
        await response.prepare(request)
        with open(archive, "rb") as source:
            while chunk := await loop.run_in_executor(None, source.read, CHUNK):
                await response.write(chunk)
        await response.write_eof()
        return response
    finally:
        os.remove(archive)

"""Listing routes for the asset picker and the LoRA manager.

The picker browses ComfyUI/input, so the only thing the frontend cannot work out
for itself is what is in there. Image thumbnails reuse core's `/api/view`, and
uploads reuse core's `/api/upload/image` (which despite the name is what
LoadVideo and LoadAudio post to as well), so neither needs a route here.

Video does need routes of its own: `/view` serves the whole clip, which is the
wrong thing to hand a 140 px grid cell or a waveform canvas. See preview.py.

LoRAs need both routes of their own. `/view` only serves input, output and temp,
so it cannot reach models/loras, and whatever sidecar sits next to each file has
to be read server-side. What those sidecars *are* is `lorameta.py`'s problem —
half a dozen tools write half a dozen layouts, and nothing here knows which one
filled this folder.

The settings pair is the one thing here that is not a listing. It has to be a
route rather than the frontend's userdata API for the reason `settings.py` opens
with: the save node reads the same file while a prompt runs, and only the server
can hand both ends the same path.

`compiled_prompt` at the bottom is not a listing either. It exists so the prompt
box can show the finished, sectioned prompt beside the sentence you typed, and
it runs the real compiler to do it — see the route.
"""

import asyncio
import json
import logging
import os

from aiohttp import web

import folder_paths
from server import PromptServer

from . import (compile as compiler, jobs, latents, lorameta, media, models, plate,
               preview, settings)

# The picker builds its grid lazily and paginates, so the cap only bounds the
# listing's JSON payload (~2 MB at this size). Newest first, so when a folder
# does exceed it the cap drops the least interesting files, and the picker
# says so on the last page.
MAX_ASSETS = 20000

# How many LoRAs get the full sidecar treatment in one listing. A collection of
# a few thousand is normal, and reading a JSON file plus listing two directories
# for every one of them is seconds of work — so only the newest MAX_LORAS are
# described, and the manager says so and offers the folder picker instead.
MAX_LORAS = 600


def _classify(filename):
    for kind in ("image", "video", "audio"):
        if folder_paths.filter_files_content_types([filename], [kind]):
            return kind
    return None


def _scan(root, annotation=""):
    """Walk one media folder -> `(assets, folders)`.

    `annotation` is ComfyUI's ` [output]` suffix.

    The folders come back because the folders *are* the answer: a shelf in the
    picker is a directory on this disk and nothing else, so the listing has to
    report every one of them — including the ones holding no media, which the
    file rows alone can never mention. A shelf that came from anywhere but here
    is a shelf that outlives the directory it named (#40): delete the input
    folder from a terminal and the picker went on offering its contents.

    Carried inside `path` rather than as a separate field because the path is
    the one thing that survives into creator_data: every consumer downstream —
    the thumb and probe routes here, `media.resolve` at execute time — already
    goes through `get_annotated_filepath`, so an annotated path is a file the
    whole pipeline can reach with no second load path.

    Read off `os.scandir`'s entries rather than `os.walk`'s names, because
    enumerating the directory has already answered everything this asks. Going
    back by path — `islink`, `getmtime`, `getsize` — is three more syscalls per
    file, and on Windows that is the entire cost of a listing: `FindFirstFileW`
    hands back the size and the timestamps inline, so `DirEntry.stat()` there is
    free for everything except a symlink, while `os.path.getmtime` on a path
    string is a fresh open through the whole filter driver stack, virus scanner
    included. On Linux and macOS the same change saves two syscalls of three and
    nothing was ever slow enough to notice, which is how a folder of renders
    that lists in a second here listed in minutes on someone's Windows
    server (#4).
    """
    assets = []
    folders = []
    pending = [root]
    index = 0
    while index < len(pending):
        directory = pending[index]
        index += 1
        try:
            with os.scandir(directory) as scan:
                entries = sorted(scan, key=lambda e: e.name)
        except OSError:
            continue
        subfolder = os.path.relpath(directory, root)
        subfolder = "" if subfolder == "." else subfolder.replace(os.sep, "/")
        if subfolder:
            folders.append(subfolder)
        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                # follow_symlinks=False is os.walk's own default: a link to a
                # directory is listed, not descended into.
                if entry.is_dir(follow_symlinks=False):
                    pending.append(entry.path)
                    continue
            except OSError:
                continue
            kind = _classify(entry.name)
            if kind is None:
                continue
            # A symlink pointing outside the root is a file this pack cannot
            # open: `get_annotated_filepath` resolves the link and then refuses
            # it for leaving the folder, so listing it would offer a thumbnail
            # that fails at execute time with "not in the input folder any
            # more" — about a file that is plainly sitting right there.
            #
            # Not worked around: the containment check is core's and is the
            # thing standing between a crafted filename and the rest of the
            # disk. Symlinking media into input/ does not work; the flag that
            # does is `--input-directory`, and the README says so.
            #
            # `is_symlink` reads the type the enumeration already returned, so
            # what cost a syscall per file now costs one per symlink.
            if entry.is_symlink() and not folder_paths.is_within_directory(root, entry.path):
                continue
            try:
                stat = entry.stat()
            except OSError:
                continue
            relative = f"{subfolder}/{entry.name}" if subfolder else entry.name
            assets.append({
                "path": relative + annotation,
                "name": entry.name,
                "subfolder": subfolder,
                "kind": kind,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            })
    return assets, folders


def _input_path(request):
    """The absolute path behind a `?filename=` query, or None if it is not ours."""
    filename = request.query.get("filename", "")
    if not filename or not folder_paths.exists_annotated_filepath(filename):
        return None
    return folder_paths.get_annotated_filepath(filename)


def _read_header(path):
    import av  # ComfyUI's own decoder stack; imported here so the listing route never needs it.

    with av.open(path) as container:
        # The picture's own size, for a clip card: it is what the timeline's
        # aspect comes from when footage is cut into the strip, and storing it
        # in the blob is what keeps `compile.py` free of disk access. Rotated
        # sources report their storage size, and the display swap is applied
        # here so the card and the render agree with the player.
        stream = next(iter(container.streams.video), None)
        width = height = None
        if stream is not None:
            width, height = int(stream.width), int(stream.height)
            if media.stream_rotation(container, stream) % 180:
                width, height = height, width
        return {
            "has_audio": bool(container.streams.audio),
            "duration": float(container.duration / av.time_base) if container.duration else None,
            "width": width,
            "height": height,
        }


@PromptServer.instance.routes.get("/continuity/probe")
async def probe_asset(request):
    """Does this clip carry a soundtrack?

    A reference video is attached with its sound on by default, which is only the
    right default when there is sound to bind — otherwise the generation would
    fail at queue time on a file the user never claimed was noisy. No browser
    reports the presence of an audio track portably, so the answer comes from
    here. It reads the container header, not the media.

    `has_audio: null` means the question could not be answered; the caller keeps
    its own default rather than guessing silence.
    """
    path = _input_path(request)
    if path is None:
        return web.json_response({"has_audio": None, "error": "not in the input folder"}, status=404)
    try:
        # Opening a container reads and seeks; on a network share that is long
        # enough to be felt, and anything blocking here blocks the whole server —
        # the prompt queue and the websocket included.
        loop = asyncio.get_running_loop()
        return web.json_response(await loop.run_in_executor(None, _read_header, path))
    except Exception as exc:  # noqa: BLE001 — an unreadable file is the caller's problem, later
        return web.json_response({"has_audio": None, "error": str(exc)})


def _read_embedded(path):
    """The `prompt` and `workflow` a finished render carries in its own file.

    Both save nodes write them — `MiniMaxH3Save` into the MP4's container tags,
    `MiniMaxH3SaveImage` into the PNG's text chunks — for the reason core's
    savers do: a render dropped back onto the canvas rebuilds the node that made
    it. Which means the file already holds every field a preset wants, and the
    only thing missing was a way for the browser to read it.

    Two readers because they are two containers, chosen by extension rather than
    by trying one and catching: `av` cannot see a PNG's text chunks and PIL
    cannot open an MP4, so a fallback chain here would only turn "the wrong
    reader" into "no metadata", which is the same answer for a file that has
    none and a file we failed to read.

    A value that is not JSON comes back as None rather than raising. These tags
    are written by whoever wrote the file, which is not always this pack — a
    render remuxed by ffmpeg keeps the tag and can lose the end of it.
    """
    if os.path.splitext(path)[1].lower() in (".png", ".webp"):
        from PIL import Image

        with Image.open(path) as image:
            raw = {key: image.info.get(key) for key in ("prompt", "workflow")}
    else:
        import av  # ComfyUI's own decoder stack, as `_read_header` above.

        with av.open(path) as container:
            raw = {key: container.metadata.get(key) for key in ("prompt", "workflow")}

    out = {}
    for key, value in raw.items():
        try:
            out[key] = json.loads(value) if value else None
        except (TypeError, ValueError):
            out[key] = None
    return out


@PromptServer.instance.routes.get("/continuity/render_meta")
async def render_meta(request):
    """The workflow embedded in one render, so a preset can be taken from it.

    A read route and not the userdata API, which is where the rest of the preset
    feature lives: this is a question about a file on this machine's disk, and
    the browser cannot open one. It does not weaken the argument `settings.py`
    makes — nothing here is read while a prompt executes, this only serves a
    file that a finished execution already wrote.

    `{prompt: null, workflow: null}` for a render that carries neither, with a
    200: a file saved under `--disable-metadata` is an ordinary file and not an
    error, and the caller says so in words the user can act on.
    """
    path = _input_path(request)
    if path is None:
        return web.json_response({"error": "not in the input or output folder"}, status=404)
    try:
        loop = asyncio.get_running_loop()
        return web.json_response(await loop.run_in_executor(None, _read_embedded, path))
    except Exception as exc:  # noqa: BLE001 — an unreadable file is the caller's problem
        return web.json_response({"prompt": None, "workflow": None, "error": str(exc)})


@PromptServer.instance.routes.get("/continuity/thumb")
async def asset_thumb(request):
    """A small webp of one clip or picture, the way its player shows it.

    Pictures too, and not core's `/view?preview=`: that re-encode opens the
    file and saves it without its orientation tag, so a phone photo stored
    sideways and tagged upright came back as a sideways thumbnail beside a
    full picture the browser had turned. See `preview._render_thumb`.

    404 rather than a placeholder: the cell falls back to an icon, and inventing
    an image here would make an undecodable file look like a fine one.
    """
    path = _input_path(request)
    if path is None:
        return web.Response(status=404)
    thumb = await preview.thumbnail(path)
    if thumb is None:
        return web.Response(status=404)
    # A caller that stamped the source's mtime into the URL has made it name one
    # immutable frame — replacing the file changes the URL. One that did not is
    # revalidated every time; the response carries an ETag, so that is a 304.
    versioned = bool(request.query.get("v"))
    return web.FileResponse(thumb, headers={
        "Content-Type": "image/webp",
        "Cache-Control": "public, max-age=31536000, immutable" if versioned else "no-cache",
    })


@PromptServer.instance.routes.get("/continuity/peaks")
async def asset_peaks(request):
    """Waveform peaks for the segment editor's timeline, normalised to 0..1.

    `peaks: null` means there is nothing to draw — no audio track, or a track
    that decoded to silence — and the timeline stays plain, which is exactly what
    it does when this is unavailable altogether.
    """
    path = _input_path(request)
    if path is None:
        return web.json_response({"peaks": None}, status=404)
    result = await preview.waveform(path)
    if result is None:
        return web.json_response({"peaks": None})
    # Not cached by the browser: the answer is keyed by mtime server-side, and
    # this is one small request per editor opening rather than one per cell.
    return web.json_response(result, headers={"Cache-Control": "no-cache"})


def _lora_names():
    """Every registered LoRA, as a forward-slash relative name.

    `get_filename_list` yields native separators; the manager stores these names
    in creator_data and posts them back, so they are normalised once here and
    stay one shape everywhere. `get_full_path` accepts either on both platforms.
    """
    return [name.replace(os.sep, "/") for name in folder_paths.get_filename_list("loras")]


def _folder_counts(names):
    """Every folder that holds LoRAs, with how many are under it.

    Counts are inclusive of nested folders — picking `Wan` and finding nothing
    because the files sit in `Wan/character` would make the picker useless. The
    root entry is the empty string, which is how the manager asks for all of them.
    """
    counts = {"": len(names)}
    for name in names:
        parts = name.split("/")[:-1]
        for depth in range(len(parts)):
            counts["/".join(parts[:depth + 1])] = counts.get("/".join(parts[:depth + 1]), 0) + 1
    return [{"path": path, "count": counts[path]} for path in sorted(counts)]


def _in_folder(name, folder):
    return not folder or name.startswith(folder + "/")


def _collect_loras(folder, refresh=False):
    """The rows for one folder, newest first, capped at MAX_LORAS.

    Two passes on purpose. Stat-ing every candidate is cheap and is the only way
    to know which ones are the newest; reading sidecars is not, so it happens
    only for the ones that survive the cap.
    """
    if refresh:
        # The manager's Rescan. `lorameta` holds a directory listing for a short
        # while and a row for as long as nothing beside the file changes, which
        # between them cannot notice a sidecar edited in place — so the button
        # that exists to say "look again" has to actually mean it.
        lorameta.forget()
    names = _lora_names()
    found = []
    for name in names:
        if not _in_folder(name, folder):
            continue
        path = folder_paths.get_full_path("loras", name)
        if path is None:
            continue
        try:
            found.append((os.path.getmtime(path), name, path))
        except OSError:
            continue
    found.sort(reverse=True)
    rows = [lorameta.row(name, path) for _, name, path in found[:MAX_LORAS]]
    return {
        "loras": rows,
        "folders": _folder_counts(names),
        "folder": folder,
        "matched": len(found),
        "truncated": len(found) > MAX_LORAS,
    }


@PromptServer.instance.routes.get("/continuity/loras")
async def list_loras(request):
    # Thousands of files means thousands of stat calls and hundreds of sidecar
    # reads. On the event loop that is the prompt queue and the websocket held
    # up for as long as it takes.
    folder = request.query.get("folder", "").strip("/")
    refresh = request.query.get("refresh") == "1"
    loop = asyncio.get_running_loop()
    return web.json_response(await loop.run_in_executor(None, _collect_loras, folder, refresh))


def _collect_named(names):
    """The rows for an explicit list of names, in the order asked for.

    The folder listing above is newest-first and capped, which is the right
    shape for browsing and the wrong one for a shelf: a favorite in a folder of
    two thousand files would be starred and then unreachable, because the client
    can only filter what the server chose to send. Naming the files sidesteps
    the cap entirely — the work is bounded by the shelf, not by the folder.

    What is *not* here comes back too. A LoRA can be renamed or deleted between
    the day it was starred and the day the shelf is opened, and a shelf that
    quietly showed nine of ten would be lying about which ten.
    """
    known = set(_lora_names())
    rows = []
    missing = []
    for name in names:
        path = folder_paths.get_full_path("loras", name) if name in known else None
        if path is None:
            missing.append(name)
            continue
        rows.append(lorameta.row(name, path))
    # The folder counts ride along because the manager's scope picker lists both
    # shelves and folders, and a session that opens straight onto a shelf would
    # otherwise have a picker with no folders in it until you left.
    return {"loras": rows, "missing": missing, "folders": _folder_counts(sorted(known))}


@PromptServer.instance.routes.post("/continuity/loras_named")
async def loras_named(request):
    body = await request.json()
    raw = body.get("names")
    names = [str(name) for name in raw][:MAX_LORAS] if isinstance(raw, list) else []
    loop = asyncio.get_running_loop()
    return web.json_response(await loop.run_in_executor(None, _collect_named, names))


def _lora_path(request):
    """The absolute path behind a `?name=`, or None.

    `get_full_path` normalises the name against the registered lora folders,
    which is also what keeps a crafted name inside them.
    """
    return folder_paths.get_full_path("loras", request.query.get("name", ""))


def _serve(path, data):
    """A media file, or bytes that were never a file, as a response.

    Embedded cover images and ModelSpec thumbnails live inside the safetensors
    header and have no filename to hand aiohttp, so they are served from memory
    with a type sniffed off their first bytes.
    """
    if path is not None:
        return web.FileResponse(path)
    if data is not None:
        payload, mime = data
        return web.Response(body=payload, content_type=mime)
    return web.Response(status=404)


@PromptServer.instance.routes.get("/continuity/lora_preview")
async def lora_preview(request):
    """Serve the card image or clip for one LoRA, from wherever it was found.

    Core's `/view` is limited to input/output/temp, so models/loras is out of its
    reach.
    """
    path = _lora_path(request)
    if path is None:
        return web.Response(status=404)
    loop = asyncio.get_running_loop()
    found, data = await loop.run_in_executor(None, lorameta.preview, path)
    return _serve(found, data)


@PromptServer.instance.routes.get("/continuity/lora_detail")
async def lora_detail(request):
    """Everything one LoRA's detail sheet needs, in one request: whatever the
    sidecars beside it know, the showcase with its generation recipes, and what
    the safetensors header itself says either way.
    """
    name = request.query.get("name", "")
    path = folder_paths.get_full_path("loras", name)
    if path is None:
        return web.json_response({"error": "no such LoRA"}, status=404)
    # Reading a header on a network share, plus a handful of sidecars, is I/O
    # the event loop must not sit on.
    loop = asyncio.get_running_loop()
    return web.json_response(await loop.run_in_executor(None, lorameta.detail, name, path))


@PromptServer.instance.routes.get("/continuity/lora_showcase")
async def lora_showcase(request):
    """Serve one showcase file by its index in the detail's showcase list.

    `?thumb=1` asks for the generated thumbnail instead — the filmstrip's
    request — and falls back to the full media when there is none, which is the
    normal state of a video showcase and of every gallery but CiviMeta's.

    The list is recomputed rather than remembered between the two requests: a
    server that held one per open sheet would be holding decoded cover images
    for every LoRA anyone had looked at.
    """
    path = _lora_path(request)
    if path is None:
        return web.Response(status=404)
    try:
        index = int(request.query.get("item", "0"))
    except ValueError:
        return web.Response(status=404)

    loop = asyncio.get_running_loop()
    entries = await loop.run_in_executor(None, lorameta.showcase, path)
    if not 0 <= index < len(entries):
        return web.Response(status=404)
    entry = entries[index]
    if request.query.get("thumb") == "1" and entry.get("thumb"):
        return web.FileResponse(entry["thumb"])
    data = None
    if entry.get("data") is not None:
        data = (entry["data"], entry.get("mime") or lorameta.sniff(entry["data"]))
    return _serve(entry.get("path"), data)


@PromptServer.instance.routes.get("/continuity/models")
async def list_models(request):
    """What the weights control can offer: one file list per field.

    The node has no model sockets any more, so this is the only way the UI knows
    what is installed. It also reports whether KJNodes' preview override is
    present, because the taeh3 preview is the one control here that depends on
    somebody else's pack being loaded.
    """
    # Four `get_filename_list` calls, each of which may walk a model directory
    # that has never been scanned. On the event loop that is the prompt queue and
    # the websocket held up behind it.
    loop = asyncio.get_running_loop()
    return web.json_response(await loop.run_in_executor(None, models.available))


@PromptServer.instance.routes.get("/continuity/assets")
async def list_assets(request):
    """The picker's grid: `?root=input` (the default) or `?root=output`.

    The output listing is the gallery — finished renders, browsed with the same
    machinery as the input folder. Its paths come back annotated (` [output]`),
    which is what lets one of them be attached as a reference: see `_scan`.
    """
    if request.query.get("root") == "output":
        root, annotation = folder_paths.get_output_directory(), " [output]"
    else:
        root, annotation = folder_paths.get_input_directory(), ""
    if not os.path.isdir(root):
        return web.json_response({"assets": [], "folders": [], "truncated": False})

    # A walk with two stat calls per file is nothing on a local disk and minutes
    # on a network share, and the event loop is also the prompt queue.
    loop = asyncio.get_running_loop()
    assets, folders = await loop.run_in_executor(None, _scan, root, annotation)
    assets.sort(key=lambda a: a["mtime"], reverse=True)
    truncated = len(assets) > MAX_ASSETS
    # Not capped with the assets. `MAX_ASSETS` is there so a folder of ten
    # thousand renders does not become a ten-megabyte JSON body, and the shelf
    # row is the one part of a truncated listing that must still be whole:
    # dropping folders would hide the places the missing files are in.
    return web.json_response({"assets": assets[:MAX_ASSETS], "folders": sorted(folders),
                              "truncated": truncated})


def _picker_root(name):
    """The absolute path of a root the picker browses, or None.

    Named rather than derived from a file, because the two folder routes below
    act on a directory and a directory has no ` [output]` suffix to read a root
    out of. Same two roots either way — nothing here rearranges `[temp]`.
    """
    if name == "output":
        return os.path.realpath(folder_paths.get_output_directory())
    if name in ("input", "", None):
        return os.path.realpath(folder_paths.get_input_directory())
    return None


def _clean_subfolder(raw):
    """A user-typed shelf name as a safe root-relative directory, or None.

    Rejects rather than sanitizes: a name that needs rewriting to be safe is a
    name the user should see refused, not silently changed.
    """
    raw = str(raw).strip().strip("/")
    if not raw:
        return ""
    parts = raw.replace("\\", "/").split("/")
    if any(not p or p.startswith(".") for p in parts):
        return None
    return "/".join(parts)


def _rooted(filename):
    """A picker path -> `(root, relative, annotation)`, or None if it is not ours.

    The ` [output]` suffix a gallery path carries is what says which folder it
    came out of, so the two organize routes take their root from the file rather
    than from a separate parameter that could disagree with it. An unannotated
    path is an input path, which is the shape every caller used before the
    gallery could be organized at all.
    """
    name, base = folder_paths.annotated_filepath(str(filename))
    if base is None:
        base, annotation = folder_paths.get_input_directory(), ""
    else:
        # Only the two roots the picker browses. `[temp]` is a real annotation
        # core would resolve, and nothing in this pack should be rearranging it.
        if os.path.realpath(base) != os.path.realpath(folder_paths.get_output_directory()):
            return None
        annotation = " [output]"
    return os.path.realpath(base), name, annotation


@PromptServer.instance.routes.post("/continuity/move")
async def move_asset(request):
    """Move one file into another subfolder of the root it already lives in —
    the picker's drag-a-thumbnail-onto-a-shelf.

    Renders organize the same way input files do. They *arrive* sorted, because
    the output prefix decides where a render lands (see `outputs.py`), but where
    a file was written is not where it has to stay: a keeper gets dragged out of
    the dated folder it landed in and onto a shelf of its own.
    """
    body = await request.json()
    subfolder = _clean_subfolder(body.get("subfolder", ""))
    if subfolder is None:
        return web.json_response({"error": "bad folder name"}, status=400)
    rooted = _rooted(body.get("filename", ""))
    if rooted is None:
        return web.json_response({"error": "that file is not in a folder the picker browses"},
                                 status=400)
    root, filename, annotation = rooted

    source = os.path.realpath(os.path.join(root, filename))
    if not folder_paths.is_within_directory(root, source) or not os.path.isfile(source):
        return web.json_response({"error": "no such file"}, status=404)

    target_dir = os.path.realpath(os.path.join(root, subfolder)) if subfolder else root
    if target_dir != root and not folder_paths.is_within_directory(root, target_dir):
        return web.json_response({"error": "bad folder name"}, status=400)
    target = os.path.join(target_dir, os.path.basename(source))
    if os.path.realpath(target) == source:
        return web.json_response({"path": filename + annotation})  # already there
    if os.path.exists(target):
        return web.json_response({"error": "a file with that name is already there"}, status=409)

    os.makedirs(target_dir, exist_ok=True)
    os.rename(source, target)
    relative = os.path.relpath(target, root).replace(os.sep, "/")
    # Annotated on the way back out, so the moved file is still addressable as
    # the same kind of thing it was: an attached render has to keep saying
    # `[output]` or `media.resolve` would look for it under input/.
    return web.json_response({"path": relative + annotation})


@PromptServer.instance.routes.post("/continuity/delete")
async def delete_asset(request):
    """Delete one file — organize mode's other action. Files only, never
    directories: a shelf whose last file goes simply drops out of the listing.

    A workflow that still references the file will fail at execute time with
    media.resolve's "not in the input folder any more", which is the honest
    answer — the picker cannot know what every saved workflow points at.

    Deleting a *render* is the case worth pausing on, and it is deliberate: a
    gallery you cannot throw anything out of stops being a gallery after a
    week's rendering. The picker asks first, and there is no undo, which is the
    same deal the input folder has always had.
    """
    body = await request.json()
    rooted = _rooted(body.get("filename", ""))
    if rooted is None:
        return web.json_response({"error": "that file is not in a folder the picker browses"},
                                 status=400)
    root, filename, _ = rooted
    path = os.path.realpath(os.path.join(root, filename))
    if not folder_paths.is_within_directory(root, path) or not os.path.isfile(path):
        return web.json_response({"error": "no such file"}, status=404)
    os.remove(path)
    return web.json_response({"ok": True})


@PromptServer.instance.routes.post("/continuity/folder")
async def make_folder(request):
    """Make a shelf — which is to say: make the directory.

    A shelf used to be a name in the user's preferences that a directory caught
    up with the first time a file was dragged onto it. That put the same fact in
    two places and let them disagree, and they did: the preferences outlived the
    disk, so a folder deleted from a terminal went on being offered by the picker
    for as long as the browser remembered typing it (#40).

    So there is one copy of it now, and it is the filesystem. Making a shelf
    makes the folder; the listing walks the disk and reports what is there;
    nothing is remembered anywhere else.
    """
    body = await request.json()
    root = _picker_root(body.get("root"))
    if root is None:
        return web.json_response({"error": "not a folder the picker browses"}, status=400)
    subfolder = _clean_subfolder(body.get("subfolder", ""))
    if not subfolder:
        return web.json_response({"error": "bad folder name"}, status=400)
    target = os.path.realpath(os.path.join(root, subfolder))
    if not folder_paths.is_within_directory(root, target):
        return web.json_response({"error": "bad folder name"}, status=400)
    if os.path.isfile(target):
        return web.json_response({"error": "a file with that name is already there"}, status=409)
    os.makedirs(target, exist_ok=True)
    return web.json_response({"folder": subfolder})


@PromptServer.instance.routes.post("/continuity/folder/delete")
async def remove_folder(request):
    """Remove an empty shelf.

    Empty is the whole of it: `os.rmdir` refuses anything else, and that refusal
    is the guard rather than a check this could get wrong. Deleting a folder of
    renders is a thing to do in a file manager, where what is about to go is
    visible; here it would be one press against a chip that says only how many.

    The counterpart of the route above, and it exists because that one is real
    now: a shelf typed by mistake used to be a preference nobody could see, and
    is a directory on the disk.
    """
    body = await request.json()
    root = _picker_root(body.get("root"))
    if root is None:
        return web.json_response({"error": "not a folder the picker browses"}, status=400)
    subfolder = _clean_subfolder(body.get("subfolder", ""))
    if not subfolder:
        return web.json_response({"error": "bad folder name"}, status=400)
    target = os.path.realpath(os.path.join(root, subfolder))
    if not folder_paths.is_within_directory(root, target) or not os.path.isdir(target):
        return web.json_response({"error": "no such folder"}, status=404)
    try:
        os.rmdir(target)
    except OSError:
        return web.json_response({"error": "that folder is not empty"}, status=409)
    return web.json_response({"ok": True})


def _plate_panels(body):
    """The panels a plate request describes, with only what the pixels need."""
    panels = []
    for panel in body.get("panels") or []:
        path = str(panel.get("path") or "").strip()
        if not path:
            continue
        made = {"path": path, "cut": bool(panel.get("cut"))}
        rect = panel.get("rect")
        if isinstance(rect, (list, tuple)) and len(rect) == 4:
            made["rect"] = [float(v) for v in rect]
        points = [{"x": float(p.get("x", 0)), "y": float(p.get("y", 0)),
                   "include": bool(p.get("include", True))}
                  for p in (panel.get("points") or []) if isinstance(p, dict)]
        if points:
            made["points"] = points
        panels.append(made)
    return panels


def _plate_models(body):
    return {"cutout": str(body.get("model") or ""),
            "segment": str(body.get("segment") or "")}


def _plate_job(body):
    """One accepted sheet, on the queue. See `creator/jobs.py`."""
    return plate.build(_plate_panels(body), _plate_models(body),
                       float(body.get("backdrop", 0.5)),
                       int(body.get("width") or 1280),
                       int(body.get("height") or 704))


jobs.register("plate", _plate_job)


@PromptServer.instance.routes.post("/continuity/plate")
async def build_plate(request):
    """Write the accepted sheet. See `creator/plate.py`.

    Posted when the sheet editor's Accept (or the picker's Add over an already
    confirmed group) commits — never while the sheet is merely being edited,
    which is what keeps `_plates/` holding only sheets somebody chose to keep.
    The editing preview never touches this route: it composites in the browser
    from `/plate/panel` cutouts, which are served from memory.

    Errors come back as `{"error": …}` with a 400 rather than as a 500, because
    every way this fails is something the user can act on — no model picked, a
    file that has been deleted out from under the picker, an install without
    core's background removal — and the editor puts the sentence on the sheet
    where the picture would have been.
    """
    body = await request.json()
    if not _plate_panels(body):
        return web.json_response({"error": "a plate needs at least one picture"},
                                 status=400)

    # Queued rather than run on a thread beside the prompt queue: a matte is a
    # forward pass through BiRefNet, and a sheet is one per panel. See
    # `creator/jobs.py`.
    try:
        prompt_id = await jobs.submit("plate", body, body.get("client_id"))
    except jobs.JobError as exc:
        return web.json_response({"error": str(exc)}, status=500)
    return web.json_response({"prompt_id": prompt_id})


# The sheet editor's per-panel cutouts, encoded once and held — bounded, and
# keyed by everything that changes the pixels (the file's stamp, the matte
# weights, the clicks), so replacing a photograph under the same name or moving
# a point makes a fresh matte rather than finding the stale one.
_PANEL_CACHE = {}
_PANEL_KEEP = 64


def _panel_png(panel, models):
    """One panel's cutout as RGBA PNG bytes — the subject over transparency.

    Transparent rather than composited, because the editor lays the panel over
    the backdrop itself: one encode serves every backdrop, and the browser's
    compositing is the same alpha-over `cutout.over` bakes on Accept.
    """
    import io as _io

    import numpy as np
    from PIL import Image

    image, alpha = plate.cut_panel(panel, models)
    rgb = image[0].clamp(0.0, 1.0).mul(255.0).round().to("cpu").numpy().astype(np.uint8)
    if alpha is None:
        made = Image.fromarray(rgb, "RGB")
    else:
        a = alpha[0].clamp(0.0, 1.0).mul(255.0).round().to("cpu").numpy().astype(np.uint8)
        made = Image.fromarray(np.dstack([rgb, a]), "RGBA")
    out = _io.BytesIO()
    made.save(out, format="PNG", compress_level=4)
    return out.getvalue()


@PromptServer.instance.routes.post("/continuity/plate/panel")
async def cut_plate_panel(request):
    """One panel of the sheet being edited, cut out, as a PNG — from memory,
    never from a file. This is what the editor's live preview is made of."""
    refused = jobs.refuse_if_busy()
    if refused is not None:
        return refused
    body = await request.json()
    panels = _plate_panels(body)
    if len(panels) != 1:
        return web.json_response({"error": "one panel at a time"}, status=400)
    panel, models = panels[0], _plate_models(body)

    try:
        stamp = media.stamp(panel["path"])
        key = json.dumps([stamp, models, panel.get("points") or [],
                          bool(panel.get("cut"))], sort_keys=True, default=str)
        png = _PANEL_CACHE.get(key)
        if png is None:
            loop = asyncio.get_running_loop()
            png = await loop.run_in_executor(
                None, lambda: _panel_png(panel, models))
            while len(_PANEL_CACHE) >= _PANEL_KEEP:
                _PANEL_CACHE.pop(next(iter(_PANEL_CACHE)))
            _PANEL_CACHE[key] = png
    except Exception as exc:                       # noqa: BLE001 — reported, not swallowed
        logging.exception("[MiniMax] cutting a panel failed")
        return web.json_response({"error": str(exc)}, status=400)
    return web.Response(body=png, content_type="image/png")


@PromptServer.instance.routes.get("/continuity/settings")
async def read_settings(request):
    """What the settings page shows: every key, filled in. See `settings.py`."""
    return web.json_response({"settings": settings.load()})


@PromptServer.instance.routes.post("/continuity/settings")
async def write_settings(request):
    """Store what the settings page changed and hand back what was stored.

    The reply is the whole settings object rather than an acknowledgement,
    because it is what the page then shows: a value the server would not write
    has to be visibly not written, not left on screen looking chosen.
    """
    try:
        stored = settings.save(await request.json())
    except ValueError as problem:
        return web.json_response({"error": str(problem)}, status=400)
    except OSError as problem:
        return web.json_response({"error": f"could not write the settings file: {problem}"},
                                 status=500)
    return web.json_response({"settings": stored})


@PromptServer.instance.routes.post("/continuity/settings/reset")
async def reset_settings(request):
    """Put every setting back to what this pack ships with. See `settings.reset`.

    Answers in the same shape the two routes above do, because the page treats
    it as one more write: what comes back is what is now in force.
    """
    try:
        stored = settings.reset()
    except OSError as problem:
        return web.json_response({"error": f"could not remove the settings file: {problem}"},
                                 status=500)
    return web.json_response({"settings": stored})


@PromptServer.instance.routes.get("/continuity/latent_cache")
async def read_latent_cache(request):
    """How much of the disk the reference cache is holding. See `latents.py`.

    Not part of the settings blob: `settings.clean` describes what this machine
    was *told*, and this is what happened as a result. A number the settings
    page could write would be a number somebody could set.
    """
    count, size = latents.usage()
    return web.json_response({"entries": count, "bytes": size})


@PromptServer.instance.routes.post("/continuity/latent_cache/clear")
async def clear_latent_cache(request):
    """Delete every cached reference. -> what was freed, so the page can say so.

    Safe at any moment, including mid-render: everything here is derived, and
    an entry deleted out from under a queued generation is an entry that
    generation encodes instead.
    """
    try:
        freed = latents.clear()
    except OSError as problem:
        return web.json_response({"error": f"could not clear the cache: {problem}"},
                                 status=500)
    return web.json_response({"freed": freed, "entries": 0, "bytes": 0})


@PromptServer.instance.routes.post("/continuity/compiled_prompt")
async def compiled_prompt(request):
    """The prompt the model will actually read, for the blob the editor holds.

    The box shows two things now — what you typed, and what is queued — and this
    is where the second one comes from. It has to be the compiler rather than a
    mirror of it in the frontend: the whole point of showing the finished prompt
    is that it is the finished prompt, and a JS re-implementation of `compose`
    would be a second opinion that agrees right up until the moment the
    disagreement is what you needed to see. `state.js` used to hold such a copy
    for the scope band, and it drifted from `contextir._DEFINE` twice.

    One entry per pass, in play order, because a timeline is not one prompt: the
    strip's cards are merged into runs and each run is a generation with its own
    six sections. `cards` maps a card's index to the pass holding it, so the box
    can show the prompt belonging to the card that is open rather than guessing
    that the two are numbered alike — on a strip with a merged run in it they
    are not.

    A blob that does not compile is not an error here. The editor asks on every
    keystroke and a half-typed piece is a normal thing to be holding — an empty
    shot, a chip whose file was just detached — so the failure is reported as
    text for the panel to show in place of the prompt.
    """
    try:
        data = await request.json()
    except (json.JSONDecodeError, ValueError) as problem:
        return web.json_response({"error": f"unreadable request: {problem}"}, status=400)

    blob = data.get("creator_data")
    if not isinstance(blob, dict):
        return web.json_response({"error": "creator_data must be a JSON object"}, status=400)

    try:
        # `timeline_payloads` and nothing else: it is what `creator_node.py`
        # builds the graph from, so it is what the render will actually be, one
        # entry per pass, merged runs already merged.
        payloads = compiler.timeline_payloads(blob, media.image_size)
        # Which pass each card ended up in. A run of merged cards is one
        # generation with one prompt, so the box has to be able to ask "the pass
        # holding card 4" rather than "pass 4" — they are only the same number
        # on a strip nothing merged.
        piece = compiler.as_piece(blob)
        segments = compiler.timeline_segments(piece)
        runs = compiler.timeline_runs(piece, segments)
        card_pass = {}
        for position, (start, end) in enumerate(runs):
            for card in range(start, end):
                card_pass[card] = position

        passes = []
        for index, payload in enumerate(payloads):
            if payload.get("clip"):
                # Supplied footage. There is nothing to compile and nothing the
                # model reads, and saying so is better than showing an empty box.
                passes.append({"index": index, "clip": True, "prompt": "",
                               "mode": "", "checkpoint": ""})
                continue
            compiled = compiler.compile_segment(payload, media.image_size)
            passes.append({
                "index": index,
                "clip": False,
                "mode": compiled.mode,
                "checkpoint": compiled.checkpoint,
                # A hand-written blob may replace the composed prompt outright,
                # and `timeline.py` swaps it in after compiling. What the model
                # reads is the override where there is one, so that is what the
                # box has to show.
                "prompt": payload.get("prompt_override") or compiled.prompt,
                "overridden": bool(payload.get("prompt_override")),
            })
    except compiler.CompileError as problem:
        return web.json_response({"passes": [], "problem": str(problem)})
    except (ValueError, KeyError, TypeError, IndexError) as problem:
        return web.json_response({"passes": [], "problem": str(problem)})

    return web.json_response({"passes": passes, "cards": card_pass})

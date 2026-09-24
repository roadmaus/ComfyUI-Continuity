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
import os

from aiohttp import web

import folder_paths
from server import PromptServer

from . import (assets, compile as compiler, crop as framing, latents, lift, lorameta, media,
               models, refmod, preview, settings, vdn)
from .guard import same_origin

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


# What is answered by opening a picture rather than a container. Extensions
# rather than a try/except chain around `av`: PyAV will happily open a PNG as a
# one-frame container and spend a decode doing it, so "is this a picture" has to
# be asked before the reader is chosen, not after it fails.
_STILL_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff")


def _read_still_header(path):
    """A picture's own size, without decoding it.

    `Image.open` reads the header and stops, so this costs a few kilobytes of a
    file that may be a 60 MB PNG. The orientation tag is applied as a swap
    rather than by transposing the picture — for the reason `preview.py` gives
    when it does transpose one: the browser turns the full picture, so anything
    reporting its size has to report the turned one.
    """
    from PIL import Image

    with Image.open(path) as image:
        width, height = image.size
        try:
            orientation = image.getexif().get(274)
        except Exception:  # noqa: BLE001 — a picture with no readable tags is not turned
            orientation = None
    if orientation in (5, 6, 7, 8):
        width, height = height, width
    return {"has_audio": False, "duration": None, "width": width, "height": height}


def _read_header(path):
    """What this file is, off its header. -> the probe's four fields.

    A still answers here too, and not only because a surface that asks "how big
    is this" should get one answer for both kinds. The upscale bench used to
    take a picture's size off the thumbnail it had already loaded, which is
    capped at 320 pixels — so every figure derived from it, the locator's square
    included, described a picture 320 pixels wide that nobody had.
    """
    if os.path.splitext(path)[1].lower() in _STILL_SUFFIXES:
        return _read_still_header(path)

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
    """What is in this file: a soundtrack, a length, a size.

    A reference video is attached with its sound on by default, which is only the
    right default when there is sound to bind — otherwise the generation would
    fail at queue time on a file the user never claimed was noisy. No browser
    reports the presence of an audio track portably, so the answer comes from
    here. It reads the container header, not the media.

    `has_audio: null` means the question could not be answered; the caller keeps
    its own default rather than guessing silence.
    """
    filename = request.query.get("filename", "")
    if refmod.is_mod(filename):
        # A mod's picture is its latent grid at the VAE's stride, and it has no
        # soundtrack and no length: the header says all of it, no container.
        try:
            meta = refmod.header(refmod.resolve(filename))
        except refmod.RefModError as exc:
            return web.json_response({"has_audio": None, "error": str(exc)}, status=404)
        return web.json_response({"has_audio": False, "width": meta["latent_w"] * 16,
                                  "height": meta["latent_h"] * 16, "mod": True,
                                  "tokens": meta["tokens"], "mode": meta["mode"]})
    path = assets.input_path(request)
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
    path = assets.input_path(request)
    if path is None:
        return web.json_response({"error": "not in the input or output folder"}, status=404)
    try:
        loop = asyncio.get_running_loop()
        return web.json_response(await loop.run_in_executor(None, assets.read_embedded, path))
    except Exception as exc:  # noqa: BLE001 — an unreadable file is the caller's problem
        return web.json_response({"prompt": None, "workflow": None, "error": str(exc)})


def _query_crop(text):
    """The thumb route's `crop` parameter -> `crop.Crop` or None.

    Positional in the URL rather than JSON, so the string is short enough to
    read in a network tab and stable enough to be a cache key.
    """
    if not text:
        return None
    parts = text.split(",")
    if len(parts) < 4:
        raise framing.CropError("crop needs x,y,w,h")
    raw = {"x": parts[0], "y": parts[1], "w": parts[2], "h": parts[3]}
    if len(parts) > 4:
        raw["turn"] = parts[4]
    if len(parts) > 5:
        raw["mirror"] = parts[5]
    return framing.parse(raw, "thumb")


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
    filename = request.query.get("filename", "")
    if refmod.is_mod(filename):
        # A mod's picture is the sidecar beside it — written when it was made,
        # or by the first render that decoded it. Nothing is decoded here: a
        # route runs on a pool worker, and the VAE stays on the render thread.
        try:
            path = refmod.preview_path(refmod.resolve(filename))
        except refmod.RefModError:
            path = None
    else:
        path = assets.input_path(request)
    if path is None:
        return web.Response(status=404)
    # `crop=x,y,w,h[,turn[,mirror]]` draws the framed picture — the same
    # window `media.load_image` hands the render, so a chip's thumbnail shows
    # what the model gets. `full=1` keeps the source's size: the subject view
    # clicks on the framed picture and needs every pixel of it.
    try:
        crop = _query_crop(request.query.get("crop"))
    except framing.CropError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    thumb = await preview.thumbnail(path, crop=crop, full=request.query.get("full") == "1")
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
    path = assets.input_path(request)
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


@PromptServer.instance.routes.get("/continuity/lora_names")
async def list_lora_names(request):
    """Every LoRA's name and nothing else — the turbo pickers' listing.

    They used to read the folder listing above and keep the names off its rows,
    which cost a stat per file and a sidecar read per row on the first press
    after a fresh start — minutes on a large folder, during which a press did
    nothing (issue #41) — and handed back only the newest MAX_LORAS, so a
    distillation older than the cap was not offered at all. This is the name
    list core already holds, off the loop for the one scan a cold start pays.
    """
    loop = asyncio.get_running_loop()
    return web.json_response({"names": await loop.run_in_executor(None, _lora_names)})


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
@same_origin
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


@PromptServer.instance.routes.get("/continuity/vdn")
async def list_vdn(request):
    """The VDN-H3 stages under `models/vdn`, for the sampler row's pill.

    Directories rather than files, which is why the weights listing cannot
    answer this — and asked when the pill opens rather than written into the
    manifest, so a stage downloaded after boot is offered without a restart.
    Off the event loop for the same reason `/continuity/models` is: it walks
    a model directory.
    """
    loop = asyncio.get_running_loop()
    names = await loop.run_in_executor(None, vdn.checkpoints)
    return web.json_response({"checkpoints": names})


@PromptServer.instance.routes.get("/continuity/assets")
async def list_assets(request):
    """The picker's grid: `?root=input` (the default) or `?root=output` — or one
    of the two places that are not media folders, `refmods` and `meshes`.

    The output listing is the gallery — finished renders, browsed with the same
    machinery as the input folder. Its paths come back annotated (` [output]`),
    which is what lets one of them be attached as a reference: see `assets.scan`.
    """
    if request.query.get("root") == "refmods":
        # Saved references, out of the model folders: a different place with
        # its own rows, browsed by the same grid. See `refmod.listing`.
        loop = asyncio.get_running_loop()
        rows, folders = await loop.run_in_executor(None, refmod.listing)
        rows.sort(key=lambda a: a["mtime"], reverse=True)
        return web.json_response({"assets": rows, "folders": folders, "truncated": False})
    if request.query.get("root") == "meshes":
        # The image-to-3D tool's shelf, each GLB with the papers it was kept
        # with. A place of its own for the same reason: a mesh is no kind the
        # media folders list, and no reference slot could take one.
        loop = asyncio.get_running_loop()
        rows, folders = await loop.run_in_executor(None, lift.shelf)
        rows.sort(key=lambda a: a["mtime"], reverse=True)
        return web.json_response({"assets": rows, "folders": folders, "truncated": False})
    if request.query.get("root") == "output":
        root, annotation = folder_paths.get_output_directory(), " [output]"
    else:
        root, annotation = folder_paths.get_input_directory(), ""
    if not os.path.isdir(root):
        return web.json_response({"assets": [], "folders": [], "truncated": False})

    # A walk with two stat calls per file is nothing on a local disk and minutes
    # on a network share, and the event loop is also the prompt queue.
    loop = asyncio.get_running_loop()
    found, folders = await loop.run_in_executor(None, assets.scan, root, annotation)
    found.sort(key=lambda a: a["mtime"], reverse=True)
    truncated = len(found) > MAX_ASSETS
    # Not capped with the files. `MAX_ASSETS` is there so a folder of ten
    # thousand renders does not become a ten-megabyte JSON body, and the shelf
    # row is the one part of a truncated listing that must still be whole:
    # dropping folders would hide the places the missing files are in.
    return web.json_response({"assets": found[:MAX_ASSETS], "folders": sorted(folders),
                              "truncated": truncated})


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
@same_origin
async def move_asset(request):
    """Move one file into another subfolder of the root it already lives in —
    the picker's drag-a-thumbnail-onto-a-shelf.

    Renders organize the same way input files do. They *arrive* sorted, because
    the output prefix decides where a render lands (see `outputs.py`), but where
    a file was written is not where it has to stay: a keeper gets dragged out of
    the dated folder it landed in and onto a shelf of its own.
    """
    body = await request.json()
    subfolder = assets.clean_subfolder(body.get("subfolder", ""))
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
@same_origin
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
@same_origin
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
    root = assets.picker_root(body.get("root"))
    if root is None:
        return web.json_response({"error": "not a folder the picker browses"}, status=400)
    subfolder = assets.clean_subfolder(body.get("subfolder", ""))
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
@same_origin
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
    root = assets.picker_root(body.get("root"))
    if root is None:
        return web.json_response({"error": "not a folder the picker browses"}, status=400)
    subfolder = assets.clean_subfolder(body.get("subfolder", ""))
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


@PromptServer.instance.routes.get("/continuity/settings")
async def read_settings(request):
    """What the settings page shows: every key, filled in. See `settings.py`."""
    return web.json_response({"settings": settings.load()})


@PromptServer.instance.routes.post("/continuity/settings")
@same_origin
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
@same_origin
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
@same_origin
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


# What "this blob does not compile" arrives as. `CompileError` is the pack's own
# refusal and carries a sentence; the four below are what a hand-edited or
# half-typed blob raises on the way there — a string where a number belongs, a
# key nothing filled in. Named as one tuple because two callers now answer them
# identically and a third would otherwise catch a different four.
COMPILE_FAILURES = (compiler.CompileError, ValueError, KeyError, TypeError, IndexError)


def compiled_passes(blob, seed=None):
    """The prompt each pass of `blob` will read: `{"passes": [...], "cards": {...}}`.

    The body of the route below, lifted out so that the chat room can run the
    same dry run before it queues anything. That is the whole point of the dry
    run — a missing weight or a duration off the frame grid becomes a sentence
    before any GPU time — and a second copy of it in another module would be a
    second opinion that agrees until the disagreement is what mattered.

    Raises: `COMPILE_FAILURES`. Both callers turn that into a sentence; neither
    treats it as an error, because a blob that does not compile yet is the
    ordinary state of one being typed and of one a chat model just wrote.
    """
    # `timeline_payloads` and nothing else: it is what `creator_node.py`
    # builds the graph from, so it is what the render will actually be, one
    # entry per pass, merged runs already merged.
    # The choices a `{a|b|c}` makes are the render's, on the number the
    # node will queue — passed in so the panel shows the take this seed
    # would shoot rather than the braces as typed. An older frontend
    # sends none, and the braces are shown as they stand.
    if isinstance(seed, (int, float)) and not isinstance(seed, bool):
        blob = compiler.varied_piece(blob, int(seed))
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
    return {"passes": passes, "cards": card_pass}


@PromptServer.instance.routes.post("/continuity/compiled_prompt")
@same_origin
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
        compiled = compiled_passes(blob, data.get("seed"))
    except COMPILE_FAILURES as problem:
        return web.json_response({"passes": [], "problem": str(problem)})

    return web.json_response(compiled)

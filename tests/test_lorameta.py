"""Six tools' sidecars, one record.

Runs standalone — `python tests/test_lorameta.py` — with no torch and no
ComfyUI, which is the property `lorameta.py` is written to keep: paths arrive
absolute and nothing in it reaches for `folder_paths`.

What is worth pinning here is not that each reader parses its own format —
that is one `json.load` each — but the three things that are easy to get wrong
and impossible to notice from a screenshot:

  * that a raw Civitai model-version's `name` becomes the *version* and
    `model.name` becomes the title, because reading the second format through
    the first one's vocabulary puts "v2.0" on every card and looks fine;
  * that a user's own activation text beats the website's trained words, and
    that a title from a website still wins over one guessed from a header;
  * that CiviMeta, which is the only layout this pack could read before any of
    the others existed, still comes out exactly as it used to.
"""

import importlib.util
import json
import os
import struct
import sys

import layout
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

spec = importlib.util.spec_from_file_location("lorameta", layout.py("lorameta"))
lorameta = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lorameta)

from harness import FAILURES, check


# ---- fixtures ---------------------------------------------------------------

# A PNG the size checks will accept. Content does not matter to anything here
# except `png_recipe`, which reads chunks and is given a real one below.
BLOB = b"\x89PNG\r\n\x1a\n" + b"\0" * 200


def write(path, data=BLOB):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)
    return path


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    return path


def safetensors(path, metadata):
    """A file with a real safetensors header and no tensors behind it."""
    header = json.dumps({"__metadata__": metadata}).encode("utf-8")
    return write(path, struct.pack("<Q", len(header)) + header)


def png(path, text):
    """A PNG carrying one tEXt chunk, which is how A1111 stores a recipe."""
    import zlib

    def chunk(kind, body):
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))

    body = b"parameters\x00" + text.encode("latin-1")
    return write(path, lorameta._PNG_MAGIC
                 + chunk(b"IHDR", b"\0" * 13)
                 + chunk(b"tEXt", body)
                 + chunk(b"IEND", b""))


# A Civitai model-version response, trimmed to the fields that matter. The trap
# it exists to spring: `name` here is the version, not the model.
VERSION = {
    "id": 4242,
    "modelId": 99,
    "name": "v2.0",
    "baseModel": "Wan Video 14B",
    "description": "<p>version notes</p>",
    "trainedWords": ["sksdog", "a photo of sksdog"],
    "stats": {"downloadCount": 1500, "thumbsUpCount": 60},
    "model": {"name": "Good Dog", "type": "LORA", "nsfw": False},
    "files": [
        {"name": "training.zip", "primary": False, "hashes": {"SHA256": "BAD"}},
        {"name": "dog.safetensors", "primary": True, "hashes": {"SHA256": "ABCDEF"}},
    ],
    "images": [
        {"nsfw": False, "meta": {"prompt": "sksdog running", "seed": 7, "cfgScale": 3.5}},
        {"nsfw": True, "meta": {"prompt": "second", "steps": 20}},
    ],
}

# The model-level object, which is the only place tags, the description and the
# sibling versions live.
MODEL = {
    "id": 99,
    "name": "Good Dog",
    "type": "LORA",
    "description": "<p>about the model</p>",
    "tags": ["dog", "animal"],
    "creator": {"username": "someone"},
    "allowCommercialUse": ["Image", "Rent"],
    "allowNoCredit": False,
    "allowDerivatives": True,
    "stats": {"downloadCount": 1500, "favoriteCount": 12, "commentCount": 3},
    "modelVersions": [
        {"id": 4242, "name": "v2.0", "baseModel": "Wan Video 14B", "createdAt": "2025-01-02"},
        {"id": 4000, "name": "v1.0", "baseModel": "Wan Video 14B", "createdAt": "2024-11-01"},
    ],
}


def fresh(directory, name="dog.safetensors"):
    """A model file in its own subdirectory, so layouts never collide."""
    lorameta.forget()
    holder = os.path.join(directory, str(len(os.listdir(directory))))
    os.makedirs(holder)
    return safetensors(os.path.join(holder, name), {})


with tempfile.TemporaryDirectory() as directory:

    # ---- CiviMeta, which must come out exactly as it always did -------------

    path = fresh(directory)
    sidecar = path + lorameta.CIVIMETA_SUFFIX
    write_json(os.path.join(sidecar, "meta.json"), {
        "name": "Good Dog",
        "versionName": "v2.0",
        "type": "LORA",
        "baseModel": "Wan Video 14B",
        "trainedWords": ["sksdog"],
        "tags": ["dog"],
        "modelId": 99,
        "versionId": 4242,
        "hash": "abcdef",
        "creator": {"username": "someone"},
        "stats": {"downloads": 1500, "favorites": 12},
        # The set literal CiviMeta stores this as, which is not what the API
        # returns and is the whole reason `_commercial` accepts both.
        "license": {"allowCommercialUse": "{Image,Rent}", "allowNoCredit": False,
                    "allowDerivatives": True},
        "versions": [{"id": 4242, "name": "v2.0", "baseModel": "Wan Video 14B"}],
        "fetchedAt": "2025-06-01",
    })
    write_json(os.path.join(sidecar, "images.json"), {"items": [
        {"nsfw": False, "meta": {"prompt": "first", "seed": 1, "cfgScale": 3.5}},
        {"nsfw": True, "meta": {"prompt": "second"}},
    ]})
    write(os.path.join(sidecar, "media", "001.mp4"))
    write(os.path.join(sidecar, "media", "002.webp"))
    write(os.path.join(sidecar, "thumbnails", "002.webp"))

    record = lorameta.describe(path, deep=True)
    check("civimeta keeps the model as the title", record["title"], "Good Dog")
    check("civimeta keeps the version as the version", record["version"], "v2.0")
    check("civimeta trigger words", record["trained_words"], ["sksdog"])
    check("civimeta stats are renamed once", record["stats"],
          {"downloads": 1500, "favorites": 12})
    check("civimeta's set-literal license", record["license"],
          {"commercial": ["Image", "Rent"], "credit": True, "derivatives": True})
    check("civimeta is the source", record["sources"][0], "civimeta")
    # A video showcase has no thumbnail, so media/ is what the card gets — the
    # behaviour the manager's still-frame and hover-clip both depend on.
    check("civimeta prefers a thumbnail for the card", record["preview"]["kind"], "image")
    check("civimeta showcase length", len(record["showcase"]), 2)
    check("civimeta showcase is the creator's order",
          [item["kind"] for item in record["showcase"]], ["video", "image"])
    check("civimeta numbers its gallery from one",
          record["showcase"][0]["meta"], {"prompt": "first", "seed": 1, "cfg": 3.5})
    check("civimeta carries the nsfw flag per image",
          record["showcase"][1]["nsfw"], True)
    check("only the image has a thumbnail",
          [bool(item["thumb"]) for item in record["showcase"]], [False, True])

    # ---- a raw .civitai.info, where `name` means something else -------------

    path = fresh(directory)
    write_json(path.replace(".safetensors", "") + ".civitai.info", VERSION)
    record = lorameta.describe(path)
    check("civitai.info title comes from model.name", record["title"], "Good Dog")
    check("civitai.info version comes from name", record["version"], "v2.0")
    check("civitai.info base model", record["base_model"], "Wan Video 14B")
    check("civitai.info trigger words", record["trained_words"],
          ["sksdog", "a photo of sksdog"])
    check("civitai.info takes the primary file's hash", record["hash"], "abcdef")
    check("civitai.info version stats", record["stats"],
          {"downloads": 1500, "favorites": 60})

    # The model-level file Browser+ writes beside it is where the rest lives.
    path = fresh(directory)
    stem = path.replace(".safetensors", "")
    write_json(stem + ".civitai.info", VERSION)
    write_json(stem + ".api_info.json", MODEL)
    write(stem + "_0.jpg")
    write(stem + "_1.jpg")
    # A sibling LoRA sharing the prefix must not be mistaken for image two.
    safetensors(stem + "_v3.safetensors", {})
    write(stem + "_v3.preview.png")
    record = lorameta.describe(path, deep=True)
    check("the model file supplies the tags", record["tags"], ["dog", "animal"])
    check("the model file supplies the description", record["description"],
          "<p>about the model</p>")
    check("the version keeps its own description", record["version_description"],
          "<p>version notes</p>")
    check("the model file supplies the creator", record["creator"], "someone")
    check("the model file supplies the siblings", len(record["versions"]), 2)
    check("an array license reads the same as a set literal", record["license"],
          {"commercial": ["Image", "Rent"], "credit": True, "derivatives": True})
    check("numbered showcase found", len(record["showcase"]), 2)
    check("a sibling LoRA is not showcase media",
          [os.path.basename(item["path"]) for item in record["showcase"]],
          ["dog_0.jpg", "dog_1.jpg"])
    check("numbered showcase zips with the images array from zero",
          record["showcase"][0]["meta"], {"prompt": "sksdog running", "seed": 7, "cfg": 3.5})
    check("and carries their nsfw flags", record["showcase"][1]["nsfw"], True)

    # Civitai Helper writes `{}` when a hash was not found, so that it never
    # rescans. That is a file saying "not on Civitai", not a broken sidecar.
    path = fresh(directory)
    write_json(path.replace(".safetensors", "") + ".civitai.info", {})
    record = lorameta.describe(path)
    check("an empty .civitai.info claims nothing", record.get("title"), None)
    check("...but is still a source that spoke", record["sources"], ["civitai_info"])

    # ---- ComfyUI-Lora-Manager ----------------------------------------------

    path = fresh(directory)
    stem = path.replace(".safetensors", "")
    write_json(stem + ".metadata.json", {
        "file_name": "dog",
        "model_name": "Good Dog",
        "sha256": "ABCDEF",
        "base_model": "Wan Video 14B",
        "tags": ["dog", "animal"],
        "modelDescription": "<p>about the model</p>",
        "notes": "works best at 0.7",
        "usage_tips": json.dumps({"strength": 0.7}),
        "civitai": VERSION,
    })
    write(stem + ".preview.mp4")
    record = lorameta.describe(path)
    check("lora manager title", record["title"], "Good Dog")
    check("lora manager reads the nested version", record["version"], "v2.0")
    check("lora manager notes", record["notes"], "works best at 0.7")
    check("lora manager usage tips become a strength", record["strength"], 0.7)
    check("lora manager hash is lowercased for the gallery lookup",
          record["hash"], "abcdef")
    # The reason `.preview.mp4` is worth supporting at all: an H3 LoRA
    # showcases a clip, and the card can play one.
    check("a video preview is found and reported as video",
          record["preview"]["kind"], "video")

    # ---- A1111 and everything downstream of it -----------------------------

    path = fresh(directory)
    stem = path.replace(".safetensors", "")
    write_json(stem + ".json", {
        "description": "my own notes",
        "activation text": "mydog, good boy",
        "preferred weight": 0.85,
        "sd version": "SDXL",
    })
    write(stem + ".preview.png")
    record = lorameta.describe(path)
    check("a1111 activation text becomes the triggers",
          record["trained_words"], ["mydog", "good boy"])
    check("a1111 preferred weight becomes the strength", record["strength"], 0.85)
    check("a1111 description", record["description"], "my own notes")
    check("a loose preview is found", record["preview"]["kind"], "image")

    # A `.txt` beside the file is a description too — A1111's oldest form, and
    # what hayden-fr's manager writes as `.md`.
    path = fresh(directory)
    write(path.replace(".safetensors", "") + ".txt", b"plain text description")
    check("a bare .txt is a description",
          lorameta.describe(path)["description"], "plain text description")

    # ---- who wins ----------------------------------------------------------

    # The case the merge exists for: Civitai knows the title, the user knows the
    # triggers. A picker that took both from the same file would throw away
    # whichever opinion that file did not hold.
    path = fresh(directory)
    stem = path.replace(".safetensors", "")
    write_json(stem + ".civitai.info", VERSION)
    write_json(stem + ".json", {"activation text": "mydog", "preferred weight": 0.6})
    record = lorameta.describe(path)
    check("the website keeps the title", record["title"], "Good Dog")
    check("the user keeps the triggers", record["trained_words"], ["mydog"])
    check("the user keeps the weight", record["strength"], 0.6)
    check("both sources are named", record["sources"], ["civitai_info", "a1111"])

    # ---- the file itself ---------------------------------------------------

    path = fresh(directory, "solo.safetensors")
    safetensors(path, {
        "modelspec.title": "Hand Trained",
        "modelspec.author": "me",
        "modelspec.trigger_phrase": "sks style",
        "modelspec.tags": "style, painterly",
        "modelspec.usage_hint": "0.8 works",
        "modelspec.thumbnail": "data:image/png;base64,"
                               + __import__("base64").b64encode(BLOB).decode(),
    })
    record = lorameta.describe(path, deep=True)
    check("modelspec title", record["title"], "Hand Trained")
    check("modelspec author is the creator", record["creator"], "me")
    check("a trigger phrase is one trigger", record["trained_words"], ["sks style"])
    check("modelspec tags split on commas", record["tags"], ["style", "painterly"])
    check("the embedded thumbnail is the card image",
          record["preview"]["kind"], "image")
    check("...and is served from memory, not from a path",
          record["preview"]["path"], None)

    # kohya's embedded gallery, which ComfyUI core already serves for its own
    # model library.
    path = fresh(directory, "kohya.safetensors")
    safetensors(path, {
        "ss_output_name": "kohya_dog",
        "ssmd_cover_images": json.dumps([__import__("base64").b64encode(BLOB).decode()]),
    })
    record = lorameta.describe(path, deep=True)
    check("cover images become a showcase", len(record["showcase"]), 1)
    check("...sniffed to a content type",
          record["showcase"][0]["mime"], "image/png")

    # A file with nothing beside it and nothing in its header is not an error;
    # it is a card with a filename on it, which is what it always was.
    path = fresh(directory, "bare.safetensors")
    record = lorameta.describe(path)
    check("a bare file claims nothing", record.get("title"), None)
    check("a bare file has no preview", record.get("preview"), None)
    check("a bare file names no sources", record["sources"], [])
    check("a bare file's detail opens as a spec sheet",
          lorameta.detail("bare.safetensors", path)["meta"], None)

    # ---- a recipe out of the picture ---------------------------------------

    path = fresh(directory)
    png(path.replace(".safetensors", "") + ".preview.png",
        "a painting of a dog\n"
        "Negative prompt: blurry, low quality\n"
        "Steps: 24, Sampler: DPM++ 2M, CFG scale: 7, Seed: 12345, Model: sdxl")
    record = lorameta.describe(path, deep=True)
    check("a lone preview is a gallery of one", len(record["showcase"]), 1)
    check("the recipe is read out of the PNG", record["showcase"][0]["meta"], {
        "prompt": "a painting of a dog",
        "negative_prompt": "blurry, low quality",
        "seed": 12345,
        "steps": 24,
        "cfg": 7,
        "sampler": "DPM++ 2M",
    })

    # No settings line means every line is prompt — an image saved before the
    # generation finished, which must not have its last line eaten.
    check("a parameters block with no settings is all prompt",
          lorameta.parse_a1111("just a prompt\nsecond line"),
          {"prompt": "just a prompt\nsecond line"})
    check("no negative section means no negative key",
          lorameta.parse_a1111("hello\nSteps: 20"), {"prompt": "hello", "steps": 20})

    # ---- the listing row ----------------------------------------------------

    path = fresh(directory)
    stem = path.replace(".safetensors", "")
    write_json(stem + ".civitai.info", VERSION)
    write_json(stem + ".api_info.json", MODEL)
    write(stem + ".preview.png")
    built = lorameta.row("sub/dog.safetensors", path)
    check("the row keeps the name it was asked about",
          built["name"], "sub/dog.safetensors")
    check("the row splits the folder off", built["folder"], "sub")
    check("the row carries the title", built["title"], "Good Dog")
    check("the row carries the preview kind", built["preview"], "image")
    check("the row carries the triggers for seeding a new entry",
          built["trained_words"], ["sksdog", "a photo of sksdog"])
    check("the row carries downloads for the card", built["downloads"], 1500)
    check("the row says which tools spoke", built["sources"],
          ["civitai_info", "loose"])
    check("a second read is the cached row", lorameta.row("sub/dog.safetensors", path), built)

    # Adding a sidecar has to invalidate it, or the manager would need a restart
    # to notice a LoRA it just identified.
    write_json(stem + ".json", {"activation text": "typed by hand"})
    check("adding a sidecar invalidates the cached row",
          lorameta.row("sub/dog.safetensors", path)["trained_words"], ["typed by hand"])

    # ---- the detail sheet ---------------------------------------------------

    sheet = lorameta.detail("sub/dog.safetensors", path)
    check("the sheet links out when there is a model to link to",
          sheet["meta"]["url"], "https://civitai.com/models/99?modelVersionId=4242")
    check("the sheet's showcase is index-addressable",
          [item["index"] for item in sheet["showcase"]], [0])
    check("the sheet carries the header either way",
          isinstance(sheet["header"].get("metadata"), dict), True)
    check("the sheet holds no bytes and no paths",
          set(sheet["showcase"][0]), {"index", "kind", "thumb", "meta", "nsfw"})

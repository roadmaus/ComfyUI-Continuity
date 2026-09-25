"""Card labels from local cm-info sidecars must not rewrite model metadata.

Runs standalone with synthetic files, without torch or ComfyUI:
    python tests/test_lora_card_labels.py
"""

import importlib.util
import json
import os
import struct
import tempfile

import layout
from harness import check, passed


spec = importlib.util.spec_from_file_location("lorameta", layout.py("lorameta"))
lorameta = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lorameta)

NAME = "Lighting/StudioLighting_V1.safetensors"
TITLE = "Studio Lighting"
SUBTITLE = "Example Base · Version One"
LABELS = {
    "UserTitle": "  Studio Lighting  ",
    "ModelName": "Catalog Lighting",
    "BaseModel": " Example Base ",
    "VersionName": " Version One ",
    # These are deliberately different from every existing metadata provider.
    "TrainedWords": ["sidecar must not replace triggers"],
}
EMBEDDED = {
    "modelspec.title": "OriginalTrainingRun",
    "modelspec.architecture": "trainer/internal",
    "modelspec.trigger_phrase": "studio_light",
}


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)


def write_json(path, value):
    write(path, json.dumps(value, ensure_ascii=False).encode("utf-8"))


def fresh(directory, name=NAME):
    lorameta.forget()
    path = os.path.join(directory, str(len(os.listdir(directory))), *name.split("/"))
    header = json.dumps({"__metadata__": EMBEDDED}).encode("utf-8")
    write(path, struct.pack("<Q", len(header)) + header)
    return path, os.path.splitext(path)[0]


def labels(label, built, title, subtitle):
    check(label + ": title", built.get("card_title"), title)
    check(label + ": subtitle", built.get("card_subtitle"), subtitle)
    check(label + ": loadable name is unchanged", built["name"], NAME)


def metadata_snapshot(path, deep):
    return {key: value for key, value in lorameta.describe(path, deep=deep).items()
            if key != "probe"}


def row_metadata(built):
    return {key: value for key, value in built.items()
            if key not in ("card_title", "card_subtitle")}


def changed_directory(path):
    """Make a create/delete observable even on coarse filesystem timestamps."""
    directory = os.path.dirname(path)
    stamp = os.stat(directory)
    os.utime(directory, (stamp.st_atime, stamp.st_mtime + 2))


def edit_in_place(path, payload):
    """An edit need not touch the directory mtime; TTL or Rescan must find it."""
    directory = os.path.dirname(path)
    folder_stamp = os.stat(directory)
    file_stamp = os.stat(path)
    write_json(path, payload)
    os.utime(path, (file_stamp.st_atime, file_stamp.st_mtime + 2))
    os.utime(directory, (folder_stamp.st_atime, folder_stamp.st_mtime))


with tempfile.TemporaryDirectory() as directory:
    path, stem = fresh(directory)
    write_json(stem + ".cm-info.json", LABELS)
    built = lorameta.row(NAME, path)
    labels("local display values", built, TITLE, SUBTITLE)
    check("embedded title is retained", built["title"], "OriginalTrainingRun")
    check("architecture remains metadata", built["base_model"], "trainer/internal")
    check("triggers remain metadata", built["trained_words"], ["studio_light"])
    check("display sidecar is not a metadata provider", built["sources"], ["header"])
    check("an unchanged row uses the cache", lorameta.row(NAME, path) is built, True)

    # A malformed or empty display sidecar must not expose the embedded title
    # and architecture on the card. Fallbacks are the exact filename and path.
    invalid = [
        ("absent", None),
        ("malformed", b"{not json"),
        ("invalid UTF-8", b"\xff\xfe"),
        ("null", b"null"),
        ("array", b"[]"),
        ("string", b'"wrong shape"'),
        ("number", b"42"),
        ("boolean", b"true"),
        ("empty object", b"{}"),
        ("blank fields", json.dumps({key: " \t\n" for key in LABELS}).encode()),
        ("null fields", json.dumps({key: None for key in LABELS}).encode()),
        ("wrong field types", json.dumps({
            "UserTitle": 5, "ModelName": ["bad"],
            "BaseModel": {"name": "bad"}, "VersionName": True,
        }).encode()),
    ]
    for label, contents in invalid:
        path, stem = fresh(directory)
        if contents is not None:
            write(stem + ".cm-info.json", contents)
        labels(label, lorameta.row(NAME, path), "StudioLighting_V1", NAME)

    # Each usable field works independently. A bad UserTitle must not hide a
    # usable ModelName, and an incomplete subtitle must not grow a stray dot.
    partial = [
        ("model title", {"ModelName": " Catalog Lighting "}, "Catalog Lighting", NAME),
        ("blank user title", {"UserTitle": " ", "ModelName": "Catalog Lighting"},
         "Catalog Lighting", NAME),
        ("invalid user title", {"UserTitle": {}, "ModelName": "Catalog Lighting"},
         "Catalog Lighting", NAME),
        ("base alone", {"BaseModel": " Example Base "}, "StudioLighting_V1", "Example Base"),
        ("version alone", {"VersionName": " Version One "}, "StudioLighting_V1", "Version One"),
        ("invalid base", {"BaseModel": [], "VersionName": "Version One"},
         "StudioLighting_V1", "Version One"),
        ("invalid version", {"BaseModel": "Example Base", "VersionName": False},
         "StudioLighting_V1", "Example Base"),
        ("unicode values", {"UserTitle": "조명 연습", "BaseModel": "예제 기반",
                            "VersionName": "버전 α"}, "조명 연습", "예제 기반 · 버전 α"),
    ]
    for label, payload, title, subtitle in partial:
        path, stem = fresh(directory)
        write_json(stem + ".cm-info.json", payload)
        labels(label, lorameta.row(NAME, path), title, subtitle)

    # Lookup is case-insensitive like existing companions, but still exact:
    # a similarly named model and the extension-appended layout are not ours.
    unicode_name = "Lighting/조명_Édition_V1.SAFETENSORS"
    path, stem = fresh(directory, unicode_name)
    write_json(os.path.join(os.path.dirname(stem), os.path.basename(stem).lower())
               + ".CM-INFO.JSON", LABELS)
    built = lorameta.row(unicode_name, path)
    check("case-insensitive Unicode companion", built.get("card_title"), TITLE)
    check("Unicode name is preserved", built["name"], unicode_name)
    check("Unicode base is preserved", built["base"], "조명_Édition_V1")

    path, stem = fresh(directory)
    for suffix in ("_extra.cm-info.json", ".cm-info.json.bak", ".safetensors.cm-info.json"):
        write_json(stem + suffix, LABELS)
    labels("same-prefix files are not companions", lorameta.row(NAME, path),
           "StudioLighting_V1", NAME)

    path, stem = fresh(directory)
    os.makedirs(stem + ".cm-info.json")
    labels("a directory is not a sidecar", lorameta.row(NAME, path), "StudioLighting_V1", NAME)

    # Every existing provider continues to own its fields. Compare the complete
    # shallow/deep records, row metadata and detail sheet before/after adding
    # the display sidecar, including previews, trigger precedence and sources.
    provider_fixtures = {
        "civimeta": (".safetensors.civitai/meta.json", {
            "name": "Catalog Metadata", "versionName": "Catalog Version",
            "baseModel": "Catalog Base", "trainedWords": ["catalog_trigger"],
            "modelId": 12, "versionId": 34,
            "stats": {"downloads": 56},
        }),
        "loramanager": (".metadata.json", {
            "model_name": "Manager Metadata", "base_model": "Manager Base",
            "notes": "Keep these notes", "usage_tips": {"strength": 0.65},
            "civitai": {"trainedWords": ["manager_trigger"]},
        }),
        "civitai_info": (".civitai.info", {
            "id": 34, "modelId": 12, "name": "Remote Version",
            "model": {"name": "Remote Metadata"}, "baseModel": "Remote Base",
            "trainedWords": ["remote_trigger"], "stats": {"downloadCount": 56},
        }),
        "a1111": (".json", {
            "activation text": "handwritten_trigger", "preferred weight": 0.75,
            "sd version": "User Base", "notes": "Handwritten notes",
        }),
    }
    for provider in ("header", "loose", *provider_fixtures, "combined"):
        path, stem = fresh(directory)
        fixtures = provider_fixtures.values() if provider == "combined" else (
            [provider_fixtures[provider]] if provider in provider_fixtures else [])
        for suffix, payload in fixtures:
            write_json(stem + suffix, payload)
        if provider in ("loose", "combined"):
            write(stem + ".preview.png", b"\x89PNG\r\n\x1a\n" + b"\0" * 200)
        before_row = row_metadata(lorameta.row(NAME, path))
        before_records = [metadata_snapshot(path, deep) for deep in (False, True)]
        before_detail = lorameta.detail(NAME, path)
        write_json(stem + ".cm-info.json", LABELS)
        lorameta.forget()
        after_row = lorameta.row(NAME, path)
        labels(provider + " display", after_row, TITLE, SUBTITLE)
        check(provider + " row metadata stays intact", row_metadata(after_row), before_row)
        check(provider + " shallow/deep metadata stays intact",
              [metadata_snapshot(path, deep) for deep in (False, True)], before_records)
        check(provider + " detail sheet stays intact", lorameta.detail(NAME, path), before_detail)

    # Creation/removal invalidate the listing immediately. Edits in place are
    # eventually visible through the existing scan TTL, or immediately after
    # the manager's explicit Rescan (forget), without touching the model file.
    path, stem = fresh(directory)
    sidecar = stem + ".cm-info.json"
    original_stat = os.stat(path)
    built = lorameta.row(NAME, path)
    labels("before sidecar creation", built, "StudioLighting_V1", NAME)
    write_json(sidecar, LABELS)
    changed_directory(sidecar)
    built = lorameta.row(NAME, path)
    labels("new companion invalidates cached row", built, TITLE, SUBTITLE)

    edit_in_place(sidecar, {"UserTitle": "Edited Lighting", "VersionName": "Second"})
    check("an in-place edit may keep the unexpired scan", lorameta.row(NAME, path) is built, True)
    lorameta._SCANS[os.path.dirname(path)].read_at -= lorameta.SCAN_TTL + 1
    built = lorameta.row(NAME, path)
    labels("scan expiry finds an in-place edit", built, "Edited Lighting", "Second")

    edit_in_place(sidecar, {"ModelName": "Rescanned Lighting", "BaseModel": "Third Base"})
    lorameta.forget()
    labels("Rescan finds an in-place edit", lorameta.row(NAME, path),
           "Rescanned Lighting", "Third Base")
    os.remove(sidecar)
    changed_directory(sidecar)
    labels("removal restores exact fallbacks", lorameta.row(NAME, path),
           "StudioLighting_V1", NAME)
    check("display refresh never changes weights", (os.stat(path).st_size, os.stat(path).st_mtime),
          (original_stat.st_size, original_stat.st_mtime))

passed("local LoRA card labels preserve metadata, providers, paths and cache refresh")

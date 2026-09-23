"""Cast inputs through the actual PreStage node, not just the cast helper.

The node's disk boundary reads tiny real RefMod headers; the family compilers
are real, while graph emission and ComfyUI's IO/media shell are stubbed. No
models, tensor loading, server, or GPU. If node is installed, also round-trip
the real Cast preset importer and PreStage serializer before executing.

    python3 tests/test_prestage_cast_inputs.py
"""

import copy
import json
import os
import shutil
import struct
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import patch

import layout
from harness import FAILURES, check, passed

pkg = layout.load("compile_image", "refmod", "flux2klein_still", "ideogram4_still",
                  "krea2_still", "qwenedit_still", "qwen21_still")
ci, rm = pkg.compile_image, pkg.refmod

# Only the outer ComfyUI shell is replaced. MiniMaxH3PreStage.execute, family
# dispatch, sampling resolution, Cast expansion and file-header parsing run.
latest = types.ModuleType("comfy_api.latest")
latest.io = types.SimpleNamespace(ComfyNode=object, NodeOutput=object)
sys.modules["comfy_api"] = types.ModuleType("comfy_api")
sys.modules["comfy_api.latest"] = latest
media = types.ModuleType(f"{pkg.__name__}.media")
media.image_size = lambda filename: (1024, 1024)
sys.modules[media.__name__] = media
setattr(pkg, "media", media)
emit = types.ModuleType(f"{pkg.__name__}.core.emit")
emit.expanded = lambda graph: graph
sys.modules[emit.__name__] = emit
layout.load("prestage")
ps = pkg.prestage
ps.MiniMaxH3PreStage.hidden = types.SimpleNamespace(unique_id="cast-inputs")


def blob(filename="anna.png", *, arch="flux2klein", prompt="@anna at dusk", **extra):
    return {"version": 1, "arch": arch, "prompt": prompt, "aspect": "1:1",
            "short_edge": 1024, "refs": [{"handle": "img-1", "filename": filename}],
            "subjects": [{"handle": "anna", "from": ["img-1"],
                          "description": "a woman in a red coat"}], "loras": [], **extra}


def run(data):
    family = ps.registry.still(data["arch"])
    with patch.object(family, "emit_still", lambda data, plan, sampler, node: plan):
        return ps.MiniMaxH3PreStage.execute(json.dumps(data), seed=1, steps=20,
                                           cfg=4.0, sampler_name="euler", scheduler="simple")


def succeeds(label, data, expected_refs, expected_mods=None):
    try:
        result = run(data)
    except Exception as exc:
        FAILURES.append(f"{label}: unexpected {type(exc).__name__}: {exc}")
        return None
    check(label + " refs", result.refs, expected_refs)
    check(label + " mods", result.mods, expected_mods or {})
    return result


def refuses(label, data, fragment):
    try:
        run(data)
    except ValueError as exc:
        check(label, fragment in str(exc), True)
    else:
        FAILURES.append(f"{label}: expected ValueError containing {fragment!r}")


def write_mod(root, name, space="flux2"):
    shape = [1, 128, 4, 4] if space == "flux2" else [1, 24, 1, 4, 4]
    count = 1
    for dim in shape:
        count *= dim
    table = {"__metadata__": {rm.META_KEY: json.dumps({"kind": "image", "vae_kind": space})},
             "latent": {"dtype": "F16", "shape": shape, "data_offsets": [0, count * 2]}}
    header = json.dumps(table).encode("utf-8")
    path = Path(root, name + ".safetensors")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack("<Q", len(header)) + header + bytes(count * 2))


with tempfile.TemporaryDirectory(prefix="continuity-cast-inputs-") as root:
    folders = types.ModuleType("folder_paths")
    folders.models_dir = root
    folders.add_model_folder_path = lambda *args: None
    folders.get_folder_paths = lambda folder: [root]
    folders.is_within_directory = lambda base, path: os.path.commonpath(
        [os.path.realpath(base), os.path.realpath(path)]) == os.path.realpath(base)
    sys.modules["folder_paths"] = folders
    # On macOS a temp root may be /var/... while resolve supplies /private/var/...
    # for its file. Exercise that aliasing contract on every platform.
    alias = os.path.join(root, "alias")
    candidate = os.path.join(root, "cast", "anna.flux2.safetensors")
    with patch.object(os.path, "realpath", side_effect=lambda path: root if path == alias else path):
        check("folder containment compares resolved roots and files",
              folders.is_within_directory(alias, candidate), True)
    write_mod(root, "cast/anna.flux2")
    # The suffix is deliberately misleading. Only the header identifies space.
    write_mod(root, "cast/not-klein.flux2", "h3_video")
    Path(root, "broken.safetensors").write_bytes(b"not a safetensors file")
    mod = "refmod:cast/anna.flux2"

    # Regression 1: the helper already knew 'words only'; the real compiler
    # caller forgot to pass the family's capability and rejected this Cast.
    result = succeeds("Ideogram uses the description of a photo Cast",
                      blob(arch="ideogram4"), [])
    if result:
        check("Ideogram keeps the description inside its caption",
              "a woman in a red coat at dusk" in result.prompt, True)
    refuses("an explicitly cited photo is still refused on Ideogram",
            blob(arch="ideogram4", prompt="@img-1 at dusk"), "no local reference conditioning")
    refuses("a words-only Cast without a description is actionable",
            blob(arch="ideogram4", subjects=[{"handle": "anna", "from": ["img-1"]}]),
            "describe them")
    succeeds("ordinary Klein photo Cast is unchanged", blob(), ["anna.png"])
    succeeds("Qwen photo Cast is unchanged", blob(arch="qwenedit"), ["anna.png"])
    bound = {"handle": "img-1", "filename": "anna.png", "mods": {"flux2": mod}}
    succeeds("a photo's existing saved rendition is unchanged",
             blob(refs=[bound]), ["anna.png"], {0: mod})

    # Regression 2: the serialized standalone Cast RefMod has no space field.
    source = blob(mod)
    before = copy.deepcopy(source)
    result = succeeds("Klein reads the standalone Cast RefMod's header", source,
                      [mod], {0: mod})
    if result:
        check("Klein's compiled prompt cites the retained latent slot",
              result.prompt, "Picture 1 (a woman in a red coat) at dusk")
    check("node preparation does not mutate the caller's blob", source, before)
    prepared = ps._cast_refmod_spaces(source, pkg.flux2klein_still)
    with patch.object(rm, "resolve", side_effect=AssertionError("compiler touched disk")), \
            patch.object(rm, "header", side_effect=AssertionError("compiler read a header")):
        result = ci.compile_prestage(prepared, pkg.flux2klein_still)
    check("the pure compiler consumes stamped spaces without file access",
          (result.refs, result.mods), ([mod], {0: mod}))
    succeeds("untrusted space cannot hide a valid Klein latent",
             blob(mod, refs=[{"handle": "img-1", "filename": mod, "space": "h3_video"}]),
             [mod], {0: mod})
    foreign = "refmod:cast/not-klein.flux2"
    succeeds("a foreign-space Cast keeps its established description fallback",
             blob(foreign, refs=[{"handle": "img-1", "filename": foreign, "space": "flux2"}]), [])
    succeeds("a foreign-space look does not hide a later usable photo",
             blob(foreign, subjects=[{"handle": "anna", "from": ["img-1", "img-2"],
                                      "description": "a woman"}],
                  refs=[{"handle": "img-1", "filename": foreign},
                        {"handle": "img-2", "filename": "anna.png"}]), ["anna.png"])
    for unavailable in ("refmod:missing", "refmod:broken"):
        result = succeeds("an unavailable Cast mod falls back to its description",
                          blob(unavailable, refs=[{"handle": "img-1", "filename": unavailable,
                                                  "space": "flux2"}]), [])
        if result:
            check("an unavailable mod cannot keep its stale space",
                  result.prompt, "a woman in a red coat at dusk")
    with patch.object(rm, "header", side_effect=rm.RefModError("permission denied")):
        succeeds("an unreadable Cast mod falls back to its description", blob(mod), [])
    refuses("an unavailable mod with no description still needs words",
            blob("refmod:missing", subjects=[{"handle": "anna", "from": ["img-1"]}]),
            "describe them")
    succeeds("an unavailable look does not hide a later usable mod",
             blob(subjects=[{"handle": "anna", "from": ["img-1", "img-2"],
                             "description": "a woman"}],
                  refs=[{"handle": "img-1", "filename": "refmod:missing", "space": "flux2"},
                        {"handle": "img-2", "filename": mod}]), [mod], {0: mod})

    # The boundary supplies facts for every cited member's mod, even after a
    # usable photo or latent. Only cast_into_still chooses which look to send.
    for first in ("anna.png", mod):
        source = blob(subjects=[{"handle": "anna", "from": ["img-1", "img-2", "img-3"],
                                "description": "a woman"},
                               {"handle": "bea", "from": ["img-4"], "description": "another woman"}],
                      refs=[{"handle": "img-1", "filename": first},
                            {"handle": "img-2", "filename": mod},
                            {"handle": "img-3", "filename": foreign},
                            {"handle": "img-4", "filename": mod}])
        prepared = ps._cast_refmod_spaces(source, pkg.flux2klein_still)
        check("all cited source mods are stamped after an already usable look",
              [r.get("space") for r in prepared["refs"]],
              ["flux2" if first == mod else None, "flux2", "h3_video", None])
        succeeds("the compiler alone still selects the first usable look", source,
                 [first], {0: mod} if first == mod else {})
    word_member = {"handle": "anna", "from": ["img-1"], "description": "a woman",
                   "wears": {"flux2klein": {"send": "words"}}}
    prepared = ps._cast_refmod_spaces(blob(mod, subjects=[word_member]), pkg.flux2klein_still)
    check("words mode is also left for the compiler to decide",
          prepared["refs"][0].get("space"), "flux2")

    # Uncited members and families without latent references need no headers.
    lookup = rm.header
    calls = []

    def counted(path):
        calls.append(path)
        return lookup(path)

    with patch.object(rm, "header", counted):
        succeeds("uncited Cast does not inspect a missing mod",
                 blob("refmod:missing", prompt="a fox at dusk"), [])
        succeeds("Ideogram Cast never needs the RefMod's file",
                 blob("refmod:missing", arch="ideogram4"), [])
        member = {"handle": "anna", "from": ["img-1"], "description": "a woman",
                  "wears": {"flux2klein": {"send": "words"}}}
        succeeds("explicit words mode tolerates a missing mod",
                 blob("refmod:missing", subjects=[member]), [])
        succeeds("a removed or muted source absent from refs remains words",
                 blob("refmod:missing", refs=[]), [])
        member = {"handle": "anna", "from": ["img-1", "img-2"], "description": "a woman"}
        succeeds("an unused later look does not become a missing-file error",
                 blob(subjects=[member], refs=[{"handle": "img-1", "filename": "anna.png"},
                                               {"handle": "img-2", "filename": "refmod:missing"}]),
                 ["anna.png"])
        check("unneeded or missing files cause no header reads", calls, [])
        # Two cast members can share one file: validate once per node execution.
        succeeds("a shared RefMod is resolved once",
                 blob(mod, prompt="@anna beside @bea", subjects=[
                     {"handle": "anna", "from": ["img-1"], "description": "a woman"},
                     {"handle": "bea", "from": ["img-2"], "description": "another woman"}],
                     refs=[{"handle": "img-1", "filename": mod},
                           {"handle": "img-2", "filename": mod}]), [mod, mod], {0: mod, 1: mod})
        check("one header read for the shared path", len(calls), 1)

    if shutil.which("node"):
        # Real importer -> real serializer -> real node compiler. This catches
        # the omitted space in the persisted shape, not an invented fixture.
        script = r"""
const S = await import('./web/creator/state.js');
const P = await import('./web/creator/presets.js');
const imported = await P.memberFromMod({ name: 'anna', path: 'refmod:cast/anna.flux2',
  kind: 'image', space: 'flux2', description: 'a woman in a red coat' }, []);
const klein = S.emptyPreStage(); klein.arch = 'flux2klein';
P.applyToPreStage(imported.body, ['cast'], klein, {}, { from: 'cast' });
klein.prompt = '@anna at dusk';
const ideogram = S.emptyPreStage(); ideogram.arch = 'ideogram4';
P.applyToPreStage({ cast: { handle: 'anna', description: 'a woman in a red coat',
  files: [{ slot: 'from', filename: 'anna.png', kind: 'image' }] } },
  ['cast'], ideogram, {}, { from: 'cast' });
ideogram.prompt = '@anna at dusk';
console.log(JSON.stringify({ klein: JSON.parse(S.serializePreStage(klein)),
                            ideogram: JSON.parse(S.serializePreStage(ideogram)) }));
"""
        with layout.pack(skip=["atlas"]) as target:
            imported = layout.in_pack(script, target)
        succeeds("imported and serialized standalone Klein Cast reaches the node",
                 imported["klein"], [mod], {0: mod})
        succeeds("imported and serialized Ideogram Cast reaches the node",
                 imported["ideogram"], [])

passed("PreStage Cast input capabilities and trusted standalone RefMod spaces")

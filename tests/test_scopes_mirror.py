"""`state.js` still agrees with `compile.py` and `contextir.py` about scopes.

Three lists and one sentence per entry, written down twice: the compiler holds
them because it is what queues the prose, and the box holds them because the
band above the prompt shows that prose while you are still setting the chips.

The duplication is what makes this worth a suite of its own. `Asset.takes` never
reaches the encode path — the DiT is handed the same tensor whatever the chip
says — so the *only* thing a scope does is put words in front of the
description. A value that exists on one side and not the other is therefore not
a cosmetic drift: it is a chip you can set that sends nothing, or a sentence the
band promises and the render never writes.

    python3 tests/test_scopes_mirror.py

Skips itself if node is not installed.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIRROR = os.path.join(ROOT, "js", "minimax_creator", "state.js")

if shutil.which("node") is None:
    print("skipped: node is not installed")
    sys.exit(0)


def _load():
    """`compile` imports its siblings relatively, so it is loaded as a package."""
    package = types.ModuleType("mmc")
    package.__path__ = [ROOT]
    sys.modules["mmc"] = package
    modules = {}
    for name in ("canvas", "contextir", "compile"):
        spec = importlib.util.spec_from_file_location(f"mmc.{name}", os.path.join(ROOT, f"{name}.py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"mmc.{name}"] = module
        setattr(package, name, module)
        spec.loader.exec_module(module)
        modules[name] = module
    return modules["compile"], modules["contextir"]


compiler, contextir = _load()

SCRIPT = """
const s = await import(process.argv[1]);
const asset = (kind, takes, rest = {}) =>
  ({ handle: `${kind}-1`, kind, role: "reference", takes, ...rest });
console.log(JSON.stringify({
  takes: { image: s.IMAGE_TAKES, video: s.VIDEO_TAKES, audio: s.AUDIO_TAKES },
  map: Object.fromEntries(Object.entries(s.TAKES)),
  define: s.DEFINE,
  // A sound-only clip scopes as audio on both sides, which is the one place the
  // kind on the blob and the vocabulary it may use disagree.
  soundOnly: s.takeOptions(asset("video", "full", { track: "sound" })),
  audioOfAudio: s.takeOptions(asset("audio", "full")),
  keyframe: s.takeOptions({ handle: "img-1", kind: "image", role: "first_frame" }),
}));
"""

proc = subprocess.run(
    ["node", "--input-type=module", "-e", SCRIPT, "--", MIRROR],
    capture_output=True, text=True)
if proc.returncode != 0:
    print(f"node failed:\n{proc.stderr}")
    sys.exit(1)
mirror = json.loads(proc.stdout)

from harness import FAILURES, passed


def check(label, got, want):
    if got != want:
        FAILURES.append(f"{label}: js {got!r}, py {want!r}")


# ---- the vocabularies -------------------------------------------------------

for kind in ("image", "video", "audio"):
    check(f"the {kind} scopes match",
          mirror["takes"][kind], list(compiler.TAKES[kind]))
check("...and so does the map they are looked up in",
      {k: list(v) for k, v in mirror["map"].items()},
      {k: list(v) for k, v in compiler.TAKES.items()})

# Which vocabulary a file may choose from. The interesting one is the clip taken
# for its soundtrack alone: it arrives among the audio, takes an `<Audio N>` and
# never has its picture encoded, so offering it "camera" would be offering a
# narrowing of a file that is not there.
check("a sound-only clip is offered the audio scopes",
      mirror["soundOnly"], list(compiler.TAKES["audio"]))
check("...and so is an audio file", mirror["audioOfAudio"], list(compiler.TAKES["audio"]))
check("a keyframe is offered nothing", mirror["keyframe"], [])

# ---- and one sentence per entry ---------------------------------------------
#
# Both sides key these the same way; only the separator differs, because a JS
# object cannot be keyed by a pair.

python_define = {f"{kind}:{takes}": text
                 for (kind, takes), text in contextir._DEFINE.items()}
check("every scope's sentence is written the same way both sides",
      mirror["define"], python_define)

# The gap this suite exists for: a value with no sentence behind it is a chip
# that sends nothing at all.
for kind, values in compiler.TAKES.items():
    for takes in values:
        key = f"{kind}:{takes}"
        if key not in python_define:
            FAILURES.append(f"compile offers {key} but contextir defines no sentence for it")
        if key not in mirror["define"]:
            FAILURES.append(f"compile offers {key} but state.js defines no sentence for it")

# ...and the reverse, which is a sentence nothing can ever ask for.
for key in python_define:
    kind, takes = key.split(":", 1)
    if takes not in compiler.TAKES.get(kind, ()):
        FAILURES.append(f"contextir defines {key}, which is not a scope compile allows")

# Every sentence has exactly one place for the label to go, or the band and the
# prompt would name different files.
for key, text in python_define.items():
    if text.count("%s") != 1:
        FAILURES.append(f"{key}: expected one %s, got {text.count('%s')}")

passed("state.js mirrors the scope vocabulary and every sentence in it")

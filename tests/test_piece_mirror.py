"""A version-1 `creator_data` blob lifts to the same one-shot piece on both sides.

    python3 tests/test_piece_mirror.py

The Creator and the Timeline used to be two nodes with two blob formats. They are
one node now, and the blob is the timeline's — so every workflow saved before the
merge holds a shape the node no longer writes. `compile.as_piece` and
`state.asPiece` are what read those, and they run on every load of every one of
those workflows rather than once at an upgrade.

Two things are worth asserting and nothing else really is:

- **They agree.** The frontend decides what the face shows and the backend
  decides what is sampled. A blob that lifts one way in the browser and another
  way at queue time is a node whose picture of itself is wrong.
- **They lift the right fields in the right direction.** The seven piece fields
  go up; `prompt` and `assets` stay down on the shot. Those two are not
  cosmetic — a prompt promoted to piece level would change what a second shot
  generates, and a keyframe promoted to the reference pool is refused outright by
  `timeline_pool`.

Skips itself if node is not installed.
"""

import json

import mirror

mirror.skip_without_node()

MIRROR = mirror.js("state.js")

compiler = mirror.load("canvas", "contextir", "compile").compile


# The blobs worth asking both sides about. A real saved Creator, the shapes a
# hand-edited one arrives in, and — just as important — every shape that must be
# left alone.
CASES = {
    # What `creator_node.DEFAULT_DATA` has always written.
    "a fresh creator": {
        "version": 1, "prompt": "", "assets": [], "loras": [], "duration_s": 6,
        "aspect": "16:9", "short_edge": 768, "checkpoint": "auto", "models": {},
    },
    # A real one, with the whole of the split represented.
    "a written creator": {
        "version": 1,
        "prompt": "A slow push through the reeds at dawn, @img-1",
        "soundscape": "wind over water",
        "music": "none",
        "assets": [{"handle": "img-1", "kind": "image", "role": "start_frame",
                    "filename": "dawn.png"}],
        "loras": [{"name": "grain.safetensors", "strength": 0.8}],
        "duration_s": 8,
        "aspect": "21:9",
        "short_edge": 640,
        "upscale": "direct",
        "sample_edge": 512,
        "refine_denoise": 0.4,
        "checkpoint": "fl2va",
        "models": {"fl2va": "fl2va.safetensors", "route": "fl2va"},
        "turbo": {"on": True, "quality": "good"},
    },
    # No version key, which is what a hand-edited blob usually looks like.
    "a hand-written shot": {"prompt": "a kite", "duration_s": 4},
    # Carries a rewrite, which belongs to the shot and not to the piece.
    "a refined creator": {
        "version": 1, "prompt": "a kite",
        "refined": {"body": "A kite, seen from below", "source": "a kite"},
        "duration_s": 6,
    },

    # ---- and everything that must be returned untouched ----
    "a fresh node": {},
    "an empty strip": {"version": 2, "prompt": "", "segments": []},
    "a written timeline": {
        "version": 2, "prompt": "Dawn on the estuary", "aspect": "16:9",
        "short_edge": 768, "models": {"route": "ref2va"},
        "segments": [{"prompt": "one", "duration_s": 6},
                     {"prompt": "two", "duration_s": 6, "continue": True}],
    },
    # Already lifted. Asking twice must be the same as asking once, because the
    # entry points each ask without tracking who asked first.
    "a lifted blob, lifted again": {
        "version": 2, "prompt": "", "models": {}, "aspect": "16:9",
        "segments": [{"prompt": "a kite", "duration_s": 4}],
    },
}

SCRIPT = """
const s = await import(process.argv[1]);
const cases = JSON.parse(process.argv[2]);
const out = { fields: s.PIECE_FIELDS, lifted: {} };
for (const [name, blob] of Object.entries(cases)) out.lifted[name] = s.asPiece(blob);
console.log(JSON.stringify(out));
"""

reflected = mirror.run(SCRIPT, MIRROR, CASES)

from harness import FAILURES, check, passed


check("the piece fields match", reflected["fields"], list(compiler.PIECE_FIELDS))

for name, blob in CASES.items():
    check(f"{name} lifts the same on both sides",
          reflected["lifted"][name], compiler.as_piece(blob))

# ---- the direction of each field, asserted against the backend ---------------

written = compiler.as_piece(CASES["a written creator"])
shot = written["segments"][0]

check("the piece holds exactly one shot", len(written["segments"]), 1)
check("the piece is version 2", written["version"], 2)

for field, value in [("aspect", "21:9"), ("short_edge", 640), ("upscale", "direct"),
                     ("sample_edge", 512), ("refine_denoise", 0.4)]:
    check(f"{field} moves up to the piece", written.get(field), value)
    check(f"...and is gone from the shot", field in shot, False)

check("the weights move up", written["models"], {"fl2va": "fl2va.safetensors", "route": "fl2va"})
check("the turbo switch moves up", written["turbo"], {"on": True, "quality": "good"})
check("neither is left on the shot", ("models" in shot, "turbo" in shot), (False, False))

# The two that go the other way, and the reason they are the load-bearing ones.
check("the prompt stays on the shot", shot["prompt"],
      "A slow push through the reeds at dawn, @img-1")
check("the piece's own prompt is empty", written["prompt"], "")
check("the assets stay on the shot — a keyframe is not a pool entry",
      shot["assets"], [{"handle": "img-1", "kind": "image", "role": "start_frame",
                        "filename": "dawn.png"}])
check("...so the piece has no pool at all", "assets" in written, False)

check("the shot keeps its own LoRAs", shot["loras"], [{"name": "grain.safetensors", "strength": 0.8}])
check("the shot keeps its duration", shot["duration_s"], 8)
check("the shot keeps its checkpoint pin", shot["checkpoint"], "fl2va")
check("the shot keeps the audio fields", (shot["soundscape"], shot["music"]),
      ("wind over water", "none"))
check("a rewrite stays with the shot it rewrites",
      compiler.as_piece(CASES["a refined creator"])["segments"][0]["refined"]["body"],
      "A kite, seen from below")
check("the version key does not ride down onto the shot", "version" in shot, False)

# A blob that carried no weights still gets an empty block, so that lifting it
# cannot pick up the empty piece's Ref2VA preference and change what it renders on.
check("a weightless blob is still given a models block",
      compiler.as_piece(CASES["a hand-written shot"])["models"], {})

# ---- and what must not move -------------------------------------------------

check("a fresh node stays an empty object", compiler.as_piece({}), {})
check("an empty strip is left alone",
      compiler.as_piece(CASES["an empty strip"]), CASES["an empty strip"])
check("a written timeline is left alone",
      compiler.as_piece(CASES["a written timeline"]), CASES["a written timeline"])
check("lifting twice is lifting once",
      compiler.as_piece(compiler.as_piece(CASES["a written creator"])), written)
check("a non-dict is handed back rather than refused here",
      compiler.as_piece("nonsense"), "nonsense")

# ---- and that the render path actually reads one ----------------------------
#
# The point of the whole exercise: an old blob must queue. `timeline_payloads` is
# what the node calls, and it has to see one segment where the blob said none.

payloads = compiler.timeline_payloads(CASES["a fresh creator"])
check("an old creator blob compiles to one payload", len(payloads), 1)
check("...which continues from nothing", payloads[0].get("continue"), False)
check("...and carries the shot's own request", "request" in payloads[0], True)

check("an old creator's segment list is its one shot",
      len(compiler.timeline_segments(CASES["a written creator"])), 1)
check("...and its keyframe is not read as a reference pool",
      compiler.timeline_pool(CASES["a written creator"]), [])

passed(f"state.js mirrors compile.py across {len(CASES)} blobs; v1 lifts to one shot")

"""A still has the cast a shot has (`compile_image.cast_into_still`).

The image compilers know pictures and a prompt, so a member is written in
those — their picture where their name stood, their description after it,
what they wear on this family onto the stack — by one expansion the PreStage
node and the chat's room both run. Runs standalone, like `test_cast_lora.py`.

    python3 tests/test_cast_still.py
"""

import os
import sys

import layout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import FAILURES, check, passed

_pkg = layout.load("canvas", "registry", "contextir", "subjects", "compile", "compile_image", "still",
                   "krea2_still", "ideogram4_still", "qwenedit_still", "flux2klein_still")
ci, compiler = _pkg.compile_image, _pkg.compile
krea, klein, qwen, ideogram = _pkg.krea2_still, _pkg.flux2klein_still, _pkg.qwenedit_still, _pkg.ideogram4_still

ANNA_KLEIN = {"name": "people/anna_klein.safetensors", "strength": 0.7, "triggers": ["ann4"]}
ANNA_H3 = {"name": "people/anna_h3.safetensors", "strength": 0.8, "triggers": ["ohwx anna"]}
ADAPTER = {"name": "krea2_identity_edit_v2.safetensors", "strength": 1.0}


def anna(**extra):
    return {"handle": "anna", "from": ["img-1", "img-2"], "description": "a red coat", **extra}


def blob(prompt, subjects, refs=None, **extra):
    return {"version": 1, "arch": "flux2klein", "prompt": prompt, "aspect": "1:1", "short_edge": 1024,
            "refs": refs if refs is not None else [{"handle": "img-1", "filename": "anna_front.png"},
                                                    {"handle": "img-2", "filename": "anna_side.png"}],
            "subjects": subjects, "loras": [{"name": "style.safetensors", "strength": 0.5}], **extra}


def refs_of(payload):
    return payload.refs


# ---- the expansion ------------------------------------------------------------

out = ci.cast_into_still(blob("@anna at dusk", [anna(wears={"flux2klein": {"loras": [ANNA_KLEIN]},
                                                            "h3": {"loras": [ANNA_H3]}})]),
                         "flux2klein", "flux2")
check("her name becomes her first picture, with her words after it",
      out["prompt"], "@img-1 (a red coat) at dusk")
check("only the picture that stands for her rides in — her second stays off the render",
      [r["handle"] for r in out["refs"]], ["img-1"])
check("she wears Klein's row on Klein, after the stack's own",
      [e["name"] for e in out["loras"]], ["style.safetensors", "people/anna_klein.safetensors"])
check("on an edit family her picture is never the one changed",
      out.get(ci.EDIT_FIRST_FIELD), None)

plain = ci.cast_into_still(blob("@anna beside @img-9", [anna()],
                                refs=[{"handle": "img-9", "filename": "wall.png"},
                                      {"handle": "img-1", "filename": "anna_front.png"}]),
                           "flux2klein", "flux2")
check("a picture cited plain leads, hers follows, and the render edits the plain one",
      ([r["handle"] for r in plain["refs"]], plain.get(ci.EDIT_FIRST_FIELD)), (["img-9", "img-1"], None))

uncited = ci.cast_into_still(blob("a fox", [anna()]), "flux2klein", "flux2")
check("a member nobody names takes their pictures with them", uncited["refs"], [])
check("...unless the prompt writes the handle itself",
      [r["handle"] for r in ci.cast_into_still(blob("a fox by @img-2", [anna()]), "flux2klein", "flux2")["refs"]],
      ["img-2"])

words = ci.cast_into_still(blob("@anna at dusk", [anna(wears={"flux2klein": {"send": "words"}})]),
                           "flux2klein", "flux2")
check("sent as words, she is her description and no picture", (words["prompt"], words["refs"]),
      ("a red coat at dusk", []))
bound = [{"handle": "img-1", "filename": "anna_front.png",
          "mods": {"flux2": "refmod:cast/anna.flux2", "h3_video": "refmod:cast/anna"}}]
saved = ci.cast_into_still(blob("@anna", [anna()], refs=bound), "flux2klein", "flux2")
check("left to decide, her picture rides in with its renditions",
      saved["refs"][0].get("mods"), {"flux2": "refmod:cast/anna.flux2", "h3_video": "refmod:cast/anna"})
pictures = ci.cast_into_still(blob("@anna", [anna(wears={"flux2klein": {"send": "pictures"}})], refs=bound),
                              "flux2klein", "flux2")
check("sent as pictures, the picture and none of its renditions", "mods" in pictures["refs"][0], False)

mod_only = [{"handle": "img-1", "filename": "refmod:cast/anna", "space": "h3_video"}]
check("a saved reference in another family's space is her words",
      ci.cast_into_still(blob("@anna", [anna()], refs=mod_only), "flux2klein", "flux2")["prompt"], "a red coat")
check("...and one in this family's space is her picture",
      ci.cast_into_still(blob("@anna", [anna()], refs=[{**mod_only[0], "space": "flux2"}]),
                         "flux2klein", "flux2")["prompt"], "@img-1 (a red coat)")
check("a family that reads no pictures gets her words",
      ci.cast_into_still(blob("@anna", [anna()]), "ideogram4", None, takes_pictures=False)["prompt"],
      "a red coat")
try:
    ci.cast_into_still(blob("@anna", [{"handle": "anna", "from": ["img-7"]}], refs=[]), "flux2klein", "flux2")
    FAILURES.append("a member with no picture here and no words is drawn")
except compiler.CompileError as exc:
    check("a member with no picture here and no words is refused, with the way out",
          "describe them" in str(exc), True)
check("no cast is the blob untouched", ci.cast_into_still({"prompt": "x", "refs": []}, "krea2", None),
      {"prompt": "x", "refs": []})

# ---- through the still compiler -----------------------------------------------

payload = ci.compile_prestage(blob("@anna at dusk", [anna(wears={"flux2klein": {"loras": [ANNA_KLEIN]}})]), klein)
check("the still cites her picture by its slot, her trigger word in front",
      payload.prompt, "ann4, Picture 1 (a red coat) at dusk")
check("...loads that picture alone, wearing her LoRA", (payload.refs, [e["name"] for e in payload.loras]),
      (["anna_front.png"], ["style.safetensors", "people/anna_klein.safetensors"]))

krea_blob = {**blob("@anna at dusk", [anna(wears={"krea2": {"loras": [ADAPTER]}})]), "arch": "krea2",
             "models": {"krea2": {}}}
adapted = ci.compile_prestage(krea_blob, krea)
check("Krea 2 reads her picture through the adapter she wears, with no field naming it",
      (adapted.refs, [e["name"] for e in adapted.loras]),
      (["anna_front.png"], ["style.safetensors", "krea2_identity_edit_v2.safetensors"]))
try:
    ci.compile_prestage({**krea_blob, "subjects": [anna()]}, krea)
    FAILURES.append("Krea 2 read a picture with no adapter on the stack")
except compiler.CompileError as exc:
    check("...and without one on the stack, refuses in its own words", "Krea 2 Edit LoRA" in str(exc), True)

passed("a still has the cast a shot has: pictures, words and what they wear, per family")

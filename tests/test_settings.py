"""What the settings file is allowed to hold, and what a broken one reads as.

Runs standalone — `python tests/test_settings.py` — with no torch and no
ComfyUI, the same way `test_outputs.py` does, because `settings.py` keeps its
one ComfyUI import inside `path()` for exactly that reason.

The cases worth pinning are the two ends of a preferences file's life: what the
settings page is allowed to store, and what the save node reads when the file on
disk is missing, half-written or edited by hand into something the encoder has
no answer for. A render must not fail over a preference — but it must not
quietly use a value nobody chose either, which is why "unusable" reads as the
default the page will then show rather than as whatever was closest.
"""

import importlib.util
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# `settings.py` validates the output prefixes through `outputs.py`, so it comes
# in as part of a synthetic package rather than as a lone file — still nothing
# from ComfyUI, which is the property this test exists to keep.
import types

package = types.ModuleType("mmcpkg")
package.__path__ = [ROOT]
sys.modules["mmcpkg"] = package
for name in ("outputs", "settings"):
    spec = importlib.util.spec_from_file_location(f"mmcpkg.{name}", os.path.join(ROOT, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"mmcpkg.{name}"] = module
    spec.loader.exec_module(module)
settings = sys.modules["mmcpkg.settings"]

from harness import FAILURES, check


def refuses(label, raw, fragment):
    try:
        settings.clean(raw)
    except ValueError as exc:
        if fragment not in str(exc):
            FAILURES.append(f"{label}: refused, but said {str(exc)!r} (wanted {fragment!r})")
        return
    FAILURES.append(f"{label}: was accepted")


# ---- what a blob may say ----------------------------------------------------

check("an empty blob is the defaults", settings.clean({}), dict(settings.DEFAULTS))
check("a null value is the default", settings.clean({"video_crf": None}),
      dict(settings.DEFAULTS))
check("a value is kept", settings.clean({"video_crf": 18})["video_crf"], 18)
check("both ends of libx264's scale are legal",
      (settings.clean({"video_crf": settings.MIN_CRF})["video_crf"],
       settings.clean({"video_crf": settings.MAX_CRF})["video_crf"]),
      (settings.MIN_CRF, settings.MAX_CRF))
# A JSON number is a float as readily as an int, and 18.0 is a whole number.
check("a whole float is a whole number", settings.clean({"video_crf": 18.0})["video_crf"], 18)
# A key this build has never heard of belongs to a newer one. Dropped rather
# than carried, so `load()` returns exactly the keys the code reads.
check("an unknown key is dropped", sorted(settings.clean({"nonsense": 1})),
      sorted(settings.DEFAULTS))

refuses("a value off the encoder's scale", {"video_crf": 99}, "between")

# The shift pills' visibility. A strict boolean: `1` and `"true"` are refused
# rather than coerced, so the file never holds a value the page's two radio
# rows cannot show back.
check("the shift pills are hidden by default", settings.clean({})["show_shift_pills"], False)
check("showing the shift pills is kept",
      settings.clean({"show_shift_pills": True})["show_shift_pills"], True)
check("a null shift-pill setting is the default",
      settings.clean({"show_shift_pills": None})["show_shift_pills"], False)
refuses("a shift-pill setting that is not a boolean", {"show_shift_pills": 1}, "true or false")

# The stage's autoplay. The same strict boolean, defaulting the other way:
# playing is what the stage has always done, so the file only ever needs to
# say "stop".
check("previews autoplay by default", settings.clean({})["autoplay_previews"], True)
check("turning autoplay off is kept",
      settings.clean({"autoplay_previews": False})["autoplay_previews"], False)
check("a null autoplay setting is the default",
      settings.clean({"autoplay_previews": None})["autoplay_previews"], True)
refuses("an autoplay setting that is not a boolean", {"autoplay_previews": "yes"}, "true or false")

# The output folders. `outputs.clean` is the authority — this only has to show
# that the setting is held to it, so a prefix that would be refused at the end
# of a render is refused while it is still a field being edited.
check("a folder is kept as typed",
      settings.clean({"video_prefix": "client/shoot-3/take"})["video_prefix"],
      "client/shoot-3/take")
check("a trailing slash keeps the default's filename stem",
      settings.clean({"image_prefix": "client/"})["image_prefix"], "client/prestage")
check("an empty folder is the default",
      settings.clean({"video_prefix": ""})["video_prefix"], settings.DEFAULT_VIDEO_PREFIX)
refuses("an absolute output folder", {"video_prefix": "/tmp/renders"}, "absolute")
refuses("a folder that escapes upwards", {"image_prefix": "../elsewhere/x"}, "'.' and '..'")
refuses("a negative value", {"video_crf": -1}, "between")
refuses("a fractional value", {"video_crf": 18.5}, "whole number")
refuses("a string", {"video_crf": "18"}, "whole number")
# `True` is an int in Python and would otherwise be stored as crf 1 — which is
# not the setting anyone meant, and is a 40× file.
refuses("a boolean", {"video_crf": True}, "whole number")
refuses("something that is not an object", ["video_crf", 18], "must be an object")

# ---- the file -----------------------------------------------------------------

with tempfile.TemporaryDirectory() as directory:
    settings.path = lambda: os.path.join(directory, settings.FILE)

    check("no file yet is the defaults", settings.load(), dict(settings.DEFAULTS))

    check("saving hands back what was stored", settings.save({"video_crf": 14}),
          {**settings.DEFAULTS, "video_crf": 14})
    check("...and that is what loads", settings.load()["video_crf"], 14)
    check("...and what the save node asks for", settings.video_crf(), 14)

    # A save is a patch over the file, not a replacement of it. The page sends
    # the one field just edited, so a second save must not hand back the first
    # field's default — the bug that made a custom stills folder disappear the
    # moment somebody touched the video one.
    check("a later save keeps the earlier one",
          settings.save({"video_prefix": "client/shoot-3/take"}),
          {**settings.DEFAULTS, "video_crf": 14, "video_prefix": "client/shoot-3/take"})
    check("...and again, from the other side",
          settings.save({"image_prefix": "client/stills"}),
          {**settings.DEFAULTS, "video_crf": 14, "video_prefix": "client/shoot-3/take",
           "image_prefix": "client/stills"})
    check("...and that is what loads", settings.load()["video_prefix"], "client/shoot-3/take")

    settings.save({"video_crf": 14, "video_prefix": settings.DEFAULT_VIDEO_PREFIX,
                   "image_prefix": settings.DEFAULT_IMAGE_PREFIX})

    # The one thing the temp file is for: a render reading this while the page
    # writes it must see one or the other, never half a JSON document.
    check("nothing is left beside it", sorted(os.listdir(directory)), [settings.FILE])

    # A file edited by hand. Both of these are in force until someone opens the
    # settings page, so both have to read as the value the page will show.
    with open(settings.path(), "w", encoding="utf-8") as handle:
        handle.write("{not json")
    check("an unreadable file is the defaults", settings.load(), dict(settings.DEFAULTS))

    with open(settings.path(), "w", encoding="utf-8") as handle:
        json.dump({"video_crf": 99}, handle)
    check("a value the encoder has no answer for is the default",
          settings.video_crf(), settings.DEFAULT_CRF)

    # An older file, written before a key existed, is not broken — it is a file
    # with fewer opinions in it.
    with open(settings.path(), "w", encoding="utf-8") as handle:
        json.dump({}, handle)
    check("a file missing a key is the default for that key",
          settings.load(), dict(settings.DEFAULTS))

# The default is libx264's own, which is what this pack wrote before the setting
# existed: turning the page on must not change anybody's files.
check("the default is what the encoder would have picked anyway",
      settings.DEFAULT_CRF, 23)

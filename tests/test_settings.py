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

import layout
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# `settings.py` validates the output prefixes through `outputs.py`, so it comes
# in as part of a synthetic package rather than as a lone file — still nothing
# from ComfyUI, which is the property this test exists to keep.
import types

package = types.ModuleType("mmcpkg")
package.__path__ = [layout.PY_ROOT]
sys.modules["mmcpkg"] = package
for name in ("outputs", "settings"):
    spec = importlib.util.spec_from_file_location(f"mmcpkg.{name}", layout.py(name))
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

# The advanced switch: the same strict boolean, and the same default. It only
# decides what a node *draws* — a row with an advanced control switched on
# keeps that control whatever this says, which is the frontend's rule and is
# why nothing here can change a render.
check("advanced controls are hidden by default", settings.clean({})["advanced"], False)
check("turning them on is kept", settings.clean({"advanced": True})["advanced"], True)
check("a null advanced setting is the default",
      settings.clean({"advanced": None})["advanced"], False)
refuses("an advanced setting that is not a boolean", {"advanced": "yes"}, "true or false")

# The stage's autoplay. The same strict boolean, defaulting the other way:
# playing is what the stage has always done, so the file only ever needs to
# say "stop".
check("previews autoplay by default", settings.clean({})["autoplay_previews"], True)
check("turning autoplay off is kept",
      settings.clean({"autoplay_previews": False})["autoplay_previews"], False)
check("a null autoplay setting is the default",
      settings.clean({"autoplay_previews": None})["autoplay_previews"], True)
refuses("an autoplay setting that is not a boolean", {"autoplay_previews": "yes"}, "true or false")

# The turbo lead-in: how many opening steps a distilled render samples without
# the distillation. A whole number of steps rather than a boolean, because "off"
# and "how far" are one answer — and held to a ceiling, past which the idea
# stops being a lead-in.
check("no lead-in by default", settings.clean({})["turbo_lead_in"], 0)
check("a lead-in is kept", settings.clean({"turbo_lead_in": 2})["turbo_lead_in"], 2)
check("a null lead-in is the default", settings.clean({"turbo_lead_in": None})["turbo_lead_in"], 0)
check("both ends of the range are legal",
      (settings.clean({"turbo_lead_in": 0})["turbo_lead_in"],
       settings.clean({"turbo_lead_in": settings.MAX_LEAD_IN})["turbo_lead_in"]),
      (0, settings.MAX_LEAD_IN))
refuses("a lead-in past the ceiling", {"turbo_lead_in": settings.MAX_LEAD_IN + 1}, "between")
refuses("a negative lead-in", {"turbo_lead_in": -1}, "between")
refuses("a fractional lead-in", {"turbo_lead_in": 1.5}, "whole number")
# `True` is an int in Python, and a settings page that sent one would be storing
# a one-step lead-in nobody picked.
refuses("a boolean lead-in", {"turbo_lead_in": True}, "whole number")

check("the seam handoff is the latent by default", settings.clean({})["seam_handoff"], "latent")
check("...and can be any of the three roads",
      [settings.clean({"seam_handoff": road})["seam_handoff"] for road in settings.SEAM_HANDOFFS],
      list(settings.SEAM_HANDOFFS))
check("a null is the default", settings.clean({"seam_handoff": None})["seam_handoff"], "latent")
refuses("a road that does not exist", {"seam_handoff": "pixels"}, "one of")
refuses("the old boolean", {"seam_handoff": True}, "one of")

check("the drift guard is off by default", settings.clean({})["drift_guard"], 0)
check("...and takes a count up to every guess",
      (settings.clean({"drift_guard": 3})["drift_guard"],
       settings.clean({"drift_guard": settings.EVERY_GUESS})["drift_guard"]),
      (3, settings.EVERY_GUESS))
check("a null guard is the default", settings.clean({"drift_guard": None})["drift_guard"], 0)
refuses("a guard past every guess", {"drift_guard": settings.EVERY_GUESS + 1}, "between")
refuses("a negative guard", {"drift_guard": -1}, "between")
refuses("a fractional guard", {"drift_guard": 2.5}, "whole number")
refuses("a boolean guard", {"drift_guard": True}, "whole number")
refuses("the old road", {"drift_guard": "middle"}, "whole number")

# The reference cache's two numbers. Both are magnitudes with a meaningful
# zero, which is the thing to hold down: 0 GB is not "no cache", it is the
# in-session one with nothing written to disk, and 0 days is not "drop
# everything", it is forever. A validator that treated either as off would be a
# settings page whose left-hand stop did the opposite of what it says.
check("the cache is on by default", settings.clean({})["latent_cache"], True)
check("its ceiling has a default", settings.clean({})["latent_cache_gb"], 8.0)
check("so does its retention", settings.clean({})["latent_cache_days"], 30.0)
check("a zero ceiling is a value, not an absence",
      settings.clean({"latent_cache_gb": 0})["latent_cache_gb"], 0.0)
check("so is forever", settings.clean({"latent_cache_days": 0})["latent_cache_days"], 0.0)
check("both ceilings reach their limits",
      (settings.clean({"latent_cache_gb": settings.MAX_CACHE_GB})["latent_cache_gb"],
       settings.clean({"latent_cache_days": settings.MAX_CACHE_DAYS})["latent_cache_days"]),
      (settings.MAX_CACHE_GB, settings.MAX_CACHE_DAYS))
refuses("a cache past its ceiling", {"latent_cache_gb": settings.MAX_CACHE_GB + 1}, "between")
refuses("a negative cache", {"latent_cache_gb": -1}, "between")
refuses("a retention past a year", {"latent_cache_days": settings.MAX_CACHE_DAYS + 1}, "between")
refuses("a negative retention", {"latent_cache_days": -1}, "between")
# `True` is an int in Python, and would sail through as a one-gigabyte store or
# a one-day retention nobody picked.
refuses("a boolean ceiling", {"latent_cache_gb": True}, "must be a number")
refuses("a boolean retention", {"latent_cache_days": True}, "must be a number")
refuses("a cache switch that is a number", {"latent_cache": 1}, "true or false")

# The text scale: one multiplier over every size the pack draws. A fraction
# rather than a count, and bounded at both ends — the floor is where the 9px
# captions stop being legible and the ceiling is where a node face holds one
# pill, and a file holding either of those is a UI with no way left on it to say
# otherwise.
check("the drawn sizes by default", settings.clean({})["text_scale"], 1.0)
check("a scale is kept", settings.clean({"text_scale": 1.25})["text_scale"], 1.25)
check("a null scale is the default", settings.clean({"text_scale": None})["text_scale"], 1.0)
check("a whole number is a scale", settings.clean({"text_scale": 1})["text_scale"], 1.0)
check("both ends of the range are legal",
      (settings.clean({"text_scale": settings.MIN_TEXT_SCALE})["text_scale"],
       settings.clean({"text_scale": settings.MAX_TEXT_SCALE})["text_scale"]),
      (settings.MIN_TEXT_SCALE, settings.MAX_TEXT_SCALE))
refuses("a scale past the ceiling", {"text_scale": settings.MAX_TEXT_SCALE + 0.1}, "between")
refuses("a scale under the floor", {"text_scale": settings.MIN_TEXT_SCALE - 0.1}, "between")
# `True` is an int in Python, and it would sail through as the drawn sizes —
# stored as a scale nobody picked and indistinguishable from one that was.
refuses("a boolean scale", {"text_scale": True}, "must be a number")
refuses("a scale that is not a number", {"text_scale": "large"}, "must be a number")

# The output folders. One row per family — a render lands somewhere because of
# what rendered it — and `outputs.clean` is the authority on what a row may say,
# so this only has to show that the setting is held to it and that one family's
# row cannot move another family's files.
DEFAULT_PREFIXES = settings.default_prefixes()

check("every family this install has gets a row",
      (sorted(settings.clean({})["video_prefix"]),
       sorted(settings.clean({})["image_prefix"])),
      (sorted(DEFAULT_PREFIXES["video"]), sorted(DEFAULT_PREFIXES["still"])))
check("a folder is kept as typed",
      settings.clean({"video_prefix": {"ltx25": "client/shoot-3/take"}})["video_prefix"]["ltx25"],
      "client/shoot-3/take")
check("...and leaves the other families where they were",
      settings.clean({"video_prefix": {"ltx25": "client/shoot-3/take"}})["video_prefix"]["h3"],
      DEFAULT_PREFIXES["video"]["h3"])
check("a trailing slash keeps that family's filename stem",
      settings.clean({"image_prefix": {"krea2": "client/"}})["image_prefix"]["krea2"],
      "client/Krea2")
check("an empty folder is the family's default",
      settings.clean({"video_prefix": {"h3": ""}})["video_prefix"]["h3"],
      DEFAULT_PREFIXES["video"]["h3"])
# A family that is not installed keeps its row rather than losing it, the same
# deal `clean_weights` gives an unknown slot: uninstalling a family for an
# afternoon should not mean typing its folder again.
check("an unknown family's row is kept",
      settings.clean({"video_prefix": {"someday": "shots/someday"}})["video_prefix"]["someday"],
      "shots/someday")
refuses("an absolute output folder", {"video_prefix": {"h3": "/tmp/renders"}}, "absolute")
refuses("a folder that escapes upwards", {"image_prefix": {"h3": "../elsewhere/x"}},
        "'.' and '..'")
refuses("a folder block that is not one", {"video_prefix": ["shots"]}, "family id")

# ---- the migration off the flat layout ----------------------------------------
#
# Every settings file written before families had their own folders holds a
# string here. It migrates onto *every* family of its kind: somebody who pointed
# their stills at `client/stills` meant every still, and moving two of the three
# architectures somewhere else would be this change breaking a working setup.
check("a typed flat video folder reaches every video family",
      settings.clean({"video_prefix": "client/shoot-3/take"})["video_prefix"],
      {family: "client/shoot-3/take" for family in DEFAULT_PREFIXES["video"]})
check("...and a typed flat stills folder every still family",
      settings.clean({"image_prefix": "client/stills"})["image_prefix"],
      {family: "client/stills" for family in DEFAULT_PREFIXES["still"]})
# The one string that must not migrate: nobody chose the old default, and
# carrying it forward would pin the install to the flat layout for good.
check("the old default migrates to the new defaults instead",
      (settings.clean({"video_prefix": settings.outputs.LEGACY_VIDEO_PREFIX})["video_prefix"],
       settings.clean({"image_prefix": settings.outputs.LEGACY_IMAGE_PREFIX})["image_prefix"]),
      (DEFAULT_PREFIXES["video"], DEFAULT_PREFIXES["still"]))
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

    check("the lead-in reaches the render the same way",
          (settings.save({"turbo_lead_in": 2})["turbo_lead_in"], settings.turbo_lead_in()),
          (2, 2))
    settings.save({"turbo_lead_in": 0})

    # A save is a patch over the file, not a replacement of it. The page sends
    # the one field just edited, so a second save must not hand back the first
    # field's default — the bug that made a custom stills folder disappear the
    # moment somebody touched the video one.
    videos = {**DEFAULT_PREFIXES["video"], "ltx25": "client/shoot-3/take"}
    stills = {**DEFAULT_PREFIXES["still"], "krea2": "client/stills"}
    check("a later save keeps the earlier one",
          settings.save({"video_prefix": videos}),
          {**settings.DEFAULTS, "video_crf": 14, "video_prefix": videos})
    check("...and again, from the other side",
          settings.save({"image_prefix": stills}),
          {**settings.DEFAULTS, "video_crf": 14, "video_prefix": videos,
           "image_prefix": stills})
    check("...and that is what the save node asks for",
          (settings.video_prefix("ltx25"), settings.video_prefix("h3"),
           settings.image_prefix("krea2")),
          ("client/shoot-3/take", DEFAULT_PREFIXES["video"]["h3"], "client/stills"))

    settings.save({"video_crf": 14, "video_prefix": DEFAULT_PREFIXES["video"],
                   "image_prefix": DEFAULT_PREFIXES["still"]})

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

# ---- the file the pack wrote when it was called MiniMax Creator ---------------
#
# The rename's one real risk. An install that had typed an output folder must
# still be filing renders there afterwards — a
# rename does not get to move where somebody's finished work lands.

with tempfile.TemporaryDirectory() as directory:
    settings.path = lambda: os.path.join(directory, settings.FILE)
    typed = {**DEFAULT_PREFIXES["video"], "h3": "client/shoot-3/take"}
    with open(settings.legacy_path(), "w", encoding="utf-8") as handle:
        json.dump({"video_crf": 14, "video_prefix": typed}, handle)

    check("the old file is read when there is no new one",
          (settings.load()["video_crf"], settings.load()["video_prefix"]["h3"]),
          (14, "client/shoot-3/take"))

    # And it is read *once*: the first save writes the new name, and from then
    # on the old file is history rather than a second source of truth.
    settings.save({"video_crf": 20})
    check("...and saving moves it to the new name",
          sorted(os.listdir(directory)), sorted([settings.FILE, settings.LEGACY_FILE]))
    check("...carrying the typed folder with it",
          settings.load()["video_prefix"]["h3"], "client/shoot-3/take")

    # The new file wins outright once it exists, even though the old one is
    # still sitting beside it. Reading both and merging would make deleting a
    # setting impossible.
    with open(settings.legacy_path(), "w", encoding="utf-8") as handle:
        json.dump({"video_crf": 14}, handle)
    check("the new file wins over the old one", settings.video_crf(), 20)

# The default is libx264's own, which is what this pack wrote before the setting
# existed: turning the page on must not change anybody's files.
check("the default is what the encoder would have picked anyway",
      settings.DEFAULT_CRF, 23)

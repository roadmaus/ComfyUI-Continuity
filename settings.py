"""Preferences that belong to this ComfyUI rather than to a workflow.

The line this file draws: a workflow says what the piece *is* — the prompt, the
references, the duration. This says how this machine writes it. Two people
opening the same `.json` should get the same shot, and should not also be made
to agree about how many megabytes it may take or which folder on their own disk
it lands in.

Encoding quality was the first thing on this side of the line; the output
folders followed it, for the same reason and one more. A prefix stored per node
meant every node was a place the answer could differ, so a workflow with a
Creator, a Timeline and a pre-stage in it had three, and moving a project to
another machine carried someone else's folder names along with it.

So it is not in `creator_data` and it is not a widget. It is one small JSON file
that the settings page writes and the save node reads.

**Where it lives, and why not under `user/default/`.** The picker's favorites go
through the frontend's userdata API, which files them per ComfyUI user. This
cannot: it is read while a queued prompt executes, and an execution has no
request behind it and therefore no user. A file that the settings page wrote to
one place and the node read from another would be a setting that silently does
nothing. One file beside `user/`, read the same way by both.

This file decides what a setting is *allowed* to be; `js/minimax_creator/
settings.js` decides what the page *offers*. They are not mirrors and there is
no mirror test: the encoder's whole scale is legal here, so a value typed into
the file by hand is honoured and shown, while the page offers the four points on
it worth choosing between.

Nothing here imports torch or ComfyUI at module scope — `tests/test_settings.py`
runs it standalone, the same way `outputs.py` is tested.
"""

import json
import os

from . import outputs

FILE = "minimax_creator.settings.json"

# libx264's own scale, verbatim: 0 is (near) lossless and 51 is unwatchable.
# Refusing anything outside it here means the number reaching the encoder is
# always a number the encoder has an answer for.
MIN_CRF = 0
MAX_CRF = 51

# What libx264 picks when nothing tells it otherwise, which is exactly what this
# pack wrote before the setting existed. Passing it explicitly changes no file.
DEFAULT_CRF = 23

# Where the two kinds of file land under ComfyUI's output directory. Prefixes,
# not folders: core's `filename_prefix` names the folder *and* the stem every
# file in it is numbered off, and expands `%year%`-style tokens per render.
# `outputs.py` owns what one is allowed to be.
DEFAULT_VIDEO_PREFIX = outputs.VIDEO_PREFIX
DEFAULT_IMAGE_PREFIX = outputs.IMAGE_PREFIX

DEFAULTS = {
    "video_crf": DEFAULT_CRF,
    "video_prefix": DEFAULT_VIDEO_PREFIX,
    "image_prefix": DEFAULT_IMAGE_PREFIX,
    # Whether the sampler row draws the two flow-shift pills. Off by default:
    # most rows never leave the checkpoints' own schedule, and two more numbers
    # on every node is a cost only the people dialling schedules should pay.
    # Nothing queued ever reads this — it is a UI preference — but it lives
    # here because it is per-machine like everything else in this file, and one
    # settings page writing one file beats a second store for one boolean.
    "show_shift_pills": False,
    # Whether the node faces offer the controls most rows never touch — the
    # turbo lead-in, and the two accelerators that trade something subtle
    # enough that a row wearing them is not a row anybody set by accident.
    # Off by default, for the same reason as the pills above: the sampler row
    # should be the length of the decisions actually being made.
    #
    # It hides rather than disables, and it never hides something that is on.
    # A control in force keeps its pill whatever this says — the rule the
    # shift pills and the custom quality row already live by — so switching
    # this off can never quietly change what a render does.
    "advanced": False,
    # Whether the stage plays a clip the moment it has one — the finished
    # render, and the animated step previews while it samples. On by default
    # because it is what the stage has always done; off is for the canvases
    # where a dozen finished renders is a dozen looping decoders playing for
    # nobody. UI-only like the pills above: nothing queued ever reads it.
    "autoplay_previews": True,
    # How many of a turbo render's opening steps run on the un-distilled
    # weights — the turbo LoRA held off the model for those steps and patched
    # on for the rest. 0 is off, which is what every render did before this
    # existed. See `render.LeadIn` for what it builds and why.
    #
    # This reaches the render, which is the line the rest of this file draws
    # and the reason it is worth naming out loud: two people opening the same
    # `.json` get the same shot only if they agree about it. It sits here
    # anyway because it is a statement about how you use a distillation rather
    # than about this piece. The LoRA, the steps and the schedule are all still
    # the workflow's; this only says where in that schedule the distillation
    # takes over.
    "turbo_lead_in": 0,
    # How large this pack draws its own text, as a multiplier on every size in
    # it. 1 is what those sizes were written to be; the Appearance tab offers
    # four points and this file will hold anything between MIN and MAX_TEXT_SCALE
    # so a machine with an unusual screen can go past them by hand.
    #
    # UI-only, like the pills and the previews above: nothing queued reads it,
    # and a `.json` shared with someone else renders the same shot at whatever
    # size their own copy draws its buttons. It is here because it is per-machine
    # — which is the whole of what this file is — and because a screen you have
    # to lean into is not a per-workflow problem.
    "text_scale": 1.0,
    # Whether this pack wears ComfyUI's palette or a dark one of its own.
    #
    # "follow" is the default and is what the stylesheet does unaided: every
    # colour in styles/ derives from the palette the Appearance tab is set to,
    # so the pack changes when the desk does. "dark" keeps a dark ground for the
    # fullscreen editor whatever the desk is set to, which is not stubbornness —
    # it is what a tool for judging pictures is: a still or a frame read against
    # white is read against the wrong thing, and every editor that grades or cuts
    # is dark for that reason. There is deliberately no "light": a light editor
    # over a dark graph is the one combination nobody asks for.
    #
    # It reaches the fullscreen shell and not the node faces. A node body sits
    # inside a node ComfyUI draws in its own palette — title, chrome, the padding
    # around whatever the custom node put there — so a dark body on a light desk
    # is a dark island in a white card rather than a dark editor. The shell
    # covers the viewport and has no host chrome left to disagree with.
    #
    # UI-only, like the pills and the text scale above.
    "theme": "follow",
    # How far this pack's surfaces step off the ground beneath them.
    #
    # The four surfaces are each a mix of the palette's ground and its ink; this
    # multiplies how far along that mix each one sits. 1 is the ladder as drawn.
    # It exists because the ladder is proportional to a palette's own contrast,
    # and some palettes have very little — on Github, Nord and Solarized the
    # four surfaces come out close enough to read as two. Below 1 for a flatter
    # face, above 1 to pull the cards apart from what they sit on.
    #
    # UI-only. Applies to whatever palette is in force, including the pinned
    # dark one above and any palette that does not exist yet.
    "surface_lift": 1.0,
    # Whether a reference's latents are kept between renders. On by default:
    # the segment node caches on its whole payload, so editing one word of the
    # prompt re-decodes and re-encodes every reference the shot cites, and a
    # reference does not know the prompt exists. See `latents.py`.
    #
    # This reaches the render the way the lead-in does, and like it, it is a
    # statement about the machine rather than about the piece — off is for a
    # disk with nothing to spare. It cannot change what a render produces:
    # `encode._quantize` runs whether this is on or off, so a hit and a miss
    # send the model the same tensors and this only decides how long the wait is.
    "latent_cache": True,
    # How much of ComfyUI's temp directory those latents may fill, in
    # gigabytes. Past it the least recently read entries go. 0 keeps the
    # in-session cache and writes nothing to disk, which is the setting for a
    # machine where temp is a ramdisk.
    "latent_cache_gb": 8.0,
}

# What the text scale is allowed to be. The floor is where the 9px captions stop
# being legible at all; the ceiling is where a node face holds one pill. Wider
# than the four points the page offers, because the page is a set of good answers
# and this is the limit of the honest ones.
MIN_TEXT_SCALE = 0.8
MAX_TEXT_SCALE = 1.6

# What the pack may wear. "follow" reads ComfyUI's palette; "dark" pins a dark
# ground regardless of it. No "light": see the note on the setting itself.
THEMES = ("follow", "dark")

# How far the surface ladder may be pushed. The floor is where the four surfaces
# stop being four; the ceiling is where the cards stop looking like they belong
# to the ground they are on. Wider than the page offers, for the same reason the
# text scale is.
MIN_SURFACE_LIFT = 0.4
MAX_SURFACE_LIFT = 2.0

# How far the lead-in may reach. Not a hard truth about the model — it is the
# point past which the idea stops being a lead-in: the distillation is what the
# remaining steps are for, and a render that spends most of its schedule on the
# base weights at turbo step counts is a bad 20-step render, not a fast one.
MAX_LEAD_IN = 4

# How large the reference cache may be told to grow. The ceiling is not a truth
# about disks — it is the point past which a cache in *temp* is no longer a
# cache, and the answer is a store that outlives the process rather than a
# bigger pile in a directory core empties on restart.
MAX_CACHE_GB = 256.0


def clean(raw):
    """A settings blob -> the settings this pack will use. Unknown keys dropped.

    Raises ValueError on a key that is present and unusable, so the route can
    refuse it rather than store a value the node would then ignore. A missing
    key is not an error: it is the default, and a file written by an older
    version is missing every key added since.
    """
    if not isinstance(raw, dict):
        raise ValueError("settings must be an object")
    clean_settings = dict(DEFAULTS)
    if "video_crf" in raw and raw["video_crf"] is not None:
        crf = raw["video_crf"]
        # `True` is an int in Python and would sail through as crf 1.
        if isinstance(crf, bool) or not isinstance(crf, (int, float)) or crf != int(crf):
            raise ValueError("video_crf must be a whole number")
        crf = int(crf)
        if not MIN_CRF <= crf <= MAX_CRF:
            raise ValueError(f"video_crf must be between {MIN_CRF} and {MAX_CRF}")
        clean_settings["video_crf"] = crf
    if "turbo_lead_in" in raw and raw["turbo_lead_in"] is not None:
        lead = raw["turbo_lead_in"]
        # `True` is an int in Python and would sail through as a one-step
        # lead-in, the same trap `video_crf` sets above.
        if isinstance(lead, bool) or not isinstance(lead, (int, float)) or lead != int(lead):
            raise ValueError("turbo_lead_in must be a whole number of steps")
        lead = int(lead)
        if not 0 <= lead <= MAX_LEAD_IN:
            raise ValueError(f"turbo_lead_in must be between 0 and {MAX_LEAD_IN}")
        clean_settings["turbo_lead_in"] = lead
    if "text_scale" in raw and raw["text_scale"] is not None:
        scale = raw["text_scale"]
        # `True` is an int in Python and would sail through as scale 1, the same
        # trap the two counts above set.
        if isinstance(scale, bool) or not isinstance(scale, (int, float)):
            raise ValueError("text_scale must be a number")
        scale = float(scale)
        if not MIN_TEXT_SCALE <= scale <= MAX_TEXT_SCALE:
            raise ValueError(
                f"text_scale must be between {MIN_TEXT_SCALE} and {MAX_TEXT_SCALE}"
            )
        clean_settings["text_scale"] = scale
    if "surface_lift" in raw and raw["surface_lift"] is not None:
        lift = raw["surface_lift"]
        # `True` is an int in Python and would sail through as lift 1, the same
        # trap every count above sets.
        if isinstance(lift, bool) or not isinstance(lift, (int, float)):
            raise ValueError("surface_lift must be a number")
        lift = float(lift)
        if not MIN_SURFACE_LIFT <= lift <= MAX_SURFACE_LIFT:
            raise ValueError(
                f"surface_lift must be between {MIN_SURFACE_LIFT} and {MAX_SURFACE_LIFT}"
            )
        clean_settings["surface_lift"] = lift
    if "theme" in raw and raw["theme"] is not None:
        theme = raw["theme"]
        if theme not in THEMES:
            raise ValueError("theme must be one of: " + ", ".join(THEMES))
        clean_settings["theme"] = theme
    if "latent_cache_gb" in raw and raw["latent_cache_gb"] is not None:
        size = raw["latent_cache_gb"]
        # `True` is an int in Python and would sail through as one gigabyte,
        # the same trap every count above sets.
        if isinstance(size, bool) or not isinstance(size, (int, float)):
            raise ValueError("latent_cache_gb must be a number")
        size = float(size)
        if not 0 <= size <= MAX_CACHE_GB:
            raise ValueError(f"latent_cache_gb must be between 0 and {MAX_CACHE_GB}")
        clean_settings["latent_cache_gb"] = size
    for flag in ("show_shift_pills", "autoplay_previews", "advanced", "latent_cache"):
        if flag in raw and raw[flag] is not None:
            if not isinstance(raw[flag], bool):
                raise ValueError(f"{flag} must be true or false")
            clean_settings[flag] = raw[flag]
    for key, fallback in (("video_prefix", DEFAULT_VIDEO_PREFIX),
                          ("image_prefix", DEFAULT_IMAGE_PREFIX)):
        if key in raw and raw[key] is not None:
            # `outputs.clean` is what the save nodes are held to, so a prefix
            # that would be refused at the end of a render is refused here
            # instead — while it is still a field somebody is editing.
            try:
                clean_settings[key] = outputs.clean(raw[key], fallback)
            except outputs.PrefixError as exc:
                raise ValueError(f"{key}: {exc}") from exc
    return clean_settings


def path():
    """The settings file. Imported lazily so this module stays standalone."""
    import folder_paths

    return os.path.join(folder_paths.get_user_directory(), FILE)


def load():
    """The stored settings, with every key filled in.

    A file that cannot be read or cannot be understood reads as the defaults —
    which is what this pack did before anyone opened the settings page, and what
    the page will show, so a value that did not survive is visibly gone rather
    than quietly in force.
    """
    try:
        with open(path(), "r", encoding="utf-8") as handle:
            return clean(json.load(handle))
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save(raw):
    """Store a settings patch and hand back the whole stored file. Raises
    ValueError on a value this pack will not write.

    A patch, not a replacement: the settings page sends the one field somebody
    just edited, and every field it did not send is one somebody chose earlier.
    `clean` starts from the defaults — it has to, since it is also what reads a
    file written by an older version — so the merge happens here, over what is
    on disk, or typing a video folder would quietly put the stills folder back.
    """
    if not isinstance(raw, dict):
        raise ValueError("settings must be an object")
    stored = clean({**load(), **raw})
    target = path()
    os.makedirs(os.path.dirname(target), exist_ok=True)
    # Written whole and moved into place: the save node reads this file while
    # renders are queued, and a half-written one would read as the defaults.
    temporary = f"{target}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(stored, handle, indent=2)
    os.replace(temporary, target)
    return stored


def video_crf():
    """The quality target for every video this pack writes."""
    return load()["video_crf"]


def video_prefix():
    """Where finished renders land, unless the blob names somewhere itself."""
    return load()["video_prefix"]


def image_prefix():
    """Where pre-stage stills land, unless the blob names somewhere itself."""
    return load()["image_prefix"]


def turbo_lead_in():
    """How many opening steps a turbo render samples without the distillation."""
    return load()["turbo_lead_in"]

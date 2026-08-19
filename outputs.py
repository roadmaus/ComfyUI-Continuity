"""Where a render lands under ComfyUI/output.

Both save nodes take a `filename_prefix` and hand it to core's
`get_save_image_path`, which splits it into a subfolder and a filename stem,
expands `%year%`-style tokens, and refuses anything that would write outside the
output directory. That was always true; what was missing is that the prefix was
a module constant, so nobody could set it.

The prefix is the whole output-structure control. `%date%`-style tokens and
`/`-separated folders come from core for free, so this module only has to say
what the defaults are and turn a typed string into one core will accept —
*before* anything is queued, because `get_save_image_path` raising after a
render has been sampled costs the user the render.

The ComfyUI output directory itself is not ours to move: `--output-directory`
(or `--base-directory`) relocates it for every node pack at once, and every path
here is relative to whatever that resolved to.
"""

import re

# The two defaults. Both live under `minimax/` so the pack keeps one shelf in
# somebody else's output folder, and they are split one level deeper so the
# gallery sorts finished videos apart from PreStage stills with no special case
# in the picker: a shelf chip is just a subfolder, and these are two subfolders.
VIDEO_PREFIX = "minimax/renders/H3"
IMAGE_PREFIX = "minimax/stills/prestage"

# Tokens core's `compute_vars` expands. Listed only so the error message can
# tell the user what *is* allowed when they typo one; core owns the real list.
TOKENS = ("%year%", "%month%", "%day%", "%hour%", "%minute%", "%second%",
          "%width%", "%height%")

# Windows cannot create these, and a workflow shared from a Mac should not
# produce a folder its Windows half cannot write into.
ILLEGAL = re.compile(r'[<>:"|?*\x00-\x1f]')


class PrefixError(ValueError):
    """A typed output prefix cannot be used as a path."""


def clean(raw, default):
    """A user-typed output prefix -> one `get_save_image_path` will accept.

    Raises `PrefixError` rather than repairing: a prefix that has to be
    rewritten to be safe is one the user should see refused, so the files land
    where the field says they will. The exception is a trailing slash, which is
    not a mistake but a folder — "my-project/" plainly means "in there, named
    the usual thing", so it keeps the default's stem.
    """
    text = ("" if raw is None else str(raw)).strip().replace("\\", "/")
    if not text:
        return default

    if text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        raise PrefixError(
            f"output folder {raw!r}: absolute paths are not allowed — the prefix is "
            "relative to ComfyUI's output folder. Use --output-directory to move "
            "the output folder itself.")

    # A trailing slash names a folder; keep the default's filename stem.
    if text.endswith("/"):
        text += default.rsplit("/", 1)[-1]

    parts = text.split("/")
    for part in parts:
        if not part:
            raise PrefixError(f"output folder {raw!r}: empty folder name.")
        if part in (".", ".."):
            raise PrefixError(f"output folder {raw!r}: '.' and '..' are not allowed.")
        if part.startswith("."):
            raise PrefixError(f"output folder {raw!r}: folder names cannot start with a dot.")
        if ILLEGAL.search(part):
            raise PrefixError(
                f"output folder {raw!r}: a name cannot contain any of < > : \" | ? *")
        if part.endswith(" ") or part.endswith("."):
            raise PrefixError(
                f"output folder {raw!r}: a name cannot end with a space or a dot.")
    return "/".join(parts)


# The blob's own key is no longer written by the UI — where files land is a
# preference of this machine and lives in `settings.py`, so a workflow shared
# with someone else does not carry your folder names to their disk. It is still
# *read*, because a hand-edited blob is a supported way to drive these nodes and
# a prefix typed into one has to mean something. Blob first, then the setting.
def video(data, default=None):
    """The prefix a Creator or Timeline render lands under."""
    return clean(data.get("output_prefix"), default or VIDEO_PREFIX)


def image(data, default=None):
    """The prefix a PreStage still lands under."""
    return clean(data.get("output_prefix"), default or IMAGE_PREFIX)


def takes(prefix):
    """A render's prefix -> the prefix its individual passes land under.

    One folder deeper, and named for what is in it. A piece shot a pass at a
    time writes a file per pass as well as the piece, and those are working
    files: they are what a card plays instead of being sampled again, and they
    are of no interest once the piece is finished. In their own shelf they sort
    apart from the renders in the gallery and can be swept in one gesture; mixed
    in with them, a ten-card piece would bury the video it made.

    The stem is the render's own, so a take is recognisably from the same
    render as the file beside it.
    """
    folder, _, stem = prefix.rpartition("/")
    return f"{folder}/takes/{stem}" if folder else f"takes/{stem}"

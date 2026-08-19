"""What a typed output prefix is allowed to be.

Runs standalone — `python tests/test_outputs.py` — with no torch and no ComfyUI,
because `outputs.py` is deliberately free of both: it decides what a prefix may
say *before* the render starts, which is the whole point of it not living inside
the save node.

The cases that matter are the refusals. `get_save_image_path` would catch a
traversal on its own, but only after a clip has been sampled, and it reports it
as a stack trace against a node nobody put on the canvas.
"""

import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

spec = importlib.util.spec_from_file_location("mmc_outputs", os.path.join(ROOT, "outputs.py"))
outputs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(outputs)

from harness import FAILURES, check, passed


def refuses(label, raw, fragment):
    try:
        outputs.clean(raw, outputs.VIDEO_PREFIX)
    except outputs.PrefixError as exc:
        if fragment not in str(exc):
            FAILURES.append(f"{label}: refused, but said {str(exc)!r} (wanted {fragment!r})")
        return
    FAILURES.append(f"{label}: was accepted")


D = outputs.VIDEO_PREFIX

# ---- the ordinary cases -----------------------------------------------------

check("nothing typed means the default", outputs.clean("", D), D)
check("None means the default", outputs.clean(None, D), D)
check("whitespace only means the default", outputs.clean("   ", D), D)
check("a plain name is kept", outputs.clean("H3", D), "H3")
check("folders are kept", outputs.clean("my-project/scene-a/take", D), "my-project/scene-a/take")
check("surrounding whitespace is trimmed", outputs.clean("  shots/a  ", D), "shots/a")

# A Windows user typing a Windows path should get a working prefix, not a
# lecture: the separator is the only thing wrong with it and it means the same.
check("backslashes are separators", outputs.clean("my-project\\take", D), "my-project/take")

# A trailing slash is a folder, not a mistake — it is what anyone types when
# they mean "in here, named the usual thing".
check("a trailing slash keeps the default's stem", outputs.clean("my-project/", D), "my-project/H3")
check("...including a bare one", outputs.clean("shots/", "minimax/stills/prestage"),
      "shots/prestage")

# Tokens are core's and pass through untouched — including in a folder, which is
# where a date token is actually useful.
check("date tokens survive", outputs.clean("minimax/%year%-%month%-%day%/H3", D),
      "minimax/%year%-%month%-%day%/H3")
check("size tokens survive", outputs.clean("H3_%width%x%height%", D), "H3_%width%x%height%")

# ---- the refusals -----------------------------------------------------------

refuses("a parent traversal", "../../etc/H3", "'.' and '..'")
refuses("a traversal in the middle", "minimax/../../H3", "'.' and '..'")
refuses("a posix absolute path", "/var/renders/H3", "absolute paths")
refuses("a windows absolute path", "C:/renders/H3", "absolute paths")
# A UNC path normalizes to a leading "//" and is caught as the absolute path it
# is, which is the message worth showing — it names the flag that does work.
refuses("a UNC path", "\\\\server\\share\\H3", "absolute paths")
refuses("a hidden folder", ".secret/H3", "cannot start with a dot")
refuses("a doubled separator", "minimax//H3", "empty folder name")
refuses("a character Windows cannot write", "minimax/a:b/H3", '< > : " | ? *')
refuses("a name ending in a space", "minimax /H3", "space or a dot")
refuses("a name ending in a dot", "minimax./H3", "space or a dot")

# The refusal has to say what to do instead, because "use --output-directory" is
# genuinely the answer for the person who typed an absolute path.
try:
    outputs.clean("/mnt/big/renders", D)
except outputs.PrefixError as exc:
    check("the absolute-path refusal points at the flag that does work",
          "--output-directory" in str(exc), True)

# ---- the two blob accessors -------------------------------------------------

check("a blob with no key gets the video default", outputs.video({}), outputs.VIDEO_PREFIX)
check("a blob with no key gets the image default", outputs.image({}), outputs.IMAGE_PREFIX)
check("a blob's key is used", outputs.video({"output_prefix": "shots/a"}), "shots/a")
# Stills and clips default apart, which is what pre-sorts the gallery into two
# shelves with no special case in the picker.
check("the two defaults are different folders",
      outputs.VIDEO_PREFIX.rsplit("/", 1)[0] != outputs.IMAGE_PREFIX.rsplit("/", 1)[0], True)

# A render's takes sort into a shelf of their own, one folder under wherever
# the render itself lands, and keep the render's stem.
check("takes go one folder deeper", outputs.takes("minimax/renders/H3"),
      "minimax/renders/takes/H3")
check("...even under a typed folder", outputs.takes("shots/a"), "shots/takes/a")
check("...and under no folder at all", outputs.takes("H3"), "takes/H3")

passed("all output-prefix tests passed")

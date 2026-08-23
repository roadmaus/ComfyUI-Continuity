"""The render loop, bound to H3 — the one family this pack ships today.

The loop itself is `core/emit.py` and knows no family; H3's half of it is
`families/h3/render.py`. This module is the seam between the two eras: every
caller — the nodes, the still path, the suites — has always spelled the loop
`render.emit` and the row `render.Sampling`, and until the family registry
lands (phase 4) there is exactly one family to bind, so the binding lives here
rather than in every caller.

Nothing is defined in this file. When a second family exists, the registry
picks what this hardcodes, and the callers name a family instead of a module.
"""

from . import sampling
from .core import emit as _loop
from .core.emit import (FILENAME_PREFIX, emit_tail, expanded,  # noqa: F401
                        inherited_audio, inherited_frames, is_clip_source)
from .families.h3 import render as _h3
from .families.h3.render import (FACE_NODE, REFINE_NODE,  # noqa: F401
                                 SEGMENT_NODE, LeadIn, face_payload,
                                 patched, routed)
from .models import Links  # noqa: F401

# Re-exported, not defined: the row and its defaults are `sampling.py`'s, which
# is a module with no ComfyUI import in it so that the blob half of the row can
# be read — and mirrored, and one day declared by a family manifest — without
# booting a server. Named here as well because everything downstream of `emit`
# has always spelled them `render.Sampling` / `render.SHIFT_DEFAULTS`.
SHIFT_DEFAULTS = sampling.SHIFT_DEFAULTS
Sampling = sampling.Sampling


def compile_all(payloads, labels):
    """The loop's early compile, bound to H3. See `core.emit.compile_all`."""
    return _loop.compile_all(_h3.FAMILY, payloads, labels)


def emit(payloads, labels, weights, sampling, acceleration, unique_id,
         filename_prefix=FILENAME_PREFIX, cards=None, seeds=None,
         whole_piece=True, lead_in=None):
    """The loop, bound to H3. See `core.emit.emit` for every argument.

    `lead_in` is the turbo lead-in this machine asks for — see `LeadIn`. Absent
    means none, which is every render this pack made before the setting existed
    and every render on a machine that leaves it off. It is H3's per-queue run
    context, which is why the normalisation happens at this binding rather than
    in the loop.
    """
    return _loop.emit(_h3.FAMILY, payloads, labels, weights, sampling,
                      acceleration, unique_id, filename_prefix=filename_prefix,
                      cards=cards, seeds=seeds, whole_piece=whole_piece,
                      run=lead_in or LeadIn())

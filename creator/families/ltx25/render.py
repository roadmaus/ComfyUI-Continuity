"""LTX 2.5's render half — the skeleton, and the refusal that stands in for it.

The family is registered, manifested and selectable before a single node of it
is emitted, deliberately: the frontend half of a second family (a piece naming
which weights it renders with, controls reading the family off the piece rather
than off a module constant) is provable only once there are two families to
choose between, and it is not provable at all against a family that cannot be
picked. So the declarations land first and this file refuses politely until the
graph behind it exists.

Refusing from `preflight` is what makes it polite. It is the first hook the
loop calls (`core/emit.py`) — before any payload compiles, before the weights
are checked, before a node is built — so a queued LTX piece stops with a
sentence instead of a `NotImplementedError` from somewhere three hooks deep.
Every other hook is inherited unimplemented, and each raises under its own
name if the loop is ever reached another way.
"""

from ..base import Family


class LTX25(Family):
    id = "ltx25"
    label = "LTX 2.5"
    produces = frozenset({"video"})

    def preflight(self, sampling, acceleration):
        raise ValueError(
            "This piece is set to render with LTX 2.5, which this node can "
            "describe but cannot yet sample: the loaders, the segment and the "
            "sampler subgraph are not built. Switch the model pill back to "
            "MiniMax H3 to queue it."
        )


FAMILY = LTX25()

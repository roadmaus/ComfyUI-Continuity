"""What a family tells the frontend about itself.

The manifest is the part that decides whether the UI survives a new family.
A family the frontend has never heard of brings concepts no H3-derived
constant would have anticipated — separate video and audio CFG scales, a
stretched schedule with its own terminal, per-guide strengths — so a manifest
does not ship a bag of values for hardcoded controls: it describes the
*controls*, in a small widget vocabulary the frontend renders from.

A widget is `{id, type, min, max, step, default, label, help, group}` with
`type` one of `slider | toggle | combo | stepper`. A combo may carry its
`options`; one that does not draws its list off the node's own widget, because
core's sampler and scheduler names are the node schema's to declare and a copy
of them here would go stale the first time core added one (the same rule
`sampling.py` follows). `group` places the control — `sampler` is the row,
`accel` the accelerator pills, `weights` the weights popover.

Beyond widgets a manifest declares: **weight slots** (which files the family
loads, from which folders, and how — mirrored off the family's own slot
table); **canvas rules** (snap multiple, the frame grid, fps and whether fps
is fixed or conditioning, native edges and area caps); **capabilities**
(bidirectional — a new family may *have* things H3 lacks); and the **prompt
pipeline** (how prose reaches the model, and what an attached reference is
called in it).

Everything here is pure and built from the same modules the compile already
reads — `sampling.DEFAULTS`, `models.SLOTS`, `canvas.py`, the family
packages — so a manifest cannot drift from the code that renders, and the
suites hold the two together without booting a server. `describe` validates
every manifest it hands out; a family that declares a malformed control fails
by name at the route, not as a blank pill in the UI.
"""

import importlib

from . import registry

WIDGET_TYPES = ("slider", "toggle", "combo", "stepper")
WIDGET_GROUPS = ("sampler", "accel", "weights", "reference")


def widget(id, type, *, label, group, default=None, min=None, max=None,
           step=None, options=None, help=""):
    """One control, in the vocabulary above. Keys with nothing to say are
    omitted rather than carried as nulls, so the frontend reads presence."""
    if type not in WIDGET_TYPES:
        raise ValueError(f"widget {id!r}: unknown type {type!r}")
    if group not in WIDGET_GROUPS:
        raise ValueError(f"widget {id!r}: unknown group {group!r}")
    entry = {"id": id, "type": type, "label": label, "group": group,
             "default": default, "help": help}
    for key, value in (("min", min), ("max", max), ("step", step),
                       ("options", value_list(options))):
        if value is not None:
            entry[key] = value
    return entry


def value_list(options):
    """Options as a plain list, or None — tuples do not survive JSON."""
    return list(options) if options is not None else None


def canvas_block(rules):
    """A `canvas.Rules` as the frontend's canvas declaration.

    Shared rather than written once per family: the *fields* are the contract
    `canvas.js`'s `rulesFrom` reads, and they are the same fields for every
    family because the math is. What differs is the numbers, and those are the
    `Rules` instance's — which is the whole point of the dataclass.

    `fps.fixed` is the one field worth reading twice: H3 was trained at 24 and
    takes no rate conditioning, so its pill is a readout; LTX carries the rate
    in `LTXVConditioning`, so its pill is a control.
    """
    return {
        "multiple": rules.multiple,
        "fps": {"value": rules.fps, "fixed": rules.fps_fixed},
        "min_short_edge": rules.min_short_edge,
        "max_short_edge": rules.max_short_edge,
        "native_short_edge": rules.native_short_edge,
        "native_max_pixels": rules.native_max_pixels,
        "min_ratio": rules.min_ratio,
        "max_ratio": rules.max_ratio,
        "aspects": dict(rules.aspects),
        "frames": {
            # Legal counts are step*n + offset — the temporal packing.
            "step": rules.frame_step,
            "offset": rules.frame_offset,
            "trained_min": rules.trained_min_frames,
            "trained_max": rules.trained_max_frames,
            "min_seconds": rules.min_seconds,
            "max_seconds": rules.max_seconds,
        },
    }


def check(manifest):
    """Refuse a malformed manifest, naming what is wrong.

    The shape checked here is the contract the frontend renders from; a family
    that forgets a field should fail at `describe`, where the family is named,
    not as a blank control three files away.
    """
    for key in ("id", "label", "description", "produces", "widgets", "weights",
                "canvas", "capabilities", "prompt"):
        if key not in manifest:
            raise ValueError(f"family {manifest.get('id')!r}: manifest has no {key!r}")
    for entry in manifest["widgets"]:
        for key in ("id", "type", "label", "group", "default"):
            if key not in entry:
                raise ValueError(
                    f"family {manifest['id']!r}: widget {entry.get('id')!r} "
                    f"has no {key!r}")
        if entry["type"] not in WIDGET_TYPES:
            raise ValueError(
                f"family {manifest['id']!r}: widget {entry['id']!r} has "
                f"unknown type {entry['type']!r}")
    for entry in manifest["weights"]:
        for key in ("id", "folder", "label"):
            if key not in entry:
                raise ValueError(
                    f"family {manifest['id']!r}: weight slot "
                    f"{entry.get('id')!r} has no {key!r}")
    return manifest


def describe(family):
    """The validated manifest of one family, by id."""
    module = importlib.import_module(f".{family}.manifest", __package__)
    return check(module.manifest())


def catalog():
    """Everything the frontend needs to know what exists: every family's
    manifest in the registry's order, how the pre-stage's arch pill maps onto
    them, and which of them a piece may be rendered with.

    The video half is served rather than derived on the frontend so the two
    sides cannot disagree about the default: `compile.piece_family` reads an
    absent `family` as `default_video_family`, and the pill has to offer the
    same set the compiler will accept.
    """
    return {
        "families": [describe(family) for family in registry.FAMILIES],
        "still_arches": dict(registry.STILL_ARCHES),
        "default_still_arch": registry.DEFAULT_STILL_ARCH,
        "video_families": list(registry.video_families()),
        "default_video_family": registry.DEFAULT_VIDEO,
    }

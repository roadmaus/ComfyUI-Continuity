"""What a family tells the frontend about itself.

The manifest is the part that decides whether the UI survives a new family.
A family the frontend has never heard of brings concepts no H3-derived
constant would have anticipated — separate video and audio CFG scales, a
stretched schedule with its own terminal, per-guide strengths — so a manifest
does not ship a bag of values for hardcoded controls: it describes the
*controls*, in a small widget vocabulary the frontend renders from.

A widget is `{id, type, min, max, step, default, label, help, group}` with
`type` one of `slider | toggle | combo | stepper | text`. A combo may carry its
`options`; one that does not draws its list off the node's own widget, because
core's sampler and scheduler names are the node schema's to declare and a copy
of them here would go stale the first time core added one (the same rule
`sampling.py` follows). `group` places the control — `sampler` is the row,
`accel` the accelerator pills, `guidance` the taste-guidance pills beside them,
`weights` the weights popover.

Four optional keys say what a value *means* rather than how it is drawn.

`off` is the value at which the control does nothing, which is what lets a pill
be lit only while it is costing something — LTX's STG is off at 0 and its
modality guidance at 1.0, and neither number is guessable from a range. It is
also what a pill reads *out* at that value: a slider sitting on its `off` says
"detail guidance off" rather than "detail guidance 0.0", so a feature nobody
switched on does not read as a number somebody dialled.

`requires` is the conditions under which the control is drawn at all — a name,
a `(name, value)` pair, or a list of either, all satisfied or the pill does not
appear. A bare name means "that control is doing something", the rule Spectrum's
blend follows on H3's handwritten row; a pair means "that control is set to
this". Both forms exist because both cases are real on one family: LTX's
terminal modifies its stretch (a name), and neither of them describes the
render at all unless `schedule` is `scheduler` (a pair). The distilled curve is
nine fixed sigmas, and drawing five live-looking pills that nothing reads is
the one thing a declared row can get worse than H3's handwritten one.

`advanced` marks a control most rows never touch, which the node draws only
when Settings → Nodes asks for everything. A length control and not a
permission: a value away from its `default` keeps its pill whatever the setting
says — in force means visible, the rule `settings.py`'s flag is documented by
and the rule the shift pills and the custom quality row already live under.

`names` renames a combo's *values* for the pill without touching them. The
options are the wire — `distilled` and `scheduler` are which SIGMAS node the
render emits — and the pill saying "recipe built-in" is a display, so the two
are separate keys rather than one list the frontend would have to translate
back before it could be sent anywhere.

Beyond widgets a manifest declares: **weight slots** (which files the family
loads, from which folders, and how — mirrored off the family's own slot
table); **canvas rules** (snap multiple, the frame grid, fps and whether fps
is fixed or conditioning, native edges and area caps); **capabilities**
(bidirectional — a new family may *have* things H3 lacks); and the **prompt
pipeline** (how prose reaches the model, what an attached reference is called in
it, and which templates the refiner offers for it — see `families/refine.py`).

Everything here is pure and built from the same modules the compile already
reads — `sampling.DEFAULTS`, `models.SLOTS`, `canvas.py`, the family
packages — so a manifest cannot drift from the code that renders, and the
suites hold the two together without booting a server. `describe` validates
every manifest it hands out; a family that declares a malformed control fails
by name at the route, not as a blank pill in the UI.
"""

import importlib

from . import registry

WIDGET_TYPES = ("slider", "toggle", "combo", "stepper", "text")
WIDGET_GROUPS = ("sampler", "accel", "guidance", "weights", "reference")


def widget(id, type, *, label, group, default=None, min=None, max=None,
           step=None, options=None, help="", off=None, requires=None,
           advanced=False, names=None, pill=None):
    """One control, in the vocabulary above. Keys with nothing to say are
    omitted rather than carried as nulls, so the frontend reads presence."""
    if type not in WIDGET_TYPES:
        raise ValueError(f"widget {id!r}: unknown type {type!r}")
    if group not in WIDGET_GROUPS:
        raise ValueError(f"widget {id!r}: unknown group {group!r}")
    entry = {"id": id, "type": type, "label": label, "group": group,
             "default": default, "help": help}
    for key, value in (("min", min), ("max", max), ("step", step),
                       ("options", value_list(options)),
                       ("off", off), ("requires", conditions(requires)),
                       ("advanced", advanced or None),
                       ("names", dict(names) if names else None),
                       ("pill", pill)):
        if value is not None:
            entry[key] = value
    return entry


def conditions(requires):
    """`requires` in its one stored shape: a list of `{id}` / `{id, value}`.

    Three spellings reach this — a name, a `(name, value)` pair, or a list of
    either — and one comes out, because the frontend asks "is every condition
    satisfied" and a renderer that had to sniff which of three shapes it was
    holding would be answering a question this function can answer once.
    """
    if requires is None:
        return None
    if isinstance(requires, str) or isinstance(requires, tuple):
        requires = [requires]
    out = []
    for entry in requires:
        if isinstance(entry, str):
            out.append({"id": entry})
        else:
            id, value = entry
            out.append({"id": id, "value": value})
    return out


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
    # `requires` names controls this one depends on, and a name that is not a
    # control is a pill that never draws — silently, which is the one failure
    # worth catching here rather than in a browser. A bare condition also has
    # to name a control that declares an `off`, or "is it doing something" has
    # no answer and the pill is again invisible for a reason nothing states.
    by_id = {entry["id"]: entry for entry in manifest["widgets"]}
    for entry in manifest["widgets"]:
        for cond in entry.get("requires", []):
            target = by_id.get(cond["id"])
            if target is None:
                raise ValueError(
                    f"family {manifest['id']!r}: widget {entry['id']!r} requires "
                    f"{cond['id']!r}, which this family does not declare")
            if "value" not in cond and "off" not in target:
                raise ValueError(
                    f"family {manifest['id']!r}: widget {entry['id']!r} requires "
                    f"{cond['id']!r} to be doing something, but {cond['id']!r} "
                    f"declares no 'off' value to be doing something against")
        for value in entry.get("names", {}):
            if value not in entry.get("options", [value]):
                raise ValueError(
                    f"family {manifest['id']!r}: widget {entry['id']!r} renames "
                    f"{value!r}, which is not one of its options")
    for entry in manifest["weights"]:
        for key in ("id", "folder", "label"):
            if key not in entry:
                raise ValueError(
                    f"family {manifest['id']!r}: weight slot "
                    f"{entry.get('id')!r} has no {key!r}")
    # The refiner's template pill, on the families that have a refiner. It
    # rewrites a shot's description, so a still-only family declares none and
    # the pill never draws for one. `auto` is what every reader spells for
    # "follow the request", and a list that did not open with it would draw a
    # pill whose first chip pins something — so the position is checked rather
    # than assumed. Each chip carries its own copy, because a chip named `FL2V`
    # says nothing to anyone who has not read the family's model card.
    if "video" in manifest["produces"]:
        templates = manifest["prompt"].get("templates")
        if not templates or templates[0].get("name") != "auto":
            raise ValueError(
                f"family {manifest['id']!r}: prompt.templates must list the "
                f"refiner's templates with 'auto' first")
        for entry in templates:
            if not entry.get("name") or not entry.get("help"):
                raise ValueError(
                    f"family {manifest['id']!r}: refine template "
                    f"{entry.get('name')!r} has no help text")
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

    `upscalers` are the backends that belong to no family — ReDetail re-renders
    a finished pass through LTX 2.5's weights whatever family made it, so its
    files and its copy are served beside the families rather than inside one.
    """
    from .. import redetail

    return {
        "families": [describe(family) for family in registry.FAMILIES],
        "upscalers": [redetail.manifest()],
        "still_arches": dict(registry.STILL_ARCHES),
        "default_still_arch": registry.DEFAULT_STILL_ARCH,
        "video_families": list(registry.video_families()),
        "default_video_family": registry.DEFAULT_VIDEO,
    }

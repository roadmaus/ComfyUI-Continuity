"""A family's sampler row, read off the blob and refused by name.

Every family stores its row in `creator_data.sampling` and every family has to
answer the same question about it: is this field the kind of thing it is
supposed to be? The answer is the same six answers each time — a whole number, a
number with or without a floor, a flag, one of a fixed list, a name, or
something only that family can judge — and it was written out twice, once per
family, differing in nothing but its field lists.

So the *kinds* are declared here and the fields are declared by the family. A
third row is six tuples rather than a second validator, which is the whole
point: a family's sampler is a different shape from H3's (LTX has no `scheduler`
at all and two CFG scales where H3 has one), and describing that shape should
not mean re-deciding what "must be a whole number" means.

**Refused rather than coerced.** A hand-edited `"steps": "twenty"` should say so
before a loader is built, not sample once at whatever `int()` made of it. The
blob is the frontend's and hand-editing it is supported, which is exactly why a
field that arrives wrong is worth a sentence naming it.

**An absent block is not an error.** It is the ordinary state of every workflow
saved before its family's row moved into the blob, and it means every field
falls back — to the node's widgets on H3, whose thirteen frozen slots *are* its
row, and to the family's own defaults everywhere else.
"""


class Row:
    """One family's row: which fields it has, and of what kind.

    `error` is the family's own exception type, so a bad row still fails as
    `sampling.SamplingError` and callers catching it are unchanged.

    `floors` gives a field the value below which it stops meaning what its name
    says — LTX's modality guidance is off at 1.0 and scales by `scale - 1`, so
    below it the guidance runs backwards. Not the same thing as a minimum: it is
    the value at which the control does nothing, which is also what the manifest
    serves as `off`.

    `custom` is the escape hatch, `{field: fn}`, for a field only the family can
    judge — LTX's `stg_blocks` is "any text with a number in it", because that
    is what core's own `re.findall` makes of it.
    """

    def __init__(self, defaults, *, error=ValueError, whole=(), number=(),
                 flag=(), choice=None, floors=None, custom=None):
        self.defaults = dict(defaults)
        self.error = error
        self.whole = tuple(whole)
        self.number = tuple(number)
        self.flag = tuple(flag)
        self.choice = dict(choice or {})
        self.floors = dict(floors or {})
        self.custom = dict(custom or {})

    def checked(self, name, value):
        """One field, validated. -> the value in the type the row holds it in."""
        if name in self.custom:
            return self.custom[name](value)
        if name in self.whole:
            # `True` is an int in Python and would sail through as one step.
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or value != int(value)):
                raise self.error(f"sampling.{name} must be a whole number")
            if int(value) < 1:
                raise self.error(f"sampling.{name} must be at least 1")
            return int(value)
        if name in self.number:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise self.error(f"sampling.{name} must be a number")
            floor = self.floors.get(name)
            if floor is not None and value < floor:
                raise self.error(
                    f"sampling.{name} must be at least {floor} — that is the "
                    f"value at which it does nothing, and below it the guidance "
                    f"runs backwards")
            return float(value)
        if name in self.flag:
            if not isinstance(value, bool):
                raise self.error(f"sampling.{name} must be true or false")
            return value
        if name in self.choice:
            if value not in self.choice[name]:
                offered = ", ".join(self.choice[name])
                raise self.error(f"sampling.{name} must be one of: {offered}")
            return value
        # Whatever is left is a name — the sampler, the scheduler. Deliberately
        # not checked against core's lists: those are what the widget offers and
        # what `KSampler` will refuse by name, and a copy of them here would go
        # stale the first time core added one.
        if not isinstance(value, str) or not value:
            raise self.error(f"sampling.{name} must be a name")
        return value

    def stored(self, data):
        """The blob's `sampling` block, validated. `{}` where there is none.

        Fields the row does not declare are dropped rather than refused: a blob
        written by a newer frontend, or one carried across from another family,
        holds names this row has no use for and that is not a reason to refuse
        the render.
        """
        raw = (data or {}).get("sampling")
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise self.error("sampling must be an object")
        return {name: self.checked(name, value)
                for name, value in raw.items()
                if name in self.defaults and value is not None}

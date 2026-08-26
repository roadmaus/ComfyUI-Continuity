"""What each panel of the Ingredients reference sheet holds, said in words.

Lightricks' `Ingredients` IC-LoRA does not read a list of references. It reads
*one* picture — "a single composite image showing characters, props, and
locations laid out on a black background" — handed in as a guide, and it holds
what is on that picture consistent through the video it generates. The picture
itself is made when you pick the files, not when the render runs: see
`creator/plate.py`, which mattes and lays out for both families and owns the
grid this module places panels against.

What is left here is the prose half, and it is pure — no torch — because
`grammar.py` reaches for it and the compiler runs long before a loader exists.
"""

from ... import plate

# What a chip means when the sheet has to say what a panel is for. The `takes`
# vocabulary is `compile.IMAGE_TAKES`, and these are its nouns — one short
# clause each, because this section is a *scaffold*: the refiner overwrites it
# with a description of what is actually in the pictures, and what is here is
# what a render that was never refined still sends. `full` gets no noun at all:
# it is the default and it means "this whole picture is the reference", which is
# a sentence with nothing in it.
_TAKES_NOUN = {
    "person": "the person",
    "object": "the object",
    "scene": "the location",
    "style": "the look",
}

# Where a panel sits, said in words. This is what an undescribed panel gets, and
# it is the one thing about a picture the compiler can always know without
# opening it — which makes it the honest scaffold. It is also *checkable*: the
# model is looking at the sheet, so "panel 3 is top right" is a statement it can
# bind to a place on an image, where "panel 3 is a reference" would be a label
# defining itself.
# Keyed by how many there are, because the middle word only exists when there is
# a middle: two columns are left and right, three are left, centre and right. A
# fixed three-word list read with a clamp called the second of two "centre".
_DOWN = {2: ("top", "bottom"), 3: ("top", "middle", "bottom")}
_ACROSS = {2: ("left", "right"), 3: ("left", "centre", "right")}


def _where(row, col, cols, rows):
    """Which cell this is, in words — "top left", "right", or "" for a lone panel."""
    down = _DOWN.get(rows, ())
    across = _ACROSS.get(cols, ())
    return " ".join(part for part in (down[row] if row < len(down) else "",
                                      across[col] if col < len(across) else "")
                    if part)


def _placed(rect):
    """An arranged panel's place, in words, from its rect's centre.

    Thirds of the canvas each way, the same vocabulary the grid words use — a
    panel dragged to the top right corner is "top right", one left near the
    middle says nothing vertical. Both middles is "" and the caller places it
    as it places a lone panel, because "the middle middle" is not a sentence.
    """
    x, y, w, h = (float(v) for v in rect)
    across = ("left", "", "right")[min(2, max(0, int((x + w / 2) * 3)))]
    down = ("top", "", "bottom")[min(2, max(0, int((y + h / 2) * 3)))]
    return " ".join(part for part in (down, across) if part)


def describe(plan, cast=()):
    """What each panel holds, as the `reference_sheet` half of the caption.

    `plan` is `compile.plan_references`' walk, so the labels here are the same
    strings the body was substituted with — `panel 1` in this section and
    `panel 1` in the description are the same panel by construction rather than
    by both counting to three.

    A cast member who claimed the file speaks for it: they are the piece's own
    description of who that is, written once and kept across every shot, which
    is a better sentence than any chip. Otherwise the chip is what there is, and
    where the chip is `full` — the default, which says only "this whole picture
    is the reference" — the panel is placed instead: "panel 3 is top right".

    **Every panel is defined, and that is the rule.** A caption naming `panel 1`
    with nothing anywhere saying what panel 1 is would be exactly the failure H3
    spent section 2 of its guide on — a label pointing at nothing. Placing an
    undescribed panel is the weakest true sentence available, and it is a
    sentence the model can check against the sheet in front of it.

    -> "" where there is nothing to describe, which is what keeps a card with no
    references composing the caption it did before this existed.
    """
    owner = {}
    for subject in cast or ():
        for handle in getattr(subject, "sources", ()) or ():
            owner.setdefault(handle, subject)

    panels = [step for step in plan if step["op"] == "image"]
    cols, rows = plate.grid(len(panels))
    clauses = []
    for index, step in enumerate(panels):
        asset = step["asset"]
        subject = owner.get(asset.handle)
        # An arranged panel is where it was put; an unarranged one is in its
        # grid cell. Same vocabulary either way, and either is checkable
        # against the sheet the model is looking at.
        where = _placed(asset.rect) if getattr(asset, "rect", None) \
            else _where(*divmod(index, cols), cols, rows)
        if subject is not None and getattr(subject, "description", ""):
            what = str(subject.description).rstrip(".")
        elif asset.takes in _TAKES_NOUN:
            what = f"{_TAKES_NOUN[asset.takes]} {where}".strip() if where \
                else _TAKES_NOUN[asset.takes]
        else:
            what = where or "the whole sheet"
        clauses.append(f"{step['label']} is {what}")
    if not clauses:
        return ""
    return "; ".join(clauses) + "."

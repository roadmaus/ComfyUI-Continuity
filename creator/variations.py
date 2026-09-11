"""`{day|night}` in a prompt: a choice the seed makes.

Braces holding alternatives separated by bars are one prompt that can become
many videos — "put them {on the beach|in a mansion {at night|by day}}" is four
shots, and which one a render makes is decided by the number it samples on.
Nothing else is random: the same seed on the same text makes the same choice,
so a take can be re-shot, and rolling the seed is what asks for a new one.

The grammar is the smallest one that does the job. A brace pair is a group
only when a bar sits directly inside it; `{like this}` is prose and stays as
typed, and so does a `{` nothing closes. Groups nest, and an alternative may be
empty — `{|, smiling}` is "sometimes add a smile". There are no weights and no
escapes, because every one that was considered was a second thing to learn for
a feature whose whole point is that it is typed like a sentence.

`web/creator/variations.js` is the mirror of this file: the prompt box lights
the alternative the seed on the node will pick, and it can only do that
honestly by making the same choice this side makes. `tests/test_variations.py`
holds the two to each other. The choice is a hash of the seed, the card and the
group's place in the text rather than a stream from a seeded generator, because
a hash is the same twelve lines in both languages and a generator is not.

Free of torch and of ComfyUI, like `compile.py`, so the suite runs it bare.
"""

from dataclasses import dataclass, field

__all__ = ["Group", "choose", "has_groups", "parse", "passed_over", "resolve",
           "shapes", "vary_mapping"]


@dataclass
class Group:
    """One `{a|b|c}`: where it sits in the text, and what it offers.

    `alternatives` are lists of parts, each part a `str` or a nested `Group`.
    `index` is the group's number in reading order, outermost first — the
    number the hash is keyed on, so an edit before a group moves its choice
    and an edit after it does not.
    """
    start: int
    end: int
    alternatives: list = field(default_factory=list)
    index: int = -1


def parse(text):
    """Text -> parts, each a `str` or a `Group` (numbered in reading order)."""
    text = str(text or "")
    root = []
    # Open brace pairs, innermost last. Each holds the offset of its `{` and the
    # alternatives read so far — a single alternative until a bar arrives.
    stack = []

    def parts():
        return stack[-1]["alternatives"][-1] if stack else root

    buffer = []

    def flush():
        if buffer:
            parts().append("".join(buffer))
            buffer.clear()

    def literal(frame):
        """A brace pair that was not a group after all, put back as typed."""
        alternatives = frame["alternatives"]
        target = parts()
        target.append("{")
        for number, alternative in enumerate(alternatives):
            if number:
                target.append("|")
            target.extend(alternative)

    for offset, char in enumerate(text):
        if char == "{":
            flush()
            stack.append({"start": offset, "alternatives": [[]]})
        elif char == "|" and stack:
            flush()
            stack[-1]["alternatives"].append([])
        elif char == "}" and stack:
            flush()
            frame = stack.pop()
            if len(frame["alternatives"]) == 1:
                literal(frame)
                parts().append("}")
            else:
                parts().append(Group(frame["start"], offset + 1, frame["alternatives"]))
        else:
            buffer.append(char)
    flush()
    # Whatever is still open was never a group: `{a|b` is those four
    # characters. Unwound innermost first, so each lands in its parent.
    while stack:
        literal(stack.pop())
    _number(root, [0])
    return root


def _number(parts, counter):
    for part in parts:
        if isinstance(part, Group):
            part.index = counter[0]
            counter[0] += 1
            for alternative in part.alternatives:
                _number(alternative, counter)


def _fnv1a(data):
    value = 0x811C9DC5
    for byte in data:
        value = ((value ^ byte) * 0x01000193) & 0xFFFFFFFF
    return value


def _fmix(value):
    """MurmurHash3's finaliser: FNV alone leaves the low bits of short keys
    too alike for `% n` to be fair, and the low bits are the ones taken."""
    value ^= value >> 16
    value = (value * 0x85EBCA6B) & 0xFFFFFFFF
    value ^= value >> 13
    value = (value * 0xC2B2AE35) & 0xFFFFFFFF
    value ^= value >> 16
    return value


def choose(seed, card, index, count):
    """Which of `count` alternatives group `index` takes, on `card` under `seed`.

    `card` is the card's number on the strip, or `"piece"` for the piece's own
    fields — so two cards holding the same sentence choose differently, and a
    card's choice does not move when another card is held back from the render.
    The key is spelled as text on both sides of the mirror, which is what keeps
    a 64-bit seed from meaning two things in two number systems.
    """
    key = f"{seed}:{card}:{index}".encode("utf-8")
    return _fmix(_fnv1a(key)) % count


def _write(parts, seed, card, out):
    for part in parts:
        if isinstance(part, Group):
            taken = choose(seed, card, part.index, len(part.alternatives))
            _write(part.alternatives[taken], seed, card, out)
        else:
            out.append(part)


def resolve(text, seed, card):
    """The text with every choice made. Text with no group comes back as is."""
    text = str(text or "")
    if "{" not in text:
        return text
    out = []
    _write(parse(text), seed, card, out)
    return "".join(out)


def has_groups(text):
    """Cheap answer to "is there anything here to choose"."""
    return bool(text) and "{" in text and any(
        isinstance(part, Group) for part in parse(text))


def shapes(text):
    """Every group in the text, in reading order, as (source, alternatives).

    The refiner's check reads this off both the request and the rewrite: a
    group survives a rewrite when a group offering the same number of
    alternatives is still there. Its words may have grown — that is what
    refining is for — so the count is the one thing that can be compared.
    """
    text = str(text or "")
    found = []

    def walk(parts):
        for part in parts:
            if isinstance(part, Group):
                found.append((text[part.start:part.end], len(part.alternatives)))
                for alternative in part.alternatives:
                    walk(alternative)

    walk(parse(text))
    return found


def vary_mapping(mapping, seed, card, keys=("prompt", "soundscape", "music")):
    """A request-shaped dict with its prose fields chosen, or the same dict.

    Only a field holding a group is rewritten, and a dict holding none comes
    back as the object it was: a request is the segment node's cache key, and
    a sentence with nothing to choose has to compile to the bytes it always did.
    The refiner's prose is a prompt too — `compile.refined_body` stands it in
    for the sentence — so its body and sections are chosen the same way.
    """
    if not isinstance(mapping, dict):
        return mapping
    out = None
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and has_groups(value):
            out = out if out is not None else dict(mapping)
            out[key] = resolve(value, seed, card)
    refined = mapping.get("refined")
    if isinstance(refined, dict):
        chosen = vary_mapping(refined, seed, card, keys=("body",))
        sections = refined.get("sections")
        if isinstance(sections, dict):
            written = vary_mapping(sections, seed, card, keys=tuple(sections))
            if written is not sections:
                chosen = chosen if chosen is not refined else dict(refined)
                chosen["sections"] = written
        if chosen is not refined:
            out = out if out is not None else dict(mapping)
            out["refined"] = chosen
    return out if out is not None else mapping


def _texts(mapping, keys):
    out = [str(mapping.get(key) or "") for key in keys]
    refined = mapping.get("refined")
    if isinstance(refined, dict):
        out.append(str(refined.get("body") or ""))
        sections = refined.get("sections")
        if isinstance(sections, dict):
            out.extend(str(text or "") for text in sections.values())
    return out


def passed_over(raw, varied, pattern, keys=("prompt", "soundscape", "music")):
    """Handles the request wrote that the choice left out, as a set.

    `@img-1` inside an alternative the seed passed over is a file the user put
    in the sentence and the render is not going to mention — and a file that is
    attached and unmentioned is still encoded and shown to the model, which
    conditions the shot exactly as hard as one the prompt names. So the caller
    mutes these for this render. Only what was written and lost: a file the
    sentence never named is the user's to keep attached, as it always was.
    `pattern` is the handle grammar (`compile.HANDLE_RE`), with the handle in
    group 1.
    """
    before = set()
    for text in _texts(raw, keys):
        before.update(pattern.findall(text))
    after = set()
    for text in _texts(varied, keys):
        after.update(pattern.findall(text))
    return before - after

"""The LoRA library as Stagehand reads it: searched, named, and described.

The manager browses a folder at a time, newest first, and that is the wrong
shape for a model that was asked for "something for rain at night": it needs
the whole library searched by what the files are about, a short line for each
hit, and one LoRA described in words when it wants to know more.

Everything here is pure over the rows `lorameta.row` builds and the record
`lorameta.detail` returns, so it is tested without a disk. The route reads the
rows; this only ranks, resolves and words them.
"""

import html
import html.parser
import re

# How many hits a search answers with, and at most. Each is one line in a
# conversation that is sent whole on every exchange.
DEFAULT_HITS = 12
MOST_HITS = 40
# A list inside a hit or a description: enough to tell the file by, no more.
MOST_WORDS = 8
MOST_TAGS = 8
# A description is a Civitai page more often than not: long, and mostly about
# itself. This much is what it is for.
MOST_ABOUT = 1800

# Where a word was found, and what it is worth there: the file's own name and
# title say what it is, its trigger words and tags say what it does, and its
# base model and folder say where it belongs.
WEIGHTS = (
    (("base", "card_title", "title"), 3),
    (("trained_words", "tags"), 2),
    (("name", "folder", "base_model", "type", "version", "card_subtitle"), 1),
)

_WORD = re.compile(r"[\w]+", re.UNICODE)


def words_of(text):
    """The words of a query, lowercased: what is searched for."""
    return [word for word in _WORD.findall(str(text or "").lower()) if len(word) > 1 or word.isdigit()]


def _haystack(value):
    if isinstance(value, (list, tuple)):
        return " ".join(str(item) for item in value if item).lower()
    return str(value or "").lower()


def _fits(row, base, folder):
    if base and base.lower() not in _haystack(row.get("base_model")):
        return False
    if folder and not (row.get("name") or "").startswith(folder.rstrip("/") + "/"):
        return False
    return True


def score(row, query_words):
    """`(words matched, points)`: how many of the query's words the row has
    somewhere, then how well placed they are. (0, 0) is no match."""
    fields = [(" ".join(_haystack(row.get(key)) for key in keys), weight) for keys, weight in WEIGHTS]
    # The name's separators are spaces to a reader: `neon_rain_v2` is about rain.
    fields = [(re.sub(r"[_\-./]+", " ", text), weight) for text, weight in fields]
    matched = points = 0
    for word in query_words:
        best = 0
        for text, weight in fields:
            if re.search(r"(?<![a-z0-9])" + re.escape(word), text):
                best = max(best, weight)
        if best:
            matched += 1
            points += best
    return matched, points


def search(rows, query="", base="", folder="", limit=DEFAULT_HITS):
    """The rows that fit, best first. -> `{hits, matched}`.

    A query matches a row that has any of its words; one that has more of them
    comes first, then one that has them in its name or title. With no query,
    every row that fits the base model and folder does, newest first.
    """
    limit = max(1, min(int(limit or DEFAULT_HITS), MOST_HITS))
    wanted = words_of(query)
    found = []
    for row in rows:
        if not _fits(row, base, folder):
            continue
        if not wanted:
            found.append(((0, 0, row.get("mtime") or 0), row))
            continue
        matched, points = score(row, wanted)
        if matched:
            found.append(((matched, points, row.get("mtime") or 0), row))
    found.sort(key=lambda pair: pair[0], reverse=True)
    return {"hits": [hit(row) for _, row in found[:limit]], "matched": len(found)}


def _listed(value, most):
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()][:most]


def hit(row):
    """A row as a hit: what tells one file from another, and nothing more."""
    out = {
        "name": row.get("name"),
        "title": row.get("title") or row.get("card_title") or row.get("base"),
        "base_model": row.get("base_model") or None,
        "type": row.get("type") or None,
        "trained_words": _listed(row.get("trained_words"), MOST_WORDS),
        "tags": _listed(row.get("tags"), MOST_TAGS),
        "strength": row.get("strength") if isinstance(row.get("strength"), (int, float)) else None,
    }
    if row.get("nsfw"):
        out["nsfw"] = True
    return out


def resolve(rows, given):
    """The one row `given` names. -> `(row, others)`: the row or None, and
    when it is None the names it could have meant.

    A model names a file the way it was shown it, mostly; but it also drops the
    folder, the extension or the case, or gives the title. Each is tried in
    that order, and a guess that fits two files is not a guess it is given.
    """
    given = str(given or "").strip().replace("\\", "/")
    if not given:
        return None, []
    lower = given.lower()
    stem = re.sub(r"\.(safetensors|ckpt|pt|bin)$", "", lower)
    tries = (
        lambda row: row.get("name") == given,
        lambda row: (row.get("name") or "").lower() == lower,
        lambda row: re.sub(r"\.(safetensors|ckpt|pt|bin)$", "", (row.get("name") or "").lower()) == stem,
        lambda row: (row.get("base") or "").lower() == stem.rsplit("/", 1)[-1],
        lambda row: (row.get("title") or "").lower() == lower or (row.get("card_title") or "").lower() == lower,
    )
    for test in tries:
        found = [row for row in rows if test(row)]
        if len(found) == 1:
            return found[0], []
        if len(found) > 1:
            return None, [row.get("name") for row in found[:MOST_HITS]]
    near = search(rows, stem, limit=5)["hits"]
    return None, [item["name"] for item in near]


class _Text(html.parser.HTMLParser):
    """A description's words, with its paragraphs and list items kept apart."""

    BREAKS = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "ul", "ol", "blockquote", "pre"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in self.BREAKS:
            self.parts.append("\n")
            if tag == "li":
                self.parts.append("- ")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BREAKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def plain(markup, most=MOST_ABOUT):
    """A description as words: its markup dropped, its blank lines folded, and
    cut at `most` characters on a word."""
    if not markup:
        return ""
    reader = _Text()
    try:
        reader.feed(str(markup))
        reader.close()
        text = "".join(reader.parts)
    except Exception:  # A page that is not HTML is read as the words it is.
        text = html.unescape(re.sub(r"<[^>]+>", " ", str(markup)))
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > most:
        text = text[:most].rsplit(" ", 1)[0].rstrip(",.;:") + " …"
    return text


def about(name, detail):
    """One LoRA described for a model, from `lorameta.detail`'s record."""
    meta = (detail or {}).get("meta") or {}
    out = {
        "name": name,
        "title": meta.get("title") or None,
        "version": meta.get("version") or None,
        "type": meta.get("type") or None,
        "base_model": meta.get("base_model") or None,
        "trained_words": _listed(meta.get("trained_words"), 24),
        "tags": _listed(meta.get("tags"), 16),
        "strength": meta.get("strength") if isinstance(meta.get("strength"), (int, float)) else None,
        "notes": plain(meta.get("notes"), 1200) or None,
        "description": plain(meta.get("description")) or None,
        "version_description": plain(meta.get("version_description"), 800) or None,
        "creator": meta.get("creator") if isinstance(meta.get("creator"), str) else None,
    }
    if meta.get("nsfw"):
        out["nsfw"] = True
    return {key: value for key, value in out.items() if value not in (None, [], "")}

"""Recover presentation groups from the saved source HTML, entirely offline.

The original catalog, detail JSON, translations and downloaded media are read
only. This supplemental index stores local media paths and known catalog IDs,
never executable HTML or outgoing URLs. Rebuild explicitly after vendoring.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit

from lxml import html

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cls(name):
    return "contains(concat(' ',normalize-space(@class),' '),' " + name + " ')"


def text(node):
    return re.sub(r"\s+", " ", node.text_content()).strip()


def resolve_technique(href, base, catalog):
    """Exact known HTTPS route only; no title/substring/filename guessing."""
    try:
        parsed = urlsplit(urljoin(base, href))
    except (ValueError, TypeError):
        return None
    if parsed.scheme != "https" or parsed.netloc != "melies.co" or parsed.username or parsed.password:
        return None
    # An explicit fragment-only URL is a section link, not self-navigation.
    if not isinstance(href, str) or not href or href.startswith("#"):
        return None
    path = parsed.path.rstrip("/")
    return catalog.get(path)


def semantic_nodes(section):
    """Keep the original extractor's block indices, including unusual FAQs."""
    for node in section.xpath(".//p|.//h3|.//h4|.//h5|.//h6|.//li|.//blockquote|.//pre|.//figcaption"):
        if any(parent.tag in {"li", "blockquote", "pre"} for parent in node.iterancestors() if parent is not section):
            continue
        if text(node):
            yield node


def inline_ranges(node, base, routes):
    """Normalize DOM text with link ownership, then emit JS UTF-16 offsets.

    Ranges apply only to exactly matching sourceText. Translated prose must use
    separate local navigation controls rather than guessed character offsets.
    """
    chars, owners, anchors = [], [], []

    def append(value, owner):
        if value:
            chars.extend(value)
            owners.extend([owner] * len(value))

    def walk(element, owner=None):
        if not isinstance(element.tag, str):
            return  # Ignore source framework comments, but parent keeps tails.
        if element.tag == "a":
            target = resolve_technique(element.get("href"), base, routes)
            if target:
                owner = len(anchors)
                anchors.append(target)
        append(element.text, owner)
        for child in element:
            walk(child, owner)
            append(child.tail, owner)

    walk(node)
    raw = "".join(chars)
    normalized, normalized_owners = [], []
    for match in re.finditer(r"\s+|\S+", raw):
        if match.group().isspace():
            distinct = set(owners[match.start():match.end()])
            normalized.append(" ")
            normalized_owners.append(next(iter(distinct)) if len(distinct) == 1 else None)
        else:
            normalized.extend(match.group())
            normalized_owners.extend(owners[match.start():match.end()])
    while normalized and normalized[0] == " ":
        normalized.pop(0)
        normalized_owners.pop(0)
    while normalized and normalized[-1] == " ":
        normalized.pop()
        normalized_owners.pop()
    source = "".join(normalized)
    assert source == text(node), "DOM normalization differs from the original extractor"
    ranges = []
    for owner, target in enumerate(anchors):
        positions = [index for index, value in enumerate(normalized_owners) if value == owner]
        if not positions:
            continue
        start, end = positions[0], positions[-1] + 1
        while start < end and source[start].isspace():
            start += 1
        while end > start and source[end - 1].isspace():
            end -= 1
        if start == end:
            continue
        ranges.append({"start": len(source[:start].encode("utf-16-le")) // 2,
                       "end": len(source[:end].encode("utf-16-le")) // 2,
                       "text": source[start:end], "targetId": target})
    return source, ranges


def local_media(element, source_url, detail_media):
    videos, images = element.xpath(".//video[@src]"), element.xpath(".//img[@src]")
    if len(videos) > 1 or len(images) > 1:
        raise ValueError("Unexpected multi-media card; explicit grouping required")
    if videos:
        video = videos[0]
        path = detail_media[urljoin(source_url, video.get("src"))]["path"]
        poster = urljoin(source_url, video.get("poster") or "")
        if len(images) != 1 or urljoin(source_url, images[0].get("src")) != poster:
            raise ValueError("Comparison video has no exact same-card poster/image pair")
        return {"kind": "video", "path": path, "poster": detail_media[poster]["path"],
                "alt": images[0].get("alt") or ""}
    if images:
        image = images[0]
        return {"kind": "image", "path": detail_media[urljoin(source_url, image.get("src"))]["path"],
                "alt": image.get("alt") or ""}
    return None


def presentation_media(doc, article, source_url, detail_media):
    """Distinguish actual article illustrations from CTA blur and OG metadata.

    A file may occur in both content and decorative chrome. Content always wins
    (notably the still thumbnail of an image-only technique). No filename-based
    pairing or deduction is permitted; future unknown source groups fail closed.
    """
    content, decorative, primary = set(), set(), {}
    roles = (("atmosphere-card", "decorative"), ("cinematic-shot", "primary"),
             ("cinematic-sheet__strip", "strip"), ("cinematic-sheet__cousin", "comparison"),
             ("cinematic-sheet__scene", "film"), ("cinematic-tile", "recommended"))
    for element in article.xpath(".//img[@src]|.//video[@src]"):
        classes = {token for ancestor in [element, *element.iterancestors()]
                   for token in (ancestor.get("class") or "").split()}
        role = next((role for name, role in roles if name in classes), None)
        if role is None:
            raise ValueError("Unknown article media group: " + source_url)
        # These source pages use src/poster only. Refuse silently losing a new
        # responsive or lazy source added to a later archive.
        if any(element.get(name) for name in ("srcset", "data-srcset", "data-src")):
            raise ValueError("New article media source attributes need classification")
        url = urljoin(source_url, element.get("src"))
        media = detail_media[url]
        target = decorative if role == "decorative" else content
        target.add(media["path"])
        if element.get("poster"):
            target.add(detail_media[urljoin(source_url, element.get("poster"))]["path"])
        if role == "primary":
            row = {"kind": "video" if element.tag == "video" else "image",
                   "path": media["path"], "alt": element.get("alt") or element.get("aria-label") or ""}
            if element.get("poster"):
                row["poster"] = detail_media[urljoin(source_url, element.get("poster"))]["path"]
            primary.setdefault(media["path"], row)  # Same source's fallback player.
    if article.xpath(".//source"):
        raise ValueError("New nested media source needs explicit classification")
    assert len(primary) == 1, (source_url, primary)
    metadata = {detail_media[urljoin(source_url, meta.get("content"))]["path"]
                for meta in doc.xpath("//meta[@property='og:image'][@content]")}
    paths = {media["path"] for media in detail_media.values()}
    unknown = paths - content - decorative - metadata
    assert not unknown, (source_url, "Unclassified detail media", unknown)
    excluded = [{"path": path, "reason": "decorative" if path in decorative else "metadata-only"}
                for path in sorted(paths - content)]
    return {"primary": next(iter(primary.values())), "articleMediaPaths": sorted(content),
            "excludedMedia": excluded}


def build_item(item, detail, source_path, routes):
    if digest(source_path) != detail["sourceHtmlSha256"]:
        raise ValueError("Stale source HTML: " + item["id"])
    doc = html.fromstring(source_path.read_bytes())
    articles = doc.xpath("//article[" + cls("cinematic-sheet") + "]")
    assert len(articles) == 1, item["id"]
    article = articles[0]
    media_by_url = {row["sourceUrl"]: row for row in detail["media"]}
    source_sections = article.xpath(".//*[" + cls("cinematic-sheet__copy") + "]/section")
    assert [section.get("id") for section in source_sections] == [section["id"] for section in detail["sections"]]
    result = {"sourceHtmlSha256": detail["sourceHtmlSha256"], "sections": {}}
    result.update(presentation_media(doc, article, item["sourceUrl"], media_by_url))
    comparison_ids = []
    for source_section, section in zip(source_sections, detail["sections"]):
        nodes = list(semantic_nodes(source_section))
        assert len(nodes) == len(section["blocks"]), (item["id"], section["id"])
        group = {"cards": [], "inlineLinks": []}
        result["sections"][section["id"]] = group
        for index, (node, block) in enumerate(zip(nodes, section["blocks"])):
            assert text(node) == block["text"], (item["id"], section["id"], index)
            if section["id"] == "prompt":
                continue  # Never reinterpret, translate or linkify prompt text.
            cousins = node.xpath(".//a[" + cls("cinematic-sheet__cousin") + "]")
            films = node.xpath(".//*[" + cls("cinematic-sheet__scene") + "]")
            cards = cousins or films
            if cards:
                assert len(cards) == 1 and block["type"] == "list-item"
                card = cards[0]
                copy_class = "cinematic-sheet__cousin-copy" if cousins else "cinematic-sheet__scene-copy"
                copy = card.xpath(".//*[" + cls(copy_class) + "]")
                assert len(copy) == 1
                pieces = [text(child) for child in copy[0] if isinstance(child.tag, str) and text(child)]
                assert len(pieces) >= 2 and "\n".join(pieces) == block["displayText"]
                row = {"kind": "technique" if cousins else "film", "blockIndex": index,
                       "title": pieces[0], "description": "\n".join(pieces[1:])}
                if cousins:
                    target = resolve_technique(card.get("href"), item["sourceUrl"], routes)
                    assert target, (item["id"], card.get("href"))
                    row["targetId"] = target
                    comparison_ids.append(target)
                media = local_media(card, item["sourceUrl"], media_by_url)
                if media:
                    row["media"] = media
                group["cards"].append(row)
            else:
                source, ranges = inline_ranges(node, item["sourceUrl"], routes)
                if ranges:
                    group["inlineLinks"].append({"blockIndex": index, "sourceText": source, "ranges": ranges})
    tiles = article.xpath(".//a[" + cls("cinematic-tile") + "]")
    recommended = [resolve_technique(tile.get("href"), item["sourceUrl"], routes) for tile in tiles]
    assert len(recommended) == 3 and all(recommended) and recommended == comparison_ids, item["id"]
    result["recommendedIds"] = recommended
    strips = article.xpath(".//figure[" + cls("cinematic-sheet__strip") + "]")
    assert len(strips) <= 1
    if strips:
        result["strip"] = local_media(strips[0], item["sourceUrl"], media_by_url)
    return result


def build(archive, data):
    catalog_path = data / "catalog.json"
    catalog = read(catalog_path)
    routes = {urlsplit(item["sourceUrl"]).path.rstrip("/"): item["id"] for item in catalog["items"]}
    assert len(routes) == len(catalog["items"]) == 424
    protected = [catalog_path, *(data / item["detail"] for item in catalog["items"])]
    protected.extend((data / "translations").rglob("*.json"))
    before = {path: digest(path) for path in protected}
    result = {"version": 1, "sourceCapturedAt": catalog["capturedAt"],
              "sourceCatalogSha256": before[catalog_path], "offsetEncoding": "utf16", "items": {}}
    for item in catalog["items"]:
        result["items"][item["id"]] = build_item(item, read(data / item["detail"]), archive / "articles" / (item["id"] + ".html"), routes)
    assert all(digest(path) == value for path, value in before.items()), "Original data changed during structure build"
    return result


def summarize(result):
    counts = Counter(articles=len(result["items"]))
    for item in result["items"].values():
        counts["frameStrips"] += bool(item.get("strip"))
        counts["primary" + item["primary"]["kind"].title()] += 1
        for excluded in item["excludedMedia"]:
            counts["excluded-" + excluded["reason"]] += 1
        for section in item["sections"].values():
            counts["inlineLinkedBlocks"] += len(section["inlineLinks"])
            counts["inlineLinks"] += sum(len(row["ranges"]) for row in section["inlineLinks"])
            for card in section["cards"]:
                counts[card["kind"] + "Cards"] += 1
                media = card.get("media", {})
                if card["kind"] == "technique":
                    counts["posterVideoPairs" if media.get("kind") == "video" else "imageOnlyTechniqueCards"] += 1
                elif media:
                    counts["filmImages"] += 1
    return dict(counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ROOT.parent / "technique-source-pages")
    parser.add_argument("--data", type=Path, default=ROOT / "web/creator/techniques")
    parser.add_argument("--output", type=Path, help="Defaults to DATA/structure.json; no network is used")
    args = parser.parse_args()
    output = args.output or args.data / "structure.json"
    result = build(args.archive, args.data)
    # Only the supplemental artifact is writable; forbid accidentally targeting
    # an original detail/catalog/translation or a downloaded media path.
    if output.resolve() != (args.data / "structure.json").resolve():
        raise SystemExit("Output must be the supplemental DATA/structure.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".json.part")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({**summarize(result), "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

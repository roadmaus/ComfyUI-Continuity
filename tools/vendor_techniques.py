"""Capture the complete, owner-authorized Melies technique catalogue for offline use.

The saved HTML is evidence only. Runtime JSON contains text, links and local media
paths, never executable source HTML. Restarting reuses complete atomic downloads.
"""
from __future__ import annotations

import argparse
from collections import Counter, OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request

from lxml import html

BASE = Path(__file__).resolve().parents[1]
# Cache/evidence stay outside the node, so source site HTML is not accidentally
# shipped or served as part of the frontend. All paths have explicit overrides.
SOURCE = BASE.parent / "technique-source-pages"
OUT = BASE / "web/creator/techniques"
EVIDENCE = BASE.parent / "technique-vendor-evidence"
SITE = "https://melies.co"
INDEX_URL = SITE + "/cinematic-techniques"
ALLOWED_HOSTS = {"melies.co", "asset.melies.co"}
HEADERS = {"User-Agent": "Continuity-Owner-Authorized-Catalogue-Archive/1.0", "Accept-Encoding": "identity"}


def text(node):
    return re.sub(r"\s+", " ", node.text_content()).strip()


def cls(name):
    return f"contains(concat(' ',normalize-space(@class),' '),' {name} ')"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_url(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"Unexpected media/page origin: {url}")
    return url


class CheckedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url, path, html_page=False):
    check_url(url)
    if path.is_file() and path.stat().st_size:
        return {"url": url, "bytes": path.stat().st_size, "sha256": sha(path), "cached": True}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    last = None
    for attempt in range(4):
        try:
            opener = urllib.request.build_opener(CheckedRedirect())
            with opener.open(urllib.request.Request(url, headers=HEADERS), timeout=75) as response:
                check_url(response.url)
                length = response.headers.get("Content-Length")
                content_type = response.headers.get("Content-Type", "")
                if not html_page and "text/html" in content_type:
                    raise ValueError("Media request returned HTML instead of media")
                with tmp.open("wb") as stream:
                    shutil.copyfileobj(response, stream, 1024 * 1024)
                if length and tmp.stat().st_size != int(length):
                    raise ValueError("Truncated HTTP body")
                if not tmp.stat().st_size:
                    raise ValueError("Empty HTTP body")
                tmp.replace(path)
                return {"url": url, "bytes": path.stat().st_size, "sha256": sha(path), "contentType": content_type}
        except Exception as exc:
            last = exc
            if attempt < 3:
                time.sleep(min(2 ** attempt, 8))
    return {"url": url, "error": f"{type(last).__name__}: {last}"}


def load_doc(path):
    # Explicit UTF-8 avoids lxml's ISO-8859-1 fallback corrupting typographic quotes.
    return html.fromstring(path.read_text(encoding="utf-8-sig"))


def inventory():
    doc = load_doc(SOURCE / "index.html")
    categories = OrderedDict()
    for anchor in doc.xpath("//a[@href]"):
        match = re.fullmatch(r"/cinematic-techniques/([a-z0-9][a-z0-9_-]*)", anchor.get("href"))
        if match and match[1] != "bookmarked":
            categories.setdefault(match[1], {"id": match[1], "title": text(anchor), "count": 0})
    items = OrderedDict()
    # The index includes a navigation inventory and tile inventory; tile metadata
    # wins because its image is the actual thumbnail shown in the source library.
    for anchor in doc.xpath("//a[@href]"):
        match = re.fullmatch(r"/cinematic-techniques/([a-z0-9][a-z0-9_-]*)/([a-z0-9][a-z0-9_-]*)", anchor.get("href"))
        if not match:
            continue
        cat, slug = match.groups()
        identity = cat + "/" + slug
        images = anchor.xpath(".//img[@src]")
        previous = items.get(identity, {})
        items[identity] = {
            "id": identity, "slug": slug, "title": text(anchor) or previous.get("title", slug),
            "categoryId": cat, "categoryTitle": categories[cat]["title"],
            "sourceUrl": SITE + anchor.get("href"),
            "thumbnailSourceUrl": images[0].get("src") if images else previous.get("thumbnailSourceUrl"),
            "detail": "details/" + identity + ".json",
        }
    for item in items.values():
        categories[item["categoryId"]]["count"] += 1
    assert len(items) == 424, f"Inventory changed: expected 424, got {len(items)}"
    assert len(categories) == 13, f"Inventory changed: expected 13 categories, got {len(categories)}"
    assert all(item.get("thumbnailSourceUrl") for item in items.values()), "Missing index thumbnail"
    return list(categories.values()), list(items.values())


def media_path(url):
    check_url(url)
    ext = Path(urllib.parse.urlsplit(url).path).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif", ".mp4", ".webm", ".mov", ".svg"}:
        raise ValueError(f"Unexpected media extension: {url}")
    return "media/" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:32] + ext


def collect_media(node, source_url, role=None):
    records = OrderedDict()
    for element in node.xpath(".//img|.//video|.//source"):
        kind = "video" if element.tag == "video" or element.getparent().tag == "video" else "image"
        candidates = [(element.get("src"), kind, role)]
        if element.get("poster"):
            candidates.append((element.get("poster"), "image", "poster"))
        for attr in ("srcset", "data-srcset"):
            if element.get(attr):
                candidates.extend((part.strip().split()[0], "image", role) for part in element.get(attr).split(",") if part.strip())
        if element.get("data-src"):
            candidates.append((element.get("data-src"), kind, role))
        for candidate, media_kind, media_role in candidates:
            if not candidate:
                continue
            url = urllib.parse.urljoin(source_url, candidate)
            record = {"kind": media_kind, "path": media_path(url), "sourceUrl": url,
                      "alt": element.get("alt") or element.get("aria-label") or ""}
            if media_role:
                record["role"] = media_role
            records.setdefault(url, record)
    return list(records.values())


def links(node, source_url):
    return [{"text": text(a), "url": urllib.parse.urljoin(source_url, a.get("href"))}
            for a in node.xpath(".//a[@href]") if text(a)]


def section_blocks(section):
    blocks = []
    for node in section.xpath(".//p|.//h3|.//h4|.//h5|.//h6|.//li|.//blockquote|.//pre|.//figcaption"):
        # One block per semantic unit, without duplicating text nested in list
        # cards/quotes. Labels and descriptions in film/related cards remain intact.
        if any(parent.tag in {"li", "blockquote", "pre"} for parent in node.iterancestors() if parent is not section):
            continue
        content = text(node)
        if not content:
            continue
        kind = "heading" if re.fullmatch(r"h[3-6]", node.tag) else "list-item" if node.tag == "li" else "quote" if node.tag in {"blockquote", "pre"} else "paragraph"
        block = {"type": kind, "text": content}
        if kind == "list-item":
            # The original CSS displays card title and description separately,
            # while DOM textContent concatenates adjacent spans. Keep that raw
            # text for source fidelity and add an explicitly presentational
            # counterpart for the native library's plain-text list renderer.
            card_copy = node.xpath(".//*[" + cls("cinematic-sheet__cousin-copy") + " or " + cls("cinematic-sheet__scene-copy") + "]")
            if card_copy:
                pieces = [text(child) for child in card_copy[0] if isinstance(child.tag, str) and text(child)]
                if len(pieces) > 1:
                    block["displayText"] = "\n".join(pieces)
        if kind == "heading":
            block["level"] = int(node.tag[1])
        local_links = links(node, "https://melies.co")
        if local_links:
            block["links"] = local_links
        blocks.append(block)
    return blocks


def parse_item(item):
    path = SOURCE / "articles" / (item["id"] + ".html")
    doc = load_doc(path)
    article = doc.xpath("//article[" + cls("cinematic-sheet") + "]")
    if len(article) != 1:
        raise ValueError(f"Expected one article for {item['id']}")
    article = article[0]
    title_nodes = article.xpath(".//h1")
    if len(title_nodes) != 1:
        raise ValueError(f"Missing title: {item['id']}")
    item = dict(item)
    item["title"] = text(title_nodes[0])
    aliases = article.xpath(".//*[" + cls("cinematic-sheet__also") + "]/*[" + cls("cinematic-tag") + "]")
    item["aliases"] = [text(node) for node in aliases]
    lede = article.xpath(".//*[" + cls("cinematic-sheet__lede") + "]")
    item["description"] = text(lede[0]) if lede else ""
    item["thumbnail"] = media_path(item["thumbnailSourceUrl"])
    primary_video = article.xpath(".//*[" + cls("cinematic-sheet__shot") + "]//video[@src]")
    item["video"] = media_path(primary_video[0].get("src")) if primary_video else None
    item["videoSourceUrl"] = primary_video[0].get("src") if primary_video else None
    all_media = OrderedDict((record["sourceUrl"], record) for record in collect_media(article, item["sourceUrl"]))
    thumbnail_url = item["thumbnailSourceUrl"]
    all_media.setdefault(thumbnail_url, {"kind": "image", "path": item["thumbnail"], "sourceUrl": thumbnail_url, "alt": item["title"], "role": "thumbnail"})
    for meta in doc.xpath("//meta[@property='og:image'][@content]"):
        url = urllib.parse.urljoin(item["sourceUrl"], meta.get("content"))
        # The source's JSON-LD has one malformed double-host URL; use the actual
        # og:image attribute rather than repairing/inventing media URLs.
        all_media.setdefault(url, {"kind": "image", "path": media_path(url), "sourceUrl": url, "alt": item["title"], "role": "hero"})
    sections = []
    for section in article.xpath(".//*[" + cls("cinematic-sheet__copy") + "]/section"):
        headings = section.xpath("./h2")
        sections.append({"id": section.get("id", ""), "title": text(headings[0]) if headings else "",
                         "blocks": section_blocks(section), "links": links(section, item["sourceUrl"]),
                         "media": collect_media(section, item["sourceUrl"]), "sourceText": text(section)})
    prompts = article.xpath(".//section[@id='prompt']")
    guidance = [text(node) for node in prompts[0].xpath("./p")] if prompts else []
    examples = article.xpath(".//pre[" + cls("cinematic-prompt__body") + "]")
    # text_content preserves deliberate line breaks in copy prompts. Do not
    # combine/deduplicate instructional paragraphs into the example prompt.
    example = examples[0].text_content() if examples else ""
    detail = {**item, "sections": sections, "prompt": {"guidance": guidance, "example": example},
              "media": list(all_media.values()), "relatedLinks": links(article.xpath(".//nav[" + cls("cinematic-sheet__see-also") + "]")[0], item["sourceUrl"]) if article.xpath(".//nav[" + cls("cinematic-sheet__see-also") + "]") else [],
              "sourceHtmlSha256": sha(path)}
    if not item["description"] or not sections or not guidance or not example:
        raise ValueError(f"Incomplete article content: {item['id']}")
    return item, detail


def run_pool(jobs, label, workers=4):
    results = []
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(download, url, path, is_html): url for url, path, is_html in jobs}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            if len(results) % 20 == 0 or len(results) == len(jobs) or result.get("error"):
                print(json.dumps({"phase": label, "done": len(results), "total": len(jobs),
                                  "failures": sum(bool(r.get('error')) for r in results),
                                  "MB": round(sum(r.get('bytes', 0) for r in results) / 1e6, 2),
                                  "seconds": round(time.monotonic() - started)}, ensure_ascii=False), flush=True)
    return results


def main():
    global SOURCE, OUT, EVIDENCE
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=SOURCE, help="HTML snapshot/cache directory (not shipped as runtime HTML)")
    parser.add_argument("--output", type=Path, default=OUT, help="Runtime catalogue directory: catalog.json, details/, media/")
    parser.add_argument("--evidence", type=Path, default=EVIDENCE, help="URL/hash inventories and capture validation reports")
    parser.add_argument("--pages-only", action="store_true")
    parser.add_argument("--offline", action="store_true", help="Reparse and validate cached captures without networking")
    args = parser.parse_args()
    SOURCE, OUT, EVIDENCE = args.archive.resolve(), args.output.resolve(), args.evidence.resolve()
    SOURCE.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    if not (SOURCE / "index.html").is_file():
        if args.offline:
            raise SystemExit("The offline archive is missing index.html.")
        result = download(INDEX_URL, SOURCE / "index.html", html_page=True)
        if result.get("error"):
            raise SystemExit(result["error"])
    categories, items = inventory()
    # The initial inspected page is reused, preserving its exact bytes.
    dolly = SOURCE / "articles/camera-movement/dolly-in.html"
    if not dolly.exists() and (SOURCE / "dolly-in.html").is_file():
        dolly.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / "dolly-in.html", dolly)
    jobs = [(item["sourceUrl"], SOURCE / "articles" / (item["id"] + ".html"), True) for item in items]
    if args.offline:
        assert all(path.is_file() for _, path, _ in jobs), "Missing captured article"
        page_results = [{"url": url, "bytes": path.stat().st_size, "sha256": sha(path), "cached": True} for url, path, _ in jobs]
    else:
        page_results = run_pool(jobs, "articles")
    write_json(EVIDENCE / "technique-page-manifest.json", sorted(page_results, key=lambda r: r["url"]))
    if any(result.get("error") for result in page_results):
        raise SystemExit("One or more articles failed; no complete catalogue claimed. Restart to retry.")
    details = []
    media = OrderedDict()
    for original in items:
        item, detail = parse_item(original)
        details.append(detail)
        for record in detail["media"]:
            entry = media.setdefault(record["sourceUrl"], {**record, "usedBy": []})
            if item["id"] not in entry["usedBy"]:
                entry["usedBy"].append(item["id"])
        write_json(OUT / item["detail"], detail)
    catalog_items = [{key: value for key, value in detail.items() if key not in {"sections", "prompt", "media", "relatedLinks", "sourceHtmlSha256"}} for detail in details]
    captured_at = datetime.now(timezone.utc).isoformat()
    if args.offline and (OUT / "catalog.json").is_file():
        captured_at = json.loads((OUT / "catalog.json").read_text(encoding="utf-8")).get("capturedAt", captured_at)
    catalog = {"version": 1, "sourceUrl": INDEX_URL, "capturedAt": captured_at, "categories": categories, "items": catalog_items}
    write_json(OUT / "catalog.json", catalog)
    write_json(EVIDENCE / "technique-media-inventory.json", list(media.values()))
    print(json.dumps({"phase": "parsed", "items": len(details), "categories": len(categories), "media": len(media),
                      "sections": dict(Counter(section["id"] for detail in details for section in detail["sections"]))}), flush=True)
    if args.pages_only:
        return
    if args.offline:
        media_results = []
        for url, record in media.items():
            path = OUT / record["path"]
            media_results.append({"url": url, "bytes": path.stat().st_size, "sha256": sha(path), "cached": True} if path.is_file() else {"url": url, "error": "Missing offline media file"})
    else:
        media_results = run_pool([(url, OUT / record["path"], False) for url, record in media.items()], "media")
    by_url = {result["url"]: result for result in media_results}
    manifest = [{**record, **by_url[url]} for url, record in media.items()]
    write_json(EVIDENCE / "technique-media-manifest.json", manifest)
    write_json(OUT / "manifest.json", {"version": 1, "sourceUrl": INDEX_URL, "capturedAt": catalog["capturedAt"], "media": manifest})
    failures = [record for record in manifest if record.get("error")]
    summary = {"sourceUrl": INDEX_URL, "capturedAt": catalog["capturedAt"], "indexSha256": sha(SOURCE / "index.html"),
               "items": len(details), "categories": categories, "htmlPages": len(page_results),
               "mediaFiles": len(manifest) - len(failures), "mediaTotal": len(manifest),
               "mediaBytes": sum(record.get("bytes", 0) for record in manifest), "failures": failures,
               "sectionCount": sum(len(detail["sections"]) for detail in details),
               "promptExamples": sum(bool(detail["prompt"]["example"]) for detail in details),
               "videos": sum(record["kind"] == "video" for record in manifest)}
    write_json(EVIDENCE / "technique-extraction-summary.json", summary)
    print(json.dumps({"phase": "complete" if not failures else "incomplete", **{k: v for k, v in summary.items() if k not in {"categories", "failures"}}, "failures": len(failures)}), flush=True)
    if failures:
        raise SystemExit("Media failures recorded; restart to retry before claiming complete offline capture.")


if __name__ == "__main__":
    main()

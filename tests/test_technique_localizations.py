"""Offline completeness/source-isolation checks, not a native-language quality claim.

Run with unittest discovery. There is deliberately no partial-data escape hatch:
shipping only the proof pages must fail rather than silently rely on English
fallback for the rest of the catalog. The validator itself is exercised against
broken fixtures so duplicate indices and translated prompt content cannot pass.
"""
from copy import deepcopy
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1] / "web/creator/techniques"
LOCALES = ("ko", "ja", "zh")
MARKER = re.compile(r"ZXQ[TFE]\s*\d+\s*QXZ", re.I)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def text(value, label):
    require(isinstance(value, str) and bool(value.strip()), f"{label}: missing text")
    require(not MARKER.search(value), f"{label}: translation token leaked")


def indexed(rows, expected, fields, label):
    require(isinstance(rows, list), f"{label}: expected list")
    require(all(isinstance(row, dict) and set(row) == fields for row in rows),
            f"{label}: unexpected keys (source/prompt fields must not enter overlays)")
    ids = [row["index"] for row in rows]
    require(all(type(index) is int for index in ids), f"{label}: non-integer index")
    require(len(ids) == len(set(ids)), f"{label}: duplicate indices")
    require(set(ids) == set(expected), f"{label}: missing or out-of-range indices")
    return {row["index"]: row for row in rows}


def media_rows(translated, source, label):
    expected = [index for index, item in enumerate(source) if item.get("alt")]
    mapped = indexed(translated, expected, {"index", "alt"}, label)
    for index, row in mapped.items():
        text(row["alt"], f"{label}/{index}")
    return len(mapped)


def validate_detail(source, local, locale):
    label = f"{locale}/{source['id']}"
    require(set(local) == {"version", "locale", "id", "sourceHtmlSha256", "description", "sections", "media"},
            f"{label}: unexpected top-level keys; titles, aliases, media paths and prompts remain source-owned")
    require(local["version"] == 1 and local["locale"] == locale and local["id"] == source["id"],
            f"{label}: wrong version/locale/id")
    require(local["sourceHtmlSha256"] == source["sourceHtmlSha256"], f"{label}: stale source hash")
    text(local["description"], f"{label}/description")
    sections = local["sections"]
    require(isinstance(sections, list), f"{label}: sections not a list")
    require(all(isinstance(section, dict) and set(section) == {"id", "title", "blocks", "media"}
                for section in sections), f"{label}: invalid section schema")
    ids = [section["id"] for section in sections]
    require(len(ids) == len(set(ids)), f"{label}: duplicate section ids")
    require(ids == [section["id"] for section in source["sections"]], f"{label}: missing/reordered sections")
    block_count, alt_count = 0, 0
    for original, translated in zip(source["sections"], sections):
        section_label = f"{label}/{original['id']}"
        text(translated["title"], f"{section_label}/title")
        if original["id"] == "prompt":
            require(translated["blocks"] == [] and translated["media"] == [],
                    f"{section_label}: original English prompt must never be translated")
            continue
        expected = [index for index, block in enumerate(original.get("blocks", []))
                    if block.get("displayText", block.get("text", ""))]
        mapped = indexed(translated["blocks"], expected, {"index", "text"}, section_label)
        for index, row in mapped.items():
            text(row["text"], f"{section_label}/{index}")
        block_count += len(mapped)
        alt_count += media_rows(translated["media"], original.get("media", []), f"{section_label}/media")
    alt_count += media_rows(local["media"], source.get("media", []), f"{label}/media")
    return {"blocks": block_count, "alts": alt_count}


def validate_catalog(source, local, locale):
    require(set(local) == {"version", "locale", "sourceCapturedAt", "items"}, f"{locale}: unexpected catalog keys")
    require(local["version"] == 1 and local["locale"] == locale, f"{locale}: catalog identity")
    require(local["sourceCapturedAt"] == source["capturedAt"], f"{locale}: wrong source capture")
    expected = {item["id"] for item in source["items"]}
    require(set(local["items"]) == expected, f"{locale}: incomplete catalog (English fallback is not coverage)")
    for key, item in local["items"].items():
        require(set(item) == {"description"}, f"{locale}/{key}: catalog may only overlay description")
        text(item["description"], f"{locale}/{key}/description")


class TechniqueLocalizationCorpusTests(unittest.TestCase):
    def test_all_424_entries_have_complete_source_bound_overlays_in_all_three_locales(self):
        catalog = read(ROOT / "catalog.json")
        self.assertEqual(len(catalog["items"]), 424)
        self.assertEqual(len({item["id"] for item in catalog["items"]}), 424)
        for locale in LOCALES:
            with self.subTest(locale=locale):
                base = ROOT / "translations" / locale
                local_catalog = read(base / "catalog.json")
                validate_catalog(catalog, local_catalog, locale)
                expected_paths = {item["detail"] for item in catalog["items"]}
                actual_paths = {path.relative_to(base).as_posix() for path in (base / "details").rglob("*.json")}
                self.assertEqual(actual_paths, expected_paths, f"{locale}: missing/unexpected detail pages")
                for item in catalog["items"]:
                    with self.subTest(id=item["id"]):
                        source, local = read(ROOT / item["detail"]), read(base / item["detail"])
                        validate_detail(source, local, locale)
                        self.assertEqual(local_catalog["items"][item["id"]]["description"], local["description"])

    def test_original_copy_prompts_and_guidance_match_source_section_blocks(self):
        # Localization must not modify the English source. Root also compares
        # pre/post hashes; this checks internal source prompt ownership offline.
        catalog = read(ROOT / "catalog.json")
        for item in catalog["items"]:
            with self.subTest(id=item["id"]):
                source = read(ROOT / item["detail"])
                prompt_section = next(section for section in source["sections"] if section["id"] == "prompt")
                blocks = prompt_section["blocks"]
                self.assertEqual(source["prompt"]["example"], next(block["text"] for block in blocks if block["type"] == "quote"))
                self.assertEqual(source["prompt"]["guidance"], [block["text"] for block in blocks if block["type"] == "paragraph"])
                self.assertFalse(re.search(r"[가-힣ぁ-ゖァ-ヺ]", source["prompt"]["example"]))
                for section in source["sections"]:
                    for link in section.get("links", []):
                        text(link.get("text"), f"{item['id']}: source link label")
                        self.assertTrue(link.get("url", "").startswith("https://"))


class TechniqueLocalizationValidatorTests(unittest.TestCase):
    def setUp(self):
        self.source = {"id": "test/item", "sourceHtmlSha256": "f" * 64,
                       "sections": [{"id": "how", "blocks": [{"text": "How"}], "media": [{"alt": "Technique name"}]},
                                    {"id": "prompt", "blocks": [{"text": "English prompt"}], "media": []}],
                       "media": [{"alt": ""}, {"alt": "Film 1984"}]}
        self.local = {"version": 1, "locale": "ko", "id": "test/item", "sourceHtmlSha256": "f" * 64,
                      "description": "설명", "sections": [
                          {"id": "how", "title": "사용법", "blocks": [{"index": 0, "text": "사용법 설명"}], "media": [{"index": 0, "alt": "Technique name"}]},
                          {"id": "prompt", "title": "영문 프롬프트", "blocks": [], "media": []}],
                      "media": [{"index": 1, "alt": "Film 1984"}]}

    def test_complete_fixture_accepts_canonical_english_names(self):
        self.assertEqual(validate_detail(self.source, self.local, "ko"), {"blocks": 1, "alts": 2})

    def test_duplicate_and_missing_indices_are_rejected(self):
        for rows in ([], [{"index": 1, "text": "잘못된 위치"}], [{"index": 0, "text": "중복"}] * 2):
            with self.subTest(rows=rows), self.assertRaises(AssertionError):
                local = deepcopy(self.local)
                local["sections"][0]["blocks"] = rows
                validate_detail(self.source, local, "ko")

    def test_prompt_content_and_top_level_prompt_or_title_are_rejected(self):
        for field in ("prompt", "title", "aliases"):
            with self.subTest(field=field), self.assertRaises(AssertionError):
                local = deepcopy(self.local)
                local[field] = "must stay English"
                validate_detail(self.source, local, "ko")
        self.local["sections"][1]["blocks"] = [{"index": 0, "text": "번역된 프롬프트"}]
        with self.assertRaisesRegex(AssertionError, "must never be translated"):
            validate_detail(self.source, self.local, "ko")

    def test_stale_source_blank_text_and_leaked_tokens_are_rejected(self):
        for field, value in (("sourceHtmlSha256", "0" * 64), ("description", " "), ("description", "ZXQT000001QXZ")):
            with self.subTest(field=field), self.assertRaises(AssertionError):
                local = deepcopy(self.local)
                local[field] = value
                validate_detail(self.source, local, "ko")

    def test_duplicate_media_and_sections_are_rejected(self):
        for field in ("media", "sections"):
            with self.subTest(field=field), self.assertRaises(AssertionError):
                local = deepcopy(self.local)
                local[field].append(deepcopy(local[field][0]))
                validate_detail(self.source, local, "ko")

    def test_partial_catalog_cannot_pass_as_fallback_coverage(self):
        source = {"capturedAt": "capture", "items": [{"id": "one"}, {"id": "two"}]}
        local = {"version": 1, "locale": "ko", "sourceCapturedAt": "capture", "items": {"one": {"description": "설명"}}}
        with self.assertRaisesRegex(AssertionError, "incomplete catalog"):
            validate_catalog(source, local, "ko")


if __name__ == "__main__":
    unittest.main()

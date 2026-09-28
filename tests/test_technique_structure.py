"""Supplemental grouping fidelity and local navigation, without network/GPU.

Corpus checks use the packaged JSON and media only. Optional lxml checks exercise
the offline maintenance helper; no saved HTML archive is required for this test.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "web/creator/techniques"
try:
    from lxml import html
except ImportError:
    html = None


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def js_slice(value, start, end):
    return value.encode("utf-16-le")[start * 2:end * 2].decode("utf-16-le")


class TechniqueStructureCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = read(DATA / "catalog.json")
        cls.items = {item["id"]: item for item in cls.catalog["items"]}
        cls.structure = read(DATA / "structure.json")

    def media_check(self, media):
        self.assertIn(media["kind"], ("image", "video"))
        for key in ("path", "poster"):
            if key in media:
                self.assertRegex(media[key], r"^media/[a-f0-9]{32}\.[a-z0-9]+$")
                self.assertTrue((DATA / media[key]).is_file())
        self.assertIn("alt", media)

    def test_all_424_records_are_bound_to_unchanged_source_data(self):
        self.assertEqual(self.structure["version"], 1)
        self.assertEqual(self.structure["offsetEncoding"], "utf16")
        self.assertEqual(self.structure["sourceCapturedAt"], self.catalog["capturedAt"])
        self.assertEqual(self.structure["sourceCatalogSha256"], hashlib.sha256((DATA / "catalog.json").read_bytes()).hexdigest())
        self.assertEqual(set(self.structure["items"]), set(self.items))
        self.assertEqual(len(self.items), 424)
        for identity, entry in self.structure["items"].items():
            with self.subTest(id=identity):
                original = read(DATA / self.items[identity]["detail"])
                self.assertEqual(entry["sourceHtmlSha256"], original["sourceHtmlSha256"])
                self.assertEqual(list(entry["sections"]), [section["id"] for section in original["sections"]])
                self.assertEqual(entry["sections"]["prompt"], {"cards": [], "inlineLinks": []})

    def test_all_cards_keep_source_block_indices_media_and_internal_targets(self):
        counts = dict(technique=0, film=0, video=0, image=0, film_images=0, strips=0)
        for identity, entry in self.structure["items"].items():
            original = read(DATA / self.items[identity]["detail"])
            sections = {section["id"]: section for section in original["sections"]}
            for section_id, group in entry["sections"].items():
                seen = set()
                for card in group["cards"]:
                    with self.subTest(id=identity, section=section_id, index=card["blockIndex"]):
                        self.assertNotIn(card["blockIndex"], seen)
                        seen.add(card["blockIndex"])
                        block = sections[section_id]["blocks"][card["blockIndex"]]
                        self.assertEqual(block["type"], "list-item")
                        self.assertEqual(card["title"] + "\n" + card["description"], block["displayText"])
                        counts[card["kind"]] += 1
                        if card["kind"] == "technique":
                            self.assertEqual(section_id, "vs")
                            target = self.items[card["targetId"]]
                            # Source comparison labels may omit an abbreviation
                            # present in the catalog (e.g. Close-Up vs (CU)).
                            # Routing is bound to the href/ID, never the label.
                            self.assertTrue(card["title"])
                            media = card["media"]
                            self.media_check(media)
                            counts[media["kind"]] += 1
                            if media["kind"] == "video":
                                self.assertEqual(media["path"], target["video"])
                                self.assertEqual(media["poster"], target["thumbnail"])
                            else:
                                self.assertEqual(media["path"], target["thumbnail"])
                                self.assertNotIn("poster", media)
                        else:
                            self.assertEqual(section_id, "examples-film")
                            self.assertNotIn("targetId", card)
                            if "media" in card:
                                counts["film_images"] += 1
                                self.media_check(card["media"])
                                self.assertEqual(card["media"]["kind"], "image")
                section_paths = {media["path"] for media in sections[section_id]["media"]}
                for card in group["cards"]:
                    if "media" in card:
                        self.assertIn(card["media"]["path"], section_paths)
                        if "poster" in card["media"]:
                            self.assertIn(card["media"]["poster"], section_paths)
            self.assertEqual(entry["recommendedIds"], [card["targetId"] for card in entry["sections"]["vs"]["cards"]])
            self.assertEqual(len(entry["recommendedIds"]), 3)
            if "strip" in entry:
                counts["strips"] += 1
                self.media_check(entry["strip"])
                self.assertIn(entry["strip"]["path"], {media["path"] for media in original["media"]})
        self.assertEqual(counts, dict(technique=1272, film=353, video=739, image=533, film_images=166, strips=250))

    def test_every_inline_span_matches_the_exact_source_utf16_substring(self):
        blocks, links = 0, 0
        for identity, entry in self.structure["items"].items():
            original = read(DATA / self.items[identity]["detail"])
            sections = {section["id"]: section for section in original["sections"]}
            for section_id, group in entry["sections"].items():
                card_indices = {card["blockIndex"] for card in group["cards"]}
                for row in group["inlineLinks"]:
                    self.assertNotIn(row["blockIndex"], card_indices)
                    self.assertEqual(row["sourceText"], sections[section_id]["blocks"][row["blockIndex"]]["text"])
                    previous_end = 0
                    blocks += 1
                    for span in row["ranges"]:
                        self.assertGreaterEqual(span["start"], previous_end)
                        self.assertGreater(span["end"], span["start"])
                        self.assertEqual(js_slice(row["sourceText"], span["start"], span["end"]), span["text"])
                        self.assertIn(span["targetId"], self.items)
                        previous_end = span["end"]
                        links += 1
        self.assertEqual((blocks, links), (1599, 2468))

    def test_article_media_allowlist_preserves_content_and_excludes_only_chrome(self):
        counts = dict(video=0, image=0, decorative=0, metadata=0)
        for identity, entry in self.structure["items"].items():
            with self.subTest(id=identity):
                original = read(DATA / self.items[identity]["detail"])
                allowed = set(entry["articleMediaPaths"])
                excluded = {row["path"] for row in entry["excludedMedia"]}
                all_paths = {row["path"] for row in original["media"]}
                self.assertFalse(allowed & excluded)
                self.assertEqual(allowed | excluded, all_paths)
                self.assertEqual(len(allowed), len(entry["articleMediaPaths"]))
                self.assertEqual(len(excluded), len(entry["excludedMedia"]))
                primary = entry["primary"]
                self.media_check(primary)
                self.assertIn(primary["path"], allowed)
                self.assertNotIn("poster", primary)  # None in these 424 source heroes.
                counts[primary["kind"]] += 1
                expected_primary = original["video"] or original["thumbnail"]
                self.assertEqual(primary["path"], expected_primary)
                for section in original["sections"]:
                    self.assertTrue({row["path"] for row in section["media"]} <= allowed)
                if "strip" in entry:
                    self.assertIn(entry["strip"]["path"], allowed)
                for row in entry["excludedMedia"]:
                    self.assertIn(row["reason"], ("decorative", "metadata-only"))
                    if row["reason"] == "decorative":
                        counts["decorative"] += 1
                        self.assertEqual(row["path"], original["thumbnail"])
                        self.assertEqual(primary["kind"], "video")
                    else:
                        counts["metadata"] += 1
                        source = next(media for media in original["media"] if media["path"] == row["path"])
                        self.assertEqual(source.get("role"), "hero")
        self.assertEqual(counts, dict(video=250, image=174, decorative=250, metadata=424))

    def test_orbit_fixture_deduplicates_posters_without_dropping_genuine_stills(self):
        item = self.structure["items"]["camera-movement/orbit-360"]
        comparison = item["sections"]["vs"]["cards"]
        self.assertEqual([card["targetId"] for card in comparison],
                         ["camera-movement/arc-left", "camera-movement/arc-right", "camera-movement/lazy-susan"])
        self.assertTrue(all(card["media"]["kind"] == "video" for card in comparison))
        self.assertEqual(comparison[1]["media"]["poster"], "media/627c7500d384beb2260120a87573cbff.webp")
        films = item["sections"]["examples-film"]["cards"]
        self.assertEqual([card["title"] for card in films], ["The Matrix 1999", "Vertigo 1958"])
        self.assertTrue(all(card["media"]["kind"] == "image" for card in films))
        self.assertEqual(item["strip"]["path"], "media/162f0126a9bf65b574af148729712499.jpg")
        self.assertEqual(item["excludedMedia"], [
            {"path": "media/2f2cab182349bbb10bcff1dc3362aba7.jpg", "reason": "metadata-only"},
            {"path": "media/47bc776685220df85d188b6f61fd0d1f.webp", "reason": "decorative"},
        ])


@unittest.skipUnless(html is not None, "lxml is required only by the optional offline maintenance helper")
class TechniqueStructureHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("structure_under_test", ROOT / "tools/build_technique_structure.py")
        cls.helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.helper)
        cls.routes = {"/cinematic-techniques/camera-movement/arc-right": "camera-movement/arc-right"}
        cls.base = "https://melies.co/cinematic-techniques/camera-movement/orbit-360"

    def test_known_routes_resolve_without_external_navigation(self):
        for value in ("/cinematic-techniques/camera-movement/arc-right", "arc-right", "https://melies.co/cinematic-techniques/camera-movement/arc-right/?query=x#how"):
            self.assertEqual(self.helper.resolve_technique(value, self.base, self.routes), "camera-movement/arc-right")

    def test_external_generator_category_and_unknown_routes_are_rejected(self):
        for value in (None, "", "#how", "javascript:alert(1)", "file:///local", "http://melies.co/cinematic-techniques/camera-movement/arc-right",
                      "https://other.invalid/cinematic-techniques/camera-movement/arc-right", "https://melies.co.evil.invalid/cinematic-techniques/camera-movement/arc-right",
                      "https://user@melies.co/cinematic-techniques/camera-movement/arc-right", "/ai-video-generator?prompt=x", "/cinematic-techniques/camera-movement",
                      "/cinematic-techniques/camera-movement/not-in-catalog"):
            with self.subTest(value=value):
                self.assertIsNone(self.helper.resolve_technique(value, self.base, self.routes))

    def test_unicode_offsets_normalization_and_repeated_anchor_labels(self):
        node = html.fromstring('<p>🎥  Begin <a href="arc-right"><b>Arc</b> Right</a>, then <a href="arc-right">Arc Right</a>.<!--ignore--></p>')
        source, ranges = self.helper.inline_ranges(node, self.base, self.routes)
        self.assertEqual(source, "🎥 Begin Arc Right, then Arc Right.")
        self.assertEqual(len(ranges), 2)
        self.assertEqual(ranges[0]["start"], 9)  # JS UTF-16 counts the emoji as two.
        for span in ranges:
            self.assertEqual(js_slice(source, span["start"], span["end"]), "Arc Right")

    def test_primary_still_is_not_hidden_when_cta_reuses_it_and_unknown_media_fails(self):
        doc = html.fromstring('<html><head><meta property="og:image" content="/og.jpg"></head>'
                              '<body><article><div class="cinematic-shot"><img src="/still.jpg" alt="Real still"></div>'
                              '<div class="atmosphere-card"><img src="/still.jpg"></div></article></body></html>')
        article = doc.xpath('//article')[0]
        media = {'https://melies.co/still.jpg': {'path': 'media/still.jpg'},
                 'https://melies.co/og.jpg': {'path': 'media/og.jpg'}}
        result = self.helper.presentation_media(doc, article, self.base, media)
        self.assertEqual(result['primary'], {'kind': 'image', 'path': 'media/still.jpg', 'alt': 'Real still'})
        self.assertEqual(result['articleMediaPaths'], ['media/still.jpg'])
        self.assertEqual(result['excludedMedia'], [{'path': 'media/og.jpg', 'reason': 'metadata-only'}])
        article.append(html.fromstring('<img src="/unknown.jpg">'))
        with self.assertRaisesRegex(ValueError, 'Unknown article media group'):
            self.helper.presentation_media(doc, article, self.base, media)


if __name__ == "__main__":
    unittest.main()

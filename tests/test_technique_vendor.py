"""Maintenance-tool path/offline contracts; no network or production writes."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    import lxml  # noqa: F401
    HAVE_LXML = True
except ImportError:
    HAVE_LXML = False

ROOT = Path(__file__).resolve().parents[1]
if HAVE_LXML:
    spec = importlib.util.spec_from_file_location("technique_vendor_under_test", ROOT / "tools/vendor_techniques.py")
    vendor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vendor)


@unittest.skipUnless(HAVE_LXML, "lxml is needed only for the optional vendoring tool")
class TechniqueVendorTests(unittest.TestCase):
    def setUp(self):
        self.saved = vendor.SOURCE, vendor.OUT, vendor.EVIDENCE
        self.temp = tempfile.TemporaryDirectory(prefix="technique-vendor-test-")
        base = Path(self.temp.name)
        self.archive, self.output, self.evidence = base / "archive", base / "output", base / "evidence"

    def tearDown(self):
        vendor.SOURCE, vendor.OUT, vendor.EVIDENCE = self.saved
        self.temp.cleanup()

    def args(self, *extra):
        return ["vendor_techniques.py", "--archive", str(self.archive), "--output", str(self.output),
                "--evidence", str(self.evidence), *extra]

    def test_offline_missing_index_never_fetches(self):
        with patch("sys.argv", self.args("--offline")), patch.object(vendor, "download", side_effect=AssertionError("unexpected network")):
            with self.assertRaisesRegex(SystemExit, "missing index.html"):
                vendor.main()

    def test_fresh_archive_downloads_index_without_seed_example(self):
        item = {"id": "lighting/soft-light", "slug": "soft-light", "title": "Soft Light",
                "categoryId": "lighting", "categoryTitle": "Lighting",
                "sourceUrl": "https://melies.co/cinematic-techniques/lighting/soft-light",
                "detail": "details/lighting/soft-light.json"}
        categories = [{"id": "lighting", "title": "Lighting", "count": 1}]
        detail = {**item, "sections": [], "media": [], "prompt": {"guidance": ["Soft light."], "example": "Example."}}
        fetched = []

        def index_download(url, path, html_page=False):
            fetched.append((url, path, html_page))
            path.write_text("<html><body>Index</body></html>", encoding="utf-8")
            return {"url": url, "bytes": path.stat().st_size, "sha256": vendor.sha(path)}

        def page_download(jobs, label):
            self.assertEqual(label, "articles")
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0][1], self.archive / "articles/lighting/soft-light.html")
            return [{"url": item["sourceUrl"], "bytes": 10, "sha256": "fixture"}]

        with patch("sys.argv", self.args("--pages-only")), patch.object(vendor, "download", side_effect=index_download), \
             patch.object(vendor, "run_pool", side_effect=page_download), patch.object(vendor, "inventory", return_value=(categories, [item])), \
             patch.object(vendor, "parse_item", return_value=(item, detail)), contextlib.redirect_stdout(io.StringIO()):
            vendor.main()
        self.assertEqual(fetched, [(vendor.INDEX_URL, self.archive / "index.html", True)])
        self.assertFalse((self.archive / "dolly-in.html").exists())
        self.assertEqual(json.loads((self.output / "catalog.json").read_text(encoding="utf-8"))["items"][0]["id"], item["id"])

    def test_only_observed_origins_and_https_are_accepted(self):
        self.assertEqual(vendor.check_url(vendor.INDEX_URL), vendor.INDEX_URL)
        self.assertEqual(vendor.check_url("https://asset.melies.co/example.mp4"), "https://asset.melies.co/example.mp4")
        for url in ("http://melies.co/example", "https://example.com/movie.mp4", "https://asset.melies.co.evil.invalid/movie.mp4", "file:///local.mp4"):
            with self.assertRaises(ValueError):
                vendor.check_url(url)

    def test_media_paths_are_relative_hashed_and_extension_checked(self):
        result = vendor.media_path("https://asset.melies.co/cinematic-techniques/mini/one.mp4")
        self.assertRegex(result, r"^media/[a-f0-9]{32}\.mp4$")
        with self.assertRaises(ValueError):
            vendor.media_path("https://asset.melies.co/script.js")


if __name__ == "__main__":
    unittest.main()

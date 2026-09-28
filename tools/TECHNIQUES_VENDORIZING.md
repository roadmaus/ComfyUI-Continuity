# Updating the offline technique catalogue

`vendor_techniques.py` is an explicitly invoked maintenance tool. The custom node
does not import or run it; browsing/applying the bundled library makes no requests
to Melies. The tool needs Python and `lxml`; that extra dependency is not needed to
use the bundled library in ComfyUI.

From the repository root, for example:

```sh
python tools/vendor_techniques.py \
  --archive ../technique-source-pages \
  --output web/creator/techniques \
  --evidence ../technique-vendor-evidence
```

On Windows PowerShell, put the same command on one line, or use PowerShell's own
line-continuation syntax instead of the shell backslashes above. All paths may be
absolute; defaults are resolved relative to the repository, not the working directory.

- A fresh archive downloads the index and all technique pages. It does not need
  a manually downloaded example page first.
- Existing complete downloads are reused. Interrupted downloads remain `.part`
  files and are retried. Download concurrency is bounded to four workers.
- Origins and redirects are restricted to `https://melies.co` and
  `https://asset.melies.co`. Site trackers, scripts and unrelated assets are not
  downloaded.
- Runtime output is structured JSON and deduplicated original images/videos;
  source HTML stays outside the node. Never replace this with source HTML injection.
- This snapshot expects **424 entries / 13 categories**. An inventory change
  stops extraction for review rather than silently claiming a complete result.
- `--pages-only` captures/extracts article data and reports media URLs without
  downloading the media. This mode does **not** produce a complete offline bundle.
- `--offline` reparses an existing archive and verifies that local media exists,
  without making network requests. Missing cached pages/assets are reported as
  failures. Independent integrity/source-fidelity tests are still required before
  packaging an updated catalogue.

## Rebuild grouped article presentation

After vendoring, rebuild the supplemental presentation index from the same saved
HTML archive. This operation is offline and does not alter the original catalogue,
detail records, translations or media:

```sh
python tools/build_technique_structure.py --archive ../technique-source-pages --data web/creator/techniques
python tests/test_technique_structure.py
python tests/test_technique_vendor.py
```

`structure.json` binds comparison/film cards, frame strips and exact internal-link
ranges to the captured article hashes. Do not reuse an index for changed details
or guess link destinations from technique names. Imported asset provenance and
authorization records are retained; the repository's software license does not
by itself relicense every bundled media asset.

## Data conventions

`catalog.json` stores categories and searchable item summaries. Each `detail`
path points to `details/<category>/<slug>.json`. Media paths resolve relative to
the catalogue directory. `manifest.json` records URL, relative path, byte size,
SHA-256 and the technique IDs using each deduplicated asset.

Copy examples preserve the original `<pre>` content. Guidance is stored separately,
never rewritten into a sample character/location. Sections preserve raw normalized
`text`, links, media and complete `sourceText`. List cards may also contain
`displayText`, which inserts the visual line break between their title and
description without altering the raw fidelity fields.

The current source has 250 video-backed and 174 still-image-only techniques. An
absent video on the latter is intentional, not an invitation to invent a clip.

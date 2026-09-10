# RefMod support

Status: design. Branch `feat/refmod-support`.

## Goal

Let the Creator attach a saved **RefMod** — a pre-encoded, optionally
compressed reference latent produced by the sibling
`ComfyUI-MiniMaxH3Mod` pack — as a reference asset, exactly where it would
attach an image or a clip file.

A RefMod carries two things the Creator otherwise spends time computing:

- a VAE latent for the DiT reference payload, already compressed (pooled,
  motion-only, or full encode), so no decode + encode is needed; and
- enough metadata to build the Qwen presentation (kind, description, concept
  type).

Everything else about the reference — its ordinal label, its
`subject_definitions` line, its `retention_analysis` marker, its place in the
cast — must come out of the Creator's existing machinery unchanged. The point
is not a second reference pipeline; it is a second *source* for the same one.

Non-goals for phase 1:

- producing RefMods from the Creator (saving its encoded references), and
- the full asset-picker UI.

## The RefMod format (a contract, not an import)

A RefMod is a `.safetensors` file under a `refmods` model root:

```text
models/refmods/<name>.safetensors
  header.__metadata__.refmod_meta = JSON:
    name, kind ("image"|"video"|"audio"), latent_h, latent_w, latent_t,
    mode, source, source_shape, pool, optimize_steps, tags,
    description, concept_type, _format_version, sample_rate
  tensor "latent":
    visual  [1, 24, T, H, W]  (fp16)
    audio   [1, 32, 2, T]
```

`kind == "image"` means `T == 1`; stacked stills are stored as a `video`
kind (`T > 1`). Legacy JSON sidecars (`<name>.json`) are still readable.

The reader lives in the Creator and parses this format directly. It does
**not** import `ComfyUI-MiniMaxH3Mod`: the two packs must be installable
independently, and the header is a stable, versioned contract owned by this
document. If the sibling pack is absent, everything else in the Creator still
works and only the RefMod source is empty.

Root discovery mirrors the sibling pack: every `folder_paths` root registered
for `refmods`, falling back to `ComfyUI/models/refmods`, including the pack's
own legacy `mods/` folder for existing files. Subfolders list with `/`
separators (`celebs/person`).

## Where it plugs in

The H3 reference pipeline is one ordered walk with two halves that are
required to agree:

```text
compile._parse_assets            blob -> [Asset]
compile.plan_references          -> plan[{op, asset, label}], labels
contextir.reference_lines/...    plan -> subject_definitions, retention_analysis
media.load_all(compiled)          -> {handle: decoded media}
encode._encode_references(...)   plan -> items[] (Qwen), blocks[] (DiT)
clip.tokenize(prompt, minimax_ref_items=items)
conditioning["minimax_refs"] = blocks
```

A RefMod changes **the source of the tensors**, not the walk. So the design
keeps `Asset.kind` in `{"image", "video"}` (the mod's stored kind), leaves
`plan_references` untouched, and teaches exactly two functions about mods:
the loader and the encoder.

### 1. `Asset` gains a `mod` field

```python
@dataclass
class Asset:
    ...
    mod: str | None = None   # RefMod name (without extension), else None
```

For a mod-backed asset: `filename` is empty, `kind` is the mod's stored kind,
and `ref_size` / `trim` / `track` are refused (a stored latent has no file to
size, trim or read a track from). `takes` is allowed and defaults from the
mod's `concept_type` when the blob does not say.

### 2. Parse and resolve

`_parse_assets` accepts `kind == "refmod"` and records `mod = filename`
(the blob's `filename` is the RefMod name). Resolution of kind + defaults
happens in `compile_segment` right after parsing, in one pass that reads each
mod's header (cheap; no tensor load), so `_parse_assets` itself stays pure and
offline:

```python
def _resolve_refmods(assets, load=refmod.load):
    for asset in assets:
        if asset.mod is None:
            continue
        mod = load(asset.mod)              # header only
        asset.kind = mod.kind
        asset.filename = ""                 # not a file
        asset.takes = asset.takes or TAKES_FROM_CONCEPT.get(mod.concept_type, "full")
```

A missing mod is a `CompileError` naming the handle and the name searched for.

### 3. Planning and labels: no change

Resolved mods sit in `compiled.ref_images` or `compiled.ref_videos` by kind,
so `plan_references` numbers them, `grammar.cite` gives them `<Picture N>` /
`<Video N>`, and `contextir.reference_lines` / `retention_lines` describe them
off `(asset.kind, asset.takes)` exactly as for a file. `subjects.claimed`,
the cast, and the summaries all work because the asset looks ordinary.

The one visible difference in the prompt is honest: a mod has no filename, and
the definition line says what the label *is* (a reference picture / motion
reference), which is already the wording for a file.

### 4. Encoding

`media.load_all` skips mod-backed assets — there is no disk decode. `encode`
gains a branch in `_encode_references`:

```python
if asset.mod is not None:
    block, item = _encode_refmod(vae, asset, compiled, tally)
elif step["op"] == "image":
    ...
```

`_encode_refmod`:

1. Loads the stored latent (`refmod.load(asset.mod).latent`), and
   **never re-encodes it** — that is the whole point.
2. Builds the Qwen presentation by decoding the latent through the H3 video
   VAE and sampling it the way a file reference is sampled (image: first
   frame; video: every `FPS // 2` frames at 2 fps, with timestamps). A pooled
   or motion-only latent decodes to a blurry sequence, which is exactly what
   the sibling pack presents to Qwen.
3. Builds the DiT block with the mod's own `latent_h`/`latent_w`/`latent_t`
   and `kind`, and for `video` the `ref_audio_t`/`audio_latent` fields (0 /
   `None`; audio refmods are phase 3).
4. Does **not** cut the clip to the generation's frame count. A stored mod is
   already a deliberate length.

### 5. Caching

The latent needs no cache (it is a file read, and `latents.py`'s disk tier
would only add a copy). The presentation — the decode and 2 fps sampling — is
what is expensive, and it is cacheable on exactly two things:

```python
parts = {"refmod": refmod.stamp(asset.mod),   # path + mtime + size
         "vae": print_of_vae}                  # latent.fingerprint
```

This reuses `encode._cached` with no changes to `latents.py`. On a hit, the
framework's existing "reused from …" line prints for free.

### 6. Limits and validation

Resolved mods count against `max_images` / `max_videos` / `max_files` by
kind, so a 9-still mod is one video-kind file, not nine pictures. `ref_size`
on a mod is refused rather than ignored, matching how a `takes` narrows a
reference. Audio-kind mods are read by the header but refused in phase 1 with
a clear message.

### 7. Frontend (phase 2)

The blob is UI-owned, so the picker is where a user actually attaches a mod:

- a `refmod` source in the asset picker, listing `models/refmods` from a
  small server route (name, kind, description, concept type, token count,
  size);
- a thumbnail: decode the first latent frame through the presentation cache,
  or store a small preview in the mod metadata (the sibling pack already
  writes a `vis_preview` in some versions — confirm before relying on it);
- the asset writes `{"kind": "refmod", "filename": "<name>", ...}`.

Nothing in the node schema changes; the blob is already free-form JSON.

## Phases

- **Phase 1 — backend (this branch's first slice).**
  `creator/refmod.py` (+ tests), `Asset.mod`, `_parse_assets` /
  `_resolve_refmods`, `media.load_all` skip, `_encode_refmod` +
  `_encode_references` branch, cache key, limits/validation. Usable through a
  hand-authored blob / the API.
- **Phase 2 — picker.** server route + `web/` source + thumbnail.
- **Phase 3 — extras.** audio RefMods; per-reference strength/curve
  (`H3RefMod.ref_block`); optionally *saving* Creator references as RefMods so
  the two packs share one library.

## Test plan

- `tests/test_refmod.py`: header-only read of a synthetic `.safetensors`
  (both `_format_version` 4 and a legacy v2), missing/malformed file errors,
  root discovery order, name normalisation with subfolders, `stamp` changes
  when the file changes.
- `tests/test_compile.py` additions: a `refmod` asset resolves to the right
  kind, counts against the right limit, refuses `ref_size`, and lands in
  `ref_images`/`ref_videos`; `plan_references` gives it the same ordinal a
  file of that kind would take.
- `tests/test_ref_form.py` / a new golden: a mod-backed reference produces the
  same `subject_definitions` / `retention_analysis` shape as a file-backed
  one with the same `takes`.
- `encode` branch: a stub VAE that returns a fixed latent for a fixed pixel
  shape, asserting the block's `kind`/`latent_h`/`latent_w`/`latent_t` come
  from the mod and that the presentation is the decoded, 2 fps-sampled
  sequence — mirroring how the existing tests stub the VAE.
- `tests/test_family_leaks.py` / import guards: `creator/refmod.py` imports no
  torch, no ComfyUI and no sibling pack at module scope (header read only), so
  `compile.py` can keep importing it before a loader exists.

## Decisions (from review)

1. **Standalone reader.** Confirmed. The Creator parses the header itself and
   never imports the sibling pack, so the two install independently. The
   `CONCEPT_TAKES` map and the `_format_version` ceiling are the contract.
2. **The picker is required.** Phase 1 alone is a backend a hand-authored blob
   can reach; the feature is not usable until a user can attach a mod from the
   node. The pre-stage is also in scope: the same picker/source should let a
   user *create* a reference there, or a small dedicated node should, whichever
   reads better against the existing still/pre-stage flow.
3. **`takes` is seeded from `concept_type`** (implemented). The mapping is an
   approximation where the two vocabularies do not line up — `clothing` ->
   `object` is the notable one — and the blob may override it. See
   `refmod.CONCEPT_TAKES`.
4. **The refiner/skill must treat a mod like any other reference.** A resolved
   mod is already an ordinary `Asset` by the time `contextir` and the refiner's
   glossary see it, so the labels and retention lines are correct for free. The
   remaining work is to confirm the LLM refiner (harness and `.skill` modes) is
   not confused by a reference whose "file" is a stored latent — in particular
   that its `description`/`concept_type` reach the prose the way a filename's
   `what_i_see` would, rather than being silently absent.

## Implemented on this branch

- `creator/refmod.py` — the reader/writer: header-only `roots`, `normalize`,
  `find`, `load_meta`, `list_names`, `stamp`, `load_latent`, `save_mod`;
  `CONCEPT_TAKES`; `FORMAT_VERSION` ceiling. torch is imported lazily, so
  `compile.py` can import this under bare Python.
- `creator/compile.py` — `Asset.mod` / `mod_description` / `mod_concept`;
  `kind="refmod"` **and** an `image`/`video` asset carrying `mod` are both
  accepted and validated by `_parse_assets`; `_resolve_refmods` reads the header
  after the cast is cut and before the image/video split, so the plan, ordinals,
  `contextir` and the limits all see an ordinary asset. Added the `refmod`->`mod`
  merge prefix, and `_asset_dict` round-trips the flag.
- `creator/families/h3/encode.py` — `_encode_refmod`: latent read from the mod
  (never re-encoded), presentation decoded + 2 fps-sampled and cached on the mod
  stamp + VAE fingerprint.
- `creator/timeline.py` — `stamps` uses a mod's own file stamp, so re-saving a
  mod invalidates the node the way replacing a file does.
- `creator/server_routes.py` — `?root=refmods` listing, in the media row shape
  with `mod: true`; one unreadable mod is skipped rather than emptying the grid.
- `creator/refmod_node.py` — the **Save as RefMod** node, registered in
  `creator_node.get_node_list`. An IMAGE batch (one still = image, many = video),
  causal trim, short-edge resize, VAE encode, token cap, atomic save.
- `creator/families/h3/refine.py` + `creator/refine_routes.py` — a mod is
  described to the refiner from its saved `description` instead of being
  reported as an unreadable file, and is not attached as a picture it does not
  have.
- `web/creator/picker.js` + `editor.js` — a **RefMod** tab (a foreign root, like
  Renders), rows pick as their stored image/video kind with `mod: true`, no
  upload/organize/trim/cut, and `attachAssets` writes the flag.
- Tests: `tests/test_refmod.py` (reader, writer round-trip, listing; torch-free
  except the writer), `tests/test_refmod_assets.py` (parse, resolve, seed,
  ordinals, refusals, merge round-trip). Full suite: 88 pass, 1 pre-existing
  environment failure, 2 skips.

Not yet: an encode-branch test with a VAE stub; RefMod thumbnails in the picker
(a kind icon stands in); audio RefMods; per-reference strength/curve; and the
mod `description` is not folded into `subject_definitions` automatically.

## Remaining questions

1. **Picker shape.** A separate `RefMod` source beside the media listing, or a
   filter inside the one picker? The listing route has to answer with mods
   (name, kind, description, concept type, tokens) and a thumbnail. The
   thumbnail can be a decode of the first latent frame through the presentation
   cache, or a stored preview if the sibling pack writes one.
2. **Creation path.** A Creator-native extractor node ("save this reference as
   a RefMod") versus reusing the sibling pack's Create/Master nodes wired into
   the pre-stage. The pre-stage already makes a still that becomes a start
   frame, so the natural version is "the pre-stage's still, saved as a RefMod"
   — but a reference the user attached as a file is also worth saving.
3. **The mod's `description`.** Fold it into `subject_definitions`
   automatically (a mod that says "ginger woman" defines its own label), or
   leave the prose to the user and the refiner?
4. **Per-reference strength/curve.** The sibling pack's `ref_block(strength,
   curve)` is not used yet; every mod enters at full strength. Phase 3 unless
   asked for sooner.

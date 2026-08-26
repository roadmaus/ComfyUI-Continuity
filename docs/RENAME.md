# Renaming the pack to Continuity

MiniMax H3 was the only thing this node rendered when it was named after it.
It is now one of four families — H3, LTX 2.5, Krea 2, Ideogram 4.0 — and a
fifth is a directory with a declaration in it. The name has to stop naming one
of them.

**Continuity** is the script supervisor's job: keeping the same person, the same
prop and the same light across shot 1 and shot 9. That is the cast, the piece
references and the seam blend — the problem this pack exists to solve, and the
one thing that stays true whichever family renders the frames.

This file is the manifest for the change: what moves, what cannot, and in what
order. It is not a design document. `PLAN.md` holds the decisions.

## The rule

A user's workflow, presets and rendered files survive the rename untouched.
Everything else is fair game. That single rule decides every line below.

## Frozen forever

These appear in files the user owns and we do not. Renaming any of them turns a
saved workflow into a red box.

| what | where | why |
|---|---|---|
| `MiniMaxH3Creator`, `MiniMaxH3Timeline`, `MiniMaxH3PreStage` | `creator_node.py`, `prestage.py` | The node class ids a saved `.json` names. |
| `creator_data`, `timeline_data`, `prestage_data` | the same schemas | Widget names, saved alongside the ids. |
| `STILL_ARCH = "minimax"` | `families/h3/declare.py` | Already documented as permanent — it is in every saved blob, and it is the key a pre-stage's H3 branch nests its whole request under (`state.minimax.request`). |
| `minimax_creator_cond_video_latents`, `minimax_creator_frame_index`, `minimax_creator_audio_end_frame` | `families/h3/payload.py` | Keys inside core's conditioning dict. Runtime-only, but they are the surface the `AUDIO_END_KEY` repair matches against on every core release. Churn buys nothing and costs a compat break. |

The dozen expand-time ids — `MiniMaxH3Reel`, `MiniMaxH3Save`, `MiniMaxH3PassFrames`
and the rest — are *not* in this table on merit. They only exist inside a
subgraph the node returns, so they never reach a saved workflow and could be
renamed freely. They stay because renaming them is 487 edits for a string
nobody sees.

Their **display names** did move, because those are shown while a render runs.
The split is by what the node actually is: shared plumbing drops the family it
never belonged to (`MiniMax H3 Reel` → `Continuity Reel`, `MiniMax H3 Save` →
`Continuity Save`), and a node that really is one family's keeps that and loses
only the pack name (`MiniMax H3 Face Pass` → `H3 Face Pass`,
`MiniMax LTX 2.5 Segment` → `LTX 2.5 Segment`, which was never MiniMax's to
begin with).

A pack called Continuity whose node class id is `MiniMaxH3Creator` reads oddly
in a grep and is invisible everywhere else: the graph shows `display_name`. That
is the trade, and it is the cheap side of it.

## Moves, with a migration

Read the new path; if it is missing and the old one is there, read the old one
and write the new. One release of that, then the fallback goes.

| what | from | to |
|---|---|---|
| machine settings | `minimax_creator.settings.json` | `continuity.settings.json` |
| preset index | `minimax_creator.presets.json` | `continuity.presets.json` |
| preset bodies | `minimax_creator.preset.<id>.json` | `continuity.preset.<id>.json` |
| picker prefs | `minimax_creator.picker.json` | `continuity.picker.json` |
| LoRA prefs | `minimax_creator.loras.json` | `continuity.loras.json` |
| refiner settings | `minimax_creator.refiner` (localStorage) | `continuity.refiner` |
| localStorage mirrors | `mmc-presets`, `mmc-preset-<id>`, `mmc-picker-prefs`, `mmc-lora-prefs` | the same names with `continuity-` |
| exported preset file | `<name>.mmcpreset.json` | `<name>.continuity-preset.json` |

The export suffix moves without a fallback because nothing reads it: the import
control accepts `.json`, and the `kind` field inside the payload is descriptive
rather than checked. A file exported by the old build still imports.

The presets are the reason this section exists rather than a delete. A preset is
work — a 24-shot strip somebody arranged by hand — and it lives in userdata
rather than in the workflow, so nothing else would carry it across.

**Output prefixes are a migration of the default only.** `outputs.RENDERS` and
`outputs.STILLS` become `continuity/renders` and `continuity/stills`, so a fresh
install files into a folder named after the pack. An install that already has a
settings file keeps the prefixes stored in it, `minimax/` included. Where
somebody's renders land is not ours to change under them; a new default is not a
move order.

**The two caches just move.** `user/minimax_creator/previews` and
`user/minimax_creator/latents` become `user/continuity/…`. Both are derived data
that regenerates. The old directories are left on disk rather than deleted —
this pack does not remove files it is no longer looking at.

## Moves outright

The frontend and the backend ship in one clone, so there is no version skew to
protect against and no alias to keep.

- Every route: `/minimax_creator/*` → `/continuity/*` (111 occurrences across
  `server_routes.py`, `refine_routes.py`, `routes/families.py` and the JS).
- The websocket event `minimax_creator.refine.done` → `continuity.refine.done`.
- `logging.getLogger("minimax_creator")` → `"continuity"`.
- `cutout.PROGRESS_ID` → `continuity-cutout`.
- `category="MiniMax"` → `"Continuity"` on both schemas.
- Display names: `MiniMax H3 Creator` → `Continuity`, `MiniMax H3 Timeline` →
  `Continuity Timeline`, `MiniMax H3 PreStage` → `Continuity PreStage`. The node
  *descriptions* need rewriting too — both currently promise FL2VA/Ref2VA
  routing as though that were the whole node.
- `locales/{ja,ko,zh}/nodeDefs.json`: the display names and descriptions, keyed
  by the frozen ids. While in there, drop the four stale keys —
  `MiniMaxH3AudioTail`, `MiniMaxH3LastFrame`, `MiniMaxH3SeamTrim` and
  `MiniMaxH3TimelineJoin` — which name nodes that no longer exist.
  `TimelineJoin` was retired when `mux.py` replaced the pairwise fold. The two
  video ids share one schema, so they take one description rather than the two
  that had drifted apart.
- The error prefix H3's payload repair raises under (`Minimax_creator: …`) and
  the LoRA loader's log line, both of which people paste into issues.
- The frontend extension itself: `app.registerExtension({name: "minimax.creator"})`
  → `"continuity"`, the settings-panel section `["MiniMax H3", "Editor", …]` →
  `["Continuity", …]`, the setting id `MiniMax.Creator.Fullscreen` →
  `Continuity.Editor.Fullscreen`, and the command `minimax.toggleFullscreen` →
  `continuity.toggleFullscreen`.

  **This is the one thing a user loses**, and it is worth naming: the fullscreen
  boolean goes back to its default, and a custom keybinding set against the old
  command id is orphaned and has to be set again. Ctrl+Shift+M itself is
  declared here, so anyone who never rebound it notices nothing. A preference
  and a shortcut are not the protected set — workflows, presets and rendered
  files are — and migrating an unregistered setting id would be more machinery
  than a boolean that defaults to off is worth.
- `README.md`, `docs/*.md`, `.github/ISSUE_TEMPLATE/*`.

## Deliberately not moving

**The `mmc-` CSS prefix.** 3680 occurrences across `web/creator/styles/*.js` and
every module that builds a node. It is an opaque prefix: no user reads it, no
route depends on it, and each of the styles files is a single template literal
where a bad sweep breaks the entire frontend at once. The payoff is zero and the
blast radius is the whole UI. It stays, with a line in `styles.js` saying what it
stood for.

**`creator/` and `web/creator/`.** "Creator" was never the vendor half of the
old name, and `creator_data` is frozen regardless.

**The H3 family label.** `LABEL = "MiniMax H3"` is correct. It is the model's
name, and the pill that shows it is the pill whose whole job is to say which
model this shot lands on.

## The Comfy Registry

`[project] name` is the registry's permanent id for a pack. It cannot be renamed
in place: a new value publishes a new entry at `registry.comfy.org/nodes/<id>`
and Manager installs it into `custom_nodes/<id>/`. So the id is either changed
now or it says `minimax-creator` forever, in the two places hardest to escape.

It is changed. `minimax-creator` has 2 downloads against 56 GitHub stars, and all
34 published versions sit at `NodeVersionStatusFlagged` rather than active — the
registry has never actually been a distribution channel for this pack, so there
is nothing to orphan.

```toml
[project]
name = "continuity"          # was "minimax-creator" — a new registry entry
version = "3.0.0"            # was "2.26"; the rename is the multi-family release

[project.urls]
Repository = "https://github.com/roadmaus/ComfyUI-Continuity"
"Bug Tracker" = "https://github.com/roadmaus/ComfyUI-Continuity/issues"

[tool.comfy]
PublisherId = "roadmaus"
DisplayName = "Continuity"
Icon = "https://raw.githubusercontent.com/roadmaus/ComfyUI-Continuity/main/docs/img/icon.svg"
```

`3.0.0` rather than `2.27`: a three-part version is what the registry stores
anyway (`2.26` was published as `2.26.0`), and starting a fresh id at 3.0.0 keeps
the two histories readable as one line.

The `Icon` URL has to be edited by hand even though GitHub redirects a renamed
repo — `raw.githubusercontent.com` does not follow those redirects, and the
registry fetches the icon at publish time.

### Before any of this lands

`.github/workflows/publish_action.yml` fires on any push to `main` that touches
`pyproject.toml`. **The rename commit is a publish.** So the flagged status gets
resolved first, or `continuity` 3.0.0 starts its life in exactly the state
`minimax-creator` never left.

What is known: the shipped package contains no `eval`, `exec`, `subprocess`,
`pickle`, `torch.load` or outbound network call — the only `subprocess` and
`urllib` in the tree are in `tools/`, which `.comfyignore` correctly keeps out of
the zip. What the package *is*, is 43 MB of which 40.2 MB is 2000 `.webp` files:
the vendored style atlas, 93% of the payload by size and 95% by file count.

That is the one lever worth pulling before asking anyone. Failing that, ask
Comfy-Org directly — the API returns an empty `status_detail`, so the reason is
not discoverable from outside.

## Order

The code half is **done** — everything above the registry section has landed on
this branch, with the two migrations covered by tests (`tests/test_settings.py`
reads a file written under the old name and proves a typed output folder
survives; `tests/test_presets.py` opens a library saved under the old one). What
is left is the part that touches the outside world:

1. Resolve the registry flag. Blocking, per above.
2. Rename the GitHub repo to `ComfyUI-Continuity`. Git and web redirects are
   permanent; existing clones keep pulling.
3. ~~Land the code rename on this branch.~~ Done, `pyproject.toml` included —
   there is no state where a half-renamed pack is useful.
4. Merge to `main`. The action publishes `continuity` 3.0.0.
5. Mark `minimax-creator` deprecated on registry.comfy.org, pointing at the new
   entry.

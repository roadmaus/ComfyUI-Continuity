"""Stagehand's view of the LoRA library: searched, resolved and described.

    python3 tests/test_lorasearch.py

Pure over rows shaped as `lorameta.row` builds them and a record shaped as
`lorameta.detail` returns it. No ComfyUI, no disk.
"""

import layout
from harness import check, passed

pkg = layout.load("lorasearch")
lorasearch = pkg.lorasearch


def row(name, mtime, **fields):
    base = name.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return {"name": name, "base": base, "folder": name.rpartition("/")[0], "card_title": base,
            "mtime": mtime, **fields}


ROWS = [
    row("style/neon_rain_v2.safetensors", 3, title="Neon Rain", base_model="LTXV 2.5",
        trained_words=["neonrain"], tags=["rain", "city", "night"], strength=0.7),
    row("style/dusty_film.safetensors", 5, title="Dusty Film Look", base_model="Wan Video 2.2",
        trained_words=["dustyfilm"], tags=["film grain", "vintage"], nsfw=True),
    row("people/mira_v1.safetensors", 4, title="Mira", base_model="LTXV 2.5",
        trained_words=["mira woman"], tags=["character"], strength="strong"),
    row("motion/orbit_cam.safetensors", 1, title=None, base_model="LTXV 2.5",
        trained_words=[], tags=["camera", "orbit", "rain"]),
    row("people/mira_v2.safetensors", 2, title="Mira", base_model="LTXV 2.5"),
]
names = lambda answer: [hit["name"] for hit in answer["hits"]]

check("words in the name rank over words in the tags", names(lorasearch.search(ROWS, "rain")),
      ["style/neon_rain_v2.safetensors", "motion/orbit_cam.safetensors"])
check("more of the query's words comes first", names(lorasearch.search(ROWS, "rain night"))[0],
      "style/neon_rain_v2.safetensors")
check("a word is matched at its start, not in the middle of another", names(lorasearch.search(ROWS, "ain")), [])
check("a base model narrows, as part of its name", names(lorasearch.search(ROWS, "film", base="wan")),
      ["style/dusty_film.safetensors"])
check("so does a folder", names(lorasearch.search(ROWS, "", folder="people/")),
      ["people/mira_v1.safetensors", "people/mira_v2.safetensors"])
check("no query is the newest", names(lorasearch.search(ROWS, "", limit=2)),
      ["style/dusty_film.safetensors", "people/mira_v1.safetensors"])
check("the limit holds both ways", [len(lorasearch.search(ROWS, "", limit=-3)["hits"]),
                                    len(lorasearch.search(ROWS * 20, "", limit=99)["hits"])], [1, 40])
check("how many fit is said apart from how many came back", lorasearch.search(ROWS, "", limit=1)["matched"], 5)

check("a hit is short, and keeps a strength only when it is a number", lorasearch.search(ROWS, "mira")["hits"][0], {
    "name": "people/mira_v1.safetensors", "title": "Mira", "base_model": "LTXV 2.5", "type": None,
    "trained_words": ["mira woman"], "tags": ["character"], "strength": None})
check("NSFW is said where it is so", lorasearch.search(ROWS, "dusty")["hits"][0].get("nsfw"), True)

found = lambda given: (lambda pair: (pair[0] and pair[0]["name"], pair[1]))(lorasearch.resolve(ROWS, given))
check("the exact name", found("style/neon_rain_v2.safetensors"), ("style/neon_rain_v2.safetensors", []))
check("without the folder or the extension, or in another case", [found("Neon_Rain_V2")[0], found("style\\neon_rain_v2")[0]],
      ["style/neon_rain_v2.safetensors", "style/neon_rain_v2.safetensors"])
check("by its title", found("dusty film look")[0], "style/dusty_film.safetensors")
check("a title two files share is not guessed", found("Mira"),
      (None, ["people/mira_v1.safetensors", "people/mira_v2.safetensors"]))
check("nothing is near guesses", found("orbit")[0], None)
check("and offers what it could have meant", found("orbit")[1], ["motion/orbit_cam.safetensors"])
check("nothing is nothing", found("  "), (None, []))

check("a page of HTML is its words", lorasearch.plain(
    "<p>Rain on <b>neon</b>&nbsp;streets.</p><ul><li>use 0.7</li><li>add <i>neonrain</i></li></ul>"
    "<script>alert(1)</script><p></p><p>Thanks!</p>"),
    "Rain on neon streets.\n\n- use 0.7\n\n- add neonrain\n\nThanks!")
long = lorasearch.plain("word " * 1000, most=50)
check("a long one is cut on a word", [len(long) <= 52, long.endswith(" …"), "wor …" not in long], [True, True, True])

DETAIL = {"meta": {"title": "Neon Rain", "version": "v2", "type": "LORA", "base_model": "LTXV 2.5",
                   "trained_words": ["neonrain"], "tags": ["rain"], "strength": 0.7, "notes": "Best at <b>0.6</b>.",
                   "description": "<p>Wet streets.</p>", "version_description": "", "creator": "someone",
                   "nsfw": False, "stats": {"downloads": 9}},
          "header": {"metadata": {}}}
check("a LoRA described, with nothing said that is empty", lorasearch.about("style/neon_rain_v2.safetensors", DETAIL), {
    "name": "style/neon_rain_v2.safetensors", "title": "Neon Rain", "version": "v2", "type": "LORA",
    "base_model": "LTXV 2.5", "trained_words": ["neonrain"], "tags": ["rain"], "strength": 0.7,
    "notes": "Best at 0.6.", "description": "Wet streets.", "creator": "someone"})
check("a file nobody wrote about is its name", lorasearch.about("x.safetensors", {"meta": None}), {"name": "x.safetensors"})
passed("the LoRA library is searched, resolved and described")

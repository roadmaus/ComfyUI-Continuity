"""`{day|night}`: the seed chooses, the box shows the same choice, the refiner keeps it.

Three claims, each its own section. The grammar and the choice
(`creator/variations.py`) are pure and run bare. The piece-level step
(`compile.varied_piece`) is checked for what it must *not* touch as much as
for what it must: a card without a group has to come back as the object it
was, because a request is the segment node's cache key. And the mirror
(`web/creator/variations.js`) is run under node on the same sentences and
seeds, because the prompt box lights the alternative it says the render will
take, and that is only true while the two hashes agree.

    python3 tests/test_variations.py

The mirror section skips itself if node is not installed; the rest runs.
"""

import shutil

import layout
from harness import check, passed

_pkg = layout.load("variations", "canvas", "contextir", "subjects", "compile",
                   "prompting")
variations, compiler, prompting = _pkg.variations, _pkg.compile, _pkg.prompting

passed("all variation tests passed")

# ---- the grammar ---------------------------------------------------------------

check("a plain sentence is left alone",
      variations.resolve("a walk in the park", 1, 1), "a walk in the park")
check("a brace pair with no bar is prose",
      variations.resolve("{alone} in {the park}", 1, 1), "{alone} in {the park}")
check("an unclosed brace is prose", variations.resolve("x {a|b", 1, 1), "x {a|b")
check("a stray closing brace is prose", variations.resolve("} {a|b}", 0, 1)[0], "}")
check("no group means nothing to choose",
      [variations.has_groups("{alone}"), variations.has_groups("{a|b}"),
       variations.has_groups(""), variations.has_groups(None)],
      [False, True, False, False])

picks = {variations.resolve("a {day|night} walk", seed, 1) for seed in range(64)}
check("a group takes each of its alternatives over the seeds",
      picks, {"a day walk", "a night walk"})
check("the same seed makes the same choice",
      variations.resolve("{a|b|c|d}", 42, 3), variations.resolve("{a|b|c|d}", 42, 3))
check("an empty alternative is allowed",
      {variations.resolve("face{|, smiling}", seed, 1) for seed in range(64)},
      {"face", "face, smiling"})

NESTED = "{at the beach {in the shade|in hard sun}|in a mansion {at night|by day}}"
check("groups nest and only the taken branch is written",
      {variations.resolve(NESTED, seed, 1) for seed in range(128)},
      {"at the beach in the shade", "at the beach in hard sun",
       "in a mansion at night", "in a mansion by day"})
check("a group inside a prose brace pair still chooses",
      {variations.resolve("{a {b|c}}", seed, 1) for seed in range(64)}, {"{a b}", "{a c}"})
check("names are alternatives like any other words",
      {variations.resolve("{@anna|@ben} walks in", seed, 1) for seed in range(64)},
      {"@anna walks in", "@ben walks in"})

check("groups are numbered in reading order, outermost first",
      [(source, count) for source, count in variations.shapes(NESTED)],
      [(NESTED, 2), ("{in the shade|in hard sun}", 2), ("{at night|by day}", 2)])

# Two cards holding the same sentence must be free to choose apart, and the
# piece's own fields choose as the piece. Over enough seeds every pairing shows.
apart = {(variations.resolve("{a|b}", seed, 1), variations.resolve("{a|b}", seed, 2))
         for seed in range(64)}
check("the card is part of the choice", len(apart), 4)
check("the choice is fair enough to be worth having",
      abs(sum(variations.choose(seed, 1, 0, 2) for seed in range(2000)) - 1000) < 120, True)
big = 18446744073709551615
check("a 64-bit seed chooses without complaint",
      variations.choose(big, "piece", 0, 3) in (0, 1, 2), True)

# ---- the piece ----------------------------------------------------------------


def shot(prompt, **fields):
    return {"prompt": prompt, "assets": [], "loras": [], **fields}


def strip(*segments, **fields):
    return {"version": 2, "prompt": "", "segments": list(segments), **fields}


plain = strip(shot("a room"), shot("a hall"))
check("a piece with nothing to choose is the object it was",
      compiler.varied_piece(plain, 7) is compiler.as_piece(plain), True)

varied = compiler.varied_piece(
    strip(shot("{day|night}"), shot("{day|night}"), shot("a hall"), prompt="{noir|pastel}"), 7)
check("a card without a group keeps its object",
      varied["segments"][2] is compiler.as_piece(varied)["segments"][2], True)
check("the piece's own prompt is chosen",
      varied["prompt"] in ("noir", "pastel"), True)
check("every card's prompt is chosen",
      all(s["prompt"] in ("day", "night") for s in varied["segments"][:2]), True)
check("a card chooses on the piece's seed by its number",
      varied["segments"][0]["prompt"],
      variations.resolve("{day|night}", 7, 1))
check("...and the second card by its own number",
      varied["segments"][1]["prompt"],
      variations.resolve("{day|night}", 7, 2))
check("the standing prompt chooses as the piece",
      varied["prompt"], variations.resolve("{noir|pastel}", 7, "piece"))

own = compiler.varied_piece(strip(shot("{a|b|c|d}", seed=99)), 7)
check("a retaken card chooses on its own seed",
      own["segments"][0]["prompt"], variations.resolve("{a|b|c|d}", 99, 1))

numbered = compiler.varied_piece(strip(shot("{a|b|c|d}", card_no=5)), 7)
check("a card in a shortened render chooses by its number on the strip",
      numbered["segments"][0]["prompt"], variations.resolve("{a|b|c|d}", 7, 5))

refined = compiler.varied_piece(strip(shot(
    "typed", refined={"enabled": True, "body": "the {dawn|dusk} light",
                      "sections": {"summary": "a {calm|tense} scene"}})), 7)
check("a refined body is chosen like a prompt",
      refined["segments"][0]["refined"]["body"] in ("the dawn light", "the dusk light"), True)
check("...and so are its sections",
      refined["segments"][0]["refined"]["sections"]["summary"]
      in ("a calm scene", "a tense scene"), True)

sound = compiler.varied_piece(strip(shot("x", soundscape="{rain|wind} on glass")), 7)
check("the soundscape is a prompt too",
      sound["segments"][0]["soundscape"] in ("rain on glass", "wind on glass"), True)

# A held card is dropped from the render by `rendered_piece`, and the card
# after it keeps the choice it had: its number, not its position, is the key.
held = strip(shot("a", hold=True), shot("{a|b|c|d}"))
rendered = compiler.varied_piece(compiler.rendered_piece(held), 7)
check("a card's choice holds still while another is held back",
      rendered["segments"][0]["prompt"], variations.resolve("{a|b|c|d}", 7, 2))

# What the render reads is the chosen text: through the payload, the choice
# reaches the request and the compiled prompt, and the braces do not.
compiled = compiler.compile_timeline(compiler.varied_piece(strip(shot("a {day|night} walk")), 7))
check("the compiled prompt carries the choice and no braces",
      ["{" in compiled[0].prompt, ("day walk" in compiled[0].prompt) or ("night walk" in compiled[0].prompt)],
      [False, True])

# A file named only inside an alternative the seed passes over is muted for
# the render: everything live in `assets` is encoded whether the prompt names
# it or not, so the words alone choosing would send both pictures.
def picture(handle):
    return {"handle": handle, "kind": "image", "role": "reference", "filename": handle + ".png"}


either = strip(shot("{@img-1|@img-2} walks in", assets=[picture("img-1"), picture("img-2")]))
for seed in range(8):
    card = compiler.varied_piece(either, seed)["segments"][0]
    named = card["prompt"].split(" ")[0][1:]
    check(f"seed {seed}: the picture the sentence lost is muted, the one it kept is not",
          {a["handle"]: a.get("enabled", True) for a in card["assets"]},
          {"img-1": named == "img-1", "img-2": named == "img-2"})
    compiled_card = compiler.compile_timeline(compiler.varied_piece(either, seed))[0]
    check(f"seed {seed}: one picture reaches the encoder",
          len(compiled_card.ref_images), 1)

unnamed = strip(shot("{a|b} walks in", assets=[picture("img-1")]))
check("a file the sentence never named is left attached, as it always was",
      compiler.varied_piece(unnamed, 3)["segments"][0]["assets"][0].get("enabled"), None)
twice = strip(shot("{@img-1|@img-1 slowly} walks in", assets=[picture("img-1")]))
check("a file every alternative names is never muted",
      compiler.varied_piece(twice, 3)["segments"][0]["assets"][0].get("enabled"), None)

# ---- the refiner ---------------------------------------------------------------

check("a rewrite that keeps every group passes",
      prompting.dropped_variations(["a {day|night} {a|b|c} walk"],
                                   "the {noon|dark} scene, {x|y|z}"), [])
check("the words may grow; the count is what is kept",
      prompting.dropped_variations(["a {day|night} walk"],
                                   "the {under a flat noon sun|by sodium streetlight} scene"), [])
check("a group the rewrite chose for itself is reported by its source",
      prompting.dropped_variations(["a {day|night} {a|b|c} walk"], "the {noon|dark} scene"),
      ["{a|b|c}"])
check("the global prompt counts too",
      prompting.dropped_variations(["a walk", "{noir|pastel}"], "a walk"), ["{noir|pastel}"])
check("a request with no groups asks nothing of the rewrite",
      prompting.dropped_variations(["a walk"], "a {long|short} walk"), [])

# ---- the mirror ------------------------------------------------------------------

if shutil.which("node") is None:
    print("mirror: skipped, node is not installed")
else:
    CASES = ["a {day|night} walk", NESTED, "{alone} in {the park}", "x {a|b", "} {a|b} {",
             "face{|, smiling}", "{@anna|@ben} walks in", "{a {b|c}}", "{a|b|c|d|e|f|g}",
             "ünïcödé {ä|ö|ü} {🎥|🎬}"]
    SEEDS = [0, 1, 2, 7, 42, 4242, 2 ** 31 - 1, 2 ** 53 - 1]
    CARDS = [1, 2, 5, "piece"]
    SCRIPT = """
const v = await import(process.argv[1]);
const cases = JSON.parse(process.argv[2]);
const seeds = JSON.parse(process.argv[3]);
const cards = JSON.parse(process.argv[4]);
const out = { resolved: [], layout: [] };
for (const text of cases) for (const seed of seeds) for (const card of cards) {
  out.resolved.push(v.resolve(text, seed, card));
}
// Painted in here rather than in Python: the offsets are the browser's, in
// UTF-16 units, and an emoji is two of those and one of Python's.
for (const text of cases) {
  const { marks, off } = v.layout(text, 7, 1);
  const chars = [...text.split("")];
  for (const [start, end] of [...off, ...marks]) for (let i = start; i < end; i += 1) chars[i] = "";
  out.layout.push({ marks: marks.map(([s, e]) => text.slice(s, e)).join(""),
                    painted: chars.join("") });
}
console.log(JSON.stringify(out));
"""
    reflected = layout.run(SCRIPT, layout.js("variations.js"), CASES, SEEDS, CARDS)
    expected = [variations.resolve(text, seed, card)
                for text in CASES for seed in SEEDS for card in CARDS]
    check("the browser makes the same choice the compiler makes",
          reflected["resolved"], expected)

    # The paint: every live group's braces and bars are marked, and the text
    # inside every alternative not taken is dimmed — so the marks and the
    # dimmed spans, laid over the text, leave the choice the compiler made.
    for text, drawn in zip(CASES, reflected["layout"]):
        check(f"marks in {text!r} are braces and bars only",
              set(drawn["marks"]) <= {"{", "|", "}"}, True)
        check(f"paint over {text!r} shows the render's own sentence",
              drawn["painted"], variations.resolve(text, 7, 1))

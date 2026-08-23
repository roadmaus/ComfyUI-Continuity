# The style atlas

A fourth tab in the preset library, holding 941 looks you can put on a shot. This
says what it is, why it is a scope rather than a dropdown, what it does to a
prompt, and how it is kept current.

## Where it comes from

[hoodtronik/minimax-h3-style-atlas](https://github.com/hoodtronik/minimax-h3-style-atlas)
indexes every distinct visual style in
[ostris/minimax_h3_1k](https://huggingface.co/datasets/ostris/minimax_h3_1k) — a
thousand H3 clips, each with a detailed multimodal caption. The atlas reads the
opening style descriptor off each caption, collapses the duplicates, groups what
is left into eight media categories, and pairs each entry with a still lifted
from its clip.

What makes that worth vendoring rather than writing our own list of adjectives is
that these are not adjectives. They are **the exact strings this model was
captioned with**, in the position the caption puts them — which is the position
the [prompt skill](../skills/minimax-h3-prompt.skill) says a style belongs in.
"Claymation with visible fingerprint texture and gently stuttering stop-motion
movement" is not a description of claymation; it is a phrase H3 has seen a
thousand frames of.

## Vendored, and only two thirds of it

`tools/vendor_style_atlas.py` takes the atlas's generated `index.html` apart and
writes two things into `web/creator/presets/`:

- **`atlas.js`** — the index. Category, descriptor and clip ids, one style per
  line, plus a header stamping the upstream revision it was taken from. It is a
  *mirror*: no titles of ours, no reordering, no editorialising. Every decision
  about how a style is shown lives next to it in `stylelib.js`, hand-written, so
  re-running the generator can never quietly undo one.
- **`atlas/<clip>.webp`** — the stills, byte-identical to the ones the page
  carries, one file per clip. About 5 MB for a thousand of them.

**No video, ever.** The atlas offers a 1.4 GB offline bundle of the dataset's
clips; this pack does not use it, download it, or need it. Text and one still
frame per clip is the whole of what is taken, and nothing here streams from
Hugging Face — the point of the still is that it costs the dataset's author
nothing to look at.

Separate files rather than data URIs in the module, because the grid lazy-loads:
a library showing a dozen cards fetches a dozen stills and the browser caches
them like any other image. Inlined they would be five megabytes of base64 parsed
on every library open, for a tab most sessions never touch. The module itself is
160 KB and is `import()`ed the first time the tab is opened — never at boot.

### Updating

```
git clone --depth 1 https://github.com/hoodtronik/minimax-h3-style-atlas /tmp/atlas
python3 tools/vendor_style_atlas.py /tmp/atlas
python3 tests/test_style_atlas.py
```

Stills for clips upstream dropped are deleted, so the folder cannot accumulate
orphans, and the revision goes in the generated header — which is what makes "is
our copy current?" answerable by reading one line rather than diffing five
megabytes. `test_style_atlas.py` checks both directions of the pairing: every
clip the index names has a still, and every still on disk is named by the index.

## A scope, not a dropdown

The library already had three scopes and the machinery to say what crosses
between them, and a style is exactly that shape: something a preset can be *of*,
applicable to a piece, a card or a pre-stage, and capturable off none of them.
So it is `scope: "style"` with `sections: ["style"]`, and it needed no new card
machinery — a style row is an ordinary builtin whose body `loadBody` hands back
inline, the same as the seven shipped starters.

`SCOPE_SECTIONS.style` is `["style"]` and nothing writes to it: the tab is a
catalogue, so Save, Import and *From a render* are absent from its bar rather
than dimmed, and the ★ Starred shelf — which nothing read-only can ever fill — is
not offered. The atlas's eight media groups take its place, and they arrive as
shelves for free: a style row's `folder` is its category, and `folders()` already
draws a shelf per distinct folder.

## What applying one does

**A style is the one section that edits the field it lands on instead of
replacing it.** Every other section owns its fields outright — applying `look`
puts a whole canvas back — but a style is a clause at the front of a sentence
somebody wrote, and a style that wiped the prompt would be a style used once.

So applying one *swaps the lead*. The descriptor goes in front; where the prompt
already opens with a descriptor from the atlas, that one comes out. Try six looks
on the same shot and you get six prompts, not six stacked paragraphs.

```
The cat knocks a mug off the table, and it shatters.
  → Claymation with visible fingerprint texture …, the cat knocks a mug off …
  → LEGO brickfilm stop motion with bright plastic sheen …, the cat knocks a mug off …
```

Three details that are not obvious:

- **The match has to end on a clause boundary.** The atlas holds a bare
  "Claymation" as well as a dozen longer ones that start with it, so the
  vocabulary is scanned longest-first — and a candidate only matches if the next
  character ends a clause, or "Claymation" would eat the front of
  "Claymationist" and swap out a word that was never a style.
- **The comma joins, and the capital mostly stays.** H3's captions run
  `<style>, <scene>`, so that is the join. An article or preposition behind the
  comma is lower-cased from a closed list — `A`, `The`, `In`, `Inside`, `On`,
  and a dozen more — because lower-casing whatever the prompt happens to start
  with would turn "Marcus waits at the gate" into "marcus waits at the gate",
  and mangling somebody's character is worse than a capital letter mid-sentence.
- **The vocabulary is registered, not imported.** `presets.js` cannot import the
  atlas without pulling 160 KB into every page load, so `stylelib.js` calls
  `setStyleVocabulary` as it loads. Loading it is the only way a style can reach
  an apply at all, so there is no order in which the swap runs blind.

Nothing else moves. A style touches the prompt of whatever it was applied to —
the piece's, the card's, or the pre-stage's — and not the canvas, the strip, the
weights or a card that was already written.

## The card

The preset card with its middle swapped. The hero is a still rather than a strip,
and the descriptor stands where the section chips would: a row of chips all
reading *style*, under nine hundred cards on a tab that holds nothing else, would
be nine hundred repetitions of the tab's own name.

The descriptor is set in two registers. Its opening clauses are the name — taken
greedily until there are enough characters to tell one entry from another, since
"Live-action" alone opens 265 of them — and the rest of the sentence is set dim
underneath, because that is what distinguishes an entry from the twenty beside
it. Between them they are the descriptor, whole: neither half is invented and
neither is printed twice. The facts line is the category and the clip count, in
the same monospace the rest of the library reads instrument values in.

**The still fills the band rather than fitting inside it**, which is the one
place this tab argues with the pre-stage card next to it. The atlas keeps each
clip's true shape, so a fitted still would draw a 4:3 clip at half the width of a
16:9 one — and the shape of somebody else's dataset clip has no bearing on the
canvas you are about to render. What is being judged here is grain, palette and
medium, and those want pixels.

Where one descriptor was read off several clips, the first fills the band and the
others are counted in the corner. All of them are in the inspector, which is
where there is room: two style sentences can read almost identically, and the
frames are what tell "grainy 16mm exploitation print" from "faded 35mm
exploitation print" at a glance.

Cards are materialised sixty at a time behind the picker's own sentinel. 941 rows
rebuilt on every keystroke of the search is a tab that stutters, and selecting a
card moves the ring in place rather than rebuilding the grid — otherwise clicking
the three-hundredth card would throw away the two hundred and forty above it.

## What the inspector does not have

No name to edit, no cover to set, nothing to export and nothing to delete: a
style is shipped and the same for everybody. What is left is the descriptor in
full — selectable, because it is the text about to go into the prompt — every
still it was read off, the one section row, and Apply.

It also carries the credit. The atlas is hoodtronik's work and the dataset under
it is ostris's, and both are named where a style is used rather than only in a
readme.

## The one honest wart

Upstream's descriptors are the *opening* of a caption, and H3's captions fuse
medium and setting: some entries run past the look into "along a brick-built
jousting lane lined with cheering crowd minifigs". Applying one of those brings
the setting with it.

This is not trimmed, and the reason is that trimming it means guessing where a
look stops being a look — and the greedy clause split that makes the card
readable is a presentation heuristic, not a claim about which half is which.
"Live-action, 1970s grindhouse style shot on faded 35mm exploitation print" /
"with a dusty amber color cast, heavy grain, and visible splice marks, at a
lonely desert gas station…" would lose the grain along with the gas station. So
the whole descriptor is shown in the inspector before Apply is pressed, and what
lands in the prompt is a prompt — sitting in the editor, ready to be cut.

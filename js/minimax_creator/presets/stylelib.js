// The Style tab's rows, built off the vendored atlas.
//
// `atlas.js` beside this file is generated and is a faithful mirror of upstream
// — category, descriptor, clip ids, and nothing else. Everything this pack
// *decides* about a style lives here, so re-running the vendoring script can
// never quietly undo a design decision. The two halves are meant to be read as
// "what upstream says" and "what we do with it".
//
// A style row is an ordinary builtin preset with one section in it, which is why
// the library needed no new card machinery to show one: it is a `scope: "style"`
// row with `sections: ["style"]`, and `loadBody` hands its body straight back
// without touching userdata, exactly as it does for the shipped starters.
//
// Two things a style row carries that no other row does:
//
// * **`thumbs`** — plain URLs, not the `{path, kind}` asset rows every other
//   picture in this pack is. A still here is a file the pack ships and the
//   frontend serves out of `WEB_DIRECTORY`; there is no output folder behind it
//   and no thumbnail route to resolve it through. Addressed off `import.meta.url`
//   so the extension's installed folder name is nobody's business but the
//   browser's.
// * **`lead` / `rest`** — the descriptor split for the card. The atlas writes one
//   long clause chain, and a card that set all of it at one size would be a wall;
//   the opening clauses name the medium and the rest is what distinguishes this
//   entry from its twenty siblings, so they are set differently and neither is
//   repeated.
//
// Nothing here is fetched. The module is imported the first time the Style tab is
// opened and never again, and the stills load as the grid scrolls them into view.

import { describe, setStyleVocabulary } from "../presets.js";
import { ATLAS, CATEGORIES, STYLES } from "./atlas.js";

export { ATLAS } from "./atlas.js";

/** Where a descriptor stops being the name of a medium and starts being the
 *  detail. Clauses are taken until there are enough characters to tell one
 *  entry from another — "Live-action" alone names 265 of them, and
 *  "2D cutout-paper stop-motion animation" names exactly one look. */
const LEAD_MIN = 34;

function split(phrase) {
  const clauses = phrase.split(", ");
  let lead = clauses[0];
  let index = 1;
  while (lead.length < LEAD_MIN && index < clauses.length) lead += `, ${clauses[index++]}`;
  return { lead, rest: clauses.slice(index).join(", ") };
}

const thumbUrl = (clip) => new URL(`./atlas/${clip}.webp`, import.meta.url).href;

let rows = null;

/**
 * Every style in the atlas as a library row, newest-first order being
 * meaningless here — they come out grouped by category and alphabetical within
 * it, which is the atlas's own order and the one its categories were written to
 * be read in.
 *
 * Registering the vocabulary is part of loading: `leadWithStyle` swaps one
 * descriptor for another and can only do that against a list of what a
 * descriptor looks like, and this is the only place that list exists.
 */
export function styleRows() {
  if (rows) return rows;
  setStyleVocabulary(STYLES.map(([, phrase]) => phrase));
  rows = STYLES.map(([category, phrase, clips]) => {
    const { lead, rest } = split(phrase);
    const data = { style: { text: phrase, category: CATEGORIES[category] ?? "", clips } };
    return {
      // Off the first clip rather than a counter: it survives upstream adding a
      // style in the middle of a category, which a positional id would not.
      id: `style.${clips[0]}`,
      name: lead,
      scope: "style",
      // The whole descriptor, which is what the library's search reads — so
      // "grindhouse", "needle-felted" and "anamorphic" all find their entries
      // without the search having to learn anything about styles.
      note: phrase,
      // The category *is* the shelf: `folders()` collects distinct folders per
      // scope and the shelf row draws them, so the atlas's eight media groups
      // arrive as shelves without a line of new code.
      folder: CATEGORIES[category] ?? "",
      starred: false,
      builtin: true,
      created: 0,
      updated: 0,
      sections: ["style"],
      cover: null,
      data,
      lead,
      rest,
      thumbs: clips.map(thumbUrl),
      ...describe(data, "style"),
    };
  });
  return rows;
}

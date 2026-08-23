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
// Three things a style row carries that no other row does:
//
// * **`thumbs`** — plain URLs, not the `{path, kind}` asset rows every other
//   picture in this pack is. A picture here is a file the pack ships and the
//   frontend serves out of `WEB_DIRECTORY`; there is no output folder behind it
//   and no thumbnail route to resolve it through. Addressed off `import.meta.url`
//   so the extension's installed folder name is nobody's business but the
//   browser's.
// * **`stills`** — the same frames at the clip's own resolution. A 192px card
//   picture tells you which look this is; it is not a reference, and `encode.py`
//   scales a reference image up to a 2048 short edge, so the source's own pixels
//   are the ceiling. These are what "Cast this frame as a look" attaches, and
//   they are the reason a style is usable on a look nobody has a folder of.
// * **`lead` / `rest`** — the descriptor split for the card. The atlas writes one
//   long clause chain, and a card that set all of it at one size would be a wall;
//   the opening clauses name the medium and the rest is what distinguishes this
//   entry from its twenty siblings, so they are set differently and neither is
//   repeated.
//
// Nothing here is fetched from anywhere but this folder — not at boot, not on
// open, not when a frame is cast. The module is imported the first time the Style
// tab is opened and never again, and the pictures load as the grid scrolls them
// into view. The whole catalogue works with the machine offline, which is why the
// frames are vendored rather than pulled from the dataset on demand.

import { describe, setStyleVocabulary } from "../presets.js";
import { ATLAS, CATEGORIES, STYLES } from "./atlas.js";

export { ATLAS } from "./atlas.js";

// ---- the subject, cut out of the style --------------------------------------
//
// A descriptor is not a style phrase. Upstream says so plainly: it is "the
// opening clause of the caption's `integrated_multimodal_description` field —
// the text before the first action beat". The split is by *action*, so a clip's
// scene and its cast ride along in front of the beat and land in the descriptor
// whole.
//
// What that costs, measured over all 941: seventy-two carry a literal `(S1)` —
// the dataset's own subject token, which means nothing to this pack and less to
// the model — and seventy-six open onto a named character. A hundred and
// sixty-one are cut off at exactly 250 characters, mid-word, because that is
// where the atlas page truncates. All of it went into the prompt verbatim, so
// asking for LEGO used to also ask for a chef minifig and a stovetop fire.
//
// So the clause chain is walked and stopped at the first clause that is about
// something rather than about how it looks: one opening on a locative
// preposition ("inside a brick-built restaurant kitchen set"), one naming a
// person, or one with a verb in it. The first clause is always kept — it names
// the medium and it is the one thing every entry has.
//
// This is a *cut*, never a rewrite. Nothing is invented, no clause is reordered,
// and the verbatim descriptor is kept beside it — it is what the search reads
// and what the inspector shows as provenance. Rewriting nine hundred phrases is
// how a catalogue stops matching the pictures under it.
//
// Here rather than in `atlas.js` deliberately: that file is a mirror of upstream
// and regenerating it must not be able to undo this.

/** The dataset's subject token — `(S1)`, `(S2)`. A reference to a character
 *  defined elsewhere in a caption this pack never had. */
const SUBJECT_TOKEN = /\s*\(S\d+\)/g;

/** A clause that opens on one of these is siting the shot, not describing it. */
const LOCATIVE = /^(?:on|in|inside|at|across|along|atop|down|through|under|over|outside|beside|behind|beneath|from|before|amid|among|against|within|near|past|around|throughout)\s/;

/** Somebody in the frame: a determiner, then within a clause's reach, a person.
 *  Determiner-anchored so "fingerprint ridges across every clay surface" — which
 *  is texture, not cast — survives. Possessives are not in the list: they change
 *  the cut on none of the 941, because a clause that introduces somebody opens on
 *  an article, and a clause that refers back to them has already been cut. */
const PEOPLE = /\b(?:a|an|the|two|three|four|five|six|their|its)\b.{0,60}?\b(?:m[ae]n|wom[ae]n|boy|girl|kid|child|teen\w*|fisherman|chef|dentist|farmer|punk|figures?|minifigs?|puppet\w*|worker|driver|soldier|dancer|singer|astronaut|alien|mechanic|crew|gnomes?|creatures?|anchor|host|stranger|couple|family|hands?)\b/;

/** Something happening. A style holds still; a beat does not. */
const ACTION = /\b(?:flips?|bursts?|hoists?|wrench\w*|plants?|blinks?|hops?|swarms?|walks?|runs?|turns?|steps?|leans?|opens?|slams?|lifts?|drops?|reaches?|pulls?|pushes?|sits?|stands?|waits?|enters?|exits?)\b/;

/**
 * The look alone, out of one atlas descriptor.
 *
 * @param {string} phrase  the descriptor, verbatim
 * @returns {string}  its style clauses, in their own order and words
 */
export function distil(phrase) {
  const clauses = String(phrase).replace(SUBJECT_TOKEN, "").split(", ")
    .map((clause) => clause.trim()).filter(Boolean);
  const kept = [];
  for (const [index, clause] of clauses.entries()) {
    const lower = clause.toLowerCase();
    // The first clause names the medium and is never in question — "Claymation",
    // "Live-action". Every one after it has to earn its place.
    if (index && (LOCATIVE.test(lower) || PEOPLE.test(lower) || ACTION.test(lower))) break;
    kept.push(clause);
  }
  return kept.join(", ");
}

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

/** The same frame at the clip's own resolution, for when it is wanted as a
 *  reference rather than as a picture of a card. Vendored beside the thumb and
 *  cut from the same frame, so the card and the reference are one moment. */
const stillUrl = (clip) => new URL(`./atlas/full/${clip}.webp`, import.meta.url).href;

let rows = null;

/**
 * Every style in the atlas as a library row, newest-first order being
 * meaningless here — they come out grouped by category and alphabetical within
 * it, which is the atlas's own order and the one its categories were written to
 * be read in.
 *
 * Registering the vocabulary is part of loading: `leadWithStyle` swaps one
 * descriptor for another and can only do that against a list of what a
 * descriptor looks like, and this is the only place that list exists. Both
 * forms of every descriptor go in — the distilled clause and the verbatim one —
 * because a prompt written before the cut opens with the long form, and a style
 * applied over it has to be able to take that back out.
 */
export function styleRows() {
  if (rows) return rows;
  setStyleVocabulary(STYLES.flatMap(([, phrase]) => [distil(phrase), phrase]));
  rows = STYLES.map(([category, phrase, clips]) => {
    const style = distil(phrase);
    const { lead, rest } = split(style);
    const data = {
      style: {
        text: style,
        category: CATEGORIES[category] ?? "",
        clips,
        // The descriptor as upstream wrote it, kept where it is cut. Not applied
        // — shown, so the inspector can say what the clip's own caption said and
        // somebody comparing against the atlas page finds their entry.
        ...(style === phrase ? {} : { caption: phrase }),
      },
    };
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
      stills: clips.map(stillUrl),
      ...describe(data, "style"),
    };
  });
  return rows;
}

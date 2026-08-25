// The shipped starters: a library that opens empty teaches nothing.
//
// A JS module rather than files on disk, which is the whole of their storage
// story: nothing to read at boot, nothing to half-write, no route to serve them
// and no id that can collide with a user's. They carry their sections inline, so
// `loadBody` hands them straight back without touching userdata.
//
// **None of them names a file.** A starter that pointed at a checkpoint, a LoRA
// or a reference would be broken on every machine but the one it was written on,
// and a library whose shipped half is red is worse than one that ships nothing.
// So these carry rows, canvases and seams — the settings that mean the same thing
// everywhere — and leave the weights to the node.
//
// They cannot be overwritten or starred: a starter is the same for everybody, and
// "Save current setup" is how you get one of your own.

import { describe } from "../presets.js";
import * as S from "../state.js";

/** Build the index row a card draws from, so a starter is described by exactly
 *  the function a saved preset is described by. */
function builtin({ id, name, scope, note, data }) {
  return {
    id: `builtin.${id}`,
    name,
    scope,
    note,
    folder: "",
    starred: false,
    builtin: true,
    created: 0,
    updated: 0,
    sections: Object.keys(data),
    cover: null,
    data,
    ...describe(data, scope),
  };
}

export const BUILTIN = [
  builtin({
    id: "native-row",
    name: "Native row — 20 steps",
    scope: "piece",
    note: "What the H3 templates sample with, and what this node declares. The way "
        + "back from a turbo row.",
    data: {
      speed: {
        turbo: null,
        row: {
          steps: S.TURBO_RESET.steps,
          cfg: 1.0,
          sampler_name: S.TURBO_RESET.sampler_name,
          scheduler: S.TURBO_RESET.scheduler,
          shift_video: S.TURBO_RESET.shift_video,
          shift_audio: S.TURBO_RESET.shift_audio,
          block_cache: "off",
          spectrum: false,
        },
      },
    },
  }),

  builtin({
    id: "draft-row",
    name: "Draft row — 4 steps",
    scope: "piece",
    note: "The row a turbo LoRA wants: euler on beta, four steps. Pick the LoRA "
        + "itself in the weights popover — a preset cannot name a file that is "
        + "only on your disk.",
    data: {
      speed: {
        turbo: null,
        row: {
          steps: S.TURBO_STEPS.draft,
          cfg: 1.0,
          sampler_name: S.TURBO_SAMPLER,
          scheduler: S.TURBO_SCHEDULER,
          block_cache: "off",
          spectrum: false,
        },
      },
    },
  }),

  builtin({
    id: "vertical",
    name: "Vertical — 9:16",
    scope: "piece",
    note: "A phone-shaped canvas at the native short edge.",
    data: {
      // No `short_edge`: the native edge is the family's, and a starter is
      // family-neutral, so a number here would be one family's edge applied to
      // whichever piece the preset lands on. Omitted, `applyToPiece` leaves the
      // piece's own — which `lookDefaults` sets to its family's native.
      look: { aspect: "9:16", upscale: "two_pass" },
    },
  }),

  builtin({
    id: "feathered-continuation",
    name: "Feathered continuation — 6 s",
    scope: "shot",
    note: "A card that runs on from the one in front of it, picture and sound, with "
        + "the medium blend across the seam instead of the classic single frame.",
    data: {
      shot: {
        duration_s: 6,
        checkpoint: "auto",
        continue: true,
        continue_audio: true,
        // The middle width of the default family's grid. A starter is
        // family-neutral and a width is not, so `applyToShot` retargets this
        // onto the grid of whatever family the card belongs to — see
        // `S.nearestFeather`. Copied verbatim it would fall off that grid and
        // read back as the classic single frame.
        feather: S.featherGridOf()[2],
      },
    },
  }),

  builtin({
    id: "hard-cut",
    name: "Hard cut — 4 s",
    scope: "shot",
    note: "A short card that starts fresh: no continuation, no blend. What a cut is.",
    data: {
      shot: { duration_s: 4, checkpoint: "auto", continue: false, continue_audio: false },
    },
  }),

  builtin({
    id: "poster-still",
    name: "Poster — Ideogram 4",
    scope: "prestage",
    note: "Ideogram 4.0 on its quality preset, landscape 3:2. Ideogram owns its own "
        + "resolution-shifted schedule, so the scheduler pill does not apply.",
    data: {
      look: { aspect: "3:2", short_edge: S.PRESTAGE_DEFAULT_EDGE },
      weights: { arch: "ideogram4", quality: "quality", models: {} },
      speed: {
        turbo: null,
        row: {
          steps: S.PRESTAGE_IDEOGRAM_STEPS.quality,
          cfg: S.PRESTAGE_IDEOGRAM_ROW.cfg,
          sampler_name: S.PRESTAGE_IDEOGRAM_ROW.sampler_name,
        },
      },
    },
  }),

  builtin({
    id: "character-sheet",
    name: "Character sheet — Krea 2",
    scope: "prestage",
    note: "Krea 2 RAW at its own row, portrait 9:16 — the shape a reference sheet "
        + "wants before it becomes a shot's @reference.",
    data: {
      look: { aspect: "9:16", short_edge: S.PRESTAGE_DEFAULT_EDGE },
      weights: { arch: "krea2", models: {} },
      speed: { turbo: null, row: { ...S.PRESTAGE_KREA_RAW } },
    },
  }),
];

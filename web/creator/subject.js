// The grey the cutouts sit on. The subject view that used to live here —
// one picture and the clicks that say which subject the scissors mean — is
// the picture editor's now (`picture.js`), where the clicks are made on the
// same window the crop is; this is what it and the picker still share.

/** One backdrop level as a CSS colour. The plate's field is a grey level
 *  because both families want a neutral one — see `creator/cutout.py` — and the
 *  preview has to sit on the same grey the panels were composited onto, or the
 *  cut-out edges read as a halo that is not in the file. */
export function greyField(level) {
  const step = Math.round(Math.max(0, Math.min(1, Number(level) || 0)) * 255);
  return "rgb(" + step + "," + step + "," + step + ")";
}

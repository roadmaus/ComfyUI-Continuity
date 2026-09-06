// Which square of a source a preview is of — the mirror of `upscale._tile`.
//
// Two surfaces draw a rectangle that has to agree with a picture the server
// cut: the upscale bench's locator, which says where its tile came from, and
// the loupe, which lays a refined tile back over the region it is a picture of.
// Both need the *server's* answer, not their own approximation of it, because
// both clamp — a square asked for near an edge comes back shifted inward, and a
// rectangle drawn where it was asked for rather than where it landed points at
// pixels nobody is looking at.
//
// So the arithmetic is here once, in the terms `upscale.py` uses, and
// `tests/test_tile_mirror.py` holds the two files together.

/** `upscale.MIN_PREVIEW_TILE`, `upscale.MAX_PREVIEW_TILE`, `upscale.PREVIEW_TILE`. */
export const MIN_TILE = 128;
export const MAX_TILE = 1024;
export const DEFAULT_TILE = 384;

/** The side the server will actually use, given what was asked for and how big
 *  the picture is. Mirrors `upscale.preview_side` and `_tile`'s own `min`. */
export function tileSide(natural, side = DEFAULT_TILE) {
  const wanted = Number.isFinite(Number(side)) ? Math.round(Number(side)) : DEFAULT_TILE;
  const bounded = Math.max(MIN_TILE, Math.min(MAX_TILE, wanted));
  return Math.min(bounded, natural.width, natural.height);
}

/**
 * Where that square lands in the source, in source pixels. Mirrors `_tile`.
 *
 * @param {{width:number, height:number}} natural  the source's own size
 * @param {[number, number]} centre  where it was aimed, in 0..1 of the frame
 * @param {number} [side]  how much of the source to cover
 * @returns {{left:number, top:number, side:number}}
 */
export function tileRect(natural, centre, side = DEFAULT_TILE) {
  const cut = tileSide(natural, side);
  const clamp = (value) => Math.min(Math.max(0, value), 1);
  const left = Math.round(clamp(centre[0]) * natural.width - cut / 2);
  const top = Math.round(clamp(centre[1]) * natural.height - cut / 2);
  return {
    left: Math.max(0, Math.min(left, natural.width - cut)),
    top: Math.max(0, Math.min(top, natural.height - cut)),
    side: cut,
  };
}

/** The same rectangle as shares of the frame, which is what a CSS box wants. */
export function tileShare(natural, centre, side = DEFAULT_TILE) {
  const rect = tileRect(natural, centre, side);
  return {
    left: rect.left / natural.width,
    top: rect.top / natural.height,
    width: rect.side / natural.width,
    height: rect.side / natural.height,
  };
}

"""Alpha bleed: colour pushed into the texels nobody sees (spec §6.2).

A fully transparent texel still has a colour, and a bilinear sample, a mip
level or a rotated sprite blends it into the edge. A paint program leaves it
black, so a scaled sprite grows a dark rim. The fix is to give every
transparent texel the colour of the nearest visible edge; alpha is left
exactly as it was.

**Push–pull, not dilation.** Growing the edge one texel per pass takes as many
passes as the widest gap — hundreds on a 1024 master with a small figure in
the middle. Push–pull does the whole picture in one pyramid: average the
visible colour down, weighted by coverage, until one texel is left; then on
the way back up, fill each level's holes from the level below. The near edge
dominates, the far gaps get a smooth average, and it costs a few array passes.
The same fill closes the holes a UV projection leaves (§7.4.5).
"""

import numpy as np


def push_pull(colour, weight):
    """Fill where `weight` is 0 from where it is not.

    `colour` is H × W × C float, `weight` H × W in 0…1. Returns the filled
    colour; texels with full weight keep theirs exactly.
    """
    height, width = weight.shape
    if weight.max() <= 0:
        return colour.copy()
    if height == 1 and width == 1:
        return colour.copy()
    # Pad to even so each 2×2 block is whole; padding carries no weight.
    ph, pw = height + height % 2, width + width % 2
    c = np.zeros((ph, pw, colour.shape[2]), np.float64)
    w = np.zeros((ph, pw), np.float64)
    c[:height, :width] = colour * weight[..., None]
    w[:height, :width] = weight
    # Push: premultiplied sums of each 2×2 block.
    cs = c.reshape(ph // 2, 2, pw // 2, 2, -1).sum(axis=(1, 3))
    ws = w.reshape(ph // 2, 2, pw // 2, 2).sum(axis=(1, 3))
    coarse = np.where(ws[..., None] > 0, cs / np.maximum(ws, 1e-12)[..., None], 0)
    coarse = push_pull(coarse, np.minimum(ws, 1.0))
    # Pull: the coarse level, up again, under what this level already had.
    up = coarse.repeat(2, axis=0).repeat(2, axis=1)[:height, :width]
    return colour * weight[..., None] + up * (1 - weight[..., None])


def bleed(rgba):
    """Every transparent texel coloured from its nearest visible neighbours."""
    alpha = rgba[..., 3]
    if alpha.min() == 255 or alpha.max() == 0:
        return rgba.copy()
    visible = (alpha > 0).astype(np.float64)
    filled = push_pull(rgba[..., :3].astype(np.float64), visible)
    out = rgba.copy()
    hidden = alpha == 0
    out[..., :3][hidden] = np.clip(filled[hidden].round(), 0, 255).astype(np.uint8)
    return out

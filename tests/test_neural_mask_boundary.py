"""The final DLSS colour/detail recipe must obey the mask, not just its head.

CPU-only production composition and temporal sessions; a deterministic head
stands in for the network. No downloaded weights or GPU are used.
"""

import numpy as np

import layout
from harness import check

port = layout.load("mlxdlss").mlxdlss
source = np.full((64, 64, 3), 0.5, dtype=np.float32)
mask = np.ones_like(source)
mask[:, :32] = 0
soft = np.full_like(source, 0.25)


class Network:
    def __init__(self, head=0.4):
        self.head = head

    def run_features(self, features):
        out = np.full((*features.shape[:2], 4), self.head, dtype=np.float32)
        out[..., 3] = 0
        return out


pipeline = object.__new__(port.NeuralRenderingPipeline)
pipeline.run_features = Network().run_features


def still(control, detail, colour, intensity=1):
    prepared = pipeline.prepare(source, control_mask=control)
    return pipeline.finish(prepared, pipeline.run_features(prepared.features),
                           detail_strength=detail, colour_strength=colour,
                           intensity=intensity).image


for detail, colour in [(1.25, 0), (1, 1), (0.5, 1.5)]:
    out = still(mask, detail, colour)
    check(f"still {detail}/{colour}: zero mask is exact source",
          np.array_equal(out[:, :32], source[:, :32]), True)
    raw = still(None, detail, colour)
    soft_out = still(soft, detail, colour)
    check(f"still {detail}/{colour}: fractional mask applied once",
          np.allclose(soft_out, source + 0.25 * (raw - source), atol=1e-6), True)
    check("zero intensity is exact source",
          np.array_equal(still(mask, detail, colour, 0), source), True)

    options = port.TemporalOptions(detail_strength=detail, colour_strength=colour,
                                   scene_cut_threshold=0)
    sequence = port.TemporalSession(Network(), options=options, motion="zero")
    for frame_index in range(3):
        out = sequence.process(source, control_mask=mask)
        check(f"temporal {detail}/{colour} frame {frame_index}: outside unchanged",
              np.array_equal(out[:, :32], source[:, :32]), True)
        check("temporal history outside is also source",
              np.array_equal(sequence.history[:, :32], source[:, :32]), True)

    # The first temporal frame and still path share the same mask semantics.
    sequence = port.TemporalSession(Network(), options=options, motion="zero")
    check("soft mask first temporal frame equals still",
          np.allclose(sequence.process(source, control_mask=soft), soft_out, atol=1e-6), True)

check("fully masked still remains the original recipe",
      np.allclose(still(np.ones_like(source), 1.25, 0), still(None, 1.25, 0), atol=1e-6), True)

# Intensity belongs before detail/colour clipping, just as in unmasked runs.
# Moving it into the final mask blend changes saturated highlights/shadows.
for level, residual in [(0.95, 0.4), (0.05, -0.4)]:
    source = np.full_like(source, level)
    network = Network(residual)
    pipeline.run_features = network.run_features
    for intensity in (0, 0.25, 0.5, 1):
        raw = still(None, 1.25, 1.5, intensity)
        check(f"saturated still {level}/{intensity}: white mask preserves recipe",
              np.allclose(still(np.ones_like(source), 1.25, 1.5, intensity), raw, atol=1e-6), True)
        check(f"saturated still {level}/{intensity}: soft mask is applied once",
              np.allclose(still(soft, 1.25, 1.5, intensity),
                          source + 0.25 * (raw - source), atol=1e-6), True)
        options = port.TemporalOptions(detail_strength=1.25, colour_strength=1.5,
                                       intensity=intensity, scene_cut_threshold=0)
        masked = port.TemporalSession(network, options=options, motion="zero")
        unmasked = port.TemporalSession(network, options=options, motion="zero")
        for frame_index in range(3):
            check(f"saturated temporal {level}/{intensity}/{frame_index}: white mask preserves recipe",
                  np.allclose(masked.process(source, control_mask=np.ones_like(source)),
                              unmasked.process(source), atol=1e-6), True)

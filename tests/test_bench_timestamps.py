"""CPU/PyAV regressions for the bench's source display intervals (#54).

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python tests/test_bench_timestamps.py

No weights are loaded: the image operator is the identity, but the fixtures,
transcode and inspection are real encodes/decodes, not mocked timestamps.
"""

import os
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI")))
import av
import numpy as np
import layout

bench = layout.load("bench", package="bench_timestamp_tests").bench


def video_file(path, stamps, rate=24, rotation=None):
    with av.open(str(path), "w") as out:
        video = out.add_stream("libx264", rate=rate)
        video.width, video.height, video.pix_fmt = 64, 32, "yuv420p"
        video.codec_context.time_base = Fraction(1, 24000)
        video.options = {"crf": "1", "bf": "0"}
        if rotation is not None:
            video.set_display_rotation(rotation)
        for when, level in stamps:
            pixels = np.full((32, 64, 3), level, np.uint8)
            pixels[:16, :32] = min(255, level + 40)
            frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            frame.pts = round(when * 24000)
            frame.time_base = Fraction(1, 24000)
            out.mux(video.encode(frame))
        out.mux(video.encode(None))


def inspect(path):
    with av.open(str(path)) as source:
        stream = source.streams.video[0]
        duration = float(stream.duration * stream.time_base)
        frames = [(frame.time, frame.to_ndarray(format="rgb24"))
                  for frame in source.decode(stream)]
    return duration, frames


class BenchTimestamps(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.directory = Path(self.scratch.name)
        self.source = self.directory / "sparse.mp4"
        video_file(self.source, [(float(i), 20 + 25 * i) for i in (0, 1, 2, 3, 4, 6)])

    def transcode(self, source=None, **kwargs):
        name = bench.transcode(str(source or self.source), str(self.directory), "out",
                               work=lambda frames: frames, **kwargs)
        return inspect(self.directory / name)

    def test_still_uses_frame_showing_at_fractional_mark(self):
        expected = dict(inspect(self.source)[1])[2.0]
        np.testing.assert_array_equal(bench.video_frame(str(self.source), 2.5), expected)
        np.testing.assert_array_equal(bench.video_frame(str(self.source), 2.0), expected)

    def test_trim_clips_last_frames_display_interval(self):
        duration, frames = self.transcode(trim=(0.0, 5.5))
        self.assertAlmostEqual(duration, 5.5, places=4)
        self.assertEqual([at for at, _ in frames], [0, 1, 2, 3, 4])

    def test_whole_cut_inside_one_held_frame(self):
        duration, frames = self.transcode(trim=(4.75, 5.5))
        self.assertAlmostEqual(duration, 0.75, places=4)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0][0], 0.0)
        self.assertLess(np.abs(frames[0][1].astype(float) -
                               dict(inspect(self.source)[1])[4.0]).mean(), 2)

    def test_both_trim_edges_cross_held_intervals(self):
        duration, frames = self.transcode(trim=(2.5, 3.5), chunk=4, overlap=2)
        self.assertAlmostEqual(duration, 1.0, places=4)
        self.assertEqual([at for at, _ in frames], [0, 0.5])

    def test_full_vfr_keeps_timing_and_last_duration(self):
        expected, original = inspect(self.source)
        duration, frames = self.transcode(chunk=4, overlap=2)
        self.assertAlmostEqual(duration, expected, places=4)
        self.assertEqual([at for at, _ in frames], [at for at, _ in original])

    def test_cfr_trim_chunk_overlap_and_rotation(self):
        source = self.directory / "phone.mp4"
        video_file(source, [(i / 24, 20 + i) for i in range(24)], rotation=-90)
        duration, frames = self.transcode(source, trim=(0.25, 0.75), chunk=4, overlap=2)
        self.assertAlmostEqual(duration, 0.5, places=4)
        self.assertEqual(len(frames), 12)
        self.assertEqual(frames[0][1].shape[:2], (64, 32))
        self.assertEqual(bench.video_frame(str(source), 0.25).shape[:2], (64, 32))

    def test_past_end_raises_useful_error_without_partial_file(self):
        before = sorted(self.directory.iterdir())
        with self.assertRaisesRegex(bench.BenchError, "no frames"):
            self.transcode(trim=(7.0, 8.0))
        self.assertEqual(sorted(self.directory.iterdir()), before)

    def test_single_frame_and_trim_past_eof_are_bounded_by_the_file(self):
        source = self.directory / "one.mp4"
        video_file(source, [(0, 80)])
        duration, frames = self.transcode(source, trim=(0.0, 2.0))
        self.assertAlmostEqual(duration, 1 / 24, places=4)
        self.assertEqual(len(frames), 1)
        expected, original = inspect(self.source)
        duration, frames = self.transcode(trim=(6.0, 20.0))
        self.assertAlmostEqual(duration, expected - 6, places=4)
        self.assertEqual(len(frames), 1)
        np.testing.assert_array_equal(bench.video_frame(str(self.source), 20), original[-1][1])


if __name__ == "__main__":
    unittest.main()

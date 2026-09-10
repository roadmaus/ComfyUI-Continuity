"""Real audio packet gaps and delayed starts survive reel/bench writes (#54).

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python tests/test_audio_timestamps.py

Lossless synthetic inputs distinguish missing packets from encoded silence;
the output is decoded AAC and checked in windows away from codec priming.
"""

import os
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI")))
import av
import numpy as np
import layout

pkg = layout.load("bench", "mux", package="audio_timestamp_tests")
bench, mux = pkg.bench, pkg.mux


def audio_video(path, spans, rate=48000, channels=2, seconds=3, packet_samples=1000):
    """Only `spans` contain audio packets; everything else is a timestamp gap."""
    with av.open(str(path), "w") as out:
        video = out.add_stream("libx264", rate=24)
        video.width, video.height, video.pix_fmt = 64, 32, "yuv420p"
        audio = out.add_stream("pcm_f32le", rate=rate)
        audio.layout = "stereo" if channels == 2 else "mono"
        for i in range(round(seconds * 24)):
            frame = av.VideoFrame.from_ndarray(np.full((32, 64, 3), 80, np.uint8), "rgb24")
            frame.pts, frame.time_base = i, Fraction(1, 24)
            out.mux(video.encode(frame))
        for start, stop in spans:
            first, final = round(start * rate), round(stop * rate)
            for offset in range(first, final, packet_samples):
                count = min(packet_samples, final - offset)
                tone = (0.25 * np.sin(2 * np.pi * 440 * np.arange(offset, offset + count) / rate))
                data = np.tile(tone.astype(np.float32), (channels, 1))
                frame = av.AudioFrame.from_ndarray(data, format="fltp", layout=audio.layout.name)
                frame.sample_rate = rate
                frame.pts, frame.time_base = offset, Fraction(1, rate)
                out.mux(audio.encode(frame))
        out.mux(audio.encode(None))
        out.mux(video.encode(None))


def decoded_audio(path):
    with av.open(str(path)) as source:
        frames = list(source.decode(audio=0))
        return np.concatenate([frame.to_ndarray() for frame in frames], axis=-1), frames[0].sample_rate


def rms(samples, rate, start, stop):
    window = samples[..., round(start * rate):round(stop * rate)]
    return float(np.sqrt(np.mean(window.astype(np.float64) ** 2)))


class AudioTimestamps(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.directory = Path(self.scratch.name)

    def write_output(self, source, route, start=0.0, duration=3.0):
        if route == "bench":
            name = bench.transcode(str(source), str(self.directory), "bench",
                                   work=lambda frames: frames, keep_sound=True,
                                   trim=(start, start + duration), chunk=4, overlap=2)
            return self.directory / name
        output = self.directory / "reel.mp4"
        mux.write(str(output), [{"clip": {"path": str(source), "start": start,
                  "duration": duration, "width": 64, "height": 32,
                  "sound": True, "rate": 48000, "channels": 2}}], fps=24, crf=1)
        return output

    def test_internal_gap_and_initial_delay_in_both_writers(self):
        for label, spans, levels in [
            ("gap", [(0, 1), (2, 3)], [True, False, True]),
            ("late", [(1, 3)], [False, True, True]),
            ("continuous", [(0, 3)], [True, True, True]),
        ]:
            source = self.directory / f"{label}.mkv"
            audio_video(source, spans)
            for route in ("reel", "bench"):
                with self.subTest(source=label, route=route):
                    samples, rate = decoded_audio(self.write_output(source, route))
                    for second, audible in enumerate(levels):
                        level = rms(samples, rate, second + 0.1, second + 0.9)
                        self.assertGreater(level, 0.1) if audible else self.assertLess(level, 0.002)

    def test_trim_rebases_gap_and_clips_partial_audio_blocks(self):
        source = self.directory / "trim.mkv"
        audio_video(source, [(0, 1), (2, 3)])
        for route in ("reel", "bench"):
            with self.subTest(route=route):
                samples, rate = decoded_audio(self.write_output(source, route, 0.75, 1.5))
                self.assertGreater(rms(samples, rate, 0.05, 0.2), 0.1)
                self.assertLess(rms(samples, rate, 0.35, 1.15), 0.002)
                self.assertGreater(rms(samples, rate, 1.3, 1.45), 0.1)
                self.assertLessEqual(samples.shape[-1], round(1.5 * rate) + 1024)

    def test_resampling_mono_preserves_gaps_and_duration(self):
        source = self.directory / "mono.mkv"
        audio_video(source, [(0, 1), (2, 3)], rate=44100, channels=1)
        target = SimpleNamespace(rate=48000, layout="stereo", channels=2)
        samples = mux._clip_sound(av, str(source), {}, 0.25, 2.5, target).numpy()
        self.assertEqual(samples.shape, (2, 120000))
        self.assertGreater(rms(samples, 48000, 0.1, 0.65), 0.1)
        self.assertLess(rms(samples, 48000, 0.9, 1.65), 0.002)
        self.assertGreater(rms(samples, 48000, 1.9, 2.4), 0.1)

    def test_overlapping_packets_do_not_extend_or_shift_the_track(self):
        source = self.directory / "overlap.mkv"
        # Two one-second packets overlap by half a second. Timestamp placement
        # keeps 1.5 seconds of sound, not two seconds followed by a shifted cut.
        audio_video(source, [(0, 1), (0.5, 1.5)], seconds=2, packet_samples=48000)
        for route in ("reel", "bench"):
            with self.subTest(route=route):
                samples, rate = decoded_audio(self.write_output(source, route, duration=2))
                self.assertGreater(rms(samples, rate, 1.1, 1.4), 0.1)
                self.assertLess(rms(samples, rate, 1.65, 1.9), 0.002)

    def test_audio_flush_is_sample_exact_after_rate_conversion(self):
        source = self.directory / "short-mono.mkv"
        audio_video(source, [(0, 1)], rate=44100, channels=1, seconds=1,
                    packet_samples=44100)
        target = SimpleNamespace(rate=48000, layout="stereo", channels=2)
        samples = mux._clip_sound(av, str(source), {}, 0, 0, target).numpy()
        self.assertEqual(samples.shape, (2, 48000))
        self.assertGreater(rms(samples, 48000, 0.95, 0.99), 0.1)

    def test_coarse_container_timestamps_do_not_create_tiny_packet_gaps(self):
        source = self.directory / "rounded-pts.mkv"
        audio_video(source, [(0, 1)], seconds=1)
        target = SimpleNamespace(rate=48000, layout="stereo", channels=2)
        samples = mux._clip_sound(av, str(source), {}, 0, 0, target).numpy()
        expected = (0.25 * np.sin(2 * np.pi * 440 * np.arange(48000) / 48000)).astype(np.float32)
        self.assertEqual(samples.shape, (2, 48000))
        np.testing.assert_array_equal(samples[0], expected)

    def test_later_reel_part_stays_on_its_own_sample_clock(self):
        source = self.directory / "gap-part.mkv"
        audio_video(source, [(0, 1), (2, 3)])
        output = self.directory / "two-parts.mp4"
        clip = {"path": str(source), "start": 0, "duration": 3, "width": 64,
                "height": 32, "sound": True, "rate": 48000, "channels": 2}
        mux.write(str(output), [{"clip": clip}, {"clip": dict(clip)}], fps=24, crf=1)
        samples, rate = decoded_audio(output)
        for second, audible in enumerate([True, False, True] * 2):
            level = rms(samples, rate, second + 0.1, second + 0.9)
            self.assertGreater(level, 0.1) if audible else self.assertLess(level, 0.002)


if __name__ == "__main__":
    unittest.main()

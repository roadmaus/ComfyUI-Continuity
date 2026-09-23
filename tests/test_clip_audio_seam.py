"""A supplied clip's sound seam reads the same source clock as its reel.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python tests/test_clip_audio_seam.py

Real lossless clips cover missing packets, an initial delay and trimmed head /
tail windows. No model, GPU or running ComfyUI server is needed.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import layout
from harness import died, passed, skip

COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
sys.path.insert(0, COMFY)
try:
    import av
    import numpy as np
    # Model-management imports happen below; these media-only checks need no
    # CUDA device even when the installed core normally starts on one.
    saved_argv = sys.argv
    sys.argv = [sys.argv[0], "--cpu", "--base-directory", os.environ.get("COMFYUI_BASE", COMFY)]
    import comfy.options
    comfy.options.enable_args_parsing()
    import comfy.cli_args
    sys.argv = saved_argv
    import folder_paths  # noqa: F401
except ImportError as exc:
    skip(f"ComfyUI / PyAV not importable: {exc}")

media = layout.load("media", package="clip_audio_seam_tests").media
# The reel regression's fixture writes packets at their real source PTS.
from test_audio_timestamps import audio_video, rms
passed("all clip audio seam tests passed")


class ClipAudioSeam(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.directory = Path(self.scratch.name)
        resolver = patch.object(media, "resolve", side_effect=lambda name: name)
        resolver.start()
        self.addCleanup(resolver.stop)

    def read(self, path, seconds, at, start=0, duration=3):
        return media.clip_audio({"filename": str(path), "start": start,
                                 "duration": duration}, seconds, at)

    def test_delayed_gapped_and_continuous_head_and_tail(self):
        for label, spans, head_sound in [
            ("late", [(1, 3)], False),
            ("gap", [(0, 1), (2, 3)], True),
            ("continuous", [(0, 3)], True),
        ]:
            path = self.directory / f"{label}.mkv"
            audio_video(path, spans)
            for at, audible in [("head", head_sound), ("tail", True)]:
                with self.subTest(source=label, at=at):
                    got = self.read(path, 1, at)
                    self.assertEqual(got["sample_rate"], 48000)
                    self.assertEqual(tuple(got["waveform"].shape), (1, 2, 48000))
                    level = rms(got["waveform"].numpy(), 48000, 0.1, 0.9)
                    self.assertGreater(level, 0.1) if audible else self.assertLess(level, 0.002)

    def test_trimmed_windows_keep_gap_source_rate_and_layout(self):
        for rate, channels in [(48000, 2), (44100, 1)]:
            path = self.directory / f"trim-{rate}.mkv"
            audio_video(path, [(0, 1), (2, 3)], rate=rate, channels=channels)
            for at in ("head", "tail"):
                with self.subTest(rate=rate, at=at):
                    got = self.read(path, 0.75, at, start=0.75, duration=1.5)
                    self.assertEqual(got["sample_rate"], rate)
                    self.assertEqual(tuple(got["waveform"].shape), (1, channels, round(0.75 * rate)))
                    samples = got["waveform"].numpy()
                    early, late = rms(samples, rate, 0.05, 0.2), rms(samples, rate, 0.55, 0.7)
                    self.assertGreater(early if at == "head" else late, 0.1)
                    self.assertLess(late if at == "head" else early, 0.002)

    def test_tail_is_bounded_and_does_not_decode_the_whole_track(self):
        path = self.directory / "bounded.mkv"
        audio_video(path, [(0, 3)])
        with patch.object(media, "load_audio", side_effect=AssertionError("whole track reader")), \
                patch.object(media.mux, "sound_blocks", wraps=media.mux.sound_blocks) as reader:
            got = self.read(path, 0.25, "tail", start=1, duration=1.5)
        self.assertEqual(tuple(got["waveform"].shape), (1, 2, 12000))
        args = reader.call_args.args
        self.assertEqual(args[1:5], (str(path), 2.25, 0.25, 48000))

    def test_tail_longer_than_clip_is_clamped_to_its_window(self):
        path = self.directory / "short.mkv"
        audio_video(path, [(0, 3)])
        for at in ("head", "tail"):
            got = self.read(path, 1, at, start=2, duration=0.5)
            self.assertEqual(tuple(got["waveform"].shape), (1, 2, 24000))
            self.assertGreater(rms(got["waveform"].numpy(), 48000, 0.1, 0.4), 0.1)

    def test_compressed_aac_windows_keep_rate_layout_and_silence(self):
        for rate, channels in [(32000, 1), (48000, 1), (48000, 2)]:
            with self.subTest(rate=rate, channels=channels):
                source = self.directory / f"aac-source-{rate}-{channels}.mkv"
                audio_video(source, [(0, 1), (2, 3)], rate=rate, channels=channels)
                path = source.with_suffix(".mp4")
                media.mux.write(str(path), [{"clip": {
                    "path": str(source), "start": 0, "duration": 3,
                    "width": 64, "height": 32, "sound": True,
                    "rate": rate, "channels": channels}}], fps=24, crf=1)
                with av.open(str(path)) as container:
                    self.assertEqual(container.streams.audio[0].codec_context.name, "aac")
                for at in ("head", "tail"):
                    got = self.read(path, 1, at)
                    self.assertEqual(got["sample_rate"], rate)
                    self.assertEqual(tuple(got["waveform"].shape), (1, channels, rate))
                    self.assertGreater(rms(got["waveform"].numpy(), rate, 0.1, 0.9), 0.1)
                silent = self.read(path, 0.5, "head", start=1, duration=1)
                self.assertEqual(tuple(silent["waveform"].shape), (1, channels, rate // 2))
                self.assertLess(rms(silent["waveform"].numpy(), rate, 0.1, 0.4), 0.002)

    def test_file_without_audio_is_still_refused(self):
        path = self.directory / "silent.mkv"
        with av.open(str(path), "w") as out:
            video = out.add_stream("libx264", rate=24)
            video.width, video.height, video.pix_fmt = 64, 32, "yuv420p"
            frame = av.VideoFrame.from_ndarray(np.zeros((32, 64, 3), np.uint8), "rgb24")
            out.mux(video.encode(frame))
            out.mux(video.encode(None))
        with self.assertRaisesRegex(media.MediaError, "No audio stream found"):
            self.read(path, 1, "tail")

    def test_empty_window_never_becomes_an_unbounded_read(self):
        with patch.object(media.mux, "sound_blocks") as reader:
            with self.assertRaisesRegex(media.MediaError, "audio window is empty"):
                self.read("empty.mkv", 1, "tail", duration=0)
        reader.assert_not_called()


if __name__ == "__main__":
    result = unittest.main(exit=False).result
    if not result.wasSuccessful():
        died("clip audio seam regression failed")

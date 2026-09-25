"""Raylight sound seams use core's real audio guides, without a local wrapper.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python tests/test_raylight_audio_seam.py

CPU only: real compiler, encoder, payload helpers and PackedLayout; small fake
CLIP/VAE objects replace weights. This verifies conditioning and coordinates,
not Ray workers or a sampled soundtrack.
"""

import json
import os
from pathlib import Path
import sys
import unittest
from dataclasses import replace
from unittest.mock import patch

import layout
from harness import died, passed, skip

comfy = Path(os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI")))
if not (comfy / "folder_paths.py").is_file():
    skip("set COMFYUI_PATH to a ComfyUI installation")
sys.path.insert(0, str(comfy))
sys.argv = ["test_raylight_audio_seam", "--cpu"]
import comfy.cli_args  # noqa: E402
comfy.cli_args.args.cpu = True
comfy.cli_args.args.base_directory = os.environ.get("COMFYUI_BASE", str(comfy))
import torch  # noqa: E402
from comfy.ldm.minimax.model import PackedLayout  # noqa: E402

pkg = layout.load("compile", "encode", "payload", "raylight", "h3_segment",
                  package="raylight_audio_seam_tests")
compiler, encoder, repair, ray = pkg.compile, pkg.encode, pkg.payload, pkg.raylight
if not repair.CORE_AUDIO_ANCHORS:
    skip("this core does not support native audio anchors")

TEXT_LEN = 7


class Clip:
    def tokenize(self, prompt, **kwargs):
        self.presentation = kwargs
        return "tokens"

    def encode_from_tokens_scheduled(self, tokens):
        return [[torch.zeros(1, TEXT_LEN, 8), {}]]


class Vae:
    def encode(self, images):
        covered, steps = 0, 0
        while covered < images.shape[0]:
            covered += encoder.FRAME_PER_TOKEN[steps % 5]
            steps += 1
        return torch.zeros(1, 24, steps, 4, 4)


class AudioVae:
    audio_sample_rate = 32000

    def encode(self, waveform):
        return torch.zeros(1, 32, 2, max(1, round(waveform.shape[1] / 800)))


def audio(steps):
    return {"waveform": torch.zeros(1, 2, steps * 800), "sample_rate": 32000}


def seam(steps, end):
    return {"kind": "audio", "ref_audio_t": steps,
            "audio_latent": torch.zeros(1, 32, 2, steps), repair.AUDIO_END_KEY: end}


def packed(values):
    return PackedLayout(TEXT_LEN, 8, 4, 4, 12,
                        keyframes=values.get("minimax_keyframes"),
                        refs=values.get("minimax_refs"))


def relative_times(packing, kind):
    origin = repair._target_origin(packing)
    return [packing.position_ids[a:b, 0] - origin
            for a, b, found in packing.segments if found == kind]


def compiled(*, refs=False, feather=22, ends=False):
    assets = ([{"handle": "img-1", "kind": "image", "role": "reference",
                "filename": "face.png"},
               {"handle": "aud-1", "kind": "audio", "role": "reference",
                "filename": "voice.wav"}] if refs else [])
    result = compiler.compile_request(
        {"prompt": "a room @img-1 @aud-1" if refs else "a room", "duration_s": 6,
         "aspect": "1:1", "short_edge": 384, "assets": assets},
        continues=True, continues_audio=True, feather=feather,
        ends_on=ends, ends_on_audio=ends, ends_feather=22 if ends else 1)
    # Tiny pixel and latent fixtures, with the real compiler's seam metadata.
    return replace(result, width=64, height=64)


def encode_case(request, native, masked=False):
    loaded = {
        encoder.PREV_FRAME: {"image": torch.zeros(39, 64, 64, 3)},
        encoder.PREV_AUDIO: {"audio": audio(37)},
        encoder.NEXT_FRAME: {"image": torch.zeros(22, 64, 64, 3)},
        encoder.NEXT_AUDIO: {"audio": audio(40)},
        "aud-1": {"audio": audio(5)},
        "img-1": {"image": torch.zeros(1, 64, 64, 3)},
    }
    if masked:
        loaded[encoder.PREV_LATENT] = {"latent": torch.ones(1, 24, 12, 4, 4)}
    clip = Clip()
    # File stamps/cache storage are unrelated to the in-memory reference.
    with patch.object(encoder, "_ref_key", return_value=None):
        cond, latent = encoder.encode(clip, Vae(), AudioVae(), request, loaded,
                                      native_audio_seams=native, masked_seam=masked)
    return cond[0][1], latent, clip.presentation


class NativeAudioSeam(unittest.TestCase):
    def test_real_layout_matches_repaired_end_alignment(self):
        video = {"resolved_frame_index": 0, "latent": torch.zeros(1, 24, 1, 4, 4)}
        ordinary = [
            {"kind": "image", "latent_h": 4, "latent_w": 4},
            {"kind": "audio", "ref_audio_t": 5},
            {"kind": "video", "latent_t": 2, "latent_h": 4,
             "latent_w": 4, "ref_audio_t": 0},
        ]
        for end in (0, 5, 22, 39, 175):
            for steps in (37, 40):
                with self.subTest(end=end, steps=steps):
                    ref = seam(steps, end)
                    guide = repair.seam_audio_keyframe(ref)
                    old_refs = [*ordinary, ref]
                    old = PackedLayout(TEXT_LEN, 8, 4, 4, 12,
                                       keyframes=[video], refs=old_refs)
                    repair._reposition(old, {"keyframes": [video], "refs": old_refs})
                    new = PackedLayout(TEXT_LEN, 8, 4, 4, 12,
                                       keyframes=[video, guide], refs=ordinary)
                    torch.testing.assert_close(relative_times(new, "cond_audio")[0],
                                               relative_times(old, "ref_audio")[-1])
                    self.assertIs(guide["audio_latent"], ref["audio_latent"])
                    self.assertEqual(set(guide), {"resolved_frame_index", "audio_latent"})
                    self.assertEqual(ref[repair.AUDIO_END_KEY], end)
        ref = seam(37, 22)
        ref["ref_audio_t"] = 999  # stale metadata cannot change native guide length
        self.assertAlmostEqual(repair.seam_audio_keyframe(ref)["resolved_frame_index"],
                               -0.2)

    def test_both_encoder_roads_and_both_ends(self):
        for refs in (False, True):
            for feather in (5, 22, 39):
                with self.subTest(refs=refs, feather=feather):
                    request = compiled(refs=refs, feather=feather, ends=True)
                    old, old_latent, old_presentation = encode_case(request, False)
                    new, new_latent, new_presentation = encode_case(request, True)
                    old_layout, new_layout = packed(old), packed(new)
                    repair._reposition(old_layout, {
                        "keyframes": old.get("minimax_keyframes", []),
                        "refs": old.get("minimax_refs", []),
                    })
                    actual = relative_times(new_layout, "cond_audio")
                    expected = relative_times(old_layout, "ref_audio")[-2:]
                    self.assertEqual(len(actual), 2)
                    for got, want in zip(actual, expected):
                        torch.testing.assert_close(got, want)
                    self.assertFalse(repair._needs_reposition({
                        "keyframes": new.get("minimax_keyframes", []),
                        "refs": new.get("minimax_refs", []),
                    }))
                    self.assertEqual(len(new.get("minimax_refs", [])), 2 if refs else 0)
                    self.assertEqual(old_presentation.keys(), new_presentation.keys())
                    for old_stream, new_stream in zip(old_latent["samples"].unbind(),
                                                      new_latent["samples"].unbind()):
                        torch.testing.assert_close(old_stream, new_stream)
                    self.assertEqual(set(old_latent), set(new_latent))
                    for got, want in zip(relative_times(new_layout, "cond"),
                                         relative_times(old_layout, "cond")):
                        torch.testing.assert_close(got, want)

    def test_unblended_reference_and_presentation_stay_unchanged(self):
        for refs in (False, True):
            with self.subTest(refs=refs):
                request = compiled(refs=refs, feather=1)
                old, _, old_presentation = encode_case(request, False)
                new, _, new_presentation = encode_case(request, True)
                self.assertEqual(len(new["minimax_refs"]), len(old["minimax_refs"]))
                self.assertFalse(any("audio_latent" in k
                                     for k in new.get("minimax_keyframes", [])))
                self.assertEqual(old_presentation.keys(), new_presentation.keys())
                if "minimax_ref_items" in old_presentation:
                    self.assertEqual([i["type"] for i in old_presentation["minimax_ref_items"]],
                                     [i["type"] for i in new_presentation["minimax_ref_items"]])

    def test_scheduled_entries_preserve_original_metadata_and_reference_order(self):
        a, b = seam(37, 22), seam(40, 175)
        voice = {"kind": "audio", "ref_audio_t": 5,
                 "audio_latent": torch.zeros(1, 32, 2, 5)}
        image = {"kind": "image", "latent_h": 4, "latent_w": 4}
        video = {"resolved_frame_index": 0, "latent": torch.zeros(1, 24, 1, 4, 4)}
        refs, guides = [voice, a, image, b], [video]
        meta = {"minimax_refs": refs, "minimax_keyframes": guides,
                "start_percent": 0.25, "end_percent": 0.75}
        untouched = {"minimax_refs": [voice], "start_percent": 0.75}
        tensors = [torch.zeros(1, TEXT_LEN, 8) for _ in range(3)]
        source = [[tensors[0], meta], [tensors[1], meta], [tensors[2], untouched]]
        result = encoder._native_audio_seams(source)
        self.assertIs(meta["minimax_refs"], refs)
        self.assertEqual([id(r) for r in refs], [id(voice), id(a), id(image), id(b)])
        self.assertEqual(guides, [video])
        for i in (0, 1):
            self.assertIs(result[i][0], tensors[i])
            self.assertIsNot(result[i][1], meta)
            self.assertEqual(result[i][1]["start_percent"], 0.25)
            self.assertEqual(result[i][1]["end_percent"], 0.75)
            self.assertEqual([id(r) for r in result[i][1]["minimax_refs"]],
                             [id(voice), id(image)])
            self.assertEqual(len(result[i][1]["minimax_keyframes"]), 3)
            self.assertIs(result[i][1]["minimax_keyframes"][1]["audio_latent"], a["audio_latent"])
            self.assertIs(result[i][1]["minimax_keyframes"][2]["audio_latent"], b["audio_latent"])
        self.assertIsNot(result[0][1]["minimax_keyframes"], result[1][1]["minimax_keyframes"])
        self.assertIs(result[2][1], untouched)

    def test_native_conversion_preserves_masked_video_seam(self):
        request = compiled()
        _, old, _ = encode_case(request, False, masked=True)
        _, new, _ = encode_case(request, True, masked=True)
        for name in ("samples", "noise_mask"):
            for got, want in zip(new[name].unbind(), old[name].unbind()):
                torch.testing.assert_close(got, want)
        video_mask, audio_mask = new["noise_mask"].unbind()
        self.assertEqual(float(video_mask[:, :, :7].sum()), 0.0)
        self.assertEqual(float(video_mask[:, :, 7:].min()), 1.0)
        self.assertEqual(float(audio_mask.min()), 1.0)

    def test_unsupported_core_keeps_guard_and_encoder_refusal(self):
        request = compiled(ends=True)
        with self.assertRaisesRegex(ValueError, "sound seam"):
            ray.refuse_run(request, False)
        ray.refuse_run(request, False, audio_anchors=True)
        with patch.object(repair, "CORE_AUDIO_ANCHORS", False):
            with self.assertRaisesRegex(ValueError, "native audio timeline anchors"):
                encode_case(request, True)
            old, _, _ = encode_case(request, False)
            self.assertTrue(any(repair.AUDIO_END_KEY in r for r in old["minimax_refs"]))

    def test_segment_selects_native_encoding_only_for_ray(self):
        segment = pkg.h3_segment
        data = json.dumps({"request": {"prompt": "a room", "duration_s": 6},
                           "continue": True, "continue_audio": True, "feather": 22})
        model = object()
        for backend, native, wrapped in (("raylight", True, 0), ("", False, 1)):
            with self.subTest(backend=backend), \
                    patch.object(segment.media, "load_all", return_value={}), \
                    patch.object(segment.lora, "apply", side_effect=lambda value, *a, **k: value), \
                    patch.object(repair, "repair", side_effect=lambda value: value) as wrapper, \
                    patch.object(encoder, "encode", return_value=([], {})) as encode:
                segment.MiniMaxH3TimelineSegment.execute(
                    Clip(), data, vae=Vae(), audio_vae=AudioVae(),
                    model_fl2va=model, model_ref2va=model, sampler_backend=backend,
                    prev_image=torch.zeros(22, 64, 64, 3), prev_audio=audio(37))
                self.assertIs(encode.call_args.kwargs["native_audio_seams"], native)
                self.assertEqual(wrapper.call_count, wrapped)

    def test_payload_probe_rejects_dropped_and_reordered_latents(self):
        from comfy.model_base import MiniMaxH3

        self.assertTrue(repair._supports_audio_payload())
        for name, action in (
                ("cond_audio_latents", lambda values: values[-1:]),
                ("cond_video_latents", lambda values: values[-1:]),
                ("cond_audio_latents", lambda values: list(reversed(values)))):
            class BrokenPayload(MiniMaxH3):
                def extra_conds(self, **kwargs):
                    values = super().extra_conds(**kwargs)
                    payload = values["minimax_payload"].cond
                    payload[name] = action(payload[name])
                    return values

            with self.subTest(field=name, action=action):
                self.assertFalse(repair._supports_audio_payload(BrokenPayload))

        class MissingPayload:
            def extra_conds(self, **kwargs):
                raise TypeError("old payload")
        self.assertFalse(repair._supports_audio_payload(MissingPayload))

    def test_capability_probe_rejects_incompatible_layouts(self):
        self.assertTrue(repair._supports_audio_anchors())

        def broken(fault):
            def construct(*args, **kwargs):
                value = PackedLayout(*args, **kwargs)
                fault(value)
                return value
            return construct

        def missing_audio(value):
            value.segments = [s for s in value.segments if s[2] != "cond_audio"]

        def rounded_audio(value):
            for a, b, kind in value.segments:
                if kind == "cond_audio":
                    value.position_ids[a:b, 0].round_()

        def wrong_stereo(value):
            a, b, _ = next(s for s in value.segments if s[2] == "cond_audio")
            value.position_ids[a:b, 2] = 0

        def generated_audio(value):
            value.audio_update[:] = True

        for fault in (missing_audio, rounded_audio, wrong_stereo, generated_audio):
            with self.subTest(fault=fault.__name__):
                self.assertFalse(repair._supports_audio_anchors(broken(fault)))
        def raises(*args, **kwargs):
            raise TypeError("old layout")
        self.assertFalse(repair._supports_audio_anchors(raises))


if __name__ == "__main__":
    result = unittest.main(argv=[sys.argv[0]], exit=False).result
    if not result.wasSuccessful():
        died("Raylight audio seam regression failed")
    passed("all Raylight audio seam tests passed")

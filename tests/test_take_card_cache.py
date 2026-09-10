"""UI card identities never become generation conditioning cache inputs.

    python tests/test_take_card_cache.py
"""

import copy
import unittest

import layout

compiler = layout.load("compile", package="take_card_cache_tests").compile


class TakeCardCache(unittest.TestCase):
    def test_ids_are_not_part_of_any_timeline_payload(self):
        for family in ("h3", "ltx25"):
            for mode in ("chained", "merged", "single", "clip", "held"):
                with self.subTest(family=family, mode=mode):
                    piece = {"family": family, "render": "chained", "prompt": "one piece",
                             "aspect": "16:9", "short_edge": 480,
                             "segments": [
                                 {"prompt": "first", "duration_s": 5, "assets": [], "loras": []},
                                 {"prompt": "second", "duration_s": 5, "assets": [], "loras": []},
                             ]}
                    if mode == "merged":
                        piece["segments"][1]["merge"] = True
                    elif mode == "single":
                        piece["render"] = "single"
                    elif mode == "clip":
                        piece["segments"][0] = {"kind": "clip", "filename": "footage.mp4",
                                                "duration_s": 5, "width": 832, "height": 480}
                    elif mode == "held":
                        piece["segments"][0].update(hold=True, take={
                            "filename": "held.mp4 [output]", "duration_s": 5,
                            "width": 832, "height": 480, "has_audio": True,
                        })
                    identified = copy.deepcopy(piece)
                    for n, segment in enumerate(identified["segments"]):
                        segment["card_id"] = f"ui-only-{n}"
                    # This is the byte-bearing payload put into each family
                    # segment node, not merely the prompt text after parsing.
                    plain = compiler.timeline_payloads(compiler.rendered_piece(piece))
                    with_ids = compiler.timeline_payloads(compiler.rendered_piece(identified))
                    self.assertEqual(plain, with_ids)


if __name__ == "__main__":
    unittest.main()

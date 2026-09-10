"""Reference size survives pool injection and merged/one-pass serialization.

Runs without ComfyUI or model weights: this is the real compiler's payload
round trip, not a render or a measurement of GPU memory.
"""

import copy

import layout
from harness import check

compiler = layout.load("compile").compile


def video(size):
    return {"handle": "vid-1", "kind": "video", "role": "reference",
            "filename": "motion.mp4", "track": "picture",
            "takes": "motion", "ref_size": size}


for kind in ("image", "video"):
    for size in ("match", "max"):
        raw = {"handle": "ref-1", "kind": kind, "filename": "reference",
               "ref_size": size}
        parsed = compiler._parse_assets([raw])[0]
        restored = compiler._parse_assets([compiler._asset_dict(parsed)])[0]
        check(f"{kind}/{size} round-trips", restored.ref_size, size)

for size in ("match", "max"):
    piece = {"version": 2, "family": "h3", "aspect": "1:1", "short_edge": 480,
             "assets": [video(size)],
             "segments": [{"duration_s": 3, "prompt": "@vid-1 walks."},
                          {"duration_s": 3, "prompt": "@vid-1 waves."}]}
    for location in ("pool", "local"):
        data = copy.deepcopy(piece)
        if location == "local":
            assets = data.pop("assets")
            for segment in data["segments"]:
                segment["assets"] = copy.deepcopy(assets)
        for mode in ("chain", "merge", "one-pass"):
            selected = copy.deepcopy(data)
            if mode == "merge":
                selected["segments"][1]["merge"] = True
            payloads = ([compiler.single_payload(selected)] if mode == "one-pass"
                        else compiler.timeline_payloads(selected))
            for index, payload in enumerate(payloads):
                compiled = compiler.compile_segment(payload)
                check(f"{location}/{mode}/{size} pass {index} keeps video size",
                      [asset.ref_size for asset in compiled.ref_videos], [size])

# Cast motion injects the video without a direct @video citation in the shot.
piece["assets"] = [{"handle": "img-1", "kind": "image", "filename": "face.png"},
                   video("match")]
piece["subjects"] = [{"handle": "anna", "from": ["img-1"], "motion": "vid-1"}]
for segment in piece["segments"]:
    segment["prompt"] = "@anna walks."
for payload in compiler.timeline_payloads(piece):
    check("cast-injected motion keeps match",
          compiler.compile_segment(payload).ref_videos[0].ref_size, "match")

# Retain the existing serialization of max-sized videos: no gratuitous cache
# key change for the common default while repairing explicit match.
check("video max remains explicit", compiler._asset_dict(
    compiler._parse_assets([video("max")])[0])["ref_size"], "max")

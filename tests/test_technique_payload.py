"""Technique provenance remains workflow UI state, never encoder cache input.

The inserted words still reach the model through the ordinary prompt path.
Pure compiler checks only; no ComfyUI, reference files or GPU required.
"""

import copy
import json

import layout
from harness import check

compiler = layout.load("canvas", "contextir", "compile").compile


def metadata(text, name="camera/dolly-in"):
    return {
        "version": 1,
        "source": text,
        "items": [{"id": name, "title": "Dolly In", "text": text,
                   "prefix": "", "start": 0, "end": len(text), "stale": False}],
    }


BASE = {
    "version": 2,
    "prompt": "Soft lighting.",
    "segments": [
        {"prompt": "A person walks.\n\nDolly in slowly.", "duration_s": 6},
        {"prompt": "The person stops.\n\nHold the camera still.", "duration_s": 6},
    ],
}

for render in ("chained", "single", "merged"):
    clean = copy.deepcopy(BASE)
    if render == "single":
        clean["render"] = "single"
    elif render == "merged":
        clean["segments"][1]["merge"] = True
    annotated = copy.deepcopy(clean)
    annotated["techniques"] = metadata(annotated["prompt"], "lighting/soft")
    for segment in annotated["segments"]:
        segment["techniques"] = metadata(segment["prompt"])
    before = copy.deepcopy(annotated)
    expected = compiler.timeline_payloads(clean)
    got = compiler.timeline_payloads(annotated)
    check(f"{render} payloads contain no technique ownership state", got, expected)
    check(f"{render} serialized conditioning cache keys are identical",
          json.dumps(got, sort_keys=True), json.dumps(expected, sort_keys=True))
    check(f"{render} compilation does not mutate workflow provenance", annotated, before)
    check(f"{render} technique prose still reaches compiled model prompts",
          compiler.compile_timeline(annotated), compiler.compile_timeline(clean))
    check(f"{render} source instruction remains in payload",
          any("Dolly in slowly." in item.get("request", {}).get("prompt", "") for item in got), True)

standalone = {"version": 1, "prompt": "A person walks.\n\nDolly in slowly.", "duration_s": 6}
annotated = {**standalone, "techniques": metadata(standalone["prompt"])}
check("legacy standalone promotion strips provenance at payload boundary",
      compiler.timeline_payloads(annotated), compiler.timeline_payloads(standalone))
check("direct standalone compiler ignores provenance without altering prose",
      compiler.compile_request(annotated), compiler.compile_request(standalone))

# A stale record can legitimately contain words which were manually removed
# from the prompt. It is provenance, not another source of model instructions.
stale = copy.deepcopy(BASE)
stale["segments"][0]["techniques"] = metadata("Unwanted private old prompt.")
stale["segments"][0]["techniques"]["items"][0]["stale"] = True
check("stale provenance cannot resurrect removed prompt text",
      compiler.timeline_payloads(stale), compiler.timeline_payloads(BASE))

"""`lift.js` names the same models a build needs as `lift.py` does.

    python3 tests/test_lift_mirror.py

The drawer lists what is missing before Build is pressed, from the frontend's
own `needs`; the route refuses on the backend's. Two answers that disagree
would be a drawer that says everything is ready above a button the server
then refuses — or one that asks for a download the build never reads. The
Python is authoritative.

Skips itself if node is not installed.
"""

import itertools

import layout

layout.skip_without_node()

lift = layout.load("outputs", "lift").lift

from harness import check, passed

CASES = []
for model, surface, background, views in itertools.product(
        lift.CHOICES["model"], lift.CHOICES["surface"], lift.CHOICES["background"], (1, 2, 4)):
    if model == "trellis" and views > 1:
        continue          # refused by `spec` before anything asks what it needs
    for have in ("both", "views only"):
        CASES.append({"model": model, "surface": surface, "background": background, "views": views,
                      "have": have})


def catalogue(have):
    models = {role: {"file": name, "folder": folder, "found": True, "url": url}
              for role, (folder, name, url) in lift.MODELS.items()}
    if have == "views only":
        models["pixal"] = dict(models["pixal"], found=False)
    return models

# In the packed tree, because `lift.js` reaches ComfyUI's `scripts/api.js`
# through `api.js` and a bare checkout has no such file two directories up.
SCRIPT = """
const m = await import("./web/creator/lift.js");
const cases = JSON.parse(process.argv[1]);
console.log(JSON.stringify(cases.map((c) => m.needs(c, c.views, c.models))));
"""

with layout.pack() as tree:
    reflected = layout.in_pack(SCRIPT, tree, [dict(case, models=catalogue(case["have"])) for case in CASES])

for case, js in zip(CASES, reflected):
    sides = dict(itertools.islice(zip(lift.VIEWS, ("a.png",) * 4), case["views"]))
    settings = lift.spec({key: value for key, value in case.items() if key != "have"} | {"views": sides})
    check(f"needs {case}", js, lift.needs(settings, catalogue(case["have"])))

passed(f"lift.js needs the same models as lift.py in all {len(CASES)} cases")

"""The image-to-3D graph against core's real nodes, and the stage node run.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_lift_graph.py

`test_lift.py` holds the graph's shape without ComfyUI. This boots core and
holds every node `lift.build` emits against the schema core actually serves —
the class exists, every input it is given is one the node takes (dynamic-combo
children included, spelled `parent.child` the way the frontend sends them),
every required input is present, and every link carries the type the input
wants. The Pixal3D nodes are new and still moving; this is the suite that says
so the day one of them renames an input.

Then it runs `ContinuityLiftStage` for real on a cube: the picture written with
its alpha, the mesh written as a GLB with the face count reported, and the
final mesh landing on the shelf under a name that does not overwrite the last.

Skips itself with a message if ComfyUI cannot be imported.
"""

import asyncio
import importlib
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.basename(ROOT)
COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
BASE = os.environ.get("COMFYUI_BASE", COMFY)


def _boot():
    sys.path.insert(0, COMFY)
    sys.argv = ["main.py", "--base-directory", BASE]
    import nodes
    import server

    loop = asyncio.new_event_loop()
    try:
        from app.assets.manager import default_asset_manager
        server.PromptServer(loop, default_asset_manager())
    except (ImportError, TypeError):
        server.PromptServer(loop)
    asyncio.set_event_loop(loop)
    loop.run_until_complete(nodes.init_extra_nodes(init_custom_nodes=False))
    sys.path.insert(0, os.path.dirname(ROOT))
    return nodes, server


try:
    comfy_nodes, comfy_server = _boot()
except Exception as exc:  # noqa: BLE001
    print(f"skipped: ComfyUI not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)

package = importlib.import_module(PACKAGE)
lift = importlib.import_module(f"{PACKAGE}.creator.lift")
liftnode = importlib.import_module(f"{PACKAGE}.creator.liftnode")

import folder_paths  # noqa: E402
import torch  # noqa: E402
from comfy_api.latest import Types  # noqa: E402

from harness import FAILURES, check, passed  # noqa: E402

comfy_nodes.NODE_CLASS_MAPPINGS.setdefault("ContinuityLiftStage", liftnode.ContinuityLiftStage)


def info(class_type):
    """What `/object_info` serves for a class — the two halves of core's own
    `node_info`, which is a closure inside the server and cannot be called."""
    node = comfy_nodes.NODE_CLASS_MAPPINGS[class_type]
    if hasattr(node, "GET_NODE_INFO_V1"):
        return node.GET_NODE_INFO_V1()
    return {"input": node.INPUT_TYPES(), "output": list(node.RETURN_TYPES)}


MODELS = {role: {"file": name, "folder": folder, "found": True, "url": url}
          for role, (folder, name, url) in lift.MODELS.items()}


def schema(class_type):
    try:
        return info(class_type)
    except KeyError:
        return None


def allowed(spec):
    names = {}
    for group in ("required", "optional"):
        for name, entry in spec["input"].get(group, {}).items():
            names[name] = entry
            if entry[0] == "COMFY_DYNAMICCOMBO_V3":
                for option in entry[1]["options"]:
                    for child, child_entry in option["inputs"].get("required", {}).items():
                        names[f"{name}.{child}"] = child_entry
    return names


def holds(label, prompt):
    for key, node in prompt.items():
        spec = schema(node["class_type"])
        if spec is None:
            FAILURES.append(f"{label}: {key} is a {node['class_type']}, which core does not have")
            continue
        names = allowed(spec)
        for name in spec["input"].get("required", {}):
            if name not in node["inputs"]:
                FAILURES.append(f"{label}: {key} lacks its required {name}")
        for name, value in node["inputs"].items():
            if name not in names:
                FAILURES.append(f"{label}: {key} has no input called {name}")
                continue
            if not isinstance(value, list):
                continue
            source = schema(prompt[value[0]]["class_type"])
            outputs = source["output"] if source else []
            if value[1] >= len(outputs):
                FAILURES.append(f"{label}: {key}.{name} reads slot {value[1]} of {value[0]}")
                continue
            want = names[name][0]
            have = outputs[value[1]]
            if isinstance(want, str) and not want.startswith("COMFY_MATCHTYPE") \
                    and have not in want.split(","):
                FAILURES.append(f"{label}: {key}.{name} wants {want}, gets {have} from {value[0]}")


for label, body in [
    ("one picture", {}),
    ("TRELLIS.2, colour, kept", {"model": "trellis", "surface": "color", "background": "keep"}),
    ("the rig, shape only, high", {"views": {"front": "a.png", "left": "b.png", "back": "c.png",
                                             "right": "d.png"}, "surface": "none", "detail": "high"}),
    ("one picture, 4K", {"texture": 4096, "faces": 2000000}),
]:
    body.setdefault("views", {"front": "a.png"})
    prompt, plan = lift.build(lift.spec(body), MODELS)
    holds(label, prompt)

# One picture on the rig's model, MoGe's field of view wired into its widget.
only_views = dict(MODELS, pixal=dict(MODELS["pixal"], found=False))
prompt, plan = lift.build(lift.spec({"views": {"front": "a.png"}}), only_views)
holds("one picture on the rig", prompt)

# ---- the stage node, run -------------------------------------------------------------

with tempfile.TemporaryDirectory() as scratch:
    folder_paths.set_output_directory(os.path.join(scratch, "output"))
    folder_paths.set_temp_directory(os.path.join(scratch, "temp"))

    image = torch.rand(1, 32, 32, 3)
    alpha = torch.zeros(1, 32, 32, 3)
    alpha[:, 8:24, 8:24] = 1.0
    record = liftnode.ContinuityLiftStage.execute(stage="cutout", image=image, alpha=alpha).ui
    shown = record["continuity_lift"][0]
    check("a picture goes to temp", (shown["image"]["type"], shown["image"]["subfolder"]),
          ("temp", liftnode.TEMP))
    from PIL import Image
    with Image.open(os.path.join(folder_paths.get_temp_directory(), liftnode.TEMP,
                                 shown["image"]["filename"])) as written:
        check("the cut-out carries its alpha", written.mode, "RGBA")
        check("transparent where the mask is not", written.getpixel((1, 1))[3], 0)

    record = liftnode.ContinuityLiftStage.execute(stage="camera", value=41.25).ui["continuity_lift"][0]
    check("the field of view arrives as a number", record, {"stage": "camera", "value": 41.25})

    corners = torch.tensor([[x, y, z] for x in (-.5, .5) for y in (-.5, .5) for z in (-.5, .5)],
                           dtype=torch.float32)
    faces = torch.tensor([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1],
                          [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]],
                         dtype=torch.int32)
    cube = Types.MESH(vertices=corners[None], faces=faces[None])
    record = liftnode.ContinuityLiftStage.execute(stage="shape", mesh=cube).ui["continuity_lift"][0]
    check("an intermediate mesh goes to temp", record["mesh"]["type"], "temp")
    check("its faces are counted", record["faces"], 12)
    path = os.path.join(folder_paths.get_temp_directory(), liftnode.TEMP, record["mesh"]["filename"])
    with open(path, "rb") as handle:
        check("it is a GLB", handle.read(4), b"glTF")

    first = liftnode.ContinuityLiftStage.execute(stage="bake", mesh=cube, final="jug",
                                                 base_color=image).ui["continuity_lift"][0]
    second = liftnode.ContinuityLiftStage.execute(stage="bake", mesh=cube, final="jug").ui["continuity_lift"][0]
    check("the kept mesh lands on the shelf", (first["mesh"]["type"], first["mesh"]["subfolder"]),
          ("output", lift.MESHES))
    check("under the picture's name", first["mesh"]["filename"], "jug.glb")
    check("and the next one does not overwrite it", second["mesh"]["filename"], "jug-2.glb")
    check("it says it is the final one", first.get("final"), True)
    check("a map is reported as a swatch", sorted(first["maps"]), ["base_color"])

passed("the lift graph holds against core, and its stage node writes what it says")

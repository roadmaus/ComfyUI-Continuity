"""`ContinuityLiftStage`: how one stage of a lift reports what it made.

The image-to-3D graph (`lift.py`) is core's own nodes end to end, and core
already has preview nodes. They do not fit for two reasons. `Preview3DAdvanced`
takes a viewport state that only its own canvas widget can fill in, so a prompt
built on the server cannot include one; and a stage has to be *recognisable* on
the wire — the tool draws a track of six stages, and "the node under key
lift-show-shape finished and here is its file" is a sentence it can read, where
a stream of anonymous previews is not.

So each stage ends in one of these: it takes whatever the stage made — a
picture and the alpha cut to match, a field of view, a mesh, the baked maps —
writes the files where `/view` serves them, and returns a record under the
pack's own `continuity_lift` key, which the frontend's node bodies never read.

Intermediates go to the temp folder, which ComfyUI empties on start: they are
pictures of work in progress and nobody should find a drawer of voxel meshes
in their output folder. The one mesh a request asks to keep — the stage named
`final` — goes to `output/continuity/meshes/`, beside the renders, and takes
its papers with it: the cut-out, the swatches and the build's record, in the
`.lift/` folder beside it (`lift.KEPT`), so the tool can open it again later.
"""

import json
import logging
import os
import uuid

import numpy as np
from comfy_api.latest import io
from PIL import Image

from . import lift, outputs

log = logging.getLogger(__name__)

# The temp subfolder intermediates are written under.
TEMP = "continuity/lift"
# The longest edge a baked map is shown at. The maps inside the GLB are full
# size; these are the swatches under the settings, and a 4K PNG per swatch
# would be sixty megabytes of thumbnails.
SWATCH = 512

# The maps the bake stage hands over, in the order the tool shows them.
MAPS = ("base_color", "roughness", "metallic", "normal_map", "occlusion")


def _pixels(image, alpha=None):
    """An IMAGE tensor's first item -> uint8 RGB(A), alpha from a mask image."""
    rgb = np.clip(image[0, ..., :3].float().cpu().numpy() * 255.0, 0, 255).astype(np.uint8)
    if alpha is None:
        return Image.fromarray(rgb, "RGB")
    a = np.clip(alpha[0, ..., 0].float().cpu().numpy() * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(np.dstack([rgb, a]), "RGBA")


def _temp_file(suffix):
    import folder_paths

    folder = os.path.join(folder_paths.get_temp_directory(), *TEMP.split("/"))
    os.makedirs(folder, exist_ok=True)
    name = f"{uuid.uuid4().hex[:12]}{suffix}"
    return os.path.join(folder, name), {"filename": name, "subfolder": TEMP, "type": "temp"}


def _final_file(stem):
    """Where the kept mesh goes: `stem.glb`, or `stem-2.glb` and on if taken."""
    import folder_paths

    folder = os.path.join(folder_paths.get_output_directory(), *outputs.MESHES.split("/"))
    os.makedirs(folder, exist_ok=True)
    name, n = f"{stem}.glb", 1
    while os.path.exists(os.path.join(folder, name)):
        n += 1
        name = f"{stem}-{n}.glb"
    return os.path.join(folder, name), {"filename": name, "subfolder": outputs.MESHES,
                                        "type": "output"}


def _faces(mesh):
    counts = getattr(mesh, "face_counts", None)
    if counts is not None:
        return int(counts.reshape(-1)[0])
    return int(mesh.faces.shape[1])


class ContinuityLiftStage(io.ComfyNode):
    """One stage of an image-to-3D build, reported. Built by `lift.build`."""

    @classmethod
    def define_schema(cls):
        maps = [io.Image.Input(name, optional=True) for name in MAPS]
        return io.Schema(
            node_id="ContinuityLiftStage",
            display_name="Continuity Lift Stage",
            category="Continuity",
            description="Internal: reports one stage of the image-to-3D tool's build.",
            # Nobody wires this by hand; `lift.build` is its only author.
            is_dev_only=True,
            is_output_node=True,
            inputs=[
                io.String.Input("stage", default=""),
                io.String.Input("final", default=""),
                io.Image.Input("image", optional=True),
                io.Image.Input("alpha", optional=True),
                io.Mesh.Input("mesh", optional=True),
                io.Float.Input("value", optional=True, force_input=True),
                # The final stage's record of the build, as JSON — `lift._keeping`.
                io.String.Input("keep", optional=True, default=""),
                *maps,
            ],
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        """Never cached. A rebuild that changes only the surface reuses the
        structure and the shape from the cache — which is the point of queueing
        a graph — but the tool still has to *hear* those stages again, and a
        cached output node says nothing."""
        return uuid.uuid4().hex

    @classmethod
    def execute(cls, stage, final="", image=None, alpha=None, mesh=None, value=None, keep="",
                **maps) -> io.NodeOutput:
        record = {"stage": stage}
        # The kept mesh's papers go beside it; name them once the GLB has one.
        papers = None
        if final and mesh is not None:
            glb_path, glb_where = _final_file(final)
            papers = (os.path.dirname(glb_path), glb_where["filename"][:-4], glb_where["subfolder"])
            os.makedirs(os.path.join(papers[0], lift.KEPT), exist_ok=True)

        def keep_file(suffix):
            folder, stem, subfolder = papers
            return lift.kept_file(folder, stem, suffix), {
                "filename": stem + suffix, "subfolder": f"{subfolder}/{lift.KEPT}", "type": "output"}

        if image is not None:
            path, where = keep_file(".png") if papers else _temp_file(".png")
            _pixels(image, alpha).save(path)
            record["image"] = where
        if value is not None:
            record["value"] = float(value)
        if mesh is not None:
            from comfy_extras.nodes_save_3d import mesh_item_to_glb_bytes

            glb = mesh_item_to_glb_bytes(mesh, 0)
            if glb is None:
                raise ValueError(f"the {stage} stage made an empty mesh")
            path, where = (glb_path, glb_where) if papers else _temp_file(".glb")
            with open(path, "wb") as handle:
                handle.write(glb)
            record["mesh"] = where
            record["faces"] = _faces(mesh)
            record["bytes"] = len(glb)
            if final:
                record["final"] = True
                log.info("continuity: lifted %s/%s (%d faces)", where["subfolder"],
                         where["filename"], record["faces"])
        swatches = {}
        for name in MAPS:
            picture = maps.get(name)
            if picture is None:
                continue
            thumb = _pixels(picture)
            thumb.thumbnail((SWATCH, SWATCH))
            path, where = keep_file(f".{name}.png") if papers else _temp_file(".png")
            thumb.save(path)
            swatches[name] = where
        if swatches:
            record["maps"] = swatches
        if papers:
            cls.keep_papers(keep_file, keep, record)
        # Round-tripped so a value the wire cannot carry fails here, by name,
        # rather than as a websocket that drops the message.
        json.dumps(record)
        return io.NodeOutput(ui={"continuity_lift": [record]})

    @staticmethod
    def keep_papers(keep_file, keep, record):
        """The build's record beside the kept mesh: what `keep` said, the camera
        made whole with the field of view that arrived on the wire, and what
        this stage wrote. File names, not `/view` records — the folder is the
        mesh's, and `lift.kept` rebuilds the records from wherever it is read."""
        try:
            papers = json.loads(keep) if keep else {}
        except ValueError:
            raise ValueError(f"the {record['stage']} stage was handed a record that is not JSON") from None
        camera = papers.get("camera")
        if camera and camera.get("fov") is None:
            camera["fov"] = record.get("value")
        papers.update(stage=record["stage"], faces=record["faces"], bytes=record["bytes"],
                      picture=record["image"]["filename"] if "image" in record else None,
                      maps={name: where["filename"] for name, where in record.get("maps", {}).items()})
        path, _ = keep_file(".json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(papers, handle, indent=1, sort_keys=True)


NODES = [ContinuityLiftStage]

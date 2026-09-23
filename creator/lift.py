"""Lifting a picture into a mesh: the graph core already ships, built on request.

Pixal3D (and TRELLIS.2 beside it) arrived in core as some thirty nodes: a
background remover, a camera estimate, three samplers over one structure, a
remesh, an unwrap and four bakes. The template that shows how they fit is the
only documentation of the order, and it is a canvas somebody has to load,
rewire for their own picture and read the output of in a 3D preview node. This
is the other way in: a picture, a handful of choices, and the mesh — with every
intermediate on the way handed back so the tool can show what each stage made.

**It is a graph, not a job.** Everything else this pack runs off the render path
is one `ContinuityJob` node calling a Python function (`jobs.py`), and that is
right for a bench whose work is one operation. This is core's own pipeline, and
running core's nodes by calling their `execute` from inside a node would throw
away exactly what the queue is for: the execution cache, which is what makes a
second build with only the surface changed start at the unwrap instead of the
structure sampler, and the per-node `executing` and `progress_state` messages,
which is what the tool's stage track is drawn from. So `build` returns an
ordinary API-format prompt and the route queues it through `jobs.enqueue`, the
same door the chat room's renders go through.

**The graph is the template's, transcribed.** `3d_pixal3d_trellis2_image_to_model`
and `3d_pixal3d_multi_views` in `comfyui_workflow_templates` fix every number
here that is not one of the tool's controls — the seeds, the step counts, the
CFG overrides and rescales ("to match the original default pipeline behaviour",
the template's own note), the remesh at 768 and the bake settings. They are not
dials because nobody choosing between a jug and a teapot has an opinion about
the texture sampler's rescale multiplier, and the template's authors did.

**What the tool adds is one node per stage**, `ContinuityLiftStage`
(`liftnode.py`): an output node that takes whatever a stage made — the cut-out
picture, the camera's field of view, a mesh — writes it where the browser can
fetch it, and says so on the wire. Core's own preview nodes would have done
half of this, but `Preview3DAdvanced` wants a viewport state only its canvas
widget can supply, and a stage has to be recognisable by the tool that queued
it; a node of our own answers both.

**Node keys are named, never numbered.** ComfyUI files outputs and progress
under the key and the frontend hands it to `getNodeById`, so a numeric key moves
the progress bar of whatever canvas node shares it (`jobs.KEY` says the same).
Every key here starts `lift-`.

Import-light on purpose — no torch, no ComfyUI — so the suite can build and
inspect the graph without booting anything. `catalogue` is the one function that
touches `folder_paths`, and it imports it where it runs.
"""

import re

# Where finished meshes land, under the output folder. Named in `outputs.py`
# with the other shelves; re-exported here because this module is its reader.
from .outputs import MESHES  # noqa: F401  (re-exported)


class LiftError(ValueError):
    """A request the tool cannot build. Reported under the button."""


# ---- the models -------------------------------------------------------------

# Each role, the folder core's loader reads it from, the file the templates
# name, and where it is downloaded from. The URL is what the tool shows when a
# file is missing: the whole point of a surface over a template is not making
# somebody go and find the template's note to learn what to download.
MODELS = {
    "pixal": ("diffusion_models", "pixal3d_int8_convrot.safetensors",
              "https://huggingface.co/Comfy-Org/Pixal3D/resolve/main/diffusion_models/pixal3d_int8_convrot.safetensors"),
    "pixal_views": ("diffusion_models", "pixal3d_multiview_int8_convrot.safetensors",
                    "https://huggingface.co/Comfy-Org/Pixal3D/resolve/main/diffusion_models/pixal3d_multiview_int8_convrot.safetensors"),
    "trellis": ("diffusion_models", "trellis_2_int8_convrot.safetensors",
                "https://huggingface.co/Comfy-Org/TRELLIS.2/resolve/main/diffusion_models/trellis_2_int8_convrot.safetensors"),
    "shape_vae": ("vae", "trellis_2_shape_vae_bf16.safetensors",
                  "https://huggingface.co/Comfy-Org/Pixal3D/resolve/main/vae/trellis_2_shape_vae_bf16.safetensors"),
    "texture_vae": ("vae", "trellis_2_texture_vae_bf16.safetensors",
                    "https://huggingface.co/Comfy-Org/Pixal3D/resolve/main/vae/trellis_2_texture_vae_bf16.safetensors"),
    "dino": ("clip_vision", "dino_v3_L_naf_fp32.safetensors",
             "https://huggingface.co/Comfy-Org/Pixal3D/resolve/main/clip_vision/dino_v3_L_naf_fp32.safetensors"),
    "moge": ("geometry_estimation", "moge_2_vitl_normal_fp16.safetensors",
             "https://huggingface.co/Comfy-Org/MoGe/resolve/main/geometry_estimation/moge_2_vitl_normal_fp16.safetensors"),
    "cutout": ("background_removal", "birefnet.safetensors",
               "https://huggingface.co/Comfy-Org/BiRefNet/resolve/main/background_removal/birefnet.safetensors"),
}

# The multi-view rig's four sides, in the order `Pixal3DMultiViewConditioning`
# takes them. The first one present is the front the mesh is posed to.
VIEWS = ("front", "left", "back", "right")

# What a request may say, and what it says when it says nothing.
CHOICES = {
    "model": ("pixal", "trellis"),
    "detail": ("standard", "high"),
    "background": ("remove", "keep"),
    "surface": ("pbr", "color", "none"),
    "texture": (1024, 2048, 4096),
}
DEFAULTS = {"model": "pixal", "detail": "standard", "background": "remove",
            "surface": "pbr", "texture": 2048, "faces": 200000, "seed": 42}

# Shape resolution per detail. Standard is the upstream repository's default
# (its low-VRAM path); High is the template's.
DETAIL_RESOLUTION = {"standard": 1024, "high": 1536}
FACES_MIN, FACES_MAX = 10000, 2000000

# The field of view a turnaround sheet is framed at. The multi-view node's own
# default, and the template's: most multi-view generators and every rig render
# are drawn this narrow, and a photographed set of views is not what this path
# is for.
VIEWS_FOV = 20.0

# The six stages the tool draws, in the order they run. The keys are what the
# frontend's track is labelled by; which nodes belong to which is decided in
# `build`, per request, because a stage can be skipped.
STAGES = ("cutout", "camera", "structure", "shape", "texture", "bake")


def _choice(body, key):
    value = body.get(key, DEFAULTS[key])
    if key == "texture":
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise LiftError(f"texture size must be one of {CHOICES[key]}") from None
    if value not in CHOICES[key]:
        raise LiftError(f"{key} must be one of {', '.join(map(str, CHOICES[key]))}")
    return value


def _int(body, key, low, high):
    try:
        value = int(body.get(key, DEFAULTS[key]))
    except (TypeError, ValueError):
        raise LiftError(f"{key} must be a whole number") from None
    return max(low, min(high, value))


def spec(body):
    """A request body -> the settings `build` takes, validated and defaulted.

    `views` maps a side to an input-relative filename, as the picker hands them
    over. One view is a single-picture lift; two or more is the multi-view rig,
    which only Pixal3D has — TRELLIS.2 reads one picture, and quietly dropping
    the others would build something the person did not ask for.
    """
    raw = body.get("views")
    if not isinstance(raw, dict):
        raise LiftError("views must name at least a front picture")
    views = {side: str(raw[side]) for side in VIEWS if raw.get(side)}
    if not views:
        raise LiftError("add a picture to lift")
    unknown = set(raw) - set(VIEWS)
    if unknown:
        raise LiftError(f"{', '.join(sorted(unknown))} is not a side of the rig")
    out = {key: _choice(body, key) for key in CHOICES}
    if len(views) > 1 and out["model"] != "pixal":
        raise LiftError("TRELLIS.2 builds from one picture; remove the extra views or pick Pixal3D")
    out["views"] = views
    out["faces"] = _int(body, "faces", FACES_MIN, FACES_MAX)
    out["seed"] = _int(body, "seed", 0, 2 ** 48)
    out["name"] = stem(body.get("name") or views[next(iter(views))])
    return out


def stem(name):
    """A file name for the mesh, from whatever the picture was called.

    The basename without its extension, cut down to letters, digits, dashes and
    underscores: it becomes a path under the output folder, and a request can
    say anything.
    """
    # A gallery path carries ComfyUI's folder annotation ("take.png [output]"),
    # which is where the file is, not what it is called.
    bare = re.sub(r"\s*\[(input|output|temp)\]$", "", str(name))
    base = re.sub(r"\.[A-Za-z0-9]+$", "", bare.replace("\\", "/").split("/")[-1])
    clean = re.sub(r"[^A-Za-z0-9_-]+", "_", base).strip("_")
    return clean[:80] or "mesh"


def model_role(settings, models=None):
    """Which diffusion model a request runs.

    One picture runs the single-view model when the machine has it, and the
    multi-view model when it has only that: the rig node takes a single view
    as happily as four, and fed MoGe's field of view it is posed on the
    photograph's own camera just the same (its own tooltip says as much). An
    install that downloaded one Pixal3D checkpoint should not be told to go
    and get the other before it can lift anything.
    """
    if settings["model"] == "trellis":
        return "trellis"
    if len(settings["views"]) > 1:
        return "pixal_views"
    if models and not models["pixal"]["found"] and models["pixal_views"]["found"]:
        return "pixal_views"
    return "pixal"


def needs(settings, models=None):
    """The model roles a request needs on disk, in the order they are loaded."""
    roles = [model_role(settings, models), "dino", "shape_vae"]
    if settings["surface"] != "none":
        roles.append("texture_vae")
    if settings["background"] == "remove":
        roles.append("cutout")
    if settings["model"] == "pixal" and len(settings["views"]) == 1:
        roles.append("moge")
    return roles


def catalogue():
    """Which of the models this machine has. Walks the model folders — run it
    off the event loop.

    `{role: {file, folder, found, url}}`, where `file` is the name core's
    loader will be handed: the template's filename wherever it sits under its
    folder, subfolders included, because the lab and most real installs file
    models into subdirectories and a loader combo lists them by relative path.
    """
    import folder_paths

    out = {}
    for role, (folder, filename, url) in MODELS.items():
        try:
            listed = folder_paths.get_filename_list(folder)
        except Exception:  # noqa: BLE001 — a folder core does not know yet is a folder with nothing in it
            listed = []
        found = next((entry for entry in listed
                      if entry.replace("\\", "/").split("/")[-1] == filename), None)
        out[role] = {"file": found or filename, "folder": folder, "found": found is not None,
                     "url": url}
    return out


def missing(settings, models):
    """The model entries this request needs and the machine does not have."""
    return [dict(models[role], role=role) for role in needs(settings, models)
            if not models[role]["found"]]


# ---- the graph --------------------------------------------------------------


class _Graph:
    """An API-format prompt under construction, with each node filed under the
    stage it belongs to."""

    def __init__(self):
        self.nodes = {}
        self.stage_of = {}

    def add(self, key, class_type, group, **inputs):
        key = f"lift-{key}"
        if key in self.nodes:
            raise AssertionError(f"{key} added twice")
        self.nodes[key] = {"class_type": class_type, "inputs": inputs}
        self.stage_of[key] = group
        return key


def _out(key, slot=0):
    return [key, slot]


def _cutout(graph, side, filename, settings, pad):
    """One picture -> the square crop the conditioning reads, plus its mask.

    Removed or kept, the subject ends up as a mask the crop is centred on. A
    kept background means the picture already carries one — its alpha, which
    `LoadImage` hands over inverted (transparent is 1), so it is turned back
    the right way up before the crop reads it.
    """
    image = graph.add(f"{side}-image", "LoadImage", "cutout", image=filename)
    if settings["background"] == "remove":
        mask = graph.add(f"{side}-matte", "RemoveBackground", "cutout",
                         bg_removal_model=_out("lift-cutout-model"), image=_out(image))
    else:
        mask = graph.add(f"{side}-matte", "InvertMask", "cutout", mask=_out(image, 1))
    crop = dict(width=1024, height=1024, pad_factor=pad, grow_mask=0, background="#000000")
    picture = graph.add(f"{side}-crop", "ImageCropToMask", "cutout",
                        images=_out(image), masks=_out(mask), **crop)
    # The mask cropped by the same rule, so the cut-out the tool shows has an
    # alpha that sits exactly on the picture the model was given.
    matte = graph.add(f"{side}-matte-image", "MaskToImage", "cutout", mask=_out(mask))
    alpha = graph.add(f"{side}-alpha", "ImageCropToMask", "cutout",
                      images=_out(matte), masks=_out(mask), **crop)
    return picture, alpha


def _stage(graph, stage, final=None, **inputs):
    """The node that reports one stage's result to the tool."""
    return graph.add(f"show-{stage}", "ContinuityLiftStage", stage,
                     stage=stage, final=final or "", **inputs)


def build(settings, models):
    """The settings -> `(prompt, plan)`.

    `prompt` is the API-format graph to queue. `plan` is what the frontend
    needs to read the wire back: which stage each node key belongs to, which
    stages this request skips, and the camera the mesh was lifted from (or
    None when the model is not aligned to one).
    """
    graph = _Graph()
    files = {role: models[role]["file"] for role in models}
    role = model_role(settings, models)
    single = len(settings["views"]) == 1
    pixal = settings["model"] == "pixal"
    textured = settings["surface"] != "none"
    seed = settings["seed"]

    # Loaders first, each under the first stage that reads it, so the track
    # shows loading as part of the stage that is waiting on it.
    if settings["background"] == "remove":
        graph.add("cutout-model", "LoadBackgroundRemovalModel", "cutout",
                  bg_removal_name=files["cutout"])

    # Pixal3D frames the subject with a tenth of margin; TRELLIS.2 fills the frame.
    pad = 1.1 if pixal else 1.0
    crops = {side: _cutout(graph, side, filename, settings, pad)
             for side, filename in settings["views"].items()}
    front_side = next(iter(settings["views"]))
    front, front_alpha = crops[front_side]
    _stage(graph, "cutout", image=_out(front), alpha=_out(front_alpha))

    graph.add("unet", "UNETLoader", "structure", unet_name=files[role], weight_dtype="default")
    graph.add("dino", "CLIPVisionLoader", "structure", clip_name=files["dino"])
    graph.add("shape-vae", "VAELoader", "structure", vae_name=files["shape_vae"])

    camera = None
    if pixal and single:
        # The camera, from the picture: MoGe's horizontal field of view is what
        # the conditioning back-projects the pixels along. This is the one step
        # that makes the mesh sit under its own photograph.
        graph.add("moge-model", "LoadMoGeModel", "camera", model_name=files["moge"])
        graph.add("moge", "MoGeInference", "camera", moge_model=_out("lift-moge-model"),
                  image=_out(front), resolution_level=9, fov_x_degrees=0.0, batch_size=4,
                  force_projection=True, apply_mask=True, refine_steps=3)
        graph.add("fov", "MoGeGeometryToFOV", "camera", moge_geometry=_out("lift-moge"),
                  axis="horizontal", unit="degrees")
        _stage(graph, "camera", value=_out("lift-fov"))
        if role == "pixal_views":
            # The rig, one view on it, at the photograph's own field of view.
            # Its camera stands back by the rig's margin, which the crop
            # already carries.
            cond = graph.add("cond", "Pixal3DMultiViewConditioning", "structure",
                             clip_vision_model=_out("lift-dino"), fov=_out("lift-fov"),
                             front=_out(front))
            camera = {"fov": None, "pad": 1.1}
        else:
            cond = graph.add("cond", "Pixal3DConditioning", "structure",
                             clip_vision_model=_out("lift-dino"), image=_out(front),
                             camera_angle_x=_out("lift-fov"))
            camera = {"fov": None, "pad": 1.0}   # the fov arrives on the wire
    elif pixal:
        views = {side: _out(crops[side][0]) for side in settings["views"]}
        cond = graph.add("cond", "Pixal3DMultiViewConditioning", "structure",
                         clip_vision_model=_out("lift-dino"), fov=VIEWS_FOV, **views)
        camera = {"fov": VIEWS_FOV, "pad": 1.1}
    else:
        cond = graph.add("cond", "Trellis2Conditioning", "structure",
                         clip_vision_model=_out("lift-dino"), image=_out(front))

    # The three model paths the template patches out of one UNet: the
    # structure sampler's, the shape samplers' and the texture sampler's.
    unet = _out("lift-unet")
    graph.add("structure-cfg", "CFGOverride", "structure", model=unet,
              cfg=1.0, start_percent=0.667, end_percent=1.0)
    graph.add("structure-rescale", "RescaleCFG", "structure",
              model=_out("lift-structure-cfg"), multiplier=0.7)
    graph.add("structure-model", "ModelSamplingSD3", "structure",
              model=_out("lift-structure-rescale"), shift=5.0)
    graph.add("shape-cfg", "CFGOverride", "shape", model=unet,
              cfg=1.0, start_percent=0.769, end_percent=1.0)
    graph.add("shape-model", "RescaleCFG", "shape", model=_out("lift-shape-cfg"), multiplier=0.5)

    sampler = dict(sampler_name="euler", denoise=1.0)
    graph.add("structure-latent", "EmptyTrellis2LatentStructure", "structure", batch_size=1)
    graph.add("structure-sample", "KSampler", "structure",
              model=_out("lift-structure-model"), positive=_out(cond, 0), negative=_out(cond, 1),
              latent_image=_out("lift-structure-latent"), seed=seed + 14, steps=12, cfg=7.5,
              scheduler="normal", **sampler)
    graph.add("voxels", "VaeDecodeStructureTrellis2", "structure",
              samples=_out("lift-structure-sample"), vae=_out("lift-shape-vae"), resolution="32")
    graph.add("voxel-mesh", "VoxelToMesh", "structure", voxel=_out("lift-voxels"),
              algorithm="basic", threshold=0.6)
    _stage(graph, "structure", mesh=_out("lift-voxel-mesh"))

    graph.add("shape-stage", "Trellis2ShapeStage", "shape",
              positive=_out(cond, 0), negative=_out(cond, 1), voxel=_out("lift-voxels"))
    graph.add("shape-sample", "KSampler", "shape",
              model=_out("lift-shape-model"), positive=_out("lift-shape-stage", 0),
              negative=_out("lift-shape-stage", 1), latent_image=_out("lift-shape-stage", 2),
              seed=seed, steps=20, cfg=7.5, scheduler="normal", **sampler)
    graph.add("upsample-stage", "Trellis2UpsampleStage", "shape",
              positive=_out("lift-shape-stage", 0), negative=_out("lift-shape-stage", 1),
              shape_latent=_out("lift-shape-sample"), vae=_out("lift-shape-vae"),
              target_resolution=DETAIL_RESOLUTION[settings["detail"]])
    graph.add("upsample-sample", "KSampler", "shape",
              model=_out("lift-shape-model"), positive=_out("lift-upsample-stage", 0),
              negative=_out("lift-upsample-stage", 1), latent_image=_out("lift-upsample-stage", 2),
              seed=seed, steps=12, cfg=7.5, scheduler="simple", **sampler)
    graph.add("shape", "VaeDecodeShapeTrellis", "shape",
              samples=_out("lift-upsample-sample"), vae=_out("lift-shape-vae"))
    graph.add("shape-info", "GetMeshInfo", "shape", mesh=_out("lift-shape"))
    graph.add("remesh", "RemeshMesh", "shape", mesh=_out("lift-shape-info"),
              resolution=768, sign_mode="udf",
              **{"sign_mode.qef": False, "sign_mode.drop_inverted_components": False,
                 "sign_mode.drop_enclosed_components": False},
              band=1.0, project_back=0.0, fix_poles=False, smooth_iters=20,
              drop_small_components=0.01, precluster_max_verts=20000000)
    graph.add("decimate", "DecimateMesh", "shape", mesh=_out("lift-remesh"),
              target_face_count=settings["faces"], placement_mode="midpoint")
    graph.add("smooth", "MeshSmoothNormals", "shape", mesh=_out("lift-decimate"), crease_angle=180.0)
    _stage(graph, "shape", mesh=_out("lift-smooth"),
           final=None if textured else settings["name"])

    skipped = []
    if not (pixal and single):
        skipped.append("camera")
    if not textured:
        skipped += ["texture", "bake"]
    else:
        graph.add("texture-vae", "VAELoader", "texture", vae_name=files["texture_vae"])
        graph.add("texture-stage", "Trellis2TextureStage", "texture",
                  positive=_out("lift-upsample-stage", 0), negative=_out("lift-upsample-stage", 1),
                  shape_latent=_out("lift-upsample-sample"))
        graph.add("texture-sample", "KSampler", "texture",
                  model=unet, positive=_out("lift-texture-stage", 0),
                  negative=_out("lift-texture-stage", 1), latent_image=_out("lift-texture-stage", 2),
                  seed=seed + 1, steps=12, cfg=1.0, scheduler="normal", **sampler)
        graph.add("colors", "VaeDecodeTextureTrellis", "texture",
                  samples=_out("lift-texture-sample"), vae=_out("lift-texture-vae"),
                  shape_subdivides=_out("lift-shape", 1))
        graph.add("painted", "PaintMesh", "texture", mesh=_out("lift-smooth"),
                  voxel_colors=_out("lift-colors"))
        pbr = settings["surface"] == "pbr"
        _stage(graph, "texture", mesh=_out("lift-painted"),
               final=None if pbr else settings["name"])
        if not pbr:
            skipped.append("bake")
        else:
            _bake(graph, settings)

    plan = {"stages": graph.stage_of, "skipped": skipped, "camera": camera,
            "order": list(STAGES), "model": role}
    return graph.nodes, plan


def _bake(graph, settings):
    """The template's PBR tail: unwrap, bake four maps, put them on the mesh."""
    size = settings["texture"]
    graph.add("unwrap", "UnwrapMesh", "bake", mesh=_out("lift-smooth"),
              segmenter="pec", resolution=size, padding=1, weld_distance=0.0002)
    graph.add("maps", "BakeTextureFromVoxel", "bake", mesh=_out("lift-unwrap"),
              voxel_colors=_out("lift-colors"), texture_size=size,
              reference_mesh=_out("lift-shape-info"))
    graph.add("normal-map", "BakeNormalMapFromMesh", "bake",
              low_poly=_out("lift-unwrap"), high_poly=_out("lift-remesh"),
              resolution=size, cage_distance=0.05, ignore_backfaces=True)
    graph.add("occlusion", "BakeAmbientOcclusion", "bake",
              low_poly=_out("lift-unwrap"), high_poly=_out("lift-remesh"),
              resolution=min(size, 1024), samples=64, max_distance=0.71, strength=1.0, bias=0.01)
    graph.add("textured", "ApplyTextureToMesh", "bake", mesh=_out("lift-unwrap"),
              base_color=_out("lift-maps", 0), metallic=_out("lift-maps", 1),
              roughness=_out("lift-maps", 2), occlusion=_out("lift-occlusion"),
              normal_map=_out("lift-normal-map"))
    graph.add("final", "MeshSmoothNormals", "bake", mesh=_out("lift-textured"), crease_angle=180.0)
    _stage(graph, "bake", mesh=_out("lift-final"), final=settings["name"],
           base_color=_out("lift-maps", 0), metallic=_out("lift-maps", 1),
           roughness=_out("lift-maps", 2), normal_map=_out("lift-normal-map"),
           occlusion=_out("lift-occlusion"))

"""The image-to-3D graph: what `lift.spec` accepts, and what `lift.build` emits.

    python3 tests/test_lift.py

Pure Python — the builder is import-light so it can be read here without
ComfyUI. `test_lift_graph.py` holds the same graphs against core's real node
schemas; this suite holds the *shape*: which stages a request runs, which
nodes carry the result, which file it lands in, and that every link names a
node that exists.
"""

import layout
from harness import FAILURES, check, passed

lift = layout.load("outputs", "lift").lift

MODELS = {role: {"file": f"sub/{name}", "folder": folder, "found": True, "url": url}
          for role, (folder, name, url) in lift.MODELS.items()}


def built(**body):
    body.setdefault("views", {"front": "lift/jug.png"})
    settings = lift.spec(body)
    return settings, *lift.build(settings, MODELS)


def refused(label, body, fragment):
    try:
        lift.spec(body)
    except lift.LiftError as exc:
        if fragment not in str(exc):
            FAILURES.append(f"{label}: {str(exc)!r} does not say {fragment!r}")
    else:
        FAILURES.append(f"{label}: accepted")


def of(prompt, class_type):
    return [key for key, node in prompt.items() if node["class_type"] == class_type]


def links_resolve(label, prompt):
    for key, node in prompt.items():
        check(f"{label}: {key} is keyed by name", key.startswith("lift-"), True)
        for name, value in node["inputs"].items():
            if isinstance(value, list):
                check(f"{label}: {key}.{name} names a node", value[0] in prompt, True)


# ---- what a request may say ----------------------------------------------------

refused("no views", {}, "front picture")
refused("empty views", {"views": {}}, "add a picture")
refused("an unknown side", {"views": {"front": "a.png", "top": "b.png"}}, "top")
refused("a bad surface", {"views": {"front": "a.png"}, "surface": "chrome"}, "surface")
refused("a bad texture size", {"views": {"front": "a.png"}, "texture": 3000}, "texture")
refused("TRELLIS.2 with side views", {"views": {"front": "a.png", "left": "b.png"}, "model": "trellis"},
        "one picture")

settings = lift.spec({"views": {"front": "lift/My Jug (2).png"}, "faces": 5, "texture": "4096"})
check("faces are clamped to the floor", settings["faces"], lift.FACES_MIN)
check("a texture size arrives as a string", settings["texture"], 4096)
check("the file is named after the picture", settings["name"], "My_Jug_2")
check("a path cannot climb out of the shelf", lift.stem("../../etc/passwd"), "passwd")
check("an empty stem still names a file", lift.stem("...."), "mesh")
check("annotations are not part of the name", lift.stem("renders/still_00012_.png [output]"),
      "still_00012")

# ---- one picture, Pixal3D, full PBR ----------------------------------------------

settings, prompt, plan = built()
links_resolve("single", prompt)
check("every stage is reported once",
      sorted(prompt[key]["inputs"]["stage"] for key in of(prompt, "ContinuityLiftStage")),
      sorted(lift.STAGES))
check("nothing is skipped", plan["skipped"], [])
check("every node is filed under a stage", set(plan["stages"].values()) <= set(lift.STAGES), True)
check("every node is in the plan", set(plan["stages"]), set(prompt))
check("the camera is MoGe's, sent on the wire", plan["camera"], {"fov": None, "pad": 1.0})
check("the conditioning reads MoGe's field of view",
      prompt["lift-cond"]["inputs"]["camera_angle_x"], ["lift-fov", 0])
check("the crop carries Pixal3D's margin", prompt["lift-front-crop"]["inputs"]["pad_factor"], 1.1)
check("the diffusion model is Pixal3D's", prompt["lift-unet"]["inputs"]["unet_name"],
      "sub/pixal3d_int8_convrot.safetensors")
check("the final mesh is the baked one",
      [prompt[key]["inputs"]["stage"] for key in of(prompt, "ContinuityLiftStage")
       if prompt[key]["inputs"]["final"]], ["bake"])
check("it lands under the picture's name", prompt["lift-show-bake"]["inputs"]["final"], "jug")
check("the maps are reported", sorted(k for k in prompt["lift-show-bake"]["inputs"]
                                      if k in ("base_color", "roughness", "metallic", "normal_map", "occlusion")),
      ["base_color", "metallic", "normal_map", "occlusion", "roughness"])
check("the decimation is the face count", prompt["lift-decimate"]["inputs"]["target_face_count"], 200000)
check("standard detail is 1024", prompt["lift-upsample-stage"]["inputs"]["target_resolution"], 1024)
check("the bake is the texture size", prompt["lift-maps"]["inputs"]["texture_size"], 2048)
check("the template's seeds, by default",
      [prompt[f"lift-{k}-sample"]["inputs"]["seed"] for k in ("structure", "shape", "upsample", "texture")],
      [56, 42, 42, 43])
check("the texture sampler reads the bare UNet", prompt["lift-texture-sample"]["inputs"]["model"],
      ["lift-unet", 0])
check("a removed background is BiRefNet's", of(prompt, "RemoveBackground"), ["lift-front-matte"])

# ---- the loaders match what `needs` says a build needs ----------------------------

def loaded(prompt):
    names = set()
    for node in prompt.values():
        for key in ("unet_name", "vae_name", "clip_name", "model_name", "bg_removal_name"):
            if key in node["inputs"]:
                names.add(node["inputs"][key])
    return names


for label, body in [
    ("single", {}),
    ("trellis colour kept", {"model": "trellis", "surface": "color", "background": "keep"}),
    ("views, shape only", {"views": {"front": "a.png", "left": "b.png", "back": "c.png"}, "surface": "none"}),
]:
    settings, prompt, plan = built(**body)
    check(f"{label}: loads exactly what it needs", loaded(prompt),
          {MODELS[role]["file"] for role in lift.needs(settings)})

# ---- TRELLIS.2, colour only, a picture that is already cut out ---------------------

settings, prompt, plan = built(model="trellis", surface="color", background="keep", detail="high")
links_resolve("trellis", prompt)
check("TRELLIS.2 has no camera", plan["camera"], None)
check("so there is no camera stage", "camera" in plan["skipped"], True)
check("TRELLIS.2 fills the frame", prompt["lift-front-crop"]["inputs"]["pad_factor"], 1.0)
check("a kept background is the alpha, turned the right way up",
      prompt["lift-front-matte"]["class_type"], "InvertMask")
check("and no background model is loaded", of(prompt, "LoadBackgroundRemovalModel"), [])
check("colour only skips the bake", "bake" in plan["skipped"], True)
check("colour only never unwraps", of(prompt, "UnwrapMesh"), [])
check("the painted mesh is the file", prompt["lift-show-texture"]["inputs"]["final"], "jug")
check("high detail is 1536", prompt["lift-upsample-stage"]["inputs"]["target_resolution"], 1536)

# ---- the multi-view rig, shape only -------------------------------------------------

settings, prompt, plan = built(views={"front": "f.png", "left": "l.png", "right": "r.png"},
                               surface="none", faces=50000, seed=7)
links_resolve("views", prompt)
cond = prompt["lift-cond"]
check("the rig conditioning", cond["class_type"], "Pixal3DMultiViewConditioning")
check("each view is its own crop",
      {side: cond["inputs"].get(side) for side in lift.VIEWS},
      {"front": ["lift-front-crop", 0], "left": ["lift-left-crop", 0], "back": None,
       "right": ["lift-right-crop", 0]})
check("the rig's camera", plan["camera"], {"fov": lift.VIEWS_FOV, "pad": 1.1})
check("the rig's model", prompt["lift-unet"]["inputs"]["unet_name"],
      "sub/pixal3d_multiview_int8_convrot.safetensors")
check("shape only skips texture and bake", plan["skipped"], ["camera", "texture", "bake"])
check("shape only never loads the texture VAE", "lift-texture-vae" in prompt, False)
check("the shape is the file", prompt["lift-show-shape"]["inputs"]["final"], "f")
check("a seed moves every sampler",
      [prompt[f"lift-{k}-sample"]["inputs"]["seed"] for k in ("structure", "shape", "upsample")],
      [21, 7, 7])
check("the face count rides through", prompt["lift-decimate"]["inputs"]["target_face_count"], 50000)

# ---- one picture on the multi-view model, when that is the only one on disk ----------

only_views = dict(MODELS, pixal=dict(MODELS["pixal"], found=False))
settings = lift.spec({"views": {"front": "lift/jug.png"}})
prompt, plan = lift.build(settings, only_views)
links_resolve("fallback", prompt)
check("one picture falls back to the rig's model", lift.model_role(settings, only_views), "pixal_views")
check("so nothing is missing", lift.missing(settings, only_views), [])
check("the rig conditioning, on the front alone", prompt["lift-cond"]["class_type"],
      "Pixal3DMultiViewConditioning")
check("posed on MoGe's field of view", prompt["lift-cond"]["inputs"]["fov"], ["lift-fov", 0])
check("with the camera still found", "camera" in plan["skipped"], False)
check("and stood back by the rig's margin", plan["camera"], {"fov": None, "pad": 1.1})
check("the plan names the model", plan["model"], "pixal_views")
check("with both on disk the single-view model wins", lift.model_role(settings, MODELS), "pixal")

# ---- what a machine is missing -------------------------------------------------------

absent = dict(MODELS, moge=dict(MODELS["moge"], found=False))
settings = lift.spec({"views": {"front": "a.png"}})
check("a missing camera model is named", [entry["role"] for entry in lift.missing(settings, absent)], ["moge"])
settings = lift.spec({"views": {"front": "a.png"}, "model": "trellis"})
check("TRELLIS.2 does not need it", lift.missing(settings, absent), [])

passed("all lift tests passed")

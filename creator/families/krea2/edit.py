"""Krea 2's reference path as two nodes the graph can build.

Both are internal, like `ContinuityVDN`: they exist so `still.emit_graph` has
something to wire, and each body is one call into the vendored Krea2Edit
classes (`creator/krea2edit/`), which are never registered themselves. That
package's docstring says what the two halves are and why they are copied; this
module only fixes the call shape.

**Which picture is which.** Upstream's convention, and the training's: with two
references the first is the scene and the second the subject — frame 1 and
frame 2 — and the `ref_boost` / `ref_position` pair applies to the *last* one,
`_a` to the first. With one reference it is the last, so the subject dials are
the only ones in play. `still.emit_graph` hands the pictures over in slot
order, which `compile_image.cast_into_still` already writes as plain pictures
first and a cast member's after: the scene, then the person.
"""

from comfy_api.latest import io

from . import still


class ContinuityKrea2EditPatch(io.ComfyNode):
    """The references laid into Krea 2's token sequence as clean frames."""

    @classmethod
    def define_schema(cls):
        places = list(still.PLACEMENTS)
        return io.Schema(
            node_id="ContinuityKrea2EditPatch",
            display_name="Continuity Krea 2 Edit (references)",
            category="Continuity/internal",
            description="The Krea 2 Identity / General Edit reference path over a Krea 2 model, "
                        "from the vendored Krea2Edit nodes.",
            is_dev_only=True,
            inputs=[
                io.Model.Input("model", tooltip="Krea 2, with the edit LoRA already patched on."),
                io.Vae.Input("vae"),
                io.Latent.Input("target",
                    tooltip="The latent the sampler starts from — tells the patch the output "
                            "grid so the references are encoded before sampling."),
                io.Image.Input("image", tooltip="The first reference: the scene, or the only picture."),
                io.Image.Input("image_b", optional=True,
                    tooltip="The second reference, the subject, when there are two."),
                io.Float.Input("boost", default=1.0, min=0.0, max=20.0, step=0.05,
                    tooltip="Likeness of the last reference: >1 pulls harder toward it."),
                io.Float.Input("boost_a", default=1.0, min=0.0, max=20.0, step=0.05,
                    tooltip="Likeness of the first reference when there are two."),
                io.Combo.Input("place", options=places, default=places[0],
                    tooltip="Where the last reference sits: pinned onto the output layout, or beside it."),
                io.Combo.Input("place_a", options=places, default=places[0],
                    tooltip="Where the first reference sits when there are two."),
            ],
            outputs=[io.Model.Output()],
        )

    @classmethod
    def execute(cls, model, vae, target, image, boost, boost_a, place, place_a,
                image_b=None) -> io.NodeOutput:
        from ...krea2edit import nodes as port

        # Upstream takes a source latent as its required input and then, with
        # the pixel path wired, never reads it: the pictures are fitted and
        # encoded at the target's grid instead. The target is a latent of the
        # right space to hand it.
        return io.NodeOutput(port.Krea2EditModelPatch().patch(
            model, target, vae=vae, source_image=image, source_image_b=image_b,
            target_latent=target, fit_mode="fit",
            ref_boost=boost, ref_boost_a=boost_a,
            ref_position=still.PLACEMENTS[place], ref_position_a=still.PLACEMENTS[place_a])[0])


class ContinuityKrea2EditEncode(io.ComfyNode):
    """The instruction read by Qwen3-VL with the references in view."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ContinuityKrea2EditEncode",
            display_name="Continuity Krea 2 Edit (grounded encode)",
            category="Continuity/internal",
            description="The Krea 2 edit instruction encoded with the references in view, "
                        "from the vendored Krea2Edit nodes.",
            is_dev_only=True,
            inputs=[
                io.Clip.Input("clip"),
                io.String.Input("prompt", multiline=True, default=""),
                io.Image.Input("image"),
                io.Image.Input("image_b", optional=True),
                io.Int.Input("grounding_px", default=still.GROUNDING_PX, min=0, max=4096, step=64,
                    tooltip="The longest side the text encoder sees each picture at."),
            ],
            outputs=[io.Conditioning.Output()],
        )

    @classmethod
    def execute(cls, clip, prompt, image, grounding_px, image_b=None) -> io.NodeOutput:
        from ...krea2edit import nodes as port

        return io.NodeOutput(port.Krea2EditGroundedEncode().encode(
            clip, prompt, image=image, image_b=image_b, grounding_px=grounding_px)[0])


NODES = [ContinuityKrea2EditPatch, ContinuityKrea2EditEncode]

"""The node that puts a saved reference into a graph: `ContinuityRefModReference`.

The still families render through graphs of core nodes (`render_image.emit`),
and a reference there is `LoadImage` → `VAEEncode` → `ReferenceLatent`. A
RefMod is that encode already done, so the graph needs one node that reads
the file and chains what it holds onto the conditioning — every reference in
it, because a Klein pack's file is a *picture set*, B latents of one person,
and both Klein packs append each of them to `reference_latents` on its own
(`refmod._klein_header`). So this is the `ReferenceLatent` step itself over a
file rather than a loader that hands back one LATENT: a file of one reference
is one entry, a set of twenty-two is twenty-two, and the family's cap on
pictures stays a cap on pictures.

`space` is the family's latent space (`declare.REFMOD["space"]`), and a file
in another is refused by name here, at the graph, since the compiler never
opens the file: a Klein still handed somebody's H3 mod says so rather than
attending to a tensor of the wrong shape.

H3 reads its mods on the render thread inside its own encode
(`families/h3/encode._mod_of`) and never needs a node.

MiniMax H3 Image reads mods in its own space (`refmod.SPACES`) through
core's `MiniMaxH3ImageConditioning`, which takes pictures, not latents: it
shows each to the vision tower and anchors its encode as a `minimax_refs`
block. The node is shown the picture a mod hangs on, and
`ContinuityRefModH3ImageAnchor` then puts the file's latent in that slot's
block. Replacing a block in place rather than appending one keeps the blocks
in `<Picture N>` order, which is how the model pairs an anchor with its
picture. A mod with no picture behind it has to be shown as something, so
`ContinuityRefModLatent` hands the file back as a LATENT for a `VAEDecode`.
"""

import node_helpers
from comfy_api.latest import io

from . import media, refmod


class ContinuityRefModReference(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ContinuityRefModReference",
            display_name="Continuity RefMod Reference",
            category="Continuity",
            description="Chain a saved reference (models/refmods) onto the conditioning "
                        "as reference latents — every reference the file holds.",
            inputs=[io.Conditioning.Input("conditioning"),
                    io.String.Input("name", default=""),
                    io.String.Input("space", default=refmod.KLEIN_SPACE)],
            outputs=[io.Conditioning.Output()],
        )

    @classmethod
    def fingerprint_inputs(cls, conditioning, name, space, **kwargs):
        # The file's stamp beside its name: `media.stamp` is path, mtime and
        # size, so a mod remade in place is not served from the cache.
        try:
            return (name, space, media.stamp(name))
        except media.MediaError:
            return (name, space, None)

    @classmethod
    def execute(cls, conditioning, name, space) -> io.NodeOutput:
        try:
            path = refmod.resolve(name)
            meta = refmod.header(path)
            if meta["space"] != space:
                raise refmod.RefModError(
                    f"{name} is a {refmod.space_label(meta['space'])} RefMod, and this "
                    f"family reads {refmod.space_label(space)} ones — hang the picture "
                    f"it was made of on the member instead")
            latents = refmod.load_latents(path, meta)
        except refmod.RefModError as exc:
            raise ValueError(str(exc)) from exc
        return io.NodeOutput(node_helpers.conditioning_set_values(
            conditioning, {"reference_latents": latents}, append=True))


def _one_still(name, space):
    """`name` -> its one image latent, `[1, 24, 1, h, w]` for MiniMax H3
    Image, refusing a file in another space, a clip and a set by name."""
    try:
        path = refmod.resolve(name)
        meta = refmod.header(path)
        if meta["space"] != space:
            raise refmod.RefModError(
                f"{name} is a {refmod.space_label(meta['space'])} RefMod, and this "
                f"family reads {refmod.space_label(space)} ones — hang the picture "
                f"it was made of on the member instead")
        if meta["kind"] != "image":
            raise refmod.RefModError(
                f"{name} is a clip or a stack, and a still reads pictures — attach "
                f"one of the pictures it was made of instead")
        return refmod.load_latent(path, meta)
    except refmod.RefModError as exc:
        raise ValueError(str(exc)) from exc


def _stamp(name):
    try:
        return media.stamp(name)
    except media.MediaError:
        return None


class ContinuityRefModLatent(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ContinuityRefModLatent",
            display_name="Continuity RefMod Latent",
            category="Continuity",
            description="A saved reference (models/refmods) of one still, as a latent "
                        "to decode.",
            inputs=[io.String.Input("name", default=""),
                    io.String.Input("space", default=refmod.DEFAULT_SPACE)],
            outputs=[io.Latent.Output()],
        )

    @classmethod
    def fingerprint_inputs(cls, name, space, **kwargs):
        return (name, space, _stamp(name))

    @classmethod
    def execute(cls, name, space) -> io.NodeOutput:
        return io.NodeOutput({"samples": _one_still(name, space)})


class ContinuityRefModH3ImageAnchor(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ContinuityRefModH3ImageAnchor",
            display_name="Continuity RefMod H3 Image Anchor",
            category="Continuity",
            description="Read one MiniMax H3 Image picture's reference latent from a "
                        "saved reference (models/refmods) instead of its encode.",
            inputs=[io.Conditioning.Input("conditioning"),
                    io.String.Input("name", default=""),
                    io.String.Input("space", default="h3_image"),
                    io.Int.Input("slot", default=0, min=0, max=99)],
            outputs=[io.Conditioning.Output()],
        )

    @classmethod
    def fingerprint_inputs(cls, conditioning, name, space, slot, **kwargs):
        return (name, space, slot, _stamp(name))

    @classmethod
    def execute(cls, conditioning, name, space, slot) -> io.NodeOutput:
        latent = _one_still(name, space)
        out = []
        for embedding, extra in conditioning:
            refs = list(extra.get("minimax_refs") or [])
            if slot >= len(refs):
                raise ValueError(
                    f"{name}: Picture {slot + 1} has no reference block to read it into "
                    f"— the conditioning node needs the VAE connected")
            # Where the encode it replaces lived, in its dtype: the model
            # casts nothing inside the H3 payload (`model_base` keeps it out
            # of the dtype pass on purpose).
            old = refs[slot]["latent"]
            refs[slot] = {**refs[slot], "latent": latent.to(old.device, dtype=old.dtype),
                          "latent_h": latent.shape[-2], "latent_w": latent.shape[-1]}
            out.append([embedding, {**extra, "minimax_refs": refs}])
        return io.NodeOutput(out)


NODES = [ContinuityRefModReference, ContinuityRefModLatent, ContinuityRefModH3ImageAnchor]

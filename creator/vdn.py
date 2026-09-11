"""VDN-H3 on the sampler row: the stage under `models/vdn`, and the node that
puts it on a MODEL.

Video Delta Net is not an accelerator in the sense the caches are. It is a
different model over the same H3 base: a linear-attention branch beside every
block and two LoRA adapters on the weights, trained by OpenVDN so that nearby
frames keep exact softmax attention inside a window while everything further
away goes through a branch whose cost is constant in clip length. The win
grows with the shot — H3's own attention is quadratic in it — and vanishes on
a short one: at fifteen latent frames or fewer the window covers the whole clip
and the port correctly falls back to dense attention, so a two-second card
pays for the adapters and gains nothing. It is for the long shot, and the
Timeline's pill says so.

**One knob.** The row picks a stage — a directory under `models/vdn` holding
`model_spec.json`, the branch weights and the adapters — or `off`. Everything
else is upstream's validated default (see `vdnh3/__init__.py`): the adapters
merged rather than bypassed, the branch weights placed by free VRAM, the
grouped softmax backend. The trained window is never deviated from.

**Turbo is the row's switch, not a second one.** A stage carries a `turbo`
adapter, the 8-step DMD distillation, and it *replaces* the community turbo
LoRAs rather than stacking on them. So the adapter follows the row's turbo
switch — on, and the distill file the switch engaged is left off the model for
the run (`render.LeadIn`) — and the turbo lead-in holds the adapter off for its
opening steps the way it holds a LoRA file off (`accel.opening`).

**Where it sits.** First of the accelerators, innermost, because it owns each
block's `attn.forward` by object patch and everything that reads the model's
attention has to see this one. KJNodes' sage patches the same key, so the two
are refused together by `accel.plan`; core's kitchen kernel goes through
`optimized_attention_override` and composes — the port keeps its windows on
exact SDPA and lets the base's own attention take the override. The caches
and Spectrum wrap whatever forward is there, and the chunked feed-forward
patches the MLP.

The node here is internal, like `ContinuitySeamHold`: it exists so the graph
has something to build, and its whole body is one call into the vendored port.
"""

import logging
import os

from comfy_api.latest import io

from . import accel

LOG = logging.getLogger("Continuity")

OFF = accel.VDN_OFF

# Upstream's defaults, named once. `merge` because bypass carries bf16 rounding
# noise the deep blocks amplify on the 8-step stages (upstream measured it);
# `auto` and `grouped` because they are what upstream validated the release on.
LORA_MODE = "merge"
BRANCH_WEIGHTS = "auto"
RETAIN_BUFFERS = "auto"
ATTENTION_BACKEND = "grouped"


def register():
    """Where a stage may sit: `vdn/` beside every `diffusion_models/` folder.

    The port registers `vdn/` beside each `loras/` folder, which on a stock
    install is the one `models/` tree and the same answer. On an install that
    reads its models through `extra_model_paths.yaml` it is not: the LoRAs may
    be aimed somewhere else entirely, and a stage rides on the diffusion
    models, so the folder the checkpoints came from is where somebody will put
    it. Registered on top of the port's own, not instead — `add_model_folder_path`
    keeps a path it already has. Cheap, and asked each time so a tree added
    after boot is seen.
    """
    import folder_paths

    for base in {os.path.dirname(p) for p in folder_paths.get_folder_paths("diffusion_models")}:
        folder_paths.add_model_folder_path("vdn", os.path.join(base, "vdn"))


def checkpoints():
    """The stages under `models/vdn`, by relative directory name.

    Asked of the port rather than of `folder_paths` directly: a stage is a
    directory, not a file, and which directories count is the port's rule (a
    `linear_branch/` holding either the bf16 or the int8 branch file).
    """
    from .vdnh3 import spec

    register()
    return spec.list_vdn_checkpoints()


def upstream_commit():
    """The vendored port's upstream revision — what the settings page prints."""
    from .vdnh3 import REVISION

    return REVISION


def apply(model, checkpoint, turbo):
    """`model` with the VDN stage `checkpoint` on it. -> the patched clone.

    `turbo` puts the stage's 8-step adapter on beside the stage-B one; off, the
    stage-B adapter alone is the 50-step model. The port refuses, by name, a
    stage that does not belong to the loaded base and a model already carrying
    VDN, so nothing here checks either twice.
    """
    from .vdnh3 import nodes as port

    register()
    return port._apply_vdn(
        model, checkpoint, strength=1.0, lora_mode=LORA_MODE,
        branch_weights=BRANCH_WEIGHTS, attention_backend=ATTENTION_BACKEND,
        verbose=False, apply_turbo_adapter=bool(turbo),
        retain_buffers=RETAIN_BUFFERS)[0]


class ContinuityVDN(io.ComfyNode):
    """VDN-H3 on a MiniMax-H3 MODEL — the vendored port, as a node the graph
    can build. See the module docstring for where it sits and why."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ContinuityVDN",
            display_name="Continuity VDN-H3",
            category="Continuity/internal",
            description="Video Delta Net hybrid attention over a MiniMax-H3 model, from a stage under models/vdn.",
            is_dev_only=True,
            inputs=[
                io.Model.Input("model"),
                io.String.Input("checkpoint",
                    tooltip="A stage directory under models/vdn — model_spec.json, linear_branch/ and adapters/."),
                io.Boolean.Input("turbo", default=False,
                    tooltip="Apply the stage's 8-step turbo adapter beside the stage-B one. Off is the 50-step model."),
            ],
            outputs=[io.Model.Output()],
        )

    @classmethod
    def execute(cls, model, checkpoint, turbo) -> io.NodeOutput:
        return io.NodeOutput(apply(model, checkpoint, turbo))


NODES = [ContinuityVDN]

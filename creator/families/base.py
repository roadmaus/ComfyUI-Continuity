"""What a model family is, to the render loop.

The graph-side boundary is the family's segment node: it takes `segment_data`
plus loader links and returns `(model, positive, latent, lead model)`. That
tuple is the contract — everything `core/emit.py` does around it (the clip
branch, seam wiring, the reel, the save node, takes) never looks inside a
conditioning or a latent, which is what lets it stay one loop for every family.

A family supplies the parts a checkpoint's training decided: how a payload
compiles, which weights a generation routes to, what the loaders are, how the
segment node is wired, what a sampler subgraph looks like (H3 emits `KSampler`;
LTX will emit a scheduler, a guider and `SamplerCustomAdvanced`), and the
refine and face passes where the family has them.

The hooks receive `sampling`, `acceleration`, `weights` and `run` as the family
shaped them — the loop passes them through and never reads their fields. Two
exceptions, and they are the contract's fine print:

- The object `emit_loaders` returns must expose `.vae` and `.audio_vae` links.
  The reel layer decodes with them, and that layer is family-neutral by
  construction — core's joint AV latent is what `LTXVConcatAVLatent` calls "any
  AV model".
- `weights` must answer `routed(payload)` — the standing route stamped onto a
  payload before it becomes a cache key, or the payload unchanged.

Hooks that create graph nodes must create them in the order they are called:
node ids are assigned sequentially, and the golden-graph suite holds every
family to byte-identical emissions.
"""


class Family:
    """One model family. Stateless; a singleton per family.

    Subclasses override everything below. The bodies here raise rather than
    pass so a family that forgets a hook fails by name at the call site.
    """

    #: "h3" — the id routes, manifests and tests know the family by.
    id = None
    #: "MiniMax H3" — what a user reads.
    label = None
    #: which kinds of thing the family renders, e.g. {"video", "still"}.
    produces = frozenset()
    #: the family's `canvas.Rules` — its frame grid, its rate, its native edge.
    #: The one thing the loop reads off the family object itself rather than
    #: through a hook: the finished file is written at a frame rate, and that
    #: rate is the one the frame counts were snapped to.
    rules = None

    #: the exception type `compile` raises for a request it refuses. The loop
    #: catches exactly this and prefixes the segment's label.
    compile_error = ValueError

    def weights_from_blob(self, data):
        """The blob's `models` block, as this family's weights object.

        The *keys* of that block are the family's slot ids — a filename under
        `dit` means nothing to a family whose checkpoint slot is called `fl2va`
        — so reading it is the family's job and not the node's. What comes back
        is passed through the loop unread except for `routed(payload)`.
        """
        raise NotImplementedError(f"{self.id}.weights_from_blob")

    def resolve_sampling(self, data, widgets):
        """-> `(sampling, acceleration)` for this queue.

        `widgets` is what the node was called with. A family whose row is the
        node's thirteen frozen widget slots may fall back to them field by
        field; a family whose row is a different shape entirely reads the blob
        and its own defaults, because none of those slots is `video_cfg`.
        """
        raise NotImplementedError(f"{self.id}.resolve_sampling")

    def run_context(self, data):
        """The family's per-queue context, or None — the `run` the loop passes
        through unread. H3's is the turbo lead-in; most families have none."""
        return None

    def preflight(self, sampling, acceleration):
        """Raise for a run that cannot happen — before anything compiles."""
        raise NotImplementedError(f"{self.id}.preflight")

    def compile(self, payload, image_size):
        """One payload -> the family's compiled form.

        The loop treats what comes back as the family's own — with one read
        surface, which is the shared subset the strip's bookkeeping needs:
        the seam fields (`continues`, `feather`, `continues_audio`,
        `audio_tail_s`, `ends_on`, `ends_feather`, `ends_on_audio`,
        `ends_tail_s`), `refine` and `face` (read only for truthiness — their
        contents go back to the family's own hooks). Everything else on the
        object — H3's checkpoint, ordinal labels, reference plan — is protocol
        the loop must never learn. The plan called for splitting those fields
        into a nested payload; the boundary is enforced here instead, because
        every reader of the H3 fields is H3-owned code that moves into this
        package anyway, and a nesting would have churned ~90 sites to move a
        line nobody crosses.
        """
        raise NotImplementedError(f"{self.id}.compile")

    def routes(self, compiled, labels):
        """`{weight slot: label of the first generation that routes to it}`."""
        raise NotImplementedError(f"{self.id}.routes")

    def check(self, weights, where, audio=True, face=False):
        """Raise if a file this render needs was never picked."""
        raise NotImplementedError(f"{self.id}.check")

    def emit_loaders(self, graph, weights, routes):
        """Build the loaders; -> the links object the other hooks receive."""
        raise NotImplementedError(f"{self.id}.emit_loaders")

    def emit_segment(self, graph, links, payload, compiled, weights, sampling,
                     seams, run):
        """The segment node, wired. -> the node whose outs are the contract
        tuple. `seams` maps the segment's seam input names to links the loop
        already built; the hook passes them through untouched."""
        raise NotImplementedError(f"{self.id}.emit_segment")

    def emit_sampler(self, graph, segment, payload, compiled, sampling,
                     acceleration, weights, seed, run):
        """The sampler subgraph over one segment. -> the sampled latent link."""
        raise NotImplementedError(f"{self.id}.emit_sampler")

    def emit_refine(self, graph, links, segment, payload, compiled, weights,
                    seams, latent, sampling, acceleration, seed, run):
        """The two-pass upscale over a sampled latent. -> the refined latent
        link. Called only where the compiled payload asks for one.

        `segment` is the node `emit_segment` returned, because the second stage
        of a two-stage render is a *continuation* of the first and not a second
        render: LTX's takes its conditioning straight off it, so that the guides
        stage one applied are the ones stage two crops. H3 re-emits a segment of
        its own at the larger canvas and ignores this — which is the honest
        difference between refining a latent and re-encoding a request.
        """
        raise NotImplementedError(f"{self.id}.emit_refine")

    def face_payload(self, payload, face):
        """The payload the face pass's conditioning is compiled from."""
        raise NotImplementedError(f"{self.id}.face_payload")

    def emit_face(self, graph, links, payload, compiled, face, written, weights,
                  sampling, acceleration, seed):
        """The face repair over a written pass. `face` is the compiled face
        spec off the *original* payload; `payload`/`compiled` are the crop's
        own. -> the node whose out(0) is the reel and out(1) the pass link,
        the same shape the reel node hands out."""
        raise NotImplementedError(f"{self.id}.emit_face")

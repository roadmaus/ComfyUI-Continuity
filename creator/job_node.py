"""`ContinuityJob`: the node the queue actually runs.

Its own module for one reason — it is the only part of this that needs
`comfy_api`, and `jobs.py` is imported by the route modules, which the suites
load without ComfyUI on the path. The argument for putting this pack's work on
the queue at all is written up there; this is the node that carries it.
"""

import json
import uuid

from comfy_api.latest import io

from . import jobs


class ContinuityJob(io.ComfyNode):
    """One press of one of this pack's buttons, as a node on the queue.

    A single node with a JSON blob rather than a node per kind of work, because
    nothing about this is a graph: there are no wires, nothing upstream, and the
    only reason it is a node at all is that a node is what the queue takes. The
    blob is the request body the route already validated.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id=jobs.NODE_ID,
            display_name="Continuity Job",
            category="Continuity",
            description="Internal: one bench, refine or plate press, on the queue.",
            # Out of the node search entirely. Nobody puts this on a canvas —
            # it is built by `submit`, queued, and thrown away.
            is_dev_only=True,
            # It writes a file (or a rewritten prompt) and returns nothing to a
            # graph, which is the definition of an output node — and is also what
            # makes a prompt containing only this node one the server will run.
            is_output_node=True,
            inputs=[io.String.Input("job", multiline=True, default="{}")],
        )

    @classmethod
    def fingerprint_inputs(cls, job, **kwargs):
        """Never cached.

        Two presses of Trace with the same dials are two tracings — the second
        writes `clip-edges-2.png` — so the execution cache returning the first
        one's result would be a button that stopped working the second time it
        was pressed. A fresh value every call is how a node says that.
        """
        return uuid.uuid4().hex

    @classmethod
    def execute(cls, job) -> io.NodeOutput:
        envelope = json.loads(job)
        kind = envelope.get("kind")
        run = jobs.runner(kind)
        if run is None:
            raise jobs.JobError(f"there is no {kind!r} job in this pack")
        # The request itself, out of the envelope. Nested rather than merged
        # because a refine body has a `kind` of its own — see `jobs.submit`.
        try:
            result = run(envelope.get("body") or {})
        finally:
            jobs.release_all()
        # Under our own key rather than one of core's: `images` and `text` are
        # read by the frontend's own node body, and this node has none.
        return io.NodeOutput(ui={"continuity": [result]})

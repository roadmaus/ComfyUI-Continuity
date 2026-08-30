"""Everything this pack does to a GPU, put on the queue ComfyUI already has.

A bench press, a refine and a plate all used to run the same way: the aiohttp
handler that took the request handed the work to `loop.run_in_executor` and
answered when it came back. That is a thread pool running beside `prompt_worker`,
not behind it — so a tracing, an upscale, a refine and a render could all be on
the one GPU at the same moment, and nothing anywhere knew the other three
existed. `bench.ONE_AT_A_TIME` held the benches apart from each other and from
nothing else.

The queue is the thing that was missing, and ComfyUI has one. So the work goes
through it: `submit` builds a one-node prompt around `ContinuityJob`, validates
it the way `/prompt` does and puts it on `PromptServer.instance.prompt_queue`.
What that buys is not just serialization —

  * Cancel reaches these jobs, because they are what Cancel cancels.
  * The progress bar is the real one. This is the fix for a bug worth naming:
    `global_progress_registry` is a *single* global that is only replaced when a
    prompt starts, so a `ProgressBar` ticked outside one wrote a phantom node
    into the *last render's* registry and rebroadcast that render's whole node
    map under that render's `prompt_id`. A render cancelled mid-node leaves its
    sampler `Running` in there forever, so the next bench press put the card
    back into "Sampling" for a render that had already stopped — and a browser
    refresh did not help, because the stale state was the server's. Queued work
    gets `reset_progress_state` called for it and a real `finish_progress`.
  * `queue_remaining` counts these, so one button can speak for all of it.

The routes keep their validation and their 400s; what changed is the last line
of each, which now enqueues and answers with a `prompt_id` instead of blocking
on the answer. The client waits for `executed`.

The node itself is next door in `job_node.py`, which is the only file here that
needs `comfy_api` — this one stays importable by a test that has not booted
ComfyUI, which is most of them.

**What is deliberately not here.** The previews are `<img src>` GETs fired on
every drag of a dial, and the browser coalescing and caching them is the whole
reason they feel like controls (`routes/control.py` argues this at length). A
queue item per drag position would replay a slider's history after the render
ahead of it finished. They stay HTTP and are gated instead: `busy()` says the
queue is not idle, the surface holds the `src` until it is, and the 409 those
routes return is the enforcement under that — for the second tab, and for the
tab that has not heard `status` yet.

The remote refiner is not here either, and for the opposite reason: it spends
somebody else's GPU, so there is nothing to queue behind.
"""

import json
import logging
import uuid

from server import PromptServer

log = logging.getLogger(__name__)

# What a saved workflow would name, if one could hold this node — none can, since
# `is_dev_only` keeps it out of the search. Frozen anyway: it is written into
# every prompt this module builds, and a rename would be a queue of jobs nobody
# can execute for as long as one is in flight across a restart.
NODE_ID = "ContinuityJob"


class JobError(ValueError):
    """A job body that cannot be run. Reported where the press was."""


# kind -> the function that does it, filled in by `register` below. A table
# rather than a chain of `if`s in `execute`, so a new kind of job is a line in
# whichever module owns that work rather than an edit here.
_KINDS = {}


def register(kind, run):
    """Declare that `kind` is done by `run(body) -> a JSON-able result`."""
    _KINDS[kind] = run


def runner(kind):
    """What does `kind`, or None. The node's half of `register`."""
    return _KINDS.get(kind)


# The bar counts to this rather than to 1, because it is an integer count and a
# fraction is what the benches report. A thousand steps is finer than any bar is
# drawn and coarse enough that a per-frame report is not a message per frame.
BAR_STEPS = 1000


def progress():
    """-> a `tell(fraction)` the benches can call, driving ComfyUI's own bar.

    Which is the whole point of being on the queue: the `token` these benches
    used to send their fraction under, on a channel of their own that only their
    own panel listened to, is now the same bar every node in every render moves.
    """
    import comfy.utils

    bar = comfy.utils.ProgressBar(BAR_STEPS)

    def tell(fraction):
        bar.update_absolute(int(max(0.0, min(1.0, float(fraction))) * BAR_STEPS), BAR_STEPS)

    return tell


def release_all():
    """Give the GPU back at the end of a job, whichever kind it was.

    Every one of these loads weights and holds them for the next press — the
    benches in `bench._HELD`, the refiner in its own slot — and holding them is
    right: a dial moved should not cost two gigabytes off the disk again. Holding
    them *on the GPU* is not. A job ends and the next thing to happen may be a
    render or may be nothing for an hour, and neither wants this sitting there.

    In a `finally`, and each half in its own `try`: a job that failed is exactly
    when the weights are most likely to be stranded.
    """
    from . import bench, refine_local

    for give_back in (bench.release, refine_local.release):
        try:
            give_back()
        except Exception:  # noqa: BLE001 — freeing is best effort; the work already happened
            log.debug("[Continuity] releasing after a job failed", exc_info=True)


# ---- putting one on the queue -----------------------------------------------


async def submit(kind, body, client_id=None):
    """Queue `body` as a `kind` job. -> its `prompt_id`.

    The same four steps `server.post_prompt` takes, because this is the same
    thing arriving by a different door: mint an id, validate, put it on the
    queue, hand the id back. Validation is not a formality — it is what catches
    a `ContinuityJob` the frontend and the server disagree about the shape of,
    and it is cheap on a one-node prompt.

    **The body is nested, not merged.** It was spread next to the kind at first,
    and a refine went out as `{"kind": "refine", **payload}` — where the payload
    is a refine request that has a `kind` of its own saying whether a shot, a
    segment or the whole timeline is being rewritten. The payload's won, and the
    queue got a job of kind "segment" that nothing in this pack does. Any of the
    four bodies could collide the same way, so none of them share a namespace
    with the envelope: `{kind, body}`, and the runner is handed `body` alone.

    `client_id` rides in `extra_data` so the `executed` message comes back to
    the tab that pressed the button, exactly as it does for a render.
    """
    import execution

    prompt_id = str(uuid.uuid4())
    prompt = {"1": {"class_type": NODE_ID,
                    "inputs": {"job": json.dumps({"kind": kind, "body": body})}}}

    valid = await execution.validate_prompt(prompt_id, prompt, None)
    if not valid[0]:
        # A shape mismatch between this module and the node it just built, which
        # is a bug here rather than anything the person pressing can act on.
        log.error("[Continuity] a %s job would not validate: %s", kind, valid[1])
        raise JobError(f"this job could not be queued: {valid[1]}")

    server = PromptServer.instance
    number = server.number
    server.number += 1
    extra_data = {"client_id": client_id} if client_id else {}
    server.prompt_queue.put((number, prompt_id, prompt, extra_data, valid[2], {}))
    return prompt_id


def busy():
    """Whether the queue has anything on it — running or waiting.

    What the gated routes refuse on and what the surfaces hold their previews
    for. Both halves matter: a job that is *pending* is one this preview would
    otherwise jump ahead of, and one that is *running* is the GPU being used.
    """
    queue = getattr(PromptServer.instance, "prompt_queue", None)
    if queue is None:
        return False
    with queue.mutex:
        return bool(queue.queue) or bool(queue.currently_running)


def refuse_if_busy():
    """The 409 a gated route returns, or None to carry on.

    Its own function because three routes say it and they must say it the same
    way: the frontend reads the status, not the sentence.
    """
    if not busy():
        return None
    from aiohttp import web

    return web.json_response(
        {"error": "the queue is busy — this waits for the render ahead of it",
         "busy": True}, status=409)

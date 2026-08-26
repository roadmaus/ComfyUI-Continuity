"""Where the refiner's model runs: a VLM loaded as a ComfyUI text encoder.

`refine.py` builds the request and reads the reply; this is the half that holds
the weights. They live in this process on purpose. A second runtime with its own
copy of the model — an Ollama, an llama.cpp server — is VRAM ComfyUI cannot see
or reclaim, and on a machine already streaming H3's own 25 GB encoder off system
RAM that is the difference between a rewrite that takes twenty seconds and one
that takes ten minutes. A text encoder loaded here is an ordinary entry in
ComfyUI's model list — and one that is *released* the moment its generation
ends (see `release`), because a button's model idling in VRAM between presses
serves nobody. The weights wait on the offload device instead, so the next
press is a copy, not a download.

**It is not H3's own encoder.** That checkpoint is Qwen3-VL-32B truncated to the
first 50 of 64 layers, with no final norm and no `lm_head` — see
`Qwen3VL_32BConfig` in `comfy/text_encoders/llama.py`. It is a conditioning tap,
not a model that can be decoded from: there is no projection back to vocabulary,
and the hidden state it exposes is mid-network. Reusing it would be free in VRAM
and would produce noise, so `_check` names it specifically rather than letting
`generate` return tokens nobody should read. What goes here is a *separate*,
small Qwen3-VL — 4B is plenty, and the phase-5 note that a 7B is enough for
prose still holds a size down.

Everything except the loading is in `refine.py`, unit-tested without torch.
"""

import gc

from .families import refine

# What one generation is allowed to cost when the user has not said. Generation
# is one forward pass per token, so this is the number that decides whether a
# refine is twenty seconds or ten minutes. Set high enough for a whole-timeline
# rewrite of a dozen cards; a model that stops early costs nothing.
#
# It is not a context size. There is no such setting on this backend: the
# tokenizer never truncates, and the prompt is embedded whole however long it
# runs. See `refine.NUM_PREDICT`.
MAX_TOKENS = refine.NUM_PREDICT

# ComfyUI's own `TextGenerate` defaults. They are tuned for exactly this — a
# small instruct model asked for one long structured answer.
TOP_K = 64
TOP_P = 0.95
MIN_P = 0.05
REPETITION_PENALTY = 1.05

# The two ComfyUI loads standalone with their language head intact. The 32B is
# named here as well so picking it produces the real reason rather than
# `KeyError`.
SUPPORTED = ("qwen3vl_4b", "qwen3vl_8b")
TRUNCATED = "qwen3vl_32b"


def list_models():
    """Text encoder files on disk. Names, as `folder_paths` knows them.

    Everything in the folder, not a guessed subset: the H3 encoder and a stack
    of T5s live there too, and a filename filter would be wrong in both
    directions — a renamed Qwen3-VL hidden, someone's `qwen3vl-something` shown
    and still unusable. `_check` decides on the loaded model instead, where the
    answer is knowable.
    """
    try:
        import folder_paths
    except ImportError:  # tests, or anywhere outside ComfyUI
        return []
    return list(folder_paths.get_filename_list("text_encoders"))


# ---- the model --------------------------------------------------------------

_loaded = {"name": None, "clip": None}


def _check(clip, name):
    """Refuse a text encoder that cannot generate, saying which kind it is."""
    inner = getattr(clip.cond_stage_model, clip.cond_stage_model.clip)
    kind = getattr(clip.cond_stage_model, "clip_name", "")

    if kind == TRUNCATED:
        raise refine.RefineError(
            f"'{name}' is H3's own conditioning encoder — Qwen3-VL-32B truncated to "
            f"50 of its 64 layers, with no final norm and no language head. It has "
            f"nothing to decode text with. Load a separate Qwen3-VL 4B or 8B text "
            f"encoder for the refiner."
        )
    if kind not in SUPPORTED:
        raise refine.RefineError(
            f"'{name}' loads as {kind or 'an unrecognised text encoder'}. The refiner "
            f"writes Qwen's chat format, so it needs a Qwen3-VL 4B or 8B text encoder."
        )

    # A model consumed as a mid-network tap is truncated the same way H3's is,
    # whatever it is called. Checked on the config rather than on the name
    # because that is where the fact lives.
    config = inner.transformer.model.config
    if not getattr(config, "final_norm", True):
        raise refine.RefineError(
            f"'{name}' is a truncated conditioning checkpoint — no final norm, so no "
            f"usable output layer. Load a full Qwen3-VL text encoder instead."
        )
    return clip


def load(name):
    """The chosen text encoder, loaded once and kept.

    Kept because the alternative is reading several gigabytes off disk every
    time the button is pressed. Keeping the object does not keep the VRAM:
    `CLIP.generate` goes through `load_models_gpu`, so the weights are an
    ordinary entry in ComfyUI's model list and the next sampler pass evicts them
    exactly as it would evict a checkpoint.
    """
    if not (name or "").strip():
        raise refine.RefineError("no text encoder chosen")
    if _loaded["name"] == name and _loaded["clip"] is not None:
        return _loaded["clip"]

    import comfy.sd
    import folder_paths

    # The old one goes first: two VLMs resident to answer one press is the
    # problem this backend exists to avoid.
    unload()

    path = folder_paths.get_full_path_or_raise("text_encoders", name)
    try:
        clip = comfy.sd.load_clip(
            ckpt_paths=[path],
            embedding_directory=folder_paths.get_folder_paths("embeddings"),
        )
    except refine.RefineError:
        raise
    except Exception as exc:  # noqa: BLE001 — a bad file is a message, not a stack trace
        raise refine.RefineError(f"'{name}' could not be loaded as a text encoder: {exc}") from exc

    _check(clip, name)
    _loaded.update(name=name, clip=clip)
    return clip


def release():
    """Move the held model's weights off the GPU, keeping the object and its RAM.

    Called at the end of every generation. Without it the refiner sits in
    ComfyUI's loaded-model list until something else needs the space — which is
    correct behaviour for a model inside a running graph and wrong for a button:
    a refine may be the last thing that happens for an hour, and idle VRAM
    should be nobody's. The weights land back on the offload device, so the
    next press is a RAM-to-GPU copy rather than a read off disk.
    """
    if _loaded["clip"] is None:
        return
    try:
        import comfy.model_management as mm

        mm.unload_model_and_clones(_loaded["clip"].patcher)
    except Exception:  # noqa: BLE001 — freeing is best effort; generation already happened
        pass


def unload():
    """Drop the held model. ComfyUI frees the VRAM; this frees the rest."""
    if _loaded["clip"] is None:
        return
    try:
        import comfy.model_management as mm

        mm.unload_model_and_clones(_loaded["clip"].patcher)
    except Exception:  # noqa: BLE001 — best effort; the reference below is what matters
        pass
    _loaded.update(name=None, clip=None)
    gc.collect()


# ---- images -----------------------------------------------------------------


def to_tensor(image):
    """A PIL image -> the `[1, H, W, C]` float batch ComfyUI passes around.

    Downscaled to `refine.IMAGE_LONG_EDGE`. The model is looking at the picture
    to say what is in it, and every extra pixel is vision tokens that sit in the
    context for the whole generation, where each of a few thousand output tokens
    attends over them again.
    """
    import numpy
    import torch
    from PIL import Image

    image = image.convert("RGB")
    if max(image.size) > refine.IMAGE_LONG_EDGE:
        image.thumbnail((refine.IMAGE_LONG_EDGE, refine.IMAGE_LONG_EDGE), Image.LANCZOS)
    array = numpy.asarray(image, dtype=numpy.float32) / 255.0
    return torch.from_numpy(array).unsqueeze(0)


# ---- the call ---------------------------------------------------------------

# Who the generation says it is, to ComfyUI's progress channel.
#
# `BaseGenerate.generate` ticks a `ProgressBar` once per token, and the hook
# behind it is written for a node in a running graph: with no executing context
# it falls back to `PromptServer.last_prompt_id`, which `main.py` only ever
# *assigns* when a prompt runs and `server.py` never initialises — so a refine
# pressed before the session's first queue crashes on an attribute that does not
# exist yet. Entering a context of our own means the hook takes both ids from
# there and never reaches that fallback.
#
# The ids are deliberately not a node's. This is a button, not a graph step;
# borrowing whichever node ran last would attribute a minute of token generation
# to something that finished long ago.
PROGRESS_ID = "continuity-refine"


def _progress_context():
    """A named context for work that is real but is not a node."""
    from comfy_execution.utils import CurrentNodeContext

    return CurrentNodeContext(prompt_id=PROGRESS_ID, node_id=PROGRESS_ID)


def chat(name, system, message, images=(), temperature=0.7, seed=-1, max_tokens=None,
         prefill=refine.PREFILL):
    """One generation -> the assistant's raw content string.

    The returned string carries the prefill back, because that is what the
    model was already holding when it started writing and `parse_reply` has to
    read the object whole. The default is the harness's opening brace; a skill
    rewrite passes `""`, because its reply is a plain-text document with no
    shape to hold the model to.

    `max_tokens` is how long the reply may run, already clamped by
    `refine.reply_tokens`. It is the output budget alone — the prompt is never
    truncated to fit anything, and `BaseGenerate.generate` reserves a KV cache of
    the prompt's length plus this.
    """
    clip = load(name)
    max_tokens = refine.reply_tokens(max_tokens) if max_tokens is not None else MAX_TOKENS

    prompt = refine.chatml(system, message, images=len(images), prefill=prefill)
    tokens = clip.tokenize(prompt, images=list(images))

    # Its own clause below, not an `isinstance` inside one: ComfyUI's interrupt
    # derives from `BaseException`, so `except Exception` never sees it.
    import comfy.model_management as mm

    seed = int(seed)
    try:
        with _progress_context():
            generated = clip.generate(
                tokens,
                do_sample=float(temperature) > 0,
                max_length=max_tokens,
                temperature=max(float(temperature), 0.01),
                top_k=TOP_K,
                top_p=TOP_P,
                min_p=MIN_P,
                repetition_penalty=REPETITION_PENALTY,
                seed=seed if seed >= 0 else 0,
            )
    except refine.RefineError:
        raise
    except mm.InterruptProcessingException as exc:
        # The same progress hook that needed the context above also polls the
        # interrupt flag, so ComfyUI's Cancel button reaches a refine. That is a
        # deliberate act and is worth saying so rather than reporting as a fault.
        raise refine.RefineError("the rewrite was cancelled") from exc
    except Exception as exc:  # noqa: BLE001
        raise refine.RefineError(f"'{name}' failed while generating: {type(exc).__name__}: {exc}") from exc
    finally:
        # The generation is over either way, and decoding needs the tokenizer,
        # not the weights. See `release`: a button's model does not idle in VRAM.
        release()

    content = prefill + clip.decode(generated)
    if not content[len(prefill):].strip():
        raise refine.RefineError(
            f"'{name}' returned nothing. It may have hit the token limit before "
            f"writing anything, or the prompt may be longer than its context."
        )
    # A reply that used every token it was given was cut off mid-sentence, and
    # `parse_reply` will fail on the JSON a few lines later with a message about
    # the *shape* of the reply. Said here instead, where the cause is known and
    # the setting that fixes it can be named.
    if len(generated) >= max_tokens:
        raise refine.RefineError(
            f"'{name}' ran out of room after {max_tokens} tokens and the reply is "
            f"cut off. Raise the reply length in the refiner's settings, or refine "
            f"fewer cards at once."
        )
    return content

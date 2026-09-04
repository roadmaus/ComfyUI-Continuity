"""Latent-mask continuation between H3 passes, wired in rather than reimplemented.

`ComfyUI-H3-Motion-Context-MultiRef`
(<https://github.com/seitanism/ComfyUI-H3-Motion-Context-MultiRef>) already
ships the splice+mask math this needs, twice over — once for copying a stored
latent's tail into a fresh target, once for encoding the same prefix live off
decoded pixels when there is no stored latent — and a save/load pair for
carrying a latent across runs. None of the four is reimplemented here: they are
looked up in `nodes.NODE_CLASS_MAPPINGS` and called with the pack's own
argument names, on exactly the terms `creator/accel.py` calls Spectrum, sparse
attention and memory optimization. A missing pack fails loudly, naming itself
and where to get it, rather than falling back to a blended seam nobody asked
for.

**Why a latent tail crosses through disk even within one render.** A masked
seam's source could be this render's own previous pass, sampled a moment ago —
and the temptation is to wire that sampled latent straight across as a live
graph link. `creator/timeline.py`'s `MiniMaxH3Reel` already explains why not:
ComfyUI keeps every node's output alive for the whole execution, and a latent
link held across a multi-segment chain is one more large tensor added to that
total for as long as the chain runs. Saving and reloading costs one small
file. It also means a masked seam behaves identically whether its source is
this render's own pass or a card locked and taken three sessions ago — one
code path, not two. So every pass saves its latent (`save_latent`,
unconditionally, keyed like a take), and a masked seam always loads
(`splice_saved`) rather than ever being handed a live sampled tensor.

**Why a second node for "no saved latent at all".** Genuine supplied footage
was never an H3 pass and has no latent to load, and neither does a take saved
before this feature shipped. Both read back as ordinary decoded frames and
audio — the exact window a blended seam already reads through
(`core/emit.py`'s `inherited_frames`/`inherited_audio`) — and
`MiniMaxH3ExistingVideoMaskedContext` (`splice_live`) builds the identical
masked prefix from them with one VAE encode. What is never regenerated is the
sampling; only a handful of frames are re-encoded.
"""

MASK_NODE = "MiniMaxH3GeneratedAVMaskedContext"
EXISTING_VIDEO_MASK_NODE = "MiniMaxH3ExistingVideoMaskedContext"
SAVE_LATENT_NODE = "MiniMaxH3MotionContextSaveLatent"
LOAD_LATENT_NODE = "MiniMaxH3MotionContextLoadLatent"

_SOURCE_URL = "https://github.com/seitanism/ComfyUI-H3-Motion-Context-MultiRef"
SOURCES = {
    MASK_NODE: _SOURCE_URL,
    EXISTING_VIDEO_MASK_NODE: _SOURCE_URL,
    SAVE_LATENT_NODE: _SOURCE_URL,
    LOAD_LATENT_NODE: _SOURCE_URL,
}

# The half-cosine release across the final audio-latent ticks of the protected
# prefix. Not yet exposed on the timeline's own seam control — see
# `PLAN-latent-mask-continuation.md` §6 — so this is the pack's own default,
# read the same way `accel.py` reads a pack's defaults for the knobs Continuity
# does not override: 8 ticks is ~0.2 s at H3's 40 Hz audio latent rate.
AUDIO_FEATHER_TICKS = 8


def _node_class(node_id):
    """The installed class for `node_id`, or None. Looked up per call, the same
    way `accel.py`'s does: an optional pack installed while ComfyUI is running
    should not need this module reloaded to be seen."""
    import nodes

    return nodes.NODE_CLASS_MAPPINGS.get(node_id)


def _require(node_id):
    node = _node_class(node_id)
    if node is None:
        raise ValueError(
            f"masked continuation needs the '{node_id}' node, which is not "
            f"installed. Get it from {SOURCES[node_id]}, restart ComfyUI, or "
            f"set this seam back to 'blend'."
        )
    return node


class SegmentWithLatent:
    """A segment node whose sampler-bound latent (out 2) has been spliced.

    Mirrors `creator/guide.py`'s `Controlled`, for the same reason: the segment
    contract is four outs and everything downstream — `emit_sampler`,
    `emit_refine`, `emit_face` — only ever reads them positionally. Splicing a
    masked latent in ahead of the sampler needs a fourth thing that answers
    `.out` like a segment without being one, on the same terms a guide already
    is; nothing is copied or re-emitted, so a masked graph differs from an
    unmasked one by exactly the nodes the splice added.
    """

    def __init__(self, segment, latent):
        self._segment = segment
        self._latent = latent

    def out(self, index):
        if index == 2:
            return self._latent
        return self._segment.out(index)


def save_latent(graph, latent, filename_prefix, clip_index):
    """Save a sampled H3 AV latent under the piece's own take numbering.

    `clip_index` is the card's own 1-based `card_no` — the same number
    `_reported`/`take_spec` key a take on — so a re-roll of card N overwrites
    slot N exactly as its `.mp4` already does; no rejects accumulate. ->
    a STRING link naming the file `MiniMaxH3MotionContextLoadLatent` (or a
    later render's `take.latent`) reads back.
    """
    _require(SAVE_LATENT_NODE)
    return graph.node(SAVE_LATENT_NODE, latent=latent,
                      filename_prefix=filename_prefix,
                      clip_index=int(clip_index)).out(0)


def load_latent(graph, latent_path):
    """Load a latent `save_latent` (this render or an earlier one) wrote.

    `latent_path` always names a specific *file* — this render's own Save
    output, or `take.latent` off a held/kept card — never a folder, which is
    what makes `clip_index` inert on the load side: there is no slot to
    re-derive from a filename convention. -> a LATENT link, shaped
    `{"samples": [video, audio]}`, which both mask nodes below accept.
    """
    _require(LOAD_LATENT_NODE)
    return graph.node(LOAD_LATENT_NODE, latent_path=latent_path, clip_index=0).out(0)


def splice_saved(graph, segment, source_latent, context_length):
    """Splice `segment`'s fresh latent from an already-loaded source latent.

    -> `(SegmentWithLatent, trim_frames link)`. `trim_frames` is the exact
    frame count the protected prefix duplicates from the source — feed it
    straight into this pass's own `MiniMaxH3Reel` as `head`.
    """
    _require(MASK_NODE)
    built = graph.node(MASK_NODE,
                       latent=segment.out(2), source_latent=source_latent,
                       context_length=int(context_length),
                       audio_feather_ticks=AUDIO_FEATHER_TICKS)
    return SegmentWithLatent(segment, built.out(0)), built.out(1)


def splice_live(graph, segment, links, source_frames, source_audio,
                context_length, crop="disabled"):
    """Splice `segment`'s fresh latent by VAE-encoding a clip's own window.

    The fallback for a source with no saved latent at all: `source_frames`/
    `source_audio` are the seam's own window, read the same way a blended seam
    already reads one (`core/emit.py`'s `inherited_frames`/`inherited_audio`).
    `source_fps` is always `media.TARGET_FPS`: every clip window Continuity
    decodes is already resampled to it, whatever the source file's native
    rate. -> the same shape as `splice_saved`.
    """
    from ... import media

    _require(EXISTING_VIDEO_MASK_NODE)
    built = graph.node(EXISTING_VIDEO_MASK_NODE,
                       latent=segment.out(2), vae=links.vae,
                       audio_vae=links.audio_vae, source_frames=source_frames,
                       source_audio=source_audio,
                       source_fps=float(media.TARGET_FPS),
                       context_length=int(context_length), crop=crop,
                       audio_feather_ticks=AUDIO_FEATHER_TICKS)
    return SegmentWithLatent(segment, built.out(0)), built.out(1)

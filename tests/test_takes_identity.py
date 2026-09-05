"""A take lands on the card that made it, wherever that card is now (issue #47).

    python3 tests/test_takes_identity.py

The save node names a take by the card's number on the strip *as it was
queued*. The strip is editable while a render runs, so by the time the take
arrives that number may point at another card: a move swaps two, a removal
slides every later card up one. `attachTakes` used to read the number against
the current strip and pin the take on whoever sat there, stamped so that the
"edited since" mark stayed quiet. It now reads it against the snapshot the
timeline body takes on `promptQueued` — the card objects in queue order — and a
card that was removed keeps its take in the history rather than handing it to a
neighbour.

The same number game, on the piece's aspect source: it names a card, and it
follows that card through a move, a copy and a removal the way a seam's source
does.

Skips itself if node is not installed.
"""

import json

import layout

layout.skip_without_node()

from harness import check, passed  # noqa: E402

MIRROR = layout.js("state.js")

SCRIPT = r"""
const s = await import(process.argv[1]);
const strip = () => s.parseTimeline(JSON.stringify({
  version: 2, render: "chained", prompt: "p", aspect: "16:9", short_edge: 768,
  aspect_source: { handle: "img-1", card: 2 },
  segments: ["a", "b", "c"].map((name, n) => ({
    prompt: "shot " + name, duration_s: 5, loras: [],
    assets: n === 1 ? [{ handle: "img-1", kind: "image", role: "first_frame", filename: "tall.png" }] : [],
  })),
}));
const report = (n) => ({ segment: n, filename: "s" + n + ".mp4", subfolder: "takes",
                         duration_s: 5, width: 1280, height: 720, has_audio: true });
const takes = (t) => t.segments.map((seg) => seg.take?.filename?.match(/s\d/)?.[0] ?? null);
const out = {};

// Queued as a, b, c; a and b swapped while the render ran.
{
  const t = strip();
  const queued = s.queuedCards(t);
  [t.segments[0], t.segments[1]] = [t.segments[1], t.segments[0]];
  s.attachTakes(t, [report(1), report(2), report(3)], queued);
  out.moved = { takes: takes(t), prompts: t.segments.map((seg) => seg.prompt) };
}

// Queued as a, b, c; a removed while the render ran.
{
  const t = strip();
  const queued = s.queuedCards(t);
  t.segments.splice(0, 1);
  const landed = s.attachTakes(t, [report(1), report(2), report(3)], queued);
  out.removed = { takes: takes(t), prompts: t.segments.map((seg) => seg.prompt), landed };
}

// The body rebuilt from the widget between queue and report: no object survives,
// so the stamp decides — an unchanged strip lands by number, an edited card does not.
{
  const t = strip();
  const queued = s.queuedCards(t);
  const rebuilt = s.parseTimeline(s.serializeTimeline(t));
  s.attachTakes(rebuilt, [report(1), report(2), report(3)], queued);
  out.rebuilt = takes(rebuilt);
  const edited = s.parseTimeline(s.serializeTimeline(t));
  edited.segments[1].prompt = "shot b, rewritten";
  s.attachTakes(edited, [report(1), report(2), report(3)], queued);
  out.edited = takes(edited);
}

// No snapshot at all — a page that loaded mid-render — is the old behaviour.
{
  const t = strip();
  s.attachTakes(t, [report(2)]);
  out.bare = takes(t);
}

// The take is stamped as the card was queued, so an edit during its own render
// is marked afterwards.
{
  const t = strip();
  const queued = s.queuedCards(t);
  t.segments[0].prompt = "shot a, rewritten mid-render";
  s.attachTakes(t, [report(1)], queued);
  out.markedDuring = [...s.editedSince(t)];
}

// The aspect source follows its card.
{
  const t = strip();
  s.remapContinueFrom(t, (n) => (n === 2 ? 3 : n === 3 ? 2 : n));   // b and c swapped
  out.aspectMoved = t.aspect_source.card;
  const u = strip();
  s.remapContinueFrom(u, (n) => (n === 2 ? null : n > 2 ? n - 1 : n));   // b removed
  out.aspectRemoved = u.aspect_source ?? null;
  const v = strip();
  s.remapContinueFrom(v, (n) => (n > 1 ? n + 1 : n));   // a duplicated
  out.aspectCopied = v.aspect_source.card;
}
console.log(JSON.stringify(out));
"""

got = layout.run(SCRIPT, MIRROR)

check("a moved card keeps its own take",
      got["moved"], {"takes": ["s2", "s1", "s3"],
                     "prompts": ["shot b", "shot a", "shot c"]})
check("a removed card's take goes to nobody",
      got["removed"], {"takes": ["s2", "s3"], "prompts": ["shot b", "shot c"],
                       "landed": True})
check("a rebuilt but unchanged strip lands by number", got["rebuilt"], ["s1", "s2", "s3"])
check("...and a card edited in the rebuilt strip is skipped", got["edited"], ["s1", None, "s3"])
check("no snapshot is the old behaviour", got["bare"], [None, "s2", None])
check("a card edited while its own render ran is marked", got["markedDuring"], [0])
check("the aspect source follows a moved card", got["aspectMoved"], 3)
check("...is dropped with a removed card", got["aspectRemoved"], None)
check("...and slides down past a copy", got["aspectCopied"], 3)

passed("takes land on the cards that made them, and the aspect source follows its card")

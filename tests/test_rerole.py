"""What an attached picture is *for*, changed after the fact.

A file used to be told what it was at the moment it arrived: picked on the Start
frame pill it was the start frame, picked with Add image it was a reference, and
that was the end of it. Changing your mind meant detaching and picking the same
file again on the other pill — which spends a handle, so a prompt that cited
@img-1 came back citing a picture that no longer existed.

`rerole` moves the role instead, and this suite pins what that has to mean: the
handle and the file survive it, a slot that was taken is swapped rather than
emptied, and the four things a frame cannot be — a clip, a sheet, a cutout, a
narrowed reference — are refused with a reason rather than queued and refused by
the compiler.

    python3 tests/test_rerole.py

Skips itself if node is not installed.
"""

import os
import sys

import layout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
STATE = layout.js("state.js")

from harness import check, passed  # noqa: E402

layout.skip_without_node()

SCRIPT = r"""
const s = await import(process.argv[1]);

const image = (handle, filename, extra = {}) =>
  ({ handle, kind: "image", role: "reference", filename, ...extra });

function shot() {
  const piece = s.emptyTimeline();
  const card = piece.segments[0];
  card.prompt = "@img-1 opens it, @img-2 is the wall";
  card.assets.push({ ...image("img-1", "opening.png"), role: "first_frame" },
                   image("img-2", "wall.png"),
                   { handle: "vid-1", kind: "video", role: "reference", filename: "walk.mp4" });
  return card;
}

const roles = (card) => card.assets.map((a) => `${a.handle}:${s.roleOf(a)}:${a.filename}`);
const why = (card, handle, role) =>
  s.reroleBlocked(card, card.assets.find((a) => a.handle === handle), role) ?? "";
const move = (card, handle, role) => {
  s.rerole(card, card.assets.find((a) => a.handle === handle), role);
  return roles(card);
};

// The plain demotion: the shot's opening becomes an ordinary reference.
const demoted = shot();
const afterDemote = move(demoted, "img-1", "reference");

// ...and the plain promotion, into an empty slot.
const promoted = shot();
const afterPromote = move(promoted, "img-2", "last_frame");

// The one this gesture exists for: two frames attached the wrong way round.
const swapped = shot();
s.rerole(swapped, swapped.assets.find((a) => a.handle === "img-2"), "last_frame");
const afterSwap = move(swapped, "img-1", "last_frame");

// A muted reference is out of the run; a keyframe cannot be, and compile
// refuses one that claims to be.
const muted = shot();
muted.assets.find((a) => a.handle === "img-2").enabled = false;
s.rerole(muted, muted.assets.find((a) => a.handle === "img-2"), "first_frame");
const afterUnmute = muted.assets.find((a) => a.handle === "img-2").enabled ?? "gone";

// Everything a frame cannot be, each said in its own words.
const refused = shot();
refused.assets.push(image("img-3", "person.png", { takes: "person" }),
                    image("img-4", "sheet.png", { panels: [image("p-1", "a.png"), image("p-2", "b.png")] }),
                    image("img-5", "cut.png", { panels: [image("p-3", "orig.png", { cut: true })] }));
const blocked = {
  clip: why(refused, "vid-1", "last_frame"),
  narrowed: why(refused, "img-3", "last_frame"),
  sheet: why(refused, "img-4", "last_frame"),
  cutout: why(refused, "img-5", "last_frame"),
  itself: why(refused, "img-1", "first_frame"),
  demote: why(refused, "img-1", "reference"),
};

// A segment that starts from the one before it already has its opening.
const continuing = shot();
continuing.continue = true;
const whileContinuing = {
  start: why(continuing, "img-2", "first_frame") !== "",
  end: why(continuing, "img-2", "last_frame"),
};

console.log(JSON.stringify({
  before: roles(shot()), afterDemote, afterPromote, afterSwap, afterUnmute,
  blocked, whileContinuing,
}));
"""

got = layout.run(SCRIPT, STATE)

check("the card as it stands", got["before"],
      ["img-1:first_frame:opening.png", "img-2:reference:wall.png",
       "vid-1:reference:walk.mp4"])

check("the opening becomes an ordinary reference, under the handle the prompt cites",
      got["afterDemote"],
      ["img-1:reference:opening.png", "img-2:reference:wall.png",
       "vid-1:reference:walk.mp4"])
check("a reference becomes the frame the shot closes on",
      got["afterPromote"],
      ["img-1:first_frame:opening.png", "img-2:last_frame:wall.png",
       "vid-1:reference:walk.mp4"])
check("moving into a slot that is taken swaps the two, and loses neither",
      got["afterSwap"],
      ["img-1:last_frame:opening.png", "img-2:first_frame:wall.png",
       "vid-1:reference:walk.mp4"])
check("a muted reference comes back into the run on its way to being a frame",
      got["afterUnmute"], "gone")

blocked = got["blocked"]
check("a clip cannot be a frame",
      blocked["clip"].startswith("A shot opens and closes on a still."), True)
check("...nor can a reference narrowed to a part of itself",
      blocked["narrowed"].startswith("A frame is used whole"), True)
check("...nor a sheet of several pictures",
      blocked["sheet"].startswith("A sheet is several pictures in one file"), True)
check("...nor a picture cut out of its background",
      blocked["cutout"].startswith("This picture is cut out of its background."), True)
check("the role it already has is never blocked", blocked["itself"], "")
check("...and nothing stops a frame becoming a reference", blocked["demote"], "")

check("a continuing segment's opening is the segment before it",
      got["whileContinuing"]["start"], True)
check("...which says nothing about the frame it closes on",
      got["whileContinuing"]["end"], "")

passed("an attached picture can be told what it is for after the fact")

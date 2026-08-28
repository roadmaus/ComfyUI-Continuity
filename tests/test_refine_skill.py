"""What the skill mode promises: the skill is the whole instruction.

Runs standalone — `python tests/test_refine_skill.py` — with no torch and no
ComfyUI. The load-bearing claims are two. The system prompt is built from the
package's own files and nothing of the harness leaks into it, because the mode
exists to measure the skill on its own. And the reply is taken as written,
with only transport noise removed, because the skill's output contract is a
plain-text document and any shaping of it here would be the harness sneaking
back in.
"""

import importlib.util
import os
import shutil
import sys

import layout
import tempfile
import types
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Through `layout.load`, which knows where a module that moved into a family
# package went. `refine` is bound off the skill module itself so the exception
# type this suite catches is the one the skill actually raises.
skill = layout.load("refine_skill").refine_skill
refine = skill.refine

from harness import FAILURES, check, passed


def expect_error(label, fn, fragment):
    try:
        fn()
    except refine.RefineError as exc:
        if fragment not in str(exc):
            FAILURES.append(f"{label}: raised {exc!r}, wanted it to mention {fragment!r}")
        return
    FAILURES.append(f"{label}: did not raise")


# ---- loading ----------------------------------------------------------------
#
# Exercised against a package built here rather than whatever ships in skills/,
# so the contract outlives the one skill the repo currently holds.

from pathlib import Path  # noqa: E402

tmp = tempfile.mkdtemp()
real_dir = skill.SKILLS_DIR
skill.SKILLS_DIR = Path(tmp)

with zipfile.ZipFile(os.path.join(tmp, "demo.skill"), "w") as z:
    z.writestr("demo/SKILL.md", "---\nname: demo\ndescription: d\n---\n\n# Demo\nRead references/a.md.")
    z.writestr("demo/references/a.md", "the reference text")
    z.writestr("demo/icon.png", b"\x89PNG\x00\xff")

os.makedirs(os.path.join(tmp, "plain"))
with open(os.path.join(tmp, "plain", "SKILL.md"), "w") as f:
    f.write("no frontmatter here")

# A single file is an instruction too: the ask this grew from is a paragraph,
# not a package. Written next to the packages so the listing has to sort them
# together and say which is which.
with open(os.path.join(tmp, "noir.md"), "w") as f:
    f.write("Write everything as 1940s noir.")
with open(os.path.join(tmp, "whole.md"), "w") as f:
    f.write("---\nmode: replace\n---\n\nYou are the prompt writer. Write the document.")
with open(os.path.join(tmp, "notes.png"), "wb") as f:
    f.write(b"\x89PNG\x00\xff")

check("both package forms are listed", skill.list_skills(),
      ["demo", "noir", "plain", "whole"])
check("each entry says what it is and which mode it wants",
      skill.entries(),
      [{"name": "demo", "kind": "skill", "mode": "replace"},
       {"name": "noir", "kind": "prompt", "mode": "add"},
       {"name": "plain", "kind": "skill", "mode": "replace"},
       {"name": "whole", "kind": "prompt", "mode": "replace"}])

noir = skill.load("noir")
check("a plain file is its own body", noir["body"], "Write everything as 1940s noir.")
check("…with nothing bundled beside it", noir["files"], [])
check("…and adds to the built-in prompting unless it says otherwise", noir["mode"], "add")
check("a file that asks to replace it is taken at its word",
      skill.load("whole")["mode"], "replace")
check("frontmatter is off the body either way",
      skill.load("whole")["body"].startswith("You are"), True)
expect_error("a file with nothing in it says so",
             lambda: (open(os.path.join(tmp, "bare.md"), "w").write("---\nmode: add\n---\n"),
                      skill.load("bare"))[1],
             "nothing to tell the model")

# In `add` mode the text lands inside a system prompt the family wrote, so it
# arrives unframed — a loader's header in the middle of it would be the node
# talking over the user.
check("a plain prompt contributes exactly what was written",
      skill.instructions(noir), "Write everything as 1940s noir.")
check("a package contributes its files under their paths",
      "========== references/a.md ==========" in skill.instructions(skill.load("demo")), True)
check("the runtime note is the replace mode's, not the text's",
      skill.RUNTIME_NOTE in skill.instructions(skill.load("demo")), False)
check("a fileless prompt run whole gets the note without the file sentence",
      skill.system_prompt(noir).startswith(skill.PROMPT_NOTE), True)

demo = skill.load("demo")
check("the wrapping folder is packaging, not path",
      [path for path, _ in demo["files"]], ["references/a.md"])
check("frontmatter is stripped", demo["body"].startswith("# Demo"), True)
check("binary files are skipped, not fatal",
      any("icon" in path for path, _ in demo["files"]), False)
check("a bare SKILL.md is a whole skill", skill.load("plain")["body"], "no frontmatter here")
expect_error("a missing skill says where one goes",
             lambda: skill.load("ghost"), "skills/ directory")

# The name is a path component taken from an HTTP body, so it is held to plain
# filenames — a traversal is refused before it touches the filesystem.
for hostile in ("../plain", "a/b", "..", ".hidden", ""):
    expect_error(f"a hostile name is refused: {hostile!r}",
                 lambda h=hostile: skill.load(h), "not a skill name")

# ---- the system prompt ------------------------------------------------------

system = skill.system_prompt(demo)
check("the runtime note leads", system.startswith(skill.RUNTIME_NOTE), True)
check("SKILL.md is fenced by name", "========== SKILL.md ==========" in system, True)
check("references are fenced by path", "========== references/a.md ==========" in system, True)
check("the reference text rides along", "the reference text" in system, True)

# Nothing of the harness. These are the built-in system prompt's own phrases;
# any one of them appearing means the mode is no longer measuring the skill.
for phrase in ("Return one JSON object", "WHAT YOU RETURN", "FIDELITY TO THE REQUEST",
               "OFFICIAL MINIMAX GUIDE"):
    check(f"no harness leak: {phrase!r}", phrase in system, False)

# ---- the real package -------------------------------------------------------
#
# The repo ships skills/minimax-h3-prompt.skill; loading it is the integration
# the mode was built for, so it has to keep loading.

skill.SKILLS_DIR = real_dir
if "minimax-h3-prompt" in skill.list_skills():
    h3 = skill.load("minimax-h3-prompt")
    check("the H3 skill's body survives", "MiniMax H3" in h3["body"], True)
    check("its references come along",
          sorted(path for path, _ in h3["files"]),
          ["references/base-modes.md", "references/reference-mode.md"])

# ---- the user message -------------------------------------------------------

shot = {
    "text": "the door opens",
    "slots": [
        {"handle": "img-1", "label": "<Picture 1>", "image": 1,
         "what": "the target video's first frame (door.png)"},
        {"handle": "aud-1", "what": "a reference audio clip (a.mp3)",
         "note": "you cannot hear it"},
    ],
}
message = skill.user_message(shot, seconds=6, images=1, mode="I2VA")
check("the mode is stated", "This request is I2VA." in message, True)
check("the duration is exact to two decimals", "runs 6.00 seconds" in message, True)
check("slots carry label and handle",
      "<Picture 1> (@img-1) [attached image 1]: the target video's first frame (door.png)" in message,
      True)
check("a slot with no label is named by its handle alone",
      "  @aud-1: a reference audio clip (a.mp3) — you cannot hear it" in message, True)
check("the request text closes the message", message.endswith("the door opens"), True)
check("no attachments is said outright",
      "No images, videos or audio are attached." in skill.user_message({"text": "hi"}), True)
check("a language other than English is asked for",
      "Write the prose and any dialogue in German." in
      skill.user_message({"text": "hi"}, language="German"), True)
check("English is the default and goes unsaid",
      "Write the prose" in skill.user_message({"text": "hi"}, language="English"), False)

# ---- the reply --------------------------------------------------------------

check("a clean reply is untouched",
      skill.parse_reply("integrated_multimodal_description: [Shot 1] x"),
      "integrated_multimodal_description: [Shot 1] x")
check("a leaked think block goes",
      skill.parse_reply("<think>hm</think>\n\ndoc"), "doc")
check("a fenced reply is unwrapped",
      skill.parse_reply("```text\ndoc\n```"), "doc")
check("a fence with chatter around it wins over the chatter",
      skill.parse_reply("Here you go:\n```\ndoc\n```\nHope that helps!"), "doc")
expect_error("an empty reply is an error", lambda: skill.parse_reply("<think>only</think>"),
             "returned nothing")

shutil.rmtree(tmp, ignore_errors=True)

passed("ok")

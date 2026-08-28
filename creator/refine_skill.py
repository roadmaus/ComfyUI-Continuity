"""An agent skill, run as the refiner's whole instruction.

The built-in refiner is a harness: a family's own `refine.py` writes the rules,
strips the guides and dictates a JSON reply, and the family assembles the prompt
around the model's prose. A skill is the opposite bet — a `.skill` package
written for an agentic model (SKILL.md plus reference files) handed over
verbatim, so that the skill's own instructions are the only prompting there is
and the model writes the *finished* prompt document itself, instruction line,
shot markers, timestamps and all. Whether a locally-run Qwen3-VL can carry that without the
harness is exactly what this mode exists to find out, so none of a family's
rules and no reply contract may leak into it.

Skills are written against H3's document form, which is what makes this an H3
mode in practice however family-neutral the transport is: the loader hands the
package over whole and judges nothing, so a skill pinned on a piece whose
encoder reads captions will hand that encoder a sectioned document.

Skills are built for a runtime this backend does not have. Claude reads
SKILL.md's frontmatter, then the body, then opens each reference file the body
points at — progressive disclosure over a file system, plus a user it can ask
questions of. A single `CLIP.generate` call has neither: no tools, no second
turn. So the disclosure is flattened — every bundled file rides along in full,
in place of the read the skill asks for — and a short runtime note (the one
piece of text here that is not the skill's) says so, and says that questions
cannot be asked. That note is the loader shim, not a prompt: it describes the
runtime, never the task.

The reply is taken as it comes. No JSON, no shot count to hold it to — the
skill's own output contract is "a single copy-pasteable plain-text block", and
the only cleanup is transport noise: a leaked `<think>` block, a markdown fence
around the document. What the model writes in labels (`<Picture 1>`) is mapped
back to `@handles` by `refine.normalize_handles` exactly as the harness's
output is, because storage is storage whichever mode wrote it.

**A plain file is a skill too, and usually an addition rather than one.** Not
everyone who wants to say something to the refiner wants to replace it: the ask
this grew from is a user with scenario presets the built-in prompting does not
cover, which is a paragraph, not a package. So a bare `.md` or `.txt` under
`skills/` is listed alongside the packages and loaded the same way, and every
entry carries a *mode*: `replace` hands it over as the whole instruction, which
is what a package means and what everything above describes; `add` leaves the
family's harness — its rules, its guides, its JSON contract — standing and joins
the text on as one more section of the system prompt. `add` is where a plain
file starts, because a paragraph written without knowing what it is replacing
almost always meant to be added; a package starts at `replace`, because that is
what it always was. A file says which it wants in its own frontmatter
(`mode: replace`), and the settings panel offers the switch either way.

No torch, no ComfyUI: like the families' own halves, everything here is ordinary
data and is unit-tested that way. `families/refine.py` is the shared harness the
few functions used below come from.
"""

import re
import zipfile
from pathlib import Path

from .families import refine

SKILLS_DIR = Path(__file__).parent / "skills"

# The one file every skill has, and the one that comes first.
SKILL_MD = "SKILL.md"

# What a single-file instruction may be called. A plain document, in the two
# extensions anyone writing prose in a folder reaches for.
PROMPT_SUFFIXES = (".md", ".txt")

# What the text does to the built-in prompting. See the module docstring.
REPLACE, ADD = "replace", "add"
MODES = (REPLACE, ADD)

_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_MODE_RE = re.compile(r"^mode:\s*(\w+)\s*$", re.MULTILINE)

# What the loader itself says. Runtime facts only — the skill cannot know it is
# being run without tools or turns, and these are the three consequences: the
# files are already here, questions cannot be asked, and the reply is the
# deliverable itself rather than a message with the deliverable in it.
RUNTIME_NOTE = """\
You are running the agent skill packaged below. This is a non-interactive \
runtime: you cannot ask the user questions and you cannot open files. Every \
file bundled with the skill is therefore included in full after SKILL.md — \
where the skill says to read a file, it is already in front of you. Where it \
says to ask the user for missing information, choose something consistent \
with the request instead. Your reply is used verbatim as the skill's \
deliverable: return the finished output as plain text, with no markdown fence \
and nothing before or after it."""

# The same three facts for a single-file prompt, minus the sentence about
# bundled files: there are none, and telling a model to look for files that are
# not there is the loader inventing a runtime the user never packaged.
PROMPT_NOTE = """\
You are following the instructions below. This is a non-interactive runtime: \
you cannot ask the user questions and you cannot open files. Where the \
instructions say to ask for missing information, choose something consistent \
with the request instead. Your reply is used verbatim as the deliverable: \
return the finished output as plain text, with no markdown fence and nothing \
before or after it."""


def _declared_mode(text, fallback):
    """The `mode:` a file asks for in its frontmatter, or `fallback`.

    Read out of the frontmatter block alone — a `mode: replace` written in the
    body is prose about a mode, not a declaration of one — and ignored when it
    names something that is not a mode, because a typo should leave the file
    working rather than break the press with a parse error.
    """
    front = _FRONTMATTER_RE.match(text or "")
    if not front:
        return fallback
    found = _MODE_RE.search(front.group(0))
    return found.group(1) if found and found.group(1) in MODES else fallback


def _kind(entry):
    """What kind of instruction a directory entry is, or None if it is neither.

    -> `("skill" | "prompt", the default mode)`.
    """
    if entry.is_file() and entry.suffix == ".skill":
        return "skill", REPLACE
    if entry.is_dir() and (entry / SKILL_MD).is_file():
        return "skill", REPLACE
    if entry.is_file() and entry.suffix in PROMPT_SUFFIXES:
        return "prompt", ADD
    return None


def entries():
    """Every installed instruction: `{"name", "kind", "mode"}`, by name.

    The panel draws off this rather than off bare names, because the two kinds
    read differently on screen and start in different modes. Listed by what is
    on disk rather than validated here — `load` is where a broken package
    becomes a message.
    """
    if not SKILLS_DIR.is_dir():
        return []
    found = {}
    for entry in sorted(SKILLS_DIR.iterdir()):
        kind = _kind(entry)
        if kind is None:
            continue
        kind, mode = kind
        name = entry.stem if entry.is_file() else entry.name
        # A package and a loose file of the same name: the package wins, which
        # is the order `load` resolves them in too.
        if name in found and found[name]["kind"] == "skill":
            continue
        text = ""
        if kind == "prompt":
            try:
                text = entry.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
        found[name] = {"name": name, "kind": kind,
                       "mode": _declared_mode(text, mode)}
    return [found[name] for name in sorted(found)]


def list_skills():
    """The installed skills, by name. Empty when the folder is bare or missing."""
    return [entry["name"] for entry in entries()]


def _read_zip(path):
    """`{relative path: text}` out of a `.skill` archive.

    The top-level folder most packages wrap their files in is stripped, so the
    same skill loads identically zipped or unpacked. Files that are not text —
    a stray icon, a compiled script — are skipped rather than fatal: the model
    could not have read them either.
    """
    files = {}
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            parts = [p for p in info.filename.split("/") if p and p != "."]
            files["/".join(parts)] = archive.read(info)
    # If everything sits under one folder, that folder is packaging, not path.
    tops = {name.split("/", 1)[0] for name in files if "/" in name}
    if len(tops) == 1 and not any("/" not in name for name in files):
        strip = next(iter(tops)) + "/"
        files = {name[len(strip):]: data for name, data in files.items()}
    out = {}
    for name, data in files.items():
        try:
            out[name] = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
    return out


def _read_dir(path):
    files = {}
    for entry in sorted(path.rglob("*")):
        if not entry.is_file():
            continue
        try:
            files[entry.relative_to(path).as_posix()] = entry.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
    return files


def load(name):
    """One installed instruction -> `{"name", "kind", "mode", "body", "files"}`.

    `body` is SKILL.md — or the whole of a single-file prompt — with its
    frontmatter taken off: the frontmatter is trigger metadata for a runtime
    that chooses between skills, and this runtime was told which one to run.
    `files` is every other bundled text file, in path order, which for the
    packages this was built against means `references/` in the order the names
    sort, and for a plain file is empty. `mode` is what the file asks for; the
    caller may override it, and the settings panel does.
    """
    # The name arrives in an HTTP body and becomes a path component, so it is
    # held to what `list_skills` can produce: one plain filename, no separators,
    # not hidden. Anything else is someone probing the filesystem, not a skill.
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _.-]*", name or ""):
        raise refine.RefineError(f"{name!r} is not a skill name")

    zipped = SKILLS_DIR / f"{name}.skill"
    unpacked = SKILLS_DIR / name
    loose = [SKILLS_DIR / f"{name}{suffix}" for suffix in PROMPT_SUFFIXES]
    if zipped.is_file():
        try:
            files = _read_zip(zipped)
        except zipfile.BadZipFile as exc:
            raise refine.RefineError(f"'{name}.skill' is not a readable skill package: {exc}") from exc
    elif unpacked.is_dir():
        files = _read_dir(unpacked)
    elif any(path.is_file() for path in loose):
        path = next(p for p in loose if p.is_file())
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            raise refine.RefineError(f"'{path.name}' could not be read as text: {exc}") from exc
        body = _FRONTMATTER_RE.sub("", text).strip()
        if not body:
            raise refine.RefineError(f"'{path.name}' is empty — there is nothing to tell the model")
        return {"name": name, "kind": "prompt", "mode": _declared_mode(text, ADD),
                "body": body, "files": []}
    else:
        raise refine.RefineError(
            f"no skill named '{name}' — put a '{name}.skill' file, a '{name}.md' "
            f"file or a '{name}/' folder with a SKILL.md in it under the node's "
            f"skills/ directory"
        )

    if SKILL_MD not in files:
        raise refine.RefineError(f"'{name}' has no {SKILL_MD}, so it is not a skill")
    body = _FRONTMATTER_RE.sub("", files[SKILL_MD]).strip()
    rest = [(path, files[path].strip()) for path in sorted(files) if path != SKILL_MD]
    return {"name": name, "kind": "skill",
            "mode": _declared_mode(files[SKILL_MD], REPLACE),
            "body": body, "files": rest}


def instructions(skill):
    """The skill's own text, whole and unframed — what the user wrote, nothing else.

    Every bundled file is included — the loader does not know which ones this
    request needs, and deciding that is the skill's own step-one logic, which
    the model is reading. Each file sits under a fence naming its path, so "read
    `references/base-modes.md`" resolves to something the model can find. A
    single-file prompt has no such files and comes back as the one paragraph it
    is, with no header bolted onto it: in `add` mode this text lands inside a
    system prompt the family wrote, and a `========== SKILL.md ==========` line
    in the middle of it would be the loader talking over the user.
    """
    if not skill["files"]:
        return skill["body"]
    parts = [f"========== {SKILL_MD} ==========\n{skill['body']}"]
    parts += [f"========== {path} ==========\n{text}" for path, text in skill["files"]]
    return "\n\n".join(parts)


def system_prompt(skill):
    """The runtime note, then the instruction, whole. `replace` mode's whole prompt."""
    note = RUNTIME_NOTE if skill["files"] else PROMPT_NOTE
    return f"{note}\n\n{instructions(skill)}"


def user_message(shot, seconds=None, images=0, mode=None, language=None):
    """The request, said the way a user of the skill would say it.

    Facts only: what the video is, how long it runs, what is attached and what
    job each attachment has. The vocabulary is the skill's — attachments are
    named by the H3 label they will be given, since that is the only name the
    skill knows — with the `@handle` alongside so the model may use either;
    whichever it writes, storage normalises to handles afterwards.
    """
    lines = []
    if mode:
        lines.append(f"This request is {mode}.")
    if seconds:
        lines.append(f"The finished video runs {float(seconds):.2f} seconds.")

    slots = shot.get("slots") or []
    if not slots:
        lines.append("No images, videos or audio are attached.")
    else:
        lines.append("Attached:")
        for slot in slots:
            label = slot.get("label")
            name = f"{label} (@{slot['handle']})" if label else f"@{slot['handle']}"
            where = f" [attached image {slot['image']}]" if slot.get("image") else ""
            extra = f" — {slot['note']}" if slot.get("note") else ""
            lines.append(f"  {name}{where}: {slot['what']}{extra}")
    if images == 1:
        lines.append("The attached image is the picture marked above. Look at it; "
                     "what you write has to match what is actually in it.")
    elif images:
        lines.append(f"The {images} attached images are the pictures marked above, "
                     f"in that order. Look at them; what you write has to match "
                     f"what is actually in them.")
    if shot.get("continues"):
        lines.append(refine.CONTINUES_NOTE)
    if language and language != "English":
        lines.append(f"Write the prose and any dialogue in {language}.")

    lines.append("")
    text = str(shot.get("text") or "").strip()
    lines.append(text if text else "(no request text was written)")
    return "\n".join(lines).strip()


_FENCED_RE = re.compile(r"```(?:\w+)?\n(.*?)```", re.DOTALL)


def parse_reply(content):
    """The model's reply -> the document, as written.

    Transport noise only: a leaked `<think>` block goes, and a reply wrapped in
    (or containing) a markdown fence is unwrapped, because a chat model fences
    a deliverable however firmly it is asked not to. Everything inside is the
    skill's output and is not judged here — the panel is an editor and
    `refine.check` reports what points at nothing.
    """
    text = refine._THINK_RE.sub("", content or "").strip()
    fenced = _FENCED_RE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    if not text:
        raise refine.RefineError("the model returned nothing the skill's output could be read from")
    return text

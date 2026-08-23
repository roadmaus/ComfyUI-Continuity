"""An agent skill, run as the refiner's whole instruction.

The built-in refiner is a harness: `refine.py` writes the rules, strips the
guides, dictates a JSON reply and lets `contextir.py` assemble the prompt around
the model's prose. A skill is the opposite bet — a `.skill` package written for
an agentic model (SKILL.md plus reference files) handed over verbatim, so that
the skill's own instructions are the only prompting there is and the model
writes the *finished* prompt document itself, instruction line, shot markers,
timestamps and all. Whether a locally-run Qwen3-VL can carry that without the
harness is exactly what this mode exists to find out, so nothing from
`refine._RULES` and no reply contract may leak into it.

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

No torch, no ComfyUI: like `refine.py`, everything here is ordinary data and is
unit-tested that way.
"""

import re
import zipfile
from pathlib import Path

from .families.h3 import refine

SKILLS_DIR = Path(__file__).parent / "skills"

# The one file every skill has, and the one that comes first.
SKILL_MD = "SKILL.md"

_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)

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


def list_skills():
    """The installed skills, by name. Empty when the folder is bare or missing.

    A skill is either a `.skill` zip or a directory with a SKILL.md in it, both
    living under `skills/`. Listed by what is on disk rather than validated
    here — `load` is where a broken package becomes a message.
    """
    if not SKILLS_DIR.is_dir():
        return []
    names = set()
    for entry in SKILLS_DIR.iterdir():
        if entry.is_file() and entry.suffix == ".skill":
            names.add(entry.stem)
        elif entry.is_dir() and (entry / SKILL_MD).is_file():
            names.add(entry.name)
    return sorted(names)


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
    """One installed skill -> `{"name", "body", "files": [(path, text)]}`.

    `body` is SKILL.md with its frontmatter taken off — the frontmatter is
    trigger metadata for a runtime that chooses between skills, and this
    runtime was told which one to run. `files` is every other bundled text
    file, in path order, which for the packages this was built against means
    `references/` in the order the names sort.
    """
    # The name arrives in an HTTP body and becomes a path component, so it is
    # held to what `list_skills` can produce: one plain filename, no separators,
    # not hidden. Anything else is someone probing the filesystem, not a skill.
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _.-]*", name or ""):
        raise refine.RefineError(f"{name!r} is not a skill name")

    zipped = SKILLS_DIR / f"{name}.skill"
    unpacked = SKILLS_DIR / name
    if zipped.is_file():
        try:
            files = _read_zip(zipped)
        except zipfile.BadZipFile as exc:
            raise refine.RefineError(f"'{name}.skill' is not a readable skill package: {exc}") from exc
    elif unpacked.is_dir():
        files = _read_dir(unpacked)
    else:
        raise refine.RefineError(
            f"no skill named '{name}' — put a '{name}.skill' file or a '{name}/' "
            f"folder with a SKILL.md in it under the node's skills/ directory"
        )

    if SKILL_MD not in files:
        raise refine.RefineError(f"'{name}' has no {SKILL_MD}, so it is not a skill")
    body = _FRONTMATTER_RE.sub("", files[SKILL_MD]).strip()
    rest = [(path, files[path].strip()) for path in sorted(files) if path != SKILL_MD]
    return {"name": name, "body": body, "files": rest}


def system_prompt(skill):
    """The runtime note, then the skill, whole.

    Every bundled file is included — the loader does not know which ones this
    request needs, and deciding that is the skill's own step-one logic, which
    the model is reading. Each file sits under a fence naming its path, so "read
    `references/base-modes.md`" resolves to something the model can find.
    """
    parts = [RUNTIME_NOTE,
             f"========== {SKILL_MD} ==========\n{skill['body']}"]
    parts += [f"========== {path} ==========\n{text}" for path, text in skill["files"]]
    return "\n\n".join(parts)


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

"""What the picker's listing walk finds, and what it costs to find it.

`server_routes` cannot be imported without ComfyUI, aiohttp and a live
PromptServer to hang its decorators off, and none of those has an opinion about
walking a folder. So the two functions under test are read out of the source and
given a `folder_paths` stub: the real text, none of the server.

    python3 tests/test_assets.py
"""

import ast
import os
import pathlib
import sys

import layout
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Core's table, cut to what the fixtures use. `_classify` asks for one kind at a
# time, so this only has to answer for one kind at a time.
MIME = {
    ".png": "image", ".jpg": "image", ".webp": "image",
    ".mp4": "video", ".mkv": "video",
    ".wav": "audio", ".mp3": "audio",
}


class _FolderPaths:
    """Only the two names `_scan` and `_classify` reach for."""

    @staticmethod
    def filter_files_content_types(files, kinds):
        return [f for f in files if MIME.get(os.path.splitext(f)[1].lower()) in kinds]

    @staticmethod
    def is_within_directory(root, path):
        root = os.path.realpath(root)
        target = os.path.realpath(path)
        return target == root or target.startswith(root + os.sep)


def _load():
    """`_classify` and `_scan` lifted out of server_routes.py by name."""
    source = pathlib.Path(layout.py("server_routes")).read_text(encoding="utf-8")
    wanted = {"_classify", "_scan"}
    picked = [n for n in ast.parse(source).body
              if isinstance(n, ast.FunctionDef) and n.name in wanted]
    missing = wanted - {n.name for n in picked}
    assert not missing, f"server_routes no longer defines {missing}"
    namespace = {"os": os, "folder_paths": _FolderPaths}
    exec(compile(ast.Module(body=picked, type_ignores=[]), "server_routes.py", "exec"), namespace)
    return namespace["_scan"]


_scan = _load()


def _touch(path, payload=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(payload)


def _tree(root):
    """One of everything the walk has to have an answer for."""
    _touch(os.path.join(root, "a.png"), b"12345")
    _touch(os.path.join(root, "notes.txt"))              # not media
    _touch(os.path.join(root, ".hidden.png"))            # hidden file
    _touch(os.path.join(root, "clips", "b.mp4"))
    _touch(os.path.join(root, "clips", "c.wav"))
    _touch(os.path.join(root, "deep", "nested", "d.mp3"))
    _touch(os.path.join(root, ".git", "e.png"))          # hidden folder


def paths(root, annotation=""):
    return sorted(row["path"] for row in _scan(root, annotation))


def test_finds_media_and_skips_the_rest():
    with tempfile.TemporaryDirectory() as root:
        _tree(root)
        assert paths(root) == ["a.png", "clips/b.mp4", "clips/c.wav", "deep/nested/d.mp3"], \
            "the walk lost a file, gained a non-media one, or descended into a dot folder"


def test_rows_carry_what_a_cell_draws():
    with tempfile.TemporaryDirectory() as root:
        _tree(root)
        rows = {row["path"]: row for row in _scan(root)}

        top = rows["a.png"]
        assert top["name"] == "a.png"
        assert top["subfolder"] == ""
        assert top["kind"] == "image"
        assert top["size"] == 5, "size comes off the entry, not off a guess"
        assert top["mtime"] > 0

        nested = rows["deep/nested/d.mp3"]
        assert nested["subfolder"] == "deep/nested", "a subfolder is posix-separated at any depth"
        assert nested["name"] == "d.mp3"
        assert nested["kind"] == "audio"


def test_annotation_rides_on_the_path():
    # The gallery's paths come back annotated, because that suffix is the only
    # thing that survives into creator_data to say which folder this came from.
    with tempfile.TemporaryDirectory() as root:
        _touch(os.path.join(root, "clips", "r.mp4"))
        assert paths(root, " [output]") == ["clips/r.mp4 [output]"]


def test_a_missing_root_is_not_a_crash():
    with tempfile.TemporaryDirectory() as root:
        assert paths(os.path.join(root, "nope")) == []


def test_symlinks():
    """A link out of the root is skipped; a link inside it is a file like any
    other; a linked directory is listed and not descended into, which is
    `os.walk`'s own default and the behaviour this walk replaced."""
    with tempfile.TemporaryDirectory() as outside, tempfile.TemporaryDirectory() as root:
        _touch(os.path.join(outside, "elsewhere.png"))
        _touch(os.path.join(outside, "sub", "buried.png"))
        _touch(os.path.join(root, "real.png"))
        try:
            os.symlink(os.path.join(outside, "elsewhere.png"), os.path.join(root, "escape.png"))
            os.symlink(os.path.join(root, "real.png"), os.path.join(root, "inside.png"))
            os.symlink(os.path.join(outside, "sub"), os.path.join(root, "linked"))
        except (OSError, NotImplementedError) as exc:
            print(f"  symlinks skipped ({type(exc).__name__})")
            return
        found = paths(root)
        assert "escape.png" not in found, "a link out of the root would 404 at execute time"
        assert "linked/buried.png" not in found, "a linked directory must not be descended into"
        assert found == ["inside.png", "real.png"], found


def test_unreadable_directory_is_stepped_over():
    if os.geteuid() == 0:
        print("  unreadable directory skipped (running as root)")
        return
    with tempfile.TemporaryDirectory() as root:
        _touch(os.path.join(root, "a.png"))
        shut = os.path.join(root, "shut")
        _touch(os.path.join(shut, "b.png"))
        os.chmod(shut, 0o000)
        try:
            assert paths(root) == ["a.png"], "one unreadable folder must not lose the listing"
        finally:
            os.chmod(shut, 0o700)


def main():
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print(f"  {test.__name__}")
    print(f"asset listing — {len(tests)} tests, the walk finds what os.walk found")


if __name__ == "__main__":
    main()
    sys.exit(0)

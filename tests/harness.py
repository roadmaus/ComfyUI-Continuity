"""One report per suite, emitted at interpreter exit.

Every suite used to end in its own `if FAILURES: ... sys.exit(1)` block, and
in four files that block drifted above sections added later — every assertion
below it was collected into a list nobody read, and `test_compile.py` shipped
~130 lines of dead checks that way. Reporting from `atexit` removes the class:
there is no block to keep at the bottom, so nothing can land below it.

Usage, at the top of a suite:

    from harness import FAILURES, check, passed

    passed("all contract tests passed")   # optional; the success line verbatim
    check("label", got, want)             # or FAILURES.append(...) for odd shapes

A crash still reports as a crash: the traceback prints, the exit code is the
interpreter's, and the success line is suppressed rather than printed under it.
"""

import __main__
import atexit
import os
import sys

FAILURES = []

# Read at import time: some graph suites rewrite sys.argv to boot ComfyUI.
_stem = os.path.splitext(os.path.basename(getattr(__main__, "__file__", "") or "tests"))[0]
_line = None
_skipped = False
_crashed = False
_stdlib_hook = sys.excepthook


def check(label, got, want):
    if got != want:
        FAILURES.append(f"{label}: got {got!r}, want {want!r}")


def passed(line):
    """The suite's success line, verbatim. Default: 'all {stem} tests passed'."""
    global _line
    _line = line


def skip(reason):
    """Print the skip and exit 0 without a report. For missing environments."""
    global _skipped
    _skipped = True
    print(f"skipped: {reason}")
    sys.exit(0)


def died(reason):
    """The suite cannot run at all — a mirror that will not parse, a helper that
    exited non-zero. Prints, and exits 1 *without* the success line.

    It exists because `sys.exit` is not an error as far as `sys.excepthook` is
    concerned: a helper that printed node's stderr and exited 1 left `_crashed`
    false and `FAILURES` empty, so the report below printed "all tests passed"
    over the top of a stack trace and the interpreter then exited 1. Anyone
    reading the log — or scrolling a run of twenty suites — saw the green line.
    """
    global _crashed
    _crashed = True
    print(reason)
    sys.stdout.flush()
    sys.exit(1)


def _note_crash(exc_type, exc, tb):
    global _crashed
    _crashed = True
    _stdlib_hook(exc_type, exc, tb)


sys.excepthook = _note_crash


def _report():
    if _skipped or _crashed:
        return
    if FAILURES:
        print(f"{len(FAILURES)} failure(s):")
        for failure in FAILURES:
            print(f"  - {failure}")
        # sys.exit cannot set the code from inside atexit; this can — but it
        # skips the interpreter's own stdio teardown, so flush first.
        sys.stdout.flush()
        os._exit(1)
    print(_line or f"all {_stem.removeprefix('test_').replace('_', ' ')} tests passed")


atexit.register(_report)

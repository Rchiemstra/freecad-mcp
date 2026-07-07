"""Run one freecad-mcp pytest marker layer under FreeCADCmd and emit a verdict file.

Invoked from the package root (tools/mcp/freecad-mcp) as::

    FreeCADCmd ci/run_freecad_tests.py

with ``MARKER`` set in the environment (``core`` or ``e2e``). It runs
``pytest -m $MARKER``, writes a JUnit report to ``results_${MARKER}.xml`` and a
``0``/``1`` verdict to ``ci_rc_${MARKER}.txt``.

Verdict is ``0`` ONLY when the JUnit report shows::

    errors == 0 AND failures == 0 AND skipped == 0 AND collected > 0

This is the green-but-lying defence. The cases it exists to catch:

* ``pytest.importorskip("FreeCAD")`` at a module top, or a still-open
  ``xfail(strict=True)``, surface as ``skipped``. pytest then exits 0, so
  FreeCADCmd's own exit code (which the caller treats as authoritative on
  non-zero, but NOT on zero) reports success while nothing was validated.
  ``skipped == 0`` turns that into a loud red.
* A plain test failure or an ``xpass(strict)`` surfaces as ``failures``.
  ``failures == 0`` is included here as defence-in-depth: if FreeCADCmd ever
  swallows pytest's non-zero exit code (the "exit code untrusted" premise),
  the caller's ``rc=$?`` short-circuit would miss it, so the JUnit verdict
  must catch it independently.
* A module that fails to import at collection time surfaces as ``errors``
  (also caught by pytest's non-zero exit, but kept here for symmetry).

The caller step MUST terminate with ``exit "$(cat ci_rc_${MARKER}.txt)"`` so
that, when FreeCADCmd exits 0, the verdict file -- not FreeCADCmd's exit code
-- decides the step's status.

``tests/`` ships without ``__init__.py``, so ``from tests.e2e._helpers import
...`` resolves only when the package root is on ``sys.path`` (the way
``python -m pytest`` puts CWD there). FreeCADCmd runs this script with the
script directory (``ci/``) on ``sys.path[0]``, so we insert CWD and CWD/src
explicitly.
"""
from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET


def _setup_paths() -> None:
    cwd = os.getcwd()
    sys.path.insert(0, cwd)
    src = os.path.join(cwd, "src")
    if os.path.isdir(src):
        sys.path.insert(0, src)


def _i(suite, name: str) -> int:
    v = suite.get(name)
    if v is None or not v.lstrip("-").isdigit():
        return 0
    return int(v)


def _parse_junit(path: str) -> tuple[int, int, int, int]:
    """Return (collected, errors, failures, skipped) summed across testsuites.

    A missing or unparseable report is treated as a single collection error:
    ``(0, 1, 0, 0)`` -> verdict 1.
    """
    try:
        root = ET.parse(path).getroot()
    except (FileNotFoundError, ET.ParseError):
        return 0, 1, 0, 0
    if root.tag == "testsuite":
        suites = [root]
    else:
        suites = list(root.iter("testsuite"))
    collected = errors = failures = skipped = 0
    for suite in suites:
        collected += _i(suite, "tests")
        errors += _i(suite, "errors")
        failures += _i(suite, "failures")
        skipped += _i(suite, "skipped")
    return collected, errors, failures, skipped


def main() -> int:
    marker = os.environ.get("MARKER", "").strip()
    if not marker:
        print("MARKER env var not set; defaulting to 'e2e'", file=sys.stderr)
        marker = "e2e"

    _setup_paths()

    try:
        import pytest
    except Exception as exc:  # pragma: no cover - preflight should preempt this
        print(f"failed to import pytest under FreeCADCmd: {exc!r}", file=sys.stderr)
        with open(f"ci_rc_{marker}.txt", "w") as fh:
            fh.write("1")
        return 2

    junit = f"results_{marker}.xml"
    args = ["-m", marker, "-ra", "--tb=short", f"--junitxml={junit}"]
    try:
        rc = pytest.main(args)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"pytest.main raised: {exc!r}", file=sys.stderr)
        rc = 2

    collected, errors, failures, skipped = _parse_junit(junit)
    verdict = 0 if (errors == 0 and failures == 0 and skipped == 0 and collected > 0) else 1
    with open(f"ci_rc_{marker}.txt", "w") as fh:
        fh.write(str(verdict))

    print(
        f"[run_freecad_tests] marker={marker} pytest_rc={rc} "
        f"collected={collected} errors={errors} failures={failures} "
        f"skipped={skipped} verdict={verdict} -> ci_rc_{marker}.txt"
    )
    return int(rc)


if __name__ == "__main__":
    sys.exit(main())

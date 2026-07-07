"""Preflight import check run under FreeCADCmd (freecad-mcp-load-preflight step).

Verifies the interpreter-identity assumption the core/e2e design rests on:
FreeCADCmd's embedded Python must be the same interpreter whose site-packages
received the editable ``freecad_mcp`` install and ``pytest``. If the image's
``pip`` targets a different python than FreeCADCmd embeds, ``import pytest`` or
``import freecad_mcp`` inside FreeCADCmd fails -- and the core/e2e steps would
then die loudly (caught by the verdict) instead of preflighting cleanly. This
step splits that diagnosis early.

It prints ``PREFLIGHT_OK`` only when ``pytest``, ``freecad_mcp``, ``FreeCAD``,
``Part`` and ``Sketcher`` all import. The caller greps for that sentinel rather
than trusting FreeCADCmd's exit code, because FreeCADCmd can swallow
``sys.exit`` / exceptions and still exit 0 (the same reason the core/e2e steps
read a ``ci_rc`` verdict file instead of trusting the exit code).

Invoked from the package root (tools/mcp/freecad-mcp) as::

    FreeCADCmd ci/preflight_imports.py < /dev/null
"""
from __future__ import annotations

import sys

try:
    import pytest
    import freecad_mcp
    import FreeCAD
    import Part
    import Sketcher
except Exception as exc:
    print(f"PREFLIGHT_FAIL: {exc!r}", file=sys.stderr)
    sys.exit(1)

print(f"PREFLIGHT_OK pytest={pytest.__version__} freecad={FreeCAD.Version()}")
sys.exit(0)

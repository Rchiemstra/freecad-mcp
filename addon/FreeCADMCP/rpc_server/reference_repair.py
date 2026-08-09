"""Recovery-safe inspection and repair of FreeCAD link properties.

These helpers intentionally do not serialize owner shapes and do not recompute by
default.  A document with a stale ``EdgeNNN``/``FaceNNN`` reference can therefore
have all of its link properties repaired before FreeCAD evaluates dependants.
"""

from __future__ import annotations

import FreeCAD

# §3.3 compatibility shims — moved symbols keep their legacy import path.
from .reference_repair_ops.inspect_references import inspect_references_gui
from .reference_repair_ops.repair_references import repair_references_gui
from .worker_protocol import validate_subelement_reference

__all__ = [
    "FreeCAD",
    "inspect_references_gui",
    "repair_references_gui",
    "validate_subelement_reference",
]

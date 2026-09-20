#!/usr/bin/env python3
"""Fast static and architecture gate for the typed ``get_objects`` slice."""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from ci.scan_execution_policy_gates import (  # noqa: E402
    _scan_document_query,
    _scan_public_adapter,
)
from ci.scan_typed_feature_contract import main_for_op as _main_for_op  # noqa: E402

_LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/get_objects.py"
_PUBLIC_ADAPTER = "src/freecad_mcp/operations/core_ops/object_ops.py"


def scan_get_objects_architecture(
    root: Path,
    *,
    source_overrides: Mapping[str, str] | None = None,
) -> list[str]:
    overrides = source_overrides or {}
    violations = _scan_document_query("get_objects", root, overrides)
    public_path = root / _PUBLIC_ADAPTER
    public_source = overrides.get(
        _PUBLIC_ADAPTER,
        public_path.read_text(encoding="utf-8"),
    )
    violations.extend(
        _scan_public_adapter(
            "get_objects",
            public_source,
            include_freecad_call=False,
        )
    )
    leaf_source = overrides.get(_LEAF, (root / _LEAF).read_text(encoding="utf-8"))
    if "build_get_objects_request(" not in leaf_source:
        violations.append(
            "GET_OBJECTS006 typed get_objects leaf missing request builder"
        )
    return violations


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    return _main_for_op("get_objects", typecheck=False)


if __name__ == "__main__":
    raise SystemExit(main())

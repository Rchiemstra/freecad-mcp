#!/usr/bin/env python3
"""Generate shadow capability artifacts into src/freecad_mcp/generated/capabilities/."""

from __future__ import annotations

import sys
from pathlib import Path
from types import MappingProxyType
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from typing_extensions import TypedDict  # noqa: E402

from freecad_mcp.capabilities.generator import write_shadow_outputs  # noqa: E402
from freecad_mcp.collaboration_client import CollaborationClient  # noqa: E402
from freecad_mcp.instrumented_server import InstrumentedFastMCP  # noqa: E402
from freecad_mcp.server_ops.tool_dependencies import ToolDependencies  # noqa: E402
from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime  # noqa: E402


class _SelectorInput(TypedDict, total=False):
    __pydantic_config__ = MappingProxyType({"extra": "forbid"})

    document_name: str
    document_session_uuid: str
    canonical_path: str


def main() -> int:
    bootstrap_unit_test_runtime()
    mcp = InstrumentedFastMCP("shadow-generator")
    connection = MagicMock(name="FreeCADConnection")
    dependencies = ToolDependencies(
        state=object(),
        get_freecad_connection=lambda: connection,
        recovery_compatibility=None,
        collaboration=CollaborationClient(connection),
        document_selector_input=_SelectorInput,
    )
    paths = write_shadow_outputs(mcp=mcp, dependencies=dependencies)
    for name, path in paths.items():
        print(f"{name}: {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

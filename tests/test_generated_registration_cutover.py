"""Phase 21: generated registration cutover."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import MappingProxyType
from unittest.mock import MagicMock

import pytest
from typing_extensions import TypedDict

from freecad_mcp.capabilities.bootstrap import load_frozen_registry_snapshot
from freecad_mcp.capabilities.generator import (
    render_production_registration,
    render_production_client_stubs,
    render_register_order,
    render_tool_export_bind_part,
    shadow_output_root,
)
from freecad_mcp.capabilities.load import all_subject_manifests
from freecad_mcp.capabilities.registry_capture import capture_registry_snapshot
from freecad_mcp.generated.capabilities.register_order import (
    REGISTER_TOOL_MODULE_OBJECTS,
    REGISTER_TOOL_MODULES,
)
from freecad_mcp.generated.capabilities.registration import register_tools
from freecad_mcp.collaboration_client import CollaborationClient
from freecad_mcp.instrumented_server import InstrumentedFastMCP
from freecad_mcp.server_ops.tool_dependencies import ToolDependencies
from freecad_mcp.server_ops.tool_exports.export_names import __all__ as EXPORT_NAMES
from freecad_mcp.tools_register_order import (
    REGISTER_TOOL_MODULE_OBJECTS as SHIM_MODULE_OBJECTS,
    REGISTER_TOOL_MODULES as SHIM_MODULES,
)
from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

pytestmark = pytest.mark.unit

_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "mcp_tool_registry_contract_snapshot.json"
)
_GENERATED_ROOT = shadow_output_root()


class _SelectorInput(TypedDict, total=False):
    __pydantic_config__ = MappingProxyType({"extra": "forbid"})

    document_name: str
    document_session_uuid: str
    canonical_path: str


def _dependencies() -> ToolDependencies:
    connection = MagicMock(name="FreeCADConnection")
    return ToolDependencies(
        state=object(),
        get_freecad_connection=lambda: connection,
        recovery_compatibility=None,
        collaboration=CollaborationClient(connection),
        document_selector_input=_SelectorInput,
    )


def _bind_export_parts() -> tuple[tuple[str, ...], tuple[str, ...]]:
    split_at = "match_subshape"
    index = EXPORT_NAMES.index(split_at)
    return tuple(EXPORT_NAMES[:index]), tuple(EXPORT_NAMES[index:])


def test_tools_register_order_shim_matches_generated_order():
    snapshot = load_frozen_registry_snapshot()
    assert list(SHIM_MODULES) == snapshot["register_order"]
    assert list(REGISTER_TOOL_MODULES) == snapshot["register_order"]
    assert SHIM_MODULE_OBJECTS == REGISTER_TOOL_MODULE_OBJECTS


def test_generated_production_artifacts_match_emitter_output():
    manifests = all_subject_manifests()
    snapshot = load_frozen_registry_snapshot()
    register_modules = tuple(snapshot["register_order"])
    part_1, part_2 = _bind_export_parts()
    from freecad_mcp.capabilities.generator import (
        current_relocated_body_digests,
        load_relocated_body_digests,
    )

    expectations = {
        "register_order.py": render_register_order(register_modules),
        "registration.py": render_production_registration(manifests),
        "tool_export_bind_part_1.py": render_tool_export_bind_part(part_1, part=1),
        "tool_export_bind_part_2.py": render_tool_export_bind_part(part_2, part=2),
        "client_stubs.py": render_production_client_stubs(manifests),
    }
    for name, expected in expectations.items():
        actual = (_GENERATED_ROOT / name).read_text(encoding="utf-8")
        assert actual == expected, f"{name} drifted from emitter output"
    frozen = load_relocated_body_digests()
    current = current_relocated_body_digests(register_modules=register_modules)
    assert current["register_modules"] == frozen["register_modules"]


def test_generated_production_files_are_marked_do_not_edit():
    from freecad_mcp.capabilities.generator import register_modules_root

    for name in (
        "register_order.py",
        "registration.py",
        "tool_export_bind_part_1.py",
        "tool_export_bind_part_2.py",
        "client_stubs.py",
    ):
        text = (_GENERATED_ROOT / name).read_text(encoding="utf-8")
        assert "do not edit" in text.lower()
    sample = next(register_modules_root().glob("tools_*.py"))
    assert "do not edit" in sample.read_text(encoding="utf-8").lower()


def test_old_binder_import_paths_remain_importable():
    bind_part_1 = importlib.import_module(
        "freecad_mcp.server_ops.tool_exports.bind_part_1"
    )
    bind_part_2 = importlib.import_module(
        "freecad_mcp.server_ops.tool_exports.bind_part_2"
    )
    generated_part_1 = importlib.import_module(
        "freecad_mcp.generated.capabilities.tool_export_bind_part_1"
    )
    generated_part_2 = importlib.import_module(
        "freecad_mcp.generated.capabilities.tool_export_bind_part_2"
    )
    assert bind_part_1.bind_tool_exports_part_1 is generated_part_1.bind_tool_exports_part_1
    assert bind_part_1.bind_default_export_namespace is (
        generated_part_1.bind_default_export_namespace
    )
    assert bind_part_2.bind_tool_exports_part_2 is generated_part_2.bind_tool_exports_part_2
    assert bind_part_2.bind_default_export_namespace is (
        generated_part_2.bind_default_export_namespace
    )


def test_binder_shims_mutate_namespace_identically():
    from freecad_mcp.generated.capabilities import (
        tool_export_bind_part_1 as generated_part_1,
        tool_export_bind_part_2 as generated_part_2,
    )
    from freecad_mcp.server_ops.tool_exports.bind_part_1 import (
        bind_tool_exports_part_1 as shim_bind_part_1,
    )
    from freecad_mcp.server_ops.tool_exports.bind_part_2 import (
        bind_tool_exports_part_2 as shim_bind_part_2,
    )

    exports = {name: object() for name in EXPORT_NAMES}
    via_shim: dict[str, object] = {}
    shim_bind_part_1(exports, via_shim)
    shim_bind_part_2(exports, via_shim)

    via_generated: dict[str, object] = {}
    generated_part_1.bind_tool_exports_part_1(exports, via_generated)
    generated_part_2.bind_tool_exports_part_2(exports, via_generated)

    assert via_shim == via_generated
    for name in EXPORT_NAMES:
        assert via_shim[name] is exports[name]


def test_generated_registration_matches_fixture_registry():
    bootstrap_unit_test_runtime()
    mcp = InstrumentedFastMCP("generated-registration-test")
    register_tools(mcp, dependencies=_dependencies())
    captured = capture_registry_snapshot(mcp)
    expected = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    assert captured == expected


def test_server_public_exports_cover_export_names():
    bootstrap_unit_test_runtime()
  # Importing server.py registers tools and binds §3.3 exports.
    server = importlib.import_module("freecad_mcp.server")
    missing = [name for name in EXPORT_NAMES if not hasattr(server, name)]
    assert not missing, f"missing public server exports: {missing!r}"


def test_tool_exports_have_no_duplicate_or_missing_bindings():
    bootstrap_unit_test_runtime()
    import freecad_mcp.server_ops.tool_exports as tool_exports
    from freecad_mcp.server_ops.tool_exports import bind_tool_exports

    exports = {name: object() for name in EXPORT_NAMES}
    bind_tool_exports(exports)
    for name in EXPORT_NAMES:
        assert tool_exports.__dict__[name] is exports[name]

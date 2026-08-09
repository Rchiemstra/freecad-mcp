"""Phase 20: capability manifests and generator."""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from unittest.mock import MagicMock

import pytest
from typing_extensions import TypedDict

from freecad_mcp.capabilities.introspection import import_operation_symbol
from freecad_mcp.capabilities.bootstrap import (
    bootstrap_subject_manifests,
    load_frozen_registry_snapshot,
)
from freecad_mcp.capabilities.generator import shadow_output_root
from freecad_mcp.capabilities.load import all_subject_manifests
from freecad_mcp.capabilities.registration_runtime import register_all_manifests
from freecad_mcp.capabilities.registry_capture import capture_registry_snapshot
from freecad_mcp.capabilities.schema import ExecutionMode, MutationClass, SubjectManifest, ToolEntry
from freecad_mcp.collaboration_client import CollaborationClient
from freecad_mcp.instrumented_server import InstrumentedFastMCP
from freecad_mcp.server_ops.tool_dependencies import ToolDependencies
from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

pytestmark = pytest.mark.unit

_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "mcp_tool_registry_contract_snapshot.json"
)
_GENERATED_REGISTRY = (
    shadow_output_root() / "registry_snapshot.json"
)


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


@pytest.fixture(scope="module")
def manifests() -> tuple[SubjectManifest, ...]:
    bootstrap_unit_test_runtime()
    return all_subject_manifests()


def test_bootstrapped_manifests_cover_frozen_snapshot(manifests):
    snapshot = load_frozen_registry_snapshot()
    manifest_tools = {entry.name for manifest in manifests for entry in manifest.tools}
    assert len(manifest_tools) == snapshot["tool_count"] == 171
    assert manifest_tools == set(snapshot["tool_order"])


def test_generated_registry_snapshot_is_byte_equal_to_fixture():
    assert _GENERATED_REGISTRY.is_file(), "run scripts/generate_capability_shadow.py"
    assert _GENERATED_REGISTRY.read_bytes() == _FIXTURE.read_bytes()


def test_shadow_registration_matches_fixture_registry(manifests):
    bootstrap_unit_test_runtime()
    mcp = InstrumentedFastMCP("shadow-registry-test")
    register_all_manifests(mcp, manifests, dependencies=_dependencies())
    captured = capture_registry_snapshot(mcp)
    expected = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    assert captured == expected


@pytest.mark.parametrize(
    ("subject", "tool_names"),
    [
        (
            "sketch",
            (
                "sketch_constrain_coincident",
                "sketch_constrain_distance",
                "sketch_constrain_radius",
            ),
        ),
        ("assembly", ("create_assembly_joint", "create_assembly_grounded_joint")),
        ("advanced", ("run_fem_analysis",)),
    ],
)
def test_schema_covers_awkward_subjects(manifests, subject, tool_names):
    manifest = next(item for item in manifests if item.subject == subject)
    by_name = {entry.name: entry for entry in manifest.tools}
    for tool_name in tool_names:
        entry = by_name[tool_name]
        assert entry.execution_mode is ExecutionMode.TYPED_GATEWAY
        assert entry.operation_path.startswith("freecad_mcp.")
        assert entry.signature
        assert entry.docstring
        import_operation_symbol(entry.operation_path)


_RELATIVE_IMPORT_SAMPLES = (
    "tools_sketch_create_1",
    "tools_advanced_a",
    "tools_assembly",
    "tools_measure_a",
    "tools_core_document",
)


def test_bootstrapped_operation_paths_are_importable(manifests):
    inline_paths = [
        entry.operation_path
        for manifest in manifests
        for entry in manifest.tools
        if ".capabilities.inline." in entry.operation_path
    ]
    assert inline_paths == [
        "freecad_mcp.capabilities.inline.tools_runtime_info.get_runtime_info"
    ]

    failures: list[str] = []
    samples = {
        entry.operation_path
        for manifest in manifests
        for entry in manifest.tools
        if entry.register_module in _RELATIVE_IMPORT_SAMPLES
    }
    importable_paths = {
        entry.operation_path
        for manifest in manifests
        for entry in manifest.tools
        if ".capabilities.inline." not in entry.operation_path
    }
    for path in sorted(importable_paths):
        try:
            import_operation_symbol(path)
        except ImportError as exc:
            failures.append(f"{path}: {exc}")
    assert not failures, "unresolvable operation_path values:\n" + "\n".join(failures)
    assert samples.issubset(importable_paths)


def test_escape_hatch_registration_uses_hand_written_impl():
    bootstrap_unit_test_runtime()
    from freecad_mcp.capabilities.registration_runtime import register_all_manifests

    manifest = SubjectManifest(
        subject="escape_hatch_fixture",
        register_modules=(),
        tools=(
            ToolEntry(
                name="escape_hatch_fixture_tool",
                docstring="escape hatch fixture",
                signature="(ctx: 'Context') -> 'CallToolResult'",
                operation_path="freecad_mcp.capabilities.inline.fixture.escape",
                rpc_method="escape_hatch_fixture_tool",
                execution_mode=ExecutionMode.ESCAPE_HATCH,
                gui_thread=False,
                mutation_class=MutationClass.READ,
                escape_hatch_impl=(
                    "tests.fixtures.capability_escape_hatch_fixture.hand_written_escape_hatch"
                ),
            ),
        ),
    )
    mcp = InstrumentedFastMCP("escape-hatch-test")
    exports = register_all_manifests(mcp, (manifest,), dependencies=_dependencies())
    expected = import_operation_symbol(manifest.tools[0].escape_hatch_impl)
    assert exports["escape_hatch_fixture_tool"] is expected


def test_generated_shadow_client_stubs_are_inert_placeholders():
    text = (shadow_output_root() / "shadow_client_stubs.py").read_text(encoding="utf-8")
    assert "inert placeholder" in text.lower()
    assert "_invoke_mutation_v2" not in text
    assert "NotImplementedError" in text


def test_generated_shadow_files_are_marked_do_not_edit():
    for name in (
        "shadow_registration.py",
        "shadow_client_stubs.py",
    ):
        text = (shadow_output_root() / name).read_text(encoding="utf-8")
        assert "do not edit" in text.lower()


def test_gateway_dispatch_has_one_entry_per_tool(manifests):
    payload = json.loads(
        (shadow_output_root() / "gateway_dispatch.json").read_text(encoding="utf-8")
    )
    assert payload["tool_count"] == 171
    assert len(payload["entries"]) == 171
    tools = {entry.name for manifest in manifests for entry in manifest.tools}
    assert {item["tool"] for item in payload["entries"]} == tools


def test_shadow_gateway_dispatch_matches_production_gateway_dispatch():
    root = shadow_output_root()
    assert (
        (root / "shadow_gateway_dispatch.json").read_bytes()
        == (root / "gateway_dispatch.json").read_bytes()
    )


def test_bootstrap_is_deterministic():
    first = bootstrap_subject_manifests()
    second = bootstrap_subject_manifests()
    assert [manifest.to_dict() for manifest in first] == [
        manifest.to_dict() for manifest in second
    ]

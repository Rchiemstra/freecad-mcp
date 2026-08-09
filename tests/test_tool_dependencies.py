"""Focused tests for the Phase 19 typed tool registration context."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import MappingProxyType
from unittest.mock import MagicMock

import pytest
from typing_extensions import TypedDict

from freecad_mcp.collaboration_client import CollaborationClient
from freecad_mcp.server_ops.tool_dependencies import ToolDependencies

pytestmark = pytest.mark.unit


class _SelectorInput(TypedDict, total=False):
    __pydantic_config__ = MappingProxyType({"extra": "forbid"})

    document_name: str
    document_session_uuid: str
    canonical_path: str


def _stub_state() -> object:
    """Minimal state double; ToolDependencies does not inspect state fields."""

    return object()


def _collaboration_connection() -> MagicMock:
    connection = MagicMock(name="FreeCADConnection")
    for method in (
        "acquire_document_lock",
        "adopt_dirty_document",
        "get_request_status",
        "claim_acquisition_result",
        "acknowledge_acquisition_claim",
        "cancel_request",
        "reconcile_document_lease",
        "stale_recovery_status",
    ):
        setattr(connection, method, MagicMock(name=method))
    return connection


def _dependencies(
    *,
    state: object | None = None,
    connection: MagicMock | None = None,
    recovery: object | None = None,
    selector: type = _SelectorInput,
) -> ToolDependencies:
    connection = _collaboration_connection() if connection is None else connection
    return ToolDependencies(
        state=state or _stub_state(),
        get_freecad_connection=lambda: connection,
        recovery_compatibility=recovery if recovery is not None else object(),
        collaboration=CollaborationClient(connection),
        document_selector_input=selector,
    )


def test_tool_dependencies_preserves_dependency_identity():
    state = _stub_state()
    connection = _collaboration_connection()
    recovery = {"compat": "token"}
    selector = _SelectorInput
    dependencies = ToolDependencies(
        state=state,
        get_freecad_connection=lambda: connection,
        recovery_compatibility=recovery,
        collaboration=CollaborationClient(connection),
        document_selector_input=selector,
    )

    assert dependencies.state is state
    assert dependencies.get_freecad_connection() is connection
    assert dependencies.recovery_compatibility is recovery
    assert dependencies.collaboration.connection is connection
    assert dependencies.document_selector_input is selector


def test_tool_dependencies_selector_isolation():
    first = _dependencies(selector=_SelectorInput)
    second = _dependencies(selector=dict)

    assert first.document_selector_input is _SelectorInput
    assert second.document_selector_input is dict
    assert first.document_selector_input is not second.document_selector_input


def test_tool_dependencies_is_frozen():
    dependencies = _dependencies()

    with pytest.raises(FrozenInstanceError):
        dependencies.state = _stub_state()  # type: ignore[misc]


def test_tool_dependencies_collaboration_rebind_is_independent_of_connection_getter():
    first_connection = _collaboration_connection()
    second_connection = _collaboration_connection()
    dependencies = _dependencies(connection=first_connection)

    dependencies.collaboration.rebind(second_connection)

    assert dependencies.get_freecad_connection() is first_connection
    assert dependencies.collaboration.connection is second_connection


def test_tool_dependencies_passes_same_bundle_to_multiple_registrations():
    dependencies = _dependencies()
    seen: list[ToolDependencies] = []

    def register(_mcp, *, dependencies: ToolDependencies) -> dict[str, object]:
        seen.append(dependencies)
        return {}

    register("mcp-a", dependencies=dependencies)
    register("mcp-b", dependencies=dependencies)

    assert len(seen) == 2
    assert seen[0] is dependencies
    assert seen[1] is dependencies

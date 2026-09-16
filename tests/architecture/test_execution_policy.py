from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from ci.check_execution_policy_contract import (
    FORBIDDEN_REGISTRY_NAMES,
    scan_execution_policy_completeness,
    scan_typed_rpc_handler_names,
)
from freecad_mcp.capabilities.execution_policies import EXECUTION_POLICIES, policy_for
from freecad_mcp.capabilities.load import all_subject_manifests
from freecad_mcp.capabilities.schema import ExecutionMode, ExecutionPolicy, MutationClass, ToolEntry
from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

pytestmark = pytest.mark.unit

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def manifests():
    bootstrap_unit_test_runtime()
    return all_subject_manifests()


def test_execution_policy_golden_mappings() -> None:
    assert policy_for("body_create") is ExecutionPolicy.DOCUMENT_MUTATION
    assert policy_for("bounding_box") is ExecutionPolicy.DOCUMENT_QUERY
    assert policy_for("open_document") is ExecutionPolicy.DOCUMENT_LIFECYCLE
    assert policy_for("undo") is ExecutionPolicy.HISTORY_OPERATION
    assert policy_for("redo") is ExecutionPolicy.HISTORY_OPERATION
    assert policy_for("export_step") is ExecutionPolicy.EXTERNAL_EFFECT
    assert policy_for("set_color") is ExecutionPolicy.GUI_GLOBAL


def test_execute_code_has_no_cad_policy(manifests) -> None:
    core = next(item for item in manifests if item.subject == "core")
    execute_code = next(entry for entry in core.tools if entry.name == "execute_code")
    assert execute_code.execution_policy is None
    assert execute_code.mutation_class is MutationClass.EXECUTION
    assert "execute_code" not in EXECUTION_POLICIES


def test_execution_policy_is_not_mutation_class() -> None:
    assert ExecutionPolicy is not MutationClass
    assert ExecutionPolicy.DOCUMENT_MUTATION.value != MutationClass.MUTATION.value


def test_registry_counts() -> None:
    counts = Counter(EXECUTION_POLICIES.values())
    assert len(EXECUTION_POLICIES) == 153
    assert counts[ExecutionPolicy.DOCUMENT_MUTATION] == 90
    assert counts[ExecutionPolicy.DOCUMENT_QUERY] == 39
    assert counts[ExecutionPolicy.DOCUMENT_LIFECYCLE] == 5
    assert counts[ExecutionPolicy.HISTORY_OPERATION] == 2
    assert counts[ExecutionPolicy.EXTERNAL_EFFECT] == 4
    assert counts[ExecutionPolicy.GUI_GLOBAL] == 13


def test_typed_rpc_handlers_are_registered() -> None:
    typed_names = scan_typed_rpc_handler_names(REPOSITORY_ROOT)
    assert len(typed_names) == 133
    missing = sorted(
        typed_names - EXECUTION_POLICIES.keys() - FORBIDDEN_REGISTRY_NAMES
    )
    assert missing == []


def test_completeness_scanner_passes() -> None:
    violations = scan_execution_policy_completeness(REPOSITORY_ROOT)
    assert violations == []


def test_completeness_scanner_fails_when_registry_entry_missing() -> None:
    trimmed = {
        name: policy.value
        for name, policy in EXECUTION_POLICIES.items()
        if name != "body_create"
    }
    violations = scan_execution_policy_completeness(
        REPOSITORY_ROOT,
        mcp_policies=trimmed,
    )
    assert any("body_create" in violation for violation in violations)


def test_tool_entry_round_trips_execution_policy() -> None:
    entry = ToolEntry(
        name="export_step",
        docstring="export step",
        signature="()",
        operation_path="freecad_mcp.operations.export_step_operation",
        rpc_method="export_step",
        execution_mode=ExecutionMode.TYPED_GATEWAY,
        gui_thread=False,
        mutation_class=MutationClass.MUTATION,
        execution_policy=ExecutionPolicy.EXTERNAL_EFFECT,
    )
    restored = ToolEntry.from_dict(entry.to_dict())
    assert restored.execution_policy is ExecutionPolicy.EXTERNAL_EFFECT
    assert restored.to_dict()["execution_policy"] == "external_effect"


def test_manifest_spot_checks(manifests) -> None:
    core = next(item for item in manifests if item.subject == "core")
    io_manifest = next(item for item in manifests if item.subject == "io")

    create_document = next(entry for entry in core.tools if entry.name == "create_document")
    execute_code = next(entry for entry in core.tools if entry.name == "execute_code")
    export_step = next(entry for entry in io_manifest.tools if entry.name == "export_step")
    set_color = next(entry for entry in io_manifest.tools if entry.name == "set_color")
    get_document_tree = next(
        entry for entry in io_manifest.tools if entry.name == "get_document_tree"
    )

    assert create_document.execution_policy is ExecutionPolicy.DOCUMENT_LIFECYCLE
    assert execute_code.execution_policy is None
    assert export_step.execution_policy is ExecutionPolicy.EXTERNAL_EFFECT
    assert set_color.execution_policy is ExecutionPolicy.GUI_GLOBAL
    assert get_document_tree.execution_policy is ExecutionPolicy.DOCUMENT_QUERY

"""Permanent template and generated-execution tombstones."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_execution_policy_contract import scan_execution_policy_completeness
from ci.check_template_tombstone_contract import (
    scan_installed_package_tombstones,
    scan_template_tombstones,
    scan_templates_directory,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]


def test_production_template_tombstones_pass() -> None:
    assert scan_template_tombstones(ROOT) == []


def test_templates_directory_would_fail(tmp_path: Path) -> None:
    (tmp_path / "src/freecad_mcp/templates").mkdir(parents=True)
    assert scan_templates_directory(tmp_path) == [
        "template tombstone: src/freecad_mcp/templates must not exist"
    ]


def test_template_resource_import_would_fail() -> None:
    synthetic = "from freecad_mcp.template_resources import render_template_lines\n"
    violations = scan_template_tombstones(
        ROOT,
        source_overrides={"src/freecad_mcp/stub_module.py": synthetic},
    )
    assert any("imports template_resources" in item for item in violations)
    assert any("render_template_lines" in item for item in violations)


def test_generated_execution_in_cad_adapter_would_fail() -> None:
    synthetic = '''
def pad_feature_operation(client, doc_name, body_name, sketch_name, length):
    return _run_code(client, "pad.py")
'''
    relative = "src/freecad_mcp/operations/parametric_ops/pad_feature.py"
    violations = scan_template_tombstones(ROOT, source_overrides={relative: synthetic})
    assert any("pad_feature_operation calls generated execution" in item for item in violations)


def test_legacy_import_in_cad_adapter_would_fail() -> None:
    synthetic = '''
import p2_editing_legacy

def sketch_trim_operation(client, doc_name, sketch_name, geo_index, point_x, point_y):
    return client.sketch_trim(doc_name, sketch_name, geo_index, point_x, point_y)
'''
    relative = "src/freecad_mcp/operations/parametric_ops/sketch_trim.py"
    violations = scan_template_tombstones(ROOT, source_overrides={relative: synthetic})
    assert any("imports legacy module p2_editing_legacy" in item for item in violations)


def test_execute_code_carveout_does_not_fail_production_tree() -> None:
    violations = scan_template_tombstones(ROOT)
    assert not any("execute_code" in item and "calls generated execution" in item for item in violations)
    assert not any("execute_code_async" in item and "calls generated execution" in item for item in violations)


def test_execution_policy_completeness_still_required() -> None:
    assert scan_execution_policy_completeness(ROOT) == []


def test_installed_package_tombstones_pass() -> None:
    assert scan_installed_package_tombstones() == []

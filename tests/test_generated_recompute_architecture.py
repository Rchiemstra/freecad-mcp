"""Architecture gates for native-owned recompute in generated mutations."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from freecad_mcp.operations.diagnostics import validate_movement_follow_operation

pytestmark = pytest.mark.unit


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "src" / "freecad_mcp" / "templates"
ASSEMBLY_BOOTSTRAP = ROOT / "src" / "freecad_mcp" / "assembly_api_bootstrap"
POST_RECOMPUTE_MARKER = "# __FREECAD_MCP_NATIVE_POST_RECOMPUTE__"
RECOMPUTE_CALL = re.compile(r"\.[ \t]*recompute[ \t]*\(")

# These are leaf compatibility APIs, not generated mutation callbacks. Their
# public boolean remains supported for direct FreeCAD-console callers. Every
# signed MCP template that invokes them is separately required to pass False.
COMPATIBILITY_RECOMPUTE_ALLOWLIST = {
    "assembly_create.py": Counter({"doc.recompute()": 1}),
    "create_joint.py": Counter({"assembly.Document.recompute()": 3}),
}

POSTCONDITION_MUTATION = re.compile(
    r"(?:"
    r"addObject|newObject|removeObject|addGeometry|addConstraint|"
    r"setExpression|setAlias|setDatum|renameConstraint|recompute"
    r")\s*\(|"
    r"\.(?:Placement|Shape|Support|AttachmentSupport|MapMode|Visibility)\s*="
)


def _template_sources() -> list[tuple[Path, str]]:
    return [
        (path, path.read_text(encoding="utf-8"))
        for path in sorted(TEMPLATES.rglob("*.txt"))
    ]


def test_generated_templates_never_recompute_inside_the_apply_callback():
    offenders = [
        path.relative_to(TEMPLATES).as_posix()
        for path, source in _template_sources()
        if RECOMPUTE_CALL.search(source)
    ]
    assert offenders == []


def test_native_post_recompute_continuations_are_single_and_read_only():
    marked = 0
    for path, source in _template_sources():
        count = source.count(POST_RECOMPUTE_MARKER)
        if count == 0:
            continue
        marked += 1
        assert count == 1, path
        apply_code, postcondition_code = source.split(POST_RECOMPUTE_MARKER)
        assert apply_code.strip(), path
        assert postcondition_code.strip(), path
        assert not POSTCONDITION_MUTATION.search(postcondition_code), path

    # An exact count makes template additions choose deliberately between a
    # pure apply-only payload and a reviewed read-only continuation.
    assert marked == 59


def test_only_guarded_leaf_compatibility_helpers_retain_recompute_calls():
    observed: dict[str, Counter[str]] = {}
    for path in sorted(ASSEMBLY_BOOTSTRAP.glob("*.py")):
        calls = Counter(
            match.group(0).replace(" ", "")
            for match in re.finditer(
                r"(?:doc|assembly\.Document)\s*\.\s*recompute\s*\(\s*\)",
                path.read_text(encoding="utf-8"),
            )
        )
        if calls:
            observed[path.name] = calls

    assert observed == COMPATIBILITY_RECOMPUTE_ALLOWLIST
    for name, allowed_calls in COMPATIBILITY_RECOMPUTE_ALLOWLIST.items():
        source = (ASSEMBLY_BOOTSTRAP / name).read_text(encoding="utf-8")
        assert source.count("if recompute:") == sum(allowed_calls.values())


@pytest.mark.parametrize(
    "template_name",
    (
        "p7_assembly/create_assembly.py.txt",
        "p7_assembly/create_grounded_joint.py.txt",
        "p7_assembly/create_joint.py.txt",
    ),
)
def test_signed_assembly_templates_suppress_leaf_local_recompute(template_name):
    source = (TEMPLATES / template_name).read_text(encoding="utf-8")
    assert "recompute=False" in source
    assert "recompute=_recompute" not in source


def test_two_phase_movement_probe_is_fail_closed_before_generated_execution():
    connection = MagicMock()

    response = validate_movement_follow_operation(
        connection,
        True,
        "Model",
        "Source",
        ["Dependent"],
        [1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0],
        15.0,
    )

    assert response.isError
    assert response.structuredContent["data"]["error_code"] == (
        "UNSUPPORTED_NATIVE_PHASE_BOUNDARY"
    )
    connection.execute_code.assert_not_called()

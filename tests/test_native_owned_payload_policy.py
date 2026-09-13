"""Generated callbacks cannot manage native transactions or history."""

from pathlib import Path


FORBIDDEN_CALLS = (
    ".openTransaction(",
    ".commitTransaction(",
    ".abortTransaction(",
    ".undo(",
    ".redo(",
    ".setTransactionMode(",
)


def test_generated_payloads_do_not_control_transactions_or_history():
    root = Path(__file__).parents[1] / "src" / "freecad_mcp" / "templates"
    violations = {}
    for path in sorted(root.rglob("*.txt")):
        source = path.read_text(encoding="utf-8")
        found = [token for token in FORBIDDEN_CALLS if token in source]
        if found:
            violations[str(path.relative_to(root))] = found
    assert violations == {}


def test_native_owned_reference_repair_does_not_control_transactions_or_history():
    root = Path(__file__).parents[1]
    path = (
        root
        / "addon"
        / "FreeCADMCP"
        / "rpc_server"
        / "reference_repair_ops"
        / "repair_references.py"
    )
    source = path.read_text(encoding="utf-8")
    assert [token for token in FORBIDDEN_CALLS if token in source] == []

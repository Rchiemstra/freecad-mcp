"""Phase 17 client-side runtime locator removal regressions."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

pytestmark = pytest.mark.unit


def test_headless_preferences_registration_accepts_an_explicit_registry(monkeypatch):
    bootstrap_unit_test_runtime()
    from freecad_mcp.assembly_api_bootstrap import headless_preferences

    monkeypatch.setattr(headless_preferences.App, "GuiUp", False)
    registry: dict[str, object] = {}
    headless_preferences.ensure_headless_preferences_shim(module_registry=registry)

    shim = registry["Preferences"]
    assert shim.__name__ == "Preferences"
    assert callable(shim.preferences)

    existing = object()
    registry["Preferences"] = existing
    headless_preferences.ensure_headless_preferences_shim(module_registry=registry)
    assert registry["Preferences"] is existing


def test_headless_preferences_old_call_uses_bootstrap_registry(monkeypatch):
    bootstrap_unit_test_runtime()
    from freecad_mcp.assembly_api_bootstrap import headless_preferences

    monkeypatch.setattr(headless_preferences.App, "GuiUp", False)
    registry: dict[str, object] = {}
    headless_preferences.bind_headless_module_registry(registry)

    headless_preferences.ensure_headless_preferences_shim()

    assert registry["Preferences"].__name__ == "Preferences"


def test_tool_export_parts_write_only_to_the_explicit_namespace():
    bootstrap_unit_test_runtime()
    from freecad_mcp.server_ops.tool_exports.bind_part_1 import (
        bind_tool_exports_part_1,
    )
    from freecad_mcp.server_ops.tool_exports.bind_part_2 import (
        bind_tool_exports_part_2,
    )
    from freecad_mcp.server_ops.tool_exports.export_names import __all__

    exports = {name: object() for name in __all__}
    namespace: dict[str, object] = {}

    bind_tool_exports_part_1(exports, namespace)
    bind_tool_exports_part_2(exports, namespace)

    assert namespace == exports


def test_tool_export_parts_preserve_one_argument_compatibility():
    bootstrap_unit_test_runtime()
    from freecad_mcp.server_ops import tool_exports

    exports = {name: object() for name in tool_exports.__all__}

    tool_exports.bind_tool_exports_part_1(exports)
    tool_exports.bind_tool_exports_part_2(exports)

    assert all(getattr(tool_exports, name) is value for name, value in exports.items())


def test_client_registration_sources_have_no_runtime_module_locators():
    root = Path(__file__).resolve().parents[1] / "src" / "freecad_mcp"
    paths = (
        root / "assembly_api_bootstrap" / "create_joint.py",
        root / "assembly_api_bootstrap" / "headless_preferences.py",
        root / "server_ops" / "tool_exports" / "bind_part_1.py",
        root / "server_ops" / "tool_exports" / "bind_part_2.py",
        root / "server_ops" / "tool_registration.py",
    )

    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert "importlib.import_module" not in source
        assert "sys.modules[" not in source
        assert " in sys.modules" not in source

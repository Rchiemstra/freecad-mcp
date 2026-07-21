"""Unit tests for isolated MCP port plumbing and interactive GUI tools."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from mcp.types import TextContent

from freecad_mcp.operations.core import get_view_operation
from freecad_mcp.operations.diagnostics import inspect_geometry_operation
from freecad_mcp.operations.interactive import (
    activate_document_operation,
    compare_documents_operation,
    diagnose_helix_operation,
    diagnose_pocket_operation,
    get_selection_operation,
    normalize_view_name,
    open_document_operation,
    select_subshapes_operation,
    set_section_view_operation,
    set_tree_expanded_operation,
)
from freecad_mcp.server_state import ServerState
from tests.helpers.geometric import assert_code_compiles, assert_code_contains


def _ok_conn(output: str = '{"ok": true}'):
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {
        "success": True,
        "message": "Python code execution scheduled. \nOutput: " + output,
        "recompute_errors": [],
    }
    return conn


def _code(conn) -> str:
    return conn.execute_code.call_args[0][0]


def _text(response) -> str:
    content = response.content if hasattr(response, "content") else response
    return " ".join(item.text for item in content if isinstance(item, TextContent))


def _load_script(name: str):
    script = Path(__file__).resolve().parents[1] / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Port / isolation plumbing
# ---------------------------------------------------------------------------


class TestPortPlumbing:
    def test_server_state_default_port_is_9875(self):
        state = ServerState()
        assert state.rpc_port == 9875
        assert state.rpc_host == "127.0.0.1"

    def test_get_freecad_connection_uses_state_port(self, monkeypatch):
        import freecad_mcp.server as server

        monkeypatch.setattr(server.state, "freecad_connection", None)
        monkeypatch.setattr(server.state, "rpc_host", "127.0.0.1")
        monkeypatch.setattr(server.state, "rpc_port", 9876)

        created = {}

        class FakeConn:
            def __init__(self, host, port):
                created["host"] = host
                created["port"] = port

            def ping(self):
                return True

        monkeypatch.setattr(server, "FreeCADConnection", FakeConn)
        conn = server.get_freecad_connection()
        assert created == {"host": "127.0.0.1", "port": 9876}
        assert conn is server.state.freecad_connection
        # cleanup
        server.state.freecad_connection = None

    def test_run_freecad_mcp_forwards_port(self, monkeypatch):
        runner = _load_script("run_freecad_mcp.py")
        captured = {}

        def fake_inprocess(extra):
            captured["extra"] = extra
            return 0

        monkeypatch.setattr(runner, "_run_inprocess", fake_inprocess)
        monkeypatch.setattr(runner, "_run_instrumented", fake_inprocess)
        monkeypatch.delenv("FREECAD_MCP_DEBUG", raising=False)
        monkeypatch.setattr(
            "sys.argv",
            ["run_freecad_mcp.py", "--host", "127.0.0.1", "--port", "9876"],
        )
        assert runner.main() == 0
        assert "--port" in captured["extra"]
        assert "9876" in captured["extra"]

    def test_setup_cursor_mcp_isolated_preserves_freecad(self, tmp_path, monkeypatch):
        setup = _load_script("setup_cursor_mcp_isolated.py")
        config = tmp_path / ".cursor" / "mcp.json"
        config.parent.mkdir(parents=True)
        original = {
            "mcpServers": {
                "freecad": {"command": "keep-me", "args": ["a"]},
            }
        }
        config.write_text(json.dumps(original), encoding="utf-8")

        monkeypatch.setattr(setup, "_repo_root", lambda: tmp_path)
        monkeypatch.setattr(
            setup, "_freecad_mcp_root", lambda: Path(__file__).resolve().parents[1]
        )

        runner = Path(__file__).resolve().parents[1] / "scripts" / "run_freecad_mcp.py"
        src = Path(__file__).resolve().parents[1] / "src"
        entry = setup._isolated_entry("python", runner, src)
        setup.merge_isolated(config, entry)

        data = json.loads(config.read_text(encoding="utf-8"))
        assert data["mcpServers"]["freecad"] == original["mcpServers"]["freecad"]
        assert "freecad-isolated" in data["mcpServers"]
        assert "9876" in data["mcpServers"]["freecad-isolated"]["args"]
        assert data["mcpServers"]["freecad-isolated"]["env"]["FREECAD_MCP_PORT"] == "9876"

    def test_setup_isolated_profile_refuses_appdata(self, tmp_path, monkeypatch):
        setup = _load_script("setup_isolated_profile.py")
        fake_appdata = tmp_path / "AppData" / "FreeCAD"
        fake_appdata.mkdir(parents=True)
        monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
        with pytest.raises(SystemExit):
            setup._ensure_not_appdata(fake_appdata / "evil")


# ---------------------------------------------------------------------------
# View aliases (no new tool — document via get_view path)
# ---------------------------------------------------------------------------


class TestViewAliases:
    def test_normalize_view_aliases(self):
        assert normalize_view_name("Rear") == "Back"
        assert normalize_view_name("Side") == "Right"
        assert normalize_view_name("SideRight") == "Right"
        assert normalize_view_name("SideLeft") == "Left"
        assert normalize_view_name("Top") == "Top"

    def test_get_view_normalizes_rear_alias(self):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = None
        conn.execute_code.return_value = {
            "success": True,
            "message": "Output: " + json.dumps({"ok": True, "fallback": True}),
            "recompute_errors": [],
        }
        # Headless fallback path still receives normalized view name in label attempt
        get_view_operation(conn, "Rear")
        conn.get_active_screenshot.assert_called()
        assert conn.get_active_screenshot.call_args[0][0] == "Back"


# ---------------------------------------------------------------------------
# Interactive RPC-backed operations
# ---------------------------------------------------------------------------


class TestInteractiveRpcOps:
    def test_open_document_calls_rpc(self):
        conn = MagicMock()
        conn.open_document.return_value = {"ok": True, "document": "V7"}
        text = _text(open_document_operation(conn, r"C:\models\v7.FCStd"))
        assert json.loads(text)["document"] == "V7"
        conn.open_document.assert_called_once_with(r"C:\models\v7.FCStd")

    def test_activate_document_calls_rpc(self):
        conn = MagicMock()
        conn.activate_document.return_value = {"ok": True, "document": "V8"}
        text = _text(activate_document_operation(conn, "V8"))
        assert json.loads(text)["document"] == "V8"

    def test_set_tree_expanded_calls_rpc(self):
        conn = MagicMock()
        conn.set_tree_expanded.return_value = {
            "ok": True,
            "mode": "expand",
            "selected": ["Body"],
        }
        text = _text(
            set_tree_expanded_operation(conn, "Doc", ["Body"], "expand")
        )
        assert json.loads(text)["selected"] == ["Body"]
        conn.set_tree_expanded.assert_called_once_with("Doc", ["Body"], "expand")

    def test_select_subshapes_calls_rpc(self):
        conn = MagicMock()
        conn.select_subshapes.return_value = {
            "ok": True,
            "selected": [{"object": "Box", "sub": "Face1"}],
            "count": 1,
            "errors": [],
        }
        text = _text(
            select_subshapes_operation(conn, "Doc", ["Box:Face1"], clear=True)
        )
        payload = json.loads(text)
        assert payload["count"] == 1
        conn.select_subshapes.assert_called_once_with("Doc", ["Box:Face1"], True)

    def test_get_selection_calls_rpc(self):
        conn = MagicMock()
        conn.get_selection.return_value = {"ok": True, "selection": [], "count": 0}
        assert json.loads(_text(get_selection_operation(conn)))["count"] == 0

    def test_set_section_view_calls_rpc(self):
        conn = MagicMock()
        conn.set_section_view.return_value = {"ok": True, "enabled": True}
        text = _text(
            set_section_view_operation(
                conn, enabled=True, base=[0, 0, 1], normal=[0, 0, 1]
            )
        )
        assert json.loads(text)["enabled"] is True
        conn.set_section_view.assert_called_once()

    def test_rpc_failure_surfaces(self):
        conn = MagicMock()
        conn.set_tree_expanded.return_value = {"ok": False, "error": "no objects"}
        resp = set_tree_expanded_operation(conn, "Doc", [], "expand")
        assert "no objects" in _text(resp)


# ---------------------------------------------------------------------------
# diagnose_pocket / diagnose_helix templates
# ---------------------------------------------------------------------------


class TestDiagnosePocket:
    def test_compiles_and_reports_key_fields(self):
        conn = _ok_conn(
            json.dumps(
                {
                    "ok": True,
                    "pocket": "Pocket",
                    "reversed": True,
                    "length": 2.0,
                    "direction": {"x": 0, "y": 0, "z": -1},
                }
            )
        )
        diagnose_pocket_operation(conn, True, "Doc", "Pocket")
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(
            code,
            "Pocket",
            "Reversed",
            "Direction",
            "Length",
            "Profile",
            "shape_null",
            "direction_vs_sketch",
        )

    def test_returns_json_payload(self):
        payload = {"ok": True, "pocket": "P1", "reversed": False, "length": 3.0}
        conn = _ok_conn(json.dumps(payload))
        text = _text(diagnose_pocket_operation(conn, True, "Doc", "P1"))
        assert '"pocket": "P1"' in text or '"pocket":"P1"' in text.replace(" ", "")


class TestDiagnoseHelix:
    def test_compiles_and_reports_key_fields(self):
        conn = _ok_conn(json.dumps({"ok": True, "helix": "Helix", "pitch": 1.0}))
        diagnose_helix_operation(conn, True, "Doc", "Helix")
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(
            code,
            "Helix",
            "Pitch",
            "Height",
            "LeftHanded",
            "Placement",
            "left_handed",
            "shape_null",
        )

    def test_returns_json_payload(self):
        conn = _ok_conn(json.dumps({"ok": True, "helix": "H1", "pitch": 2.5}))
        text = _text(diagnose_helix_operation(conn, True, "Doc", "H1"))
        assert "H1" in text


# ---------------------------------------------------------------------------
# compare_documents + inspect_geometry activate wiring
# ---------------------------------------------------------------------------


class TestCompareDocuments:
    def test_compare_documents_pairs(self, monkeypatch):
        freecad = MagicMock()
        states = {
            "V7": {
                "ok": True,
                "doc": "V7",
                "objects": [
                    {
                        "name": "Body",
                        "bbox": {
                            "xmin": 0,
                            "ymin": 0,
                            "zmin": 0,
                            "xmax": 1,
                            "ymax": 1,
                            "zmax": 1,
                        },
                        "placement_base": {"x": 0, "y": 0, "z": 0},
                        "placement_rotation": None,
                        "face_count": 6,
                    }
                ],
            },
            "V8": {
                "ok": True,
                "doc": "V8",
                "objects": [
                    {
                        "name": "Body",
                        "bbox": {
                            "xmin": 0,
                            "ymin": 0,
                            "zmin": 0,
                            "xmax": 2,
                            "ymax": 1,
                            "zmax": 1,
                        },
                        "placement_base": {"x": 0, "y": 0, "z": 0},
                        "placement_rotation": None,
                        "face_count": 6,
                    }
                ],
            },
        }

        def fake_run_json_code(freecad, only_text, code, err, **kwargs):
            from freecad_mcp.responses import tool_ok

            doc = kwargs.get("document")
            return tool_ok(json.dumps(states[doc]))

        monkeypatch.setattr(
            "freecad_mcp.operations.interactive._run_json_code",
            fake_run_json_code,
        )
        resp = compare_documents_operation(
            freecad, True, "V7", "V8", object_pairs=[{"a": "Body", "b": "Body"}]
        )
        payload = json.loads(_text(resp))
        assert payload["ok"] is True
        assert payload["doc_a"] == "V7"
        assert payload["diff"]["diffs"][0]["changed"] is True


class TestInspectGeometryActivate:
    def test_activate_selects_subshape(self):
        conn = _ok_conn(
            json.dumps({"ok": True, "object": "Box", "subshape": "Face1"})
        )
        conn.activate_document.return_value = {"ok": True}
        conn.select_subshapes.return_value = {"ok": True}
        inspect_geometry_operation(
            conn, True, "Doc", "Box", subshape="Face1", activate=True
        )
        conn.activate_document.assert_called_once_with("Doc")
        conn.select_subshapes.assert_called_once_with(
            "Doc", ["Box:Face1"], clear=True
        )
        assert_code_compiles(_code(conn))


# ---------------------------------------------------------------------------
# gui_tools pure helpers (no FreeCAD import — selection parsing via mock)
# ---------------------------------------------------------------------------


class TestGuiToolsSelectionParsing:
    def test_select_subshapes_string_and_dict_forms(self, monkeypatch):
        """Exercise select_subshapes parsing with stub FreeCAD modules."""
        import types
        import sys

        selected = []

        class FakeSel:
            @staticmethod
            def clearSelection():
                selected.clear()

            @staticmethod
            def addSelection(*args):
                if len(args) == 1:
                    selected.append((args[0].Name, ""))
                else:
                    selected.append((args[1], args[2] if len(args) > 2 else ""))

            @staticmethod
            def getSelection():
                return []

            @staticmethod
            def getSelectionEx():
                return []

        class FakeObj:
            def __init__(self, name):
                self.Name = name

        class FakeDoc:
            Name = "Doc"

            def getObject(self, name):
                return FakeObj(name) if name in ("Box", "Body") else None

        fake_fc = types.SimpleNamespace(
            getDocument=lambda name: FakeDoc(),
            Placement=object,
            Vector=lambda *a: a,
            Rotation=object,
        )
        fake_gui = types.SimpleNamespace(Selection=FakeSel)

        monkeypatch.setitem(sys.modules, "FreeCAD", fake_fc)
        monkeypatch.setitem(sys.modules, "FreeCADGui", fake_gui)

        # Reload gui_tools against stubs
        import importlib

        # Import from addon path
        addon_rpc = (
            Path(__file__).resolve().parents[1] / "addon" / "FreeCADMCP" / "rpc_server"
        )
        sys.path.insert(0, str(addon_rpc.parent))
        # gui_tools imports .gui_dispatch — stub that too
        gui_dispatch = types.ModuleType("rpc_server.gui_dispatch")
        gui_dispatch._flush_gui_events = lambda delay_ms=20: None
        rpc_pkg = types.ModuleType("rpc_server")
        rpc_pkg.gui_dispatch = gui_dispatch
        monkeypatch.setitem(sys.modules, "rpc_server", rpc_pkg)
        monkeypatch.setitem(sys.modules, "rpc_server.gui_dispatch", gui_dispatch)

        # Load gui_tools as a free module with patched relatives
        path = addon_rpc / "gui_tools.py"
        spec = importlib.util.spec_from_file_location("gui_tools_under_test", path)
        mod = importlib.util.module_from_spec(spec)
        # Patch package-relative import by injecting before exec
        sys.modules["gui_tools_under_test"] = mod

        # Rewrite: exec with fake relative import support
        source = path.read_text(encoding="utf-8")
        source = source.replace(
            "from .gui_dispatch import _flush_gui_events",
            "def _flush_gui_events(delay_ms=20):\n    pass",
        )
        exec(compile(source, str(path), "exec"), mod.__dict__)

        result = mod.select_subshapes(
            "Doc",
            ["Box:Face1", {"object": "Body", "sub": "Edge2"}],
            clear=True,
        )
        assert result["ok"] is True
        assert result["count"] == 2
        assert {"object": "Box", "sub": "Face1"} in result["selected"]
        assert {"object": "Body", "sub": "Edge2"} in result["selected"]

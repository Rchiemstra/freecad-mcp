"""Shared pytest fixtures for the freecad-mcp test suite.

Three test layers are supported via markers (declared in pyproject.toml and
re-registered here defensively):

* ``unit``  - mock-based tests of generated code; no FreeCAD required.
* ``e2e``   - live tests driving a real headless FreeCAD (FreeCADCmd).
* ``core``  - live tests reproducing FreeCAD core C++ behavior
              (placement/attacher/sketcher/pad). These are the regression
              gates for the bugs listed in doc/mcp-feedback.md.

The live layers use the in-process ``exec`` pattern: the test interpreter is
expected to be FreeCAD's own Python (e.g. running pytest inside the
freecad-mcp-tests Docker image, or under FreeCADCmd). When FreeCAD is not
importable the live fixtures skip automatically.
"""
from __future__ import annotations

from tests.helpers import runtime_bootstrap  # noqa: F401  - install PySide/FreeCADGui stubs

import contextlib
import io
import json
import math
from unittest.mock import MagicMock

import pytest
from mcp.types import ImageContent, TextContent


# ---------------------------------------------------------------------------
# Marker registration (defensive; also declared in [tool.pytest.ini_options])
# ---------------------------------------------------------------------------

def pytest_configure(config: pytest.Config) -> None:
    for marker in ("unit", "e2e", "core"):
        config.addinivalue_line("markers", marker)


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Default any test with no layer marker to ``unit``.

    The bulk of the suite (``tests/test_*.py``) is mock-based and carries no
    explicit ``unit``/``e2e``/``core`` marker. Without this, ``pytest -m unit``
    -- what the CI unit-tests job runs -- deselects every one of them and the
    job goes green while exercising only the handful of explicitly-tagged unit
    tests. Auto-tagging the unmarked (mock-based, FreeCAD-free by convention)
    tests as ``unit`` makes the job actually run them, and keeps new test files
    covered without needing a marker on each. Tests already tagged unit/e2e/core
    are left untouched.
    """
    layers = {"unit", "e2e", "core"}
    for item in items:
        if not layers.intersection(m.name for m in item.iter_markers()):
            item.add_marker(pytest.mark.unit)


# ---------------------------------------------------------------------------
# Mock connection factories (Layer A/B unit tests)
# ---------------------------------------------------------------------------

def _ok_conn(output: str = "done", recompute_errors: list | None = None):
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {
        "success": True,
        "message": output,
        "recompute_errors": recompute_errors or [],
    }
    return conn


def _fail_conn(error: str = "oops"):
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {"success": False, "error": error}
    return conn


# ---------------------------------------------------------------------------
# Mock-layer response helpers
# ---------------------------------------------------------------------------

def _text(response) -> str:
    content = response.content if hasattr(response, "content") else response
    return " ".join(item.text for item in content if isinstance(item, TextContent))


def _has_image(response) -> bool:
    content = response.content if hasattr(response, "content") else response
    return any(isinstance(item, ImageContent) for item in content)


def _code(conn) -> str:
    """Return the code string passed to execute_code on the last call."""
    return conn.execute_code.call_args[0][0]


# ---------------------------------------------------------------------------
# Mock fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ok_conn():
    return _ok_conn()


@pytest.fixture
def fail_conn():
    return _fail_conn()


# ---------------------------------------------------------------------------
# Live FreeCAD layer (e2e / core)
# ---------------------------------------------------------------------------

# These imports are deferred so the module can be imported in a plain-Python
# environment (the unit layer must not require FreeCAD).
FreeCAD = None
_Part = None
_Sketcher = None

try:  # pragma: no cover - exercised only when FreeCAD is importable
    import FreeCAD as _FreeCAD  # type: ignore
    import Part as _PartMod  # type: ignore
    import Sketcher as _SketcherMod  # type: ignore

    FreeCAD = _FreeCAD
    _Part = _PartMod
    _Sketcher = _SketcherMod
except Exception:  # FreeCAD not available in this interpreter
    FreeCAD = None


class LiveFreeCADConnection:
    """In-process connection that ``exec``s generated MCP code against the
    real FreeCAD modules, mirroring the contract of
    ``freecad_mcp.freecad_client.FreeCADConnection.execute_code``.

    This is the same strategy used by
    ``tests/integration/test_assembly_path_live.py``'s ``DirectFreeCADConnection``,
    generalised here so every e2e/core repro test can share it.
    """

    def __init__(self, doc_name: str):
        if FreeCAD is None:  # pragma: no cover - guard
            raise RuntimeError("FreeCAD is not importable in this interpreter")
        # Mirror addon/FreeCADMCP/Init.py for direct in-process operation tests.
        from freecad_mcp.assembly_api_bootstrap import install

        install()
        self.doc = FreeCAD.newDocument(doc_name)
        self._globals = {
            "FreeCAD": FreeCAD,
            "Part": _Part,
            "Sketcher": _Sketcher,
            "doc": self.doc,
        }

    # -- FreeCADConnection-compatible API ----------------------------------

    def execute_code(self, code: str, options=None):
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer):
                exec(code, self._globals)  # noqa: S102 - intentional exec
            return {
                "success": True,
                "message": "Python code execution scheduled. \nOutput: " + buffer.getvalue(),
                "recompute_errors": [],
            }
        except Exception as err:  # surface the failure to the test
            return {"success": False, "error": f"{type(err).__name__}: {err}"}

    def invoke_rpc(self, method: str, *args, **kwargs):
        """Route typed lifecycle calls through the addon's real GUI helpers.

        The live fixture intentionally avoids XML-RPC transport overhead, but
        must still track the production ``FreeCADConnection`` interface as
        operations move away from generated Python.
        """
        if kwargs:
            raise TypeError(
                "LiveFreeCADConnection.invoke_rpc accepts positional RPC args"
            )
        import FreeCADGui

        if not hasattr(FreeCADGui, "addCommand"):
            FreeCADGui.addCommand = lambda *_args, **_kwargs: None
        from addon.FreeCADMCP.rpc_server.rpc_server import FreeCADRPC

        handlers = {
            "snapshot": FreeCADRPC._snapshot_gui,
            "restore": FreeCADRPC._restore_gui,
        }
        try:
            handler = handlers[method]
        except KeyError as exc:
            raise AttributeError(f"Unsupported live fixture RPC method: {method}") from exc
        result = handler(self, *args)
        if method == "restore" and isinstance(result, dict) and result.get("ok"):
            rebound = FreeCAD.getDocument(str(result.get("new_doc") or self.doc.Name))
            if rebound is not None:
                self.doc = rebound
                self._globals["doc"] = rebound
        return result

    def get_active_screenshot(self, *args, **kwargs):
        # Screenshots require the GUI; unavailable in FreeCADCmd headless.
        return None

    # -- helpers used by repro tests ---------------------------------------

    def recompute(self):
        return self.doc.recompute()

    def close(self):
        try:
            FreeCAD.closeDocument(self.doc.Name)
        except Exception:  # pragma: no cover - best-effort cleanup
            pass


def _freecad_available() -> bool:
    return FreeCAD is not None


@pytest.fixture
def freecad(request):
    """Yield the FreeCAD module, skipping the test if it is unavailable.

    Use this for low-level repro tests that build a model directly with the
    FreeCAD/Part/Sketcher APIs rather than through MCP operations.
    """
    if not _freecad_available():
        pytest.skip("FreeCAD not importable; run under FreeCADCmd or the Docker image")
    return FreeCAD


@pytest.fixture
def freecad_session(request):
    """Yield a :class:`LiveFreeCADConnection` bound to a fresh document.

    The document is closed on teardown. Skip the test if FreeCAD is not
    importable. Marks itself as ``e2e``/``core`` automatically so plain
    ``pytest`` runs do not attempt it without ``-m e2e``/``-m core``.
    """
    if not _freecad_available():
        pytest.skip("FreeCAD not importable; run under FreeCADCmd or the Docker image")
    doc_name = f"MCP_{request.node.name.replace('[', '_').replace(']', '')}"
    session = LiveFreeCADConnection(doc_name)
    yield session
    session.close()


# ---------------------------------------------------------------------------
# Vector / placement assertion helpers (used by core/e2e repro tests)
# ---------------------------------------------------------------------------

def vec_close(a, b, *, tol: float = 1e-4) -> bool:
    """True if two 3-vectors (FreeCAD.Vector or tuple) are within *tol* mm."""
    ax, ay, az = (a.x, a.y, a.z) if hasattr(a, "x") else a
    bx, by, bz = (b.x, b.y, b.z) if hasattr(b, "x") else b
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2) <= tol


def assert_vec_close(a, b, *, tol: float = 1e-4) -> None:
    ax, ay, az = (a.x, a.y, a.z) if hasattr(a, "x") else a
    bx, by, bz = (b.x, b.y, b.z) if hasattr(b, "x") else b
    err = math.sqrt((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2)
    assert err <= tol, f"Vector mismatch: {ax, ay, az} vs {bx, by, bz} (dist {err:.4e} > tol {tol:.2e})"


def assert_parallel(a, b, *, angle_tol: float = 1e-3) -> None:
    """Assert two unit-direction vectors are parallel (or anti-parallel)."""
    ax, ay, az = (a.x, a.y, a.z) if hasattr(a, "x") else a
    bx, by, bz = (b.x, b.y, b.z) if hasattr(b, "x") else b
    dot = (ax * bx + ay * by + az * bz)
    # |dot| ~ 1 means parallel; sin^2 = 1 - dot^2
    sin2 = max(0.0, 1.0 - dot * dot)
    assert sin2 <= angle_tol * angle_tol, (
        f"Directions not parallel: {ax, ay, az} vs {bx, by, bz} (|sin|={math.sqrt(sin2):.4e})"
    )


def parse_json_response(response) -> dict:
    """Parse the JSON payload out of an MCP tool response (TextContent)."""
    content = response.content if hasattr(response, "content") else response
    text = " ".join(item.text for item in content if isinstance(item, TextContent))
    if "Output:" in text:
        text = text.split("Output:", 1)[1].strip()
    return json.loads(text.splitlines()[-1])

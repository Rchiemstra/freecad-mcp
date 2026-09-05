"""Shared pytest fixtures for the freecad-mcp test suite.

Test layers via markers (declared in pyproject.toml and re-registered here
defensively):

* ``unit``         - mock-based tests of generated code; no FreeCAD required.
* ``e2e``          - live tests driving a real headless FreeCAD (FreeCADCmd).
* ``core``         - live tests reproducing FreeCAD core C++ behavior
                     (placement/attacher/sketcher/pad). These are the regression
                     gates for the bugs listed in doc/mcp-feedback.md.
* ``session_e2e``  - opt-in throwaway-profile session recovery / soak; not
                     selected by ``MARKER=e2e`` (avoids skip → verdict=1).

The live layers run inside FreeCAD's own Python (for example under
``FreeCADCmd``).  Document mutations use the add-on's production ``FreeCADRPC``
facade and native collaboration coordinator.  Read-only generated-code probes
remain in-process because this fixture deliberately does not emulate the
production worker subprocess.  When FreeCAD is not importable the live
fixtures skip automatically.
"""
from __future__ import annotations

import contextlib
import io
import json
import math
import os
import sys
from unittest.mock import MagicMock

import pytest
from mcp.types import ImageContent, TextContent

from tests.helpers import (
    runtime_bootstrap,  # noqa: F401  - install PySide/FreeCADGui stubs
)

_RPC_RUNTIME_COMPATIBILITY_NAMES = frozenset(
    {
        "gui_dispatcher",
        "rpc_acquisition_claim_store",
        "rpc_handoff_continuation_store",
        "rpc_inflight_request_registry",
        "rpc_request_replay_cache",
        "rpc_runtime_manifest",
        "rpc_server_actual_endpoint",
        "rpc_server_instance",
        "rpc_server_runtime_id",
        "rpc_server_started_at",
        "rpc_server_thread",
        "rpc_session_manager",
        "shutdown_requested",
        "worker_manager",
    }
)

_BRANCH_NATIVE_DOCUMENT_APIS = (
    "commitCompatibilityMutation",
    "getMutationReadiness",
    "getFileChangeState",
    "hasPendingFileChanges",
    "saveWithOutcome",
    "forceSave",
    "saveAsWithOutcome",
    "saveCopyWithOutcome",
    "collaborationIdentity",
    "captureSemanticRevisions",
    "beginEditSession",
    "snapshotForEdit",
    "prepareEditWithExpectedRevisions",
    "commitEdit",
    "cancelEdit",
    "editSessionStatus",
)

_LIVE_TYPED_RPC_METHODS = frozenset(
    {
        "body_create",
        "body_set_tip",
        "diagnose_parametric",
        "set_expression",
        "sketch_add_constraint",
        "sketch_add_geometry",
        "sketch_attach",
        "sketch_create",
        "sketch_edit_constraint",
        "spreadsheet_create",
        "spreadsheet_set_cells",
    }
)


def _missing_branch_native_document_apis(document) -> tuple[str, ...]:
    return tuple(
        name
        for name in _BRANCH_NATIVE_DOCUMENT_APIS
        if not callable(getattr(document, name, None))
    )


def _reject_missing_branch_native_document_apis(
    missing_apis: tuple[str, ...],
) -> None:
    message = (
        "This E2E fixture requires the branch-native App::Document mutation, "
        "collaboration, file-state, and save-outcome APIs; missing: "
        + ", ".join(missing_apis)
        + ". Stock FreeCAD compatibility images intentionally skip this "
        "production coverage."
    )
    if os.environ.get("FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION") == "1":
        pytest.fail(message)
    pytest.skip(message)


@pytest.fixture(autouse=True)
def _clear_legacy_rpc_runtime_test_overrides():
    """Prevent legacy module-alias monkeypatches from shadowing runtime views."""

    yield
    for module_name in (
        "addon.FreeCADMCP.rpc_server.rpc_server",
        "rpc_server.rpc_server",
    ):
        module = sys.modules.get(module_name)
        if module is None:
            continue
        namespace = vars(module)
        for name in _RPC_RUNTIME_COMPATIBILITY_NAMES:
            if name in namespace:
                delattr(module, name)


# ---------------------------------------------------------------------------
# Marker registration (defensive; also declared in [tool.pytest.ini_options])
# ---------------------------------------------------------------------------

def pytest_configure(config: pytest.Config) -> None:
    for marker in ("unit", "e2e", "core", "session_e2e", "benchmark", "integration"):
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
    covered without needing a marker on each. Tests already tagged with a layer
    marker are left untouched.

    ``integration`` must stay in this set too: it marks real-subprocess tests
    (e.g. against the sibling freecad_git CLI) that need a package the unit
    job never installs. Leaving it out of ``layers`` would let this same
    function silently ALSO tag those tests ``unit``, so ``pytest -m unit``
    would pick them up and fail in an environment that was never meant to run
    them.
    """
    layers = {"unit", "e2e", "core", "session_e2e", "benchmark", "integration"}
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


class _InlineGuiDispatcher:
    """Execute a production RPC GUI task in the current FreeCADCmd thread.

    The ordinary live fixture has no authenticated request/session context. If
    production code unexpectedly tries to use one, fail closed instead of
    pretending that this small dispatcher implements transport semantics.
    """

    def submit(
        self,
        callback,
        timeout,
        *,
        request_id=None,
        session_id=None,
        on_complete=None,
    ):
        del timeout
        if request_id is not None or session_id is not None or on_complete is not None:
            from addon.FreeCADMCP.dispatch.gui_errors import GuiDispatchError

            raise GuiDispatchError(
                "Live fixture cannot emulate authenticated or asynchronous GUI dispatch"
            )
        return callback()


def _build_live_freecad_rpc():
    """Compose an isolated production ``FreeCADRPC`` for in-process E2E use."""

    import threading
    import uuid

    import FreeCADGui

    if not hasattr(FreeCADGui, "addCommand"):
        FreeCADGui.addCommand = lambda *_args, **_kwargs: None

    from addon.FreeCADMCP.dispatch.inflight_request_registry import (
        InflightRequestRegistry,
    )
    from addon.FreeCADMCP.rpc_server import rpc_server as rpc_module
    from addon.FreeCADMCP.transport.replay import RequestReplayCache

    replay_cache = RequestReplayCache()
    inflight_requests = InflightRequestRegistry()
    runtime_id = str(uuid.uuid4())
    collaboration = rpc_module._build_collaboration_collaborators(
        runtime_manifest=None,
        inflight_request_registry=inflight_requests,
        request_replay_cache=replay_cache,
        runtime_id=runtime_id,
    )
    execution = rpc_module._build_execution_collaborators(
        compatibility_api=collaboration.compatibility_api,
        gui_dispatcher_value=_InlineGuiDispatcher(),
        worker_manager_value=None,
        shutdown_requested_value=threading.Event(),
        request_replay_cache=replay_cache,
        inflight_request_registry=inflight_requests,
        session_manager_value=None,
        runtime_manifest_value=None,
        actual_endpoint_value=None,
        runtime_id_value=runtime_id,
        server_started_at_value="",
    )
    return rpc_module.FreeCADRPC(
        allow_execute_code=True,
        collaboration_collaborators=collaboration,
        execution_collaborators=execution,
    )


class LiveFreeCADConnection:
    """Production-faithful in-process connection for FreeCADCmd E2E tests.

    Typed methods and mutating generated code traverse the real add-on RPC
    facade, local write admission, readiness gates, and native compatibility-
    mutation coordinator. The fixture intentionally bypasses only transport/
    authentication. Read-only
    generated code is executed directly; without a real ``WorkerManager`` the
    alternative would be a fake worker implementation or a fail-closed
    ``worker_unavailable`` response that invalidates existing geometry probes.
    """

    def __init__(self, doc_name: str):
        if FreeCAD is None:  # pragma: no cover - guard
            raise RuntimeError("FreeCAD is not importable in this interpreter")
        # Mirror addon/FreeCADMCP/Init.py for direct in-process operation tests.
        from freecad_mcp.assembly_api_bootstrap import install

        install(module_registry=sys.modules)
        self.doc = FreeCAD.newDocument(doc_name)
        self._typed_rpc = None
        self._globals = {
            "FreeCAD": FreeCAD,
            "Part": _Part,
            "Sketcher": _Sketcher,
            "doc": self.doc,
        }

    # -- FreeCADConnection-compatible API ----------------------------------

    def execute_code(self, code: str, options=None):
        if options is None:
            normalized_options = {}
        elif isinstance(options, dict):
            normalized_options = dict(options)
        else:
            to_dict = getattr(options, "to_dict", None)
            if not callable(to_dict):
                raise TypeError("execute_code options must be a mapping or ExecuteOptions")
            normalized_options = dict(to_dict())

        if not normalized_options.get("read_only", False):
            if not normalized_options.get("document"):
                normalized_options["document"] = self.doc.Name
            return self._dispatch("execute_code", code, normalized_options)

        # Deliberately retain a direct, in-process read harness. The production
        # RPC would correctly require a WorkerManager for this request; the live
        # fixture neither starts one nor pretends to provide worker isolation.
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

    @property
    def _rpc(self):
        if self._typed_rpc is None:
            self._typed_rpc = _build_live_freecad_rpc()
        return self._typed_rpc

    def _dispatch(self, method: str, *params):
        """Use the production local dispatcher without inventing RPC auth."""

        return self._rpc._dispatch(method, list(params))

    def __getattr__(self, name: str):
        """Expose the typed methods used by live operation-level tests.

        Production ``FreeCADConnection`` receives these methods from generated
        facade bindings.  This intentionally small test facade dispatches the
        same RPC method names while continuing to bypass transport only.
        """

        if name not in _LIVE_TYPED_RPC_METHODS:
            raise AttributeError(name)
        return lambda *params: self._dispatch(name, *params)

    def pad_feature(
        self,
        doc_name,
        sketch_name,
        pad_name,
        length,
        body_name=None,
        symmetric=False,
        reversed_dir=False,
        strict=False,
    ):
        return self._dispatch(
            "pad_feature",
            doc_name,
            sketch_name,
            pad_name,
            length,
            body_name,
            symmetric,
            reversed_dir,
            strict,
        )

    def pocket_feature(
        self,
        doc_name,
        sketch_name,
        pocket_name,
        length,
        body_name=None,
        symmetric=False,
        reversed_dir=False,
        strict=False,
    ):
        return self._dispatch(
            "pocket_feature",
            doc_name,
            sketch_name,
            pocket_name,
            length,
            body_name,
            symmetric,
            reversed_dir,
            strict,
        )

    def undo(self, doc_name):
        return self._dispatch("undo", doc_name)

    def redo(self, doc_name):
        return self._dispatch("redo", doc_name)

    def get_mutation_readiness(self, doc_name=None):
        return self._dispatch("get_mutation_readiness", doc_name)

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
        supported = {"snapshot", "restore", "close_document"}
        if method not in supported:
            raise AttributeError(f"Unsupported live fixture RPC method: {method}")
        result = self._dispatch(method, *args)
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
    return FreeCAD is not None and not bool(
        getattr(FreeCAD, "__mcp_test_stub__", False)
    )


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
    missing_apis = _missing_branch_native_document_apis(session.doc)
    if missing_apis:
        session.close()
        _reject_missing_branch_native_document_apis(missing_apis)
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

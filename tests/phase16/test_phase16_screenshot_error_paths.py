"""Phase 3e Lane I residuals: get_active_screenshot error-path contracts."""

from __future__ import annotations

import struct
import zlib
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.json_rpc_errors import json_rpc_error_from_result
from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.gui_interaction import (
    activate_document,
)
from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.view_capture import (
    get_active_screenshot,
)
from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.view_refresh import (
    refresh_view,
)
from addon.FreeCADMCP.rpc_server.methods.v2_methods_ops.invoke_v2_dispatch import (
    run_invoke_v2_dispatch,
)
from addon.FreeCADMCP.rpc_server.view_manager_ops.screenshot_blank import (
    is_near_blank_png,
)

from .test_phase16_personal_view import _Document, _facade

pytestmark = pytest.mark.unit


def _no_documents_facade(**kwargs):
    """Build a facade with zero open documents."""
    facade, saved, calls = _facade(**kwargs)
    facade._gui_collaborators.freecad.listDocuments = dict
    facade._gui_collaborators.freecad.ActiveDocument = None
    return facade, saved, calls


def _blank_png(width: int = 8, height: int = 8) -> bytes:
    rgb = (40, 44, 48)
    raw = bytearray()
    for _ in range(height):
        raw.append(0)
        raw.extend(bytes(rgb) * width)
    compressed = zlib.compress(bytes(raw), level=9)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr + b"\x00\x00\x00\x00"
        + struct.pack(">I", len(compressed)) + b"IDAT" + compressed + b"\x00\x00\x00\x00"
        + struct.pack(">I", 0) + b"IEND" + b"\x00\x00\x00\x00"
    )


def _invoke_v2_screenshot_result(facade) -> dict:
    token = SimpleNamespace(
        checkpoint=lambda *_args, **_kwargs: None,
        snapshot=lambda: SimpleNamespace(
            cancellation_requested=False,
            mutation_started=False,
            uncertain=False,
        ),
        finish_handler=lambda _status: None,
    )
    inflight = SimpleNamespace(token=token)
    handler_state = {"status": "running", "finalized": False}
    envelope = SimpleNamespace(request_id="request-1", method="get_active_screenshot")
    session = SimpleNamespace(session_id="session-1", mcp=SimpleNamespace(runtime_id="mcp-1"))
    collaborators = SimpleNamespace(
        inflight_request_registry=SimpleNamespace(
            finish_handler=lambda *_args, **_kwargs: None,
        ),
    )
    replay_cache = SimpleNamespace(complete=lambda *_args, **_kwargs: None)
    rpc = SimpleNamespace(
        _dispatch=lambda _method, _params: get_active_screenshot(facade),
        _complete_request_cancellation=lambda *_args, **_kwargs: {},
    )
    return run_invoke_v2_dispatch(
        collaborators=collaborators,
        self=rpc,
        session=session,
        envelope=envelope,
        params={},
        inflight=inflight,
        invocation_runtime_id="runtime-1",
        replay_cache=replay_cache,
        handler_state=handler_state,
    )


def test_p3e_r1_no_open_documents_returns_structured_error_not_none() -> None:
    facade, _, _ = _no_documents_facade()

    screenshot = get_active_screenshot(facade)
    refresh = refresh_view(facade)
    activate = activate_document(facade, "Model")

    assert screenshot is not None
    assert isinstance(screenshot, dict)
    assert screenshot["ok"] is False
    assert "no open documents are available" in screenshot["error"]
    assert refresh["ok"] is False
    assert "no open documents are available" in refresh["error"]
    assert activate["ok"] is False
    assert "no open documents are available" in activate["error"]

    error = json_rpc_error_from_result(screenshot)
    assert error is not None
    assert error["code"] == -32000
    assert "no open documents are available" in error["message"]


def test_p3e_r2_unknown_document_hint_returns_readable_error() -> None:
    model = _Document("Model")
    other = _Document("Other")
    facade, _, _ = _facade(documents=[model, other], active_document=model)

    result = get_active_screenshot(facade, document="Missing")

    assert isinstance(result, dict)
    assert result["ok"] is False
    assert "requested document is unavailable or ambiguous" in result["error"]
    error = json_rpc_error_from_result(result)
    assert error is not None
    assert error["code"] == -32000
    assert "requested document is unavailable or ambiguous" in error["message"]


def test_p3e_r3_invoke_v2_no_docs_does_not_become_outcome_uncertain() -> None:
    facade, _, _ = _no_documents_facade()

    response = _invoke_v2_screenshot_result(facade)

    assert response["ok"] is False
    assert response["result"]["ok"] is False
    assert "no open documents are available" in response["result"]["error"]
    assert response.get("error", {}).get("code") != "REQUEST_OUTCOME_UNCERTAIN"


def test_p3e_r4_blank_png_returns_structured_miss_not_none() -> None:
    blank = _blank_png()
    assert is_near_blank_png(blank)
    facade, _, _ = _facade(
        saved={("Model", "actor-a"): {
            "camera": (
                "OrthographicCamera { position 0 0 100 orientation 0 0 0 1 "
                "focalDistance 100 height 100 }"
            ),
            "projection": "Orthographic",
            "selection_paths": [],
            "preselection_path": None,
            "expanded_tree_paths": [],
            "tree_horizontal_scroll": 0,
            "tree_vertical_scroll": 0,
            "active_document": "Model",
            "active_view": "view-1",
            "active_workbench": "Part",
            "edit_focus": "",
            "temporary_overlays": [],
        }},
        render=lambda *_args: blank,
    )

    result = get_active_screenshot(facade)

    assert result is not None
    assert isinstance(result, dict)
    assert result["ok"] is False
    assert result.get("screenshot_miss_reason") == "near_blank_png"
    assert "near-blank" in result["error"].lower()

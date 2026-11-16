"""Native saves retain a bounded budget long enough for larger FCStd documents."""

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods import native_lifecycle_methods as lifecycle

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("method", "resolver", "kwargs"),
    [
        ("save_document", "_resolve_and_save_gui", {}),
        (
            "save_document_as",
            "_resolve_and_save_as_gui",
            {"destination": "/work/Other.FCStd"},
        ),
        (
            "save_document_copy",
            "_resolve_and_save_copy_gui",
            {"destination": "/work/Copy.FCStd"},
        ),
        ("finalize_document_edit", "_resolve_and_save_gui", {}),
        (
            "finalize_document_edit",
            "_resolve_and_save_as_gui",
            {"save_mode": "save_as", "destination": "/work/Final.FCStd"},
        ),
        (
            "finalize_document_edit",
            "_resolve_and_save_as_gui",
            {"save_mode": "first_save", "destination": "/work/First.FCStd"},
        ),
    ],
)
def test_save_variants_allow_native_save_longer_than_general_gui_budget(
    monkeypatch, method, resolver, kwargs
):
    result = {
        "success": True,
        "saved": True,
        "resulting_clean": True,
        "durability_verified": True,
    }
    monkeypatch.setattr(lifecycle, resolver, lambda *_args: dict(result))
    budgets = []

    def dispatch(callback, timeout=30.0):
        budgets.append(timeout)
        # A measured larger model save takes 49 seconds, exceeding the general
        # dispatcher default but fitting safely inside the 150-second transport.
        if timeout < 49.0:
            return {
                "success": False,
                "error_code": "GUI_TIMEOUT_DURING_EXECUTION",
                "completion_uncertain": True,
            }
        return callback()

    facade = SimpleNamespace(_dispatch_gui=dispatch)
    actual = getattr(lifecycle, method)(facade, {"document_name": "Model"}, **kwargs)
    assert actual["success"] is True
    assert actual["saved"] is True
    assert budgets == [120.0]
    assert 49.0 < budgets[0] < 150.0
    if method == "finalize_document_edit":
        assert actual["finalized"] is True


@pytest.mark.parametrize(
    ("method", "kwargs"),
    [
        ("save_document", {}),
        ("save_document_as", {"destination": "/work/Other.FCStd"}),
        ("save_document_copy", {"destination": "/work/Copy.FCStd"}),
        ("finalize_document_edit", {}),
    ],
)
def test_save_budget_preserves_timeout_uncertainty_and_request_identity(method, kwargs):
    failure = {
        "success": False,
        "error_code": "GUI_TIMEOUT_DURING_EXECUTION",
        "completion_uncertain": True,
        "request_id": "timed-out-save",
        "execution_started": True,
    }
    facade = SimpleNamespace(_dispatch_gui=lambda _callback, **_kwargs: failure)
    actual = getattr(lifecycle, method)(facade, {"document_name": "Model"}, **kwargs)
    assert actual["success"] is False
    for key, value in failure.items():
        assert actual[key] == value
    if method == "finalize_document_edit":
        assert actual["finalized"] is False

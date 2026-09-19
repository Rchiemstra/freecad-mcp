"""D-15 follow-up: the modal-dialog diagnosis must reach the caller.

The dispatcher named the blocking dialog, but under a new error code that no other layer
knew. Natively, ``get_object`` behind an open dialog reported
``INVALID_GET_OBJECT_RESPONSE`` / "document state requires reconciliation" and buried the
dialog title in ``diagnostics``. A blocked-dialog timeout is a pre-execution GUI timeout
with a better message, so every layer that recognises ``GUI_TIMEOUT_BEFORE_EXECUTION``
must recognise it too.
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest

from addon.FreeCADMCP.dispatch import gui_block_state, gui_submit
from addon.FreeCADMCP.dispatch.gui_errors import GuiDispatchTimeout
from addon.FreeCADMCP.dispatch.gui_request import GuiRequest

pytestmark = pytest.mark.unit

_TITLE = "D15 harmless modal"
_PROTOCOL_PACKAGES = ("addon.FreeCADMCP._shared.protocol", "freecad_mcp._shared.protocol")


class _Dialog:
    def windowTitle(self) -> str:
        return _TITLE


def _timeout_payload(*, blocked: bool) -> dict[str, object]:
    """The dispatcher payload as it arrived natively (keys taken from the live response)."""

    gui_block_state.clear_gui_block()
    if blocked:
        gui_block_state.note_blocking_widget("modal dialog", _Dialog())
    try:
        with pytest.raises(GuiDispatchTimeout) as caught:
            gui_submit.raise_submit_timeout_error(
                GuiRequest(callable=lambda: None), 30.0, before_execution=True
            )
    finally:
        gui_block_state.clear_gui_block()
    return {
        **caught.value.to_public_dict(),
        "success": False,
        "error": str(caught.value),
        "recovery_incident_id": None,
    }


def _contract_readers() -> list[tuple[str, object]]:
    readers = []
    for package_name in _PROTOCOL_PACKAGES:
        package = importlib.import_module(package_name)
        for info in pkgutil.iter_modules(package.__path__):
            if not info.name.endswith("_contract"):
                continue
            module = importlib.import_module(f"{package_name}.{info.name}")
            tool = info.name.removesuffix("_contract")
            parser = getattr(module, f"parse_{tool}_response", None)
            if callable(parser):
                readers.append((f"{package_name}.{tool}", parser))
    return readers


_READERS = _contract_readers()


def test_every_generated_contract_parser_was_found() -> None:
    assert len(_READERS) >= 250


@pytest.mark.parametrize(("tool", "parse"), _READERS, ids=[tool for tool, _ in _READERS])
def test_contract_treats_a_blocked_dialog_like_any_pre_execution_timeout(tool: str, parse) -> None:
    generic = _timeout_payload(blocked=False)
    blocked = _timeout_payload(blocked=True)
    assert blocked["error_code"] != generic["error_code"]

    generic_result = parse(generic)
    blocked_result = parse(blocked)

    if generic_result["error_code"] == generic["error_code"]:
        assert blocked_result["error_code"] == blocked["error_code"]
        assert _TITLE in blocked_result["error"]
    assert blocked_result["outcome"] == generic_result["outcome"]


def test_client_recognises_a_blocked_dialog_as_a_pre_execution_gui_timeout() -> None:
    from freecad_mcp._shared.protocol.json_rpc_client import JsonRpcRemoteError
    from freecad_mcp.responses.gui_dispatch_outcome import (
        gui_dispatch_timeout_envelope_from_exception,
        is_gui_dispatch_timeout_envelope,
        is_gui_dispatch_timeout_exception,
    )

    blocked = _timeout_payload(blocked=True)
    exc = JsonRpcRemoteError(-32000, str(blocked["error"]), data=blocked)

    assert is_gui_dispatch_timeout_envelope(blocked)
    assert is_gui_dispatch_timeout_exception(exc)
    envelope = gui_dispatch_timeout_envelope_from_exception(exc)
    assert envelope is not None
    assert envelope["error_code"] == blocked["error_code"]
    assert envelope["timeout_stage"] == "before_execution"
    assert _TITLE in envelope["error"]


def test_blocked_dialog_code_is_a_known_error_code() -> None:
    from freecad_mcp.outcomes import COMMON_ERROR_CODES

    assert _timeout_payload(blocked=True)["error_code"] in COMMON_ERROR_CODES

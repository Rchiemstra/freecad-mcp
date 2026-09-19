"""D-15: a GUI timeout caused by an open modal dialog must name the dialog.

After an unclean shutdown FreeCAD opened a "Document Recovery" modal dialog. The dispatcher
correctly deferred every MCP request while it was open, but the caller only saw
"Timed out after 30.0s waiting for FreeCAD GUI response before execution" and had no way to
learn that a human has to close a dialog.
"""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.dispatch import gui_block_state, gui_submit
from addon.FreeCADMCP.dispatch.gui_core import GuiDispatchCore
from addon.FreeCADMCP.dispatch.gui_errors import GuiDispatchTimeout
from addon.FreeCADMCP.dispatch.gui_request import GuiRequest

pytestmark = pytest.mark.unit


class _Dialog:
    def __init__(self, title: str) -> None:
        self._title = title

    def windowTitle(self) -> str:
        return self._title


@pytest.fixture(autouse=True)
def _clean_state():
    gui_block_state.clear_gui_block()
    yield
    gui_block_state.clear_gui_block()


def test_blocking_widget_is_described_with_its_title():
    gui_block_state.note_blocking_widget("modal dialog", _Dialog("Document Recovery"))
    detail = gui_block_state.describe_gui_block()
    assert detail is not None
    assert "modal dialog" in detail
    assert "Document Recovery" in detail


def test_cleared_state_has_no_description():
    gui_block_state.note_blocking_widget("modal dialog", _Dialog("Document Recovery"))
    gui_block_state.clear_gui_block()
    assert gui_block_state.describe_gui_block() is None


def test_submit_timeout_names_the_blocking_dialog():
    gui_block_state.note_blocking_widget("modal dialog", _Dialog("Document Recovery"))
    with pytest.raises(GuiDispatchTimeout) as caught:
        gui_submit.raise_submit_timeout_error(GuiRequest(callable=lambda: None), 30.0, before_execution=True)
    assert "Document Recovery" in str(caught.value)
    assert caught.value.error_code == "GUI_BLOCKED_BY_MODAL_DIALOG"
    assert caught.value.execution_started is False


def test_core_timeout_names_the_blocking_dialog():
    gui_block_state.note_blocking_widget("modal dialog", _Dialog("Document Recovery"))
    core = GuiDispatchCore.__new__(GuiDispatchCore)
    core._emit_terminal = lambda *args, **kwargs: None
    core._release_outstanding = lambda request: None
    with pytest.raises(GuiDispatchTimeout) as caught:
        core._raise_timeout(GuiRequest(callable=lambda: None), 30.0, before_execution=True)
    assert "Document Recovery" in str(caught.value)
    assert caught.value.error_code == "GUI_BLOCKED_BY_MODAL_DIALOG"


def test_unblocked_timeout_keeps_generic_code():
    with pytest.raises(GuiDispatchTimeout) as caught:
        gui_submit.raise_submit_timeout_error(GuiRequest(callable=lambda: None), 30.0, before_execution=True)
    assert caught.value.error_code == "GUI_TIMEOUT_BEFORE_EXECUTION"


def test_running_timeout_is_not_blamed_on_a_dialog():
    gui_block_state.note_blocking_widget("modal dialog", _Dialog("Document Recovery"))
    with pytest.raises(GuiDispatchTimeout) as caught:
        gui_submit.raise_submit_timeout_error(GuiRequest(callable=lambda: None), 30.0, before_execution=False)
    assert caught.value.error_code == "GUI_TIMEOUT_DURING_EXECUTION"

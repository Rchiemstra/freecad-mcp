"""Regression tests for the unattended modal-command refusal.

execute_code always runs on the GUI thread with no human attached, so any
modal dialog it opens is never dismissed: the thread blocks until the RPC
times out and the dialog is left owning the event loop.
"""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.rpc_server.execution_safety import find_modal_command_risk
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_policy import (
    modal_command_block_response,
)


@pytest.mark.parametrize(
    "code, trigger",
    [
        ('Gui.runCommand("Std_Save")', "Std_Save"),
        ('FreeCADGui.runCommand("Std_SaveAs")', "Std_SaveAs"),
        ('Gui.runCommand("Std_SaveCopy", 0)', "Std_SaveCopy"),
        ('Gui.SendMsgToActiveView("Std_Revert")', "Std_Revert"),
        ('Gui.runCommand("Std_DlgPreferences")', "Std_DlgPreferences"),
        ('Gui.runCommand("Std_Import")', "Std_Import"),
    ],
)
def test_refuses_modal_std_commands(code, trigger):
    risk = find_modal_command_risk(code)
    assert risk is not None
    assert risk.kind == "modal_gui_command"
    assert risk.trigger == trigger


def test_refuses_a_qt_modal_event_loop():
    risk = find_modal_command_risk("dialog = QtWidgets.QMessageBox()\ndialog.exec()")
    assert risk is not None
    assert risk.kind == "modal_event_loop"
    assert risk.trigger == ".exec()"


def test_python_builtin_exec_is_not_a_modal_dialog():
    # exec(...) is an ast.Name, not an ast.Attribute -- it must not be matched.
    assert find_modal_command_risk('exec("value = 1")') is None


def test_allows_non_modal_gui_commands_and_ordinary_modelling():
    assert find_modal_command_risk('Gui.runCommand("Std_ViewFitAll")') is None
    assert find_modal_command_risk('Gui.SendMsgToActiveView("ViewFit")') is None
    assert find_modal_command_risk("doc.recompute()\ndoc.save()") is None


def test_a_non_literal_command_name_is_not_guessed():
    # The guard reports only what it can prove from a string literal.
    assert find_modal_command_risk("Gui.runCommand(command_name)") is None


def test_syntax_error_defers_to_the_normal_structured_error():
    assert find_modal_command_risk("def broken(") is None


def test_block_response_names_the_trigger_and_the_typed_tool():
    response = modal_command_block_response(
        lambda payload: payload,
        code='Gui.runCommand("Std_Save")',
        find_modal_command_risk_fn=find_modal_command_risk,
    )
    assert response is not None
    assert response["success"] is False
    assert response["is_error"] is True
    assert response["retryable"] is False
    assert response["error_code"] == "MODAL_GUI_COMMAND_REFUSED"
    assert response["blocked"] == "modal_gui_command"
    assert "Std_Save" in response["error"]
    assert "save_document" in response["error"]


def test_block_response_passes_clean_code_through():
    assert (
        modal_command_block_response(
            lambda payload: payload,
            code="doc.recompute()",
            find_modal_command_risk_fn=find_modal_command_risk,
        )
        is None
    )


def test_save_copy_refusal_names_the_copy_tool_not_the_overwriting_ones():
    """Std_SaveCopy has no counterpart in the save/save-as pair.

    A copy writes a second file and deliberately leaves the open document
    modified. Pointing a blocked Std_SaveCopy at save_document/save_document_as
    sends the caller to tools that overwrite the document being edited.
    """
    blocked = modal_command_block_response(
        lambda payload: payload,
        code="import FreeCADGui\nFreeCADGui.runCommand('Std_SaveCopy')\n",
        find_modal_command_risk_fn=find_modal_command_risk,
    )
    assert blocked is not None
    assert blocked["error_code"] == "MODAL_GUI_COMMAND_REFUSED"
    assert "save_document_copy" in blocked["error"]
    assert "save_document /" not in blocked["error"]


def test_plain_save_refusal_still_offers_the_copy_tool_as_an_alternative():
    blocked = modal_command_block_response(
        lambda payload: payload,
        code="import FreeCADGui\nFreeCADGui.runCommand('Std_Save')\n",
        find_modal_command_risk_fn=find_modal_command_risk,
    )
    assert blocked is not None
    assert "save_document / save_document_as" in blocked["error"]
    assert "save_document_copy" in blocked["error"]


def test_non_save_modal_refusal_keeps_the_generic_remedy():
    blocked = modal_command_block_response(
        lambda payload: payload,
        code="import FreeCADGui\nFreeCADGui.runCommand('Std_Import')\n",
        find_modal_command_risk_fn=find_modal_command_risk,
    )
    assert blocked is not None
    assert "typed tool instead of a dialog" in blocked["error"]
    assert "save_document" not in blocked["error"]

"""Print-only live execution must preserve the real undo head."""
import pytest
from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_orphan_pad import _healthy_pad
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


def _pad(mcp, doc):
    assert_ok(mcp.call('create_document', name=doc))
    assert_ok(mcp.call('body_create', doc_name=doc, body_name='Body'))
    _healthy_pad(mcp, doc)


def _names(mcp, doc):
    result = _payload(assert_ok(mcp.call('get_objects', doc_name=doc, fields=['Name'], page_size=30)))
    return str(result)


def test_mutating_execute_code_is_undoable(mcp, gui_log):
    doc = 'R15UndoMutation'
    _pad(mcp, doc)
    assert_ok(mcp.call('execute_code', document=doc, recompute='target', execution_mode='gui',
                       code="import FreeCAD\nFreeCAD.getDocument(%r).addObject('Part::Box','Extra')" % doc))
    assert 'Extra' in _names(mcp, doc)
    assert_ok(mcp.call('undo', doc_name=doc))
    assert 'Extra' not in _names(mcp, doc)
    assert 'OwnedPad' in _names(mcp, doc)
    assert_ok(mcp.call('close_document', doc_name=doc))
    assert_clean(gui_log)


def test_print_only_execute_code_preserves_undo_head(mcp, gui_log):
    doc = 'R15UndoPrint'
    _pad(mcp, doc)
    assert_ok(mcp.call('execute_code', document=doc, recompute='none', execution_mode='gui',
                       code="import FreeCAD\nprint(FreeCAD.getDocument(%r).UndoCount)" % doc))
    assert_ok(mcp.call('undo', doc_name=doc))
    assert 'OwnedPad' not in _names(mcp, doc)
    assert_ok(mcp.call('close_document', doc_name=doc))
    assert_clean(gui_log)

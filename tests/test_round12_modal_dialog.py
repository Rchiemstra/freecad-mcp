from types import SimpleNamespace as NS
import pytest
from addon.FreeCADMCP.rpc_server.gui_dispatcher_qt import GuiDispatcher

pytestmark = pytest.mark.unit


def dispatcher(title):
    # The sample is produced on the Qt owner thread, then read by RPC threads.
    return NS(_modal_title=title, _sample_modal_dialog=lambda: None, _core=NS(submit=lambda fn, *a, **kw: fn()))


def test_unblocked_dispatch_executes():
    assert GuiDispatcher.submit(dispatcher(None), lambda: 'done', 1) == 'done'


def test_modal_dispatch_rejects_without_running_body():
    executed = []
    result = GuiDispatcher.submit(dispatcher('Document Recovery'), lambda: executed.append(1), 1)
    assert result['error_code'] == 'GUI_BLOCKED_BY_MODAL_DIALOG'
    assert result['error'] == 'GUI blocked by modal dialog: Document Recovery'
    assert result['retry_safe'] is True
    assert executed == []


def test_widget_is_sampled_only_on_owner_and_rpc_reads_cached_title(monkeypatch):
    import threading
    from addon.FreeCADMCP.rpc_server import gui_dispatcher_qt as module
    owner = threading.get_ident()
    class Application:
        @classmethod
        def instance(cls):
            assert threading.get_ident() == owner
            return cls()
        def activeModalWidget(self):
            assert threading.get_ident() == owner
            return NS(windowTitle=lambda:'Recovery')
    monkeypatch.setattr(module.QtWidgets, 'QApplication', Application)
    state = dispatcher(None)
    state._owner_thread_ident = owner
    GuiDispatcher._sample_modal_dialog(state)
    results = []
    thread = threading.Thread(target=lambda: results.append(GuiDispatcher.submit(state, lambda:1, 1)))
    thread.start(); thread.join(timeout=2)
    assert results[0]['error_code'] == 'GUI_BLOCKED_BY_MODAL_DIALOG'


def test_closed_modal_widget_does_not_block(monkeypatch):
    import threading
    from addon.FreeCADMCP.rpc_server import gui_dispatcher_qt as module
    class Application:
        @classmethod
        def instance(cls):
            return cls()
        def activeModalWidget(self):
            return NS(isVisible=lambda:False, windowTitle=lambda:'Closed')
    monkeypatch.setattr(module.QtWidgets, 'QApplication', Application)
    state = dispatcher('Closed')
    state._owner_thread_ident = threading.get_ident()
    GuiDispatcher._sample_modal_dialog(state)
    assert state._modal_title is None
    assert GuiDispatcher.submit(state, lambda:42, 1) == 42

from types import SimpleNamespace as NS
from unittest.mock import MagicMock
import pytest
from addon.FreeCADMCP.dispatch.gui_errors import GuiDispatchTimeout
from addon.FreeCADMCP.dispatch.gui_outcome import GuiOutcome
from addon.FreeCADMCP.dispatch.inflight_request_registry import InflightRequestRegistry
from addon.FreeCADMCP.rpc_server.gui_dispatcher_qt import GuiDispatcher
from addon.FreeCADMCP.rpc_server.methods.dispatch_helpers_ops.dispatch_gui import dispatch_gui

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


def _tracked_dispatch(title=None, *, timeout_started=None):
    registry = InflightRequestRegistry()
    request = registry.register('modal-session', 'modal-request', 'get_report_view')
    state = dispatcher(title)
    pending = {}

    def submit(callback, timeout, **options):
        pending['complete'] = options['on_complete']
        if timeout_started is not None:
            state._modal_title = 'Document Recovery'
            if timeout_started:
                request.token.mark_mutation_started()
            raise GuiDispatchTimeout(
                'GUI response timed out', request_id=request.request_id,
                timeout_stage='during_execution' if timeout_started else 'before_execution',
                execution_started=timeout_started, mutation_started=timeout_started,
                completion_uncertain=timeout_started,
            )
        result = callback()
        options['on_complete'](request.request_id, GuiOutcome(ok=True, value=result))
        return result

    state._core.submit = submit
    state.submit = lambda *args, **kwargs: GuiDispatcher.submit(state, *args, **kwargs)
    collaborators = NS(
        gui_dispatcher=state, inflight_request_registry=registry,
        request_replay_cache=None, runtime_id='addon-runtime', logger=MagicMock(),
        request_identity_provider=lambda: NS(get_request_identity=lambda: {}),
    )
    facade = NS(
        _execution_collaborators=collaborators, _mutation_context=NS(value=None),
        _current_inflight=lambda: request, TIMEOUT=1,
    )
    return facade, registry, request, pending


def test_unblocked_dispatch_completes_inflight_gui_phase():
    facade, registry, request, _pending = _tracked_dispatch()
    assert dispatch_gui(facade, lambda: 'done') == 'done'
    snapshot = registry.finish_handler(request.session_id, request.request_id, status='completed')
    assert snapshot.active_gui_phases == 0
    assert snapshot.terminal is True


def test_cached_modal_rejection_completes_inflight_gui_phase():
    facade, registry, request, _pending = _tracked_dispatch('Document Recovery')
    executed = []
    result = dispatch_gui(facade, lambda: executed.append(1))
    assert result['error_code'] == 'GUI_BLOCKED_BY_MODAL_DIALOG'
    assert result['retry_safe'] is True
    assert executed == []
    snapshot = registry.finish_handler(request.session_id, request.request_id, status='rejected')
    assert snapshot.active_gui_phases == 0
    assert snapshot.terminal is True
    assert registry.request_cancel(request.session_id, request.request_id).status == 'completed'


def test_modal_timeout_before_execution_completes_inflight_gui_phase():
    facade, registry, request, _pending = _tracked_dispatch(timeout_started=False)
    result = dispatch_gui(facade, lambda: pytest.fail('body must not run'))
    assert result['error_code'] == 'GUI_BLOCKED_BY_MODAL_DIALOG'
    assert result['execution_started'] is False
    snapshot = registry.finish_handler(request.session_id, request.request_id, status='rejected')
    assert snapshot.active_gui_phases == 0
    assert snapshot.terminal is True


def test_modal_timeout_after_execution_tracks_recovery_until_late_completion():
    facade, registry, request, pending = _tracked_dispatch(timeout_started=True)
    result = dispatch_gui(facade, lambda: pytest.fail('body is already pending'))
    assert result['error_code'] == 'GUI_BLOCKED_BY_MODAL_DIALOG'
    assert result['completion_uncertain'] is True
    snapshot = registry.finish_handler(request.session_id, request.request_id, status='uncertain')
    assert snapshot.active_gui_phases == 1
    assert snapshot.terminal is False
    assert snapshot.uncertain is True
    assert snapshot.recovery_incident_id
    assert result['recovery_incident_id'] == snapshot.recovery_incident_id

    pending['complete'](request.request_id, GuiOutcome(ok=True, value='done', late=True))
    final = registry.status(request.session_id, request.request_id)
    assert final.active_gui_phases == 0
    assert final.terminal is True
    assert final.uncertain is False

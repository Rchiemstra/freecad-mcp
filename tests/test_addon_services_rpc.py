"""Native add-on invocation contract: real registry/CollaborationAPI, no GUI or solver."""
from types import SimpleNamespace
from unittest.mock import Mock
import threading

import pytest

from addon.FreeCADMCP.rpc_server.methods import addon_services as rpc
from tests.helpers.addon_services import NativeDocument, host, registry_with

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("access", ["query", "mutation"])
def test_native_authority_refusal_never_runs_even_a_query_callback(access):
    callback = Mock()
    service, lookup, validate = host(NativeDocument(allowed=False), registry_with(callback, access=access))
    result = service.invoke_addon_operation("Target", "Example", "run", {"value": 1})
    assert result["success"] is False and result["committed"] is False
    assert result["native_status"] == "Conflict"
    lookup.assert_called_once_with("Target")
    callback.assert_not_called()
    validate.assert_not_called()


def test_resolves_explicit_target_and_runs_callback_on_native_owner():
    document = NativeDocument()
    seen = []
    caller = threading.get_ident()
    def callback(context, args):
        seen.append((context.document, context.access, threading.get_ident()))
        context.document.value = args["value"]
        return {"job": "opaque-1", "document": context.document.Name}
    service, lookup, validate = host(document, registry_with(callback, access="query"))
    result = service.invoke_addon_operation("Target", "Example", "run", {"value": 3})
    assert result["success"] is True and result["committed"] is True
    assert result["result"] == {"job": "opaque-1", "document": "Target"}
    assert document.value == 3
    assert seen == [(document, "mutation", document.owner)]
    assert document.owner != caller
    lookup.assert_called_once_with("Target")
    validate.assert_called_once_with(document)


@pytest.mark.parametrize("addon,operation,args,code", [
    ("Missing", "run", {"value": 1}, "ADDON_NOT_FOUND"),
    ("Example", "__import__", {"value": 1}, "OPERATION_NOT_FOUND"),
    ("Example", "run", {}, "INVALID_ARGUMENT"),
    ("Example", "run", {"value": True}, "INVALID_ARGUMENT"),
    ("Example", "run", {"value": 100}, "INVALID_ARGUMENT"),
    ("Example", "run", {"value": 1, "module": "os"}, "INVALID_ARGUMENT"),
    ("Example", "run", [], "INVALID_ARGUMENT"),
])
def test_invalid_requests_never_callback(addon, operation, args, code):
    callback = Mock()
    service, _, _ = host(NativeDocument(), registry_with(callback))
    result = service.invoke_addon_operation("Target", addon, operation, args)
    assert result["error_code"] == code
    assert result["committed"] is False
    callback.assert_not_called()


def test_missing_document_never_callbacks():
    callback = Mock()
    service, lookup, _ = host(NativeDocument(), registry_with(callback))
    result = service.invoke_addon_operation("Other", "Example", "run", {"value": 1})
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"
    lookup.assert_called_once_with("Other")
    callback.assert_not_called()


@pytest.mark.parametrize("result", [object(), {"bad": float("nan")}, {1: "bad"}, "x" * (2 * 1024 * 1024)])
def test_non_json_or_oversized_result_rolls_back_document(result):
    document = NativeDocument()
    def callback(context, _args):
        context.document.value = 4
        return result
    service, _, _ = host(document, registry_with(callback))
    actual = service.invoke_addon_operation("Target", "Example", "run", {"value": 1})
    assert actual["success"] is False and actual["committed"] is False
    assert actual["error_code"] in {"INVALID_JSON", "PAYLOAD_TOO_LARGE"}
    assert actual["rollback_succeeded"] is True
    assert actual["retry_safe"] is False  # External plugin effects are not covered by document rollback.
    assert document.rolled_back and document.value == 0


def test_callback_exception_rolls_back_with_public_error():
    document = NativeDocument()
    def callback(context, _args):
        context.document.value = 2
        raise RuntimeError("provider failed")
    service, _, _ = host(document, registry_with(callback))
    actual = service.invoke_addon_operation("Target", "Example", "run", {"value": 1})
    assert actual["error_code"] == "ADDON_OPERATION_FAILED"
    assert actual["error"] == "provider failed"
    assert actual["rollback_succeeded"] and document.value == 0


def test_failed_document_invariant_rolls_back():
    document = NativeDocument()
    def callback(context, _args):
        context.document.value = 2
    service, _, validate = host(document, registry_with(callback))
    validate.side_effect = RuntimeError("unhealthy document")
    actual = service.invoke_addon_operation("Target", "Example", "run", {"value": 1})
    assert actual["error_code"] == "DOCUMENT_HEALTH_DEGRADED"
    assert actual["rollback_succeeded"] and document.value == 0


@pytest.mark.parametrize("terminal", [None, True, {}, {"success": True},
    {"status": "Committed"}, {"status": "Queued", "committed": False},
    {"status": "RollbackFailed", "committed": False},
    {"status": "Committed", "committed": True, "rollback_succeeded": False},
    {"status": "Committed", "committed": True, "rollback_failed": "false"}])
def test_provisional_callback_result_never_proves_commit(terminal):
    service, _, _ = host(NativeDocument(status=terminal if terminal is not None else {}), registry_with(lambda *_: {"success": True}))
    result = service.invoke_addon_operation("Target", "Example", "run", {"value": 1})
    assert result["success"] is False and result["outcome"] == "uncertain"
    assert result["retry_safe"] is False


def test_async_native_commit_is_only_interpreted_after_terminal_wait():
    document = NativeDocument()
    callback = Mock(return_value={"handle": "opaque"})
    registry = registry_with(callback)
    class Pending:
        def await_result(self, timeout):
            apply(document)
            assert postcondition(document)
            return {"status": "Committed", "committed": True}
    def commit(_name, apply_arg, postcondition_arg, **_kwargs):
        nonlocal apply, postcondition
        apply, postcondition = apply_arg, postcondition_arg
        return Pending()
    apply = postcondition = None
    result = rpc.run_addon_operation(SimpleNamespace(commit_native_mutation=commit), registry, lambda _: None,
                                     "Target", "Example", "run", {"value": 1})
    callback.assert_not_called()
    assert not isinstance(result, dict)
    assert result.await_result()["committed"] is True
    callback.assert_called_once()


def test_async_timeout_is_uncertain_without_claiming_rollback():
    class Pending:
        def await_result(self, timeout):
            raise TimeoutError("native commit still running")
    result = rpc.run_addon_operation(SimpleNamespace(commit_native_mutation=lambda *a, **k: Pending()),
        registry_with(Mock()), lambda _: None, "Target", "Example", "run", {"value": 1})
    actual = result.await_result()
    assert actual["committed"] is None and actual["outcome"] == "uncertain"
    assert "rollback_succeeded" not in actual




def test_committed_status_without_callbacks_is_uncertain():
    callback = Mock()
    result = rpc.run_addon_operation(SimpleNamespace(commit_native_mutation=lambda *a, **k: {
        "status": "Committed", "committed": True}), registry_with(callback), lambda _: None,
        "Target", "Example", "run", {"value": 1})
    assert result["outcome"] == "uncertain"
    callback.assert_not_called()


def test_wrong_document_is_rejected_before_provider():
    callback = Mock()
    def commit(name, apply, postcondition, **_kwargs):
        try:
            apply(NativeDocument("Other"))
        except Exception:
            return {"status": "ApplyFailed", "committed": False, "rollback_succeeded": True}
        raise AssertionError("wrong document was accepted")
    result = rpc.run_addon_operation(SimpleNamespace(commit_native_mutation=commit), registry_with(callback),
                                    lambda _: None, "Target", "Example", "run", {"value": 1})
    assert result["error_code"] == "DOCUMENT_IDENTITY_MISMATCH"
    callback.assert_not_called()


@pytest.mark.parametrize('rejected', [False, True])
def test_provider_cleanup_runs_only_when_native_commit_is_not_proven(rejected):
    cleanup = Mock()

    def callback(context, arguments):
        context.on_rejected(cleanup)
        return {"value": arguments["value"]}

    status = ({"status": "PublicationFailed", "committed": False, "rollback_succeeded": True}
              if rejected else {"status": "Committed", "committed": True})
    service, _, _ = host(NativeDocument(status=status), registry_with(callback))
    result = service.invoke_addon_operation('Target', 'Example', 'run', {'value': 1})
    assert result['success'] is not rejected
    assert cleanup.call_count == int(rejected)

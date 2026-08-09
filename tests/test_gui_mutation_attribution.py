"""Authenticated request identity after GUI mutation attribution removal."""

from __future__ import annotations

import threading

from addon.FreeCADMCP.rpc_server import request_identity


def _clear_context() -> None:
    request_identity.clear_request_identity()


def test_request_identity_is_copy_on_read_and_replace_on_write():
    _clear_context()
    request_identity.set_request_identity(
        instance_id="runtime-a",
        request_id="11111111-1111-4111-8111-111111111111",
        authenticated_session_id="session-a",
    )

    first = request_identity.get_request_identity()
    first["instance_id"] = "tampered"
    assert request_identity.get_request_identity() == {
        "instance_id": "runtime-a",
        "request_id": "11111111-1111-4111-8111-111111111111",
        "authenticated_session_id": "session-a",
    }

    request_identity.set_request_identity(instance_id="runtime-b")
    assert request_identity.get_request_identity() == {"instance_id": "runtime-b"}
    _clear_context()


def test_request_identity_is_visible_only_on_its_handler_thread():
    _clear_context()
    request_identity.set_request_identity(instance_id="main-runtime")
    entered = threading.Event()
    release = threading.Event()
    worker_results: list[dict[str, object]] = []

    def worker() -> None:
        worker_results.append(request_identity.get_request_identity())
        request_identity.set_request_identity(instance_id="worker-runtime")
        worker_results.append(request_identity.get_request_identity())
        entered.set()
        release.wait(timeout=5)
        request_identity.clear_request_identity()

    thread = threading.Thread(target=worker)
    thread.start()
    assert entered.wait(timeout=5)
    assert request_identity.get_request_identity() == {"instance_id": "main-runtime"}
    release.set()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert worker_results == [{}, {"instance_id": "worker-runtime"}]
    _clear_context()


def test_transport_identity_surface_has_no_document_mutation_authority():
    assert request_identity.__all__ == [
        "clear_request_identity",
        "get_request_identity",
        "set_request_identity",
    ]
    for retired_name in (
        "begin_agent_mutation_scope",
        "begin_internal_snapshot_save_scope",
        "is_agent_mutating",
        "is_internal_snapshot_save",
        "register_observer",
    ):
        assert not hasattr(request_identity, retired_name)

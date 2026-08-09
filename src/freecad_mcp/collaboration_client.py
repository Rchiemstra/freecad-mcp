"""Thin MCP-side delegation to the installed FreeCAD collaboration surface.

This adapter deliberately owns no connection configuration, credentials, or
collaboration state.  The injected connection remains the sole transport and
session implementation; replacing it is the complete reconnect operation.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

__all__ = ["CollaborationClient"]

_CONNECTION_METHODS = (
    "acquire_document_lock",
    "adopt_dirty_document",
    "get_request_status",
    "claim_acquisition_result",
    "acknowledge_acquisition_claim",
    "cancel_request",
    "reconcile_document_lease",
    "stale_recovery_status",
)


class _CollaborationConnection(Protocol):
    """The existing collaboration-facing subset of ``FreeCADConnection``."""

    def acquire_document_lock(
        self,
        doc_name: str = "",
        file_path: str = "",
        session_id: str = "",
        task_description: str = "",
        client: str = "",
        selector: Mapping[str, Any] | None = None,
        agent_id: str = "",
        hash_policy: str = "sha256",
        request_id: str | None = None,
    ) -> dict[str, Any]: ...

    def adopt_dirty_document(
        self,
        *,
        selector: Mapping[str, Any],
        task_description: str = "",
        client: str = "",
        agent_id: str = "",
        hash_policy: str = "sha256",
        request_id: str | None = None,
    ) -> dict[str, Any]: ...

    def get_request_status(
        self, target_request_id: str, *, request_id: str | None = None
    ) -> dict[str, Any]: ...

    def claim_acquisition_result(
        self, target_request_id: str, *, request_id: str | None = None
    ) -> dict[str, Any]: ...

    def acknowledge_acquisition_claim(
        self, target_request_id: str, *, request_id: str | None = None
    ) -> dict[str, Any]: ...

    def cancel_request(
        self, target_request_id: str, *, request_id: str | None = None
    ) -> dict[str, Any]: ...

    def reconcile_document_lease(
        self, document_session_uuid: str, *, request_id: str | None = None
    ) -> dict[str, Any]: ...

    def stale_recovery_status(self) -> dict[str, Any]: ...


class CollaborationClient:
    """Policy-free facade over injected collaboration RPC operations.

    ``rebind`` intentionally does not reconnect, authenticate, copy state, or
    revive an old connection.  The composition owner supplies the replacement
    connection after its normal reconnect flow, while existing consumers keep
    this collaboration-client object.
    """

    def __init__(self, connection: _CollaborationConnection) -> None:
        self._validate_connection(connection)
        self._connection = connection

    @property
    def connection(self) -> _CollaborationConnection:
        """Return the currently installed connection by identity."""

        return self._connection

    def rebind(self, connection: _CollaborationConnection) -> None:
        """Install a fully prepared replacement connection after reconnect."""

        self._validate_connection(connection)
        self._connection = connection

    @staticmethod
    def _validate_connection(connection: _CollaborationConnection) -> None:
        missing = [
            name
            for name in _CONNECTION_METHODS
            if not callable(getattr(connection, name, None))
        ]
        if missing:
            raise TypeError(
                "CollaborationClient requires a FreeCADConnection-compatible "
                f"dependency; missing {', '.join(missing)}"
            )

    def acquire_document_lock(
        self,
        doc_name: str = "",
        file_path: str = "",
        session_id: str = "",
        task_description: str = "",
        client: str = "",
        selector: Mapping[str, Any] | None = None,
        agent_id: str = "",
        hash_policy: str = "sha256",
        request_id: str | None = None,
    ) -> dict[str, Any]:
        return self._connection.acquire_document_lock(
            doc_name,
            file_path,
            session_id,
            task_description,
            client,
            selector,
            agent_id,
            hash_policy,
            request_id,
        )

    def adopt_dirty_document(
        self,
        *,
        selector: Mapping[str, Any],
        task_description: str = "",
        client: str = "",
        agent_id: str = "",
        hash_policy: str = "sha256",
        request_id: str | None = None,
    ) -> dict[str, Any]:
        return self._connection.adopt_dirty_document(
            selector=selector,
            task_description=task_description,
            client=client,
            agent_id=agent_id,
            hash_policy=hash_policy,
            request_id=request_id,
        )

    def get_request_status(
        self, target_request_id: str, *, request_id: str | None = None
    ) -> dict[str, Any]:
        return self._connection.get_request_status(
            target_request_id, request_id=request_id
        )

    def claim_acquisition_result(
        self, target_request_id: str, *, request_id: str | None = None
    ) -> dict[str, Any]:
        return self._connection.claim_acquisition_result(
            target_request_id, request_id=request_id
        )

    def acknowledge_acquisition_claim(
        self, target_request_id: str, *, request_id: str | None = None
    ) -> dict[str, Any]:
        return self._connection.acknowledge_acquisition_claim(
            target_request_id, request_id=request_id
        )

    def cancel_request(
        self, target_request_id: str, *, request_id: str | None = None
    ) -> dict[str, Any]:
        return self._connection.cancel_request(target_request_id, request_id=request_id)

    def reconcile_document_lease(
        self, document_session_uuid: str, *, request_id: str | None = None
    ) -> dict[str, Any]:
        return self._connection.reconcile_document_lease(
            document_session_uuid, request_id=request_id
        )

    def stale_recovery_status(self) -> dict[str, Any]:
        return self._connection.stale_recovery_status()

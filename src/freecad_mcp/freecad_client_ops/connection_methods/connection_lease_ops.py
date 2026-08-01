"""FreeCADConnection method implementations."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

logger = logging.getLogger("FreeCADMCPserver")



def acquire_document_lock(
        conn,
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
        params = {
            "doc_name": doc_name,
            "file_path": file_path,
            "session_id": session_id,
            "task_description": task_description,
            "client": client,
            "selector": dict(selector or {}),
            "agent_id": agent_id,
            "hash_policy": hash_policy,
        }
        routed = conn._invoke_mutation_v2(
            "acquire_document_lock",
            params,
            operation_name="Acquire document lease",
            request_id=request_id,
            require_credentials=False,
        )
        if routed is not None:
            return routed
        return conn.server.acquire_document_lock(
            doc_name,
            file_path,
            session_id,
            task_description,
            client,
            dict(selector or {}),
            agent_id,
            hash_policy,
        )


def adopt_dirty_document(
        conn,
        *,
        selector: Mapping[str, Any],
        task_description: str = "",
        client: str = "",
        agent_id: str = "",
        hash_policy: str = "sha256",
        request_id: str | None = None,
    ) -> dict[str, Any]:
        params = {
            "selector": dict(selector),
            "task_description": task_description,
            "client": client,
            "agent_id": agent_id,
            "hash_policy": hash_policy,
        }
        routed = conn._invoke_mutation_v2(
            "adopt_dirty_document",
            params,
            operation_name="Adopt dirty document",
            request_id=request_id,
            require_credentials=False,
        )
        if routed is not None:
            return routed
        return conn.server.adopt_dirty_document(
            dict(selector),
            task_description,
            client,
            agent_id,
            hash_policy,
        )


def get_document_lock(
        conn,
        doc_name: str = "",
        file_path: str = "",
        session_id: str = "",
        selector: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return conn.server.get_document_lock(
            doc_name, file_path, session_id, dict(selector or {})
        )


def list_document_locks(conn) -> dict[str, Any]:
        return conn.server.list_document_locks()


def heartbeat_document_lock(
        conn,
        doc_key: str,
        token: str,
        current_operation: str = "",
        state: str = "",
        document_dirty: bool | None = None,
    ) -> dict[str, Any]:
        return conn.server.heartbeat_document_lock(
            doc_key, token, current_operation, state, document_dirty
        )


def update_document_lock(
        conn,
        selector: Mapping[str, Any],
        task_description: str = "",
        progress_detail: str = "",
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        selected = dict(selector)
        routed = conn._invoke_mutation_v2(
            "update_document_lock",
            {
                "selector": selected,
                "task_description": task_description,
                "progress_detail": progress_detail,
            },
            selectors=(selected,),
            operation_name="Update lease metadata",
            request_id=request_id,
        )
        if routed is not None:
            return routed
        return conn.server.update_document_lock(
            selected, task_description, progress_detail
        )

"""FreeCADConnection method implementations."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from .connection_lease_ops import _legacy_authority_removed

logger = logging.getLogger("FreeCADMCPserver")



def save_document(
        conn,
        selector: Mapping[str, Any],
        validation_profile: str = "default",
        *,
        request_id: str | None = None,
        legacy_token: str = "",
    ) -> dict[str, Any]:
        selected = dict(selector)
        del legacy_token
        routed = conn._invoke_mutation_v2(
            "save_document",
            {
                "selector": selected,
                "validation_profile": validation_profile,
            },
            selectors=(selected,),
            operation_name="Save and verify document",
            request_id=request_id,
        )
        if routed is not None:
            return routed
        return conn.server.save_document(selected, validation_profile)


def save_document_as(
        conn,
        selector: Mapping[str, Any],
        destination: str,
        overwrite: bool = False,
        expected_destination_sha256: str = "",
        validation_profile: str = "default",
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        selected = dict(selector)
        routed = conn._invoke_mutation_v2(
            "save_document_as",
            {
                "selector": selected,
                "destination": destination,
                "overwrite": overwrite,
                "expected_destination_sha256": expected_destination_sha256,
                "validation_profile": validation_profile,
            },
            selectors=(selected,),
            operation_name="Save As and verify document",
            request_id=request_id,
        )
        if routed is not None:
            return routed
        return conn.server.save_document_as(
            selected,
            destination,
            overwrite,
            expected_destination_sha256,
            validation_profile,
        )


def finalize_document_edit(
        conn,
        selector: Mapping[str, Any],
        save_mode: str = "save",
        destination: str = "",
        overwrite: bool = False,
        expected_destination_sha256: str = "",
        validation_profile: str = "default",
        *,
        request_id: str | None = None,
        legacy_token: str = "",
    ) -> dict[str, Any]:
        selected = dict(selector)
        del legacy_token
        routed = conn._invoke_mutation_v2(
            "finalize_document_edit",
            {
                "selector": selected,
                "save_mode": save_mode,
                "destination": destination,
                "overwrite": overwrite,
                "expected_destination_sha256": expected_destination_sha256,
                "validation_profile": validation_profile,
            },
            selectors=(selected,),
            operation_name="Finalize document edit",
            request_id=request_id,
        )
        if routed is not None:
            return routed
        return conn.server.finalize_document_edit(
            selected,
            save_mode,
            destination,
            overwrite,
            expected_destination_sha256,
            validation_profile,
        )


def release_document_lock(
        conn,
        doc_key: str = "",
        token: str = "",
        *,
        selector: Mapping[str, Any] | None = None,
        disposition: str = "saved",
        request_id: str | None = None,
    ) -> dict[str, Any]:
        del conn, doc_key, token, selector, disposition, request_id
        return _legacy_authority_removed()


def force_release_stale_lock(conn, doc_key: str) -> dict[str, Any]:
        del conn, doc_key
        return {
            "success": False,
            "ok": False,
            "error_code": "LEGACY_LEASE_AUTHORITY_REMOVED",
            "error": "Document authority is owned by native FreeCAD collaboration.",
        }

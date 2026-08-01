"""FreeCADConnection method implementations."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

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
        if legacy_token:
            conn.set_active_lease_token(legacy_token)
            try:
                return conn.server.save_document(selected, validation_profile)
            finally:
                conn.set_active_lease_token(None)
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
        if legacy_token:
            conn.set_active_lease_token(legacy_token)
            try:
                return conn.server.finalize_document_edit(
                    selected,
                    save_mode,
                    destination,
                    overwrite,
                    expected_destination_sha256,
                    validation_profile,
                )
            finally:
                conn.set_active_lease_token(None)
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
        selected = None if selector is None else dict(selector)
        if selected is not None:
            routed = conn._invoke_mutation_v2(
                "release_document_lock",
                {
                    "doc_key": doc_key,
                    "token": token,
                    "selector": selected,
                    "disposition": disposition,
                },
                selectors=(selected,),
                operation_name="Release document lease",
                request_id=request_id,
            )
            if routed is not None:
                return routed
        return conn.server.release_document_lock(
            doc_key,
            token,
            selected,
            disposition,
        )


def force_release_stale_lock(conn, doc_key: str) -> dict[str, Any]:
        return conn.server.force_release_stale_lock(doc_key)

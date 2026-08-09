from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    from document_state import document_modified_or_dirty, document_modified_state
except ImportError:
    from addon.FreeCADMCP.document_state import (
        document_modified_or_dirty,
        document_modified_state,
    )

from .formatting import _bounded_text
from .lease_view import _lease_view
from .local_recovery import _v2_lease_service
from .runtime_bindings import current_runtime_bindings
from .secret_redaction import _redact_secrets


def _append_v2_leases(
    result: list[dict[str, Any]], seen: set[str], service: Any
) -> None:
    try:
        effective_list = getattr(service, "list_effective_records", service.list_records)
        for payload in effective_list():
            safe = _redact_secrets(payload)
            record_id = _lease_view(safe)["record_id"]
            result.append(safe)
            seen.add(record_id)
        for payload in _foreign_shadow_leases(service):
            safe = _redact_secrets(payload)
            record_id = _lease_view(safe)["record_id"]
            if record_id not in seen:
                result.append(safe)
                seen.add(record_id)
    except Exception:
        # A temporarily unavailable v2 service must not prevent legacy
        # status from continuing to render.
        pass


def _append_legacy_leases(
    result: list[dict[str, Any]], seen: set[str], list_leases: Any
) -> None:
    if not callable(list_leases):
        return
    try:
        for record in list_leases():
            if hasattr(record, "to_public_dict"):
                payload = record.to_public_dict()
            elif hasattr(record, "to_dict"):
                payload = record.to_dict()
            elif isinstance(record, Mapping):
                payload = dict(record)
            else:
                continue
            safe = _redact_secrets(payload)
            record_id = _lease_view(safe)["record_id"]
            if record_id not in seen:
                result.append(safe)
                seen.add(record_id)
    except Exception:
        pass


def _active_leases() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()

    service = _v2_lease_service()
    if service is not None:
        _append_v2_leases(result, seen, service)

    bindings = current_runtime_bindings()
    list_compatibility_leases = (
        bindings.list_compatibility_leases if bindings is not None else None
    )
    _append_legacy_leases(result, seen, list_compatibility_leases)
    return result


def _foreign_shadow_leases(service: Any) -> list[dict[str, Any]]:
    """Read token-free sidecar shadows for currently open documents."""

    bindings = current_runtime_bindings()
    freecad = bindings.freecad if bindings is not None else None
    list_documents = getattr(freecad, "listDocuments", None)
    if not callable(list_documents):
        return []

    effective_list = getattr(service, "list_effective_records", service.list_records)
    local_sessions = {
        str(
            item.get("local_document", {}).get("session_uuid")
            or item.get("document", {}).get("session_uuid")
            or ""
        )
        for item in effective_list()
        if isinstance(item, Mapping)
    }
    shadows: list[dict[str, Any]] = []
    for document in list_documents().values():
        try:
            identity = service.identity_service.resolve(
                {"document_name": str(getattr(document, "Name", "") or "")}
            )
            if identity.session_uuid in local_sessions or not identity.canonical_path:
                continue
            sidecar = Path(f"{identity.canonical_path}.freecad-mcp.lock")
            if not os.path.lexists(sidecar):
                continue
            inspector = bindings.inspect_compatibility_lease
            try:
                compatibility = inspector(identity.canonical_path)
            except Exception:
                compatibility = None
            if compatibility is not None:
                continue
            try:
                record = service.sidecar_store.read(sidecar)
                payload = record.to_public_dict()
                payload["source"] = "foreign_sidecar"
                shadows.append(payload)
            except Exception as exc:
                shadows.append(
                    {
                        "schema_version": 2,
                        "record_kind": "freecad-mcp-document-lease-shadow",
                        "lease_id": f"unknown:{identity.session_uuid}",
                        "generation": 0,
                        "source": "unknown_sidecar",
                        "document": identity.to_dict(),
                        "owner": {},
                        "lease": {
                            "state": "SIDECAR_MALFORMED",
                            "current_operation": "Recovery required",
                        },
                        "document_state": {
                            "dirty": document_modified_or_dirty(document),
                            "dirty_state_known": (
                                document_modified_state(document) is not None
                            ),
                            "baseline": None,
                            "error": {
                                "code": "SIDECAR_UNKNOWN",
                                "message": _bounded_text(exc, limit=300),
                            },
                        },
                    }
                )
        except Exception:
            continue
    return shadows

"""Register one live proxy and conservatively import its v2 sidecar."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ._log import logger
from .document_helpers import document_display_name
from .identity_drift import (
    collect_identity_drift_fields,
    identity_refresh_refusal_code,
)
from .identity_registration_failure import (
    IDENTITY_REGISTRATION_BRANCH_POST_INSPECTION_FAILED,
    IDENTITY_REGISTRATION_BRANCH_REGISTRATION_FAILED,
    IdentityRegistrationFailure,
)


def _registration_failure(
    *,
    document_name: str,
    failure_branch: str,
    drifted_fields: tuple[str, ...],
    identity_refresh_attempted: bool,
    identity_refresh_refused_reason: str,
) -> tuple[None, None, IdentityRegistrationFailure]:
    return (
        None,
        None,
        IdentityRegistrationFailure(
            document_name=document_name,
            failure_branch=failure_branch,
            drifted_fields=drifted_fields,
            identity_refresh_attempted=identity_refresh_attempted,
            identity_refresh_refused_reason=identity_refresh_refused_reason,
        ),
    )


def _try_initial_registration(
    identities: Any,
    document: Any,
) -> tuple[Any | None, bool]:
    try:
        return identities.register_document(document), False
    except Exception:
        return None, True


def _try_identity_repair(
    service: Any,
    document: Any,
) -> tuple[Any | None, bool, bool, str]:
    repairer = getattr(service, "repair_registered_document_identity", None)
    if not callable(repairer):
        return None, True, False, ""
    try:
        return repairer(document=document), False, True, ""
    except Exception as repair_exc:
        logger.debug(
            "baseline-preserving identity repair was not applicable",
            exc_info=True,
        )
        return (
            None,
            True,
            True,
            identity_refresh_refusal_code(repair_exc),
        )


def _try_closed_rebind(service: Any, document: Any) -> Any | None:
    rebinder = getattr(service, "rebind_closed_recovery_document", None)
    if not callable(rebinder):
        logger.debug(
            "live document registration failed; skip recovery import",
            exc_info=True,
        )
        return None
    try:
        return rebinder(document=document)
    except Exception:
        logger.debug(
            "closed live document rebind failed; try orphan repair",
            exc_info=True,
        )
        return None


def _needs_orphan_repair(
    service: Any,
    document: Any,
    identity: Any,
    registration_failed: bool,
) -> bool:
    if registration_failed:
        return True
    raw_path = str(getattr(document, "FileName", "") or "").strip()
    get_foreign = getattr(service, "get_foreign_recovery", None)
    if not raw_path or os.path.lexists(f"{raw_path}.freecad-mcp.lock"):
        return False
    try:
        return bool(
            callable(get_foreign) and get_foreign(identity.session_uuid) is not None
        )
    except Exception:
        return False


def _try_orphan_refresh(service: Any, document: Any) -> Any | None:
    orphan_refresher = getattr(
        service,
        "refresh_orphaned_foreign_document_identity",
        None,
    )
    if not callable(orphan_refresher):
        return None
    try:
        return orphan_refresher(document=document)
    except Exception:
        logger.debug(
            "orphaned foreign document identity repair was not applicable",
            exc_info=True,
        )
        return None


def _resolve_registered_identity(
    service: Any,
    identities: Any,
    document: Any,
    document_name: str,
    drifted_fields: tuple[str, ...],
) -> tuple[Any | None, bool, str] | tuple[None, None, IdentityRegistrationFailure]:
    identity, registration_failed = _try_initial_registration(identities, document)
    refresh_attempted = False
    refresh_refused = ""

    if registration_failed:
        identity, registration_failed, repaired, refused = _try_identity_repair(
            service, document
        )
        refresh_attempted = refresh_attempted or repaired
        if refused:
            refresh_refused = refused

    if registration_failed:
        rebound = _try_closed_rebind(service, document)
        if rebound is not None:
            identity = rebound
            registration_failed = False

    if _needs_orphan_repair(service, document, identity, registration_failed):
        refreshed = _try_orphan_refresh(service, document)
        if refreshed is not None:
            identity = refreshed
            registration_failed = False

    if registration_failed:
        return _registration_failure(
            document_name=document_name,
            failure_branch=IDENTITY_REGISTRATION_BRANCH_REGISTRATION_FAILED,
            drifted_fields=drifted_fields,
            identity_refresh_attempted=refresh_attempted,
            identity_refresh_refused_reason=refresh_refused,
        )

    return identity, refresh_attempted, refresh_refused


def _inspect_live_identity(
    identities: Any,
    identity: Any,
    document: Any,
    *,
    document_name: str,
    drifted_fields: tuple[str, ...],
    identity_refresh_attempted: bool,
    identity_refresh_refused_reason: str,
) -> tuple[Any | None, IdentityRegistrationFailure | None]:
    try:
        return identities.inspect_registered_document(
            identity.session_uuid, document
        ), None
    except Exception:
        logger.debug(
            "registered live proxy mismatch; skip recovery import",
            exc_info=True,
        )
        return None, IdentityRegistrationFailure(
            document_name=document_name,
            failure_branch=IDENTITY_REGISTRATION_BRANCH_POST_INSPECTION_FAILED,
            drifted_fields=collect_identity_drift_fields(identities, document)
            or drifted_fields
            or ("live_proxy_inspection_failed",),
            identity_refresh_attempted=identity_refresh_attempted,
            identity_refresh_refused_reason=identity_refresh_refused_reason,
        )


def _try_import_adjacent_recovery(
    service: Any,
    live_identity: Any,
) -> Mapping[str, Any] | None:
    if not live_identity.canonical_path:
        return None
    sidecar = Path(f"{live_identity.canonical_path}.freecad-mcp.lock")
    if not os.path.lexists(sidecar):
        return None
    if service.get(live_identity.session_uuid) is not None:
        return None
    get_foreign = getattr(service, "get_foreign_recovery", None)
    if callable(get_foreign):
        existing = get_foreign(live_identity.session_uuid)
        if existing is not None:
            return None
    importer = getattr(service, "import_adjacent_foreign_recovery", None)
    if not callable(importer):
        return None
    try:
        return importer(
            live_identity.session_uuid,
            live_document=live_identity,
        )
    except Exception:
        logger.warning(
            "unable to import adjacent document recovery sidecar",
            exc_info=True,
        )
        return None


def register_live_document_recovery(
    service: Any, document: Any
) -> tuple[Any, Mapping[str, Any] | None, IdentityRegistrationFailure | None]:
    """Register one live proxy, then conservatively import its v2 sidecar."""

    identities = getattr(service, "identity_service", None)
    if identities is None:
        raise RuntimeError("document identity service is unavailable")
    document_name = document_display_name(document)
    drifted_fields = collect_identity_drift_fields(identities, document)

    resolved = _resolve_registered_identity(
        service,
        identities,
        document,
        document_name,
        drifted_fields,
    )
    if isinstance(resolved[2], IdentityRegistrationFailure):
        return resolved

    identity, identity_refresh_attempted, identity_refresh_refused_reason = resolved

    live_identity, inspection_failure = _inspect_live_identity(
        identities,
        identity,
        document,
        document_name=document_name,
        drifted_fields=drifted_fields,
        identity_refresh_attempted=identity_refresh_attempted,
        identity_refresh_refused_reason=identity_refresh_refused_reason,
    )
    if inspection_failure is not None:
        return None, None, inspection_failure

    imported = _try_import_adjacent_recovery(service, live_identity)
    return live_identity, imported, None

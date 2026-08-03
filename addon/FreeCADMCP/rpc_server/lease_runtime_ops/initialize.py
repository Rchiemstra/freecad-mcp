"""Initialize process-lifetime document identity and lease authority."""

from __future__ import annotations

import logging
from typing import Any

import FreeCAD

from ..save_service import SaveService
from ..settings import SettingsPolicyError

try:
    from ..._shared.protocol.request_replay_cache import RequestReplayCache
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.request_replay_cache import RequestReplayCache

logger = logging.getLogger("FreeCADMCP.rpc_server")


def _effective_lease_records(rpc_mod: Any) -> list[Any]:
    service = rpc_mod.document_lease_service
    if service is None:
        return []
    list_records = getattr(service, "list_effective_records", service.list_records)
    return list_records()


def _parse_lease_settings(
    settings: dict[str, Any], rpc_mod: Any
) -> tuple[str, tuple[bool, bool, bool]]:
    lease_mode = str(settings.get("document_lease_mode") or "off")
    if lease_mode not in {"off", "observe", "enforce"}:
        raise SettingsPolicyError(
            "document_lease_mode must be one of: enforce, observe, off"
        )
    persist_task_summary = settings.get("persist_task_summary_in_sidecar", False)
    if not isinstance(persist_task_summary, bool):
        raise SettingsPolicyError(
            "persist_task_summary_in_sidecar must be true or false"
        )
    desired_policy = (
        lease_mode == "enforce",
        bool(settings.get("allow_network_sidecar", False)),
        persist_task_summary,
    )
    return lease_mode, desired_policy


def _validate_runtime_mode_change(
    rpc_mod: Any,
    *,
    lease_mode: str,
    effective_records: list[Any],
) -> None:
    if (
        rpc_mod.document_lease_runtime_mode is not None
        and rpc_mod.document_lease_runtime_mode != lease_mode
        and effective_records
    ):
        raise SettingsPolicyError(
            "document lease mode cannot change while active lease or recovery "
            "records exist"
        )


def _validate_runtime_policy_change(
    rpc_mod: Any,
    *,
    desired_policy: tuple[bool, bool, bool],
    effective_records: list[Any],
) -> None:
    if (
        rpc_mod.document_lease_service is not None
        and rpc_mod.document_lease_runtime_policy != desired_policy
    ):
        if effective_records:
            raise SettingsPolicyError(
                "document lease sidecar policy cannot change while active "
                "lease or recovery records exist"
            )
        rpc_mod.document_lease_service = None


def _create_lease_service(
    rpc_mod: Any,
    *,
    settings: dict[str, Any],
    lease: Any,
    desired_policy: tuple[bool, bool, bool],
) -> None:
    if rpc_mod.document_lease_service is not None:
        return
    rpc_mod.document_lease_service = lease.DocumentLeaseService(
        rpc_mod.document_identity_service,
        lease.SidecarStore(
            strict_permissions=desired_policy[0],
            allow_network=desired_policy[1],
            persist_task_summary=desired_policy[2],
        ),
        local_runtime_identity=rpc_mod._make_local_runtime_identity(
            settings, lease
        ),
        process_liveness_probe=rpc_mod._probe_process_liveness,
    )
    rpc_mod.document_lease_runtime_policy = desired_policy


def _configure_replay_and_save_services(rpc_mod: Any) -> None:
    if rpc_mod.rpc_request_replay_cache is None:
        # Compatibility for tests or an older module state hot-reloaded into
        # this FreeCAD process.  Ordinary listener restarts reuse the object.
        rpc_mod.rpc_request_replay_cache = RequestReplayCache()
    rpc_mod.rpc_request_replay_cache.set_owner_lease_predicate(
        rpc_mod.document_lease_service.has_unresolved_owner
    )
    if rpc_mod.save_service is None:
        rpc_mod.save_service = SaveService(
            platform=rpc_mod.document_identity_service.platform
        )


def _register_live_documents(rpc_mod: Any) -> None:
    try:
        for document in FreeCAD.listDocuments().values():
            rpc_mod._ensure_v2_document(document)
    except Exception as exc:
        logger.warning("Could not register all live document identities: %s", exc)


def initialize_document_lease_runtime(settings=None, *, rpc_mod: Any):
    """Create process-lifetime document identity/lease authority.

    The runtime is intentionally independent from the XML-RPC listener.  This
    lets observers and the status UI detect foreign sidecars before auto-start
    and preserves document session UUIDs across listener restarts.
    """

    settings = dict(settings or rpc_mod.load_settings())
    lease_mode, desired_policy = _parse_lease_settings(settings, rpc_mod)
    lease = rpc_mod._import_document_lease()

    if rpc_mod.document_identity_service is None:
        rpc_mod.document_identity_service = lease.DocumentIdentityService()
    effective_records = _effective_lease_records(rpc_mod)
    _validate_runtime_mode_change(
        rpc_mod, lease_mode=lease_mode, effective_records=effective_records
    )
    _validate_runtime_policy_change(
        rpc_mod, desired_policy=desired_policy, effective_records=effective_records
    )
    _create_lease_service(
        rpc_mod, settings=settings, lease=lease, desired_policy=desired_policy
    )
    rpc_mod.document_lease_runtime_mode = lease_mode
    rpc_mod._import_document_lock().configure_runtime_lease_mode(lease_mode)
    _configure_replay_and_save_services(rpc_mod)
    _register_live_documents(rpc_mod)
    rpc_mod._ensure_lease_watchdog_running()
    return rpc_mod.document_lease_service

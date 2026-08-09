"""Recovery proof validation helpers for document lease service operations."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from ..errors.foreign_recovery_error import ForeignRecoveryError
from ..errors.local_recovery_error import LocalRecoveryError
from ..errors.process_liveness_evidence import ProcessLivenessEvidence
from ..model import LeaseOwner
from .constants import MCP_PROCESS_START_FUTURE_TOLERANCE_SECONDS


def validate_local_runtime_for_foreign_proof(self) -> tuple[Any, datetime]:
    local = self._local_runtime_identity
    if local is None:
        raise ForeignRecoveryError("local runtime identity evidence is unavailable")
    if (
        not local.addon_profile_id
        or not local.addon_runtime_id
        or local.freecad_pid < 1
        or not local.freecad_process_started_at
    ):
        raise ForeignRecoveryError("local runtime identity evidence is incomplete")
    try:
        uuid.UUID(local.addon_profile_id)
        uuid.UUID(local.addon_runtime_id)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ForeignRecoveryError(
            "local addon profile/runtime identity is invalid"
        ) from exc
    local_started = self._parse_timestamp(local.freecad_process_started_at)
    if local_started is None:
        raise ForeignRecoveryError("FreeCAD process-start identity evidence is invalid")
    return local, local_started


def assert_same_host_boot_identity(local, owner: LeaseOwner) -> None:
    if not local.hostname or not owner.hostname:
        raise ForeignRecoveryError("same-host ownership cannot be proven")
    if local.hostname.casefold() != owner.hostname.casefold():
        raise ForeignRecoveryError(
            "foreign owner belongs to another host; local death is unprovable"
        )
    if not local.boot_id or not owner.boot_id:
        raise ForeignRecoveryError("host boot identity evidence is incomplete")


def foreign_death_same_process_proof(
    local,
    owner: LeaseOwner,
    *,
    local_started: datetime,
    owner_started: datetime,
) -> str | None:
    if local.boot_id != owner.boot_id:
        return "same host restarted since the recorded owner runtime"
    if local.freecad_pid != owner.freecad_pid:
        return None
    if local_started != owner_started:
        return "recorded FreeCAD PID was reused after its owner exited"
    if local.addon_runtime_id != owner.addon_runtime_id:
        return "recorded addon runtime was replaced in the same process"
    raise ForeignRecoveryError(
        "the foreign record identifies the current live addon runtime"
    )


def foreign_death_process_probe_proof(
    self,
    owner: LeaseOwner,
    *,
    owner_started: datetime,
) -> str:
    probe = self._process_liveness_probe
    if probe is None:
        raise ForeignRecoveryError("same-boot process liveness evidence is unavailable")
    try:
        evidence = probe(owner.freecad_pid)
    except Exception as exc:
        raise ForeignRecoveryError(
            f"owner process liveness could not be established: {exc}"
        ) from exc
    if not isinstance(evidence, ProcessLivenessEvidence):
        raise ForeignRecoveryError("owner process probe returned invalid evidence")
    if evidence.exists is False:
        return "recorded FreeCAD process no longer exists on this boot"
    if evidence.exists is None:
        raise ForeignRecoveryError("owner process liveness is unknown")
    if not evidence.process_started_at:
        raise ForeignRecoveryError("live owner process start identity is unavailable")
    evidence_started = self._parse_timestamp(evidence.process_started_at)
    if evidence_started is None:
        raise ForeignRecoveryError("live owner process start identity is invalid")
    if evidence_started == owner_started:
        raise ForeignRecoveryError("the recorded FreeCAD owner process is still alive")
    return "recorded FreeCAD PID now belongs to a different process"


def validate_local_mcp_runtime_match(self, owner: LeaseOwner) -> None:
    local = self._local_runtime_identity
    if local is None:
        raise LocalRecoveryError("local runtime identity evidence is unavailable")
    expected_runtime = (
        local.addon_profile_id,
        local.addon_runtime_id,
        local.freecad_pid,
        local.freecad_process_started_at,
        local.boot_id,
    )
    recorded_runtime = (
        owner.addon_profile_id,
        owner.addon_runtime_id,
        owner.freecad_pid,
        owner.freecad_process_started_at,
        owner.boot_id,
    )
    if recorded_runtime != expected_runtime:
        raise LocalRecoveryError(
            "lease authority does not belong to this FreeCAD runtime"
        )
    if (
        not local.hostname
        or not owner.hostname
        or local.hostname.casefold() != owner.hostname.casefold()
    ):
        raise LocalRecoveryError("the lease does not belong to this FreeCAD host")
    if (
        not owner.mcp_hostname
        or owner.mcp_hostname.casefold() != local.hostname.casefold()
    ):
        raise LocalRecoveryError(
            "the credential-owning MCP process is not proven co-located"
        )
    if owner.mcp_pid < 1 or not owner.mcp_process_started_at:
        raise LocalRecoveryError("MCP process identity evidence is incomplete")


def mcp_death_process_probe_proof(self, owner: LeaseOwner) -> str:
    owner_started = self._parse_timestamp(owner.mcp_process_started_at)
    if owner_started is None:
        raise LocalRecoveryError("MCP process-start identity evidence is invalid")
    probe = self._process_liveness_probe
    if probe is None:
        raise LocalRecoveryError("MCP process liveness evidence is unavailable")
    try:
        evidence = probe(owner.mcp_pid)
    except Exception as exc:
        raise LocalRecoveryError(
            f"MCP process liveness could not be established: {exc}"
        ) from exc
    if not isinstance(evidence, ProcessLivenessEvidence):
        raise LocalRecoveryError("MCP process probe returned invalid evidence")
    if evidence.exists is False:
        return "recorded MCP process no longer exists on this boot"
    if evidence.exists is None:
        raise LocalRecoveryError("MCP process liveness is unknown")
    if not evidence.process_started_at:
        raise LocalRecoveryError("live MCP process start identity is unavailable")
    evidence_started = self._parse_timestamp(evidence.process_started_at)
    if evidence_started is None:
        raise LocalRecoveryError("live MCP process start identity is invalid")
    seconds_after_owner_marker = (evidence_started - owner_started).total_seconds()
    if seconds_after_owner_marker > MCP_PROCESS_START_FUTURE_TOLERANCE_SECONDS:
        return "recorded MCP PID now belongs to a different process"
    raise LocalRecoveryError("the credential-owning MCP process may still be alive")

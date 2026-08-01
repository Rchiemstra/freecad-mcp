from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from .facade_surfaces import current_time
from .lease_state import LeaseState


@dataclass
class LeaseRecord:
    doc_key: str
    doc_name: str
    token: str = field(repr=False)
    instance_id: str
    client: str
    pid: int
    host: str
    task_description: str = ""
    acquired_at: float = field(default_factory=current_time)
    last_heartbeat: float = field(default_factory=current_time)
    current_operation: str = ""
    document_dirty: bool = False
    last_save_time: float | None = None
    baseline_mtime: float | None = None
    baseline_hash: str | None = None
    state: str = LeaseState.LOCKED_IDLE.value
    rpc_port: int | None = None
    lease_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    generation: int = 1
    state_revision: int = 1
    record_revision: int = 1
    heartbeat_sequence: int = 0
    last_mutation_revision: int = 0
    last_verified_save_revision: int = 0
    user_intervened: bool = False
    request_id: str | None = None
    error_info: dict[str, Any] | None = None
    document_session_uuid: str = ""
    token_fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("token", None)
        payload.pop("token_fingerprint", None)
        return payload

    def to_sidecar_dict(self) -> dict[str, Any]:
        payload = self.to_dict()
        digest = self.token_fingerprint or hashlib.sha256(
            self.token.encode("utf-8")
        ).hexdigest()
        payload["token_fingerprint"] = f"sha256:{digest.removeprefix('sha256:')}"
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LeaseRecord:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        values = {k: v for k, v in data.items() if k in known}
        raw_token = str(values.get("token") or "")
        fingerprint = str(values.get("token_fingerprint") or "")
        if raw_token and not fingerprint:
            fingerprint = "sha256:" + hashlib.sha256(
                raw_token.encode("utf-8")
            ).hexdigest()
        # A sidecar is public coordination metadata, never credential custody.
        values["token"] = ""
        values["token_fingerprint"] = fingerprint
        return cls(**values)

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from typing import Any

from .validation import ValidationResult


def _sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


@dataclass(frozen=True)
class ExecutionBinding:
    run_id: str
    attempt_id: str
    sequence: int
    nonce: str
    output_root: str
    configured_candidate: str
    raw_candidate: str
    repository: str
    image: str
    package_manifest: str
    trusted_bootstrap: str
    commands: str
    scope: str
    reviewer_key: str
    authorization_sha256: str = ""
    signature_sha256: str = ""
    start_utc: str = ""

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def parse(cls, value: Any, artifact: str, field: str = "/binding") -> tuple["ExecutionBinding | None", ValidationResult]:
        if not isinstance(value, dict) or set(value) != set(cls.__annotations__):
            return None, ValidationResult.fail("binding", "EXECUTION_BINDING_SCHEMA", artifact, field)
        if not isinstance(value.get("sequence"), int) or isinstance(value.get("sequence"), bool):
            return None, ValidationResult.fail("binding", "EXECUTION_BINDING_SCHEMA", artifact, field + "/sequence")
        if any(not isinstance(value.get(name), str) for name in cls.__annotations__ if name != "sequence"):
            return None, ValidationResult.fail("binding", "EXECUTION_BINDING_SCHEMA", artifact, field)
        hashes = ("nonce", "configured_candidate", "raw_candidate", "repository", "package_manifest", "trusted_bootstrap", "commands", "reviewer_key", "authorization_sha256", "signature_sha256")
        if any(not _sha256(value.get(name)) for name in hashes) or not str(value.get("image", "")).startswith("sha256:") or not value.get("output_root") or not value.get("scope"):
            return None, ValidationResult.fail("binding", "EXECUTION_BINDING_VALUE", artifact, field)
        try:
            return cls(**value), ValidationResult.ok()
        except TypeError:
            return None, ValidationResult.fail("binding", "EXECUTION_BINDING_SCHEMA", artifact, field)

    @classmethod
    def from_snapshot(cls, authorization: bytes, signature: bytes, start_utc: str, direct: "AuthorizationBinding") -> "ExecutionBinding":
        return cls(**direct.as_dict(), authorization_sha256=hashlib.sha256(authorization).hexdigest(), signature_sha256=hashlib.sha256(signature).hexdigest(), start_utc=start_utc)  # type: ignore[arg-type]


@dataclass(frozen=True)
class AuthorizationBinding:
    run_id: str
    attempt_id: str
    sequence: int
    nonce: str
    output_root: str
    configured_candidate: str
    raw_candidate: str
    repository: str
    image: str
    package_manifest: str
    trusted_bootstrap: str
    commands: str
    scope: str
    reviewer_key: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ContainerExecutionBinding:
    execution: ExecutionBinding
    container_id: str
    raw_inspect_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "execution": self.execution.as_dict(),
            "container_id": self.container_id,
            "raw_inspect_sha256": self.raw_inspect_sha256,
        }

    @classmethod
    def parse(cls, value: Any, artifact: str, field: str = "/binding") -> tuple["ContainerExecutionBinding | None", ValidationResult]:
        if not isinstance(value, dict) or set(value) != {"execution", "container_id", "raw_inspect_sha256"}:
            return None, ValidationResult.fail("child", "CHILD_BINDING_SCHEMA", artifact, field)
        execution, result = ExecutionBinding.parse(value["execution"], artifact, field + "/execution")
        if not result.passed or execution is None:
            return None, result
        if not _sha256(value["container_id"]) or not _sha256(value["raw_inspect_sha256"]):
            return None, ValidationResult.fail("child", "CHILD_BINDING_VALUE", artifact, field)
        return cls(execution, value["container_id"], value["raw_inspect_sha256"]), ValidationResult.ok()

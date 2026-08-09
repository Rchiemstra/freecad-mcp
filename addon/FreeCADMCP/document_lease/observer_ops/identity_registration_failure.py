"""Diagnostics when live document registration returns None."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

IDENTITY_REGISTRATION_BRANCH_REGISTRATION_FAILED = "registration_failed"
IDENTITY_REGISTRATION_BRANCH_POST_INSPECTION_FAILED = (
    "post_registration_inspection_failed"
)


@dataclass(frozen=True)
class IdentityRegistrationFailure:
    """Token-free diagnostics when live document registration returns None."""

    document_name: str
    failure_branch: str
    drifted_fields: tuple[str, ...] = ()
    identity_refresh_attempted: bool = False
    identity_refresh_refused_reason: str = ""

    def to_details(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "document_name": self.document_name,
            "failure_branch": self.failure_branch,
            "identity_refresh_attempted": self.identity_refresh_attempted,
        }
        if self.drifted_fields:
            payload["drifted_fields"] = list(self.drifted_fields)
        if (
            self.identity_refresh_attempted
            and self.identity_refresh_refused_reason
        ):
            payload["identity_refresh_refused_reason"] = (
                self.identity_refresh_refused_reason
            )
        return payload

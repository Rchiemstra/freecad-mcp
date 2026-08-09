"""Result of a trusted same-host process identity probe."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessLivenessEvidence:
    """Result of a trusted same-host process identity probe.

    ``exists=None`` means the probe could not establish either liveness or
    death. A live process must include its observed start timestamp so PID
    reuse can be distinguished from the recorded owner.
    """

    exists: bool | None
    process_started_at: str | None = None


ProcessLivenessEvidence.__module__ = "document_lease.service"

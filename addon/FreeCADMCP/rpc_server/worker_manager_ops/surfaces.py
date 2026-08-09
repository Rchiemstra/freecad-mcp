"""§3.3 monkeypatch surfaces for WorkerManager."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .worker_invocation import WorkerInvocation


def attach_worker_manager_surfaces(manager_cls) -> None:
    def _candidate_paths(self) -> list[Path]:
        from .executable_discovery import candidate_paths

        return candidate_paths(self.runtime)

    def _probe_version(self, candidate: Path) -> tuple[str, str, str, str]:
        from .executable_discovery import probe_version

        return probe_version(candidate)

    @staticmethod
    def _worker_environment(workspace: Path) -> dict[str, str]:
        from .worker_environment import worker_environment

        return worker_environment(workspace)

    def _promote_artifacts(self, artifacts, staging: Path, job_id: str):
        from .artifact_promotion import promote_artifacts

        return promote_artifacts(self, artifacts, staging, job_id)

    def _temp_usage(self) -> int:
        from .temp_usage import temp_usage

        return temp_usage(self.temp_root)

    def _execute_now(self, invocation: WorkerInvocation) -> dict[str, Any]:
        from .execute_job import execute_job_now

        return execute_job_now(self, invocation)

    manager_cls._candidate_paths = _candidate_paths
    manager_cls._probe_version = _probe_version
    manager_cls._worker_environment = _worker_environment
    manager_cls._promote_artifacts = _promote_artifacts
    manager_cls._temp_usage = _temp_usage
    manager_cls._execute_now = _execute_now

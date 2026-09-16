from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Callable, Mapping, Sequence

from .environment import sanitized_host_environment
from .launch_source import ApprovedLaunchSource
from .host import select_host_interpreter
from .policy import PYTHON_FLAGS


def isolated_python_argv(interpreter: Path, bootstrap: Path) -> tuple[str, ...]:
    if not interpreter.is_absolute() or not bootstrap.is_absolute():
        raise ValueError("absolute interpreter and bootstrap required")
    return (str(interpreter), *PYTHON_FLAGS, str(bootstrap))


def run_isolated(
    bootstrap: Path,
    package: Path,
    arguments: Sequence[str],
    source_environment: Mapping[str, str],
    approved_bootstrap_sha256: str,
    approved_interpreter_sha256: str,
    approved_reviewer_sha256: str,
    expected_run_id: str,
    expected_attempt_id: str,
    expected_sequence: int,
    expected_scope: str,
    timeout: float = 60,
    pre_open_hook: Callable[[], None] | None = None,
    pre_spawn_hook: Callable[[], None] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Hash the trusted bootstrap immediately before an isolated spawn."""
    if not bootstrap.is_absolute() or not package.is_absolute():
        raise ValueError("absolute bootstrap and package required")
    if len(approved_reviewer_sha256) != 64:
        raise ValueError("trusted reviewer approval missing")
    interpreter = select_host_interpreter(source_environment)
    argv = (
        *isolated_python_argv(interpreter, bootstrap), str(package),
        "--reviewer-sha256", approved_reviewer_sha256,
        "--interpreter-sha256", approved_interpreter_sha256,
        "--run-id", expected_run_id, "--attempt-id", expected_attempt_id,
        "--sequence", str(expected_sequence), "--scope", expected_scope,
        "--", *arguments,
    )
    environment = sanitized_host_environment(dict(source_environment))
    with ApprovedLaunchSource(interpreter, approved_interpreter_sha256, "interpreter", interpreter.name, "HOST_INTERPRETER") as executable:
        with ApprovedLaunchSource(bootstrap, approved_bootstrap_sha256, "startup", bootstrap.name, "LAUNCH_SOURCE", pre_open_hook) as source:
            return source.run(argv, 4, (), environment=environment, timeout=timeout, before_spawn=pre_spawn_hook, additional_sources={0: executable})

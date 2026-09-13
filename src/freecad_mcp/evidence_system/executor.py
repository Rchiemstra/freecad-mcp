"""Offline executor boundary for the evidence lifecycle.

The signed package authorizes a command identity, never a prerecorded result.
The controlled executor is invoked after preflight and returns newly observed
container data while writing its own child phase records.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import tempfile
import os
from typing import Any, Callable

from .bindings import ContainerExecutionBinding, ExecutionBinding
from .environment import sanitized_host_environment
from .launch_source import ApprovedLaunchSource, LaunchSourceError
from .validation import ValidationResult


@dataclass(frozen=True)
class ControlledOfflineExecutor:
    command: tuple[str, ...]
    policy: object
    expected_sha256: str
    pre_open_hook: Callable[[], None] | None = None
    pre_spawn_hook: Callable[[], None] | None = None

    def _approved_source(self) -> ApprovedLaunchSource:
        if tuple(getattr(self.policy, "executor_argv")) != self.command:
            raise LaunchSourceError("executor", "EXECUTOR_SOURCE_BINDING", "executor-worker", "/command")
        target = Path(self.command[4])
        return ApprovedLaunchSource(target, self.expected_sha256, "executor", target.name, "EXECUTOR_SOURCE", self.pre_open_hook)

    def _approved_interpreter(self) -> ApprovedLaunchSource:
        digest = getattr(self.policy, "binaries", {}).get("host_interpreter")
        if not isinstance(digest, str):
            raise LaunchSourceError("interpreter", "HOST_INTERPRETER_UNAPPROVED", "host-interpreter", "/sha256")
        return ApprovedLaunchSource(Path(self.command[0]), digest, "interpreter", "host-interpreter", "HOST_INTERPRETER")

    def capture_preflight(self, binding: ExecutionBinding, policy: object) -> bytes:
        request = json.dumps({"binding": binding.as_dict(), "policy": _policy_wire(policy)}, sort_keys=True, separators=(",", ":"))
        with self._approved_interpreter() as executable, self._approved_source() as source:
            completed = _invoke(source, executable, self.command, "--preflight-request", request, self.pre_spawn_hook)
        if completed.returncode != 0:
            raise ValueError("preflight executor exit")
        # Preserve bytes exactly as observed; the preflight validator owns JSON parsing.
        return completed.stdout.encode("utf-8")

    def execute(self, output: Path, binding: ExecutionBinding) -> tuple[dict[str, object], int, ContainerExecutionBinding]:
        if not self.command or not Path(self.command[0]).is_absolute():
            raise ValueError("executor command")
        request = json.dumps({"output": str(output), "binding": binding.as_dict(), "policy": _policy_wire(self.policy)}, sort_keys=True, separators=(",", ":"))
        with self._approved_interpreter() as executable, self._approved_source() as source:
            completed = _invoke(source, executable, self.command, "--evidence-request", request, self.pre_spawn_hook)
        if completed.returncode not in {0, 1}:
            raise ValueError("executor exit")
        try:
            value: Any = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError("executor output") from exc
        required = {"execution", "parent_exit", "container_id", "raw_inspect_sha256"}
        if not isinstance(value, dict) or set(value) != required or not isinstance(value["execution"], dict) or not isinstance(value["parent_exit"], int) or isinstance(value["parent_exit"], bool) or not all(isinstance(value[name], str) for name in ("container_id", "raw_inspect_sha256")):
            raise ValueError("executor record")
        return value["execution"], value["parent_exit"], ContainerExecutionBinding(binding, value["container_id"], value["raw_inspect_sha256"])

    def cleanup(self, output: Path, binding: ExecutionBinding) -> dict[str, object]:
        request = json.dumps({"output": str(output), "binding": binding.as_dict(), "policy": _policy_wire(self.policy)}, sort_keys=True, separators=(",", ":"))
        with self._approved_interpreter() as executable, self._approved_source() as source:
            completed = _invoke(source, executable, self.command, "--cleanup-request", request, self.pre_spawn_hook)
        try: value: Any = json.loads(completed.stdout)
        except json.JSONDecodeError as error: raise ValueError("cleanup output") from error
        if completed.returncode != 0 or not isinstance(value, dict) or set(value) != {"passed", "errors"} or not isinstance(value["passed"], bool) or not isinstance(value["errors"], list) or not all(isinstance(row, str) for row in value["errors"]):
            raise ValueError("cleanup record")
        return value


def _policy_wire(policy: object) -> dict[str, object]:
    names = ("sources", "binaries", "environment", "mounts", "outer_argv", "executor_argv", "docker_argv")
    return {name: list(getattr(policy, name)) if name.endswith("argv") else getattr(policy, name) for name in names}


def _invoke(source: ApprovedLaunchSource, executable: ApprovedLaunchSource, command: tuple[str, ...], mode: str, request: str, before_spawn: Callable[[], None] | None) -> subprocess.CompletedProcess[str]:
    """Keep the controlled request out of Windows' command-line size limit."""
    handle = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", delete=False)
    try:
        handle.write(request); handle.close()
        return source.run(
            command, 4, (mode, "--request-file", handle.name),
            environment=sanitized_host_environment(dict(__import__("os").environ)), timeout=60,
            before_spawn=before_spawn, additional_sources={0: executable},
        )
    finally:
        try:
            handle.close(); __import__("os").unlink(handle.name)
        except OSError:
            pass


def validate_executor_command(value: object) -> ValidationResult:
    if not isinstance(value, list) or len(value) < 5 or not all(isinstance(item, str) for item in value):
        return ValidationResult.fail("executor", "EXECUTOR_COMMAND_SCHEMA", "evidence-config.json", "/runtime/executor_command")
    if not Path(value[0]).is_absolute() or tuple(value[1:4]) != ("-I", "-S", "-B") or not Path(value[4]).is_absolute():
        return ValidationResult.fail("executor", "EXECUTOR_COMMAND_CONTRACT", "evidence-config.json", "/runtime/executor_command")
    return ValidationResult.ok()

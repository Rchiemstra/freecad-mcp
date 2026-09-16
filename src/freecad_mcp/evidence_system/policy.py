"""Strict, signed configuration policy for the tracked evidence boundary."""
from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any
from pathlib import Path

PYTHON_FLAGS = ("-I", "-S", "-B")
HOST_ENVIRONMENT_KEYS = ("SystemRoot", "WINDIR", "ComSpec", "TEMP", "TMP")
CONTAINER_ENVIRONMENT_KEYS = ("HOME", "APPDATA", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "FREECAD_USER_HOME", "FREECAD_USER_DATA", "FREECAD_USER_TEMP", "LD_LIBRARY_PATH", "DISPLAY", "QT_QPA_PLATFORM")
FORBIDDEN_PYTHON_KEYS = frozenset(("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONNOUSERSITE", "PYTHONUSERBASE"))
AUTHORIZATION_SCOPE = "tracked-evidence-scope/44"
GOVERNED_RUNNER = "runner.py"
PREFLIGHT_CHECKS = ("package", "authorization", "configured_candidate", "raw_candidate", "repository", "sources", "binaries", "image", "output_freshness", "conflicting_processes", "port", "cache", "resolved_outer_command", "resolved_executor_command", "resolved_docker_command", "environment", "mounts", "timestamp_freshness")
REQUIRED_PACKAGE_FILES = frozenset(("runner.py", "package-manifest.json", "package-manifest.sig", "review-authorization.json", "review-authorization.sig", "reviewer.pub", "evidence-config.json"))


@dataclass(frozen=True)
class EvidencePolicy:
    run_id: str
    attempt_id: str
    sequence: int
    reviewer_key: str
    scope: str
    interpreter: str
    outer_argv: tuple[str, ...]
    executor_argv: tuple[str, ...]
    docker_argv: tuple[str, ...]
    environment: dict[str, str]
    mounts: tuple[dict[str, object], ...]
    sources: dict[str, str]
    binaries: dict[str, str]
    container_environment: dict[str, str] = dataclass_field(default_factory=dict)
    container_entrypoint: tuple[str, ...] = ("/usr/bin/python3", "-I", "-S", "-B", "/trusted/bootstrap.py")
    container_cmd: tuple[str, ...] = ()
    max_age_seconds: int = 60
    future_skew_seconds: int = 5
    authorization_lifetime_seconds: int = 900

    def __post_init__(self) -> None:
        def absolute(value: str) -> bool:
            return value.startswith("/") or (len(value) > 2 and value[1] == ":" and value[2] in "/\\")

        if not self.run_id or not self.attempt_id or not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or len(self.reviewer_key) != 64 or any(character not in "0123456789abcdef" for character in self.reviewer_key):
            raise ValueError("policy identity")
        if self.scope != AUTHORIZATION_SCOPE:
            raise ValueError("policy scope/interpreter")
        if set(self.environment) - set(HOST_ENVIRONMENT_KEYS) or set(self.environment) & FORBIDDEN_PYTHON_KEYS:
            raise ValueError("policy environment")
        if set(self.container_environment) - set(CONTAINER_ENVIRONMENT_KEYS) or set(self.container_environment) & FORBIDDEN_PYTHON_KEYS:
            raise ValueError("policy container environment")
        for command in (self.outer_argv, self.executor_argv):
            if len(command) < 5 or tuple(command[1:4]) != PYTHON_FLAGS or not absolute(command[0]) or not absolute(command[4]):
                raise ValueError("policy isolated argv")
        if not _absolute(self.interpreter) or self.outer_argv[0] != self.interpreter or self.executor_argv[0] != self.interpreter:
            raise ValueError("policy host interpreter binding")
        if not _hash(self.binaries.get("host_interpreter")):
            raise ValueError("policy host interpreter identity")
        if self.outer_argv.count("--interpreter-sha256") != 1:
            raise ValueError("policy root interpreter approval")
        approval_index = self.outer_argv.index("--interpreter-sha256")
        if approval_index + 1 >= len(self.outer_argv) or self.outer_argv[approval_index + 1] != self.binaries["host_interpreter"]:
            raise ValueError("policy root interpreter approval")
        if not self.docker_argv or not absolute(self.docker_argv[0]):
            raise ValueError("policy docker executable")
        if tuple(self.container_entrypoint[1:4]) != PYTHON_FLAGS or self.container_entrypoint[-1] != "/trusted/bootstrap.py":
            raise ValueError("policy container entrypoint")
        expected_destinations = ("/diagnostic", "/trusted/bootstrap.py", "/repo", "/build", "/out")
        if len(self.mounts) != len(expected_destinations) or tuple(row.get("Destination") for row in self.mounts) != expected_destinations:
            raise ValueError("policy mount destinations")
        if any(row.get("Type") != "bind" for row in self.mounts) or tuple(row.get("RW") for row in self.mounts) != (False, False, False, False, True):
            raise ValueError("policy mount modes")
        if not isinstance(self.mounts[1].get("Source"), str) or not self.mounts[1]["Source"]:
            raise ValueError("policy trusted bootstrap mount")

    @classmethod
    def from_signed_config(cls, value: Any) -> "EvidencePolicy":
        required = {"run_id", "attempt_id", "sequence", "reviewer_key", "scope", "interpreter", "outer_argv", "executor_argv", "docker_argv", "environment", "container_environment", "mounts", "sources", "binaries", "container_entrypoint", "container_cmd"}
        if not isinstance(value, dict) or set(value) != required:
            raise ValueError("policy keys")
        if value["scope"] != AUTHORIZATION_SCOPE:
            raise ValueError("policy scope/interpreter")
        arrays = ("outer_argv", "executor_argv", "docker_argv")
        if any(not isinstance(value[key], list) or not all(isinstance(item, str) for item in value[key]) for key in arrays):
            raise ValueError("policy argv")
        if not isinstance(value["environment"], dict) or set(value["environment"]) - set(HOST_ENVIRONMENT_KEYS):
            raise ValueError("policy environment")
        if not isinstance(value["container_environment"], dict) or set(value["container_environment"]) - set(CONTAINER_ENVIRONMENT_KEYS):
            raise ValueError("policy container environment")
        if any(key in FORBIDDEN_PYTHON_KEYS for key in value["environment"]):
            raise ValueError("policy environment")
        for command in (value["outer_argv"], value["executor_argv"]):
            if len(command) < 5 or tuple(command[1:4]) != PYTHON_FLAGS or not command[0] or not command[4]:
                raise ValueError("policy isolated argv")
        if not value["docker_argv"] or not (":" in value["docker_argv"][0] or value["docker_argv"][0].startswith("/")):
            raise ValueError("policy docker executable")
        if not isinstance(value["mounts"], list) or not all(isinstance(item, dict) for item in value["mounts"]):
            raise ValueError("policy mounts")
        if any(not isinstance(value[key], list) or not all(isinstance(item, str) for item in value[key]) for key in ("container_entrypoint", "container_cmd")):
            raise ValueError("policy container command")
        if not all(isinstance(value[key], dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in value[key].items()) for key in ("sources", "binaries")):
            raise ValueError("policy identities")
        return cls(value["run_id"], value["attempt_id"], value["sequence"], value["reviewer_key"], value["scope"], value["interpreter"], tuple(value["outer_argv"]), tuple(value["executor_argv"]), tuple(value["docker_argv"]), dict(value["environment"]), tuple(dict(item) for item in value["mounts"]), dict(value["sources"]), dict(value["binaries"]), dict(value["container_environment"]), tuple(value["container_entrypoint"]), tuple(value["container_cmd"]))


def _absolute(value: object) -> bool:
    return isinstance(value, str) and (value.startswith("/") or (len(value) > 2 and value[1] == ":" and value[2] in "/\\"))


def _hash(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)

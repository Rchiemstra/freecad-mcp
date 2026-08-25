"""Offline Docker launch/inspect contract; no daemon interaction occurs here."""
from __future__ import annotations

from .validation import ValidationResult
from .bindings import ContainerExecutionBinding
import hashlib
import json

TMPFS_LITERAL = "/tmp:rw,nosuid,nodev,size=2g"
TMPFS_INSPECT = "rw,nosuid,nodev,size=2g"


def validate_tmpfs(launch: list[str], inspect: dict[str, object], kernel_mount: str) -> ValidationResult:
    positions = [index for index, value in enumerate(launch) if value == "--tmpfs"]
    if len(positions) != 1 or positions[0] + 1 >= len(launch) or launch[positions[0] + 1] != TMPFS_LITERAL:
        return ValidationResult.fail("docker", "TMPFS_LAUNCH", "docker-argv", "/--tmpfs")
    host = inspect.get("HostConfig")
    if not isinstance(host, dict) or host.get("Tmpfs") != {"/tmp": TMPFS_INSPECT}:
        return ValidationResult.fail("docker", "TMPFS_INSPECT", "inspect", "/HostConfig/Tmpfs")
    if kernel_mount != TMPFS_INSPECT:
        return ValidationResult.fail("docker", "TMPFS_KERNEL", "kernel-mount", "/tmp")
    return ValidationResult.ok()


def validate_diagnostic_mounts(mounts: object, expected_source: str) -> ValidationResult:
    if not isinstance(mounts, list):
        return ValidationResult.fail("mount", "DIAGNOSTIC_MOUNT_SCHEMA", "inspect", "/Mounts")
    rows = [(index, item) for index, item in enumerate(mounts) if isinstance(item, dict) and item.get("Destination") == "/diagnostic"]
    if not rows:
        return ValidationResult.fail("mount", "DIAGNOSTIC_MOUNT_MISSING", "inspect", "/Mounts")
    if len(rows) != 1:
        return ValidationResult.fail("mount", "DIAGNOSTIC_MOUNT_UNIQUENESS", "inspect", "/Mounts")
    index, mount = rows[0]
    if mount.get("Type") != "bind":
        return ValidationResult.fail("mount", "DIAGNOSTIC_MOUNT_TYPE", "inspect", "/Mounts/%d/Type" % index)
    if mount.get("RW") is not False:
        return ValidationResult.fail("mount", "DIAGNOSTIC_MOUNT_MODE", "inspect", "/Mounts/%d/RW" % index)
    if mount.get("Source") != expected_source:
        return ValidationResult.fail("mount", "DIAGNOSTIC_MOUNT_SOURCE", "inspect", "/Mounts/%d/Source" % index)
    return ValidationResult.ok()


def validate_diagnostic_contract(launch: list[str], mounts: object, expected_source: str, expected_mounts: tuple[dict[str, object], ...]) -> ValidationResult:
    """Bind the exact create argv to the independently inspected mount row."""
    rows: list[str] = []
    for index, argument in enumerate(launch[:-1]):
        if argument == "--mount":
            rows.append(launch[index + 1])
    diagnostic = [row for row in rows if "dst=/diagnostic" in row or "destination=/diagnostic" in row]
    if not diagnostic:
        return ValidationResult.fail("mount", "DIAGNOSTIC_MOUNT_LAUNCH_MISSING", "docker-argv", "/--mount")
    if len(diagnostic) != 1:
        return ValidationResult.fail("mount", "DIAGNOSTIC_MOUNT_LAUNCH_UNIQUENESS", "docker-argv", "/--mount")
    expected = f"type=bind,src={expected_source},dst=/diagnostic,readonly"
    if diagnostic[0] != expected:
        return ValidationResult.fail("mount", "DIAGNOSTIC_MOUNT_LAUNCH_CONTRACT", "docker-argv", "/--mount")
    expected_launch = [
        f"type=bind,src={row['Source']},dst={row['Destination']}" + ("" if row["RW"] else ",readonly")
        for row in expected_mounts
    ]
    if rows != expected_launch:
        return ValidationResult.fail("mount", "MOUNT_LAUNCH_SET_CONTRACT", "docker-argv", "/--mount")
    if not isinstance(mounts, list):
        return ValidationResult.fail("mount", "MOUNT_SET_SCHEMA", "inspect", "/Mounts")
    fields = ("Type", "Source", "Destination", "RW")
    normalized = [{field: row.get(field) for field in fields} for row in mounts if isinstance(row, dict)]
    wanted = [{field: row.get(field) for field in fields} for row in expected_mounts]
    if normalized != wanted:
        return ValidationResult.fail("mount", "MOUNT_SET_CONTRACT", "inspect", "/Mounts")
    return validate_diagnostic_mounts(mounts, expected_source)


def validate_container_environment(actual: object, expected: dict[str, str]) -> ValidationResult:
    if not isinstance(actual, list) or not all(isinstance(row, str) and "=" in row for row in actual):
        return ValidationResult.fail("environment", "CONTAINER_ENVIRONMENT_CONTRACT", "inspect", "/Config/Env")
    parsed: dict[str, str] = {}
    for row in actual:
        key, value = row.split("=", 1)
        if not key or key in parsed:
            return ValidationResult.fail("environment", "CONTAINER_ENVIRONMENT_CONTRACT", "inspect", "/Config/Env")
        parsed[key] = value
    if parsed != expected:
        return ValidationResult.fail("environment", "CONTAINER_ENVIRONMENT_CONTRACT", "inspect", "/Config/Env")
    return ValidationResult.ok()


def validate_execution_contract(
    launch: object,
    inspect: object,
    kernel_tmpfs: object,
    image: str,
    entrypoint: tuple[str, ...],
    command: tuple[str, ...],
    environment: dict[str, str],
    mounts: tuple[dict[str, object], ...],
    expected_launch: tuple[str, ...],
    container_binding: ContainerExecutionBinding,
) -> ValidationResult:
    """Validate the frozen offline Docker record before a production PASS.

    This intentionally consumes records supplied by the executor; it never
    invokes Docker or reads a daemon.  The launch, inspect, and kernel record
    must agree on the complete pinned container contract.
    """
    if not isinstance(launch, list) or not all(isinstance(item, str) for item in launch):
        return ValidationResult.fail("docker", "DOCKER_LAUNCH_SCHEMA", "docker-argv", "/")
    if not launch or launch[-1] != image:
        return ValidationResult.fail("docker", "DOCKER_IMAGE", "docker-argv", "/image")
    tmpfs = validate_tmpfs(launch, inspect if isinstance(inspect, dict) else {}, kernel_tmpfs if isinstance(kernel_tmpfs, str) else "")
    if not tmpfs.passed:
        return tmpfs
    if launch != list(expected_launch):
        return ValidationResult.fail("docker", "DOCKER_LAUNCH_CONTRACT", "docker-argv", "/")
    if not isinstance(inspect, dict):
        return ValidationResult.fail("docker", "DOCKER_INSPECT_SCHEMA", "inspect", "/")
    raw = inspect.get("_raw_bytes")
    if not isinstance(raw, str):
        return ValidationResult.fail("docker", "DOCKER_RAW_INSPECT", "inspect", "/raw")
    try:
        parsed_raw = json.loads(raw)
    except json.JSONDecodeError:
        return ValidationResult.fail("docker", "DOCKER_RAW_INSPECT", "inspect", "/raw")
    if parsed_raw != {key: value for key, value in inspect.items() if key != "_raw_bytes"}:
        return ValidationResult.fail("docker", "DOCKER_RAW_INSPECT", "inspect", "/raw")
    if hashlib.sha256(raw.encode("utf-8")).hexdigest() != container_binding.raw_inspect_sha256:
        return ValidationResult.fail("docker", "DOCKER_INSPECT_HASH", "inspect", "/raw")
    if inspect.get("Id") != container_binding.container_id:
        return ValidationResult.fail("docker", "DOCKER_CONTAINER_ID", "inspect", "/Id")
    config = inspect.get("Config")
    host = inspect.get("HostConfig")
    if not isinstance(config, dict) or not isinstance(host, dict):
        return ValidationResult.fail("docker", "DOCKER_INSPECT_SCHEMA", "inspect", "/")
    if config.get("Image") != image:
        return ValidationResult.fail("docker", "DOCKER_IMAGE", "inspect", "/Config/Image")
    if config.get("Entrypoint") != list(entrypoint):
        return ValidationResult.fail("docker", "DOCKER_ENTRYPOINT", "inspect", "/Config/Entrypoint")
    if config.get("Cmd") != list(command):
        return ValidationResult.fail("docker", "DOCKER_CMD", "inspect", "/Config/Cmd")
    if host.get("NetworkMode") != "none":
        return ValidationResult.fail("docker", "DOCKER_NETWORK", "inspect", "/HostConfig/NetworkMode")
    if host.get("ReadonlyRootfs") is not True:
        return ValidationResult.fail("docker", "DOCKER_READONLY_ROOT", "inspect", "/HostConfig/ReadonlyRootfs")
    env = validate_container_environment(config.get("Env"), environment)
    if not env.passed:
        return env
    mounts_result = validate_diagnostic_contract(launch, inspect.get("Mounts"), str(mounts[0].get("Source", "")) if mounts else "", mounts)
    if not mounts_result.passed:
        return mounts_result
    return ValidationResult.ok()

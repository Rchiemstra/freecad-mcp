from __future__ import annotations

from .policy import CONTAINER_ENVIRONMENT_KEYS, HOST_ENVIRONMENT_KEYS


def sanitized_host_environment(source: dict[str, str]) -> dict[str, str]:
    """Copy only declared host inputs; absent values are not invented."""
    return {key: source[key] for key in HOST_ENVIRONMENT_KEYS if isinstance(source.get(key), str) and source[key]}


def sanitized_container_environment(source: dict[str, str]) -> dict[str, str]:
    """Copy only the exact declared container inputs before creation."""
    return {key: source[key] for key in CONTAINER_ENVIRONMENT_KEYS if isinstance(source.get(key), str) and source[key]}

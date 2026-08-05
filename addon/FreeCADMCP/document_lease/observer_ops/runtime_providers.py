"""Runtime service discovery and headless-safe notification queueing."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ._log import logger
from .events import ServiceProvider

_bound_service_provider: ServiceProvider | None = None
_bound_agent_mutation_checker: Callable[[str], bool] | None = None
_bound_snapshot_save_checker: Callable[[Any, Any], bool] | None = None


def bind_default_service_provider(provider: ServiceProvider) -> None:
    """Install the explicit process-lifetime lease-service collaborator."""

    global _bound_service_provider
    if not callable(provider):
        raise TypeError("service provider must be callable")
    _bound_service_provider = provider


def bind_legacy_attribution(
    *,
    agent_mutation_checker: Callable[[str], bool],
    snapshot_save_checker: Callable[[Any, Any], bool],
) -> None:
    """Inject the two temporary Phase-18 document-lock attribution bridges."""

    if not callable(agent_mutation_checker) or not callable(snapshot_save_checker):
        raise TypeError("legacy attribution collaborators must be callable")
    global _bound_agent_mutation_checker
    global _bound_snapshot_save_checker
    _bound_agent_mutation_checker = agent_mutation_checker
    _bound_snapshot_save_checker = snapshot_save_checker


def default_service_provider() -> Any | None:
    """Return the explicitly bound service without locating the RPC module."""

    return _bound_service_provider() if _bound_service_provider is not None else None


def get_runtime_service(provider: ServiceProvider | None = None) -> Any | None:
    """Return the current lease service, or ``None`` when RPC is not running."""

    try:
        selected = provider or _bound_service_provider
        return selected() if selected is not None else None
    except Exception:
        logger.debug("lease service provider failed", exc_info=True)
        return None


def default_agent_mutation_checker(key: str) -> bool:
    """Delegate attribution to the legacy request-scoped mutation context."""

    checker = _bound_agent_mutation_checker
    if not callable(checker):
        return False
    try:
        return bool(checker(key))
    except Exception:
        logger.debug("agent mutation attribution failed for %r", key, exc_info=True)
        return False


def is_internal_snapshot_save(document: Any, filename: Any) -> bool:
    """Recognize only the exact synchronous save callback of worker saveCopy."""

    checker = _bound_snapshot_save_checker
    if not callable(checker):
        return False
    try:
        return bool(checker(document, filename))
    except Exception:
        logger.debug("internal snapshot save attribution failed", exc_info=True)
        return False


def default_selected_document_provider() -> Any | None:
    return None


def qt_or_direct_queue(callback: Callable[[], None]) -> None:
    """Queue through Qt when available, with a headless-safe fallback."""

    callback()

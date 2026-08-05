"""Share document_lock_ops module identity across flat and package imports."""

from __future__ import annotations

import sys

_CANONICAL_PREFIX = "addon.FreeCADMCP.document_lock_ops"
_FLAT_PREFIX = "document_lock_ops"


def _paired_names(qualified: str) -> tuple[str, str]:
    if qualified == _CANONICAL_PREFIX or qualified.startswith(f"{_CANONICAL_PREFIX}."):
        suffix = qualified[len(_CANONICAL_PREFIX) :]
        return qualified, f"{_FLAT_PREFIX}{suffix}"
    if qualified == _FLAT_PREFIX or qualified.startswith(f"{_FLAT_PREFIX}."):
        suffix = qualified[len(_FLAT_PREFIX) :]
        return f"{_CANONICAL_PREFIX}{suffix}", qualified
    return qualified, qualified


def _publish_aliases(qualified: str, aliases: tuple[str, ...]) -> None:
    current = sys.modules.get(qualified)
    if current is None:
        return
    owner = next(
        (
            module
            for name in aliases
            if (module := sys.modules.get(name)) is not None and module is not current
        ),
        current,
    )
    for alias in aliases:
        sys.modules[alias] = owner


def install_facade_aliases(qualified: str, aliases: tuple[str, ...]) -> None:
    """Publish a compatibility facade under all of its static import names."""

    _publish_aliases(qualified, aliases)


def install_module_aliases(qualified: str) -> None:
    """Publish one module object under both compatibility import trees."""

    canonical, flat = _paired_names(qualified)
    _publish_aliases(qualified, (canonical, flat))


def install_package_aliases() -> None:
    """Publish the package object under both compatibility import trees."""

    install_module_aliases(_CANONICAL_PREFIX)
    install_module_aliases(_FLAT_PREFIX)


def install_loaded_module_aliases() -> None:
    """Alias already-loaded implementation modules after facade composition."""

    for qualified in list(sys.modules):
        if qualified.startswith((f"{_CANONICAL_PREFIX}.", f"{_FLAT_PREFIX}.")):
            install_module_aliases(qualified)

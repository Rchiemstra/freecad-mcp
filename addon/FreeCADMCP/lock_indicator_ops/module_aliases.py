"""Share lock_indicator_ops module identity across flat and package imports."""

from __future__ import annotations

import sys

_CANONICAL_PREFIX = "addon.FreeCADMCP.lock_indicator_ops"
_FLAT_PREFIX = "lock_indicator_ops"


def _paired_names(qualified: str) -> tuple[str, str]:
    if qualified == _CANONICAL_PREFIX or qualified.startswith(f"{_CANONICAL_PREFIX}."):
        suffix = qualified[len(_CANONICAL_PREFIX) :]
        return qualified, f"{_FLAT_PREFIX}{suffix}"
    if qualified == _FLAT_PREFIX or qualified.startswith(f"{_FLAT_PREFIX}."):
        suffix = qualified[len(_FLAT_PREFIX) :]
        return f"{_CANONICAL_PREFIX}{suffix}", qualified
    return qualified, qualified


def install_module_aliases(qualified: str) -> None:
    """Publish one module object under both import trees."""
    current = sys.modules.get(qualified)
    if current is None:
        return
    canonical, flat = _paired_names(qualified)
    owner = next(
        (
            module
            for name in (canonical, flat)
            if (module := sys.modules.get(name)) is not None and module is not current
        ),
        current,
    )
    sys.modules[canonical] = owner
    sys.modules[flat] = owner


def install_package_aliases() -> None:
    install_module_aliases(_CANONICAL_PREFIX)
    install_module_aliases(_FLAT_PREFIX)

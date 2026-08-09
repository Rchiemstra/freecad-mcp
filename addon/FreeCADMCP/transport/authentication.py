"""Transport-facing identities for the canonical authentication protocol."""

try:
    from .._shared.protocol.manifest import make_runtime_manifest
    from .._shared.protocol.profile_secret import load_profile_secret
    from .._shared.protocol.session_manager import SessionManager
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from _shared.protocol.manifest import make_runtime_manifest
    from _shared.protocol.profile_secret import load_profile_secret
    from _shared.protocol.session_manager import SessionManager

__all__ = ["SessionManager", "load_profile_secret", "make_runtime_manifest"]

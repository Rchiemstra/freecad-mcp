"""Compatibility imports for canonical protocol redaction."""

try:
    from ..._shared.protocol.redaction import _key_is_sensitive, redact_sensitive
except ImportError:
    from _shared.protocol.redaction import _key_is_sensitive, redact_sensitive

__all__ = ["_key_is_sensitive", "redact_sensitive"]

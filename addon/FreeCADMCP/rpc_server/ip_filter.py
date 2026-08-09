"""Compatibility imports for the canonical bounded JSON-RPC server."""

from .filtered_xmlrpc_server import (
    FilteredXMLRPCServer,
    validate_allowed_ips,
)
from .filtered_xmlrpc_server import (
    _parse_allowed_ips as _parse_allowed_ips,
)

__all__ = ["FilteredXMLRPCServer", "validate_allowed_ips"]

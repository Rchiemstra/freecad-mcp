"""IP allow-list validation for transport listeners."""

from __future__ import annotations

import ipaddress
import logging
import re

__all__ = ["validate_allowed_ips"]

_logger = logging.getLogger("FreeCADMCP.rpc_server")
_COMMA_SEP_RE = re.compile(r"^\s*[^,\s]+(\s*,\s*[^,\s]+)*\s*$")


def validate_allowed_ips(allowed_ips_str: str) -> tuple[list[str], list[str]]:
    """Validate comma-separated IP addresses and subnets."""

    errors: list[str] = []
    if not allowed_ips_str or not allowed_ips_str.strip():
        return [], ["Input must not be empty."]
    if not _COMMA_SEP_RE.match(allowed_ips_str):
        return [], [(
            "Malformed list — check for leading/trailing commas, "
            "double commas, or missing separators."
        )]

    valid: list[str] = []
    for value in allowed_ips_str.split(","):
        entry = value.strip()
        try:
            ipaddress.ip_network(entry, strict=False)
            valid.append(entry)
        except ValueError:
            errors.append(f"Invalid IP/subnet: '{entry}'")
    return valid, errors


def _parse_allowed_ips(
    allowed_ips_str: str,
) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Parse an allow-list into standard-library network objects."""

    valid, errors = validate_allowed_ips(allowed_ips_str)
    for message in errors:
        _logger.warning("MCP RPC: %s, skipping", message)
    return [ipaddress.ip_network(entry, strict=False) for entry in valid]

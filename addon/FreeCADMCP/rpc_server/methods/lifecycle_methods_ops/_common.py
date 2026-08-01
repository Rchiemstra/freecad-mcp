"""Shared runtime access for dispatch helper modules."""

import logging

logger = logging.getLogger("FreeCADMCP.rpc_server")


def _rpc_mod():
    from ... import rpc_server as rpc_mod

    return rpc_mod


__all__ = ["_rpc_mod", "logger"]



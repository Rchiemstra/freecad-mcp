"""Shared runtime access for GUI / view RPC method modules."""

from __future__ import annotations


def _rpc_mod():
    from ... import rpc_server as rpc_mod

    return rpc_mod


__all__ = ["_rpc_mod"]

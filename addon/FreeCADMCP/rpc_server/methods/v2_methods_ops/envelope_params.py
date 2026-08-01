"""Envelope parameter binding for legacy positional RPC methods."""

from __future__ import annotations

import inspect

from ...lease_protocol import LeaseProtocolError


def ordered_envelope_params(method, params):
    """Bind named envelope params to the legacy positional RPC methods."""
    signature = inspect.signature(method)
    bound = signature.bind(**dict(params))
    bound.apply_defaults()
    ordered = []
    for parameter in signature.parameters.values():
        if parameter.name == "self":
            continue
        if parameter.kind in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        }:
            ordered.append(bound.arguments[parameter.name])
        elif parameter.kind == inspect.Parameter.VAR_POSITIONAL:
            ordered.extend(bound.arguments.get(parameter.name, ()))
        elif parameter.kind == inspect.Parameter.KEYWORD_ONLY:
            raise LeaseProtocolError(
                "INVALID_METHOD_PARAMS",
                "Authenticated RPC target has unsupported keyword-only parameters",
            )
        elif (
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            and bound.arguments.get(parameter.name)
        ):
            raise LeaseProtocolError(
                "INVALID_METHOD_PARAMS",
                "Authenticated RPC target does not accept arbitrary fields",
            )
    return tuple(ordered)

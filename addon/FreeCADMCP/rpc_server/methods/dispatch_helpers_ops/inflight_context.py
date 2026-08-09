from __future__ import annotations

# ruff: noqa: F403
from ._support import *

"""Inflight request context helpers."""

def current_inflight(self):
    return getattr(self._inflight_context, "value", None)


def request_checkpoint(self, phase):
    inflight = self._current_inflight()
    if inflight is None:
        return None
    return inflight.token.checkpoint(phase)

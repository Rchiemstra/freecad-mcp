"""Compatibility import for the retired LeaseClientManager initializer."""

from .lease_client_manager import _compat_init_manager as init_manager

__all__ = ("init_manager",)

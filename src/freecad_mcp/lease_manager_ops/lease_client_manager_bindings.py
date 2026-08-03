"""Compatibility import for the retired LeaseClientManager binder."""

from .lease_client_manager import bind_lease_client_manager

__all__ = ("bind_lease_client_manager",)

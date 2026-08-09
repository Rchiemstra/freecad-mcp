"""Snapshot restore safety errors."""


class SnapshotRestoreError(RuntimeError):
    """A lease-preserving restore could not be proven safe."""

    code = "LEASE_SNAPSHOT_RESTORE_FAILED"

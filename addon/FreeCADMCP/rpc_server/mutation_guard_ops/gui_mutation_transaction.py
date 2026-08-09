"""GUI-thread document transaction open/commit/abort helper."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..telemetry import emit as emit_telemetry
from .object_helpers import object_name
from .rollback_coverage import RollbackCoverage


class GuiMutationTransaction:
    """Open/commit or abort one named transaction on each declared document."""

    def __init__(self, documents: Iterable[Any], name: str, *, enabled: bool):
        self.documents = tuple(documents)
        self.name = str(name)[:128] or "MCP mutation"
        self.enabled = bool(enabled)
        self._opened: list[Any] = []
        self.started = False
        self.committed = False
        self.abort_attempted = False
        self.abort_succeeded: bool | None = None
        self.abort_errors: list[dict[str, str]] = []
        self._original_undo_modes: list[tuple[Any, Any]] = []

    def _ensure_undo_enabled(self, document: Any) -> None:
        """Enable FreeCAD transaction recording when a headless doc disabled it."""

        try:
            mode = document.UndoMode
        except (AttributeError, RuntimeError):
            # Test doubles and some legacy proxies expose transaction methods
            # without an UndoMode property.
            return
        try:
            disabled = int(mode) == 0
        except (TypeError, ValueError):
            disabled = mode is False
        if not disabled:
            return
        try:
            document.UndoMode = 1
        except Exception as exc:
            raise RuntimeError(
                f"cannot enable transaction recording for "
                f"{object_name(document) or '<document>'}: {exc}"
            ) from exc
        self._original_undo_modes.append((document, mode))

    def _restore_undo_modes(self) -> None:
        while self._original_undo_modes:
            document, mode = self._original_undo_modes.pop()
            try:
                document.UndoMode = mode
            except Exception as exc:
                self.abort_errors.append(
                    {
                        "document": object_name(document),
                        "error_type": type(exc).__name__,
                        "message": (
                            "could not restore document UndoMode: " + str(exc)
                        )[:1024],
                    }
                )

    def __enter__(self):
        if not self.enabled:
            return self
        try:
            for document in self.documents:
                self._ensure_undo_enabled(document)
                document.openTransaction(self.name)
                self._opened.append(document)
            self.started = bool(self._opened)
            emit_telemetry(
                "transaction",
                "transaction_started",
                payload={
                    "name": self.name,
                    "documents": [object_name(item) for item in self.documents],
                    "enabled": self.enabled,
                },
            )
        except Exception:
            self.abort()
            raise
        return self

    def commit(self) -> None:
        try:
            while self._opened:
                self._opened.pop(0).commitTransaction()
        finally:
            self._restore_undo_modes()
        if self.enabled and self.started:
            self.committed = True
            emit_telemetry(
                "transaction",
                "transaction_committed",
                payload={
                    "name": self.name,
                    "documents": [object_name(item) for item in self.documents],
                },
            )

    def abort(self) -> bool:
        if self.committed:
            return False
        self.abort_attempted = self.abort_attempted or bool(self._opened)
        while self._opened:
            document = self._opened.pop()
            try:
                document.abortTransaction()
            except Exception as exc:
                self.abort_errors.append(
                    {
                        "document": object_name(document),
                        "error_type": type(exc).__name__,
                        "message": str(exc)[:1024],
                    }
                )
        self._restore_undo_modes()
        if self.abort_attempted:
            self.abort_succeeded = not self.abort_errors
            emit_telemetry(
                "transaction",
                (
                    "transaction_aborted"
                    if self.abort_succeeded
                    else "transaction_rollback_failed"
                ),
                status="succeeded" if self.abort_succeeded else "degraded",
                error_code=(
                    None
                    if self.abort_succeeded
                    else "TRANSACTION_ROLLBACK_FAILED"
                ),
                payload={
                    "name": self.name,
                    "documents": [object_name(item) for item in self.documents],
                    "abort_errors": self.abort_errors,
                },
            )
        return bool(self.abort_succeeded)

    def to_dict(
        self,
        *,
        coverage: RollbackCoverage | str = RollbackCoverage.DOCUMENT_ONLY,
    ) -> dict[str, Any]:
        normalized_coverage = str(getattr(coverage, "value", coverage))
        if not self.enabled:
            status = "unavailable"
        elif self.committed:
            status = "committed"
        elif self.abort_attempted and self.abort_succeeded:
            status = "aborted"
        elif self.abort_attempted:
            status = "rollback_failed"
        elif self.started:
            status = "started"
        else:
            status = "not_started"
        return {
            "status": status,
            "enabled": self.enabled,
            "documents": [object_name(item) for item in self.documents],
            "started": self.started,
            "committed": self.committed,
            "abort_attempted": self.abort_attempted,
            "abort_succeeded": self.abort_succeeded,
            "abort_errors": list(self.abort_errors),
            "rollback_attempted": self.abort_attempted,
            "rollback_succeeded": self.abort_succeeded,
            "coverage": normalized_coverage,
        }

    def __exit__(self, exc_type, _exc, _traceback):
        if exc_type is not None:
            self.abort()
        elif self._opened:
            self.commit()
        return False

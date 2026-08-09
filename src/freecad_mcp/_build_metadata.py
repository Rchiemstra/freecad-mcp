"""Optional build-time metadata injected by CI or wheel packaging."""

from __future__ import annotations

GIT_COMMIT: str | None = None
GIT_DIRTY: bool | None = None
BUILD_TIMESTAMP: str | None = None
BUILD_ID: str | None = None

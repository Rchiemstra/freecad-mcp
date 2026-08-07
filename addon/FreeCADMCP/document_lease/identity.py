"""Stable live-document identities and cross-platform path comparison."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from typing import Any

# Moved types preserve the prior import surface.
from .identity_helpers.document_values import document_values as _document_values
from .identity_helpers.inspect import (
    inspect_registered_document as _inspect_registered_document,
)
from .identity_helpers.path_availability import (
    assert_path_available as _assert_path_available_impl,
)
from .identity_helpers.path_baseline import capture_file_baseline  # noqa: F401
from .identity_helpers.path_canonicalize import canonicalize_path  # noqa: F401
from .identity_helpers.path_file_identity import file_identity_for_path  # noqa: F401
from .identity_helpers.path_file_identity import (
    windows_file_identity as _windows_file_identity,  # noqa: F401
)
from .identity_helpers.path_open import (
    assert_open_path_available as _assert_open_path_available,
)
from .identity_helpers.path_preview import preview_path_update as _preview_path_update
from .identity_helpers.path_update import update_path as _update_path
from .identity_helpers.platform import platform_name as _platform_name
from .identity_helpers.rebind import rebind_document as _rebind_document
from .identity_helpers.refresh_saved import (
    refresh_saved_document as _refresh_saved_document,
)
from .identity_helpers.register import (
    _register as _register_impl,
)
from .identity_helpers.register import (
    register as _register_public,
)
from .identity_helpers.register import (
    register_document as _register_document,
)
from .identity_helpers.resolve import resolve as _resolve
from .identity_helpers.session_uuid import (
    registered_session_uuid as _registered_session_uuid,
)
from .identity_helpers.unregister import (
    list_identities as _list_identities,
)
from .identity_helpers.unregister import (
    unregister as _unregister,
)
from .identity_types.document_identity_error import DocumentIdentityError  # noqa: F401
from .identity_types.duplicate_document_error import DuplicateDocumentError  # noqa: F401
from .identity_types.entry import _Entry
from .identity_types.identity_mismatch_error import IdentityMismatchError  # noqa: F401
from .identity_types.unknown_document_error import UnknownDocumentError  # noqa: F401
from .types.document_identity import DocumentIdentity  # noqa: F401
from .types.document_selector import DocumentSelector  # noqa: F401
from .types.file_baseline import FileBaseline  # noqa: F401
from .types.file_identity import FileIdentity  # noqa: F401


class DocumentIdentityService:
    """Issue and resolve UUIDs for documents that are live in one addon runtime."""

    def __init__(
        self,
        *,
        platform: str | None = None,
        uuid_factory: Callable[[], uuid.UUID | str] = uuid.uuid4,
    ) -> None:
        self.platform = _platform_name(platform)
        self._uuid_factory = uuid_factory
        self._entries: dict[str, _Entry] = {}
        self._objects: dict[int, str] = {}
        self._names: dict[str, str] = {}
        self._paths: dict[str, str] = {}
        self._files: dict[tuple[Any, ...], str] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _document_values(document: Any) -> tuple[str, str | None]:
        return _document_values(document)

    register_document = _register_document
    registered_session_uuid = _registered_session_uuid
    refresh_saved_document = _refresh_saved_document
    inspect_registered_document = _inspect_registered_document
    preview_path_update = _preview_path_update
    assert_open_path_available = _assert_open_path_available
    register = _register_public
    _register = _register_impl
    _assert_path_available = _assert_path_available_impl
    update_path = _update_path
    rebind_document = _rebind_document
    resolve = _resolve
    unregister = _unregister
    list_identities = _list_identities

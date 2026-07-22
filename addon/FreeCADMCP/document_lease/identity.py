"""Stable live-document identities and cross-platform path comparison."""

from __future__ import annotations

import hashlib
import ntpath
import os
import posixpath
import threading
import uuid
from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping

from .model import (
    DocumentIdentity,
    DocumentSelector,
    FileBaseline,
    FileIdentity,
)


class DocumentIdentityError(ValueError):
    pass


class UnknownDocumentError(DocumentIdentityError):
    pass


class DuplicateDocumentError(DocumentIdentityError):
    pass


class IdentityMismatchError(DocumentIdentityError):
    pass


def _platform_name(platform: str | None = None) -> str:
    value = (platform or ("windows" if os.name == "nt" else "posix")).lower()
    return "windows" if value.startswith("win") or value == "nt" else "posix"


def canonicalize_path(
    path: str | os.PathLike[str], *, platform: str | None = None
) -> tuple[str, str]:
    """Return a display canonical path and stable comparison key.

    A non-native ``platform`` is supported to make path policy unit-testable on
    either host.  Native paths additionally pass through ``realpath`` so that
    ordinary symlink spellings converge.
    """

    raw = os.fspath(path)
    if not isinstance(raw, str) or not raw.strip():
        raise DocumentIdentityError("document path must be a non-empty string")
    target = _platform_name(platform)
    if target == "windows":
        canonical = ntpath.normpath(ntpath.abspath(raw))
        if os.name == "nt":
            canonical = os.path.realpath(canonical)
        comparison_key = ntpath.normcase(canonical).casefold()
        return canonical, comparison_key

    canonical = posixpath.normpath(posixpath.abspath(raw))
    if os.name != "nt":
        canonical = os.path.realpath(canonical)
    return canonical, canonical


def _windows_file_identity(path: str) -> FileIdentity | None:
    """Read volume/file-index identity using a handle, when running on Windows."""

    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("dwFileAttributes", wintypes.DWORD),
                ("ftCreationTime", wintypes.FILETIME),
                ("ftLastAccessTime", wintypes.FILETIME),
                ("ftLastWriteTime", wintypes.FILETIME),
                ("dwVolumeSerialNumber", wintypes.DWORD),
                ("nFileSizeHigh", wintypes.DWORD),
                ("nFileSizeLow", wintypes.DWORD),
                ("nNumberOfLinks", wintypes.DWORD),
                ("nFileIndexHigh", wintypes.DWORD),
                ("nFileIndexLow", wintypes.DWORD),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.restype = wintypes.HANDLE
        create_file.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        handle = create_file(
            path,
            0x80,  # FILE_READ_ATTRIBUTES
            0x1 | 0x2 | 0x4,  # FILE_SHARE_READ/WRITE/DELETE
            None,
            3,  # OPEN_EXISTING
            0x02000000,  # FILE_FLAG_BACKUP_SEMANTICS
            None,
        )
        invalid = wintypes.HANDLE(-1).value
        if handle == invalid:
            return None
        try:
            info = BY_HANDLE_FILE_INFORMATION()
            if not kernel32.GetFileInformationByHandle(handle, ctypes.byref(info)):
                return None
            file_index = (int(info.nFileIndexHigh) << 32) | int(info.nFileIndexLow)
            return FileIdentity(
                platform="windows",
                volume_serial=int(info.dwVolumeSerialNumber),
                file_index=file_index,
            )
        finally:
            kernel32.CloseHandle(handle)
    except (AttributeError, OSError, ValueError):
        return None


def file_identity_for_path(
    path: str | os.PathLike[str], *, platform: str | None = None
) -> FileIdentity | None:
    """Return a best-effort filesystem identity for an existing regular file."""

    canonical, _ = canonicalize_path(path, platform=platform)
    if not os.path.exists(canonical):
        return None
    target = _platform_name(platform)
    if target == "windows" and os.name == "nt":
        result = _windows_file_identity(canonical)
        if result is not None:
            return result
    try:
        stat_result = os.stat(canonical, follow_symlinks=True)
    except OSError:
        return None
    if target == "windows":
        # Python exposes stable st_dev/st_ino on current Windows versions.  Map
        # them onto the Windows wire shape when the Win32 handle path failed.
        return FileIdentity(
            platform="windows",
            volume_serial=int(stat_result.st_dev),
            file_index=int(stat_result.st_ino),
        )
    return FileIdentity(
        platform="posix",
        device=int(stat_result.st_dev),
        inode=int(stat_result.st_ino),
    )


def capture_file_baseline(
    path: str | os.PathLike[str],
    *,
    platform: str | None = None,
    chunk_size: int = 1024 * 1024,
) -> FileBaseline:
    """Hash an unchanged file, rejecting a concurrent writer."""

    canonical, _ = canonicalize_path(path, platform=platform)
    before = os.stat(canonical)
    digest = hashlib.sha256()
    with open(canonical, "rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    after = os.stat(canonical)
    before_key = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_key = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_key != after_key:
        raise DocumentIdentityError("document changed while its baseline was captured")
    return FileBaseline(
        mtime_ns=int(after.st_mtime_ns),
        size=int(after.st_size),
        sha256=digest.hexdigest(),
        file_identity=file_identity_for_path(canonical, platform=platform),
    )


@dataclass
class _Entry:
    identity: DocumentIdentity
    object_key: int | None
    aliases: set[str]


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
        name = getattr(document, "Name", None) or getattr(document, "Label", None)
        if not name:
            raise DocumentIdentityError("live document has no Name")
        path = getattr(document, "FileName", None) or None
        return str(name), str(path) if path else None

    def register_document(self, document: Any) -> DocumentIdentity:
        name, path = self._document_values(document)
        object_key = id(document)
        with self._lock:
            known = self._objects.get(object_key)
            if known:
                entry = self._entries[known]
                observed = self.inspect_registered_document(known, document)
                expected = entry.identity
                if (
                    observed.name != expected.name
                    or observed.comparison_key != expected.comparison_key
                    or observed.file_identity != expected.file_identity
                ):
                    raise IdentityMismatchError(
                        "live document identity changed outside an explicit "
                        "Save As, reload, or restore rebind"
                    )
                return entry.identity
            return self._register(name=name, path=path, object_key=object_key)

    def inspect_registered_document(
        self, session_uuid: str, document: Any
    ) -> DocumentIdentity:
        """Describe a registered live proxy without changing its identity maps.

        This is deliberately separate from :meth:`register_document`: safety
        preflights must observe an unexpected Save As/path replacement rather
        than silently accepting it as a new alias.
        """

        name, path = self._document_values(document)
        object_key = id(document)
        with self._lock:
            entry = self._entries.get(session_uuid)
            if entry is None:
                raise UnknownDocumentError(session_uuid)
            if entry.object_key is None or entry.object_key != object_key:
                raise IdentityMismatchError(
                    "the supplied object is not the registered live document proxy"
                )
            canonical: str | None = None
            comparison: str | None = None
            file_identity: FileIdentity | None = None
            if path:
                canonical, comparison = canonicalize_path(
                    path, platform=self.platform
                )
                file_identity = file_identity_for_path(
                    canonical, platform=self.platform
                )
            return DocumentIdentity(
                session_uuid=session_uuid,
                name=name,
                canonical_path=canonical,
                comparison_key=comparison,
                file_identity=file_identity,
            )

    def preview_path_update(
        self, session_uuid: str, path: str | os.PathLike[str]
    ) -> DocumentIdentity:
        """Validate and describe a path migration without publishing aliases."""

        canonical, comparison = canonicalize_path(path, platform=self.platform)
        file_identity = file_identity_for_path(canonical, platform=self.platform)
        with self._lock:
            entry = self._entries.get(session_uuid)
            if entry is None:
                raise UnknownDocumentError(session_uuid)
            self._assert_path_available(
                comparison, file_identity, except_uuid=session_uuid
            )
            return replace(
                entry.identity,
                canonical_path=canonical,
                comparison_key=comparison,
                file_identity=file_identity,
            )

    def assert_open_path_available(
        self, path: str | os.PathLike[str]
    ) -> tuple[str, str, FileIdentity | None]:
        """Reject a path/file identity already owned by a live document.

        Typed open calls use this before touching FreeCAD's application
        document list.  Registration still repeats the check after open to
        close the unavoidable filesystem-to-GUI race conservatively.
        """

        canonical, comparison = canonicalize_path(path, platform=self.platform)
        file_identity = file_identity_for_path(canonical, platform=self.platform)
        with self._lock:
            self._assert_path_available(comparison, file_identity)
        return canonical, comparison, file_identity

    def register(
        self, *, name: str, path: str | os.PathLike[str] | None = None
    ) -> DocumentIdentity:
        """Register a live logical document when no proxy object is available."""

        with self._lock:
            return self._register(name=name, path=path, object_key=None)

    def _register(
        self,
        *,
        name: str,
        path: str | os.PathLike[str] | None,
        object_key: int | None,
    ) -> DocumentIdentity:
        clean_name = str(name).strip()
        if not clean_name:
            raise DocumentIdentityError("document name must not be empty")
        if clean_name in self._names:
            raise DuplicateDocumentError(f"document name is already live: {clean_name}")
        canonical: str | None = None
        comparison: str | None = None
        file_identity: FileIdentity | None = None
        if path:
            canonical, comparison = canonicalize_path(path, platform=self.platform)
            file_identity = file_identity_for_path(canonical, platform=self.platform)
            self._assert_path_available(comparison, file_identity)
        session_uuid = str(self._uuid_factory())
        identity = DocumentIdentity(
            session_uuid=session_uuid,
            name=clean_name,
            canonical_path=canonical,
            comparison_key=comparison,
            file_identity=file_identity,
        )
        aliases = {comparison} if comparison else set()
        self._entries[session_uuid] = _Entry(identity, object_key, aliases)
        self._names[clean_name] = session_uuid
        if object_key is not None:
            self._objects[object_key] = session_uuid
        if comparison:
            self._paths[comparison] = session_uuid
        if file_identity:
            self._files[file_identity.comparison_tuple()] = session_uuid
        return identity

    def _assert_path_available(
        self,
        comparison: str,
        file_identity: FileIdentity | None,
        *,
        except_uuid: str | None = None,
    ) -> None:
        path_owner = self._paths.get(comparison)
        if path_owner and path_owner != except_uuid:
            raise DuplicateDocumentError(
                f"another live document already uses path {comparison}"
            )
        if file_identity:
            file_owner = self._files.get(file_identity.comparison_tuple())
            if file_owner and file_owner != except_uuid:
                raise DuplicateDocumentError(
                    "another live document already uses the same filesystem file"
                )

    def update_path(
        self, session_uuid: str, path: str | os.PathLike[str]
    ) -> DocumentIdentity:
        """Rebind Save As while preserving the addon-issued session UUID."""

        canonical, comparison = canonicalize_path(path, platform=self.platform)
        file_identity = file_identity_for_path(canonical, platform=self.platform)
        with self._lock:
            entry = self._entries.get(session_uuid)
            if entry is None:
                raise UnknownDocumentError(session_uuid)
            self._assert_path_available(
                comparison, file_identity, except_uuid=session_uuid
            )
            entry.aliases.add(comparison)
            self._paths[comparison] = session_uuid
            if file_identity:
                self._files[file_identity.comparison_tuple()] = session_uuid
            entry.identity = replace(
                entry.identity,
                canonical_path=canonical,
                comparison_key=comparison,
                file_identity=file_identity,
            )
            return entry.identity

    def rebind_document(self, session_uuid: str, document: Any) -> DocumentIdentity:
        """Attach a replacement proxy after a lease-preserving reload/restore."""

        name, path = self._document_values(document)
        object_key = id(document)
        with self._lock:
            entry = self._entries.get(session_uuid)
            if entry is None:
                raise UnknownDocumentError(session_uuid)
            other = self._objects.get(object_key)
            if other and other != session_uuid:
                raise DuplicateDocumentError("replacement proxy is already registered")
            existing_name = self._names.get(name)
            if existing_name and existing_name != session_uuid:
                raise DuplicateDocumentError(name)
            # Validate the replacement path before changing object/name indexes,
            # so a duplicate path cannot leave a partially rebound entry.
            if path:
                _, comparison = canonicalize_path(path, platform=self.platform)
                file_identity = file_identity_for_path(path, platform=self.platform)
                self._assert_path_available(
                    comparison, file_identity, except_uuid=session_uuid
                )
            if entry.object_key is not None:
                self._objects.pop(entry.object_key, None)
            if name != entry.identity.name:
                self._names.pop(entry.identity.name, None)
                self._names[name] = session_uuid
                entry.identity = replace(entry.identity, name=name)
            entry.object_key = object_key
            self._objects[object_key] = session_uuid
            if path:
                return self.update_path(session_uuid, path)
            return entry.identity

    def resolve(
        self, selector: DocumentSelector | Mapping[str, Any] | str
    ) -> DocumentIdentity:
        """Resolve every supplied selector assertion to the same live entry."""

        if isinstance(selector, str):
            selector = DocumentSelector(document_session_uuid=selector)
        elif isinstance(selector, Mapping):
            selector = DocumentSelector(
                document_session_uuid=selector.get("document_session_uuid"),
                document_name=selector.get("document_name"),
                canonical_path=selector.get("canonical_path"),
            )
        candidates: list[str] = []
        with self._lock:
            if selector.document_session_uuid:
                if selector.document_session_uuid not in self._entries:
                    raise UnknownDocumentError(selector.document_session_uuid)
                candidates.append(selector.document_session_uuid)
            if selector.document_name:
                resolved = self._names.get(selector.document_name)
                if not resolved:
                    raise UnknownDocumentError(selector.document_name)
                candidates.append(resolved)
            if selector.canonical_path:
                _, comparison = canonicalize_path(
                    selector.canonical_path, platform=self.platform
                )
                resolved = self._paths.get(comparison)
                if not resolved:
                    raise UnknownDocumentError(selector.canonical_path)
                candidates.append(resolved)
            if not candidates:
                raise DocumentIdentityError("at least one document selector is required")
            if any(candidate != candidates[0] for candidate in candidates[1:]):
                raise IdentityMismatchError(
                    "document selector fields identify different live documents"
                )
            return self._entries[candidates[0]].identity

    def unregister(self, session_uuid: str) -> DocumentIdentity:
        with self._lock:
            entry = self._entries.pop(session_uuid, None)
            if entry is None:
                raise UnknownDocumentError(session_uuid)
            self._names.pop(entry.identity.name, None)
            if entry.object_key is not None:
                self._objects.pop(entry.object_key, None)
            for alias in entry.aliases:
                if self._paths.get(alias) == session_uuid:
                    self._paths.pop(alias, None)
            for key, owner in list(self._files.items()):
                if owner == session_uuid:
                    self._files.pop(key, None)
            return entry.identity

    def list_identities(self) -> list[DocumentIdentity]:
        with self._lock:
            return [entry.identity for entry in self._entries.values()]

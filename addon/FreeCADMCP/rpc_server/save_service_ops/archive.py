"""FCStd archive verification for save_service."""

from __future__ import annotations

import os
import zipfile

from ..save_types.archive_verification import (
    DEFAULT_REQUIRED_MEMBERS as _DEFAULT_REQUIRED_MEMBERS,
)
from ..save_types.archive_verification import ArchiveVerification
from ..save_types.fcstd_verification_error import FcstdVerificationError
from ..save_types.save_service_error import SaveServiceError

try:
    from document_lease.identity import canonicalize_path
except ImportError:
    from addon.FreeCADMCP.document_lease.identity import canonicalize_path

def verify_fcstd_archive(
    path: str | os.PathLike[str],
    *,
    required_members: tuple[str, ...] = _DEFAULT_REQUIRED_MEMBERS,
) -> ArchiveVerification:
    """Fully read an FCStd ZIP and require its core document member."""

    canonical, _ = canonicalize_path(path)
    try:
        with zipfile.ZipFile(canonical, "r") as archive:
            infos = archive.infolist()
            names = {item.filename for item in infos}
            missing = [name for name in required_members if name not in names]
            if missing:
                raise FcstdVerificationError(
                    "saved archive is missing required FCStd members",
                    stage="archive_verification",
                    path=canonical,
                    mutation_may_have_occurred=True,
                    details={"missing_members": missing},
                )
            corrupt_member = archive.testzip()
            if corrupt_member is not None:
                raise FcstdVerificationError(
                    "saved archive contains a corrupt member",
                    stage="archive_verification",
                    path=canonical,
                    mutation_may_have_occurred=True,
                    details={"corrupt_member": corrupt_member},
                )
            return ArchiveVerification(
                member_count=len(infos),
                uncompressed_size=sum(int(item.file_size) for item in infos),
                required_members=required_members,
            )
    except SaveServiceError:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise FcstdVerificationError(
            f"saved file is not a readable FCStd archive: {exc}",
            stage="archive_verification",
            path=canonical,
            mutation_may_have_occurred=True,
        ) from exc

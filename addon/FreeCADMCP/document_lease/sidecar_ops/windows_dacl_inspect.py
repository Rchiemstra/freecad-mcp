"""Inspect Windows DACLs without modifying them."""

from __future__ import annotations

import os
from pathlib import Path

from .windows_dacl_ace_verify import verify_dacl_aces
from .windows_dacl_apis import bind_windows_security_apis


def inspect_windows_owner_only(path: Path) -> tuple[bool, str]:
    """Inspect an NT security descriptor without modifying it.

    The writer installs ``D:P(A;;FA;;;SY)(A;;FA;;;OW)``.  A strict reader
    accepts only that effective structure on an object owned by the current
    process user: a protected DACL with exactly two non-inherited allow ACEs,
    both granting ``FILE_ALL_ACCESS``, to SYSTEM and OWNER RIGHTS.  Checking
    the ACEs directly avoids brittle SDDL string comparison and rejects extra
    allow/deny/object/inherited ACEs.
    """

    if os.name != "nt":
        return True, ""

    try:
        import ctypes
        from ctypes import wintypes

        from ..sidecar_winapi.access_allowed_ace import (
            AccessAllowedAce as _AccessAllowedAce,
        )
        from ..sidecar_winapi.acl_size_information import (
            AclSizeInformation as _AclSizeInformation,
        )

        apis = bind_windows_security_apis(ctypes, wintypes)
        owner, dacl, descriptor, token, expected_sids = _load_security_context(
            path, apis, wintypes
        )
        try:
            return _validate_security_context(
                apis,
                ctypes,
                wintypes,
                owner,
                dacl,
                descriptor,
                token,
                expected_sids,
                _AccessAllowedAce,
                _AclSizeInformation,
            )
        finally:
            _release_security_context(apis, expected_sids, token, descriptor)
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        return False, f"unable to inspect Windows DACL: {exc}"


def _load_security_context(
    path: Path,
    apis: dict[str, object],
    wintypes: object,
) -> tuple[object, object, object, object, list[object]]:
    import ctypes

    owner = wintypes.LPVOID()
    dacl = wintypes.LPVOID()
    descriptor = wintypes.LPVOID()
    security_result = apis["get_named_security"](
        str(path),
        1,  # SE_FILE_OBJECT
        0x00000001 | 0x00000004,  # OWNER + DACL_SECURITY_INFORMATION
        ctypes.byref(owner),
        None,
        ctypes.byref(dacl),
        None,
        ctypes.byref(descriptor),
    )
    if security_result != 0:
        raise ValueError(f"GetNamedSecurityInfoW failed with error {security_result}")

    token = wintypes.HANDLE()
    expected_sids: list[object] = []
    for sid_text in ("S-1-5-18", "S-1-3-4"):  # SYSTEM, OWNER RIGHTS
        sid = wintypes.LPVOID()
        if not apis["convert_sid"](sid_text, ctypes.byref(sid)):
            raise OSError(
                f"ConvertStringSidToSidW failed with Windows error {ctypes.get_last_error()}"
            )
        expected_sids.append(sid)
    return owner, dacl, descriptor, token, expected_sids


def _validate_security_context(
    apis: dict[str, object],
    ctypes: object,
    wintypes: object,
    owner: object,
    dacl: object,
    descriptor: object,
    token: object,
    expected_sids: list[object],
    access_allowed_ace: type[object],
    acl_size_information: type[object],
) -> tuple[bool, str]:
    if not owner.value:
        return False, "security descriptor has no owner SID"
    if not dacl.value:
        return False, "security descriptor has a null or absent DACL"

    control = ctypes.c_ushort()
    revision = wintypes.DWORD()
    if not apis["get_descriptor_control"](
        descriptor, ctypes.byref(control), ctypes.byref(revision)
    ):
        return False, (
            "GetSecurityDescriptorControl failed with Windows error "
            f"{ctypes.get_last_error()}"
        )
    if not control.value & 0x1000:  # SE_DACL_PROTECTED
        return False, "DACL is not protected from inheritance"

    owner_valid, owner_reason = _verify_process_owns_object(
        apis, ctypes, wintypes, owner, token
    )
    if not owner_valid:
        return False, owner_reason

    return verify_dacl_aces(
        apis,
        ctypes,
        wintypes,
        dacl,
        expected_sids,
        access_allowed_ace,
        acl_size_information,
    )


def _verify_process_owns_object(
    apis: dict[str, object],
    ctypes: object,
    wintypes: object,
    owner: object,
    token: object,
) -> tuple[bool, str]:
    if not apis["open_process_token"](
        apis["kernel32"].GetCurrentProcess(),
        0x0008,  # TOKEN_QUERY
        ctypes.byref(token),
    ):
        return False, (
            "OpenProcessToken failed with Windows error "
            f"{ctypes.get_last_error()}"
        )
    token_size = wintypes.DWORD()
    apis["get_token_information"](
        token,
        1,  # TokenUser
        None,
        0,
        ctypes.byref(token_size),
    )
    if token_size.value == 0:
        return False, (
            "GetTokenInformation sizing failed with Windows error "
            f"{ctypes.get_last_error()}"
        )
    token_buffer = ctypes.create_string_buffer(token_size.value)
    if not apis["get_token_information"](
        token,
        1,
        token_buffer,
        token_size,
        ctypes.byref(token_size),
    ):
        return False, (
            "GetTokenInformation failed with Windows error "
            f"{ctypes.get_last_error()}"
        )
    from ..sidecar_winapi.sid_and_attributes import SidAndAttributes as _SidAndAttributes

    token_user = ctypes.cast(
        token_buffer, ctypes.POINTER(_SidAndAttributes)
    ).contents
    if not token_user.Sid or not apis["equal_sid"](owner, token_user.Sid):
        return False, "object owner is not the current process user"
    return True, ""


def _release_security_context(
    apis: dict[str, object],
    expected_sids: list[object],
    token: object,
    descriptor: object,
) -> None:
    for sid in expected_sids:
        if sid.value:
            apis["kernel32"].LocalFree(sid)
    if token.value:
        apis["kernel32"].CloseHandle(token)
    if descriptor.value:
        apis["kernel32"].LocalFree(descriptor)

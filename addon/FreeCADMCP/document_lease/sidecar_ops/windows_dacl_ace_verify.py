"""Validate individual DACL ACE entries on Windows."""

from __future__ import annotations


def verify_dacl_aces(
    apis: dict[str, object],
    ctypes: object,
    wintypes: object,
    dacl: object,
    expected_sids: list[object],
    access_allowed_ace: type[object],
    acl_size_information: type[object],
) -> tuple[bool, str]:
    acl_info = acl_size_information()
    if not apis["get_acl_information"](
        dacl,
        ctypes.byref(acl_info),
        ctypes.sizeof(acl_info),
        2,  # AclSizeInformation
    ):
        return False, (
            "GetAclInformation failed with Windows error "
            f"{ctypes.get_last_error()}"
        )
    if acl_info.AceCount != 2:
        return False, f"DACL contains {acl_info.AceCount} ACEs instead of 2"

    seen = [False, False]
    sid_offset = access_allowed_ace.SidStart.offset
    minimum_ace_size = sid_offset + 8
    for index in range(acl_info.AceCount):
        ace_valid, ace_reason, matched_index = _verify_single_ace(
            apis,
            ctypes,
            wintypes,
            dacl,
            index,
            expected_sids,
            access_allowed_ace,
            sid_offset,
            minimum_ace_size,
        )
        if not ace_valid:
            return False, ace_reason
        if seen[matched_index]:
            return False, f"DACL ACE {index} duplicates a principal"
        seen[matched_index] = True
    if not all(seen):
        return False, "DACL is missing SYSTEM or OWNER RIGHTS"
    return True, ""


def _verify_single_ace(
    apis: dict[str, object],
    ctypes: object,
    wintypes: object,
    dacl: object,
    index: int,
    expected_sids: list[object],
    access_allowed_ace: type[object],
    sid_offset: int,
    minimum_ace_size: int,
) -> tuple[bool, str, int]:
    ace_pointer = wintypes.LPVOID()
    if not apis["get_ace"](dacl, index, ctypes.byref(ace_pointer)):
        return (
            False,
            f"GetAce({index}) failed with Windows error {ctypes.get_last_error()}",
            -1,
        )
    ace = ctypes.cast(
        ace_pointer, ctypes.POINTER(access_allowed_ace)
    ).contents
    if ace.Header.AceType != 0:  # ACCESS_ALLOWED_ACE_TYPE
        return False, f"DACL ACE {index} is not a simple allow ACE", -1
    if ace.Header.AceFlags != 0:
        return False, f"DACL ACE {index} has inheritance flags", -1
    if ace.Header.AceSize < minimum_ace_size:
        return False, f"DACL ACE {index} is truncated", -1
    if ace.Mask != 0x001F01FF:  # FILE_ALL_ACCESS
        return False, f"DACL ACE {index} does not grant exact full control", -1
    sid_pointer = wintypes.LPVOID(ace_pointer.value + sid_offset)
    if not apis["is_valid_sid"](sid_pointer):
        return False, f"DACL ACE {index} contains an invalid SID", -1
    if apis["get_length_sid"](sid_pointer) != ace.Header.AceSize - sid_offset:
        return False, f"DACL ACE {index} has inconsistent SID length", -1
    matches = [
        bool(apis["equal_sid"](sid_pointer, expected))
        for expected in expected_sids
    ]
    if matches.count(True) != 1:
        return False, f"DACL ACE {index} grants an unexpected principal", -1
    return True, "", matches.index(True)

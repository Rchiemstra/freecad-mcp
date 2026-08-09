"""Win32 security API bindings for DACL inspection."""

from __future__ import annotations


def bind_windows_security_apis(ctypes: object, wintypes: object) -> dict[str, object]:
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    get_named_security = advapi32.GetNamedSecurityInfoW
    get_named_security.argtypes = [
        wintypes.LPWSTR,
        ctypes.c_int,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.LPVOID),
    ]
    get_named_security.restype = wintypes.DWORD

    get_descriptor_control = advapi32.GetSecurityDescriptorControl
    get_descriptor_control.argtypes = [
        wintypes.LPVOID,
        ctypes.POINTER(ctypes.c_ushort),
        ctypes.POINTER(wintypes.DWORD),
    ]
    get_descriptor_control.restype = wintypes.BOOL

    get_acl_information = advapi32.GetAclInformation
    get_acl_information.argtypes = [
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.c_int,
    ]
    get_acl_information.restype = wintypes.BOOL

    get_ace = advapi32.GetAce
    get_ace.argtypes = [
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPVOID),
    ]
    get_ace.restype = wintypes.BOOL

    equal_sid = advapi32.EqualSid
    equal_sid.argtypes = [wintypes.LPVOID, wintypes.LPVOID]
    equal_sid.restype = wintypes.BOOL
    is_valid_sid = advapi32.IsValidSid
    is_valid_sid.argtypes = [wintypes.LPVOID]
    is_valid_sid.restype = wintypes.BOOL
    get_length_sid = advapi32.GetLengthSid
    get_length_sid.argtypes = [wintypes.LPVOID]
    get_length_sid.restype = wintypes.DWORD

    convert_sid = advapi32.ConvertStringSidToSidW
    convert_sid.argtypes = [
        wintypes.LPCWSTR,
        ctypes.POINTER(wintypes.LPVOID),
    ]
    convert_sid.restype = wintypes.BOOL

    open_process_token = advapi32.OpenProcessToken
    open_process_token.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    open_process_token.restype = wintypes.BOOL
    get_token_information = advapi32.GetTokenInformation
    get_token_information.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    get_token_information.restype = wintypes.BOOL

    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL

    return {
        "advapi32": advapi32,
        "kernel32": kernel32,
        "get_named_security": get_named_security,
        "get_descriptor_control": get_descriptor_control,
        "get_acl_information": get_acl_information,
        "get_ace": get_ace,
        "equal_sid": equal_sid,
        "is_valid_sid": is_valid_sid,
        "get_length_sid": get_length_sid,
        "convert_sid": convert_sid,
        "open_process_token": open_process_token,
        "get_token_information": get_token_information,
    }

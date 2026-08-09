"""OS boot evidence for process-lifetime lease identity."""

from __future__ import annotations

from typing import Any


def boot_identity(*, rpc_mod: Any) -> str:
    """Compatibility accessor for the one trusted process-lifetime boot ID."""

    return trusted_boot_identity(rpc_mod=rpc_mod)


def _linux_boot_id(*, rpc_mod: Any) -> str:
    try:
        value = (
            rpc_mod.Path("/proc/sys/kernel/random/boot_id")
            .read_text(encoding="ascii")
            .strip()
        )
        if value:
            return value
    except (OSError, UnicodeError):
        pass
    return ""


def _windows_boot_ticks(*, rpc_mod: Any) -> str:
    try:
        import ctypes

        # SystemTimeOfDayInformation is a fixed-size class: the kernel
        # returns STATUS_INFO_LENGTH_MISMATCH for anything but its exact
        # size (48 bytes on x64) rather than filling a larger buffer, so
        # an oversized allocation silently yields no boot evidence. Retry
        # once at the length the kernel reports back.
        status_info_length_mismatch = 0xC0000004
        returned = ctypes.c_ulong()
        for size in (48, None):
            if size is None:
                size = int(returned.value)
                if size <= 0:
                    break
            buffer = (ctypes.c_ubyte * size)()
            status = ctypes.windll.ntdll.NtQuerySystemInformation(
                3, buffer, ctypes.sizeof(buffer), ctypes.byref(returned)
            )
            if status == 0:
                boot_ticks = ctypes.c_int64.from_buffer(buffer).value
                if boot_ticks > 0:
                    return f"windows-boot:{boot_ticks:x}"
                break
            if (status & 0xFFFFFFFF) != status_info_length_mismatch:
                break
    except Exception:
        pass
    return ""


def _psutil_boot_time() -> str:
    try:
        import psutil

        boot_time = float(psutil.boot_time())
        if boot_time > 0:
            return f"boot-time:{boot_time:.6f}"
    except Exception:
        pass
    return ""


def trusted_boot_identity(*, rpc_mod: Any) -> str:
    """Return OS boot evidence, or empty text when it cannot be proven."""

    linux_boot = _linux_boot_id(rpc_mod=rpc_mod)
    if linux_boot:
        return linux_boot
    if rpc_mod.os.name == "nt":
        windows_boot = _windows_boot_ticks(rpc_mod=rpc_mod)
        if windows_boot:
            return windows_boot
    return _psutil_boot_time()

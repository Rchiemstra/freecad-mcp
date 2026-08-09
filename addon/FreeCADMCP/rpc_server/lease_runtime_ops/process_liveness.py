"""Process liveness probes for lease recovery evidence."""

from __future__ import annotations

from typing import Any

from .timestamps import utc_timestamp


def process_started_at(*, addon_loaded_at: str, rpc_mod: Any) -> str:
    """Return the current process start time without requiring psutil."""
    if rpc_mod.os.name == "nt":
        started = _windows_process_started_at(rpc_mod=rpc_mod)
        if started is not None:
            return started
    started = _linux_process_started_at(rpc_mod=rpc_mod)
    if started is not None:
        return started
    return addon_loaded_at


def _windows_process_started_at(*, rpc_mod: Any) -> str | None:
    try:
        import ctypes
        from ctypes import wintypes

        create = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        if ctypes.windll.kernel32.GetProcessTimes(
            handle,
            ctypes.byref(create),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            ticks = (int(create.dwHighDateTime) << 32) | int(create.dwLowDateTime)
            return utc_timestamp(ticks / 10_000_000 - 11_644_473_600)
    except Exception:
        pass
    return None


def _linux_process_started_at(*, rpc_mod: Any) -> str | None:
    try:
        stat_fields = rpc_mod.Path("/proc/self/stat").read_text(encoding="ascii").split()
        boot_seconds = float(
            next(
                line.split()[1]
                for line in rpc_mod.Path("/proc/stat")
                .read_text(encoding="ascii")
                .splitlines()
                if line.startswith("btime ")
            )
        )
        return utc_timestamp(
            boot_seconds
            + float(stat_fields[21]) / float(rpc_mod.os.sysconf("SC_CLK_TCK"))
        )
    except Exception:
        return None


def probe_process_liveness(pid: Any, *, rpc_mod: Any):
    """Return exact process-start evidence, never guessing through errors."""

    lease = rpc_mod._import_document_lease()
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return lease.ProcessLivenessEvidence(exists=None)
    if pid < 1:
        return lease.ProcessLivenessEvidence(exists=None)

    if rpc_mod.os.name == "nt":
        return _probe_windows_liveness(pid, lease, rpc_mod=rpc_mod)
    if rpc_mod.sys.platform.startswith("linux"):
        return _probe_linux_liveness(pid, lease, rpc_mod=rpc_mod)
    return _probe_psutil_liveness(pid, lease)


def _probe_windows_liveness(pid: int, lease: Any, *, rpc_mod: Any):
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            # ERROR_INVALID_PARAMETER is Windows' documented result for a
            # PID that does not identify a process. Access denial and all
            # other failures remain unknown.
            if ctypes.get_last_error() == 87:
                return lease.ProcessLivenessEvidence(exists=False)
            return lease.ProcessLivenessEvidence(exists=None)
        try:
            create = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel = wintypes.FILETIME()
            user = wintypes.FILETIME()
            if not kernel32.GetProcessTimes(
                handle,
                ctypes.byref(create),
                ctypes.byref(exit_time),
                ctypes.byref(kernel),
                ctypes.byref(user),
            ):
                return lease.ProcessLivenessEvidence(exists=None)
            ticks = (int(create.dwHighDateTime) << 32) | int(create.dwLowDateTime)
            return lease.ProcessLivenessEvidence(
                exists=True,
                process_started_at=utc_timestamp(
                    ticks / 10_000_000 - 11_644_473_600
                ),
            )
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return lease.ProcessLivenessEvidence(exists=None)


def _probe_linux_liveness(pid: int, lease: Any, *, rpc_mod: Any):
    try:
        raw = rpc_mod.Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
        fields = raw[raw.rfind(")") + 2 :].split()
        start_ticks = float(fields[19])
        boot_seconds = float(
            next(
                line.split()[1]
                for line in rpc_mod.Path("/proc/stat")
                .read_text(encoding="ascii")
                .splitlines()
                if line.startswith("btime ")
            )
        )
        return lease.ProcessLivenessEvidence(
            exists=True,
            process_started_at=utc_timestamp(
                boot_seconds
                + start_ticks / float(rpc_mod.os.sysconf("SC_CLK_TCK"))
            ),
        )
    except FileNotFoundError:
        try:
            rpc_mod.os.kill(pid, 0)
        except ProcessLookupError:
            return lease.ProcessLivenessEvidence(exists=False)
        except (PermissionError, OSError):
            return lease.ProcessLivenessEvidence(exists=None)
        return lease.ProcessLivenessEvidence(exists=None)
    except (OSError, UnicodeError, ValueError, IndexError, StopIteration):
        return lease.ProcessLivenessEvidence(exists=None)


def _probe_psutil_liveness(pid: int, lease: Any):
    try:
        import psutil

        process = psutil.Process(pid)
        return lease.ProcessLivenessEvidence(
            exists=True,
            process_started_at=utc_timestamp(float(process.create_time())),
        )
    except ImportError:
        return lease.ProcessLivenessEvidence(exists=None)
    except Exception as exc:
        try:
            import psutil

            if isinstance(exc, psutil.NoSuchProcess):
                return lease.ProcessLivenessEvidence(exists=False)
        except Exception:
            pass
        return lease.ProcessLivenessEvidence(exists=None)


def make_local_runtime_identity(settings, lease=None, *, rpc_mod: Any):
    """Bind lease recovery to this addon's process-lifetime identity."""

    lease = lease or rpc_mod._import_document_lease()
    profile_id = str(
        settings.get("profile_instance_id") or settings.get("instance_id") or ""
    )
    try:
        import uuid

        uuid.UUID(profile_id)
    except (AttributeError, TypeError, ValueError):
        # Ordinary profiles predate persisted profile IDs. A stable UUIDv5 of
        # the profile path is identification only; it is never an auth secret.
        import uuid

        profile_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                "freecad-mcp-profile:" + rpc_mod._profile_fingerprint(),
            )
        )
    evidence = rpc_mod._probe_process_liveness(rpc_mod.os.getpid())
    return lease.LocalRuntimeIdentity(
        addon_profile_id=profile_id,
        addon_runtime_id=rpc_mod._ADDON_RUNTIME_ID,
        freecad_pid=rpc_mod.os.getpid(),
        freecad_process_started_at=evidence.process_started_at or "",
        boot_id=rpc_mod._boot_identity(),
        hostname=rpc_mod.platform.node(),
    )


def profile_fingerprint(*, rpc_mod: Any) -> str:
    import hashlib

    import FreeCAD

    try:
        profile = rpc_mod.os.path.realpath(FreeCAD.getUserAppDataDir())
    except Exception:
        profile = "unknown-profile"
    return hashlib.sha256(rpc_mod.os.path.normcase(profile).encode("utf-8")).hexdigest()


def require_authenticated_lease_runtime(profile_id: str, *, rpc_mod: Any):
    """Return the exact lease identity used to build the RPC manifest."""

    runtime = getattr(rpc_mod.document_lease_service, "local_runtime_identity", None)
    if (
        runtime is None
        or not runtime.freecad_process_started_at
        or not runtime.boot_id
        or not runtime.hostname
    ):
        raise RuntimeError("trusted FreeCAD process/boot/host identity is unavailable")
    if (
        runtime.addon_profile_id != profile_id
        or runtime.addon_runtime_id != rpc_mod.rpc_server_runtime_id
        or runtime.freecad_pid != rpc_mod.os.getpid()
    ):
        raise RuntimeError(
            "lease runtime identity disagrees with authenticated startup"
        )
    return runtime

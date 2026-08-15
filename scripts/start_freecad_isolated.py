#!/usr/bin/env python3
"""Launch FreeCAD with the isolated MCP profile and prove its RPC identity.

The launcher refuses an already occupied endpoint.  It starts one FreeCAD
process, uses ``get_instance_info`` only to discover the candidate runtime,
then accepts readiness only after a profile-secret-authenticated v2 handshake
proves the launched PID, persistent profile identity, endpoint, runtime UUID,
process start, version and build metadata.  It never stops or reuses a process
already listening on the configured endpoint, including the default :9875
instance.  ``FREECAD_MCP_ISOLATED_FREECAD`` may select an absolute branch-built
FreeCAD executable without changing the isolated profile or endpoint.
"""
from __future__ import annotations

import hashlib
import importlib.util
import ipaddress
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Any

# The launcher is run directly from ``scripts/`` as well as from an installed
# package.  Put this checkout's ``src`` first so its authentication codec is
# exactly the one paired with the addon being launched.
_MCP_SOURCE = Path(__file__).resolve().parents[1] / "src"
if str(_MCP_SOURCE) not in sys.path:
    sys.path.insert(0, str(_MCP_SOURCE))

from freecad_mcp._shared.protocol.json_rpc_client import (  # noqa: E402
    JsonRpcProtocolMismatchError,
    JsonRpcRemoteError,
)
from freecad_mcp.build_info import build_id as MCP_BUILD_ID  # noqa: E402
from freecad_mcp.freecad_client import FreeCADConnection  # noqa: E402
from freecad_mcp.rpc_auth import (  # noqa: E402
    PROTOCOL_VERSION,
    REQUIRED_PROTOCOL_FEATURES,
    McpRuntimeIdentity,
    RpcAuthError,
    build_handshake_request,
    load_profile_secret,
    make_mcp_runtime_identity,
    verify_handshake_response,
)

PROFILE_NAME = ".freecad-mcp-isolated"
MANIFEST_FILENAME = "instance-manifest.json"
LAUNCH_STATE_FILENAME = "launch-state.json"
MANIFEST_SCHEMA_VERSION = 1
LAUNCHER_BUILD_ID = f"{MCP_BUILD_ID}-isolated-launcher"
FREECAD_EXECUTABLE_ENV = "FREECAD_MCP_ISOLATED_FREECAD"
SUPERVISE_FLAG = "--supervise"
_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "rpc_host",
        "rpc_port",
        "profile_instance_id",
        "profile_path",
        "auth_secret_file",
        "expected_freecad_pid",
        "expected_freecad_process_started_at",
        "expected_addon_runtime_id",
        "expected_boot_id",
        "expected_protocol_version",
        "expected_protocol_features",
        "expected_addon_version",
        "expected_addon_build_id",
        "expected_freecad_version",
        "expected_freecad_revision",
        "expected_profile_path_fingerprint",
        "created_at",
    }
)


def _resolve_profile(repo: Path, *, profile_name: str | None = None) -> Path:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from _profile_resolve import resolve_isolated_profile

    return resolve_isolated_profile(
        repo, profile_name=profile_name, default_name=PROFILE_NAME
    )


def _consume_launcher_args(argv: list[str]) -> tuple[str | None, list[str]]:
    """Peel launcher-only flags; return (profile_name, freecad_argv)."""

    profile_name: str | None = None
    remainder: list[str] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--profile-name":
            if index + 1 >= len(argv):
                raise SystemExit("--profile-name requires a value")
            profile_name = argv[index + 1]
            index += 2
            continue
        if arg.startswith("--profile-name="):
            profile_name = arg.split("=", 1)[1]
            index += 1
            continue
        remainder.append(arg)
        index += 1
    return profile_name, remainder


def _consume_supervision_flag(argv: list[str]) -> tuple[bool, list[str]]:
    supervise = False
    remainder: list[str] = []
    for arg in argv:
        if arg == SUPERVISE_FLAG:
            if supervise:
                raise SystemExit(f"{SUPERVISE_FLAG} may be specified only once")
            supervise = True
        else:
            remainder.append(arg)
    return supervise, remainder


class InstanceValidationError(RuntimeError):
    """The endpoint answered, but it is not the launched isolated runtime."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _resolve_freecad_executable(repo: Path) -> Path:
    """Select one explicit FreeCAD executable without changing profile policy."""

    configured = os.environ.get(FREECAD_EXECUTABLE_ENV, "").strip()
    if configured:
        expanded = os.path.expandvars(os.path.expanduser(configured))
        candidate = Path(expanded)
        if not candidate.is_absolute():
            raise SystemExit(
                f"{FREECAD_EXECUTABLE_ENV} must be an absolute path: {configured!r}"
            )
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise SystemExit(
                f"{FREECAD_EXECUTABLE_ENV} does not identify an existing file: "
                f"{candidate}"
            ) from exc
        if not resolved.is_file():
            raise SystemExit(
                f"{FREECAD_EXECUTABLE_ENV} must identify a regular file: {resolved}"
            )
        if os.name != "nt" and not os.access(resolved, os.X_OK):
            raise SystemExit(
                f"{FREECAD_EXECUTABLE_ENV} is not executable: {resolved}"
            )
        return resolved

    executable_name = "FreeCAD.exe" if sys.platform == "win32" else "FreeCAD"
    candidate = repo / "build" / "release" / "bin" / executable_name
    if not candidate.is_file():
        raise SystemExit(f"build/release FreeCAD not found: {candidate}")
    if os.name != "nt" and not os.access(candidate, os.X_OK):
        raise SystemExit(f"build/release FreeCAD is not executable: {candidate}")
    return candidate


def _manifest_path(profile: Path) -> Path:
    return profile / MANIFEST_FILENAME


def _launch_state_path(profile: Path) -> Path:
    return profile / LAUNCH_STATE_FILENAME


def _load_manifest(profile: Path) -> dict[str, Any]:  # noqa: C901
    path = _manifest_path(profile)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(
            f"Isolated manifest missing: {path}\n"
            "Run scripts/setup_isolated_profile.py first."
        ) from exc
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Cannot read isolated manifest {path}: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise SystemExit(f"Unsupported isolated manifest: {path}")
    if set(value) != _MANIFEST_FIELDS:
        missing = sorted(_MANIFEST_FIELDS.difference(value))
        extra = sorted(set(value).difference(_MANIFEST_FIELDS))
        raise SystemExit(
            f"Invalid isolated manifest fields in {path}: missing={missing}, extra={extra}"
        )
    for field in (
        "rpc_host",
        "profile_instance_id",
        "profile_path",
        "auth_secret_file",
        "created_at",
    ):
        if not isinstance(value.get(field), str) or not value[field]:
            raise SystemExit(f"Invalid {field} in isolated manifest: {path}")
    port = value.get("rpc_port")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise SystemExit(f"Invalid rpc_port in isolated manifest: {path}")
    try:
        rpc_address = ipaddress.ip_address(value["rpc_host"])
    except ValueError as exc:
        raise SystemExit(
            "Isolated rpc_host must be an explicit loopback IP address"
        ) from exc
    if not rpc_address.is_loopback:
        raise SystemExit(
            "Isolated rpc_host must remain on loopback; use a local SSH/TLS "
            "tunnel endpoint for remote workflows"
        )
    if not Path(value["profile_path"]).is_absolute():
        raise SystemExit(f"profile_path must be absolute in isolated manifest: {path}")
    if _normalize_path(value["profile_path"]) != _normalize_path(profile):
        raise SystemExit(f"profile_path does not identify {profile}: {path}")
    configured_secret = Path(value["auth_secret_file"])
    if not configured_secret.is_absolute():
        raise SystemExit(f"auth_secret_file must be absolute in isolated manifest: {path}")
    if configured_secret.is_symlink():
        raise SystemExit(
            f"Authentication secret must not be a symlink: {configured_secret}"
        )
    secret_path = configured_secret.resolve()
    try:
        secret_path.relative_to(profile.resolve())
    except ValueError as exc:
        raise SystemExit(
            f"Authentication secret must remain inside isolated profile: {secret_path}"
        ) from exc
    try:
        secret_size = secret_path.stat().st_size
    except OSError as exc:
        raise SystemExit(f"Authentication secret is unavailable: {secret_path}") from exc
    if not secret_path.is_file() or secret_size != 32:
        raise SystemExit(
            f"Authentication secret must be a regular 32-byte file: {secret_path}"
        )
    return value


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        with suppress(OSError):
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except Exception:
        with suppress(OSError):
            temporary.unlink()
        raise


def _write_manifest(profile: Path, value: dict[str, Any]) -> None:
    _write_json_atomic(_manifest_path(profile), value)


def _write_launch_state(profile: Path, *, process, executable: Path) -> None:
    """Persist the exact spawned PID before any readiness wait can fail."""

    _write_json_atomic(
        _launch_state_path(profile),
        {
            "schema_version": 1,
            "freecad_pid": int(process.pid),
            "profile_path": str(profile.resolve()),
            "freecad_executable": str(executable.resolve()),
            "created_at_unix": time.time(),
        },
    )


def _clear_launch_state(profile: Path) -> None:
    with suppress(FileNotFoundError):
        _launch_state_path(profile).unlink()


def _terminate_spawned_process(process, *, timeout_seconds: float = 10.0) -> bool:
    """Stop only the process object created by this launcher."""

    if process.poll() is not None:
        return True
    with suppress(OSError):
        process.terminate()
    try:
        process.wait(timeout=timeout_seconds)
        return True
    except subprocess.TimeoutExpired:
        pass
    except OSError:
        return process.poll() is not None
    with suppress(OSError):
        process.kill()
    try:
        process.wait(timeout=timeout_seconds)
    except (OSError, subprocess.TimeoutExpired):
        return process.poll() is not None
    return process.poll() is not None


class _WindowsLifetimeJob:
    """Kill-on-close Job Object assigned before a suspended child first runs."""

    _KILL_ON_JOB_CLOSE = 0x00002000
    _EXTENDED_LIMIT_INFORMATION = 9

    def __init__(self) -> None:  # noqa: C901 - bounded ctypes declarations
        import ctypes
        from ctypes import wintypes

        self._ctypes = ctypes
        self._wintypes = wintypes
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class BASIC_LIMITS(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class EXTENDED_LIMITS(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BASIC_LIMITS),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        self._limits_type = EXTENDED_LIMITS
        self._kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self._kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        self._kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        self._kernel32.SetInformationJobObject.restype = wintypes.BOOL
        self._kernel32.AssignProcessToJobObject.argtypes = [
            wintypes.HANDLE,
            wintypes.HANDLE,
        ]
        self._kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        self._kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self._kernel32.TerminateJobObject.restype = wintypes.BOOL
        self._kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
        self._kernel32.ResumeThread.restype = wintypes.DWORD
        self._kernel32.GetExitCodeProcess.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self._kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        self._kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self._kernel32.WaitForSingleObject.restype = wintypes.DWORD
        self._kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self._kernel32.TerminateProcess.restype = wintypes.BOOL
        self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._handle = self._kernel32.CreateJobObjectW(None, None)
        if not self._handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
        limits = EXTENDED_LIMITS()
        limits.BasicLimitInformation.LimitFlags = self._KILL_ON_JOB_CLOSE
        if not self._kernel32.SetInformationJobObject(
            self._handle,
            self._EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            error = ctypes.get_last_error()
            self.close()
            raise OSError(error, "SetInformationJobObject failed")

    def bind_suspended_process(self, process_handle, thread_handle) -> None:
        if not self._kernel32.AssignProcessToJobObject(self._handle, process_handle):
            raise OSError(
                self._ctypes.get_last_error(),
                "AssignProcessToJobObject failed",
            )
        previous_suspend_count = self._kernel32.ResumeThread(thread_handle)
        if previous_suspend_count == 0xFFFFFFFF:
            raise OSError(self._ctypes.get_last_error(), "ResumeThread failed")

    def terminate(self) -> None:
        if self._handle and not self._kernel32.TerminateJobObject(self._handle, 1):
            raise OSError(self._ctypes.get_last_error(), "TerminateJobObject failed")

    def close(self) -> None:
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


class _WindowsCreatedProcess:
    """Minimal Popen-compatible owner backed by retained Win32 handles."""

    STILL_ACTIVE = 259

    def __init__(self, *, api, process_handle, pid: int) -> None:
        self._api = api
        self._handle = process_handle
        self.pid = int(pid)
        self.returncode = None

    def poll(self):
        if self.returncode is not None:
            return self.returncode
        code = self._api._wintypes.DWORD()
        if not self._api._kernel32.GetExitCodeProcess(
            self._handle, self._api._ctypes.byref(code)
        ):
            raise OSError(
                self._api._ctypes.get_last_error(), "GetExitCodeProcess failed"
            )
        if code.value == self.STILL_ACTIVE:
            return None
        self.returncode = int(code.value)
        return self.returncode

    def wait(self, timeout=None):
        milliseconds = 0xFFFFFFFF if timeout is None else max(0, int(timeout * 1000))
        result = self._api._kernel32.WaitForSingleObject(self._handle, milliseconds)
        if result == 258:
            raise subprocess.TimeoutExpired("FreeCAD", timeout)
        if result != 0:
            raise OSError(
                self._api._ctypes.get_last_error(), "WaitForSingleObject failed"
            )
        return self.poll()

    def kill(self):
        if not self._api._kernel32.TerminateProcess(self._handle, 1):
            raise OSError(
                self._api._ctypes.get_last_error(), "TerminateProcess failed"
            )

    def terminate(self):
        self.kill()

    def close(self) -> None:
        if self._handle:
            self._api._kernel32.CloseHandle(self._handle)
            self._handle = None


def _windows_quote_command(argv: list[str]) -> str:
    return subprocess.list2cmdline(argv)


def _windows_environment_block(env: dict[str, str]):
    # CreateProcessW requires case-insensitive ordering and a double-NUL tail.
    entries = [f"{key}={value}" for key, value in sorted(env.items(), key=lambda x: x[0].upper())]
    return "\0".join(entries) + "\0\0"


def _create_windows_suspended_process(cmd, *, env, cwd, job: _WindowsLifetimeJob):
    """Create suspended, bind to the preconfigured Job, then resume."""

    ctypes = job._ctypes
    wintypes = job._wintypes
    kernel32 = job._kernel32

    class STARTUPINFOW(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("lpReserved", wintypes.LPWSTR),
            ("lpDesktop", wintypes.LPWSTR),
            ("lpTitle", wintypes.LPWSTR),
            ("dwX", wintypes.DWORD),
            ("dwY", wintypes.DWORD),
            ("dwXSize", wintypes.DWORD),
            ("dwYSize", wintypes.DWORD),
            ("dwXCountChars", wintypes.DWORD),
            ("dwYCountChars", wintypes.DWORD),
            ("dwFillAttribute", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("wShowWindow", wintypes.WORD),
            ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.POINTER(ctypes.c_ubyte)),
            ("hStdInput", wintypes.HANDLE),
            ("hStdOutput", wintypes.HANDLE),
            ("hStdError", wintypes.HANDLE),
        ]

    class STARTUPINFOEXW(ctypes.Structure):
        _fields_ = [
            ("StartupInfo", STARTUPINFOW),
            ("lpAttributeList", ctypes.c_void_p),
        ]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", wintypes.HANDLE),
            ("hThread", wintypes.HANDLE),
            ("dwProcessId", wintypes.DWORD),
            ("dwThreadId", wintypes.DWORD),
        ]

    kernel32.CreateProcessW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.BOOL,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.LPCWSTR,
        ctypes.POINTER(STARTUPINFOEXW),
        ctypes.POINTER(PROCESS_INFORMATION),
    ]
    kernel32.CreateProcessW.restype = wintypes.BOOL
    kernel32.InitializeProcThreadAttributeList.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    kernel32.InitializeProcThreadAttributeList.restype = wintypes.BOOL
    kernel32.UpdateProcThreadAttribute.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    kernel32.UpdateProcThreadAttribute.restype = wintypes.BOOL
    kernel32.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
    class SECURITY_ATTRIBUTES(ctypes.Structure):
        _fields_ = [
            ("nLength", wintypes.DWORD),
            ("lpSecurityDescriptor", ctypes.c_void_p),
            ("bInheritHandle", wintypes.BOOL),
        ]

    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(SECURITY_ATTRIBUTES),
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    security = SECURITY_ATTRIBUTES(
        ctypes.sizeof(SECURITY_ATTRIBUTES),
        None,
        True,
    )
    # The supervised FreeCAD child must never inherit the launcher's private
    # STOP pipe. Give it explicit NUL standard handles instead.
    null_input = kernel32.CreateFileW(
        "NUL",
        0x80000000,  # GENERIC_READ
        0x00000001 | 0x00000002,  # FILE_SHARE_READ | FILE_SHARE_WRITE
        ctypes.byref(security),
        3,  # OPEN_EXISTING
        0,
        None,
    )
    null_output = kernel32.CreateFileW(
        "NUL",
        0x40000000,  # GENERIC_WRITE
        0x00000001 | 0x00000002,
        ctypes.byref(security),
        3,
        0,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if null_input in (None, invalid_handle) or null_output in (None, invalid_handle):
        error = ctypes.get_last_error()
        for handle in (null_input, null_output):
            if handle not in (None, invalid_handle):
                kernel32.CloseHandle(handle)
        raise OSError(error, "CreateFileW(NUL) failed")

    attribute_size = ctypes.c_size_t()
    kernel32.InitializeProcThreadAttributeList(
        None,
        1,
        0,
        ctypes.byref(attribute_size),
    )
    if not attribute_size.value:
        error = ctypes.get_last_error()
        kernel32.CloseHandle(null_input)
        kernel32.CloseHandle(null_output)
        raise OSError(error, "InitializeProcThreadAttributeList sizing failed")
    attribute_storage = ctypes.create_string_buffer(attribute_size.value)
    attribute_list = ctypes.cast(attribute_storage, ctypes.c_void_p)
    if not kernel32.InitializeProcThreadAttributeList(
        attribute_list,
        1,
        0,
        ctypes.byref(attribute_size),
    ):
        error = ctypes.get_last_error()
        kernel32.CloseHandle(null_input)
        kernel32.CloseHandle(null_output)
        raise OSError(error, "InitializeProcThreadAttributeList failed")
    inherited_handles = (wintypes.HANDLE * 2)(null_input, null_output)
    if not kernel32.UpdateProcThreadAttribute(
        attribute_list,
        0,
        0x00020002,  # PROC_THREAD_ATTRIBUTE_HANDLE_LIST
        ctypes.cast(inherited_handles, ctypes.c_void_p),
        ctypes.sizeof(inherited_handles),
        None,
        None,
    ):
        error = ctypes.get_last_error()
        kernel32.DeleteProcThreadAttributeList(attribute_list)
        kernel32.CloseHandle(null_input)
        kernel32.CloseHandle(null_output)
        raise OSError(error, "UpdateProcThreadAttribute(HANDLE_LIST) failed")

    startup = STARTUPINFOEXW()
    startup.StartupInfo.cb = ctypes.sizeof(startup)
    startup.StartupInfo.dwFlags = 0x00000100  # STARTF_USESTDHANDLES
    startup.StartupInfo.hStdInput = null_input
    startup.StartupInfo.hStdOutput = null_output
    startup.StartupInfo.hStdError = null_output
    startup.lpAttributeList = attribute_list
    info = PROCESS_INFORMATION()
    command_line = ctypes.create_unicode_buffer(_windows_quote_command(list(cmd)))
    environment = ctypes.create_unicode_buffer(_windows_environment_block(dict(env)))
    flags = (
        0x00000004  # CREATE_SUSPENDED
        | 0x00000200  # CREATE_NEW_PROCESS_GROUP
        | 0x00000400  # CREATE_UNICODE_ENVIRONMENT
        | 0x00080000  # EXTENDED_STARTUPINFO_PRESENT
    )
    create_error = 0
    try:
        created = kernel32.CreateProcessW(
            str(cmd[0]),
            command_line,
            None,
            None,
            True,
            flags,
            environment,
            str(cwd),
            ctypes.byref(startup),
            ctypes.byref(info),
        )
        if not created:
            create_error = ctypes.get_last_error()
    finally:
        kernel32.DeleteProcThreadAttributeList(attribute_list)
        kernel32.CloseHandle(null_input)
        kernel32.CloseHandle(null_output)
    if not created:
        raise OSError(create_error, "CreateProcessW failed")
    process = _WindowsCreatedProcess(
        api=job,
        process_handle=info.hProcess,
        pid=int(info.dwProcessId),
    )
    try:
        job.bind_suspended_process(info.hProcess, info.hThread)
    except BaseException:
        with suppress(Exception):
            process.kill()
        with suppress(Exception):
            process.wait(timeout=10.0)
        process.close()
        raise
    finally:
        kernel32.CloseHandle(info.hThread)
    return process


class _SupervisedChild:
    """Lifetime owner retained by test-only supervision mode."""

    def __init__(self, process, *, windows_job=None) -> None:
        self.process = process
        self._windows_job = windows_job
        self._closed = False
        self._terminated = False

    def terminate_exact_tree(self, *, grace_seconds: float = 5.0) -> None:
        if self._closed:
            raise RuntimeError("supervised child ownership has been closed")
        if self._windows_job is not None:
            self._windows_job.terminate()
            self.process.wait(timeout=grace_seconds)
            self._terminated = True
            return

        # The direct child has never been waited/reaped, so its numeric PID
        # cannot be reused while this supervisor owns it. As session leader it
        # also pins the private process-group identity for all descendants.
        # TERM is followed by an unconditional group KILL: a TERM handler may
        # fork, but its descendants remain in this creation-owned group.
        group = int(self.process.pid)
        with suppress(ProcessLookupError):
            os.killpg(group, signal.SIGTERM)
        time.sleep(max(0.0, grace_seconds))
        with suppress(ProcessLookupError):
            os.killpg(group, signal.SIGKILL)
        self.process.wait(timeout=max(1.0, grace_seconds))
        self._terminated = True

    def exit_code_if_exited(self):
        """Observe early exit without reaping the POSIX session leader."""

        if self._windows_job is not None:
            return self.process.poll()
        waitid = getattr(os, "waitid", None)
        wait_nowait = getattr(os, "WNOWAIT", None)
        if waitid is None or wait_nowait is None:
            return None
        try:
            result = waitid(
                os.P_PID,
                int(self.process.pid),
                os.WEXITED | os.WNOHANG | wait_nowait,
            )
        except ChildProcessError:
            return 1
        if result is None:
            return None
        return int(getattr(result, "si_status", 1) or 1)

    def close(self) -> None:
        if self._closed:
            return
        if not self._terminated:
            with suppress(Exception):
                self.terminate_exact_tree(grace_seconds=1.0)
        self._closed = True
        if self._windows_job is not None:
            self._windows_job.close()
        close_process = getattr(self.process, "close", None)
        if callable(close_process):
            close_process()

    @property
    def terminated(self) -> bool:
        return self._terminated


class _SupervisorControl:
    """Consume the private parent pipe from spawn until exact-tree shutdown."""

    def __init__(self, stream=None) -> None:
        self._stream = sys.stdin if stream is None else stream
        self._stop = threading.Event()
        self._command: str | None = None
        self._read_error: BaseException | None = None
        self._signal_requested = False
        self._handlers: dict[object, object] = {}
        self._thread = threading.Thread(
            target=self._read_control,
            name="freecad-mcp-supervisor-control",
            daemon=True,
        )

    def start(self) -> None:
        self._install_signal_handlers()
        try:
            self._thread.start()
        except BaseException:
            self.close()
            raise

    def _read_control(self) -> None:
        try:
            self._command = self._stream.readline()
        except BaseException as exc:
            self._read_error = exc
        finally:
            self._stop.set()

    def _install_signal_handlers(self) -> None:
        def request_stop(_signum, _frame) -> None:
            # Python invokes this on the main thread. Mutate only the shared
            # stop state; owned process cleanup remains in normal control flow.
            self._signal_requested = True
            self._stop.set()

        for candidate in (
            getattr(signal, "SIGTERM", None),
            getattr(signal, "SIGINT", None),
        ):
            if candidate is None:
                continue
            try:
                self._handlers[candidate] = signal.signal(candidate, request_stop)
            except (OSError, ValueError):
                continue

    def wait(self, timeout: float | None = None) -> bool:
        return self._stop.wait(timeout)

    def requested(self) -> bool:
        return self._stop.is_set()

    def exit_code(self) -> int:
        if self._signal_requested:
            return 0
        if self._read_error is not None:
            return 1
        return 0 if self._command in {"STOP\n", "STOP\r\n", ""} else 2

    def close(self) -> None:
        for candidate, previous in self._handlers.items():
            with suppress(OSError, ValueError):
                signal.signal(candidate, previous)
        self._handlers.clear()


def _spawn_freecad_process(
    cmd,
    *,
    env,
    cwd,
    supervise: bool,
):
    """Spawn FreeCAD, binding supervised Windows children before first run."""

    if sys.platform == "win32" and supervise:
        windows_job = _WindowsLifetimeJob()
        try:
            process = _create_windows_suspended_process(
                cmd, env=env, cwd=cwd, job=windows_job
            )
        except BaseException:
            windows_job.close()
            raise
        return process, _SupervisedChild(process, windows_job=windows_job)

    creationflags = 0
    start_new_session = os.name != "nt"
    windows_job = None
    if sys.platform == "win32":
        creationflags = (
            subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
        )
    try:
        process = subprocess.Popen(
            cmd,
            env=env,
            cwd=cwd,
            stdin=subprocess.DEVNULL if supervise else None,
            creationflags=creationflags,
            close_fds=True,
            start_new_session=start_new_session,
        )
    except BaseException:
        if windows_job is not None:
            windows_job.close()
        raise
    return process, (_SupervisedChild(process, windows_job=windows_job) if supervise else None)


def _spawn_supervised_process_with_control(cmd, *, env, cwd):
    """Atomically hand a new supervised child to its control monitor."""

    control = _SupervisorControl()
    control.start()
    process = None
    owner = None
    try:
        if control.requested():
            raise InterruptedError("supervisor stop requested before child spawn")
        process, owner = _spawn_freecad_process(
            cmd,
            env=env,
            cwd=cwd,
            supervise=True,
        )
        if control.requested():
            owner.terminate_exact_tree()
            raise InterruptedError("supervisor stop requested during child spawn")
    except BaseException:
        if owner is not None:
            owner.close()
        control.close()
        raise
    return process, owner, control


def _supervise_until_stop(
    owner: _SupervisedChild,
    control: _SupervisorControl,
) -> int:
    """Hold lifetime ownership until the private parent pipe requests stop."""

    print("SUPERVISOR_READY", flush=True)
    control.wait()
    requested_exit = control.exit_code()
    if requested_exit != 0:
        print("ERROR: invalid supervisor command; stopping exact child", file=sys.stderr)
    try:
        owner.terminate_exact_tree()
    except Exception as exc:
        print(f"ERROR: identity-bound supervisor shutdown failed: {exc}", file=sys.stderr)
        return 1
    print("SUPERVISOR_STOPPED", flush=True)
    return requested_exit


def _close_supervised_lifecycle(owner, control) -> None:
    """Tear down exact ownership before restoring external signal handlers."""

    if owner is not None:
        owner.close()
    if control is not None:
        control.close()


def _reserve_endpoint(host: str, port: int) -> socket.socket:
    """Exclusively bind the endpoint without contacting an existing listener.

    The returned socket is intentionally not put into listening mode.  Holding
    the bind closes the preflight check/use window while launch arguments and
    environment are prepared.  The launcher releases it immediately before
    spawning FreeCAD because the addon cannot inherit an already-bound socket.
    """

    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    reservation = socket.socket(family, socket.SOCK_STREAM)
    try:
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            reservation.setsockopt(
                socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1
            )
        else:
            reservation.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        reservation.bind((host, port))
    except OSError as exc:
        reservation.close()
        raise SystemExit(
            f"Refusing to start isolated FreeCAD: {host}:{port} is already occupied. "
            "The existing process was not contacted, probed, reused, or stopped."
        ) from exc
    return reservation


def _normalize_path(value: object) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(str(value))))


def _freecad_build_identity(value: object) -> tuple[str, str]:
    parts = list(value) if isinstance(value, (list, tuple)) else [value]
    rendered = [str(part) for part in parts]
    version = ".".join(rendered[:3])
    revision = rendered[3] if len(rendered) > 3 and rendered[3] else "unknown"
    return version, revision


def _profile_path_fingerprint(profile: Path) -> str:
    """Match the addon's authenticated profile-path fingerprint."""

    normalized = os.path.normcase(os.path.realpath(str(profile)))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _validate_instance_info(  # noqa: C901
    info: object, manifest: dict[str, Any], launched_pid: int
) -> dict[str, Any]:
    if not isinstance(info, dict) or info.get("ok") is not True:
        raise InstanceValidationError("get_instance_info did not return ok=true")

    expected_profile = manifest["profile_instance_id"]
    actual_profile = info.get("profile_instance_id") or info.get("instance_id")
    if actual_profile != expected_profile:
        raise InstanceValidationError(
            f"profile mismatch: expected {expected_profile!r}, got {actual_profile!r}"
        )
    if info.get("pid") != launched_pid:
        raise InstanceValidationError(
            f"PID mismatch: launched {launched_pid}, endpoint reported {info.get('pid')!r}"
        )

    endpoint = info.get("actual_endpoint")
    if not isinstance(endpoint, dict):
        endpoint = {"host": info.get("host"), "port": info.get("port")}
    if (
        endpoint.get("host") != manifest["rpc_host"]
        or endpoint.get("port") != manifest["rpc_port"]
    ):
        raise InstanceValidationError(
            "RPC endpoint mismatch: expected "
            f"{manifest['rpc_host']}:{manifest['rpc_port']}, got "
            f"{endpoint.get('host')}:{endpoint.get('port')}"
        )

    actual_profile_path = info.get("profile_path")
    if not actual_profile_path or _normalize_path(actual_profile_path) != _normalize_path(
        manifest["profile_path"]
    ):
        raise InstanceValidationError(
            f"profile path mismatch: expected {manifest['profile_path']!r}, "
            f"got {actual_profile_path!r}"
        )

    runtime_id = info.get("addon_runtime_id")
    try:
        parsed_runtime = uuid.UUID(str(runtime_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise InstanceValidationError("addon_runtime_id is missing or invalid") from exc
    if parsed_runtime.int == 0:
        raise InstanceValidationError("addon_runtime_id must not be the nil UUID")

    addon_version = info.get("addon_version")
    addon_build_id = info.get("addon_build_id")
    freecad_version, freecad_revision = _freecad_build_identity(
        info.get("freecad_version")
    )
    process_started_at = info.get("freecad_process_started_at") or info.get(
        "addon_loaded_at"
    )
    boot_id = info.get("boot_id")
    profile_fingerprint = info.get("profile_path_fingerprint")
    protocol_version = info.get("protocol_version")
    protocol_features = info.get("protocol_features")
    if not isinstance(addon_version, str) or not addon_version:
        raise InstanceValidationError("addon_version is missing")
    if not isinstance(addon_build_id, str) or not addon_build_id:
        raise InstanceValidationError("addon_build_id is missing")
    if not freecad_version:
        raise InstanceValidationError("freecad_version is missing")
    if not isinstance(process_started_at, str) or not process_started_at:
        raise InstanceValidationError("FreeCAD process start time is missing")
    if not isinstance(boot_id, str) or not boot_id:
        raise InstanceValidationError("host boot identity is missing")
    expected_profile_fingerprint = _profile_path_fingerprint(
        Path(manifest["profile_path"])
    )
    if profile_fingerprint != expected_profile_fingerprint:
        raise InstanceValidationError("profile path fingerprint mismatch")
    if info.get("document_lease_mode") != "enforce":
        raise InstanceValidationError("isolated addon is not in document_lease_mode=enforce")
    versions = info.get("protocol_versions")
    if (
        not isinstance(versions, (list, tuple))
        or PROTOCOL_VERSION not in versions
        or protocol_version != PROTOCOL_VERSION
    ):
        raise InstanceValidationError("addon does not advertise RPC protocol v2")
    if not isinstance(protocol_features, (list, tuple)) or not all(
        isinstance(item, str) and item for item in protocol_features
    ):
        raise InstanceValidationError("RPC protocol features are missing")
    normalized_features = tuple(sorted(set(protocol_features)))
    if not REQUIRED_PROTOCOL_FEATURES.issubset(normalized_features):
        raise InstanceValidationError("addon omits required RPC protocol features")

    expectations = {
        "expected_freecad_pid": launched_pid,
        "expected_freecad_process_started_at": process_started_at,
        "expected_addon_runtime_id": str(parsed_runtime),
        "expected_boot_id": boot_id,
        "expected_protocol_version": protocol_version,
        "expected_protocol_features": list(normalized_features),
        "expected_addon_version": addon_version,
        "expected_addon_build_id": addon_build_id,
        "expected_freecad_version": freecad_version,
        "expected_freecad_revision": freecad_revision,
        "expected_profile_path_fingerprint": expected_profile_fingerprint,
    }
    for key, actual in expectations.items():
        expected = manifest.get(key)
        if expected is not None and expected != actual:
            raise InstanceValidationError(
                f"runtime manifest mismatch for {key}: expected {expected!r}, got {actual!r}"
            )
    return expectations


def _prove_authenticated_instance(
    proxy: Any,
    *,
    info: object,
    manifest: dict[str, Any],
    launched_pid: int,
    secret: bytes,
    launcher_identity: McpRuntimeIdentity | None = None,
) -> dict[str, Any]:
    """Authenticate the candidate endpoint and return only proven facts.

    ``get_instance_info`` is intentionally unauthenticated so it remains a
    compatibility/readiness probe.  Its values are used only as exact
    assertions in the signed request and response verification; callers must
    never persist them until this function succeeds.
    """

    candidate = _validate_instance_info(info, manifest, launched_pid)
    identity = launcher_identity or make_mcp_runtime_identity(
        client_build_id=LAUNCHER_BUILD_ID
    )
    try:
        request = build_handshake_request(
            secret=secret,
            mcp=identity,
            expected_profile_id=manifest["profile_instance_id"],
            expected_freecad_pid=launched_pid,
            expected_freecad_process_started_at=candidate[
                "expected_freecad_process_started_at"
            ],
            expected_addon_runtime_id=candidate["expected_addon_runtime_id"],
            expected_boot_id=candidate["expected_boot_id"],
            expected_rpc_host=manifest["rpc_host"],
            expected_rpc_port=manifest["rpc_port"],
            expected_protocol_version=candidate["expected_protocol_version"],
            expected_protocol_features=candidate[
                "expected_protocol_features"
            ],
            expected_addon_version=candidate["expected_addon_version"],
            expected_addon_build_id=candidate["expected_addon_build_id"],
            expected_freecad_version=candidate["expected_freecad_version"],
            expected_freecad_revision=candidate["expected_freecad_revision"],
            expected_profile_path_fingerprint=candidate[
                "expected_profile_path_fingerprint"
            ],
        )
        response = proxy.handshake_v2(request)
        verified = verify_handshake_response(
            response,
            secret=secret,
            expected_client_nonce=request["client_nonce"],
            expected_profile_id=manifest["profile_instance_id"],
            expected_freecad_pid=launched_pid,
            expected_addon_runtime_id=candidate["expected_addon_runtime_id"],
            expected_freecad_process_started_at=candidate[
                "expected_freecad_process_started_at"
            ],
            expected_rpc_host=manifest["rpc_host"],
            expected_rpc_port=manifest["rpc_port"],
            expected_protocol_version=candidate["expected_protocol_version"],
            expected_protocol_features=candidate[
                "expected_protocol_features"
            ],
            expected_addon_version=candidate["expected_addon_version"],
            expected_addon_build_id=candidate["expected_addon_build_id"],
            expected_freecad_version=candidate["expected_freecad_version"],
            expected_freecad_revision=candidate["expected_freecad_revision"],
            expected_boot_id=candidate["expected_boot_id"],
            expected_profile_path_fingerprint=candidate[
                "expected_profile_path_fingerprint"
            ],
        )
    except (
        JsonRpcProtocolMismatchError,
        JsonRpcRemoteError,
        OSError,
        RpcAuthError,
        TypeError,
        ValueError,
    ) as exc:
        # Authentication errors are deliberately bounded and never include the
        # profile secret or issued session credential.
        raise InstanceValidationError(
            f"authenticated RPC v2 handshake failed: {exc}"
        ) from exc

    expected_fingerprint = _profile_path_fingerprint(Path(manifest["profile_path"]))
    if verified.manifest.profile_path_fingerprint != expected_fingerprint:
        raise InstanceValidationError(
            "authenticated profile path fingerprint does not match the isolated profile"
        )

    # Populate readiness exclusively from the HMAC-authenticated manifest,
    # never from the preceding unauthenticated discovery response.
    runtime = verified.manifest
    return {
        "expected_freecad_pid": runtime.freecad_pid,
        "expected_freecad_process_started_at": runtime.freecad_process_started_at,
        "expected_addon_runtime_id": runtime.addon_runtime_id,
        "expected_boot_id": runtime.boot_id,
        "expected_protocol_version": runtime.protocol_version,
        "expected_protocol_features": list(runtime.features),
        "expected_addon_version": runtime.addon_version,
        "expected_addon_build_id": runtime.addon_build_id,
        "expected_freecad_version": runtime.freecad_version,
        "expected_freecad_revision": runtime.freecad_revision,
        "expected_profile_path_fingerprint": runtime.profile_path_fingerprint,
    }


def _load_parent_start_freecad():
    """Load FreeCADModeling/start_freecad.py for PATH/Qt helpers only."""

    parent = _repo_root().parent / "start_freecad.py"
    if not parent.is_file():
        alt = _repo_root() / ".." / "start_freecad.py"
        parent = alt.resolve() if alt.is_file() else parent
    if not parent.is_file():
        raise SystemExit(f"Parent start_freecad.py not found at {parent}")
    spec = importlib.util.spec_from_file_location("freecadmodeling_start_freecad", parent)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load {parent}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:  # noqa: C901
    repo = _repo_root()
    supervise, launcher_argv = _consume_supervision_flag(sys.argv[1:])
    profile_name, freecad_argv = _consume_launcher_args(launcher_argv)
    profile = _resolve_profile(repo, profile_name=profile_name)
    freecad = _resolve_freecad_executable(repo)

    if not profile.is_dir():
        raise SystemExit(
            f"Isolated profile missing: {profile}\n"
            "Run scripts/setup_isolated_profile.py first "
            "(pass --profile-name when using a throwaway profile)."
        )
    for required in (profile / "Mod", profile / "temp"):
        required.mkdir(parents=True, exist_ok=True)

    manifest = _load_manifest(profile)
    host = manifest["rpc_host"]
    port = manifest["rpc_port"]
    if _normalize_path(manifest["profile_path"]) != _normalize_path(profile):
        raise SystemExit(
            "Manifest profile_path does not identify this isolated profile; "
            "run setup_isolated_profile.py again."
        )
    try:
        profile_secret = load_profile_secret(manifest["auth_secret_file"])
    except RpcAuthError as exc:
        raise SystemExit(
            f"Cannot authenticate the isolated profile: {exc.public_message}"
        ) from exc
    endpoint_reservation = _reserve_endpoint(host, port)
    try:
        helper = _load_parent_start_freecad()
        # Launch FreeCAD directly so Popen.pid is the exact process identity
        # authenticated by the addon.  The general launcher may wrap build-tree
        # executables in ``pixi run``; on Windows that leaves Pixi as the parent
        # PID and makes strict runtime binding reject the real FreeCAD child.
        cmd = [str(freecad), *freecad_argv]
        cwd = str(freecad.parent)
        env = dict(helper._launch_env(freecad))
        env["FREECAD_USER_HOME"] = str(profile)
        env["FREECAD_USER_DATA"] = str(profile)
        env["FREECAD_USER_TEMP"] = str(profile / "temp")

        print("Starting isolated FreeCAD:")
        print(f"  exe:      {freecad}")
        print(f"  profile:  {profile}")
        print(f"  manifest: {_manifest_path(profile)}")
        print(f"  RPC:      {host}:{port}")
        print("  existing default MCP instance is not contacted or stopped")

    except BaseException:
        endpoint_reservation.close()
        raise
    # This is the narrowest possible release-to-bind window without changing
    # FreeCAD's addon listener to inherit a pre-bound socket.
    endpoint_reservation.close()
    process = None
    supervised_owner = None
    supervisor_control = None
    connection = None
    readiness_published = False
    launch_state_written = False
    try:
        if supervise:
            process, supervised_owner, supervisor_control = (
                _spawn_supervised_process_with_control(cmd, env=env, cwd=cwd)
            )
        else:
            process, supervised_owner = _spawn_freecad_process(
                cmd,
                env=env,
                cwd=cwd,
                supervise=False,
            )
        print(f"  pid:      {process.pid}")
        # This record closes the crash window between Popen and authenticated
        # manifest publication. A caller can refuse or clean up this exact PID
        # even if the launcher itself is interrupted during readiness proof.
        _write_launch_state(profile, process=process, executable=freecad)
        launch_state_written = True

        # Keep launch expectations in memory.  The persistent readiness
        # manifest is not updated with candidate runtime facts until their
        # HMAC-authenticated handshake has been verified.
        launch_manifest = dict(manifest)
        launch_manifest.update(
            {
                "expected_freecad_pid": process.pid,
                "expected_freecad_process_started_at": None,
                "expected_addon_runtime_id": None,
                "expected_boot_id": None,
                "expected_protocol_version": None,
                "expected_protocol_features": None,
                "expected_addon_version": None,
                "expected_addon_build_id": None,
                "expected_freecad_version": None,
                "expected_freecad_revision": None,
                "expected_profile_path_fingerprint": None,
            }
        )

        deadline = time.monotonic() + 60.0
        launcher_identity = make_mcp_runtime_identity(client_build_id=LAUNCHER_BUILD_ID)
        connection = FreeCADConnection(
            host=host,
            port=port,
            timeout=2.0,
            mcp_instance_id=launcher_identity.runtime_id,
            mcp_client=launcher_identity.client_build_id,
            mcp_pid=launcher_identity.pid,
            mcp_host=launcher_identity.hostname,
        )
        proxy = connection.server
        while time.monotonic() < deadline:
            if supervisor_control is not None and supervisor_control.requested():
                return _supervise_until_stop(
                    supervised_owner,
                    supervisor_control,
                )
            exit_code = (
                supervised_owner.exit_code_if_exited()
                if supervised_owner is not None
                else process.poll()
            )
            if exit_code is not None:
                print(
                    f"ERROR: FreeCAD exited before RPC identity was proven "
                    f"(code {exit_code})",
                    file=sys.stderr,
                )
                return exit_code or 1
            try:
                info = proxy.get_instance_info()
            except (JsonRpcProtocolMismatchError, JsonRpcRemoteError, OSError):
                if supervisor_control is None or not supervisor_control.wait(0.5):
                    continue
                return _supervise_until_stop(
                    supervised_owner,
                    supervisor_control,
                )
            try:
                expectations = _prove_authenticated_instance(
                    proxy,
                    info=info,
                    manifest=launch_manifest,
                    launched_pid=process.pid,
                    secret=profile_secret,
                    launcher_identity=launcher_identity,
                )
            except InstanceValidationError as exc:
                print(
                    "ERROR: authenticated RPC endpoint identity validation failed: "
                    f"{exc}. The exact spawned process will be stopped.",
                    file=sys.stderr,
                )
                return 1
            validated_manifest = dict(launch_manifest)
            validated_manifest.update(expectations)
            _write_manifest(profile, validated_manifest)
            readiness_published = True
            # The authenticated readiness manifest supersedes the unresolved
            # launch record. Failure to remove the redundant record must not
            # turn a proven-ready child into an unowned detached process.
            with suppress(OSError):
                _clear_launch_state(profile)
            print(
                f"Isolated MCP RPC identity authenticated on {host}:{port} "
                f"(pid={process.pid}, "
                f"runtime={expectations['expected_addon_runtime_id']})"
            )
            if supervised_owner is not None:
                return _supervise_until_stop(
                    supervised_owner,
                    supervisor_control,
                )
            return 0
    finally:
        if supervised_owner is None and process is not None and not readiness_published:
            stopped = _terminate_spawned_process(process)
            if stopped:
                if launch_state_written:
                    _clear_launch_state(profile)
            elif not launch_state_written:
                # A launch-state write failure must not erase the only durable
                # record of a child that also resisted exact-process cleanup.
                with suppress(Exception):
                    _write_launch_state(profile, process=process, executable=freecad)
        if connection is not None:
            with suppress(Exception):
                connection.disconnect()
        _close_supervised_lifecycle(supervised_owner, supervisor_control)

    print(
        f"ERROR: FreeCAD started, but no authenticated isolated RPC appeared on "
        f"{host}:{port} within 60 seconds. The exact spawned process was stopped "
        "when possible; unresolved launch state was preserved otherwise.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Offline Docker records are rejected by the production lifecycle, not a daemon."""
from __future__ import annotations

import os

from tests.evidence_system.packet_harness import run_packet


def test_tmpfs_launch_literal_is_frozen(tmp_path):
    result, output = run_packet(tmp_path, {"kind":"docker","case":"tmpfs_launch"}); assert result["issue"] == {"stage":"docker","code":"TMPFS_LAUNCH","artifact":"docker-argv","field":"/--tmpfs"} and not (output / "final-verdict.json").exists()


def test_tmpfs_inspect_literal_is_frozen(tmp_path):
    result, output = run_packet(tmp_path, {"kind":"docker","case":"tmpfs_inspect"}); assert result["issue"] == {"stage":"docker","code":"TMPFS_INSPECT","artifact":"inspect","field":"/HostConfig/Tmpfs"} and not (output / "final-verdict.json").exists()


def test_tmpfs_kernel_mount_is_frozen(tmp_path):
    result, output = run_packet(tmp_path, {"kind":"docker","case":"tmpfs_kernel"}); assert result["issue"] == {"stage":"docker","code":"TMPFS_KERNEL","artifact":"kernel-mount","field":"/tmp"} and not (output / "final-verdict.json").exists()


def test_tmpfs_full_offline_semantics_pass(tmp_path):
    result, output = run_packet(tmp_path)
    assert result["passed"] is True and (output / "final-verdict.json").exists()
    # A fresh full signed packet traverses trusted bootstrap -> captured main
    # -> executor -> runner.  Its hook makes an actual junction only between
    # the gate's ancestor walk and CreateFileW; the worker never runs.
    race_root=tmp_path/"worker-race";race_root.mkdir(); race, race_output=run_packet(race_root,{"kind":"worker_race"})
    assert race == {"passed":False,"issue":{"stage":"executor","code":"EXECUTOR_SOURCE_REPARSE","artifact":"offline_worker.py","field":"/ancestors"}}
    assert (race_root/"worker-race-hook").read_text()=="hook-ran"
    assert not (race_root/"unapproved-worker-side-effect").exists() and not (race_output/"final-verdict.json").exists()
    # The post-hash/pre-spawn race holds the worker handle.  Windows denies
    # replacement and proves the approved worker ran; POSIX reports the exact
    # changed-source guard.  Either branch is a fresh verdict-free packet.
    swap_root=tmp_path/"worker-swap";swap_root.mkdir();swap,swap_output=run_packet(swap_root,{"kind":"worker_swap"})
    if os.name=="nt":
        assert swap=={"passed":False,"issue":{"stage":"preflight","code":"PREFLIGHT_JSON","artifact":"preflight.json","field":"/"}}
        assert (swap_root/"worker-swap-hook").read_text()=="swap-denied" and (swap_root/"approved-worker-ran").read_text()=="ran"
    else: assert swap=={"passed":False,"issue":{"stage":"executor","code":"EXECUTOR_SOURCE_CHANGED","artifact":"offline_worker.py","field":"/path"}}
    assert not (swap_root/"unapproved-worker-side-effect").exists() and not (swap_output/"final-verdict.json").exists()


def test_docker_diagnostic_mount_missing(tmp_path):
    result, output = run_packet(tmp_path, {"kind": "docker", "case": "missing"})
    assert result["issue"] == {"stage": "mount", "code": "MOUNT_SET_CONTRACT", "artifact": "inspect", "field": "/Mounts"}
    assert not (output / "final-verdict.json").exists()


def test_docker_diagnostic_mount_writable(tmp_path):
    result, output = run_packet(tmp_path, {"kind": "docker", "case": "writable"})
    assert result["issue"] == {"stage": "mount", "code": "MOUNT_SET_CONTRACT", "artifact": "inspect", "field": "/Mounts"}
    assert not (output / "final-verdict.json").exists()


def test_docker_diagnostic_mount_changed_source_destination_and_uniqueness(tmp_path):
    result, output = run_packet(tmp_path, {"kind": "docker", "case": "changed"})
    assert result["issue"] == {"stage": "mount", "code": "MOUNT_SET_CONTRACT", "artifact": "inspect", "field": "/Mounts"}
    assert not (output / "final-verdict.json").exists()

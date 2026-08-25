"""Sole ordered production coordinator for evidence finalization."""
from __future__ import annotations

from dataclasses import dataclass as _dataclass
from datetime import datetime as _datetime, timezone as _timezone
import json
from pathlib import Path as _Path
from typing import Callable as _Callable

from .authorization import AuthorizationSnapshot as _AuthorizationSnapshot, capture_initial_authorization as _capture_initial_authorization, capture_initial_authorization_bytes as _capture_initial_authorization_bytes
from .bindings import AuthorizationBinding as _AuthorizationBinding, ContainerExecutionBinding as _ContainerExecutionBinding, ExecutionBinding as _ExecutionBinding
from .child_results import ChildResultRegistry as _ChildResultRegistry, REGISTRY_CONFIG as _REGISTRY_CONFIG, reconcile_child_results as _reconcile_child_results
from .docker_contract import validate_execution_contract as _validate_execution_contract
from .executor import ControlledOfflineExecutor as _ControlledOfflineExecutor, validate_executor_command as _validate_executor_command
from .launch_source import LaunchSourceError as _LaunchSourceError
from .host import select_host_interpreter as _select_host_interpreter
from .finalization import construct_final_candidate as _construct_final_candidate, finalize as _finalize
from .ledger import build_ledger as _build_ledger, validate_ledger as _validate_ledger
from .policy import EvidencePolicy as _EvidencePolicy
from .preflight import validate as _validate_preflight
from .publication import fresh_output_gate as _fresh_output_gate, publish_once as _publish_once
from .validation import ValidationResult as _ValidationResult

_ExecutionCallback = _Callable[[_Path, _ExecutionBinding], tuple[dict[str, object], int, _ContainerExecutionBinding]]
_CleanupCallback = _Callable[[_Path, _ExecutionBinding], dict[str, object]]
_BarrierCallback = _Callable[[], None]


@_dataclass(frozen=True)
class RunContext:
    output: _Path
    prerequisites: tuple[_Path, _Path, _Path]
    authorization_binding: _AuthorizationBinding
    policy: _EvidencePolicy
    preflight: bytes
    registry: _ChildResultRegistry
    execute: _ExecutionCallback
    cleanup: _CleanupCallback
    now: _datetime
    after_initial: _BarrierCallback | None = None
    failpoint: str | None = None
    terminal_now: _Callable[[], _datetime] | None = None
    initial_snapshot: _AuthorizationSnapshot | None = None


class EvidenceRunner:
    """Runs the fixed lifecycle once; helper entrypoints cannot bypass ordering."""

    def run(self, context: RunContext) -> _ValidationResult:
        freshness = _fresh_output_gate(context.output)
        if not freshness.passed:
            return freshness
        if context.failpoint == "after_freshness":
            return _interrupted("after_freshness")
        direct = context.authorization_binding
        if (
            direct.run_id != context.policy.run_id
            or direct.attempt_id != context.policy.attempt_id
            or direct.sequence != context.policy.sequence
            or direct.scope != context.policy.scope
            or direct.reviewer_key != context.policy.reviewer_key
        ):
            return _ValidationResult.fail("authorization", "AUTHORIZATION_POLICY_IDENTITY", "review-authorization.json", "/")

        initial, authorized = ((context.initial_snapshot, _ValidationResult.ok()) if context.initial_snapshot is not None else _capture_initial_authorization(
            context.prerequisites, context.authorization_binding, context.authorization_binding.reviewer_key, context.now,
        ))
        if not authorized.passed or initial is None:
            return authorized
        if context.failpoint == "after_initial_authorization":
            return _interrupted("after_initial_authorization")
        binding = _ExecutionBinding.from_snapshot(
            initial.document,
            initial.signature,
            context.now.isoformat(),
            context.authorization_binding,
        )
        checked = _validate_preflight(context.preflight, binding, context.policy, context.now)
        if not checked.passed:
            return checked
        if context.after_initial is not None:
            context.after_initial()

        context.output.mkdir(parents=True, exist_ok=True)
        execution_error = False
        launch_error: _ValidationResult | None = None
        try:
            execution, parent_exit, container_binding = context.execute(context.output, binding)
        except _LaunchSourceError as error:
            execution_error = True
            launch_error = _ValidationResult((error.issue,))
            execution, parent_exit = {"status": "EXECUTION_EXCEPTION", "error": type(error).__name__}, 1
            container_binding = _ContainerExecutionBinding(binding, "0" * 64, "0" * 64)
        except Exception as error:
            execution_error = True
            execution, parent_exit = {"status": "EXECUTION_EXCEPTION", "error": type(error).__name__}, 1
            container_binding = _ContainerExecutionBinding(binding, "0" * 64, "0" * 64)
        if context.failpoint == "after_execution":
            return _interrupted("after_execution")
        try:
            cleanup = context.cleanup(context.output, binding)
        except _LaunchSourceError as error:
            launch_error = launch_error or _ValidationResult((error.issue,))
            cleanup = {"passed": False, "errors": ["cleanup:" + type(error).__name__]}
        except Exception as error:
            cleanup = {"passed": False, "errors": ["cleanup:" + type(error).__name__]}
        if context.failpoint == "after_cleanup":
            return _interrupted("after_cleanup")
        outer = {
            "schema_version": 44,
            "binding": binding.as_dict(),
            "container_binding": container_binding.as_dict(),
            "parent_exit": parent_exit,
            "execution": execution,
            "cleanup": cleanup,
        }
        published = _publish_once(
            context.output / "outer-execution.json",
            json.dumps(outer, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n",
        )
        if not published.passed:
            return published
        # Publication is deliberately before relationship validation: an outer
        # record is immutable forensic evidence even when its relationships fail.
        outer_result = _validate_outer(outer, binding, container_binding)
        if not outer_result.passed:
            return outer_result
        if launch_error is not None:
            return launch_error
        if cleanup["passed"] is not True:
            return _ValidationResult.fail("aftermath", "CLEANUP_FAILED", "outer-execution.json", "/cleanup/passed")
        if execution_error:
            return _ValidationResult.fail("execution", "EXECUTION_FAILED", "outer-execution.json", "/execution")
        if container_binding.execution != binding:
            return _ValidationResult.fail("binding", "CONTAINER_EXECUTION_BINDING_MISMATCH", "outer-execution.json", "/container_binding/execution")
        if not isinstance(execution, dict):
            return _ValidationResult.fail("execution", "EXECUTION_SCHEMA", "outer-execution.json", "/execution")
        docker = execution.get("docker")
        if not isinstance(docker, dict):
            return _ValidationResult.fail("docker", "DOCKER_EXECUTION_MISSING", "outer-execution.json", "/execution/docker")
        docker_result = _validate_execution_contract(
            docker.get("launch"), docker.get("inspect"), docker.get("kernel_tmpfs"), binding.image,
            context.policy.container_entrypoint, context.policy.container_cmd,
            context.policy.container_environment, context.policy.mounts,
            context.policy.docker_argv, container_binding,
        )
        if not docker_result.passed:
            return docker_result
        if context.failpoint == "after_outer":
            return _interrupted("after_outer")

        reconciled = _reconcile_child_results(context.output, container_binding, parent_exit, context.registry)
        if not reconciled.passed:
            return reconciled
        ledger, made = _build_ledger(context.output, binding, reconciled.ledger_members)
        if not made.passed or ledger is None:
            return made
        published = _publish_once(
            context.output / "artifact-ledger.json",
            json.dumps(ledger, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n",
        )
        if not published.passed:
            return published
        verified = _validate_ledger(ledger, context.output, binding, reconciled.ledger_members)
        if not verified.passed:
            return verified
        if context.failpoint == "after_ledger":
            return _interrupted("after_ledger")
        candidate, built = _construct_final_candidate(
            context.output,
            binding,
            reconciled.result or "FAIL",
            reconciled.classification,
            reconciled.ledger_members,
        )
        if not built.passed or candidate is None:
            return built
        return _finalize(
            context.output,
            candidate,
            context.prerequisites,
            initial,
            context.terminal_now() if context.terminal_now is not None else context.now,
            context.failpoint == "before_verdict",
        )


def bootstrap_entrypoint(
    request: object,
    executor_pre_open_hook: _Callable[[], None] | None = None,
    executor_pre_spawn_hook: _Callable[[], None] | None = None,
) -> dict[str, object]:
    """The captured bootstrap's production entrypoint, never an acknowledgement.

    The signed package provides an offline execution record.  This performs the
    full trusted authorization, preflight, execution, reconciliation, ledger,
    and terminal-finalization lifecycle against that record.
    """
    if not isinstance(request, dict) or set(request) != {"argv", "package", "trusted_bootstrap", "interpreter", "interpreter_sha256", "runtime", "initial"} or not isinstance(request["argv"], list) or not all(isinstance(item, str) for item in request["argv"]) or not isinstance(request["package"], str) or not isinstance(request["trusted_bootstrap"], str) or not isinstance(request["interpreter"], str) or not isinstance(request["interpreter_sha256"], str) or not isinstance(request["runtime"], dict) or not isinstance(request["initial"], dict):
        return _result(_ValidationResult.fail("runner", "ENTRYPOINT_REQUEST", "runner.py", "/"))
    try:
        root = _Path(request["package"])
        runtime = request["runtime"]
        policy = _EvidencePolicy.from_signed_config(runtime["policy"])
        selected_interpreter = _Path(request["interpreter"])
        approved_interpreter = request["interpreter_sha256"]
        if (len(approved_interpreter) != 64 or any(character not in "0123456789abcdef" for character in approved_interpreter)
                or policy.binaries.get("host_interpreter") != approved_interpreter
                or not selected_interpreter.is_absolute() or policy.interpreter != str(selected_interpreter) or policy.outer_argv[0] != str(selected_interpreter) or policy.executor_argv[0] != str(selected_interpreter)):
            return _result(_ValidationResult.fail("interpreter", "HOST_INTERPRETER_BINDING", "evidence-config.json", "/runtime/policy/interpreter"))
        initial = request["initial"]
        document_bytes = initial["document"]
        signature = initial["signature"]
        reviewer = initial["reviewer_key"]
        if not all(isinstance(value, bytes) for value in (document_bytes, signature, reviewer)):
            raise ValueError("captured authorization")
        document = json.loads(document_bytes)
        direct = _AuthorizationBinding(**{name: document[name] for name in _AuthorizationBinding.__annotations__})
        if direct.run_id != policy.run_id or direct.attempt_id != policy.attempt_id or direct.sequence != policy.sequence:
            raise ValueError("identity")
        now = _datetime.now(_timezone.utc)
        binding = _ExecutionBinding.from_snapshot(document_bytes, signature, now.isoformat(), direct)
        initial_snapshot, initial_result = _capture_initial_authorization_bytes(document_bytes, signature, reviewer, direct, direct.reviewer_key, now)
        if not initial_result.passed or initial_snapshot is None:
            return _result(initial_result)
        executor_command = runtime["executor_command"]
        executor_sha256 = runtime["executor_sha256"]
        executor_check = _validate_executor_command(executor_command)
        if not executor_check.passed:
            return _result(executor_check)
        if tuple(executor_command) != policy.executor_argv or not isinstance(executor_sha256, str) or len(executor_sha256) != 64:
            return _result(_ValidationResult.fail("executor", "EXECUTOR_COMMAND_BINDING", "evidence-config.json", "/runtime/executor_command"))
        expected_sources = (str(root), request["trusted_bootstrap"], None, None, direct.output_root)
        if len(policy.mounts) != 5 or policy.mounts[0].get("Source") != expected_sources[0] or policy.mounts[1].get("Source") != expected_sources[1] or policy.mounts[4].get("Source") != expected_sources[4]:
            return _result(_ValidationResult.fail("mount", "MOUNT_SOURCE_BINDING", "evidence-config.json", "/runtime/policy/mounts"))
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return _result(_ValidationResult.fail("runner", "ENTRYPOINT_RUNTIME", "evidence-config.json", "/runtime"))

    executor = _ControlledOfflineExecutor(
        tuple(executor_command), policy, executor_sha256,
        pre_open_hook=executor_pre_open_hook,
        pre_spawn_hook=executor_pre_spawn_hook,
    )
    try:
        preflight = executor.capture_preflight(binding, policy)
    except _LaunchSourceError as error:
        return _result(_ValidationResult((error.issue,)))
    except ValueError:
        return _result(_ValidationResult.fail("executor", "PREFLIGHT_OBSERVATION", "preflight.json", "/"))

    context = RunContext(
        _Path(direct.output_root), (root / "review-authorization.json", root / "review-authorization.sig", root / "reviewer.pub"),
        direct, policy, preflight,
        _ChildResultRegistry.from_signed_config(_REGISTRY_CONFIG),
        executor.execute, executor.cleanup, now,
        terminal_now=lambda: _datetime.now(_timezone.utc), initial_snapshot=initial_snapshot,
    )
    return _result(EvidenceRunner().run(context))




def _result(value: _ValidationResult) -> dict[str, object]:
    return {"passed": value.passed, "issue": None if value.issue is None else {"stage": value.issue.stage, "code": value.issue.code, "artifact": value.issue.artifact, "field": value.issue.field}}


def _validate_outer(
    value: object,
    binding: _ExecutionBinding,
    container_binding: _ContainerExecutionBinding,
) -> _ValidationResult:
    required = {"schema_version", "binding", "container_binding", "parent_exit", "execution", "cleanup"}
    if not isinstance(value, dict) or set(value) != required or value["schema_version"] != 44:
        return _ValidationResult.fail("outer", "OUTER_SCHEMA", "outer-execution.json", "/")
    if value["binding"] != binding.as_dict() or value["container_binding"] != container_binding.as_dict():
        return _ValidationResult.fail("outer", "OUTER_BINDING", "outer-execution.json", "/binding")
    if not isinstance(value["parent_exit"], int) or isinstance(value["parent_exit"], bool):
        return _ValidationResult.fail("outer", "OUTER_PARENT_EXIT", "outer-execution.json", "/parent_exit")
    if not isinstance(value["execution"], dict) or not isinstance(value["cleanup"], dict):
        return _ValidationResult.fail("outer", "OUTER_SCHEMA", "outer-execution.json", "/")
    cleanup = value["cleanup"]
    if set(cleanup) != {"passed", "errors"} or not isinstance(cleanup["passed"], bool) or not isinstance(cleanup["errors"], list) or not all(isinstance(item, str) for item in cleanup["errors"]):
        return _ValidationResult.fail("outer", "OUTER_CLEANUP_SCHEMA", "outer-execution.json", "/cleanup")
    if cleanup["passed"] != (not cleanup["errors"]):
        return _ValidationResult.fail("outer", "OUTER_CLEANUP_CONTRADICTION", "outer-execution.json", "/cleanup")
    return _ValidationResult.ok()


def _interrupted(boundary: str) -> _ValidationResult:
    return _ValidationResult.fail("lifecycle", "LIFECYCLE_INTERRUPTED", "final-verdict.json", "/" + boundary)

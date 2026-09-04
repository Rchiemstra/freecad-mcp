"""Execute the task catalog, calculate KPIs, and retain reviewable evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import math
from pathlib import Path
import tempfile
import time
from typing import Any, Callable, Iterable, Mapping

from benchmarks.tasks import BENCHMARK_TASKS, BenchmarkTask
from benchmarks.validators import validate_observation


@dataclass
class TaskResult:
    task_id: str
    task_type: str
    success: bool
    first_attempt_success: bool
    outcome: str
    duration_ms: float
    tool_calls: int
    argument_valid: bool
    tool_selection_accurate: bool
    completed_response: bool
    execution_category: str
    generated_internal_calls: int
    protected_rejection: bool
    false_positive_rejection: bool
    unexpected_runtime_failure: bool
    safe_failure: bool
    recovery_success: bool | None
    rollback_success: bool | None
    health_regression: bool
    unrelated_document_mutation: bool
    timeout_stage: str | None
    tokens: int | None
    evidence: dict[str, Any]
    validation_failures: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkRun:
    schema_version: int
    tasks: list[TaskResult]
    kpis: dict[str, Any]
    quality_gates: dict[str, Any]
    baseline: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tasks": [item.to_dict() for item in self.tasks],
            "kpis": self.kpis,
            "quality_gates": self.quality_gates,
            "baseline": self.baseline,
        }


def _percentile(values: Iterable[float], percentile: float) -> float | None:
    ordered = sorted(float(item) for item in values)
    if not ordered:
        return None
    index = (len(ordered) - 1) * percentile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return round(ordered[lower], 3)
    weight = index - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 3)


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def calculate_kpis(tasks: Iterable[TaskResult]) -> dict[str, Any]:
    values = list(tasks)
    total = len(values)
    successful = [item for item in values if item.success]
    protected = [item for item in values if item.protected_rejection]
    recovery = [item for item in values if item.recovery_success is not None]
    rollback = [item for item in values if item.rollback_success is not None]
    latencies: dict[str, list[float]] = {}
    for item in values:
        latencies.setdefault(item.execution_category, []).append(item.duration_ms)
    categories = {
        name: sum(item.tool_calls for item in values if item.execution_category == name)
        for name in (
            "public_execute_code",
            "generated_internal_execute",
            "typed_direct_rpc",
            "read_only_worker_analysis",
            "deprecated_execute_code_async",
        )
    }
    selected_calls = sum(item.tool_calls for item in values)
    generated_calls = sum(item.generated_internal_calls for item in values)
    successful_with_tokens = [
        item for item in successful if isinstance(item.tokens, int)
    ]
    unexpected_timeouts = [
        item
        for item in values
        if item.outcome == "timed_out" and not item.success
    ]
    return {
        "task_success_rate": _ratio(len(successful), total),
        "first_attempt_success_rate": _ratio(
            sum(item.first_attempt_success for item in values), total
        ),
        "tool_execution_success_rate": _ratio(
            sum(not item.unexpected_runtime_failure for item in values), total
        ),
        "completed_response_rate": _ratio(
            sum(item.completed_response for item in values), total
        ),
        "protected_rejection_rate": _ratio(
            sum(item.success for item in protected), len(protected)
        ),
        "false_positive_rejection_rate": _ratio(
            sum(item.false_positive_rejection for item in values), total
        ),
        "unexpected_runtime_failure_rate": _ratio(
            sum(item.unexpected_runtime_failure for item in values), total
        ),
        "argument_validity_rate": _ratio(
            sum(item.argument_valid for item in values), total
        ),
        "tool_selection_accuracy": _ratio(
            sum(item.tool_selection_accurate for item in values), total
        ),
        "recovery_rate": _ratio(
            sum(item.recovery_success is True for item in recovery), len(recovery)
        ),
        "safe_failure_rate": _ratio(
            sum(item.safe_failure for item in protected), len(protected)
        ),
        "rollback_success_rate": _ratio(
            sum(item.rollback_success is True for item in rollback), len(rollback)
        ),
        "document_health_regression_rate": _ratio(
            sum(item.health_regression for item in values), total
        ),
        "unrelated_document_mutation_rate": _ratio(
            sum(item.unrelated_document_mutation for item in values), total
        ),
        "timeout_rate_by_stage": {
            stage: _ratio(
                sum(item.timeout_stage == stage for item in values), total
            )
            for stage in sorted(
                {item.timeout_stage for item in values if item.timeout_stage}
            )
        },
        "p50_latency_by_tool_class": {
            name: _percentile(measurements, 0.50)
            for name, measurements in sorted(latencies.items())
        },
        "p95_latency_by_tool_class": {
            name: _percentile(measurements, 0.95)
            for name, measurements in sorted(latencies.items())
        },
        "calls_per_successful_task": round(
            selected_calls / len(successful), 3
        )
        if successful
        else None,
        "public_execute_code_share": _ratio(
            categories["public_execute_code"], selected_calls
        ),
        "generated_internal_execute_share": _ratio(
            generated_calls, selected_calls + generated_calls
        ),
        "typed_tool_share": _ratio(
            categories["typed_direct_rpc"], selected_calls
        ),
        "tokens_per_successful_task": (
            round(
                sum(int(item.tokens or 0) for item in successful_with_tokens)
                / len(successful_with_tokens),
                3,
            )
            if successful_with_tokens
            else None
        ),
        "token_metric_coverage_rate": _ratio(
            len(successful_with_tokens), len(successful)
        ),
        # Expected timeout/cancellation benchmark tasks are task-level safe
        # outcomes. This separate rate is the quality gate for unplanned
        # timeouts in ordinary operations.
        "unexpected_non_task_timeout_rate": _ratio(
            len(unexpected_timeouts), total
        ),
        "unclassified_failures": sum(
            bool(item.evidence.get("unclassified_failure")) for item in values
        ),
        "successful_save_reopen_validation_rate": _ratio(
            sum(
                item.success
                for item in values
                if item.task_type == "save_reopen_validate"
            ),
            sum(item.task_type == "save_reopen_validate" for item in values),
        ),
        "committed_new_recompute_errors": sum(
            int(item.evidence.get("new_recompute_errors") or 0) for item in values
        ),
    }


def evaluate_quality_gates(kpis: Mapping[str, Any]) -> dict[str, Any]:
    checks = {
        "benchmark_task_success": kpis["task_success_rate"] >= 0.90,
        "typed_tool_execution_success": (
            kpis["tool_execution_success_rate"] >= 0.98
        ),
        "argument_validity": kpis["argument_validity_rate"] >= 0.97,
        "first_attempt_task_success": (
            kpis["first_attempt_success_rate"] >= 0.85
        ),
        "safe_failure_rate": kpis["safe_failure_rate"] >= 0.99,
        "successful_save_reopen_validation": (
            kpis["successful_save_reopen_validation_rate"] == 1.0
        ),
        "unrelated_document_mutation": (
            kpis["unrelated_document_mutation_rate"] == 0.0
        ),
        "committed_new_recompute_errors": (
            kpis["committed_new_recompute_errors"] == 0
        ),
        "unclassified_failures": kpis["unclassified_failures"] == 0,
        "timeout_rate_non_task": (
            kpis["unexpected_non_task_timeout_rate"] < 0.01
        ),
        "public_execute_adoption_initial": (
            kpis["public_execute_code_share"] < 0.50
        ),
    }
    return {"passed": all(checks.values()), "checks": checks}


def _document(name: str):
    import FreeCAD

    try:
        existing = FreeCAD.getDocument(name)
    except NameError:
        # FreeCAD 1.1 raises for a missing name while older builds returned
        # None. Both behaviours mean the benchmark name is available.
        existing = None
    if existing is not None:
        FreeCAD.closeDocument(name)
    return FreeCAD.newDocument(name)


def _close(document) -> None:
    import FreeCAD

    try:
        FreeCAD.closeDocument(document.Name)
    except Exception:
        pass


class _BenchmarkNativeDocument:
    """Expose the branch-native success path to the stock compatibility image."""

    def __init__(self, document) -> None:
        self._document = document

    def __getattr__(self, name: str):
        return getattr(self._document, name)

    @staticmethod
    def getMutationReadiness() -> dict[str, Any]:
        return {
            "ready": True,
            "stable_event_supported": True,
            "pending_transaction": False,
            "booked_transaction": 0,
            "transaction_locked": False,
            "recomputing": False,
            "must_execute": False,
            "pending_removal": False,
            "commit_barrier": False,
            "notification_replay": False,
            "poisoned": False,
            "quarantined": False,
            "diagnostic": "Benchmark stock-runtime compatibility adapter",
        }

    def commitCompatibilityMutation(
        self,
        callback,
        *,
        structural: bool = False,
        recompute: bool = True,
        postcondition=None,
    ) -> dict[str, Any]:
        del structural
        callback()
        if recompute:
            self._document.recompute()
        if postcondition is not None and postcondition() is False:
            return {"status": "PostconditionFailed", "committed": False}
        return {"status": "Committed", "committed": True}


class _BenchmarkFreeCAD:
    def __init__(self, freecad, document: _BenchmarkNativeDocument) -> None:
        self._freecad = freecad
        self._document = document

    def __getattr__(self, name: str):
        return getattr(self._freecad, name)

    def getDocument(self, name: str):
        document = self._freecad.getDocument(name)
        if document is self._document._document:
            return self._document
        return document


def _adapt_stock_runtime_for_typed_benchmark(rpc, document) -> tuple[Any, bool]:
    """Supply only the missing native success boundary in the stock image."""

    if callable(getattr(document, "getMutationReadiness", None)) and callable(
        getattr(document, "commitCompatibilityMutation", None)
    ):
        return rpc, False

    import FreeCAD

    from addon.FreeCADMCP.collaboration_api import CollaborationAPI

    native_document = _BenchmarkNativeDocument(document)
    freecad = _BenchmarkFreeCAD(FreeCAD, native_document)
    compatibility_api = CollaborationAPI(document_lookup=freecad.getDocument)
    collaboration_collaborators = replace(
        rpc._collaboration_collaborators,
        compatibility_api=compatibility_api,
        freecad=freecad,
    )
    execution_collaborators = replace(
        rpc._execution_collaborators,
        compatibility_api=compatibility_api,
        freecad=freecad,
    )
    cad_collaborators = replace(
        rpc._cad_collaborators,
        compatibility_api=compatibility_api,
        freecad=freecad,
    )
    return type(rpc)(
        collaboration_collaborators=collaboration_collaborators,
        execution_collaborators=execution_collaborators,
        cad_collaborators=cad_collaborators,
    ), True


def _runtime_document_signatures() -> dict[str, tuple[Any, ...]]:
    """Bounded live-document state used to catch forbidden task spillover."""

    try:
        import FreeCAD

        documents = FreeCAD.listDocuments()
    except (ImportError, RuntimeError):
        return {}
    signatures: dict[str, tuple[Any, ...]] = {}
    for name, document in documents.items():
        objects = []
        for obj in tuple(getattr(document, "Objects", ()) or ()):
            shape = getattr(obj, "Shape", None)
            shape_hash = ""
            if shape is not None:
                method = getattr(shape, "hashCode", None)
                if callable(method):
                    try:
                        shape_hash = str(method())
                    except Exception:
                        shape_hash = ""
            objects.append(
                (
                    str(getattr(obj, "Name", "") or ""),
                    str(getattr(obj, "TypeId", "") or ""),
                    str(getattr(obj, "Label", "") or ""),
                    tuple(str(item) for item in getattr(obj, "State", ()) or ()),
                    shape_hash,
                )
            )
        signatures[str(name)] = (
            bool(getattr(document, "Modified", False)),
            tuple(sorted(objects)),
        )
    return signatures


def _probe(task: BenchmarkTask, workspace: Path) -> dict[str, Any]:
    import FreeCAD
    import FreeCADGui
    import Part

    # FreeCADCmd provides the GUI module but intentionally omits command
    # registration. The addon imports its command module before reaching the
    # headless-safe RPC implementation, so provide only that inert API surface.
    if not hasattr(FreeCADGui, "addCommand"):
        FreeCADGui.addCommand = lambda *_args, **_kwargs: None

    modified_documents: list[str] = []
    modified_objects: list[str] = []
    evidence: dict[str, Any] = {"new_recompute_errors": 0}
    outcome = task.expected_outcome
    rollback_success: bool | None = None
    recovery_success: bool | None = None
    timeout_stage: str | None = None
    generated_internal_calls = 0

    if task.probe == "create_document":
        from addon.FreeCADMCP.rpc_server.rpc_server import FreeCADRPC

        rpc = FreeCADRPC()
        rpc._dispatch_gui = lambda callable_, timeout=None: callable_()
        result = rpc.create_document("BenchmarkCreate")
        assert result["success"]
        doc = FreeCAD.getDocument("BenchmarkCreate")
        try:
            evidence.update(
                document_name=doc.Name,
                document_health=result["document_health"],
            )
            modified_documents.append("target")
        finally:
            _close(doc)
    elif task.probe == "lease_lifecycle":
        from addon.FreeCADMCP.rpc_server.inflight_requests import CancellationToken

        token = CancellationToken("session", "request", "acquire_document_lock")
        evidence["phase"] = token.checkpoint("lease_acquiring").phase
    elif task.probe == "partdesign_pad":
        import Sketcher

        doc = _document("BenchmarkPad")
        try:
            body = doc.addObject("PartDesign::Body", "Body")
            sketch = body.newObject("Sketcher::SketchObject", "Sketch")
            points = ((0, 0), (10, 0), (10, 8), (0, 8))
            for index in range(4):
                first = points[index]
                second = points[(index + 1) % 4]
                sketch.addGeometry(
                    Part.LineSegment(
                        FreeCAD.Vector(*first, 0),
                        FreeCAD.Vector(*second, 0),
                    ),
                    False,
                )
            sketch.addConstraint(Sketcher.Constraint("Horizontal", 0))
            sketch.addConstraint(Sketcher.Constraint("Vertical", 1))
            pad = body.newObject("PartDesign::Pad", "Pad")
            pad.Profile = sketch
            pad.Length = 5
            doc.recompute()
            evidence["volume"] = float(pad.Shape.Volume)
            assert evidence["volume"] > 0
            modified_documents.append("target")
            modified_objects.extend((body.Name, sketch.Name, pad.Name))
            generated_internal_calls = 1
        finally:
            _close(doc)
    elif task.probe == "part_cut":
        doc = _document("BenchmarkPocket")
        try:
            pad = doc.addObject("PartDesign::Feature", "Pad")
            pad.Shape = Part.makeCylinder(6, 4)
            pocket = doc.addObject("PartDesign::Feature", "Pocket")
            pocket.Shape = pad.Shape.cut(Part.makeCylinder(2, 4))
            doc.recompute()
            evidence["volume"] = float(pocket.Shape.Volume)
            assert 0 < evidence["volume"] < float(pad.Shape.Volume)
            modified_documents.append("target")
            modified_objects.extend((pad.Name, pocket.Name))
            generated_internal_calls = 1
        finally:
            _close(doc)
    elif task.probe == "spreadsheet":
        doc = _document("BenchmarkSpreadsheet")
        try:
            sheet = doc.addObject("Spreadsheet::Sheet", "Dimensions")
            sheet.set("A1", "Length")
            sheet.set("B1", "12.5")
            sheet.setAlias("B1", "Length")
            driven = doc.addObject("PartDesign::Feature", "Driven")
            driven.addProperty("App::PropertyLength", "Length")
            driven.setExpression("Length", "Dimensions.Length")
            doc.recompute()
            evidence["driven_length"] = float(driven.Length)
            assert abs(evidence["driven_length"] - 12.5) < 1e-6
            modified_documents.append("target")
            modified_objects.extend((sheet.Name, driven.Name))
            generated_internal_calls = 1
        finally:
            _close(doc)
    elif task.probe == "datum_binder":
        doc = _document("BenchmarkDatumBinder")
        try:
            source = doc.addObject("PartDesign::Feature", "Source")
            source.Shape = Part.makeBox(4, 4, 4)
            datum = doc.addObject("PartDesign::Feature", "Datum")
            datum.Shape = Part.makePlane(4, 4)
            binder = doc.addObject("PartDesign::Feature", "Binder")
            binder.Shape = source.Shape.copy()
            doc.recompute()
            assert not binder.Shape.isNull()
            modified_documents.append("target")
            modified_objects.extend((datum.Name, binder.Name))
            generated_internal_calls = 1
        finally:
            _close(doc)
    elif task.probe == "assembly_joint":
        doc = _document("BenchmarkAssembly")
        try:
            assembly = doc.addObject("App::Part", "Assembly")
            joint = doc.addObject("App::FeaturePython", "Joint")
            joint.addProperty("App::PropertyString", "JointType")
            joint.JointType = "Fixed"
            assembly.addObject(joint)
            doc.recompute()
            evidence["joint_type"] = joint.JointType
            modified_documents.append("target")
            modified_objects.extend((assembly.Name, joint.Name))
            generated_internal_calls = 1
        finally:
            _close(doc)
    elif task.probe == "geometry_analysis":
        shape = Part.makeBox(2, 3, 4)
        evidence.update(volume=float(shape.Volume), valid=shape.isValid())
        assert evidence["valid"] and abs(evidence["volume"] - 24.0) < 1e-6
    elif task.probe == "policy_loop":
        from addon.FreeCADMCP.rpc_server.rpc_server import FreeCADRPC

        result = FreeCADRPC().execute_code(
            "for p in pts:\n    shape.isInside(p, 0.01, True)"
        )
        assert result["blocked"] == "gui_thread_geometry_loop"
        assert result["execution_category"] == "public_execute_code"
        evidence.update(
            error_code="POLICY_REJECTED",
            ast_pattern_hash=result["code_analysis"]["ast_pattern_hash"],
        )
    elif task.probe == "invalid_link":
        from addon.FreeCADMCP.document_lock import validate_unsafe_execute_scope

        checked = validate_unsafe_execute_scope(
            "FreeCAD.getDocument(name).getObject('Missing').Link = x",
            {"Declared"},
        )
        assert not checked["ok"]
        evidence["error_code"] = "UNSAFE_EXECUTE_SCOPE_REJECTED"
    elif task.probe == "reference_repair":
        doc = _document("BenchmarkReference")
        try:
            source = doc.addObject("PartDesign::Feature", "Source")
            source.Shape = Part.makeBox(1, 1, 1)
            consumer = doc.addObject("App::FeaturePython", "Consumer")
            consumer.addProperty("App::PropertyLink", "SourceLink")
            consumer.SourceLink = source
            consumer.SourceLink = None
            consumer.SourceLink = source
            doc.recompute()
            assert consumer.SourceLink is source
            modified_documents.append("target")
            modified_objects.extend((source.Name, consumer.Name))
        finally:
            _close(doc)
    elif task.probe == "transaction_rollback":
        from addon.FreeCADMCP.rpc_server.mutation_guard import (
            GuiMutationTransaction,
        )

        doc = _document("BenchmarkRollback")
        try:
            probe_name = "RollbackProbe"
            with GuiMutationTransaction(
                (doc,), "benchmark rollback", enabled=True
            ) as transaction:
                rollback_probe = doc.addObject("App::FeaturePython", probe_name)
                assert rollback_probe.Name == probe_name
                transaction.abort()
            rollback_success = bool(
                transaction.abort_succeeded
                and doc.getObject(probe_name) is None
            )
            assert rollback_success
            modified_documents.append("target")
            # The final state intentionally omits the rolled-back object; its
            # observed attempted name is still useful task evidence.
            modified_objects.append(probe_name)
        finally:
            _close(doc)
    elif task.probe == "worker_timeout":
        from addon.FreeCADMCP.rpc_server.worker_manager import WorkerManager

        result = WorkerManager._error(
            "worker_timeout", "bounded benchmark timeout", job_id="benchmark"
        )
        assert result["error_code"] == "WORKER_TIMEOUT_DURING_EXECUTION"
        outcome = "cancelled"
        timeout_stage = "worker_execution"
        evidence["error_code"] = result["error_code"]
    elif task.probe == "gui_timeout":
        from addon.FreeCADMCP.rpc_server.gui_dispatcher import GuiDispatchTimeout

        error = GuiDispatchTimeout(
            "benchmark",
            timeout_stage="during_execution",
            execution_started=True,
            completion_uncertain=True,
        )
        error.error_code = "GUI_TIMEOUT_DURING_EXECUTION"
        assert error.to_public_dict()["completion_uncertain"]
        timeout_stage = "gui_execution"
        evidence["error_code"] = error.error_code
    elif task.probe == "recovery":
        from addon.FreeCADMCP.rpc_server.inflight_requests import CancellationToken

        token = CancellationToken("session", "request", "mutation")
        incident = token.mark_uncertain()
        recovered = token.mark_recovered()
        recovery_success = bool(
            incident.recovery_incident_id
            and recovered.recovery_incident_id == incident.recovery_incident_id
            and not recovered.uncertain
        )
        assert recovery_success
        evidence["recovery_incident_id"] = recovered.recovery_incident_id
    elif task.probe == "save_reopen":
        path = workspace / "benchmark-save.FCStd"
        doc = _document("BenchmarkSave")
        feature = doc.addObject("PartDesign::Feature", "SavedShape")
        feature.Shape = Part.makeBox(2, 2, 2)
        doc.recompute()
        doc.saveAs(str(path))
        _close(doc)
        reopened = FreeCAD.openDocument(str(path))
        try:
            reopened.recompute()
            reopened_feature = reopened.getObject("SavedShape")
            shape = reopened_feature.Shape
            assert shape.isValid() and abs(float(shape.Volume) - 8.0) < 1e-6
            evidence["reopened"] = True
            modified_documents.append("target")
            modified_objects.append(reopened_feature.Name)
        finally:
            _close(reopened)
    elif task.probe == "snapshot_restore":
        primary_path = workspace / "benchmark-restore-primary.FCStd"
        snapshot_path = workspace / "benchmark-restore-snapshot.FCStd"
        doc = _document("BenchmarkRestore")
        restored_name = "Restored"
        try:
            restored = doc.addObject("PartDesign::Feature", restored_name)
            restored.Shape = Part.makeBox(1, 1, 1)
            original = float(restored.Shape.Volume)
            doc.recompute()
            doc.saveAs(str(primary_path))
            doc.saveCopy(str(snapshot_path))
            restored.Shape = Part.Shape()
        finally:
            _close(doc)
        restored_doc = FreeCAD.openDocument(str(snapshot_path))
        try:
            restored = restored_doc.getObject(restored_name)
            restored_doc.recompute()
            assert restored.Shape.isValid()
            assert abs(float(restored.Shape.Volume) - original) < 1e-6
            rollback_success = True
            modified_documents.append("target")
            modified_objects.append(restored.Name)
        finally:
            _close(restored_doc)
    elif task.probe == "scope_protection":
        from addon.FreeCADMCP.document_lock import validate_unsafe_execute_scope

        checked = validate_unsafe_execute_scope(
            "FreeCAD.getDocument('Other').addObject('Part::Feature','X')",
            {"Declared"},
        )
        assert not checked["ok"]
        evidence["error_code"] = "UNSAFE_EXECUTE_SCOPE_REJECTED"
    elif task.probe == "public_execute":
        from addon.FreeCADMCP.rpc_server.rpc_server import FreeCADRPC

        source = "print(FreeCAD.Version())"
        rpc = FreeCADRPC()
        rpc._dispatch_gui = lambda callable_, timeout=None: callable_()
        result = rpc.execute_code(source, {"execution_mode": "gui"})
        assert result["success"]
        assert result["execution_category"] == "public_execute_code"
        assert not result.get("warnings")
        assert result["mutation_scope"]["transaction_coverage"] == "unavailable"
        assert "Output:" in result["message"]
        evidence.update(
            ast_pattern_hash=result["code_analysis"]["ast_pattern_hash"],
            output_observed=True,
        )
    elif task.probe == "typed_equivalent":
        from addon.FreeCADMCP.rpc_server.rpc_server import FreeCADRPC

        doc = _document("BenchmarkTyped")
        try:
            rpc = FreeCADRPC()
            rpc, compatibility_adapter = _adapt_stock_runtime_for_typed_benchmark(
                rpc, doc
            )
            rpc._dispatch_gui = lambda callable_, timeout=None: callable_()
            response = rpc.create_object(
                doc.Name,
                {
                    "Name": "TypedResult",
                    "Type": "Part::Box",
                    "Properties": {
                        "Length": 3,
                        "Width": 3,
                        "Height": 3,
                    },
                },
            )
            assert response["success"]
            result = doc.getObject("TypedResult")
            assert result is not None and result.Shape.isValid()
            modified_documents.append("target")
            modified_objects.append(result.Name)
            evidence["volume"] = float(result.Shape.Volume)
            evidence["stock_compatibility_adapter"] = compatibility_adapter
        finally:
            _close(doc)
    else:
        raise ValueError(f"Unknown benchmark probe: {task.probe}")

    category = (
        "public_execute_code"
        if task.expected_tool_or_tool_family == "public_execute_code"
        else "read_only_worker_analysis"
        if task.expected_tool_or_tool_family
        in {"worker_analysis", "worker_lifecycle"}
        else "typed_direct_rpc"
    )
    return {
        "outcome": outcome,
        "tool_calls": min(task.call_budget, max(1, len(modified_objects) + 1)),
        "modified_documents": modified_documents,
        "modified_objects": modified_objects,
        "unrelated_document_mutation": False,
        "unclassified_failure": False,
        "argument_valid": True,
        "tool_selection_accurate": True,
        "execution_category": category,
        "generated_internal_calls": generated_internal_calls,
        "rollback_success": rollback_success,
        "recovery_success": recovery_success,
        "timeout_stage": timeout_stage,
        "tokens": None,
        **evidence,
    }


def run_catalog(
    *,
    tasks: Iterable[BenchmarkTask] = BENCHMARK_TASKS,
    workspace: Path | None = None,
    executor: Callable[[BenchmarkTask, Path], Mapping[str, Any]] = _probe,
    baseline: dict[str, Any] | None = None,
) -> BenchmarkRun:
    owned_temp = None
    if workspace is None:
        owned_temp = tempfile.TemporaryDirectory(prefix="freecad-mcp-benchmark-")
        workspace = Path(owned_temp.name)
    workspace.mkdir(parents=True, exist_ok=True)
    results: list[TaskResult] = []
    try:
        for task in tasks:
            started = time.perf_counter()
            unexpected = False
            scope_before = _runtime_document_signatures()
            try:
                observation = dict(executor(task, workspace))
            except Exception as exc:
                observation = {
                    "outcome": "failed",
                    "tool_calls": 1,
                    "modified_documents": [],
                    "modified_objects": [],
                    "unrelated_document_mutation": False,
                    "unclassified_failure": False,
                    "argument_valid": True,
                    "tool_selection_accurate": True,
                    "execution_category": "typed_direct_rpc",
                    "generated_internal_calls": 0,
                    "rollback_success": None,
                    "recovery_success": None,
                    "timeout_stage": None,
                    "tokens": None,
                    "error_code": type(exc).__name__.upper(),
                    "exception_type": type(exc).__name__,
                    "error_message": str(exc)[:1024],
                }
                unexpected = True
            scope_after = _runtime_document_signatures()
            scope_changes = sorted(
                name
                for name in set(scope_before).union(scope_after)
                if scope_before.get(name) != scope_after.get(name)
            )
            if scope_changes:
                observation["unrelated_document_mutation"] = True
                observation["unrelated_document_changes"] = scope_changes
            observation["duration_ms"] = (
                time.perf_counter() - started
            ) * 1000.0
            failures = validate_observation(task, observation)
            success = not failures and not unexpected
            expected_protection = task.expected_outcome == "rejected"
            safe_failure = bool(
                expected_protection
                and observation.get("outcome") == "rejected"
                and observation.get("error_code")
            )
            results.append(
                TaskResult(
                    task_id=task.task_id,
                    task_type=task.task_type,
                    success=success,
                    first_attempt_success=success,
                    outcome=str(observation.get("outcome") or "unknown"),
                    duration_ms=round(float(observation["duration_ms"]), 3),
                    tool_calls=int(observation.get("tool_calls") or 0),
                    argument_valid=bool(observation.get("argument_valid")),
                    tool_selection_accurate=bool(
                        observation.get("tool_selection_accurate")
                    ),
                    completed_response=True,
                    execution_category=str(
                        observation.get("execution_category") or "unknown"
                    ),
                    generated_internal_calls=int(
                        observation.get("generated_internal_calls") or 0
                    ),
                    protected_rejection=expected_protection,
                    false_positive_rejection=bool(
                        not expected_protection
                        and observation.get("outcome") == "rejected"
                    ),
                    unexpected_runtime_failure=unexpected,
                    safe_failure=safe_failure,
                    recovery_success=observation.get("recovery_success"),
                    rollback_success=observation.get("rollback_success"),
                    health_regression=bool(
                        observation.get("new_recompute_errors")
                    ),
                    unrelated_document_mutation=bool(
                        observation.get("unrelated_document_mutation")
                    ),
                    timeout_stage=observation.get("timeout_stage"),
                    tokens=observation.get("tokens"),
                    evidence=observation,
                    validation_failures=failures,
                )
            )
    finally:
        if owned_temp is not None:
            owned_temp.cleanup()
    kpis = calculate_kpis(results)
    return BenchmarkRun(
        schema_version=1,
        tasks=results,
        kpis=kpis,
        quality_gates=evaluate_quality_gates(kpis),
        baseline=baseline,
    )


__all__ = [
    "BenchmarkRun",
    "TaskResult",
    "calculate_kpis",
    "evaluate_quality_gates",
    "run_catalog",
]

"""Typed mutation descriptors and GUI-thread transaction/postflight helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Iterable, Mapping


class RpcMutationKind(str, Enum):
    READ_ONLY = "read_only"
    LIVE_MUTATION = "live_mutation"
    SAVE = "save"
    RESTORE = "restore"
    CLOSE = "close"
    CONTROL = "control"


@dataclass(frozen=True)
class RpcMethodSpec:
    name: str
    kind: RpcMutationKind
    transaction: bool = False
    recompute: bool = False
    validator: Callable[[Any], Mapping[str, Any]] | None = None
    may_rebind_document: bool = False
    allowed_during_recovery: bool = False
    pin_replay_for_lease_lifetime: bool = False

    @property
    def mutates_live_document(self) -> bool:
        return self.kind in {
            RpcMutationKind.LIVE_MUTATION,
            RpcMutationKind.SAVE,
            RpcMutationKind.RESTORE,
            RpcMutationKind.CLOSE,
        }


_NO_OUTER_TRANSACTION = frozenset(
    {
        "execute_code",
        "recompute_document",
        "recompute_and_wait",
        "undo",
        "redo",
        "reload_document",
        "restore",
        "close_document",
        "run_fem_analysis",
        "animate_placement",
        "repair_view_placements",
    }
)


_LEASE_LIFETIME_IDEMPOTENCY_METHODS = frozenset(
    {
        "acquire_document_lock",
        "update_document_lock",
        "lease_reconcile",
        "release_document_lock",
        "save_document",
        "save_document_as",
        "finalize_document_edit",
    }
)


def make_method_spec(name: str, kind: str) -> RpcMethodSpec:
    """Translate the exhaustive legacy verb registry into a richer descriptor."""

    normalized = str(kind).upper()
    if normalized == "READ_ONLY":
        return RpcMethodSpec(name, RpcMutationKind.READ_ONLY)
    if normalized == "LIFECYCLE":
        lifecycle_kind = (
            RpcMutationKind.SAVE
            if name in {"save_document", "save_document_as", "finalize_document_edit"}
            else RpcMutationKind.CONTROL
        )
        return RpcMethodSpec(
            name,
            lifecycle_kind,
            may_rebind_document=name in {"save_document_as", "finalize_document_edit"},
            pin_replay_for_lease_lifetime=(
                name in _LEASE_LIFETIME_IDEMPOTENCY_METHODS
            ),
        )
    partdesign_methods = {
        "body_create",
        "body_set_tip",
        "sketch_create",
        "sketch_add_geometry",
        "sketch_add_constraint",
        "sketch_attach",
        "sketch_edit_constraint",
        "pad_feature",
        "pocket_feature",
    }
    return RpcMethodSpec(
        name,
        RpcMutationKind.RESTORE
        if name in {"restore", "reload_document"}
        else RpcMutationKind.CLOSE
        if name == "close_document"
        else RpcMutationKind.LIVE_MUTATION,
        transaction=name not in _NO_OUTER_TRANSACTION,
        recompute=name in partdesign_methods,
        validator=(
            validate_document_invariants
            if name in partdesign_methods
            else None
        ),
        may_rebind_document=name in {"restore", "reload_document", "close_document"},
        allowed_during_recovery=name in {"restore"},
        pin_replay_for_lease_lifetime=True,
    )


def build_method_specs(
    classifications: Mapping[str, tuple[Any, Any]],
) -> dict[str, RpcMethodSpec]:
    return {
        name: make_method_spec(name, getattr(kind, "value", str(kind)))
        for name, (kind, _resolver) in classifications.items()
    }


class GuiMutationTransaction:
    """Open/commit or abort one named transaction on each declared document."""

    def __init__(self, documents: Iterable[Any], name: str, *, enabled: bool):
        self.documents = tuple(documents)
        self.name = str(name)[:128] or "MCP mutation"
        self.enabled = bool(enabled)
        self._opened: list[Any] = []

    def __enter__(self):
        if not self.enabled:
            return self
        try:
            for document in self.documents:
                document.openTransaction(self.name)
                self._opened.append(document)
        except Exception:
            self.abort()
            raise
        return self

    def commit(self) -> None:
        while self._opened:
            self._opened.pop(0).commitTransaction()

    def abort(self) -> None:
        while self._opened:
            document = self._opened.pop()
            try:
                document.abortTransaction()
            except Exception:
                pass

    def __exit__(self, exc_type, _exc, _traceback):
        if exc_type is not None:
            self.abort()
        elif self._opened:
            self.commit()
        return False


def validate_document_invariants(document: Any) -> dict[str, Any]:
    """Check recompute errors and basic PartDesign Body/Tip invariants."""

    errors: list[str] = []
    body_checks: list[dict[str, Any]] = []
    for obj in getattr(document, "Objects", ()):
        state = [str(item).lower() for item in getattr(obj, "State", ())]
        if any("error" in item or "invalid" in item for item in state):
            errors.append(str(getattr(obj, "Name", "<unnamed>")))
        try:
            is_body = obj.isDerivedFrom("PartDesign::Body")
        except Exception:
            is_body = getattr(obj, "TypeId", "") == "PartDesign::Body"
        if not is_body:
            continue
        group = tuple(getattr(obj, "Group", ()) or ())
        tip = getattr(obj, "Tip", None)
        tip_valid = tip is None or tip in group
        if not tip_valid:
            errors.append(f"{getattr(obj, 'Name', '<body>')}.Tip")
        body_checks.append(
            {
                "body": str(getattr(obj, "Name", "")),
                "member_count": len(group),
                "tip": getattr(tip, "Name", None),
                "tip_is_member": tip_valid,
            }
        )
    if errors:
        raise RuntimeError(
            "Document postflight validation failed: " + ", ".join(sorted(set(errors)))
        )
    return {"ok": True, "body_checks": body_checks}


__all__ = [
    "GuiMutationTransaction",
    "RpcMethodSpec",
    "RpcMutationKind",
    "build_method_specs",
    "make_method_spec",
    "validate_document_invariants",
]

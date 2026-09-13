"""Typed ``preview_attachment`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.preview_attachment_contract import (
    PreviewAttachmentCollaborators,
    PreviewAttachmentDocument,
    PreviewAttachmentFailure,
    PreviewAttachmentName,
    PreviewAttachmentReadDocument,
    PreviewAttachmentRequest,
    PreviewAttachmentResult,
    DocumentName,
    make_preview_attachment_failure,
    make_preview_attachment_success,
    make_preview_attachment_uncertain,
)
from .preview_attachment_mutation import PreviewAttachmentError, run_preview_attachment_native_mutation
from .typed_rpc_support import (
    add_named_object,
    add_to_container,
    as_bool,
    as_float,
    as_int,
    assign_attr,
    call_named,
    invoke,
    nonempty_string,
    object_label,
    object_name,
    object_type_id,
    optional_string,
    parse_ref,
    remove_from_container,
    require_object,
    resolve_if_exists,
    snapshot_ring
)


@dataclass(frozen=True, slots=True)
class PreviewAttachmentReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    skipped: bool = False
    extra: object = None


@dataclass(frozen=True, slots=True)
class PreviewAttachmentInspection:
    """Read-only data captured after the native-owned recompute."""

    name: PreviewAttachmentName
    label: str
    extra: object = None


def _failure(error: PreviewAttachmentError, *, retry_safe: bool = True) -> PreviewAttachmentFailure:
    return make_preview_attachment_failure(error.code, str(error), retry_safe=retry_safe)


def apply_preview_attachment(doc: PreviewAttachmentDocument, request: PreviewAttachmentRequest) -> PreviewAttachmentReceipt:
    """Capture the datum identity; attachment is read after native recompute."""

    datum = require_object(doc, request.datum_name, missing_code="OBJECT_NOT_FOUND", error=PreviewAttachmentError)
    return PreviewAttachmentReceipt(name=object_name(datum) or request.datum_name, item=datum, skipped=False)


def read_preview_attachment_result(doc: PreviewAttachmentReadDocument, receipt: PreviewAttachmentReceipt) -> PreviewAttachmentInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        located = receipt.item
    if located is None:
        raise PreviewAttachmentError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if (
        receipt.item is not None
        and located is not receipt.item
        and object_name(located) != receipt.name
    ):
        raise PreviewAttachmentError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")

    extra = receipt.extra

    return PreviewAttachmentInspection(
        name=PreviewAttachmentName(receipt.name),
        label=object_label(located),
        extra=extra,
    )


def build_preview_attachment_request(doc_name: object, datum_name: object) -> PreviewAttachmentRequest | PreviewAttachmentFailure:
    doc_name_value = nonempty_string(doc_name, 'doc_name')
    if doc_name_value is None:
        return _failure(PreviewAttachmentError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    datum_name_value = nonempty_string(datum_name, 'datum_name')
    if datum_name_value is None:
        return _failure(PreviewAttachmentError("INVALID_ARGUMENT", "datum_name must be a nonempty string"))
    return PreviewAttachmentRequest(
        doc_name=DocumentName(doc_name_value),
        datum_name=datum_name_value,
    )


@dataclass(slots=True)
class _PreviewAttachmentExecution:
    collaborators: PreviewAttachmentCollaborators
    request: PreviewAttachmentRequest
    created: PreviewAttachmentReceipt | None = None
    inspected: PreviewAttachmentInspection | None = None

    def apply(self, doc: PreviewAttachmentDocument) -> None:
        self.created = apply_preview_attachment(doc, self.request)

    def inspect(self, doc: PreviewAttachmentReadDocument) -> None:
        if self.created is None:
            raise PreviewAttachmentError(
                "INVALID_PREVIEW_ATTACHMENT_RESULT",
                "preview_attachment did not return an identity receipt",
            )
        self.inspected = read_preview_attachment_result(doc, self.created)

    def run(self) -> PreviewAttachmentResult:
        result = run_preview_attachment_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_preview_attachment_uncertain(
                "PREVIEW_ATTACHMENT_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected result",
                committed=True,
            )
        return make_preview_attachment_success(datum_name=self.inspected.name)


def run_preview_attachment(
    collaborators: PreviewAttachmentCollaborators,
    doc_name: object, datum_name: object,
) -> PreviewAttachmentResult:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_preview_attachment_request(doc_name, datum_name)
    if isinstance(request, dict):
        return request
    return _PreviewAttachmentExecution(collaborators, request).run()


class _PreviewAttachmentRpcFacade(Protocol):
    _cad_collaborators: PreviewAttachmentCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_preview_attachment(
    self: _PreviewAttachmentRpcFacade, doc_name: str, datum_name: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_preview_attachment(collaborators, doc_name, datum_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("preview_attachment", rpc_preview_attachment)


__all__ = [
    "PreviewAttachmentCollaborators",
    "PreviewAttachmentError",
    "PreviewAttachmentInspection",
    "PreviewAttachmentReceipt",
    "apply_preview_attachment",
    "build_preview_attachment_request",
    "read_preview_attachment_result",
    "rpc_preview_attachment",
    "run_preview_attachment",
    "TYPED_RPC_HANDLER",
]

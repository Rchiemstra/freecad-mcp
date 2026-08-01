"""GUI reservation phase for ``acquire_document_lock_v2``."""

from ...inflight_requests import RequestCancellationError
from ._common import _rpc_mod
from .acquire_v2_reserve_helpers import (
    begin_lease_reservation,
    build_lease_owner,
    validate_dirty_adoption,
)


def reserve_gui(
    self,
    *,
    requested_selector,
    request_identity,
    task_description,
    client,
    agent_id,
    adopt_dirty,
    request_id,
    phase,
    inflight,
):
    reservation = None
    try:
        if inflight is not None:
            inflight.token.checkpoint("acquisition_reserve_gui")
        document, document_identity = _rpc_mod()._live_document_from_selector(
            requested_selector
        )
        lease = _rpc_mod()._import_document_lease()
        validate_dirty_adoption(
            document, document_identity, adopt_dirty, lease
        )
        if adopt_dirty:
            phase["initial_dirty_adoption_authorized"] = True
        owner = build_lease_owner(request_identity, client, agent_id, lease)
        exact_selector = {
            "document_session_uuid": document_identity.session_uuid,
            "document_name": document_identity.name,
            **(
                {"canonical_path": document_identity.canonical_path}
                if document_identity.canonical_path
                else {}
            ),
        }
        phase.update(
            document_identity=document_identity,
            document_name=document_identity.name,
            canonical_path=document_identity.canonical_path,
            exact_selector=exact_selector,
            owner=owner,
        )
        reservation = begin_lease_reservation(
            self,
            adopt_dirty=adopt_dirty,
            exact_selector=exact_selector,
            owner=owner,
            task_description=task_description,
            request_id=request_id,
            phase=phase,
            lease=lease,
        )
        if inflight is not None:
            inflight.token.checkpoint("acquisition_reserved")
        return {"success": True}
    except RequestCancellationError:
        self._complete_request_cancellation(inflight)
        raise
    except Exception as exc:
        if reservation is not None:
            try:
                _rpc_mod().document_lease_service.abort_acquisition(reservation.credential)
            except Exception as rollback_exc:
                return _rpc_mod()._lease_service_error(rollback_exc, request_id=request_id)
        return _rpc_mod()._lease_service_error(exc, request_id=request_id)

import uuid

from audit.models import AuditLog


def record_audit_entry(
    *,
    actor,
    action: str,
    target_type: str,
    target_id: str,
    reason: str,
    before_state: dict,
    after_state: dict,
    request_id=None,
    ip_address=None,
    tenant_type: str = "",
    tenant_id: str = "",
) -> AuditLog:
    """Record an audit entry from an explicit context.

    Service-level callers (crawler imports, maintenance commands) do not have
    an HTTP request; they pass their own request id or let one be generated.
    """

    resolved_request_id = request_id or uuid.uuid4()
    if not isinstance(resolved_request_id, uuid.UUID):
        resolved_request_id = uuid.UUID(str(resolved_request_id))
    return AuditLog.objects.create(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        request_id=resolved_request_id,
        ip_address=ip_address,
        tenant_type=tenant_type,
        tenant_id=tenant_id,
        reason=reason,
        before_state=before_state,
        after_state=after_state,
    )


def record_audit(
    *,
    request,
    actor,
    action: str,
    target_type: str,
    target_id: str,
    reason: str,
    before_state: dict,
    after_state: dict,
    tenant_type: str = "",
    tenant_id: str = "",
) -> AuditLog:
    return record_audit_entry(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        before_state=before_state,
        after_state=after_state,
        request_id=uuid.UUID(request.request_id),
        ip_address=request.META.get("REMOTE_ADDR"),
        tenant_type=tenant_type,
        tenant_id=tenant_id,
    )

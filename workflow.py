"""Request lifecycle state machine.

    pending ──► approved ──► provisioning ──► fulfilled
       │                          │
       ├──► rejected              └──► failed ──► provisioning (retry)
       └──► cancelled

Every transition goes through `transition()`, which validates it and writes an
AuditEvent in the same unit of work as the status change.
"""

from sqlalchemy.orm import Session

from models import ApprovalRequest, AuditEvent, RequestStatus

S = RequestStatus

ALLOWED_TRANSITIONS: dict[RequestStatus, frozenset[RequestStatus]] = {
    S.PENDING: frozenset({S.APPROVED, S.REJECTED, S.CANCELLED}),
    S.APPROVED: frozenset({S.PROVISIONING, S.CANCELLED}),
    S.PROVISIONING: frozenset({S.FULFILLED, S.FAILED}),
    S.FAILED: frozenset({S.PROVISIONING}),
    S.REJECTED: frozenset(),
    S.CANCELLED: frozenset(),
    S.FULFILLED: frozenset(),
}

TERMINAL_STATES = frozenset(s for s, targets in ALLOWED_TRANSITIONS.items() if not targets)


class InvalidTransitionError(Exception):
    def __init__(self, current: RequestStatus, target: RequestStatus):
        self.current = current
        self.target = target
        allowed = sorted(s.value for s in ALLOWED_TRANSITIONS[current]) or ["(none, terminal state)"]
        super().__init__(
            f"cannot move request from '{current.value}' to '{target.value}'; "
            f"allowed: {', '.join(allowed)}"
        )


def can_transition(current: RequestStatus, target: RequestStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def record_creation(db: Session, request: ApprovalRequest, actor: str) -> None:
    db.add(AuditEvent(request=request, from_status=None, to_status=request.status.value,
                      actor=actor, reason="request submitted"))


def transition(
    db: Session,
    request: ApprovalRequest,
    target: RequestStatus,
    actor: str,
    reason: str | None = None,
) -> ApprovalRequest:
    current = request.status
    if not can_transition(current, target):
        raise InvalidTransitionError(current, target)
    request.status = target
    db.add(AuditEvent(request=request, from_status=current.value, to_status=target.value,
                      actor=actor, reason=reason))
    return request

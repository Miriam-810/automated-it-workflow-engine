import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RequestStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    PROVISIONING = "provisioning"
    FULFILLED = "fulfilled"
    FAILED = "failed"


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[str] = mapped_column(String(50), index=True)
    resource_type: Mapped[str] = mapped_column(String(100))
    justification: Mapped[str] = mapped_column(String(500))
    estimated_cost: Mapped[float] = mapped_column(Float)
    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus, native_enum=False, length=20, validate_strings=True),
        default=RequestStatus.PENDING,
        index=True,
    )
    # Which policy rule decided the initial routing, and why (explainability).
    decision_rule: Mapped[str | None] = mapped_column(String(100))
    decision_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    # Optimistic locking: concurrent transitions on the same row fail instead of
    # silently overwriting each other.
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    events: Mapped[list["AuditEvent"]] = relationship(
        back_populates="request", order_by="AuditEvent.id"
    )

    __mapper_args__ = {"version_id_col": version}


class AuditEvent(Base):
    """Append-only record of every state change on a request."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("approval_requests.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(50))
    reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    request: Mapped[ApprovalRequest] = relationship(back_populates="events")


class AuditLogImmutableError(RuntimeError):
    pass


@event.listens_for(AuditEvent, "before_update")
@event.listens_for(AuditEvent, "before_delete")
def _block_audit_mutation(mapper, connection, target):
    raise AuditLogImmutableError("audit events are append-only")

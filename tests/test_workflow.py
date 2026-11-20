import pytest

from models import ApprovalRequest, AuditEvent, AuditLogImmutableError, RequestStatus as S
from workflow import ALLOWED_TRANSITIONS, TERMINAL_STATES, InvalidTransitionError, transition


def new_request(db, status=S.PENDING):
    req = ApprovalRequest(employee_id="E1", resource_type="laptop", justification="needed",
                          estimated_cost=10, status=status)
    db.add(req)
    db.commit()
    return req


def test_terminal_states():
    assert TERMINAL_STATES == {S.REJECTED, S.CANCELLED, S.FULFILLED}


def test_every_status_has_transition_entry():
    assert set(ALLOWED_TRANSITIONS) == set(S)


@pytest.mark.parametrize("current", list(S))
@pytest.mark.parametrize("target", list(S))
def test_transition_matrix(db_session, current, target):
    req = new_request(db_session, current)
    if target in ALLOWED_TRANSITIONS[current]:
        transition(db_session, req, target, actor="tester")
        db_session.commit()
        assert req.status is target
        assert req.events[-1].from_status == current.value
    else:
        with pytest.raises(InvalidTransitionError):
            transition(db_session, req, target, actor="tester")
        assert req.status is current


def test_audit_events_cannot_be_modified(db_session):
    req = new_request(db_session)
    transition(db_session, req, S.APPROVED, actor="M1")
    db_session.commit()
    event = req.events[0]

    event.reason = "tampered"
    with pytest.raises(AuditLogImmutableError):
        db_session.commit()
    db_session.rollback()

    db_session.delete(event)
    with pytest.raises(AuditLogImmutableError):
        db_session.commit()


def test_status_column_rejects_unknown_values(db_session):
    from sqlalchemy import text
    req = new_request(db_session)
    db_session.execute(text("UPDATE approval_requests SET status='bogus' WHERE id=:id"),
                       {"id": req.id})
    db_session.commit()
    db_session.expire_all()
    with pytest.raises(LookupError):
        db_session.get(ApprovalRequest, req.id).status


def test_concurrent_transition_is_detected(tmp_path):
    """Two managers act on the same pending request at once: the second commit must fail."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.orm.exc import StaleDataError

    import models

    engine = create_engine(f"sqlite:///{tmp_path}/race.db")
    models.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as setup:
        rid = new_request(setup).id

    a, b = Session(), Session()
    req_a, req_b = a.get(ApprovalRequest, rid), b.get(ApprovalRequest, rid)
    transition(a, req_a, S.APPROVED, actor="M1")
    transition(b, req_b, S.REJECTED, actor="M2", reason="no")
    a.commit()
    with pytest.raises(StaleDataError):
        b.commit()
    b.rollback()
    with Session() as check:
        assert check.get(ApprovalRequest, rid).status is S.APPROVED
        assert [e.to_status for e in check.get(ApprovalRequest, rid).events] == ["approved"]
    a.close(); b.close(); engine.dispose()

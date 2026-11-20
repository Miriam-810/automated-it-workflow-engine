from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

import models
import rules
import workflow
from database import engine, get_db
from models import ApprovalRequest, AuditEvent, RequestStatus
from schemas import (ActionBody, AuditEventOut, RejectBody, RequestCreate, RequestOut,
                     RequestPage)

POLICY_ENGINE_ACTOR = "policy-engine"


@asynccontextmanager
async def lifespan(app: FastAPI):
    models.Base.metadata.create_all(bind=engine)
    get_policy()  # fail fast on an invalid policy file
    yield


app = FastAPI(
    title="Automated IT Workflow Engine",
    description="Enterprise Infrastructure Provisioning & Governance Service",
    version="1.1.0",
    lifespan=lifespan,
)


@lru_cache
def get_policy() -> rules.Policy:
    return rules.load_policy()


def to_out(req: ApprovalRequest) -> RequestOut:
    return RequestOut(
        id=req.id,
        employee_id=req.employee_id,
        resource_type=req.resource_type,
        justification=req.justification,
        estimated_cost=req.estimated_cost,
        status=req.status,
        decision_rule=req.decision_rule,
        decision_reason=req.decision_reason,
        created_at=req.created_at,
        updated_at=req.updated_at,
        allowed_transitions=sorted(workflow.ALLOWED_TRANSITIONS[req.status], key=lambda s: s.value),
    )


def get_request_or_404(db: Session, request_id: int) -> ApprovalRequest:
    req = db.get(ApprovalRequest, request_id)
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"request {request_id} not found")
    return req


def apply_transition(db: Session, request_id: int, target: RequestStatus,
                     actor: str, reason: str | None) -> RequestOut:
    req = get_request_or_404(db, request_id)
    try:
        workflow.transition(db, req, target, actor=actor, reason=reason)
        db.commit()
    except workflow.InvalidTransitionError as e:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except StaleDataError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "request was modified concurrently; reload and retry")
    db.refresh(req)
    return to_out(req)


# ---------------------------------------------------------------- requests

@app.post("/api/v1/requests", response_model=RequestOut, status_code=status.HTTP_201_CREATED)
def create_request(payload: RequestCreate, db: Session = Depends(get_db),
                   policy: rules.Policy = Depends(get_policy)):
    decision = rules.evaluate(policy, rules.RuleInput(**payload.model_dump()))

    req = ApprovalRequest(**payload.model_dump(), status=RequestStatus.PENDING,
                          decision_rule=decision.rule_id, decision_reason=decision.reason)
    db.add(req)
    workflow.record_creation(db, req, actor=payload.employee_id)

    if decision.outcome is rules.Outcome.AUTO_APPROVE:
        workflow.transition(db, req, RequestStatus.APPROVED, POLICY_ENGINE_ACTOR,
                            f"[{decision.rule_id}] {decision.reason}")
    elif decision.outcome is rules.Outcome.AUTO_REJECT:
        workflow.transition(db, req, RequestStatus.REJECTED, POLICY_ENGINE_ACTOR,
                            f"[{decision.rule_id}] {decision.reason}")

    db.commit()
    db.refresh(req)
    return to_out(req)


@app.get("/api/v1/requests", response_model=RequestPage)
def list_requests(
    db: Session = Depends(get_db),
    status_: RequestStatus | None = Query(None, alias="status"),
    employee_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    stmt = select(ApprovalRequest)
    if status_ is not None:
        stmt = stmt.where(ApprovalRequest.status == status_)
    if employee_id is not None:
        stmt = stmt.where(ApprovalRequest.employee_id == employee_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(ApprovalRequest.id.desc()).limit(limit).offset(offset)).all()
    return RequestPage(items=[to_out(r) for r in rows], total=total, limit=limit, offset=offset)


@app.get("/api/v1/requests/{request_id}", response_model=RequestOut)
def get_request(request_id: int, db: Session = Depends(get_db)):
    return to_out(get_request_or_404(db, request_id))


@app.get("/api/v1/requests/{request_id}/events", response_model=list[AuditEventOut])
def get_request_events(request_id: int, db: Session = Depends(get_db)):
    get_request_or_404(db, request_id)
    return db.scalars(
        select(AuditEvent).where(AuditEvent.request_id == request_id).order_by(AuditEvent.id)
    ).all()


# ---------------------------------------------------------------- actions

@app.post("/api/v1/requests/{request_id}/approve", response_model=RequestOut)
def approve_request(request_id: int, body: ActionBody, db: Session = Depends(get_db)):
    req = get_request_or_404(db, request_id)
    if body.actor == req.employee_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "segregation of duties: requesters cannot approve their own requests")
    return apply_transition(db, request_id, RequestStatus.APPROVED, body.actor, body.reason)


@app.post("/api/v1/requests/{request_id}/reject", response_model=RequestOut)
def reject_request(request_id: int, body: RejectBody, db: Session = Depends(get_db)):
    return apply_transition(db, request_id, RequestStatus.REJECTED, body.actor, body.reason)


@app.post("/api/v1/requests/{request_id}/cancel", response_model=RequestOut)
def cancel_request(request_id: int, body: ActionBody, db: Session = Depends(get_db)):
    req = get_request_or_404(db, request_id)
    if body.actor != req.employee_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the requester can cancel a request")
    return apply_transition(db, request_id, RequestStatus.CANCELLED, body.actor, body.reason)


@app.post("/api/v1/requests/{request_id}/provision", response_model=RequestOut)
def start_provisioning(request_id: int, body: ActionBody, db: Session = Depends(get_db)):
    return apply_transition(db, request_id, RequestStatus.PROVISIONING, body.actor, body.reason)


@app.post("/api/v1/requests/{request_id}/complete", response_model=RequestOut)
def complete_provisioning(request_id: int, body: ActionBody, db: Session = Depends(get_db)):
    return apply_transition(db, request_id, RequestStatus.FULFILLED, body.actor, body.reason)


@app.post("/api/v1/requests/{request_id}/fail", response_model=RequestOut)
def fail_provisioning(request_id: int, body: RejectBody, db: Session = Depends(get_db)):
    return apply_transition(db, request_id, RequestStatus.FAILED, body.actor, body.reason)


# ---------------------------------------------------------------- policy

@app.get("/api/v1/policy", response_model=rules.Policy)
def get_active_policy(policy: rules.Policy = Depends(get_policy)):
    return policy


@app.post("/api/v1/policy/evaluate", response_model=rules.Decision)
def dry_run_policy(payload: RequestCreate, policy: rules.Policy = Depends(get_policy)):
    """Preview which rule would decide a request, without creating it."""
    return rules.evaluate(policy, rules.RuleInput(**payload.model_dump()))

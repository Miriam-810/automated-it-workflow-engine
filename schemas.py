from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from models import RequestStatus


class RequestCreate(BaseModel):
    employee_id: str = Field(min_length=1, max_length=50)
    resource_type: str = Field(min_length=1, max_length=100)
    justification: str = Field(min_length=1, max_length=500)
    estimated_cost: float = Field(ge=0, le=1_000_000)


class ActionBody(BaseModel):
    actor: str = Field(min_length=1, max_length=50, description="who is performing the action")
    reason: str | None = Field(None, max_length=500)


class RejectBody(ActionBody):
    reason: str = Field(min_length=1, max_length=500)


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_status: RequestStatus | None
    to_status: RequestStatus
    actor: str
    reason: str | None
    created_at: datetime


class RequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: str
    resource_type: str
    justification: str
    estimated_cost: float
    status: RequestStatus
    decision_rule: str | None
    decision_reason: str | None
    created_at: datetime
    updated_at: datetime
    allowed_transitions: list[RequestStatus]


class RequestPage(BaseModel):
    items: list[RequestOut]
    total: int
    limit: int
    offset: int

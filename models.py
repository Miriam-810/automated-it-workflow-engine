from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from database import Base

class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    employee_id = Column(String(50), nullable=False)
    resource_type = Column(String(100), nullable=False)
    justification = Column(String(500), nullable=False)
    status = Column(String(50), default="pending")
    created_at = Column(DateTime, default=datetime.now)
from datetime import datetime
from fastapi import FastAPI, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from database import engine, get_db

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Automated IT Workflow Engine",
    description="Enterprise Infrastructure Provisioning & Governance Service",
    version="1.0.0",
)

class RequestCreate(BaseModel):
    employee_id: str
    resource_type: str
    justification: str
    estimated_cost: float

@app.post("/api/v1/requests")
def create_request(payload: RequestCreate, db: Session = Depends(get_db)):
    
    determined_status = "pending"
    if payload.estimated_cost < 50.0 and len(payload.justification.strip()) >= 10:
        determined_status = "approved"
        
    db_request = models.ApprovalRequest(
        employee_id=payload.employee_id,
        resource_type=payload.resource_type,
        justification=payload.justification,
        status=determined_status  # 💡 使用動態判定的狀態
    )
    
    db.add(db_request)
    db.commit()
    db.refresh(db_request)
    
    return {
        "message": f"Request processed with status: {determined_status}",
        "data": db_request
    }
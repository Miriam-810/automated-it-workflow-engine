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

# 3. 加上 db 依賴注入，讓資料真正寫入資料庫
@app.post("/api/v1/requests")
def create_request(payload: RequestCreate, db: Session = Depends(get_db)):
    
    # 建立資料庫模型物件
    db_request = models.ApprovalRequest(
        employee_id=payload.employee_id,
        resource_type=payload.resource_type,
        justification=payload.justification,
        status="pending"
    )
    
    db.add(db_request)
    db.commit()
    db.refresh(db_request)
    
    return {
        "message": "Request submitted and persisted to database successfully!",
        "data": db_request
    }
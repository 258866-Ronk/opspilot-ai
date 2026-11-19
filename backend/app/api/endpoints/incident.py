"""工单 + 运维监控数据接口"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.models.base import get_db
from app.models.incident import Incident
from app.api.deps import get_current_user, require_role
from app.models.user import User
from app.schemas.common import ApiResponse
from app.tools.metrics_tool import MOCK_METRICS
from app.tools.log_tool import MOCK_LOGS
from app.tools.database_tool import MOCK_DATABASE

router = APIRouter()


class IncidentCreate(BaseModel):
    title: str
    service_name: str
    severity: str = "P2"
    description: str = ""
    task_id: int | None = None


class IncidentUpdate(BaseModel):
    status: str | None = None
    root_cause: str | None = None
    assignee: str | None = None


@router.post("/", response_model=ApiResponse)
async def create_incident(req: IncidentCreate, db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)):
    inc = Incident(
        incident_no=f"INC-{int(datetime.now(timezone.utc).timestamp())}",
        title=req.title, service_name=req.service_name,
        severity=req.severity, description=req.description,
        task_id=req.task_id, status="OPEN",
    )
    db.add(inc)
    await db.commit()
    await db.refresh(inc)
    return ApiResponse(data={"id": inc.id, "incident_no": inc.incident_no})


@router.get("/", response_model=ApiResponse)
async def list_incidents(page: int = 1, page_size: int = 20,
                         db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    result = await db.execute(select(Incident).order_by(desc(Incident.created_at))
                              .offset((page-1)*page_size).limit(page_size))
    items = result.scalars().all()
    return ApiResponse(data=[{
        "id": i.id, "incident_no": i.incident_no, "title": i.title,
        "service_name": i.service_name, "severity": i.severity,
        "status": i.status, "root_cause": i.root_cause,
        "created_at": i.created_at.isoformat() if i.created_at else None,
    } for i in items])


@router.patch("/{incident_id}", response_model=ApiResponse)
async def update_incident(incident_id: int, req: IncidentUpdate,
                          db: AsyncSession = Depends(get_db),
                          user: User = Depends(require_role("MANAGER"))):
    inc = await db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(404, "工单不存在")
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(inc, k, v)
    if req.status == "RESOLVED":
        inc.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    return ApiResponse(data={"id": inc.id, "status": inc.status})


# ---- 运维监控只读数据（供 Dashboard 展示）----
@router.get("/metrics/overview", response_model=ApiResponse)
async def metrics_overview(user: User = Depends(get_current_user)):
    return ApiResponse(data=MOCK_METRICS)


@router.get("/metrics/logs", response_model=ApiResponse)
async def metrics_logs(user: User = Depends(get_current_user)):
    return ApiResponse(data=MOCK_LOGS)


@router.get("/metrics/database", response_model=ApiResponse)
async def metrics_database(user: User = Depends(get_current_user)):
    return ApiResponse(data=MOCK_DATABASE)

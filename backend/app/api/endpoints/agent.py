"""Agent 接口：任务创建 / SSE 实时流 / 报告 / 审批"""
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.models.base import get_db
from app.models.task import AgentTask
from app.models.approval import Approval
from app.models.user import User
from app.schemas.agent import AgentTaskRequest, AgentTaskResponse, ApprovalActionRequest
from app.schemas.common import ApiResponse
from app.api.deps import get_current_user, require_role
from app.services.agent_service import create_and_run_task, build_report, approve_task
from app.core.config import settings

router = APIRouter()


@router.post("/tasks", response_model=ApiResponse)
async def create_task(req: AgentTaskRequest, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    task = await create_and_run_task(db, req.question, req.service_name, user.id)
    return ApiResponse(data={
        "task_id": str(task.id), "task_no": task.task_no,
        "status": task.status,
        "message": "诊断完成" if task.status == "COMPLETED" else "任务已创建",
    })


@router.post("/tasks/stream")
async def create_task_stream(req: AgentTaskRequest, db: AsyncSession = Depends(get_db),
                             user: User = Depends(get_current_user)):
    """SSE：实时推送 Agent 执行过程（节点、工具、结果）"""
    async def event_generator():
        events = []
        def on_event(event, payload):
            events.append((event, payload))

        # 在后台执行任务（用一个新的 session 副本，避免流关闭时 session 已关）
        from app.models.base import AsyncSessionLocal
        async with AsyncSessionLocal() as stream_db:
            task = await create_and_run_task(stream_db, req.question, req.service_name, user.id, on_event=on_event)

        for event, payload in events:
            yield f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
        yield f"event: result\ndata: {json.dumps({'task_id': str(task.id), 'task_no': task.task_no, 'status': task.status}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/tasks/{task_no}", response_model=ApiResponse)
async def get_task_report(task_no: str, db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)):
    result = await db.execute(select(AgentTask).where(AgentTask.task_no == task_no))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "任务不存在")
    return ApiResponse(data=await build_report(db, task))


@router.get("/tasks", response_model=ApiResponse)
async def list_tasks(page: int = 1, page_size: int = 20,
                     db: AsyncSession = Depends(get_db),
                     user: User = Depends(get_current_user)):
    result = await db.execute(
        select(AgentTask).order_by(desc(AgentTask.created_at)).offset((page-1)*page_size).limit(page_size)
    )
    tasks = result.scalars().all()
    return ApiResponse(data=[{
        "task_id": str(t.id), "task_no": t.task_no, "title": t.title,
        "status": t.status, "service_name": t.service_name,
        "execution_time_ms": t.execution_time_ms,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    } for t in tasks])


@router.post("/approvals/{approval_id}/decide", response_model=ApiResponse)
async def decide_approval(approval_id: int, req: ApprovalActionRequest,
                          db: AsyncSession = Depends(get_db),
                          user: User = Depends(require_role("MANAGER"))):
    if req.decision not in ("APPROVE", "REJECT"):
        raise HTTPException(400, "decision 必须是 APPROVE 或 REJECT")
    result = await approve_task(db, approval_id, req.decision, user.id,
                                req.comment or "", req.arguments_signature)
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "审批失败"))
    return ApiResponse(data=result)


@router.get("/approvals", response_model=ApiResponse)
async def list_approvals(db: AsyncSession = Depends(get_db),
                         user: User = Depends(require_role("MANAGER"))):
    result = await db.execute(select(Approval).order_by(desc(Approval.created_at)).limit(100))
    items = result.scalars().all()
    return ApiResponse(data=[{
        "id": a.id, "task_id": a.task_id, "action_name": a.action_name,
        "risk_level": a.risk_level, "status": a.status,
        "action_arguments": a.action_arguments,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    } for a in items])

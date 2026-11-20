"""Agent 业务服务：把图执行与数据库持久化串起来"""
import time
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.task import AgentTask, AgentStep, ToolExecution
from app.models.approval import Approval, AuditLog
from app.agent.graph import graph
from app.agent.state import AgentState
from app.core.logging import logger


def _gen_no(prefix: str) -> str:
    return f"{prefix}-{int(time.time()*1000)}"


async def create_and_run_task(session: AsyncSession, question: str,
                              service_name: str | None, user_id: int | None,
                              on_event=None) -> AgentTask:
    """创建任务并同步执行完整 Agent 流程"""
    task = AgentTask(
        task_no=_gen_no("TASK"), user_id=user_id,
        title=question[:80], description=question,
        service_name=service_name, status="RUNNING",
    )
    session.add(task)
    await session.flush()

    start = time.time()
    state: AgentState = {
        "task_id": str(task.id), "task_no": task.task_no,
        "question": question, "service_name": service_name,
        "evidence": [], "steps": [], "tool_calls": [],
        "suggestions": [], "status": "RUNNING",
    }

    try:
        state = await graph.run(state, session, on_event=on_event)
        task.status = state["status"]
        task.result = {
            "root_cause": state.get("root_cause"),
            "suggestions": state.get("suggestions", []),
            "final_report": state.get("final_report"),
            "plan": state.get("plan", {}).get("reasoning", ""),
            "approval_status": state.get("approval_status", "NONE"),
        }
        if state.get("needs_approval"):
            # 保存待审批记录
            action = state.get("approval_action") or {}
            approval = Approval(
                task_id=task.id,
                action_name=action.get("action_name", ""),
                action_arguments=action.get("arguments", {}),
                arguments_signature=action.get("signature", ""),
                risk_level=action.get("risk", "HIGH"),
                requested_by=user_id, status="PENDING",
            )
            session.add(approval)
    except Exception as e:
        logger.exception("Agent task failed")
        task.status = "FAILED"
        task.error_message = str(e)
        task.result = {"error": str(e)}

    task.execution_time_ms = int((time.time() - start) * 1000)
    task.finished_at = datetime.now(timezone.utc)

    # 持久化 steps 和 tool_calls
    for s in state.get("steps", []):
        session.add(AgentStep(task_id=task.id, **s))
    for tc in state.get("tool_calls", []):
        session.add(ToolExecution(
            task_id=task.id, tool_name=tc["tool_name"],
            arguments=tc.get("arguments"), result=tc.get("result"),
            status=tc.get("status"), error_message=tc.get("error_message"),
            duration_ms=tc.get("duration_ms", 0),
        ))
    session.add(AuditLog(user_id=user_id, task_id=task.id, action="RUN_AGENT",
                         resource_type="agent_task", resource_id=task.task_no))
    await session.commit()
    await session.refresh(task)
    return task


async def build_report(session: AsyncSession, task: AgentTask) -> dict:
    """组装完整报告（含步骤、工具调用、审批）"""
    result = await session.execute(
        select(AgentStep).where(AgentStep.task_id == task.id).order_by(AgentStep.step_no)
    )
    steps = result.scalars().all()
    result = await session.execute(
        select(ToolExecution).where(ToolExecution.task_id == task.id).order_by(ToolExecution.id)
    )
    tools = result.scalars().all()
    result = await session.execute(
        select(Approval).where(Approval.task_id == task.id).order_by(Approval.id)
    )
    approvals = result.scalars().all()

    r = task.result or {}
    return {
        "task_id": str(task.id), "task_no": task.task_no,
        "status": task.status, "question": task.description,
        "service_name": task.service_name,
        "root_cause": r.get("root_cause"),
        "suggestions": r.get("suggestions", []),
        "final_report": r.get("final_report"),
        "evidence": r.get("plan"),
        "steps": [{
            "step_no": s.step_no, "node_name": s.node_name, "action": s.action,
            "status": s.status, "duration_ms": s.duration_ms,
            "input_data": s.input_data, "output_data": s.output_data,
        } for s in steps],
        "tool_calls": [{
            "tool_name": t.tool_name, "arguments": t.arguments, "result": t.result,
            "status": t.status, "error_message": t.error_message, "duration_ms": t.duration_ms,
        } for t in tools],
        "approvals": [{
            "id": a.id, "action_name": a.action_name, "risk_level": a.risk_level,
            "status": a.status, "review_comment": a.review_comment,
        } for a in approvals],
        "total_tokens": task.total_tokens,
        "execution_time_ms": task.execution_time_ms,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }


async def approve_task(session: AsyncSession, approval_id: int,
                       decision: str, reviewer_id: int,
                       comment: str = "", signature: str | None = None) -> dict:
    """
    审批高风险操作：后端必须校验 5 件事
    1. 审批是否存在  2. 是否仍 PENDING  3. 审批人权限
    4. 是否重复审批  5. 参数签名是否一致（防篡改）
    """
    from app.core.security import has_role, ROLE_MANAGER
    from app.models.user import User

    approval = await session.get(Approval, approval_id)
    if not approval:
        return {"success": False, "error": "审批记录不存在"}
    if approval.status != "PENDING":
        return {"success": False, "error": "该审批已处理，不能重复审批"}
    if signature and approval.arguments_signature and signature != approval.arguments_signature:
        return {"success": False, "error": "参数签名不一致，操作参数可能被篡改，已拒绝"}

    reviewer = await session.get(User, reviewer_id)
    if not reviewer or not has_role(reviewer.role, ROLE_MANAGER):
        return {"success": False, "error": "审批人权限不足，需要运维负责人及以上角色"}

    approval.status = "APPROVED" if decision == "APPROVE" else "REJECTED"
    approval.review_comment = comment
    approval.reviewed_by = reviewer_id
    approval.reviewed_at = datetime.now(timezone.utc)

    task = await session.get(AgentTask, approval.task_id)
    if task:
        if decision == "APPROVE":
            # 续跑高风险操作 → 分析 → 报告
            state: AgentState = {
                "task_id": str(task.id), "question": task.description,
                "service_name": task.service_name,
                "evidence": [], "steps": [], "tool_calls": [], "suggestions": [],
                "approval_status": "APPROVED",
                "approval_action": {
                    "action_name": approval.action_name,
                    "arguments": approval.action_arguments,
                },
            }
            state = await graph.resume_after_approval(state, session)
            task.result = {
                **(task.result or {}),
                "final_report": state.get("final_report"),
                "approval_status": "APPROVED",
            }
            task.status = state.get("status", "COMPLETED")
        else:
            task.result = {**(task.result or {}), "approval_status": "REJECTED"}
            task.status = "COMPLETED"

    session.add(AuditLog(user_id=reviewer_id, task_id=approval.task_id,
                         action=f"APPROVAL_{decision}", resource_type="approval",
                         resource_id=str(approval.id), detail={"comment": comment}))
    await session.commit()
    return {"success": True, "status": approval.status}

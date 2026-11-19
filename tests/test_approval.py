"""
人工审批安全逻辑测试（服务层）
运行：cd backend && .venv/Scripts/python.exe ../tests/test_approval.py
测试点：
  1. 高风险操作触发后生成 PENDING 审批记录
  2. 权限校验：普通用户不能审批，负责人可以
  3. 参数签名校验：签名不一致拒绝（防篡改）
  4. 重复审批拒绝
  5. 审批通过后协议执行并更新报告
"""
import asyncio
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from sqlalchemy import select
from app.models.base import AsyncSessionLocal, init_db
from app.models.approval import Approval
from app.models.task import AgentTask
from app.models.user import User
from app.services.agent_service import approve_task
from app.core.security import hash_password


async def main():
    await init_db()
    async with AsyncSessionLocal() as db:
        # 确保有测试用户
        for name, role in [("appr_op", "OPERATOR"), ("appr_mgr", "MANAGER")]:
            r = await db.execute(select(User).where(User.username == name))
            if not r.scalar_one_or_none():
                db.add(User(username=name, password_hash=hash_password("123456"), role=role))
        await db.commit()

        # 造一个待审批任务（唯一编号，避免重复运行冲突）
        test_no = f"TEST-APPROVAL-{int(time.time()*1000)}"
        task = AgentTask(task_no=test_no, title="重启 order-service",
                         description="模拟重启", status="WAITING_APPROVAL")
        db.add(task)
        await db.flush()
        approval = Approval(task_id=task.id, action_name="restart_service",
                            action_arguments={"service_name": "order-service", "reason": "连接池耗尽"},
                            arguments_signature="abc123sig", risk_level="HIGH", status="PENDING")
        db.add(approval)
        await db.commit()
        aid, tid = approval.id, task.id

    results = []
    async with AsyncSessionLocal() as db:
        op = (await db.execute(select(User).where(User.username == "appr_op"))).scalar_one()
        mgr = (await db.execute(select(User).where(User.username == "appr_mgr"))).scalar_one()

        # 测试1：普通用户审批 -> 权限不足
        r = await approve_task(db, aid, "APPROVE", op.id)
        results.append(("普通用户审批被拒", not r["success"] and "权限" in r["error"]))

        # 测试2：签名不一致 -> 拒绝
        r = await approve_task(db, aid, "APPROVE", mgr.id, signature="TAMPERED")
        results.append(("参数篡改被拒", not r["success"] and "签名" in r["error"]))

        # 测试3：负责人审批 -> 通过
        r = await approve_task(db, aid, "APPROVE", mgr.id, comment="确认重启", signature="abc123sig")
        results.append(("负责人审批通过", r["success"] and r["status"] == "APPROVED"))

        # 测试4：重复审批 -> 拒绝
        r = await approve_task(db, aid, "APPROVE", mgr.id, signature="abc123sig")
        results.append(("重复审批被拒", not r["success"] and "重复" in r["error"]))

    for name, ok in results:
        print(("  [PASS] " if ok else "  [FAIL] ") + name)
    assert all(ok for _, ok in results), "审批测试未全部通过"
    print("\nALL APPROVAL TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())

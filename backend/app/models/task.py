"""
Agent 任务 / 步骤 / 工具调用记录 三张表
======================================
面试高频问题：为什么 agent_steps 和 tool_executions 要分开存？
  答：一次「任务规划」是一个 step，但它内部可能调用 3 个工具。
      step 记录「Agent 在想什么、这一步结论是什么」，
      tool_execution 记录「具体调了哪个工具、传了什么参、返回了什么」。
      分开后才能回答「Agent 为什么得出这个结论」——这是可解释性/可追踪性的基础。
"""
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Integer, BigInteger, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


def _now():
    return datetime.now(timezone.utc)


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    service_name: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)
    task_type: Mapped[str | None] = mapped_column(String(50))
    result: Mapped[dict | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    execution_time_ms: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)

    steps: Mapped[list["AgentStep"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    tool_executions: Mapped[list["ToolExecution"]] = relationship(back_populates="task", cascade="all, delete-orphan")


class AgentStep(Base):
    __tablename__ = "agent_steps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("agent_tasks.id"), index=True)
    step_no: Mapped[int] = mapped_column(Integer)
    node_name: Mapped[str | None] = mapped_column(String(100))
    action: Mapped[str | None] = mapped_column(String(100))
    input_data: Mapped[dict | None] = mapped_column(JSON)
    output_data: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str | None] = mapped_column(String(32))
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    task: Mapped["AgentTask"] = relationship(back_populates="steps")


class ToolExecution(Base):
    __tablename__ = "tool_executions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("agent_tasks.id"), index=True)
    tool_name: Mapped[str] = mapped_column(String(100))
    arguments: Mapped[dict | None] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str | None] = mapped_column(String(32))
    error_message: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    task: Mapped["AgentTask"] = relationship(back_populates="tool_executions")

"""Agent 相关接口 Schema"""
from typing import Any
from pydantic import BaseModel, Field


class AgentTaskRequest(BaseModel):
    question: str = Field(min_length=5, max_length=2000, description="运维人员的自然语言问题")
    service_name: str | None = Field(default=None, description="可选：指定服务名，如 order-service")


class AgentTaskResponse(BaseModel):
    task_id: str
    task_no: str
    status: str
    message: str


class AgentStepSchema(BaseModel):
    step_no: int
    node_name: str | None = None
    action: str | None = None
    status: str | None = None
    duration_ms: int | None = None
    input_data: Any = None
    output_data: Any = None


class ToolExecutionSchema(BaseModel):
    tool_name: str
    arguments: Any = None
    result: Any = None
    status: str | None = None
    error_message: str | None = None
    duration_ms: int | None = None


class AgentReportSchema(BaseModel):
    task_id: str
    task_no: str
    status: str
    question: str
    service_name: str | None = None
    root_cause: str | None = None
    suggestions: list[str] = []
    evidence: Any = None
    steps: list[AgentStepSchema] = []
    tool_calls: list[ToolExecutionSchema] = []
    approvals: list[dict] = []
    total_tokens: int = 0
    execution_time_ms: int | None = None
    created_at: Any = None


class ApprovalActionRequest(BaseModel):
    decision: str = Field(description="APPROVE 或 REJECT")
    comment: str | None = None
    arguments_signature: str | None = None  # 复核参数未被篡改

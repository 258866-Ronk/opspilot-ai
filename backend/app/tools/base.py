"""
工具系统基座：定义工具的统一契约、风险等级、注册中心、执行器
=============================================================
这是「Agent 工程」里最核心的设计之一：

1. 为什么工具要统一契约？
   Agent 需要用统一的格式描述工具（名字/用途/参数 schema），LLM 才能做 Function Calling。
   统一契约也让「执行记录」「权限校验」「重试」可以集中处理，而不是散落在每个工具里。

2. 为什么要有风险等级？
   查询类操作（读日志）可以自动执行；重启服务/删数据必须拦截审批。
   把风险等级作为工具的元数据，审批逻辑就能通用化，而不是写 if-else。

3. 为什么要有工具注册中心（ToolRegistry）？
   LangGraph / LLM 需要拿到一个「可用工具列表」。注册中心是单一数据源（Single Source of Truth），
   新增工具只要注册一次，API 文档、LLM 工具列表、执行器都自动同步——这就是可扩展性。
"""
import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable

from pydantic import BaseModel

from app.core.logging import logger


class RiskLevel(str, Enum):
    LOW = "LOW"          # 只读查询，自动执行
    MEDIUM = "MEDIUM"    # 需权限检查
    HIGH = "HIGH"        # 必须人工审批
    CRITICAL = "CRITICAL"  # 默认禁止


def requires_approval(risk: RiskLevel) -> bool:
    return risk in (RiskLevel.HIGH, RiskLevel.CRITICAL)


@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: str | None = None
    duration_ms: int = 0
    retry_count: int = 0
    risk: RiskLevel = RiskLevel.LOW
    needs_approval: bool = False

    def to_dict(self):
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "retry_count": self.retry_count,
            "risk": self.risk.value,
            "needs_approval": self.needs_approval,
        }


@dataclass
class ToolSpec:
    """工具的描述/元数据"""
    name: str
    description: str
    risk: RiskLevel = RiskLevel.LOW
    params_schema: type[BaseModel] | None = None
    fn: Callable[..., Awaitable[Any]] = field(default=None)
    timeout: float = 10.0
    retries: int = 1

    def signature_of(self, args: dict) -> str:
        """参数签名：用于审批后比对，防止参数被篡改"""
        raw = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def llm_schema(self) -> dict:
        """转成 OpenAI Function Calling 格式"""
        params = {"type": "object", "properties": {}, "required": []}
        if self.params_schema:
            schema = self.params_schema.model_json_schema()
            params = {
                "type": "object",
                "properties": schema.get("properties", {}),
                "required": schema.get("required", []),
            }
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": f"{self.description}（风险等级：{self.risk.value}）",
                "parameters": params,
            },
        }


class ToolRegistry:
    """工具注册中心"""
    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec):
        self._tools[spec.name] = spec
        logger.debug("Registered tool: %s (risk=%s)", spec.name, spec.risk.value)

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def list_tools(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def llm_schemas(self) -> list[dict]:
        return [t.llm_schema() for t in self._tools.values()]

    async def execute(self, name: str, args: dict) -> ToolResult:
        """Execute a tool with validation, timeout, retry. Does NOT enforce approval here."""
        spec = self.get(name)
        start = time.time()
        if not spec:
            return ToolResult(False, error=f"Unknown tool: {name}", risk=RiskLevel.CRITICAL)

        # 参数校验
        if spec.params_schema:
            try:
                validated = spec.params_schema(**args)
                args = validated.model_dump()
            except Exception as e:
                return ToolResult(False, error=f"Invalid arguments: {e}", risk=spec.risk)

        last_error = None
        retry_count = 0
        for attempt in range(spec.retries + 1):
            try:
                data = await asyncio.wait_for(spec.fn(**args), timeout=spec.timeout)
                dur = int((time.time() - start) * 1000)
                return ToolResult(
                    success=True, data=data, duration_ms=dur,
                    retry_count=retry_count, risk=spec.risk,
                    needs_approval=requires_approval(spec.risk),
                )
            except asyncio.TimeoutError:
                last_error = f"Tool timeout after {spec.timeout}s"
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
            retry_count = attempt + 1
            if attempt < spec.retries:
                logger.warning("Tool %s failed (%s), retry %d/%d", name, last_error, attempt + 1, spec.retries)
                await asyncio.sleep(0.2 * (attempt + 1))  # 简单退避

        dur = int((time.time() - start) * 1000)
        return ToolResult(
            False, error=last_error, duration_ms=dur,
            retry_count=retry_count, risk=spec.risk,
            needs_approval=requires_approval(spec.risk),
        )


# 全局单例
registry = ToolRegistry()

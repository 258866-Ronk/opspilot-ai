"""
工具注册入口
============
在这里把所有工具一次性注册到全局 registry。
新增工具只需两步：① 写工具函数 ② 在这里 register 一次。
API 文档、LLM 工具列表、执行器会自动同步——这就是「可扩展性」。
"""
from app.tools.base import registry, ToolSpec, RiskLevel, ToolResult, requires_approval
from app.tools import log_tool, metrics_tool, database_tool, ticket_tool


def build_registry():
    registry.register(ToolSpec(
        name="search_logs",
        description="查询指定微服务的错误日志，可按关键词和级别过滤。用于定位 HTTP 500、异常堆栈等问题。",
        risk=RiskLevel.LOW,
        params_schema=log_tool.LogSearchParams,
        fn=log_tool.search_logs,
    ))
    registry.register(ToolSpec(
        name="query_metrics",
        description="查询指定微服务的监控指标（CPU、内存、错误率、响应时间、QPS）。用于判断服务健康状态。",
        risk=RiskLevel.LOW,
        params_schema=metrics_tool.MetricsQueryParams,
        fn=metrics_tool.query_metrics,
    ))
    registry.register(ToolSpec(
        name="diagnose_database",
        description="诊断数据库连接池、慢查询、死锁状态。用于排查连接超时、数据库瓶颈问题。",
        risk=RiskLevel.LOW,
        params_schema=None,
        fn=database_tool.diagnose_database,
    ))
    registry.register(ToolSpec(
        name="rag_search",
        description="检索企业运维知识库，查找历史故障处理方案和 Runbook。",
        risk=RiskLevel.LOW,
        params_schema=None,  # 后面 RAG 模块会覆盖注册
        fn=_placeholder_rag,
    ))
    registry.register(ToolSpec(
        name="create_ticket",
        description="创建故障工单。",
        risk=RiskLevel.MEDIUM,
        params_schema=ticket_tool.CreateTicketParams,
        fn=ticket_tool.create_ticket,
    ))
    registry.register(ToolSpec(
        name="restart_service",
        description="重启指定微服务。高风险操作，需要人工审批，且仅模拟执行。",
        risk=RiskLevel.HIGH,
        params_schema=ticket_tool.RestartServiceParams,
        fn=ticket_tool.restart_service,
    ))
    registry.register(ToolSpec(
        name="notify_oncall",
        description="通知值班工程师。",
        risk=RiskLevel.MEDIUM,
        params_schema=None,
        fn=lambda service_name, message="": ticket_tool.notify_oncall(service_name, message),
    ))
    return registry


async def _placeholder_rag(**kwargs):
    return {"success": True, "message": "RAG 工具尚未初始化", "results": []}


build_registry()

__all__ = [
    "registry", "ToolSpec", "RiskLevel", "ToolResult",
    "requires_approval", "build_registry",
]

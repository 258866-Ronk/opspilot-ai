"""
Agent 工作流的节点实现
======================
Planner → Executor → Analyzer → (Approval) → Reporter

每个节点是一个 async 函数：接收 state，返回对 state 的部分更新。
这样设计的好处：节点无状态、可单测、可复用（LangGraph 和轻量引擎共用同一批节点）。
"""
import time
from app.core.logging import logger
from app.core.config import settings
from app.agent.llm import call_llm
from app.agent.state import AgentState
from app.tools import registry
from app.rag import rag_search
from sqlalchemy.ext.asyncio import AsyncSession


def _step(state, node, action, status="SUCCESS", duration=0, input_data=None, output_data=None):
    return {
        "step_no": len(state.get("steps", [])) + 1,
        "node_name": node, "action": action, "status": status,
        "duration_ms": duration,
        "input_data": input_data, "output_data": output_data,
    }


async def planner_node(state: AgentState, session: AsyncSession) -> dict:
    """任务理解与规划：让 LLM（或规则引擎）决定调用哪些工具"""
    start = time.time()
    messages = [{"role": "user", "content": state["question"]}]
    plan = await call_llm(messages, tools=registry.llm_schemas())

    tool_calls = plan.get("tool_calls", [])
    # 过滤出已注册的工具，防止 LLM 幻觉出不存在的工具
    valid = [c for c in tool_calls if registry.get(c.get("name"))]
    service = plan.get("service_name") or state.get("service_name") or _guess_service(state["question"])

    duration = int((time.time() - start) * 1000)
    logger.info("Planner chose tools: %s", [c["name"] for c in valid])
    return {
        "plan": plan,
        "pending_tools": valid,
        "tool_cursor": 0,
        "service_name": service,
        "steps": [_step(state, "planner", "任务规划", output_data={
            "reasoning": plan.get("reasoning", ""),
            "selected_tools": [c["name"] for c in valid],
        }, duration=duration)],
    }


async def executor_node(state: AgentState, session: AsyncSession) -> dict:
    """执行单个工具：一次只执行一个，方便记录、审批和重试"""
    pending = state.get("pending_tools", [])
    cursor = state.get("tool_cursor", 0)
    if cursor >= len(pending):
        return {}

    call = pending[cursor]
    name = call["name"]
    args = dict(call.get("arguments") or {})

    # RAG 工具需要 session，特殊处理
    if name == "rag_search":
        start = time.time()
        try:
            res = await rag_search(session, args.get("query", state["question"]))
            tool_result = {
                "success": res["success"], "data": res,
                "error": None, "duration_ms": int((time.time()-start)*1000),
                "retry_count": 0, "risk": "LOW", "needs_approval": False,
            }
        except Exception as e:
            tool_result = {"success": False, "error": str(e), "data": None,
                           "duration_ms": int((time.time()-start)*1000), "risk": "LOW"}
    else:
        tool_result = (await registry.execute(name, args)).to_dict()

    record = {
        "tool_name": name, "arguments": args,
        "result": tool_result.get("data"), "status": "SUCCESS" if tool_result.get("success") else "FAILED",
        "error_message": tool_result.get("error"),
        "duration_ms": tool_result.get("duration_ms", 0),
        "risk": tool_result.get("risk", "LOW"),
        "needs_approval": tool_result.get("needs_approval", False),
        "signature": registry.get(name).signature_of(args) if registry.get(name) else "",
    }

    evidence = {
        "tool": name,
        "arguments": args,
        "data": tool_result.get("data"),
        "success": tool_result.get("success"),
        "hint": (tool_result.get("data") or {}).get("analysis_hint") if isinstance(tool_result.get("data"), dict) else None,
    }

    # 检测高风险操作（如 LLM 规划出 restart_service）
    needs_approval = tool_result.get("needs_approval", False)
    approval_action = None
    if needs_approval:
        approval_action = {
            "action_name": name, "arguments": args,
            "signature": record["signature"],
            "risk": tool_result.get("risk", "HIGH"),
        }

    return {
        "tool_cursor": cursor + 1,
        "evidence": [evidence],
        "tool_calls": [record],
        "needs_approval": needs_approval,
        "approval_action": approval_action,
        "steps": [_step(state, "executor", f"执行工具 {name}",
                        status=record["status"], duration=record["duration_ms"],
                        input_data=args, output_data={"success": tool_result.get("success")})],
    }


async def analyzer_node(state: AgentState, session: AsyncSession) -> dict:
    """故障分析：整合证据，得出根因和建议"""
    start = time.time()
    evidence = state.get("evidence", [])
    root_cause, suggestions = _analyze(state["question"], evidence, state.get("service_name"))

    duration = int((time.time() - start) * 1000)
    return {
        "root_cause": root_cause,
        "suggestions": suggestions,
        "status": "ANALYZED",
        "steps": [_step(state, "analyzer", "故障分析", duration=duration,
                        input_data={"evidence_count": len(evidence)},
                        output_data={"root_cause": root_cause, "suggestions": suggestions})],
    }


def _analyze(question, evidence, service):
    """
    基于证据规则综合得出结论（LLM 模式下可替换为让模型总结）
    改进版：汇总所有已收集到的证据维度，生成信息完整的诊断结论。
    """
    data_by_tool = {e["tool"]: e.get("data") for e in evidence if e.get("success")}
    causes, suggestions = [], []

    db = data_by_tool.get("diagnose_database") or {}
    metrics = data_by_tool.get("query_metrics") or {}
    logs = data_by_tool.get("search_logs") or {}
    rag = data_by_tool.get("rag_search") or {}
    m = metrics.get("metrics") or {}

    # ---- 监控指标维度：把所有指标写进结论，避免信息遗漏 ----
    if m:
        status_cn = {"HEALTHY": "健康", "DEGRADED": "降级", "DOWN": "宕机"}.get(m.get("status"), m.get("status"))
        causes.append(
            f"监控指标显示服务状态为{status_cn}，"
            f"错误率 {m.get('error_rate')}%、平均响应时间 {m.get('avg_response_time_ms')}ms、"
            f"P99 响应时间 {m.get('p99_response_time_ms')}ms、CPU 使用率 {m.get('cpu_usage')}%、"
            f"内存使用率 {m.get('memory_usage')}%、QPS {m.get('request_qps')}"
        )
        if m.get("error_rate", 0) > 5:
            causes.append(f"错误率 {m['error_rate']}% 明显超过正常阈值（<1%）")
        if m.get("avg_response_time_ms", 0) > 1000:
            causes.append(f"平均响应时间 {m['avg_response_time_ms']}ms 过长，用户体验受损")

    # ---- 日志维度 ----
    counts = logs.get("level_counts") or {}
    if counts:
        causes.append(f"日志检索共命中 {logs.get('total', 0)} 条（ERROR {counts.get('ERROR',0)} 条、WARN {counts.get('WARN',0)} 条、INFO {counts.get('INFO',0)} 条）")
    error_msgs = []
    for l in logs.get("logs", []):
        msg = str(l.get("message", ""))
        if l.get("level") == "ERROR" or any(k in msg for k in ("timeout", "refused", "500", "HikariPool")):
            error_msgs.append(msg[:90])
    if error_msgs:
        causes.append("典型异常日志：" + " | ".join(error_msgs[:2]))
    if counts.get("ERROR", 0) >= 1:
        causes.append("错误日志中包含 HTTP 500 / 连接超时堆栈")

    # ---- 数据库维度 ----
    d = db.get("database") or {}
    if d:
        causes.append(
            f"数据库诊断：连接池 {d.get('active_connections')}/{d.get('max_connections')}（使用率 {db.get('connection_usage',0)*100:.0f}%）、"
            f"慢查询 {d.get('slow_query_count')} 条、死锁 {d.get('deadlocks_last_hour')} 次、"
            f"连接超时阈值 {d.get('connection_timeout_seconds')}s、复制延迟 {d.get('replication_lag_seconds')}s"
        )
    usage = db.get("connection_usage", 0)
    if usage and usage > 0.9:
        causes.append("数据库连接池接近耗尽，是 HTTP 500 的高概率根因")
        suggestions.append("临时调大 HikariPool maxPoolSize，并为高频查询表添加联合索引")
        suggestions.append("批量导入任务改分页限速，连接池使用率超过 80% 配置告警")

    # ---- Redis / 缓存维度 ----
    all_log_text = " ".join(str(l.get("message", "")) for l in logs.get("logs", []))
    if "Redis" in all_log_text or "redis" in all_log_text:
        causes.append("日志显示 Redis 连接被拒绝，缓存层异常")
        suggestions.append("检查 Redis 服务状态与连接配置，必要时降级为本地缓存并限流保护数据库")

    # ---- 知识库维度 ----
    if rag.get("results"):
        causes.append(f"知识库检索命中 {len(rag['results'])} 条历史相似故障 Runbook，可作诊断参考")
        suggestions.append("参考 Runbook 中的排查步骤、根因分析与预防措施执行")

    # ---- 兜底 ----
    if not causes:
        causes.append("证据未显示明确异常，建议扩大时间范围或补充更多工具数据")
    if not suggestions:
        suggestions = [
            "收集更完整的监控指标与日志上下文",
            "复现问题并在测试环境验证假设",
            "必要时创建工单并通知值班工程师跟进",
        ]

    root = "；".join(causes) + f"。综合判断：{service or '目标服务'} 故障与上述监控、日志及数据库证据相关。"
    return root, suggestions[:6]


async def approval_node(state: AgentState, session: AsyncSession) -> dict:
    """审批节点：高风险操作在此暂停，等待人工决策（真实系统用 interrupt）"""
    action = state.get("approval_action") or {}
    return {
        "status": "WAITING_APPROVAL",
        "steps": [_step(state, "approval", "等待人工审批", status="PENDING",
                        input_data=action)],
    }


async def reporter_node(state: AgentState, session: AsyncSession) -> dict:
    """报告生成：输出结构化故障报告"""
    report_lines = [
        f"# OpsPilot AI 故障诊断报告",
        f"",
        f"**问题**：{state['question']}",
        f"**目标服务**：{state.get('service_name') or '未指定'}",
        f"",
        f"## 一、故障根因",
        state.get("root_cause", "分析中"),
        f"",
        f"## 二、处理建议",
    ]
    for i, s in enumerate(state.get("suggestions", []), 1):
        report_lines.append(f"{i}. {s}")
    report_lines += [
        f"",
        f"## 三、工具调用与证据",
    ]
    for i, tc in enumerate(state.get("tool_calls", []), 1):
        report_lines.append(f"{i}. `{tc['tool_name']}` ({tc['status']}, {tc.get('duration_ms',0)}ms)")
    if state.get("approval_status") == "APPROVED":
        report_lines += ["", "> 高风险操作已经人工审批通过并模拟执行。"]
    if state.get("approval_status") == "REJECTED":
        report_lines += ["", "> 高风险操作已被人工拒绝，未执行。"]

    report = "\n".join(report_lines)
    return {
        "final_report": report,
        "status": "COMPLETED",
        "steps": [_step(state, "reporter", "生成报告")],
    }

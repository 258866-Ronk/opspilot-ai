"""
LLM 封装：双栈设计（真实 API + 规则引擎降级）
=============================================
- 配了 LLM_API_KEY/BASE_URL/MODEL → 走 OpenAI 兼容的 Function Calling
- 没配 → 走内置规则引擎，基于关键词做任务规划和工具选择（完全可演示）

为什么这样设计？
  LLM 调用抽象为统一接口，模型可插拔。
  在没有 Key 的环境 else 用规则引擎保证 DEMO 可跑，这在企业里对应『模型降级/兜底策略』，
  保证核心流程不因为外部模型不可用而中断。」——这是很成熟工程思维。
"""
import json
import re
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import logger

SYSTEM_PROMPT = """你是 OpsPilot AI，一名资深 SRE 运维诊断专家。
你的任务是根据运维人员描述的问题，选择合适的工具收集证据，分析故障根因并给出处理建议。

可用工具：
- search_logs：查错误日志（定位堆栈/异常）
- query_metrics：查监控指标（错误率/响应时间/CPU/内存）
- diagnose_database：诊断数据库连接池/慢查询/死锁
- rag_search：检索历史故障 Runbook
- create_ticket：创建工单
- restart_service：重启服务（高风险，需审批）
- notify_oncall：通知值班人

要求：
1. 优先调用低风险的只读工具收集证据，不要盲目调用所有工具。
2. 根据问题类型选工具：HTTP 500/异常→日志；服务宕机/慢→监控；连接超时→数据库；历史方案→RAG。
3. 收集到足够证据后给出结论，不要无限调用。
4. 输出 JSON 格式：{"tool_calls":[{"name":"工具名","arguments":{...}}],"reasoning":"思考过程"}
   如果不需要工具了：{"tool_calls":[],"reasoning":"...","conclusion":"诊断结论"}
"""


async def call_llm(messages: list[dict], tools: list[dict] | None = None) -> dict:
    """统一 LLM 调用入口"""
    if not settings.llm_enabled:
        logger.debug("LLM not configured, using rule-based planner")
        return rule_based_plan(messages)

    url = settings.LLM_BASE_URL.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.LLM_MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
        "temperature": 0,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    try:
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            msg = resp.json()["choices"][0]["message"]
        return _parse_llm_message(msg)
    except Exception as e:
        logger.error("LLM call failed: %s, falling back to rules", e)
        return rule_based_plan(messages)


def _parse_llm_message(msg: dict) -> dict:
    """解析 LLM 响应：支持原生 tool_calls 或 JSON 文本"""
    tool_calls = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function", {})
        try:
            args = json.loads(fn.get("arguments", "{}"))
        except Exception:
            args = {}
        tool_calls.append({"name": fn.get("name"), "arguments": args})

    content = msg.get("content") or ""
    reasoning, conclusion = "", ""
    if content:
        parsed = _try_parse_json(content)
        if parsed:
            reasoning = parsed.get("reasoning", "")
            conclusion = parsed.get("conclusion", "")
            if not tool_calls:
                tool_calls = parsed.get("tool_calls", [])
        else:
            conclusion = content
    return {"tool_calls": tool_calls, "reasoning": reasoning, "conclusion": conclusion, "raw": content}


def _try_parse_json(text: str) -> dict | None:
    """从可能带 markdown 代码块的文本里提取 JSON"""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        m = re.search(r"\{.*\}", cleaned, re.S)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                return None
    return None


def _last_user_text(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return str(m.get("content", ""))
    return ""


def rule_based_plan(messages: list[dict]) -> dict:
    """
    规则引擎：根据问题关键词决定工具调用（无 LLM 时的降级方案）
    这是「确定性 + 可解释」的规划，也正好演示了 Agent 与固定流程的区别：
    不同问题走不同工具组合，而不是每次调全部工具。
    """
    question = _last_user_text(messages).lower()
    service = _detect_service(question)
    calls = []
    reasoning_parts = []

    has_connection_kw = any(k in question for k in ["500", "连接", "timeout", "超时", "连接池", "数据库", "connection"])
    has_metrics_kw = any(k in question for k in ["慢", "响应", "宕机", "cpu", "内存", "指标", "监控", "卡"])
    has_redis_kw = any(k in question for k in ["redis", "缓存", "支付"])
    has_history_kw = any(k in question for k in ["历史", "之前", "以前", "类似", "复盘", "方案", "runbook"])

    # 服务名解析（默认 order-service）
    svc = service or "order-service"

    if has_redis_kw:
        calls.append({"name": "query_metrics", "arguments": {"service_name": svc}})
        calls.append({"name": "search_logs", "arguments": {"service_name": svc, "keyword": "Redis"}})
        calls.append({"name": "rag_search", "arguments": {"query": "Redis 连接失败 处理"}})
        reasoning_parts.append("检测到 Redis/缓存关键词，优先查监控+日志并检索缓存故障 Runbook")
    elif has_connection_kw:
        calls.append({"name": "search_logs", "arguments": {"service_name": svc, "keyword": ""}})
        calls.append({"name": "query_metrics", "arguments": {"service_name": svc}})
        calls.append({"name": "diagnose_database", "arguments": {}})
        calls.append({"name": "rag_search", "arguments": {"query": f"{svc} 数据库连接池耗尽 HTTP 500"}})
        reasoning_parts.append("检测到连接/500/超时关键词，按日志→监控→数据库→知识库顺序收集证据")
    elif has_metrics_kw:
        calls.append({"name": "query_metrics", "arguments": {"service_name": svc}})
        calls.append({"name": "search_logs", "arguments": {"service_name": svc, "keyword": "ERROR"}})
        reasoning_parts.append("检测到性能/健康关键词，先查监控指标再查错误日志")
    elif has_history_kw:
        calls.append({"name": "rag_search", "arguments": {"query": question}})
        reasoning_parts.append("用户想查历史方案，直接检索知识库")
    else:
        # 兜底：日志 + 监控 + 知识库
        calls.append({"name": "search_logs", "arguments": {"service_name": svc, "keyword": ""}})
        calls.append({"name": "query_metrics", "arguments": {"service_name": svc}})
        calls.append({"name": "rag_search", "arguments": {"query": question}})
        reasoning_parts.append("未识别明确意图，按通用排查流程收集日志、监控与知识库证据")

    return {
        "tool_calls": calls,
        "reasoning": "；".join(reasoning_parts),
        "conclusion": "",
        "service_name": svc,
    }


def _detect_service(question: str) -> str | None:
    mapping = {
        "order": "order-service", "订单": "order-service",
        "user": "user-service", "用户": "user-service",
        "product": "product-service", "商品": "product-service",
        "payment": "payment-service", "支付": "payment-service",
        "gateway": "gateway-service", "网关": "gateway-service",
    }
    for kw, svc in mapping.items():
        if kw in question:
            return svc
    return None

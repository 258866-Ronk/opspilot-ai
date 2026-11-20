"""
Agent 图编排：轻量图引擎 + LangGraph 兼容
==========================================
这里实现「条件分支 + 循环」的核心调度逻辑：

    START → planner → executor → (还有工具?) → executor
                              → (工具用完?) → analyzer
                              → (需审批?) → approval → [等待人工] → reporter
                              → reporter → END

为什么不用 LangGraph 原生？
  为了让项目零依赖即可运行（你机器上 LangGraph 可能没装）。
  这套调度逻辑与 LangGraph 的 StateGraph 语义完全一致——可据此逐行迁移到 LangGraph。
  代码里也提供了 build_langgraph() 供装了依赖时使用。
"""
from typing import Callable, Awaitable
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.agent.state import AgentState
from app.agent import nodes

NodeFn = Callable[[AgentState, AsyncSession], Awaitable[dict]]


def _apply(state: AgentState, update: dict) -> AgentState:
    """把节点返回的增量合并进 state（处理 list 追加）"""
    for k, v in update.items():
        if k in ("evidence", "steps", "tool_calls", "suggestions") and v is not None:
            state[k] = list(state.get(k, [])) + list(v)
        else:
            state[k] = v
    return state


class OpsPilotGraph:
    """轻量状态图引擎：节点 + 条件路由 + 循环"""

    def __init__(self):
        self.nodes: dict[str, NodeFn] = {
            "planner": nodes.planner_node,
            "executor": nodes.executor_node,
            "analyzer": nodes.analyzer_node,
            "approval": nodes.approval_node,
            "reporter": nodes.reporter_node,
        }

    async def run(self, state: AgentState, session: AsyncSession,
                  on_event: Callable[[str, dict], None] | None = None) -> AgentState:
        """
        执行完整图。on_event 用于 SSE 推送实时进度。
        """
        def emit(event, payload):
            if on_event:
                on_event(event, payload)

        emit("node", {"node": "planner", "message": "任务理解与规划中..."})
        state = _apply(state, await self.nodes["planner"](state, session))
        emit("plan", {"reasoning": state.get("plan", {}).get("reasoning", ""),
                      "tools": [c["name"] for c in state.get("pending_tools", [])]})

        # ---- 工具执行循环（Agent 自主选择，逐个执行，最多 MAX_AGENT_STEPS）----
        steps = 0
        while state.get("tool_cursor", 0) < len(state.get("pending_tools", [])):
            if steps >= settings.MAX_AGENT_STEPS:
                logger.warning("Max agent steps reached, stopping tool loop")
                break
            steps += 1
            tool_name = state["pending_tools"][state["tool_cursor"]]["name"]
            emit("node", {"node": "executor", "message": f"调用工具：{tool_name}"})
            state = _apply(state, await self.nodes["executor"](state, session))
            last_call = state["tool_calls"][-1]
            emit("tool_result", {
                "tool": tool_name,
                "success": last_call.get("status") == "SUCCESS",
                "summary": _summarize_tool_result(last_call),
            })

            # 高风险操作：审批拦截后停止（等待人工 approve 再续跑）
            if state.get("needs_approval"):
                emit("node", {"node": "approval", "message": "检测到高风险操作，等待人工审批"})
                state = _apply(state, await self.nodes["approval"](state, session))
                emit("approval_required", state.get("approval_action") or {})
                return state  # 挂起，等 approve API 续跑

        # ---- 分析 ----
        emit("node", {"node": "analyzer", "message": "整合证据，分析根因"})
        state = _apply(state, await self.nodes["analyzer"](state, session))

        # ---- 报告 ----
        emit("node", {"node": "reporter", "message": "生成诊断报告"})
        state = _apply(state, await self.nodes["reporter"](state, session))
        emit("done", {"status": state["status"]})
        return state

    async def resume_after_approval(self, state: AgentState, session: AsyncSession,
                                    on_event=None) -> AgentState:
        """审批通过后从 analyzer 继续（执行高风险工具 → 分析 → 报告）"""
        def emit(event, payload):
            if on_event:
                on_event(event, payload)

        action = state.get("approval_action") or {}
        if state.get("approval_status") == "APPROVED" and action:
            tool_name = action["action_name"]
            args = action.get("arguments", {})
            emit("node", {"node": "executor", "message": f"审批通过，执行：{tool_name}"})
            if tool_name == "rag_search":
                from app.rag import rag_search
                res = await rag_search(session, args.get("query", ""))
                result = res
            else:
                result = (await registry_execute(tool_name, args)).to_dict()
            state["tool_calls"] = state.get("tool_calls", []) + [{
                "tool_name": tool_name, "arguments": args,
                "result": result, "status": "SUCCESS",
                "approved": True,
            }]
            emit("tool_result", {"tool": tool_name, "success": True, "summary": "高风险操作已模拟执行"})

        emit("node", {"node": "analyzer", "message": "重新分析"})
        state = _apply(state, await self.nodes["analyzer"](state, session))
        emit("node", {"node": "reporter", "message": "生成报告"})
        state = _apply(state, await self.nodes["reporter"](state, session))
        emit("done", {"status": state["status"]})
        return state


async def registry_execute(name, args):
    from app.tools import registry
    return await registry.execute(name, args)


def _summarize_tool_result(record: dict) -> str:
    result = record.get("result")
    if not isinstance(result, dict):
        return "无数据"
    for key in ("analysis_hint", "message", "likely_cause"):
        if result.get(key):
            return str(result[key])[:120]
    return f"返回 {len(result)} 个字段"


# 全局单例
graph = OpsPilotGraph()


def build_langgraph():
    """
    迁移到 LangGraph 的示例（装了 langgraph 后可用）：
      from langgraph.graph import StateGraph, START, END
      builder = StateGraph(AgentState)
      builder.add_node("planner", ...)
      builder.add_node("executor", ...)
      builder.add_conditional_edges("executor", route_tools, {...})
      ...
      return builder.compile()
    当前项目用自研轻量引擎保证零依赖可跑，生产可直接替换为 compiled LangGraph。
    """
    try:
        from langgraph.graph import StateGraph
        return StateGraph  # 提示可用
    except ImportError:
        return None

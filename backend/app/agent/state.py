"""
AgentState：贯穿整个工作流的状态
================================
LangGraph 用 TypedDict + Annotated 定义状态，每个节点返回对状态的增量更新。
这里也兼容我们的轻量图引擎（本质就是一个 dict，节点函数原地更新）。

设计要点：
  - 为什么用 TypedDict 而不是普通 class？因为状态是「数据流」，TypedDict 描述结构、零开销，
    配合 add_messages reducer 可以实现消息追加而不是覆盖。
  - 状态里为什么要放 evidence / steps / tool_calls？为了可追踪——每一步的证据和执行记录都留痕。
"""
from typing import TypedDict, Annotated, Any


def merge_list(a: list, b: list) -> list:
    """自定义 reducer：合并而非覆盖"""
    return (a or []) + (b or [])


class AgentState(TypedDict, total=False):
    # 输入
    task_id: str
    task_no: str
    question: str
    service_name: str | None

    # 规划
    plan: dict
    pending_tools: list[dict]
    tool_cursor: int

    # 证据与结论
    evidence: Annotated[list, merge_list]
    root_cause: str
    suggestions: list[str]

    # 审批
    needs_approval: bool
    approval_action: dict | None
    approval_status: str   # PENDING / APPROVED / REJECTED / NONE

    # 输出与追踪
    final_report: str
    steps: Annotated[list, merge_list]
    tool_calls: Annotated[list, merge_list]
    status: str
    error_message: str

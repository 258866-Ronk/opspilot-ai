# 系统架构设计

## 1. 分层架构

```
前端展示层   控制台(原生JS) · REST · SSE 实时推送
─────────────────────────────────────────────
API 接入层   FastAPI · JWT · RBAC · Pydantic 校验
─────────────────────────────────────────────
Agent 核心层 Planner → Executor → Analyzer → Approval → Reporter
            （状态/节点/条件边/循环/重试/中断）
─────────────────────────────────────────────
工具与知识层 日志/监控/数据库/RAG/工单/重启/通知 + 注册中心
─────────────────────────────────────────────
数据基础设施 SQLite·PostgreSQL(pgvector) · Redis · 文件存储
```

**关键原则：Agent 只是后端的一个核心业务模块，不是整个后端。**
- `api`：接收请求
- `services`：业务编排
- `agent`：工作流
- `tools`：外部工具
- `rag`：知识库
- `models` / `schemas` / `repositories`：数据与接口契约

## 2. Agent 内部工作流（图结构）

```
START → planner ──→ executor ──┬─(还有工具?)──→ executor  (循环)
                                ├─(工具用完)──→ analyzer
                                └─(高风险!)──→ approval ──[人工审批]──→ reporter
                                                          ↓
                                                     analyzer → reporter → END
```

- **State**：贯穿全流程的状态（question/plan/evidence/tool_calls/root_cause/report）
- **Node**：纯函数，接收 state 返回增量更新（无状态、可单测、可复用）
- **Conditional Edge**：根据是否有待执行工具、是否需要审批决定下一步
- **Loop**：证据不足时继续调用工具，直到工具用完或达到 MAX_AGENT_STEPS

## 3. 数据流（一次诊断请求）

1. 前端 POST `/agent/tasks`（或 SSE `/agent/tasks/stream`）。
2. 创建 AgentTask 记录（status=RUNNING）。
3. Planner 调用 LLM/规则引擎 → 选出工具列表。
4. Executor 逐个执行工具（每次一个，便于记录/审批/重试）：
   - 结果写入 `evidence`（证据）和 `tool_calls`（记录）。
   - 若工具风险为 HIGH/CRITICAL → 中断，写 Approval(PENDING)。
5. Analyzer 汇总所有证据 → 根因 + 建议。
6. Reporter 生成 Markdown 报告。
7. 持久化 steps / tool_calls / audit_log，更新任务状态。

## 4. 双栈降级矩阵

| 组件 | 默认（开箱即跑） | 生产/可升级 |
|---|---|---|
| LLM | 规则引擎（关键词→工具映射） | DeepSeek 兼容 API Function Calling |
| 数据库 | SQLite + aiosqlite | PostgreSQL + asyncpg |
| 向量库 | JSON 数组 + numpy 余弦 | pgvector + HNSW 索引 |
| Embedding | 字符哈希向量(384维) | BGE-small-zh 语义模型 |
| 图引擎 | 自研轻量图引擎 | LangGraph StateGraph |
| 缓存 | 无 | Redis |

## 5. 安全设计

- 密码 bcrypt 加盐哈希（截断 72 字节防异常）。
- JWT 无状态鉴权，Token 含 sub/role/uid。
- RBAC 层级：OPERATOR < MANAGER < ADMIN。
- 高风险操作：风险分级 + 审批拦截 + 参数签名防篡改 + 审计日志。
- 所有运维工具均为**模拟数据**，不连接真实生产环境（符合 PRD 安全原则）。

## 6. 可扩展点

- 新增工具：写函数 → 在 `tools/__init__.py` 注册一次（API 文档/LLM 工具列表/执行器自动同步）。
- 新增节点：在 `graph.py` 的 nodes 字典注册 + 定义条件边。
- 接真实数据源：把 MOCK_* 数据替换成 ELK/Prometheus/CMDB 调用，工具契约不变。

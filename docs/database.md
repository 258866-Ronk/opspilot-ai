# 数据库设计

## 核心表（10 张）

| 表 | 作用 |
|---|---|
| users | 用户 |
| agent_tasks | Agent 任务（状态、结果、耗时、Token） |
| agent_steps | Agent 工作流节点记录 |
| tool_executions | 工具调用记录 |
| knowledge_documents | 知识文档 |
| knowledge_chunks | 文档切片 + 向量 |
| incidents | 故障工单 |
| approvals | 人工审批（含参数签名） |
| audit_logs | 操作审计 |
| （roles 角色：当前用 users.role 字符串，生产可拆 RBAC 四表） |

## 关键设计说明

### 为什么 agent_steps 和 tool_executions 分开？
Agent 节点（如"任务规划"）与工具调用不是一回事：一个分析节点内部可能调用多个工具。分开存储才能完整回答"Agent 为什么得出这个结论"。这是可解释性/可追踪性的基础。

### 为什么用 JSON/JSONB？
不同工具输入输出结构不同（日志数组、监控对象、数据库指标）。JSONB 灵活且 PostgreSQL 支持 GIN 索引与 JSON 查询。

### 向量字段
- SQLite：`embedding` 用 JSON 数组存 384 维向量。
- PostgreSQL：`VECTOR(384)` + HNSW 索引（`vector_cosine_ops`）。
- 维度必须与 Embedding 模型一致（config.EMBEDDING_DIM 统一管理）。

### 审批表的关键字段
`arguments_signature`：审批时的参数 SHA256 签名。执行前比对，防止 Agent 审批后篡改参数——这是审批机制的核心安全点。

## 索引
- agent_tasks: task_no(唯一)、created_at
- knowledge_chunks: document_id、embedding(HNSW)
- audit_logs: created_at
- approvals: status、task_id

## DDL
完整 PostgreSQL DDL 见 `database/init.sql`（含 pgvector 扩展与 HNSW 索引）。
SQLite 由 SQLAlchemy `create_all` 自动建表。

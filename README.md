# OpsPilot AI — 企业级智能 IT 运维 Agent 平台

> 基于 FastAPI + LangGraph 思想 + RAG 的智能运维诊断 Agent。支持故障诊断、多工具自主编排、企业知识检索、人工审批与执行轨迹追踪。

## ⭐ 怎么打开（最简单）

在 Windows 文件资源管理器里进入本项目文件夹 `opspilot-ai`：

1. **双击 `一键启动.bat`** → 会自动启动后端服务，并打开浏览器控制台
2. 等几秒，浏览器里出现登录页 → 输入 `operator` / `123456` → 登录即可用
3. 用完想关：双击 `停止服务.bat`，或直接关掉那个黑色的 "OpsPilot AI Backend" 窗口

> 当前服务已经在运行的话，直接双击 `frontend/index.html` 打开控制台即可（登录 operator / 123456）。

---

## 一、项目亮点速览

- **真 Agent，不是固定流程**：Planner 根据问题类型**自主选择工具**（HTTP 500 → 日志+监控+数据库+RAG；Redis 故障 → 监控+日志+RAG），不同问题走不同工具组合。
- **双栈可降级设计**：
  - LLM：配了 DeepSeek 兼容 API 走 Function Calling；**没配则用内置规则引擎，全功能可演示**。
  - 数据库：默认 SQLite 零依赖开箱即跑；改一行配置切 PostgreSQL + pgvector。
  - 向量：默认本地哈希向量；可切换 BGE 中文语义模型。
- **完整企业特性**：JWT + RBAC 三级权限、高风险操作人工审批（含参数签名防篡改）、审计日志、执行轨迹、SSE 实时推送。
- **可评测**：32 个故障测试集 + 评测脚本，实测工具选择准确率 **99%**、结论关键词命中率 **85.9%**、平均响应 **70ms**。

## 二、5 分钟快速启动

### 方式 A：零依赖演示（推荐，你现在的环境）

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\python.exe -m pip install -r requirements-core.txt
# 启动
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开：
- API 文档：http://127.0.0.1:8000/docs
- 控制台前端：**直接双击 `frontend/index.html`**（无需 npm）

### 方式 B：接入真实 LLM（可选）

复制 `backend/.env.example` 为 `backend/.env`，填入：
```
LLM_API_KEY=你的key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
```
重启后自动切换为真实模型驱动的工具选择（根目录 `/` 接口的 `llm_mode` 会变成 `real`）。

### 方式 C：生产基础设施（可选）

```bash
docker compose up -d   # 启动 PostgreSQL(pgvector) + Redis
```
然后 `.env` 里把 `DATABASE_URL` 改成 postgresql+asyncpg 连接串。

## 三、演示账号

| 账号 | 密码 | 角色 | 权限 |
|---|---|---|---|
| operator | 123456 | 运维员 | 发起诊断、看报告 |
| manager | 123456 | 运维负责人 | 审批高风险操作、管工单 |
| admin | 123456 | 管理员 | 管用户、知识库 |

## 四、体验路径

1. 登录控制台 → 运维总览看微服务健康状态。
2. Agent 诊断 → 点快捷问题「订单服务大量 HTTP 500」→ 看右侧**实时执行过程**（节点→工具→证据）。
3. 执行轨迹 → 查看节点耗时、工具参数、完整证据链。
4. 知识库 → 语义检索「数据库连接池耗尽怎么办」。
5. 接真实 LLM 后，可触发 `restart_service` 高风险操作 → 用 manager 登录审批（含参数签名防篡改校验）。

## 五、技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 前端 | 原生 JS 单页控制台 | 零构建；Vue3 版结构见设计文档 |
| API | FastAPI + Pydantic | 统一响应、参数校验 |
| 鉴权 | JWT + bcrypt + RBAC | 三级角色 |
| Agent | LangGraph 思想自研图引擎 | 状态/节点/条件边/循环；附 LangGraph 迁移路径 |
| LLM | DeepSeek 兼容 API / 规则引擎 | Function Calling，可插拔 |
| RAG | 切片 + 哈希/BGE 向量 + 余弦检索 | 可选 pgvector |
| 存储 | SQLite / PostgreSQL+pgvector | 双栈 |
| 缓存 | Redis（可选） | |
| 部署 | Docker Compose | |

## 六、项目结构

```
opspilot-ai/
├── backend/app/
│   ├── core/        # 配置、安全、日志
│   ├── api/         # 路由与端点
│   ├── agent/       # LLM封装、State、节点、图编排  ← Agent 核心
│   ├── tools/       # 工具实现 + 注册中心 + 风险等级
│   ├── rag/         # 加载/切片/Embedding/检索
│   ├── models/      # 数据库实体
│   ├── schemas/     # 接口 Schema
│   └── services/    # 业务编排
├── frontend/index.html  # 免构建控制台
├── database/init.sql    # PostgreSQL DDL
├── mock-data/           # 模拟运维数据
├── docs/                # PRD / 架构 / 数据库
└── tests/               # 端到端 + 审批 + 评测脚本与报告
```

## 七、测试与评测

```bash
# 端到端（需服务运行）
python tests/e2e_test.py
# 审批安全逻辑
cd backend && .venv/Scripts/python.exe ../tests/test_approval.py
# Agent 评测（32 案例，生成 eval_report.json）
python tests/evaluate.py
```

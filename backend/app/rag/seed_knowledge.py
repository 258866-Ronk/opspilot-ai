"""
演示用运维知识文档（Runbook）
这些是「历史故障处理方案」，RAG 会检索它们来辅助诊断。
真实项目里这些来自 PDF/Confluence/工单系统。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.knowledge import KnowledgeDocument
from app.rag.pipeline import ingest_text

RUNBOOKS = {
    "订单服务HTTP500故障处理Runbook.txt": """
# 订单服务 HTTP 500 故障处理 Runbook

## 现象
order-service 出现大量 HTTP 500 错误，平均响应时间从 120ms 飙升至 2000ms 以上，网关侧观察到上游返回 500。

## 常见根因
1. 数据库连接池耗尽：HikariPool 报 "Connection is not available, request timed out after 30000ms"。
2. 慢查询堆积：订单表缺少索引导致全表扫描，连接被长时间占用。
3. 下游服务（支付、库存）超时引发级联失败。

## 排查步骤
1. 查询 order-service 错误日志，确认是否有连接超时堆栈。
2. 查询监控指标：错误率、P99 响应时间、内存使用率。
3. 诊断数据库连接池：.active_connections / max_connections 是否 > 0.9。
4. 检索历史相似故障工单。

## 处理方案
- 连接池耗尽：临时扩大 maxPoolSize，随后排查慢查询并加索引；必要时重启服务释放连接（需审批）。
- 慢查询：为 orders(user_id, created_at) 添加联合索引。
- 级联失败：先恢复下游服务再重启 order-service。

## 预防措施
- 连接池使用率超过 80% 配置告警。
- 慢查询超过 1s 记录并告警。
""",
    "数据库连接池耗尽故障复盘.txt": """
# 数据库连接池耗尽故障复盘

## 故障概述
某日下午 order-service 大量报 HTTP 500，持续 12 分钟。根因是数据库连接池耗尽。

## 时间线
- 14:02 订单导入任务启动，批量写入 50 万条订单。
- 14:05 慢查询增多，连接被长时间占用。
- 14:08 HikariPool 连接池 95/100，新请求获取连接超时 30s。
- 14:10 大量 HTTP 500 出现，告警触发。
- 14:14 运维扩容连接池并限流导入任务，服务恢复。

## 根因分析
批量导入任务使用了未加索引的查询，每个连接被占用数秒，连接池被打满。
连接超时进一步导致 Spring 事务回滚，产生 HTTP 500。

## 改进项
1. 为 orders 表添加 (user_id, created_at) 联合索引。
2. 批量导入改为分页 + 限速。
3. 连接池使用率 > 80% 触发告警。
4. 引入连接池隔离：导入任务使用独立连接池。

## 关键词
connection timeout, HikariPool, 连接池耗尽, HTTP 500, order-service, 慢查询
""",
    "Redis连接失败处理指南.txt": """
# Redis 连接失败处理指南

## 现象
payment-service 报 "Redis connection refused: 127.0.0.1:6379"，缓存不可用，接口响应变慢。

## 排查
1. 检查 Redis 进程是否存活：redis-cli ping。
2. 检查连接配置：host/port/password 是否正确。
3. 检查网络策略/防火墙。

## 处理
- Redis 宕机：重启 Redis 服务（高风险，需审批）。
- 配置错误：修正配置并滚动重启应用。
- 缓存击穿：临时降级为本地缓存，限流保护 DB。

## 关键词
Redis, connection refused, payment-service, 缓存, 降级
""",
}


async def seed_knowledge(session: AsyncSession) -> int:
    """首次启动时把演示 Runbook 入库（已入库则跳过）"""
    count = 0
    for filename, text in RUNBOOKS.items():
        exists = await session.execute(
            select(KnowledgeDocument).where(KnowledgeDocument.filename == filename)
        )
        if exists.scalar_one_or_none() is None:
            await ingest_text(session, filename, text)
            count += 1
    return count

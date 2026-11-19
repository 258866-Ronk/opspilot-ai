"""数据库诊断工具（模拟数据）"""
from typing import Any


MOCK_DATABASE = {
    "status": "WARNING",
    "active_connections": 95,
    "max_connections": 100,
    "connection_timeout_seconds": 30,
    "slow_query_count": 12,
    "replication_lag_seconds": 0.5,
    "deadlocks_last_hour": 2,
}


async def diagnose_database() -> dict[str, Any]:
    usage = MOCK_DATABASE["active_connections"] / MOCK_DATABASE["max_connections"]
    findings = []
    if usage > 0.9:
        findings.append(f"连接池使用率高达 {usage*100:.0f}%，接近耗尽")
    if MOCK_DATABASE["slow_query_count"] > 5:
        findings.append(f"慢查询数量偏多：{MOCK_DATABASE['slow_query_count']} 条")
    if MOCK_DATABASE["deadlocks_last_hour"] > 0:
        findings.append(f"最近 1 小时发生 {MOCK_DATABASE['deadlocks_last_hour']} 次死锁")

    return {
        "success": True,
        "database": MOCK_DATABASE,
        "connection_usage": round(usage, 2),
        "findings": findings,
        "analysis_hint": "；".join(findings) if findings else "数据库状态正常",
        "likely_cause": "连接池耗尽可能导致应用获取连接超时，进而引发 HTTP 500" if usage > 0.9 else None,
    }

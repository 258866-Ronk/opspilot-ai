"""日志查询工具（模拟数据）"""
from datetime import datetime, timedelta, timezone
from typing import Any
from pydantic import BaseModel, Field


class LogSearchParams(BaseModel):
    service_name: str = Field(description="服务名，如 order-service")
    keyword: str = Field(default="", description="关键词，如 ERROR / timeout")
    minutes: int = Field(default=60, ge=1, le=10080, description="查询最近 N 分钟")
    level: str = Field(default="", description="日志级别过滤：ERROR/WARN/INFO")


# 模拟日志库：真实项目里这里会对接 ELK / Loki
MOCK_LOGS: list[dict] = [
    {"service": "order-service", "level": "ERROR", "timestamp": datetime.now(timezone.utc).isoformat(),
     "message": "Database connection timeout after 30000ms", "trace_id": "a1b2c3"},
    {"service": "order-service", "level": "ERROR", "timestamp": datetime.now(timezone.utc).isoformat(),
     "message": "HikariPool-1 - Connection is not available, request timed out after 30000ms", "trace_id": "a1b2c3"},
    {"service": "order-service", "level": "ERROR", "timestamp": datetime.now(timezone.utc).isoformat(),
     "message": "HTTP 500 Internal Server Error on POST /api/orders", "trace_id": "d4e5f6"},
    {"service": "order-service", "level": "WARN", "timestamp": datetime.now(timezone.utc).isoformat(),
     "message": "Slow query detected: SELECT * FROM orders WHERE user_id = ? (3210ms)", "trace_id": "d4e5f6"},
    {"service": "user-service", "level": "INFO", "timestamp": datetime.now(timezone.utc).isoformat(),
     "message": "User login success", "trace_id": "u1001"},
    {"service": "payment-service", "level": "ERROR", "timestamp": datetime.now(timezone.utc).isoformat(),
     "message": "Redis connection refused: 127.0.0.1:6379", "trace_id": "p2001"},
    {"service": "gateway-service", "level": "WARN", "timestamp": datetime.now(timezone.utc).isoformat(),
     "message": "Upstream order-service returned 500", "trace_id": "g3001"},
]


async def search_logs(service_name: str, keyword: str = "", minutes: int = 60, level: str = "") -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=minutes)
    matched = []
    for log in MOCK_LOGS:
        ts = datetime.fromisoformat(log["timestamp"])
        if log["service"] != service_name:
            continue
        if ts < start:
            continue
        if level and log["level"] != level:
            continue
        if keyword and keyword.lower() not in log["message"].lower():
            continue
        matched.append(log)

    # 统计各级别数量
    level_counts: dict[str, int] = {}
    for log in matched:
        level_counts[log["level"]] = level_counts.get(log["level"], 0) + 1

    return {
        "success": True,
        "service": service_name,
        "time_range_minutes": minutes,
        "total": len(matched),
        "level_counts": level_counts,
        "logs": matched[:20],  # 模拟截断，避免上下文过长
        "analysis_hint": "发现大量 ERROR 日志，关键词集中在 connection timeout / pool" if level_counts.get("ERROR", 0) >= 2 else "日志量正常",
    }

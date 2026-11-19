"""监控指标查询工具（模拟数据）"""
from typing import Any
from pydantic import BaseModel, Field


class MetricsQueryParams(BaseModel):
    service_name: str = Field(description="服务名")


MOCK_METRICS: dict[str, dict] = {
    "order-service": {
        "cpu_usage": 78.5, "memory_usage": 82.3,
        "error_rate": 15.6, "avg_response_time_ms": 2300,
        "p99_response_time_ms": 5800, "request_qps": 1200,
        "status": "DEGRADED",
    },
    "user-service": {
        "cpu_usage": 35.2, "memory_usage": 42.1,
        "error_rate": 0.5, "avg_response_time_ms": 120,
        "p99_response_time_ms": 310, "request_qps": 800,
        "status": "HEALTHY",
    },
    "payment-service": {
        "cpu_usage": 45.0, "memory_usage": 55.0,
        "error_rate": 8.2, "avg_response_time_ms": 900,
        "p99_response_time_ms": 2100, "request_qps": 300,
        "status": "DEGRADED",
    },
    "product-service": {
        "cpu_usage": 20.1, "memory_usage": 30.0,
        "error_rate": 0.1, "avg_response_time_ms": 80,
        "p99_response_time_ms": 190, "request_qps": 500,
        "status": "HEALTHY",
    },
    "gateway-service": {
        "cpu_usage": 60.0, "memory_usage": 58.0,
        "error_rate": 3.4, "avg_response_time_ms": 450,
        "p99_response_time_ms": 1200, "request_qps": 2800,
        "status": "HEALTHY",
    },
}


async def query_metrics(service_name: str) -> dict[str, Any]:
    metrics = MOCK_METRICS.get(service_name)
    if metrics is None:
        return {"success": False, "message": f"Service '{service_name}' not found",
                "available_services": list(MOCK_METRICS.keys())}

    anomalies = []
    if metrics["error_rate"] > 5:
        anomalies.append(f"错误率偏高 {metrics['error_rate']}%")
    if metrics["avg_response_time_ms"] > 1000:
        anomalies.append(f"平均响应时间过长 {metrics['avg_response_time_ms']}ms")
    if metrics["memory_usage"] > 80:
        anomalies.append(f"内存使用率偏高 {metrics['memory_usage']}%")

    return {
        "success": True,
        "service": service_name,
        "metrics": metrics,
        "anomalies": anomalies,
        "analysis_hint": "; ".join(anomalies) if anomalies else "各项指标正常",
    }

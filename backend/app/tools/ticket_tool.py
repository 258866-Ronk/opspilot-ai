"""工单创建工具 + 高风险操作工具（模拟执行）"""
from typing import Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class CreateTicketParams(BaseModel):
    title: str = Field(description="工单标题")
    service_name: str = Field(description="服务名")
    severity: str = Field(default="P2", description="严重程度 P0-P3")
    description: str = Field(default="", description="工单描述")


class RestartServiceParams(BaseModel):
    service_name: str = Field(description="要重启的服务名")
    reason: str = Field(default="", description="重启原因")


async def create_ticket(title: str, service_name: str, severity: str = "P2", description: str = "") -> dict[str, Any]:
    """创建工单：中风险，自动执行（生产环境应加权限校验）"""
    ticket_no = f"INC-{int(datetime.now(timezone.utc).timestamp())}"
    return {
        "success": True,
        "ticket_no": ticket_no,
        "title": title,
        "service_name": service_name,
        "severity": severity,
        "status": "OPEN",
        "message": f"工单 {ticket_no} 创建成功（模拟）",
    }


async def restart_service(service_name: str, reason: str = "") -> dict[str, Any]:
    """重启服务：高风险，必须审批，且这里只模拟不真实执行"""
    return {
        "success": True,
        "action": "restart_service",
        "service_name": service_name,
        "reason": reason,
        "message": f"[模拟执行] 已重启 {service_name}。真实环境此处会调用 K8s/运维平台 API。",
        "simulated": True,
    }


async def notify_oncall(service_name: str, message: str = "") -> dict[str, Any]:
    """通知值班人：中风险"""
    return {
        "success": True,
        "action": "notify_oncall",
        "service_name": service_name,
        "message": f"[模拟] 已通知 {service_name} 值班工程师：{message}",
        "simulated": True,
    }

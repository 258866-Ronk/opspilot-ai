"""API 路由汇总"""
from fastapi import APIRouter
from app.api.endpoints import auth, agent, knowledge, incident

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["认证"])
api_router.include_router(agent.router, prefix="/agent", tags=["Agent 核心"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["知识库"])
api_router.include_router(incident.router, prefix="/incidents", tags=["工单与监控"])

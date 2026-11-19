"""
OpsPilot AI 后端入口
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging, logger
from app.api.router import api_router
from app.models.base import init_db, engine
from app.rag.seed_knowledge import seed_knowledge
from app.models.base import AsyncSessionLocal


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化数据库和种子数据"""
    setup_logging(settings.DEBUG)
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)
    await init_db()
    # 入库演示知识文档
    async with AsyncSessionLocal() as session:
        n = await seed_knowledge(session)
        if n:
            logger.info("Seeded %d demo knowledge documents", n)
    yield
    await engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    description="企业级智能 IT 运维 Agent 平台",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 开发环境放开；生产应配置具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_PREFIX)


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "llm_mode": "real" if settings.llm_enabled else "rule-based (fallback)",
        "database": "postgresql" if settings.is_postgres else "sqlite",
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "opspilot-ai"}

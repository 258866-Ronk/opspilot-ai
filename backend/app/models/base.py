"""
SQLAlchemy 声明式基类 + 数据库会话管理
=====================================
双栈设计：
  - 默认 SQLite：零依赖，clone 下来就能跑，方便演示和教学
  - 生产 PostgreSQL：改 DATABASE_URL 即可，模型代码不用动
  - pgvector 向量类型也做了兼容：SQLite 下退化为 JSON 存储向量
"""
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import settings
from app.core.logging import logger

# 根据 URL 决定引擎参数（SQLite 需要特殊处理）
_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

_engine_kwargs = {"echo": False, "future": True}
if _is_sqlite:
    # SQLite 用文件数据库，需要允许跨线程
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


class Base(DeclarativeBase):
    pass


async def init_db():
    """建表。开发期用 create_all；生产环境应该用 Alembic 迁移脚本。"""
    import asyncio
    from app.models import user, task, incident, approval, knowledge  # noqa: F401

    if _is_sqlite:
        import os
        os.makedirs("data", exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info(" Database initialized (SQLite=%s)", _is_sqlite)
    await seed_default_users()


async def seed_default_users():
    """种子数据：建 3 个演示账号，方便立刻登录体验。"""
    from app.models.user import User
    from app.core.security import hash_password

    demo_users = [
        ("operator", "123456", "运营小王", "OPERATOR"),
        ("manager", "123456", "运维张经理", "MANAGER"),
        ("admin", "123456", "系统管理员", "ADMIN"),
    ]
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        for username, pwd, nickname, role in demo_users:
            result = await session.execute(select(User).where(User.username == username))
            if result.scalar_one_or_none() is None:
                session.add(User(
                    username=username,
                    password_hash=hash_password(pwd),
                    email=f"{username}@opspilot.demo",
                    nickname=nickname,
                    role=role,
                ))
        await session.commit()
    logger.info(" Seed users ready: operator / manager / admin (pwd: 123456)")


async def get_db():
    """FastAPI 依赖注入：每个请求拿到独立 session，用完自动关闭。"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

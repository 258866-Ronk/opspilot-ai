"""
配置管理模块
============
为什么需要它：
  1. 把「会变化的东西」（数据库地址、API Key、模型名）从代码里抽出来，
     放到环境变量或 .env 文件。这样同一份代码可以在开发/测试/生产环境切换，
     也不至于把密码写死在代码里提交到 GitHub。
  2. pydantic-settings 的 BaseSettings 会自动读取环境变量和 .env 文件，
     而且带类型校验和默认值——比如 DEBUG 会自动把 "true" 转成布尔 True。

面试点：
  - 配置与代码分离（12-Factor App 原则）
  - 用 Pydantic 做启动前的配置校验，配置错了服务根本起不来，fail-fast
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ---- 应用基础 ----
    APP_NAME: str = "OpsPilot AI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    API_PREFIX: str = "/api/v1"

    # ---- 数据库 ----
    # 默认用 SQLite（零依赖，开箱即跑）。
    # 想切 PostgreSQL：改成 postgresql+asyncpg://user:pass@host:5432/opspilot
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/opspilot.db"

    # ---- Redis（可选，没装也不影响启动）----
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_ENABLED: bool = False

    # ---- LLM（可选，没填 Key 自动降级到规则引擎）----
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = ""      # 例：https://api.deepseek.com
    LLM_MODEL: str = ""         # 例：deepseek-chat
    LLM_TIMEOUT: int = 60

    # ---- Embedding（可选，没装模型自动降级到本地哈希向量）----
    EMBEDDING_PROVIDER: str = "local"   # local | model
    EMBEDDING_MODEL: str = "BAAI/bge-small-zh-v1.5"
    EMBEDDING_DIM: int = 384            # 本地哈希向量的维度

    # ---- JWT ----
    SECRET_KEY: str = "dev-only-change-this-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    # ---- Agent ----
    MAX_TOOL_RETRIES: int = 2
    MAX_AGENT_STEPS: int = 15

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",   # 忽略 .env 里多出来的字段，避免启动报错
    )

    @property
    def llm_enabled(self) -> bool:
        """是否配置了真实 LLM。没配就走规则引擎降级。"""
        return bool(self.LLM_API_KEY and self.LLM_BASE_URL and self.LLM_MODEL)

    @property
    def is_postgres(self) -> bool:
        return self.DATABASE_URL.startswith("postgresql")


@lru_cache()
def get_settings() -> Settings:
    """单例配置：避免每次调用都重新读一遍 .env 文件。"""
    return Settings()


settings = get_settings()

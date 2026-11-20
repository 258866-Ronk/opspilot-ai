"""
安全模块：密码哈希 + JWT 令牌 + RBAC 权限
=========================================
设计要点：
  - 密码绝不能明文存储 → 用 passlib bcrypt 加盐哈希
  - JWT 无状态鉴权 → 服务端不存 session，适合分布式
  - RBAC 基于角色 → 用依赖注入把「当前用户」和「角色要求」注入到接口
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
import bcrypt

from app.core.config import settings

ALGORITHM = "HS256"


def _safe_bytes(password: str) -> bytes:
    # bcrypt 限制密码 <= 72 字节，超长需截断
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    """直接用 bcrypt 官方 API，避免 passlib 与新版 bcrypt 的兼容性问题"""
    return bcrypt.hashpw(_safe_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_safe_bytes(plain), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


# ---- 角色与权限 ----
ROLE_OPERATOR = "OPERATOR"   # 普通运维：发起分析、看报告
ROLE_MANAGER = "MANAGER"     # 运维负责人：审批、管工单
ROLE_ADMIN = "ADMIN"         # 管理员：用户、知识库、工具权限

ROLE_HIERARCHY = {ROLE_OPERATOR: 1, ROLE_MANAGER: 2, ROLE_ADMIN: 3}


def has_role(user_role: str, required: str) -> bool:
    """层级式权限：ADMIN 拥有所有低阶权限。"""
    return ROLE_HIERARCHY.get(user_role, 0) >= ROLE_HIERARCHY.get(required, 99)

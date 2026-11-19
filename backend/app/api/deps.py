"""FastAPI 依赖注入：当前用户 / 角色校验"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.base import get_db
from app.models.user import User
from app.core.security import decode_access_token, has_role

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user(token: str | None = Depends(oauth2_scheme),
                           db: AsyncSession = Depends(get_db)) -> User:
    if not token:
        raise HTTPException(status_code=401, detail="未登录：缺少访问令牌")
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")
    result = await db.execute(select(User).where(User.username == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    if user.status != "ACTIVE":
        raise HTTPException(status_code=403, detail="用户已被禁用")
    return user


def require_role(role: str):
    """角色守卫工厂：require_role('MANAGER')"""
    def checker(user: User = Depends(get_current_user)) -> User:
        if not has_role(user.role, role):
            raise HTTPException(status_code=403, detail=f"权限不足，需要 {role} 角色")
        return user
    return checker

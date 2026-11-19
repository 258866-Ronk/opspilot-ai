"""认证接口：注册 / 登录 / 当前用户"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.base import get_db
from app.models.user import User
from app.core.security import hash_password, verify_password, create_access_token
from app.api.deps import get_current_user
from app.schemas.common import ApiResponse

router = APIRouter()


class RegisterReq(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=64)
    email: str | None = None
    nickname: str | None = None


class LoginReq(BaseModel):
    username: str
    password: str


@router.post("/register", response_model=ApiResponse)
async def register(req: RegisterReq, db: AsyncSession = Depends(get_db)):
    exists = await db.execute(select(User).where(User.username == req.username))
    if exists.scalar_one_or_none():
        raise HTTPException(400, "用户名已存在")
    user = User(username=req.username, password_hash=hash_password(req.password),
                email=req.email, nickname=req.nickname, role="OPERATOR")
    db.add(user)
    await db.commit()
    return ApiResponse(data={"username": user.username, "role": user.role})


@router.post("/login", response_model=ApiResponse)
async def login(req: LoginReq, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    token = create_access_token({"sub": user.username, "role": user.role, "uid": user.id})
    return ApiResponse(data={
        "access_token": token, "token_type": "bearer",
        "username": user.username, "nickname": user.nickname, "role": user.role,
    })


@router.get("/me", response_model=ApiResponse)
async def me(user: User = Depends(get_current_user)):
    return ApiResponse(data={
        "username": user.username, "nickname": user.nickname,
        "role": user.role, "email": user.email,
    })

"""认证路由：/login /me /logout。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUserDep, get_db
from app.api.schemas.auth_request import LoginRequest
from app.api.schemas.auth_response import LoginResponse, MeResponse
from app.services.auth_service import AuthService, build_auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def get_auth_service(session: Annotated[AsyncSession, Depends(get_db)]) -> AuthService:
    """FastAPI 依赖：构造 AuthService（DB Session 由 get_db 注入）。"""
    return build_auth_service(session)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


@router.post("/login", response_model=LoginResponse)
async def login(data: LoginRequest, service: AuthServiceDep) -> LoginResponse:
    """登录端点（公开）。"""
    return await service.login(data.username, data.password)


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUserDep, service: AuthServiceDep) -> MeResponse:
    """当前用户信息（需登录）。"""
    return await service.me(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(user: CurrentUserDep, service: AuthServiceDep) -> Response:
    """登出（需登录）：清 Redis 位图。"""
    await service.logout(user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

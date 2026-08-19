"""FastAPI 依赖注入：DB Session / CurrentUser / require_permission 工厂。

> T01：AuthService 已就绪，get_current_user 走真实链路。
> 剩余服务 Depends 占位留待 T02+ 替换。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import (
    AuthenticationError,
    PermissionDeniedError,
)
from app.domain.user import CurrentUser
from app.infrastructure.database import get_db
from app.infrastructure.jwt import JWTIssuer, get_jwt_issuer
from app.infrastructure.redis_client import RedisClient, get_redis
from app.services.auth_service import build_auth_service

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    jwt_issuer: Annotated[JWTIssuer, Depends(get_jwt_issuer)],
    redis: Annotated[RedisClient, Depends(get_redis)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> CurrentUser:
    """FastAPI 依赖：解析 Authorization Bearer，校验 JWT + 加载完整 CurrentUser。

    流程：
    1. Bearer 头缺失 → AuthenticationError(401)
    2. jwt_issuer.verify() 失败 → InvalidAccessTokenError(401)
    3. AuthService.load_current_user 加载部门链/角色码/部门名
    4. Redis 鉴权位图查询 → permissions（缺失则空列表，触发 RBAC 拦截）
    5. 返回 CurrentUser
    """
    if credentials is None:
        raise AuthenticationError("missing bearer token")
    payload = jwt_issuer.verify(credentials.credentials)
    service = build_auth_service(session, jwt_issuer=jwt_issuer, redis=redis)
    current = await service.load_current_user(int(payload.sub))
    current.permissions = await redis.get_bitmap(current.id) or []
    return current


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require_permission(*codes: str) -> Callable:
    """工厂：生成 FastAPI 依赖，校验 CurrentUser 是否含 codes 任一权限码。"""

    async def checker(user: CurrentUserDep) -> None:
        if not any(code in user.permissions for code in codes):
            raise PermissionDeniedError(f"missing permission: {','.join(codes)}")

    return Depends(checker)


# ── 兼容占位（PR0 留下的 type alias，供后续模块平滑切换） ─────────────────────────────

# 鉴权
AuthServiceDep = Annotated[None, Depends(lambda: None)]  # placeholder
AuthRepositoryDep = Annotated[None, Depends(lambda: None)]

# 组织架构（M2）
UserServiceDep = Annotated[None, Depends(lambda: None)]
DepartmentServiceDep = Annotated[None, Depends(lambda: None)]
RoleServiceDep = Annotated[None, Depends(lambda: None)]

# 知识资产（M3）
KnowledgeServiceDep = Annotated[None, Depends(lambda: None)]

# AI 问答（M4）
AIServiceDep = Annotated[None, Depends(lambda: None)]

# 数据看板（M5）
DashboardServiceDep = Annotated[None, Depends(lambda: None)]

# 知识沉淀（M6）
FaqServiceDep = Annotated[None, Depends(lambda: None)]
KnowledgeGapServiceDep = Annotated[None, Depends(lambda: None)]


def http_error_from_app_error(exc: Exception) -> HTTPException:
    """AppError → FastAPI HTTPException 转换（在全局 ExceptionHandler 调用）。"""
    if isinstance(exc, AuthenticationError):
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": getattr(exc, "error_code", "authentication_required")},
        )
    if isinstance(exc, PermissionDeniedError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error_code": getattr(exc, "error_code", "permission_denied")},
        )
    if hasattr(exc, "status_code") and hasattr(exc, "error_code"):
        return HTTPException(
            status_code=exc.status_code,  # type: ignore[attr-defined]
            detail={"error_code": exc.error_code},  # type: ignore[attr-defined]
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"error_code": "internal_error"},
    )

"""FastAPI 依赖注入：DB Session / CurrentUser / require_permission 工厂。

> PR0 阶段仅提供占位 + CurrentUser 框架；具体 AuthService 实现留给 T01。
> T01 完成后会扩展此文件加载完整 CurrentUser（dept_ids + permissions）。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.common.errors import (
    AuthenticationError,
    PermissionDeniedError,
)
from app.domain.user import CurrentUser
from app.infrastructure.jwt import JWTIssuer, get_jwt_issuer
from app.infrastructure.redis_client import RedisClient, get_redis

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    jwt_issuer: Annotated[JWTIssuer, Depends(get_jwt_issuer)],
    redis: Annotated[RedisClient, Depends(get_redis)],
) -> CurrentUser:
    """FastAPI 依赖：解析 Authorization: Bearer，校验 JWT + 加载鉴权位图。

    流程：
    1. 检查 Bearer 头缺失 → AuthenticationError(401)
    2. jwt_issuer.verify() → TokenPayload；签名/过期失败 → InvalidAccessTokenError(401)
    3. Redis 鉴权位图查询 → permissions（缺失则空列表，触发 RBAC 拦截）
    4. 组装 CurrentUser 返回
    """
    if credentials is None:
        raise AuthenticationError("missing bearer token")
    payload = jwt_issuer.verify(credentials.credentials)  # raises InvalidAccessTokenError
    user_id = int(payload.sub)
    permissions = await redis.get_bitmap(user_id) or []

    return CurrentUser(
        id=user_id,
        username=payload.username,
        display_name="",  # 由 AuthService.load_current_user 补全
        department_id=0,
        role_codes=payload.role_codes,
        permissions=permissions,
        dept_ids=[],
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require_permission(*codes: str) -> Callable:
    """工厂：生成 FastAPI 依赖，校验 CurrentUser 是否含 codes 任一权限码。

    用法：
        @router.get("/api/v1/users", dependencies=[require_permission("user:read")])
    """

    async def checker(user: CurrentUserDep) -> None:
        if not any(code in user.permissions for code in codes):
            raise PermissionDeniedError(f"missing permission: {','.join(codes)}")

    return Depends(checker)


# ── Service Depends 占位（PR0 阶段留空，T01+ 实现） ─────────────────────────────

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


# ── 导出 HTTPException 供其他模块复用 ─────────────────────────────


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

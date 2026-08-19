# IMPL-M1 — 认证鉴权（Python 方法级实现蓝图）

| 项目 | 内容 |
| --- | --- |
| 文档版本 | V1.0 |
| 阶段 | P0 |
| 编写依据 | [Spec M1](../specs/M1-认证鉴权.md) |
| 范围 | 完整方法级 Python 伪代码（中文注释）+ 完整 pytest 用例 |

---

## 1. 文件清单

```
app/
├── api/
│   ├── routers/auth_router.py
│   └── schemas/
│       ├── auth_request.py
│       └── auth_response.py
├── domain/
│   ├── user.py
│   └── permission.py
├── services/auth_service.py
├── repositories/auth_repository.py
├── infrastructure/
│   ├── jwt.py
│   └── password_hasher.py
└── api/dependencies.py                  # 与现有集成

tests/
├── test_auth_login.py
├── test_auth_me.py
├── test_auth_token.py
└── test_auth_permission.py
```

---

## 2. 后端实现

### 2.1 领域层

```python
# app/domain/user.py
"""用户领域实体与当前用户上下文。"""
from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class UserEntity:
    """纯领域实体；不含 ORM 依赖。"""
    id: int
    username: str
    display_name: str
    department_id: int
    status: int                         # 1=启用 / 0=停用


@dataclass(slots=True, frozen=True)
class UserWithPassword(UserEntity):
    """仅 Repository 内部使用；Service 层对外不应暴露 password_hash。"""
    password_hash: str


@dataclass(slots=True, frozen=True)
class CurrentUser:
    """登录后注入到请求上下文的当前用户信息。"""
    id: int
    username: str
    display_name: str
    department_id: int
    department_name: str
    role_codes: list[str]
    dept_ids: list[int]                 # 用户所属部门 + 所有祖先部门 id
    role_ids: list[int]


# app/domain/permission.py
"""权限码常量。"""
class PermissionCode:
    USER_READ = "user:read"
    USER_WRITE = "user:write"
    ROLE_READ = "role:read"
    ROLE_WRITE = "role:write"
    DEPT_READ = "dept:read"
    DEPT_WRITE = "dept:write"
    KNOWLEDGE_READ = "knowledge:read"
    KNOWLEDGE_WRITE = "knowledge:write"
    KNOWLEDGE_DELETE = "knowledge:delete"
    KNOWLEDGE_ASSIGN_PERMISSION = "knowledge:assign_permission"  # 新增（H3 修复）
    AI_CHAT = "ai:chat"
    KNOWLEDGE_CHECK = "knowledge:check"  # 新增（H1 修复）
    DASHBOARD_READ = "dashboard:read"
    FAQ_READ = "faq:read"
    FAQ_WRITE = "faq:write"
    FAQ_REVIEW = "faq:review"
    GAP_READ = "gap:read"
    # 注意：原 gap:write 已在 ADR-0007 后移除（H4 决议）

ALL_PERMISSION_CODES: list[str] = [
    "user:read", "user:write",
    "role:read", "role:write",
    "dept:read", "dept:write",
    "knowledge:read", "knowledge:write", "knowledge:delete", "knowledge:assign_permission",
    "knowledge:check", "ai:chat",
    "dashboard:read",
    "faq:read", "faq:write", "faq:review",
    "gap:read",
]
```

### 2.2 Repository 层

```python
# app/repositories/auth_repository.py
"""AuthRepository：users / user_roles / role_permissions 查询。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.user import UserWithPassword, CurrentUser
from app.infrastructure.database import UserRecord, UserRoleRecord, RoleRecord, RolePermissionRecord, DepartmentRecord


class AuthRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def find_by_username(self, username: str) -> UserWithPassword | None:
        """根据用户名查用户（含密码哈希）。"""
        stmt = select(UserRecord).where(UserRecord.username == username)
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        if record is None:
            return None
        return UserWithPassword(
            id=record.id,
            username=record.username,
            display_name=record.display_name,
            department_id=record.department_id,
            status=record.status,
            password_hash=record.password_hash,
        )

    async def list_role_codes(self, user_id: int) -> list[str]:
        """查用户的所有角色 code。"""
        stmt = (
            select(RoleRecord.role_code)
            .join(UserRoleRecord, UserRoleRecord.role_id == RoleRecord.id)
            .where(UserRoleRecord.user_id == user_id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_role_ids(self, user_id: int) -> list[int]:
        """查用户的所有角色 id（供鉴权位图使用）。"""
        stmt = select(UserRoleRecord.role_id).where(UserRoleRecord.user_id == user_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_dept_ids_with_ancestors(self, dept_id: int) -> list[int]:
        """查用户部门及其所有祖先部门 id（向上递归）。"""
        # 演示期部门层级 ≤ 3 层，单次查询即可；如层级较深可改用递归 CTE
        stmt = select(DepartmentRecord.id, DepartmentRecord.parent_id).where(
            DepartmentRecord.id == dept_id
        )
        result = await self._session.execute(stmt)
        row = result.first()
        if row is None:
            return []
        ids = [row.id]
        # 向上找 parent_id 直到 NULL
        current_id = row.parent_id
        while current_id is not None:
            ids.append(current_id)
            stmt2 = select(DepartmentRecord.parent_id).where(DepartmentRecord.id == current_id)
            r2 = await self._session.execute(stmt2)
            current_id = r2.scalar_one_or_none()
        return ids

    async def list_permissions(self, role_codes: list[str]) -> list[str]:
        """查多个角色的权限码并集。"""
        if not role_codes:
            return []
        stmt = (
            select(RolePermissionRecord.permission_code)
            .join(RoleRecord, RoleRecord.id == RolePermissionRecord.role_id)
            .where(RoleRecord.role_code.in_(role_codes))
        )
        result = await self._session.execute(stmt)
        # 去重
        return list(set(result.scalars().all()))

    async def find_department(self, dept_id: int) -> DepartmentRecord | None:
        """查部门信息（用于响应填充 department_name）。"""
        stmt = select(DepartmentRecord).where(DepartmentRecord.id == dept_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def load_current_user(self, user_id: int) -> CurrentUser | None:
        """组装 CurrentUser（含部门名 + 角色码 + 部门链 + 角色 id）。"""
        # 1. 查 user
        stmt = select(UserRecord).where(UserRecord.id == user_id)
        result = await self._session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None or user.status != 1:
            return None

        # 2. 查部门
        dept = await self.find_department(user.department_id)
        if dept is None:
            return None

        # 3. 查角色码 + id
        role_codes = await self.list_role_codes(user_id)
        role_ids = await self.list_role_ids(user_id)

        # 4. 查部门链
        dept_ids = await self.list_dept_ids_with_ancestors(user.department_id)

        return CurrentUser(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            department_id=user.department_id,
            department_name=dept.name,
            role_codes=role_codes,
            dept_ids=dept_ids,
            role_ids=role_ids,
        )

    async def update_password(self, user_id: int, password_hash: str) -> None:
        """更新密码哈希（admin 重置密码时调用）。"""
        stmt = select(UserRecord).where(UserRecord.id == user_id)
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        if record is None:
            raise UserNotFoundError(user_id)
        record.password_hash = password_hash
        await self._session.flush()
```

### 2.3 Service 层

```python
# app/services/auth_service.py
"""AuthService：登录 / 当前用户 / 登出的业务编排。"""
from loguru import logger

from app.config.settings import settings
from app.common.errors import (
    InvalidCredentialsError, UserDisabledError,
    AuthenticationRequiredError, InvalidAccessTokenError,
)
from app.domain.user import CurrentUser
from app.api.schemas.auth_response import LoginResponse, MeResponse, CurrentUserInfo
from app.infrastructure.jwt import JWTIssuer, TokenPayload
from app.infrastructure.password_hasher import PasswordHasher
from app.infrastructure.redis_client import RedisClient


class AuthService:
    def __init__(
        self,
        auth_repo: AuthRepository,
        password_hasher: PasswordHasher,
        jwt_issuer: JWTIssuer,
        redis: RedisClient,
    ):
        self._repo = auth_repo
        self._password_hasher = password_hasher
        self._jwt = jwt_issuer
        self._redis = redis

    async def login(self, username: str, password: str) -> LoginResponse:
        """登录流程。

        步骤：
        1. 查用户（含密码哈希）
        2. 校验账号状态（status == 1）
        3. 校验密码（bcrypt）
        4. 加载角色码 / 权限码 / 部门链
        5. 签发 JWT（HS256，8 小时）
        6. 写 Redis 鉴权位图（TTL 5 分钟）
        7. 构造响应
        """
        # 1. 查用户
        user = await self._repo.find_by_username(username)
        if user is None:
            logger.warning("auth.login.fail username={} reason=user_not_found", username)
            raise InvalidCredentialsError()      # 不区分"用户不存在"和"密码错误"，防枚举

        # 2. 校验账号状态
        if user.status != 1:
            logger.warning("auth.login.fail user_id={} reason=user_disabled", user.id)
            raise UserDisabledError()

        # 3. 校验密码（bcrypt cost=12，约 200ms）
        if not self._password_hasher.verify(password, user.password_hash):
            logger.warning("auth.login.fail user_id={} reason=wrong_password", user.id)
            raise InvalidCredentialsError()

        # 4. 加载角色 + 权限 + 部��链
        role_codes = await self._repo.list_role_codes(user.id)
        permissions = await self._repo.list_permissions(role_codes)
        dept = await self._repo.find_department(user.department_id)

        # 5. 签发 JWT
        access_token, expires_in = self._jwt.issue(
            user_id=user.id,
            username=user.username,
            role_codes=role_codes,
        )

        # 6. 写 Redis 鉴权位图（key: auth:bitmap:{user_id}，TTL 5 分钟）
        await self._redis.set_bitmap(
            user_id=user.id,
            permissions=permissions,
            ttl=settings.auth_bitmap_ttl_seconds,
        )

        # 7. 记录成功日志
        logger.info("auth.login.success user_id={} username={}", user.id, username)

        # 8. 构造响应
        return LoginResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=expires_in,
            user_info=CurrentUserInfo(
                id=user.id,
                username=user.username,
                display_name=user.display_name,
                department_id=user.department_id,
                department_name=dept.name if dept else "",
                role_codes=role_codes,
            ),
            permissions=permissions,
        )

    async def load_current_user(self, user_id: int) -> CurrentUser:
        """从 user_id  加载 CurrentUser（供 get_current_user 依赖注入）。"""
        current = await self._repo.load_current_user(user_id)
        if current is None:
            raise AuthenticationRequiredError()
        return current

    async def me(self, user: CurrentUser) -> MeResponse:
        """返回当前用户信息 + 权限。

        步骤：
        1. 读 Redis 鉴权位图；不存在则重算
        2. 返回 MeResponse
        """
        # 1. 读 Redis 位图
        cached = await self._redis.get_bitmap(user.id)
        if cached is None:
            # 位图过期或被踢出，重算
            cached = await self._repo.list_permissions(
                [code for code in user.role_codes]   # 用 role_codes 反查
            )
            # 重写回 Redis
            await self._redis.set_bitmap(
                user_id=user.id,
                permissions=cached,
                ttl=settings.auth_bitmap_ttl_seconds,
            )

        # 2. 构造响应
        return MeResponse(
            user_info=CurrentUserInfo(
                id=user.id,
                username=user.username,
                display_name=user.display_name,
                department_id=user.department_id,
                department_name=user.department_name,
                role_codes=user.role_codes,
            ),
            permissions=cached,
        )

    async def logout(self, user_id: int) -> None:
        """登出：清 Redis 鉴权位图（Token 因无状态不强制失效）。

        步骤：
        1. DEL auth:bitmap:{user_id}
        2. 记录日志
        """
        await self._redis.del_bitmap(user_id)
        logger.info("auth.logout user_id={}", user_id)
```

### 2.4 Infrastructure 层

```python
# app/infrastructure/redis_client.py
"""Redis 异步客户端：通用 KV + 鉴权位图 + FAQ 缓存 Hash 统一抽象。

## 方法分组
- 通用 KV: set / get / delete / exists
- 鉴权位图 (auth:bitmap:{user_id}): set_bitmap / get_bitmap / del_bitmap / del_bitmaps_by_role
- Hash (faq:cache:{hash}): hset / hgetall / hdel
- 单例: get_redis()
"""
from __future__ import annotations

import redis.asyncio as aioredis
from app.config.settings import settings


class RedisClient:
    """Redis 异步客户端封装。

    步骤：
    1. 构造时从 settings.redis_url 读连接
    2. 各类方法复用 self._client
    3. get_redis() FastAPI 依赖
    """

    def __init__(self, redis_url: str | None = None):
        url = redis_url or settings.redis_url
        self._client: aioredis.Redis = aioredis.from_url(url, decode_responses=True)

    # ===== 通用 KV =====
    async def set(self, key: str, value, ex: int | None = None) -> None:
        """SET key value [EX seconds]"""
        await self._client.set(key, value, ex=ex)

    async def get(self, key: str) -> str | None:
        return await self._client.get(key)

    async def delete(self, key: str) -> None:
        await self._client.delete(key)

    async def exists(self, key: str) -> bool:
        return bool(await self._client.exists(key))

    # ===== 鉴权位图（auth:bitmap:{user_id}）=====
    def _bitmap_key(self, user_id: int) -> str:
        return f"auth:bitmap:{user_id}"

    async def set_bitmap(self, *, user_id: int, permissions: list[str], ttl: int) -> None:
        """写入位图（JSON 列表 + TTL）"""
        import json
        await self._client.set(self._bitmap_key(user_id), json.dumps(permissions), ex=ttl)

    async def get_bitmap(self, user_id: int) -> list[str] | None:
        import json
        raw = await self._client.get(self._bitmap_key(user_id))
        if raw is None:
            return None
        return json.loads(raw)

    async def del_bitmap(self, user_id: int) -> None:
        await self._client.delete(self._bitmap_key(user_id))

    async def del_bitmaps_by_role(self, role_id: int) -> int:
        """删除所有持有 role_id 的用户的位图（用于角色权限变更后批量失效）。

        步骤：
        1. SCAN user_roles WHERE role_id=role_id
        2. 批量 DEL auth:bitmap:{user_id}
        """
        # 实际应通过 UserRoleRecord 查受影响的 user_ids —— 此处暴露方法签名
        # 实现由 IMPL-M2 RoleService 调用时注入的 repository 完成
        # 这里只演示高层 API
        raise NotImplementedError("Caller must inject dependency and call internally")

    # ===== Hash (faq:cache:{hash}) =====
    async def hset(self, key: str, mapping: dict) -> None:
        await self._client.hset(key, mapping=mapping)

    async def hgetall(self, key: str) -> dict:
        return await self._client.hgetall(key)

    async def hdel(self, key: str, *fields: str) -> None:
        await self._client.hdel(key, *fields)

    async def close(self) -> None:
        await self._client.aclose()


# 全局单例 + FastAPI 依赖
_redis_instance: RedisClient | None = None


def get_redis() -> RedisClient:
    """FastAPI 依赖：获取 RedisClient 单例。"""
    global _redis_instance
    if _redis_instance is None:
        _redis_instance = RedisClient()
    return _redis_instance
```

```python
# app/infrastructure/password_hasher.py
"""bcrypt 密码哈希与验证。"""
import bcrypt


class PasswordHasher:
    def __init__(self, cost: int = 12):
        self._cost = cost

    def hash(self, password: str) -> str:
        """生成 bcrypt 哈希。"""
        salt = bcrypt.gensalt(rounds=self._cost)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    def verify(self, password: str, password_hash: str) -> bool:
        """验证密码（恒定时间比较）。"""
        try:
            return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        except (ValueError, TypeError):
            return False


# app/infrastructure/jwt.py
"""JWT 签发与校验。"""
import time
from dataclasses import dataclass

import jwt

from app.config.settings import settings


@dataclass(slots=True, frozen=True)
class TokenPayload:
    """JWT 解码后的 Claims。"""
    sub: int                    # user_id
    username: str
    role_codes: list[str]
    iat: int
    exp: int


class JWTIssuer:
    def __init__(self, secret: str, algorithm: str = "HS256", expire_minutes: int = 480):
        self._secret = secret
        self._algorithm = algorithm
        self._expire_minutes = expire_minutes

    def issue(self, user_id: int, username: str, role_codes: list[str]) -> tuple[str, int]:
        """签发 JWT。

        返回 (token, expires_in_seconds)。
        """
        now = int(time.time())
        exp = now + self._expire_minutes * 60
        payload = {
            "sub": user_id,
            "username": username,
            "role_codes": role_codes,
            "iat": now,
            "exp": exp,
        }
        token = jwt.encode(payload, self._secret, algorithm=self._algorithm)
        return token, exp - now

    def verify(self, token: str) -> TokenPayload:
        """校验 JWT；过期/签名错误抛 InvalidTokenError。"""
        try:
            payload = jwt.decode(token, self._secret, algorithms=[self._algorithm])
        except jwt.ExpiredSignatureError as exc:
            raise InvalidAccessTokenError("token_expired") from exc
        except jwt.InvalidTokenError as exc:
            raise InvalidAccessTokenError("token_invalid") from exc

        return TokenPayload(
            sub=int(payload["sub"]),
            username=str(payload["username"]),
            role_codes=list(payload.get("role_codes", [])),
            iat=int(payload["iat"]),
            exp=int(payload["exp"]),
        )
```

### 2.5 API 层

```python
# app/api/routers/auth_router.py
"""认证路由：/login /me /logout。"""
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies import AuthServiceDep, CurrentUserDep
from app.api.schemas.auth_request import LoginRequest
from app.api.schemas.auth_response import LoginResponse, MeResponse
from app.domain.permission import PermissionCode
from app.domain.user import CurrentUser

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


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
```

```python
# app/api/dependencies.py（增量补丁）
"""依赖注入链。"""
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.domain.user import CurrentUser
from app.services.auth_service import AuthService
from app.infrastructure.jwt import JWTIssuer, InvalidAccessTokenError


_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    jwt_issuer: Annotated[JWTIssuer, Depends(get_jwt_issuer)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> CurrentUser:
    """从 Authorization Bearer 提取并校验 JWT，返回 CurrentUser。"""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication_required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt_issuer.verify(credentials.credentials)
    except InvalidAccessTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_access_token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return await auth_service.load_current_user(payload.sub)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require_permission(*codes: str):
    """RBAC 操作权限拦截工厂。

    用法：
        @router.get(..., dependencies=[Depends(require_permission("user:read"))])
    """
    async def checker(
        user: CurrentUserDep,
        redis: Annotated[RedisClient, Depends(get_redis)],
    ) -> None:
        cached = await redis.get_bitmap(user.id)
        perms = cached or []
        if not any(c in perms for c in codes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="permission_denied",
            )
    return Depends(checker)
```

---

## 3. 前端实现（精简）

```typescript
// frontend/src/api/auth.ts
import api from './client';

export interface LoginRequest { username: string; password: string; }
export interface CurrentUserInfo {
  id: number;
  username: string;
  display_name: string;
  department_id: number;
  department_name: string;
  role_codes: string[];
}
export interface LoginResponse {
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
  user_info: CurrentUserInfo;
  permissions: string[];
}
export interface MeResponse {
  user_info: CurrentUserInfo;
  permissions: string[];
}

/** 登录：保存 token 到 localStorage。 */
export const authApi = {
  login: async (data: LoginRequest): Promise<LoginResponse> => {
    const { data: resp } = await api.post<LoginResponse>('/auth/login', data);
    localStorage.setItem('kb_mp_token', resp.access_token);
    localStorage.setItem('kb_mp_user', JSON.stringify(resp.user_info));
    localStorage.setItem('kb_mp_perms', JSON.stringify(resp.permissions));
    return resp;
  },

  /** 当前用户：从 localStorage 同步读，避免每次请求额外打 /me。 */
  me: async (): Promise<MeResponse> => {
    const user_info = JSON.parse(localStorage.getItem('kb_mp_user') || '{}');
    const permissions = JSON.parse(localStorage.getItem('kb_mp_perms') || '[]');
    return { user_info, permissions };
  },

  /** 登出：清 localStorage + 通知服务端清 Redis 位图。 */
  logout: async (): Promise<void> => {
    await api.post('/auth/logout');
    localStorage.removeItem('kb_mp_token');
    localStorage.removeItem('kb_mp_user');
    localStorage.removeItem('kb_mp_perms');
  },
};
```

---

## 4. 测试用例（完整 pytest）

```python
# tests/test_auth_login.py
"""登录端点测试。"""
import pytest
from httpx import AsyncClient

from app.main_module import app


@pytest.mark.asyncio
class TestLogin:
    """POST /api/v1/auth/login 三种状态：成功 / 凭据错 / 账号停用。"""

    async def test_login_success_returns_token_and_permissions(self, async_client: AsyncClient, seeded_admin):
        """正确凭据返回 access_token + user_info + 17 个权限码。"""
        # Arrange: seeded_admin fixture 已创建 admin 用户并写入 bcrypt 哈希密码
        req = {"username": "admin", "password": "Admin@123"}

        # Act
        resp = await async_client.post("/api/v1/auth/login", json=req)

        # Assert
        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert isinstance(body["access_token"], str) and len(body["access_token"]) > 50
        assert body["expires_in"] == 480 * 60
        assert body["user_info"]["username"] == "admin"
        assert body["user_info"]["role_codes"] == ["system_admin"]
        assert "user:read" in body["permissions"]
        assert "user:write" in body["permissions"]
        assert len(body["permissions"]) == 17     # 系统管理员全权限

    async def test_login_wrong_password_returns_invalid_credentials(self, async_client, seeded_admin):
        """错误密码返回 401 invalid_credentials，不区分用户是否存在。"""
        req = {"username": "admin", "password": "WrongPassword"}
        resp = await async_client.post("/api/v1/auth/login", json=req)
        assert resp.status_code == 401
        assert resp.json()["error_code"] == "invalid_credentials"

    async def test_login_nonexistent_user_returns_invalid_credentials(self, async_client):
        """不存在的用户同样返回 invalid_credentials（防枚举）。"""
        req = {"username": "ghost_user", "password": "anything"}
        resp = await async_client.post("/api/v1/auth/login", json=req)
        assert resp.status_code == 401
        assert resp.json()["error_code"] == "invalid_credentials"

    async def test_login_disabled_user_returns_user_disabled(self, async_client, seeded_disabled_user):
        """status=0 用户返回 403 user_disabled。"""
        req = {"username": "disabled", "password": "Pass@1234"}
        resp = await async_client.post("/api/v1/auth/login", json=req)
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "user_disabled"

    async def test_login_validation_username_too_short(self, async_client):
        """username < 3 位返回 422。"""
        req = {"username": "ab", "password": "Pass@1234"}
        resp = await async_client.post("/api/v1/auth/login", json=req)
        assert resp.status_code == 422
        assert "username" in str(resp.json()["detail"])

    async def test_login_validation_password_too_short(self, async_client):
        """password < 6 位返回 422。"""
        req = {"username": "validuser", "password": "12345"}
        resp = await async_client.post("/api/v1/auth/login", json=req)
        assert resp.status_code == 422


# tests/test_auth_me.py
@pytest.mark.asyncio
class TestMe:
    """GET /api/v1/auth/me"""

    async def test_me_with_valid_token_returns_user_info(self, async_client, admin_token):
        """带有效 token 返回 user_info + permissions。"""
        resp = await async_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["user_info"]["username"] == "admin"
        assert "user:read" in body["permissions"]

    async def test_me_without_token_returns_401(self, async_client):
        """无 token 返回 401 authentication_required。"""
        resp = await async_client.get("/api/v1/auth/me")
        assert resp.status_code == 401
        assert resp.json()["error_code"] == "authentication_required"

    async def test_me_with_malformed_token_returns_401(self, async_client):
        """格式错误 token 返回 401 invalid_access_token。"""
        resp = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer not.a.jwt"},
        )
        assert resp.status_code == 401
        assert resp.json()["error_code"] == "invalid_access_token"

    async def test_me_with_expired_token_returns_401(self, async_client, expired_token):
        """过期 token 返回 401 invalid_access_token。"""
        resp = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert resp.status_code == 401
        assert resp.json()["error_code"] == "invalid_access_token"


# tests/test_auth_token.py
@pytest.mark.asyncio
class TestToken:
    """JWT 签发与校验。"""

    async def test_token_decode_returns_payload(self, jwt_issuer):
        """签发后解码 payload 一致。"""
        token, expires_in = jwt_issuer.issue(user_id=42, username="alice", role_codes=["regular_user"])
        payload = jwt_issuer.verify(token)
        assert payload.sub == 42
        assert payload.username == "alice"
        assert payload.role_codes == ["regular_user"]
        assert expires_in > 0

    async def test_token_expired_raises(self, jwt_issuer):
        """过期抛 InvalidAccessTokenError。"""
        from app.infrastructure.jwt import InvalidAccessTokenError
        # 制造一个立刻过期的 token
        jwt_issuer._expire_minutes = 0       # 调整 TTL
        token, _ = jwt_issuer.issue(user_id=1, username="alice", role_codes=[])
        with pytest.raises(InvalidAccessTokenError):
            jwt_issuer.verify(token)


# tests/test_auth_permission.py
@pytest.mark.asyncio
class TestPermission:
    """RBAC 权限拦截。"""

    async def test_admin_can_access_user_endpoint(self, async_client, admin_token):
        """admin 调用 GET /api/v1/users 返回 200。"""
        resp = await async_client.get(
            "/api/v1/org/users",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200

    async def test_regular_user_cannot_access_user_endpoint(self, async_client, regular_user_token):
        """regular_user 调用 GET /api/v1/users 返回 403 permission_denied。"""
        resp = await async_client.get(
            "/api/v1/org/users",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission_denied"

    async def test_bitmap_miss_recomputes_permissions(self, async_client, admin_token, redis_client):
        """Redis 位图被 DEL 后下次请求自动重算。"""
        # 1. 首次调用（写入位图）
        resp1 = await async_client.get(
            "/api/v1/org/users",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp1.status_code == 200

        # 2. DEL 位图模拟失效
        await redis_client.delete(f"auth:bitmap:1")

        # 3. 再次调用：应自动重算并返回 200
        resp2 = await async_client.get(
            "/api/v1/org/users",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp2.status_code == 200

    async def test_logout_clears_redis_bitmap(self, async_client, admin_token, redis_client):
        """登出后 Redis 位图被清除。"""
        # 登录 → 位图写入
        await async_client.get(
            "/api/v1/org/users",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert await redis_client.exists("auth:bitmap:1") is True

        # 登出
        resp = await async_client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 204
        assert await redis_client.exists("auth:bitmap:1") is False
```

### 4.1 conftest.py（关键 fixture）

```python
# tests/conftest.py
"""全局 fixture：admin / disabled / regular_user / tokens / redis / db。"""
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from app.main_module import app
from app.config.settings import settings
from app.infrastructure.database import Base
from app.infrastructure.password_hasher import PasswordHasher


@pytest_asyncio.fixture
async def async_engine():
    """每个测试用内存 SQLite 或事务回滚的 MySQL。"""
    engine = create_async_engine(settings.database_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def async_client(async_engine):
    async with AsyncClient(app=app, base_url="http://test") as client:
        async with async_engine.begin() as conn:
            # 注入 session 依赖
            pass
        yield client


@pytest_asyncio.fixture
async def seeded_admin(async_engine):
    """创建 admin 用户 + system_admin 角色 + 17 权限码。"""
    hasher = PasswordHasher(cost=4)       # 测试用低 cost 加速
    async with AsyncSession(async_engine) as session:
        # INSERT roles + permissions + users ... 详见 seed.py
        ...
        await session.commit()
    yield {"username": "admin", "password_hash": hasher.hash("Admin@123")}


@pytest.fixture
def admin_token():
    """直接签发 admin token，绕过 /login。"""
    from app.infrastructure.jwt import JWTIssuer
    issuer = JWTIssuer(secret=settings.jwt_secret, expire_minutes=480)
    token, _ = issuer.issue(user_id=1, username="admin", role_codes=["system_admin"])
    return token


@pytest.fixture
def regular_user_token():
    from app.infrastructure.jwt import JWTIssuer
    issuer = JWTIssuer(secret=settings.jwt_secret, expire_minutes=480)
    token, _ = issuer.issue(user_id=3, username="alice", role_codes=["regular_user"])
    return token
```

---

## 5. 验收 Checklist

- [ ] 6 个登录用例全通过（含 username/password 校验）
- [ ] 4 个 me 用例全通过（含过期/格式错）
- [ ] 2 个 JWT 签发/校验用例通过
- [ ] 4 个 RBAC 权限拦截用例通过（含位图失效）
- [ ] bcrypt cost=12 验证（生产）/ 测试环境允许 cost=4
- [ ] 错误码与 Spec §7.1 一致
- [ ] pytest 覆盖率 ≥ 90%（`uv run pytest --cov=app/services/auth_service --cov-report=term-missing`）

---

## 6. 已知风险与扩展

| 风险 | 缓解 |
| --- | --- |
| bcrypt 200ms 阻塞 | 用 `asyncio.to_thread` 包 bcrypt 调用；或切 argon2 |
| Redis 位图不一致 | 权限变更时主动 DEL（M2 RoleService.assign_permissions） |
| JWT 无法主动失效 | 演示期不维护黑名单；登出仅清位图 |
| 高并发下 token 签发耗时 | HS256 本身够快；如压力测试出现瓶颈可换 EdDSA |
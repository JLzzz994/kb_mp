"""AuthService：登录 / 当前用户 / 登出的业务编排。"""

from __future__ import annotations

from loguru import logger

from app.api.schemas.auth_response import (
    CurrentUserInfo,
    LoginResponse,
    MeResponse,
)
from app.common.errors import (
    AuthenticationError,
    InvalidCredentialsError,
    UserDisabledError,
)
from app.config.settings import settings
from app.domain.user import CurrentUser
from app.infrastructure.jwt import JWTIssuer
from app.infrastructure.password_hasher import PasswordHasher
from app.infrastructure.redis_client import RedisClient, get_redis
from app.repositories.auth_repository import AuthRepository


class AuthService:
    def __init__(
        self,
        auth_repo: AuthRepository,
        password_hasher: PasswordHasher,
        jwt_issuer: JWTIssuer,
        redis: RedisClient,
    ) -> None:
        self._repo = auth_repo
        self._password_hasher = password_hasher
        self._jwt = jwt_issuer
        self._redis = redis

    async def login(self, username: str, password: str) -> LoginResponse:
        """登录：查用户 → 校验状态 → 校验密码 → 加载角色/权限 → 签发 JWT → 写位图 → 返回。"""
        user = await self._repo.find_by_username(username)
        if user is None:
            logger.warning("auth.login.fail username={} reason=user_not_found", username)
            raise InvalidCredentialsError()

        if user.status != 1:
            logger.warning("auth.login.fail user_id={} reason=user_disabled", user.id)
            raise UserDisabledError()

        if not self._password_hasher.verify(password, user.password_hash):
            logger.warning("auth.login.fail user_id={} reason=wrong_password", user.id)
            raise InvalidCredentialsError()

        role_codes = await self._repo.list_role_codes(user.id)
        permissions = await self._repo.list_permissions(role_codes)
        dept = await self._repo.find_department(user.department_id)

        access_token, expires_in = self._jwt.issue(
            user_id=user.id,
            username=user.username,
            role_codes=role_codes,
        )

        await self._redis.set_bitmap(
            user_id=user.id,
            permissions=permissions,
            ttl=settings.auth_bitmap_ttl_seconds,
        )

        logger.info("auth.login.success user_id={} username={}", user.id, username)

        return LoginResponse(
            access_token=access_token,
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
        """从 user_id 加载完整 CurrentUser（含 dept_ids / role_ids / department_name）。"""
        current = await self._repo.load_current_user(user_id)
        if current is None:
            raise AuthenticationError("user_not_loadable")
        return current

    async def me(self, user: CurrentUser) -> MeResponse:
        """返回当前用户信息 + 权限（位图优先，缺失则重算并写回）。"""
        cached = await self._redis.get_bitmap(user.id)
        if cached is None:
            cached = await self._repo.list_permissions(user.role_codes)
            await self._redis.set_bitmap(
                user_id=user.id,
                permissions=cached,
                ttl=settings.auth_bitmap_ttl_seconds,
            )

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
        """登出：DEL Redis 鉴权位图（Token 因无状态不强制失效）。"""
        await self._redis.del_bitmap(user_id)
        logger.info("auth.logout user_id={}", user_id)


# ── 工厂 + FastAPI 依赖 ─────────────────────────────


def build_auth_service(
    session,
    password_hasher: PasswordHasher | None = None,
    jwt_issuer: JWTIssuer | None = None,
    redis: RedisClient | None = None,
) -> AuthService:
    """DI 工厂：构造 AuthService（可被 Depends 复用）。"""
    from app.infrastructure.jwt import get_jwt_issuer
    from app.infrastructure.password_hasher import get_password_hasher

    return AuthService(
        auth_repo=AuthRepository(session),
        password_hasher=password_hasher or get_password_hasher(),
        jwt_issuer=jwt_issuer or get_jwt_issuer(),
        redis=redis or get_redis(),
    )

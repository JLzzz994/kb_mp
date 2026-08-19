"""RoleService：角色列表 + 权限分配 + 位图批量失效。"""

from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.role_schema import RoleResponse
from app.common.errors import InvalidPermissionCodeError, RoleNotFoundError
from app.domain.permission import ALL_PERMISSION_CODES
from app.infrastructure.redis_client import RedisClient
from app.repositories.role_repository import RoleRepository


class RoleService:
    def __init__(self, repo: RoleRepository, session: AsyncSession, redis: RedisClient) -> None:
        self._repo = repo
        self._session = session
        self._redis = redis

    async def list(self) -> list[RoleResponse]:
        """返回所有角色 + 各自权限码列表。"""
        pairs = await self._repo.list_all_with_permissions()
        return [
            RoleResponse(
                id=r.id,
                role_name=r.role_name,
                role_code=r.role_code,
                description=r.description,
                permissions=perms,
            )
            for r, perms in pairs
        ]

    async def list_all_permission_codes(self) -> list[str]:
        """返回 17 码白名单（前端用于角色分配 UI）。"""
        return list(ALL_PERMISSION_CODES)

    async def assign_permissions(self, role_id: int, codes: list[str]) -> None:
        """替换 role 的全部权限码 + 批量失效持有此 role 用户的 Redis 位图。

        步骤：
        1. 校验 role 存在
        2. 校验 codes ⊆ ALL_PERMISSION_CODES
        3. 替换 role_permissions
        4. 查持有此 role 的 user_ids
        5. DEL auth:bitmap:{user_id}（受影响的用户在下次请求会重算）
        """
        # 1. role 存在
        role = await self._repo.find_by_id(role_id)
        if role is None:
            raise RoleNotFoundError(f"id={role_id}")

        # 2. codes 白名单校验
        invalid = set(codes) - set(ALL_PERMISSION_CODES)
        if invalid:
            raise InvalidPermissionCodeError(f"invalid codes: {sorted(invalid)}")

        # 3. 替换
        await self._repo.replace_role_permissions(role_id, codes)
        await self._session.commit()

        # 4-5. 批量失效位图
        affected_user_ids = await self._repo.list_users_with_role(role_id)
        for uid in affected_user_ids:
            await self._redis.del_bitmap(uid)

        logger.warning(
            "role.permissions_change role_id={} codes={} affected_users={}",
            role_id,
            sorted(codes),
            len(affected_user_ids),
        )


def build_role_service(session: AsyncSession, redis: RedisClient) -> RoleService:
    return RoleService(RoleRepository(session), session, redis)

"""KnowledgePermissionService：四维权限 OR 合并 + check-permissions 共享接口。"""

from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.knowledge_schema import CheckPermissionsResponse
from app.domain.unit_permission import PermissionTarget
from app.infrastructure.redis_client import RedisClient
from app.repositories.auth_repository import AuthRepository
from app.repositories.knowledge_unit_repository import UnitPermissionRepository


class KnowledgePermissionService:
    """知识数据权限核心：四维 OR 合并 → 单位用户的可访问 unit_id 集合。"""

    def __init__(self, session: AsyncSession, redis: RedisClient) -> None:
        self._session = session
        self._redis = redis
        self._auth_repo = AuthRepository(session)
        self._perm_repo = UnitPermissionRepository(session)

    async def check_permissions(
        self, user_id: int, unit_ids: list[int]
    ) -> CheckPermissionsResponse:
        """每次实时重算（不污染 M1 的 RBAC auth:bitmap）。

        M3-C 决策：
        - auth:bitmap:{user_id} 保留 M1 语义（17 个权限码）
        - 单位级访问表每次从 DB 重算（演示期数据量小，无需 Redis 缓存）
        - 后续如需缓存，新增 key auth:data_bitmap:{user_id} 不污染 RBAC
        """

        current = await self._auth_repo.load_current_user(user_id)
        if current is None:
            return CheckPermissionsResponse(authorized_unit_ids=[], unauthorized_unit_ids=unit_ids)

        # 单次拉取所有 unit_permissions（演示期数据量 <10K）
        perms = await self._perm_repo.list_all()
        authorized_set = compute_user_permission_bitmap_sync(current, perms)

        authorized = [uid for uid in unit_ids if uid in authorized_set]
        unauthorized = [uid for uid in unit_ids if uid not in authorized_set]
        return CheckPermissionsResponse(
            authorized_unit_ids=authorized, unauthorized_unit_ids=unauthorized
        )

    async def _load_and_cache(self, user_id: int) -> list[int]:
        """保留兼容：未来加 auth:data_bitmap:* 时使用。"""

        current = await self._auth_repo.load_current_user(user_id)
        if current is None:
            return []

        perms = await self._perm_repo.list_all()
        authorized = compute_user_permission_bitmap_sync(current, perms)
        result = sorted(authorized)

        logger.info(
            "knowledge.permission.bitmap.recompute user_id={} unit_count={}",
            user_id,
            len(result),
        )
        return result

    async def invalidate_user_bitmap(self, user_id: int) -> None:
        """权限配置变更 / 单元删除时调用：清 Redis 鉴权位图。"""
        await self._redis.del_bitmap(user_id)


def compute_user_permission_bitmap_sync(
    current_user,  # CurrentUser（避免循环依赖）
    unit_permissions: list,
) -> set[int]:
    """纯函数：内存集合运算（无 IO），供 LangGraph permission_filter 节点调用。

    OR 逻辑：任一维度匹配即放行
    - global：所有人均可（target_id IS NULL）
    - department：target_id ∈ user.dept_ids
    - role：target_id ∈ user.role_ids
    - user：target_id == user.id
    """
    if not unit_permissions:
        return set()

    global_units = {
        up.unit_id for up in unit_permissions if up.target_type == PermissionTarget.GLOBAL.value
    }
    dept_units = {
        up.unit_id
        for up in unit_permissions
        if up.target_type == PermissionTarget.DEPARTMENT.value
        and up.target_id in current_user.dept_ids
    }
    role_units = {
        up.unit_id
        for up in unit_permissions
        if up.target_type == PermissionTarget.ROLE.value and up.target_id in current_user.role_ids
    }
    user_units = {
        up.unit_id
        for up in unit_permissions
        if up.target_type == PermissionTarget.USER.value and up.target_id == current_user.id
    }
    return global_units | dept_units | role_units | user_units


def build_knowledge_permission_service(
    session: AsyncSession, redis: RedisClient
) -> KnowledgePermissionService:
    return KnowledgePermissionService(session, redis)

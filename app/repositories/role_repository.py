"""RoleRepository：roles + role_permissions CRUD。"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.permission import ALL_PERMISSION_CODES
from app.infrastructure.database import RolePermissionRecord, RoleRecord, UserRoleRecord


class RoleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all_with_permissions(self) -> list[tuple[RoleRecord, list[str]]]:
        """一次拉所有角色 + 权限码（聚合）。"""
        roles = (
            (await self._session.execute(select(RoleRecord).order_by(RoleRecord.id)))
            .scalars()
            .all()
        )
        if not roles:
            return []
        # 一次查所有 role_id 的权限码
        stmt = select(RolePermissionRecord.role_id, RolePermissionRecord.permission_code).where(
            RolePermissionRecord.role_id.in_([r.id for r in roles])
        )
        rows = (await self._session.execute(stmt)).all()
        # 按 role_id 分组
        perms_map: dict[int, list[str]] = {r.id: [] for r in roles}
        for role_id, code in rows:
            perms_map[role_id].append(code)
        return [(r, sorted(perms_map[r.id])) for r in roles]

    async def find_by_id(self, role_id: int) -> RoleRecord | None:
        stmt = select(RoleRecord).where(RoleRecord.id == role_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def batch_find_by_ids(self, role_ids: list[int]) -> list[RoleRecord]:
        if not role_ids:
            return []
        stmt = select(RoleRecord).where(RoleRecord.id.in_(role_ids))
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_users_with_role(self, role_id: int) -> list[int]:
        """持有此 role 的所有 user_id（用于位图批量失效）。"""
        stmt = select(UserRoleRecord.user_id).where(UserRoleRecord.role_id == role_id)
        return [int(x) for x in (await self._session.execute(stmt)).scalars().all()]

    async def replace_role_permissions(self, role_id: int, codes: list[str]) -> None:
        """替换 role 的全部权限码（事务保证）。"""
        await self._session.execute(
            delete(RolePermissionRecord).where(RolePermissionRecord.role_id == role_id)
        )
        for code in codes:
            self._session.add(
                RolePermissionRecord(
                    role_id=role_id,
                    permission_code=code,
                    permission_type="api",
                )
            )
        await self._session.flush()

    async def list_all_permission_codes(self) -> list[str]:
        """返回 17 码白名单常量。"""
        return list(ALL_PERMISSION_CODES)

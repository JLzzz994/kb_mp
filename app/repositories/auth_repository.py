"""AuthRepository：users / user_roles / role_permissions 查询。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import UserNotFoundError
from app.domain.user import CurrentUser, UserWithPassword
from app.infrastructure.database import (
    DepartmentRecord,
    RolePermissionRecord,
    RoleRecord,
    UserRecord,
    UserRoleRecord,
)


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_username(self, username: str) -> UserWithPassword | None:
        """根据 username 查用户（含密码哈希）。不存在返回 None。"""
        stmt = select(UserRecord).where(UserRecord.username == username)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return UserWithPassword(
            id=row.id,
            username=row.username,
            display_name=row.display_name,
            department_id=row.department_id,
            status=row.status,
            password_hash=row.password_hash,
        )

    async def list_role_codes(self, user_id: int) -> list[str]:
        """查用户的所有角色 code。"""
        stmt = (
            select(RoleRecord.role_code)
            .join(UserRoleRecord, UserRoleRecord.role_id == RoleRecord.id)
            .where(UserRoleRecord.user_id == user_id)
        )
        return [str(x) for x in (await self._session.execute(stmt)).scalars().all()]

    async def list_role_ids(self, user_id: int) -> list[int]:
        """查用户的所有角色 id。"""
        stmt = select(UserRoleRecord.role_id).where(UserRoleRecord.user_id == user_id)
        return [int(x) for x in (await self._session.execute(stmt)).scalars().all()]

    async def list_dept_ids_with_ancestors(self, dept_id: int) -> list[int]:
        """查部门链（自身 + 父级递归）。演示期部门层级 ≤3 层，循环即可。"""
        ids: list[int] = []
        current_id: int | None = dept_id
        while current_id is not None:
            ids.append(current_id)
            stmt = select(DepartmentRecord.parent_id).where(DepartmentRecord.id == current_id)
            current_id = (await self._session.execute(stmt)).scalar_one_or_none()
        return ids

    async def list_permissions(self, role_codes: list[str]) -> list[str]:
        """查多个角色的权限码并集（去重）。"""
        if not role_codes:
            return []
        stmt = (
            select(RolePermissionRecord.permission_code)
            .join(RoleRecord, RoleRecord.id == RolePermissionRecord.role_id)
            .where(RoleRecord.role_code.in_(role_codes))
        )
        # 去重 + 保留稳定顺序
        return sorted({str(x) for x in (await self._session.execute(stmt)).scalars().all()})

    async def find_department(self, dept_id: int) -> DepartmentRecord | None:
        stmt = select(DepartmentRecord).where(DepartmentRecord.id == dept_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def load_current_user(self, user_id: int) -> CurrentUser | None:
        """组装 CurrentUser（含部门名 + 角色码 + 部门链 + 角色 id）。"""
        user_row = (
            await self._session.execute(select(UserRecord).where(UserRecord.id == user_id))
        ).scalar_one_or_none()
        if user_row is None or user_row.status != 1:
            return None

        dept = await self.find_department(user_row.department_id)
        if dept is None:
            return None

        role_codes = await self.list_role_codes(user_id)
        await self.list_role_ids(user_id)
        dept_ids = await self.list_dept_ids_with_ancestors(user_row.department_id)

        return CurrentUser(
            id=user_row.id,
            username=user_row.username,
            display_name=user_row.display_name,
            department_id=user_row.department_id,
            role_codes=role_codes,
            dept_ids=dept_ids,
        )

    async def update_password(self, user_id: int, password_hash: str) -> None:
        """更新密码哈希（admin 重置密码时调用）。"""
        row = (
            await self._session.execute(select(UserRecord).where(UserRecord.id == user_id))
        ).scalar_one_or_none()
        if row is None:
            raise UserNotFoundError(f"id={user_id}")
        row.password_hash = password_hash
        await self._session.flush()

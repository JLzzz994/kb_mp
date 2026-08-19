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
        """查部门链（自身 + 父级递归）。演示期部门层级 ≤3 层循环即可；
        如未来层级 ≥5 层，改用递归 CTE（WITH RECURSIVE）。"""
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
        """组装 CurrentUser（1 次 JOIN + 1 次部门链递归；原 4 次往返 → 2 次）。"""
        # Query A: 单次 JOIN 同时拉 user + dept_name + role_codes + role_ids
        stmt = (
            select(
                UserRecord,
                DepartmentRecord.name.label("dept_name"),
                RoleRecord.role_code,
                RoleRecord.id.label("role_id"),
            )
            .outerjoin(DepartmentRecord, DepartmentRecord.id == UserRecord.department_id)
            .outerjoin(UserRoleRecord, UserRoleRecord.user_id == UserRecord.id)
            .outerjoin(RoleRecord, RoleRecord.id == UserRoleRecord.role_id)
            .where(UserRecord.id == user_id)
        )
        rows = (await self._session.execute(stmt)).all()

        # 第 1 行带 user 行；其余 2-3 列可能为 None（用户无部门 / 无角色）
        user_row = next((r[0] for r in rows if r[0] is not None), None)
        if user_row is None or user_row.status != 1:
            return None

        dept_name = next((r[1] for r in rows if r[1] is not None), "")

        # 去重（多角色场景下 JOIN 笛卡尔积会被去重）
        role_codes = sorted({r[2] for r in rows if r[2] is not None})
        _ = [r[3] for r in rows if r[3] is not None]  # role_ids 当前未用，预留未来

        # Query B: 部门链递归（演示期 ≤3 层循环；未来改 CTE）
        dept_ids = await self.list_dept_ids_with_ancestors(user_row.department_id)

        return CurrentUser(
            id=user_row.id,
            username=user_row.username,
            display_name=user_row.display_name,
            department_id=user_row.department_id,
            department_name=dept_name,
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

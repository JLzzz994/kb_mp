"""UserRepository：users + user_roles CRUD。"""

from __future__ import annotations

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import (
    DepartmentRecord,
    RoleRecord,
    UserRecord,
    UserRoleRecord,
)


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_paginated(
        self,
        *,
        page: int,
        page_size: int,
        department_id: int | None,
        status: int | None,
        keyword: str | None,
    ) -> tuple[list[tuple[UserRecord, str, list[str]]], int]:
        """分页查询（含部门名 + 角色码）。"""
        stmt = select(UserRecord, DepartmentRecord.name).join(
            DepartmentRecord, DepartmentRecord.id == UserRecord.department_id
        )
        if department_id is not None:
            stmt = stmt.where(UserRecord.department_id == department_id)
        if status is not None:
            stmt = stmt.where(UserRecord.status == status)
        if keyword:
            stmt = stmt.where(
                or_(
                    UserRecord.username.like(f"%{keyword}%"),
                    UserRecord.display_name.like(f"%{keyword}%"),
                )
            )

        # 总数
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = int((await self._session.execute(count_stmt)).scalar_one())

        # 分页
        stmt = stmt.order_by(UserRecord.id).offset((page - 1) * page_size).limit(page_size)
        rows = (await self._session.execute(stmt)).all()

        # 批量查 role_codes
        user_ids = [row[0].id for row in rows]
        role_map = await self._batch_role_codes(user_ids)
        return [(row[0], row[1], role_map.get(row[0].id, [])) for row in rows], total

    async def _batch_role_codes(self, user_ids: list[int]) -> dict[int, list[str]]:
        if not user_ids:
            return {}
        stmt = (
            select(UserRoleRecord.user_id, RoleRecord.role_code)
            .join(RoleRecord, RoleRecord.id == UserRoleRecord.role_id)
            .where(UserRoleRecord.user_id.in_(user_ids))
        )
        result: dict[int, list[str]] = {uid: [] for uid in user_ids}
        for uid, code in (await self._session.execute(stmt)).all():
            result[int(uid)].append(str(code))
        return result

    async def find_by_id(self, user_id: int) -> UserRecord | None:
        stmt = select(UserRecord).where(UserRecord.id == user_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def find_by_username(self, username: str) -> UserRecord | None:
        stmt = select(UserRecord).where(UserRecord.username == username)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create(
        self, *, username: str, password_hash: str, display_name: str, department_id: int
    ) -> UserRecord:
        record = UserRecord(
            username=username,
            password_hash=password_hash,
            display_name=display_name,
            department_id=department_id,
            status=1,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def insert_user_roles(self, user_id: int, role_ids: list[int]) -> None:
        for role_id in role_ids:
            self._session.add(UserRoleRecord(user_id=user_id, role_id=role_id))
        await self._session.flush()

    async def replace_user_roles(self, user_id: int, role_ids: list[int]) -> None:
        """全量替换用户的角色（事务）。"""
        await self._session.execute(delete(UserRoleRecord).where(UserRoleRecord.user_id == user_id))
        for role_id in role_ids:
            self._session.add(UserRoleRecord(user_id=user_id, role_id=role_id))
        await self._session.flush()

    async def update(
        self,
        user_id: int,
        *,
        display_name: str | None,
        department_id: int | None,
        status: int | None,
    ) -> UserRecord | None:
        record = await self.find_by_id(user_id)
        if record is None:
            return None
        if display_name is not None:
            record.display_name = display_name
        if department_id is not None:
            record.department_id = department_id
        if status is not None:
            record.status = status
        await self._session.flush()
        return record

    async def set_status(self, user_id: int, status: int) -> UserRecord | None:
        record = await self.find_by_id(user_id)
        if record is None:
            return None
        record.status = status
        await self._session.flush()
        return record

    async def update_password(self, user_id: int, password_hash: str) -> UserRecord | None:
        record = await self.find_by_id(user_id)
        if record is None:
            return None
        record.password_hash = password_hash
        await self._session.flush()
        return record

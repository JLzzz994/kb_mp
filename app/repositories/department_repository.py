"""DepartmentRepository：departments 表 CRUD + 成员计数。"""

from __future__ import annotations

from sqlalchemy import delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import DepartmentRecord, UserRecord


class DepartmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[DepartmentRecord]:
        """拉全部部门（按 sort_order, id 升序）。"""
        stmt = select(DepartmentRecord).order_by(DepartmentRecord.sort_order, DepartmentRecord.id)
        return list((await self._session.execute(stmt)).scalars().all())

    async def find_by_id(self, dept_id: int) -> DepartmentRecord | None:
        stmt = select(DepartmentRecord).where(DepartmentRecord.id == dept_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create(
        self,
        *,
        name: str,
        parent_id: int | None,
        leader_id: int | None,
        sort_order: int,
    ) -> DepartmentRecord:
        row = DepartmentRecord(
            name=name,
            parent_id=parent_id,
            leader_id=leader_id,
            sort_order=sort_order,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def update(
        self,
        dept_id: int,
        *,
        name: str,
        parent_id: int | None,
        leader_id: int | None,
        sort_order: int,
    ) -> DepartmentRecord | None:
        row = await self.find_by_id(dept_id)
        if row is None:
            return None
        row.name = name
        row.parent_id = parent_id
        row.leader_id = leader_id
        row.sort_order = sort_order
        await self._session.flush()
        return row

    async def delete(self, dept_id: int) -> bool:
        """物理删除。返回是否真删了一行。"""
        stmt = delete(DepartmentRecord).where(DepartmentRecord.id == dept_id)
        result = await self._session.execute(stmt)
        return (result.rowcount or 0) > 0

    async def has_children(self, dept_id: int) -> bool:
        """是否存在直接子部门。"""
        stmt = select(exists().where(DepartmentRecord.parent_id == dept_id))
        return bool((await self._session.execute(stmt)).scalar())

    async def has_members(self, dept_id: int) -> bool:
        """是否存在属于该部门的用户。"""
        stmt = select(exists().where(UserRecord.department_id == dept_id))
        return bool((await self._session.execute(stmt)).scalar())

    async def count_members_by_dept(self) -> dict[int, int]:
        """一次聚合 COUNT(users) 按 department_id 分组 → {dept_id: count}。"""
        stmt = select(UserRecord.department_id, func.count()).group_by(UserRecord.department_id)
        return {
            int(dept_id): int(cnt) for dept_id, cnt in (await self._session.execute(stmt)).all()
        }


__all__ = ["DepartmentRepository"]

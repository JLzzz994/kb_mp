"""KnowledgeUnitRepository：知识单元 CRUD + 权限 JOIN 查询。"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import (
    DepartmentRecord,
    KnowledgeUnitRecord,
    UnitPermissionRecord,
    UserRecord,
)


class KnowledgeUnitRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_content_hash(self, content_hash: str) -> KnowledgeUnitRecord | None:
        stmt = select(KnowledgeUnitRecord).where(KnowledgeUnitRecord.content_hash == content_hash)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def find_by_id(self, unit_id: int) -> KnowledgeUnitRecord | None:
        stmt = select(KnowledgeUnitRecord).where(KnowledgeUnitRecord.id == unit_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_paginated(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str | None,
        category: str | None,
        status: str | None,
    ) -> tuple[list[tuple[KnowledgeUnitRecord, str, int]], int]:
        """分页 + 含 creator_name + permissions_count。"""
        stmt = (
            select(
                KnowledgeUnitRecord,
                UserRecord.display_name,
                func.count(UnitPermissionRecord.id),
            )
            .outerjoin(UserRecord, UserRecord.id == KnowledgeUnitRecord.creator_id)
            .outerjoin(UnitPermissionRecord, UnitPermissionRecord.unit_id == KnowledgeUnitRecord.id)
        )
        if keyword:
            stmt = stmt.where(
                or_(
                    KnowledgeUnitRecord.title.like(f"%{keyword}%"),
                    KnowledgeUnitRecord.unit_code.like(f"%{keyword}%"),
                    KnowledgeUnitRecord.content.like(f"%{keyword}%"),
                )
            )
        if category:
            stmt = stmt.where(KnowledgeUnitRecord.category == category)
        if status:
            stmt = stmt.where(KnowledgeUnitRecord.status == status)

        # 总数
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = int((await self._session.execute(count_stmt)).scalar_one())

        # 分页
        stmt = (
            stmt.group_by(KnowledgeUnitRecord.id, UserRecord.display_name)
            .order_by(KnowledgeUnitRecord.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self._session.execute(stmt)).all()
        return [(row[0], row[1] or "", int(row[2])) for row in rows], total

    async def list_by_ids(self, ids: list[int]) -> list[KnowledgeUnitRecord]:
        if not ids:
            return []
        stmt = select(KnowledgeUnitRecord).where(KnowledgeUnitRecord.id.in_(ids))
        return list((await self._session.execute(stmt)).scalars().all())

    async def get_with_creator(self, unit_id: int) -> tuple[KnowledgeUnitRecord, str, str] | None:
        """unit + creator_name + department_name。"""
        stmt = (
            select(
                KnowledgeUnitRecord,
                UserRecord.display_name,
                DepartmentRecord.name,
            )
            .outerjoin(UserRecord, UserRecord.id == KnowledgeUnitRecord.creator_id)
            .outerjoin(DepartmentRecord, DepartmentRecord.id == UserRecord.department_id)
            .where(KnowledgeUnitRecord.id == unit_id)
        )
        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None
        return (row[0], row[1] or "", row[2] or "")

    async def create(self, record: KnowledgeUnitRecord) -> KnowledgeUnitRecord:
        self._session.add(record)
        await self._session.flush()
        return record

    async def update(
        self,
        unit_id: int,
        *,
        title: str | None = None,
        content: str | None = None,
        summary: str | None = None,
        category: str | None = None,
        content_hash: str | None = None,
    ) -> KnowledgeUnitRecord | None:
        record = await self.find_by_id(unit_id)
        if record is None:
            return None
        if title is not None:
            record.title = title
        if content is not None:
            record.content = content
        if summary is not None:
            record.summary = summary
        if category is not None:
            record.category = category
        if content_hash is not None:
            record.content_hash = content_hash
        await self._session.flush()
        return record

    async def delete_by_ids(self, ids: list[int]) -> int:
        if not ids:
            return 0
        from sqlalchemy import delete

        stmt = delete(KnowledgeUnitRecord).where(KnowledgeUnitRecord.id.in_(ids))
        result = await self._session.execute(stmt)
        return int(result.rowcount or 0)


class UnitPermissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_unit(self, unit_id: int) -> list[UnitPermissionRecord]:
        stmt = select(UnitPermissionRecord).where(UnitPermissionRecord.unit_id == unit_id)
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_for_units(self, unit_ids: list[int]) -> list[UnitPermissionRecord]:
        if not unit_ids:
            return []
        stmt = select(UnitPermissionRecord).where(UnitPermissionRecord.unit_id.in_(unit_ids))
        return list((await self._session.execute(stmt)).scalars().all())

    async def replace_all(self, unit_id: int, entries: list[tuple[str, int | None]]) -> None:
        """全量替换 unit 的权限配置。"""
        from sqlalchemy import delete

        await self._session.execute(
            delete(UnitPermissionRecord).where(UnitPermissionRecord.unit_id == unit_id)
        )
        for target_type, target_id in entries:
            self._session.add(
                UnitPermissionRecord(unit_id=unit_id, target_type=target_type, target_id=target_id)
            )
        await self._session.flush()

    async def list_all(self) -> list[UnitPermissionRecord]:
        """全表扫描（供 KnowledgePermissionService 鉴权位图用）。"""
        stmt = select(UnitPermissionRecord)
        return list((await self._session.execute(stmt)).scalars().all())

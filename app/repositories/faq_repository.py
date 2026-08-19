"""FAQ Repository：人工 CRUD + 审核。"""

from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import FaqRecord, KnowledgeUnitRecord


class FaqRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def compute_question_hash(question: str) -> str:
        return hashlib.sha1(question.lower().strip().encode("utf-8")).hexdigest()

    async def find_by_id(self, faq_id: int) -> FaqRecord | None:
        return (
            await self._session.execute(select(FaqRecord).where(FaqRecord.id == faq_id))
        ).scalar_one_or_none()

    async def find_by_question_hash(self, qhash: str) -> FaqRecord | None:
        return (
            await self._session.execute(select(FaqRecord).where(FaqRecord.question_hash == qhash))
        ).scalar_one_or_none()

    async def list_paginated(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
        source_type: str | None = None,
    ) -> tuple[list[FaqRecord], int]:
        stmt = select(FaqRecord)
        if status:
            stmt = stmt.where(FaqRecord.status == status)
        if source_type:
            stmt = stmt.where(FaqRecord.source_type == source_type)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = int((await self._session.execute(count_stmt)).scalar_one())

        stmt = stmt.order_by(FaqRecord.id.desc()).offset((page - 1) * page_size).limit(page_size)
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows), total

    async def list_recommendations(self, *, page: int, page_size: int) -> list[FaqRecord]:
        """仅返回 status=pending_review（审核页）。"""
        stmt = (
            select(FaqRecord)
            .where(FaqRecord.status == "pending_review")
            .order_by(FaqRecord.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def get_unit_updated_at(self, unit_id: int) -> datetime | None:
        """用于 FAQ 缓存版本校验。"""
        return (
            await self._session.execute(
                select(KnowledgeUnitRecord.updated_at).where(KnowledgeUnitRecord.id == unit_id)
            )
        ).scalar_one_or_none()

    async def create(
        self,
        *,
        question: str,
        answer: str,
        category: str | None,
        related_unit_id: int | None,
        source_type: str,
        status: str,
    ) -> FaqRecord:
        record = FaqRecord(
            question=question,
            question_hash=self.compute_question_hash(question),
            answer=answer,
            category=category,
            related_unit_id=related_unit_id,
            unit_updated_at_snapshot=None,
            source_type=source_type,
            status=status,
            hit_count=0,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def update_for_approve(
        self,
        faq_id: int,
        *,
        edited_answer: str | None,
        reviewer_id: int,
        unit_updated_at: datetime | None,
    ) -> FaqRecord | None:
        record = await self.find_by_id(faq_id)
        if record is None:
            return None
        if edited_answer:
            record.answer = edited_answer
        record.status = "published"
        record.reviewer_id = reviewer_id
        record.reviewed_at = datetime.utcnow()
        record.unit_updated_at_snapshot = unit_updated_at
        await self._session.flush()
        return record

    async def update_for_reject(self, faq_id: int, reviewer_id: int) -> FaqRecord | None:
        record = await self.find_by_id(faq_id)
        if record is None:
            return None
        record.status = "rejected"
        record.reviewer_id = reviewer_id
        record.reviewed_at = datetime.utcnow()
        await self._session.flush()
        return record

    async def delete(self, faq_id: int) -> bool:
        result = await self._session.execute(delete(FaqRecord).where(FaqRecord.id == faq_id))
        return (result.rowcount or 0) > 0

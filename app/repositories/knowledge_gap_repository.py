"""KnowledgeGapRepository：缺口聚合 CRUD。"""

from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import KnowledgeGapRecord


class KnowledgeGapRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def compute_pattern_hash(question: str) -> str:
        return hashlib.sha1(question.lower().strip()[:255].encode("utf-8")).hexdigest()

    async def find_by_pattern_hash(self, pattern_hash: str) -> KnowledgeGapRecord | None:
        return (
            await self._session.execute(
                select(KnowledgeGapRecord).where(
                    KnowledgeGapRecord.question_pattern_hash == pattern_hash
                )
            )
        ).scalar_one_or_none()

    async def find_by_id(self, gap_id: int) -> KnowledgeGapRecord | None:
        return (
            await self._session.execute(
                select(KnowledgeGapRecord).where(KnowledgeGapRecord.id == gap_id)
            )
        ).scalar_one_or_none()

    async def list_paginated(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
    ) -> tuple[list[KnowledgeGapRecord], int]:
        stmt = select(KnowledgeGapRecord)
        if status:
            stmt = stmt.where(KnowledgeGapRecord.status == status)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = int((await self._session.execute(count_stmt)).scalar_one())

        stmt = (
            stmt.order_by(KnowledgeGapRecord.ask_count.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows), total

    async def create_or_increment(
        self,
        *,
        pattern: str,
        pattern_hash: str,
        question: str,
    ) -> KnowledgeGapRecord:
        """UPSERT 缺口：旧记录 +1 + 追加 sample；新记录 +1 + 新样本。"""
        existing = await self.find_by_pattern_hash(pattern_hash)
        if existing is None:
            record = KnowledgeGapRecord(
                question_pattern=pattern,
                question_pattern_hash=pattern_hash,
                sample_questions_json=[question],
                ask_count=1,
                last_asked_at=datetime.utcnow(),
                status="unresolved",
            )
            self._session.add(record)
            await self._session.flush()
            return record
        # existing → +1, 追加 sample
        existing.ask_count += 1
        existing.last_asked_at = datetime.utcnow()
        samples = list(existing.sample_questions_json or [])
        samples.append(question)
        if len(samples) > 20:
            samples = samples[-20:]
        existing.sample_questions_json = samples
        await self._session.flush()
        return existing

    async def set_resolved(self, gap_id: int, unit_id: int) -> KnowledgeGapRecord | None:
        """一键建档后：标记 resolved + 回填 resolved_unit_id。"""
        record = await self.find_by_id(gap_id)
        if record is None:
            return None
        record.status = "resolved"
        record.resolved_unit_id = unit_id
        await self._session.flush()
        return record

    async def delete(self, gap_id: int) -> bool:
        result = await self._session.execute(
            delete(KnowledgeGapRecord).where(KnowledgeGapRecord.id == gap_id)
        )
        return (result.rowcount or 0) > 0

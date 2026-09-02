"""KnowledgeGapService：缺口记录 + 一键建档。"""

from __future__ import annotations

import hashlib

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.knowledge_gap_schema import (
    CreateUnitFromGapRequest,
    CreateUnitFromGapResponse,
    KnowledgeGapListResponse,
    KnowledgeGapResponse,
)
from app.common.errors import KnowledgeGapNotFoundError
from app.repositories.knowledge_gap_repository import KnowledgeGapRepository
from app.repositories.knowledge_unit_repository import (
    KnowledgeUnitRepository,
    UnitPermissionRepository,
)
from app.services.knowledge_index_service import (
    KnowledgeIndexService,
    build_knowledge_index_service,
)
from app.services.knowledge_unit_service import (
    _compute_content_hash,
    _gen_unit_code,
)


class KnowledgeGapService:
    def __init__(
        self,
        session: AsyncSession,
        index_service: KnowledgeIndexService | None = None,
    ) -> None:
        self._session = session
        self._repo = KnowledgeGapRepository(session)
        self._unit_repo = KnowledgeUnitRepository(session)
        self._perm_repo = UnitPermissionRepository(session)
        self._index_service = index_service or build_knowledge_index_service(session)

    async def record(
        self,
        *,
        question: str,
        retrieved_citations: list[dict],
    ) -> bool:
        """M4 record_log 节点调用：检索评分低于阈值 → 记录缺口。

        阈值：top1 < 0.5 且 top3_avg < 0.55。
        """
        if not retrieved_citations:
            return False

        top1 = float(retrieved_citations[0].get("score", 0.0))
        top3_avg = sum(float(c.get("score", 0.0)) for c in retrieved_citations[:3]) / min(
            3, len(retrieved_citations)
        )
        if not (top1 < 0.5 and top3_avg < 0.55):
            return False

        pattern = question.lower().strip()[:255]
        pattern_hash = hashlib.sha1(pattern.encode("utf-8")).hexdigest()

        await self._repo.create_or_increment(
            pattern=pattern,
            pattern_hash=pattern_hash,
            question=question,
        )
        await self._session.commit()
        logger.info(
            "knowledge_gap.record pattern_hash={} top1={} top3_avg={}",
            pattern_hash[:8],
            top1,
            top3_avg,
        )
        return True

    async def list(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
    ) -> KnowledgeGapListResponse:
        rows, total = await self._repo.list_paginated(page=page, page_size=page_size, status=status)
        return KnowledgeGapListResponse(
            items=[self._to_response(r) for r in rows],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def one_click_create_unit(
        self,
        gap_id: int,
        data: CreateUnitFromGapRequest,
        user_id: int,
    ) -> CreateUnitFromGapResponse:
        """一键建档：基于缺口 → 创建 knowledge_unit + 标记 resolved。"""
        gap = await self._repo.find_by_id(gap_id)
        if gap is None:
            raise KnowledgeGapNotFoundError(f"id={gap_id}")

        # 取第一个 sample 作默认 content
        samples = list(gap.sample_questions_json or [])
        if not data.content and not samples:
            raise ValueError("no content provided and sample_questions_json is empty")
        content = data.content or ("\n".join(samples) if samples else data.title)

        # 走 KnowledgeUnitRepository.create
        from app.infrastructure.database import KnowledgeUnitRecord

        content_hash = _compute_content_hash(content)
        existing_unit = await self._unit_repo.find_by_content_hash(content_hash)
        if existing_unit is not None:
            unit_id = existing_unit.id
            if existing_unit.status != "active":
                await self._index_service.rebuild_unit(unit_id, prefer_source=False)
        else:
            record = KnowledgeUnitRecord(
                unit_code=_gen_unit_code(),
                title=data.title,
                content=content,
                summary=data.summary or (samples[0] if samples else None),
                category=data.category,
                content_hash=content_hash,
                status="vector_pending",
                creator_id=user_id,
            )
            await self._unit_repo.create(record)
            unit_id = record.id

            # 缺口建档默认遵循最小权限：先仅创建者本人可见。
            # 知识管理员可在知识资产页审核后再扩大到部门/角色/global。
            await self._perm_repo.replace_all(unit_id, [("user", user_id)])
            await self._session.commit()

            # 不存在源文件，明确按 DB 正文建立 chunk 索引。
            # 索引失败时保持 vector_pending，gap 也不提前标 resolved。
            await self._index_service.rebuild_unit(unit_id, prefer_source=False)

        await self._repo.set_resolved(gap_id, unit_id)
        await self._session.commit()
        logger.info(
            "knowledge_gap.one_click_create gap_id={} unit_id={} user_id={}",
            gap_id,
            unit_id,
            user_id,
        )
        return CreateUnitFromGapResponse(gap_id=gap_id, unit_id=unit_id)

    def _to_response(self, record) -> KnowledgeGapResponse:
        samples = record.sample_questions_json or []
        if isinstance(samples, list):
            samples_list = [str(x) for x in samples]
        else:
            samples_list = []
        return KnowledgeGapResponse(
            id=record.id,
            question_pattern=record.question_pattern,
            sample_questions_json=samples_list,
            ask_count=record.ask_count,
            last_asked_at=record.last_asked_at,
            status=record.status,
            resolved_unit_id=record.resolved_unit_id,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


def build_knowledge_gap_service(
    session: AsyncSession,
    index_service: KnowledgeIndexService | None = None,
) -> KnowledgeGapService:
    return KnowledgeGapService(session, index_service=index_service)

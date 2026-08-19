"""FAQ Review Service：人工 CRUD + 审核发布（含缓存同步）。"""

from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.faq_schema import (
    CreateFaqRequest,
    FaqListResponse,
    FaqResponse,
    FaqReviewRequest,
)
from app.common.errors import (
    FaqNotFoundError,
    InvalidPermissionCodeError,
    UsernameConflictError,
)
from app.infrastructure.redis_client import RedisClient
from app.repositories.faq_repository import FaqRepository
from app.services.faq_cache_service import FaqCacheService


class FaqService:
    def __init__(self, session: AsyncSession, cache: FaqCacheService) -> None:
        self._session = session
        self._repo = FaqRepository(session)
        self._cache = cache

    async def list(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
        source_type: str | None = None,
    ) -> FaqListResponse:
        rows, total = await self._repo.list_paginated(
            page=page,
            page_size=page_size,
            status=status,
            source_type=source_type,
        )
        return FaqListResponse(
            items=[self._to_response(r) for r in rows],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def list_recommendations(self, *, page: int, page_size: int) -> FaqListResponse:
        rows = await self._repo.list_recommendations(page=page, page_size=page_size)
        return FaqListResponse(
            items=[self._to_response(r) for r in rows],
            page=page,
            page_size=page_size,
            total=len(rows),
        )

    async def create(self, data: CreateFaqRequest, user_id: int) -> FaqResponse:
        # 查重
        qhash = self._repo.compute_question_hash(data.question)
        if await self._repo.find_by_question_hash(qhash):
            raise UsernameConflictError(f"FAQ question hash exists: {qhash[:12]}…")
        record = await self._repo.create(
            question=data.question,
            answer=data.answer,
            category=data.category,
            related_unit_id=data.related_unit_id,
            source_type="manual",
            status="pending_review",
        )
        await self._session.commit()
        await self._session.refresh(record)
        logger.info("faq.create faq_id={} user_id={}", record.id, user_id)
        return self._to_response(record)

    async def review(self, faq_id: int, data: FaqReviewRequest, reviewer_id: int) -> FaqResponse:
        record = await self._repo.find_by_id(faq_id)
        if record is None:
            raise FaqNotFoundError(f"id={faq_id}")
        if record.status != "pending_review":
            raise InvalidPermissionCodeError(f"faq {faq_id} already {record.status}")

        if data.action == "approve":
            unit_updated_at = None
            if record.related_unit_id:
                unit_updated_at = await self._repo.get_unit_updated_at(record.related_unit_id)
            await self._repo.update_for_approve(
                faq_id,
                edited_answer=data.edited_answer,
                reviewer_id=reviewer_id,
                unit_updated_at=unit_updated_at,
            )
            # 写 Redis 缓存
            await self._cache.set(
                faq_id=record.id,
                question=record.question,
                answer=data.edited_answer or record.answer,
                related_unit_id=record.related_unit_id,
                unit_updated_at=unit_updated_at,
            )
            logger.info("faq.review.approve faq_id={} reviewer={}", faq_id, reviewer_id)
        else:  # reject
            await self._repo.update_for_reject(faq_id, reviewer_id)
            # 清缓存
            await self._cache.delete(record.question)
            logger.info("faq.review.reject faq_id={} reviewer={}", faq_id, reviewer_id)

        await self._session.commit()
        await self._session.refresh(record)
        return self._to_response(record)

    async def delete(self, faq_id: int) -> None:
        record = await self._repo.find_by_id(faq_id)
        if record is None:
            raise FaqNotFoundError(f"id={faq_id}")
        await self._cache.delete(record.question)
        await self._repo.delete(faq_id)
        await self._session.commit()

    def _to_response(self, record) -> FaqResponse:
        return FaqResponse(
            id=record.id,
            question=record.question,
            answer=record.answer,
            category=record.category,
            related_unit_id=record.related_unit_id,
            related_unit_code=None,  # 演示期不 JOIN；T03 ticket 04 e2e 用
            source_type=record.source_type,
            status=record.status,
            hit_count=record.hit_count,
            reviewer_id=record.reviewer_id,
            reviewed_at=record.reviewed_at,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


def build_faq_service(session: AsyncSession, redis: RedisClient) -> FaqService:
    from app.services.faq_cache_service import build_faq_cache_service

    return FaqService(session, build_faq_cache_service(session, redis))


__all__ = ["FaqService", "build_faq_service"]

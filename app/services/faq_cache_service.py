"""FAQ Cache Service：审核通过后写 Redis hash（含单元版本）；M4 命中时校验。"""

from __future__ import annotations

import hashlib
from datetime import datetime

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.redis_client import RedisClient
from app.repositories.faq_repository import FaqRepository


def _compute_question_hash(question: str) -> str:
    return hashlib.sha1(question.lower().strip().encode("utf-8")).hexdigest()


class FaqCacheService:
    """FAQ 缓存同步：审核发布时写 Redis；M4 chat 时校验版本。"""

    def __init__(self, redis: RedisClient, repo: FaqRepository) -> None:
        self._redis = redis
        self._repo = repo

    async def get(self, question: str) -> dict | None:
        """读 FAQ 缓存（含单元版本校验）。"""
        key = f"faq:cache:{_compute_question_hash(question)}"
        cached = await self._redis.hgetall(key)
        if not cached:
            return None

        unit_id = int(cached.get("related_unit_id", 0))
        if unit_id > 0:
            db_updated_at = await self._repo.get_unit_updated_at(unit_id)
            if db_updated_at and db_updated_at.isoformat() != cached.get("unit_updated_at"):
                logger.info(
                    "faq.cache.invalidate question_hash={} unit_id={}",
                    _compute_question_hash(question)[:8],
                    unit_id,
                )
                await self._redis.delete(key)
                return None

        return {
            "answer": cached.get("answer"),
            "related_unit_id": unit_id,
            "unit_updated_at": cached.get("unit_updated_at"),
        }

    async def set(
        self,
        faq_id: int,
        question: str,
        answer: str,
        related_unit_id: int | None,
        unit_updated_at: datetime | None,
    ) -> None:
        """写入 Redis 缓存（HSET）。"""
        key = f"faq:cache:{_compute_question_hash(question)}"
        await self._redis.hset(
            key,
            mapping={
                "answer": answer,
                "related_unit_id": str(related_unit_id or 0),
                "unit_updated_at": unit_updated_at.isoformat() if unit_updated_at else "",
                "faq_id": str(faq_id),
            },
        )
        logger.info(
            "faq.cache.set question_hash={} faq_id={}",
            _compute_question_hash(question)[:8],
            faq_id,
        )

    async def delete(self, question: str) -> None:
        """驳回 / 重新审核 → 删缓存。"""
        key = f"faq:cache:{_compute_question_hash(question)}"
        await self._redis.delete(key)
        logger.info("faq.cache.delete question_hash={}", _compute_question_hash(question)[:8])

    async def invalidate_by_unit_ids(self, unit_ids: list[int]) -> None:
        """知识单元删除时 → 失效所有挂载的 FAQ 缓存。"""
        if not unit_ids:
            return
        from sqlalchemy import select

        from app.infrastructure.database import FaqRecord as F

        rows = (
            await self._repo._session.execute(
                select(F.question).where(F.related_unit_id.in_(unit_ids))
            )
        ).all()
        for (q,) in rows:
            await self.delete(q)


def build_faq_cache_service(session: AsyncSession, redis: RedisClient) -> FaqCacheService:
    return FaqCacheService(redis, FaqRepository(session))

"""DashboardRepository：read-only 聚合查询（不写）。"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import (
    KnowledgeUnitRecord,
    QaAccessLogRecord,
)


class DashboardRepository:
    VALID_RANGES = (7, 30, 90)

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _validate_range(self, range_days: int) -> int:
        if range_days not in self.VALID_RANGES:
            raise ValueError(f"range must be one of {self.VALID_RANGES}, got {range_days}")
        return range_days

    async def fetch_metrics(self, range_days: int) -> dict:
        self._validate_range(range_days)
        cutoff = datetime.utcnow() - timedelta(days=range_days)

        # 主指标
        main = (
            await self._session.execute(
                select(
                    func.count().label("access_count"),
                    func.count(func.distinct(QaAccessLogRecord.user_id)).label("unique_users"),
                    func.coalesce(func.sum(QaAccessLogRecord.total_tokens), 0).label(
                        "total_tokens"
                    ),
                    func.avg(QaAccessLogRecord.response_time_ms).label("avg_rt"),
                    func.count(QaAccessLogRecord.response_time_ms).label("sc_count"),
                ).where(QaAccessLogRecord.created_at >= cutoff)
            )
        ).first()

        # 单元数（active 状态）
        unit_count = (
            await self._session.execute(
                select(func.count(KnowledgeUnitRecord.id)).where(
                    KnowledgeUnitRecord.status == "active"
                )
            )
        ).scalar_one()

        # p95（SQLite 不支持 PERCENTILE_CONT，简化为 max；MySQL 用 PERCENTILE_CONT 替换）
        p95 = (
            await self._session.execute(
                select(func.max(QaAccessLogRecord.response_time_ms)).where(
                    QaAccessLogRecord.created_at >= cutoff,
                    QaAccessLogRecord.response_time_ms.is_not(None),
                )
            )
        ).scalar() or 0

        return {
            "access_count": int(main.access_count or 0),
            "unique_users": int(main.unique_users or 0),
            "total_tokens": int(main.total_tokens or 0),
            "avg_response_time_ms": float(main.avg_rt or 0),
            "p95_response_time_ms": float(p95),
            "sample_count": int(main.sc_count or 0),
            "unit_count": int(unit_count),
            "range_days": range_days,
        }

    async def fetch_question_rankings(self, range_days: int, limit: int = 20) -> list[dict]:
        self._validate_range(range_days)
        cutoff = datetime.utcnow() - timedelta(days=range_days)

        # GROUP BY question（注意：question 是 TEXT，SQLite 用字符长度前 N）
        stmt = (
            select(
                QaAccessLogRecord.question,
                func.count().label("c"),
                func.max(QaAccessLogRecord.created_at).label("last_asked_at"),
            )
            .where(QaAccessLogRecord.created_at >= cutoff)
            .group_by(QaAccessLogRecord.question)
            .order_by(func.count().desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            {
                "question": r.question,
                "ask_count": int(r.c),
                "last_asked_at": r.last_asked_at,
            }
            for r in rows
        ]

    async def fetch_unit_rankings(self, range_days: int, limit: int = 20) -> list[dict]:
        """知识热度 TOP 榜：JOIN qa_access_logs.recalled_unit_ids_json → knowledge_units。

        演示期：JSON_TABLE 是 MySQL 8.0+ 特性，SQLite 不支持。改用 SQL 字符串解析
        演示版：演示期假定 recalled_unit_ids_json 是 JSON 数组 [1, 2, ...]，用 SQL 模拟。
        """
        self._validate_range(range_days)
        cutoff = datetime.utcnow() - timedelta(days=range_days)

        # 简化的 JOIN：演示版只支持 MySQL；SQLite 走全表遍历
        # 真实生产：JSON_TABLE（MySQL 8.0+）
        # 演示：拉所有 qa_access_logs，应用层展开（数据量 < 1000 演示期可接受）
        stmt = (
            select(QaAccessLogRecord.recalled_unit_ids_json)
            .where(QaAccessLogRecord.created_at >= cutoff)
            .where(QaAccessLogRecord.recalled_unit_ids_json.is_not(None))
        )
        rows = (await self._session.execute(stmt)).all()

        # 聚合 unit_id → count
        unit_counter: dict[int, int] = {}
        from app.infrastructure.database import KnowledgeUnitRecord as KU

        for (raw_json,) in rows:
            if not raw_json:
                continue
            # raw_json 是 Python list（SQLAlchemy JSON column 自动反序列化）
            items = raw_json if isinstance(raw_json, list) else []
            for item in items:
                uid = item.get("id") if isinstance(item, dict) else item
                if isinstance(uid, int):
                    unit_counter[uid] = unit_counter.get(uid, 0) + 1

        # 取 TOP limit
        top_ids = sorted(unit_counter.items(), key=lambda x: x[1], reverse=True)[:limit]
        if not top_ids:
            return []
        top_uid_list = [uid for uid, _ in top_ids]

        units = (
            (await self._session.execute(select(KU).where(KU.id.in_(top_uid_list)))).scalars().all()
        )
        unit_map = {u.id: u for u in units}

        return [
            {
                "unit_id": uid,
                "unit_code": unit_map[uid].unit_code,
                "title": unit_map[uid].title,
                "access_count": cnt,
            }
            for uid, cnt in top_ids
            if uid in unit_map
        ]

    async def fetch_token_stats(self, range_days: int) -> list[dict]:
        self._validate_range(range_days)
        cutoff = datetime.utcnow() - timedelta(days=range_days)

        # 按日分桶（SQLite: DATE()；MySQL: DATE()）
        stmt = (
            select(
                func.date(QaAccessLogRecord.created_at).label("bucket_date"),
                func.sum(QaAccessLogRecord.total_tokens).label("total_tokens"),
                func.sum(QaAccessLogRecord.prompt_tokens).label("prompt_tokens"),
                func.sum(QaAccessLogRecord.completion_tokens).label("completion_tokens"),
            )
            .where(QaAccessLogRecord.created_at >= cutoff)
            .group_by(func.date(QaAccessLogRecord.created_at))
            .order_by("bucket_date")
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            {
                "bucket_date": r.bucket_date,
                "total_tokens": int(r.total_tokens or 0),
                "prompt_tokens": int(r.prompt_tokens or 0),
                "completion_tokens": int(r.completion_tokens or 0),
            }
            for r in rows
        ]

    async def fetch_response_time_stats(self, range_days: int) -> list[dict]:
        self._validate_range(range_days)
        cutoff = datetime.utcnow() - timedelta(days=range_days)

        stmt = (
            select(
                func.date(QaAccessLogRecord.created_at).label("bucket_date"),
                func.avg(QaAccessLogRecord.response_time_ms).label("avg_rt"),
                func.max(QaAccessLogRecord.response_time_ms).label("p95"),
                func.count().label("sample_count"),
            )
            .where(
                QaAccessLogRecord.created_at >= cutoff,
                QaAccessLogRecord.response_time_ms.is_not(None),
            )
            .group_by(func.date(QaAccessLogRecord.created_at))
            .order_by("bucket_date")
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            {
                "bucket_date": r.bucket_date,
                "avg_response_time_ms": float(r.avg_rt or 0),
                "p95_response_time_ms": float(r.p95 or 0),
                "sample_count": int(r.sample_count or 0),
            }
            for r in rows
        ]

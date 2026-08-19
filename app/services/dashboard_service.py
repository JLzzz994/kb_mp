"""DashboardService：5 项指标 + TOP 榜 + 趋势（包装 Repository）。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.dashboard_schema import (
    MetricsResponse,
    QuestionRankingItem,
    ResponseTimeStatsBucket,
    TokenStatsBucket,
    UnitRankingItem,
)
from app.repositories.dashboard_repository import DashboardRepository


class DashboardService:
    def __init__(self, repo: DashboardRepository) -> None:
        self._repo = repo

    async def metrics(self, range_days: int) -> MetricsResponse:
        rows = await self._repo.fetch_metrics(range_days)
        return MetricsResponse(**rows)

    async def question_rankings(
        self, range_days: int, limit: int = 20
    ) -> list[QuestionRankingItem]:
        rows = await self._repo.fetch_question_rankings(range_days, limit)
        return [QuestionRankingItem(**r) for r in rows]

    async def unit_rankings(self, range_days: int, limit: int = 20) -> list[UnitRankingItem]:
        rows = await self._repo.fetch_unit_rankings(range_days, limit)
        return [UnitRankingItem(**r) for r in rows]

    async def token_stats(self, range_days: int) -> list[TokenStatsBucket]:
        rows = await self._repo.fetch_token_stats(range_days)
        return [TokenStatsBucket(**r) for r in rows]

    async def response_time_stats(self, range_days: int) -> list[ResponseTimeStatsBucket]:
        rows = await self._repo.fetch_response_time_stats(range_days)
        return [ResponseTimeStatsBucket(**r) for r in rows]


def build_dashboard_service(session: AsyncSession) -> DashboardService:
    return DashboardService(DashboardRepository(session))

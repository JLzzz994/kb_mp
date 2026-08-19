"""DashboardRouter：5 端点（metrics / 2× rankings / 2× stats）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, require_permission
from app.api.schemas.dashboard_schema import (
    MetricsResponse,
    QuestionRankingItem,
    ResponseTimeStatsBucket,
    TokenStatsBucket,
    UnitRankingItem,
)
from app.services.dashboard_service import DashboardService, build_dashboard_service

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


def get_dashboard_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DashboardService:
    return build_dashboard_service(session)


DashboardServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    dependencies=[Depends(require_permission("dashboard:read"))],
)
async def get_metrics(
    service: DashboardServiceDep,
    range: int = Query(7, description="7 | 30 | 90"),
) -> MetricsResponse:
    return await service.metrics(range)


@router.get(
    "/rankings/questions",
    response_model=list[QuestionRankingItem],
    dependencies=[Depends(require_permission("dashboard:read"))],
)
async def get_question_rankings(
    service: DashboardServiceDep,
    range: int = Query(7),
    limit: int = Query(20, ge=1, le=100),
) -> list[QuestionRankingItem]:
    return await service.question_rankings(range, limit)


@router.get(
    "/rankings/units",
    response_model=list[UnitRankingItem],
    dependencies=[Depends(require_permission("dashboard:read"))],
)
async def get_unit_rankings(
    service: DashboardServiceDep,
    range: int = Query(7),
    limit: int = Query(20, ge=1, le=100),
) -> list[UnitRankingItem]:
    return await service.unit_rankings(range, limit)


@router.get(
    "/stats/tokens",
    response_model=list[TokenStatsBucket],
    dependencies=[Depends(require_permission("dashboard:read"))],
)
async def get_token_stats(
    service: DashboardServiceDep,
    range: int = Query(7),
) -> list[TokenStatsBucket]:
    return await service.token_stats(range)


@router.get(
    "/stats/response-time",
    response_model=list[ResponseTimeStatsBucket],
    dependencies=[Depends(require_permission("dashboard:read"))],
)
async def get_response_time_stats(
    service: DashboardServiceDep,
    range: int = Query(7),
) -> list[ResponseTimeStatsBucket]:
    return await service.response_time_stats(range)

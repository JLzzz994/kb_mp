"""SettlementRouter：FAQ CRUD + 审核 + 知识缺口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUserDep, get_db, get_redis, require_permission
from app.api.schemas.faq_schema import (
    CreateFaqRequest,
    FaqListResponse,
    FaqResponse,
    FaqReviewRequest,
)
from app.infrastructure.redis_client import RedisClient
from app.services.faq_service import FaqService, build_faq_service

router = APIRouter(tags=["settlement"])


def get_faq_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[RedisClient, Depends(get_redis)],
) -> FaqService:
    return build_faq_service(session, redis)


FaqServiceDep = Annotated[FaqService, Depends(get_faq_service)]


# ── FAQ CRUD ─────────────────────────────


@router.get(
    "/api/v1/faqs",
    response_model=FaqListResponse,
    dependencies=[Depends(require_permission("faq:read"))],
)
async def list_faqs(
    service: FaqServiceDep,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    source_type: str | None = None,
) -> FaqListResponse:
    return await service.list(
        page=page, page_size=page_size, status=status, source_type=source_type
    )


@router.get(
    "/api/v1/faqs/recommendations",
    response_model=FaqListResponse,
    dependencies=[Depends(require_permission("faq:review"))],
)
async def list_faq_recommendations(
    service: FaqServiceDep,
    page: int = 1,
    page_size: int = 20,
) -> FaqListResponse:
    """审核页：仅返回 status=pending_review。"""
    return await service.list_recommendations(page=page, page_size=page_size)


@router.post(
    "/api/v1/faqs",
    response_model=FaqResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("faq:write"))],
)
async def create_faq(
    data: CreateFaqRequest,
    user: CurrentUserDep,
    service: FaqServiceDep,
) -> FaqResponse:
    return await service.create(data, user.id)


@router.post(
    "/api/v1/faqs/{faq_id}/review",
    response_model=FaqResponse,
    dependencies=[Depends(require_permission("faq:review"))],
)
async def review_faq(
    faq_id: int,
    data: FaqReviewRequest,
    user: CurrentUserDep,
    service: FaqServiceDep,
) -> FaqResponse:
    return await service.review(faq_id, data, user.id)


@router.delete(
    "/api/v1/faqs/{faq_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("faq:write"))],
)
async def delete_faq(faq_id: int, service: FaqServiceDep) -> None:
    await service.delete(faq_id)

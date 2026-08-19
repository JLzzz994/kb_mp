"""FAQ Schema（Pydantic）。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class FaqResponse(BaseModel):
    id: int
    question: str
    answer: str
    category: str | None = None
    related_unit_id: int | None = None
    related_unit_code: str | None = None
    source_type: Literal["manual", "auto_mined"]
    status: Literal["pending_review", "published", "rejected"]
    hit_count: int
    reviewer_id: int | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class FaqListResponse(BaseModel):
    items: list[FaqResponse]
    page: int
    page_size: int
    total: int


class CreateFaqRequest(BaseModel):
    question: str = Field(min_length=5, max_length=2000)
    answer: str = Field(min_length=1, max_length=10000)
    category: str | None = None
    related_unit_id: int | None = None


class FaqReviewRequest(BaseModel):
    action: Literal["approve", "reject"]
    edited_answer: str | None = None


__all__ = ["FaqResponse", "FaqListResponse", "CreateFaqRequest", "FaqReviewRequest"]

"""KnowledgeGap Schema + 一键建档 请求。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class KnowledgeGapResponse(BaseModel):
    id: int
    question_pattern: str
    sample_questions_json: list[str]
    ask_count: int
    last_asked_at: datetime
    status: str
    resolved_unit_id: int | None
    created_at: datetime
    updated_at: datetime


class KnowledgeGapListResponse(BaseModel):
    items: list[KnowledgeGapResponse]
    page: int
    page_size: int
    total: int


class CreateUnitFromGapRequest(BaseModel):
    """一键建档：基于缺口创建一个 knowledge_unit。"""

    title: str
    category: str | None = None
    summary: str | None = None
    content: str | None = None  # 不传则取 sample_questions_json[0]


class CreateUnitFromGapResponse(BaseModel):
    gap_id: int
    unit_id: int


__all__ = [
    "KnowledgeGapResponse",
    "KnowledgeGapListResponse",
    "CreateUnitFromGapRequest",
    "CreateUnitFromGapResponse",
]

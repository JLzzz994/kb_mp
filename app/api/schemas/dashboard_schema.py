"""数据看板 Schema。"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

# ── 5 项指标 ─────────────────────────────


class MetricsResponse(BaseModel):
    access_count: int
    unique_users: int
    unit_count: int
    total_tokens: int
    avg_response_time_ms: float
    p95_response_time_ms: float
    sample_count: int
    range_days: int


# ── TOP 榜 ─────────────────────────────


class QuestionRankingItem(BaseModel):
    question: str
    ask_count: int
    last_asked_at: datetime


class UnitRankingItem(BaseModel):
    unit_id: int
    unit_code: str
    title: str
    access_count: int


# ── 趋势图（按日分桶） ─────────────────────────────


class TokenStatsBucket(BaseModel):
    bucket_date: date
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int


class ResponseTimeStatsBucket(BaseModel):
    bucket_date: date
    avg_response_time_ms: float
    p95_response_time_ms: float
    sample_count: int


__all__ = [
    "MetricsResponse",
    "QuestionRankingItem",
    "UnitRankingItem",
    "TokenStatsBucket",
    "ResponseTimeStatsBucket",
]

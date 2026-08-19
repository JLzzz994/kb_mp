"""AI Chat Stream Schema。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatStreamRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    question: str = Field(min_length=1, max_length=2000)


class ChatResumeRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    question: str = Field(min_length=1, max_length=2000)


# ── SSE event payloads ─────────────────────────────


class CitationEvent(BaseModel):
    unit_id: int
    title: str
    score: float


class UnauthorizedEvent(BaseModel):
    unit_ids: list[int]


class InterruptEvent(BaseModel):
    reason: Literal["no_recall", "no_recall_with_permission", "low_confidence"]
    session_id: str


class FinalEvent(BaseModel):
    answer: str
    usage: dict
    source: str  # "llm" / "faq_cache"


__all__ = [
    "ChatStreamRequest",
    "ChatResumeRequest",
    "CitationEvent",
    "UnauthorizedEvent",
    "InterruptEvent",
    "FinalEvent",
]

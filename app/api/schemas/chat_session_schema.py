"""Chat Session Schema。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class UpdateSessionRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class ChatSessionResponse(BaseModel):
    id: str
    user_id: int
    title: str | None
    history_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class SessionListItem(BaseModel):
    id: str
    title: str | None
    updated_at: datetime


__all__ = [
    "CreateSessionRequest",
    "UpdateSessionRequest",
    "ChatSessionResponse",
    "SessionListItem",
]

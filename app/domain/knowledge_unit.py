"""知识单元领域实体。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class KnowledgeUnitEntity:
    id: int
    unit_code: str
    title: str
    content: str
    summary: str | None
    category: str | None
    source_file_name: str | None
    file_type: str | None
    file_size: int | None
    content_hash: str | None
    status: str  # active / vector_pending / failed
    creator_id: int
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class KnowledgeChunk:
    """切片后的单片。"""

    text: str
    index: int


__all__ = ["KnowledgeUnitEntity", "KnowledgeChunk"]

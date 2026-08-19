"""知识导入 Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ImportRejectedItem(BaseModel):
    filename: str
    reason: str  # duplicate_content / unsupported_format / size_exceeded / parse_error


class ImportTaskResponse(BaseModel):
    task_id: str
    accepted_count: int
    rejected: list[ImportRejectedItem] = Field(default_factory=list)


__all__ = ["ImportRejectedItem", "ImportTaskResponse"]

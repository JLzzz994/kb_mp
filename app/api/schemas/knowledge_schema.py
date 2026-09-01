"""知识单元 + 权限 Schema。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ── 权限条目 ─────────────────────────────


class PermissionEntryResponse(BaseModel):
    target_type: Literal["global", "department", "role", "user"]
    target_id: int | None
    target_label: str = ""


class ConfigurePermissionsRequest(BaseModel):
    permissions: list[PermissionEntryResponse] = Field(min_length=1)


# ── 知识单元 ─────────────────────────────


class KnowledgeUnitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    unit_code: str
    title: str
    summary: str | None
    category: str | None
    file_type: str | None
    source_file_name: str | None
    permissions_summary: str
    creator_id: int
    creator_name: str
    status: str
    created_at: datetime
    updated_at: datetime


class KnowledgeUnitDetailResponse(KnowledgeUnitResponse):
    content: str
    permissions: list[PermissionEntryResponse] = Field(default_factory=list)


class KnowledgeUnitListResponse(BaseModel):
    items: list[KnowledgeUnitResponse]
    page: int
    page_size: int
    total: int


class KnowledgeUnitPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = None
    summary: str | None = None
    category: str | None = None


class BatchDeleteRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)


class KnowledgeIndexStatusResponse(BaseModel):
    unit_id: int
    configured: bool
    db_status: str
    chunk_count: int | None
    consistent: bool
    detail: str = ""


# ── check-permissions 共享接口 ─────────────────────────────


class CheckPermissionsRequest(BaseModel):
    user_id: int
    unit_ids: list[int] = Field(min_length=1, max_length=500)


class CheckPermissionsResponse(BaseModel):
    authorized_unit_ids: list[int]
    unauthorized_unit_ids: list[int]


__all__ = [
    "PermissionEntryResponse",
    "ConfigurePermissionsRequest",
    "KnowledgeUnitResponse",
    "KnowledgeUnitDetailResponse",
    "KnowledgeUnitListResponse",
    "KnowledgeUnitPatch",
    "BatchDeleteRequest",
    "KnowledgeIndexStatusResponse",
    "CheckPermissionsRequest",
    "CheckPermissionsResponse",
]

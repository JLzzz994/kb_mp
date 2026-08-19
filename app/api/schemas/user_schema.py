"""用户 Schema（Pydantic）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=64)
    department_id: int
    role_ids: list[int] = Field(min_length=1)


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=64)
    department_id: int | None = None
    role_ids: list[int] | None = None
    status: int | None = Field(default=None, ge=0, le=1)


class UserStatusPatch(BaseModel):
    status: int = Field(ge=0, le=1)


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    department_id: int
    department_name: str = ""
    role_codes: list[str] = Field(default_factory=list)
    status: int
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    items: list[UserResponse]
    page: int
    page_size: int
    total: int


__all__ = [
    "UserCreate",
    "UserUpdate",
    "UserStatusPatch",
    "ResetPasswordRequest",
    "UserResponse",
    "UserListResponse",
]

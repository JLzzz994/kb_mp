"""鉴权请求 Schema（仅入参校验）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)


__all__ = ["LoginRequest"]

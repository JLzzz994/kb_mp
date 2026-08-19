"""鉴权响应 Schema。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class CurrentUserInfo(BaseModel):
    id: int
    username: str
    display_name: str
    department_id: int
    department_name: str
    role_codes: list[str]


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int  # 秒
    user_info: CurrentUserInfo
    permissions: list[str]


class MeResponse(BaseModel):
    user_info: CurrentUserInfo
    permissions: list[str]


__all__ = ["LoginResponse", "MeResponse", "CurrentUserInfo"]

"""角色 Schema（Pydantic）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RoleResponse(BaseModel):
    id: int
    role_name: str
    role_code: str
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)


class AssignPermissionsRequest(BaseModel):
    """替换某角色的全部权限码（与 create 行为一致：全量替换）。"""

    permission_codes: list[str] = Field(min_length=1)


__all__ = ["RoleResponse", "AssignPermissionsRequest"]

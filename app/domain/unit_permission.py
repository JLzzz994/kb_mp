"""知识四维权限领域实体。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PermissionTarget(StrEnum):
    """四维权限目标类型（OR 逻辑合并）。"""

    GLOBAL = "global"
    DEPARTMENT = "department"
    ROLE = "role"
    USER = "user"


@dataclass(slots=True)
class UnitPermissionEntity:
    id: int
    unit_id: int
    target_type: PermissionTarget
    target_id: int | None  # global → None；其余 → 实体 id


@dataclass(slots=True)
class PermissionEntry:
    """配置 / 展示层用的权限条目（DTO）。"""

    target_type: PermissionTarget
    target_id: int | None
    target_label: str = ""  # 部门名 / 角色名 / 用户名（用于前端展示）


__all__ = ["PermissionTarget", "UnitPermissionEntity", "PermissionEntry"]

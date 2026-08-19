"""部门领域实体（dataclass）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DepartmentEntity:
    """部门树节点。"""

    id: int
    parent_id: int | None
    name: str
    leader_id: int | None
    sort_order: int


@dataclass(slots=True)
class DepartmentNode:
    """部门树渲染节点（嵌套 children）。"""

    id: int
    parent_id: int | None
    name: str
    leader_id: int | None
    sort_order: int
    children: list[DepartmentNode]

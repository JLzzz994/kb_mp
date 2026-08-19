"""部门请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DepartmentNode(BaseModel):
    """部门树渲染节点（嵌套 children）。"""

    id: int
    parent_id: int | None
    name: str
    leader_id: int | None
    sort_order: int
    member_count: int = 0
    children: list[DepartmentNode] = Field(default_factory=list)


class DepartmentCreate(BaseModel):
    """部门创建请求。parent_id 为 None 表示创建顶级部门。"""

    name: str = Field(min_length=1, max_length=64)
    parent_id: int | None = None
    leader_id: int | None = None
    sort_order: int = 0


class DepartmentUpdate(BaseModel):
    """部门更新请求（全量字段）。"""

    name: str = Field(min_length=1, max_length=64)
    parent_id: int | None = None
    leader_id: int | None = None
    sort_order: int = 0


# 解决前向引用
DepartmentNode.model_rebuild()


__all__ = ["DepartmentNode", "DepartmentCreate", "DepartmentUpdate"]

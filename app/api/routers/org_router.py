"""OrgRouter：组织架构路由（部门 + 角色 + 用户，共用 prefix /api/v1/org）。

> 当前 T02 阶段只注册部门端点；T03 角色 / T04 用户将合并到本文件。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, require_permission
from app.api.schemas.department_schema import (
    DepartmentCreate,
    DepartmentNode,
    DepartmentUpdate,
)
from app.services.department_service import DepartmentService, build_department_service

router = APIRouter(prefix="/api/v1/org", tags=["org"])


def get_department_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DepartmentService:
    return build_department_service(session)


DepartmentServiceDep = Annotated[DepartmentService, Depends(get_department_service)]


# ── 部门端点 ─────────────────────────────


@router.get(
    "/departments",
    response_model=list[DepartmentNode],
    dependencies=[Depends(require_permission("dept:read"))],
)
async def list_departments(service: DepartmentServiceDep) -> list[DepartmentNode]:
    """部门树（按 sort_order ASC, id ASC 递归）。"""
    return await service.list_tree()


@router.post(
    "/departments",
    response_model=DepartmentNode,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("dept:write"))],
)
async def create_department(
    data: DepartmentCreate,
    service: DepartmentServiceDep,
) -> DepartmentNode:
    """创建部门。parent_id 不存在 → 404 department_not_found。"""
    return await service.create(data)


@router.put(
    "/departments/{dept_id}",
    response_model=DepartmentNode,
    dependencies=[Depends(require_permission("dept:write"))],
)
async def update_department(
    dept_id: int,
    data: DepartmentUpdate,
    service: DepartmentServiceDep,
) -> DepartmentNode:
    """更新部门（全量字段）。不存在 → 404。"""
    return await service.update(dept_id, data)


@router.delete(
    "/departments/{dept_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("dept:write"))],
)
async def delete_department(dept_id: int, service: DepartmentServiceDep) -> Response:
    """删除部门。子部门或成员存在 → 422 department_not_empty。"""
    await service.delete(dept_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

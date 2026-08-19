"""OrgRouter：组织架构路由（部门 + 角色 + 用户，共用 prefix /api/v1/org）。

> 当前包含 T02 部门 + T03 角色端点；T04 用户将合并到本文件。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_redis, require_permission
from app.api.schemas.department_schema import (
    DepartmentCreate,
    DepartmentNode,
    DepartmentUpdate,
)
from app.api.schemas.role_schema import AssignPermissionsRequest, RoleResponse
from app.infrastructure.redis_client import RedisClient
from app.services.department_service import DepartmentService, build_department_service
from app.services.role_service import RoleService, build_role_service

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


# ── 角色端点 ─────────────────────────────


def get_role_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[RedisClient, Depends(get_redis)],
) -> RoleService:
    return build_role_service(session, redis)


RoleServiceDep = Annotated[RoleService, Depends(get_role_service)]


@router.get(
    "/roles",
    response_model=list[RoleResponse],
    dependencies=[Depends(require_permission("role:read"))],
)
async def list_roles(service: RoleServiceDep) -> list[RoleResponse]:
    """所有角色 + 各自权限码列表。"""
    return await service.list()


@router.get(
    "/permissions",
    response_model=list[str],
    dependencies=[Depends(require_permission("role:read"))],
)
async def list_permission_codes(service: RoleServiceDep) -> list[str]:
    """17 码白名单（前端用于角色分配 UI）。"""
    return await service.list_all_permission_codes()


@router.post(
    "/roles/{role_id}/permissions",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("role:write"))],
)
async def assign_role_permissions(
    role_id: int,
    data: AssignPermissionsRequest,
    service: RoleServiceDep,
) -> Response:
    """替换 role 的全部权限码 + 批量失效持有此 role 的 Redis 位图。"""
    await service.assign_permissions(role_id, data.permission_codes)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

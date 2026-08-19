"""KnowledgeRouter：知识单元 CRUD + 权限配置 + check-permissions 共享接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUserDep, get_db, get_redis, require_permission
from app.api.schemas.knowledge_schema import (
    BatchDeleteRequest,
    CheckPermissionsRequest,
    CheckPermissionsResponse,
    ConfigurePermissionsRequest,
    KnowledgeUnitDetailResponse,
    KnowledgeUnitListResponse,
    KnowledgeUnitPatch,
    KnowledgeUnitResponse,
    PermissionEntryResponse,
)
from app.infrastructure.redis_client import RedisClient
from app.services.knowledge_permission_service import (
    KnowledgePermissionService,
    build_knowledge_permission_service,
)
from app.services.knowledge_unit_service import (
    KnowledgeUnitService,
    build_knowledge_unit_service,
)

router = APIRouter(tags=["knowledge"])


def get_knowledge_unit_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> KnowledgeUnitService:
    return build_knowledge_unit_service(session)


KnowledgeUnitServiceDep = Annotated[KnowledgeUnitService, Depends(get_knowledge_unit_service)]


def get_knowledge_permission_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[RedisClient, Depends(get_redis)],
) -> KnowledgePermissionService:
    return build_knowledge_permission_service(session, redis)


KnowledgePermissionServiceDep = Annotated[
    KnowledgePermissionService, Depends(get_knowledge_permission_service)
]


# ── 知识单元 CRUD ─────────────────────────────


@router.get(
    "/api/v1/knowledge-units",
    response_model=KnowledgeUnitListResponse,
    dependencies=[Depends(require_permission("knowledge:read"))],
)
async def list_knowledge_units(
    service: KnowledgeUnitServiceDep,
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    category: str | None = None,
    status: str | None = None,
) -> KnowledgeUnitListResponse:
    return await service.list(
        page=page,
        page_size=page_size,
        keyword=keyword,
        category=category,
        status=status,
    )


@router.get(
    "/api/v1/knowledge-units/{unit_id}",
    response_model=KnowledgeUnitDetailResponse,
    dependencies=[Depends(require_permission("knowledge:read"))],
)
async def get_knowledge_unit(
    unit_id: int,
    service: KnowledgeUnitServiceDep,
) -> KnowledgeUnitDetailResponse:
    return await service.get(unit_id)


@router.patch(
    "/api/v1/knowledge-units/{unit_id}",
    response_model=KnowledgeUnitResponse,
    dependencies=[Depends(require_permission("knowledge:write"))],
)
async def patch_knowledge_unit(
    unit_id: int,
    data: KnowledgeUnitPatch,
    service: KnowledgeUnitServiceDep,
    user: CurrentUserDep,
) -> KnowledgeUnitResponse:
    return await service.patch(unit_id, data, user)


@router.delete(
    "/api/v1/knowledge-units",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("knowledge:delete"))],
)
async def batch_delete_knowledge_units(
    req: BatchDeleteRequest,
    service: KnowledgeUnitServiceDep,
) -> None:
    deleted = await service.batch_delete(req)
    if deleted == 0:
        return
    from fastapi import Response

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── 权限配置 ─────────────────────────────


@router.post(
    "/api/v1/knowledge-units/{unit_id}/permissions",
    response_model=list[PermissionEntryResponse],
    dependencies=[Depends(require_permission("knowledge:assign_permission"))],
)
async def configure_knowledge_permissions(
    unit_id: int,
    req: ConfigurePermissionsRequest,
    service: KnowledgeUnitServiceDep,
    user: CurrentUserDep,
) -> list[PermissionEntryResponse]:
    entries = await service.configure_permissions(unit_id, req, user)
    return entries


# ── check-permissions（M3 定义，M4 共享） ─────────────────────────────


@router.post(
    "/api/v1/knowledge/check-permissions",
    response_model=CheckPermissionsResponse,
    dependencies=[Depends(require_permission("knowledge:check"))],
)
async def check_knowledge_permissions(
    req: CheckPermissionsRequest,
    service: KnowledgePermissionServiceDep,
) -> CheckPermissionsResponse:
    return await service.check_permissions(req.user_id, req.unit_ids)

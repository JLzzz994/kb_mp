"""KnowledgeRouter：知识单元 CRUD + 权限配置 + check-permissions 共享接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUserDep, get_db, get_redis, require_permission
from app.api.schemas.knowledge_import_schema import ImportTaskResponse
from app.api.schemas.knowledge_schema import (
    BatchDeleteRequest,
    CheckPermissionsRequest,
    CheckPermissionsResponse,
    ConfigurePermissionsRequest,
    KnowledgeIndexStatusResponse,
    KnowledgeUnitDetailResponse,
    KnowledgeUnitListResponse,
    KnowledgeUnitPatch,
    KnowledgeUnitResponse,
    PermissionEntryResponse,
)
from app.infrastructure.redis_client import RedisClient
from app.services.knowledge_import_service import (
    KnowledgeImportService,
    build_knowledge_import_service,
)
from app.services.knowledge_index_service import (
    KnowledgeIndexService,
    build_knowledge_index_service,
)
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


def get_knowledge_import_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> KnowledgeImportService:
    return build_knowledge_import_service(session)


KnowledgeImportServiceDep = Annotated[KnowledgeImportService, Depends(get_knowledge_import_service)]


def get_knowledge_index_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> KnowledgeIndexService:
    return build_knowledge_index_service(session)


KnowledgeIndexServiceDep = Annotated[KnowledgeIndexService, Depends(get_knowledge_index_service)]


# ── 导入（multipart） ─────────────────────────────


@router.post(
    "/api/v1/knowledge/import",
    response_model=ImportTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission("knowledge:write"))],
)
async def import_knowledge(
    request: Request,
    service: KnowledgeImportServiceDep,
    user: CurrentUserDep,
) -> ImportTaskResponse:
    """multipart/form-data 接收 files（多文件），返回 202 + task_id + accepted + rejected。"""
    form = await request.form()
    uploads = form.getlist("files")
    files_data: list[tuple[str, bytes]] = []
    for up in uploads:
        # up 可能是 UploadFile（来自 multipart）
        if hasattr(up, "filename"):
            content = await up.read()
            files_data.append((up.filename or "unnamed", content))
        else:
            # 兜底：直接是字符串字段
            files_data.append((str(up), b""))
    return await service.import_files(files=files_data, user_id=user.id)


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


@router.get(
    "/api/v1/knowledge-units/{unit_id}/index-status",
    response_model=KnowledgeIndexStatusResponse,
    dependencies=[Depends(require_permission("knowledge:read"))],
)
async def get_knowledge_index_status(
    unit_id: int,
    service: KnowledgeIndexServiceDep,
) -> KnowledgeIndexStatusResponse:
    result = await service.get_status(unit_id)
    return KnowledgeIndexStatusResponse(
        unit_id=result.unit_id,
        configured=result.configured,
        db_status=result.db_status,
        chunk_count=result.chunk_count,
        consistent=result.consistent,
        detail=result.detail,
    )


@router.post(
    "/api/v1/knowledge-units/{unit_id}/reindex",
    response_model=KnowledgeIndexStatusResponse,
    dependencies=[Depends(require_permission("knowledge:write"))],
)
async def reindex_knowledge_unit(
    unit_id: int,
    service: KnowledgeIndexServiceDep,
) -> KnowledgeIndexStatusResponse:
    result = await service.rebuild_unit(unit_id)
    return KnowledgeIndexStatusResponse(
        unit_id=result.unit_id,
        configured=result.configured,
        db_status=result.db_status,
        chunk_count=result.chunk_count,
        consistent=result.consistent,
        detail=result.detail,
    )


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

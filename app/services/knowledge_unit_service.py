"""KnowledgeUnitService：知识单元 CRUD + 权限配置 + 摘要。"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.knowledge_schema import (
    BatchDeleteRequest,
    ConfigurePermissionsRequest,
    KnowledgeUnitDetailResponse,
    KnowledgeUnitListResponse,
    KnowledgeUnitPatch,
    KnowledgeUnitResponse,
    PermissionEntryResponse,
)
from app.common.errors import (
    DuplicateContentError,
    InvalidPermissionConfigurationError,
    KnowledgeUnitNotFoundError,
)
from app.domain.unit_permission import PermissionEntry, PermissionTarget
from app.infrastructure.database import (
    DepartmentRecord,
    KnowledgeUnitRecord,
    RoleRecord,
    UserRecord,
)
from app.infrastructure.source_storage import SourceStorage, build_source_storage
from app.repositories.knowledge_unit_repository import (
    KnowledgeUnitRepository,
    UnitPermissionRepository,
)
from app.services.knowledge_index_service import (
    KnowledgeIndexService,
    build_knowledge_index_service,
)

if TYPE_CHECKING:
    from app.domain.user import CurrentUser


def _compute_content_hash(content: str) -> str:
    """SHA-256 hex 摘要。"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _gen_unit_code() -> str:
    """业务编号 KU-YYYYMM-xxxxxx（演示期简单生成）。"""
    now = datetime.utcnow()
    return f"KU-{now.strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}"


def _summarize_permissions(entries: list[PermissionEntry]) -> str:
    """生成 "全局公开" / "研发部 + 管理员角色" / "研发部 + 张三" 这类摘要。"""
    if not entries:
        return "未配置"
    labels = [e.target_label or e.target_type for e in entries]
    return " + ".join(labels[:3]) + ("…" if len(labels) > 3 else "")


async def _resolve_target_labels(
    session: AsyncSession,
    entries: list[PermissionEntry],
) -> list[PermissionEntry]:
    """解析 target_label（部门名 / 角色名 / 用户名）。global → "全局公开"。"""
    if not entries:
        return []
    from sqlalchemy import select

    dept_ids = [e.target_id for e in entries if e.target_type == "department" and e.target_id]
    role_ids = [e.target_id for e in entries if e.target_type == "role" and e.target_id]
    user_ids = [e.target_id for e in entries if e.target_type == "user" and e.target_id]

    dept_map: dict[int, str] = {}
    role_map: dict[int, str] = {}
    user_map: dict[int, str] = {}

    if dept_ids:
        rows = (
            (
                await session.execute(
                    select(DepartmentRecord).where(DepartmentRecord.id.in_(dept_ids))
                )
            )
            .scalars()
            .all()
        )
        dept_map.update({d.id: d.name for d in rows})
    if role_ids:
        rows = (
            (await session.execute(select(RoleRecord).where(RoleRecord.id.in_(role_ids))))
            .scalars()
            .all()
        )
        role_map.update({r.id: r.role_name for r in rows})
    if user_ids:
        rows = (
            (await session.execute(select(UserRecord).where(UserRecord.id.in_(user_ids))))
            .scalars()
            .all()
        )
        user_map.update({u.id: u.display_name for u in rows})

    resolved: list[PermissionEntry] = []
    for e in entries:
        if e.target_type == "global":
            resolved.append(
                PermissionEntry(target_type=e.target_type, target_id=None, target_label="全局公开")
            )
        elif e.target_type == "department" and e.target_id:
            resolved.append(
                PermissionEntry(
                    target_type=e.target_type,
                    target_id=e.target_id,
                    target_label=dept_map.get(e.target_id, f"#{e.target_id}"),
                )
            )
        elif e.target_type == "role" and e.target_id:
            resolved.append(
                PermissionEntry(
                    target_type=e.target_type,
                    target_id=e.target_id,
                    target_label=role_map.get(e.target_id, f"#{e.target_id}"),
                )
            )
        elif e.target_type == "user" and e.target_id:
            resolved.append(
                PermissionEntry(
                    target_type=e.target_type,
                    target_id=e.target_id,
                    target_label=user_map.get(e.target_id, f"#{e.target_id}"),
                )
            )
    return resolved


class KnowledgeUnitService:
    def __init__(
        self,
        session: AsyncSession,
        index_service: KnowledgeIndexService | None = None,
        source_storage: SourceStorage | None = None,
    ) -> None:
        self._session = session
        self._unit_repo = KnowledgeUnitRepository(session)
        self._perm_repo = UnitPermissionRepository(session)
        self._index_service = index_service or build_knowledge_index_service(session)
        self._source_storage = source_storage or build_source_storage()

    async def list(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str | None,
        category: str | None,
        status: str | None,
    ) -> KnowledgeUnitListResponse:
        rows, total = await self._unit_repo.list_paginated(
            page=page,
            page_size=page_size,
            keyword=keyword,
            category=category,
            status=status,
        )
        items = [
            KnowledgeUnitResponse(
                id=u.id,
                unit_code=u.unit_code,
                title=u.title,
                summary=u.summary,
                category=u.category,
                file_type=u.file_type,
                source_file_name=u.source_file_name,
                permissions_summary=f"{count_count} 条权限" if count_count else "未配置",
                creator_id=u.creator_id,
                creator_name=creator_name,
                status=u.status,
                created_at=u.created_at,
                updated_at=u.updated_at,
            )
            for u, creator_name, count_count in rows
        ]
        return KnowledgeUnitListResponse(items=items, page=page, page_size=page_size, total=total)

    async def get(self, unit_id: int) -> KnowledgeUnitDetailResponse:
        triple = await self._unit_repo.get_with_creator(unit_id)
        if triple is None:
            raise KnowledgeUnitNotFoundError(f"id={unit_id}")
        unit, creator_name, dept_name = triple

        perm_records = await self._perm_repo.list_for_unit(unit_id)
        perm_entries: list[PermissionEntry] = [
            PermissionEntry(
                target_type=PermissionTarget(r.target_type),
                target_id=r.target_id,
                target_label="",
            )
            for r in perm_records
        ]
        # 解析 label
        perm_entries = await _resolve_target_labels(self._session, perm_entries)

        return KnowledgeUnitDetailResponse(
            id=unit.id,
            unit_code=unit.unit_code,
            title=unit.title,
            content=unit.content,
            summary=unit.summary,
            category=unit.category,
            file_type=unit.file_type,
            source_file_name=unit.source_file_name,
            permissions_summary=_summarize_permissions(perm_entries),
            creator_id=unit.creator_id,
            creator_name=creator_name,
            status=unit.status,
            created_at=unit.created_at,
            updated_at=unit.updated_at,
            permissions=[
                PermissionEntryResponse(
                    target_type=e.target_type.value
                    if hasattr(e.target_type, "value")
                    else e.target_type,
                    target_id=e.target_id,
                    target_label=e.target_label,
                )
                for e in perm_entries
            ],
        )

    async def patch(
        self, unit_id: int, data: KnowledgeUnitPatch, user: CurrentUser
    ) -> KnowledgeUnitResponse:
        update_kwargs: dict = {}
        content_changed = data.content is not None
        metadata_changed = data.title is not None or data.category is not None

        if data.title is not None:
            update_kwargs["title"] = data.title
        if data.content is not None:
            update_kwargs["content"] = data.content
            update_kwargs["content_hash"] = _compute_content_hash(data.content)
        if data.summary is not None:
            update_kwargs["summary"] = data.summary
        if data.category is not None:
            update_kwargs["category"] = data.category
        if content_changed or metadata_changed:
            update_kwargs["status"] = "vector_pending"

        unit = await self._unit_repo.update(unit_id, **update_kwargs)
        if unit is None:
            raise KnowledgeUnitNotFoundError(f"id={unit_id}")
        await self._session.commit()

        if content_changed:
            await self._index_service.rebuild_unit(unit_id, prefer_source=False)
        elif metadata_changed:
            await self._index_service.sync_metadata(unit_id)

        logger.info("knowledge.unit.patch unit_id={} actor={}", unit_id, user.id)
        refreshed = await self._unit_repo.find_by_id(unit_id)
        return await self._build_summary(unit_id, refreshed or unit)

    async def patch_full(
        self, unit_id: int, data: KnowledgeUnitPatch, user: CurrentUser
    ) -> KnowledgeUnitDetailResponse:
        """返回完整响应（含 content + permissions）—— 不走 Router 走 Service。"""
        await self.patch(unit_id, data, user)
        return await self.get(unit_id)

    async def batch_delete(self, req: BatchDeleteRequest) -> int:
        records = await self._unit_repo.list_by_ids(req.ids)
        await self._index_service.delete_units(req.ids)
        deleted = await self._unit_repo.delete_by_ids(req.ids)
        await self._session.commit()

        for record in records:
            try:
                await self._source_storage.delete_unit_sources(record.unit_code)
            except Exception as exc:
                # DB 已删除后，对象残留只会形成不可检索 orphan；不回滚业务删除。
                logger.warning(
                    "knowledge.source.delete_orphan unit_code={} backend={} error={}",
                    record.unit_code,
                    self._source_storage.backend_name,
                    exc,
                )

        logger.warning("knowledge.unit.batch_delete count={}", deleted)
        return deleted

    async def create(
        self,
        *,
        title: str,
        content: str,
        summary: str | None,
        category: str | None,
        creator_id: int,
        file_type: str | None,
        source_file_name: str | None,
        file_size: int | None,
    ) -> KnowledgeUnitRecord:
        """手动新建（导入路径会用到；M6 一键建档会复用）。"""
        content_hash = _compute_content_hash(content)
        existing = await self._unit_repo.find_by_content_hash(content_hash)
        if existing is not None:
            raise DuplicateContentError(f"hash={content_hash[:12]}…")
        record = KnowledgeUnitRecord(
            unit_code=_gen_unit_code(),
            title=title,
            content=content,
            summary=summary,
            category=category,
            file_type=file_type,
            source_file_name=source_file_name,
            file_size=file_size,
            content_hash=content_hash,
            status="active",
            creator_id=creator_id,
        )
        return await self._unit_repo.create(record)

    async def configure_permissions(
        self,
        unit_id: int,
        req: ConfigurePermissionsRequest,
        user: CurrentUser,
    ) -> list[PermissionEntryResponse]:
        """配置 unit 权限（事务保证全量替换）。"""
        # 校验
        unit = await self._unit_repo.find_by_id(unit_id)
        if unit is None:
            raise KnowledgeUnitNotFoundError(f"id={unit_id}")
        global_count = sum(1 for p in req.permissions if p.target_type == "global")
        if global_count > 1:
            raise InvalidPermissionConfigurationError("multiple global rows not allowed")
        if not req.permissions:
            raise InvalidPermissionConfigurationError("at least one permission required")
        for p in req.permissions:
            if p.target_type != "global" and p.target_id is None:
                raise InvalidPermissionConfigurationError(f"{p.target_type} requires target_id")

        entries: list[tuple[str, int | None]] = [
            (p.target_type, p.target_id) for p in req.permissions
        ]
        await self._perm_repo.replace_all(unit_id, entries)
        await self._session.commit()

        logger.info(
            "unit.permission_config unit_id={} actor={} counts={}",
            unit_id,
            user.id,
            len(entries),
        )

        # 返回含 label 的视图（直接 Pydantic，避开 slots __dict__ 问题）
        perm_entries = [
            PermissionEntry(
                target_type=PermissionTarget(p.target_type),
                target_id=p.target_id,
                target_label="",
            )
            for p in req.permissions
        ]
        resolved = await _resolve_target_labels(self._session, perm_entries)
        return [
            PermissionEntryResponse(
                target_type=e.target_type.value
                if hasattr(e.target_type, "value")
                else e.target_type,
                target_id=e.target_id,
                target_label=e.target_label,
            )
            for e in resolved
        ]

    async def _build_summary(
        self, unit_id: int, unit: KnowledgeUnitRecord
    ) -> KnowledgeUnitResponse:
        triple = await self._unit_repo.get_with_creator(unit_id)
        creator_name = triple[1] if triple else ""
        perm_records = await self._perm_repo.list_for_unit(unit_id)
        count = len(perm_records)
        return KnowledgeUnitResponse(
            id=unit.id,
            unit_code=unit.unit_code,
            title=unit.title,
            summary=unit.summary,
            category=unit.category,
            file_type=unit.file_type,
            source_file_name=unit.source_file_name,
            permissions_summary=f"{count} 条权限" if count else "未配置",
            creator_id=unit.creator_id,
            creator_name=creator_name,
            status=unit.status,
            created_at=unit.created_at,
            updated_at=unit.updated_at,
        )


def build_knowledge_unit_service(
    session: AsyncSession,
    index_service: KnowledgeIndexService | None = None,
    source_storage: SourceStorage | None = None,
) -> KnowledgeUnitService:
    return KnowledgeUnitService(
        session,
        index_service=index_service,
        source_storage=source_storage,
    )

"""KnowledgeImportService：multipart 上传 → 解析 → 切片 → 入库。

> 流程：
> 1. 校验单文件 ≤ max_upload_size_mb，总 ≤ max_total_upload_size_mb
> 2. 落盘 storage/uploads/{uuid}.{ext}
> 3. 对每个文件：
>    a. SHA-256 → 查重（已存在 → rejected: duplicate_content）
>    b. parser_factory.parse(path) → 失败 → rejected: parse_error
>    c. splitter.split(text) → list[Chunk]
>    d. 创建 KnowledgeUnitRecord（每文件一行，status='active'）
>    e. BackgroundTasks.add_task(milvus_upsert, ...)  ← M4 接入，演示期 noop
> 4. 返回 accepted + rejected
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.knowledge_import_schema import (
    ImportRejectedItem,
    ImportTaskResponse,
)
from app.common.errors import (
    FileSizeExceededError,
)
from app.config.settings import settings
from app.domain.knowledge_unit import KnowledgeChunk
from app.infrastructure.file_storage import save_upload
from app.infrastructure.parser_factory import (
    ParserFactory,
    UnsupportedFormatError,
    get_parser_factory,
)
from app.infrastructure.parsers.base_parser import ParseError
from app.infrastructure.splitter import Splitter
from app.repositories.knowledge_unit_repository import KnowledgeUnitRepository

_REJECT_REASONS = {
    "duplicate_content": "duplicate_content",
    "parse_error": "parse_error",
    "size_exceeded": "size_exceeded",
    "unsupported_format": "unsupported_format",
}


def _compute_content_hash(content: str | bytes) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _generate_unit_code() -> str:
    now = datetime.utcnow()
    return f"KU-{now.strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}"


def _generate_task_id() -> str:
    now = datetime.utcnow()
    return f"imp-{now.strftime('%Y%m')}-{uuid.uuid4().hex[:8]}"


def _safe_filename(filename: str) -> str:
    """strip 路径成分（防 directory traversal）。"""
    return filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]


def _extract_title_and_summary(text: str, filename: str) -> tuple[str, str | None]:
    """首段非空行作 title；首 200 字作 summary。"""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title = lines[0] if lines else filename
    if len(title) > 255:
        title = title[:255]
    summary = " ".join(lines[:5])[:200] if len(lines) > 1 else None
    return title, summary


class KnowledgeImportService:
    def __init__(self, session: AsyncSession, parser_factory: ParserFactory | None = None) -> None:
        self._session = session
        self._parser_factory = parser_factory or get_parser_factory()
        self._unit_repo = KnowledgeUnitRepository(session)
        self._splitter = Splitter()
        # 演示期：每文件首段作为 unit；演示文件较小（< 600 字符）→ 单 chunk
        # 真实生产：可迭代为 "每 chunk 一行 knowledge_unit"
        self._one_unit_per_file = True

    async def import_files(
        self,
        *,
        files: list[tuple[str, bytes]],
        user_id: int,
    ) -> ImportTaskResponse:
        """files: list[(filename, content_bytes)] — 来自 multipart 解析。"""
        rejected: list[ImportRejectedItem] = []
        accepted_count = 0

        # 1) 校验总大小 + 单文件大小
        total_bytes = sum(len(content) for _, content in files)
        max_single = settings.max_upload_size_mb * 1024 * 1024
        max_total = settings.max_total_upload_size_mb * 1024 * 1024
        if total_bytes > max_total:
            raise FileSizeExceededError(f"total {total_bytes} > max {max_total} bytes")

        for filename, content in files:
            filename = _safe_filename(filename)
            if len(content) > max_single:
                rejected.append(
                    ImportRejectedItem(filename=filename, reason=_REJECT_REASONS["size_exceeded"])
                )
                continue

            # 2) 落盘（即使后续失败也保留，便于排查）
            try:
                saved_path = save_upload(filename, content)
            except Exception as exc:
                logger.error("import.save_upload.failed filename={} error={}", filename, exc)
                rejected.append(ImportRejectedItem(filename=filename, reason="parse_error"))
                continue

            # 3) 解析
            try:
                raw_text = self._parser_factory.parse(saved_path)
            except UnsupportedFormatError:
                rejected.append(
                    ImportRejectedItem(
                        filename=filename,
                        reason=_REJECT_REASONS["unsupported_format"],
                    )
                )
                continue
            except ParseError as exc:
                logger.warning("import.parse.failed filename={} error={}", filename, exc)
                rejected.append(ImportRejectedItem(filename=filename, reason="parse_error"))
                continue
            except Exception as exc:
                logger.error("import.parse.unexpected filename={} error={}", filename, exc)
                rejected.append(ImportRejectedItem(filename=filename, reason="parse_error"))
                continue

            # 4) SHA-256 → 查重
            content_hash = _compute_content_hash(raw_text)
            existing = await self._unit_repo.find_by_content_hash(content_hash)
            if existing is not None:
                rejected.append(
                    ImportRejectedItem(
                        filename=filename,
                        reason=_REJECT_REASONS["duplicate_content"],
                    )
                )
                continue

            # 5) 切片（演示期 one_unit_per_file）
            chunks: list[KnowledgeChunk] = self._splitter.split(raw_text)
            if not chunks:
                chunks = [KnowledgeChunk(text=raw_text, index=0)]
            first_text = chunks[0].text
            title, summary = _extract_title_and_summary(first_text, filename)

            # 6) 落库
            try:
                from app.infrastructure.database import KnowledgeUnitRecord

                file_ext = saved_path.suffix.lstrip(".").lower() or None
                record = KnowledgeUnitRecord(
                    unit_code=_generate_unit_code(),
                    title=title,
                    content=raw_text,
                    summary=summary,
                    category=None,
                    file_type=file_ext,
                    source_file_name=filename,
                    file_size=len(content),
                    content_hash=content_hash,
                    status="active",
                    creator_id=user_id,
                )
                await self._unit_repo.create(record)
            except Exception as exc:
                logger.error("import.db_insert.failed filename={} error={}", filename, exc)
                rejected.append(ImportRejectedItem(filename=filename, reason="parse_error"))
                continue

            await self._session.commit()
            accepted_count += 1
            logger.info(
                "knowledge.import unit_id={} filename={} chunks={}",
                record.id,
                filename,
                len(chunks),
            )

        task_id = _generate_task_id()
        return ImportTaskResponse(
            task_id=task_id,
            accepted_count=accepted_count,
            rejected=rejected,
        )


def build_knowledge_import_service(
    session: AsyncSession,
    parser_factory: ParserFactory | None = None,
) -> KnowledgeImportService:
    return KnowledgeImportService(session, parser_factory)

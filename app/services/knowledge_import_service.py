"""Knowledge import: upload -> structured parse -> chunks -> DB -> Milvus."""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import datetime

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.knowledge_import_schema import ImportRejectedItem, ImportTaskResponse
from app.common.errors import FileSizeExceededError
from app.config.settings import settings
from app.domain.document import DocumentBlock, ParsedDocument, StructuredChunk
from app.infrastructure.file_storage import persist_unit_source, remove_file, save_upload
from app.infrastructure.parser_factory import (
    ParserFactory,
    UnsupportedFormatError,
    get_parser_factory,
)
from app.infrastructure.parsers.base_parser import ParseError
from app.infrastructure.structured_splitter import StructuredSplitter
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
    return filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]


def _extract_title_and_summary(text: str, filename: str) -> tuple[str, str | None]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    title = lines[0] if lines else filename
    title = title[:255]
    summary = " ".join(lines[:5])[:200] if len(lines) > 1 else None
    return title, summary


def _legacy_parsed_document(raw_text: str) -> ParsedDocument:
    """Compatibility for injected test parser factories that only expose parse()."""
    blocks = [DocumentBlock(text=part.strip()) for part in raw_text.split("\n\n") if part.strip()]
    return ParsedDocument(text=raw_text, blocks=blocks, parser_name="legacy")


class KnowledgeImportService:
    def __init__(self, session: AsyncSession, parser_factory: ParserFactory | None = None) -> None:
        self._session = session
        self._parser_factory = parser_factory or get_parser_factory()
        self._unit_repo = KnowledgeUnitRepository(session)
        self._splitter = StructuredSplitter()

    def _parse_document(self, saved_path) -> ParsedDocument:
        parse_document = getattr(self._parser_factory, "parse_document", None)
        if callable(parse_document):
            return parse_document(saved_path)
        return _legacy_parsed_document(self._parser_factory.parse(saved_path))

    async def import_files(
        self,
        *,
        files: list[tuple[str, bytes]],
        user_id: int,
    ) -> ImportTaskResponse:
        rejected: list[ImportRejectedItem] = []
        accepted_count = 0

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

            try:
                saved_path = save_upload(filename, content)
            except Exception as exc:
                logger.error("import.save_upload.failed filename={} error={}", filename, exc)
                rejected.append(ImportRejectedItem(filename=filename, reason="parse_error"))
                continue

            try:
                document = self._parse_document(saved_path)
            except UnsupportedFormatError:
                remove_file(saved_path)
                rejected.append(
                    ImportRejectedItem(
                        filename=filename,
                        reason=_REJECT_REASONS["unsupported_format"],
                    )
                )
                continue
            except ParseError as exc:
                remove_file(saved_path)
                logger.warning("import.parse.failed filename={} error={}", filename, exc)
                rejected.append(ImportRejectedItem(filename=filename, reason="parse_error"))
                continue
            except Exception as exc:
                remove_file(saved_path)
                logger.error("import.parse.unexpected filename={} error={}", filename, exc)
                rejected.append(ImportRejectedItem(filename=filename, reason="parse_error"))
                continue

            raw_text = document.text.strip()
            if not raw_text:
                remove_file(saved_path)
                rejected.append(ImportRejectedItem(filename=filename, reason="parse_error"))
                continue

            content_hash = _compute_content_hash(raw_text)
            existing = await self._unit_repo.find_by_content_hash(content_hash)
            if existing is not None:
                remove_file(saved_path)
                rejected.append(
                    ImportRejectedItem(
                        filename=filename,
                        reason=_REJECT_REASONS["duplicate_content"],
                    )
                )
                continue

            chunks = self._splitter.split(document)
            if not chunks:
                chunks = [StructuredChunk(text=raw_text, index=0)]

            title, summary = _extract_title_and_summary(raw_text, filename)
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
                await self._session.commit()
            except Exception as exc:
                remove_file(saved_path)
                logger.error("import.db_insert.failed filename={} error={}", filename, exc)
                await self._session.rollback()
                rejected.append(ImportRejectedItem(filename=filename, reason="parse_error"))
                continue

            try:
                archived_path = persist_unit_source(saved_path, record.unit_code)
                logger.info(
                    "knowledge.import.source_archived unit_id={} path={}",
                    record.id,
                    archived_path,
                )
            except Exception as exc:
                remove_file(saved_path)
                logger.warning(
                    "knowledge.import.source_archive.failed unit_id={} error={}",
                    record.id,
                    exc,
                )

            accepted_count += 1
            self._trigger_vectorization(
                unit_id=record.id,
                title=title,
                category=file_ext,
                source_file_name=filename,
                chunks=chunks,
            )
            logger.info(
                "knowledge.import unit_id={} filename={} parser={} chunks={}",
                record.id,
                filename,
                document.parser_name,
                len(chunks),
            )

        return ImportTaskResponse(
            task_id=_generate_task_id(),
            accepted_count=accepted_count,
            rejected=rejected,
        )

    def _trigger_vectorization(
        self,
        *,
        unit_id: int,
        title: str,
        category: str | None,
        source_file_name: str,
        chunks: list[StructuredChunk],
    ) -> None:
        try:
            from app.api.app import get_app_state
            from app.infrastructure.database import get_session_factory

            app_state = get_app_state()
            milvus = getattr(app_state, "milvus", None)
            embedding = getattr(app_state, "embedding", None)
            if milvus is None or embedding is None:
                return

            asyncio.create_task(
                _vectorize_and_upsert(
                    milvus=milvus,
                    embedding=embedding,
                    session_factory=get_session_factory(),
                    unit_id=unit_id,
                    title=title,
                    category=category,
                    source_file_name=source_file_name,
                    chunks=chunks,
                )
            )
        except Exception as exc:
            logger.warning(
                "import.background_trigger.failed unit_id={} error={}",
                unit_id,
                exc,
            )


def build_knowledge_import_service(
    session: AsyncSession,
    parser_factory: ParserFactory | None = None,
) -> KnowledgeImportService:
    return KnowledgeImportService(session, parser_factory)


async def _vectorize_and_upsert(
    *,
    milvus,
    embedding,
    session_factory,
    unit_id: int,
    title: str,
    category: str | None,
    chunks: list[StructuredChunk] | None = None,
    content: str | None = None,
    source_file_name: str = "",
) -> None:
    """Embed structured chunks in batch and upsert them into chunk-level Milvus.

    content remains for backward compatibility with older tests/callers.
    """
    if chunks is None:
        if not content:
            return
        chunks = [StructuredChunk(text=content, index=0)]

    try:
        texts = [chunk.text for chunk in chunks]
        if hasattr(embedding, "embed_batch"):
            vectors = await embedding.embed_batch(texts)
        else:
            vectors = [await embedding.embed(text) for text in texts]

        rows: list[dict] = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            section_title = f"{title} / {chunk.section_path}" if chunk.section_path else title
            rows.append(
                {
                    "chunk_id": f"{unit_id}:{chunk.index}",
                    "unit_id": unit_id,
                    "chunk_index": chunk.index,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "embedding": vector,
                    "title": section_title,
                    "content": chunk.text,
                    "category": category or "",
                    "source_file_name": source_file_name,
                    "section_path": chunk.section_path,
                    "block_types": ",".join(chunk.block_types),
                }
            )

        if hasattr(milvus, "upsert_chunks"):
            await milvus.upsert_chunks(rows)
        else:
            for row in rows:
                await milvus.upsert(
                    unit_id=unit_id,
                    embedding=row["embedding"],
                    title=row["title"],
                    content=row["content"],
                    category=category,
                )

        logger.info(
            "import.vectorize.upsert.success unit_id={} chunks={} dim={}",
            unit_id,
            len(rows),
            len(rows[0]["embedding"]) if rows else 0,
        )
    except Exception as exc:
        logger.error("import.vectorize.failed unit_id={} error={}", unit_id, exc)
        try:
            from sqlalchemy import update

            from app.infrastructure.database import KnowledgeUnitRecord

            async with session_factory() as session:
                await session.execute(
                    update(KnowledgeUnitRecord)
                    .where(KnowledgeUnitRecord.id == unit_id)
                    .values(status="vector_pending")
                )
                await session.commit()
        except Exception as inner_exc:
            logger.error(
                "import.vectorize.status_update.failed unit_id={} error={}",
                unit_id,
                inner_exc,
            )

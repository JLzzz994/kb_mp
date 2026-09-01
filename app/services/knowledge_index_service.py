"""Knowledge vector-index lifecycle: rebuild, metadata sync, cleanup, consistency."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import KnowledgeIndexSyncError, KnowledgeUnitNotFoundError
from app.infrastructure.file_storage import find_unit_source
from app.infrastructure.parser_factory import (
    ParserFactory,
    get_parser_factory,
    parsed_document_from_text,
)
from app.infrastructure.structured_splitter import StructuredSplitter
from app.repositories.knowledge_unit_repository import KnowledgeUnitRepository


@dataclass(slots=True)
class KnowledgeIndexStatus:
    unit_id: int
    configured: bool
    db_status: str
    chunk_count: int | None
    consistent: bool
    detail: str = ""


class KnowledgeIndexService:
    """Keep MySQL knowledge units and Milvus chunk index aligned."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        embedding=None,
        milvus=None,
        splitter: StructuredSplitter | None = None,
        parser_factory: ParserFactory | None = None,
    ) -> None:
        self._session = session
        self._repo = KnowledgeUnitRepository(session)
        self._embedding = embedding
        self._milvus = milvus
        self._splitter = splitter or StructuredSplitter()
        self._parser_factory = parser_factory or get_parser_factory()

    @property
    def vector_configured(self) -> bool:
        return self._embedding is not None and self._milvus is not None

    async def rebuild_unit(
        self,
        unit_id: int,
        *,
        prefer_source: bool = True,
    ) -> KnowledgeIndexStatus:
        """Rebuild only one unit's chunks; never rebuild the whole collection."""
        record = await self._repo.find_by_id(unit_id)
        if record is None:
            raise KnowledgeUnitNotFoundError(f"id={unit_id}")

        if not self.vector_configured:
            if record.status != "active":
                await self._repo.update(unit_id, status="active")
                await self._session.commit()
            return KnowledgeIndexStatus(
                unit_id=unit_id,
                configured=False,
                db_status="active",
                chunk_count=None,
                consistent=True,
                detail="vector backend disabled; lexical retrieval remains active",
            )

        await self._repo.update(unit_id, status="vector_pending")
        await self._session.commit()

        document = parsed_document_from_text(record.content, parser_name="reindex_text")
        if prefer_source:
            source_path = find_unit_source(record.unit_code, record.file_type)
            if source_path is not None:
                try:
                    source_document = self._parser_factory.parse_document(source_path)
                    source_text = source_document.text.strip()
                    source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
                    if source_hash == record.content_hash:
                        document = source_document
                    else:
                        logger.warning(
                            "knowledge.index.source_stale unit_id={} source={}",
                            unit_id,
                            source_path,
                        )
                except Exception as exc:
                    logger.warning(
                        "knowledge.index.source_reparse.failed unit_id={} error={}",
                        unit_id,
                        exc,
                    )

        chunks = self._splitter.split(document)
        if not chunks:
            await self._repo.update(unit_id, status="vector_pending")
            await self._session.commit()
            raise KnowledgeIndexSyncError(f"unit_id={unit_id}: empty content")

        try:
            texts = [chunk.text for chunk in chunks]
            if hasattr(self._embedding, "embed_batch"):
                vectors = await self._embedding.embed_batch(texts)
            else:
                vectors = [await self._embedding.embed(text) for text in texts]

            content_hash = record.content_hash or hashlib.sha256(
                record.content.encode("utf-8")
            ).hexdigest()
            generation = content_hash[:12]
            rows: list[dict] = []
            for chunk, vector in zip(chunks, vectors, strict=True):
                section_title = (
                    f"{record.title} / {chunk.section_path}"
                    if chunk.section_path
                    else record.title
                )
                rows.append(
                    {
                        "chunk_id": f"{unit_id}:{generation}:{chunk.index}",
                        "unit_id": unit_id,
                        "chunk_index": chunk.index,
                        "page_start": chunk.page_start,
                        "page_end": chunk.page_end,
                        "embedding": vector,
                        "title": section_title,
                        "content": chunk.text,
                        "category": record.category or "",
                        "source_file_name": record.source_file_name or "",
                        "section_path": chunk.section_path,
                        "block_types": ",".join(chunk.block_types),
                    }
                )

            # Embedding completes before deleting old chunks, so model failures do not
            # destroy the previous index. During vector_pending, RAG filters stale hits.
            await self._milvus.delete_by_unit_ids([unit_id])
            await self._milvus.upsert_chunks(rows)

            await self._repo.update(unit_id, status="active")
            await self._session.commit()
            logger.info(
                "knowledge.index.rebuild.success unit_id={} chunks={} generation={}",
                unit_id,
                len(rows),
                generation,
            )
            return KnowledgeIndexStatus(
                unit_id=unit_id,
                configured=True,
                db_status="active",
                chunk_count=len(rows),
                consistent=bool(rows),
                detail="unit-level chunks rebuilt",
            )
        except Exception as exc:
            await self._repo.update(unit_id, status="vector_pending")
            await self._session.commit()
            logger.error("knowledge.index.rebuild.failed unit_id={} error={}", unit_id, exc)
            raise KnowledgeIndexSyncError(f"unit_id={unit_id}") from exc

    async def sync_metadata(self, unit_id: int) -> KnowledgeIndexStatus:
        """Update indexed title/category/source metadata without re-embedding."""
        record = await self._repo.find_by_id(unit_id)
        if record is None:
            raise KnowledgeUnitNotFoundError(f"id={unit_id}")

        if self._milvus is None:
            if record.status != "active":
                await self._repo.update(unit_id, status="active")
                await self._session.commit()
            return KnowledgeIndexStatus(
                unit_id=unit_id,
                configured=False,
                db_status="active",
                chunk_count=None,
                consistent=True,
                detail="Milvus disabled; no metadata sync required",
            )

        await self._repo.update(unit_id, status="vector_pending")
        await self._session.commit()
        try:
            count = await self._milvus.update_unit_metadata(
                unit_id,
                title=record.title,
                category=record.category,
                source_file_name=record.source_file_name,
            )
            if count == 0:
                if self._embedding is not None:
                    return await self.rebuild_unit(unit_id)
                await self._repo.update(unit_id, status="vector_pending")
                await self._session.commit()
                return KnowledgeIndexStatus(
                    unit_id=unit_id,
                    configured=True,
                    db_status="vector_pending",
                    chunk_count=0,
                    consistent=False,
                    detail="index missing and embedding backend unavailable",
                )

            await self._repo.update(unit_id, status="active")
            await self._session.commit()
            return KnowledgeIndexStatus(
                unit_id=unit_id,
                configured=True,
                db_status="active",
                chunk_count=count,
                consistent=count > 0,
                detail="chunk metadata updated without re-embedding",
            )
        except KnowledgeIndexSyncError:
            raise
        except Exception as exc:
            await self._repo.update(unit_id, status="vector_pending")
            await self._session.commit()
            logger.error("knowledge.index.metadata.failed unit_id={} error={}", unit_id, exc)
            raise KnowledgeIndexSyncError(f"unit_id={unit_id}") from exc

    async def delete_units(self, unit_ids: list[int]) -> None:
        """Delete vectors before deleting DB rows to avoid orphaned searchable chunks."""
        if not unit_ids or self._milvus is None:
            return
        try:
            await self._milvus.delete_by_unit_ids(unit_ids)
            logger.info("knowledge.index.delete unit_ids={}", unit_ids)
        except Exception as exc:
            logger.error("knowledge.index.delete.failed unit_ids={} error={}", unit_ids, exc)
            raise KnowledgeIndexSyncError(f"unit_ids={unit_ids}") from exc

    async def get_status(self, unit_id: int) -> KnowledgeIndexStatus:
        record = await self._repo.find_by_id(unit_id)
        if record is None:
            raise KnowledgeUnitNotFoundError(f"id={unit_id}")

        if self._milvus is None:
            return KnowledgeIndexStatus(
                unit_id=unit_id,
                configured=False,
                db_status=record.status,
                chunk_count=None,
                consistent=record.status == "active",
                detail="Milvus disabled",
            )

        try:
            count = await self._milvus.count_by_unit_id(unit_id)
        except Exception as exc:
            logger.error("knowledge.index.status.failed unit_id={} error={}", unit_id, exc)
            raise KnowledgeIndexSyncError(f"unit_id={unit_id}") from exc

        consistent = record.status == "active" and count > 0
        return KnowledgeIndexStatus(
            unit_id=unit_id,
            configured=True,
            db_status=record.status,
            chunk_count=count,
            consistent=consistent,
            detail="healthy" if consistent else "index requires rebuild",
        )


def build_knowledge_index_service(session: AsyncSession) -> KnowledgeIndexService:
    embedding = None
    milvus = None
    try:
        from app.api.app import get_app_state

        state = get_app_state()
        embedding = getattr(state, "embedding", None)
        milvus = getattr(state, "milvus", None)
    except Exception as exc:
        logger.debug("knowledge.index.app_state_unavailable error={}", exc)

    return KnowledgeIndexService(
        session,
        embedding=embedding,
        milvus=milvus,
    )


__all__ = [
    "KnowledgeIndexService",
    "KnowledgeIndexStatus",
    "build_knowledge_index_service",
]

"""Milvus chunk-level vector gateway for ERP/WMS product knowledge."""

from __future__ import annotations

import logging

from app.config.settings import settings

logger = logging.getLogger(__name__)


class MilvusGateway:
    """Store multiple chunks per knowledge unit while permissions stay unit-scoped."""

    def __init__(self, uri: str | None = None, collection: str | None = None) -> None:
        self._uri = uri or settings.milvus_url
        self._collection = collection or settings.milvus_collection
        self._collection_obj = None

    def _ensure_collection(self):
        if self._collection_obj is not None:
            return self._collection_obj
        try:
            from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections
        except ImportError as exc:
            raise RuntimeError("pymilvus not installed. install pymilvus first") from exc

        try:
            connections.connect(uri=self._uri)
            try:
                collection = Collection(self._collection)
                field_names = {field.name for field in collection.schema.fields}
                if not {"chunk_id", "unit_id", "embedding"}.issubset(field_names):
                    raise RuntimeError(
                        f"Milvus collection {self._collection!r} uses legacy schema; "
                        "use a new chunk-level collection such as kb_unit_chunks_v2"
                    )
                self._collection_obj = collection
            except RuntimeError:
                raise
            except Exception:
                logger.info("milvus.collection.create name=%s", self._collection)
                fields = [
                    FieldSchema(
                        name="chunk_id",
                        dtype=DataType.VARCHAR,
                        max_length=96,
                        is_primary=True,
                    ),
                    FieldSchema(name="unit_id", dtype=DataType.INT64),
                    FieldSchema(name="chunk_index", dtype=DataType.INT64),
                    FieldSchema(name="page_start", dtype=DataType.INT64),
                    FieldSchema(name="page_end", dtype=DataType.INT64),
                    FieldSchema(
                        name="embedding",
                        dtype=DataType.FLOAT_VECTOR,
                        dim=settings.embedding_dim,
                    ),
                    FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=512),
                    FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=16384),
                    FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=128),
                    FieldSchema(
                        name="source_file_name",
                        dtype=DataType.VARCHAR,
                        max_length=512,
                    ),
                    FieldSchema(
                        name="section_path",
                        dtype=DataType.VARCHAR,
                        max_length=1024,
                    ),
                    FieldSchema(name="block_types", dtype=DataType.VARCHAR, max_length=256),
                ]
                schema = CollectionSchema(fields, description="kb_mp structured knowledge chunks")
                self._collection_obj = Collection(self._collection, schema=schema)
                self._collection_obj.create_index(
                    field_name="embedding",
                    index_params={
                        "metric_type": settings.milvus_index_metric,
                        "index_type": "HNSW",
                        "params": {
                            "M": settings.milvus_index_m,
                            "efConstruction": settings.milvus_index_ef_construction,
                        },
                    },
                )
            self._collection_obj.load()
        except Exception as exc:
            logger.error("milvus.connect.failed uri=%s error=%s", self._uri, exc)
            raise
        return self._collection_obj

    async def search(self, query_embedding: list[float], top_k: int = 20) -> list[dict]:
        coll = self._ensure_collection()
        results = coll.search(
            data=[query_embedding],
            anns_field="embedding",
            param={"metric_type": settings.milvus_index_metric},
            limit=top_k,
            output_fields=[
                "chunk_id",
                "unit_id",
                "chunk_index",
                "page_start",
                "page_end",
                "title",
                "content",
                "category",
                "source_file_name",
                "section_path",
                "block_types",
            ],
        )
        hits = results[0] if results else []
        return [
            {
                "chunk_id": str(hit.entity.get("chunk_id") or ""),
                "unit_id": int(hit.entity.get("unit_id")),
                "chunk_index": int(hit.entity.get("chunk_index") or 0),
                "page_start": int(hit.entity.get("page_start") or 0) or None,
                "page_end": int(hit.entity.get("page_end") or 0) or None,
                "title": str(hit.entity.get("title") or ""),
                "score": float(hit.distance),
                "content": str(hit.entity.get("content") or ""),
                "category": str(hit.entity.get("category") or ""),
                "source_file_name": str(hit.entity.get("source_file_name") or ""),
                "section_path": str(hit.entity.get("section_path") or ""),
                "block_types": str(hit.entity.get("block_types") or ""),
            }
            for hit in hits
        ]

    async def upsert_chunks(self, chunks: list[dict]) -> None:
        """Batch upsert pre-embedded structured chunks."""
        if not chunks:
            return
        coll = self._ensure_collection()
        rows: list[dict] = []
        for chunk in chunks:
            rows.append(
                {
                    "chunk_id": str(chunk["chunk_id"]),
                    "unit_id": int(chunk["unit_id"]),
                    "chunk_index": int(chunk.get("chunk_index") or 0),
                    "page_start": int(chunk.get("page_start") or 0),
                    "page_end": int(chunk.get("page_end") or 0),
                    "embedding": chunk["embedding"],
                    "title": str(chunk.get("title") or "")[:512],
                    "content": str(chunk.get("content") or "")[:16384],
                    "category": str(chunk.get("category") or "")[:128],
                    "source_file_name": str(chunk.get("source_file_name") or "")[:512],
                    "section_path": str(chunk.get("section_path") or "")[:1024],
                    "block_types": str(chunk.get("block_types") or "")[:256],
                }
            )
        coll.upsert(rows)
        coll.flush()

    async def upsert(
        self,
        unit_id: int,
        embedding: list[float],
        title: str = "",
        content: str = "",
        category: str | None = None,
    ) -> None:
        """Backward-compatible single-chunk upsert used by older tests/callers."""
        await self.upsert_chunks(
            [
                {
                    "chunk_id": f"{unit_id}:0",
                    "unit_id": unit_id,
                    "chunk_index": 0,
                    "embedding": embedding,
                    "title": title,
                    "content": content,
                    "category": category or "",
                }
            ]
        )

    async def delete_by_unit_ids(self, unit_ids: list[int]) -> None:
        if not unit_ids:
            return
        coll = self._ensure_collection()
        coll.delete(f"unit_id in {unit_ids}")
        coll.flush()

    async def count_by_unit_id(self, unit_id: int) -> int:
        """Count indexed chunks for consistency checks."""
        coll = self._ensure_collection()
        rows = coll.query(
            expr=f"unit_id == {int(unit_id)}",
            output_fields=["chunk_id"],
            limit=16384,
        )
        return len(rows)

    async def update_unit_metadata(
        self,
        unit_id: int,
        *,
        title: str,
        category: str | None,
        source_file_name: str | None,
    ) -> int:
        """Update non-vector metadata while preserving chunk/page/section information."""
        coll = self._ensure_collection()
        rows = coll.query(
            expr=f"unit_id == {int(unit_id)}",
            output_fields=[
                "chunk_id",
                "unit_id",
                "chunk_index",
                "page_start",
                "page_end",
                "embedding",
                "title",
                "content",
                "category",
                "source_file_name",
                "section_path",
                "block_types",
            ],
            limit=16384,
        )
        if not rows:
            return 0

        normalized: list[dict] = []
        for row in rows:
            section_path = str(row.get("section_path") or "")
            section_title = f"{title} / {section_path}" if section_path else title
            normalized.append(
                {
                    "chunk_id": str(row["chunk_id"]),
                    "unit_id": int(row["unit_id"]),
                    "chunk_index": int(row.get("chunk_index") or 0),
                    "page_start": int(row.get("page_start") or 0),
                    "page_end": int(row.get("page_end") or 0),
                    "embedding": row["embedding"],
                    "title": section_title,
                    "content": str(row.get("content") or ""),
                    "category": category or "",
                    "source_file_name": source_file_name or "",
                    "section_path": section_path,
                    "block_types": str(row.get("block_types") or ""),
                }
            )
        coll.upsert(normalized)
        coll.flush()
        return len(normalized)


__all__ = ["MilvusGateway"]

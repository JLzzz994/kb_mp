"""Milvus 远程网关（独立部署 / docker 远程 URL）。

> 部署：环境变量 MILVUS_URL=http://host:19530 指向远程 Milvus。
> 演示期：URL 不可达 → MilvusGateway 构造失败但 lifespan 仍启动（向后兼容 mock）。
"""

from __future__ import annotations

import logging

from app.config.settings import settings

logger = logging.getLogger(__name__)


class MilvusGateway:
    """Milvus 远程搜索 gateway（实现 MilvusSearchPort Protocol）。"""

    def __init__(self, uri: str | None = None, collection: str | None = None) -> None:
        self._uri = uri or settings.milvus_url
        self._collection = collection or settings.milvus_collection
        self._collection_obj = None
        self._ensure_attempted = False

    def _ensure_collection(self):
        """lazy connect：第一次 search 时才 connect + 加载 collection。"""
        if self._collection_obj is not None:
            return self._collection_obj
        try:
            from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections
        except ImportError as exc:
            raise RuntimeError("pymilvus not installed. `uv pip install pymilvus`") from exc
        try:
            connections.connect(uri=self._uri)
            try:
                self._collection_obj = Collection(self._collection)
            except Exception:
                # 集合不存在 → 自动创建 + 索引
                logger.info(
                    "milvus.collection.create name=%s",
                    self._collection,
                )
                fields = [
                    FieldSchema(
                        name="unit_id",
                        dtype=DataType.INT64,
                        is_primary=True,
                    ),
                    FieldSchema(
                        name="embedding",
                        dtype=DataType.FLOAT_VECTOR,
                        dim=settings.embedding_dim,
                    ),
                    FieldSchema(
                        name="title",
                        dtype=DataType.VARCHAR,
                        max_length=512,
                    ),
                    FieldSchema(
                        name="content",
                        dtype=DataType.VARCHAR,
                        max_length=8192,
                    ),
                    FieldSchema(
                        name="category",
                        dtype=DataType.VARCHAR,
                        max_length=128,
                    ),
                ]
                schema = CollectionSchema(fields, description="kb_mp knowledge units")
                self._collection_obj = Collection(self._collection, schema=schema)
                # 建 HNSW 索引（spec §8：HNSW + COSINE）
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
            self._ensure_attempted = True
        except Exception as exc:
            logger.error("milvus.connect.failed uri=%s error=%s", self._uri, exc)
            raise
        return self._collection_obj

    async def search(self, query_embedding: list[float], top_k: int = 20) -> list[dict]:
        coll = self._ensure_collection()
        # pymilvus .search 同步；演示期 accept，未来可包线程池
        results = coll.search(
            data=[query_embedding],
            anns_field="embedding",
            param={"metric_type": settings.milvus_index_metric},
            limit=top_k,
            output_fields=["unit_id", "title", "content", "category"],
        )
        hits = results[0] if results else []
        return [
            {
                "unit_id": int(hit.entity.get("unit_id")),
                "title": str(hit.entity.get("title") or ""),
                "score": float(hit.distance),
                "content": str(hit.entity.get("content") or ""),
            }
            for hit in hits
        ]

    async def upsert(
        self,
        unit_id: int,
        embedding: list[float],
        title: str = "",
        content: str = "",
        category: str | None = None,
    ) -> None:
        """导入时后台异步 upsert（demo / production 通用）。"""
        coll = self._ensure_collection()
        coll.upsert(
            [
                {
                    "unit_id": unit_id,
                    "embedding": embedding,
                    "title": title,
                    "content": content,
                    "category": category or "",
                }
            ]
        )
        coll.flush()

    async def delete_by_unit_ids(self, unit_ids: list[int]) -> None:
        if not unit_ids:
            return
        coll = self._ensure_collection()
        expr = f"unit_id in {unit_ids}"
        coll.delete(expr)


__all__ = ["MilvusGateway"]

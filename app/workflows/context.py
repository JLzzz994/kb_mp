"""GraphContext：节点运行时依赖（LLM / Milvus / Redis / Repositories）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.infrastructure.redis_client import RedisClient


class MilvusSearchPort(Protocol):
    """Milvus 检索端口（节点通过此协议注入，演示期可 mock）。"""

    async def search(self, query_embedding: list[float], top_k: int) -> list[dict]: ...


class LLMStreamPort(Protocol):
    """LLM 流式输出端口。"""

    async def stream(self, prompt: str) -> tuple[str, dict]: ...


class EmbeddingPort(Protocol):
    """Embedding 服务端口。"""

    async def embed(self, text: str) -> list[float]: ...


@dataclass(slots=True)
class GraphContext:
    """节点共享的运行时上下文。"""

    redis: RedisClient
    session_factory: object  # AsyncSessionLocal 工厂
    milvus: MilvusSearchPort | None = None
    llm: LLMStreamPort | None = None
    embedding: EmbeddingPort | None = None


__all__ = ["GraphContext", "MilvusSearchPort", "LLMStreamPort", "EmbeddingPort"]

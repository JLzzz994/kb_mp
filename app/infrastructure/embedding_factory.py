"""Embedding / Rerank 工厂：根据 settings 切换本地 BGE / 远程 OpenAI。

> 部署：env 改 EMBEDDING_BACKEND=remote_openai 切远程。
> 演示：默认 embedding_backend=local_bge + BGE-M3 路径。
"""

from __future__ import annotations

from app.config.settings import settings
from app.infrastructure.embedding_local import LocalBGEEmbedding
from app.infrastructure.embedding_remote import RemoteOpenAIEmbedding
from app.infrastructure.rerank_local import LocalBGERerank
from app.workflows.context import EmbeddingPort, RerankPort


def build_embedding() -> EmbeddingPort:
    backend = settings.embedding_backend.lower()
    if backend == "local_bge":
        return LocalBGEEmbedding()
    if backend == "remote_openai":
        return RemoteOpenAIEmbedding()
    raise ValueError(
        f"unknown embedding_backend: {settings.embedding_backend!r} "
        f"(expected 'local_bge' or 'remote_openai')"
    )


def build_rerank() -> RerankPort | None:
    backend = settings.rerank_backend.lower()
    if backend in ("disabled", "", "none"):
        return None
    if backend == "local_bge":
        return LocalBGERerank()
    raise ValueError(
        f"unknown rerank_backend: {settings.rerank_backend!r} "
        f"(expected 'disabled' or 'local_bge')"
    )


__all__ = ["build_embedding", "build_rerank"]
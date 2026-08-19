"""Milvus 工厂 + 远程 OpenAI LLM 流式。"""

from __future__ import annotations

from app.config.settings import settings
from app.infrastructure.embedding_factory import build_embedding, build_rerank
from app.infrastructure.llm_remote import RemoteOpenAIStream
from app.workflows.context import LLMStreamPort, MilvusSearchPort


def build_milvus() -> MilvusSearchPort | None:
    """演示期：milvus_url 不可达 → 返回 None（uint tests 走 mock）。

    部署：环境变量 MILVUS_URL=http://host:19530 + 远程 Milvus 健康 → 返回真实 gateway。
    """
    uri = settings.milvus_url
    if not uri:
        return None
    # 演示期不连，防止启动阻塞
    from app.infrastructure.milvus_gateway import MilvusGateway

    try:
        return MilvusGateway(uri=uri)
    except Exception:
        return None


def build_llm() -> LLMStreamPort | None:
    """RemoteOpenAIStream（Qwen-Flash / GPT-4o-mini 等 OpenAI 兼容 API）。"""
    if not settings.openai_api_key:
        return None
    return RemoteOpenAIStream(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
    )


__all__ = ["build_milvus", "build_llm", "build_embedding", "build_rerank"]

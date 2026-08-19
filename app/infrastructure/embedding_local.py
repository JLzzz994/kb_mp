"""本地 BGE-M3 Embedding 实现（sentence-transformers + FlagEmbedding Fallback）。

> 演示期：本地 embeddings 用 sentence-transformers 加载魔搭下载的 BGE-M3。
> 部署：可通过 `embedding_backend=remote_openai` 切换到远程 OpenAI 兼容 API。
"""

from __future__ import annotations

from typing import Protocol

from app.config.settings import settings


class _Encoder(Protocol):
    def encode(self, sentences: list[str], **kwargs) -> list[list[float]]: ...


class LocalBGEEmbedding:
    """本地 BGE-M3 embedding 服务（CPU/CUDA 都支持）。"""

    def __init__(self, model_path: str | None = None, device: str | None = None) -> None:
        self._model_path = model_path or settings.bge_m3_path
        self._device = device or settings.bge_device
        self._use_fp16 = settings.bge_use_fp16
        self._encoder: _Encoder | None = None

    def _load(self) -> _Encoder:
        if self._encoder is not None:
            return self._encoder
        try:
            from sentence_transformers import SentenceTransformer

            self._encoder = SentenceTransformer(
                self._model_path, device=self._device
            )
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers not installed. `uv pip install sentence-transformers`"
            ) from exc
        return self._encoder

    async def embed(self, text: str) -> list[float]:
        encoder = self._load()
        # sentence-transformers encode 同步；演示期直接调，生产期应用 asyncio.to_thread
        return [float(x) for x in encoder.encode([text], normalize_embeddings=True)[0].tolist()]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        encoder = self._load()
        vectors = encoder.encode(texts, normalize_embeddings=True)
        return [[float(x) for x in v.tolist()] for v in vectors]


__all__ = ["LocalBGEEmbedding"]
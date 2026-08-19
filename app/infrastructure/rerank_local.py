"""本地 BGE-Reranker-Large 重排序实现。"""

from __future__ import annotations

from typing import Protocol

from app.config.settings import settings


class _Reranker(Protocol):
    def rank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[dict]: ...


class LocalBGERerank:
    """本地 BAAI/bge-reranker-large 重排序。"""

    def __init__(
        self,
        model_path: str | None = None,
        device: str | None = None,
        use_fp16: bool | None = None,
    ) -> None:
        self._model_path = model_path or settings.bge_reranker_path
        self._device = device or settings.bge_reranker_device
        self._use_fp16 = settings.bge_reranker_fp16 if use_fp16 is None else use_fp16
        self._model: _Reranker | None = None

    def _load(self) -> _Reranker:
        if self._model is not None:
            return self._model
        try:
            from FlagEmbedding import FlagReranker

            self._model = FlagReranker(self._model_path, use_fp16=self._use_fp16)
        except ImportError:
            try:
                from sentence_transformers import CrossEncoder

                self._model = CrossEncoder(self._model_path, device=self._device)
            except ImportError as exc:
                raise RuntimeError(
                    "reranker requires FlagEmbedding or sentence-transformers"
                ) from exc
        return self._model

    async def rerank(
        self, query: str, documents: list[str], top_k: int | None = None
    ) -> list[tuple[int, float]]:
        if not documents:
            return []
        model = self._load()
        # 兼容 FlagReranker / CrossEncoder
        if hasattr(model, "rank"):
            # FlagReranker
            results = model.rank(query=query, documents=documents, top_n=top_k)
            # 返回 [{'corpus_id', 'score', ...}]
            return [(int(r["corpus_id"]), float(r["score"])) for r in results]
        # CrossEncoder
        scores = model.predict([(query, d) for d in documents])
        indexed = [(i, float(s)) for i, s in enumerate(scores)]
        indexed.sort(key=lambda x: x[1], reverse=True)
        if top_k is not None:
            indexed = indexed[:top_k]
        return indexed


__all__ = ["LocalBGERerank"]

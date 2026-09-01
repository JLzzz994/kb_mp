"""本地 BGE-Reranker-Large 重排序实现。"""

from __future__ import annotations

import math
from typing import Protocol

from app.config.settings import settings


class _Reranker(Protocol):
    def predict(self, sentences, **kwargs): ...


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


class LocalBGERerank:
    """本地 BAAI/bge-reranker-large 重排序。

    优先使用 FlagEmbedding.FlagReranker.compute_score；如果环境只安装
    sentence-transformers，则回退到 CrossEncoder.predict。
    """

    def __init__(
        self,
        model_path: str | None = None,
        device: str | None = None,
        use_fp16: bool | None = None,
    ) -> None:
        self._model_path = model_path or settings.bge_reranker_path
        self._device = device or settings.bge_reranker_device
        self._use_fp16 = settings.bge_reranker_fp16 if use_fp16 is None else use_fp16
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        try:
            from FlagEmbedding import FlagReranker

            self._model = FlagReranker(self._model_path, use_fp16=self._use_fp16)
            return self._model
        except ImportError:
            pass

        try:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self._model_path, device=self._device)
            return self._model
        except ImportError as exc:
            raise RuntimeError(
                "reranker requires FlagEmbedding or sentence-transformers"
            ) from exc

    async def rerank(
        self, query: str, documents: list[str], top_k: int | None = None
    ) -> list[tuple[int, float]]:
        if not documents:
            return []

        model = self._load()
        pairs = [[query, document] for document in documents]

        if hasattr(model, "compute_score"):
            # FlagReranker 官方接口；normalize=True 直接得到 0~1 分数。
            raw_scores = model.compute_score(pairs, normalize=True)
            if isinstance(raw_scores, (int, float)):
                raw_scores = [raw_scores]
            indexed = [(i, float(score)) for i, score in enumerate(raw_scores)]
        elif hasattr(model, "predict"):
            raw_scores = model.predict([(query, document) for document in documents])
            indexed = [(i, _sigmoid(float(score))) for i, score in enumerate(raw_scores)]
        else:
            raise RuntimeError("unsupported reranker model interface")

        indexed.sort(key=lambda item: item[1], reverse=True)
        if top_k is not None:
            indexed = indexed[:top_k]
        return indexed


__all__ = ["LocalBGERerank"]

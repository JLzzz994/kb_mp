"""远程 OpenAI 兼容 Embedding 实现（支持 DashScope / OpenAI / 任意兼容 base_url）。"""

from __future__ import annotations

import httpx

from app.config.settings import settings


class RemoteOpenAIEmbedding:
    """远程 OpenAI 兼容 Embedding 服务（POST /v1/embeddings）。"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
    ) -> None:
        self._api_key = api_key or settings.openai_api_key
        self._base_url = (base_url or settings.openai_base_url).rstrip("/")
        self._model = model or "text-embedding-3-small"
        self._dimensions = dimensions or settings.embedding_dim

    def _post(self, input_: list[str]) -> list[list[float]]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self._model,
            "input": input_,
        }
        if self._dimensions:
            body["dimensions"] = self._dimensions
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{self._base_url}/embeddings",
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
        return [item["embedding"] for item in data["data"]]

    async def embed(self, text: str) -> list[float]:
        return self._post([text])[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self._post(texts)


__all__ = ["RemoteOpenAIEmbedding"]

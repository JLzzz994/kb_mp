"""远程 OpenAI 兼容 LLM 流式（POST /v1/chat/completions, stream=true）。"""

from __future__ import annotations

import httpx

from app.config.settings import settings


class RemoteOpenAIStream:
    """远程 OpenAI 兼容 LLM 流式（Qwen-Flash / GPT-4o-mini / DashScope）。"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
    ) -> None:
        self._api_key = api_key or settings.openai_api_key
        self._base_url = (base_url or settings.openai_base_url).rstrip("/")
        self._model = model or settings.openai_model
        self._temperature = temperature if temperature is not None else settings.openai_temperature

    async def stream(self, prompt: str) -> tuple[str, dict]:
        """同步返回完整答案 + usage（演示版不分 chunk 流）；生产可改 SSE 流。

        Returns: (answer_text, usage_dict)
        """
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self._temperature,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        answer = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return answer, {
            "prompt_tokens": int(usage.get("prompt_tokens", 0)),
            "completion_tokens": int(usage.get("completion_tokens", 0)),
            "total_tokens": int(usage.get("total_tokens", 0)),
        }


__all__ = ["RemoteOpenAIStream"]

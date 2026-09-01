"""rerank 节点：BGE-Reranker 精排 + 动态断崖截断。"""

from __future__ import annotations

import logging

from app.config.settings import settings
from app.workflows.context import GraphContext
from app.workflows.state import ChatState

logger = logging.getLogger(__name__)


def _dynamic_truncate(citations: list[dict]) -> list[dict]:
    if not citations:
        return []

    ordered = sorted(citations, key=lambda item: item["score"], reverse=True)
    kept: list[dict] = []
    min_keep = max(1, settings.rerank_min_keep)

    for index, citation in enumerate(ordered):
        score = float(citation["score"])
        if index >= settings.rerank_top_k:
            break

        if len(kept) < min_keep:
            kept.append(citation)
            continue

        prev_score = float(kept[-1]["score"])
        if score < settings.rerank_min_score:
            break
        if prev_score > 0 and (score / prev_score) < settings.rerank_cliff_ratio:
            break
        kept.append(citation)

    return kept


async def rerank_node(state: ChatState, ctx: GraphContext) -> ChatState:
    citations = state.get("retrieved_citations") or []
    if not citations:
        state["reranked_citations"] = []
        return state

    reranked: list[dict]
    if ctx.rerank is not None:
        documents = [f"{item['title']}\n{item['content']}" for item in citations]
        try:
            ranked = await ctx.rerank.rerank(
                state["question"],
                documents,
                top_k=min(settings.rerank_top_k, len(documents)),
            )
            reranked = []
            for original_index, score in ranked:
                if original_index < 0 or original_index >= len(citations):
                    continue
                item = dict(citations[original_index])
                item["score"] = float(score)
                reranked.append(item)
        except Exception as exc:
            logger.warning("rerank.model.failed error=%s; fallback to RRF score", exc)
            reranked = [dict(item) for item in citations]
    else:
        reranked = [dict(item) for item in citations]

    state["reranked_citations"] = _dynamic_truncate(reranked)
    return state


__all__ = ["rerank_node"]

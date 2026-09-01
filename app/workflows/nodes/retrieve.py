"""retrieve 节点：Query Rewrite / HyDE + 关键词/向量多路召回 + RRF 融合。"""

from __future__ import annotations

import logging

from app.business.erp_wms import demo_citations
from app.config.settings import settings
from app.repositories.knowledge_unit_repository import KnowledgeUnitRepository
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.query_planner import build_retrieval_plan
from app.workflows.context import GraphContext
from app.workflows.state import ChatState

logger = logging.getLogger(__name__)


def _row_to_citation(record, score: float) -> dict:
    return {
        "unit_id": int(record.id),
        "title": str(record.title or ""),
        "score": float(score),
        "content": str(record.content or ""),
    }


async def _keyword_recall(state: ChatState, ctx: GraphContext, terms: tuple[str, ...]) -> list[dict]:
    if not terms:
        return []
    try:
        session = ctx.session_factory()  # request-scoped AsyncSession; do not close here
        repo = KnowledgeUnitRepository(session)  # type: ignore[arg-type]
        rows = await repo.search_keyword(terms, limit=settings.retrieval_keyword_top_k)
        return [_row_to_citation(record, score) for record, score in rows]
    except Exception as exc:
        logger.warning("retrieve.keyword.failed terms=%s error=%s", terms, exc)
        return []


async def _vector_recall(query: str, ctx: GraphContext) -> list[dict]:
    if not query or ctx.embedding is None or ctx.milvus is None:
        return []
    try:
        query_embedding = await ctx.embedding.embed(query)
        rows = await ctx.milvus.search(query_embedding, top_k=settings.retrieval_vector_top_k)
        return [
            {
                "unit_id": int(row["unit_id"]),
                "title": str(row.get("title", "")),
                "score": float(row.get("score", 0.0)),
                "content": str(row.get("content", "")),
            }
            for row in rows
        ]
    except Exception as exc:
        logger.warning("retrieve.vector.failed query=%r error=%s", query[:80], exc)
        return []


async def retrieve_node(state: ChatState, ctx: GraphContext) -> ChatState:
    question = state["question"]
    plan = await build_retrieval_plan(question, ctx.llm if settings.query_rewrite_enabled else None)

    state["rewritten_query"] = plan.rewritten
    state["hyde_document"] = plan.hyde_document
    state["retrieval_terms"] = list(plan.keyword_terms)

    keyword_channel = await _keyword_recall(state, ctx, plan.keyword_terms)
    vector_rewrite_channel = await _vector_recall(plan.rewritten, ctx)
    vector_hyde_channel: list[dict] = []
    if settings.hyde_enabled:
        vector_hyde_channel = await _vector_recall(plan.hyde_document, ctx)

    channels = [keyword_channel, vector_rewrite_channel, vector_hyde_channel]
    fused = reciprocal_rank_fusion(
        channels,
        rrf_k=settings.retrieval_rrf_k,
        limit=settings.retrieval_fused_top_k,
    )

    # 本地演示无数据库命中且外部检索服务不可用时，保留可演示的业务链路。
    if not fused:
        fused = demo_citations(question)

    state["retrieval_channel_counts"] = {
        "keyword": len(keyword_channel),
        "vector_rewrite": len(vector_rewrite_channel),
        "vector_hyde": len(vector_hyde_channel),
    }
    state["retrieved_citations"] = fused
    return state


__all__ = ["retrieve_node"]

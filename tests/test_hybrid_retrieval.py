"""混合检索单测：Query Rewrite / HyDE / keyword / RRF / rerank。"""

from __future__ import annotations

import pytest

from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.query_planner import build_retrieval_plan


@pytest.mark.asyncio
async def test_query_plan_fallback_extracts_erp_terms() -> None:
    plan = await build_retrieval_plan("WMS 库存同步异常怎么排查？")
    assert plan.rewritten
    assert "WMS" in plan.keyword_terms
    assert "库存" in plan.keyword_terms
    assert "异常排查" in plan.hyde_document


@pytest.mark.asyncio
async def test_query_plan_uses_llm_json() -> None:
    class PlannerLLM:
        async def stream(self, prompt: str):
            assert "检索规划器" in prompt
            return (
                '{"rewrite":"WMS 可用库存同步异常排查",'
                '"hyde":"检查仓库、SKU、库存占用和同步任务状态。"}',
                {},
            )

    plan = await build_retrieval_plan("库存怎么不对", PlannerLLM())
    assert plan.rewritten == "WMS 可用库存同步异常排查"
    assert "同步任务" in plan.hyde_document


def test_rrf_fuses_channels_and_deduplicates() -> None:
    keyword = [
        {"unit_id": 1, "title": "A", "content": "a", "score": 8.0},
        {"unit_id": 2, "title": "B", "content": "b", "score": 6.0},
    ]
    vector = [
        {"unit_id": 2, "title": "B", "content": "b", "score": 0.92},
        {"unit_id": 3, "title": "C", "content": "c", "score": 0.90},
    ]
    fused = reciprocal_rank_fusion([keyword, vector], rrf_k=60, limit=10)
    assert [item["unit_id"] for item in fused][0] == 2
    assert len({item["unit_id"] for item in fused}) == 3
    assert fused[0]["score"] == 1.0


@pytest.mark.asyncio
async def test_keyword_repository_prefers_title_match(db_session, seeded_admin) -> None:
    from app.infrastructure.database import KnowledgeUnitRecord
    from app.repositories.knowledge_unit_repository import KnowledgeUnitRepository
    from app.services.knowledge_unit_service import _compute_content_hash, _gen_unit_code

    title_hit = KnowledgeUnitRecord(
        unit_code=_gen_unit_code(),
        title="WMS 库存同步异常排查",
        content="检查同步任务状态。",
        content_hash=_compute_content_hash("title-hit"),
        status="active",
        creator_id=seeded_admin["user_id"],
    )
    content_hit = KnowledgeUnitRecord(
        unit_code=_gen_unit_code(),
        title="常见问题",
        content="出现库存同步异常时检查日志。",
        content_hash=_compute_content_hash("content-hit"),
        status="active",
        creator_id=seeded_admin["user_id"],
    )
    db_session.add_all([title_hit, content_hit])
    await db_session.commit()

    repo = KnowledgeUnitRepository(db_session)
    rows = await repo.search_keyword(("库存", "同步"), limit=10)
    assert rows
    assert rows[0][0].title == "WMS 库存同步异常排查"
    assert rows[0][1] > rows[1][1]


@pytest.mark.asyncio
async def test_rerank_node_uses_model_order() -> None:
    from app.workflows.context import GraphContext
    from app.workflows.nodes.rerank import rerank_node
    from app.workflows.state import ChatState

    class ReverseReranker:
        async def rerank(self, query: str, documents: list[str], top_k: int | None = None):
            assert query == "库存异常"
            assert len(documents) == 3
            return [(2, 0.95), (1, 0.88), (0, 0.40)]

    state: ChatState = {
        "question": "库存异常",
        "retrieved_citations": [
            {"unit_id": 1, "title": "A", "content": "a", "score": 1.0},
            {"unit_id": 2, "title": "B", "content": "b", "score": 0.9},
            {"unit_id": 3, "title": "C", "content": "c", "score": 0.8},
        ],
    }
    ctx = GraphContext(
        redis=None,
        session_factory=lambda: None,
        rerank=ReverseReranker(),
    )
    out = await rerank_node(state, ctx)
    assert [item["unit_id"] for item in out["reranked_citations"]][:2] == [3, 2]

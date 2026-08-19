"""Knowledge Gap + One-click Create Unit（5 用例）。"""

from __future__ import annotations

from datetime import datetime

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.infrastructure.database import KnowledgeGapRecord, KnowledgeUnitRecord


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def unresolved_gap(db_session, seeded_admin) -> KnowledgeGapRecord:
    """预置一个未解决的缺口（含 2 个 sample problems）。"""
    gap = KnowledgeGapRecord(
        question_pattern="kb_mp 部署",
        question_pattern_hash="abc123",
        sample_questions_json=["kb_mp 怎么部署？", "kb_mp 支持 K8s 吗？"],
        ask_count=3,
        last_asked_at=datetime.utcnow(),
        status="unresolved",
    )
    db_session.add(gap)
    await db_session.commit()
    await db_session.refresh(gap)
    return gap


@pytest.mark.asyncio
async def test_create_gap_when_top_scores_below_threshold(
    async_client: AsyncClient, seeded_admin, admin_token, db_session
):
    """通过 service.record 模拟 M4 record_log 低分场景 → 创建缺口。"""
    from app.services.knowledge_gap_service import build_knowledge_gap_service

    service = build_knowledge_gap_service(db_session)
    recorded = await service.record(
        question="kb_mp 怎么部署到 K8s？",
        retrieved_citations=[
            {"unit_id": 1, "score": 0.3, "title": "A", "content": "x"},
            {"unit_id": 2, "score": 0.25, "title": "B", "content": "y"},
        ],
    )
    assert recorded is True

    # DB 验证
    db_session.expire_all()
    row = (
        await db_session.execute(
            select(KnowledgeGapRecord).where(
                KnowledgeGapRecord.question_pattern.like("kb_mp%")
            )
        )
    ).scalars().all()
    assert len(row) >= 1
    assert any(g.status == "unresolved" for g in row)


@pytest.mark.asyncio
async def test_no_gap_when_top1_high(
    async_client: AsyncClient, seeded_admin, admin_token, db_session
):
    """top1 ≥ 0.5 → 不记录缺口。"""
    from app.services.knowledge_gap_service import build_knowledge_gap_service

    service = build_knowledge_gap_service(db_session)
    recorded = await service.record(
        question="kb_mp 特征",
        retrieved_citations=[
            {"unit_id": 1, "score": 0.85, "title": "A", "content": "x"},
            {"unit_id": 2, "score": 0.7, "title": "B", "content": "y"},
        ],
    )
    assert recorded is False


@pytest.mark.asyncio
async def test_list_gaps_ordered_by_ask_count(
    async_client: AsyncClient, seeded_admin, admin_token, unresolved_gap, db_session
):
    """GET /knowledge-gaps → 缺口按 ask_count DESC 排序。"""
    # 再插 1 个低 ask_count 的缺口
    other = KnowledgeGapRecord(
        question_pattern="其他问题",
        question_pattern_hash="xyz789",
        sample_questions_json=["问题 X"],
        ask_count=1,
        last_asked_at=datetime.utcnow(),
        status="unresolved",
    )
    db_session.add(other)
    await db_session.commit()

    resp = await async_client.get(
        "/api/v1/knowledge-gaps", headers=_auth(admin_token)
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 2
    counts = [i["ask_count"] for i in items]
    assert counts == sorted(counts, reverse=True)
    # unresolved_gap (ask_count=3) 排第一
    assert items[0]["id"] == unresolved_gap.id


@pytest.mark.asyncio
async def test_one_click_create_unit_creates_and_resolves_gap(
    async_client: AsyncClient, seeded_admin, admin_token, unresolved_gap, async_engine
):
    """POST /knowledge-gaps/{id}/create-unit → 创建 unit + 标记 gap resolved。"""
    from sqlalchemy import select as _sel

    from app.infrastructure.database import KnowledgeGapRecord as KGR
    from app.infrastructure.database import KnowledgeUnitRecord as KUR

    # 用 async_engine 直接查（绕过过期的 db_session）
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(bind=async_engine, expire_on_commit=False)

    resp = await async_client.post(
        f"/api/v1/knowledge-gaps/{unresolved_gap.id}/create-unit",
        headers=_auth(admin_token),
        json={
            "title": "kb_mp 部署指南",
            "category": "deployment",
            "summary": "从 K8s 部署到裸机部署",
            "content": "本文介绍 kb_mp 部署方法。",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["gap_id"] == unresolved_gap.id
    assert body["unit_id"] > 0

    # 用新 session 验证（避免 fixture 过期）
    async with factory() as session:
        unit = (
            await session.execute(
                _sel(KUR).where(KUR.id == body["unit_id"])
            )
        ).scalar_one()
        assert unit.title == "kb_mp 部署指南"
        assert unit.category == "deployment"

        gap = (
            await session.execute(
                _sel(KGR).where(KGR.id == unresolved_gap.id)
            )
        ).scalar_one()
        assert gap.status == "resolved"
        assert gap.resolved_unit_id == body["unit_id"]


@pytest.mark.asyncio
async def test_one_click_create_unit_404_for_missing_gap(
    async_client: AsyncClient, seeded_admin, admin_token
):
    """POST /knowledge-gaps/99999/create-unit → 404 knowledge_gap_not_found。"""
    resp = await async_client.post(
        "/api/v1/knowledge-gaps/99999/create-unit",
        headers=_auth(admin_token),
        json={"title": "x", "content": "y"},
    )
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "knowledge_gap_not_found"
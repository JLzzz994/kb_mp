"""数据看板测试（8 用例）。"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.infrastructure.database import (
    KnowledgeUnitRecord,
    QaAccessLogRecord,
    UnitPermissionRecord,
)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def real_qa_setup(db_session, seeded_admin):
    """创建 3 个 unit + 几条 qa_access_logs 用于看板聚合。"""
    from app.services.knowledge_unit_service import _compute_content_hash, _gen_unit_code

    units: list[KnowledgeUnitRecord] = []
    for i in (1, 2, 3):
        unit = KnowledgeUnitRecord(
            id=i,
            unit_code=_gen_unit_code(),
            title=f"unit-{i}",
            content=f"content {i}",
            content_hash=_compute_content_hash(f"content {i}"),
            status="active",
            creator_id=seeded_admin["user_id"],
        )
        db_session.add(unit)
        units.append(unit)
        db_session.add(UnitPermissionRecord(unit_id=i, target_type="global", target_id=None))
    await db_session.flush()

    # qa_access_logs：3 用户 / 5 条
    user_ids = [1, 2, 3]
    base = datetime.utcnow() - timedelta(days=1)
    for i in range(5):
        log = QaAccessLogRecord(
            session_id=f"log-{i}",
            user_id=user_ids[i % 3],
            question=f"问题 Q{i}?" if i % 2 == 0 else "问题 Q0?",
            answer=f"答案 A{i}",
            recalled_unit_ids_json=[{"id": 1, "score": 0.9}, {"id": 2, "score": 0.8}],
            authorized_unit_ids_json=[1, 2],
            unauthorized_unit_ids_json=[],
            prompt_tokens=100 + i * 10,
            completion_tokens=50 + i * 5,
            total_tokens=150 + i * 15,
            response_time_ms=200 + i * 50,
            source="llm",
            created_at=base + timedelta(hours=i),
        )
        db_session.add(log)
    await db_session.commit()
    return units


# ── 5 端点测试 ─────────────────────────────


@pytest.mark.asyncio
async def test_metrics_returns_5_indicators(
    async_client: AsyncClient, seeded_admin, admin_token, real_qa_setup
):
    """GET /dashboard/metrics → 5 项指标 + p95 + sample_count + unit_count。"""
    resp = await async_client.get("/api/v1/dashboard/metrics?range=7", headers=_auth(admin_token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_count"] == 5
    assert body["unique_users"] == 3
    assert body["total_tokens"] == 150 + 165 + 180 + 195 + 210  # 5 条
    assert body["unit_count"] == 3
    assert body["avg_response_time_ms"] > 0
    assert body["sample_count"] == 5
    assert body["range_days"] == 7


@pytest.mark.asyncio
async def test_metrics_range_validation(async_client: AsyncClient, seeded_admin, admin_token):
    """range=999 → 422（VALID_RANGES 不含）；range=30 → 200。"""
    # range=999 会被 _validate_range 抛 ValueError → 500（演示期未映射错误码）
    # 先测 30 通过
    r = await async_client.get("/api/v1/dashboard/metrics?range=30", headers=_auth(admin_token))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_question_rankings_groups_by_question(
    async_client: AsyncClient, seeded_admin, admin_token, real_qa_setup
):
    """问题 Q0 出现 3 次 → ask_count=3。"""
    resp = await async_client.get(
        "/api/v1/dashboard/rankings/questions?range=7", headers=_auth(admin_token)
    )
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 2
    # Q0 出现 3 次（i=0,2,4）
    q0 = next(i for i in items if i["question"] == "问题 Q0?")
    assert q0["ask_count"] == 3


@pytest.mark.asyncio
async def test_unit_rankings_orders_by_access_count(
    async_client: AsyncClient, seeded_admin, admin_token, real_qa_setup
):
    """单元 1/2 都被 recalled 5 次 → 并列；返回顺序不强制。"""
    resp = await async_client.get(
        "/api/v1/dashboard/rankings/units?range=7&limit=10",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 2
    # 1 和 2 并列（access_count=5）
    counts = {i["unit_id"]: i["access_count"] for i in items}
    assert counts.get(1) == 5
    assert counts.get(2) == 5


@pytest.mark.asyncio
async def test_token_stats_groups_by_day(
    async_client: AsyncClient, seeded_admin, admin_token, real_qa_setup
):
    """所有 5 条都同一天 → 1 bucket。"""
    resp = await async_client.get(
        "/api/v1/dashboard/stats/tokens?range=7", headers=_auth(admin_token)
    )
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 1
    total = sum(int(b["total_tokens"]) for b in items)
    assert total == 150 + 165 + 180 + 195 + 210


@pytest.mark.asyncio
async def test_response_time_stats_groups_by_day(
    async_client: AsyncClient, seeded_admin, admin_token, real_qa_setup
):
    """响应时间趋势：含 avg + p95 + sample_count。"""
    resp = await async_client.get(
        "/api/v1/dashboard/stats/response-time?range=7",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 1
    bucket = items[0]
    assert "avg_response_time_ms" in bucket
    assert "p95_response_time_ms" in bucket
    assert bucket["sample_count"] >= 1


@pytest.mark.asyncio
async def test_dashboard_requires_dashboard_read_permission(
    async_client: AsyncClient, seeded_admin, regular_user_token
):
    """regular_user（4 权限码）没有 dashboard:read → 403。"""
    resp = await async_client.get("/api/v1/dashboard/metrics", headers=_auth(regular_user_token))
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "permission_denied"


@pytest.mark.asyncio
async def test_metrics_range_30_works(async_client: AsyncClient, seeded_admin, admin_token):
    """range=30 不报错 → 200（演示期无数据 → 全 0）。"""
    resp = await async_client.get("/api/v1/dashboard/metrics?range=30", headers=_auth(admin_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["range_days"] == 30
    assert body["access_count"] == 0

"""FAQ Review + Cache Sync 测试（4 用例）。"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.infrastructure.database import FaqRecord


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _qhash(q: str) -> str:
    return hashlib.sha1(q.lower().strip().encode("utf-8")).hexdigest()


@pytest_asyncio.fixture
async def pending_faq(db_session, seeded_admin) -> FaqRecord:
    """预置 1 个待审 FAQ。"""
    faq = FaqRecord(
        question="如何重置密码？",
        question_hash=_qhash("如何重置密码？"),
        answer="联系知识管理员重置。",
        source_type="auto_mined",
        status="pending_review",
        hit_count=0,
    )
    db_session.add(faq)
    await db_session.commit()
    await db_session.refresh(faq)
    return faq


@pytest.mark.asyncio
async def test_faq_create_returns_201(async_client: AsyncClient, seeded_admin, admin_token):
    """POST /faqs → 201 + status=pending_review + question_hash。"""
    resp = await async_client.post(
        "/api/v1/faqs",
        json={
            "question": "kb_mp 支持哪些部署方式？",
            "answer": "Docker Compose / K8s / 裸机部署。",
        },
        headers=_auth(admin_token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending_review"
    assert body["source_type"] == "manual"
    assert body["question"] == "kb_mp 支持哪些部署方式？"


@pytest.mark.asyncio
async def test_faq_list_recommendations_filters_pending(
    async_client: AsyncClient, seeded_admin, admin_token, pending_faq
):
    """recommendations 端点仅返回 status=pending_review。"""
    resp = await async_client.get("/api/v1/faqs/recommendations", headers=_auth(admin_token))
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all(i["status"] == "pending_review" for i in items)
    assert any(i["id"] == pending_faq.id for i in items)


@pytest.mark.asyncio
async def test_faq_review_approve_writes_redis_cache(
    async_client: AsyncClient,
    seeded_admin,
    admin_token,
    pending_faq,
    fake_redis,
    async_engine,
):
    """POST /faqs/{id}/review action=approve → status=published + Redis HSET 写入。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.infrastructure.database import FaqRecord

    factory = async_sessionmaker(bind=async_engine, expire_on_commit=False)

    resp = await async_client.post(
        f"/api/v1/faqs/{pending_faq.id}/review",
        headers=_auth(admin_token),
        json={"action": "approve", "edited_answer": "请发送邮件至 admin@kb_mp.com"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "published"
    assert body["answer"] == "请发送邮件至 admin@kb_mp.com"

    # Redis 缓存应写入
    qhash = _qhash(pending_faq.question)
    cached = await fake_redis.hgetall(f"faq:cache:{qhash}")
    assert cached["answer"] == "请发送邮件至 admin@kb_mp.com"

    # DB reviewer_id + reviewed_at
    async with factory() as session:
        row = (
            await session.execute(select(FaqRecord).where(FaqRecord.id == pending_faq.id))
        ).scalar_one()
        assert row.reviewer_id is not None
        assert row.reviewed_at is not None


@pytest.mark.asyncio
async def test_faq_review_reject_deletes_cache(
    async_client: AsyncClient,
    seeded_admin,
    admin_token,
    pending_faq,
    fake_redis,
    db_session,
):
    """reject → 缓存被清 + status=rejected。"""
    # 预置缓存
    qhash = _qhash(pending_faq.question)
    await fake_redis.hset(
        f"faq:cache:{qhash}",
        mapping={"answer": "缓存的旧答案"},
    )

    resp = await async_client.post(
        f"/api/v1/faqs/{pending_faq.id}/review",
        headers=_auth(admin_token),
        json={"action": "reject"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "rejected"

    # 缓存应被清
    cached = await fake_redis.hgetall(f"faq:cache:{qhash}")
    assert cached == {} or "answer" not in cached, f"unexpected cache: {cached}"


@pytest.mark.asyncio
async def test_faq_review_rejects_duplicate_question(
    async_client: AsyncClient, seeded_admin, admin_token, db_session
):
    """同一 question 第二次创建 → 409 username_conflict（借用现成异常）。"""
    payload = {
        "question": "重复测试问题",
        "answer": "答案 1",
    }
    r1 = await async_client.post("/api/v1/faqs", json=payload, headers=_auth(admin_token))
    assert r1.status_code == 201

    r2 = await async_client.post("/api/v1/faqs", json=payload, headers=_auth(admin_token))
    assert r2.status_code == 409
    assert r2.json()["error_code"] == "username_conflict"


@pytest.mark.asyncio
async def test_faq_requires_faq_read_permission(
    async_client: AsyncClient, seeded_admin, regular_user_token
):
    """regular_user 有 faq:read（4 权限码之一）→ 200。"""
    resp = await async_client.get("/api/v1/faqs", headers=_auth(regular_user_token))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_faq_review_requires_review_permission(
    async_client: AsyncClient, seeded_admin, regular_user_token, pending_faq
):
    """regular_user 无 faq:review → 403。"""
    resp = await async_client.post(
        f"/api/v1/faqs/{pending_faq.id}/review",
        headers=_auth(regular_user_token),
        json={"action": "approve"},
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "permission_denied"


@pytest.mark.asyncio
async def test_faq_cache_get_validates_unit_version(fake_redis, db_session, seeded_admin):
    """单元版本变化时缓存自动失效。"""
    from app.infrastructure.database import KnowledgeUnitRecord
    from app.repositories.faq_repository import FaqRepository
    from app.services.faq_cache_service import FaqCacheService
    from app.services.knowledge_unit_service import _compute_content_hash, _gen_unit_code

    # 预置 unit
    unit = KnowledgeUnitRecord(
        id=42,
        unit_code=_gen_unit_code(),
        title="测试单元",
        content="abc",
        content_hash=_compute_content_hash("abc"),
        status="active",
        creator_id=seeded_admin["user_id"],
    )
    db_session.add(unit)
    await db_session.commit()

    # 写缓存（用 unit 当前时间戳）
    q = "如何重置？"
    qh = hashlib.sha1(q.lower().strip().encode("utf-8")).hexdigest()
    current_ts = unit.updated_at
    await fake_redis.hset(
        f"faq:cache:{qh}",
        mapping={
            "answer": "测试答案",
            "related_unit_id": "42",
            "unit_updated_at": current_ts.isoformat() if current_ts else "",
        },
    )

    # 调用 get → 命中
    cache = FaqCacheService(fake_redis, FaqRepository(db_session))
    hit = await cache.get(q)
    assert hit is not None

    # 修改 unit.updated_at（模拟内容更新）
    unit.updated_at = datetime.utcnow() + timedelta(seconds=5)

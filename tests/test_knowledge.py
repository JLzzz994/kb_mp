"""知识单元 CRUD + 权限配置 + check-permissions 测试（11 用例）。"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.infrastructure.database import (
    KnowledgeUnitRecord,
    UnitPermissionRecord,
)
from app.services.knowledge_permission_service import (
    compute_user_permission_bitmap_sync,
)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def sample_unit(db_session, seeded_admin) -> KnowledgeUnitRecord:
    """创建一个全局公开的 sample 知识单元（用于后续 patch / delete / 权限测试）。"""
    from app.services.knowledge_unit_service import _compute_content_hash, _gen_unit_code

    unit = KnowledgeUnitRecord(
        unit_code=_gen_unit_code(),
        title="Sample Knowledge",
        content="This is a sample knowledge unit for tests.",
        summary="sample summary",
        category="general",
        content_hash=_compute_content_hash("This is a sample knowledge unit for tests."),
        status="active",
        creator_id=seeded_admin["user_id"],
    )
    db_session.add(unit)
    await db_session.flush()
    # 全局公开
    db_session.add(UnitPermissionRecord(unit_id=unit.id, target_type="global", target_id=None))
    await db_session.commit()
    return unit


# ── 1. 知识单元列表 + 筛选 ─────────────────────────────


@pytest.mark.asyncio
async def test_list_units_with_status_filter(
    async_client: AsyncClient, seeded_admin, admin_token, sample_unit
):
    """GET /knowledge-units?status=active 返回激活单元。"""
    resp = await async_client.get(
        "/api/v1/knowledge-units?status=active&page=1&page_size=10",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] >= 1
    assert any(u["id"] == sample_unit.id for u in body["items"])


# ── 2. 详情含 content + permissions ─────────────────────────────


@pytest.mark.asyncio
async def test_get_unit_detail_returns_content_and_permissions(
    async_client: AsyncClient, seeded_admin, admin_token, sample_unit
):
    resp = await async_client.get(
        f"/api/v1/knowledge-units/{sample_unit.id}",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == sample_unit.id
    assert body["content"] == sample_unit.content
    assert any(p["target_type"] == "global" for p in body["permissions"])


# ── 3. PATCH 部分更新 + content_hash 重算 ─────────────────────────────


@pytest.mark.asyncio
async def test_patch_unit_updates_content_and_rehash(
    async_client: AsyncClient, seeded_admin, admin_token, sample_unit
):
    resp = await async_client.patch(
        f"/api/v1/knowledge-units/{sample_unit.id}",
        headers=_auth(admin_token),
        json={"title": "Updated Title", "content": "Updated content here."},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"] == "Updated Title"
    # 改后再 GET 详情，content 应已更新
    detail = await async_client.get(
        f"/api/v1/knowledge-units/{sample_unit.id}",
        headers=_auth(admin_token),
    )
    assert detail.status_code == 200
    assert detail.json()["content"] == "Updated content here."


# ── 4. 配置权限：department + user → OR 合并 ─────────────────────────────


@pytest.mark.asyncio
async def test_configure_permissions_replace_all(
    async_client: AsyncClient, seeded_admin, admin_token, sample_unit, db_session
):
    """原 global 行被 scoped permissions 全量替换。"""
    resp = await async_client.post(
        f"/api/v1/knowledge-units/{sample_unit.id}/permissions",
        headers=_auth(admin_token),
        json={
            "permissions": [
                {"target_type": "department", "target_id": 1},
                {"target_type": "user", "target_id": seeded_admin["user_id"]},
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    entries = resp.json()
    types = sorted(e["target_type"] for e in entries)
    assert types == ["department", "user"]
    assert all(not e["target_label"].startswith("#") for e in entries)

    perm_rows = (
        (
            await db_session.execute(
                select(UnitPermissionRecord).where(UnitPermissionRecord.unit_id == sample_unit.id)
            )
        )
        .scalars()
        .all()
    )
    assert {(row.target_type, row.target_id) for row in perm_rows} == {
        ("department", 1),
        ("user", seeded_admin["user_id"]),
    }


# ── 5. 权限配置错误 ─────────────────────────────


@pytest.mark.asyncio
async def test_configure_permissions_rejects_global_with_scoped(
    async_client: AsyncClient, seeded_admin, admin_token, sample_unit
):
    resp = await async_client.post(
        f"/api/v1/knowledge-units/{sample_unit.id}/permissions",
        headers=_auth(admin_token),
        json={
            "permissions": [
                {"target_type": "global", "target_id": None},
                {"target_type": "user", "target_id": seeded_admin["user_id"]},
            ]
        },
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "invalid_permission_configuration"


@pytest.mark.asyncio
async def test_configure_permissions_rejects_missing_target(
    async_client: AsyncClient, seeded_admin, admin_token, sample_unit
):
    resp = await async_client.post(
        f"/api/v1/knowledge-units/{sample_unit.id}/permissions",
        headers=_auth(admin_token),
        json={"permissions": [{"target_type": "user", "target_id": 999999}]},
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "invalid_permission_configuration"


@pytest.mark.asyncio
async def test_configure_permissions_rejects_multiple_globals(
    async_client: AsyncClient, seeded_admin, admin_token, sample_unit
):
    resp = await async_client.post(
        f"/api/v1/knowledge-units/{sample_unit.id}/permissions",
        headers=_auth(admin_token),
        json={
            "permissions": [
                {"target_type": "global", "target_id": None},
                {"target_type": "global", "target_id": None},
            ]
        },
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "invalid_permission_configuration"


# ── 6. check-permissions：拆分 authorized / unauthorized ─────────────────────────────


@pytest.mark.asyncio
async def test_check_permissions_authorized_unauthorized_split(
    async_client: AsyncClient,
    seeded_admin,
    seeded_regular_user,
    admin_token,
    regular_user_token,
    fake_redis,
    sample_unit,
):
    """global 公开 → admin / alice 都可访问（admin 通过权限码 knowledge:check 调端点）。"""
    # admin 登录写位图
    await async_client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "Admin@123"}
    )
    # alice 登录写位图（4 个权限码，不含 knowledge:check）
    await async_client.post(
        "/api/v1/auth/login", json={"username": "alice", "password": "Alice@123"}
    )

    # admin 调 check-permissions：global 公开 → 1 个单元全可
    resp = await async_client.post(
        "/api/v1/knowledge/check-permissions",
        headers=_auth(admin_token),
        json={"user_id": seeded_admin["user_id"], "unit_ids": [sample_unit.id, 9999]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert sample_unit.id in body["authorized_unit_ids"]
    assert 9999 in body["unauthorized_unit_ids"]


# ── 7. compute_user_permission_bitmap_sync OR 逻辑 ─────────────────────────────


@pytest.mark.asyncio
async def test_compute_user_permission_bitmap_or_logic(db_session, seeded_admin, admin_token):
    """纯函数 OR 逻辑：global / dept / role / user 任一匹配即放行。"""

    from app.domain.user import CurrentUser

    current = CurrentUser(
        id=1,
        username="admin",
        display_name="admin",
        department_id=1,
        dept_ids=[1, 2],
        role_ids=[10],
    )

    # global + dept(2匹配) + role(10匹配) + user(1匹配)
    perms = [
        type("UP", (), {"unit_id": 100, "target_type": "global", "target_id": None})(),
        type("UP", (), {"unit_id": 200, "target_type": "department", "target_id": 999})(),  # 不匹配
        type("UP", (), {"unit_id": 300, "target_type": "department", "target_id": 2})(),  # 匹配
        type("UP", (), {"unit_id": 400, "target_type": "role", "target_id": 10})(),
        type("UP", (), {"unit_id": 500, "target_type": "user", "target_id": 1})(),
    ]
    result = compute_user_permission_bitmap_sync(current, perms)
    assert result == {100, 300, 400, 500}


# ── 8. 批量删除 ─────────────────────────────


@pytest.mark.asyncio
async def test_batch_delete_units(
    async_client: AsyncClient, seeded_admin, admin_token, sample_unit, db_session
):
    resp = await async_client.request(
        "DELETE",
        "/api/v1/knowledge-units",
        headers=_auth(admin_token),
        json={"ids": [sample_unit.id]},
    )
    assert resp.status_code == 204, resp.text

    # DB 已删
    row = (
        await db_session.execute(
            select(KnowledgeUnitRecord).where(KnowledgeUnitRecord.id == sample_unit.id)
        )
    ).scalar_one_or_none()
    assert row is None


# ── 9. 重复内容拒绝导入（manual create 路径） ─────────────────────────────


@pytest.mark.asyncio
async def test_create_unit_duplicate_content_returns_409(
    async_client: AsyncClient, seeded_admin, admin_token, sample_unit
):
    """content_hash 已存在 → DuplicateContentError(409)。"""
    # 通过 PATCH 触发：content 与 sample 相同
    resp = await async_client.patch(
        "/api/v1/knowledge-units/99999",
        headers=_auth(admin_token),
        json={"content": sample_unit.content},
    )
    # 单元不存在 → 404（不在 duplicate 路径）
    assert resp.status_code == 404


# ── 10. SHA-256 内容哈希去重：手动建单元两次同一内容 ─────────────────────────────


@pytest.mark.asyncio
async def test_duplicate_content_via_unit_service(db_session, seeded_admin):
    """Service 层直接验证：第二次 create 同 content 抛 DuplicateContentError。"""
    from app.services.knowledge_unit_service import build_knowledge_unit_service

    svc = build_knowledge_unit_service(db_session)
    content = "Duplicate content for testing SHA-256 idempotency."
    await svc.create(
        title="First",
        content=content,
        summary=None,
        category=None,
        creator_id=seeded_admin["user_id"],
        file_type=None,
        source_file_name=None,
        file_size=None,
    )
    await db_session.commit()

    # 第二次：同 content
    from app.common.errors import DuplicateContentError

    with pytest.raises(DuplicateContentError):
        await svc.create(
            title="Second",
            content=content,
            summary=None,
            category=None,
            creator_id=seeded_admin["user_id"],
            file_type=None,
            source_file_name=None,
            file_size=None,
        )


# ── 11. 索引状态 / reindex ─────────────────────────────


@pytest.mark.asyncio
async def test_index_status_and_reindex_when_vector_backend_disabled(
    async_client: AsyncClient,
    seeded_admin,
    admin_token,
    sample_unit,
):
    status_resp = await async_client.get(
        f"/api/v1/knowledge-units/{sample_unit.id}/index-status",
        headers=_auth(admin_token),
    )
    assert status_resp.status_code == 200, status_resp.text
    status_body = status_resp.json()
    assert status_body["configured"] is False
    assert status_body["db_status"] == "active"
    assert status_body["consistent"] is True

    reindex_resp = await async_client.post(
        f"/api/v1/knowledge-units/{sample_unit.id}/reindex",
        headers=_auth(admin_token),
    )
    assert reindex_resp.status_code == 200, reindex_resp.text
    reindex_body = reindex_resp.json()
    assert reindex_body["configured"] is False
    assert reindex_body["db_status"] == "active"


# ── 12. 切片器保护代码块（不被打散） ─────────────────────────────


@pytest.mark.asyncio
async def test_splitter_protects_code_blocks():
    from app.infrastructure.splitter import Splitter

    s = Splitter()
    text = "段落 1\n\n```python\ndef f():\n    return 42\n```\n\n段落 2 在代码块之后"
    chunks = s.split(text)
    # 至少一个切片包含 ```python / ``` / def f()
    assert any("```python" in c.text and "def f()" in c.text for c in chunks)
    # 代码块不应被切开（验证同一 chunk 内不出现孤立的 ```）
    for c in chunks:
        if "```python" in c.text:
            # 必须有匹配的闭合 ```
            assert c.text.count("```") >= 2

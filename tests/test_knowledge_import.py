"""KnowledgeImport 测试。

> 测试用 httpx multipart 直接构造 files 字段，不走本地文件落盘（in-memory）。
"""

from __future__ import annotations

import io

import pytest
from httpx import AsyncClient


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _txt_file(name: str, content: str) -> tuple[str, io.BytesIO, str]:
    """构造 httpx multipart files 三元组。"""
    return (name, io.BytesIO(content.encode("utf-8")), "text/plain")


@pytest.mark.asyncio
async def test_import_txt_returns_202_with_task_id(
    async_client: AsyncClient, seeded_admin, admin_token, db_session
):
    """POST /knowledge/import 接收 1 个 TXT → 202 + task_id + accepted=1。"""
    files = {"files": _txt_file("hello.txt", "Hello World\n这是导入测试。\n")}
    resp = await async_client.post(
        "/api/v1/knowledge/import",
        files=files,
        headers=_auth(admin_token),
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["accepted_count"] == 1
    assert body["rejected"] == []
    assert body["task_id"].startswith("imp-")


@pytest.mark.asyncio
async def test_import_duplicate_content_rejected(
    async_client: AsyncClient, seeded_admin, admin_token
):
    """同一文件导入两次 → 第二次返回 duplicate_content。"""
    files = {"files": _txt_file("dup.txt", "Duplicate content test.\nA" * 100)}
    r1 = await async_client.post(
        "/api/v1/knowledge/import", files=files, headers=_auth(admin_token)
    )
    assert r1.status_code == 202
    assert r1.json()["accepted_count"] == 1

    r2 = await async_client.post(
        "/api/v1/knowledge/import", files=files, headers=_auth(admin_token)
    )
    assert r2.status_code == 202
    body = r2.json()
    assert body["accepted_count"] == 0
    assert any(item["reason"] == "duplicate_content" for item in body["rejected"])


@pytest.mark.asyncio
async def test_import_unsupported_format(async_client: AsyncClient, seeded_admin, admin_token):
    """不支持的格式 → rejected: unsupported_format。"""
    files = {"files": ("data.xlsx", io.BytesIO(b"fake xlsx content"), "application/vnd.ms-excel")}
    resp = await async_client.post(
        "/api/v1/knowledge/import", files=files, headers=_auth(admin_token)
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["accepted_count"] == 0
    assert any(item["reason"] == "unsupported_format" for item in body["rejected"])


@pytest.mark.asyncio
async def test_import_mixed_files_partial_accept(
    async_client: AsyncClient, seeded_admin, admin_token
):
    """先 r1 导入 2 个新文件 → accepted=2；r2 再导入同 2 个文件 → accepted=0 + rejected=2。"""
    files = [
        ("files", _txt_file("new.txt", "New content unique A1B2C3")),
        ("files", _txt_file("dup.txt", "Dup content batch test ZZZZ")),
    ]
    r1 = await async_client.post(
        "/api/v1/knowledge/import", files=files, headers=_auth(admin_token)
    )
    assert r1.status_code == 202
    assert r1.json()["accepted_count"] == 2

    # 第二次：相同内容 → 全 duplicate
    r2 = await async_client.post(
        "/api/v1/knowledge/import", files=files, headers=_auth(admin_token)
    )
    assert r2.status_code == 202
    assert r2.json()["accepted_count"] == 0
    assert len(r2.json()["rejected"]) == 2
    assert all(item["reason"] == "duplicate_content" for item in r2.json()["rejected"])


@pytest.mark.asyncio
async def test_import_file_size_exceeded_rejected(
    async_client: AsyncClient, seeded_admin, admin_token, monkeypatch
):
    """单文件超 max_upload_size_mb → rejected: size_exceeded。"""
    # 临时降低 max_upload_size_mb 方便测试
    from app.config import settings as s

    monkeypatch.setattr(s.settings, "max_upload_size_mb", 1)  # 1MB

    # 2MB 文件
    big_content = "X" * (2 * 1024 * 1024)
    files = {"files": _txt_file("big.txt", big_content)}
    resp = await async_client.post(
        "/api/v1/knowledge/import", files=files, headers=_auth(admin_token)
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["accepted_count"] == 0
    assert any(item["reason"] == "size_exceeded" for item in body["rejected"])


@pytest.mark.asyncio
async def test_import_requires_knowledge_write_permission(
    async_client: AsyncClient, seeded_admin, seeded_regular_user, regular_user_token
):
    """regular_user 没有 knowledge:write → 403 permission_denied。"""
    files = {"files": _txt_file("test.txt", "Permission check content ABC")}
    resp = await async_client.post(
        "/api/v1/knowledge/import",
        files=files,
        headers=_auth(regular_user_token),
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "permission_denied"


@pytest.mark.asyncio
async def test_import_creates_knowledge_unit_record(
    async_client: AsyncClient, seeded_admin, admin_token, db_session
):
    """导入成功 → DB 中应可查到对应 knowledge_unit 行。"""
    from sqlalchemy import select

    from app.infrastructure.database import KnowledgeUnitRecord

    files = {"files": _txt_file("verify.txt", "Verify record creation ABC123XYZ")}
    resp = await async_client.post(
        "/api/v1/knowledge/import",
        files=files,
        headers=_auth(admin_token),
    )
    assert resp.status_code == 202

    # DB 验证
    row = (
        await db_session.execute(
            select(KnowledgeUnitRecord).where(KnowledgeUnitRecord.source_file_name == "verify.txt")
        )
    ).scalar_one_or_none()
    assert row is not None
    assert row.file_type == "txt"
    assert row.content_hash is not None
    assert len(row.content_hash) == 64
    assert row.status == "active"

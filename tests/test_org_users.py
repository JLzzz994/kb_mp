"""用户管理端点测试（5 用例 + e2e）。"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select as _select

from app.infrastructure.database import DepartmentRecord, RoleRecord, RolePermissionRecord
from app.domain.permission import ALL_PERMISSION_CODES, PermissionCode


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _ensure_role_with_perms(db_session, role_code: str, role_name: str, perms: list[str]) -> int:
    """确保 role + 权限码存在，返回 role_id。同步 fixture 风格。"""
    import asyncio

    async def _do() -> int:
        from app.infrastructure.database import RoleRecord

        existing = (
            await db_session.execute(
                _select(RoleRecord).where(RoleRecord.role_code == role_code)
            )
        ).scalar_one_or_none()
        if existing is None:
            rec = RoleRecord(role_name=role_name, role_code=role_code, description="test")
            db_session.add(rec)
            await db_session.flush()
            rid = rec.id
        else:
            rid = existing.id
        # 重新写权限码
        from app.infrastructure.database import RolePermissionRecord as RP

        await db_session.execute(
            RP.__table__.delete().where(RP.role_id == rid)
        )
        for c in perms:
            db_session.add(RolePermissionRecord(role_id=rid, permission_code=c, permission_type="api"))
        await db_session.commit()
        return rid

    return asyncio.get_event_loop().run_until_complete(_do())


@pytest_asyncio.fixture
async def known_role_ids(db_session, seeded_regular_user) -> dict[str, int]:
    """已知角色 id。默认带 system_admin（来自 seeded_admin）+ regular_user（来自 seeded_regular_user）。
    再额外创建 knowledge_admin 以满足测试用例。"""
    rows = (await db_session.execute(_select(RoleRecord))).scalars().all()
    code_to_id = {r.role_code: r.id for r in rows}

    # 补 knowledge_admin
    if "knowledge_admin" not in code_to_id:
        rec = RoleRecord(
            role_name="知识管理员",
            role_code="knowledge_admin",
            description="test",
        )
        db_session.add(rec)
        await db_session.flush()
        code_to_id["knowledge_admin"] = rec.id
        for c in (
            PermissionCode.KNOWLEDGE_READ,
            PermissionCode.KNOWLEDGE_WRITE,
            PermissionCode.KNOWLEDGE_DELETE,
            PermissionCode.KNOWLEDGE_ASSIGN_PERMISSION,
            PermissionCode.KNOWLEDGE_CHECK,
            PermissionCode.AI_CHAT,
            PermissionCode.DASHBOARD_READ,
            PermissionCode.FAQ_READ,
            PermissionCode.FAQ_WRITE,
            PermissionCode.FAQ_REVIEW,
            PermissionCode.GAP_READ,
        ):
            db_session.add(
                RolePermissionRecord(role_id=rec.id, permission_code=c, permission_type="api")
            )
        await db_session.commit()
    return code_to_id


@pytest_asyncio.fixture
async def extra_dept_id(db_session) -> int:
    """额外创建 1 个顶级部门（user.create 测试需要 department_id）。"""
    dept = DepartmentRecord(name="业务部", parent_id=None, sort_order=0)
    db_session.add(dept)
    await db_session.commit()
    return dept.id


@pytest.mark.asyncio
async def test_list_users_paginated(
    async_client: AsyncClient, seeded_admin, admin_token
):
    """GET /api/v1/org/users 返回分页 + 含 department_name + role_codes。"""
    resp = await async_client.get(
        "/api/v1/org/users?page=1&page_size=10", headers=_auth(admin_token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["page"] == 1
    assert body["page_size"] == 10
    assert body["total"] >= 1
    admin = next(u for u in body["items"] if u["username"] == "admin")
    assert admin["department_name"] == "研发中心"
    assert "system_admin" in admin["role_codes"]
    assert admin["status"] == 1


@pytest.mark.asyncio
async def test_create_user_duplicate_username_returns_409(
    async_client: AsyncClient,
    seeded_admin,
    admin_token,
    known_role_ids,
    extra_dept_id,
):
    """重名 username → 409 username_conflict。"""
    resp = await async_client.post(
        "/api/v1/org/users",
        headers=_auth(admin_token),
        json={
            "username": "admin",  # 已存在
            "password": "Newpass@123",
            "display_name": "重��",
            "department_id": extra_dept_id,
            "role_ids": [known_role_ids["system_admin"]],
        },
    )
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "username_conflict"


@pytest.mark.asyncio
async def test_create_user_password_hashed(
    async_client: AsyncClient,
    seeded_admin,
    admin_token,
    known_role_ids,
    extra_dept_id,
    db_session,
):
    """创建用户的密码经 bcrypt 哈希（$2b$ 开头）。"""
    username = "newuser"
    resp = await async_client.post(
        "/api/v1/org/users",
        headers=_auth(admin_token),
        json={
            "username": username,
            "password": "Newpass@123",
            "display_name": "新用户",
            "department_id": extra_dept_id,
            "role_ids": [known_role_ids["regular_user"]],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["username"] == username

    # DB 中 password_hash 是 bcrypt
    from app.infrastructure.database import UserRecord

    rec = (
        await db_session.execute(_select(UserRecord).where(UserRecord.username == username))
    ).scalar_one()
    assert rec.password_hash.startswith("$2b$")


@pytest.mark.asyncio
async def test_set_status_clears_redis_bitmap(
    async_client: AsyncClient,
    seeded_admin,
    admin_token,
    fake_redis,
):
    """PATCH /users/{id}/status 停用时清 Redis 位图。"""
    user_id = seeded_admin["user_id"]
    bitmap_key = f"auth:bitmap:{user_id}"
    # 1. 登录写入位图
    await async_client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin@123"},
    )
    assert int(await fake_redis.exists(bitmap_key)) == 1

    # 2. 停用
    resp = await async_client.patch(
        f"/api/v1/org/users/{user_id}/status",
        headers=_auth(admin_token),
        json={"status": 0},
    )
    assert resp.status_code == 204
    assert int(await fake_redis.exists(bitmap_key)) == 0


@pytest.mark.asyncio
async def test_reset_password_clears_bitmap(
    async_client: AsyncClient,
    seeded_admin,
    admin_token,
    fake_redis,
):
    """POST /users/{id}/reset-password → 清位图（旧密码 token 失效）。"""
    user_id = seeded_admin["user_id"]
    bitmap_key = f"auth:bitmap:{user_id}"
    await async_client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin@123"},
    )
    assert int(await fake_redis.exists(bitmap_key)) == 1

    resp = await async_client.post(
        f"/api/v1/org/users/{user_id}/reset-password",
        headers=_auth(admin_token),
        json={"new_password": "Newpass@456"},
    )
    assert resp.status_code == 204
    assert int(await fake_redis.exists(bitmap_key)) == 0


@pytest.mark.asyncio
async def test_e2e_admin_full_flow(
    async_client: AsyncClient,
    seeded_admin,
    admin_token,
    known_role_ids,
    extra_dept_id,
):
    """端到端：admin 登录 → 拉部门树 → 创建新用户 → 分配 knowledge_admin → 验证权限流转。"""
    # 1. 登录（admin_token 已隐含通过 seeding + admin_token fixture）

    # 2. 部门树
    tree_resp = await async_client.get(
        "/api/v1/org/departments", headers=_auth(admin_token)
    )
    assert tree_resp.status_code == 200
    assert len(tree_resp.json()) >= 1

    # 3. 创建新用户（knowledge_admin 角色）
    create_resp = await async_client.post(
        "/api/v1/org/users",
        headers=_auth(admin_token),
        json={
            "username": "kmanager",
            "password": "Kmanager@123",
            "display_name": "知识管理员测试",
            "department_id": extra_dept_id,
            "role_ids": [known_role_ids["knowledge_admin"]],
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    new_user = create_resp.json()
    new_user_id = new_user["id"]

    # 4. 用 kmanager 登录 → 验证权限（应含知识管理权限但不含 user:write）
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"username": "kmanager", "password": "Kmanager@123"},
    )
    assert login_resp.status_code == 200
    perms = login_resp.json()["permissions"]
    assert "knowledge:write" in perms
    assert "user:write" not in perms  # 普通知识管理员不应有 user 管理

    # 5. admin 修改新用户状态为停用
    patch_resp = await async_client.patch(
        f"/api/v1/org/users/{new_user_id}/status",
        headers=_auth(admin_token),
        json={"status": 0},
    )
    assert patch_resp.status_code == 204
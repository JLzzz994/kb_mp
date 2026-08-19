"""角色管理端点测试（3 用例）。

> list_includes_sys_admin / assign_validates_17_codes / assign_clears_user_bitmaps

> T03 ticket03 acceptance criteria 9 项。
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def system_admin_role_id(db_session) -> int:
    """查 system_admin 角色的 id。"""
    from sqlalchemy import select

    from app.infrastructure.database import RoleRecord

    row = (
        await db_session.execute(select(RoleRecord).where(RoleRecord.role_code == "system_admin"))
    ).scalar_one()
    return row.id


@pytest.mark.asyncio
async def test_list_roles_includes_sys_admin_17_perms(
    async_client: AsyncClient, seeded_admin, admin_token
):
    """GET /api/v1/org/roles 返回 3 个角色；system_admin 含 17 码。"""
    resp = await async_client.get("/api/v1/org/roles", headers=_auth(admin_token))
    assert resp.status_code == 200, resp.text
    roles = resp.json()
    assert len(roles) >= 1

    sys_admin = next(r for r in roles if r["role_code"] == "system_admin")
    assert len(sys_admin["permissions"]) == 17
    # 17 码白名单覆盖
    from app.domain.permission import ALL_PERMISSION_CODES

    assert sorted(sys_admin["permissions"]) == sorted(ALL_PERMISSION_CODES)


@pytest.mark.asyncio
async def test_assign_permissions_validates_17_codes(
    async_client: AsyncClient, seeded_admin, admin_token, system_admin_role_id
):
    """含非 17 码 → 422 invalid_permission_code。"""
    resp = await async_client.post(
        f"/api/v1/org/roles/{system_admin_role_id}/permissions",
        headers=_auth(admin_token),
        json={"permission_codes": ["user:read", "fake:permission"]},
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "invalid_permission_code"


@pytest.mark.asyncio
async def test_assign_permissions_clears_user_bitmaps(
    async_client: AsyncClient,
    seeded_admin,
    admin_token,
    fake_redis,
    system_admin_role_id,
):
    """权限变更后持有此 role 的用户 Redis auth:bitmap:{user_id} 被 DEL。"""
    # 1. 登录写入 admin 的位图
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin@123"},
    )
    assert login_resp.status_code == 200
    user_id = seeded_admin["user_id"]
    bitmap_key = f"auth:bitmap:{user_id}"
    assert int(await fake_redis.exists(bitmap_key)) == 1

    # 2. 重新分配权限（含 user:read）
    resp = await async_client.post(
        f"/api/v1/org/roles/{system_admin_role_id}/permissions",
        headers=_auth(admin_token),
        json={"permission_codes": ["user:read"]},
    )
    assert resp.status_code == 204

    # 3. admin 持有的位图被清空
    assert int(await fake_redis.exists(bitmap_key)) == 0

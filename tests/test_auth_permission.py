"""RBAC 权限拦截 + 登出 + 位图失效重算测试。

> 借助一个 require_permission 装饰的测试端点做 RBAC 验证，
> 端点注册在模块加载时一次性 include，避免测试间路由污染。
"""

from __future__ import annotations

import pytest
from fastapi import APIRouter, Depends
from httpx import AsyncClient

from app.api.app import app as _app
from app.api.dependencies import CurrentUserDep, require_permission


# ── 模块级注册一次：测试路由 ─────────────────────────────
_test_router = APIRouter(prefix="/api/v1/_perm_test")


@_test_router.get(
    "/admin-only",
    dependencies=[Depends(require_permission("user:read"))],
)
async def admin_only(user: CurrentUserDep) -> dict:
    return {"ok": True, "user": user.username}


_app.include_router(_test_router)


@pytest.mark.asyncio
class TestPermission:
    async def test_admin_can_access_protected_endpoint(
        self, async_client, seeded_admin, admin_token
    ):
        """admin 带 token + 鉴权位图命中 → 通过 require_permission。"""
        await async_client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "Admin@123"},
        )
        resp = await async_client.get(
            "/api/v1/_perm_test/admin-only",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["user"] == "admin"

    async def test_regular_user_cannot_access_admin_endpoint(
        self, async_client, seeded_regular_user, regular_user_token
    ):
        resp = await async_client.get(
            "/api/v1/_perm_test/admin-only",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission_denied"

    async def test_logout_clears_redis_bitmap(
        self, async_client, seeded_admin, admin_token, fake_redis
    ):
        user_id = seeded_admin["user_id"]
        bitmap_key = f"auth:bitmap:{user_id}"

        await async_client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "Admin@123"},
        )
        # fake_redis.exists 返回 int(1) / int(0)
        assert int(await fake_redis.exists(bitmap_key)) == 1

        resp = await async_client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 204
        assert int(await fake_redis.exists(bitmap_key)) == 0

    async def test_bitmap_miss_auto_recomputes(
        self, async_client, seeded_admin, admin_token, fake_redis
    ):
        """[必须修复] #3: Redis 位图缺失（TTL 过期 / 重启）→ 自动重算权限，
        受保护端点仍可通过，而不是全部 403。"""
        user_id = seeded_admin["user_id"]
        bitmap_key = f"auth:bitmap:{user_id}"
        # 模拟位图丢失（从未登录 / TTL 过期 / DEL 后）
        assert int(await fake_redis.exists(bitmap_key)) == 0

        # 受保护端点应仍可通过（permissions 自动从 DB 重算）
        resp = await async_client.get(
            "/api/v1/_perm_test/admin-only",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200, resp.text
        # 位图被自动回写
        assert int(await fake_redis.exists(bitmap_key)) == 1
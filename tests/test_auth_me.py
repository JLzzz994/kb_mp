"""GET /api/v1/auth/me 端点测试。"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
class TestMe:
    async def test_me_with_valid_token_returns_user_info(self, async_client, admin_token):
        resp = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["user_info"]["username"] == "admin"
        assert "user:read" in body["permissions"]

    async def test_me_without_token_returns_401(self, async_client):
        resp = await async_client.get("/api/v1/auth/me")
        assert resp.status_code == 401
        assert resp.json()["error_code"] == "authentication_required"

    async def test_me_with_malformed_token_returns_401(self, async_client):
        resp = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer not.a.jwt"},
        )
        assert resp.status_code == 401
        assert resp.json()["error_code"] == "invalid_access_token"

    async def test_me_with_expired_token_returns_401(self, async_client, expired_token):
        resp = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert resp.status_code == 401
        assert resp.json()["error_code"] == "invalid_access_token"

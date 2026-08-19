"""登录端点测试。"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestLogin:
    """POST /api/v1/auth/login 三种状态：成功 / 凭据错 / 账号停用。"""

    async def test_login_success_returns_token_and_17_perms(
        self, async_client: AsyncClient, seeded_admin
    ):
        req = {"username": "admin", "password": "Admin@123"}
        resp = await async_client.post("/api/v1/auth/login", json=req)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert isinstance(body["access_token"], str) and len(body["access_token"]) > 50
        assert body["expires_in"] == 480 * 60
        assert body["user_info"]["username"] == "admin"
        assert body["user_info"]["role_codes"] == ["system_admin"]
        assert "user:read" in body["permissions"]
        assert "user:write" in body["permissions"]
        assert len(body["permissions"]) == 17

    async def test_login_wrong_password_returns_invalid_credentials(
        self, async_client, seeded_admin
    ):
        resp = await async_client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "WrongPassword"},
        )
        assert resp.status_code == 401
        assert resp.json()["error_code"] == "invalid_credentials"

    async def test_login_nonexistent_user_returns_invalid_credentials(
        self, async_client, seeded_admin
    ):
        """不存在的用户同样返回 invalid_credentials（防枚举）。"""
        resp = await async_client.post(
            "/api/v1/auth/login",
            json={"username": "ghost_user", "password": "anything"},
        )
        assert resp.status_code == 401
        assert resp.json()["error_code"] == "invalid_credentials"

    async def test_login_disabled_user_returns_user_disabled(
        self, async_client, seeded_disabled_user
    ):
        resp = await async_client.post(
            "/api/v1/auth/login",
            json={"username": "disabled", "password": "Pass@1234"},
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "user_disabled"

    async def test_login_validation_username_too_short(self, async_client):
        resp = await async_client.post(
            "/api/v1/auth/login", json={"username": "ab", "password": "Pass@1234"}
        )
        assert resp.status_code == 422

    async def test_login_validation_password_too_short(self, async_client):
        resp = await async_client.post(
            "/api/v1/auth/login", json={"username": "validuser", "password": "12345"}
        )
        assert resp.status_code == 422
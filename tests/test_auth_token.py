"""JWT 签发 / 校验单元测试。"""

from __future__ import annotations

import pytest

from app.infrastructure.jwt import JWTIssuer
from app.common.errors import InvalidAccessTokenError


class TestJWTIssuer:
    def test_token_decode_returns_payload(self):
        issuer = JWTIssuer(secret="test-secret", expire_minutes=10)
        token, expires_in = issuer.issue(user_id=42, username="alice", role_codes=["regular_user"])
        payload = issuer.verify(token)
        assert payload.sub == "42"
        assert payload.username == "alice"
        assert payload.role_codes == ["regular_user"]
        assert expires_in > 0

    def test_token_expired_raises(self):
        expired = JWTIssuer(secret="test-secret", expire_minutes=-1)
        token, _ = expired.issue(user_id=1, username="alice", role_codes=[])
        with pytest.raises(InvalidAccessTokenError):
            JWTIssuer(secret="test-secret", expire_minutes=10).verify(token)

    def test_token_invalid_signature_raises(self):
        token, _ = JWTIssuer(secret="secret-A", expire_minutes=10).issue(
            user_id=1, username="alice", role_codes=[]
        )
        with pytest.raises(InvalidAccessTokenError):
            JWTIssuer(secret="secret-B", expire_minutes=10).verify(token)

    def test_token_malformed_raises(self):
        with pytest.raises(InvalidAccessTokenError):
            JWTIssuer(secret="test", expire_minutes=10).verify("not.a.jwt")
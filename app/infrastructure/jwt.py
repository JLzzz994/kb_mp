"""JWT 签发 / 校验（HS256）。

> 锁定决策 Q1：JWT secret 来源 .env 硬编码（演示期）。
> 锁定决策见 docs/CONTEXT.md §Q1 + 接口约定 §6 / Spec M1 §8。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.common.errors import InvalidAccessTokenError
from app.config.settings import settings


@dataclass(slots=True)
class TokenPayload:
    """JWT payload 解码后的领域对象。"""

    sub: str  # user_id（字符串存储避免精度问题）
    username: str
    role_codes: list[str]
    exp: int


class JWTIssuer:
    """JWT 签发 / 校验。

    - issue: 签发 access_token（HS256，过期 = settings.jwt_expire_minutes 分钟）
    - verify: 校验签名 + 过期时间；失败抛 InvalidAccessTokenError
    """

    def __init__(
        self,
        secret: str | None = None,
        algorithm: str | None = None,
        expire_minutes: int | None = None,
    ) -> None:
        self._secret = secret or settings.jwt_secret
        self._algorithm = algorithm or settings.jwt_algorithm
        self._expire_minutes = expire_minutes or settings.jwt_expire_minutes

    def issue(self, user_id: int, username: str, role_codes: list[str]) -> tuple[str, int]:
        """签发 JWT，返回 (token, expires_in_seconds)。"""
        now = datetime.now(tz=UTC)
        expire = now + timedelta(minutes=self._expire_minutes)
        payload = {
            "sub": str(user_id),
            "username": username,
            "role_codes": list(role_codes),
            "iat": int(now.timestamp()),
            "exp": int(expire.timestamp()),
        }
        token = jwt.encode(payload, self._secret, algorithm=self._algorithm)
        return token, int((expire - now).total_seconds())

    def verify(self, token: str) -> TokenPayload:
        """校验 JWT，返回 TokenPayload。失败抛 InvalidAccessTokenError。"""
        try:
            data = jwt.decode(token, self._secret, algorithms=[self._algorithm])
        except jwt.ExpiredSignatureError as exc:
            raise InvalidAccessTokenError("token_expired") from exc
        except jwt.InvalidTokenError as exc:
            raise InvalidAccessTokenError(f"invalid_token: {exc!s}") from exc

        return TokenPayload(
            sub=str(data["sub"]),
            username=str(data.get("username", "")),
            role_codes=list(data.get("role_codes", [])),
            exp=int(data["exp"]),
        )


_jwt_issuer_singleton: JWTIssuer | None = None


def get_jwt_issuer() -> JWTIssuer:
    """FastAPI 依赖注入：返回全局 JWTIssuer 单例。"""
    global _jwt_issuer_singleton
    if _jwt_issuer_singleton is None:
        _jwt_issuer_singleton = JWTIssuer()
    return _jwt_issuer_singleton

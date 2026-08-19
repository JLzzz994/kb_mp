"""bcrypt 密码哈希（cost=12）。

> 锁定决策 Q2：测试 cost=4，生产 cost=12；本模块默认 12，启动时从 settings 读取。
> pytest 环境若需加速，注入 cost=4 覆盖；详见 tests/conftest.py。
"""

from __future__ import annotations

import bcrypt

from app.config.settings import settings


class PasswordHasher:
    """bcrypt 密码哈希 / 校验。

    - hash: 明文 → bcrypt 哈希（cost 取自 settings）
    - verify: 明文 + 哈希 → bool；不抛异常
    """

    def __init__(self, cost: int | None = None) -> None:
        self._cost = cost or settings.bcrypt_cost

    def hash(self, plaintext: str) -> str:
        """生成 bcrypt 哈希。"""
        salt = bcrypt.gensalt(rounds=self._cost)
        return bcrypt.hashpw(plaintext.encode("utf-8"), salt).decode("utf-8")

    def verify(self, plaintext: str, hashed: str) -> bool:
        """校验明文是否匹配哈希。"""
        if not hashed:
            return False
        try:
            return bcrypt.checkpw(plaintext.encode("utf-8"), hashed.encode("utf-8"))
        except (ValueError, TypeError):
            return False


_password_hasher_singleton: PasswordHasher | None = None


def get_password_hasher() -> PasswordHasher:
    """FastAPI 依赖注入：返回全局 PasswordHasher 单例。"""
    global _password_hasher_singleton
    if _password_hasher_singleton is None:
        _password_hasher_singleton = PasswordHasher()
    return _password_hasher_singleton

"""Redis 客户端抽象：鉴权位图 + 通用 KV。

> **职责分层**（Phase 4 low 修复，IMPL-M3 §7 与 IMPL-M1 §2.4 对齐）：
> - 鉴权位图专用方法：`set_bitmap / get_bitmap / del_bitmap`（封装 key=`auth:bitmap:{user_id}` 与 TTL）
> - 通用 KV 方法：`set / get / delete`（供 FAQ 缓存、临时键等非位图场景使用）
>
> 这样上层 Service（AuthService / KnowledgePermissionService）只需调用语义化方法，
> 不再自己拼接 Redis key 字符串，避免 Phase 1-2 期间出现的 key 漂移 bug（C1 教训）。
"""
from __future__ import annotations

import json
from typing import Any

import redis.asyncio as redis_async

from app.config.settings import settings


AUTH_BITMAP_KEY_PREFIX = "auth:bitmap:"
AUTH_BITMAP_NAMESPACE = "auth:bitmap"


class RedisClient:
    """Redis 异步客户端封装。

    - `set_bitmap / get_bitmap / del_bitmap`：鉴权位图专用，封装 key 前缀与 TTL
    - `set / get / delete`：通用 KV，供 FAQ 缓存（faq:cache:<hash>）、临时键等使用
    """

    def __init__(self, client: redis_async.Redis | None = None) -> None:
        self._client = client or redis_async.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )

    # ===== 鉴权位图（IMPL-M1 / IMPL-M3 共用） =====

    @staticmethod
    def _bitmap_key(user_id: int) -> str:
        return f"{AUTH_BITMAP_KEY_PREFIX}{user_id}"

    async def set_bitmap(
        self,
        *,
        user_id: int,
        permissions: list[str],
        ttl: int,
    ) -> None:
        """写入用户鉴权位图（key: `auth:bitmap:{user_id}`，TTL 秒）。

        - 持久化为 JSON 数组字符串（与 `get_bitmap` 配对）
        - TTL 由调用方传入（典型值 `settings.auth_bitmap_ttl_seconds`）
        """
        await self._client.set(
            self._bitmap_key(user_id),
            json.dumps(permissions),
            ex=ttl,
        )

    async def get_bitmap(self, user_id: int) -> list[str] | None:
        """读取用户鉴权位图；不存在 / 过期返回 None。

        - 反序列化失败时返回 None，触发上层重算路径
        """
        raw = await self._client.get(self._bitmap_key(user_id))
        if raw is None:
            return None
        try:
            value = json.loads(raw)
        except (ValueError, TypeError):
            return None
        if not isinstance(value, list):
            return None
        return [str(x) for x in value]

    async def del_bitmap(self, user_id: int) -> None:
        """删除用户鉴权位图（登出 / 权限变更时调用）。"""
        await self._client.delete(self._bitmap_key(user_id))

    async def del_bitmaps_by_role(self, role_id: int, user_ids: list[int]) -> int:
        """批量删除指定 user_ids 列表的鉴权位图（M2 角色权限变更调用）。

        返回实际删除的数量。
        """
        if not user_ids:
            return 0
        keys = [self._bitmap_key(uid) for uid in user_ids]
        return int(await self._client.delete(*keys))

    # ===== 通用 KV（FAQ 缓存、临时键等） =====

    async def set(
        self,
        key: str,
        value: Any,
        ex: int | None = None,
    ) -> None:
        """通用 SET：支持 `ex` 秒级 TTL。

        value 非字符串时由调用方负责序列化（避免隐式行为）；推荐使用 `json.dumps` 后传入。
        """
        await self._client.set(key, value, ex=ex)

    async def get(self, key: str) -> Any:
        """通用 GET：返回原始字符串 / bytes（由调用方反序列化）。"""
        return await self._client.get(key)

    async def delete(self, key: str) -> int:
        """通用 DEL：返回删除条目数。"""
        return int(await self._client.delete(key))

    async def exists(self, key: str) -> bool:
        """通用 EXISTS。"""
        return bool(await self._client.exists(key))

    # ===== 哈希（FAQ 缓存 HSET/HGETALL/DEL 用） =====

    async def hset(self, key: str, mapping: dict[str, Any]) -> int:
        await self._client.hset(key, mapping=mapping)
        return 1

    async def hgetall(self, key: str) -> dict[str, str]:
        raw = await self._client.hgetall(key)
        return {str(k): str(v) for k, v in raw.items()}

    async def hdel(self, key: str, *fields: str) -> int:
        if not fields:
            return 0
        return int(await self._client.hdel(key, *fields))


# ===== 依赖注入辅助（与 FastAPI 集成） =====

_singleton: RedisClient | None = None


def get_redis() -> RedisClient:
    """FastAPI 依赖：返回全局 RedisClient 单例。"""
    global _singleton
    if _singleton is None:
        _singleton = RedisClient()
    return _singleton
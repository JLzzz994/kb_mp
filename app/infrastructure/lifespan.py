"""应用启动 / 关闭钩子。

> 锁定决策（ADR-0003 / docs/CONTEXT.md Q4）：
> - 启动时 `redis_client.ping()` 失败 → `raise RuntimeError("redis unavailable")`，uvicorn 启动失败
> - 不做进程内 dict fallback（鉴权位图失效 = 越权风险）
> - pytest 环境（`PYTEST_CURRENT_TEST` 存在）跳过 ping，避免依赖 Redis
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.common.logging import configure_logging
from app.infrastructure.redis_client import get_redis


def _is_pytest() -> bool:
    """检测是否在 pytest 中运行（避免依赖外部 Redis）。"""
    return bool(os.environ.get("PYTEST_CURRENT_TEST")) or "PYTEST_VERSION" in os.environ


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """启动 / 关闭钩子：初始化 Redis ping + 关闭客户端。"""
    configure_logging()

    if not _is_pytest():
        # 启动 fast-fail（ADR-0003 决策 1）
        redis = get_redis()
        await redis.ping()
        app.state.redis = redis

    try:
        yield
    finally:
        # 关闭：断开 Redis 连接
        if not _is_pytest():
            try:
                await redis.aclose()
            except Exception:  # noqa: BLE001 — 关闭阶段吞异常
                pass
